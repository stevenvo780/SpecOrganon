"""Actual shared D118 capsules and original A/B/C tools behind a persistent parent."""
from __future__ import annotations

import copy
import json
import subprocess
import sys

import pytest

from coordinated_runtime_fixture import SyntheticRoles, bundle_configuration, configuration, runtime


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    root = tmp_path_factory.mktemp("D119-original-bundle")
    target = root / "bundle"
    runtime.preparation.build_coordinated_round(target, bundle_configuration(), runtime.SPEC / "public_contract", runtime.SPEC_SHA256)
    return target


def run_id(bundle, arm="C", case_id="D-E"):
    schedule = json.loads((bundle / "schedule.json").read_bytes())
    return next(row["run_id"] for row in schedule["runs"]
                if row["arm"] == arm and row["case_id"] == case_id and row["replica"] == 1)


@pytest.mark.parametrize("bad", ["extra", "bool_schema", "bool_output", "over_output", "role_extra", "reviewer_turns", "epochs", "wall"])
def test_invalid_configuration_creates_no_inputs_run_or_claim(bundle, tmp_path, bad):
    value = configuration()
    if bad == "extra":
        value["execution_authorized"] = True
    elif bad == "bool_schema":
        value["schema"] = True
    elif bad == "bool_output":
        value["role_config"]["leader"]["max_output_tokens"] = True
    elif bad == "over_output":
        value["role_config"]["worker-1"]["max_output_tokens"] = 1001
    elif bad == "role_extra":
        value["role_config"]["worker-1"]["approved"] = True
    elif bad == "reviewer_turns":
        value["role_config"]["reviewer"]["max_model_turns"] = 2
    elif bad == "epochs":
        value["max_epochs"] = 129
    else:
        value["tool_wall_seconds"] = 301
    with pytest.raises(ValueError):
        runtime.prepare_coordinated_runtime(tmp_path / "run", bundle, run_id(bundle), value, admission_root=tmp_path / "admission")
    assert not any((tmp_path / name).exists() for name in ("run", "run-inputs", "admission"))


@pytest.mark.parametrize("bad", ["bundle_child", "repo_child", "admission_overlap", "run_alias", "unknown_run"])
def test_unbound_or_overlapping_paths_rejected_before_io(bundle, tmp_path, bad):
    run, admission = tmp_path / "run", tmp_path / "admission"
    selected = run_id(bundle)
    if bad == "bundle_child":
        run = bundle / "forbidden"
    elif bad == "repo_child":
        run = runtime.ROOT / "forbidden-D119-output"
    elif bad == "admission_overlap":
        admission = run / "admission"
    elif bad == "run_alias":
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        run = alias / "run"
    else:
        selected = "dev-coord-not-published"
    with pytest.raises((ValueError, OSError)):
        runtime.prepare_coordinated_runtime(run, bundle, selected, configuration(), admission_root=admission)
    assert not run.exists() and not (run.parent / (run.name + "-inputs")).exists()
    assert not admission.exists()


@pytest.mark.parametrize("arm", list("ABC"))
@pytest.mark.parametrize("case_id", ["D-F", "D-E"])
def test_original_modes_multiple_delegations_same_budget_and_final_host_analysis(bundle, tmp_path, arm, case_id):
    from coordinated_prototype_broker import CoordinatedPrototypeBroker
    from local_replay_sandbox import probe_sandbox
    capability = probe_sandbox()
    assert capability.available, capability.reason
    run = tmp_path / "run"
    status = runtime.prepare_coordinated_runtime(run, bundle, run_id(bundle, arm, case_id), configuration(),
                                                 admission_root=tmp_path / "admission")
    fixture = SyntheticRoles(run)
    transports = fixture.transports()
    assert status["budget"]["request_count"] == 0
    assert not list((tmp_path / "admission").glob("*.json"))
    saved_claim, requests = None, []
    for _ in range(50):
        status = runtime.execute_coordinated_runtime_step(run, transports, expected_checkpoint=status["checkpoint_sha256"])
        requests.append(status["budget"]["request_count"])
        claims = sorted(path for path in (tmp_path / "admission").glob("*.json")
                        if not path.name.endswith(".coordinated-binding.json"))
        assert len(claims) == 1
        if saved_claim is None:
            saved_claim = claims[0].read_bytes()
        assert claims[0].read_bytes() == saved_claim
        if status["state"] != "paused":
            break
    assert status["state"] == "completed", status
    assert requests == sorted(requests) and len(set(requests)) == len(requests)
    assert status["budget"]["settled_tokens"] == 7 * requests[-1]
    broker = CoordinatedPrototypeBroker(run, json.loads((run / "run.json").read_bytes())["broker_binding"])
    events = broker._events()
    activations = [row for row in events if row["kind"] == "activate"]
    merges = [row for row in events if row["kind"] == "merge"]
    assert len(activations) == len(merges) >= 2
    final = broker.public_state()
    assert final["mode"] == {"A": "sequential", "B": "graph", "C": "risk"}[arm]
    assert final["state"]["nodes"]["E"]["status"] == "supported"
    assert final["state"]["nodes"]["N"]["status"] == "pending"
    assert not all(value == "accepted" for value in final["state"]["phase_status"].values())
    fresh = broker.current_metrics("leader")
    assert fresh is not None
    metadata = json.loads((bundle / "assets" / case_id / "case.json").read_bytes())
    assert fresh["metrics"]["observed_source_inventory"] == metadata["files"]
    checked = runtime.delivery.check_delivery(bundle / "assets" / case_id, broker.leader_stage() / "work",
                    runtime.delivery.delivery_contract_template())
    assert checked["structural_checks_passed"] is True and checked["quality_assessed"] is False
    review = fixture.payloads["reviewer"]
    assert len(review) == 1 and "tools" not in review[0]
    assert "SYNTHETIC-PRIVATE:" not in json.dumps(review)
    assert "SYNTHETIC-PRIVATE:leader:" not in json.dumps(fixture.payloads["worker-1"])
    if arm == "A":
        assert not fixture.payloads["worker-2"]
    command = [sys.executable, "-I", "-B", str(runtime.SCRIPTS / "coordinated_prototype_runtime.py"),
               "status", "--run-dir", str(run)]
    reopened = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert reopened.returncode == 0, reopened.stdout + reopened.stderr
    assert json.loads(reopened.stdout)["checkpoint_sha256"] == status["checkpoint_sha256"]
    (tmp_path / "synthetic_trace.json").write_text(json.dumps(fixture.trace, sort_keys=True))
    (tmp_path / "final_summary.json").write_text(json.dumps({"case_id": case_id, "arm": arm,
        "delegations": len(activations), "requests": requests[-1], "final_metric": fresh,
        "checker": checked, "status": status}, sort_keys=True))


def test_stale_checkpoint_rejected_without_transport_or_budget_changes(bundle, tmp_path):
    run = tmp_path / "run"
    status = runtime.prepare_coordinated_runtime(run, bundle, run_id(bundle), configuration(), admission_root=tmp_path / "admission")
    fixture = SyntheticRoles(run)
    transports = fixture.transports()
    runtime.execute_coordinated_runtime_step(run, transports, expected_checkpoint=status["checkpoint_sha256"])
    ledger = (run / "ledger/ledger.json").read_bytes()
    trace = copy.deepcopy(fixture.trace)
    with pytest.raises(ValueError):
        runtime.execute_coordinated_runtime_step(run, transports, expected_checkpoint=status["checkpoint_sha256"])
    assert (run / "ledger/ledger.json").read_bytes() == ledger and fixture.trace == trace
