"""Persistent mode-aware public prototype tools under one coordinated parent.

The original core and D113 launcher are sealed unchanged. Host activation/merge
events join one flat tool journal; an uncertain local effect never auto-retries.
This reviewed same-UID development harness does not authenticate people/models.
"""

from __future__ import annotations

import ast
import base64
import math
import os
from pathlib import Path
import sys
import threading
import time

import coordinated_prototype_kernel as kernel
import development_analysis_tool as analyzer
import development_method_tool as method
import parallel_analysis_broker as analysis
import parallel_tool_broker as primitive
from local_replay_sandbox import default_python_runtime_roots, run_sandboxed
from run_staged_local_tool import _immutable_snapshot
from staged_tool_session import _analysis_output, _analysis_source, _publish_analysis_metrics
from tool_policy import _read_bounded_file

BrokerError = primitive.BrokerError
_canonical, _sha, _read_json = primitive._canonical, primitive._sha, primitive._read_json
_new_file, _fsync_dir = primitive._new_file, primitive._fsync_dir
_parse, _work = primitive._parse, primitive._work
ROLES = ("leader", "worker-1", "worker-2")
METHOD_OPS = {"init", "status", "revise", "review", "advance", "plan", "read", "write", "replace"}
CORE_OPS = {"status", "revise", "review", "advance", "plan"}
OWNED_FILES = {"worker-1": ["analysis.py"], "worker-2": ["report.md", "sources.json"]}
FUNCTIONS = {"development_method": "workspace", "development_analysis": "analysis_readonly"}
MAX_STREAM = 256 * 1024
MAX_RECORD = 4 * 1024 * 1024
RESERVATION_FIELDS = {"schema", "manifest_sha256", "claim_sha256", "task_id", "request_id",
    "call_id", "function_name", "profile", "arguments", "arguments_sha256", "global_ordinal",
    "local_ordinal", "epoch", "work_before", "work_before_sha256"}
RECEIPT_FIELDS = {"schema", "reservation_sha256", "manifest_sha256", "claim_sha256", "task_id",
    "request_id", "call_id", "function_name", "profile", "global_ordinal", "local_ordinal", "epoch",
    "stdout_sha256", "stderr_sha256", "stdout_bytes", "stderr_bytes", "sandbox", "status",
    "method_state_raw", "output", "output_json", "work_after", "work_after_sha256"}
ANALYSIS_FIELDS = {"analysis_script_sha256", "analysis_metrics_sha256", "analysis_status",
                   "analysis_diagnostic", "analysis_work_after_child"}
_ast_names = {}
_ast_lock = threading.RLock()


def _raw(path: Path, cap=primitive.MAX_MANIFEST_BYTES) -> bytes:
    return _read_bounded_file(path, "coordinated broker evidence", cap)


