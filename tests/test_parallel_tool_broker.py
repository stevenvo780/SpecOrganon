"""Local sandbox and durable-journal checks for parallel private tools."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import local_run_admission as admission  # noqa: E402
import parallel_tool_broker as broker  # noqa: E402
from local_replay_sandbox import probe_sandbox  # noqa: E402


TOOL = r'''import json
import sys
from pathlib import Path

case, inputs, work = map(Path, sys.argv[1:4])
outer = json.loads(sys.argv[4])
request = json.loads(outer["request"])
operation = request["op"]
if operation == "write":
    target = work / "answer.txt"
    target.write_text(request["content"], encoding="utf-8")
    result = {"ok": True, "method_exit_code": 0, "method_state_sha256": "1" * 64}
elif operation == "cross":
    try:
        Path(request["path"]).read_text(encoding="utf-8")
    except PermissionError:
        result = {"ok": False, "denied": True}
    else:
        result = {"ok": True, "denied": False}
elif operation == "read":
    result = {"ok": True, "text": (work / "answer.txt").read_text(encoding="utf-8")}
else:
    result = {"ok": False}
print(json.dumps(result, sort_keys=True, separators=(",", ":")))
'''


class Context:
    def __init__(self, run_dir: Path, cap: int = 2):
        self.run_dir, self.cap = run_dir, cap
        self.deadline = time.monotonic() + 30
        self.active = True

    def require_active(self) -> None:
        if not self.active or time.monotonic() >= self.deadline:
            raise RuntimeError("inactive context")

    def status(self) -> dict:
        self.require_active()
        return {"state": "active", "tools_reserved":
                len(list((self.run_dir / "tool_reservations").glob("*.json"))),
                "max_tool_calls": self.cap}


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def _new(path: Path, value: dict) -> None:
    path.write_bytes(broker._canonical(value))


def prepared(tmp_path: Path, *, cap: int = 2,
             profile: str = "workspace") -> tuple[broker.ParallelToolBroker, Context]:
    tmp_path.chmod(0o700)
    root = _private(tmp_path / "branches")
    tools = _private(root / "tools")
    executable = tools / "method"
    executable.write_bytes(f"#!{sys.executable}\n{TOOL}".encode())
    executable.chmod(0o500)
    stages = _private(root / "stages")
    specs = []
    for number in (1, 2):
        stage = _private(stages / f"c-task-{number}")
        case = _private(stage / "case")
        inputs = _private(stage / "inputs")
        _private(stage / "work")
        _new(case / "case.json", {"case_id": "public-fixture"})
        _new(inputs / "arm_prompt", {"alternative": "C", "mode": "graph"})
        _new(stage / "stage.json", {"task_id": f"c-task-{number}"})
        specs.append({"task_id": f"c-task-{number}", "owned_node_ids": [f"node-{number}"],
                      "stage_dir": stage, "functions": [
                          {"name": "method", "executable": executable,
                           "profile": profile}]})
    binding = broker.prepare_branch_manifest(root, specs)
    run_dir = _private(tmp_path / "tool-wave")
    for name in ("broker", "tool_reservations", "tool_receipts"):
        _private(run_dir / name)
    plan = {"schema": 2, "run_id": "tool-wave-fixture",
            "branch_manifest": binding, "tool_wall_seconds": 5}
    plan_raw = broker._canonical(plan)
    (run_dir / "plan.json").write_bytes(plan_raw)
    descriptor = admission.descriptor(tmp_path / "admission")
    selected_owner = admission.owner("oneshot", run_dir, run_dir)
    plan_sha = hashlib.sha256(plan_raw).hexdigest()
    claim_sha = admission.claim_digest(plan_sha, plan["run_id"],
                                       selected_owner, descriptor)
    _new(run_dir / "run.json", {
        "schema": 2, "run_id": plan["run_id"], "plan_sha256": plan_sha,
        "admission_descriptor": descriptor, "claim_sha256": claim_sha,
    })
    published = admission.publish_claim(
        plan_sha, plan["run_id"], selected_owner, descriptor,
        override=tmp_path / "admission",
    )
    assert published == claim_sha
    return broker.ParallelToolBroker(run_dir, binding), Context(run_dir, cap)


def _call(call_id: str, request: dict) -> dict:
    return {"name": "method", "call_id": call_id,
            "arguments": json.dumps({"request": json.dumps(request)})}


def _sandbox_or_skip() -> None:
    capability = probe_sandbox()
    if not capability.available:
        pytest.skip(capability.reason or "sandbox unavailable")


def test_manifest_pins_private_stages_and_disjoint_ownership(tmp_path: Path) -> None:
    host, _ = prepared(tmp_path)
    assert host.verify()["reservations"] == 0
    assert len(host.journal_roots()) == 3
    assert host.branch("c-task-1")["owned_node_ids"] == ["node-1"]
    stage = Path(host.branch("c-task-1")["stage_dir"])
    (stage / "inputs" / "arm_prompt").write_text("changed")
    with pytest.raises(broker.BrokerError, match="changed"):
        host.verify()


def test_real_sandbox_two_branches_global_cap_and_replay(tmp_path: Path) -> None:
    _sandbox_or_skip()
    host, context = prepared(tmp_path)
    first = host.invoke("c-task-1", "c-task-1-turn-0001",
                        _call("call-1", {"op": "write", "content": "one"}),
                        context, lambda: None)
    second = host.invoke("c-task-2", "c-task-2-turn-0001",
                         _call("call-2", {"op": "write", "content": "two"}),
                         context, lambda: None)
    assert first["type"] == second["type"] == "function_call_output"
    assert host.verify() == {"manifest_sha256": host.sha256, "reservations": 2,
                             "receipts": 2, "pending": [], "blocked": False}
    assert [item["request"]["content"] for item in host.operations()] == ["one", "two"]
    assert all(item["terminal"]["status"] == "success" for item in host.operations())
    assert (Path(host.branch("c-task-1")["stage_dir"]) / "work" / "answer.txt").read_text() == "one"
    assert (Path(host.branch("c-task-2")["stage_dir"]) / "work" / "answer.txt").read_text() == "two"
    with pytest.raises(broker.BrokerError, match="cap"):
        host.invoke("c-task-1", "c-task-1-turn-0002",
                    _call("call-3", {"op": "read"}), context, lambda: None)
    assert len(list(host.reservations.iterdir())) == 2


def test_real_sandbox_cannot_cross_branch_roots(tmp_path: Path) -> None:
    _sandbox_or_skip()
    host, context = prepared(tmp_path)
    other = Path(host.branch("c-task-2")["stage_dir"]) / "case" / "case.json"
    answer = host.invoke("c-task-1", "c-task-1-turn-0001",
                         _call("call-1", {"op": "cross", "path": str(other)}),
                         context, lambda: None)
    assert json.loads(answer["output"]) == {"denied": True, "ok": False}


def test_concurrent_pending_branches_share_ordinals(tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    _sandbox_or_skip()
    host, context = prepared(tmp_path)
    gate = threading.Barrier(2)
    original = broker.run_sandboxed

    def synchronized(**kwargs: object):
        gate.wait(timeout=5)
        return original(**kwargs)

    monkeypatch.setattr(broker, "run_sandboxed", synchronized)
    answers: list[dict] = []
    failures: list[BaseException] = []

    def worker(task: str, number: int) -> None:
        try:
            answers.append(host.invoke(task, f"{task}-turn-0001",
                                       _call(f"call-{number}", {
                                           "op": "write", "content": task,
                                       }), context, lambda: None))
        except BaseException as exc:
            failures.append(exc)

    threads = [threading.Thread(target=worker, args=(f"c-task-{i}", i)) for i in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not failures
    assert len(answers) == 2
    assert host.verify()["receipts"] == 2
    assert {item["task_id"] for item in host.operations()} == {"c-task-1", "c-task-2"}


def test_readonly_profile_does_not_get_work_write_root(tmp_path: Path) -> None:
    _sandbox_or_skip()
    host, context = prepared(tmp_path, profile="analysis_readonly")
    result = host.invoke("c-task-1", "c-task-1-turn-0001",
                         _call("call-1", {"op": "write", "content": "forbidden"}),
                         context, lambda: None)
    assert result["type"] == "function_call_output"
    assert host.operations()[0]["terminal"]["status"] in {"tool_failure", "invalid_json"}
    assert not list((Path(host.branch("c-task-1")["stage_dir"]) / "work").iterdir())


def test_pending_reservation_blocks_reconstructed_broker(tmp_path: Path,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    host, context = prepared(tmp_path)
    def crash(**kwargs: object) -> None:
        raise RuntimeError("synthetic crash after durable reservation")
    monkeypatch.setattr(broker, "run_sandboxed", crash)
    with pytest.raises(RuntimeError, match="synthetic crash"):
        host.invoke("c-task-1", "c-task-1-turn-0001",
                    _call("call-1", {"op": "read"}), context, lambda: None)
    reopened = broker.ParallelToolBroker(host.run_dir, host.binding)
    assert reopened.verify()["pending"] == [1]
    with pytest.raises(broker.BrokerError, match="unreconciled"):
        reopened.invoke("c-task-2", "c-task-2-turn-0001",
                        _call("call-2", {"op": "read"}), context, lambda: None)
    assert len(list(host.receipts.iterdir())) == 0


def test_claim_manifest_and_receipt_tamper_are_rejected(tmp_path: Path) -> None:
    _sandbox_or_skip()
    host, context = prepared(tmp_path)
    host.invoke("c-task-1", "c-task-1-turn-0001",
                _call("call-1", {"op": "write", "content": "proof"}),
                context, lambda: None)
    receipt = host.receipts / "0001.json"
    original = receipt.read_bytes()
    receipt.write_bytes(original.replace(b'"status":"success"', b'"status":"failure"'))
    with pytest.raises(broker.BrokerError, match="feedback"):
        host.verify()
    receipt.write_bytes(original)
    state = host.run_dir / "run.json"
    original_state = state.read_bytes()
    state.write_bytes(original_state.replace(b"tool-wave-fixture", b"tool-wave-other"))
    with pytest.raises(broker.BrokerError, match="identity"):
        host.invoke("c-task-2", "c-task-2-turn-0001",
                    _call("call-2", {"op": "write", "content": "no"}),
                    context, lambda: None)
    assert len(list(host.reservations.iterdir())) == 1
    state.write_bytes(original_state)
    manifest = host.path
    manifest.write_bytes(manifest.read_bytes() + b" ")
    with pytest.raises(broker.BrokerError, match="digest"):
        host.verify()


def test_invalid_calls_and_ownership_never_reserve(tmp_path: Path) -> None:
    host, context = prepared(tmp_path)
    invalid = [
        {"name": "method", "call_id": "call-1", "arguments": '{"request":1,"request":2}'},
        {"name": "method", "call_id": "call-1", "arguments": '{"value":NaN}'},
        {"name": "method", "call_id": "call-1", "arguments": '{"value":1e1000}'},
        {"name": "other", "call_id": "call-1", "arguments": "{}"},
    ]
    for call in invalid:
        with pytest.raises(broker.BrokerError):
            host.invoke("c-task-1", "c-task-1-turn-0001", call, context, lambda: None)
    assert host.verify()["reservations"] == 0


def test_copied_owner_cannot_spend_parent_claim(tmp_path: Path) -> None:
    host, context = prepared(tmp_path)
    copied = _private(tmp_path / "copied-run")
    for name in ("broker", "tool_reservations", "tool_receipts"):
        _private(copied / name)
    for name in ("plan.json", "run.json"):
        shutil.copyfile(host.run_dir / name, copied / name)
    copied_broker = broker.ParallelToolBroker(copied, host.binding)
    copied_context = Context(copied)
    with pytest.raises(broker.BrokerError, match="claim"):
        copied_broker.invoke("c-task-1", "c-task-1-turn-0001",
                             _call("call-1", {"op": "read"}), copied_context,
                             lambda: None)
    assert not list(copied_broker.reservations.iterdir())
