"""Opt-in durable budget for a bounded wave of concurrent Responses sends.

Schema 3 is separate from the serial TokenLedger schemas 1 and 2.  The price
profile is a declared ceiling, not an authenticated tariff or invoice.  This
module stores request metadata and digests, never prompts or response bodies.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import secrets
import stat
import time
from pathlib import Path
from typing import Any, Iterator

from managed_token_ledger import (
    BudgetError, CostBudgetExhausted, TokenBudgetExhausted,
    _DIGEST_RE, _IDENTIFIER_RE, _ROLE_RE, _USAGE_KEYS,
    _canonical, _price_profile, _reserved_cost, _settled_cost,
    _private_directory, _private_regular_file,
)


SCHEMA = 3
MAX_WAVE_SIZE = 4
MAX_LEDGER_BYTES = 4 * 1024 * 1024
_LEDGER_NAME = "ledger.json"
_LOCK_NAME = ".lock"
_LEDGER_FIELDS = {
    "schema", "limit_tokens", "max_requests", "cost_limit_micro_usd",
    "price_profile", "price_profile_sha256", "model", "effort",
    "requests", "waves",
}
_ITEM_FIELDS = {
    "request_id", "role", "payload_sha256", "input_tokens",
    "max_output_tokens", "model", "effort",
}
_RECORD_FIELDS = _ITEM_FIELDS | {
    "wave_id", "state", "held_tokens", "held_cost_micro_usd",
    "send_started_ns", "usage", "usage_details", "reason_sha256",
    "response_sha256",
}
_WAVE_FIELDS = {"wave_id", "request_ids", "manifest_sha256", "permit_sha256", "created_ns"}
_IMMUTABLE_ITEM_FIELDS = (
    "request_id", "role", "payload_sha256", "input_tokens",
    "max_output_tokens", "model", "effort",
)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _valid_sha(value: Any) -> bool:
    return type(value) is str and _DIGEST_RE.fullmatch(value) is not None


def _valid_id(value: Any) -> bool:
    return type(value) is str and _IDENTIFIER_RE.fullmatch(value) is not None


def _effort(value: Any) -> str:
    if (type(value) is not str or not value or value != value.strip()
            or len(value) > 64):
        raise BudgetError("effort must be a nonempty trimmed string of at most 64 characters")
    return value


def _item(value: Any, model: str, effort: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _ITEM_FIELDS:
        raise BudgetError("wave item has missing or unexpected fields")
    if not _valid_id(value["request_id"]):
        raise BudgetError("wave request_id is invalid")
    if type(value["role"]) is not str or _ROLE_RE.fullmatch(value["role"]) is None:
        raise BudgetError("wave role is invalid")
    if not _valid_sha(value["payload_sha256"]):
        raise BudgetError("wave payload_sha256 is invalid")
    if (type(value["input_tokens"]) is not int or value["input_tokens"] < 0
            or type(value["max_output_tokens"]) is not int
            or value["max_output_tokens"] < 0):
        raise BudgetError("wave token counts must be nonnegative integers")
    if value["model"] != model or value["effort"] != effort:
        raise BudgetError("wave item model or effort differs from frozen ledger")
    return {key: value[key] for key in _IMMUTABLE_ITEM_FIELDS}


def _manifest_sha(wave_id: str, items: list[dict[str, Any]]) -> str:
    return _sha(_canonical({"wave_id": wave_id, "items": items}))


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BudgetError("wave ledger contains a duplicate key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise BudgetError(f"wave ledger contains invalid numeric constant {value}")


class WavePermit:
    """Process-local permission returned only by the original wave reservation."""

    __slots__ = ("_ledger", "_wave_id", "_nonce", "_pid", "_manifest_sha256")

    def __init__(self, ledger: WaveLedger, wave_id: str, nonce: str,
                 manifest_sha256: str) -> None:
        self._ledger = ledger
        self._wave_id = wave_id
        self._nonce = nonce
        self._pid = os.getpid()
        self._manifest_sha256 = manifest_sha256

    def __getstate__(self) -> None:
        raise TypeError("a wave send permit cannot be serialized or resumed")

    def begin_send(self, request_id: str, payload_sha256: str) -> dict[str, Any]:
        """Durably mark one reserved request inflight before any external send."""
        if os.getpid() != self._pid:
            raise BudgetError("wave send permit belongs to another process")
        return self._ledger._begin_send(
            self._wave_id, self._nonce, self._manifest_sha256,
            request_id, payload_sha256,
        )


class WaveLedger:
    """One private ledger and one global set of token, cost and request caps."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        _private_directory(self.directory)
        _private_regular_file(self.directory / _LOCK_NAME)
        _private_regular_file(self.directory / _LEDGER_NAME)
        self._read_unlocked()

    @classmethod
    def create(cls, directory: Path, limit_tokens: int, max_requests: int, *,
               cost_limit_micro_usd: int, price_profile: dict[str, Any],
               effort: str) -> WaveLedger:
        """Exclusively create a priced schema-3 ledger; never upgrade an old one."""
        if type(limit_tokens) is not int or limit_tokens < 1:
            raise BudgetError("limit_tokens must be a positive integer")
        if type(max_requests) is not int or max_requests < 1:
            raise BudgetError("max_requests must be a positive integer")
        if type(cost_limit_micro_usd) is not int or cost_limit_micro_usd < 0:
            raise BudgetError("cost_limit_micro_usd must be a nonnegative integer")
        profile = _price_profile(price_profile)
        frozen_effort = _effort(effort)
        path = Path(directory)
        try:
            path.mkdir(mode=0o700)
            path.chmod(0o700)
        except OSError as exc:
            raise BudgetError("wave ledger directory must be newly created") from exc
        _private_directory(path)
        lock_path = path / _LOCK_NAME
        try:
            fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600)
            try:
                os.fchmod(fd, 0o600)
                os.fsync(fd)
            finally:
                os.close(fd)
            value = {
                "schema": SCHEMA, "limit_tokens": limit_tokens,
                "max_requests": max_requests,
                "cost_limit_micro_usd": cost_limit_micro_usd,
                "price_profile": profile,
                "price_profile_sha256": _sha(_canonical(profile)),
                "model": profile["model"], "effort": frozen_effort,
                "requests": {}, "waves": {},
            }
            cls._write_atomic(path, value)
            cls._fsync_directory(path.parent)
        except OSError as exc:
            raise BudgetError("could not initialize private wave ledger") from exc
        return cls(path)

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @staticmethod
    def _write_atomic(directory: Path, value: dict[str, Any]) -> None:
        data = _canonical(value)
        if len(data) > MAX_LEDGER_BYTES:
            raise BudgetError("wave ledger exceeds byte limit")
        temporary = directory / f".{_LEDGER_NAME}.{secrets.token_hex(16)}.tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb", closefd=False) as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
        finally:
            os.close(fd)
        os.replace(temporary, directory / _LEDGER_NAME)
        WaveLedger._fsync_directory(directory)

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        _private_directory(self.directory)
        lock_path = self.directory / _LOCK_NAME
        _private_regular_file(lock_path)
        fd = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW)
        try:
            opened = os.fstat(fd)
            fcntl.flock(fd, fcntl.LOCK_EX)
            named = lock_path.lstat()
            if (not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.getuid()
                    or stat.S_IMODE(opened.st_mode) != 0o600
                    or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)):
                raise BudgetError("wave ledger lock identity changed")
            _private_directory(self.directory)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def _read_unlocked(self) -> tuple[dict[str, Any], bytes]:
        path = self.directory / _LEDGER_NAME
        _private_regular_file(path)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                before = os.fstat(fd)
                raw = bytearray()
                while len(raw) <= MAX_LEDGER_BYTES:
                    piece = os.read(fd, min(65536, MAX_LEDGER_BYTES - len(raw) + 1))
                    if not piece:
                        break
                    raw.extend(piece)
                after = os.fstat(fd)
                named = path.lstat()
                if (len(raw) > MAX_LEDGER_BYTES or len(raw) != before.st_size
                        or not stat.S_ISREG(before.st_mode)
                        or before.st_uid != os.getuid()
                        or stat.S_IMODE(before.st_mode) != 0o600
                        or before.st_nlink != 1
                        or (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size)
                        != (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size)
                        or (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino)):
                    raise BudgetError("wave ledger file changed while being read")
            finally:
                os.close(fd)
            value = json.loads(bytes(raw).decode("utf-8"), object_pairs_hook=_unique_pairs,
                               parse_constant=_reject_constant)
        except BudgetError:
            raise
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            raise BudgetError("wave ledger is unreadable or invalid JSON") from exc
        if type(value) is not dict or bytes(raw) != _canonical(value):
            raise BudgetError("wave ledger is not canonical JSON")
        self._validate(value)
        return value, bytes(raw)

    @staticmethod
    def _validate(value: dict[str, Any]) -> None:
        if set(value) != _LEDGER_FIELDS or type(value["schema"]) is not int or value["schema"] != SCHEMA:
            raise BudgetError("wave ledger schema or fields are invalid")
        if (type(value["limit_tokens"]) is not int or value["limit_tokens"] < 1
                or type(value["max_requests"]) is not int or value["max_requests"] < 1
                or type(value["cost_limit_micro_usd"]) is not int
                or value["cost_limit_micro_usd"] < 0):
            raise BudgetError("wave ledger caps are invalid")
        profile = _price_profile(value["price_profile"])
        if (not _valid_sha(value["price_profile_sha256"])
                or value["price_profile_sha256"] != _sha(_canonical(profile))
                or value["model"] != profile["model"]):
            raise BudgetError("wave ledger model or price profile changed")
        effort = _effort(value["effort"])
        requests = value["requests"]
        waves = value["waves"]
        if (type(requests) is not dict or len(requests) > value["max_requests"]
                or type(waves) is not dict or len(waves) > value["max_requests"]):
            raise BudgetError("wave ledger request or wave set is invalid")
        seen: set[str] = set()
        for wave_id, wave in waves.items():
            if (not _valid_id(wave_id) or type(wave) is not dict or set(wave) != _WAVE_FIELDS
                    or wave["wave_id"] != wave_id
                    or type(wave["request_ids"]) is not list
                    or not 1 <= len(wave["request_ids"]) <= MAX_WAVE_SIZE
                    or not _valid_sha(wave["manifest_sha256"])
                    or not _valid_sha(wave["permit_sha256"])
                    or type(wave["created_ns"]) is not int or wave["created_ns"] < 1):
                raise BudgetError("wave ledger wave manifest is invalid")
            items: list[dict[str, Any]] = []
            for request_id in wave["request_ids"]:
                if not _valid_id(request_id) or request_id in seen or request_id not in requests:
                    raise BudgetError("wave ledger request membership is invalid")
                seen.add(request_id)
                record = requests[request_id]
                if type(record) is not dict or record.get("wave_id") != wave_id:
                    raise BudgetError("wave ledger record differs from wave membership")
                items.append({key: record.get(key) for key in _IMMUTABLE_ITEM_FIELDS})
            if wave["manifest_sha256"] != _manifest_sha(wave_id, items):
                raise BudgetError("wave ledger manifest digest differs")
        if seen != set(requests):
            raise BudgetError("wave ledger has orphan request records")
        committed_tokens = committed_cost = 0
        for request_id, record in requests.items():
            if (type(record) is not dict or set(record) != _RECORD_FIELDS
                    or record["request_id"] != request_id):
                raise BudgetError("wave ledger record fields are invalid")
            item = _item({key: record[key] for key in _ITEM_FIELDS}, profile["model"], effort)
            full_tokens = item["input_tokens"] + item["max_output_tokens"]
            full_cost = _reserved_cost(item["input_tokens"], item["max_output_tokens"], profile)
            state = record["state"]
            started = record["send_started_ns"]
            response_sha = record["response_sha256"]
            if (type(state) is not str
                    or type(record["held_tokens"]) is not int
                    or type(record["held_cost_micro_usd"]) is not int
                    or record["held_tokens"] < 0
                    or record["held_cost_micro_usd"] < 0):
                raise BudgetError("wave ledger state or hold types are invalid")
            if state == "reserved":
                if (started is not None or record["usage"] is not None
                        or record["usage_details"] is not None
                        or record["reason_sha256"] is not None or response_sha is not None
                        or record["held_tokens"] != full_tokens
                        or record["held_cost_micro_usd"] != full_cost):
                    raise BudgetError("wave ledger reservation is inconsistent")
            elif state in {"inflight", "indeterminate", "settled"}:
                if type(started) is not int or started < 1:
                    if not (state == "indeterminate" and started is None):
                        raise BudgetError("wave ledger send marker is invalid")
                if state == "inflight":
                    if (record["usage"] is not None or record["usage_details"] is not None
                            or record["reason_sha256"] is not None or response_sha is not None
                            or record["held_tokens"] != full_tokens
                            or record["held_cost_micro_usd"] != full_cost):
                        raise BudgetError("wave ledger inflight hold is inconsistent")
                elif state == "indeterminate":
                    if (not _valid_sha(record["reason_sha256"])
                            or record["usage"] is not None
                            or record["usage_details"] is not None
                            or response_sha is not None and not _valid_sha(response_sha)
                            or record["held_tokens"] != full_tokens
                            or record["held_cost_micro_usd"] != full_cost):
                        raise BudgetError("wave ledger indeterminate hold is inconsistent")
                else:
                    usage = record["usage"]
                    if (type(usage) is not dict or set(usage) != _USAGE_KEYS
                            or any(type(usage[key]) is not int or usage[key] < 0
                                   for key in _USAGE_KEYS)
                            or usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]
                            or usage["input_tokens"] != item["input_tokens"]
                            or usage["output_tokens"] > item["max_output_tokens"]
                            or not _valid_sha(response_sha)
                            or record["reason_sha256"] is not None
                            or record["held_tokens"] != usage["total_tokens"]
                            or record["held_cost_micro_usd"] !=
                            _settled_cost(usage, record["usage_details"], profile)
                            or record["held_cost_micro_usd"] > full_cost):
                        raise BudgetError("wave ledger settlement is inconsistent")
            else:
                raise BudgetError("wave ledger request state is invalid")
            committed_tokens += record["held_tokens"]
            committed_cost += record["held_cost_micro_usd"]
        if (committed_tokens > value["limit_tokens"]
                or committed_cost > value["cost_limit_micro_usd"]):
            raise BudgetError("wave ledger exceeds frozen caps")

    def reserve_wave(self, wave_id: str, items: list[dict[str, Any]]) -> WavePermit:
        """Commit every allowance with one durable replacement before any send."""
        if not _valid_id(wave_id):
            raise BudgetError("wave_id is invalid")
        if type(items) is not list or not 1 <= len(items) <= MAX_WAVE_SIZE:
            raise BudgetError("wave must contain one through four requests")
        with self._locked():
            ledger, _ = self._read_unlocked()
            if wave_id in ledger["waves"]:
                raise BudgetError("wave_id has already been reserved")
            if any(record["state"] != "settled" for record in ledger["requests"].values()):
                raise BudgetError("wave ledger has unresolved reservations")
            if len(ledger["requests"]) + len(items) > ledger["max_requests"]:
                raise TokenBudgetExhausted("wave request cap exhausted before send")
            frozen = [_item(value, ledger["model"], ledger["effort"]) for value in items]
            ids = [item["request_id"] for item in frozen]
            if len(ids) != len(set(ids)) or any(request_id in ledger["requests"] for request_id in ids):
                raise BudgetError("wave request_id is duplicate or previously used")
            token_hold = sum(item["input_tokens"] + item["max_output_tokens"] for item in frozen)
            cost_hold = sum(_reserved_cost(item["input_tokens"], item["max_output_tokens"],
                                           ledger["price_profile"]) for item in frozen)
            committed_tokens = sum(record["held_tokens"] for record in ledger["requests"].values())
            committed_cost = sum(record["held_cost_micro_usd"]
                                 for record in ledger["requests"].values())
            if token_hold > ledger["limit_tokens"] - committed_tokens:
                raise TokenBudgetExhausted("wave token cap exhausted before send")
            if cost_hold > ledger["cost_limit_micro_usd"] - committed_cost:
                raise CostBudgetExhausted("wave cost cap exhausted before send")
            nonce = secrets.token_hex(32)
            manifest_sha = _manifest_sha(wave_id, frozen)
            ledger["waves"][wave_id] = {
                "wave_id": wave_id, "request_ids": ids,
                "manifest_sha256": manifest_sha,
                "permit_sha256": _sha(nonce.encode("ascii")),
                "created_ns": time.time_ns(),
            }
            for item in frozen:
                ledger["requests"][item["request_id"]] = {
                    **item, "wave_id": wave_id, "state": "reserved",
                    "held_tokens": item["input_tokens"] + item["max_output_tokens"],
                    "held_cost_micro_usd": _reserved_cost(
                        item["input_tokens"], item["max_output_tokens"],
                        ledger["price_profile"]),
                    "send_started_ns": None, "usage": None, "usage_details": None,
                    "reason_sha256": None, "response_sha256": None,
                }
            self._write_atomic(self.directory, ledger)
            return WavePermit(self, wave_id, nonce, manifest_sha)

    def _begin_send(self, wave_id: str, nonce: str, manifest_sha256: str,
                    request_id: str, payload_sha256: str) -> dict[str, Any]:
        if not _valid_id(request_id) or not _valid_sha(payload_sha256):
            raise BudgetError("send identity is invalid")
        with self._locked():
            ledger, _ = self._read_unlocked()
            wave = ledger["waves"].get(wave_id)
            record = ledger["requests"].get(request_id)
            if (wave is None or wave["permit_sha256"] != _sha(nonce.encode("ascii"))
                    or wave["manifest_sha256"] != manifest_sha256
                    or record is None or record["wave_id"] != wave_id
                    or record["payload_sha256"] != payload_sha256
                    or record["state"] != "reserved"):
                raise BudgetError("send permit or exact reserved request differs")
            if any(ledger["requests"][sibling]["state"] == "indeterminate"
                   for sibling in wave["request_ids"]):
                raise BudgetError("wave is blocked by an indeterminate sibling")
            record["state"] = "inflight"
            record["send_started_ns"] = time.time_ns()
            self._write_atomic(self.directory, ledger)
            return dict(record)

    def _mark_indeterminate_unlocked(self, ledger: dict[str, Any], request_id: str,
                                     reason: str, response_sha256: str | None) -> dict[str, Any]:
        record = ledger["requests"].get(request_id)
        if record is None:
            raise BudgetError("request_id is not present in wave ledger")
        if record["state"] == "settled":
            raise BudgetError("settled wave request cannot become indeterminate")
        if record["state"] == "indeterminate":
            return dict(record)
        record["state"] = "indeterminate"
        record["reason_sha256"] = _sha(reason.encode("utf-8"))
        record["response_sha256"] = response_sha256
        self._write_atomic(self.directory, ledger)
        return dict(record)

    def mark_indeterminate(self, request_id: str, reason: str, *,
                           response_sha256: str | None = None) -> dict[str, Any]:
        """Keep the full allowance, including one that may never have been sent."""
        if not _valid_id(request_id) or type(reason) is not str or not reason:
            raise BudgetError("indeterminate request identity or reason is invalid")
        if response_sha256 is not None and not _valid_sha(response_sha256):
            raise BudgetError("response_sha256 is invalid")
        with self._locked():
            ledger, _ = self._read_unlocked()
            return self._mark_indeterminate_unlocked(ledger, request_id, reason,
                                                     response_sha256)

    def settle(self, request_id: str, response_sha256: str, usage: dict[str, Any], *,
               usage_details: dict[str, Any] | None = None) -> dict[str, Any]:
        """Reconcile only this inflight request against its own response digest."""
        if not _valid_id(request_id) or not _valid_sha(response_sha256):
            raise BudgetError("settlement identity or response digest is invalid")
        with self._locked():
            ledger, _ = self._read_unlocked()
            record = ledger["requests"].get(request_id)
            if record is None or record["state"] != "inflight":
                raise BudgetError("only an inflight wave request can be settled")
            error: str | None = None
            if type(usage) is not dict or set(usage) != _USAGE_KEYS:
                error = "usage fields are missing or unexpected"
            elif any(type(usage[key]) is not int or usage[key] < 0 for key in _USAGE_KEYS):
                error = "usage token counts must be nonnegative integers"
            elif usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]:
                error = "usage total does not equal input plus output"
            elif usage["input_tokens"] != record["input_tokens"]:
                error = "measured input differs from counted wave request input"
            elif usage["output_tokens"] > record["max_output_tokens"]:
                error = "measured output exceeds reserved wave output cap"
            details: dict[str, Any] | None = None
            cost: int | None = None
            if error is None:
                try:
                    details = (None if usage_details is None
                               else json.loads(_canonical(usage_details)))
                    cost = _settled_cost(usage, details, ledger["price_profile"])
                    if cost > record["held_cost_micro_usd"]:
                        raise BudgetError("measured cost exceeds wave reservation")
                except BudgetError as exc:
                    error = str(exc)
            if error is not None:
                self._mark_indeterminate_unlocked(ledger, request_id, error,
                                                  response_sha256)
                raise BudgetError(error)
            record["state"] = "settled"
            record["held_tokens"] = usage["total_tokens"]
            record["held_cost_micro_usd"] = cost
            record["usage"] = dict(usage)
            record["usage_details"] = details
            record["response_sha256"] = response_sha256
            self._write_atomic(self.directory, ledger)
            return dict(record)

    def snapshot(self) -> dict[str, Any]:
        """Read status and the digest of those exact ledger bytes under one lock."""
        with self._locked():
            ledger, raw = self._read_unlocked()
            requests = ledger["requests"]
            states = ("reserved", "inflight", "indeterminate", "settled")
            tokens = {state: sum(record["held_tokens"] for record in requests.values()
                                  if record["state"] == state) for state in states}
            costs = {state: sum(record["held_cost_micro_usd"] for record in requests.values()
                                 if record["state"] == state) for state in states}
            committed_tokens = sum(tokens.values())
            committed_cost = sum(costs.values())
            return {
                "schema": SCHEMA, "ledger_sha256": _sha(raw),
                "limit_tokens": ledger["limit_tokens"],
                "max_requests": ledger["max_requests"],
                "cost_limit_micro_usd": ledger["cost_limit_micro_usd"],
                "model": ledger["model"], "effort": ledger["effort"],
                "price_profile": dict(ledger["price_profile"]),
                "price_profile_sha256": ledger["price_profile_sha256"],
                "request_count": len(requests), "wave_count": len(ledger["waves"]),
                "waves": {key: dict(value) for key, value in ledger["waves"].items()},
                "requests": {key: dict(value) for key, value in requests.items()},
                "reserved_tokens": tokens["reserved"],
                "inflight_tokens": tokens["inflight"],
                "indeterminate_tokens": tokens["indeterminate"],
                "settled_tokens": tokens["settled"],
                "committed_tokens": committed_tokens,
                "remaining_tokens": ledger["limit_tokens"] - committed_tokens,
                "reserved_cost_micro_usd": costs["reserved"],
                "inflight_cost_micro_usd": costs["inflight"],
                "indeterminate_cost_micro_usd": costs["indeterminate"],
                "settled_cost_micro_usd": costs["settled"],
                "committed_cost_micro_usd": committed_cost,
                "remaining_cost_micro_usd": ledger["cost_limit_micro_usd"] - committed_cost,
                "blocked": any(record["state"] != "settled" for record in requests.values()),
            }

    def status(self) -> dict[str, Any]:
        """Compatibility view without the byte-exact checkpoint digest."""
        result = self.snapshot()
        del result["ledger_sha256"]
        return result
