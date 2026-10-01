"""Opt-in empty-work bootstrap and D116 branches under one parent journal.

The bootstrap descriptor stays the reservation binding in both phases. An
append-only activation receipt pins the derived worker delegation and the
actual terminal bootstrap inventory; the existing D116 runner and replay do
all participant execution and host metric publication.
"""

from __future__ import annotations

import ast
import base64
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import development_branch_tool as branch_tool
import development_method_tool as method
import parallel_analysis_broker as analysis
import parallel_tool_broker as legacy
from c_parallel_work import CParallelError, _state, select_independent_work
from tool_policy import _read_bounded_file


BrokerError = legacy.BrokerError
PROFILE = "parent_analysis_two_phase_v1"
BOOTSTRAP_NAME = "bootstrap_manifest.json"
TRANSITION_NAME = "transition.json"
INTENT_NAME = "activation_intent.json"
ACTIVATION_NAME = "activation.json"
BOOTSTRAP_OPS = {"init", "status", "read", "write", "replace", "plan"}


def _sources() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    pending, seen, captured = [Path(__file__).stem], set(), {}
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        raw = _read_bounded_file(root / f"{name}.py", "parent source", legacy.MAX_EXECUTABLE_BYTES)
        captured[f"scripts/{name}.py"] = legacy._sha(raw)
        seen.add(name)
        for node in ast.walk(ast.parse(raw)):
            names = ([item.name.split(".")[0] for item in node.names]
                     if isinstance(node, ast.Import) else
                     [node.module.split(".")[0]]
                     if isinstance(node, ast.ImportFrom) and node.module else [])
            pending.extend(item for item in names if (root / f"{item}.py").is_file())
    captured["prototypes/core.py"] = legacy._sha(_read_bounded_file(
        method.DEFAULT_CORE, "prototype core", method.MAX_CORE_BYTES))
    if any(legacy._sha(_read_bounded_file(root.parent / name, "parent source",
                                        legacy.MAX_EXECUTABLE_BYTES)) != digest
           for name, digest in captured.items()):
        raise BrokerError("parent source closure changed during capture")
    return dict(sorted(captured.items()))


def _method_bytes(owned: list[str] | None = None) -> bytes:
    raw = _read_bounded_file(method.DEFAULT_CORE, "prototype core", method.MAX_CORE_BYTES)
    runtime = method._RUNTIME.replace("__EMBEDDED_CORE_B64__", base64.b64encode(raw).decode()).replace(
        "__EMBEDDED_CORE_SHA256__", legacy._sha(raw))
    if owned is not None:
        guard = ('        op = request["op"]\n'
                 '        if op in {"init", "advance", "approve"}:\n'
                 '            raise ToolError("branch cannot initialize, approve or advance")\n'
                 '        if op in {"revise", "review"}:\n'
                 f'            if request.get("id") not in {json.dumps(owned)}:\n'
                 '                raise ToolError("operation is outside branch ownership")\n'
                 '        base = result_base(')
        if runtime.count(branch_tool._ANCHOR) != 1:
            raise BrokerError("reviewed branch dispatcher anchor changed")
        runtime = runtime.replace(branch_tool._ANCHOR, guard)
    return (f"#!{sys.executable}\n" + runtime).encode()


def _functions(specs: Any, stage: Path, owned: list[str] | None = None) -> list[dict]:
    if type(specs) is not list or not 1 <= len(specs) <= 2:
        raise BrokerError("parent functions require one method and optional analysis")
    frozen, names, profiles = [], set(), set()
    for item in specs:
        if type(item) is not dict or set(item) != {"name", "executable", "profile"}:
            raise BrokerError("parent function specification is invalid")
        name = legacy._identifier(item["name"], "function name")
        profile = item["profile"]
        if name in names or profile not in legacy.PROFILES or profile in profiles:
            raise BrokerError("parent function names or profiles repeat")
        path = legacy._absolute(item["executable"], "parent executable")
        if path.is_relative_to(stage):
            raise BrokerError("executable is inside mutable stage")
        raw, identity = legacy._executable(path)
        expected = _method_bytes(owned) if profile == "workspace" else analysis._launcher_bytes()
        if raw != expected:
            raise BrokerError("parent executable differs from exact reviewed driver")
        names.add(name)
        profiles.add(profile)
        frozen.append({"name": name, "profile": profile, **identity})
    if "workspace" not in profiles:
        raise BrokerError("parent method function is absent")
    return frozen


