"""Read-only byte-checked observation of one exposed D-E pilot directory.

Usage: ``python scripts/observe_development_run.py /absolute/run/directory``.
This exports local evidence only. It is neither a provider receipt nor a
confirmatory or criterion-4 result, and it never runs generated code.
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

from run_development_arm import PUBLIC_FILES, _assembled_prompt, _parse_usage


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
            or timed_out
        ):
            raise ObservationError(
                f"{prefix} capture has inconsistent launch failure fields"
            )
    elif exit_code is None:
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
        # Pre-check no-command pilots stored the same aggregate parser fields
        # without this new trace summary. Recompute the gate before accepting
        # that historical shape; an observed command still changes terminal_success.
        legacy_observed = dict(observed)
        legacy_observed.pop("no_command_tool_trace", None)
        if not agy_no_command_tool or legacy_observed != declared:
            raise ObservationError("cli_usage differs from the verified local CLI stream")
    return {
        "origin": observed["origin"],
        "complete": observed["complete"],
        "terminal_success": observed["terminal_success"],
        "final_usage": observed["final_usage"],
        "preterminal_step_usage": observed["preterminal_step_usage"],
        "no_command_tool_trace": observed.get("no_command_tool_trace"),
    }


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
    run_fd: int, work_fd: int, raw: Any, streams: dict[str, dict[str, Any]]
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
        if arm not in ("N", "S", "T") or provider not in ("codex", "agy"):
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

        verified_inputs: dict[str, dict[str, Any]] = {}
        verified_streams: dict[str, dict[str, Any]] = {}
        verified_artifacts: dict[str, dict[str, Any]] = {}
        unavailable: list[str] = []
        unrecorded: list[str] = []
        partial = status in {"preparing", "preflight_failure"}
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
                    wheel_name, wheel_record = _verify_toolkit(
                        run_fd, work_fd, toolkit, verified_streams
                    )
                    verified_inputs[f"work/{wheel_name}"] = wheel_record
                if summary.get("t_ledger") is not None:
                    raise ObservationError(
                        "partial run has a ledger record before CLI completion"
                    )
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
                        run_fd, work_fd, toolkit, verified_streams
                    )
                    verified_inputs[f"work/{wheel_name}"] = wheel_record
                elif arm == "T":
                    raise ObservationError("T run lacks a toolkit record")
                ledger = summary.get("t_ledger")
                ledger_valid = True
                if arm == "T":
                    ledger = _object(ledger, "t_ledger")
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
                        if type(data) is dict and status_capture is None:
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

                if capture["timed_out"]:
                    initial_status = "cli_timeout"
                elif capture["exit_code"] != 0:
                    initial_status = "cli_failure"
                elif not usage["terminal_success"]:
                    initial_status = "cli_internal_failure"
                elif any(value is None for value in artifacts.values()):
                    initial_status = "required_artifact_missing"
                elif arm == "T" and not ledger_valid:
                    initial_status = "t_signed_ledger_missing_or_invalid"
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
                    if summary.get("replay_material_mismatches") != []:
                        raise ObservationError("replay recorded material mismatches")
                    if replay_capture["timed_out"]:
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
                else "recorded_materials_verified"
            ),
            "arm": arm,
            "provider_cli": provider,
            "requested_model": model,
            "requested_effort": effort,
            "tool_policy": tool_policy,
            "cli_usage": usage,
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
