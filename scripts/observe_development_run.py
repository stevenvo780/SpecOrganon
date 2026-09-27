"""Read-only byte-checked observation of one exposed D-E pilot directory.

Usage: ``python scripts/observe_development_run.py /absolute/run/directory``.
This exports local evidence only. Same-UID local files cannot authenticate
that a pilot plan existed before a CLI call. This is neither a provider receipt
nor a confirmatory or criterion-4 result, and it never runs generated code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Iterator

from run_development_arm import (
    DOSSIER_ASSET_PATHS, MAX_ACTIVE_BUDGET_SECONDS, PUBLIC_FILES, RunError,
    T_SETUP_STEPS, T_TRACE_MAX_BYTES, T_TRACE_METHOD,
    _assembled_prompt, _parse_t_process_trace_bytes, _parse_usage,
    _validate_pilot_triplet_plan,
)


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MAX_SUMMARY_BYTES = 4 * 1024 * 1024
MAX_RECORDED_JSON_BYTES = 64 * 1024 * 1024
MAX_PROMPT_COMPONENT_BYTES = 4 * 1024 * 1024
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
ARTIFACTS = ("analysis.py", "report.md")
REPLAY_STATUSES = frozenset(
    {
        "output_replayed",
        "replay_artifacts_mutated",
        "analysis_replay_timeout",
        "analysis_replay_failure",
        "analysis_replay_launch_failure",
    }
)
RUN_STATUSES = (
    frozenset(
        {
            "cli_timeout",
            "cli_failure",
            "cli_internal_failure",
            "public_packet_mutated",
            "required_artifact_missing",
            "t_signed_ledger_missing_or_invalid",
            "t_tool_execution_unverified",
            "run_time_budget_exhausted",
            "artifacts_ready_for_inspection",
        }
    )
    | REPLAY_STATUSES
)


class ObservationError(ValueError):
    """The local run cannot support a byte-checked observation."""


def _pairs_unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ObservationError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ObservationError("nonfinite JSON number")


def _finite(value: Any) -> bool:
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(_finite(item) for item in value)
    if type(value) is dict:
        return all(_finite(item) for item in value.values())
    return True


def _object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ObservationError(f"{label} is not an object")
    return value


def _digest(value: Any, label: str) -> str:
    if type(value) is not str or SHA256.fullmatch(value) is None:
        raise ObservationError(f"{label} has no valid SHA-256 digest")
    return value


def _expected_record(value: Any, label: str) -> dict[str, Any]:
    record = _object(value, label)
    if set(record) != {"sha256", "bytes"}:
        raise ObservationError(f"{label} has invalid record fields")
    _digest(record["sha256"], label)
    if type(record["bytes"]) is not int or record["bytes"] < 0:
        raise ObservationError(f"{label} has invalid byte count")
    return record


def _open_run_directory(path: Path, stack: ExitStack) -> int:
    if not path.is_absolute() or ".." in path.parts or "\x00" in os.fspath(path):
        raise ObservationError(
            "run directory must be an absolute path without unsafe components"
        )
    try:
        current = os.open("/", DIR_FLAGS)
        stack.callback(os.close, current)
        for name in path.parts[1:]:
            next_fd = os.open(name, DIR_FLAGS, dir_fd=current)
            stack.callback(os.close, next_fd)
            current = next_fd
        return current
    except OSError as exc:
        raise ObservationError(
            "run directory is unavailable or contains a symlink"
        ) from exc


@contextmanager
def _directory(parent_fd: int, *parts: str) -> Iterator[int]:
    with ExitStack() as stack:
        current = parent_fd
        try:
            for name in parts:
                current = os.open(name, DIR_FLAGS, dir_fd=current)
                stack.callback(os.close, current)
        except OSError as exc:
            raise ObservationError(
                "recorded directory is unavailable or unsafe"
            ) from exc
        yield current


def _open_regular(directory_fd: int, name: str) -> int:
    try:
        fd = os.open(name, FILE_FLAGS, dir_fd=directory_fd)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise ObservationError(f"{name} is not a regular file")
        return fd
    except OSError as exc:
        raise ObservationError(f"{name} is absent or unsafe") from exc


def _exists(directory_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ObservationError(f"{name} could not be inspected") from exc
    return True


def _hash_fd(fd: int, label: str) -> dict[str, Any]:
    before = os.fstat(fd)
    digest = hashlib.sha256()
    size = 0
    os.lseek(fd, 0, os.SEEK_SET)
    while chunk := os.read(fd, 1024 * 1024):
        digest.update(chunk)
        size += len(chunk)
    after = os.fstat(fd)

    def identity(item: os.stat_result) -> tuple[int, int, int, int, int]:
        return (
            item.st_dev,
            item.st_ino,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
        )

    if identity(before) != identity(after) or size != after.st_size:
        raise ObservationError(f"{label} changed while being inspected")
    return {"sha256": digest.hexdigest(), "bytes": size}


def _verify_record(
    directory_fd: int, name: str, expected: Any, label: str
) -> dict[str, Any]:
    target = _expected_record(expected, label)
    fd = _open_regular(directory_fd, name)
    try:
        actual = _hash_fd(fd, label)
    finally:
        os.close(fd)
    if actual != target:
        raise ObservationError(f"{label} differs from its recorded bytes")
    return actual


def _verify_optional(
    directory_fd: int,
    name: str,
    expected: Any,
    label: str,
    *,
    allow_absent: bool = False,
) -> dict[str, Any] | None:
    if expected is None:
        if _exists(directory_fd, name):
            raise ObservationError(f"{label} exists without a byte record")
        return None
    if allow_absent and not _exists(directory_fd, name):
        return None
    return _verify_record(directory_fd, name, expected, label)


def _verify_hash(
    directory_fd: int,
    name: str,
    expected: Any,
    label: str,
    *,
    allow_absent: bool = False,
) -> dict[str, Any] | None:
    digest = _digest(expected, label)
    if allow_absent and not _exists(directory_fd, name):
        return None
    fd = _open_regular(directory_fd, name)
    try:
        record = _hash_fd(fd, label)
    finally:
        os.close(fd)
    if record["sha256"] != digest:
        raise ObservationError(f"{label} differs from its recorded digest")
    return record


def _read_hashed_prompt_component(directory_fd: int, name: str, expected: Any) -> bytes:
    """Read the same bounded regular-file bytes whose digest was checked."""
    digest = _digest(expected, name)
    fd = _open_regular(directory_fd, name)
    try:
        before = _hash_fd(fd, name)
        if before["sha256"] != digest or before["bytes"] > MAX_PROMPT_COMPONENT_BYTES:
            raise ObservationError(f"{name} has invalid prompt component bytes")
        os.lseek(fd, 0, os.SEEK_SET)
        raw = bytearray()
        while chunk := os.read(fd, 1024 * 1024):
            raw.extend(chunk)
            if len(raw) > MAX_PROMPT_COMPONENT_BYTES:
                raise ObservationError(f"{name} exceeds the prompt component size limit")
        if (len(raw) != before["bytes"] or hashlib.sha256(raw).hexdigest() != digest
                or _hash_fd(fd, name) != before):
            raise ObservationError(f"{name} changed during prompt policy inspection")
    finally:
        os.close(fd)
    return bytes(raw)


def _parse_strict_json(raw: bytes, label: str) -> Any:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs_unique,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, ObservationError):
            raise ObservationError(f"{label}: {exc}") from exc
        raise ObservationError(f"{label} is not valid strict JSON") from exc
    if not _finite(value):
        raise ObservationError(f"{label} contains a nonfinite number")
    return value


def _read_recorded_json(directory_fd: int, name: str, expected: Any, label: str) -> Any:
    record = _expected_record(expected, label)
    if record["bytes"] > MAX_RECORDED_JSON_BYTES:
        raise ObservationError(f"{label} exceeds the JSON size limit")
    fd = _open_regular(directory_fd, name)
    try:
        if _hash_fd(fd, label) != record:
            raise ObservationError(f"{label} differs from its recorded bytes")
        os.lseek(fd, 0, os.SEEK_SET)
        raw = bytearray()
        while chunk := os.read(fd, 1024 * 1024):
            raw.extend(chunk)
            if len(raw) > MAX_RECORDED_JSON_BYTES:
                raise ObservationError(f"{label} exceeds the JSON size limit")
        if (
            len(raw) != record["bytes"]
            or hashlib.sha256(raw).hexdigest() != record["sha256"]
        ):
            raise ObservationError(f"{label} changed during JSON inspection")
        if _hash_fd(fd, label) != record:
            raise ObservationError(f"{label} changed during JSON inspection")
    finally:
        os.close(fd)
    return _parse_strict_json(bytes(raw), label)


def _read_summary(run_fd: int) -> tuple[dict[str, Any], str]:
    fd = _open_regular(run_fd, "run.json")
    try:
        before = os.fstat(fd)
        if before.st_size > MAX_SUMMARY_BYTES:
            raise ObservationError("run.json exceeds the size limit")
        raw = os.read(fd, MAX_SUMMARY_BYTES + 1)
        after = os.fstat(fd)
        if (
            len(raw) > MAX_SUMMARY_BYTES
            or len(raw) != after.st_size
            or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
        ):
            raise ObservationError("run.json changed while being inspected")
    finally:
        os.close(fd)
    summary = _parse_strict_json(raw, "run.json")
    return _object(summary, "run.json"), hashlib.sha256(raw).hexdigest()


def _verify_capture(
    run_fd: int, raw: Any, prefix: str, streams: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    capture = _object(raw, prefix)
    timed_out = capture.get("timed_out")
    exit_code = capture.get("exit_code")
    launch_error = capture.get("launch_error")
    if type(timed_out) is not bool or (
        exit_code is not None and type(exit_code) is not int
    ):
        raise ObservationError(f"{prefix} capture has invalid timeout or exit fields")
    if launch_error is not None:
        if (
            type(launch_error) is not str
            or not launch_error
            or exit_code is not None
            or (timed_out and prefix != "analysis_replay")
        ):
            raise ObservationError(
                f"{prefix} capture has inconsistent launch failure fields"
            )
    elif exit_code is None and not (prefix == "analysis_replay" and timed_out):
        raise ObservationError(f"{prefix} capture has no exit or launch failure")
    for suffix in ("stdout", "stderr"):
        filename = (
            f"{prefix}.{suffix}"
            if prefix != "cli"
            else ("cli.stdout.jsonl" if suffix == "stdout" else "cli.stderr")
        )
        streams[filename] = _verify_record(
            run_fd, filename, capture.get(suffix), filename
        )
    return capture


def _verify_budget_capture(
    capture: dict[str, Any], stage_limit: Any, label: str, budget_limit: int,
    walls: dict[str, float],
) -> None:
    seconds = capture.get("timeout_seconds")
    wall = capture.get("wall_seconds")
    if (type(stage_limit) is not int or stage_limit < 1
            or type(seconds) not in {int, float} or not math.isfinite(seconds)
            or seconds < 0 or seconds > min(stage_limit, budget_limit)
            or capture.get("timeout_cap") not in {"stage", "run_budget"}
            or type(wall) not in {int, float} or not math.isfinite(wall)
            or wall < 0):
        raise ObservationError(f"{label} has an invalid active budget timeout")
    if seconds == 0 and not capture["timed_out"]:
        raise ObservationError(f"{label} has zero timeout without expiry")
    if capture["timeout_cap"] == "stage" and seconds != stage_limit:
        raise ObservationError(f"{label} stage timeout differs from its recorded limit")
    walls[label] = float(wall)


def _verify_usage(
    run_fd: int, provider: str, model: str, expected: Any, stream_record: dict[str, Any],
    *, agy_no_command_tool: bool = False,
) -> dict[str, Any]:
    declared = _object(expected, "cli_usage")
    fd = _open_regular(run_fd, "cli.stdout.jsonl")
    try:
        before = _hash_fd(fd, "cli.stdout.jsonl")
        if before != stream_record:
            raise ObservationError("cli.stdout.jsonl changed before usage inspection")
        try:
            observed = _parse_usage(
                provider, Path(f"/proc/self/fd/{fd}"), model,
                agy_no_command_tool=agy_no_command_tool,
            )
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise ObservationError(
                "CLI usage could not be parsed from the verified stream"
            ) from exc
        if _hash_fd(fd, "cli.stdout.jsonl") != before:
            raise ObservationError("cli.stdout.jsonl changed during usage inspection")
    finally:
        os.close(fd)
    if observed != declared:
        # Historical Agy summaries can omit the local identity state and the
        # no-command trace summary. Recompute both from the verified stream;
        # contradictory IDs and observed commands still change terminal_success.
        legacy_observed = dict(observed)
        if provider == "agy" and "conversation_identity" not in declared:
            legacy_observed.pop("conversation_identity", None)
        if agy_no_command_tool and "no_command_tool_trace" not in declared:
            legacy_observed.pop("no_command_tool_trace", None)
        if legacy_observed != declared:
            raise ObservationError("cli_usage differs from the verified local CLI stream")
    return {
        "origin": observed["origin"],
        "complete": observed["complete"],
        "terminal_success": observed["terminal_success"],
        **({"conversation_identity": observed["conversation_identity"]}
           if provider == "agy" else {}),
        "final_usage": observed["final_usage"],
        "preterminal_step_usage": observed["preterminal_step_usage"],
        "no_command_tool_trace": observed.get("no_command_tool_trace"),
    }


def _verify_t_process_trace(
    run_fd: int, raw: Any, work: Path, streams: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Recompute the local T activity summary from byte-checked strace output."""
    if raw is None:
        if _exists(run_fd, "t_execve.log"):
            raise ObservationError("T process trace exists without a record")
        return _parse_t_process_trace_bytes(b"", work)
    trace = _object(raw, "t_process_trace")
    expected_keys = {"method", "record", "organon_cli_execs", "organon_mcp_execs",
                     "tool_ledger_publish_count", "other_ledger_write_count", "inspectable"}
    if set(trace) != expected_keys or trace.get("method") != T_TRACE_METHOD:
        raise ObservationError("T process trace has an invalid method or fields")
    record = trace.get("record")
    if record is None:
        _verify_optional(run_fd, "t_execve.log", None, "T process trace")
        observed = _parse_t_process_trace_bytes(b"", work)
    else:
        expected = _expected_record(record, "T process trace")
        fd = _open_regular(run_fd, "t_execve.log")
        try:
            before = _hash_fd(fd, "T process trace")
            if before != expected:
                raise ObservationError("T process trace differs from recorded bytes")
            if expected["bytes"] > T_TRACE_MAX_BYTES:
                observed = _parse_t_process_trace_bytes(b"", work)
            else:
                os.lseek(fd, 0, os.SEEK_SET)
                chunks: list[bytes] = []
                size = 0
                while chunk := os.read(fd, 1024 * 1024):
                    size += len(chunk)
                    if size > T_TRACE_MAX_BYTES:
                        raise ObservationError("T process trace grew during inspection")
                    chunks.append(chunk)
                observed = _parse_t_process_trace_bytes(b"".join(chunks), work)
            if _hash_fd(fd, "T process trace") != before:
                raise ObservationError("T process trace changed during inspection")
        finally:
            os.close(fd)
        streams["t_execve.log"] = expected
    if any(trace.get(key) != value or type(trace.get(key)) is not type(value)
           for key, value in observed.items()):
        raise ObservationError("T process trace counts differ from verified bytes")
    return observed


