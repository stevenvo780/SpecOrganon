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
deletes possibly effected work. A host-local claim admits only one staged
owner or one-shot owner for each scheduled attempt. The first call claims;
init alone does not. Budgets are enforced for the winning local session only.
Provider/model/study budgets and external custody are not enforced here.

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
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator

import local_run_admission as admission
from local_replay_sandbox import (
    _MAX_CONFIG_BYTES,
    _roots,
    _validate_env,
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
    _held_retry_gate,
    _immutable_snapshot,
    _inventory,
    _private_receipt_dir,
    _require_retry_gate,
)
from tool_policy import (
    MAX_POLICY_BYTES,
    ToolPolicyError,
    _check_directory_chain,
    _open_directory_chain,
    _read_bounded_file,
    _same_file_state,
    execution_profile,
    validate_tool_policy_bytes,
)
from verify_released_run import ReleaseVerificationError, _read_schedule
from verify_staged_run import StageVerificationError, verify_stage


CLASSIFICATION = "development_staged_local_tool_session_unsealed"
ANCHOR_CLASSIFICATION = "development_staged_local_tool_session_anchor_unsealed"
NOTICE = (
    "Offline local generic tools only. Schedule and stage have no external custody; "
    "runtime image is declared, not sealed. No provider calls, measured model "
    "tokens, cost, or criterion-4 assessment. One configured host-local registry "
    "admits one stage/session or one-shot owner at attempt 1; budgets apply "
    "only to that winner, not globally across providers/models/studies. "
    "Same-UID mutation and clock changes remain outside this journal's guarantees."
)
RETRY_NOTICE = NOTICE.replace(
    "at attempt 1", "per scheduled attempt"
)
BUDGET_SCOPE = "stage_instance_local"
SCHEMA = 1
ACTIVE_GUARD_SECONDS = 1.0
MAX_SESSION_WALL_SECONDS = 86400.0
MAX_JOURNAL_BYTES = 4 * 1024 * 1024
MAX_CALLS = 10000
MAX_TOOL_ARGS_BYTES = 16 * 1024
MAX_TOOL_ARGS_DEPTH = 32
MAX_ANALYSIS_SCRIPT_BYTES = 256 * 1024
MAX_ANALYSIS_JSON_BYTES = 128 * 1024


class SessionError(ValueError):
    """The session is invalid, exhausted, indeterminate, or cannot launch."""


def _digest(value: Any) -> str:
    data = _canonical_bytes(value)
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(value: Any, *, newline: bool = False) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + ("\n" if newline else "")).encode("utf-8")


def _canonical_tool_args(tool_args: dict[str, Any] | None) -> bytes | None:
    """Bound one JSON object before a claim, keeping its bytes out of the journal."""
    if tool_args is None:
        return None
    if type(tool_args) is not dict:
        raise SessionError("tool_args must be a JSON object")
    stack: list[tuple[Any, int]] = [(tool_args, 1)]
    active: set[int] = set()
    nodes = 0
    while stack:
        value, depth = stack.pop()
        if depth == 0:
            active.remove(id(value))
            continue
        nodes += 1
        if nodes > MAX_TOOL_ARGS_BYTES:
            raise SessionError("tool_args exceeds maximum canonical byte length")
        if depth > MAX_TOOL_ARGS_DEPTH:
            raise SessionError("tool_args exceeds maximum JSON depth")
        if type(value) in (dict, list):
            if len(value) > MAX_TOOL_ARGS_BYTES:
                raise SessionError("tool_args exceeds maximum canonical byte length")
            if id(value) in active:
                raise SessionError("tool_args contains a JSON cycle")
            active.add(id(value))
            stack.append((value, 0))
            if type(value) is dict:
                if any(type(key) is not str for key in value):
                    raise SessionError("tool_args object keys must be strings")
                if any(len(key) > MAX_TOOL_ARGS_BYTES for key in value):
                    raise SessionError("tool_args exceeds maximum canonical byte length")
                stack.extend((item, depth + 1) for item in value.values())
            else:
                stack.extend((item, depth + 1) for item in value)
        elif type(value) is float:
            if not math.isfinite(value):
                raise SessionError("tool_args contains a non-finite number")
        elif type(value) is str:
            if len(value) > MAX_TOOL_ARGS_BYTES:
                raise SessionError("tool_args exceeds maximum canonical byte length")
        elif type(value) not in (int, bool, type(None)):
            raise SessionError("tool_args contains a non-JSON value")
    try:
        canonical = _canonical_bytes(tool_args)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise SessionError("tool_args cannot be encoded as canonical JSON") from exc
    if len(canonical) > MAX_TOOL_ARGS_BYTES:
        raise SessionError("tool_args exceeds maximum canonical byte length")
    return canonical


def _parse_tool_args_json(raw: str) -> dict[str, Any]:
    try:
        if len(raw.encode("utf-8")) > MAX_TOOL_ARGS_BYTES:
            raise SessionError("--args-json exceeds maximum input byte length")

        def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise SessionError("--args-json contains a duplicate object key")
                result[key] = value
            return result

        def reject_constant(value: str) -> None:
            raise SessionError(f"--args-json contains non-JSON constant {value}")

        def canonical_roundtrip_decimal(token: str) -> float:
            try:
                value = float(token)
                original = Decimal(token)
            except (InvalidOperation, OverflowError, ValueError) as exc:
                raise SessionError("--args-json contains an invalid decimal") from exc
            if (not math.isfinite(value)
                or original != Decimal(_canonical_bytes(value).decode("ascii"))):
                raise SessionError("--args-json decimal value changes when canonicalized")
            return value

        parsed = json.loads(raw, object_pairs_hook=unique_object,
                            parse_constant=reject_constant,
                            parse_float=canonical_roundtrip_decimal)
    except SessionError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise SessionError("--args-json is invalid JSON") from exc
    if type(parsed) is not dict:
        raise SessionError("--args-json must be a JSON object")
    _canonical_tool_args(parsed)
    return parsed


