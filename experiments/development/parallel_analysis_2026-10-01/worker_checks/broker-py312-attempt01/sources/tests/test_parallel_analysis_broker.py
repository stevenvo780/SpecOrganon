"""Real read-only analysis, CAS repair, provenance, and blocked-effect replay."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import development_analysis_tool as launcher  # noqa: E402
import development_method_tool as method  # noqa: E402
import local_run_admission as admission  # noqa: E402
import parallel_analysis_broker as analysis  # noqa: E402
import parallel_tool_broker as legacy  # noqa: E402
from local_replay_sandbox import probe_sandbox  # noqa: E402


GOOD = b"import json\nprint(json.dumps({'measured_fixture': 7, 'finite': 0.5}))\n"


class Context:
    def __init__(self, run_dir: Path, cap: int):
        self.run_dir, self.cap, self.active = run_dir, cap, True
        self.deadline = time.monotonic() + 60

    def require_active(self) -> None:
        if not self.active or time.monotonic() >= self.deadline:
            raise RuntimeError("inactive context")

    def status(self) -> dict:
        self.require_active()
        return {"state": "active", "tools_reserved":
                len(list((self.run_dir / "tool_reservations").glob("*.json"))),
                "max_tool_calls": self.cap}


def private(path: Path) -> Path:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def put(path: Path, raw: bytes) -> None:
    path.write_bytes(raw)
    path.chmod(0o600)


def fixture(tmp_path: Path, *, source: bytes = GOOD, cap: int = 8,
            wall: float = 5) -> tuple[analysis.AnalysisParallelToolBroker, Context]:
    tmp_path.chmod(0o700)
    root = private(tmp_path / "branches")
    executable = root / "method"
    method.build_tool(executable)
    analyzer = root / "analyzer"
    launcher.build_analysis_tool(analyzer)
    specs = []
    for number in (1, 2):
        stage = private(root / f"task-{number}")
        case, inputs, work = (private(stage / name) for name in ("case", "inputs", "work"))
        public = b"Public fixture only; no field evidence.\n"
        put(case / "task.md", public)
        put(case / "case.json", legacy._canonical({"case_id": "D116-PUBLIC", "files": [{
            "path": "task.md", "bytes": len(public), "sha256": legacy._sha(public)}],
            "deliverables": ["analysis.py", "metrics.json", "report.md", "sources.json"]}))
        put(inputs / "arm_prompt", legacy._canonical({"alternative": "C", "mode": "risk",
            "instructions": "Keep all empirical and human acceptance pending."}))
        put(inputs / "tool_policy", legacy._canonical({"schema": 2}))
        put(stage / "stage.json", legacy._canonical({"task_id": f"task-{number}"}))
        put(work / "analysis.py", source)
        specs.append({"task_id": f"task-{number}", "owned_node_ids": [f"node-{number}"],
            "stage_dir": stage, "functions": [
                {"name": "method", "executable": executable, "profile": "workspace"},
                {"name": "analyze", "executable": analyzer, "profile": "analysis_readonly"}]})
    binding = analysis.prepare_analysis_branch_manifest(root, specs)
    run_dir = private(tmp_path / "run")
    for name in ("broker", "tool_reservations", "tool_receipts"):
        private(run_dir / name)
    plan = {"schema": 2, "run_id": "d116-public", "branch_manifest": binding, "tool_wall_seconds": wall}
    raw = legacy._canonical(plan)
    put(run_dir / "plan.json", raw)
    descriptor = admission.descriptor(tmp_path / "admission")
    owner = admission.owner("oneshot", run_dir, run_dir)
    plan_sha = legacy._sha(raw)
    claim_sha = admission.claim_digest(plan_sha, plan["run_id"], owner, descriptor)
    put(run_dir / "run.json", legacy._canonical({"schema": 2, "run_id": plan["run_id"],
        "plan_sha256": plan_sha, "admission_descriptor": descriptor, "claim_sha256": claim_sha}))
    assert admission.publish_claim(plan_sha, plan["run_id"], owner, descriptor,
                                   override=tmp_path / "admission") == claim_sha
    return analysis.AnalysisParallelToolBroker(run_dir, binding), Context(run_dir, cap)


@pytest.fixture(autouse=True)
def real_sandbox() -> None:
    capability = probe_sandbox()
    if not capability.available:
        pytest.skip(capability.reason or "sandbox unavailable")


def work(host: analysis.AnalysisParallelToolBroker, task: str = "task-1") -> Path:
    return Path(host.branch(task)["stage_dir"]) / "work"


def invoke(host: analysis.AnalysisParallelToolBroker, context: Context, source: bytes,
           number: int = 1, task: str = "task-1", guard=None) -> dict:
    return host.invoke(task, f"{task}-turn-{number:04d}", {
        "name": "analyze", "call_id": f"analysis-{task}-{number}",
        "arguments": json.dumps({"script_sha256": legacy._sha(source)})},
        context, guard or (lambda: None))


def replace(host: analysis.AnalysisParallelToolBroker, context: Context, before: bytes,
            after: bytes, number: int = 2, expected: str | None = None) -> dict:
    request = {"op": "replace", "path": "analysis.py", "expected_sha256":
               expected or legacy._sha(before), "content": after.decode()}
    return host.invoke("task-1", f"task-1-turn-{number:04d}", {
        "name": "method", "call_id": f"method-{number}",
        "arguments": json.dumps({"request": json.dumps(request)})}, context, lambda: None)


def test_two_real_branches_publish_actual_host_inventory_and_replay(tmp_path: Path) -> None:
    host, context = fixture(tmp_path, cap=2)
    immutable = {p: p.read_bytes() for branch in host.manifest["branches"]
                 for name in ("case", "inputs") for p in (Path(branch["stage_dir"]) / name).iterdir()}
    for task in ("task-1", "task-2"):
        assert json.loads(invoke(host, context, GOOD, task=task)["output"])["measured_fixture"] == 7
        metrics = host.current_metrics(task)
        assert metrics is not None and metrics["analysis_script_sha256"] == legacy._sha(GOOD)
        assert metrics["analysis_metrics_sha256"] == legacy._sha(work(host, task).joinpath("metrics.json").read_bytes())
    reopened = analysis.AnalysisParallelToolBroker(host.run_dir, host.binding)
    assert reopened.operations() == host.operations()
    assert [op["global_ordinal"] for op in reopened.operations()] == [1, 2]
    for op in reopened.operations():
        terminal = op["terminal"]
        assert terminal["analysis_work_before"] == terminal["analysis_work_after_child"]
        assert terminal["analysis_work_after_child"] != terminal["work_after"]
        assert terminal["schema"] == 2 and terminal["analysis_status"] == "valid"
    assert all(p.read_bytes() == raw for p, raw in immutable.items())
    assert host.manifest["schema"] == 2 and host.manifest["analysis_contract"] == analysis.CONTRACT
    underlying = json.loads(Path(host.manifest["legacy_manifest"]["path"]).read_bytes())
    assert underlying["schema"] == 1 and underlying["branches"] == host.manifest["branches"]
    assert "scripts/parallel_analysis_broker.py" in host.manifest["source_bindings"]
    with pytest.raises(legacy.BrokerError, match="shape"):
        legacy.ParallelToolBroker(host.run_dir, host.binding)
    with pytest.raises(analysis.BrokerError, match="cap"):
        invoke(host, context, GOOD, number=2)


@pytest.mark.parametrize("source,status", [
    (b"print('not JSON')\n", "invalid_json"),
    (b"raise ValueError('participant error')\n", "participant_failed"),
    (b"import os\nos._exit(79)\n", "participant_failed"),
    (b"print('{\"x\":1,\"x\":2}')\n", "invalid_json"),
    (b"print('{\"x\":NaN}')\n", "invalid_json"),
    (b"print('{\"x\":1e1000}')\n", "invalid_json"),
    (b"import sys\nsys.stdout.buffer.write(bytes([255]))\n", "error"),
    (b"print('x'*300000)\n", "error"),
])
def test_ordinary_errors_deliver_feedback_and_real_cas_repair(
    tmp_path: Path, source: bytes, status: str,
) -> None:
    host, context = fixture(tmp_path, source=source, cap=3)
    claim = json.loads((host.run_dir / "run.json").read_bytes())["claim_sha256"]
    feedback = json.loads(invoke(host, context, source)["output"])
    assert feedback["analysis_status"] == status and len(json.dumps(feedback)) < 1024
    assert not (work(host) / "metrics.json").exists()
    assert json.loads(replace(host, context, source, GOOD)["output"])["ok"]
    invoke(host, context, GOOD, number=3)
    assert host.current_metrics("task-1")["metrics"]["measured_fixture"] == 7
    operations = host.operations()
    assert [op["terminal"]["schema"] for op in operations] == [2, 1, 2]
    assert all(op["terminal"]["claim_sha256"] == claim for op in operations)
    assert context.status()["tools_reserved"] == 3


def test_changed_script_is_stale_and_invalid_analysis_retires_metrics(tmp_path: Path) -> None:
    host, context = fixture(tmp_path, cap=3)
    invoke(host, context, GOOD)
    assert host.current_metrics("task-1") is not None
    bad = b"print('invalid')\n"
    replace(host, context, GOOD, bad)
    assert (work(host) / "metrics.json").exists()
    assert host.current_metrics("task-1") is None
    invoke(host, context, bad, number=3)
    assert not (work(host) / "metrics.json").exists()
    assert host.current_metrics("task-1") is None
    assert analysis.AnalysisParallelToolBroker(host.run_dir, host.binding).verify()["receipts"] == 3


def test_failed_cas_and_wrong_analysis_arguments_spend_no_analysis_reservation(tmp_path: Path) -> None:
    host, context = fixture(tmp_path)
    before = GOOD
    response = replace(host, context, before, b"print('{}')\n", number=1, expected="0" * 64)
    assert json.loads(response["output"])["broker_status"] == "tool_failure"
    assert (work(host) / "analysis.py").read_bytes() == before
    for arguments in ({"script_sha256": "0" * 64}, {"script_sha256": legacy._sha(GOOD), "extra": 1}, {}):
        with pytest.raises(analysis.BrokerError):
            host.invoke("task-1", "task-1-turn-0002", {"name": "analyze", "call_id": "bad-args",
                "arguments": json.dumps(arguments)}, context, lambda: None)
    assert host.verify()["reservations"] == 1


def test_json_above_64_kib_stays_valid_below_128_kib(tmp_path: Path) -> None:
    source = b"import json\nprint(json.dumps({'fixture': 'x'*70000}))\n"
    host, context = fixture(tmp_path, source=source)
    output = invoke(host, context, source)
    assert len(json.loads(output["output"])["fixture"]) == 70000
    assert host.current_metrics("task-1")["metrics_bytes"] < 128 * 1024


def test_child_can_read_work_but_cannot_write_it(tmp_path: Path) -> None:
    source = b"""import json
