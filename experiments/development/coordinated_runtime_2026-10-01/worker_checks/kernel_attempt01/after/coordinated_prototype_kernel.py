"""Validate and replay the original four-phase prototypes for D119.

Selection is the prospective adapter policy: A uses phase/ID and local
dependency readiness with one worker, B uses phase/ID and dependency closure,
and C uses the original risk queue. Mutation always runs the unchanged core.
An unsafe accepted phase in A remains observable through ``core.audit``.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
from pathlib import Path


CORE_PATH = Path(__file__).resolve().parents[1] / "prototypes" / "core.py"
_spec = importlib.util.spec_from_file_location("d119_original_core", CORE_PATH)
assert _spec is not None and _spec.loader is not None
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)
MODES = ("sequential", "graph", "risk")
PHASES = core.PHASES
MAX_STATE_BYTES = 256 * 1024
ROLES = ("leader", "worker-1", "worker-2")
_NODE_FIELDS = {"id", "kind", "phase", "status", "claim", "depends_on", "risk", "version", "stale"}


class KernelError(ValueError):
    """A state or operation differs from the sealed prototype contract."""


def _exact(value, fields, label):
    if type(value) is not dict or set(value) != set(fields):
        raise KernelError(f"{label} fields differ")


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise KernelError(f"{label} must be nonempty text")


def _positive(value, label):
    if type(value) is not int or value < 1:
        raise KernelError(f"{label} must be a positive integer")


def _mode(mode):
    if type(mode) is not str or mode not in MODES:
        raise KernelError("workflow mode is invalid")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise KernelError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_value):
    raise KernelError("nonfinite JSON value")


def _json(raw):
    if type(raw) is not bytes or not raw or len(raw) > MAX_STATE_BYTES:
        raise KernelError("state bytes are absent or exceed the bound")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise KernelError("state is not bounded strict JSON") from exc


def _history(state):
    """Check native version, staleness and phase changes, including invalidation."""
    nodes, history, mode = state["nodes"], state["history"], state["mode"]
    if type(history) is not list or not history:
        raise KernelError("state history is absent")
    versions = dict.fromkeys(nodes, 1)
    stale = dict.fromkeys(nodes, False)
    phases = dict.fromkeys(PHASES, "not_started")
    snapshots = {}
    for seq, row in enumerate(history, 1):
        if type(row) is not dict or type(row.get("seq")) is not int or row["seq"] != seq:
            raise KernelError("history sequence differs")
        action = row.get("action")
        if seq == 1:
            _exact(row, {"seq", "action", "source"}, "init history")
            if action != "init":
                raise KernelError("history does not begin with init")
            _text(row["source"], "init source")
            continue
        if action == "revise":
            _exact(row, {"seq", "action", "node", "status", "reason", "affected"}, "revise history")
            node_id = row["node"]
            if type(node_id) is not str or node_id not in nodes or nodes[node_id]["kind"] == "normative":
                raise KernelError("history revision node is invalid")
            if type(row["status"]) is not str or row["status"] not in core.STATUSES:
                raise KernelError("history revision status is invalid")
            _text(row["reason"], "history revision reason")
            affected = {node_id}
            if mode != "sequential":
                affected.update(core.descendants(nodes, node_id))
            if row["affected"] != sorted(affected):
                raise KernelError("history affected nodes differ from native invalidation")
            versions[node_id] += 1
            for child in affected - {node_id}:
                stale[child] = True
            for phase in PHASES:
                if phases[phase] == "accepted" and any(nodes[key]["phase"] == phase for key in affected):
                    phases[phase] = "needs_review"
        elif action == "review":
            _exact(row, {"seq", "action", "node", "version"}, "review history")
            node_id = row["node"]
            if (mode == "sequential" or type(node_id) is not str or node_id not in nodes
                    or nodes[node_id]["kind"] == "normative" or not stale[node_id]):
                raise KernelError("history review is not native review")
            versions[node_id] += 1
            if type(row["version"]) is not int or row["version"] != versions[node_id]:
                raise KernelError("history review version differs")
            stale[node_id] = False
        elif action == "advance":
            _exact(row, {"seq", "action", "phase"}, "advance history")
            phase = row["phase"]
            if type(phase) is not str or phase not in PHASES:
                raise KernelError("history advance phase is invalid")
            if mode != "risk" and any(phases[key] != "accepted" for key in PHASES[:PHASES.index(phase)]):
                raise KernelError("history advance violates native prior phases")
            phases[phase] = "accepted"
            closure = core.closure_versions(nodes, [key for key, node in nodes.items() if node["phase"] == phase])
            snapshots[phase] = {key: versions[key] for key in closure}
        else:
            raise KernelError("history contains a forbidden or unknown action")
    if state["phase_status"] != phases or state["accepted_versions"] != snapshots:
        raise KernelError("phase state differs from native history")
    if any(nodes[key]["version"] != versions[key] or nodes[key]["stale"] is not stale[key] for key in nodes):
        raise KernelError("node versions or staleness differ from native history")


def parse_state(raw: bytes, *, mode: str, case_id: str | None = None) -> dict:
    _mode(mode)
    state = _json(raw)
    _exact(state, {"schema", "case_id", "mode", "nodes", "phase_status", "accepted_versions", "history"}, "state")
    if type(state["schema"]) is not int or state["schema"] != 1 or state["mode"] != mode:
        raise KernelError("state schema or workflow mode differs")
    _text(state["case_id"], "case identity")
    if case_id is not None and state["case_id"] != case_id:
        raise KernelError("state case identity differs")
    nodes = state["nodes"]
    if type(nodes) is not dict or not 4 <= len(nodes) <= 64:
        raise KernelError("state needs 4 to 64 nodes")
    initial = []
    for node_id, node in nodes.items():
        _text(node_id, "node identity")
        _exact(node, _NODE_FIELDS, "node")
        if node["id"] != node_id or type(node["stale"]) is not bool:
            raise KernelError("node identity or staleness is invalid")
        _positive(node["version"], "node version")
        _exact(node["risk"], {"impact", "uncertainty", "effort"}, "node risk")
        if type(node["depends_on"]) is not list or len(set(map(str, node["depends_on"]))) != len(node["depends_on"]):
            raise KernelError("node dependencies are not unique")
        # The original validator checks identifiers, kinds, phases, claims,
        # risks, all dependencies and cycles. Only version/stale are restored.
        initial.append({key: value for key, value in node.items() if key not in {"version", "stale"}})
    try:
        core.validate_case({"case_id": state["case_id"], "nodes": initial})
    except (core.WorkflowError, TypeError, KeyError, RecursionError) as exc:
        raise KernelError("state nodes differ from the original graph schema") from exc
    _exact(state["phase_status"], PHASES, "phase status")
    if any(type(value) is not str or value not in {"not_started", "accepted", "needs_review"}
           for value in state["phase_status"].values()):
        raise KernelError("phase status is invalid")
    snapshots = state["accepted_versions"]
    if type(snapshots) is not dict or set(snapshots) - set(PHASES):
        raise KernelError("accepted version phases are invalid")
    for snapshot in snapshots.values():
        if type(snapshot) is not dict or set(snapshot) - set(nodes):
            raise KernelError("accepted version nodes are invalid")
        for key, version in snapshot.items():
            _positive(version, "accepted version")
            if version > nodes[key]["version"]:
                raise KernelError("accepted version exceeds current version")
    _history(state)
    return state


def validate_initialization(proposal: dict, state_raw: bytes, *, mode: str,
                            case_id: str, proposal_path: Path) -> dict:
    _mode(mode)
    _exact(proposal, {"case_id", "nodes"}, "proposal")
    if proposal["case_id"] != case_id or not isinstance(proposal_path, Path):
        raise KernelError("proposal case or source path differs")
    items = proposal["nodes"]
    if type(items) is not list or not 4 <= len(items) <= 64:
        raise KernelError("proposal needs 4 to 64 nodes")
    fields = _NODE_FIELDS - {"risk", "version", "stale"}
    for node in items:
        if (type(node) is not dict or not fields <= set(node) or set(node) - (fields | {"risk"})
                or node.get("status") != "pending"):
            raise KernelError("proposal nodes must begin pending with exact fields")
        if "risk" in node:
            _exact(node["risk"], {"impact", "uncertainty", "effort"}, "proposal risk")
    try:
        nodes = core.validate_case(proposal)
    except (core.WorkflowError, TypeError, KeyError, RecursionError) as exc:
        raise KernelError("proposal differs from original graph schema") from exc
    normative = {key for key, node in nodes.items() if node["kind"] == "normative"}
    if not any(node["kind"] == "requirement" and node["phase"] == "engineering"
               and normative.intersection(core.closure_versions(nodes, [key])) for key, node in nodes.items()):
        raise KernelError("engineering requirement lacks pending normative dependency")
    state = parse_state(state_raw, mode=mode, case_id=case_id)
    expected = {"schema": 1, "case_id": case_id, "mode": mode, "nodes": nodes,
                "phase_status": dict.fromkeys(PHASES, "not_started"), "accepted_versions": {},
                "history": [{"seq": 1, "action": "init", "source": str(proposal_path)}]}
    if state != expected:
        raise KernelError("state differs from exact native pending initialization")
    return state


def select_work(state: dict, limit: int = 2) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 2:
        raise KernelError("selection limit must be 1 or 2")
    if type(state) is not dict:
        raise KernelError("selection needs a parsed state")
    try:
        raw = json.dumps(state, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise KernelError("selection state is invalid") from exc
    state = parse_state(raw, mode=state.get("mode"))
    nodes, mode = state["nodes"], state["mode"]
    if mode == "risk":
        queue = [row for row in core.risk_plan(nodes)["work_queue"]
                 if row["action"] != "approve" and not row["blocked_by"]]
    else:
        dependency_ready = (lambda key: core.ready(nodes[key])) if mode == "sequential" else (
            lambda key: core.closure_ready(nodes, key))
        queue = [{"id": key, "action": "revise" if node["status"] != "supported" else "review"}
                 for key, node in nodes.items() if node["kind"] != "normative" and not core.ready(node)
                 and all(dependency_ready(dep) for dep in node["depends_on"])]
        queue.sort(key=lambda row: (PHASES.index(nodes[row["id"]]["phase"]), row["id"]))
        if mode == "sequential":
            queue = [row for row in queue if row["action"] == "revise"]
            limit = 1
    selected = []
    for row in queue:
        node_id = row["id"]
        if any(node_id in core.descendants(nodes, prior["id"])
               or prior["id"] in core.descendants(nodes, node_id) for prior in selected):
            continue
        selected.append({"id": node_id, "phase": nodes[node_id]["phase"], "action": row["action"]})
        if len(selected) == limit:
            break
    return selected


def _arguments(request, role):
    if type(request) is not dict or type(request.get("op")) is not str:
        raise KernelError("method arguments are invalid")
    op = request["op"]
    if op in {"init", "approve"}:
        raise KernelError("initialization or normative approval cannot be replayed")
    if role != "leader" and op == "advance":
        raise KernelError("worker cannot advance phases")
    if op == "revise":
        _exact(request, {"op", "id", "status", "reason"}, "revision arguments")
        _text(request["id"], "revision id")
        _text(request["reason"], "revision reason")
        if type(request["status"]) is not str or request["status"] not in core.STATUSES:
            raise KernelError("revision status is invalid")
        return [op, "--id", request["id"], "--status", request["status"], "--reason", request["reason"]]
    if op == "review":
        _exact(request, {"op", "id"}, "review arguments")
        _text(request["id"], "review id")
        return [op, "--id", request["id"]]
    if op == "advance":
        _exact(request, {"op", "phase"}, "advance arguments")
        if type(request["phase"]) is not str or request["phase"] not in PHASES:
            raise KernelError("advance phase is invalid")
        return [op, "--phase", request["phase"]]
    if op == "status":
        _exact(request, {"op"}, "status arguments")
        return [op]
    if op == "plan":
        _exact(request, {"op", "budget"}, "plan arguments")
        if type(request["budget"]) is not int or not 1 <= request["budget"] <= 64:
            raise KernelError("plan budget is invalid")
        return [op, "--budget", str(request["budget"])]
    raise KernelError("operation is outside the method replay schema")


def _operations(operations):
    if type(operations) is not list:
        raise KernelError("operations must be a list")
    previous = 0
    for row in operations:
        _exact(row, {"global_ordinal", "role", "arguments", "success"}, "operation")
        _positive(row["global_ordinal"], "global ordinal")
        if row["global_ordinal"] <= previous:
            raise KernelError("operation global ordinals are not strictly increasing")
        previous = row["global_ordinal"]
        if type(row["role"]) is not str or row["role"] not in ROLES or type(row["success"]) is not bool:
            raise KernelError("operation role or success is invalid")
        _arguments(row["arguments"], row["role"])


def apply_operations(base_raw: bytes, operations: list[dict], *, mode: str) -> bytes:
    parse_state(base_raw, mode=mode)
    _operations(operations)
    with tempfile.TemporaryDirectory(prefix="specorganon-D119-native-replay-") as folder:
        path = Path(folder) / "method_state.json"
        path.write_bytes(base_raw)
        for row in operations:
            if not row["success"]:
                continue
            args = _arguments(row["arguments"], row["role"]) + ["--state", str(path)]
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = core.run(mode, args)
            if code != 0 or stderr.getvalue():
                raise KernelError("successful operation disagrees with original core replay")
            outcome = _json(stdout.getvalue().encode("utf-8"))
            if type(outcome) is not dict or outcome.get("ok") is not True:
                raise KernelError("original core replay outcome differs")
        result = path.read_bytes()
    parse_state(result, mode=mode)
    return result


def merge_operations(base_raw: bytes, branches: list[dict], *, mode: str) -> bytes:
    base = parse_state(base_raw, mode=mode)
    if type(branches) is not list or not 1 <= len(branches) <= (1 if mode == "sequential" else 2):
        raise KernelError("branch count differs from mode selection policy")
    task_ids, owned, ordinals, global_ops = set(), set(), set(), []
    for branch in branches:
        _exact(branch, {"task_id", "owned_node_ids", "state_raw", "operations"}, "branch")
        task_id, scope = branch["task_id"], branch["owned_node_ids"]
        if type(task_id) is not str or task_id not in {"worker-1", "worker-2"} or task_id in task_ids:
            raise KernelError("branch task identity is invalid or duplicated")
        task_ids.add(task_id)
        if (type(scope) is not list or not scope or any(type(key) is not str or key not in base["nodes"] for key in scope)
                or len(set(scope)) != len(scope) or owned.intersection(scope)):
            raise KernelError("branch node ownership is invalid or overlaps")
        if any(base["nodes"][key]["kind"] == "normative" for key in scope):
            raise KernelError("normative nodes cannot be owned by workers")
        owned.update(scope)
        _operations(branch["operations"])
        for row in branch["operations"]:
            request = row["arguments"]
            if row["role"] != task_id or request["op"] not in {"revise", "review", "status", "plan"}:
                raise KernelError("branch operation role or operation differs")
            if request["op"] in {"revise", "review"} and request["id"] not in scope:
                raise KernelError("branch operation exceeds node ownership")
            if row["global_ordinal"] in ordinals:
                raise KernelError("branch global ordinal is duplicated")
            ordinals.add(row["global_ordinal"])
        replay = apply_operations(base_raw, branch["operations"], mode=mode)
        observed = parse_state(branch["state_raw"], mode=mode, case_id=base["case_id"])
        if replay != branch["state_raw"] or parse_state(replay, mode=mode) != observed:
            raise KernelError("observed branch differs from exact original core replay")
        global_ops.extend(branch["operations"])
    scopes = [branch["owned_node_ids"] for branch in branches]
    if len(scopes) == 2 and any(right in core.descendants(base["nodes"], left)
                                or left in core.descendants(base["nodes"], right)
                                for left in scopes[0] for right in scopes[1]):
        raise KernelError("worker branches are not independent")
    return apply_operations(base_raw, sorted(global_ops, key=lambda row: row["global_ordinal"]), mode=mode)
