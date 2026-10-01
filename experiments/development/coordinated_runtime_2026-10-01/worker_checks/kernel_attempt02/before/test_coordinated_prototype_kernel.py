from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import coordinated_prototype_kernel as kernel


def node(node_id, phase, deps=(), *, kind="evidence", status="pending", risk=None):
    row = {"id": node_id, "phase": phase, "kind": kind, "status": status,
           "claim": f"Public claim {node_id}", "depends_on": list(deps)}
    if risk is not None:
        row["risk"] = risk
    return row


def proposal(*, supported=False, normative=True):
    status = "supported" if supported else "pending"
    nodes = [node("p", "philosophy", status=status),
             node("s", "science", ("p",), status=status),
             node("e", "engineering", ("s",), kind="requirement", status=status),
             node("v", "validation", ("e",), kind="test_result", status=status)]
    if normative:
        nodes.append(node("n", "philosophy", kind="normative"))
        nodes[2]["depends_on"].append("n")
    return {"case_id": "case-real", "nodes": nodes}


def initialize(tmp_path, mode, case=None):
    case = proposal() if case is None else case
    source = tmp_path / "proposal.json"
    source.write_text(json.dumps(case), encoding="utf-8")
    path = tmp_path / "method_state.json"
    with contextlib.redirect_stdout(io.StringIO()):
        assert kernel.core.run(mode, ["init", "--case", str(source), "--state", str(path)]) == 0
    return path.read_bytes(), source


def row(ordinal, request, *, role="leader", success=True):
    return {"global_ordinal": ordinal, "role": role, "arguments": request, "success": success}


def revision(node_id, *, status="supported", reason="public source checked"):
    return {"op": "revise", "id": node_id, "status": status, "reason": reason}


