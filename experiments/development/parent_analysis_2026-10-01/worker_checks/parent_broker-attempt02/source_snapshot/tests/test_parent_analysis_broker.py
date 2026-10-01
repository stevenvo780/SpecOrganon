"""Real sealed bootstrap, one global journal, readonly repair and failed cuts."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import development_analysis_tool as launcher  # noqa: E402
import development_branch_tool as branch_tool  # noqa: E402
import development_method_tool as method  # noqa: E402
import local_run_admission as admission  # noqa: E402
import parallel_analysis_broker as analysis  # noqa: E402
import parallel_tool_broker as legacy  # noqa: E402
import parent_analysis_broker as parent  # noqa: E402
from c_parallel_work import select_independent_work  # noqa: E402
from local_replay_sandbox import probe_sandbox  # noqa: E402


GOOD = "import json\nprint(json.dumps({'fixture':7,'finite':0.5}))\n"
BAD = "print('ordinary malformed JSON')\n"


class Context:
    """Small broker interface; root integration uses the real shared context."""

    def __init__(self, run: Path, cap: int):
        self.run, self.cap = run, cap
        self.deadline = time.monotonic() + 120

    def require_active(self):
        if time.monotonic() >= self.deadline:
            raise RuntimeError("active lease deadline expired")

    def status(self):
        self.require_active()
        return {"state": "active", "tools_reserved": len(list((self.run / "tool_reservations").iterdir())),
                "max_tool_calls": self.cap}


def private(path):
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def put(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)


def nodes():
    return [{"id": node_id, "kind": kind, "phase": phase, "depends_on": deps,
             "status": "pending", "claim": "Public synthetic control " + node_id}
            for node_id, kind, phase, deps in (
                ("P1", "problem", "philosophy", []), ("P2", "assumption", "philosophy", []),
                ("N", "normative", "philosophy", ["P1"]), ("E", "evidence", "science", ["P1"]),
                ("R", "requirement", "engineering", ["E", "N"]), ("V", "test_result", "validation", ["R"]))]


def fixture(tmp_path, *, cap=20, wall=5, analyzer=True):
    tmp_path.chmod(0o700)
    root = private(tmp_path / "run-stages")
    leader = private(root / "leader")
    case, inputs, work = (private(leader / name) for name in ("case", "inputs", "work"))
    public = b"Public fixture only; no field result.\n"
    put(case / "task.md", public)
    put(case / "case.json", legacy._canonical({"case_id": "D117-public", "files": [{
        "path": "task.md", "bytes": len(public), "sha256": legacy._sha(public)}],
        "deliverables": ["analysis.py", "report.md", "sources.json", "metrics.json"]}))
    put(inputs / "arm_prompt", legacy._canonical({"alternative": "C", "mode": "risk",
        "instructions": "Mechanical fixture; normative acceptance stays pending."}))
    put(inputs / "tool_policy", legacy._canonical({"schema": 2}))
    put(leader / "stage.json", legacy._canonical({"schema": "parent_empty_leader.v1", "task_id": "leader"}))
    method_path, analyzer_path = root / "leader-method.py", root / "analysis-tool.py"
    method.build_tool(method_path)
    launcher.build_analysis_tool(analyzer_path)
    functions = [{"name": "method", "profile": "workspace", "executable": str(method_path)}]
    if analyzer:
        functions.append({"name": "analyze", "profile": "analysis_readonly", "executable": str(analyzer_path)})
    slots = []
    for task in ("task-1", "task-2"):
        stage = private(root / task)
        private(stage / "work")
        slots.append({"task_id": task, "stage_dir": str(stage)})
    binding = parent.prepare_parent_broker_manifest(root, {
        "task_id": "leader", "stage_dir": str(leader), "functions": functions}, slots)
    assert list(work.iterdir()) == []
    assert not (root / analysis.MANIFEST_NAME).exists()
    run = private(tmp_path / "run")
    for name in ("broker", "tool_reservations", "tool_receipts"):
        private(run / name)
    plan = {"schema": 1, "run_id": "D117-public", "bootstrap_manifest": binding,
            "tool_wall_seconds": wall}
    raw = legacy._canonical(plan)
    put(run / "plan.json", raw)
    descriptor = admission.descriptor(tmp_path / "admission")
    owner = admission.owner("oneshot", run, run)
    plan_sha = legacy._sha(raw)
    claim_sha = admission.claim_digest(plan_sha, plan["run_id"], owner, descriptor)
    put(run / "run.json", legacy._canonical({"schema": 1, "run_id": plan["run_id"],
        "plan_sha256": plan_sha, "admission_descriptor": descriptor, "claim_sha256": claim_sha}))
    assert admission.publish_claim(plan_sha, plan["run_id"], owner, descriptor,
                                   override=tmp_path / "admission") == claim_sha
    return parent.ParentAnalysisBroker(run, binding), Context(run, cap)


@pytest.fixture(autouse=True)
def sandbox():
    result = probe_sandbox()
    if not result.available:
        pytest.skip(result.reason)


def invoke(host, context, request=None, *, task="leader", source=None, call_id=None, guard=None):
    ordinal = len(list(host.reservations.iterdir())) + 1
    call = {"name": "method" if source is None else "analyze",
            "call_id": call_id or f"call-{ordinal}",
            "arguments": json.dumps({"request": json.dumps(request)} if source is None else
                                    {"script_sha256": legacy._sha(source.encode())})}
    return host.invoke(task, f"{task}-turn-{ordinal:04d}", call, context, guard or (lambda: None))


def init(host, context):
    result = invoke(host, context, {"op": "init", "nodes": nodes()})
    assert json.loads(result["output"])["ok"] is True


def write(host, context, source, *, task="task-1", path="analysis.py"):
    return invoke(host, context, {"op": "write", "path": path, "offset": 0, "content": source}, task=task)


def transition(host, *, seed=b"", owned=None):
    snap = host.bootstrap_snapshot()
    root = Path(host.manifest["root"])
    leader = Path(snap["stage_dir"])
    selected = select_independent_work(snap["state"], 2)
    specs = []
    for slot, entry in zip(host.manifest["bootstrap"]["slots"], selected, strict=True):
        task, stage = slot["task_id"], Path(slot["stage_dir"])
        for name in ("case", "inputs"):
            directory = private(stage / name)
            for path in (leader / name).iterdir():
                put(directory / path.name, path.read_bytes())
        put(stage / "work/method_state.json", seed or (leader / "work/method_state.json").read_bytes())
        owned_ids = [owned or entry["id"]]
        put(stage / "stage.json", legacy._canonical({"task_id": task, "owned_node_ids": owned_ids}))
        executable = root / f"{task}-method.py"
        branch_tool.build_branch_tool(executable, owned_ids)
        specs.append({"task_id": task, "stage_dir": str(stage), "owned_node_ids": owned_ids,
            "functions": [{"name": "method", "profile": "workspace", "executable": str(executable)},
                          {"name": "analyze", "profile": "analysis_readonly", "executable": str(root / "analysis-tool.py")}]})
    binding = analysis.prepare_analysis_branch_manifest(root, specs)
    descriptor = {key: snap[key] for key in ("bootstrap_manifest", "first_worker_ordinal",
                                             "leader_work_sha256", "leader_state_sha256")}
    put(root / "metadata/transition.json", legacy._canonical({"schema": "fixture_cut.v1", **descriptor,
                                                             "branch_manifest": binding}))
    return binding


def activate(host, context):
    binding = transition(host)
    assert host.verify()["blocked"] is True
    return host.activate(binding, context, lambda: None)


def test_real_init_shared_ordinals_fresh_metrics_and_reopen(tmp_path):
    host, context = fixture(tmp_path)
    roots = host.journal_roots()
    claim = host._state_claim()
    init(host, context)
    assert host.operations()[0]["terminal"]["schema"] == 1
    assert host.bootstrap_snapshot()["first_worker_ordinal"] == 2
    marker = activate(host, context)
    assert host.journal_roots() == roots
    assert host._state_claim() == claim
    for task in ("task-1", "task-2"):
        write(host, context, GOOD, task=task)
        invoke(host, context, task=task, source=GOOD)
        assert host.current_metrics(task)["metrics"]["fixture"] == 7
    operations = host.operations()
    assert [op["global_ordinal"] for op in operations] == [1, 2, 3, 4, 5]
    assert [op["phase"] for op in operations] == ["bootstrap", "wave", "wave", "wave", "wave"]
    assert [op["terminal"]["schema"] for op in operations] == [1, 1, 2, 1, 2]
    assert all(op["terminal"]["manifest_sha256"] == host.sha256 for op in operations)
    assert all(op["terminal"]["claim_sha256"] == claim for op in operations)
    view = host.wave_view()
    assert len(view.operations()) == 4
    assert view.current_metrics("task-2")["global_ordinal"] == 5
    assert legacy._sha(Path(marker["path"]).read_bytes()) == marker["sha256"]
    program = ("import json,sys;sys.path.insert(0,sys.argv[1]);"
               "from parent_analysis_broker import ParentAnalysisBroker;from pathlib import Path;"
               "b=ParentAnalysisBroker(Path(sys.argv[2]),json.loads(sys.argv[3]));"
               "print(json.dumps({'report':b.verify(),'metrics':b.current_metrics('task-1')}))")
    process = subprocess.run([sys.executable, "-B", "-I", "-c", program, str(SCRIPTS),
                              str(host.run_dir), json.dumps(host.binding)], capture_output=True, timeout=30)
    assert process.returncode == 0, process.stderr.decode()
    observed = json.loads(process.stdout)
    assert observed["report"]["receipts"] == 5
    assert observed["metrics"]["global_ordinal"] == 3


@pytest.mark.parametrize("op", ["revise", "review", "advance", "approve", "analyze"])
def test_bootstrap_authority_ops_rejected_before_reservation(tmp_path, op):
    host, context = fixture(tmp_path)
    with pytest.raises(parent.BrokerError, match="allowlist"):
        invoke(host, context, {"op": op})
    assert host.verify()["reservations"] == 0
    assert list((Path(host.branch("leader")["stage_dir"]) / "work").iterdir()) == []


def test_wrong_phase_duplicate_init_and_global_call_ids(tmp_path):
    host, context = fixture(tmp_path)
    with pytest.raises(parent.BrokerError, match="unknown|phase"):
        invoke(host, context, {"op": "status"}, task="task-1")
    init(host, context)
    with pytest.raises(parent.BrokerError, match="already reserved"):
        init(host, context)
    activate(host, context)
    with pytest.raises(parent.BrokerError, match="phase"):
        invoke(host, context, {"op": "status"})
    with pytest.raises(parent.BrokerError, match="already reserved"):
        invoke(host, context, {"op": "status"}, task="task-1", call_id="call-1")
    assert host.verify()["receipts"] == 1


def test_missing_or_invalid_real_init_cannot_make_transition(tmp_path):
    host, context = fixture(tmp_path)
    with pytest.raises(parent.BrokerError, match="exactly one"):
        host.bootstrap_snapshot()
    result = invoke(host, context, {"op": "init", "nodes": []})
    assert json.loads(result["output"])["ok"] is False
    assert host.verify()["receipts"] == 1
    with pytest.raises(parent.BrokerError, match="failed"):
        host.bootstrap_snapshot()


@pytest.mark.parametrize("bad", [BAD, "print('{}')\nraise SystemExit(3)\n"])
def test_analysis_repair_retirement_and_full_input_freshness(tmp_path, bad):
    host, context = fixture(tmp_path)
    init(host, context)
    activate(host, context)
    write(host, context, bad)
    failure = invoke(host, context, task="task-1", source=bad)
    assert json.loads(failure["output"])["analysis_status"] in {"invalid_json", "participant_failed"}
    assert host.current_metrics("task-1") is None
    repaired = invoke(host, context, {"op": "replace", "path": "analysis.py",
        "expected_sha256": legacy._sha(bad.encode()), "content": GOOD}, task="task-1")
    assert json.loads(repaired["output"])["ok"] is True
    invoke(host, context, task="task-1", source=GOOD)
    assert host.current_metrics("task-1")["global_ordinal"] == 5
    write(host, context, "Report changed an analysis input.\n", path="report.md")
    assert host.current_metrics("task-1") is None
    invoke(host, context, task="task-1", source=GOOD)
    assert host.current_metrics("task-1")["global_ordinal"] == 7
    invoke(host, context, {"op": "replace", "path": "analysis.py",
        "expected_sha256": legacy._sha(GOOD.encode()), "content": BAD}, task="task-1")
    invoke(host, context, task="task-1", source=BAD)
    assert host.current_metrics("task-1") is None
    assert not (Path(host.branch("task-1")["stage_dir"]) / "work/metrics.json").exists()
    assert host.verify()["receipts"] == 9


def test_common_cap_includes_bootstrap(tmp_path):
    host, context = fixture(tmp_path, cap=1)
    init(host, context)
    activate(host, context)
    with pytest.raises(parent.BrokerError, match="cap"):
        write(host, context, GOOD)
    assert host.verify()["reservations"] == 1


@pytest.mark.parametrize("target", ["transition", "activation", "seed", "stream"])
def test_phase_or_seed_or_stream_tamper_prevents_replay(tmp_path, target):
    host, context = fixture(tmp_path)
    init(host, context)
    activate(host, context)
    root = Path(host.manifest["root"])
    if target in {"activation", "transition"}:
        path = root / "metadata" / f"{target}.json"
    elif target == "seed":
        path = Path(host.branch("leader")["stage_dir"]) / "work/method_state.json"
    else:
        path = host.broker_dir / "0001/stdout"
    put(path, path.read_bytes() + b" ")
    with pytest.raises((parent.BrokerError, ValueError)):
        parent.ParentAnalysisBroker(host.run_dir, host.binding).verify()


def test_transition_and_intent_crash_are_blocked_on_reopen(tmp_path):
    host, context = fixture(tmp_path)
    init(host, context)
    binding = transition(host)
    reopened = parent.ParentAnalysisBroker(host.run_dir, host.binding)
    assert reopened.verify()["blocked"] is True
    with pytest.raises(parent.BrokerError, match="uncertain"):
        reopened.activate(binding, context, lambda: None)
    with pytest.raises(parent.BrokerError, match="blocks"):
        invoke(reopened, context, {"op": "status"})

    def revoke_after_intent():
        if (Path(host.manifest["root"]) / "metadata/activation_intent.json").exists():
            raise RuntimeError("simulated crash after durable intent")

    with pytest.raises(RuntimeError, match="durable intent"):
        host.activate(binding, context, revoke_after_intent)
    reopened = parent.ParentAnalysisBroker(host.run_dir, host.binding)
    assert reopened.verify()["blocked"] is True
    with pytest.raises(parent.BrokerError, match="uncertain"):
        reopened.activate(binding, context, lambda: None)
    assert not (Path(host.manifest["root"]) / "metadata/activation.json").exists()


@pytest.mark.parametrize("source", ["import time\ntime.sleep(5)\n", "import os\nos.abort()\n"])
def test_timeout_and_signal_leave_global_reservation_blocked(tmp_path, source):
    host, context = fixture(tmp_path, wall=0.25)
    init(host, context)
    activate(host, context)
    write(host, context, source)
    with pytest.raises(parent.BrokerError, match="uncertain"):
        invoke(host, context, task="task-1", source=source)
    reopened = parent.ParentAnalysisBroker(host.run_dir, host.binding)
    assert reopened.verify()["pending"] == [3]
    assert reopened.verify()["blocked"] is True
    with pytest.raises(parent.BrokerError):
        reopened.current_metrics("task-1")


def test_seed_mismatch_rejects_activation_without_intent(tmp_path):
    host, context = fixture(tmp_path)
    init(host, context)
    binding = transition(host, seed=b"{}\n")
    with pytest.raises(parent.BrokerError, match="seed"):
        host.activate(binding, context, lambda: None)
    assert not (Path(host.manifest["root"]) / "metadata/activation_intent.json").exists()


def test_optional_leader_analysis_keeps_real_bootstrap_inventory(tmp_path):
    host, context = fixture(tmp_path)
    init(host, context)
    write(host, context, GOOD, task="leader")
    invoke(host, context, task="leader", source=GOOD)
    assert host.current_metrics("leader")["global_ordinal"] == 3
    assert host.bootstrap_snapshot()["first_worker_ordinal"] == 4
    activate(host, context)
    assert host.current_metrics("leader")["global_ordinal"] == 3
    assert host.wave_view().operations() == []