def _bound(path: Path, binding: Any, label: str) -> dict:
    if (type(binding) is not dict or set(binding) != {"path", "sha256"}
            or legacy._absolute(binding["path"], label) != path):
        raise BrokerError(f"{label} binding is invalid")
    digest = legacy._digest(binding["sha256"], label)
    raw = _read_bounded_file(path, label, legacy.MAX_MANIFEST_BYTES)
    value = legacy._parse(raw, label, legacy.MAX_MANIFEST_BYTES)
    if type(value) is not dict or legacy._canonical(value) != raw or legacy._sha(raw) != digest:
        raise BrokerError(f"{label} digest or canonical bytes changed")
    return value


def prepare_parent_broker_manifest(root: Path, leader_spec: dict, slots: list[dict]) -> dict:
    """Freeze a real empty leader stage and future empty work slots, no graph."""
    root = legacy._absolute(root, "parent stage root")
    legacy._private_dir(root)
    if type(leader_spec) is not dict or set(leader_spec) != {"task_id", "stage_dir", "functions"}:
        raise BrokerError("leader specification has invalid fields or fictitious ownership")
    if type(slots) is not list or not 2 <= len(slots) <= 4:
        raise BrokerError("parent requires two through four future slots")
    sources = _sources()
    task = legacy._identifier(leader_spec["task_id"], "leader task ID")
    stage = legacy._absolute(leader_spec["stage_dir"], "leader stage")
    seen_stages, seen_tasks = [stage], {task}
    if not stage.is_relative_to(root) or stage == root:
        raise BrokerError("leader stage is outside parent root")
    for directory in (stage, stage / "case", stage / "inputs", stage / "work"):
        legacy._private_dir(directory)
    initial = legacy._work(stage)
    if initial["files"] or set(initial["directories"]) != {""}:
        raise BrokerError("leader must start with empty work")
    leader = {"task_id": task, "owned_node_ids": [], "stage_dir": str(stage),
              "stage_identity": legacy._identity(stage, directory=True),
              "snapshot": legacy._parse(legacy._canonical(legacy._immutable_snapshot(stage)),
                                         "leader snapshot", legacy.MAX_MANIFEST_BYTES),
              "initial_work": initial,
              "functions": _functions(leader_spec["functions"], stage)}
    frozen_slots = []
    for slot in slots:
        if type(slot) is not dict or set(slot) != {"task_id", "stage_dir"}:
            raise BrokerError("future slot specification is invalid")
        slot_task = legacy._identifier(slot["task_id"], "future task ID")
        slot_stage = legacy._absolute(slot["stage_dir"], "future stage")
        if (slot_task in seen_tasks or not slot_stage.is_relative_to(root) or slot_stage == root
                or any(slot_stage == other or slot_stage.is_relative_to(other)
                       or other.is_relative_to(slot_stage) for other in seen_stages)):
            raise BrokerError("future slot tasks or stages overlap")
        legacy._private_dir(slot_stage)
        legacy._private_dir(slot_stage / "work")
        work = legacy._work(slot_stage)
        if set(path.name for path in slot_stage.iterdir()) != {"work"} or work["files"] \
                or set(work["directories"]) != {""}:
            raise BrokerError("future slot must contain only empty work")
        seen_stages.append(slot_stage)
        seen_tasks.add(slot_task)
        frozen_slots.append({"task_id": slot_task, "stage_dir": str(slot_stage),
                             "stage_identity": legacy._identity(slot_stage, directory=True),
                             "initial_work": work})
    metadata = root / "metadata"
    if not metadata.exists():
        metadata.mkdir(mode=0o700)
        legacy._fsync_dir(root)
    legacy._private_dir(metadata)
    if any((metadata / name).exists() for name in (TRANSITION_NAME, INTENT_NAME, ACTIVATION_NAME)):
        raise BrokerError("parent phase descriptors already exist")
    if sources != _sources():
        raise BrokerError("parent source closure changed before publication")
    manifest = {"schema": 1, "profile": PROFILE, "root": str(root),
                "root_identity": legacy._identity(root, directory=True),
                "metadata_identity": legacy._identity(metadata, directory=True),
                "leader": leader, "slots": frozen_slots, "source_bindings": sources}
    path = metadata / BOOTSTRAP_NAME
    return {"path": str(path), "sha256": legacy._new_file(path, legacy._canonical(manifest))}


