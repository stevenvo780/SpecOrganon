"""Engine guards with actual ledgers/context/broker and synthetic model replies.

Fault injection below is explicit; it does not certify an actual provider.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from coordinated_runtime_fixture import SyntheticRoles, bundle_configuration, configuration, runtime
import managed_coordinated_prototype as engine
from managed_run_context import RunContext
from run_managed_conversation import _canonical


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    directory = tmp_path_factory.mktemp("D119-engine-bundle") / "bundle"
    runtime.preparation.build_coordinated_round(directory, bundle_configuration(),
                                               runtime.SPEC / "public_contract", runtime.SPEC_SHA256)
    return directory


def prepare(bundle, tmp_path, arm="C", config=None):
    schedule = json.loads((bundle / "schedule.json").read_bytes())
    selected = next(row["run_id"] for row in schedule["runs"]
                    if row["arm"] == arm and row["case_id"] == "D-E" and row["replica"] == 1)
    run = tmp_path / "run"
    initial = runtime.prepare_coordinated_runtime(run, bundle, selected, config or configuration(),
                                                 admission_root=tmp_path / "admission")
    return run, initial, SyntheticRoles(run)


def step(run, status, fixture):
    return runtime.execute_coordinated_runtime_step(run, fixture.transports(),
                                                    expected_checkpoint=status["checkpoint_sha256"])


def reach_delegations(run, status, fixture, count=2):
    for _ in range(40):
        if len(status["delegations"]) >= count:
            return status
        status = step(run, status, fixture)
        assert status["state"] == "paused", status
    pytest.fail("fixture did not reach bounded delegation count")


@pytest.mark.parametrize("arm", list("ABC"))
def test_two_delegations_keep_global_ids_context_and_claim(bundle, tmp_path, arm):
    run, status, fixture = prepare(bundle, tmp_path, arm)
    context_before = json.loads((run / "context/run.json").read_bytes())
    status = reach_delegations(run, status, fixture)
    context_after = json.loads((run / "context/run.json").read_bytes())
    assert context_before["bindings"] == context_after["bindings"]
    assert context_after["schema"] == 2 and status["budget"]["schema"] == 3
    assert len(status["delegations"]) == 2 and len(status["merges"]) == 1
    assert len(list((tmp_path / "admission").glob("*.json"))) == 1
    side = list((tmp_path / "admission").glob("*.coordinated-binding"))
    assert len(side) == 1
    binding = json.loads(side[0].read_bytes())
    assert binding["schedule_sha256"] == status["schedule_sha256"]
    assert binding["owner"]["mode"] == "oneshot"
    first = status["delegations"][0]["assignments"]
    assert len(first) == (1 if arm == "A" else 2)
    assert len(status["delegations"][1]["assignments"]) >= 1
    if arm != "A":
        assert status["delegations"][1]["selection"][0]["id"] == "E"
    assert status["roles"]["worker-1"]["turns"] > 0
    requests = status["budget"]["requests"]
    assert len(requests) == status["completed_requests"]
    assert len(requests) == len(set(requests))
    assert status["budget"]["settled_tokens"] == 7 * len(requests)
    assert engine.read_status(run)["checkpoint_sha256"] == status["checkpoint_sha256"]


def test_closed_plan_validation_is_pure_before_input_creation(bundle, tmp_path):
    run, _, _ = prepare(bundle, tmp_path)
    plan = json.loads((run / "plan.json").read_bytes())
    plan["inputs_dir"] = str(tmp_path / "nonexistent-inputs")
    plan["journal_roots"] = [str(tmp_path / "nonexistent-root")]
    assert engine.validate_plan(plan, check_inputs=False) == plan
    assert not Path(plan["inputs_dir"]).exists()


@pytest.mark.parametrize("fault", ["permission", "model", "limit", "reviewer", "closure"])
def test_bad_closed_plan_never_creates_run(bundle, tmp_path, fault):
    run, _, _ = prepare(bundle, tmp_path)
    plan = json.loads((run / "plan.json").read_bytes())
    if fault == "permission":
        plan["execution_authorized"] = True
    elif fault == "model":
        plan["model"] = "unbound-model"
    elif fault == "limit":
        plan["limits"]["limit_tokens"] += 1
    elif fault == "reviewer":
        plan["role_config"]["reviewer"]["max_model_turns"] = 2
    else:
        plan["runtime_source_digests"].pop("prototypes/core.py")
    target = tmp_path / "rejected"
    with pytest.raises(ValueError):
        engine.prepare_coordinated_prototype(target, plan, admission_root=tmp_path / "other-admission")
    assert not target.exists() and not (tmp_path / "other-admission").exists()


def test_transport_and_stale_cas_fail_before_model_io(bundle, tmp_path):
    run, initial, fixture = prepare(bundle, tmp_path)
    with pytest.raises(ValueError, match="transport keys"):
        engine.execute_step(run, {"worker-1": fixture.transports()["worker-1"]},
                            expected_checkpoint=initial["checkpoint_sha256"])
    assert fixture.trace == []
    status = step(run, initial, fixture)
    budget = (run / "ledger/ledger.json").read_bytes()
    trace = copy.deepcopy(fixture.trace)
    with pytest.raises(ValueError, match="checkpoint"):
        engine.execute_step(run, fixture.transports(), expected_checkpoint=initial["checkpoint_sha256"])
    assert fixture.trace == trace and (run / "ledger/ledger.json").read_bytes() == budget
    assert engine.read_status(run)["checkpoint_sha256"] == status["checkpoint_sha256"]


@pytest.mark.parametrize("fault", ["raw", "counter", "history", "side_binding", "context"])
def test_restart_rejects_changed_durable_bindings_before_io(bundle, tmp_path, fault):
    run, initial, fixture = prepare(bundle, tmp_path)
    status = step(run, initial, fixture)
    if fault == "raw":
        path = next((run / "responses").iterdir())
        value = json.loads(path.read_bytes())
        value["id"] = "tampered-raw"
    elif fault == "counter":
        path = run / "run.json"
        value = json.loads(path.read_bytes())
        value["roles"]["leader"]["turns"] += 1
    elif fault == "history":
        path = run / "histories/leader/run.json"
        value = json.loads(path.read_bytes())
        value["history"].append({"role": "user", "content": "unbound-feedback"})
    elif fault == "side_binding":
        path = next((tmp_path / "admission").glob("*.coordinated-binding"))
        value = json.loads(path.read_bytes())
        value["limits"]["limit_tokens"] += 1
    else:
        path = run / "context/run.json"
        value = json.loads(path.read_bytes())
        value["max_tool_calls"] += 1
    path.write_bytes(_canonical(value))
    trace = copy.deepcopy(fixture.trace)
    with pytest.raises(ValueError):
        engine.execute_step(run, fixture.transports(), expected_checkpoint=status["checkpoint_sha256"])
    assert fixture.trace == trace


def test_external_guard_rejection_consumes_no_model_io(bundle, tmp_path):
    run, status, fixture = prepare(bundle, tmp_path)
    def guard(_plan, _state, _broker):
        raise ValueError("external declared source binding changed")
    with pytest.raises(ValueError, match="external"):
        engine.execute_step(run, fixture.transports(), expected_checkpoint=status["checkpoint_sha256"], guard=guard)
    assert fixture.trace == [] and engine.read_status(run)["budget"]["request_count"] == 0


class TextTransport:
    def __init__(self, model, text):
        self.model, self.text, self.counts, self.sends = model, text, 0, 0

    def count_input(self, _payload, *, timeout_seconds):
        assert timeout_seconds > 0
        self.counts += 1
        return 5

    def send(self, _payload, *, timeout_seconds):
        assert timeout_seconds > 0
        self.sends += 1
        return {"id": "synthetic-text", "model": self.model, "service_tier": "default", "status": "completed",
                "output": [{"type": "message", "role": "assistant", "status": "completed",
                            "content": [{"type": "output_text", "text": self.text}]}],
                "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}}


@pytest.mark.parametrize("text", [
    '{"action":"delegate","public_text":"public"}',
    '{"action":"deliver","public_text":"public"}',
    '{"action":"delegate","public_text":"public","approved":true}',
])
def test_terminal_leader_cannot_skip_actual_init_or_add_host_instructions(bundle, tmp_path, text):
    run, initial, _ = prepare(bundle, tmp_path)
    plan = json.loads((run / "plan.json").read_bytes())
    transport = TextTransport(plan["model"], text)
    status = engine.execute_step(run, {"leader": transport}, expected_checkpoint=initial["checkpoint_sha256"])
    assert status["state"] == "indeterminate" and status["delegations"] == []
    assert transport.sends == 1 and not (run / "publication.json").exists()
    with pytest.raises(ValueError, match="never reexecute"):
        engine.execute_step(run, {"leader": transport}, expected_checkpoint=status["checkpoint_sha256"])
    assert transport.sends == 1


def test_finish_failure_keeps_delivery_forensic_and_blocks_publication(bundle, tmp_path, monkeypatch):
    run, status, fixture = prepare(bundle, tmp_path)
    for _ in range(45):
        if status["runtime_stage"] == "reviewer":
            break
        status = step(run, status, fixture)
        assert status["state"] == "paused", status
    assert status["runtime_stage"] == "reviewer"
    delivery = (run / "control/delivery.json").read_bytes()
    def fail_finish(_context, _cursor):
        raise RuntimeError("injected context finish failure")
    monkeypatch.setattr(RunContext, "finish", fail_finish)
    status = step(run, status, fixture)
    assert status["state"] == "indeterminate" and "finish failure" in status["reason"]
    assert (run / "control/delivery.json").read_bytes() == delivery
    assert status["artifacts"] == [] and status["delivery"] is None
    assert not (run / "publication.json").exists()


def test_source_closure_change_is_rejected_before_count(bundle, tmp_path, monkeypatch):
    run, status, fixture = prepare(bundle, tmp_path)
    closure = engine._sources()
    monkeypatch.setattr(engine, "_sources", lambda: {**closure, "scripts/nonexistent.py": "0" * 64})
    with pytest.raises(ValueError, match="closure"):
        engine.execute_step(run, fixture.transports(), expected_checkpoint=status["checkpoint_sha256"])
    assert fixture.trace == []
