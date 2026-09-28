"""Durable local reservations for provider-request token and cost budgets.

The ledger records request metadata and budget accounting only. Price rates are
supplied by the caller, not authenticated provider prices or billing receipts.
Callers must not put prompts, credentials, or provider response bodies here.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
from pathlib import Path
from typing import Any, Iterator


class BudgetError(ValueError):
    """A budget reservation or settlement cannot safely be accepted."""


class TokenBudgetExhausted(BudgetError):
    """The token or request cap rejects a request before provider send."""


class CostBudgetExhausted(BudgetError):
    """The configured cost cap rejects a request before provider send."""


_SCHEMA_1 = 1
_SCHEMA_2 = 2
_LEDGER_NAME = "ledger.json"
_LOCK_NAME = ".lock"
_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_ROLE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")
_USAGE_KEYS = {"input_tokens", "output_tokens", "total_tokens"}
_REQUEST_KEYS_1 = {
    "request_id", "role", "payload_sha256", "input_tokens", "max_output_tokens",
    "state", "held_tokens", "usage", "reason_sha256",
}
_REQUEST_KEYS_2 = _REQUEST_KEYS_1 | {
    "model", "held_cost_micro_usd", "usage_details",
}
_LEDGER_KEYS_1 = {"schema", "limit_tokens", "max_requests", "requests"}
_LEDGER_KEYS_2 = _LEDGER_KEYS_1 | {
    "cost_limit_micro_usd", "price_profile", "price_profile_sha256",
}
_PRICE_KEYS = {
    "model", "input_rate_micro_usd_per_million",
    "cached_input_rate_micro_usd_per_million",
    "cache_write_rate_micro_usd_per_million",
    "output_rate_micro_usd_per_million",
}
_MICRO_USD_PER_MILLION_TOKENS = 1_000_000


def _canonical(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=True, sort_keys=True,
                           separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise BudgetError("ledger value is not canonical JSON") from exc


def _exact_nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise BudgetError(f"{label} must be a nonnegative integer")
    return value


def _price_profile(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _PRICE_KEYS:
        raise BudgetError("price_profile has missing or unexpected fields")
    model = value["model"]
    if type(model) is not str or not model.strip() or len(model) > 128:
        raise BudgetError("price_profile model must be a nonempty exact model name")
    for key in _PRICE_KEYS - {"model"}:
        _exact_nonnegative_int(value[key], f"price_profile {key}")
    if (value["input_rate_micro_usd_per_million"] == 0
            or value["output_rate_micro_usd_per_million"] == 0):
        raise BudgetError("price_profile input and output rates must be positive")
    return dict(value)


def _ceil_micro_usd(numerator: int) -> int:
    return (numerator + _MICRO_USD_PER_MILLION_TOKENS - 1) // _MICRO_USD_PER_MILLION_TOKENS


def _max_input_rate(profile: dict[str, Any]) -> int:
    return max(
        profile["input_rate_micro_usd_per_million"],
        profile["cached_input_rate_micro_usd_per_million"],
        profile["cache_write_rate_micro_usd_per_million"],
    )


def _reserved_cost(input_tokens: int, max_output_tokens: int,
                   profile: dict[str, Any]) -> int:
    return _ceil_micro_usd(
        input_tokens * _max_input_rate(profile)
        + max_output_tokens * profile["output_rate_micro_usd_per_million"]
    )


def _settled_cost(usage: dict[str, int], details: Any,
                  profile: dict[str, Any]) -> int:
    """Price known input classes; conservatively price unclassified input."""
    if details is not None and type(details) is not dict:
        raise BudgetError("usage_details must be an object")
    details = details or {}
    input_details = details.get("input_tokens_details", {})
    output_details = details.get("output_tokens_details", {})
    if type(input_details) is not dict or type(output_details) is not dict:
        raise BudgetError("usage detail groups must be objects")
    known = {"cached_tokens", "cache_read_tokens", "cache_write_tokens", "uncached_tokens"}
    for key in known & input_details.keys():
        _exact_nonnegative_int(input_details[key], f"usage_details {key}")
    if "reasoning_tokens" in output_details:
        reasoning = _exact_nonnegative_int(output_details["reasoning_tokens"],
                                           "usage_details reasoning_tokens")
        if reasoning > usage["output_tokens"]:
            raise BudgetError("reasoning_tokens exceeds output_tokens")
    if ("cached_tokens" in input_details and "cache_read_tokens" in input_details
            and input_details["cached_tokens"] != input_details["cache_read_tokens"]):
        raise BudgetError("cache read aliases disagree")
    cache_read = input_details.get("cache_read_tokens", input_details.get("cached_tokens", 0))
    cache_write = input_details.get("cache_write_tokens", 0)
    uncached = input_details.get("uncached_tokens", 0)
    classified = cache_read + cache_write + uncached
    if classified > usage["input_tokens"]:
        raise BudgetError("input usage details exceed input_tokens")
    unknown = usage["input_tokens"] - classified
    numerator = (
        cache_read * profile["cached_input_rate_micro_usd_per_million"]
        + cache_write * profile["cache_write_rate_micro_usd_per_million"]
        + uncached * profile["input_rate_micro_usd_per_million"]
        + unknown * _max_input_rate(profile)
        + usage["output_tokens"] * profile["output_rate_micro_usd_per_million"]
    )
    return _ceil_micro_usd(numerator)


def _private_directory(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise BudgetError("ledger directory is unavailable") from exc
    if (stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700):
        raise BudgetError("ledger directory must be owned by this user with mode 0700")


def _private_regular_file(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise BudgetError("ledger file is unavailable") from exc
    if (stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600):
        raise BudgetError("ledger files must be owned by this user with mode 0600")


class TokenLedger:
    """A process-safe, fail-closed budget with one unresolved send at a time."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        _private_directory(self.directory)
        _private_regular_file(self.directory / _LEDGER_NAME)
        _private_regular_file(self.directory / _LOCK_NAME)
        self._read_unlocked()

    @classmethod
    def create(cls, directory: Path, limit_tokens: int, max_requests: int, *,
               cost_limit_micro_usd: int | None = None,
               price_profile: dict[str, Any] | None = None) -> TokenLedger:
        """Exclusively create a private ledger; cost accounting is optional.

        The profile is operator-supplied and is not an authenticated tariff.
        """
        if type(limit_tokens) is not int or limit_tokens < 1:
            raise BudgetError("limit_tokens must be a positive integer")
        if type(max_requests) is not int or max_requests < 1:
            raise BudgetError("max_requests must be a positive integer")
        if (cost_limit_micro_usd is None) != (price_profile is None):
            raise BudgetError("cost_limit_micro_usd and price_profile must be supplied together")
        profile: dict[str, Any] | None = None
        if cost_limit_micro_usd is not None:
            if type(cost_limit_micro_usd) is not int or cost_limit_micro_usd < 0:
                raise BudgetError("cost_limit_micro_usd must be a nonnegative integer")
            profile = _price_profile(price_profile)
        path = Path(directory)
        try:
            path.mkdir(mode=0o700)
            path.chmod(0o700)
        except OSError as exc:
            raise BudgetError("ledger directory must be newly and exclusively created") from exc
        _private_directory(path)
        lock_path = path / _LOCK_NAME
        try:
            fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                os.fchmod(fd, 0o600)
                os.fsync(fd)
            finally:
                os.close(fd)
            ledger = {
                "schema": _SCHEMA_2 if profile is not None else _SCHEMA_1,
                "limit_tokens": limit_tokens,
                "max_requests": max_requests, "requests": {},
            }
            if profile is not None:
                ledger.update({
                    "cost_limit_micro_usd": cost_limit_micro_usd,
                    "price_profile": profile,
                    "price_profile_sha256": hashlib.sha256(_canonical(profile)).hexdigest(),
                })
            cls._write_atomic(path, ledger)
            cls._fsync_directory(path)
            cls._fsync_directory(path.parent)
        except OSError as exc:
            raise BudgetError("could not initialize private token ledger") from exc
        return cls(path)

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @staticmethod
    def _write_atomic(directory: Path, value: dict[str, Any]) -> None:
        target = directory / _LEDGER_NAME
        temporary = directory / f".{_LEDGER_NAME}.{secrets.token_hex(16)}.tmp"
        data = _canonical(value)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, target)
        TokenLedger._fsync_directory(directory)

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        _private_directory(self.directory)
        lock_path = self.directory / _LOCK_NAME
        _private_regular_file(lock_path)
        fd = os.open(lock_path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            _private_directory(self.directory)
            _private_regular_file(lock_path)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def _read_unlocked(self) -> dict[str, Any]:
        path = self.directory / _LEDGER_NAME
        _private_regular_file(path)
        try:
            raw = path.read_bytes()
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=self._unique_pairs,
                               parse_constant=self._reject_constant)
        except BudgetError:
            raise
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            raise BudgetError("token ledger is unreadable or invalid JSON") from exc
        if type(value) is not dict or type(value.get("schema")) is not int:
            raise BudgetError("token ledger has an invalid structure")
        expected = (_LEDGER_KEYS_1 if value["schema"] == _SCHEMA_1
                    else _LEDGER_KEYS_2 if value["schema"] == _SCHEMA_2 else None)
        if expected is None:
            raise BudgetError("token ledger schema is unsupported")
        if set(value) != expected:
            raise BudgetError("token ledger has an invalid structure")
        if raw != _canonical(value):
            raise BudgetError("token ledger is not canonical JSON")
        self._validate(value)
        return value

    @staticmethod
    def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise BudgetError("token ledger contains a duplicate key")
            result[key] = value
        return result

    @staticmethod
    def _reject_constant(value: str) -> None:
        raise BudgetError(f"token ledger contains invalid numeric constant {value}")

    @staticmethod
    def _validate(value: dict[str, Any]) -> None:
        schema = value["schema"]
        if schema not in {_SCHEMA_1, _SCHEMA_2}:
            raise BudgetError("token ledger schema is unsupported")
        if type(value["limit_tokens"]) is not int or value["limit_tokens"] < 1:
            raise BudgetError("token ledger limit is invalid")
        if type(value["max_requests"]) is not int or value["max_requests"] < 1:
            raise BudgetError("token ledger request cap is invalid")
        profile = None
        if schema == _SCHEMA_2:
            if (type(value["cost_limit_micro_usd"]) is not int
                    or value["cost_limit_micro_usd"] < 0):
                raise BudgetError("token ledger cost limit is invalid")
            profile = _price_profile(value["price_profile"])
            digest = hashlib.sha256(_canonical(profile)).hexdigest()
            if value["price_profile_sha256"] != digest:
                raise BudgetError("token ledger price profile digest is invalid")
        requests = value["requests"]
        if type(requests) is not dict or len(requests) > value["max_requests"]:
            raise BudgetError("token ledger request set is invalid")
        for request_id, record in requests.items():
            if (type(request_id) is not str or _IDENTIFIER_RE.fullmatch(request_id) is None
                    or type(record) is not dict
                    or set(record) != (_REQUEST_KEYS_2 if profile is not None
                                       else _REQUEST_KEYS_1)
                    or record["request_id"] != request_id
                    or type(record["role"]) is not str
                    or _ROLE_RE.fullmatch(record["role"]) is None
                    or type(record["payload_sha256"]) is not str
                    or _DIGEST_RE.fullmatch(record["payload_sha256"]) is None):
                raise BudgetError("token ledger contains invalid request metadata")
            if profile is not None:
                if (record["model"] != profile["model"]
                        or type(record["held_cost_micro_usd"]) is not int
                        or record["held_cost_micro_usd"] < 0):
                    raise BudgetError("token ledger contains invalid cost metadata")
            input_tokens = record["input_tokens"]
            output_cap = record["max_output_tokens"]
            held = record["held_tokens"]
            if (type(input_tokens) is not int or input_tokens < 0
                    or type(output_cap) is not int or output_cap < 0
                    or type(held) is not int or held < 0):
                raise BudgetError("token ledger contains invalid token counts")
            state = record["state"]
            if type(state) is not str or state not in {"reserved", "settled", "indeterminate"}:
                raise BudgetError("token ledger contains an invalid request state")
            usage = record["usage"]
            reason_digest = record["reason_sha256"]
            if state == "reserved":
                if (held != input_tokens + output_cap or usage is not None
                        or reason_digest is not None):
                    raise BudgetError("token ledger reservation is inconsistent")
                if (profile is not None
                        and (record["held_cost_micro_usd"] !=
                             _reserved_cost(input_tokens, output_cap, profile)
                             or record["usage_details"] is not None)):
                    raise BudgetError("token ledger cost reservation is inconsistent")
            elif state == "settled":
                if (type(usage) is not dict or set(usage) != _USAGE_KEYS
                        or any(type(usage[key]) is not int or usage[key] < 0 for key in _USAGE_KEYS)
                        or usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]
                        or usage["input_tokens"] != input_tokens
                        or usage["output_tokens"] > output_cap
                        or held != usage["total_tokens"] or reason_digest is not None):
                    raise BudgetError("token ledger settlement is inconsistent")
                if profile is not None:
                    cost = _settled_cost(usage, record["usage_details"], profile)
                    if (record["held_cost_micro_usd"] != cost
                            or cost > _reserved_cost(input_tokens, output_cap, profile)):
                        raise BudgetError("token ledger cost settlement is inconsistent")
            else:
                if (held != input_tokens + output_cap or usage is not None
                        or type(reason_digest) is not str
                        or _DIGEST_RE.fullmatch(reason_digest) is None):
                    raise BudgetError("token ledger indeterminate reservation is inconsistent")
                if (profile is not None
                        and (record["held_cost_micro_usd"] !=
                             _reserved_cost(input_tokens, output_cap, profile)
                             or record["usage_details"] is not None)):
                    raise BudgetError("token ledger indeterminate cost is inconsistent")
        committed = sum(record["held_tokens"] for record in requests.values())
        if committed > value["limit_tokens"]:
            raise BudgetError("token ledger exceeds its token limit")
        if (profile is not None
                and sum(record["held_cost_micro_usd"] for record in requests.values())
                > value["cost_limit_micro_usd"]):
            raise BudgetError("token ledger exceeds its cost limit")

    @staticmethod
    def _validate_request(request_id: str, role: str, payload_sha256: str,
                          input_tokens: int, max_output_tokens: int) -> None:
        if type(request_id) is not str or _IDENTIFIER_RE.fullmatch(request_id) is None:
            raise BudgetError("request_id must be a short metadata identifier")
        if type(role) is not str or _ROLE_RE.fullmatch(role) is None:
            raise BudgetError("role must be a short metadata label")
        if type(payload_sha256) is not str or _DIGEST_RE.fullmatch(payload_sha256) is None:
            raise BudgetError("payload_sha256 must be a lowercase SHA-256 digest")
        _exact_nonnegative_int(input_tokens, "input_tokens")
        _exact_nonnegative_int(max_output_tokens, "max_output_tokens")

    def reserve(self, request_id: str, role: str, payload_sha256: str,
                input_tokens: int, max_output_tokens: int, *,
                model: str | None = None) -> dict[str, Any]:
        """Persist the full request allowance before returning permission to send."""
        self._validate_request(request_id, role, payload_sha256, input_tokens, max_output_tokens)
        with self._locked():
            ledger = self._read_unlocked()
            requests = ledger["requests"]
            if request_id in requests:
                raise BudgetError("request_id has already been reserved")
            if len(requests) >= ledger["max_requests"]:
                raise TokenBudgetExhausted("token ledger request cap exhausted")
            profile = ledger.get("price_profile")
            if profile is not None and (type(model) is not str or model != profile["model"]):
                raise BudgetError("request model must exactly match price_profile model")
            if any(record["state"] == "indeterminate" for record in requests.values()):
                raise BudgetError("token ledger is blocked by an indeterminate request")
            if any(record["state"] == "reserved" for record in requests.values()):
                raise BudgetError("token ledger is blocked by an unresolved reserved request")
            held = sum(record["held_tokens"] for record in requests.values())
            requested = input_tokens + max_output_tokens
            if requested > ledger["limit_tokens"] - held:
                raise TokenBudgetExhausted("token budget exhausted before provider request")
            requested_cost = None
            if profile is not None:
                requested_cost = _reserved_cost(input_tokens, max_output_tokens, profile)
                committed_cost = sum(record["held_cost_micro_usd"]
                                     for record in requests.values())
                if requested_cost > ledger["cost_limit_micro_usd"] - committed_cost:
                    raise CostBudgetExhausted("cost budget exhausted before provider request")
            record = {
                "request_id": request_id, "role": role,
                "payload_sha256": payload_sha256, "input_tokens": input_tokens,
                "max_output_tokens": max_output_tokens, "state": "reserved",
                "held_tokens": requested, "usage": None, "reason_sha256": None,
            }
            if profile is not None:
                record.update({"model": model, "held_cost_micro_usd": requested_cost,
                               "usage_details": None})
            requests[request_id] = record
            self._write_atomic(self.directory, ledger)
            return dict(record)

    def _mark_indeterminate_unlocked(self, ledger: dict[str, Any], request_id: str,
                                     reason: str) -> dict[str, Any]:
        record = ledger["requests"].get(request_id)
        if record is None:
            raise BudgetError("request_id is not present in the token ledger")
        if record["state"] == "settled":
            raise BudgetError("settled request cannot become indeterminate")
        if record["state"] == "reserved":
            record["state"] = "indeterminate"
            # Keep caller text out of the durable record; retain only a digest.
            record["reason_sha256"] = hashlib.sha256(reason.encode("utf-8")).hexdigest()
            self._write_atomic(self.directory, ledger)
        return dict(record)

    def mark_indeterminate(self, request_id: str, reason: str) -> dict[str, Any]:
        """Spend an unresolved reservation and block later reservations."""
        if type(request_id) is not str or _IDENTIFIER_RE.fullmatch(request_id) is None:
            raise BudgetError("request_id must be a short metadata identifier")
        if type(reason) is not str or not reason:
            raise BudgetError("reason must be a nonempty string")
        with self._locked():
            return self._mark_indeterminate_unlocked(self._read_unlocked(), request_id, reason)

    def settle(self, request_id: str, usage: dict[str, Any], *,
               usage_details: dict[str, Any] | None = None) -> dict[str, Any]:
        """Reconcile a request; invalid telemetry makes its reservation indeterminate."""
        if type(request_id) is not str or _IDENTIFIER_RE.fullmatch(request_id) is None:
            raise BudgetError("request_id must be a short metadata identifier")
        with self._locked():
            ledger = self._read_unlocked()
            record = ledger["requests"].get(request_id)
            if record is None:
                raise BudgetError("request_id is not present in the token ledger")
            if record["state"] != "reserved":
                raise BudgetError("only a reserved request can be settled")
            error: str | None = None
            if type(usage) is not dict or set(usage) != _USAGE_KEYS:
                error = "usage fields are missing or unexpected"
            elif any(type(usage[key]) is not int or usage[key] < 0 for key in _USAGE_KEYS):
                error = "usage token counts must be nonnegative integers"
            elif usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]:
                error = "usage total does not equal input plus output"
            elif usage["input_tokens"] != record["input_tokens"]:
                error = "measured input differs from the counted request input"
            elif usage["output_tokens"] > record["max_output_tokens"]:
                error = "measured output exceeds the reserved output cap"
            cost = None
            details = None
            if error is None and ledger["schema"] == _SCHEMA_2:
                try:
                    details = (None if usage_details is None
                               else json.loads(_canonical(usage_details)))
                    cost = _settled_cost(usage, details, ledger["price_profile"])
                    if cost > record["held_cost_micro_usd"]:
                        raise BudgetError("measured cost exceeds the reservation")
                except BudgetError as exc:
                    error = str(exc)
            if error is not None:
                self._mark_indeterminate_unlocked(ledger, request_id, error)
                raise BudgetError(error)
            record["state"] = "settled"
            record["held_tokens"] = usage["total_tokens"]
            record["usage"] = dict(usage)
            if ledger["schema"] == _SCHEMA_2:
                record["held_cost_micro_usd"] = cost
                record["usage_details"] = details
            self._write_atomic(self.directory, ledger)
            return dict(record)

    def status(self) -> dict[str, Any]:
        """Return aggregate accounting and metadata-only request records."""
        with self._locked():
            ledger = self._read_unlocked()
            requests = ledger["requests"]
            reserved = sum(record["held_tokens"] for record in requests.values()
                           if record["state"] == "reserved")
            indeterminate = sum(record["held_tokens"] for record in requests.values()
                                if record["state"] == "indeterminate")
            settled = sum(record["held_tokens"] for record in requests.values()
                          if record["state"] == "settled")
            committed = reserved + indeterminate + settled
            cost_keys = {
                "cost_limit_micro_usd": None,
                "reserved_cost_micro_usd": None,
                "indeterminate_cost_micro_usd": None,
                "settled_cost_micro_usd": None,
                "committed_cost_micro_usd": None,
                "remaining_cost_micro_usd": None,
                "price_profile": None,
                "price_profile_sha256": None,
            }
            if ledger["schema"] == _SCHEMA_2:
                costs = {
                    state: sum(record["held_cost_micro_usd"] for record in requests.values()
                               if record["state"] == state)
                    for state in ("reserved", "indeterminate", "settled")
                }
                cost_committed = sum(costs.values())
                cost_keys.update({
                    "cost_limit_micro_usd": ledger["cost_limit_micro_usd"],
                    "reserved_cost_micro_usd": costs["reserved"],
                    "indeterminate_cost_micro_usd": costs["indeterminate"],
                    "settled_cost_micro_usd": costs["settled"],
                    "committed_cost_micro_usd": cost_committed,
                    "remaining_cost_micro_usd": ledger["cost_limit_micro_usd"] - cost_committed,
                    "price_profile": dict(ledger["price_profile"]),
                    "price_profile_sha256": ledger["price_profile_sha256"],
                })
            return {
                "schema": ledger["schema"],
                "limit_tokens": ledger["limit_tokens"],
                "max_requests": ledger["max_requests"],
                "request_count": len(requests),
                "reserved_tokens": reserved,
                "indeterminate_tokens": indeterminate,
                "settled_tokens": settled,
                "committed_tokens": committed,
                "remaining_tokens": ledger["limit_tokens"] - committed,
                "blocked": any(record["state"] != "settled" for record in requests.values()),
                "requests": {key: dict(value) for key, value in requests.items()},
                **cost_keys,
            }
