"""Real D119 sandbox, persistent epochs, scope, metrics and fail-closed journals."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import coordinated_prototype_broker as module  # noqa: E402
import coordinated_prototype_kernel as kernel  # noqa: E402
import local_run_admission as admission  # noqa: E402
from local_replay_sandbox import probe_sandbox  # noqa: E402

GOOD = "import json\nprint(json.dumps({'public_fixture': 7, 'finite': 0.5}))\n"


class Context:
    """Explicit local test lease; model/identity/use is not authenticated."""
    def __init__(self, run, cap=32):
        self.run, self.cap = run, cap
        self.deadline = time.monotonic() + 60

    def require_active(self):
        if time.monotonic() >= self.deadline:
            raise RuntimeError("test lease expired")

    def status(self):
        self.require_active()
        return {"state": "active", "max_tool_calls": self.cap,
                "tools_reserved": len(list((self.run / "tool_reservations").glob("*.json")))}


def private(path):
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def put(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)


def source_fixture(tmp_path, mode="graph"):
    tmp_path.chmod(0o700)
    case, inputs, run = (private(tmp_path / name) for name in ("case", "inputs", "run"))
    raw = b"Public synthetic case; no normative authorization or field result.\n"
    put(case / "task.md", raw)
    put(case / "case.json", module._canonical({"case_id": "D119-PUBLIC",
        "files": [{"path": "task.md", "bytes": len(raw), "sha256": module._sha(raw)}],
        "deliverables": ["analysis.py", "report.md", "sources.json", "metrics.json"]}))
    arm = {"sequential": "A", "graph": "B", "risk": "C"}[mode]
    put(inputs / "arm_prompt", module._canonical({"alternative": arm, "mode": mode,
        "instructions": "Use original method; norms remain pending."}))
    put(inputs / "tool_policy", module._canonical({"schema": 2}))
    return run, case, inputs


def fixture(tmp_path, mode="graph", cap=32):
    run, case, inputs = source_fixture(tmp_path, mode)
    binding = module.prepare_broker(run, case, inputs, mode=mode)
    host = module.CoordinatedPrototypeBroker(run, binding)
    schedule_sha = "a" * 64
    plan = {"run_id": "dev-coord-public-fixture",
        "schedule": {"schedule_sha256": schedule_sha}, "descriptor": {"schedule_sha256": schedule_sha},
        "max_epochs": 4, "limits": {"tool_wall_seconds": 5}}
    raw = module._canonical(plan)
    put(run / "plan.json", raw)
    descriptor = admission.descriptor(tmp_path / "admission")
    owner = admission.owner("oneshot", run, run)
    claimed = admission.publish_claim(schedule_sha, plan["run_id"], owner, descriptor,
                                     override=tmp_path / "admission")
    put(run / "run.json", module._canonical({"run_id": plan["run_id"],
        "plan_sha256": module._sha(raw), "broker_binding": binding,
        "admission_descriptor": descriptor, "claim_sha256": claimed}))
    return host, Context(run, cap)


def nodes():
    rows = [
        ("p1", "problem", "philosophy", [], 10),
        ("p2", "assumption", "philosophy", [], 9),
        ("n", "normative", "philosophy", [], 8),
        ("e", "evidence", "science", ["p1", "p2"], 7),
        ("r", "requirement", "engineering", ["n", "e"], 6),
        ("v", "test_result", "validation", ["r"], 5)]
    return [{"id": key, "kind": kind, "phase": phase, "status": "pending",
             "claim": "Public fixture " + key, "depends_on": dependencies,
             "risk": {"impact": max(1, risk - 5), "uncertainty": 3, "effort": 1}}
            for key, kind, phase, dependencies, risk in rows]


def invoke(host, context, role, request, *, analyze=False, guard=None):
    prior = [row for row in host.operations() if row["task_id"] == role]
    number = len(prior) + 1
    result = host.invoke(role, f"{role}-turn-{number:04d}", {
        "name": "development_analysis" if analyze else "development_method",
        "call_id": f"call-{role}-{number:04d}",
        "arguments": json.dumps(request if analyze else {"request": json.dumps(request)})},
        context, guard or (lambda: None))
    return json.loads(result["output"])


def initialize(host, context):
    assert invoke(host, context, "leader", {"op": "init", "nodes": nodes()})["ok"]


def assignments(host):
    selected = kernel.select_work(host.public_state()["state"], limit=2)
    return [{"task_id": f"worker-{number}", "owned_node_ids": [row["id"]],
             "owned_files": module.OWNED_FILES[f"worker-{number}"]}
            for number, row in enumerate(selected, 1)]


@pytest.fixture(autouse=True)
def capability():
    result = probe_sandbox()
    if not result.available:
        pytest.skip(result.reason or "real sandbox unavailable")


@pytest.mark.parametrize("mode", ["sequential", "graph", "risk"])
def test_two_real_epochs_same_flat_stream_and_final_metrics(mode, tmp_path):
    host, context = fixture(tmp_path, mode)
    initialize(host, context)
    immutable = {path: path.read_bytes() for role in module.ROLES
                 for folder in ("case", "inputs")
                 for path in (Path(host.manifest["stages"][role]["stage_dir"]) / folder).iterdir()}
    selected = assignments(host)
    assert len(selected) == (1 if mode == "sequential" else 2)
    first = host.activate_epoch(1, selected, guard=lambda: None)
    assert first["epoch"] == 1
    for assignment in selected:
        role = assignment["task_id"]
        assert invoke(host, context, role, {"op": "revise", "id": assignment["owned_node_ids"][0],
            "status": "supported", "reason": "Synthetic positive fixture."})["ok"]
        if role == "worker-1":
            assert invoke(host, context, role, {"op": "write", "path": "analysis.py", "offset": 0,
                                               "content": GOOD})["ok"]
            assert invoke(host, context, role, {"script_sha256": module._sha(GOOD.encode())}, analyze=True)["public_fixture"] == 7
        else:
            assert invoke(host, context, role, {"op": "write", "path": "report.md", "offset": 0,
                                               "content": "Public report only.\n"})["ok"]
    merged = host.merge_epoch(1, guard=lambda: None)
    assert merged["method_state_sha256"] == host.public_state()["method_state_sha256"]
    assert host.current_metrics("leader") is None
    leader = host.leader_stage() / "work"
    assert (leader / "analysis.py").read_text() == GOOD
    selected = assignments(host)
    assert selected
    before = len(host.operations())
    host.activate_epoch(2, selected, guard=lambda: None)
    for assignment in selected:
        role, key = assignment["task_id"], assignment["owned_node_ids"][0]
        state = kernel.parse_state((Path(host.branch(role)["stage_dir"]) / "work/method_state.json").read_bytes(), mode=mode)
        if state["nodes"][key]["stale"]:
            if state["nodes"][key]["status"] == "pending":
                assert invoke(host, context, role, {"op": "revise", "id": key,
                    "status": "supported", "reason": "Supported before native stale review."})["ok"]
            outcome = invoke(host, context, role, {"op": "review", "id": key})
            assert outcome["ok"] is (mode != "sequential")
        else:
            assert invoke(host, context, role, {"op": "revise", "id": key, "status": "supported", "reason": "Epoch two."})["ok"]
    host.merge_epoch(2, guard=lambda: None)
    assert len(host.operations()) > before
    assert host.public_state()["state"]["nodes"]["n"]["status"] == "pending"
    assert invoke(host, context, "leader", {"script_sha256": module._sha(GOOD.encode())}, analyze=True)["public_fixture"] == 7
    metrics = host.current_metrics("leader")
    assert metrics["analysis_metrics_sha256"] == module._sha((leader / "metrics.json").read_bytes())
    reopened = module.CoordinatedPrototypeBroker(host.run_dir, host.binding)
    assert reopened.operations() == host.operations()
    assert reopened.current_metrics("leader") == metrics
    assert [row["global_ordinal"] for row in host.operations()] == list(range(1, len(host.operations()) + 1))
    assert all(path.read_bytes() == raw for path, raw in immutable.items())
    assert len(list((host.root / "epochs").iterdir())) == 2


@pytest.mark.parametrize("command", [
    {"op": "init", "nodes": []}, {"op": "advance", "phase": "philosophy"},
    {"op": "approve", "id": "n"}, {"op": "revise", "id": "r", "status": "supported", "reason": "wrong owner"},
    {"op": "write", "path": "report.md", "offset": 0, "content": "not owned"},
])
def test_worker_scope_rejected_before_reservation_or_effect(tmp_path, command):
    host, context = fixture(tmp_path)
    initialize(host, context)
    host.activate_epoch(1, assignments(host), guard=lambda: None)
    before = host.verify()["reservations"]
    work = module._work(Path(host.branch("worker-1")["stage_dir"]))
    with pytest.raises(module.BrokerError):
        invoke(host, context, "worker-1", command)
    assert host.verify()["reservations"] == before
    assert module._work(Path(host.branch("worker-1")["stage_dir"])) == work


def test_final_metrics_stale_after_edit_and_real_cas_error_repair(tmp_path):
    host, context = fixture(tmp_path)
    initialize(host, context)
    invoke(host, context, "leader", {"op": "write", "path": "analysis.py", "offset": 0, "content": GOOD})
    invoke(host, context, "leader", {"script_sha256": module._sha(GOOD.encode())}, analyze=True)
    assert host.current_metrics("leader")
    failure = invoke(host, context, "leader", {"op": "replace", "path": "analysis.py",
        "expected_sha256": "0"*64, "content": "print('bad')\n"})
    assert failure["analysis_status"] == "tool_failure"
    assert host.current_metrics("leader")
    assert invoke(host, context, "leader", {"op": "write", "path": "report.md", "offset": 0, "content": "Later input."})["ok"]
    assert host.current_metrics("leader") is None
    invoke(host, context, "leader", {"op": "replace", "path": "analysis.py",
        "expected_sha256": module._sha(GOOD.encode()), "content": "print('bad')\n"})
    feedback = invoke(host, context, "leader", {"script_sha256": module._sha(b"print('bad')\n")}, analyze=True)
    assert feedback["analysis_status"] == "invalid_json"
    assert not (host.leader_stage() / "work/metrics.json").exists()
    assert invoke(host, context, "leader", {"op": "replace", "path": "analysis.py",
        "expected_sha256": module._sha(b"print('bad')\n"), "content": GOOD})["ok"]
    invoke(host, context, "leader", {"script_sha256": module._sha(GOOD.encode())}, analyze=True)
    assert host.current_metrics("leader")["metrics"]["public_fixture"] == 7


@pytest.mark.parametrize("change", ["claim", "inputs", "work", "receipt", "epoch"])
def test_tamper_before_effect_keeps_tool_count(tmp_path, change):
    host, context = fixture(tmp_path)
    initialize(host, context)
    if change == "claim":
        for path in (tmp_path / "admission").rglob("*.json"):
            path.unlink()
    elif change == "inputs":
        put(host.leader_stage() / "inputs/arm_prompt", b"{}\n")
    elif change == "work":
        put(host.leader_stage() / "work/method_state.json", b"{}\n")
    elif change == "receipt":
        path = host.receipts / "0001.json"
        value = json.loads(path.read_bytes())
        value["unexpected"] = True
        put(path, module._canonical(value))
    else:
        host.activate_epoch(1, assignments(host), guard=lambda: None)
        path = host.root / "metadata/0001.json"
        value = json.loads(path.read_bytes())
        value["base_path"] = "../outside-untrusted-path"
        put(path, module._canonical(value))
    before = len(list(host.reservations.iterdir()))
    with pytest.raises((module.BrokerError, ValueError)):
        invoke(host, context, "leader", {"op": "status"})
    assert len(list(host.reservations.iterdir())) == before


def test_one_init_reviewer_no_tools_cap_and_bad_public_source_preflight(tmp_path):
    host, context = fixture(tmp_path)
    initialize(host, context)
    for role, request in (("leader", {"op": "init", "nodes": nodes()}), ("reviewer", {"op": "status"})):
        with pytest.raises(module.BrokerError):
            invoke(host, context, role, request)
    assert host.verify()["reservations"] == 1
    context.cap = 1
    with pytest.raises(module.BrokerError, match="cap"):
        invoke(host, context, "leader", {"op": "status"})
    sibling = private(tmp_path / "preflight")
    run, case, inputs = source_fixture(sibling)
    put(case / "task.md", b"tampered public source")
    with pytest.raises(module.BrokerError, match="source"):
        module.prepare_broker(run, case, inputs, mode="graph")
    assert list(run.iterdir()) == []


def test_epoch_ownership_conflict_and_crash_intent_blocks_reopen(tmp_path):
    host, context = fixture(tmp_path)
    initialize(host, context)
    selected = assignments(host)
    selected[1]["owned_files"] = selected[0]["owned_files"]
    with pytest.raises(module.BrokerError):
        host.activate_epoch(1, selected, guard=lambda: None)
    assert not (host.root / "metadata/.intent.json").exists()
    selected = assignments(host)
    calls = 0
    def fail_after_intent():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected interruption after durable host intent")
    with pytest.raises(RuntimeError, match="interruption"):
        host.activate_epoch(1, selected, guard=fail_after_intent)
    assert (host.root / "metadata/.intent.json").is_file()
    reopened = module.CoordinatedPrototypeBroker(host.run_dir, host.binding)
    with pytest.raises(module.BrokerError, match="uncertain"):
        reopened.verify()


def test_late_tool_preserves_raw_and_pending_without_relaunch(tmp_path):
    host, context = fixture(tmp_path)
    initialize(host, context)
    invoke(host, context, "leader", {"op": "write", "path": "analysis.py", "offset": 0,
        "content": "while True:\n    pass\n"})
    context.deadline = time.monotonic() + 2
    with pytest.raises((module.BrokerError, RuntimeError)):
        invoke(host, context, "leader", {"script_sha256": module._sha(b"while True:\n    pass\n")}, analyze=True)
    before = len(list(host.reservations.iterdir()))
    assert (host.broker_dir / "0003/stdout").is_file()
    reopened = module.CoordinatedPrototypeBroker(host.run_dir, host.binding)
    assert reopened.verify()["blocked"]
    assert reopened.verify()["pending"] == [3]
    with pytest.raises(module.BrokerError):
        invoke(reopened, Context(host.run_dir), "leader", {"op": "status"})
    assert len(list(host.reservations.iterdir())) == before


@pytest.mark.parametrize("mode", ["sequential", "graph", "risk"])
def test_original_advance_then_upstream_revision_keeps_native_audit(mode, tmp_path):
    host, context = fixture(tmp_path, mode)
    proposal = nodes()
    next(row for row in proposal if row["id"] == "n")["phase"] = "engineering"
    assert invoke(host, context, "leader", {"op": "init", "nodes": proposal})["ok"]
    for key in ("p1", "p2"):
        assert invoke(host, context, "leader", {"op": "revise", "id": key,
            "status": "supported", "reason": "Explicit synthetic support."})["ok"]
    assert invoke(host, context, "leader", {"op": "advance", "phase": "philosophy"})["ok"]
    assert invoke(host, context, "leader", {"op": "revise", "id": "e",
        "status": "supported", "reason": "Synthetic science fixture."})["ok"]
    if mode != "sequential":
        assert invoke(host, context, "leader", {"op": "review", "id": "e"})["ok"]
    assert invoke(host, context, "leader", {"op": "advance", "phase": "science"})["ok"]
    assert invoke(host, context, "leader", {"op": "revise", "id": "p1",
        "status": "supported", "reason": "Changed upstream premise."})["ok"]
    public = host.public_state()
    assert public["state"]["phase_status"]["philosophy"] == "needs_review"
    assert public["state"]["phase_status"]["science"] == ("accepted" if mode == "sequential" else "needs_review")
    assert public["state"]["nodes"]["n"]["status"] == "pending"
    assert bool(public["audit"]["unsafe_accepted_phases"]) is (mode == "sequential")
    assert module.CoordinatedPrototypeBroker(host.run_dir, host.binding).public_state() == public