def _assert_sandbox_config_fits(
    argv: list[str], stage: Path, runtime_roots: tuple[Path, ...],
    cpu_seconds: int, address_space_bytes: int, file_bytes_per_file: int,
    *, read_roots: list[Path] | None = None,
    write_roots: list[Path] | None = None,
) -> None:
    """Mirror the sandbox's bounded config before admission spends the call."""
    try:
        reads = _roots(read_roots if read_roots is not None else
                       [stage / "case", stage / "inputs"], directories_only=False)
        writes = _roots(write_roots if write_roots is not None else
                        [stage / "work"], directories_only=True)
        runtimes = _roots(runtime_roots, directories_only=False, allow_char_device=True)
        child_env = _validate_env(None, writes, stage / "case")
        config = {
            "argv": argv, "read_roots": reads, "write_roots": writes,
            "runtime_roots": runtimes, "env": child_env,
            "cpu_seconds": cpu_seconds, "address_space_bytes": address_space_bytes,
            "file_bytes_per_file": file_bytes_per_file,
            # A real Linux file descriptor needs fewer digits than sys.maxsize.
            "sealed_executable_fd": sys.maxsize,
        }
        encoded = json.dumps(config, separators=(",", ":")).encode("utf-8")
    except (SandboxError, TypeError, ValueError, UnicodeError, OSError) as exc:
        raise SessionError("sandbox argument configuration is invalid") from exc
    if len(encoded) > _MAX_CONFIG_BYTES:
        raise SessionError("tool_args exceeds sandbox configuration byte limit")


def _paths(stage_dir: Path | str, session_dir: Path | str) -> tuple[Path, Path]:
    stage, session = Path(stage_dir), Path(session_dir)
    if not stage.is_absolute() or not session.is_absolute():
        raise SessionError("stage and session paths must be absolute")
    if any(part in (".", "..") for path in (stage, session) for part in path.parts):
        raise SessionError("paths must not contain dot components")
    if stage == session or stage.is_relative_to(session) or session.is_relative_to(stage):
        raise SessionError("session directory must be separate from stage")
    return stage, session


def _paths_overlap(first: Path, second: Path) -> bool:
    """Compare names and existing directory identities, including path aliases."""
    try:
        resolved_first = first.resolve(strict=False)
        resolved_second = second.resolve(strict=False)
        if (resolved_first == resolved_second
            or resolved_first.is_relative_to(resolved_second)
            or resolved_second.is_relative_to(resolved_first)):
            return True
        for path, root in ((first, second), (second, first)):
            try:
                root_info = root.stat()
            except FileNotFoundError:
                continue
            for ancestor in (path, *path.parents):
                try:
                    info = ancestor.stat()
                except FileNotFoundError:
                    continue
                if (info.st_dev, info.st_ino) == (root_info.st_dev, root_info.st_ino):
                    return True
    except (OSError, RuntimeError) as exc:
        raise SessionError("gate, admission, or session path cannot be checked") from exc
    return False


def _assert_gated_paths_disjoint(
    session: Path, gate_root: Path | str | None, admission_root: Path | str | None,
) -> None:
    if gate_root is None:
        return
    try:
        gate = admission.configured_root(gate_root)
        registry = admission.configured_root(admission_root)
    except (admission.AdmissionError, OSError, TypeError) as exc:
        raise SessionError("gate or admission root path is invalid") from exc
    if _paths_overlap(session, gate):
        raise SessionError("session directory must be outside gate root")
    if _paths_overlap(gate, registry):
        raise SessionError("gate and admission roots must be disjoint")


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
    expected = {
            "schema": SCHEMA, "classification": ANCHOR_CLASSIFICATION,
            "run_id": run["run_id"], "run_sha256": run["run_sha256"],
            "schedule_sha256": schedule["schedule_sha256"],
            "stage_dir": str(stage), "session_dir": str(session),
            "immutable_snapshot_sha256": manifest["immutable_snapshot_sha256"],
            "created_ns": manifest["created_ns"],
            "local_run_admission_root": manifest["local_run_admission_root"],
            "local_run_admission_root_identity": manifest["local_run_admission_root_identity"],
            "local_run_admission_scope": admission.SCOPE,
            "local_run_claim_sha256": manifest["local_run_claim_sha256"],
            "attempt_number": manifest["attempt_number"],
            "budget_scope": BUDGET_SCOPE, "global_run_limits_enforced": False,
    }
    if "release_gate_root" in manifest:
        expected.update({key: manifest[key] for key in (
            "release_gate_root", "release_dir", "claim_sha256", "publication_sha256"
        )})
    if hashlib.sha256(data).hexdigest() != manifest.get("anchor_sha256") or anchor != expected:
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