def _toolkit_fingerprint(work_fd: int) -> str:
    """Recompute the runner's limited Python-source fingerprint without symlinks."""
    files: list[tuple[str, str]] = []
    with _directory(work_fd, ".venv") as venv_fd:
        with _directory(venv_fd, "bin") as bin_fd:
            fd = _open_regular(bin_fd, "organon")
            try:
                files.append(("bin/organon", _hash_fd(fd, "bin/organon")["sha256"]))
            finally:
                os.close(fd)
        with _directory(venv_fd, "lib") as lib_fd:
            for version in sorted(
                entry.name
                for entry in os.scandir(lib_fd)
                if entry.name.startswith("python")
            ):
                with _directory(
                    lib_fd, version, "site-packages", "specorganon"
                ) as package_fd:

                    def visit(directory_fd: int, relative: str) -> None:
                        for entry in os.scandir(directory_fd):
                            if entry.is_symlink():
                                raise ObservationError(
                                    "toolkit source tree contains a symlink"
                                )
                            child = f"{relative}/{entry.name}"
                            if entry.is_dir(follow_symlinks=False):
                                with _directory(directory_fd, entry.name) as child_fd:
                                    visit(child_fd, child)
                            elif entry.name.endswith(".py"):
                                fd = _open_regular(directory_fd, entry.name)
                                try:
                                    files.append((child, _hash_fd(fd, child)["sha256"]))
                                finally:
                                    os.close(fd)

                    visit(package_fd, f"lib/{version}/site-packages/specorganon")
    if len(files) < 2:
        raise ObservationError("toolkit fingerprint has too few source files")
    digest = hashlib.sha256()
    for name, file_sha in sorted(files):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(file_sha))
    return digest.hexdigest()


