"""Run one digest-pinned generic tool against an existing development stage.

Usage::

    python scripts/run_staged_local_tool.py SCHEDULE.json RUN_ID /absolute/STAGE \
        TOOL_ID /absolute/EXECUTABLE /absolute/NEW_RECEIPT_DIR

The executable receives three absolute arguments: CASE_DIR, INPUTS_DIR, and
WORK_DIR. Its current directory is CASE_DIR. The visible case and inputs trees
are read-only; WORK_DIR is the only writable tree. The executable and Python
runtime roots (including stdlib, site-packages, and system libraries) are also
readable/executable. Stdout and stderr are captured in the private receipt
directory. The policy's /case and /work names are logical declarations; this
runner passes actual stage paths to Landlock rather than mounting those names.
This is an offline, single-process local tool run, not a model/provider run or
criterion-4 evidence. The policy's tool list and runtime_image_sha256 are
declarations; no image is sealed or attested.

The executable bytes are passed to the sandbox as a sealed anonymous file for
launch. Landlock/libseccomp restrictions are per child, without an aggregate
cgroup, filesystem quota, or complete same-UID isolation. In particular, a
same-UID process can change stage or runtime paths between validation and use
(TOCTOU). We rehash visible inputs afterward, but cannot rule out transient
swaps. Do not run unreviewed hostile code with this development primitive.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import stat
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from local_replay_sandbox import (
    SandboxError,
    SandboxUnavailable,
    default_python_runtime_roots,
    run_sandboxed,
)
from tool_policy import (
    MAX_POLICY_BYTES,
    ToolPolicyError,
    _check_directory_chain,
    _open_directory_chain,
    _read_bounded_file,
    validate_tool_policy_bytes,
)
from verify_released_run import ReleaseVerificationError, _read_schedule
from verify_staged_run import StageVerificationError, verify_stage


CLASSIFICATION = "development_local_generic_tool_execution_unsealed"
NOTICE = (
    "Offline local process only; generic_tools and runtime_image_sha256 are "
    "declarations without a sealed image. No provider call, model token "
    "measurement, external custody, or criterion-4 assessment is established. "
    "Stage and output inventories remain point-in-time same-UID checks."
)
MAX_EXECUTABLE_BYTES = 16 * 1024 * 1024
MAX_STAGE_FILES = 600
MAX_STAGE_BYTES = 1200 * 1024 * 1024
MAX_STAGE_ENTRIES = 5000
MAX_WORK_FILES = 256
MAX_WORK_BYTES = 64 * 1024 * 1024
MAX_WORK_FILE_BYTES = 8 * 1024 * 1024
MAX_WORK_ENTRIES = 512
MAX_TREE_DEPTH = 16
MAX_RELATIVE_PATH_BYTES = 2048
CHUNK = 1024 * 1024
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW


class LocalToolError(ValueError):
    """The local tool run cannot be prepared or its receipt cannot be saved."""


class _InventoryLimit(Exception):
    pass


def _bounded_names(directory_fd: int, maximum: int) -> list[str]:
    names: list[str] = []
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            if len(names) >= maximum:
                raise _InventoryLimit("tree entry limit reached")
            names.append(entry.name)
    return sorted(names)


def _state(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
        info.st_size, info.st_mtime_ns, info.st_ctime_ns,
    )


def _hash_file(directory_fd: int, name: str, max_bytes: int) -> tuple[int, str, tuple[int, ...]]:
    fd = os.open(name, FILE_FLAGS, dir_fd=directory_fd)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise LocalToolError("tree contains a nonregular or multiply linked file")
        if before.st_size > max_bytes:
            raise _InventoryLimit("file byte limit reached")
        digest = hashlib.sha256()
        read = 0
        while chunk := os.read(fd, min(CHUNK, max_bytes - read + 1)):
            read += len(chunk)
            if read > max_bytes:
                raise _InventoryLimit("file byte limit reached")
            digest.update(chunk)
        after = os.fstat(fd)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if read != before.st_size or _state(before) != _state(after) or _state(before) != _state(named):
            raise LocalToolError("tree file changed during hashing")
        return read, digest.hexdigest(), _state(before)
    finally:
        os.close(fd)


def _inventory(
    root: Path, *, max_files: int, max_bytes: int,
    max_file_bytes: int, max_entries: int,
) -> tuple[list[dict[str, Any]], dict[str, tuple[int, ...]], bool, str | None]:
    """No-follow inventory; partial results are never called complete."""
    files: list[dict[str, Any]] = []
    directories: dict[str, tuple[int, ...]] = {}
    total = 0

    def walk(directory_fd: int, prefix: str, depth: int) -> None:
        nonlocal total
        if depth > MAX_TREE_DEPTH:
            raise _InventoryLimit("tree depth limit reached")
        before = os.fstat(directory_fd)
        if not stat.S_ISDIR(before.st_mode):
            raise LocalToolError("tree directory is not a directory")
        if len(files) + len(directories) >= max_entries:
            raise _InventoryLimit("tree entry limit reached")
        directories[prefix] = _state(before)
        names = _bounded_names(directory_fd, max_entries)
        for name in names:
            if name in (".", "..") or "/" in name:
                raise LocalToolError("tree contains an invalid name")
            relative = f"{prefix}/{name}" if prefix else name
            if len(relative.encode("utf-8", errors="surrogateescape")) > MAX_RELATIVE_PATH_BYTES:
                raise _InventoryLimit("tree path byte limit reached")
            if len(files) + len(directories) >= max_entries:
                raise _InventoryLimit("tree entry limit reached")
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                fd = os.open(name, DIR_FLAGS, dir_fd=directory_fd)
                try:
                    if _state(info) != _state(os.fstat(fd)):
                        raise LocalToolError("tree directory changed during opening")
                    walk(fd, relative, depth + 1)
                    if _state(info) != _state(os.fstat(fd)):
                        raise LocalToolError("tree directory changed during scan")
                finally:
                    os.close(fd)
            elif stat.S_ISREG(info.st_mode):
                if len(files) >= max_files or total + info.st_size > max_bytes:
                    raise _InventoryLimit("file count or aggregate byte limit reached")
                size, sha256, file_state = _hash_file(directory_fd, name, max_file_bytes)
                total += size
                files.append({"path": relative, "bytes": size, "sha256": sha256,
                              "state": file_state})
            else:
                raise LocalToolError("tree contains a symlink or special file")
        if _bounded_names(directory_fd, max_entries) != names or _state(os.fstat(directory_fd)) != _state(before):
            raise LocalToolError("tree directory changed during scan")

    try:
        fd = os.open(root, DIR_FLAGS)
        try:
            walk(fd, "", 0)
        finally:
            os.close(fd)
        return files, directories, True, None
    except (_InventoryLimit, LocalToolError, OSError) as exc:
        return files, directories, False, str(exc)


def _immutable_snapshot(stage: Path) -> dict[str, Any]:
    root_fd = os.open(stage, DIR_FLAGS)
    try:
        try:
            if set(_bounded_names(root_fd, 5)) != {"case", "inputs", "work", "stage.json"}:
                raise LocalToolError("stage root entries changed")
        except _InventoryLimit as exc:
            raise LocalToolError("stage root has too many entries") from exc
    finally:
        os.close(root_fd)
    root_info = os.stat(stage, follow_symlinks=False)
    if not stat.S_ISDIR(root_info.st_mode):
        raise LocalToolError("stage root is not a directory")
    result: dict[str, Any] = {"root_identity": (
        root_info.st_dev, root_info.st_ino, root_info.st_mode,
        root_info.st_uid, root_info.st_nlink,
    )}
    for name in ("case", "inputs"):
        files, directories, complete, reason = _inventory(
            stage / name, max_files=MAX_STAGE_FILES,
            max_bytes=MAX_STAGE_BYTES, max_file_bytes=MAX_STAGE_BYTES,
            max_entries=MAX_STAGE_ENTRIES,
        )
        if not complete:
            raise LocalToolError(f"stage {name} snapshot incomplete: {reason}")
        result[name] = {"files": files, "directories": directories}
    root_fd = os.open(stage, DIR_FLAGS)
    try:
        size, digest, state = _hash_file(root_fd, "stage.json", 1024 * 1024)
    finally:
        os.close(root_fd)
    result["stage.json"] = (size, digest, state)
    work_info = os.stat(stage / "work", follow_symlinks=False)
    if not stat.S_ISDIR(work_info.st_mode):
        raise LocalToolError("work root is not a directory")
    result["work_identity"] = (
        work_info.st_dev, work_info.st_ino, work_info.st_mode,
        work_info.st_uid,
    )
    return result


def _check_snapshot_bindings(
    schedule: dict[str, Any], run_id: str, stage: Path, snapshot: dict[str, Any]
) -> None:
    """Bind every staged input to the independent schedule after verification."""
    run = next(item for item in schedule["runs"] if item["run_id"] == run_id)
    expected: dict[str, str] = {
        "case_package": run["case_package_sha256"],
        "task_contract": schedule["inputs"]["task_contract"]["sha256"],
        "common_prompt": schedule["inputs"]["common_prompt"]["sha256"],
        "arm_prompt": schedule["inputs"]["arm_prompts"][run["arm"]]["sha256"],
        "tool_policy": schedule["inputs"]["tool_policy"]["sha256"],
    }
    if run["arm"] == "S":
        expected["sdd_guide"] = schedule["inputs"]["sdd_guide"]["sha256"]
    if run["arm"] == "T":
        expected["toolkit"] = schedule["inputs"]["toolkit"]["sha256"]
    actual = {item["path"]: item["sha256"] for item in snapshot["inputs"]["files"]}
    if actual != expected:
        raise LocalToolError("staged input bytes differ from independent schedule")
    stage_bytes = _read_bounded_file(stage / "stage.json", "stage manifest", 1024 * 1024)
    if hashlib.sha256(stage_bytes).hexdigest() != snapshot["stage.json"][1]:
        raise LocalToolError("stage manifest changed after snapshot")
    manifest = json.loads(stage_bytes)
    if (
        manifest["run_id"] != run_id
        or manifest["schedule_sha256"] != schedule["schedule_sha256"]
        or {role: item["sha256"] for role, item in manifest["visible_files"].items()} != expected
    ):
        raise LocalToolError("stage manifest differs from independent schedule")


def _private_receipt_dir(path: Path, stage: Path) -> None:
    if not path.is_absolute() or path == Path("/"):
        raise LocalToolError("receipt directory must be an absolute new path")
    if path.is_relative_to(stage) or stage.is_relative_to(path):
        raise LocalToolError("receipt directory must be separate from stage")
    with ExitStack() as stack:
        parent_fd, name, chain = _open_directory_chain(path, "receipt directory", stack)
        _check_directory_chain(chain, "receipt directory")
        parent = os.fstat(parent_fd)
        if parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
            raise LocalToolError("receipt parent must be owned by current UID and not writable by others")
        os.mkdir(name, 0o700, dir_fd=parent_fd)
        child = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(child.st_mode) or child.st_uid != os.geteuid() or stat.S_IMODE(child.st_mode) != 0o700:
            raise LocalToolError("receipt directory is not private")


def _write_receipt(path: Path, value: dict[str, Any]) -> None:
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def run_staged_local_tool(
    schedule_raw: Any, run_id: str, stage_dir: Path | str, tool_id: str,
    executable: Path | str, receipt_dir: Path | str, *,
    wall_seconds: float = 30.0, cpu_seconds: int = 10,
    address_space_bytes: int = 512 * 1024 * 1024,
    file_bytes_per_file: int = 8 * 1024 * 1024,
) -> dict[str, Any]:
    """Prepare, execute once, and save a separate local receipt."""
    stage = Path(stage_dir)
    tool = Path(executable)
    receipt = Path(receipt_dir)
    if not stage.is_absolute() or not tool.is_absolute() or not receipt.is_absolute():
        raise LocalToolError("stage, executable, and receipt paths must be absolute")
    if any(part in (".", "..") for path in (stage, tool, receipt) for part in path.parts):
        raise LocalToolError("paths must not contain dot components")
    if type(tool_id) is not str or not tool_id:
        raise LocalToolError("tool_id is required")
    try:
        schedule = copy.deepcopy(schedule_raw)
    except (TypeError, ValueError, RuntimeError, RecursionError) as exc:
        raise LocalToolError("candidate schedule cannot be snapshotted") from exc
    baseline = _immutable_snapshot(stage)
    verified = verify_stage(schedule, run_id, stage)
    after_verification = _immutable_snapshot(stage)
    if after_verification != baseline:
        raise LocalToolError("stage changed across verification")
    _check_snapshot_bindings(schedule, run_id, stage, after_verification)
    policy_bytes = _read_bounded_file(stage / "inputs" / "tool_policy", "staged tool policy", MAX_POLICY_BYTES)
    if hashlib.sha256(policy_bytes).hexdigest() != schedule["inputs"]["tool_policy"]["sha256"]:
        raise LocalToolError("staged tool policy differs from independent schedule")
    policy = validate_tool_policy_bytes(
        policy_bytes, expected_limits=schedule["per_run_limits"]
    )
    selected = next((item for item in policy["generic_tools"] if item["id"] == tool_id), None)
    if selected is None:
        raise LocalToolError("tool_id is absent from staged generic_tools")
    tool_bytes = _read_bounded_file(tool, "tool executable", MAX_EXECUTABLE_BYTES)
    actual = hashlib.sha256(tool_bytes).hexdigest()
    if actual != selected["executable_sha256"]:
        raise LocalToolError("tool executable SHA-256 differs from staged policy")
    if not os.access(tool, os.X_OK):
        raise LocalToolError("tool executable is not executable")
    if (
        type(wall_seconds) not in (float, int) or not math.isfinite(wall_seconds)
        or not 0 < wall_seconds <= min(300, policy["limits"]["active_seconds"])
        or type(cpu_seconds) is not int or not 1 <= cpu_seconds <= 300
        or type(address_space_bytes) is not int or not 64 * 1024 * 1024 <= address_space_bytes <= 1024 * 1024 * 1024
        or type(file_bytes_per_file) is not int or not 4096 <= file_bytes_per_file <= MAX_WORK_FILE_BYTES
    ):
        raise LocalToolError("invalid local wall, CPU, address-space, or file-size limits")
    before = _immutable_snapshot(stage)
    if before != baseline:
        raise LocalToolError("stage changed before local tool launch")
    _check_snapshot_bindings(schedule, run_id, stage, before)
    work_fd = os.open(stage / "work", DIR_FLAGS)
    try:
        try:
            if _bounded_names(work_fd, 1):
                raise LocalToolError("stage work directory is not empty")
        except _InventoryLimit as exc:
            raise LocalToolError("stage work directory is not empty") from exc
    finally:
        os.close(work_fd)
    case_manifest = json.loads(_read_bounded_file(
        stage / "case" / "case.json", "staged case manifest", 1024 * 1024
    ))
    deliverables = case_manifest["deliverables"]
    _private_receipt_dir(receipt, stage)
    stdout_path = receipt / "stdout"
    stderr_path = receipt / "stderr"
    sandbox_result = None
    launch_error = None
    try:
        sandbox_result = run_sandboxed(
            argv=[str(tool), str(stage / "case"), str(stage / "inputs"), str(stage / "work")],
            cwd=stage / "case", read_roots=[stage / "case", stage / "inputs"],
            write_roots=[stage / "work"],
            runtime_roots=default_python_runtime_roots(),
            stdout_path=stdout_path, stderr_path=stderr_path,
            timeout_seconds=float(wall_seconds), cpu_seconds=cpu_seconds,
            address_space_bytes=address_space_bytes,
            file_bytes_per_file=file_bytes_per_file,
            env={"HOME": str(stage / "work"), "TMPDIR": str(stage / "work")},
            sealed_executable_bytes=tool_bytes,
            sealed_executable_sha256=actual,
        )
    except (SandboxError, SandboxUnavailable, OSError, ValueError) as exc:
        launch_error = f"{type(exc).__name__}: {exc}"
    if sandbox_result is not None:
        launch_error = sandbox_result.launch_error

    files, _directories, inventory_complete, inventory_reason = _inventory(
        stage / "work", max_files=MAX_WORK_FILES,
        max_bytes=MAX_WORK_BYTES, max_file_bytes=MAX_WORK_FILE_BYTES,
        max_entries=MAX_WORK_ENTRIES,
    )
    try:
        stage_unchanged = _immutable_snapshot(stage) == before
        stage_change_reason = None if stage_unchanged else "stage visible bytes or metadata changed"
    except (LocalToolError, OSError) as exc:
        stage_unchanged = False
        stage_change_reason = str(exc)
    try:
        executable_unchanged = hashlib.sha256(
            _read_bounded_file(tool, "tool executable", MAX_EXECUTABLE_BYTES)
        ).hexdigest() == actual
    except ToolPolicyError:
        executable_unchanged = False
    execution_bytes_sealed = (
        sandbox_result is not None
        and sandbox_result.sealed_executable_sha256 == actual
        and sandbox_result.launch_error is None
    )
    if sandbox_result is not None and not execution_bytes_sealed and launch_error is None:
        launch_error = "sealed executable launch was not confirmed"
    output_paths = {entry["path"] for entry in files}
    deliverables_present = (
        all(item in output_paths for item in deliverables) if inventory_complete else None
    )
    if not stage_unchanged or not executable_unchanged:
        status = "stage_or_executable_mutated"
    elif sandbox_result is not None and sandbox_result.timed_out:
        status = "timeout"
    elif launch_error is not None:
        status = "launch_failure"
    elif sandbox_result is None or sandbox_result.exit_code != 0:
        status = "tool_failure"
    elif not inventory_complete:
        status = "output_inventory_incomplete"
    elif not deliverables_present:
        status = "deliverables_missing"
    else:
        status = "success"
    report = {
        "schema": 1, "classification": CLASSIFICATION, "notice": NOTICE,
        "run_id": run_id, "run_sha256": verified["run_sha256"],
        "schedule_sha256": verified["schedule_sha256"],
        "tool_id": tool_id, "tool_version": selected["version"],
        "executable_sha256": actual, "executable_unchanged_after_run": executable_unchanged,
        "sealed_executable_sha256": (
            sandbox_result.sealed_executable_sha256 if sandbox_result else None
        ),
        "execution_bytes_sealed": execution_bytes_sealed,
        "policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
        "runtime_image_sha256_declared": policy["runtime_image_sha256"],
        "runtime_image_verified": False,
        "status": status, "exit_code": sandbox_result.exit_code if sandbox_result else None,
        "timed_out": sandbox_result.timed_out if sandbox_result else False,
        "launch_error": launch_error,
        "duration_seconds": sandbox_result.duration_seconds if sandbox_result else None,
        "landlock_abi": sandbox_result.landlock_abi if sandbox_result else None,
        "stage_unchanged_after_run": stage_unchanged,
        "stage_change_reason": stage_change_reason,
        "output_inventory_complete": inventory_complete,
        "output_inventory_reason": inventory_reason,
        "outputs": [{key: entry[key] for key in ("path", "bytes", "sha256")} for entry in files],
        "deliverables": deliverables, "deliverables_present": deliverables_present,
        "stdout": str(stdout_path) if stdout_path.exists() else None,
        "stderr": str(stderr_path) if stderr_path.exists() else None,
        "provider_calls": 0, "measured_tokens": None,
        "criterion_4": "not_assessed", "provider_receipt": False,
        "local_tool_calls": 0 if launch_error else 1,
        "limits_applied": {
            "wall_seconds": wall_seconds, "cpu_seconds": cpu_seconds,
            "address_space_bytes": address_space_bytes,
            "file_bytes_per_file": file_bytes_per_file,
        },
    }
    _write_receipt(receipt / "receipt.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("schedule")
    parser.add_argument("run_id")
    parser.add_argument("stage_dir")
    parser.add_argument("tool_id")
    parser.add_argument("executable")
    parser.add_argument("receipt_dir")
    parser.add_argument("--wall-seconds", type=float, default=30.0)
    parser.add_argument("--cpu-seconds", type=int, default=10)
    parser.add_argument("--address-space-bytes", type=int, default=512 * 1024 * 1024)
    parser.add_argument("--file-bytes-per-file", type=int, default=8 * 1024 * 1024)
    args = parser.parse_args(argv)
    try:
        report = run_staged_local_tool(
            _read_schedule(args.schedule), args.run_id, args.stage_dir,
            args.tool_id, args.executable, args.receipt_dir,
            wall_seconds=args.wall_seconds, cpu_seconds=args.cpu_seconds,
            address_space_bytes=args.address_space_bytes,
            file_bytes_per_file=args.file_bytes_per_file,
        )
    except (LocalToolError, StageVerificationError, ReleaseVerificationError,
            ToolPolicyError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"Local tool preparation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return {"success": 0, "launch_failure": 3, "timeout": 4,
            "tool_failure": 5, "output_inventory_incomplete": 6,
            "deliverables_missing": 7, "stage_or_executable_mutated": 8}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