def _sources() -> dict:
    scripts = Path(__file__).resolve().parent
    todo, seen, result = [Path(__file__).stem], set(), {}
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        raw = _raw(scripts / (name + ".py"))
        digest = _sha(raw)
        with _ast_lock:
            names = _ast_names.get(digest)
            if names is None:
                names = []
                for node in ast.walk(ast.parse(raw)):
                    if isinstance(node, ast.Import):
                        names.extend(item.name.split(".")[0] for item in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        names.append(node.module.split(".")[0])
                _ast_names[digest] = names
        # Recheck candidate existence every time; the cache retains only AST names.
        todo.extend(item for item in names if (scripts / (item + ".py")).is_file())
        result[str(scripts / (name + ".py"))] = digest
    result[str(method.DEFAULT_CORE)] = _sha(_raw(method.DEFAULT_CORE))
    if any(_sha(_raw(Path(path))) != digest for path, digest in result.items()):
        raise BrokerError("broker source closure changed during capture")
    return dict(sorted(result.items()))


def _directory(path: Path):
    path.mkdir(mode=0o700)
    primitive._private_dir(path)


def _copy_flat(source: Path, destination: Path):
    rows = []
    for path in sorted(source.iterdir()):
        primitive._absolute(path, "public input")
        if not path.is_file() or path.is_symlink():
            raise BrokerError("public case/inputs must be flat regular files")
        raw = _raw(path)
        _new_file(destination / path.name, raw)
        rows.append({"path": path.name, "bytes": len(raw), "sha256": _sha(raw)})
    if not rows:
        raise BrokerError("public source directory is empty")
    return rows


def _method_bytes() -> bytes:
    core = _raw(method.DEFAULT_CORE, method.MAX_CORE_BYTES)
    return (f"#!{sys.executable}\n" + method._RUNTIME.replace(
        "__EMBEDDED_CORE_B64__", base64.b64encode(core).decode()).replace(
        "__EMBEDDED_CORE_SHA256__", _sha(core))).encode()


def prepare_broker(run_dir: Path, case_dir: Path, inputs_dir: Path, *, mode: str) -> dict:
    run_dir = primitive._absolute(run_dir, "run")
    primitive._private_dir(run_dir)
    case_dir = primitive._absolute(case_dir, "case")
    inputs_dir = primitive._absolute(inputs_dir, "inputs")
    if mode not in kernel.MODES:
        raise BrokerError("unknown original prototype mode")
    for source in (case_dir, inputs_dir):
        if (source == run_dir or source in run_dir.parents or run_dir in source.parents):
            raise BrokerError("run and public sources must not overlap")
    case = _parse(_raw(case_dir / "case.json"), "case", 1024 * 1024)
    prompt = _parse(_raw(inputs_dir / "arm_prompt"), "arm prompt", 64 * 1024)
    policy = _parse(_raw(inputs_dir / "tool_policy"), "tool policy", 128 * 1024)
    if (type(case) is not dict or type(case.get("case_id")) is not str
            or type(prompt) is not dict or set(prompt) != {"alternative", "mode", "instructions"}
            or prompt["mode"] != mode or method_map().get(prompt["alternative"]) != mode
            or type(prompt["instructions"]) is not str or not prompt["instructions"].strip()
            or type(policy) is not dict or type(policy.get("schema")) is not int or policy["schema"] != 2):
        raise BrokerError("case, selected mode, or CAS tool policy is invalid")
    # Validate/read every public byte before creating stages.
    before = {}
    for folder in (case_dir, inputs_dir):
        before[str(folder)] = {item.name: _raw(primitive._absolute(item, "public input"))
                               for item in sorted(folder.iterdir())}
    listed = case.get("files")
    if type(listed) is not list or not 1 <= len(listed) <= 64:
        raise BrokerError("case manifest must enumerate bounded original public files")
    names = set()
    for row in listed:
        if (type(row) is not dict or set(row) != {"path", "bytes", "sha256"}
                or type(row["path"]) is not str or Path(row["path"]).name != row["path"]
                or row["path"] in {".", "..", "case.json"} or row["path"] in names
                or type(row["bytes"]) is not int or row["bytes"] < 0):
            raise BrokerError("case public inventory record is malformed")
        names.add(row["path"])
        actual = before[str(case_dir)].get(row["path"])
        if actual is None or len(actual) != row["bytes"] or _sha(actual) != row["sha256"]:
            raise BrokerError("public source differs from case manifest")
    if set(before[str(case_dir)]) != names | {"case.json"}:
        raise BrokerError("case contains unlisted public bytes")
    sources = _sources()
    root, tools = run_dir / "broker_stages", run_dir / "broker_tools"
    if root.exists() or tools.exists():
        raise BrokerError("broker stages/tools must be new")
    _directory(root)
    _directory(root / "metadata")
    _directory(root / "epochs")
    _directory(tools)
    method.build_tool(tools / "method")
    analyzer.build_analysis_tool(tools / "analyzer")
    functions = []
    for name, path in (("development_method", tools / "method"), ("development_analysis", tools / "analyzer")):
        raw, frozen = primitive._executable(path)
        expected = _method_bytes() if name == "development_method" else analysis._launcher_bytes()
        if raw != expected:
            raise BrokerError("generated tool differs from the exact original launcher")
        functions.append({"name": name, "profile": FUNCTIONS[name], **frozen})
    stages = {}
    for role in ROLES:
        stage = root / role
        _directory(stage)
        for name in ("case", "inputs", "work"):
            _directory(stage / name)
        _copy_flat(case_dir, stage / "case")
        _copy_flat(inputs_dir, stage / "inputs")
        _new_file(stage / "stage.json", _canonical({"task_id": role, "mode": mode}))
        stages[role] = {"stage_dir": str(stage), "identity": primitive._identity(stage, directory=True),
                        "snapshot": _parse(_canonical(_immutable_snapshot(stage)), "stage", primitive.MAX_MANIFEST_BYTES),
                        "initial_work": _work(stage)}
    if sources != _sources() or any(
            {item.name: _raw(item) for item in sorted(Path(folder).iterdir())} != rows
            for folder, rows in before.items()):
        raise BrokerError("public inputs/source closure changed during preparation")
    manifest = {"schema": 1, "classification": "coordinated_prototype_broker_unsealed",
                "mode": mode, "case_id": case["case_id"], "root": str(root),
                "root_identity": primitive._identity(root, directory=True), "stages": stages,
                "functions": functions, "source_digests": sources}
    path = root / "metadata/manifest.json"
    return {"path": str(path), "sha256": _new_file(path, _canonical(manifest))}


def method_map():
    return {"A": "sequential", "B": "graph", "C": "risk"}


def _nonmetrics(work: dict):
    return {"directories": work["directories"],
            "files": [row for row in work["files"] if row["path"] != "metrics.json"]}


def _file(work, name):
    return next((row for row in work["files"] if row["path"] == name), None)


def _state_raw(stage: Path):
    path = stage / "work/method_state.json"
    return _raw(path, kernel.MAX_STATE_BYTES) if path.exists() else None


def _replace_host(path: Path, raw: bytes | None):
    if raw is None:
        if path.exists():
            _raw(path)
            path.unlink()
            _fsync_dir(path.parent)
        return
    temporary = path.parent / (".host-" + path.name)
    _new_file(temporary, raw)
    os.replace(temporary, path)
    _fsync_dir(path.parent)


class CoordinatedPrototypeBroker:
    def __init__(self, run_dir: Path, binding: dict):
        self.run_dir = primitive._absolute(run_dir, "run")
        primitive._private_dir(self.run_dir)
        if type(binding) is not dict or set(binding) != {"path", "sha256"}:
            raise BrokerError("broker binding needs path and sha256")
        self.binding = {"path": str(primitive._absolute(binding["path"], "manifest")),
                        "sha256": primitive._digest(binding["sha256"], "manifest digest")}
        self.path, self.sha256 = Path(self.binding["path"]), self.binding["sha256"]
        self.manifest = self._manifest()
        self.root = Path(self.manifest["root"])
        self.broker_dir = self.run_dir / "broker"
        self.reservations, self.receipts = self.run_dir / "tool_reservations", self.run_dir / "tool_receipts"
        for folder in (self.broker_dir, self.reservations, self.receipts):
            if not folder.exists():
                _directory(folder)
            primitive._private_dir(folder)
        self._lock_path = self.broker_dir / ".lock"
        if not self._lock_path.exists():
            _new_file(self._lock_path, b"")
        self._process_lock, self._active = threading.RLock(), set()
        self._unusable, self._host_active = False, False

    _locked = primitive.ParallelToolBroker._locked

    def _manifest(self):
        raw = _raw(self.path)
        value = _parse(raw, "broker manifest", primitive.MAX_MANIFEST_BYTES)
        if (_sha(raw) != self.sha256 or type(value) is not dict or _canonical(value) != raw
                or set(value) != {"schema", "classification", "mode", "case_id", "root",
                                 "root_identity", "stages", "functions", "source_digests"}
                or type(value["schema"]) is not int or value["schema"] != 1
                or value["classification"] != "coordinated_prototype_broker_unsealed"
                or value["mode"] not in kernel.MODES or set(value["stages"]) != set(ROLES)
                or value["source_digests"] != _sources()):
            raise BrokerError("broker manifest/source binding changed")
        root = primitive._absolute(value["root"], "stages root")
        if (root != self.run_dir / "broker_stages" or self.path != root / "metadata/manifest.json"
                or primitive._identity(root, directory=True) != value["root_identity"]):
            raise BrokerError("broker root identity changed")
        for role, item in value["stages"].items():
            stage = primitive._absolute(item["stage_dir"], "stage")
            if stage != root / role or primitive._identity(stage, directory=True) != item["identity"]:
                raise BrokerError("role stage identity changed")
            if _parse(_canonical(_immutable_snapshot(stage)), "stage snapshot",
                      primitive.MAX_MANIFEST_BYTES) != item["snapshot"]:
                raise BrokerError("public case/inputs or stage binding changed")
        for function in value["functions"]:
            raw, current = primitive._executable(Path(function["path"]))
            if (current != {key: function[key] for key in ("path", "sha256", "bytes", "identity")}
                    or FUNCTIONS.get(function["name"]) != function["profile"]
                    or raw != (_method_bytes() if function["profile"] == "workspace" else analysis._launcher_bytes())):
                raise BrokerError("original sealed executable changed")
        if {row["name"] for row in value["functions"]} != set(FUNCTIONS):
            raise BrokerError("delegated function inventory changed")
        return value

    def journal_roots(self):
        return [self.root]

    def leader_stage(self):
        return Path(self.manifest["stages"]["leader"]["stage_dir"])

    def _plan_state(self):
        state = _read_json(self.run_dir / "run.json", primitive.MAX_PLAN_BYTES)
        raw = _raw(self.run_dir / "plan.json", primitive.MAX_PLAN_BYTES)
        plan = _parse(raw, "parent plan", primitive.MAX_PLAN_BYTES)
        if (_sha(raw) != state.get("plan_sha256") or plan.get("run_id") != state.get("run_id")
                or plan.get("broker_manifest") != self.binding):
            raise BrokerError("parent plan, run identity, or broker binding changed")
        schedule_sha = primitive._digest(plan["schedule"]["schedule_sha256"], "schedule digest")
        if plan["descriptor"]["schedule_sha256"] != schedule_sha:
            raise BrokerError("runtime descriptor schedule binding changed")
        descriptor = state["admission_descriptor"]
        owner = primitive.admission.owner("oneshot", self.run_dir, self.run_dir)
        expected = primitive.admission.claim_digest(schedule_sha, state["run_id"], owner, descriptor)
        if state.get("claim_sha256") != expected:
            raise BrokerError("schedule/run claim digest changed")
        return plan, state

    def _state_claim(self):
        plan, state = self._plan_state()
        descriptor = state["admission_descriptor"]
        claimed = primitive.admission.require_claim(plan["schedule"]["schedule_sha256"], state["run_id"],
            primitive.admission.owner("oneshot", self.run_dir, self.run_dir), descriptor,
            override=descriptor["local_run_admission_root"])
        if claimed != state["claim_sha256"]:
            raise BrokerError("current parent claim changed")
        return claimed

    def _guard(self, context, guard):
        if context is not None:
            context.require_active()
        guard()
        claimed = self._state_claim()
        if context is not None:
            context.require_active()
        return claimed

    def _events(self):
        metadata = self.root / "metadata"
        names = sorted(path.name for path in metadata.iterdir())
        allowed = {"manifest.json", ".intent.json"}
        numbered = [name for name in names if name not in allowed]
        if numbered != [f"{number:04d}.json" for number in range(1, len(numbered) + 1)]:
            raise BrokerError("host epoch metadata sequence changed")
        if ".intent.json" in names and not self._host_active:
            raise BrokerError("uncertain host transition blocks replay")
        return [_read_json(metadata / name, MAX_RECORD) for name in numbered]

    def branch(self, task_id):
        primitive._identifier(task_id, "task ID")
        if task_id not in ROLES:
            raise BrokerError("reviewer/unknown role has no tools")
        events = self._events()
        activation = next((row for row in reversed(events) if row["kind"] == "activate"), None)
        if task_id != "leader" and (activation is None or events[-1]["kind"] != "activate"
                                   or task_id not in {row["task_id"] for row in activation["assignments"]}):
            raise BrokerError("worker is outside its active epoch")
        assignment = next((row for row in activation["assignments"] if row["task_id"] == task_id), None) if task_id != "leader" else None
        return {"task_id": task_id, "stage_dir": self.manifest["stages"][task_id]["stage_dir"],
                "owned_node_ids": assignment["owned_node_ids"] if assignment else [],
                "owned_files": assignment["owned_files"] if assignment else [],
                "functions": [{"name": row["name"], "executable": row["path"], "profile": row["profile"]}
                              for row in self.manifest["functions"]]}

    def _request(self, role, arguments, assignment=None):
        if type(arguments) is not dict or set(arguments) != {"request"} or type(arguments["request"]) is not str:
            raise BrokerError("method call requires the original request JSON string")
        request = _parse(arguments["request"], "method request", primitive.MAX_ARGUMENT_BYTES)
        if type(request) is not dict or request.get("op") not in METHOD_OPS:
            raise BrokerError("method operation is outside original permissions")
        op = request["op"]
        if role != "leader":
            if op in {"init", "advance"}:
                raise BrokerError("worker cannot init or advance")
            if op in {"revise", "review"} and request.get("id") not in assignment["owned_node_ids"]:
                raise BrokerError("worker node ownership mismatch")
            if op in {"write", "replace"} and request.get("path") not in assignment["owned_files"]:
                raise BrokerError("worker file ownership mismatch")
        return request

    def _records(self):
        events = self._events()
        names = sorted(path.name for path in self.reservations.iterdir())
        receipts = {path.name for path in self.receipts.iterdir()}
        if (names != [f"{number:04d}.json" for number in range(1, len(names) + 1)]
                or not receipts <= set(names)):
            raise BrokerError("global tool stream is not contiguous")
        allowed_streams = {".lock"} | {f"{number:04d}" for number in range(1, len(names) + 1)}
        if {path.name for path in self.broker_dir.iterdir()} - allowed_streams:
            raise BrokerError("uncertain or unexpected broker stream/staging artifact")
        work = {role: value["initial_work"] for role, value in self.manifest["stages"].items()}
        states = dict.fromkeys(ROLES)
        counts, seen, records, pending = dict.fromkeys(ROLES, 0), set(), [], set()
        current, event_index = None, 0
        for ordinal in range(len(names) + 1):
            while event_index < len(events) and events[event_index]["after_tool_ordinal"] == ordinal:
                event = events[event_index]
                fields = {"schema", "seq", "kind", "epoch", "manifest_sha256", "after_tool_ordinal",
                          "assignments", "before", "after"} | ({"base_path", "base_sha256"}
                          if event.get("kind") == "activate" else {"state_path", "method_state_sha256"})
                if (set(event) != fields or type(event["schema"]) is not int or event["schema"] != 1
                        or any(type(event[key]) is not int for key in ("seq", "epoch", "after_tool_ordinal"))
                        or event["seq"] != event_index + 1 or event["epoch"] != event_index // 2 + 1
                        or event["kind"] != ("activate" if event_index % 2 == 0 else "merge")
                        or event["manifest_sha256"] != self.sha256):
                    raise BrokerError("epoch lifecycle metadata changed")
                expected_path = f"epochs/{event['epoch']:04d}/" + (
                    "base_state.json" if event["kind"] == "activate" else "merged_state.json")
                if event.get("base_path", event.get("state_path")) != expected_path:
                    raise BrokerError("host event source path is outside its fixed epoch slot")
                for role, before in event["before"].items():
                    if before != work[role]:
                        raise BrokerError("host transition before snapshot changed")
                if event["kind"] == "activate":
                    if current is not None or states["leader"] is None:
                        raise BrokerError("epoch activated without an initialized merged leader")
                    base = _raw(self.root / event["base_path"], kernel.MAX_STATE_BYTES)
                    if base != states["leader"] or _sha(base) != event["base_sha256"]:
                        raise BrokerError("epoch base state differs from the real leader")
                    self._assignments(event["assignments"], kernel.parse_state(base, mode=self.manifest["mode"]))
                    for item in event["assignments"]:
                        role = item["task_id"]
                        expected = [row for row in work["leader"]["files"] if row["path"] != "metrics.json"]
                        if [(row["path"], row["bytes"], row["sha256"]) for row in event["after"][role]["files"]] != [
                                (row["path"], row["bytes"], row["sha256"]) for row in expected]:
                            raise BrokerError("worker activation has extra/missing/private source bytes")
                        work[role] = event["after"][role]
                        states[role] = base
                    current = event
                else:
                    if current is None or event["epoch"] != current["epoch"]:
                        raise BrokerError("merge has no active epoch")
                    base = _raw(self.root / current["base_path"], kernel.MAX_STATE_BYTES)
                    branches = []
                    for item in current["assignments"]:
                        role = item["task_id"]
                        operations = self._kernel_ops(records, role, current["epoch"])
                        branches.append({"task_id": role, "owned_node_ids": item["owned_node_ids"],
                                         "state_raw": states[role], "operations": operations})
                    merged = kernel.merge_operations(base, branches, mode=self.manifest["mode"])
                    saved = _raw(self.root / event["state_path"], kernel.MAX_STATE_BYTES)
                    if saved != merged or event["method_state_sha256"] != _sha(merged):
                        raise BrokerError("host merged state differs from actual kernel replay")
                    expected = {row["path"]: (row["bytes"], row["sha256"]) for row in work["leader"]["files"]
                                if row["path"] != "metrics.json"}
                    expected["method_state.json"] = (len(merged), _sha(merged))
                    for item in current["assignments"]:
                        for row in work[item["task_id"]]["files"]:
                            if row["path"] in item["owned_files"]:
                                expected[row["path"]] = (row["bytes"], row["sha256"])
                    if {row["path"]: (row["bytes"], row["sha256"]) for row in event["after"]["leader"]["files"]} != expected:
                        raise BrokerError("host merge overwrote unowned files or retained branch metrics")
                    work["leader"], states["leader"], current = event["after"]["leader"], merged, None
                event_index += 1
            if ordinal == len(names):
                break
            number, name = ordinal + 1, names[ordinal]
            reserved = _read_json(self.reservations / name)
            readonly = reserved.get("profile") == "analysis_readonly"
            if (set(reserved) != RESERVATION_FIELDS | ({"analysis_script_sha256", "old_metrics_sha256"} if readonly else set())
                    or type(reserved["schema"]) is not int or reserved["schema"] != 1
                    or any(type(reserved[key]) is not int for key in ("global_ordinal", "local_ordinal", "epoch"))):
                raise BrokerError("tool reservation schema changed")
            role = reserved["task_id"]
            epoch = current["epoch"] if role != "leader" and current is not None else 0
            if (role not in ROLES or (role == "leader" and current is not None)
                    or (role != "leader" and current is None)
                    or reserved["global_ordinal"] != number or reserved["epoch"] != epoch
                    or reserved["manifest_sha256"] != self.sha256 or role in pending):
                raise BrokerError("tool reservation role/epoch/binding changed")
            counts[role] += 1
            if (reserved["local_ordinal"] != counts[role] or reserved["call_id"] in seen
                    or reserved["work_before"] != work[role]
                    or reserved["work_before_sha256"] != _sha(_canonical(work[role]))
                    or not reserved["request_id"].startswith(role + "-turn-")):
                raise BrokerError("tool IDs, counters, or prior work changed")
            seen.add(reserved["call_id"])
            args = _parse(reserved["arguments"], "reserved arguments", primitive.MAX_ARGUMENT_BYTES)
            if (_canonical(args).decode().strip() != reserved["arguments"]
                    or _sha(reserved["arguments"].encode()) != reserved["arguments_sha256"]):
                raise BrokerError("reserved arguments changed")
            assignment = next((row for row in current["assignments"] if row["task_id"] == role), None) if current and role != "leader" else None
            if role != "leader" and assignment is None:
                raise BrokerError("worker was not assigned to epoch")
            function = next((row for row in self.manifest["functions"] if row["name"] == reserved["function_name"]), None)
            if function is None or function["profile"] != reserved["profile"]:
                raise BrokerError("tool delegation changed")
            request = self._request(role, args, assignment) if function["profile"] == "workspace" else None
            terminal = None
            if name in receipts:
                terminal = _read_json(self.receipts / name, MAX_RECORD)
                if (set(terminal) != RECEIPT_FIELDS | (ANALYSIS_FIELDS if readonly else set())
                        or type(terminal["schema"]) is not int or terminal["schema"] != 1
                        or terminal["reservation_sha256"] != _sha(_canonical(reserved))
                        or terminal["work_after_sha256"] != _sha(_canonical(terminal["work_after"]))
                        or any(terminal[key] != reserved[key] for key in (
                            "manifest_sha256", "claim_sha256", "task_id", "request_id", "call_id",
                            "global_ordinal", "local_ordinal", "epoch", "function_name", "profile"))):
                    raise BrokerError("tool receipt binding changed")
                streams = {key: _raw(self.broker_dir / f"{number:04d}" / key, MAX_STREAM) for key in ("stdout", "stderr")}
                if any(terminal[key + "_sha256"] != _sha(body) or terminal[key + "_bytes"] != len(body)
                       for key, body in streams.items()):
                    raise BrokerError("tool raw streams changed")
                sandbox = terminal["sandbox"]
                if (sandbox["timed_out"] is not False or sandbox["launch_error"] is not None
                        or type(sandbox["exit_code"]) is not int or sandbox["exit_code"] < 0
                        or sandbox["sealed_executable_sha256"] != function["sha256"]):
                    raise BrokerError("tool terminal seal or deadline is uncertain")
                if function["profile"] == "analysis_readonly":
                    status, diagnostic, _, _, parsed = _analysis_output(
                        self.broker_dir / f"{number:04d}/stdout", sandbox["exit_code"], MAX_STREAM)
                    if (terminal["analysis_status"] != status or terminal["analysis_diagnostic"] != diagnostic
                            or terminal["output_json"] != parsed or terminal["output"] != analysis._feedback(status, diagnostic, streams["stdout"], parsed)
                            or terminal["analysis_work_after_child"] != work[role]
                            or reserved["analysis_script_sha256"] != args.get("script_sha256")
                            or (_file(work[role], "analysis.py") or {}).get("sha256") != args.get("script_sha256")):
                        raise BrokerError("readonly analysis feedback/provenance changed")
                    analysis._metrics_transition(work[role], terminal["work_after"], parsed)
                    if terminal["analysis_metrics_sha256"] != (_sha(_canonical(parsed)) if parsed is not None else None):
                        raise BrokerError("analysis host metrics digest changed")
                else:
                    parsed = None
                    try:
                        candidate = _parse(streams["stdout"], "tool stdout", primitive.MAX_OUTPUT_BYTES)
                        if type(candidate) is dict:
                            parsed = candidate
                    except BrokerError:
                        pass
                    output = _canonical(parsed).decode().strip() if parsed is not None else analysis._feedback(
                        "tool_failure", "original method tool failed", streams["stdout"], None)
                    if terminal["output_json"] != parsed or terminal["output"] != output:
                        raise BrokerError("method feedback differs from raw stdout")
                    if parsed is not None and (parsed.get("operation") != request["op"]
                            or parsed.get("mode") != self.manifest["mode"]
                            or parsed.get("case_id") != self.manifest["case_id"]
                            or parsed.get("embedded_core_sha256") != _sha(_raw(method.DEFAULT_CORE))):
                        raise BrokerError("original method result headers differ from its request/source")
                    after_raw = terminal["method_state_raw"]
                    after_raw = after_raw.encode() if after_raw is not None else None
                    success = parsed is not None and parsed.get("ok") is True
                    if request["op"] == "init" and success:
                        if states[role] is not None or role != "leader":
                            raise BrokerError("prototype init repeated or not by leader")
                        kernel.validate_initialization({"case_id": self.manifest["case_id"], "nodes": request["nodes"]},
                            after_raw, mode=self.manifest["mode"], case_id=self.manifest["case_id"],
                            proposal_path=Path(self.manifest["stages"][role]["stage_dir"]) / "work/proposal.json")
                    elif request["op"] in CORE_OPS and states[role] is not None:
                        expected = kernel.apply_operations(states[role], [{
                            "global_ordinal": number, "role": role, "arguments": request, "success": success}],
                            mode=self.manifest["mode"])
                        if expected != after_raw:
                            raise BrokerError("method state differs from original operation replay")
                    elif after_raw != states[role]:
                        raise BrokerError("file/read/failing operation changed method state")
                    states[role] = after_raw
                state_file = _file(terminal["work_after"], "method_state.json")
                if state_file is not None and states[role] is not None and state_file["sha256"] != _sha(states[role]):
                    raise BrokerError("recorded graph inventory differs from replay")
                work[role] = terminal["work_after"]
            else:
                pending.add(role)
            records.append((number, reserved, terminal))
        if event_index != len(events):
            raise BrokerError("host epoch event lies beyond the tool stream")
        for role, item in self.manifest["stages"].items():
            if role not in pending and not self._host_active and _work(Path(item["stage_dir"])) != work[role]:
                raise BrokerError("current role work differs from tool/host replay")
        return records, work, states, current

    @staticmethod
    def _kernel_ops(records, role, epoch):
        result = []
        for number, reserved, terminal in records:
            if reserved["task_id"] != role or reserved["epoch"] != epoch or reserved["profile"] != "workspace":
                continue
            args = _parse(reserved["arguments"], "arguments", primitive.MAX_ARGUMENT_BYTES)
            request = _parse(args["request"], "request", primitive.MAX_ARGUMENT_BYTES)
            if request["op"] in CORE_OPS:
                result.append({"global_ordinal": number, "role": role, "arguments": request,
                               "success": terminal is not None and terminal["output_json"] is not None
                               and terminal["output_json"].get("ok") is True})
        return result

    def verify(self):
        if self._manifest() != self.manifest:
            raise BrokerError("broker manifest changed")
        records, _, _, current = self._records()
        _, state = self._plan_state()
        if records or self._events():
            self._state_claim()
        if any(row["claim_sha256"] != state["claim_sha256"] for _, row, _ in records):
            raise BrokerError("tool stream claim changed")
        pending = [number for number, _, terminal in records if terminal is None]
        return {"manifest_sha256": self.sha256, "reservations": len(records),
                "receipts": len(records) - len(pending), "pending": pending,
                "blocked": any(number not in self._active for number in pending),
                "pending_host": self._host_active, "active_epoch": current["epoch"] if current else None}

    def invoke(self, task_id, request_id, call, context, guard):
        if self._unusable:
            raise BrokerError("broker has an uncertain local effect")
        primitive._identifier(request_id, "request ID")
        if (type(call) is not dict or set(call) != {"name", "call_id", "arguments"}
                or not request_id.startswith(task_id + "-turn-") or not callable(guard)):
            raise BrokerError("tool call identity/fields/guard are invalid")
        branch = self.branch(task_id)
        function = next((row for row in self.manifest["functions"] if row["name"] == call["name"]), None)
        if function is None:
            raise BrokerError("function was not delegated")
        call_id = primitive._identifier(call["call_id"], "call ID")
        args = _parse(call["arguments"], "tool arguments", primitive.MAX_ARGUMENT_BYTES)
        canonical = _canonical(args).decode().strip()
        if function["profile"] == "workspace":
            request = self._request(task_id, args, branch)
            if task_id == "leader" and request["op"] == "init" and _state_raw(self.leader_stage()) is not None:
                raise BrokerError("leader init is allowed once")
        stage = Path(branch["stage_dir"])
        with self._locked():
            claimed = self._guard(context, guard)
            report = self.verify()
            records, _, _, current = self._records()
            if task_id == "leader" and current is not None:
                raise BrokerError("leader tools cannot race an active worker epoch")
            branch = self.branch(task_id)
            if function["profile"] == "workspace":
                self._request(task_id, args, branch)
            if report["blocked"] or any(row["task_id"] == task_id and terminal is None for _, row, terminal in records):
                raise BrokerError("pending tool blocks new effects")
            status = context.status()
            if (status["state"] != "active" or status["tools_reserved"] >= status["max_tool_calls"]
                    or status["tools_reserved"] != len(records) or any(row["call_id"] == call_id for _, row, _ in records)):
                raise BrokerError("common cap/count or unique call ID changed")
            before = _work(stage)
            number = len(records) + 1
            reserved = {"schema": 1, "manifest_sha256": self.sha256, "claim_sha256": claimed,
                "task_id": task_id, "request_id": request_id, "call_id": call_id,
                "function_name": function["name"], "profile": function["profile"],
                "arguments": canonical, "arguments_sha256": _sha(canonical.encode()),
                "global_ordinal": number, "local_ordinal": 1 + sum(row["task_id"] == task_id for _, row, _ in records),
                "epoch": current["epoch"] if task_id != "leader" else 0,
                "work_before": before, "work_before_sha256": _sha(_canonical(before))}
            if function["profile"] == "analysis_readonly":
                source, old = _analysis_source(stage, before, args, [(row, terminal) for _, row, terminal in records
                    if row["task_id"] == task_id and terminal is not None])
                reserved.update(analysis_script_sha256=source, old_metrics_sha256=old)
            self._guard(context, guard)
            primitive._publish_file(self.reservations / f"{number:04d}.json", _canonical(reserved), self.broker_dir)
            self._active.add(number)
        try:
            self._guard(context, guard)
            stream_dir = self.broker_dir / f"{number:04d}"
            _directory(stream_dir)
            self._manifest()
            tool_raw = primitive._executable(Path(function["path"]))[0]
            plan, _ = self._plan_state()
            remaining, wall = context.deadline - time.monotonic(), plan["limits"]["tool_wall_seconds"]
            if (type(wall) not in (int, float) or not math.isfinite(wall) or not 0 < wall <= 300
                    or not math.isfinite(remaining) or remaining <= 0):
                raise BrokerError("shared deadline/tool wall cap invalid")
            timeout = min(float(wall), remaining)
            readonly = function["profile"] == "analysis_readonly"
            self._guard(context, guard)
            start = time.monotonic()
            result = run_sandboxed(argv=[function["path"], str(stage / "case"), str(stage / "inputs"),
                str(stage / "work"), canonical], cwd=stage / "case",
                read_roots=[stage / "case", stage / "inputs"] + ([stage / "work"] if readonly else []),
                write_roots=[] if readonly else [stage / "work"], runtime_roots=default_python_runtime_roots(),
                stdout_path=stream_dir / "stdout", stderr_path=stream_dir / "stderr",
                timeout_seconds=timeout, cpu_seconds=max(1, min(60, math.ceil(timeout))),
                file_bytes_per_file=MAX_STREAM, sealed_executable_bytes=tool_raw,
                sealed_executable_sha256=function["sha256"])
            elapsed = time.monotonic() - start
            self._guard(context, guard)
            stdout, stderr = _raw(stream_dir / "stdout", MAX_STREAM), _raw(stream_dir / "stderr", MAX_STREAM)
            child = _work(stage)
            if (result.timed_out or result.launch_error is not None or type(result.exit_code) is not int
                    or result.exit_code < 0 or result.sealed_executable_sha256 != function["sha256"]):
                raise BrokerError("tool launch/termination is uncertain")
            terminal = {"schema": 1, "reservation_sha256": _sha(_canonical(reserved)),
                **{key: reserved[key] for key in ("manifest_sha256", "claim_sha256", "task_id", "request_id", "call_id",
                    "function_name", "profile", "global_ordinal", "local_ordinal", "epoch")},
                "stdout_sha256": _sha(stdout), "stderr_sha256": _sha(stderr),
                "stdout_bytes": len(stdout), "stderr_bytes": len(stderr),
                "sandbox": {"exit_code": result.exit_code, "timed_out": result.timed_out,
                    "launch_error": result.launch_error, "landlock_abi": result.landlock_abi,
                    "duration_seconds": result.duration_seconds, "host_elapsed_seconds": elapsed,
                    "sealed_executable_sha256": result.sealed_executable_sha256}}
            if readonly:
                if child != before:
                    raise BrokerError("readonly participant altered work")
                status, diagnostic, _, _, parsed = _analysis_output(stream_dir / "stdout", result.exit_code, MAX_STREAM)
                self._guard(context, guard)
                metric_sha = _publish_analysis_metrics(stage / "work", parsed, reserved["old_metrics_sha256"])
                after = _work(stage)
                analysis._metrics_transition(child, after, parsed)
                output = analysis._feedback(status, diagnostic, stdout, parsed)
                terminal.update(analysis_status=status, analysis_diagnostic=diagnostic,
                    analysis_script_sha256=reserved["analysis_script_sha256"], analysis_metrics_sha256=metric_sha,
                    analysis_work_after_child=child, method_state_raw=None)
            else:
                parsed = None
                try:
                    value = _parse(stdout, "tool output", primitive.MAX_OUTPUT_BYTES)
                    if type(value) is dict:
                        parsed = value
                except BrokerError:
                    pass
                output = _canonical(parsed).decode().strip() if parsed is not None else analysis._feedback(
                    "tool_failure", "original method tool failed", stdout, None)
                after = child
                raw_state = _state_raw(stage)
                terminal.update(method_state_raw=raw_state.decode() if raw_state is not None else None)
            terminal.update(status="success" if readonly or parsed is not None and parsed.get("ok") is True else "tool_failure",
                output=output, output_json=parsed, work_after=after, work_after_sha256=_sha(_canonical(after)))
            self._guard(context, guard)
            primitive._publish_file(self.receipts / f"{number:04d}.json", _canonical(terminal), self.broker_dir)
            self._guard(context, guard)
            return {"type": "function_call_output", "call_id": call_id, "output": output}
        except BaseException:
            self._unusable = True
            raise
        finally:
            self._active.discard(number)

    def operations(self):
        self.verify()
        records, _, _, _ = self._records()
        return [{"task_id": row["task_id"], "request_id": row["request_id"], "call_id": row["call_id"],
                 "epoch": row["epoch"], "global_ordinal": number, "local_ordinal": row["local_ordinal"],
                 "function_name": row["function_name"], "profile": row["profile"],
                 "outer_arguments": _parse(row["arguments"], "arguments", primitive.MAX_ARGUMENT_BYTES),
                 "request": _parse(_parse(row["arguments"], "arguments", primitive.MAX_ARGUMENT_BYTES)["request"],
                                   "request", primitive.MAX_ARGUMENT_BYTES) if row["profile"] == "workspace" else None,
                 "terminal": terminal, "output_json": terminal["output_json"] if terminal else None,
                 "result": {"type": "function_call_output", "call_id": row["call_id"], "output": terminal["output"]}
                           if terminal else None}
                for number, row, terminal in records]

    def public_state(self):
        self.verify()
        raw = _state_raw(self.leader_stage())
        if raw is None:
            return {"state": None, "audit": None, "method_state_sha256": None,
                    "case_id": self.manifest["case_id"], "mode": self.manifest["mode"]}
        state = kernel.parse_state(raw, mode=self.manifest["mode"], case_id=self.manifest["case_id"])
        return {"state": state, "audit": kernel.core.audit(state), "method_state_sha256": _sha(raw),
                "case_id": self.manifest["case_id"], "mode": self.manifest["mode"]}

    def current_metrics(self, task_id):
        self.verify()
        if task_id not in ROLES:
            raise BrokerError("unknown metric role")
        records, work, _, _ = self._records()
        metrics, source = _file(work[task_id], "metrics.json"), _file(work[task_id], "analysis.py")
        if metrics is None or source is None:
            return None
        prior = next(((number, row, terminal) for number, row, terminal in reversed(records)
                      if row["task_id"] == task_id and terminal is not None and terminal.get("analysis_status") == "valid"), None)
        if prior is None:
            return None
        number, row, receipt = prior
        if (source["sha256"] != receipt["analysis_script_sha256"] or metrics["sha256"] != receipt["analysis_metrics_sha256"]
                or _nonmetrics(work[task_id]) != _nonmetrics(receipt["work_after"])):
            return None
        return {"task_id": task_id, "function_name": row["function_name"], "global_ordinal": number,
                "local_ordinal": row["local_ordinal"], "analysis_script_sha256": source["sha256"],
                "analysis_metrics_sha256": metrics["sha256"], "metrics_bytes": metrics["bytes"],
                "metrics_path": str(Path(self.manifest["stages"][task_id]["stage_dir"]) / "work/metrics.json"),
                "metrics": receipt["output_json"], "receipt_sha256": _sha(_canonical(receipt))}

    def _assignments(self, assignments, state):
        if type(assignments) is not list or not 1 <= len(assignments) <= 2:
            raise BrokerError("epoch must delegate one or two actual workers")
        expected = {row["id"] for row in kernel.select_work(state, limit=2)}
        nodes, roles = set(), set()
        for row in assignments:
            if (type(row) is not dict or set(row) != {"task_id", "owned_node_ids", "owned_files"}
                    or row["task_id"] not in OWNED_FILES or row["task_id"] in roles
                    or type(row["owned_node_ids"]) is not list or not row["owned_node_ids"]
                    or set(row["owned_files"]) != set(OWNED_FILES[row["task_id"]])
                    or len(row["owned_files"]) != len(OWNED_FILES[row["task_id"]])):
                raise BrokerError("epoch ownership fields/files are invalid")
            roles.add(row["task_id"])
            for node in row["owned_node_ids"]:
                if node in nodes or node not in expected:
                    raise BrokerError("epoch owns duplicated/nonready nodes")
                nodes.add(node)
        if nodes != expected or len(nodes) != len(assignments):
            raise BrokerError("epoch assignments differ from deterministic original-mode selection")

    def _host_begin(self, kind, epoch, guard):
        if self._unusable or not callable(guard):
            raise BrokerError("host transition cannot start")
        self._guard(None, guard)
        report = self.verify()
        if report["pending"]:
            raise BrokerError("host transition needs reconciled tools")
        self._host_active = True
        _new_file(self.root / "metadata/.intent.json", _canonical({
            "kind": kind, "epoch": epoch, "manifest_sha256": self.sha256}))
        self._guard(None, guard)

    def _host_end(self, event, guard):
        path = self.root / "metadata" / f"{event['seq']:04d}.json"
        self._guard(None, guard)
        binding = {"path": str(path), "sha256": _new_file(path, _canonical(event))}
        self._guard(None, guard)
        (self.root / "metadata/.intent.json").unlink()
        _fsync_dir(self.root / "metadata")
        self._host_active = False
        self._guard(None, guard)
        self.verify()
        return {**binding, **{key: event[key] for key in ("epoch", "assignments")},
                "method_state_sha256": event.get("method_state_sha256", event.get("base_sha256")),
                "work_before_sha256": _sha(_canonical(event["before"])),
                "work_after_sha256": _sha(_canonical(event["after"]))}

    def activate_epoch(self, epoch, assignments, *, guard):
        with self._locked():
            records, work, states, current = self._records()
            events = self._events()
            plan, _ = self._plan_state()
            if (type(epoch) is not int or epoch != len(events) // 2 + 1 or current is not None
                    or epoch > plan["max_epochs"] or states["leader"] is None):
                raise BrokerError("epoch number/cap or leader initialization is invalid")
            self._assignments(assignments, kernel.parse_state(states["leader"], mode=self.manifest["mode"]))
            self._host_begin("activate", epoch, guard)
            try:
                directory = self.root / "epochs" / f"{epoch:04d}"
                _directory(directory)
                _new_file(directory / "base_state.json", states["leader"])
                before, after = {}, {}
                for item in assignments:
                    role = item["task_id"]
                    stage = Path(self.manifest["stages"][role]["stage_dir"])
                    before[role] = work[role]
                    for path in list((stage / "work").iterdir()):
                        self._guard(None, guard)
                        _raw(path)
                        path.unlink()
                    for row in work["leader"]["files"]:
                        if row["path"] == "metrics.json":
                            continue
                        self._guard(None, guard)
                        _new_file(stage / "work" / row["path"], _raw(self.leader_stage() / "work" / row["path"]))
                    after[role] = _work(stage)
                event = {"schema": 1, "seq": len(events) + 1, "kind": "activate", "epoch": epoch,
                         "manifest_sha256": self.sha256, "after_tool_ordinal": len(records),
                         "assignments": assignments, "base_path": f"epochs/{epoch:04d}/base_state.json",
                         "base_sha256": _sha(states["leader"]), "before": before, "after": after}
                return self._host_end(event, guard)
            except BaseException:
                self._unusable = True
                raise

    def merge_epoch(self, epoch, *, guard):
        with self._locked():
            records, work, states, current = self._records()
            if current is None or type(epoch) is not int or current["epoch"] != epoch:
                raise BrokerError("merge epoch is not the active delegation")
            self._host_begin("merge", epoch, guard)
            try:
                branches = [{"task_id": row["task_id"], "owned_node_ids": row["owned_node_ids"],
                             "state_raw": states[row["task_id"]],
                             "operations": self._kernel_ops(records, row["task_id"], epoch)}
                            for row in current["assignments"]]
                base = _raw(self.root / current["base_path"], kernel.MAX_STATE_BYTES)
                merged = kernel.merge_operations(base, branches, mode=self.manifest["mode"])
                destination = self.root / "epochs" / f"{epoch:04d}"
                self._guard(None, guard)
                _new_file(destination / "merged_state.json", merged)
                expected_files = {}
                for row in current["assignments"]:
                    for file in work[row["task_id"]]["files"]:
                        if file["path"] in row["owned_files"]:
                            if file["path"] in expected_files:
                                raise BrokerError("branch file conflict has no silent winner")
                            expected_files[file["path"]] = _raw(Path(self.manifest["stages"][row["task_id"]]["stage_dir"]) / "work" / file["path"])
                leader_work = self.leader_stage() / "work"
                self._guard(None, guard)
                _replace_host(leader_work / "metrics.json", None)
                self._guard(None, guard)
                _replace_host(leader_work / "method_state.json", merged)
                for name, raw in expected_files.items():
                    self._guard(None, guard)
                    _replace_host(leader_work / name, raw)
                event = {"schema": 1, "seq": len(self._events()) + 1, "kind": "merge", "epoch": epoch,
                         "manifest_sha256": self.sha256, "after_tool_ordinal": len(records),
                         "assignments": current["assignments"], "before": {"leader": work["leader"]},
                         "after": {"leader": _work(self.leader_stage())},
                         "state_path": f"epochs/{epoch:04d}/merged_state.json",
                         "method_state_sha256": _sha(merged)}
                return self._host_end(event, guard)
            except BaseException:
                self._unusable = True
                raise