def _verify_toolkit(
    run_fd: int, work_fd: int, raw: Any, streams: dict[str, dict[str, Any]],
    *, setup_timeout: int | None = None, budget_limit: int | None = None,
    budget_walls: dict[str, float] | None = None,
) -> tuple[str, dict[str, Any]]:
    toolkit = _object(raw, "toolkit")
    wheels = [
        entry.name for entry in os.scandir(work_fd) if entry.name.endswith(".whl")
    ]
    if len(wheels) != 1:
        raise ObservationError("toolkit wheel is absent or ambiguous")
    wheel_record = _verify_record(
        work_fd, wheels[0], toolkit.get("wheel"), "toolkit wheel"
    )
    steps = _object(toolkit.get("steps"), "toolkit.steps")
    if set(steps) != {
        "toolkit_venv",
        "toolkit_install",
        "toolkit_init",
        "toolkit_status",
    }:
        raise ObservationError("toolkit setup steps are incomplete")
    for name in sorted(steps):
        step = _verify_capture(run_fd, steps[name], name, streams)
        if setup_timeout is not None:
            assert budget_limit is not None and budget_walls is not None
            _verify_budget_capture(step, setup_timeout, name, budget_limit,
                                   budget_walls)
        if (
            step.get("timed_out") is not False
            or type(step.get("exit_code")) is not int
            or step["exit_code"] != 0
        ):
            raise ObservationError(f"{name} has a failed or invalid setup capture")
    if toolkit.get("signed_policy_verified_in_local_probe") is not True:
        raise ObservationError(
            "toolkit probe does not record signed policy verification"
        )
    probe = _read_recorded_json(
        run_fd,
        "toolkit_status.stdout",
        streams["toolkit_status.stdout"],
        "toolkit status probe",
    )
    if (
        type(probe) is not dict
        or type(probe.get("project")) is not dict
        or probe["project"].get("approval_policy") != "signed"
    ):
        raise ObservationError("toolkit status probe does not show signed policy")
    expected = _digest(
        toolkit.get("toolkit_files_fingerprint_sha256"), "toolkit fingerprint"
    )
    if _toolkit_fingerprint(work_fd) != expected:
        raise ObservationError("toolkit source fingerprint differs from the run record")
    return wheels[0], wheel_record