prepare_parent_manifest = prepare_parent_broker_manifest


class ParentAnalysisBroker(analysis.AnalysisParallelToolBroker):
    """One claim, context tool cap and flat ordinal stream across two phases."""

    def _manifest(self) -> dict:
        bootstrap = _bound(self.path, self.binding, "bootstrap manifest")
        if (set(bootstrap) != {"schema", "profile", "root", "root_identity", "metadata_identity",
                               "leader", "slots", "source_bindings"}
                or type(bootstrap["schema"]) is not int or bootstrap["schema"] != 1
                or bootstrap["profile"] != PROFILE or bootstrap["source_bindings"] != _sources()):
            raise BrokerError("parent bootstrap contract or source closure changed")
        root = legacy._absolute(bootstrap["root"], "parent stage root")
        metadata = root / "metadata"
        if (self.path != metadata / BOOTSTRAP_NAME
                or legacy._identity(root, directory=True) != bootstrap["root_identity"]
                or legacy._identity(metadata, directory=True) != bootstrap["metadata_identity"]):
            raise BrokerError("parent root or metadata identity changed")
        leader = bootstrap["leader"]
        if (type(leader) is not dict or set(leader) != {"task_id", "owned_node_ids", "stage_dir",
                "stage_identity", "snapshot", "initial_work", "functions"}
                or leader["owned_node_ids"] != [] or leader["initial_work"]["files"]
                or set(leader["initial_work"]["directories"]) != {""}):
            raise BrokerError("bootstrap leader or empty initial work changed")
        legacy._identifier(leader["task_id"], "leader task ID")
        if _functions(self._function_specs(leader), Path(leader["stage_dir"])) != leader["functions"]:
            raise BrokerError("bootstrap driver identity changed")
        slots = bootstrap["slots"]
        if type(slots) is not list or not 2 <= len(slots) <= 4:
            raise BrokerError("future slot count changed")
        tasks, stages = {leader["task_id"]}, [Path(leader["stage_dir"])]
        for slot in slots:
            if type(slot) is not dict or set(slot) != {"task_id", "stage_dir", "stage_identity", "initial_work"}:
                raise BrokerError("future slot fields changed")
            task = legacy._identifier(slot["task_id"], "future task ID")
            stage = legacy._absolute(slot["stage_dir"], "future stage")
            if (task in tasks or stage == root or not stage.is_relative_to(root)
                    or any(stage == other or stage.is_relative_to(other)
                           or other.is_relative_to(stage) for other in stages)
                    or legacy._identity(stage, directory=True) != slot["stage_identity"]
                    or slot["initial_work"]["files"] or set(slot["initial_work"]["directories"]) != {""}
                    or legacy._identity(stage / "work", directory=True) != slot["initial_work"]["directories"][""][:2]
                    + slot["initial_work"]["directories"][""][3:4]
                    + [slot["initial_work"]["directories"][""][2] & 0o7777]):
                raise BrokerError("future slot identity or empty origin changed")
            tasks.add(task)
            stages.append(stage)
        activation = None
        branches = [leader]
        if (metadata / ACTIVATION_NAME).exists():
            activation = legacy._read_json(metadata / ACTIVATION_NAME, legacy.MAX_MANIFEST_BYTES)
            intent = legacy._read_json(metadata / INTENT_NAME, legacy.MAX_MANIFEST_BYTES)
            if (set(activation) != set(intent) | {"intent_sha256"}
                    or any(activation[key] != value for key, value in intent.items())
                    or activation["intent_sha256"] != legacy._sha(legacy._canonical(intent))
                    or intent.get("schema") != 1 or intent.get("profile") != PROFILE
                    or intent.get("bootstrap_manifest") != self.binding):
                raise BrokerError("parent activation receipt or intent changed")
            transition = _bound(metadata / TRANSITION_NAME, intent["transition"], "transition")
            worker_manifest = self._worker_manifest(intent["branch_manifest"])
            self._transition_fields(transition, intent["branch_manifest"], intent)
            branches += worker_manifest["branches"]
        return {"schema": 1, "profile": PROFILE, "root": str(root),
                "root_identity": bootstrap["root_identity"], "branches": branches,
                "bootstrap": bootstrap, "activation": activation}

    @staticmethod
    def _function_specs(branch: dict) -> list[dict]:
        return [{"name": fn["name"], "profile": fn["profile"], "executable": fn["path"]}
                for fn in branch["functions"]]

    def _worker_manifest(self, binding: dict) -> dict:
        root = Path(self.path).parent.parent
        if legacy._absolute(binding.get("path"), "worker manifest") != root / analysis.MANIFEST_NAME:
            raise BrokerError("worker manifest is outside predeclared root")
        reader = SimpleNamespace(path=Path(binding["path"]), sha256=binding.get("sha256"))
        manifest = analysis.AnalysisParallelToolBroker._manifest(reader)
        # Use the pinned bootstrap itself while constructing __init__'s first manifest.
        bootstrap = _bound(self.path, self.binding, "bootstrap manifest")
        if manifest["root"] != bootstrap["root"] or len(manifest["branches"]) != len(bootstrap["slots"]):
            raise BrokerError("worker root or slot count changed")
        for branch, slot in zip(manifest["branches"], bootstrap["slots"], strict=True):
            if any(branch[key] != slot[key] for key in ("task_id", "stage_dir", "stage_identity")):
                raise BrokerError("worker delegation differs from predeclared slot")
            if _functions(self._function_specs(branch), Path(branch["stage_dir"]),
                          branch["owned_node_ids"]) != branch["functions"]:
                raise BrokerError("worker driver differs from exact ownership wrapper")
        return manifest

    def journal_roots(self) -> list[Path]:
        return [Path(self.manifest["root"])]

    def _plan_state(self) -> tuple[dict, dict]:
        state = legacy._read_json(self.run_dir / "run.json")
        raw = _read_bounded_file(self.run_dir / "plan.json", "parent plan", legacy.MAX_PLAN_BYTES)
        plan = legacy._parse(raw, "parent plan", legacy.MAX_PLAN_BYTES)
        if (type(plan) is not dict or legacy._sha(raw) != state.get("plan_sha256")
                or plan.get("run_id") != state.get("run_id")
                or plan.get("bootstrap_manifest") != self.binding):
            raise BrokerError("parent plan or bootstrap binding changed")
        descriptor = state.get("admission_descriptor")
        if type(descriptor) is not dict:
            raise BrokerError("parent admission descriptor is absent")
        expected = legacy.admission.claim_digest(state["plan_sha256"], state["run_id"],
            legacy.admission.owner("oneshot", self.run_dir, self.run_dir), descriptor)
        if state.get("claim_sha256") != expected:
            raise BrokerError("parent claim digest changed")
        return plan, state

    @staticmethod
    def _request(reservation: dict) -> dict:
        outer = legacy._parse(reservation["arguments"], "bootstrap arguments", legacy.MAX_ARGUMENT_BYTES)
        if type(outer) is not dict or set(outer) != {"request"} or type(outer["request"]) is not str:
            raise BrokerError("bootstrap method arguments are invalid")
        request = legacy._parse(outer["request"], "bootstrap request", legacy.MAX_ARGUMENT_BYTES)
        if type(request) is not dict or request.get("op") not in BOOTSTRAP_OPS:
            raise BrokerError("bootstrap operation is outside its fixed allowlist")
        return request

    def _records(self) -> tuple[list[tuple[int, dict, dict | None]], dict[str, dict]]:
        records, work = super()._records()
        leader = self.manifest["bootstrap"]["leader"]["task_id"]
        activation = self.manifest["activation"]
        cut = activation["first_worker_ordinal"] if activation else len(records) + 1
        inits = []
        for ordinal, reservation, receipt in records:
            if (reservation["task_id"] == leader) != (ordinal < cut):
                raise BrokerError("tool history crossed its parent phase boundary")
            if reservation["task_id"] == leader and reservation["profile"] == "workspace":
                if self._request(reservation)["op"] == "init":
                    inits.append(ordinal)
        if len(inits) > 1:
            raise BrokerError("bootstrap init was reserved more than once")
        if activation:
            self._activation_replay(activation, records, work[leader])
        return records, work

    def verify(self) -> dict:
        current = self._manifest()
        if self.manifest.get("activation") is not None and current != self.manifest:
            raise BrokerError("activated parent manifest changed")
        if current["bootstrap"] != self.manifest["bootstrap"]:
            raise BrokerError("bootstrap manifest changed")
        self.manifest = current
        _, state = self._plan_state()
        records, _ = self._records()
        if records or current["activation"]:
            self._state_claim()
        if any(record["claim_sha256"] != state["claim_sha256"] for _, record, _ in records):
            raise BrokerError("parent tool claim changed")
        pending = [ordinal for ordinal, _, receipt in records if receipt is None]
        phase_pending = current["activation"] is None and any(
            (Path(current["root"]) / "metadata" / name).exists()
            for name in (TRANSITION_NAME, INTENT_NAME))
        return {"manifest_sha256": self.sha256, "reservations": len(records),
                "receipts": len(records) - len(pending), "pending": pending,
                "blocked": self._unusable or phase_pending
                           or any(number not in self._active for number in pending)}

    def _empty_slots(self) -> None:
        for slot in self.manifest["bootstrap"]["slots"]:
            stage = Path(slot["stage_dir"])
            if set(path.name for path in stage.iterdir()) != {"work"} \
                    or legacy._work(stage) != slot["initial_work"]:
                raise BrokerError("future slots were materialized before transition")

    def invoke(self, task_id: str, request_id: str, call: dict, context: Any,
               guard: Callable[[], None]) -> dict:
        report = self.verify()
        if report["blocked"]:
            raise BrokerError("unreconciled parent effect or transition blocks tools")
        leader = self.manifest["bootstrap"]["leader"]
        active = self.manifest["activation"] is not None
        if (task_id == leader["task_id"]) == active:
            raise BrokerError("tool task is outside the active parent phase")
        if not active:
            self._empty_slots()
            function = next((fn for fn in leader["functions"] if fn["name"] == call.get("name")), None) \
                if type(call) is dict else None
            if function and function["profile"] == "workspace":
                request = self._request({"arguments": call.get("arguments")})
                if request["op"] == "init" and any(
                    record["profile"] == "workspace" and self._request(record)["op"] == "init"
                    for _, record, _ in self._records()[0]):
                    raise BrokerError("bootstrap init was already reserved")
        return super().invoke(task_id, request_id, call, context, guard)

    def operations(self) -> list[dict]:
        leader = self.manifest["bootstrap"]["leader"]["task_id"]
        return [{**operation, "phase": "bootstrap" if operation["task_id"] == leader else "wave"}
                for operation in super().operations()]

    def _terminal_bootstrap(self, records: list, work: dict) -> dict:
        leader = self.manifest["bootstrap"]["leader"]
        selected = [(ordinal, record, receipt) for ordinal, record, receipt in records
                    if record["task_id"] == leader["task_id"] and record["profile"] == "workspace"
                    and self._request(record)["op"] == "init"]
        if len(selected) != 1 or any(receipt is None for _, _, receipt in records):
            raise BrokerError("activation requires exactly one terminal bootstrap init")
        ordinal, record, receipt = selected[0]
        output = receipt["output_json"]
        state_file, proposal = analysis._file(work, "method_state.json"), analysis._file(work, "proposal.json")
        if (receipt["status"] != "success" or type(output) is not dict or output.get("ok") is not True
                or output.get("operation") != "init" or state_file is None or proposal is None
                or output.get("method_state_sha256") != state_file["sha256"]
                or output.get("proposal_sha256") != proposal["sha256"]):
            raise BrokerError("bootstrap init failed or its real seed changed")
        stage = Path(leader["stage_dir"])
        state_raw = _read_bounded_file(stage / "work/method_state.json", "bootstrap state", legacy.MAX_RECORD_BYTES)
        try:
            state = _state(state_raw)
        except (CParallelError, ValueError, KeyError, TypeError) as exc:
            raise BrokerError("bootstrap graph is invalid") from exc
        if (any(node["status"] != "pending" or node["version"] != 1 or node["stale"]
                for node in state["nodes"].values()) or state["accepted_versions"]
                or any(value != "not_started" for value in state["phase_status"].values())):
            raise BrokerError("bootstrap graph has a resolved node or accepted phase")
        proposal_raw = _read_bounded_file(stage / "work/proposal.json", "bootstrap proposal", legacy.MAX_RECORD_BYTES)
        expected = {"case_id": state["case_id"], "nodes": self._request(record)["nodes"]}
        if legacy._parse(proposal_raw, "bootstrap proposal", legacy.MAX_RECORD_BYTES) != expected:
            raise BrokerError("real init differs from its request proposal")
        return {"leader_state_sha256": state_file["sha256"],
                "leader_work_sha256": legacy._sha(legacy._canonical(work)),
                "init_global_ordinal": ordinal, "state": state}

    def bootstrap_snapshot(self) -> dict:
        report = self.verify()
        if report["pending"] or report["blocked"] or self.manifest["activation"]:
            raise BrokerError("bootstrap snapshot requires a reconciled bootstrap phase")
        records, work = self._records()
        leader = self.manifest["bootstrap"]["leader"]
        terminal = self._terminal_bootstrap(records, work[leader["task_id"]])
        return {"bootstrap_manifest": self.binding, "leader_task_id": leader["task_id"],
                "stage_dir": leader["stage_dir"], "first_worker_ordinal": len(records) + 1,
                "work": work[leader["task_id"]], **terminal, "operations": self.operations()}

    def _transition_fields(self, transition: dict, binding: dict, terminal: dict) -> None:
        expected = {"bootstrap_manifest": self.binding, "branch_manifest": binding,
                    **{key: terminal[key] for key in ("first_worker_ordinal", "leader_work_sha256",
                                                      "leader_state_sha256")}}
        if any(transition.get(key) != value for key, value in expected.items()):
            raise BrokerError("transition differs from actual bootstrap or delegation")

    def _activation_replay(self, activation: dict, records: list, work: dict) -> None:
        fields = {"schema", "profile", "bootstrap_manifest", "branch_manifest", "transition",
                  "plan_sha256", "claim_sha256", "first_worker_ordinal", "leader_work_sha256",
                  "leader_state_sha256", "bootstrap_receipts_sha256", "intent_sha256"}
        if (set(activation) != fields or type(activation["first_worker_ordinal"]) is not int
                or not 1 < activation["first_worker_ordinal"] <= len(records) + 1):
            raise BrokerError("parent activation ordinal or fields changed")
        _, state = self._plan_state()
        if any(activation[key] != state[key] for key in ("plan_sha256", "claim_sha256")):
            raise BrokerError("activation parent plan or claim changed")
        before = [item for item in records if item[0] < activation["first_worker_ordinal"]]
        terminal = self._terminal_bootstrap(before, work)
        if (any(activation[key] != terminal[key] for key in ("leader_work_sha256", "leader_state_sha256"))
                or activation["bootstrap_receipts_sha256"] != legacy._sha(legacy._canonical(
                    [legacy._sha(legacy._canonical(receipt)) for _, _, receipt in before]))):
            raise BrokerError("activation terminal bootstrap or receipt chain changed")
        try:
            selected = select_independent_work(terminal["state"], len(self.manifest["bootstrap"]["slots"]))
        except CParallelError as exc:
            raise BrokerError("bootstrap graph lacks independent worker tasks") from exc
        for branch, entry in zip(self.manifest["branches"][1:], selected, strict=True):
            seed = branch["initial_work"]["files"]
            if (branch["owned_node_ids"] != [entry["id"]] or len(seed) != 1
                    or seed[0]["path"] != "method_state.json"
                    or seed[0]["sha256"] != terminal["leader_state_sha256"]
                    or set(branch["initial_work"]["directories"]) != {""}):
                raise BrokerError("worker ownership or initial seed differs from real bootstrap")

    def activate(self, branch_manifest: dict, context: Any, guard: Callable[[], None]) -> dict:
        """Seal one derived delegation; partial transition cannot auto-recover."""
        with self._locked():
            self._guard(context, guard)
            self.verify()
            metadata = Path(self.manifest["root"]) / "metadata"
            if (self._unusable or self._active or self.manifest["activation"]
                    or (metadata / INTENT_NAME).exists()):
                raise BrokerError("parent activation is duplicate, active or uncertain")
            records, work = self._records()
            if any(receipt is None for _, _, receipt in records):
                raise BrokerError("pending bootstrap effect prevents activation")
            leader = self.manifest["bootstrap"]["leader"]["task_id"]
            terminal = self._terminal_bootstrap(records, work[leader])
            workers = self._worker_manifest(branch_manifest)
            transition_path = metadata / TRANSITION_NAME
            transition = legacy._read_json(transition_path, legacy.MAX_MANIFEST_BYTES)
            _, state = self._plan_state()
            intent = {"schema": 1, "profile": PROFILE, "bootstrap_manifest": self.binding,
                      "branch_manifest": branch_manifest,
                      "transition": {"path": str(transition_path), "sha256": legacy._sha(legacy._canonical(transition))},
                      "plan_sha256": state["plan_sha256"], "claim_sha256": state["claim_sha256"],
                      "first_worker_ordinal": len(records) + 1,
                      **{key: terminal[key] for key in ("leader_work_sha256", "leader_state_sha256")},
                      "bootstrap_receipts_sha256": legacy._sha(legacy._canonical(
                          [legacy._sha(legacy._canonical(receipt)) for _, _, receipt in records]))}
            self._transition_fields(transition, branch_manifest, intent)
            candidate = {**self.manifest, "branches": self.manifest["branches"] + workers["branches"]}
            previous = self.manifest
            try:
                self.manifest = candidate
                self._activation_replay({**intent, "intent_sha256": "0" * 64}, records, work[leader])
            finally:
                self.manifest = previous
            status = context.status()
            if (status["state"] != "active" or status["tools_reserved"] != len(records)
                    or len(records) > status["max_tool_calls"]):
                raise BrokerError("shared context tool cap changed at transition")
            self._guard(context, guard)
            try:
                intent_sha = legacy._new_file(metadata / INTENT_NAME, legacy._canonical(intent))
                self._guard(context, guard)
                if legacy._work(Path(self.manifest["bootstrap"]["leader"]["stage_dir"])) != work[leader]:
                    raise BrokerError("bootstrap work changed during activation")
                if self._worker_manifest(branch_manifest) != workers:
                    raise BrokerError("worker delegation changed during activation")
                _bound(transition_path, intent["transition"], "transition")
                activation = {**intent, "intent_sha256": intent_sha}
                path = metadata / ACTIVATION_NAME
                digest = legacy._new_file(path, legacy._canonical(activation))
                self._guard(context, guard)
                self.verify()
                return {"path": str(path), "sha256": digest}
            except BaseException:
                self._unusable = True
                raise

    def wave_view(self) -> _WaveView:
        self.verify()
        if self.manifest["activation"] is None:
            raise BrokerError("worker view requires activated delegation")
        return _WaveView(self)


class _WaveView:
    """Filter leader operations for the existing branch merger, keep real IDs."""

    def __init__(self, parent: ParentAnalysisBroker):
        self.parent = parent

    def verify(self) -> dict:
        return self.parent.verify()

    def operations(self) -> list[dict]:
        return [item for item in self.parent.operations() if item["phase"] == "wave"]

    def branch(self, task_id: str) -> dict:
        if task_id == self.parent.manifest["bootstrap"]["leader"]["task_id"]:
            raise BrokerError("leader is outside worker view")
        return self.parent.branch(task_id)

    def current_metrics(self, task_id: str) -> dict | None:
        self.branch(task_id)
        return self.parent.current_metrics(task_id)
