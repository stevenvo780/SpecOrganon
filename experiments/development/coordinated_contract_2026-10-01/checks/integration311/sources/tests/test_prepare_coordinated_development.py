"""Public original DEV bundles, complete byte verification and no run execution."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import prepare_coordinated_development as preparer  # noqa: E402

PUBLIC = ROOT / "experiments/development/coordinated_contract_2026-10-01/public_contract"
FREEZE = "d" * 64


def configuration() -> dict:
    model = "offline-fixture-model"
    return {"schema": 1, "seed": 118, "model": {
        "model_id": model, "version": model, "family": "fixture", "tier": "fixture",
        "effort": "medium", "effort_provider_value": "medium"},
        "price_profile": {"model": model, "input_rate_micro_usd_per_million": 1000000,
                          "cached_input_rate_micro_usd_per_million": 1000000,
                          "cache_write_rate_micro_usd_per_million": 1000000,
                          "output_rate_micro_usd_per_million": 1000000},
        "per_run_limits": {"measured_tokens": 1000, "active_seconds": 120, "tool_calls": 64},
        "max_model_requests": 128, "cost_limit_micro_usd": 1000,
        "provider_route": {"provider": "fixture", "api": "responses", "version": "offline-v1", "service_tier": "default"}}


@pytest.fixture
def contracts(tmp_path):
    destination = tmp_path / "public_contract"
    destination.mkdir(mode=0o700)
    for name in preparer.CONTRACT_NAMES:
        (destination / name).write_bytes((PUBLIC / name).read_bytes())
    return destination


@pytest.fixture
def bundle(tmp_path, contracts):
    destination = tmp_path / "bundle"
    preparer.build_coordinated_round(destination, configuration(), contracts, FREEZE)
    return destination


def repin_inventory(bundle):
    path = bundle / "bundle.json"
    receipt = json.loads(path.read_bytes())
    receipt["inventory"] = preparer._inventory(bundle)
    path.write_bytes(preparer._canonical(receipt))


def test_original_cases_shared_all_six_combinations_and_deterministic_schedule(bundle, tmp_path, contracts):
    result = preparer.verify_coordinated_bundle(bundle)
    assert result["prepared_cell_count"] == 12 and result["formal_cells_executed"] == 0
    assert result["scope"] == "preparation_and_byte_verification_only"
    schedule = json.loads((bundle / "schedule.json").read_bytes())
    assert {(run["arm"], run["case_id"], run["replica"]) for run in schedule["runs"]} == {
        (arm, case_id, replica) for arm in "ABC" for case_id in ("D-F", "D-E") for replica in (1, 2)}
    assert all(run["run_id"].startswith("dev-coord-") and run["agent_count"] == 4
               and run["agents"] == "leader_two_workers_reviewer_v1" for run in schedule["runs"])
    assert schedule["coordination"] == preparer.planner.COORDINATION
    for case_id, sources in preparer.original.CASE_INPUTS.items():
        for name in sources:
            assert (bundle / "assets" / case_id / Path(name).name).read_bytes() == (ROOT / name).read_bytes()
        runs = [run for run in schedule["runs"] if run["case_id"] == case_id]
        assert len({run["case_package_sha256"] for run in runs}) == 1
    capsule = json.loads((bundle / "assets/D-F/case.json").read_bytes())
    assert any(row["path"] == "source_lca_page_01.txt" for row in capsule["files"])
    preparer.text_inputs.verify_text_inputs(bundle / "assets/D-F")
    assert {json.loads((bundle / "assets" / f"prompt_{arm}").read_bytes())["mode"] for arm in "ABC"} == {
        "sequential", "graph", "risk"}
    assert "executes calls serially" not in (bundle / "assets/prompt_C").read_text()
    assert not any((bundle / name).exists() for name in ("ledger", "context", "claim.json", "run.json", "work"))
    for name in preparer.CONTRACT_NAMES:
        assert (bundle / "assets" / name).read_bytes() == (contracts / name).read_bytes()
    again = tmp_path / "again"
    preparer.build_coordinated_round(again, configuration(), contracts, FREEZE)
    assert (again / "schedule.json").read_bytes() == (bundle / "schedule.json").read_bytes()


@pytest.mark.parametrize("bad", ["bool_schema", "bool_tokens", "price_mismatch", "unknown_field",
                                  "price_digest", "invalid_route", "negative_cost"])
def test_bad_configuration_has_zero_output_effects(tmp_path, contracts, bad):
    value = configuration()
    if bad == "bool_schema":
        value["schema"] = True
    elif bad == "bool_tokens":
        value["per_run_limits"]["measured_tokens"] = True
    elif bad == "price_mismatch":
        value["price_profile"]["model"] = "different-model"
    elif bad == "unknown_field":
        value["execution_authorized"] = True
    elif bad == "price_digest":
        value["model"]["price_profile_sha256"] = FREEZE
    elif bad == "invalid_route":
        value["provider_route"]["api"] = "https://example.invalid"
    else:
        value["cost_limit_micro_usd"] = -1
    target = tmp_path / "invalid"
    with pytest.raises(ValueError):
        preparer.build_coordinated_round(target, value, contracts, FREEZE)
    assert not target.exists()


@pytest.mark.parametrize("bad", ["missing", "extra", "invalid_delivery", "invalid_rubric", "bad_freeze"])
def test_bad_contract_or_freeze_rejected_before_output(tmp_path, contracts, bad):
    freeze = FREEZE
    if bad == "missing":
        (contracts / "rubric.json").unlink()
    elif bad == "extra":
        (contracts / "reference_answer.json").write_text("{}")
    elif bad == "invalid_delivery":
        (contracts / "delivery_contract.json").write_text('{"schema":true}')
    elif bad == "invalid_rubric":
        (contracts / "rubric.json").write_text('{"schema":1}')
    else:
        freeze = "not-a-digest"
    target = tmp_path / "invalid"
    with pytest.raises((ValueError, OSError)):
        preparer.build_coordinated_round(target, configuration(), contracts, freeze)
    assert not target.exists()


@pytest.mark.parametrize("bad", ["contract_child", "source_child", "output_alias", "contract_alias"])
def test_overlap_or_symlink_roots_rejected_before_output(tmp_path, contracts, bad):
    if bad == "contract_child":
        target = contracts / "bundle"
    elif bad == "source_child":
        target = ROOT / "cases/bread_development/D118-forbidden-output"
    elif bad == "output_alias":
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        target = alias / "bundle"
    else:
        alias = tmp_path / "alias"
        alias.symlink_to(contracts, target_is_directory=True)
        contracts = alias
        target = tmp_path / "bundle"
    before = {name: (contracts / name).read_bytes() for name in preparer.CONTRACT_NAMES}
    with pytest.raises((ValueError, OSError)):
        preparer.build_coordinated_round(target, configuration(), contracts, FREEZE)
    assert not target.exists()
    assert before == {name: (contracts / name).read_bytes() for name in preparer.CONTRACT_NAMES}


def test_changed_original_source_rejected_before_mkdir(tmp_path, contracts, monkeypatch):
    copied = tmp_path / "public_sources"
    for name in preparer.original.SOURCE_PINS:
        target = copied / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    source = copied / "cases/building_energy/sample_first_complete_week.csv"
    source.write_bytes(source.read_bytes() + b"\n")
    monkeypatch.setattr(preparer.original, "ROOT", copied)
    target = tmp_path / "bundle"
    with pytest.raises(ValueError, match="public source differs"):
        preparer.build_coordinated_round(target, configuration(), contracts, FREEZE)
    assert not target.exists()


@pytest.mark.parametrize("name", ["assets/D-F/source_lca_page_01.txt", "assets/D-E/sample_first_complete_week.csv",
                                   "assets/method_tool", "assets/analysis_tool", "price_profile.json",
                                   "assets/delivery_contract.json", "assets/rubric.json", "assets/runtime_policy.json",
                                   "assets/D-F.zip", "schedule.json"])
def test_every_source_tool_price_contract_package_and_schedule_tamper_rejected(bundle, name):
    path = bundle / name
    path.chmod(0o600)
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        preparer.verify_coordinated_bundle(bundle)


@pytest.mark.parametrize("change", ["extra_file", "extra_directory", "missing", "symlink", "fifo"])
def test_closed_inventory_missing_extra_and_nonregular_rejected(bundle, change):
    if change == "extra_file":
        (bundle / "unexpected").write_text("extra public fixture")
    elif change == "extra_directory":
        (bundle / "unexpected").mkdir(mode=0o700)
    elif change == "missing":
        (bundle / "assets/coordination_prompt.md").unlink()
    elif change == "symlink":
        (bundle / "unexpected").symlink_to(bundle / "price_profile.json")
    else:
        import os
        os.mkfifo(bundle / "unexpected", 0o600)
    with pytest.raises((ValueError, OSError)):
        preparer.verify_coordinated_bundle(bundle)


@pytest.mark.parametrize("name", ["assets/D-F/source_claims.json", "assets/method_tool",
                                   "assets/coordination_prompt.md", "assets/runtime_policy.json"])
def test_repinning_inventory_does_not_make_changed_semantic_bytes_valid(bundle, name):
    path = bundle / name
    path.chmod(0o600)
    path.write_bytes(path.read_bytes() + b"\n")
    repin_inventory(bundle)
    with pytest.raises(ValueError, match="source contract"):
        preparer.verify_coordinated_bundle(bundle)


def test_original_contract_after_build_changed_and_repeated_destination_rejected(bundle, contracts):
    before = (bundle / "schedule.json").read_bytes()
    with pytest.raises(FileExistsError):
        preparer.build_coordinated_round(bundle, configuration(), contracts, FREEZE)
    assert (bundle / "schedule.json").read_bytes() == before
    (contracts / "coordination_prompt.md").write_text("changed public contract")
    with pytest.raises(ValueError, match="captured bytes"):
        preparer.verify_coordinated_bundle(bundle)


def test_real_cli_build_and_fresh_process_verify(tmp_path, contracts):
    target = tmp_path / "cli_bundle"
    config = tmp_path / "configuration.json"
    config.write_text(json.dumps(configuration()))
    script = ROOT / "scripts/prepare_coordinated_development.py"
    built = subprocess.run([sys.executable, "-B", "-I", str(script), "build",
        "--destination", str(target), "--configuration", str(config), "--contract-dir", str(contracts),
        "--source-freeze-sha256", FREEZE], capture_output=True, text=True, timeout=90)
    assert built.returncode == 0, built.stdout + built.stderr
    checked = subprocess.run([sys.executable, "-B", "-I", str(script), "verify", "--bundle", str(target)],
        capture_output=True, text=True, timeout=60)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert json.loads(checked.stdout) == json.loads(built.stdout)
    before = {name: (target / name).read_bytes() for name in ("schedule.json", "bundle.json")}
    (target / "assets/prompt_A").write_bytes(b'{"alternative":"C","mode":"risk"}\n')
    failed = subprocess.run([sys.executable, "-B", "-I", str(script), "verify", "--bundle", str(target)],
        capture_output=True, text=True, timeout=60)
    assert failed.returncode == 2
    assert before == {name: (target / name).read_bytes() for name in before}
