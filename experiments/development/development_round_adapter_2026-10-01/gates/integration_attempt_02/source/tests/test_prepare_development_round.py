"""Original public cases through actual sealed A/B/C tools; fake model transport."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_run_admission as admission  # noqa: E402
import prepare_development_round as adapter  # noqa: E402
import run_managed_team as team  # noqa: E402
from analyze_confirmatory import AnalysisError, _validate_schedule  # noqa: E402
from preflight_assets import PreflightError, _candidate_schedule, preflight  # noqa: E402
from test_run_managed_team import FakeTransport, _message  # noqa: E402
from verify_staged_run import verify_stage  # noqa: E402


def configuration() -> dict:
    model = "offline-fixture-model"
    return {"schema": 1, "seed": 112, "model": {
        "model_id": model, "version": model, "family": "fixture", "tier": "fixture",
        "effort": "default", "effort_provider_value": None},
        "price_profile": {"model": model, "input_rate_micro_usd_per_million": 1000000,
                          "cached_input_rate_micro_usd_per_million": 1000000,
                          "cache_write_rate_micro_usd_per_million": 1000000,
                          "output_rate_micro_usd_per_million": 1000000},
        "per_run_limits": {"measured_tokens": 1000, "active_seconds": 120, "tool_calls": 12},
        "max_model_requests": 16, "cost_limit_micro_usd": 1000}


def nodes() -> list[dict]:
    return [{"id": node_id, "kind": kind, "phase": phase, "status": "pending",
             "claim": "public synthetic workflow proposal", "depends_on": deps}
            for node_id, kind, phase, status, deps in [
                ("P", "problem", "philosophy", "supported", []),
                ("N", "normative", "philosophy", "pending", ["P"]),
                ("E", "evidence", "science", "supported", ["P"]),
                ("R", "requirement", "engineering", "supported", ["N", "E"]),
                ("V", "test_result", "validation", "pending", ["R"])]]


def call(request: dict, number: int) -> dict:
    return {"type": "function_call", "name": "development_method", "status": "completed",
            "call_id": f"offline-{number}",
            "arguments": json.dumps({"request": json.dumps(request)})}


def test_capsules_preserve_original_public_bytes_and_no_reserved_assets(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    result = adapter.build_round(bundle, configuration())
    schedule = json.loads((bundle / "schedule.json").read_text())
    assets = json.loads((bundle / "assets.json").read_text())
    assert result["formal_cells_executed"] == result["real_provider_requests"] == 0
    assert result["execution_authorized"] is False
    assert schedule["run_count"] == 12
    assert {(run["case_id"], run["arm"], run["replica"]) for run in schedule["runs"]} == {
        (case_id, arm, replica) for case_id in ("D-F", "D-E")
        for arm in "ABC" for replica in (1, 2)}
    assert all(run["case_reference_sha256"] is None for run in schedule["runs"])
    for case_id, sources in adapter.CASE_INPUTS.items():
        manifest = json.loads((bundle / "assets" / case_id / "case.json").read_text())
        assert len(manifest["files"]) == len(sources)
        for source in sources:
            assert (bundle / "assets" / case_id / Path(source).name).read_bytes() == (ROOT / source).read_bytes()
    report = preflight(schedule, assets)
    assert report["verified_assets"] == 8 and report["verified_hidden_references"] == 0
    assert _candidate_schedule(schedule) == schedule
    with pytest.raises(AnalysisError):
        _validate_schedule(schedule)
    with pytest.raises(PreflightError, match="confirmatory gate"):
        preflight(schedule, assets, gate_root=tmp_path / "gate")
    again = tmp_path / "again"
    adapter.build_round(again, configuration())
    assert (again / "schedule.json").read_bytes() == (bundle / "schedule.json").read_bytes()


@pytest.mark.parametrize("case_id", ["D-F", "D-E"])
@pytest.mark.parametrize("arm", ["A", "B", "C"])
def test_original_cases_actual_methods_one_ledger_resume_and_chunk_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case_id: str, arm: str,
) -> None:
    monkeypatch.setenv(admission.ROOT_ENV, str(tmp_path / "admissions"))
    bundle = tmp_path / "bundle"
    adapter.build_round(bundle, configuration())
    schedule = json.loads((bundle / "schedule.json").read_text())
    run = next(item for item in schedule["runs"]
               if item["case_id"] == case_id and item["arm"] == arm and item["replica"] == 1)
    attempt = tmp_path / "attempt"
    prepared = adapter.prepare_cell(bundle, run["run_id"], attempt)
    assert prepared["state"] == "prepared" and prepared["budget"]["request_count"] == 0
    assert verify_stage(schedule, run["run_id"], attempt / "stage")["execution_ready"] is False
    # 21KB delivery exceeds one tool-argument envelope: three counted chunks.
    chunks = ["public synthetic result\n" + "x" * 6976, "y" * 7000, "z" * 7000]
    requests = [
        {"op": "read", "path": "task.md", "offset": 0, "length": 4096},
        {"op": "init", "nodes": nodes()},
        {"op": "revise", "id": "P", "status": "supported", "reason": "synthetic proposal only; not field evidence"},
        {"op": "advance", "phase": "philosophy"},
    ]
    offset = 0
    for chunk in chunks:
        requests.append({"op": "write", "path": "report.md", "offset": offset, "content": chunk})
        offset += len(chunk.encode())
    requests.append({"op": "plan", "budget": 2} if arm == "C" else {"op": "status"})
    first_transport = FakeTransport(run["model_id"],
                                    [[call(request, index)] for index, request in enumerate(requests, 1)]
                                    + [[_message("mechanical partial delivery; normative pending")]])
    first = team.execute_team_segment(attempt / "managed", first_transport,
                                      prepared["checkpoint_sha256"])
    assert first["state"] == "paused" and first["cursor"] == 1
    assert first["tool_calls_completed"] == len(requests)
    state = json.loads((attempt / "stage/work/method_state.json").read_text())
    assert state["mode"] == adapter.MODES[arm]
    assert state["nodes"]["N"]["status"] == "pending"
    assert state["phase_status"]["philosophy"] == "not_started"
    assert (attempt / "stage/work/report.md").read_text() == "".join(chunks)
    assert not (attempt / "stage/work/metrics.json").exists()
    # A separate segment uses the same claim/ledger/context and no new allowance.
    checkpoint = team.read_team_status(attempt / "managed")["checkpoint_sha256"]
    second_transport = FakeTransport(run["model_id"], [[_message("reviewed partial artifact only")]])
    second = team.execute_team_segment(attempt / "managed", second_transport, checkpoint)
    assert second["state"] == "completed" and second["cursor"] == 2
    assert second["tool_calls_completed"] == len(requests)
    assert second["budget"]["request_count"] == len(requests) + 2
    assert second["budget"]["settled_tokens"] == 15 * (len(requests) + 2)
    assert second["budget"]["cost_limit_micro_usd"] == 1000
    assert json.loads((attempt / "preparation.json").read_text())["formal_cell_executed"] is False


def test_bad_configuration_and_changed_price_fail_before_attempt(tmp_path: Path) -> None:
    bad = configuration()
    bad["per_run_limits"]["tool_calls"] = 17
    with pytest.raises(ValueError):
        adapter.build_round(tmp_path / "bad", bad)
    assert not (tmp_path / "bad").exists()
    bundle = tmp_path / "bundle"
    adapter.build_round(bundle, configuration())
    schedule = json.loads((bundle / "schedule.json").read_text())
    profile_path = bundle / "price_profile.json"
    profile = json.loads(profile_path.read_text())
    profile["input_rate_micro_usd_per_million"] += 1
    profile_path.write_text(json.dumps(profile))
    with pytest.raises(adapter.PreparationError, match="price profile"):
        adapter.prepare_cell(bundle, schedule["runs"][0]["run_id"], tmp_path / "attempt")
    assert not (tmp_path / "attempt").exists()


def test_repeated_build_and_originals_are_not_replaced(tmp_path: Path) -> None:
    original = {source: hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
                for sources in adapter.CASE_INPUTS.values() for source in sources}
    bundle = tmp_path / "bundle"
    adapter.build_round(bundle, configuration())
    before = (bundle / "schedule.json").read_bytes()
    with pytest.raises(FileExistsError):
        adapter.build_round(bundle, copy.deepcopy(configuration()))
    assert (bundle / "schedule.json").read_bytes() == before
    assert original == {source: hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
                        for source in original}