def _verify_partial_toolkit(
    run_fd: int, work_fd: int, raw: Any, streams: dict[str, dict[str, Any]],
    *, setup_timeout: int, exhausted_stage: str, budget_limit: int,
    budget_walls: dict[str, float],
) -> tuple[str, dict[str, Any]]:
    toolkit = _object(raw, "partial toolkit")
    wheels = [entry.name for entry in os.scandir(work_fd) if entry.name.endswith(".whl")]
    if len(wheels) != 1:
        raise ObservationError("partial toolkit wheel is absent or ambiguous")
    wheel_record = _verify_record(work_fd, wheels[0], toolkit.get("wheel"), "toolkit wheel")
    steps = _object(toolkit.get("steps"), "partial toolkit steps")
    names = [name for name in T_SETUP_STEPS if name in steps]
    if set(steps) != set(names) or names != list(T_SETUP_STEPS[:len(names)]):
        raise ObservationError("partial toolkit setup steps are out of order")
    for name in T_SETUP_STEPS:
        if name not in steps:
            if _exists(run_fd, f"{name}.stdout") or _exists(run_fd, f"{name}.stderr"):
                raise ObservationError("unrecorded partial toolkit stream exists")
            continue
        step = _verify_capture(run_fd, steps[name], name, streams)
        _verify_budget_capture(step, setup_timeout, name, budget_limit,
                               budget_walls)
        if step["timed_out"]:
            if (name != names[-1] or exhausted_stage != name
                    or step["timeout_cap"] != "run_budget"):
                raise ObservationError("partial toolkit timeout contradicts budget stage")
        elif step["exit_code"] != 0:
            raise ObservationError("partial toolkit records a non-budget setup failure")
    if exhausted_stage in T_SETUP_STEPS:
        index = T_SETUP_STEPS.index(exhausted_stage)
        if len(names) not in {index, index + 1}:
            raise ObservationError("partial toolkit stage differs from captured steps")
    elif exhausted_stage not in {"cli", "post_cli", "finalize"} or len(names) != len(T_SETUP_STEPS):
        raise ObservationError("partial toolkit ended at an inconsistent stage")
    if len(names) == len(T_SETUP_STEPS) and all(
        not _object(steps[name], name).get("timed_out") for name in T_SETUP_STEPS
    ):
        if toolkit.get("signed_policy_verified_in_local_probe") is True:
            _verify_toolkit(run_fd, work_fd, toolkit, streams,
                            setup_timeout=setup_timeout, budget_limit=budget_limit,
                            budget_walls=budget_walls)
        elif (exhausted_stage != "toolkit_status"
              or set(toolkit) != {"wheel", "steps"}):
            raise ObservationError("completed toolkit setup lacks its probe verification")
    elif toolkit.get("signed_policy_verified_in_local_probe") is True:
        raise ObservationError("partial toolkit claims completed signed-policy probe")
    return wheels[0], wheel_record