from pathlib import Path
work = Path(__file__).parent
try:
    (work/'metrics.json').write_text('{}')
except PermissionError:
    print(json.dumps({'readonly': True, 'source_visible': (work/'analysis.py').exists()}))
else:
    raise AssertionError('unexpected child write')
"""
    host, context = fixture(tmp_path, source=source)
    assert json.loads(invoke(host, context, source)["output"]) == {"readonly": True, "source_visible": True}
    assert host.operations()[0]["terminal"]["analysis_work_before"] == host.operations()[0]["terminal"]["analysis_work_after_child"]


@pytest.mark.parametrize("field", ["analysis_status", "analysis_metrics_sha256", "analysis_script_sha256",
                                   "old_metrics_sha256", "analysis_work_after_child_sha256", "global_ordinal"])
def test_closed_replay_rejects_receipt_tamper(tmp_path: Path, field: str) -> None:
    host, context = fixture(tmp_path)
    invoke(host, context, GOOD)
    path = host.receipts / "0001.json"
    value = json.loads(path.read_bytes())
    value[field] = 2 if field == "global_ordinal" else "tampered"
    put(path, legacy._canonical(value))
    with pytest.raises(analysis.BrokerError):
        analysis.AnalysisParallelToolBroker(host.run_dir, host.binding).verify()


@pytest.mark.parametrize("target", ["stdout", "metrics", "launcher", "legacy_manifest", "manifest"])
def test_external_tamper_never_exports_metrics(tmp_path: Path, target: str) -> None:
    host, context = fixture(tmp_path)
    invoke(host, context, GOOD)
    if target == "stdout":
        path = host.broker_dir / "0001/stdout"
    elif target == "metrics":
        path = work(host) / "metrics.json"
    elif target == "launcher":
        path = Path(host.manifest["branches"][0]["functions"][1]["path"])
    elif target == "legacy_manifest":
        path = Path(host.manifest["legacy_manifest"]["path"])
    else:
        path = host.path
    path.chmod(0o600)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(analysis.BrokerError):
        host.current_metrics("task-1")


@pytest.mark.parametrize("failure", ["timeout", "signal", "crash", "guard"])
def test_uncertain_effect_blocks_reconstruction_and_reexecution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    source = (b"import time\ntime.sleep(2)\nprint('{}')\n" if failure == "timeout" else
              b"import os\nos.abort()\n" if failure == "signal" else GOOD)
    host, context = fixture(tmp_path, source=source, wall=0.1 if failure == "timeout" else 5)
    def guard():
        return None

    if failure == "crash":
        def crash(*args, **kwargs):
            raise KeyboardInterrupt("crash after host metrics write")
        # Install only after the durable reservation, immediately before metrics publication.
        original = analysis._publish_analysis_metrics
        def publish(*args, **kwargs):
            result = original(*args, **kwargs)
            monkeypatch.setattr(analysis.legacy, "_publish_file", crash)
            return result
        monkeypatch.setattr(analysis, "_publish_analysis_metrics", publish)
    elif failure == "guard":
        def guard():
            if any(host.reservations.iterdir()):
                raise RuntimeError("lost parent guard")
    with pytest.raises((analysis.BrokerError, KeyboardInterrupt, RuntimeError)):
        invoke(host, context, source, guard=guard)
    reopened = analysis.AnalysisParallelToolBroker(host.run_dir, host.binding)
    assert reopened.verify()["pending"] == [1]
    with pytest.raises(analysis.BrokerError, match="unreconciled"):
        reopened.current_metrics("task-1")
    with pytest.raises(analysis.BrokerError, match="unreconciled"):
        invoke(reopened, context, source, number=2, task="task-2")
    assert len(list(host.receipts.iterdir())) == 0
    assert len(list(host.reservations.iterdir())) == 1
    assert (work(host) / "metrics.json").exists() is (failure == "crash")


def test_manifest_source_closure_tamper_is_rejected(tmp_path: Path) -> None:
    host, _ = fixture(tmp_path)
    value = json.loads(host.path.read_bytes())
    value["source_bindings"]["scripts/parallel_analysis_broker.py"] = "0" * 64
    raw = legacy._canonical(value)
    put(host.path, raw)
    binding = {"path": str(host.path), "sha256": hashlib.sha256(raw).hexdigest()}
    with pytest.raises(analysis.BrokerError, match="source closure"):
        analysis.AnalysisParallelToolBroker(host.run_dir, binding)


def test_duplicate_call_ids_cannot_cross_branches(tmp_path: Path) -> None:
    host, context = fixture(tmp_path)
    invoke(host, context, GOOD)
    with pytest.raises(analysis.BrokerError, match="already reserved"):
        host.invoke("task-2", "task-2-turn-0001", {"name": "analyze", "call_id": "analysis-task-1-1",
            "arguments": json.dumps({"script_sha256": legacy._sha(GOOD)})}, context, lambda: None)
    assert host.verify()["reservations"] == 1


def test_initial_metrics_and_arbitrary_readonly_launcher_are_rejected(tmp_path: Path) -> None:
    host, _ = fixture(tmp_path)
    specifications = [{"task_id": branch["task_id"], "owned_node_ids": branch["owned_node_ids"],
        "stage_dir": branch["stage_dir"], "functions": [{"name": fn["name"], "executable": fn["path"],
        "profile": fn["profile"]} for fn in branch["functions"]]} for branch in host.manifest["branches"]]
    put(work(host) / "metrics.json", b"{}\n")
    with pytest.raises(analysis.BrokerError, match="initial metrics"):
        analysis.prepare_analysis_branch_manifest(Path(host.manifest["root"]), specifications)
    os.unlink(work(host) / "metrics.json")
    fake = Path(host.manifest["root"]) / "fake-analyzer"
    put(fake, f"#!{sys.executable}\nprint('{{}}')\n".encode())
    fake.chmod(0o500)
    specifications[0]["functions"][1]["executable"] = str(fake)
    with pytest.raises(analysis.BrokerError, match="exact D113 launcher"):
        analysis.prepare_analysis_branch_manifest(Path(host.manifest["root"]), specifications)
