"""Durable tool delegation to private branches of one managed development wave.

This is a same-UID development primitive, not a boundary for hostile code.
The parent owns the only admission claim, context, and token ledger.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import secrets
import stat
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

import local_run_admission as admission
from local_replay_sandbox import default_python_runtime_roots, run_sandboxed
from run_staged_local_tool import MAX_EXECUTABLE_BYTES, _immutable_snapshot
from staged_tool_session import _work_inventory
from tool_policy import _read_bounded_file


class BrokerError(ValueError):
    """A delegation, claim, journal, or local effect cannot be trusted."""


MANIFEST_NAME = "branch_manifest.json"
MAX_MANIFEST_BYTES = 12 * 1024 * 1024
MAX_RECORD_BYTES = 1024 * 1024
MAX_ARGUMENT_BYTES = 64 * 1024
MAX_STREAM_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 128 * 1024
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
PROFILES = {"workspace", "analysis_readonly"}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _unique(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BrokerError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise BrokerError(f"nonfinite JSON constant: {value}")


def _parse(raw: bytes | str, label: str, maximum: int) -> Any:
    data = raw.encode("utf-8") if type(raw) is str else raw
    if type(data) is not bytes or len(data) > maximum:
        raise BrokerError(f"{label} exceeds byte bound")
    try:
        return json.loads(data, object_pairs_hook=_unique, parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise BrokerError(f"{label} is invalid JSON") from exc


def _read_json(path: Path, maximum: int = MAX_RECORD_BYTES) -> dict:
    raw = _read_bounded_file(path, "broker record", maximum)
    obj = _parse(raw, "broker record", maximum)
    if type(obj) is not dict or _canonical(obj) != raw:
        raise BrokerError("broker record is not canonical JSON object")
    return obj


def _identifier(value: Any, label: str) -> str:
    if type(value) is not str or ID.fullmatch(value) is None:
        raise BrokerError(f"invalid {label}")
    return value


def _digest(value: Any, label: str) -> str:
    if type(value) is not str or SHA.fullmatch(value) is None:
        raise BrokerError(f"invalid {label}")
    return value


def _absolute(value: Any, label: str) -> Path:
    path = Path(value) if isinstance(value, (Path, str)) else None
    if (path is None or not path.is_absolute() or path == Path("/")
            or any(part in (".", "..") for part in path.parts)):
        raise BrokerError(f"{label} must be absolute without dot components")
    for component in (*reversed(path.parents), path):
        if component.is_symlink():
            raise BrokerError(f"{label} contains a symlink")
    return path


def _private_dir(path: Path) -> None:
    path = _absolute(path, "private directory")
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise BrokerError("broker directory must be private 0700")


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _new_file(path: Path, raw: bytes) -> str:
    if len(raw) > MAX_MANIFEST_BYTES:
        raise BrokerError("broker file exceeds bound")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:])
            if written <= 0:
                raise OSError("broker file write made no progress")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_dir(path.parent)
    return _sha(raw)


def _publish_file(path: Path, raw: bytes, staging: Path) -> str:
    """Publish complete bytes without exposing a partial numbered journal."""
    temporary = staging / f".prepared-{secrets.token_hex(16)}"
    digest = _new_file(temporary, raw)
    os.link(temporary, path, follow_symlinks=False)
    _fsync_dir(path.parent)
    temporary.unlink()
    _fsync_dir(staging)
    return digest


def _identity(path: Path, *, directory: bool) -> list[int]:
    info = path.lstat()
    if ((directory and not stat.S_ISDIR(info.st_mode))
            or (not directory and not stat.S_ISREG(info.st_mode))
            or info.st_uid != os.geteuid()
            or (not directory and info.st_nlink != 1)):
        raise BrokerError("delegated path identity is invalid")
    return [info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)]


def _work(stage: Path) -> dict:
    inventory = _work_inventory(stage)
    if not inventory["complete"]:
        raise BrokerError("branch work inventory is incomplete")
    return _parse(_canonical(inventory), "work inventory", MAX_RECORD_BYTES)


def _executable(path: Path) -> tuple[bytes, dict]:
    identity = _identity(path, directory=False)
    if identity[-1] != 0o500:
        raise BrokerError("delegated executable must have mode 0500")
    raw = _read_bounded_file(path, "delegated executable", MAX_EXECUTABLE_BYTES)
    if not raw or _identity(path, directory=False) != identity:
        raise BrokerError("delegated executable changed during read")
    return raw, {"path": str(path), "sha256": _sha(raw), "bytes": len(raw),
                 "identity": identity}


def prepare_branch_manifest(root: Path, specifications: list[dict]) -> dict:
    """Freeze 2-4 existing stage roots and reviewed executable bytes once."""
    root = _absolute(root, "branch root")
    _private_dir(root)
    if type(specifications) is not list or not 2 <= len(specifications) <= 4:
        raise BrokerError("manifest requires two through four branches")
    branches = []
    seen_tasks: set[str] = set()
    seen_nodes: set[str] = set()
    seen_stages: list[Path] = []
    for spec in specifications:
        if type(spec) is not dict or set(spec) != {
            "task_id", "owned_node_ids", "stage_dir", "functions"
        }:
            raise BrokerError("branch specification fields are invalid")
        task_id = _identifier(spec["task_id"], "task ID")
        if task_id in seen_tasks:
            raise BrokerError("duplicate task ID")
        seen_tasks.add(task_id)
        stage = _absolute(spec["stage_dir"], "stage directory")
        if (not stage.is_relative_to(root) or stage == root
                or any(stage == other or stage.is_relative_to(other)
                       or other.is_relative_to(stage) for other in seen_stages)):
            raise BrokerError("branch stage is outside root or overlaps")
        seen_stages.append(stage)
        for directory in (stage, stage / "case", stage / "inputs", stage / "work"):
            _private_dir(directory)
        nodes = spec["owned_node_ids"]
        if type(nodes) is not list or not 1 <= len(nodes) <= 128:
            raise BrokerError("branch ownership must be nonempty")
        for node in nodes:
            _identifier(node, "owned node")
            if node in seen_nodes:
                raise BrokerError("branch ownership overlaps")
            seen_nodes.add(node)
        functions = spec["functions"]
        if type(functions) is not list or not 1 <= len(functions) <= 8:
            raise BrokerError("branch functions must be nonempty")
        frozen_functions = []
        names = set()
        for item in functions:
            if type(item) is not dict or set(item) != {"name", "executable", "profile"}:
                raise BrokerError("branch function fields are invalid")
            name = _identifier(item["name"], "function name")
            if name in names or item["profile"] not in PROFILES:
                raise BrokerError("function names repeat or profile is invalid")
            names.add(name)
            tool = _absolute(item["executable"], "executable")
            if tool.is_relative_to(stage):
                raise BrokerError("executable cannot be stored in a mutable stage")
            _, frozen = _executable(tool)
            frozen_functions.append({"name": name, "profile": item["profile"], **frozen})
        branches.append({"task_id": task_id, "owned_node_ids": list(nodes),
                         "stage_dir": str(stage),
                         "stage_identity": _identity(stage, directory=True),
                         "snapshot": _parse(_canonical(_immutable_snapshot(stage)),
                                            "stage snapshot", MAX_MANIFEST_BYTES),
                         "initial_work": _work(stage), "functions": frozen_functions})
    manifest = {"schema": 1, "classification": "development_parallel_tool_branches_unsealed",
                "root": str(root), "root_identity": _identity(root, directory=True),
                "branches": branches}
    path = root / MANIFEST_NAME
    raw = _canonical(manifest)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise BrokerError("branch manifest exceeds byte bound")
    return {"path": str(path), "sha256": _new_file(path, raw)}


class ParallelToolBroker:
    """A global tool journal for several private stages under one parent claim."""

    def __init__(self, run_dir: Path, binding: dict):
        self.run_dir = _absolute(run_dir, "run directory")
        _private_dir(self.run_dir)
        if type(binding) is not dict or set(binding) != {"path", "sha256"}:
            raise BrokerError("manifest binding requires path and sha256")
        self.path = _absolute(binding["path"], "manifest path")
        self.sha256 = _digest(binding["sha256"], "manifest digest")
        self.binding = {"path": str(self.path), "sha256": self.sha256}
        self.manifest = self._manifest()
        self.reservations = self.run_dir / "tool_reservations"
        self.receipts = self.run_dir / "tool_receipts"
        self.broker_dir = self.run_dir / "broker"
        for folder in (self.reservations, self.receipts, self.broker_dir):
            _private_dir(folder)
        self._lock_path = self.broker_dir / ".lock"
        try:
            _new_file(self._lock_path, b"")
        except FileExistsError:
            if _identity(self._lock_path, directory=False)[-1] != 0o600:
                raise BrokerError("broker lock changed")
        self._process_lock = threading.RLock()
        self._active: set[int] = set()
        self._unusable = False

    def _manifest(self) -> dict:
        raw = _read_bounded_file(self.path, "branch manifest", MAX_MANIFEST_BYTES)
        if _sha(raw) != self.sha256:
            raise BrokerError("branch manifest digest changed")
        manifest = _parse(raw, "branch manifest", MAX_MANIFEST_BYTES)
        if type(manifest) is not dict or _canonical(manifest) != raw:
            raise BrokerError("branch manifest is not canonical")
        if (set(manifest) != {"schema", "classification", "root", "root_identity", "branches"}
                or manifest["schema"] != 1
                or manifest["classification"] != "development_parallel_tool_branches_unsealed"):
            raise BrokerError("branch manifest shape changed")
        return manifest

    def journal_roots(self) -> list[Path]:
        return [self.path] + [Path(item["stage_dir"]) / "work"
                              for item in self.manifest["branches"]]

    def branch(self, task_id: str) -> dict:
        _identifier(task_id, "task ID")
        for item in self.manifest["branches"]:
            if item["task_id"] == task_id:
                return {"task_id": task_id, "stage_dir": item["stage_dir"],
                        "owned_node_ids": list(item["owned_node_ids"]),
                        "functions": [{"name": fn["name"], "executable": fn["path"],
                                       "profile": fn["profile"]}
                                      for fn in item["functions"]]}
        raise BrokerError("unknown branch task")

    def _state_claim(self) -> str:
        state = _read_json(self.run_dir / "run.json")
        plan_raw = _read_bounded_file(self.run_dir / "plan.json", "wave plan", MAX_RECORD_BYTES)
        plan = _parse(plan_raw, "wave plan", MAX_RECORD_BYTES)
        if (type(plan) is not dict or type(state.get("plan_sha256")) is not str
                or _sha(plan_raw) != state["plan_sha256"]
                or plan.get("run_id") != state.get("run_id")):
            raise BrokerError("parent plan or run identity changed")
        if plan.get("branch_manifest") != self.binding:
            raise BrokerError("parent plan does not bind this branch manifest")
        selected_owner = admission.owner("oneshot", self.run_dir, self.run_dir)
        descriptor = state.get("admission_descriptor")
        if type(descriptor) is not dict:
            raise BrokerError("parent admission descriptor is absent")
        expected = admission.claim_digest(state["plan_sha256"], state["run_id"],
                                          selected_owner, descriptor)
        if expected != state.get("claim_sha256"):
            raise BrokerError("parent claim digest changed")
        actual = admission.require_claim(
            state["plan_sha256"], state["run_id"], selected_owner, descriptor,
            override=descriptor["local_run_admission_root"],
        )
        if actual != expected:
            raise BrokerError("parent claim changed")
        return actual

    def _stage(self, item: dict) -> Path:
        stage = _absolute(item["stage_dir"], "branch stage")
        if _identity(stage, directory=True) != item["stage_identity"]:
            raise BrokerError("branch stage identity changed")
        if _parse(_canonical(_immutable_snapshot(stage)), "stage snapshot",
                  MAX_MANIFEST_BYTES) != item["snapshot"]:
            raise BrokerError("branch case, inputs, or stage manifest changed")
        for fn in item["functions"]:
            _, current = _executable(_absolute(fn["path"], "executable"))
            if current != {key: fn[key] for key in ("path", "sha256", "bytes", "identity")}:
                raise BrokerError("delegated executable changed")
        return stage

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with self._process_lock:
            fd = os.open(self._lock_path, os.O_RDWR | os.O_NOFOLLOW)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                    raise BrokerError("broker lock changed")
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def _guard(self, context: Any, guard: Callable[[], None]) -> str:
        context.require_active()
        guard()
        claimed = self._state_claim()
        context.require_active()
        return claimed

    def _records(self) -> tuple[list[tuple[int, dict, dict | None]], dict[str, dict]]:
        reservation_names = sorted(path.name for path in self.reservations.iterdir())
        receipt_names = sorted(path.name for path in self.receipts.iterdir())
        if any(re.fullmatch(r"[0-9]{4}\.json", name) is None
               for name in reservation_names + receipt_names):
            raise BrokerError("tool journal contains unexpected files")
        if not set(receipt_names) <= set(reservation_names):
            raise BrokerError("tool receipt has no reservation")
        expected_names = [f"{number:04d}.json"
                          for number in range(1, len(reservation_names) + 1)]
        if reservation_names != expected_names:
            raise BrokerError("global tool ordinals are not contiguous")
        branches = {item["task_id"]: item for item in self.manifest["branches"]}
        last_work = {task: item["initial_work"] for task, item in branches.items()}
        local_counts = dict.fromkeys(branches, 0)
        calls: set[str] = set()
        records: list[tuple[int, dict, dict | None]] = []
        pending_tasks: set[str] = set()
        for ordinal, name in enumerate(reservation_names, 1):
            reservation = _read_json(self.reservations / name)
            if (set(reservation) != {
                    "schema", "manifest_sha256", "claim_sha256", "task_id", "request_id",
                    "call_id", "function_name", "profile", "arguments", "arguments_sha256",
                    "global_ordinal", "local_ordinal", "work_before_sha256"}
                    or reservation["schema"] != 1
                    or reservation["manifest_sha256"] != self.sha256
                    or reservation["global_ordinal"] != ordinal):
                raise BrokerError("tool reservation is malformed")
            task = reservation["task_id"]
            if task not in branches or task in pending_tasks:
                raise BrokerError("tool reservation has unknown or pending branch")
            for field in ("request_id", "call_id", "function_name"):
                _identifier(reservation[field], field)
            if reservation["call_id"] in calls:
                raise BrokerError("function call ID was reserved twice")
            calls.add(reservation["call_id"])
            local_counts[task] += 1
            if (reservation["local_ordinal"] != local_counts[task]
                    or reservation["work_before_sha256"] != _sha(_canonical(last_work[task]))):
                raise BrokerError("branch work sequence changed")
            functions = {fn["name"]: fn for fn in branches[task]["functions"]}
            selected = functions.get(reservation["function_name"])
            if selected is None or reservation["profile"] != selected["profile"]:
                raise BrokerError("reservation function was not delegated")
            arguments = reservation["arguments"]
            if (type(arguments) is not str
                    or _sha(arguments.encode("utf-8")) != reservation["arguments_sha256"]
                    or _canonical(_parse(arguments, "reserved arguments",
                                         MAX_ARGUMENT_BYTES)).decode().strip() != arguments):
                raise BrokerError("reserved arguments changed")
            receipt = None
            if name in receipt_names:
                receipt = _read_json(self.receipts / name)
                if (set(receipt) != {
                    "schema", "reservation_sha256", "manifest_sha256", "claim_sha256",
                    "task_id", "request_id", "call_id", "function_name", "profile",
                    "global_ordinal", "local_ordinal", "stdout_sha256", "stderr_sha256",
                    "stdout_bytes", "stderr_bytes", "sandbox", "status", "output",
                    "output_json", "work_after", "work_after_sha256"}
                        or receipt["schema"] != 1
                        or receipt["reservation_sha256"] != _sha(_canonical(reservation))
                        or any(receipt[field] != reservation[field] for field in (
                            "manifest_sha256", "claim_sha256", "task_id", "request_id",
                            "call_id", "function_name", "profile", "global_ordinal",
                            "local_ordinal"))
                        or receipt["work_after_sha256"] != _sha(_canonical(receipt["work_after"]))):
                    raise BrokerError("tool receipt does not match its reservation")
                stream_dir = self.broker_dir / f"{ordinal:04d}"
                for stream in ("stdout", "stderr"):
                    raw = _read_bounded_file(stream_dir / stream,
                                             f"tool {stream}", MAX_STREAM_BYTES)
                    if (len(raw) != receipt[f"{stream}_bytes"]
                            or _sha(raw) != receipt[f"{stream}_sha256"]):
                        raise BrokerError("tool stream changed")
                sandbox = receipt["sandbox"]
                if (type(sandbox) is not dict
                        or set(sandbox) != {"exit_code", "timed_out", "launch_error",
                                            "landlock_abi", "duration_seconds",
                                            "sealed_executable_sha256", "host_elapsed_seconds"}
                        or sandbox["timed_out"] is not False
                        or sandbox["launch_error"] is not None
                        or sandbox["sealed_executable_sha256"] != selected["sha256"]):
                    raise BrokerError("tool terminal sandbox seal changed")
                stdout = _read_bounded_file(stream_dir / "stdout",
                                            "tool stdout", MAX_STREAM_BYTES)
                parsed = None
                if len(stdout) <= MAX_OUTPUT_BYTES:
                    try:
                        value = _parse(stdout, "tool stdout", MAX_OUTPUT_BYTES)
                    except BrokerError:
                        value = None
                    if type(value) is dict:
                        parsed = value
                expected_status = ("success" if sandbox["exit_code"] == 0
                                   else "tool_failure")
                if selected["profile"] == "analysis_readonly" and parsed is None:
                    expected_status = "invalid_json"
                output = (_canonical(parsed).decode().strip() if parsed is not None
                          else _canonical({"ok": False, "broker_status": expected_status,
                                           "stdout_sha256": _sha(stdout),
                                           "stdout_bytes": len(stdout)}).decode().strip())
                if (receipt["status"] != expected_status or receipt["output_json"] != parsed
                        or receipt["output"] != output):
                    raise BrokerError("tool feedback differs from raw stream")
                if (selected["profile"] == "analysis_readonly"
                        and receipt["work_after"] != last_work[task]):
                    raise BrokerError("readonly tool changed branch work")
                last_work[task] = receipt["work_after"]
            else:
                pending_tasks.add(task)
            records.append((ordinal, reservation, receipt))
        for task, item in branches.items():
            stage = self._stage(item)
            if task not in pending_tasks and _work(stage) != last_work[task]:
                raise BrokerError("branch work differs from last terminal receipt")
        return records, last_work

    def verify(self) -> dict:
        current = self._manifest()
        if current != self.manifest:
            raise BrokerError("branch manifest changed")
        root = _absolute(current["root"], "branch root")
        if _identity(root, directory=True) != current["root_identity"]:
            raise BrokerError("branch root identity changed")
        records, _ = self._records()
        pending = [ordinal for ordinal, _, receipt in records if receipt is None]
        return {"manifest_sha256": self.sha256, "reservations": len(records),
                "receipts": len(records) - len(pending), "pending": pending,
                "blocked": any(number not in self._active for number in pending)}

    def invoke(self, task_id: str, request_id: str, call: dict, context: Any,
               guard: Callable[[], None]) -> dict:
        """Reserve one global ordinal, run sealed bytes, and publish one receipt."""
        if self._unusable:
            raise BrokerError("broker already has an uncertain local effect")
        _identifier(task_id, "task ID")
        _identifier(request_id, "request ID")
        if type(call) is not dict or set(call) != {"name", "call_id", "arguments"}:
            raise BrokerError("function call fields are invalid")
        name = _identifier(call["name"], "function name")
        call_id = _identifier(call["call_id"], "call ID")
        if type(call["arguments"]) is not str:
            raise BrokerError("function arguments must be JSON text")
        arguments = _parse(call["arguments"], "function arguments", MAX_ARGUMENT_BYTES)
        if type(arguments) is not dict:
            raise BrokerError("function arguments must be a JSON object")
        canonical_arguments = _canonical(arguments).decode().strip()
        if len(canonical_arguments.encode("utf-8")) > MAX_ARGUMENT_BYTES:
            raise BrokerError("canonical function arguments exceed byte bound")
        if not callable(guard):
            raise BrokerError("effect guard is required")
        branch = next((item for item in self.manifest["branches"]
                       if item["task_id"] == task_id), None)
        if branch is None:
            raise BrokerError("unknown branch task")
        function = next((item for item in branch["functions"] if item["name"] == name), None)
        if function is None:
            raise BrokerError("function is not delegated to this branch")
        stage = Path(branch["stage_dir"])
        with self._locked():
            self._guard(context, guard)
            report = self.verify()
            if any(number not in self._active for number in report["pending"]):
                raise BrokerError("unreconciled tool reservation blocks new effects")
            records, _ = self._records()
            if any(record["task_id"] == task_id and receipt is None
                   for _, record, receipt in records):
                raise BrokerError("branch already has an active tool")
            status = context.status()
            if (status["state"] != "active"
                    or status["tools_reserved"] >= status["max_tool_calls"]
                    or report["reservations"] != status["tools_reserved"]):
                raise BrokerError("shared tool cap or count changed")
            if any(record["call_id"] == call_id for _, record, _ in records):
                raise BrokerError("function call ID was already reserved")
            ordinal = report["reservations"] + 1
            local = sum(record["task_id"] == task_id for _, record, _ in records) + 1
            work_before = _work(stage)
            claimed = self._guard(context, guard)
            reservation = {
                "schema": 1, "manifest_sha256": self.sha256, "claim_sha256": claimed,
                "task_id": task_id, "request_id": request_id, "call_id": call_id,
                "function_name": name, "profile": function["profile"],
                "arguments": canonical_arguments,
                "arguments_sha256": _sha(canonical_arguments.encode("utf-8")),
                "global_ordinal": ordinal, "local_ordinal": local,
                "work_before_sha256": _sha(_canonical(work_before)),
            }
            _publish_file(self.reservations / f"{ordinal:04d}.json",
                          _canonical(reservation), self.broker_dir)
            self._active.add(ordinal)
        try:
            self._guard(context, guard)
            stream_dir = self.broker_dir / f"{ordinal:04d}"
            stream_dir.mkdir(mode=0o700)
            _fsync_dir(self.broker_dir)
            tool_bytes, current_tool = _executable(Path(function["path"]))
            if current_tool != {key: function[key]
                                for key in ("path", "sha256", "bytes", "identity")}:
                raise BrokerError("delegated executable changed before launch")
            self._stage(branch)
            self._guard(context, guard)
            remaining = context.deadline - time.monotonic()
            if not math.isfinite(remaining) or remaining <= 0:
                raise BrokerError("shared active deadline expired before local launch")
            plan = _read_json(self.run_dir / "plan.json")
            wall = plan.get("tool_wall_seconds")
            if type(wall) not in (int, float) or not math.isfinite(wall) or wall <= 0:
                raise BrokerError("frozen plan lacks valid tool wall cap")
            timeout = min(float(wall), remaining)
            read_roots = [stage / "case", stage / "inputs"]
            write_roots = [stage / "work"]
            if function["profile"] == "analysis_readonly":
                read_roots.append(stage / "work")
                write_roots = []
            self._guard(context, guard)
            started = time.monotonic()
            result = run_sandboxed(
                argv=[function["path"], str(stage / "case"), str(stage / "inputs"),
                      str(stage / "work"), canonical_arguments],
                cwd=stage / "case", read_roots=read_roots, write_roots=write_roots,
                runtime_roots=default_python_runtime_roots(),
                stdout_path=stream_dir / "stdout", stderr_path=stream_dir / "stderr",
                timeout_seconds=timeout,
                cpu_seconds=max(1, min(60, math.ceil(timeout))),
                file_bytes_per_file=MAX_STREAM_BYTES,
                sealed_executable_bytes=tool_bytes,
                sealed_executable_sha256=function["sha256"],
            )
            elapsed = time.monotonic() - started
            self._guard(context, guard)
            stdout = _read_bounded_file(stream_dir / "stdout", "tool stdout",
                                        MAX_STREAM_BYTES)
            stderr = _read_bounded_file(stream_dir / "stderr", "tool stderr",
                                        MAX_STREAM_BYTES)
            work_after = _work(stage)
            self._stage(branch)
            if function["profile"] == "analysis_readonly" and work_after != work_before:
                raise BrokerError("readonly analysis mutated branch work")
            if (result.sealed_executable_sha256 != function["sha256"]
                    or result.launch_error is not None or result.timed_out):
                raise BrokerError("local tool launch, seal, or deadline is uncertain")
            parsed_output = None
            if len(stdout) <= MAX_OUTPUT_BYTES:
                try:
                    candidate = _parse(stdout, "tool stdout", MAX_OUTPUT_BYTES)
                except BrokerError:
                    candidate = None
                if type(candidate) is dict:
                    parsed_output = candidate
            status_name = "success" if result.exit_code == 0 else "tool_failure"
            if function["profile"] == "analysis_readonly" and parsed_output is None:
                status_name = "invalid_json"
            output = (_canonical(parsed_output).decode().strip()
                      if parsed_output is not None else
                      _canonical({"ok": False, "broker_status": status_name,
                                  "stdout_sha256": _sha(stdout),
                                  "stdout_bytes": len(stdout)}).decode().strip())
            receipt = {
                "schema": 1, "reservation_sha256": _sha(_canonical(reservation)),
                "manifest_sha256": self.sha256, "claim_sha256": claimed,
                "task_id": task_id, "request_id": request_id, "call_id": call_id,
                "function_name": name, "profile": function["profile"],
                "global_ordinal": ordinal, "local_ordinal": local,
                "stdout_sha256": _sha(stdout), "stderr_sha256": _sha(stderr),
                "stdout_bytes": len(stdout), "stderr_bytes": len(stderr),
                "sandbox": {
                    "exit_code": result.exit_code, "timed_out": result.timed_out,
                    "launch_error": result.launch_error,
                    "landlock_abi": result.landlock_abi,
                    "duration_seconds": result.duration_seconds,
                    "sealed_executable_sha256": result.sealed_executable_sha256,
                    "host_elapsed_seconds": elapsed,
                },
                "status": status_name, "output": output,
                "output_json": parsed_output, "work_after": work_after,
                "work_after_sha256": _sha(_canonical(work_after)),
            }
            self._guard(context, guard)
            _publish_file(self.receipts / f"{ordinal:04d}.json",
                          _canonical(receipt), self.broker_dir)
            self._guard(context, guard)
            return {"type": "function_call_output", "call_id": call_id,
                    "output": output}
        except BaseException:
            self._unusable = True
            raise
        finally:
            with self._process_lock:
                self._active.discard(ordinal)

    def operations(self) -> list[dict]:
        report = self.verify()
        if report["blocked"]:
            raise BrokerError("unreconciled tool reservation blocks replay")
        operations = []
        for ordinal, reservation, receipt in self._records()[0]:
            assert receipt is not None
            outer = _parse(reservation["arguments"], "outer function arguments",
                           MAX_ARGUMENT_BYTES)
            request = None
            if type(outer) is dict and type(outer.get("request")) is str:
                request = _parse(outer["request"], "method request", MAX_ARGUMENT_BYTES)
            operations.append({
                "task_id": reservation["task_id"],
                "request_id": reservation["request_id"],
                "call_id": reservation["call_id"],
                "global_ordinal": ordinal,
                "local_ordinal": reservation["local_ordinal"],
                "function_name": reservation["function_name"],
                "profile": reservation["profile"],
                "outer_arguments": outer, "request": request,
                "terminal": receipt, "output_json": receipt["output_json"],
                "result": {"type": "function_call_output",
                           "call_id": reservation["call_id"],
                           "output": receipt["output"]},
            })
        return operations