def observe_run_dir(run_dir: Path | str) -> dict[str, Any]:
    """Return only hashes and local aggregate telemetry after verifying recorded bytes."""
    path = Path(run_dir)
    with ExitStack() as stack:
        run_fd = _open_run_directory(path, stack)
        summary, summary_sha = _read_summary(run_fd)
        if (
            type(summary.get("schema")) is not int
            or summary["schema"] != 1
            or summary.get("classification") != "exposed_development_unsealed"
        ):
            raise ObservationError("run.json is not an exposed development run")
        arm, provider = summary.get("arm"), summary.get("provider_cli")
        model, effort = summary.get("requested_model"), summary.get("requested_effort")
        status = summary.get("execution_status")
        if arm not in ("N", "S", "T") or provider not in ("codex", "agy", "opencode"):
            raise ObservationError("run.json has an invalid arm or provider")
        tool_policy = summary.get("tool_policy")
        if tool_policy not in {"default", "no_command_tool"}:
            raise ObservationError("run.json has an unknown tool policy")
        if tool_policy == "no_command_tool" and (provider != "agy" or arm == "T"):
            raise ObservationError("no-command tool policy requires Agy N/S")
        if any(
            type(value) is not str or not value.strip() for value in (model, effort)
        ):
            raise ObservationError("run.json has no requested model or effort")
        if provider == "opencode":
            if re.fullmatch(r"minimax/[A-Za-z0-9._:-]+", model) is None or effort != "uncontrolled":
                raise ObservationError("OpenCode run has an unsupported model route or effort")
            if (summary.get("cli_mode") is None
                    and status in {"preparing", "preflight_failure", "run_time_budget_exhausted"}
                    and summary.get("cli") is None):
                pass
            elif summary.get("cli_mode") != {
                "opencode_format": "json", "opencode_pure": True, "opencode_agent": "build",
            }:
                raise ObservationError("OpenCode run has an inconsistent CLI mode")
        if type(status) is not str or status not in RUN_STATUSES | {
            "preparing",
            "preflight_failure",
        }:
            raise ObservationError("run.json has an unknown execution status")
        if status == "replay_artifacts_mutated":
            raise ObservationError(
                "replay_artifacts_mutated cannot be observed: original material bytes are no longer verifiable"
            )
        if summary.get("controlled_comparison_eligible") is not False:
            raise ObservationError("run.json claims controlled comparison eligibility")
        if any(
            summary.get(key) is not None
            for key in ("provider_request_id", "price", "cost")
        ):
            raise ObservationError(
                "run.json claims unsupported provider or cost evidence"
            )
        budget_raw = summary.get("run_time_budget")
        budget: dict[str, Any] | None = None
        if budget_raw is not None:
            budget = _object(budget_raw, "run_time_budget")
            limit = summary.get("active_budget_seconds")
            elapsed = budget.get("elapsed_seconds")
            exhausted_stage = budget.get("exhausted_stage")
            if (set(budget) not in (
                        {"scope", "started_at_utc", "elapsed_seconds", "exhausted_stage"},
                        {"scope", "started_at_utc", "elapsed_seconds", "exhausted_stage",
                         "active_budget_seconds"},
                    )
                    or budget["scope"] != "single_local_invocation_no_agent_or_retry_accounting"
                    or type(limit) is not int or not 1 <= limit <= MAX_ACTIVE_BUDGET_SECONDS
                    or ("active_budget_seconds" in budget and (
                        type(budget["active_budget_seconds"]) is not int
                        or budget["active_budget_seconds"] != limit))
                    or type(budget["started_at_utc"]) is not str
                    or not budget["started_at_utc"]
                    or (elapsed is not None and (
                        type(elapsed) not in {int, float} or not math.isfinite(elapsed)
                        or elapsed < 0))
                    or (exhausted_stage is not None and (
                        type(exhausted_stage) is not str or not exhausted_stage))):
                raise ObservationError("run_time_budget has invalid local declarations")
            if ((status == "run_time_budget_exhausted") is not (exhausted_stage is not None)):
                raise ObservationError("run time budget status contradicts its local declaration")
            if (status not in {"preparing", "preflight_failure"} and elapsed is None):
                raise ObservationError("terminal run lacks local elapsed time declaration")
            if (status not in {"run_time_budget_exhausted", "preflight_failure"}
                    and elapsed is not None
                    and elapsed > limit + 0.001):
                raise ObservationError("run exceeds declared budget without terminal expiry")
        elif status == "run_time_budget_exhausted":
            raise ObservationError("run budget exhaustion lacks a local budget record")

        pilot_binding = summary.get("pilot_triplet_binding")
        pilot_mode = summary.get("pilot_mode", "generic_exploratory")
        if type(pilot_mode) is not str or pilot_mode not in {"generic_exploratory", "explicit_triplet"}:
            raise ObservationError("run.json has an invalid pilot mode")
        if (pilot_mode == "explicit_triplet") is not (pilot_binding is not None):
            raise ObservationError("pilot mode and triplet binding are inconsistent")
        pilot_assets: dict[str, str] | None = None
        observed_binding: dict[str, Any] | None = None
        pilot_copies: dict[str, dict[str, Any]] = {}
        if pilot_binding is None:
            if _exists(run_fd, "pilot_triplet_plan.json") or _exists(run_fd, "activation_dossier.json"):
                raise ObservationError("pilot triplet copies exist without a run.json binding")
        else:
            binding = _object(pilot_binding, "pilot triplet binding")
            legacy_binding_keys = {
                "schema", "scope", "plan_sha256", "activation_dossier_sha256",
                "plan_record", "dossier_record", "cell", "declared_model_version",
                "other_model_parameters",
            }
            binding_schema = binding.get("schema")
            if (type(binding_schema) is not int or binding_schema not in {1, 2}
                    or set(binding) != (legacy_binding_keys if binding_schema == 1
                                        else legacy_binding_keys | {"active_budget_seconds"})
                    or binding["scope"] != "local_requested_configuration_only"):
                raise ObservationError("pilot triplet binding has invalid fields")
            plan_sha = _digest(binding["plan_sha256"], "pilot triplet plan")
            dossier_sha = _digest(binding["activation_dossier_sha256"], "activation dossier")
            plan_record = _expected_record(binding["plan_record"], "pilot triplet plan")
            dossier_record = _expected_record(binding["dossier_record"], "activation dossier")
            if plan_record["sha256"] != plan_sha or dossier_record["sha256"] != dossier_sha:
                raise ObservationError("pilot triplet plan or dossier digest differs from run.json binding")
            cell = _object(binding["cell"], "pilot triplet cell")
            if (set(cell) != {"family_slot", "arm"} or cell["arm"] != arm
                    or type(cell["family_slot"]) is not str
                    or cell["family_slot"] not in {"A", "B"}):
                raise ObservationError("pilot triplet cell differs from run.json arm")
            plan = _read_recorded_json(
                run_fd, "pilot_triplet_plan.json", plan_record, "pilot triplet plan",
            )
            dossier = _read_recorded_json(
                run_fd, "activation_dossier.json", dossier_record, "activation dossier",
            )
            pilot_copies = {
                "pilot_triplet_plan.json": plan_record,
                "activation_dossier.json": dossier_record,
            }
            dossier = _object(dossier, "activation dossier")
            if (type(dossier.get("schema")) is not int or dossier["schema"] != 1
                    or dossier.get("classification") != "offline_exploratory_pilot_preflight_no_provider_calls"
                    or dossier.get("status") != "no_go_for_provider_calls"
                    or dossier.get("criterion_4") != "not_assessed"
                    or dossier.get("provider_requests_made_for_this_dossier") != 0
                    or dossier.get("spend_authorized_usd") != 0):
                raise ObservationError("copied activation dossier is not the offline NO-GO dossier")
            assets = _object(dossier.get("fixed_local_assets_sha256"), "dossier assets")
            if set(assets) != DOSSIER_ASSET_PATHS or any(
                type(value) is not str or SHA256.fullmatch(value) is None
                for value in assets.values()
            ):
                raise ObservationError("copied activation dossier has invalid asset hashes")
            try:
                selected = _validate_pilot_triplet_plan(
                    plan, dossier_sha, cell["family_slot"], arm, provider, model, effort,
                    summary.get("active_budget_seconds"), allow_legacy_v1=True,
                )
            except RunError as exc:
                raise ObservationError(f"pilot triplet local binding differs: {exc}") from exc
            if type(plan) is not dict or plan.get("schema") != binding_schema:
                raise ObservationError("pilot triplet plan and binding schema differ")
            if binding_schema == 2:
                if (budget is None or set(budget) != {
                        "scope", "started_at_utc", "elapsed_seconds", "exhausted_stage",
                        "active_budget_seconds",
                    } or type(binding["active_budget_seconds"]) is not int
                        or binding["active_budget_seconds"] != plan["active_budget_seconds"]
                        or budget["active_budget_seconds"] != plan["active_budget_seconds"]):
                    raise ObservationError("pilot triplet active budget differs across plan, binding and run_time_budget")
            elif budget is not None and "active_budget_seconds" in budget:
                raise ObservationError("legacy pilot triplet cannot claim a shared budget")
            if (binding["declared_model_version"] != selected["model_version"]
                    or binding["other_model_parameters"] != selected["other_model_parameters"]):
                raise ObservationError("pilot triplet declared parameters differ from the copied plan")
            pilot_assets = assets
            observed_binding = {
                "scope": "local_requested_configuration_only",
                "plan_sha256": plan_sha,
                "activation_dossier_sha256": dossier_sha,
                "cell": cell,
                "plan_schema": binding_schema,
                "declared_model_version": selected["model_version"],
                "other_model_parameters": selected["other_model_parameters"],
                **({"active_budget_seconds": plan["active_budget_seconds"]}
                   if binding_schema == 2 else {}),
                "effective_model_and_effort_verified": False,
                "all_dossier_assets_available_locally": False,
                "prelaunch_binding_authenticated": False,
            }

        verified_inputs: dict[str, dict[str, Any]] = {}
        verified_inputs.update(pilot_copies)
        verified_streams: dict[str, dict[str, Any]] = {}
        budget_walls: dict[str, float] = {}
        verified_artifacts: dict[str, dict[str, Any]] = {}
        unavailable: list[str] = []
        unrecorded: list[str] = []
        process_trace: dict[str, Any] | None = None
        partial = status in {"preparing", "preflight_failure"} or (
            status == "run_time_budget_exhausted" and summary.get("cli") is None
        )
        with _directory(run_fd, "work") as work_fd:
            packet = _object(summary.get("packet"), "packet")
            if set(packet) != set(PUBLIC_FILES):
                raise ObservationError("packet input records are incomplete")
            for name in PUBLIC_FILES:
                verified_inputs[f"work/{name}"] = _verify_record(
                    work_fd, name, packet[name], f"packet {name}"
                )
            prompt = _object(summary.get("prompt"), "prompt")
            if set(prompt) != {"assembled_sha256", "common_sha256", "arm_sha256"}:
                raise ObservationError("prompt digest records are incomplete")
            verified_inputs["prompt.txt"] = _verify_hash(
                run_fd, "prompt.txt", prompt["assembled_sha256"], "prompt.txt"
            )
            if pilot_assets is not None:
                for name in PUBLIC_FILES:
                    if verified_inputs[f"work/{name}"]["sha256"] != pilot_assets[f"cases/building_energy/{name}"]:
                        raise ObservationError(f"pilot dossier differs from copied packet: {name}")
            for filename, key in (
                ("common.md", "common_sha256"),
                ("arm.md", "arm_sha256"),
            ):
                checked = _verify_hash(
                    work_fd,
                    filename,
                    prompt[key],
                    f"work/{filename}",
                    allow_absent=partial,
                )
                if checked is None:
                    unavailable.append(f"work/{filename}")
                else:
                    verified_inputs[f"work/{filename}"] = checked
                    if pilot_assets is not None:
                        source_name = ("common.md" if filename == "common.md"
                                       else f"arm_{arm.lower()}.md")
                        if checked["sha256"] != pilot_assets[f"experiments/development/energy_pilot/{source_name}"]:
                            raise ObservationError(f"pilot dossier differs from copied prompt: {filename}")
            if not partial:
                common_bytes = _read_hashed_prompt_component(
                    work_fd, "common.md", prompt["common_sha256"]
                )
                arm_bytes = _read_hashed_prompt_component(
                    work_fd, "arm.md", prompt["arm_sha256"]
                )
                try:
                    expected_prompt = _assembled_prompt(
                        arm, common_bytes, arm_bytes,
                        agy_no_command_tool=tool_policy == "no_command_tool",
                    )
                except UnicodeError as exc:
                    raise ObservationError("assigned prompt source is not UTF-8") from exc
                if hashlib.sha256(expected_prompt.encode("utf-8")).hexdigest() != prompt["assembled_sha256"]:
                    raise ObservationError("tool policy differs from the verified prompt bytes")

            artifacts = _object(summary.get("artifacts"), "artifacts")
            if partial:
                if (
                    artifacts
                    or summary.get("cli") is not None
                    or summary.get("cli_usage") is not None
                ):
                    raise ObservationError(
                        "partial run has inconsistent CLI or artifact records"
                    )
                if (
                    summary.get("packet_after") is not None
                    or summary.get("analysis_replay") is not None
                ):
                    raise ObservationError(
                        "partial run has inconsistent post-run records"
                    )
                if status == "preflight_failure" and not summary.get("preflight_error"):
                    raise ObservationError("preflight failure lacks a recorded reason")
                toolkit = summary.get("toolkit")
                if toolkit is not None:
                    if arm != "T":
                        raise ObservationError("non-T arm has a toolkit record")
                    if status == "run_time_budget_exhausted":
                        assert budget is not None
                        wheel_name, wheel_record = _verify_partial_toolkit(
                            run_fd, work_fd, toolkit, verified_streams,
                            setup_timeout=summary.get("setup_timeout_seconds"),
                            exhausted_stage=budget["exhausted_stage"],
                            budget_limit=summary["active_budget_seconds"],
                            budget_walls=budget_walls,
                        )
                    else:
                        wheel_name, wheel_record = _verify_toolkit(
                            run_fd, work_fd, toolkit, verified_streams,
                            setup_timeout=(summary.get("setup_timeout_seconds")
                                           if budget is not None else None),
                            budget_limit=(summary["active_budget_seconds"]
                                          if budget is not None else None),
                            budget_walls=(budget_walls if budget is not None else None),
                        )
                    verified_inputs[f"work/{wheel_name}"] = wheel_record
                elif status == "run_time_budget_exhausted":
                    if budget is None or budget["exhausted_stage"] not in {
                        "prelaunch", "toolkit_copy", "cli", "finalize"
                    }:
                        raise ObservationError("uncaptured budget stage is inconsistent")
                    if arm == "T" and any(
                        _exists(run_fd, f"{name}.{suffix}")
                        for name in T_SETUP_STEPS for suffix in ("stdout", "stderr")
                    ):
                        raise ObservationError("T setup streams exist without budget captures")
                if summary.get("t_ledger") is not None:
                    raise ObservationError(
                        "partial run has a ledger record before CLI completion"
                    )
                if summary.get("t_process_trace") is not None:
                    raise ObservationError("partial run has a completed T process trace")
                if _exists(run_fd, "t_execve.log"):
                    unrecorded.append("t_execve.log")
                for name in ("cli.stdout.jsonl", "cli.stderr"):
                    (unrecorded if _exists(run_fd, name) else unavailable).append(name)
                for name in ARTIFACTS:
                    label = f"work/{name}"
                    (unrecorded if _exists(work_fd, name) else unavailable).append(
                        label
                    )
                usage = None
            else:
                if set(artifacts) != set(ARTIFACTS):
                    raise ObservationError("artifact records are incomplete")
                for name in ARTIFACTS:
                    checked = _verify_optional(
                        work_fd, name, artifacts[name], f"artifact {name}"
                    )
                    if checked is None:
                        unavailable.append(f"work/{name}")
                    else:
                        verified_artifacts[f"work/{name}"] = checked
                after = _object(summary.get("packet_after"), "packet_after")
                if set(after) != set(PUBLIC_FILES):
                    raise ObservationError("post-run packet records are incomplete")
                if after != packet or summary.get("packet_unchanged") is not True:
                    raise ObservationError(
                        "packet input changed; original bytes cannot be reverified"
                    )
                capture = _verify_capture(
                    run_fd, summary.get("cli"), "cli", verified_streams
                )
                if budget is not None:
                    _verify_budget_capture(capture, summary.get("timeout_seconds"), "cli",
                                           summary["active_budget_seconds"], budget_walls)
                usage = _verify_usage(
                    run_fd,
                    provider,
                    model,
                    summary.get("cli_usage"),
                    verified_streams["cli.stdout.jsonl"],
                    agy_no_command_tool=tool_policy == "no_command_tool",
                )

                toolkit = summary.get("toolkit")
                if toolkit is not None:
                    if arm != "T":
                        raise ObservationError("non-T arm has a toolkit record")
                    wheel_name, wheel_record = _verify_toolkit(
                        run_fd, work_fd, toolkit, verified_streams,
                        setup_timeout=(summary.get("setup_timeout_seconds")
                                       if budget is not None else None),
                        budget_limit=(summary["active_budget_seconds"]
                                      if budget is not None else None),
                        budget_walls=(budget_walls if budget is not None else None),
                    )
                    verified_inputs[f"work/{wheel_name}"] = wheel_record
                elif arm == "T":
                    raise ObservationError("T run lacks a toolkit record")
                if arm == "T":
                    process_trace = _verify_t_process_trace(
                        run_fd, summary.get("t_process_trace"), path / "work",
                        verified_streams,
                    )
                elif summary.get("t_process_trace") is not None or _exists(run_fd, "t_execve.log"):
                    raise ObservationError("non-T arm has a T process trace")
                ledger = summary.get("t_ledger")
                ledger_valid = True
                if arm == "T":
                    if ledger is None and status == "run_time_budget_exhausted":
                        assert budget is not None
                        if budget["exhausted_stage"] not in {"cli", "post_cli", "finalize"}:
                            raise ObservationError("T budget stage lacks a ledger capture")
                        if (_exists(run_fd, "toolkit_after_status.stdout")
                                or _exists(run_fd, "toolkit_after_status.stderr")):
                            raise ObservationError("T status streams exist without budget capture")
                        ledger_valid = False
                    else:
                        ledger = _object(ledger, "t_ledger")
                if arm == "T" and ledger is not None:
                    if ledger.get("model_cli_invocations_proven") is not False:
                        raise ObservationError(
                            "T ledger claims unproven model CLI invocations"
                        )
                    if type(ledger.get("toolkit_files_unchanged")) is not bool:
                        raise ObservationError(
                            "T ledger has invalid toolkit integrity status"
                        )
                    if ledger.get("present") is True:
                        if not ledger["toolkit_files_unchanged"]:
                            raise ObservationError(
                                "T ledger exists despite a changed toolkit"
                            )
                        with _directory(work_fd, "case") as case_fd:
                            record = _verify_hash(
                                case_fd,
                                "organon.json",
                                ledger.get("sha256"),
                                "case/organon.json",
                            )
                            verified_artifacts["work/case/organon.json"] = record
                            data = _read_recorded_json(
                                case_fd, "organon.json", record, "case/organon.json"
                            )
                        project = data.get("project") if type(data) is dict else None
                        events = data.get("events") if type(data) is dict else None
                        actual_signed = (
                            type(project) is dict
                            and project.get("approval_policy") == "signed"
                        )
                        actual_event_count = (
                            len(events) if type(events) is list else None
                        )
                        if (
                            type(ledger.get("event_count"))
                            is not type(actual_event_count)
                            or ledger.get("event_count") != actual_event_count
                        ):
                            raise ObservationError(
                                "T ledger event count differs from verified bytes"
                            )
                        status_capture = ledger.get("independent_cli_status")
                        if (type(data) is dict and status_capture is None
                                and not (status == "run_time_budget_exhausted"
                                         and budget is not None
                                         and budget["exhausted_stage"] == "toolkit_after_status")):
                            raise ObservationError(
                                "T ledger lacks independent status capture"
                            )
                        if type(data) is not dict and status_capture is not None:
                            raise ObservationError(
                                "T ledger has unexpected status capture"
                            )
                    elif ledger.get("present") is False:
                        if (
                            ledger.get("sha256") is not None
                            or ledger.get("event_count") is not None
                            or ledger.get("independent_cli_status") is not None
                        ):
                            raise ObservationError(
                                "absent T ledger has contradictory records"
                            )
                        if _exists(work_fd, "case"):
                            with _directory(work_fd, "case") as case_fd:
                                if _exists(case_fd, "organon.json"):
                                    raise ObservationError(
                                        "T ledger exists but is marked absent"
                                    )
                        actual_signed = False
                    else:
                        raise ObservationError("T ledger present flag is invalid")
                    if ledger.get("independent_cli_status") is not None:
                        status_capture = _verify_capture(
                            run_fd,
                            ledger["independent_cli_status"],
                            "toolkit_after_status",
                            verified_streams,
                        )
                        if budget is not None:
                            _verify_budget_capture(
                                status_capture, summary.get("setup_timeout_seconds"),
                                "toolkit_after_status", summary["active_budget_seconds"],
                                budget_walls,
                            )
                        if (
                            status_capture["exit_code"] == 0
                            and not status_capture["timed_out"]
                        ):
                            observed_status = _read_recorded_json(
                                run_fd,
                                "toolkit_after_status.stdout",
                                verified_streams["toolkit_after_status.stdout"],
                                "independent toolkit status",
                            )
                            actual_signed = bool(
                                actual_signed
                                and type(observed_status) is dict
                                and type(observed_status.get("project")) is dict
                                and observed_status["project"].get("approval_policy")
                                == "signed"
                            )
                        else:
                            actual_signed = False
                    if (
                        type(ledger.get("signed_policy")) is not bool
                        or ledger["signed_policy"] != actual_signed
                    ):
                        raise ObservationError(
                            "T ledger signed-policy claim differs from verified bytes"
                        )
                    ledger_valid = bool(
                        ledger.get("present")
                        and actual_signed
                        and type(ledger.get("event_count")) is int
                        and ledger["event_count"] >= 1
                        and ledger.get("toolkit_files_unchanged")
                    )
                elif ledger is not None:
                    raise ObservationError("non-T arm has a ledger record")

                if (status == "run_time_budget_exhausted" and budget is not None):
                    if budget["exhausted_stage"] not in {
                        "cli", "post_cli", "toolkit_after_status", "finalize"
                    }:
                        raise ObservationError("budget stage contradicts captured CLI")
                    if (budget["exhausted_stage"] == "cli"
                            and not (capture["timed_out"] and capture.get("timeout_cap") == "run_budget")):
                        raise ObservationError("CLI budget expiry lacks its timeout capture")
                    if (budget["exhausted_stage"] == "toolkit_after_status"
                            and (arm != "T" or ledger is None)):
                        raise ObservationError("T status budget expiry lacks ledger evidence")
                    initial_status = "run_time_budget_exhausted"
                elif capture["timed_out"] and capture.get("timeout_cap") == "run_budget":
                    initial_status = "run_time_budget_exhausted"
                elif capture["timed_out"]:
                    initial_status = "cli_timeout"
                elif capture["exit_code"] != 0:
                    initial_status = "cli_failure"
                elif not usage["terminal_success"]:
                    initial_status = "cli_internal_failure"
                elif any(value is None for value in artifacts.values()):
                    initial_status = "required_artifact_missing"
                elif arm == "T" and not ledger_valid:
                    initial_status = "t_signed_ledger_missing_or_invalid"
                elif arm == "T" and (
                    process_trace is None
                    or not process_trace["inspectable"]
                    or process_trace["tool_ledger_publish_count"]
                    < ledger["event_count"] + 1
                    or process_trace["other_ledger_write_count"]
                ):
                    initial_status = "t_tool_execution_unverified"
                else:
                    initial_status = "artifacts_ready_for_inspection"
                if status not in REPLAY_STATUSES and status != initial_status:
                    raise ObservationError(
                        "execution status contradicts the verified run records"
                    )
                if (
                    status in REPLAY_STATUSES
                    and initial_status != "artifacts_ready_for_inspection"
                ):
                    raise ObservationError(
                        "replay status lacks a successful initial run"
                    )

                replay = summary.get("analysis_replay")
                if replay is not None:
                    if status not in REPLAY_STATUSES:
                        raise ObservationError(
                            "replay stream exists with a non-replay status"
                        )
                    if (
                        summary.get("reviewed_analysis_sha256")
                        != artifacts["analysis.py"]["sha256"]
                    ):
                        raise ObservationError(
                            "reviewed analysis digest differs from artifact"
                        )
                    replay_capture = _verify_capture(
                        run_fd, replay, "analysis_replay", verified_streams
                    )
                    sandbox_claim = replay_capture.get("sandbox")
                    if sandbox_claim is not None:
                        sandbox_claim = _object(sandbox_claim, "analysis_replay sandbox")
                        backend = sandbox_claim.get("backend")
                        enforced = sandbox_claim.get("enforced")
                        if (
                            type(enforced) is not bool
                            or type(backend) is not str
                            or backend not in {
                                "none", "linux_landlock_seccomp_rlimit_single_process"
                            }
                            or enforced is not (
                                backend == "linux_landlock_seccomp_rlimit_single_process"
                                and replay_capture.get("launch_error") is None
                            )
                        ):
                            raise ObservationError("replay sandbox claim is inconsistent")
                    if summary.get("replay_material_mismatches") != []:
                        raise ObservationError("replay recorded material mismatches")
                    if replay_capture.get("launch_error") is not None:
                        replay_status = "analysis_replay_launch_failure"
                    elif replay_capture["timed_out"]:
                        replay_status = "analysis_replay_timeout"
                    elif replay_capture["exit_code"] != 0:
                        replay_status = "analysis_replay_failure"
                    else:
                        replay_status = "output_replayed"
                    if status != replay_status:
                        raise ObservationError(
                            "replay status contradicts verified replay records"
                        )
                elif status in REPLAY_STATUSES:
                    raise ObservationError("replay status lacks replay stream records")

        if pilot_assets is not None and arm == "T":
            wheel = verified_inputs.get("work/specorganon-0.1.0-py3-none-any.whl")
            if wheel is None:
                if partial:
                    unavailable.append("work/specorganon-0.1.0-py3-none-any.whl")
                else:
                    raise ObservationError("pilot T wheel is unavailable for local dossier verification")
            elif wheel["sha256"] != pilot_assets["dist/specorganon-0.1.0-py3-none-any.whl"]:
                raise ObservationError("pilot T wheel differs from the copied dossier")
        if budget is not None and budget["elapsed_seconds"] is not None:
            # Each sequential subprocess is part of the invocation's elapsed
            # time. Millisecond rounding in each local declaration needs slack;
            # this checks consistency, not authenticated wall-clock custody.
            rounding_slack = 0.001 * (len(budget_walls) + 1)
            if sum(budget_walls.values()) > budget["elapsed_seconds"] + rounding_slack:
                raise ObservationError(
                    "run elapsed time is shorter than verified capture wall time"
                )
        if _read_summary(run_fd)[1] != summary_sha:
            raise ObservationError("run.json changed during observation")
        return {
            "schema": 1,
            "classification": "development_observation_unsealed",
            "run_json_sha256": summary_sha,
            "execution_status": status,
            "observation_state": (
                "partial"
                if partial or unavailable or unrecorded
                else "recorded_materials_verified_prelaunch_unproven"
                if observed_binding is not None
                else "recorded_materials_verified"
            ),
            "arm": arm,
            "pilot_mode": pilot_mode,
            "provider_cli": provider,
            "requested_model": model,
            "requested_effort": effort,
            "tool_policy": tool_policy,
            "pilot_triplet_binding": observed_binding,
            "prelaunch_binding_authenticated": False,
            "cli_usage": usage,
            "run_time_budget": (
                {"origin": "local_monotonic_declaration_not_authenticated",
                 "active_budget_seconds": summary["active_budget_seconds"],
                 "elapsed_seconds": budget["elapsed_seconds"],
                 "exhausted_stage": budget["exhausted_stage"]}
                if budget is not None else None
            ),
            "t_process_trace": process_trace,
            "verified_inputs": verified_inputs,
            "verified_streams": verified_streams,
            "verified_artifacts": verified_artifacts,
            "unavailable_materials": unavailable,
            "unrecorded_materials": unrecorded,
            "provider_request_ids": None,
            "authenticated_model_id": None,
            "authenticated_model_version": None,
            "authenticated_cost_usd": None,
            "authenticated_agent_attribution": None,
            "cap_status": "unknown",
            "controlled_comparison_eligible": False,
            "criterion_4": "not_assessed",
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_dir", type=Path, help="absolute directory from run_development_arm.py"
    )
    args = parser.parse_args(argv)
    try:
        result = observe_run_dir(args.run_dir)
    except (ObservationError, OSError) as exc:
        parser.exit(2, f"observe_development_run: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
