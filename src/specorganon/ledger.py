"""Atomic, versioned event storage shared by CLI and MCP.

The hash chain detects local corruption. An optional external head anchor detects
coherent history replacement while its independent custody is maintained.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import stat
import tempfile
import uuid
from decimal import Decimal, InvalidOperation
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from . import anchor


SCHEMA_VERSION = 1
FILE_NAME = "organon.json"
ZERO_HASH = "0" * 64


class LedgerError(ValueError):
    """A project is missing, invalid, or cannot accept the requested event."""


class ConflictError(LedgerError):
    """A writer's expected revision does not match the current revision."""


def _reject_nonfinite(raw: str) -> None:
    raise ValueError(f"non-finite JSON number {raw} is not allowed")


def _finite_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value):
        _reject_nonfinite(raw)
    mantissa = raw.split("e", 1)[0].split("E", 1)[0]
    if value == 0.0:
        if any(digit in "123456789" for digit in mantissa):
            raise ValueError("JSON number underflows to zero")
        return value
    try:
        if Decimal(str(value)) != Decimal(raw):
            raise ValueError("JSON number loses decimal precision")
    except InvalidOperation as exc:
        raise ValueError("JSON number exceeds supported decimal range") from exc
    return value


def strict_json_loads(raw: str) -> Any:
    """Parse JSON without nonfinite numbers or visible decimal value loss."""
    return json.loads(raw, parse_constant=_reject_nonfinite, parse_float=_finite_float)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
    except ValueError as exc:
        raise LedgerError(f"ledger value is not strict JSON: {exc}") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def project_file(directory: str | Path) -> Path:
    return Path(directory) / FILE_NAME


def _open_regular_file(path: Path, flags: int) -> int:
    """Open one private regular case file without following links or blocking on a FIFO."""
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o666)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise LedgerError(f"not a regular file: {path}")
        if opened.st_nlink != 1:
            raise LedgerError(f"hard-linked file is not allowed: {path}")
    except Exception:
        os.close(fd)
        raise
    return fd


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    try:
        payload = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    except ValueError as exc:
        raise LedgerError(f"ledger value is not strict JSON: {exc}") from exc
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".organon-", delete=False) as temp:
            temp_name = temp.name
            temp.write(payload)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_name, path)
        temp_name = None
        dir_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)


@contextmanager
def _locked(directory: Path) -> Iterator[None]:
    directory.mkdir(parents=True, exist_ok=True)
    fd = _open_regular_file(directory / ".organon.lock", os.O_RDWR | os.O_CREAT | os.O_APPEND)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def init_project(directory: str | Path, title: str, domain: str, actor: str, approval_policy: str = "signed") -> dict[str, Any]:
    """Create a project, refusing to replace an existing ledger."""
    if not all(isinstance(v, str) and v.strip() for v in (title, domain, actor)):
        raise LedgerError("title, domain and actor must be nonempty strings")
    if approval_policy not in {"signed", "fixture"}:
        raise LedgerError("approval_policy must be signed or fixture")
    directory = Path(directory)
    with _locked(directory):
        target = project_file(directory)
        if os.path.lexists(target):
            raise LedgerError(f"project already exists: {target}")
        data = {
            "schema": SCHEMA_VERSION,
            "project": {"case_id": str(uuid.uuid4()), "title": title.strip(), "domain": domain.strip(),
                        "created_at": _now(), "created_by": actor.strip(), "approval_policy": approval_policy},
            "events": [],
        }
        _atomic_write(target, data)
        return data


def read_project(directory: str | Path, *, verify_external_anchor: bool = True) -> dict[str, Any]:
    target = project_file(directory)
    try:
        with os.fdopen(_open_regular_file(target, os.O_RDONLY), "r", encoding="utf-8") as source:
            data = strict_json_loads(source.read())
    except FileNotFoundError as exc:
        raise LedgerError(f"project not found: {target}") from exc
    except (OSError, ValueError) as exc:
        raise LedgerError(f"cannot read project: {target}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA_VERSION or not isinstance(data.get("events"), list):
        raise LedgerError("unsupported or malformed project ledger")
    if not isinstance(data.get("project"), dict):
        raise LedgerError("malformed project metadata")
    policy = data["project"].get("approval_policy", "signed")
    if not isinstance(policy, str) or policy not in {"signed", "fixture"}:
        raise LedgerError("malformed project approval policy")
    case_id = data["project"].get("case_id")
    if case_id is not None:
        try:
            valid_case_id = isinstance(case_id, str) and str(uuid.UUID(case_id)) == case_id
        except (ValueError, AttributeError):
            valid_case_id = False
        if not valid_case_id:
            raise LedgerError("malformed project case_id")
    prior = ZERO_HASH
    for index, event in enumerate(data["events"], start=1):
        if not isinstance(event, dict) or event.get("seq") != index or event.get("prev_hash") != prior:
            raise LedgerError(f"broken event chain at sequence {index}")
        supplied = event.get("hash")
        if not isinstance(supplied, str) or supplied != _digest({key: value for key, value in event.items() if key != "hash"}):
            raise LedgerError(f"event digest mismatch at sequence {index}")
        prior = supplied
    if verify_external_anchor:
        try:
            anchor.verify(data, directory)
        except ValueError as exc:
            raise LedgerError(f"ledger anchor verification failed: {exc}") from exc
    return data


def append_event(
    directory: str | Path,
    kind: str,
    payload: dict[str, Any],
    actor: str,
    *,
    expected_seq: int | None = None,
) -> dict[str, Any]:
    """Append one event under a file lock and atomically publish the new ledger."""
    if not isinstance(kind, str) or not kind.strip() or not isinstance(actor, str) or not actor.strip():
        raise LedgerError("kind and actor must be nonempty strings")
    if not isinstance(payload, dict):
        raise LedgerError("event payload must be an object")
    directory = Path(directory)
    with _locked(directory):
        data = read_project(directory)
        seq = len(data["events"])
        if expected_seq is not None and expected_seq != seq:
            raise ConflictError(f"revision conflict: expected {expected_seq}, current {seq}")
        event = {
            "seq": seq + 1,
            "at": _now(),
            "actor": actor.strip(),
            "kind": kind.strip(),
            "payload": payload,
            "prev_hash": data["events"][-1]["hash"] if seq else ZERO_HASH,
        }
        event["hash"] = _digest(event)
        data["events"].append(event)
        _atomic_write(project_file(directory), data)
        return event