def _analysis_source(
    stage: Path, work_before: dict[str, Any], tool_args: dict[str, Any] | None,
    calls: list[tuple[dict[str, Any] | None, dict[str, Any] | None]],
) -> tuple[str, str | None]:
    """Bind the source and any previous host-owned metrics before a new call."""
    if (type(tool_args) is not dict or set(tool_args) != {"script_sha256"}
            or not _is_sha256(tool_args["script_sha256"])):
        raise SessionError("analysis tool requires one exact script_sha256 argument")
    source = next((item for item in work_before["files"]
                   if item["path"] == "analysis.py"), None)
    if (source is None or not 0 < source["bytes"] <= MAX_ANALYSIS_SCRIPT_BYTES
            or source["sha256"] != tool_args["script_sha256"]):
        raise SessionError("analysis.py is absent, oversized, or differs from tool arguments")
    raw = _read_bounded_file(stage / "work" / "analysis.py", "analysis source",
                             MAX_ANALYSIS_SCRIPT_BYTES)
    info = os.stat(stage / "work" / "analysis.py", follow_symlinks=False)
    if (not raw or len(raw) != source["bytes"]
            or hashlib.sha256(raw).hexdigest() != source["sha256"]
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        raise SessionError("analysis source identity or private mode differs")
    old_metrics = next((item for item in work_before["files"]
                        if item["path"] == "metrics.json"), None)
    if old_metrics is None:
        return source["sha256"], None
    prior_sha = next((terminal.get("analysis_metrics_sha256") for _, terminal in reversed(calls)
                      if terminal is not None and terminal.get("analysis_status") == "valid"), None)
    if prior_sha != old_metrics["sha256"]:
        raise SessionError("existing metrics.json lacks matching host analysis provenance")
    return source["sha256"], prior_sha


def _analysis_output(path: Path, exit_code: int, maximum_file_bytes: int
                     ) -> tuple[str, str, int, str, dict[str, Any] | None]:
    """Classify untrusted participant stdout, retaining its exact journal bytes."""
    raw = _read_bounded_file(path, "analysis stdout", maximum_file_bytes)
    digest = hashlib.sha256(raw).hexdigest()
    if exit_code != 0:
        return "participant_failed", "participant process exited nonzero", len(raw), digest, None
    if len(raw) > MAX_ANALYSIS_JSON_BYTES:
        return "error", "analysis stdout exceeds 128 KiB", len(raw), digest, None
    try:
        decoded = raw.decode("utf-8")
    except UnicodeError:
        return "error", "analysis stdout is not UTF-8", len(raw), digest, None

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def finite(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("nonfinite JSON number")
        return parsed

    try:
        value = json.loads(decoded, object_pairs_hook=unique,
                           parse_float=finite,
                           parse_constant=lambda _value: (_ for _ in ()).throw(
                               ValueError("nonfinite JSON value")))
        if type(value) is not dict or len(_canonical_bytes(value, newline=True)) > MAX_ANALYSIS_JSON_BYTES:
            raise ValueError("analysis result is not a bounded JSON object")
    except (UnicodeError, ValueError, OverflowError, RecursionError, TypeError):
        return "invalid_json", "analysis stdout is not a strict finite JSON object", len(raw), digest, None
    return "valid", "analysis result is a strict JSON object", len(raw), digest, value


def _publish_analysis_metrics(work: Path, value: dict[str, Any] | None,
                              old_sha: str | None) -> str | None:
    """Replace or retire only a prior host-authored metrics file after sandbox exit."""
    path = work / "metrics.json"
    if old_sha is not None:
        raw = _read_bounded_file(path, "previous host metrics", MAX_ANALYSIS_JSON_BYTES)
        info = os.stat(path, follow_symlinks=False)
        if (hashlib.sha256(raw).hexdigest() != old_sha
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise SessionError("previous host metrics changed before retirement")
    elif path.exists() or path.is_symlink():
        raise SessionError("unexpected metrics.json appeared before host publication")
    if value is None:
        if old_sha is not None:
            os.unlink(path)
            _fsync_directory(work)
        return None
    temporary = work / f".metrics-{secrets.token_hex(16)}"
    digest = _write_json(temporary, value)
    os.replace(temporary, path)
    _fsync_directory(work)
    return digest


def _valid_terminal(
    terminal: dict[str, Any], reservation: dict[str, Any], run: dict[str, Any],
    schedule: dict[str, Any], reservation_sha256: str,
    deliverables: list[str], call_dir: Path, policy: dict[str, Any],
) -> bool:
    selected = next((item for item in policy["generic_tools"]
                     if item["id"] == reservation.get("tool_id")), None)
    if selected is None or selected["executable_sha256"] != reservation.get("executable_sha256"):
        return False
    profile = execution_profile(selected)
    if policy["schema"] == 2:
        if (reservation.get("execution_profile") != profile
                or terminal.get("execution_profile") != profile):
            return False
    elif "execution_profile" in reservation or "execution_profile" in terminal:
        return False
    if profile == "analysis_readonly":
        if (not _is_sha256(reservation.get("analysis_script_sha256"))
                or terminal.get("analysis_script_sha256") != reservation["analysis_script_sha256"]
                or terminal.get("analysis_status") not in
                {None, "valid", "participant_failed", "invalid_json", "error"}
                or type(terminal.get("analysis_diagnostic")) is not str
                or len(terminal["analysis_diagnostic"]) > 160
                or type(terminal.get("analysis_work_readonly_unchanged")) is not bool
                or not _is_sha256(terminal.get("analysis_work_after_child_sha256"))
                or type(terminal.get("analysis_stdout_bytes")) is not int
                or terminal["analysis_stdout_bytes"] < 0
                or not _is_sha256(terminal.get("analysis_stdout_sha256"))):
            return False
        if terminal["status"] == "success":
            if (terminal["analysis_status"] is None
                    or terminal["analysis_work_readonly_unchanged"] is not True
                    or terminal["analysis_work_after_child_sha256"]
                    != reservation["work_before_sha256"]):
                return False
            try:
                observed_status, observed_diagnostic, size, digest, parsed = _analysis_output(
                    call_dir / "stdout", terminal["exit_code"],
                    reservation["limits_applied"]["file_bytes_per_file"])
            except (OSError, ToolPolicyError, ValueError, TypeError, KeyError):
                return False
            if (terminal["analysis_status"] != observed_status
                    or terminal["analysis_diagnostic"] != observed_diagnostic
                    or terminal["analysis_stdout_bytes"] != size
                    or terminal["analysis_stdout_sha256"] != digest):
                return False
            expected_metrics = (hashlib.sha256(_canonical_bytes(parsed, newline=True)).hexdigest()
                                if parsed is not None else None)
            output_metrics = next((item["sha256"] for item in terminal.get("outputs", [])
                                   if type(item) is dict and item.get("path") == "metrics.json"), None)
            if (terminal.get("analysis_metrics_sha256") != expected_metrics
                    or output_metrics != expected_metrics):
                return False
        elif terminal.get("analysis_status") is not None:
            return False
    elif any(key.startswith("analysis_") for key in (*reservation, *terminal)):
        return False
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
        (exit_code != 0 if profile != "analysis_readonly"
         else type(exit_code) is not int or exit_code == 79)
        or type(exit_code) is not int or timed_out is not False
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
    if status == "readonly_work_mutated" and (
        profile != "analysis_readonly"
        or terminal.get("analysis_work_readonly_unchanged") is not False
    ):
        return False
    if status == "analysis_source_rejected" and (
        profile != "analysis_readonly" or exit_code != 79
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
    if profile == "analysis_readonly":
        stream = call_dir / "stdout"
        try:
            raw_stream = (_read_bounded_file(stream, "analysis stdout",
                                             reservation["limits_applied"]["file_bytes_per_file"])
                          if stream.exists() else b"")
        except (OSError, ToolPolicyError, TypeError, KeyError, ValueError):
            return False
        if (terminal["analysis_stdout_bytes"] != len(raw_stream)
                or terminal["analysis_stdout_sha256"] != hashlib.sha256(raw_stream).hexdigest()
                or (status != "success" and terminal.get("analysis_metrics_sha256") is not None)):
            return False
    return (
        terminal.get("schema") == SCHEMA
        and terminal.get("classification") == CLASSIFICATION
        and terminal.get("notice") == (RETRY_NOTICE if reservation["attempt_number"] > 1 else NOTICE)
        and terminal.get("call_number") == reservation["call_number"]
        and terminal.get("reservation_sha256") == reservation_sha256
        and terminal.get("run_id") == run["run_id"]
        and terminal.get("run_sha256") == run["run_sha256"]
        and terminal.get("schedule_sha256") == schedule["schedule_sha256"]
        and terminal.get("tool_id") == reservation["tool_id"]
        and terminal.get("tool_version") == reservation["tool_version"]
        and (("tool_args_sha256" not in reservation and "tool_args_sha256" not in terminal)
             or ("tool_args_sha256" in reservation
                 and terminal.get("tool_args_sha256") == reservation["tool_args_sha256"]))
        and terminal.get("executable_sha256") == reservation["executable_sha256"]
        and terminal.get("policy_sha256") == reservation["policy_sha256"]
        and terminal.get("work_before_sha256") == reservation["work_before_sha256"]
        and _is_sha256(terminal.get("work_after_sha256"))
        and type(status) is str
        and status in {
            "success", "timeout", "launch_failure", "tool_failure",
            "output_inventory_incomplete", "stage_or_executable_mutated",
            "readonly_work_mutated", "analysis_source_rejected",
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
        and terminal.get("local_run_admission_root") == reservation["local_run_admission_root"]
        and terminal.get("local_run_admission_root_identity") == reservation["local_run_admission_root_identity"]
        and terminal.get("local_run_admission_scope") == admission.SCOPE
        and terminal.get("local_run_claim_sha256") == reservation["local_run_claim_sha256"]
        and type(terminal.get("attempt_number")) is int
        and terminal.get("attempt_number") == reservation["attempt_number"]
    )


def _read_state(
    schedule: dict[str, Any], run: dict[str, Any], stage: Path, session: Path,
    admission_root: Path | str | None,
) -> tuple[dict[str, Any], list[tuple[dict[str, Any] | None, dict[str, Any] | None]], dict[str, Any]]:
    manifest = _read_json(session / "session.json")
    if (
        manifest.get("schema") != SCHEMA or manifest.get("classification") != CLASSIFICATION
        or manifest.get("run_id") != run["run_id"]
        or manifest.get("run_sha256") != run["run_sha256"]
        or manifest.get("schedule_sha256") != schedule["schedule_sha256"]
        or manifest.get("stage_dir") != str(stage)
        or manifest.get("session_dir") != str(session)
        or manifest.get("notice") != (
            RETRY_NOTICE if type(manifest.get("attempt_number")) is int
            and manifest["attempt_number"] > 1 else NOTICE
        )
        or manifest.get("budget_scope") != BUDGET_SCOPE
        or manifest.get("global_run_limits_enforced") is not False
        or manifest.get("tool_call_cap") != schedule["per_run_limits"]["tool_calls"]
        or manifest.get("policy_sha256") != schedule["inputs"]["tool_policy"]["sha256"]
        or not _is_sha256(manifest.get("immutable_snapshot_sha256"))
        or not _is_sha256(manifest.get("initial_work_sha256"))
        or not _is_sha256(manifest.get("anchor_sha256"))
        or type(manifest.get("local_run_admission_root")) is not str
        or not _is_sha256(manifest.get("local_run_admission_root_identity"))
        or manifest.get("local_run_admission_scope") != admission.SCOPE
        or not _is_sha256(manifest.get("local_run_claim_sha256"))
        or type(manifest.get("attempt_number")) is not int
        or not 1 <= manifest.get("attempt_number") <= admission.MAX_ATTEMPT_NUMBER
        or type(manifest.get("deliverables")) is not list
    ):
        raise SessionError("session identity differs from independent schedule or paths")
    gate_fields = ("release_gate_root", "release_dir", "claim_sha256", "publication_sha256")
    has_gate = any(key in manifest for key in gate_fields)
    if manifest["attempt_number"] > 1 and not has_gate:
        raise SessionError("retry session lacks gate provenance")
    if has_gate and (type(manifest.get("release_gate_root")) is not str
                     or type(manifest.get("release_dir")) is not str
                     or not _is_sha256(manifest.get("claim_sha256"))
                     or not _is_sha256(manifest.get("publication_sha256"))):
        raise SessionError("session gate provenance is incomplete or invalid")
    if has_gate:
        _assert_gated_paths_disjoint(
            session, manifest["release_gate_root"], manifest["local_run_admission_root"]
        )
    if (type(manifest.get("active_budget_seconds")) not in (float, int)
        or type(manifest.get("wall_budget_seconds")) not in (float, int)
        or type(manifest.get("created_ns")) is not int
        or not 0 < manifest["active_budget_seconds"] <= schedule["per_run_limits"]["active_seconds"]
        or not 0 < manifest["wall_budget_seconds"] <= MAX_SESSION_WALL_SECONDS):
        raise SessionError("session budget or creation time is invalid")
    _check_anchor(stage, session, schedule, run, manifest)
    policy_data = _read_bounded_file(stage / "inputs" / "tool_policy",
                                     "staged tool policy", MAX_POLICY_BYTES)
    if hashlib.sha256(policy_data).hexdigest() != manifest["policy_sha256"]:
        raise SessionError("staged tool policy changed after session creation")
    policy = validate_tool_policy_bytes(
        policy_data, expected_limits=schedule["per_run_limits"])
    calls_root = session / "calls"
    _check_private_directory(calls_root)
    all_names = sorted(path.name for path in calls_root.iterdir())
    # A crash while preparing a reservation can leave an unpublished private
    # directory. No numbered call was reserved and no compliant launch can
    # have occurred; retain it as evidence and allow the same owner to retry.
    for name in (item for item in all_names if item.startswith(".prepared-")):
        prepared = calls_root / name
        _check_private_directory(prepared)
        if {entry.name for entry in prepared.iterdir()} - {"reservation.json"}:
            raise SessionError("unpublished reservation directory has unexpected entries")
    names = [name for name in all_names if not name.startswith(".prepared-")]
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
                or reservation.get("local_run_admission_root") != manifest["local_run_admission_root"]
                or reservation.get("local_run_admission_root_identity") != manifest["local_run_admission_root_identity"]
                or reservation.get("local_run_admission_scope") != admission.SCOPE
                or reservation.get("local_run_claim_sha256") != manifest["local_run_claim_sha256"]
                or type(reservation.get("attempt_number")) is not int
                or reservation.get("attempt_number") != manifest["attempt_number"]
                or reservation.get("previous_terminal_sha256") != previous_digest
                or reservation.get("policy_sha256") != manifest["policy_sha256"]
                or reservation.get("immutable_snapshot_sha256") != manifest["immutable_snapshot_sha256"]
                or not _is_sha256(reservation.get("work_before_sha256"))
                or not _is_sha256(reservation.get("executable_sha256"))
                or type(reservation.get("tool_id")) is not str
                or type(reservation.get("tool_version")) is not str
                or (selected := next((item for item in policy["generic_tools"]
                                      if item["id"] == reservation.get("tool_id")), None)) is None
                or reservation.get("tool_version") != selected["version"]
                or reservation.get("executable_sha256") != selected["executable_sha256"]
                or (policy["schema"] == 2 and reservation.get("execution_profile")
                    != execution_profile(selected))
                or (policy["schema"] == 1 and "execution_profile" in reservation)
                or (execution_profile(selected) == "analysis_readonly" and
                    (not _is_sha256(reservation.get("analysis_script_sha256"))
                     or "tool_args_sha256" not in reservation))
                or ("tool_args_sha256" in reservation
                    and not _is_sha256(reservation["tool_args_sha256"]))
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
                manifest["deliverables"], call_dir, policy,
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
    claim_reason = None
    claim_status = "unclaimed"
    root_descriptor = {
        key: manifest[key] for key in ("local_run_admission_root",
                                       "local_run_admission_root_identity",
                                       "local_run_admission_scope")
    }
    selected_owner = admission.owner("staged", stage, session)
    try:
        if admission.descriptor(admission_root, create=False) != root_descriptor:
            raise admission.AdmissionError("configured admission registry root differs from session")
        claim_sha256 = admission.require_claim(
            schedule["schedule_sha256"], run["run_id"], selected_owner,
            root_descriptor, override=admission_root, allow_missing=not calls,
            attempt_number=manifest["attempt_number"],
        )
        if claim_sha256 is not None:
            if claim_sha256 != manifest["local_run_claim_sha256"]:
                raise admission.AdmissionError("local admission claim digest differs from session")
            claim_status = "claimed"
    except (admission.AdmissionError, OSError) as exc:
        claim_status = "blocked"
        claim_reason = str(exc)
    gate_reason = None
    if has_gate:
        try:
            _require_retry_gate(
                schedule, run["run_id"], manifest, manifest["release_gate_root"]
            )
        except (LocalToolError, OSError, ValueError) as exc:
            gate_reason = str(exc)
    last = calls[-1][1] if calls and pending is None else None
    blocked_reason = claim_reason or gate_reason
    if blocked_reason is None and last is not None and (last.get("output_inventory_complete") is not True
                              or last.get("stage_unchanged_after_run") is not True
                              or last.get("status") == "stage_or_executable_mutated"
                              or (last.get("execution_profile") == "analysis_readonly"
                                  and last.get("status") != "success")
                              or last.get("active_budget_overrun") is True):
        blocked_reason = "previous receipt cannot establish a complete, unchanged continuation"
    exhausted_reason = None
    if len(calls) >= manifest["tool_call_cap"]:
        exhausted_reason = "stage-instance local tool_calls cap exhausted before launch"
    elif charged + ACTIVE_GUARD_SECONDS >= manifest["active_budget_seconds"]:
        exhausted_reason = "local active budget exhausted before launch"
    elif wall_elapsed + ACTIVE_GUARD_SECONDS >= manifest["wall_budget_seconds"]:
        exhausted_reason = "session wall budget exhausted before launch"
    status = ("blocked" if blocked_reason else "indeterminate" if pending is not None
              else "exhausted" if exhausted_reason else "ready")
    summary = {
        "schema": SCHEMA, "classification": CLASSIFICATION, "notice": manifest["notice"],
        "budget_scope": BUDGET_SCOPE, "global_run_limits_enforced": False,
        **root_descriptor, "local_run_claim_sha256": manifest["local_run_claim_sha256"],
        "local_run_claim_status": claim_status, "attempt_number": manifest["attempt_number"],
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
    admission_root: Path | str | None = None, gate_root: Path | str | None = None,
) -> dict[str, Any]:
    """Verify an empty stage exactly once and create a new durable session."""
    stage, session = _paths(stage_dir, session_dir)
    _assert_gated_paths_disjoint(session, gate_root, admission_root)
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
    _require_retry_gate(schedule, run_id, verified, gate_root)
    after = _immutable_snapshot(stage)
    if before != after:
        raise SessionError("stage changed across initial verification")
    _check_snapshot_bindings(schedule, run_id, stage, after)
    policy, policy_sha256 = _policy(stage, schedule, run_id, after)
    work = _work_inventory(stage)
    if not work["complete"] or work["files"] or set(work["directories"]) != {""}:
        raise SessionError("stage work directory must be completely empty at init")
    attempt_number = verified["attempt_number"]
    root_descriptor = admission.descriptor(admission_root)
    selected_owner = admission.owner("staged", stage, session)
    claim_sha256 = admission.claim_digest(
        schedule["schedule_sha256"], run_id, selected_owner, root_descriptor,
        attempt_number=attempt_number,
    )
    gate_provenance = (
        {"release_gate_root": str(gate_root),
         "release_dir": verified["release_dir"],
         "claim_sha256": verified["claim_sha256"],
         "publication_sha256": verified["publication_sha256"]}
        if verified["release_dir"] is not None else {}
    )
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
        **root_descriptor, "local_run_claim_sha256": claim_sha256,
        "attempt_number": attempt_number,
        **gate_provenance,
        "budget_scope": BUDGET_SCOPE, "global_run_limits_enforced": False,
    }
    anchor_sha256 = hashlib.sha256(_canonical_bytes(anchor, newline=True)).hexdigest()
    manifest = {
        "schema": SCHEMA, "classification": CLASSIFICATION,
        "notice": RETRY_NOTICE if attempt_number > 1 else NOTICE,
        "budget_scope": BUDGET_SCOPE, "global_run_limits_enforced": False,
        "run_id": run_id, "run_sha256": verified["run_sha256"],
        "schedule_sha256": schedule["schedule_sha256"], "stage_dir": str(stage),
        "session_dir": str(session), "created_ns": created_ns,
        "immutable_snapshot_sha256": _digest(after), "initial_work_sha256": _digest(work),
        "anchor_sha256": anchor_sha256,
        **root_descriptor, "local_run_claim_sha256": claim_sha256,
        "attempt_number": attempt_number,
        **gate_provenance,
        "policy_sha256": policy_sha256, "tool_call_cap": policy["limits"]["tool_calls"],
        "deliverables": case_manifest["deliverables"],
        "active_budget_seconds": float(active_budget),
        "wall_budget_seconds": float(wall_budget),
    }
    _write_json(session / "session.json", manifest)
    if _write_anchor(stage, run_id, anchor) != anchor_sha256:
        raise SessionError("published stage/run anchor differs from prepared manifest")
    return resume_session(schedule, run_id, stage, session, admission_root=admission_root)


def resume_session(
    schedule_raw: Any, run_id: str, stage_dir: Path | str, session_dir: Path | str,
    *, admission_root: Path | str | None = None,
) -> dict[str, Any]:
    """Read durable state without launching or retrying an indeterminate call."""
    stage, session = _paths(stage_dir, session_dir)
    schedule, run = _schedule(schedule_raw, run_id)
    with _locked_session(session):
        manifest, calls, summary = _read_state(schedule, run, stage, session, admission_root)
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
    tool_args: dict[str, Any] | None = None,
    wall_seconds: float = 30.0, cpu_seconds: int = 10,
    address_space_bytes: int = 512 * 1024 * 1024,
    file_bytes_per_file: int = 8 * 1024 * 1024,
    admission_root: Path | str | None = None,
) -> dict[str, Any]:
    """Reserve one call, execute sealed bytes, and write a terminal receipt."""
    canonical_args = _canonical_tool_args(tool_args)
    tool_args_sha256 = (hashlib.sha256(canonical_args).hexdigest()
                        if canonical_args is not None else None)
    stage, session = _paths(stage_dir, session_dir)
    tool = Path(executable)
    if not tool.is_absolute() or any(part in (".", "..") for part in tool.parts):
        raise SessionError("tool executable must be an absolute path without dot components")
    if type(tool_id) is not str or not tool_id:
        raise SessionError("tool_id is required")
    _validate_call_limits(wall_seconds, cpu_seconds, address_space_bytes, file_bytes_per_file)
    schedule, run = _schedule(schedule_raw, run_id)
    with _locked_session(session), ExitStack() as retry_gate_guard:
        manifest, calls, summary = _read_state(schedule, run, stage, session, admission_root)
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
        profile = execution_profile(selected)
        analysis_script_sha: str | None = None
        old_metrics_sha: str | None = None
        if profile == "analysis_readonly":
            analysis_script_sha, old_metrics_sha = _analysis_source(
                stage, work_before, tool_args, calls)
        tool_bytes = _read_bounded_file(tool, "tool executable", MAX_EXECUTABLE_BYTES)
        executable_sha256 = hashlib.sha256(tool_bytes).hexdigest()
        if executable_sha256 != selected["executable_sha256"]:
            raise SessionError("tool executable SHA-256 differs from staged policy")
        if not os.access(tool, os.X_OK):
            raise SessionError("tool executable is not executable")
        sandbox_argv = [str(tool), str(stage / "case"), str(stage / "inputs"), str(stage / "work")]
        if canonical_args is not None:
            sandbox_argv.append(canonical_args.decode("ascii"))
        read_roots = [stage / "case", stage / "inputs"]
        write_roots = [stage / "work"]
        if profile == "analysis_readonly":
            read_roots.append(stage / "work")
            write_roots = []
        runtime_roots = default_python_runtime_roots()
        _assert_sandbox_config_fits(
            sandbox_argv, stage, runtime_roots, cpu_seconds,
            address_space_bytes, file_bytes_per_file,
            read_roots=read_roots, write_roots=write_roots,
        )
        now_ns = time.time_ns()
        wall_elapsed = _wall_elapsed(manifest["created_ns"], now_ns)
        reserved_active = float(wall_seconds) + ACTIVE_GUARD_SECONDS
        if reserved_active > manifest["active_budget_seconds"] - summary["active_seconds_charged"] + 1e-9:
            raise SessionError("local active budget exhausted before launch")
        if reserved_active > manifest["wall_budget_seconds"] - wall_elapsed + 1e-9:
            raise SessionError("session wall budget exhausted before launch")
        root_descriptor = {
            key: manifest[key] for key in ("local_run_admission_root",
                                           "local_run_admission_root_identity",
                                           "local_run_admission_scope")
        }
        # Close the gap between the point-in-time gate check in _read_state
        # and the durable reservation. Once a call can be reserved, the gate
        # stays held until its terminal receipt and directory are fsynced.
        retry_gate_guard.enter_context(_held_retry_gate(
            schedule, run_id, {**manifest, "release_dir": manifest.get("release_dir")},
            manifest.get("release_gate_root"),
        ))
        if not calls:
            claimed = admission.acquire_staged_claim(
                schedule["schedule_sha256"], run_id, admission.owner("staged", stage, session),
                root_descriptor, override=admission_root,
                attempt_number=manifest["attempt_number"],
            )
        else:
            claimed = admission.require_claim(
                schedule["schedule_sha256"], run_id, admission.owner("staged", stage, session),
                root_descriptor, override=admission_root,
                attempt_number=manifest["attempt_number"],
            )
        if claimed != manifest["local_run_claim_sha256"]:
            raise SessionError("local admission claim digest differs from session")
        launch_deadline_ns = manifest["created_ns"] + int(
            (manifest["wall_budget_seconds"] - reserved_active) * 1_000_000_000
        )
        call_number = len(calls) + 1
        call_dir = session / "calls" / f"{call_number:06d}"
        previous = calls[-1][1] if calls else None
        previous_digest = (hashlib.sha256(_read_bounded_file(
            session / "calls" / f"{call_number - 1:06d}" / "terminal.json",
            "previous terminal receipt", MAX_JOURNAL_BYTES
        )).hexdigest() if previous is not None else None)
        reservation = {
            "schema": SCHEMA, "call_number": call_number, "run_id": run_id,
            "budget_scope": BUDGET_SCOPE, "global_run_limits_enforced": False,
            **root_descriptor, "local_run_claim_sha256": claimed,
            "attempt_number": manifest["attempt_number"],
            "schedule_sha256": schedule["schedule_sha256"],
            "previous_terminal_sha256": previous_digest,
            "reserved_at_ns": now_ns, "tool_id": tool_id,
            "tool_version": selected["version"], "executable_sha256": executable_sha256,
            **({"execution_profile": profile} if policy["schema"] == 2 else {}),
            **({"analysis_script_sha256": analysis_script_sha}
               if analysis_script_sha is not None else {}),
            **({"tool_args_sha256": tool_args_sha256} if tool_args_sha256 is not None else {}),
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
        # Publish the numbered directory only after its reservation is fsynced.
        # A crash before rename leaves an ignored .prepared-* directory; after
        # rename the reservation is spent, even if no terminal receipt follows.
        prepared = session / "calls" / f".prepared-{call_number:06d}-{secrets.token_hex(16)}"
        prepared.mkdir(mode=0o700)
        reservation_sha256 = _write_json(prepared / "reservation.json", reservation)
        if call_dir.exists():
            raise SessionError("numbered call directory appeared before reservation publication")
        os.rename(prepared, call_dir)
        _fsync_directory(call_dir.parent)
        if admission.require_claim(
            schedule["schedule_sha256"], run_id, admission.owner("staged", stage, session),
            root_descriptor, override=admission_root,
            attempt_number=manifest["attempt_number"],
        ) != claimed:
            raise SessionError("local admission claim changed before launch")
        result = None
        launch_error = None
        elapsed = 0.0
        try:
            if time.time_ns() >= launch_deadline_ns:
                launch_error = "session wall budget expired after reservation before launch"
            else:
                start = time.monotonic()
                try:
                    result = run_sandboxed(
                        argv=sandbox_argv,
                        cwd=stage / "case", read_roots=read_roots,
                        write_roots=write_roots, runtime_roots=runtime_roots,
                        stdout_path=call_dir / "stdout", stderr_path=call_dir / "stderr",
                        timeout_seconds=float(wall_seconds), cpu_seconds=cpu_seconds,
                        address_space_bytes=address_space_bytes,
                        file_bytes_per_file=file_bytes_per_file,
                        env=None,
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
        child_work = _work_inventory(stage)
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
        analysis_status: str | None = None
        analysis_diagnostic = "analysis did not complete"
        analysis_stdout_bytes = 0
        analysis_stdout_sha = hashlib.sha256(b"").hexdigest()
        analysis_metrics_sha: str | None = None
        readonly_unchanged = child_work["complete"] and _digest(child_work) == _digest(work_before)
        if profile == "analysis_readonly":
            stream = call_dir / "stdout"
            if stream.exists():
                raw_stream = _read_bounded_file(stream, "analysis stdout", file_bytes_per_file)
                analysis_stdout_bytes = len(raw_stream)
                analysis_stdout_sha = hashlib.sha256(raw_stream).hexdigest()
            if (sealed and result is not None and not result.timed_out
                    and type(result.exit_code) is int and result.exit_code >= 0
                    and result.exit_code != 79 and readonly_unchanged
                    and stage_unchanged and executable_unchanged):
                (analysis_status, analysis_diagnostic, analysis_stdout_bytes,
                 analysis_stdout_sha, parsed) = _analysis_output(
                    stream, result.exit_code, file_bytes_per_file)
                analysis_metrics_sha = _publish_analysis_metrics(
                    stage / "work", parsed, old_metrics_sha)
        work_after = _work_inventory(stage) if profile == "analysis_readonly" else child_work
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
        elif profile == "analysis_readonly" and not readonly_unchanged:
            status = "readonly_work_mutated"
        elif profile == "analysis_readonly" and result is not None and result.exit_code == 79:
            status = "analysis_source_rejected"
        elif profile == "analysis_readonly" and result is not None and type(result.exit_code) is int and result.exit_code < 0:
            status = "tool_failure"
        elif result is None or result.exit_code != 0:
            status = ("success" if profile == "analysis_readonly" and analysis_status is not None
                      else "tool_failure")
        elif not work_after["complete"]:
            status = "output_inventory_incomplete"
        else:
            status = "success"
        active_charged = elapsed + ACTIVE_GUARD_SECONDS
        terminal = {
            "schema": SCHEMA, "classification": CLASSIFICATION,
            "notice": manifest["notice"],
            "budget_scope": BUDGET_SCOPE, "global_run_limits_enforced": False,
            **root_descriptor, "local_run_claim_sha256": claimed,
            "attempt_number": manifest["attempt_number"],
            "call_number": call_number, "reservation_sha256": reservation_sha256,
            "run_id": run_id, "run_sha256": run["run_sha256"],
            "schedule_sha256": schedule["schedule_sha256"],
            "tool_id": tool_id, "tool_version": selected["version"],
            **({"execution_profile": profile} if policy["schema"] == 2 else {}),
            **({"analysis_script_sha256": analysis_script_sha,
                "analysis_status": analysis_status,
                "analysis_diagnostic": analysis_diagnostic,
                "analysis_stdout_bytes": analysis_stdout_bytes,
                "analysis_stdout_sha256": analysis_stdout_sha,
                "analysis_metrics_sha256": analysis_metrics_sha,
                "analysis_work_readonly_unchanged": bool(readonly_unchanged),
                "analysis_work_after_child_sha256": _digest(child_work)}
               if profile == "analysis_readonly" else {}),
            **({"tool_args_sha256": tool_args_sha256} if tool_args_sha256 is not None else {}),
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
    init.add_argument("--admission-root")
    init.add_argument("--gate-dir")
    status = sub.add_parser("status")
    call = sub.add_parser("call")
    for command in (status, call):
        command.add_argument("schedule")
        command.add_argument("run_id")
        command.add_argument("stage_dir")
        command.add_argument("session_dir")
        command.add_argument("--admission-root")
    call.add_argument("tool_id")
    call.add_argument("executable")
    call.add_argument("--args-json")
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
                admission_root=args.admission_root,
                gate_root=args.gate_dir,
            )
        elif args.command == "status":
            report = resume_session(schedule, args.run_id, args.stage_dir, args.session_dir,
                                    admission_root=args.admission_root)
        else:
            tool_args = (_parse_tool_args_json(args.args_json)
                         if args.args_json is not None else None)
            report = call_tool(
                schedule, args.run_id, args.stage_dir, args.session_dir,
                args.tool_id, args.executable, tool_args=tool_args,
                wall_seconds=args.wall_seconds,
                cpu_seconds=args.cpu_seconds,
                address_space_bytes=args.address_space_bytes,
                file_bytes_per_file=args.file_bytes_per_file,
                admission_root=args.admission_root,
            )
    except (admission.AdmissionError, SessionError, LocalToolError, StageVerificationError, ReleaseVerificationError,
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
