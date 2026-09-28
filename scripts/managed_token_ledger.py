"""Durable local reservations for provider-request token budgets.

The ledger records request metadata and token accounting only. Callers must not
put prompts, credentials, or provider response bodies in this file.
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
    """A token reservation or settlement cannot safely be accepted."""


_SCHEMA = 1
_LEDGER_NAME = "ledger.json"
_LOCK_NAME = ".lock"
_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_ROLE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")
_USAGE_KEYS = {"input_tokens", "output_tokens", "total_tokens"}
_REQUEST_KEYS = {
    "request_id", "role", "payload_sha256", "input_tokens", "max_output_tokens",
    "state", "held_tokens", "usage", "reason_sha256",
}
_LEDGER_KEYS = {"schema", "limit_tokens", "max_requests", "requests"}


def _canonical(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=True, sort_keys=True,
                           separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise BudgetError("ledger value is not canonical JSON") from exc


def _exact_nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise BudgetError(f"{label} must be a nonnegative integer")
    return value


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
    def create(cls, directory: Path, limit_tokens: int, max_requests: int) -> TokenLedger:
        """Exclusively create a new private ledger with the supplied hard caps."""
        if type(limit_tokens) is not int or limit_tokens < 1:
            raise BudgetError("limit_tokens must be a positive integer")
        if type(max_requests) is not int or max_requests < 1:
            raise BudgetError("max_requests must be a positive integer")
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
            cls._write_atomic(path, {
                "schema": _SCHEMA, "limit_tokens": limit_tokens,
                "max_requests": max_requests, "requests": {},
            })
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
        if type(value) is not dict or set(value) != _LEDGER_KEYS:
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
        if type(value["schema"]) is not int or value["schema"] != _SCHEMA:
            raise BudgetError("token ledger schema is unsupported")
        if type(value["limit_tokens"]) is not int or value["limit_tokens"] < 1:
            raise BudgetError("token ledger limit is invalid")
        if type(value["max_requests"]) is not int or value["max_requests"] < 1:
            raise BudgetError("token ledger request cap is invalid")
        requests = value["requests"]
        if type(requests) is not dict or len(requests) > value["max_requests"]:
            raise BudgetError("token ledger request set is invalid")
        for request_id, record in requests.items():
            if (type(request_id) is not str or _IDENTIFIER_RE.fullmatch(request_id) is None
                    or type(record) is not dict or set(record) != _REQUEST_KEYS
                    or record["request_id"] != request_id
                    or type(record["role"]) is not str
                    or _ROLE_RE.fullmatch(record["role"]) is None
                    or type(record["payload_sha256"]) is not str
                    or _DIGEST_RE.fullmatch(record["payload_sha256"]) is None):
                raise BudgetError("token ledger contains invalid request metadata")
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
            elif state == "settled":
                if (type(usage) is not dict or set(usage) != _USAGE_KEYS
                        or any(type(usage[key]) is not int or usage[key] < 0 for key in _USAGE_KEYS)
                        or usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]
                        or usage["input_tokens"] != input_tokens
                        or usage["output_tokens"] > output_cap
                        or held != usage["total_tokens"] or reason_digest is not None):
                    raise BudgetError("token ledger settlement is inconsistent")
            else:
                if (held != input_tokens + output_cap or usage is not None
                        or type(reason_digest) is not str
                        or _DIGEST_RE.fullmatch(reason_digest) is None):
                    raise BudgetError("token ledger indeterminate reservation is inconsistent")
        committed = sum(record["held_tokens"] for record in requests.values())
        if committed > value["limit_tokens"]:
            raise BudgetError("token ledger exceeds its token limit")

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
                input_tokens: int, max_output_tokens: int) -> dict[str, Any]:
        """Persist the full request allowance before returning permission to send."""
        self._validate_request(request_id, role, payload_sha256, input_tokens, max_output_tokens)
        with self._locked():
            ledger = self._read_unlocked()
            requests = ledger["requests"]
            if request_id in requests:
                raise BudgetError("request_id has already been reserved")
            if len(requests) >= ledger["max_requests"]:
                raise BudgetError("token ledger request cap exhausted")
            if any(record["state"] == "indeterminate" for record in requests.values()):
                raise BudgetError("token ledger is blocked by an indeterminate request")
            if any(record["state"] == "reserved" for record in requests.values()):
                raise BudgetError("token ledger is blocked by an unresolved reserved request")
            held = sum(record["held_tokens"] for record in requests.values())
            requested = input_tokens + max_output_tokens
            if requested > ledger["limit_tokens"] - held:
                raise BudgetError("token budget exhausted before provider request")
            record = {
                "request_id": request_id, "role": role,
                "payload_sha256": payload_sha256, "input_tokens": input_tokens,
                "max_output_tokens": max_output_tokens, "state": "reserved",
                "held_tokens": requested, "usage": None, "reason_sha256": None,
            }
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

    def settle(self, request_id: str, usage: dict[str, Any]) -> dict[str, Any]:
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
            if error is not None:
                self._mark_indeterminate_unlocked(ledger, request_id, error)
                raise BudgetError(error)
            record["state"] = "settled"
            record["held_tokens"] = usage["total_tokens"]
            record["usage"] = dict(usage)
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
            return {
                "limit_tokens": ledger["limit_tokens"],
                "max_requests": ledger["max_requests"],
                "request_count": len(requests),
                "reserved_tokens": reserved,
                "indeterminate_tokens": indeterminate,
                "settled_tokens": settled,
                "committed_tokens": committed,
                "remaining_tokens": ledger["limit_tokens"] - committed,
                "blocked": reserved > 0 or indeterminate > 0,
                "requests": {key: dict(value) for key, value in requests.items()},
            }
