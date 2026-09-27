"""Opt-in local repeat audit of a current signed test execution report.

Usage::

    python scripts/audit_signed_test_execution.py CASE ITEM RUN_DIR \
        --executable-sha256 HEX

RUN_DIR must be a new, private (0700) directory containing only an ``input``
directory. No path component of RUN_DIR or ``input`` may be a symlink. The
signed argv runs with ``input`` as its read-only cwd; HOME is the
new ``artifacts`` write directory and TMPDIR is a separate new write directory.
Report artifact paths are relative to ``artifacts``. The executable named by
argv[0] must be an absolute, canonical, regular file. Its exact bytes are
digest-pinned and copied to the sandbox's sealed executable FD before launch.
The sandbox uses ``/proc/self/fd/N`` as the child's argv[0] in sealed mode;
the JSON records that the declared argv is therefore not reproduced literally.

This repeats the declared command now. A match cannot establish that the
historical signed report came from an execution or an independent custodian.
The existing engine gate is not modified. This CLI never appends to the case.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path
from typing import Any

from specorganon import engine, test_execution
from specorganon.ledger import read_project

from local_replay_sandbox import (
    SandboxError,
    SandboxUnavailable,
    default_python_runtime_roots,
    probe_sandbox,
    run_sandboxed,
)


MAX_EXECUTABLE_BYTES = 16 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
PATH_DIR_FLAGS = os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
LIMITATIONS = [
    "A local repeat run does not prove the historical signed execution occurred.",
    "The configured signer is not an independent custodian of this local observation.",
    "Landlock and seccomp restrict one child, without namespace or aggregate filesystem quotas; same-UID path races remain possible.",
    "Only declared artifact paths are hashed, with bounded file reads.",
    "The sandbox's sealed exec substitutes a procfd path for argv[0] inside the child; argv[1:] is unchanged.",
]


class AuditError(ValueError):
    """The signed target or local preparation cannot support this audit."""


def _state(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _private_directory(path: Path) -> Path:
    if not path.is_absolute() or ".." in path.parts or len(path.parts) > 64:
        raise AuditError("private directory path must be absolute with at most 63 components and no '..'")
    try:
        fd = os.open("/", PATH_DIR_FLAGS)
        try:
            for component in path.parts[1:]:
                next_fd = os.open(component, PATH_DIR_FLAGS, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            info = os.fstat(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise AuditError("private directory is unavailable or contains a symlink") from exc
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise AuditError("private directory must be owned by the current UID with mode 0700")
    resolved = path.resolve(strict=True)
    if resolved != path:
        raise AuditError("private directory changed or contains a symlink")
    return resolved


def _read_executable(path: str, expected_sha256: str) -> bytes:
    if not SHA256.fullmatch(expected_sha256):
        raise AuditError("executable SHA-256 pin must be a lowercase digest")
    executable = Path(path)
    if (not executable.is_absolute() or any(part in {".", ".."} for part in executable.parts)
            or executable.is_symlink() or executable.resolve(strict=True) != executable):
        raise AuditError("signed argv[0] must name an absolute canonical non-symlink executable")
    try:
        fd = os.open(executable, FILE_FLAGS)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or not before.st_mode & 0o111:
                raise AuditError("signed executable is not an executable regular file")
            if before.st_size <= 0 or before.st_size > MAX_EXECUTABLE_BYTES:
                raise AuditError("signed executable exceeds the sealed-byte limit")
            chunks: list[bytes] = []
            total = 0
            while chunk := os.read(fd, min(1024 * 1024, MAX_EXECUTABLE_BYTES - total + 1)):
                total += len(chunk)
                if total > MAX_EXECUTABLE_BYTES:
                    raise AuditError("signed executable exceeds the sealed-byte limit")
                chunks.append(chunk)
            after = os.fstat(fd)
            named = os.stat(executable, follow_symlinks=False)
            if total != before.st_size or _state(before) != _state(after) or _state(before) != _state(named):
                raise AuditError("signed executable changed while being read")
        finally:
            os.close(fd)
    except OSError as exc:
        raise AuditError("signed executable could not be opened safely") from exc
    contents = b"".join(chunks)
    if hashlib.sha256(contents).hexdigest() != expected_sha256:
        raise AuditError("signed executable does not match the SHA-256 pin")
    return contents


def _hash_beneath(root: Path, relative: str, maximum: int) -> tuple[str, int]:
    """Hash one regular file using no-follow dirfd opens for every component."""
    parts = relative.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise AuditError("noncanonical artifact path")
    opened: list[int] = []
    try:
        directory_fd = os.open(root, DIR_FLAGS)
        opened.append(directory_fd)
        for part in parts[:-1]:
            directory_fd = os.open(part, DIR_FLAGS, dir_fd=directory_fd)
            opened.append(directory_fd)
        fd = os.open(parts[-1], FILE_FLAGS, dir_fd=directory_fd)
        opened.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise AuditError("artifact is not a singly linked regular file")
        if before.st_size > maximum:
            raise AuditError("artifact exceeds the byte limit")
        digest = hashlib.sha256()
        total = 0
        while chunk := os.read(fd, min(1024 * 1024, maximum - total + 1)):
            total += len(chunk)
            if total > maximum:
                raise AuditError("artifact exceeds the byte limit")
            digest.update(chunk)
        after = os.fstat(fd)
        named = os.stat(parts[-1], dir_fd=directory_fd, follow_symlinks=False)
        if total != before.st_size or _state(before) != _state(after) or _state(before) != _state(named):
            raise AuditError("artifact changed while being hashed")
        return digest.hexdigest(), total
    finally:
        for fd in reversed(opened):
            os.close(fd)


def _current_signed_report(case: Path, item_id: str) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    state = engine.get_state(case)
    if state["project"].get("approval_policy") != "signed":
        raise AuditError("case does not use signed approvals")
    item = state["items"].get(item_id)
    if item is None or item["kind"] != "test" or test_execution.item_issues(item):
        raise AuditError("item is not a valid current signed test")
    provenance = item.get("test_execution_provenance")
    if (state["test_execution_trust"] != "configured" or provenance is None
            or item["test_execution_status"] not in {"signed_passed", "signed_failed"}):
        raise AuditError("current test has no valid trusted signed execution report")
    ledger = read_project(case)
    seq, event_hash = provenance
    if (state["revision"] != len(ledger["events"]) or type(seq) is not int
            or not 1 <= seq <= len(ledger["events"])):
        raise AuditError("case changed while selecting its signed report")
    event = ledger["events"][seq - 1]
    history = next((entry for entry in state["test_execution_history"]
                    if entry["seq"] == seq and entry["hash"] == event_hash), None)
    if (event["hash"] != event_hash or event["kind"] != "test_execution"
            or history is None or history["signature_verified"] is not True
            or event["payload"].get("id") != item_id
            or event["payload"].get("version") != item["version"]):
        raise AuditError("signed report provenance is unavailable or unverified")
    report = test_execution.validate_report(event["payload"]["report"])
    if report["argv"] != item["data"]["argv"]:
        raise AuditError("signed report argv differs from the current item")
    head_hash = ledger["events"][-1]["hash"] if ledger["events"] else "0" * 64
    return (report, {"seq": seq, "hash": event_hash, "item_version": item["version"]},
            head_hash, state["project"]["case_id"])


def audit_signed_test_execution(
    case_dir: Path | str, item_id: str, run_dir: Path | str, executable_sha256: str,
    *, timeout_seconds: float = 10.0, cpu_seconds: int = 10,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> dict[str, Any]:
    """Repeat one current signed argv under the Linux sandbox; never write the case."""
    if (not math.isfinite(timeout_seconds) or timeout_seconds <= 0 or timeout_seconds > 300
            or type(cpu_seconds) is not int or not 1 <= cpu_seconds <= 300
            or type(max_file_bytes) is not int or not 4096 <= max_file_bytes <= MAX_FILE_BYTES):
        raise AuditError("invalid local resource limits")
    case = Path(case_dir).resolve(strict=True)
    run = _private_directory(Path(run_dir))
    if case == run or case.is_relative_to(run) or run.is_relative_to(case):
        raise AuditError("run directory must be separate from the case")
    input_dir = _private_directory(run / "input")
    if input_dir.parent != run or set(path.name for path in run.iterdir()) != {"input"}:
        raise AuditError("new run directory must contain only input before launch")
    report, provenance, head_before, case_id = _current_signed_report(case, item_id)
    executable_bytes = _read_executable(report["argv"][0], executable_sha256)
    capability = probe_sandbox()
    if not capability.available:
        raise SandboxUnavailable(capability.reason or "sandbox unavailable")

    artifacts = run / "artifacts"
    temporary = run / "tmp"
    artifacts.mkdir(mode=0o700)
    temporary.mkdir(mode=0o700)
    result = run_sandboxed(
        argv=report["argv"], cwd=input_dir, read_roots=[input_dir],
        write_roots=[artifacts, temporary],
        runtime_roots=default_python_runtime_roots(),
        stdout_path=run / "stdout.bin", stderr_path=run / "stderr.bin",
        timeout_seconds=timeout_seconds, cpu_seconds=cpu_seconds,
        file_bytes_per_file=max_file_bytes,
        env={"HOME": str(artifacts), "TMPDIR": str(temporary)},
        sealed_executable_bytes=executable_bytes,
        sealed_executable_sha256=executable_sha256,
    )
    observation: dict[str, Any] = {
        "signature_verified": True,
        "observed_locally": False,
        "observed_passed": False,
        "report_matches_observation": False,
        "case_id": case_id,
        "item_id": item_id,
        "report_provenance": provenance,
        "declared_argv_sha256": hashlib.sha256(json.dumps(
            report["argv"], ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).hexdigest(),
        "declared_executable_sha256_pin": executable_sha256,
        "sealed_executable_sha256": result.sealed_executable_sha256,
        "exact_argv_reproduced": False,
        "executed_argv0_form": "/proc/self/fd/<sealed-fd>",
        "sandbox": {"landlock_abi": result.landlock_abi,
                    "timed_out": result.timed_out, "exit_code": result.exit_code,
                    "launch_error": result.launch_error},
        "checks": {},
        "limitations": LIMITATIONS,
    }
    checks = observation["checks"]
    checks["exit_code"] = result.exit_code == report["exit_code"]
    checks["timed_out"] = result.timed_out == report["timed_out"]
    checks["sealed_executable"] = result.sealed_executable_sha256 == executable_sha256
    checks["launch"] = result.launch_error is None
    for label in ("stdout", "stderr"):
        try:
            digest, _ = _hash_beneath(run, f"{label}.bin", max_file_bytes)
            checks[f"{label}_sha256"] = digest == report[f"{label}_sha256"]
            observation[f"{label}_sha256"] = digest
        except (AuditError, OSError) as exc:
            checks[f"{label}_sha256"] = False
            observation[f"{label}_error"] = type(exc).__name__
    artifact_checks: list[dict[str, Any]] = []
    remaining = MAX_ARTIFACT_BYTES
    for expected in report["artifacts"]:
        item_check: dict[str, Any] = {"path": expected["path"], "matches": False}
        try:
            digest, size = _hash_beneath(artifacts, expected["path"], min(max_file_bytes, remaining))
            remaining -= size
            item_check.update({"observed_sha256": digest,
                               "matches": digest == expected["sha256"]})
        except (AuditError, OSError) as exc:
            item_check["error"] = type(exc).__name__
        artifact_checks.append(item_check)
    observation["artifact_checks"] = artifact_checks
    checks["artifacts"] = all(item["matches"] for item in artifact_checks)
    ledger_after = read_project(case)
    head_after = ledger_after["events"][-1]["hash"] if ledger_after["events"] else "0" * 64
    checks["ledger_unchanged"] = head_after == head_before
    matched = all(checks.values())
    observation["report_matches_observation"] = matched
    observation["observed_locally"] = matched
    observation["observed_passed"] = matched and report["exit_code"] == 0 and not report["timed_out"]
    return observation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("item_id")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--executable-sha256", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--cpu-seconds", type=int, default=10)
    args = parser.parse_args(argv)
    try:
        output = audit_signed_test_execution(
            args.case, args.item_id, args.run_dir, args.executable_sha256,
            timeout_seconds=args.timeout_seconds, cpu_seconds=args.cpu_seconds,
        )
        status = 0 if output["observed_passed"] else 1
    except (AuditError, SandboxError, SandboxUnavailable, OSError, ValueError, KeyError) as exc:
        try:
            _current_signed_report(args.case.resolve(strict=True), args.item_id)
        except (AuditError, OSError, ValueError, KeyError):
            signature_verified = False
        else:
            signature_verified = True
        detail = str(exc) if isinstance(exc, (AuditError, SandboxError, SandboxUnavailable)) else "audit could not complete"
        output = {"signature_verified": signature_verified, "observed_locally": False,
                  "observed_passed": False, "report_matches_observation": False,
                  "error": f"{type(exc).__name__}: {detail}", "limitations": LIMITATIONS}
        status = 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