def encode(state):
    return (json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


@pytest.mark.parametrize("mode", kernel.MODES)
def test_exact_pending_initialization_and_norm_dependency(tmp_path, mode):
    case = proposal()
    raw, source = initialize(tmp_path, mode, case)
    state = kernel.validate_initialization(case, raw, mode=mode, case_id="case-real", proposal_path=source)
    assert state["mode"] == mode
    assert kernel.core.audit(state)["pending_normative"] == ["n"]
    assert set(state["phase_status"].values()) == {"not_started"}
    with pytest.raises(kernel.KernelError, match="exact native"):
        kernel.validate_initialization(case, raw, mode=mode, case_id="case-real", proposal_path=source.parent / "other.json")


@pytest.mark.parametrize("change", ["supported", "no_norm", "no_requirement", "extra_field"])
def test_initialization_rejects_nonpending_or_no_engineering_dependency(tmp_path, change):
    case = proposal()
    if change == "supported":
        case["nodes"][0]["status"] = "supported"
    elif change == "no_norm":
        case["nodes"][-1]["kind"] = "assumption"
    elif change == "no_requirement":
        case["nodes"][2]["kind"] = "evidence"
    else:
        case["nodes"][0]["hidden"] = "answer"
    raw, source = initialize(tmp_path, "risk", case)
    with pytest.raises(kernel.KernelError):
        kernel.validate_initialization(case, raw, mode="risk", case_id="case-real", proposal_path=source)


@pytest.mark.parametrize("mode", kernel.MODES)
def test_revise_downstream_has_no_phase_permission_gate(tmp_path, mode):
    raw, _ = initialize(tmp_path, mode)
    state = kernel.parse_state(kernel.apply_operations(raw, [row(3, revision("v"))], mode=mode), mode=mode)
    assert state["nodes"]["v"]["status"] == "supported"
    assert set(state["phase_status"].values()) == {"not_started"}


@pytest.mark.parametrize("mode,success", [("sequential", False), ("graph", False), ("risk", True)])
def test_advance_preserves_native_prior_phase_rule(tmp_path, mode, success):
    raw, _ = initialize(tmp_path, mode, proposal(supported=True, normative=False))
    op = row(7, {"op": "advance", "phase": "validation"}, success=success)
    result = kernel.apply_operations(raw, [op], mode=mode)
    state = kernel.parse_state(result, mode=mode)
    assert state["phase_status"]["validation"] == ("accepted" if success else "not_started")
    if not success:
        with pytest.raises(kernel.KernelError, match="core replay"):
            kernel.apply_operations(raw, [{**op, "success": True}], mode=mode)
        assert result == raw


def test_a_local_advance_and_unsafe_audit_remain_observable(tmp_path):
    raw, _ = initialize(tmp_path, "sequential", proposal(supported=True, normative=False))
    ops = [row(i + 1, {"op": "advance", "phase": phase}) for i, phase in enumerate(kernel.PHASES)]
    accepted = kernel.apply_operations(raw, ops, mode="sequential")
    result = kernel.apply_operations(accepted, [row(9, revision("p", status="contradicted"))], mode="sequential")
    state = kernel.parse_state(result, mode="sequential")
    assert state["phase_status"]["philosophy"] == "needs_review"
    assert state["phase_status"]["validation"] == "accepted"
    assert state["nodes"]["s"]["stale"] is False
    assert kernel.core.audit(state)["unsafe_accepted_phases"] == ["science", "engineering", "validation"]


@pytest.mark.parametrize("mode", ["graph", "risk"])
def test_descendant_invalidation_and_review_preserve_phase_ids(tmp_path, mode):
    raw, _ = initialize(tmp_path, mode, proposal(supported=True, normative=False))
    accepted = kernel.apply_operations(raw, [row(i + 1, {"op": "advance", "phase": phase})
                                             for i, phase in enumerate(kernel.PHASES)], mode=mode)
    stale_raw = kernel.apply_operations(accepted, [row(8, revision("p"))], mode=mode)
    state = kernel.parse_state(stale_raw, mode=mode)
    assert set(state["phase_status"].values()) == {"needs_review"}
    assert kernel.core.audit(state)["stale_nodes"] == ["e", "s", "v"]
    assert kernel.select_work(state) == [{"id": "s", "phase": "science", "action": "review"}]
    with pytest.raises(kernel.KernelError, match="core replay"):
        kernel.apply_operations(stale_raw, [row(9, {"op": "review", "id": "v"})], mode=mode)
    refreshed = kernel.apply_operations(stale_raw, [row(10, {"op": "review", "id": "s"}),
                                                   row(11, {"op": "review", "id": "e"}),
                                                   row(12, {"op": "review", "id": "v"})], mode=mode)
    assert kernel.core.audit(kernel.parse_state(refreshed, mode=mode))["stale_nodes"] == []
    assert kernel.parse_state(refreshed, mode=mode)["phase_status"]["science"] == "needs_review"


def test_a_review_denied_has_no_effect(tmp_path):
    raw, _ = initialize(tmp_path, "sequential")
    op = row(2, {"op": "review", "id": "s"}, success=False)
    assert kernel.apply_operations(raw, [op], mode="sequential") == raw
    with pytest.raises(kernel.KernelError, match="core replay"):
        kernel.apply_operations(raw, [{**op, "success": True}], mode="sequential")


@pytest.mark.parametrize("mode", kernel.MODES)
def test_selection_singleton_empty_and_pending_norm_has_no_actor(tmp_path, mode):
    raw, _ = initialize(tmp_path, mode)
    state = kernel.parse_state(raw, mode=mode)
    assert kernel.select_work(state) == [{"id": "p", "phase": "philosophy", "action": "revise"}]
    ops = [row(1, revision("p")), row(2, revision("s"))]
    if mode != "sequential":
        ops.append(row(3, {"op": "review", "id": "s"}))
    state = kernel.parse_state(kernel.apply_operations(raw, ops, mode=mode), mode=mode)
    assert kernel.select_work(state) == []
    assert state["nodes"]["n"]["status"] == "pending"


@pytest.mark.parametrize("mode,ids", [("sequential", ["a"]), ("graph", ["a", "z"]), ("risk", ["z", "a"])])
def test_adapter_selection_order_distinct_from_risk_score(tmp_path, mode, ids):
    case = proposal(normative=False)
    case["nodes"][0]["id"] = "a"
    case["nodes"][1]["depends_on"] = ["a"]
    case["nodes"][0]["risk"] = {"impact": 1, "uncertainty": 1, "effort": 5}
    case["nodes"].append(node("z", "validation", risk={"impact": 5, "uncertainty": 5, "effort": 1}))
    raw, _ = initialize(tmp_path, mode, case)
    selected = kernel.select_work(kernel.parse_state(raw, mode=mode))
    assert [entry["id"] for entry in selected] == ids
    assert all(set(entry) == {"id", "phase", "action"} for entry in selected)


@pytest.mark.parametrize("mode,expected", [("sequential", ["v"]), ("graph", []), ("risk", [])])
def test_a_local_readiness_is_not_transitive_closure(tmp_path, mode, expected):
    case = proposal(supported=True, normative=False)
    case["nodes"][0]["status"] = "contradicted"
    case["nodes"][0]["depends_on"] = ["v"]
    # Keep a DAG while making v depend on ready e whose ancestor s is blocked.
    case["nodes"][1]["status"] = "contradicted"
    case["nodes"][1]["depends_on"] = []
    case["nodes"][1]["kind"] = "normative"
    case["nodes"][1]["status"] = "pending"
    case["nodes"][3]["status"] = "pending"
    raw, _ = initialize(tmp_path, mode, case)
    assert [entry["id"] for entry in kernel.select_work(kernel.parse_state(raw, mode=mode))] == expected


@pytest.mark.parametrize("mutation", ["approved", "cycle", "version", "stale", "phase", "snapshot", "history", "mode", "bool_schema", "extra", "risk"])
def test_parser_rejects_shape_graph_and_history_tamper(tmp_path, mutation):
    raw, _ = initialize(tmp_path, "graph")
    state = json.loads(raw)
    if mutation == "approved":
        state["nodes"]["n"]["status"] = "approved"
    elif mutation == "cycle":
        state["nodes"]["p"]["depends_on"] = ["v"]
    elif mutation == "version":
        state["nodes"]["p"]["version"] = 2
    elif mutation == "stale":
        state["nodes"]["s"]["stale"] = True
    elif mutation == "phase":
        state["phase_status"]["engineering"] = "accepted"
    elif mutation == "snapshot":
        state["accepted_versions"]["philosophy"] = {"p": 1}
    elif mutation == "history":
        state["history"][0]["seq"] = True
    elif mutation == "mode":
        state["mode"] = "risk"
    elif mutation == "bool_schema":
        state["schema"] = True
    elif mutation == "risk":
        state["nodes"]["p"]["risk"]["impact"] = True
    else:
        state["authority"] = True
    with pytest.raises(kernel.KernelError):
        kernel.parse_state(encode(state), mode="graph")


@pytest.mark.parametrize("raw", [b'{"schema":1,"schema":1}', b'{"x":NaN}', b'\xff', b'[]', b'x' * (kernel.MAX_STATE_BYTES + 1)])
def test_strict_json_bytes(raw):
    with pytest.raises(kernel.KernelError):
        kernel.parse_state(raw, mode="risk")


@pytest.mark.parametrize("bad", ["ordinal", "order", "role", "success", "approve", "init", "worker_advance", "extra_args", "extra_row"])
def test_replay_rejects_ambiguous_operations(tmp_path, bad):
    raw, _ = initialize(tmp_path, "risk")
    ops = [row(4, revision("p"))]
    if bad == "ordinal":
        ops[0]["global_ordinal"] = True
    elif bad == "order":
        ops.append(row(3, revision("s")))
    elif bad == "role":
        ops[0]["role"] = "reviewer"
    elif bad == "success":
        ops[0]["success"] = 1
    elif bad in {"approve", "init"}:
        ops[0]["arguments"] = {"op": bad, "id": "n"}
    elif bad == "worker_advance":
        ops[0].update(role="worker-1", arguments={"op": "advance", "phase": "philosophy"})
    elif bad == "extra_args":
        ops[0]["arguments"]["phase_permission"] = True
    else:
        ops[0]["claimed_authority"] = True
    with pytest.raises(kernel.KernelError):
        kernel.apply_operations(raw, ops, mode="risk")


def branch(base, mode, task_id, scope, ops):
    return {"task_id": task_id, "owned_node_ids": scope,
            "state_raw": kernel.apply_operations(base, ops, mode=mode), "operations": ops}


@pytest.mark.parametrize("mode", ["graph", "risk"])
def test_merge_global_order_and_multiple_cycles_with_phase_invalidation(tmp_path, mode):
    case = proposal(supported=True, normative=False)
    case["nodes"].append(node("q", "philosophy", status="supported"))
    raw, _ = initialize(tmp_path, mode, case)
    base = kernel.apply_operations(raw, [row(i + 1, {"op": "advance", "phase": phase})
                                         for i, phase in enumerate(kernel.PHASES)], mode=mode)
    first = branch(base, mode, "worker-1", ["p"], [row(12, revision("p"), role="worker-1")])
    second = branch(base, mode, "worker-2", ["q"], [row(7, revision("q"), role="worker-2")])
    merged = kernel.merge_operations(base, [first, second], mode=mode)
    state = kernel.parse_state(merged, mode=mode)
    assert [entry["node"] for entry in state["history"][-2:]] == ["q", "p"]
    assert set(state["phase_status"].values()) == {"needs_review"}
    next_branch = branch(merged, mode, "worker-1", ["s"], [row(20, {"op": "review", "id": "s"}, role="worker-1")])
    second_merge = kernel.merge_operations(merged, [next_branch], mode=mode)
    assert kernel.parse_state(second_merge, mode=mode)["nodes"]["s"]["stale"] is False
    assert len(kernel.parse_state(second_merge, mode=mode)["history"]) == len(state["history"]) + 1


def test_a_merge_preserves_local_invalidation(tmp_path):
    raw, _ = initialize(tmp_path, "sequential", proposal(supported=True, normative=False))
    base = kernel.apply_operations(raw, [row(i + 1, {"op": "advance", "phase": phase})
                                         for i, phase in enumerate(kernel.PHASES)], mode="sequential")
    worker = branch(base, "sequential", "worker-1", ["p"], [row(9, revision("p"), role="worker-1")])
    merged = kernel.merge_operations(base, [worker], mode="sequential")
    assert kernel.core.audit(kernel.parse_state(merged, mode="sequential"))["unsafe_accepted_phases"]


@pytest.mark.parametrize("bad", ["ownership", "role", "scope_overlap", "ordinal_overlap", "bytes", "state", "dependent", "actor"])
def test_merge_rejects_ownership_order_and_observed_tamper(tmp_path, bad):
    case = proposal(normative=False)
    case["nodes"].append(node("q", "philosophy"))
    raw, _ = initialize(tmp_path, "risk", case)
    one = branch(raw, "risk", "worker-1", ["p"], [row(2, revision("p"), role="worker-1")])
    two = branch(raw, "risk", "worker-2", ["q"], [row(4, revision("q"), role="worker-2")])
    if bad == "ownership":
        one["owned_node_ids"] = ["q"]
    elif bad == "role":
        one["operations"][0]["role"] = "leader"
    elif bad == "scope_overlap":
        two["owned_node_ids"] = ["p", "q"]
    elif bad == "ordinal_overlap":
        two["operations"][0]["global_ordinal"] = 2
    elif bad == "bytes":
        one["state_raw"] += b" "
    elif bad == "state":
        altered = json.loads(one["state_raw"])
        altered["nodes"]["p"]["claim"] = "altered claim"
        one["state_raw"] = encode(altered)
    elif bad == "dependent":
        two = branch(raw, "risk", "worker-2", ["s"], [row(4, revision("s"), role="worker-2")])
    else:
        one["task_id"] = "phantom"
    with pytest.raises(kernel.KernelError):
        kernel.merge_operations(raw, [one, two], mode="risk")


@pytest.mark.parametrize("mode", kernel.MODES)
def test_status_and_plan_keep_original_mode_and_bytes(tmp_path, mode):
    raw, _ = initialize(tmp_path, mode)
    assert kernel.apply_operations(raw, [row(1, {"op": "status"})], mode=mode) == raw
    if mode == "risk":
        assert kernel.apply_operations(raw, [row(3, {"op": "plan", "budget": 2})], mode=mode) == raw
    else:
        with pytest.raises(kernel.KernelError):
            kernel.apply_operations(raw, [row(3, {"op": "plan", "budget": 2})], mode=mode)


def test_original_core_bytes_are_not_modified(tmp_path):
    before = kernel.CORE_PATH.read_bytes()
    raw, _ = initialize(tmp_path, "risk")
    kernel.apply_operations(raw, [row(1, revision("p"))], mode="risk")
    assert kernel.CORE_PATH.read_bytes() == before


@pytest.mark.parametrize("limit", [0, 3, True, "2"])
def test_selection_rejects_invalid_limits(tmp_path, limit):
    raw, _ = initialize(tmp_path, "risk")
    with pytest.raises(kernel.KernelError):
        kernel.select_work(kernel.parse_state(raw, mode="risk"), limit=limit)


def test_forged_snapshot_after_legitimate_invalidation_is_rejected(tmp_path):
    raw, _ = initialize(tmp_path, "graph", proposal(supported=True, normative=False))
    raw = kernel.apply_operations(raw, [row(i + 1, {"op": "advance", "phase": phase})
                                        for i, phase in enumerate(kernel.PHASES)], mode="graph")
    raw = kernel.apply_operations(raw, [row(8, revision("p"))], mode="graph")
    state = kernel.parse_state(raw, mode="graph")
    altered = copy.deepcopy(state)
    altered["accepted_versions"]["science"]["p"] = 2
    with pytest.raises(kernel.KernelError, match="native history"):
        kernel.parse_state(encode(altered), mode="graph")


@pytest.mark.parametrize("mode,success", [("sequential", True), ("graph", False), ("risk", False)])
def test_advance_a_local_readiness_versus_b_c_closure(tmp_path, mode, success):
    case = proposal(supported=True, normative=False)
    case["nodes"][1]["depends_on"] = ["v"]
    case["nodes"][3].update(kind="normative", status="pending", depends_on=[])
    raw, _ = initialize(tmp_path, mode, case)
    base = kernel.apply_operations(raw, [row(1, {"op": "advance", "phase": "philosophy"})], mode=mode)
    request = {"op": "advance", "phase": "science"}
    if success:
        result = kernel.apply_operations(base, [row(2, request)], mode=mode)
        state = kernel.parse_state(result, mode=mode)
        assert state["phase_status"]["science"] == "accepted"
        assert kernel.core.audit(state)["unsafe_accepted_phases"] == ["science"]
    else:
        with pytest.raises(kernel.KernelError, match="core replay"):
            kernel.apply_operations(base, [row(2, request)], mode=mode)
        assert kernel.apply_operations(base, [row(2, request, success=False)], mode=mode) == base


def test_malformed_cli_like_value_fails_closed(tmp_path):
    raw, _ = initialize(tmp_path, "risk")
    with pytest.raises(kernel.KernelError, match="could not execute"):
        kernel.apply_operations(raw, [row(1, revision("p", reason="--not-an-option"))], mode="risk")
