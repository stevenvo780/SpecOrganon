"""Durable, development-only session for sequential staged local generic tools.

Usage::

    python scripts/staged_tool_session.py init SCHEDULE RUN_ID STAGE SESSION
    python scripts/staged_tool_session.py call SCHEDULE RUN_ID STAGE SESSION TOOL_ID EXECUTABLE
    python scripts/staged_tool_session.py status SCHEDULE RUN_ID STAGE SESSION

SESSION is a new private directory outside STAGE. The first command verifies
the stage once, while work is empty. Later commands bind the immutable visible
case, inputs and policy to the independent caller-supplied schedule without
rerunning the empty-work stage verifier. Each numbered call reserves a slot in
an fsynced journal before launch. A missing terminal receipt is indeterminate:
its slot remains spent and no later call is launched. Nothing retries or
deletes possibly effected work. Budgets are enforced for one local STAGE
instance only. The schedule's per_run_limits supply values, but another stage
of the same release/run can independently spend those values; global run limits
are not enforced by this primitive.

This is a same-UID, point-in-time local development primitive, not external
custody or criterion-4 evidence. The active budget charges observed local
subprocess elapsed time plus a one-second guard per call; it excludes human
wait and work between calls. Each requested subprocess timeout plus that guard
must fit before launch. Process cleanup can exceed the timeout, in which case
the overrun is recorded and subsequent calls stop. The separate session wall
budget uses the host UTC clock across resumes, including idle time; it is not
an attested clock. Neither bound measures provider work, tokens or cost.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import math
import os
import secrets
import stat
import sys
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Iterator

from local_replay_sandbox import (
    SandboxError,
    SandboxUnavailable,
    default_python_runtime_roots,
    run_sandboxed,
)
from preflight_assets import PreflightError, _candidate_schedule
from run_staged_local_tool import (
    DIR_FLAGS,
    MAX_EXECUTABLE_BYTES,
    MAX_WORK_BYTES,
    MAX_WORK_ENTRIES,
    MAX_WORK_FILE_BYTES,
    MAX_WORK_FILES,
    LocalToolError,
    _check_snapshot_bindings,
    _immutable_snapshot,
    _inventory,
    _private_receipt_dir,
)
from tool_policy import (
    MAX_POLICY_BYTES,
    ToolPolicyError,
    _check_directory_chain,
    _open_directory_chain,
    _read_bounded_file,
    _same_file_state,
    validate_tool_policy_bytes,
)
from verify_released_run import ReleaseVerificationError, _read_schedule
from verify_staged_run import StageVerificationError, verify_stage


CLASSIFICATION = "development_staged_local_tool_session_unsealed"
ANCHOR_CLASSIFICATION = "development_staged_local_tool_session_anchor_unsealed"
NOTICE = (
    "Offline local generic tools only. Schedule and stage have no external custody; "
    "runtime image is declared, not sealed. No provider calls, measured model "
    "tokens, cost, or criterion-4 assessment. Budgets apply to one local stage "
    "instance; per_run_limits are source values, not global run enforcement. "
    "Same-UID mutation and clock changes remain outside this journal's guarantees."
)
BUDGET_SCOPE = "stage_instance_local"
SCHEMA = 1
ACTIVE_GUARD_SECONDS = 1.0
MAX_SESSION_WALL_SECONDS = 86400.0
MAX_JOURNAL_BYTES = 4 * 1024 * 1024
MAX_CALLS = 10000


class SessionError(ValueError):
    """The session is invalid, exhausted, indeterminate, or cannot launch."""


def _digest(value: Any) -> str:
    data = _canonical_bytes(value)
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(value: Any, *, newline: bool = False) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + ("\n" if newline else "")).encode("utf-8")


def _paths(stage_dir: Path | str, session_dir: Path | str) -> tuple[Path, Path]:
    stage, session = Path(stage_dir), Path(session_dir)
    if not stage.is_absolute() or not session.is_absolute():
        raise SessionError("stage and session paths must be absolute")
    if any(part in (".", "..") for path in (stage, session) for part in path.parts):
        raise SessionError("paths must not contain dot components")
    if stage == session or stage.is_relative_to(session) or session.is_relative_to(stage):
        raise SessionError("session directory must be separate from stage")
    return stage, session


def _schedule(raw: Any, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        schedule = _candidate_schedule(copy.deepcopy(raw))
    except (PreflightError, TypeError, ValueError, RuntimeError, RecursionError) as exc:
        raise SessionError("invalid independent schedule") from exc
    run = next((item for item in schedule["runs"] if item["run_id"] == run_id), None)
    if run is None:
        raise SessionError("run_id is absent from independent schedule")
    return schedule, run


def _policy(
    stage: Path, schedule: dict[str, Any], run_id: str, snapshot: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    _check_snapshot_bindings(schedule, run_id, stage, snapshot)
    data = _read_bounded_file(stage / "inputs" / "tool_policy", "staged tool policy", MAX_POLICY_BYTES)
    digest = hashlib.sha256(data).hexdigest()
    if digest != schedule["inputs"]["tool_policy"]["sha256"]:
        raise SessionError("staged tool policy differs from independent schedule")
    return validate_tool_policy_bytes(data, expected_limits=schedule["per_run_limits"]), digest


def _work_inventory(stage: Path) -> dict[str, Any]:
    files, directories, complete, reason = _inventory(
        stage / "work", max_files=MAX_WORK_FILES, max_bytes=MAX_WORK_BYTES,
        max_file_bytes=MAX_WORK_FILE_BYTES, max_entries=MAX_WORK_ENTRIES,
    )
    return {"files": files, "directories": directories,
            "complete": complete, "reason": reason}


def _write_json(path: Path, value: dict[str, Any]) -> str:
    data = _canonical_bytes(value, newline=True)
    if len(data) > MAX_JOURNAL_BYTES:
        raise SessionError("journal record exceeds byte limit")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    finally:
        _fsync_directory(path.parent)
    return hashlib.sha256(data).hexdigest()


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, DIR_FLAGS)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_json(path: Path) -> dict[str, Any]:
    data = _read_bounded_file(path, "session journal record", MAX_JOURNAL_BYTES)
    try:
        value = json.loads(data)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise SessionError("session journal record is invalid JSON") from exc
    try:
        canonical = _canonical_bytes(value, newline=True) if type(value) is dict else None
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise SessionError("session journal record contains invalid JSON values") from exc
    if canonical != data:
        raise SessionError("session journal record is not canonical JSON")
    return value


def _check_private_directory(path: Path) -> None:
    info = os.stat(path, follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise SessionError("session journal directory is not private")


def _anchor_path(stage: Path, run_id: str) -> Path:
    key = _digest({"stage_dir": str(stage), "run_id": run_id})[:32]
    return stage.parent / f".staged-local-session-{key}.json"


@contextmanager
def _controlled_stage_parent(stage: Path) -> Iterator[int]:
    with ExitStack() as stack:
        parent_fd, _name, chain = _open_directory_chain(stage, "stage parent", stack)
        _check_directory_chain(chain, "stage parent")
        info = os.fstat(parent_fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o022):
            raise SessionError("stage parent must be owned by current UID and not writable by others")
        yield parent_fd
        _check_directory_chain(chain, "stage parent")


def _anchor_preflight(stage: Path, run_id: str) -> None:
    anchor = _anchor_path(stage, run_id)
    with _controlled_stage_parent(stage) as parent_fd:
        try:
            os.stat(anchor.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
    raise SessionError("stage/run already has a durable local session anchor")


def _write_anchor(stage: Path, run_id: str, value: dict[str, Any]) -> str:
    anchor = _anchor_path(stage, run_id)
    data = _canonical_bytes(value, newline=True)
    with _controlled_stage_parent(stage) as parent_fd:
        temporary = f"{anchor.name}.{secrets.token_hex(16)}.tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent_fd)
        try:
            written = 0
            while written < len(data):
                count = os.write(fd, data[written:])
                if count <= 0:
                    raise OSError("stage/run anchor temporary write made no progress")
                written += count
            os.fsync(fd)
        finally:
            os.close(fd)
        fcntl.flock(parent_fd, fcntl.LOCK_EX)
        try:
            try:
                os.stat(anchor.name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise SessionError("stage/run already has a durable local session anchor")
            os.rename(temporary, anchor.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            os.fsync(parent_fd)
        finally:
            fcntl.flock(parent_fd, fcntl.LOCK_UN)
    return hashlib.sha256(data).hexdigest()


def _check_anchor(
    stage: Path, session: Path, schedule: dict[str, Any], run: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    anchor_path = _anchor_path(stage, run["run_id"])
    with _controlled_stage_parent(stage) as parent_fd:
        fcntl.flock(parent_fd, fcntl.LOCK_SH)
        try:
            try:
                info = os.stat(anchor_path.name, dir_fd=parent_fd, follow_symlinks=False)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                    raise SessionError("stage/run anchor is not a private regular file")
                data = _read_bounded_file(anchor_path, "stage/run session anchor", MAX_JOURNAL_BYTES)
                anchor = _read_json(anchor_path)
            except (ToolPolicyError, OSError) as exc:
                raise SessionError("stage/run session anchor cannot be read securely") from exc
            if not _same_file_state(
                os.stat(anchor_path.name, dir_fd=parent_fd, follow_symlinks=False), info
            ):
                raise SessionError("stage/run session anchor changed during reading")
            try:
                os.fsync(parent_fd)
            except OSError as exc:
                raise SessionError("stage/run anchor durability could not be confirmed") from exc
        finally:
            fcntl.flock(parent_fd, fcntl.LOCK_UN)
    if (hashlib.sha256(data).hexdigest() != manifest.get("anchor_sha256")
        or anchor != {
            "schema": SCHEMA, "classification": ANCHOR_CLASSIFICATION,
            "run_id": run["run_id"], "run_sha256": run["run_sha256"],
            "schedule_sha256": schedule["schedule_sha256"],
            "stage_dir": str(stage), "session_dir": str(session),
            "immutable_snapshot_sha256": manifest["immutable_snapshot_sha256"],
            "created_ns": manifest["created_ns"],
            "budget_scope": BUDGET_SCOPE, "global_run_limits_enforced": False,
        }):
        raise SessionError("stage/run anchor differs from this session")


@contextmanager
def _locked_session(session: Path) -> Iterator[None]:
    _check_private_directory(session)
    fd = os.open(session, DIR_FLAGS)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SessionError("session is busy in another process") from exc
        yield
    finally:
        os.close(fd)


def _wall_elapsed(created_ns: int, observed_ns: int) -> float:
    if type(created_ns) is not int or type(observed_ns) is not int or observed_ns < created_ns:
        raise SessionError("host clock moved before session creation")
    return (observed_ns - created_ns) / 1_000_000_000


def _is_sha256(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _valid_terminal(
    terminal: dict[str, Any], reservation: dict[str, Any], run: dict[str, Any],
    schedule: dict[str, Any], reservation_sha256: str,
    deliverables: list[str], call_dir: Path,
) -> bool:
    duration = terminal.get("local_elapsed_seconds")
    debit = terminal.get("active_seconds_charged")
    outputs = terminal.get("outputs")
    if type(outputs) is not list or any(
        type(item) is not dict or set(item) != {"path", "bytes", "sha256"}
        or type(item["path"]) is not str or not item["path"]
        or item["path"].startswith("/") or any(part in ("", ".", "..") for part in item["path"].split("/"))
        or type(item["bytes"]) is not int or not 0 <= item["bytes"] <= MAX_WORK_FILE_BYTES
        or not _is_sha256(item["sha256"])
        for item in outputs
    ):
        return False
    output_paths = [item["path"] for item in outputs]
    if len(set(output_paths)) != len(output_paths):
        return False
    complete = terminal.get("output_inventory_complete")
    if complete is True:
        if (terminal.get("output_inventory_reason") is not None
            or terminal.get("deliverables_present") is not all(
                name in output_paths for name in deliverables
            )):
            return False
    elif complete is False:
        if terminal.get("deliverables_present") is not None or type(terminal.get("output_inventory_reason")) is not str:
            return False
    else:
        return False
    status = terminal.get("status")
    sealed = terminal.get("execution_bytes_sealed")
    exit_code = terminal.get("exit_code")
    timed_out = terminal.get("timed_out")
    launch_error = terminal.get("launch_error")
    if status == "success" and (
        exit_code != 0 or type(exit_code) is not int or timed_out is not False
        or launch_error is not None or sealed is not True or complete is not True
        or terminal.get("stage_unchanged_after_run") is not True
        or terminal.get("executable_unchanged_after_run") is not True
        or terminal.get("sealed_executable_sha256") != reservation["executable_sha256"]
    ):
        return False
    if status == "timeout" and timed_out is not True:
        return False
    if status == "launch_failure" and (type(launch_error) is not str or not launch_error or sealed is not False):
        return False
    if status == "output_inventory_incomplete" and complete is not False:
        return False
    if status == "stage_or_executable_mutated" and (
        terminal.get("stage_unchanged_after_run") is True
        and terminal.get("executable_unchanged_after_run") is True
    ):
        return False
    for stream in ("stdout", "stderr"):
        expected = call_dir / stream
        declared = terminal.get(stream)
        if declared is None:
            if expected.exists() or status == "success":
                return False
        elif declared != str(expected):
            return False
        else:
            try:
                info = os.stat(expected, follow_symlinks=False)
            except OSError:
                return False
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
                return False
    return (
        terminal.get("schema") == SCHEMA
        and terminal.get("classification") == CLASSIFICATION
        and terminal.get("notice") == NOTICE
        and terminal.get("call_number") == reservation["call_number"]
        and terminal.get("reservation_sha256") == reservation_sha256
        and terminal.get("run_id") == run["run_id"]
        and terminal.get("run_sha256") == run["run_sha256"]
        and terminal.get("schedule_sha256") == schedule["schedule_sha256"]
        and terminal.get("tool_id") == reservation["tool_id"]
        and terminal.get("tool_version") == reservation["tool_version"]
        and terminal.get("executable_sha256") == reservation["executable_sha256"]
        and terminal.get("policy_sha256") == reservation["policy_sha256"]
        and terminal.get("work_before_sha256") == reservation["work_before_sha256"]
        and _is_sha256(terminal.get("work_after_sha256"))
        and type(status) is str
        and status in {
            "success", "timeout", "launch_failure", "tool_failure",
            "output_inventory_incomplete", "stage_or_executable_mutated",
        }
        and type(terminal.get("output_inventory_complete")) is bool
        and type(terminal.get("stage_unchanged_after_run")) is bool
        and type(terminal.get("active_budget_overrun")) is bool
        and type(terminal.get("execution_bytes_sealed")) is bool
        and type(terminal.get("executable_unchanged_after_run")) is bool
        and type(duration) in (int, float) and math.isfinite(duration) and duration >= 0
        and type(debit) in (int, float) and math.isfinite(debit)
        and debit >= duration + ACTIVE_GUARD_SECONDS - 1e-9
        and terminal.get("deliverables") == deliverables
        and terminal.get("reserved_tool_calls") == reservation["call_number"]
        and terminal.get("provider_calls") == 0
        and terminal.get("measured_tokens") is None
        and terminal.get("criterion_4") == "not_assessed"
        and terminal.get("provider_receipt") is False
        and terminal.get("runtime_image_verified") is False
        and terminal.get("budget_scope") == BUDGET_SCOPE
        and terminal.get("global_run_limits_enforced") is False
    )


def _read_state(
    schedule: dict[str, Any], run: dict[str, Any], stage: Path, session: Path,
) -> tuple[dict[str, Any], list[tuple[dict[str, Any] | None, dict[str, Any] | None]], dict[str, Any]]:
    manifest = _read_json(session / "session.json")
    if (
        manifest.get("schema") != SCHEMA or manifest.get("classification") != CLASSIFICATION
        or manifest.get("run_id") != run["run_id"]
        or manifest.get("run_sha256") != run["run_sha256"]
        or manifest.get("schedule_sha256") != schedule["schedule_sha256"]
        or manifest.get("stage_dir") != str(stage)
        or manifest.get("session_dir") != str(session)
        or manifest.get("notice") != NOTICE
        or manifest.get("budget_scope") != BUDGET_SCOPE
        or manifest.get("global_run_limits_enforced") is not False
        or manifest.get("tool_call_cap") != schedule["per_run_limits"]["tool_calls"]
        or manifest.get("policy_sha256") != schedule["inputs"]["tool_policy"]["sha256"]
        or not _is_sha256(manifest.get("immutable_snapshot_sha256"))
        or not _is_sha256(manifest.get("initial_work_sha256"))
        or not _is_sha256(manifest.get("anchor_sha256"))
        or type(manifest.get("deliverables")) is not list
    ):
        raise SessionError("session identity differs from independent schedule or paths")
    if (type(manifest.get("active_budget_seconds")) not in (float, int)
        or type(manifest.get("wall_budget_seconds")) not in (float, int)
        or type(manifest.get("created_ns")) is not int
        or not 0 < manifest["active_budget_seconds"] <= schedule["per_run_limits"]["active_seconds"]
        or not 0 < manifest["wall_budget_seconds"] <= MAX_SESSION_WALL_SECONDS):
        raise SessionError("session budget or creation time is invalid")
    _check_anchor(stage, session, schedule, run, manifest)
    calls_root = session / "calls"
    _check_private_directory(calls_root)
    names = sorted(path.name for path in calls_root.iterdir())
    if len(names) > MAX_CALLS or names != [f"{number:06d}" for number in range(1, len(names) + 1)]:
        raise SessionError("session call journal has unexpected numbering")
    calls: list[tuple[dict[str, Any] | None, dict[str, Any] | None]] = []
    previous_digest: str | None = None
    measured = charged = 0.0
    pending_reason: str | None = None
    for number, name in enumerate(names, 1):
        call_dir = calls_root / name
        _check_private_directory(call_dir)
        entries = {entry.name for entry in call_dir.iterdir()}
        if not entries <= {"reservation.json", "terminal.json", "stdout", "stderr"}:
            raise SessionError("session call directory has unexpected entries")
        try:
            reservation = _read_json(call_dir / "reservation.json") if "reservation.json" in entries else None
            terminal = _read_json(call_dir / "terminal.json") if "terminal.json" in entries else None
        except (SessionError, ToolPolicyError, OSError):
            if number != len(names):
                raise SessionError("nonterminal journal record precedes another call") from None
            reservation = terminal = None
            pending_reason = "latest journal record is incomplete or unreadable"
        if reservation is not None:
            if (reservation.get("schema") != SCHEMA
                or reservation.get("call_number") != number or reservation.get("run_id") != run["run_id"]
                or reservation.get("schedule_sha256") != schedule["schedule_sha256"]
                or reservation.get("budget_scope") != BUDGET_SCOPE
                or reservation.get("global_run_limits_enforced") is not False
                or reservation.get("previous_terminal_sha256") != previous_digest
                or reservation.get("policy_sha256") != manifest["policy_sha256"]
                or reservation.get("immutable_snapshot_sha256") != manifest["immutable_snapshot_sha256"]
                or not _is_sha256(reservation.get("work_before_sha256"))
                or not _is_sha256(reservation.get("executable_sha256"))
                or type(reservation.get("tool_id")) is not str
                or type(reservation.get("tool_version")) is not str
                or type(reservation.get("reserved_at_ns")) is not int
                or type(reservation.get("active_seconds_reserved")) not in (int, float)):
                if number != len(names):
                    raise SessionError("invalid reservation precedes another call")
                reservation = terminal = None
                pending_reason = "latest reservation identity is invalid"
        if terminal is not None and reservation is None:
            if number != len(names):
                raise SessionError("terminal without reservation precedes another call")
            terminal = None
            pending_reason = "terminal receipt has no valid reservation"
        if terminal is not None:
            reservation_digest = hashlib.sha256(_canonical_bytes(reservation, newline=True)).hexdigest()
            if not _valid_terminal(
                terminal, reservation, run, schedule, reservation_digest,
                manifest["deliverables"], call_dir,
            ):
                if number != len(names):
                    raise SessionError("invalid terminal receipt precedes another call")
                terminal = None
                pending_reason = "latest terminal receipt is invalid"
            else:
                previous_digest = hashlib.sha256(_canonical_bytes(terminal, newline=True)).hexdigest()
                measured += terminal["local_elapsed_seconds"]
                charged += terminal["active_seconds_charged"]
        if terminal is None and pending_reason is None:
            pending_reason = "reservation or call directory lacks a terminal receipt"
        calls.append((reservation, terminal))
    if set(path.name for path in session.iterdir()) != {"session.json", "calls"}:
        raise SessionError("session directory has unexpected entries")
    now_ns = time.time_ns()
    wall_elapsed = _wall_elapsed(manifest["created_ns"], now_ns)
    pending = next((index for index, (_, terminal) in enumerate(calls, 1) if terminal is None), None)
    if pending is not None and pending != len(calls):
        raise SessionError("session contains a call after an indeterminate reservation")
    last = calls[-1][1] if calls and pending is None else None
    blocked_reason = None
    if last is not None and (last.get("output_inventory_complete") is not True
                              or last.get("stage_unchanged_after_run") is not True
                              or last.get("status") == "stage_or_executable_mutated"
                              or last.get("active_budget_overrun") is True):
        blocked_reason = "previous receipt cannot establish a complete, unchanged continuation"
    exhausted_reason = None
    if len(calls) >= manifest["tool_call_cap"]:
        exhausted_reason = "stage-instance local tool_calls cap exhausted before launch"
    elif charged + ACTIVE_GUARD_SECONDS >= manifest["active_budget_seconds"]:
        exhausted_reason = "local active budget exhausted before launch"
    elif wall_elapsed + ACTIVE_GUARD_SECONDS >= manifest["wall_budget_seconds"]:
        exhausted_reason = "session wall budget exhausted before launch"
    status = ("indeterminate" if pending is not None else "blocked" if blocked_reason
              else "exhausted" if exhausted_reason else "ready")
    summary = {
        "schema": SCHEMA, "classification": CLASSIFICATION, "notice": NOTICE,
        "budget_scope": BUDGET_SCOPE, "global_run_limits_enforced": False,
        "run_id": run["run_id"], "schedule_sha256": schedule["schedule_sha256"],
        "status": status, "blocked_reason": blocked_reason or exhausted_reason,
        "pending_call": pending, "pending_reason": pending_reason if pending else None,
        "reserved_tool_calls": len(calls), "completed_tool_calls": len(calls) - (pending is not None),
        "remaining_tool_calls": max(0, schedule["per_run_limits"]["tool_calls"] - len(calls)),
        "local_elapsed_seconds": measured, "active_seconds_charged": charged,
        "active_budget_seconds": manifest["active_budget_seconds"],
        "active_budget_scope": "local sandbox call elapsed plus one-second guard per terminal call",
        "wall_elapsed_seconds": wall_elapsed,
        "wall_budget_seconds": manifest["wall_budget_seconds"],
        "wall_budget_scope": "host UTC elapsed since init, including idle time",
        "last_terminal_status": last.get("status") if last else None,
        "deliverables_present": last.get("deliverables_present") if last else False,
        "provider_calls": 0, "measured_tokens": None, "criterion_4": "not_assessed",
    }
    return manifest, calls, summary


def _assert_stage_and_work(
    schedule: dict[str, Any], run_id: str, stage: Path, manifest: dict[str, Any],
    calls: list[tuple[dict[str, Any] | None, dict[str, Any] | None]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    snapshot = _immutable_snapshot(stage)
    if _digest(snapshot) != manifest["immutable_snapshot_sha256"]:
        raise SessionError("stage case, inputs, manifest or work root changed since init")
    _check_snapshot_bindings(schedule, run_id, stage, snapshot)
    policy, policy_sha256 = _policy(stage, schedule, run_id, snapshot)
    work = _work_inventory(stage)
    if not work["complete"]:
        raise SessionError(f"work inventory incomplete before call: {work['reason']}")
    expected = calls[-1][1]["work_after_sha256"] if calls else manifest["initial_work_sha256"]
    if _digest(work) != expected:
        raise SessionError("work tree differs from last durable receipt")
    if calls:
        actual_outputs = [
            {key: item[key] for key in ("path", "bytes", "sha256")}
            for item in work["files"]
        ]
        if actual_outputs != calls[-1][1]["outputs"]:
            raise SessionError("terminal output list differs from current work inventory")
    return snapshot, work, policy, policy_sha256


def create_session(
    schedule_raw: Any, run_id: str, stage_dir: Path | str, session_dir: Path | str, *,
    active_budget_seconds: float | None = None, wall_budget_seconds: float | None = None,
) -> dict[str, Any]:
    """Verify an empty stage exactly once and create a new durable session."""
    stage, session = _paths(stage_dir, session_dir)
    schedule, run = _schedule(schedule_raw, run_id)
    policy_cap = schedule["per_run_limits"]["active_seconds"]
    active_budget = float(policy_cap) if active_budget_seconds is None else active_budget_seconds
    wall_budget = MAX_SESSION_WALL_SECONDS if wall_budget_seconds is None else wall_budget_seconds
    if (type(active_budget) not in (int, float) or not math.isfinite(active_budget)
        or not 0 < active_budget <= policy_cap
        or type(wall_budget) not in (int, float) or not math.isfinite(wall_budget)
        or not 0 < wall_budget <= MAX_SESSION_WALL_SECONDS):
        raise SessionError("invalid active or session wall budget")
    if session.exists():
        raise FileExistsError("session directory already exists")
    _anchor_preflight(stage, run_id)
    before = _immutable_snapshot(stage)
    verified = verify_stage(schedule, run_id, stage)
    after = _immutable_snapshot(stage)
    if before != after:
        raise SessionError("stage changed across initial verification")
    _check_snapshot_bindings(schedule, run_id, stage, after)
    policy, policy_sha256 = _policy(stage, schedule, run_id, after)
    work = _work_inventory(stage)
    if not work["complete"] or work["files"] or set(work["directories"]) != {""}:
        raise SessionError("stage work directory must be completely empty at init")
    case_manifest = json.loads(_read_bounded_file(
        stage / "case" / "case.json", "staged case manifest", 1024 * 1024
    ))
    _private_receipt_dir(session, stage)
    _fsync_directory(session.parent)
    (session / "calls").mkdir(mode=0o700)
    _fsync_directory(session)
    created_ns = time.time_ns()
    anchor = {
        "schema": SCHEMA, "classification": ANCHOR_CLASSIFICATION,
        "run_id": run_id, "run_sha256": verified["run_sha256"],
        "schedule_sha256": schedule["schedule_sha256"],
        "stage_dir": str(stage), "session_dir": str(session),
        "immutable_snapshot_sha256": _digest(after), "created_ns": created_ns,
        "budget_scope": BUDGET_SCOPE, "global_run_limits_enforced": False,
    }
    anchor_sha256 = hashlib.sha256(_canonical_bytes(anchor, newline=True)).hexdigest()
    manifest = {
        "schema": SCHEMA, "classification": CLASSIFICATION, "notice": NOTICE,
        "budget_scope": BUDGET_SCOPE, "global_run_limits_enforced": False,
        "run_id": run_id, "run_sha256": verified["run_sha256"],
        "schedule_sha256": schedule["schedule_sha256"], "stage_dir": str(stage),
        "session_dir": str(session), "created_ns": created_ns,
        "immutable_snapshot_sha256": _digest(after), "initial_work_sha256": _digest(work),
        "anchor_sha256": anchor_sha256,
        "policy_sha256": policy_sha256, "tool_call_cap": policy["limits"]["tool_calls"],
        "deliverables": case_manifest["deliverables"],
        "active_budget_seconds": float(active_budget),
        "wall_budget_seconds": float(wall_budget),
    }
    _write_json(session / "session.json", manifest)
    if _write_anchor(stage, run_id, anchor) != anchor_sha256:
        raise SessionError("published stage/run anchor differs from prepared manifest")
    return resume_session(schedule, run_id, stage, session)


def resume_session(
    schedule_raw: Any, run_id: str, stage_dir: Path | str, session_dir: Path | str,
) -> dict[str, Any]:
    """Read durable state without launching or retrying an indeterminate call."""
    stage, session = _paths(stage_dir, session_dir)
    schedule, run = _schedule(schedule_raw, run_id)
    with _locked_session(session):
        manifest, calls, summary = _read_state(schedule, run, stage, session)
        if summary["status"] in ("ready", "exhausted"):
            try:
                _assert_stage_and_work(schedule, run_id, stage, manifest, calls)
            except (SessionError, LocalToolError, ToolPolicyError, OSError, KeyError, ValueError) as exc:
                summary["status"] = "blocked"
                summary["blocked_reason"] = str(exc)
        return summary


def _validate_call_limits(
    wall_seconds: float, cpu_seconds: int, address_space_bytes: int,
    file_bytes_per_file: int,
) -> None:
    if (type(wall_seconds) not in (int, float) or not math.isfinite(wall_seconds)
        or not 0 < wall_seconds <= 300
        or type(cpu_seconds) is not int or not 1 <= cpu_seconds <= 300
        or type(address_space_bytes) is not int
        or not 64 * 1024 * 1024 <= address_space_bytes <= 1024 * 1024 * 1024
        or type(file_bytes_per_file) is not int
        or not 4096 <= file_bytes_per_file <= MAX_WORK_FILE_BYTES):
        raise SessionError("invalid local wall, CPU, address-space, or file-size limits")


def call_tool(
    schedule_raw: Any, run_id: str, stage_dir: Path | str, session_dir: Path | str,
    tool_id: str, executable: Path | str, *,
    wall_seconds: float = 30.0, cpu_seconds: int = 10,
    address_space_bytes: int = 512 * 1024 * 1024,
    file_bytes_per_file: int = 8 * 1024 * 1024,
) -> dict[str, Any]:
    """Reserve one call, execute sealed bytes, and write a terminal receipt."""
    stage, session = _paths(stage_dir, session_dir)
    tool = Path(executable)
    if not tool.is_absolute() or any(part in (".", "..") for part in tool.parts):
        raise SessionError("tool executable must be an absolute path without dot components")
    if type(tool_id) is not str or not tool_id:
        raise SessionError("tool_id is required")
    _validate_call_limits(wall_seconds, cpu_seconds, address_space_bytes, file_bytes_per_file)
    schedule, run = _schedule(schedule_raw, run_id)
    with _locked_session(session):
        manifest, calls, summary = _read_state(schedule, run, stage, session)
        if summary["status"] != "ready":
            raise SessionError(
                f"session is {summary['status']}: "
                f"{summary['blocked_reason'] or summary['pending_reason']}; "
                "no call or retry is permitted"
            )
        if len(calls) >= manifest["tool_call_cap"]:
            raise SessionError("stage-instance local tool_calls cap exhausted before launch")
        if len(calls) >= MAX_CALLS:
            raise SessionError("local journal call limit exhausted")
        snapshot, work_before, policy, policy_sha256 = _assert_stage_and_work(
            schedule, run_id, stage, manifest, calls
        )
        selected = next((item for item in policy["generic_tools"] if item["id"] == tool_id), None)
        if selected is None:
            raise SessionError("tool_id is absent from staged generic_tools")
        tool_bytes = _read_bounded_file(tool, "tool executable", MAX_EXECUTABLE_BYTES)
        executable_sha256 = hashlib.sha256(tool_bytes).hexdigest()
        if executable_sha256 != selected["executable_sha256"]:
            raise SessionError("tool executable SHA-256 differs from staged policy")
        if not os.access(tool, os.X_OK):
            raise SessionError("tool executable is not executable")
        now_ns = time.time_ns()
        wall_elapsed = _wall_elapsed(manifest["created_ns"], now_ns)
        reserved_active = float(wall_seconds) + ACTIVE_GUARD_SECONDS
        if reserved_active > manifest["active_budget_seconds"] - summary["active_seconds_charged"] + 1e-9:
            raise SessionError("local active budget exhausted before launch")
        if reserved_active > manifest["wall_budget_seconds"] - wall_elapsed + 1e-9:
            raise SessionError("session wall budget exhausted before launch")
        launch_deadline_ns = manifest["created_ns"] + int(
            (manifest["wall_budget_seconds"] - reserved_active) * 1_000_000_000
        )
        call_number = len(calls) + 1
        call_dir = session / "calls" / f"{call_number:06d}"
        call_dir.mkdir(mode=0o700)
        _fsync_directory(call_dir.parent)
        previous = calls[-1][1] if calls else None
        previous_digest = (hashlib.sha256(_read_bounded_file(
            session / "calls" / f"{call_number - 1:06d}" / "terminal.json",
            "previous terminal receipt", MAX_JOURNAL_BYTES
        )).hexdigest() if previous is not None else None)
        reservation = {
            "schema": SCHEMA, "call_number": call_number, "run_id": run_id,
            "budget_scope": BUDGET_SCOPE, "global_run_limits_enforced": False,
            "schedule_sha256": schedule["schedule_sha256"],
            "previous_terminal_sha256": previous_digest,
            "reserved_at_ns": now_ns, "tool_id": tool_id,
            "tool_version": selected["version"], "executable_sha256": executable_sha256,
            "policy_sha256": policy_sha256, "immutable_snapshot_sha256": _digest(snapshot),
            "work_before_sha256": _digest(work_before),
            "active_seconds_reserved": reserved_active,
            "launch_deadline_utc_ns": launch_deadline_ns,
            "limits_applied": {
                "wall_seconds": float(wall_seconds), "cpu_seconds": cpu_seconds,
                "address_space_bytes": address_space_bytes,
                "file_bytes_per_file": file_bytes_per_file,
            },
        }
        reservation_sha256 = _write_json(call_dir / "reservation.json", reservation)
        result = None
        launch_error = None
        elapsed = 0.0
        try:
            runtime_roots = default_python_runtime_roots()
            if time.time_ns() >= launch_deadline_ns:
                launch_error = "session wall budget expired after reservation before launch"
            else:
                start = time.monotonic()
                try:
                    result = run_sandboxed(
                        argv=[str(tool), str(stage / "case"), str(stage / "inputs"), str(stage / "work")],
                        cwd=stage / "case", read_roots=[stage / "case", stage / "inputs"],
                        write_roots=[stage / "work"], runtime_roots=runtime_roots,
                        stdout_path=call_dir / "stdout", stderr_path=call_dir / "stderr",
                        timeout_seconds=float(wall_seconds), cpu_seconds=cpu_seconds,
                        address_space_bytes=address_space_bytes,
                        file_bytes_per_file=file_bytes_per_file,
                        env={"HOME": str(stage / "work"), "TMPDIR": str(stage / "work")},
                        sealed_executable_bytes=tool_bytes,
                        sealed_executable_sha256=executable_sha256,
                        launch_deadline_utc_ns=launch_deadline_ns,
                    )
                finally:
                    elapsed = time.monotonic() - start
        except (SandboxError, SandboxUnavailable, OSError, ValueError) as exc:
            launch_error = f"{type(exc).__name__}: {exc}"
        if result is not None:
            launch_error = result.launch_error
        work_after = _work_inventory(stage)
        try:
            stage_unchanged = _immutable_snapshot(stage) == snapshot
        except (LocalToolError, OSError):
            stage_unchanged = False
        try:
            executable_unchanged = hashlib.sha256(
                _read_bounded_file(tool, "tool executable", MAX_EXECUTABLE_BYTES)
            ).hexdigest() == executable_sha256
        except ToolPolicyError:
            executable_unchanged = False
        sealed = (result is not None and result.sealed_executable_sha256 == executable_sha256
                  and result.launch_error is None)
        if result is not None and not sealed and launch_error is None:
            launch_error = "sealed executable launch was not confirmed"
        deliverables = manifest["deliverables"]
        output_paths = {entry["path"] for entry in work_after["files"]}
        deliverables_present = (
            all(name in output_paths for name in deliverables) if work_after["complete"] else None
        )
        if not stage_unchanged or not executable_unchanged:
            status = "stage_or_executable_mutated"
        elif result is not None and result.timed_out:
            status = "timeout"
        elif launch_error is not None:
            status = "launch_failure"
        elif result is None or result.exit_code != 0:
            status = "tool_failure"
        elif not work_after["complete"]:
            status = "output_inventory_incomplete"
        else:
            status = "success"
        active_charged = elapsed + ACTIVE_GUARD_SECONDS
        terminal = {
            "schema": SCHEMA, "classification": CLASSIFICATION, "notice": NOTICE,
            "budget_scope": BUDGET_SCOPE, "global_run_limits_enforced": False,
            "call_number": call_number, "reservation_sha256": reservation_sha256,
            "run_id": run_id, "run_sha256": run["run_sha256"],
            "schedule_sha256": schedule["schedule_sha256"],
            "tool_id": tool_id, "tool_version": selected["version"],
            "executable_sha256": executable_sha256,
            "sealed_executable_sha256": result.sealed_executable_sha256 if result else None,
            "execution_bytes_sealed": sealed,
            "executable_unchanged_after_run": executable_unchanged,
            "policy_sha256": policy_sha256,
            "runtime_image_sha256_declared": policy["runtime_image_sha256"],
            "runtime_image_verified": False,
            "status": status, "exit_code": result.exit_code if result else None,
            "timed_out": result.timed_out if result else False,
            "launch_error": launch_error,
            "sandbox_duration_seconds": result.duration_seconds if result else None,
            "local_elapsed_seconds": elapsed,
            "active_seconds_charged": active_charged,
            "active_budget_overrun": (
                summary["active_seconds_charged"] + active_charged
                > manifest["active_budget_seconds"] + 1e-9
            ),
            "stage_unchanged_after_run": stage_unchanged,
            "output_inventory_complete": work_after["complete"],
            "output_inventory_reason": work_after["reason"],
            "work_before_sha256": _digest(work_before),
            "work_after_sha256": _digest(work_after),
            "outputs": [{key: item[key] for key in ("path", "bytes", "sha256")}
                        for item in work_after["files"]],
            "deliverables": deliverables, "deliverables_present": deliverables_present,
            "stdout": str(call_dir / "stdout") if (call_dir / "stdout").exists() else None,
            "stderr": str(call_dir / "stderr") if (call_dir / "stderr").exists() else None,
            "reserved_tool_calls": call_number, "provider_calls": 0,
            "measured_tokens": None, "criterion_4": "not_assessed",
            "provider_receipt": False,
        }
        _write_json(call_dir / "terminal.json", terminal)
        return terminal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("schedule")
    init.add_argument("run_id")
    init.add_argument("stage_dir")
    init.add_argument("session_dir")
    init.add_argument("--active-budget-seconds", type=float)
    init.add_argument("--wall-budget-seconds", type=float)
    status = sub.add_parser("status")
    call = sub.add_parser("call")
    for command in (status, call):
        command.add_argument("schedule")
        command.add_argument("run_id")
        command.add_argument("stage_dir")
        command.add_argument("session_dir")
    call.add_argument("tool_id")
    call.add_argument("executable")
    call.add_argument("--wall-seconds", type=float, default=30.0)
    call.add_argument("--cpu-seconds", type=int, default=10)
    call.add_argument("--address-space-bytes", type=int, default=512 * 1024 * 1024)
    call.add_argument("--file-bytes-per-file", type=int, default=8 * 1024 * 1024)
    args = parser.parse_args(argv)
    try:
        schedule = _read_schedule(args.schedule)
        if args.command == "init":
            report = create_session(
                schedule, args.run_id, args.stage_dir, args.session_dir,
                active_budget_seconds=args.active_budget_seconds,
                wall_budget_seconds=args.wall_budget_seconds,
            )
        elif args.command == "status":
            report = resume_session(schedule, args.run_id, args.stage_dir, args.session_dir)
        else:
            report = call_tool(
                schedule, args.run_id, args.stage_dir, args.session_dir,
                args.tool_id, args.executable, wall_seconds=args.wall_seconds,
                cpu_seconds=args.cpu_seconds,
                address_space_bytes=args.address_space_bytes,
                file_bytes_per_file=args.file_bytes_per_file,
            )
    except (SessionError, LocalToolError, StageVerificationError, ReleaseVerificationError,
            ToolPolicyError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"Staged local session failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    if args.command != "call":
        return 0 if report["status"] == "ready" else 3
    return {"success": 0, "launch_failure": 4, "timeout": 5, "tool_failure": 6,
            "output_inventory_incomplete": 7, "stage_or_executable_mutated": 8}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
