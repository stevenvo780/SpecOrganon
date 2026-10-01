"""Budget continuity and replay across the real parent bootstrap boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_c_parent_analysis import c, fixture_case, prepare, sandbox, step, transports
import managed_parent_analysis as parent
from run_managed_conversation import _canonical


def prepared(tmp_path, **caps):
    case, inputs, config = fixture_case(tmp_path)
    config.update(caps)
    run = tmp_path / "run"
    status = c.prepare_c_parent_analysis(run, case, inputs, config, admission_root=tmp_path / "admission")
    return run, status


def test_phase_transport_rejected_before_count_or_claim(tmp_path):
    run, status = prepared(tmp_path)
    adapters = transports()
    with pytest.raises(parent.ParentAnalysisError, match="transport keys"):
        c.execute_c_parent_analysis_step(run, {key: value for key, value in adapters.items() if key != "leader"},
                                        expected_checkpoint=status["checkpoint_sha256"])
    assert sum(t.counts + t.sends for t in adapters.values()) == 0
    assert not list((tmp_path / "admission").glob("*.json"))
    assert c.read_c_parent_analysis_status(run)["budget"]["request_count"] == 0


@pytest.mark.parametrize("field,replacement", [
    ("max_tool_calls", 64), ("active_limit_seconds", 5400),
    ("roles", ["coordinator", "leader"]), ("journal_roots", []),
])
def test_changed_effective_context_policy_never_sends(tmp_path, field, replacement):
    run, status = prepared(tmp_path)
    path = run / "context/run.json"
    captured = json.loads(path.read_bytes())
    captured[field] = replacement
    path.write_bytes(_canonical(captured))
    adapters = transports()
    with pytest.raises(ValueError):
        c.execute_c_parent_analysis_step(run, {"leader": adapters["leader"]},
                                        expected_checkpoint=status["checkpoint_sha256"])
    assert adapters["leader"].counts == adapters["leader"].sends == 0
    assert not list((run / "requests").iterdir())


def test_stale_checkpoint_keeps_original_ledger_and_claim(tmp_path):
    sandbox()
    run, initial = prepare(tmp_path)[:2]
    adapters = transports()
    after_init = step(run, initial, adapters)
    assert after_init["state"] == "paused", after_init
    ledger_path = run / "ledger/ledger.json"
    before = ledger_path.read_bytes()
    claim_files = sorted((tmp_path / "admission").glob("*.json"))
    assert len(claim_files) == 1
    claim = claim_files[0].read_bytes()
    with pytest.raises(ValueError):
        c.execute_c_parent_analysis_step(run, {"leader": adapters["leader"]},
                                        expected_checkpoint=initial["checkpoint_sha256"])
    assert adapters["leader"].sends == 1
    assert ledger_path.read_bytes() == before and claim_files[0].read_bytes() == claim
    assert c.read_c_parent_analysis_status(run)["budget"]["request_count"] == 1


@pytest.mark.parametrize("caps", [
    {"max_model_requests": 3}, {"limit_tokens": 530}, {"cost_limit_micro_usd": 530},
])
def test_leader_budget_not_replenished_for_first_worker_batch(tmp_path, caps):
    sandbox()
    run, status = prepared(tmp_path, **caps)
    adapters = transports()
    status = step(run, status, adapters)
    assert status["state"] == "paused", status
    status = step(run, status, adapters)
    assert status["state"] == "paused" and status["phase"] == "wave", status
    assert status["budget"]["request_count"] == 2 and status["budget"]["settled_tokens"] == 14
    status = step(run, status, adapters)
    assert status["state"] == "indeterminate", status
    assert adapters["c-task-1"].sends == adapters["c-task-2"].sends == 0
    assert status["budget"]["request_count"] == 2
    assert status["budget"]["settled_tokens"] == 14
    assert status["tool_calls_completed"] == 1
    assert len(list((tmp_path / "admission").glob("*.json"))) == 1
    assert not (run / "publication.json").exists()
    with pytest.raises(ValueError):
        step(run, status, adapters)


def test_tool_limit_includes_leader_init(tmp_path):
    sandbox()
    run, status = prepared(tmp_path, max_tool_calls=1)
    adapters = transports()
    status = step(run, status, adapters)
    status = step(run, status, adapters)
    assert status["state"] == "paused" and status["phase"] == "wave", status
    status = step(run, status, adapters)
    assert status["state"] == "indeterminate", status
    assert status["tool_calls_completed"] == 1
    assert status["budget"]["request_count"] == 4
    assert len(list((run / "tool_reservations").iterdir())) == 1
    assert all(not (work / "analysis.py").exists()
               for work in (tmp_path / "run-stages/slots").glob("*/work"))
    assert not (run / "publication.json").exists()


def test_callback_cannot_change_caps_at_activation(tmp_path):
    sandbox()
    run, status = prepared(tmp_path)
    adapters = transports()
    status = step(run, status, adapters)
    assert status["state"] == "paused", status

    def changed_policy(plan, state, broker, context, guard):
        transition = c.bootstrap_to_wave(plan, state, broker, context, guard)
        transition["wave_plan"]["limit_tokens"] += 1
        return transition

    status = parent.execute_parent_analysis_step(
        run, {"leader": adapters["leader"]}, expected_checkpoint=status["checkpoint_sha256"],
        bootstrap_to_wave=changed_policy, merge=c.merge_c_parent, guard=c.guard_c_parent)
    assert status["state"] == "indeterminate", status
    assert "resource" in status["reason"]
    assert status["budget"]["limit_tokens"] == 5000
    assert adapters["c-task-1"].sends == adapters["reviewer"].sends == 0
    assert not (tmp_path / "run-stages/metadata/activation.json").exists()
    assert not (run / "publication.json").exists()


def test_source_change_rejected_before_provider_io(tmp_path, monkeypatch):
    run, status = prepared(tmp_path)
    adapters = transports()
    closure = parent._sources()
    monkeypatch.setattr(parent, "_sources", lambda: {**closure, "scripts/changed.py": "0" * 64})
    with pytest.raises(parent.ParentAnalysisError, match="source"):
        c.execute_c_parent_analysis_step(run, {"leader": adapters["leader"]},
                                        expected_checkpoint=status["checkpoint_sha256"])
    assert adapters["leader"].counts == adapters["leader"].sends == 0
    assert not list((run / "requests").iterdir())
    assert not list(Path(tmp_path / "admission").glob("*.json"))
