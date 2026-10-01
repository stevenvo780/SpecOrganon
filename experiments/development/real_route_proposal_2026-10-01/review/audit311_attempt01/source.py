"""Independent finite audit: verify existing bundles and validate declarations only."""

from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
DOSSIER = Path(__file__).resolve().parents[1]
PRIOR = "9f90b79b75c087ea5e9c6ab87f270880e7fb684a"
PRIOR_RECEIPT = ROOT / "experiments/development/coordinated_observation_2026-10-01/receipt.json"
PRIOR_SHA = "76c59b7597884ee0517a88836dffc377658a5bf1fe91e512e9dd1d6f0f35ec22"
SPEC = ROOT / "experiments/development/coordinated_contract_2026-10-01/source_freeze.json"
SPEC_SHA = "6724df13d881e46b08c17213e440a5e231eca16c5541abc283f06ae101f4a044"
DOCS = {"docs/activacion_validacion.md", "docs/decisiones.md", "docs/estado.md", "docs/validacion_actual.md"}
OPTIONS = ("astra", "luna")
COORDINATES = {(case, replica, arm) for case in ("D-F", "D-E") for replica in (1, 2) for arm in "ABC"}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read(path: Path) -> bytes:
    metadata = path.lstat()
    assert stat.S_ISREG(metadata.st_mode), str(path)
    raw = path.read_bytes()
    assert len(raw) == metadata.st_size, str(path)
    return raw


def load(path: Path) -> dict:
    return json.loads(read(path))


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def file_record(path: Path) -> dict:
    raw = read(path)
    return {"path": str(path), "bytes": len(raw), "sha256": sha(raw),
            "mode": stat.S_IMODE(path.lstat().st_mode)}


def snapshot(bundle: Path) -> dict:
    result = {".": {"kind": "directory", "mode": stat.S_IMODE(bundle.lstat().st_mode)}}
    for path in sorted(bundle.rglob("*")):
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            entry = {"kind": "directory", "mode": stat.S_IMODE(metadata.st_mode)}
        else:
            assert stat.S_ISREG(metadata.st_mode), str(path)
            raw = read(path)
            entry = {"kind": "regular", "mode": stat.S_IMODE(metadata.st_mode),
                     "bytes": len(raw), "sha256": sha(raw)}
        result[path.relative_to(bundle).as_posix()] = entry
    return result


def baseline() -> dict:
    receipt_raw = read(PRIOR_RECEIPT)
    assert sha(receipt_raw) == PRIOR_SHA
    assert len(receipt_raw) == 1853998
    prior = json.loads(receipt_raw)
    assert len(prior["records"]) == 5879
    records = []
    old_docs = []
    for row in prior["records"]:
        if row["path"] in DOCS:
            result = subprocess.run(["git", "show", f"{PRIOR}:{row['path']}"], cwd=ROOT,
                                    capture_output=True, check=True)
            raw = result.stdout
            assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
            old_docs.append({"path": row["path"], "historical_sha256": sha(raw),
                             "current_matches_historical": sha(read(ROOT / row["path"])) == sha(raw)})
            continue
        path = ROOT / row["path"]
        actual = file_record(path)
        assert row["kind"] == "regular" and row["mode"] == "100644"
        assert actual["bytes"] == row["bytes"] and actual["sha256"] == row["sha256"]
        assert actual["mode"] == 0o644
        records.append(actual)
    assert len(records) == 5875 and len(old_docs) == 4
    assert sha(read(SPEC)) == SPEC_SHA
    freeze = load(SPEC)
    for row in freeze["records"] + freeze["external_tools"]:
        path = Path(row["path"])
        if not path.is_absolute():
            path = ROOT / path
        raw = read(path)
        assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
    return {"D121_non_active_doc_records_live": len(records), "D121_root_receipt_sha256": PRIOR_SHA,
            "D121_active_docs_historical_git_verified": old_docs,
            "D121_records_live_digest": sha(canonical(records)),
            "D118_freeze_sha256": SPEC_SHA, "D118_live_source_records": len(freeze["records"]),
            "D118_external_tools": freeze["external_tools"]}


def capture(argv: list[str], output: Path) -> dict:
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=240, check=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".stdout").write_bytes(result.stdout)
    output.with_suffix(".stderr").write_bytes(result.stderr)
    record = {"argv": argv, "exit_code": result.returncode,
              "stdout_sha256": sha(result.stdout), "stderr_sha256": sha(result.stderr)}
    output.with_suffix(".command.json").write_text(json.dumps(record, indent=2) + "\n")
    assert result.returncode == 0, record
    return {**record, "result": json.loads(result.stdout)}


def forecast_check() -> dict:
    forecast = load(DOSSIER / "forecast.json")
    rows = []
    expected_profiles = {
        "astra": (10000000, 1000000, 12500000, 50000000, 5000000),
        "luna": (100000, 10000, 125000, 500000, 50000),
    }
    keys = ("input_rate_micro_usd_per_million", "cached_input_rate_micro_usd_per_million",
            "cache_write_rate_micro_usd_per_million", "output_rate_micro_usd_per_million")
    assert len(forecast["candidates"]) == 2
    assert {row["candidate"] for row in forecast["candidates"]} == set(OPTIONS)
    for row in forecast["candidates"]:
        option = row["candidate"]
        configuration = load(DOSSIER / "candidates" / option / "configuration.json")
        profile = configuration["price_profile"]
        assert row["price_profile_declared"] == profile
        assert tuple(profile[key] for key in keys) == expected_profiles[option][:4]
        assert all(type(profile[key]) is int for key in keys)
        rate = max(profile[key] for key in keys)
        bound = (80000 * rate + 999999) // 1000000 + 128
        cap = configuration["cost_limit_micro_usd"]
        assert cap == expected_profiles[option][4]
        assert row["conditional_model_token_ceiling_micro_usd_per_cell"] == bound
        assert row["conditional_model_token_ceiling_micro_usd_for_12_cells"] == bound * 12
        assert row["conditional_model_token_ceiling_usd_per_cell"] == f"{bound / 1000000:.6f}"
        assert row["conditional_model_token_ceiling_usd_for_12_cells"] == f"{bound * 12 / 1000000:.6f}"
        assert row["proposed_local_model_budget_micro_usd_per_cell"] == cap
        assert row["proposed_local_model_budget_micro_usd_for_12_cells"] == cap * 12
        assert bound <= cap and row["conditional_ceiling_within_proposed_local_budget"] is True
        assert row["model_snapshot_pinned"] is False
        for key in ("account_access", "actual_model_version", "actual_provider", "effective_effort", "verified_API_calls"):
            assert row[key] is None
        rows.append({"option": option, "rate_micro_usd_per_million": rate,
                     "bound_micro_usd_per_cell": bound, "bound_micro_usd_per_12": bound * 12,
                     "proposed_cap_micro_usd_per_cell": cap})
    for key in ("execution_performed", "formal_cell_executed", "paid_route_authorized", "quality_assessed",
                "Q_demonstrated", "cost_authenticated", "full_cost_complete", "usage_authenticated",
                "model_version_authenticated", "effort_authenticated", "provider_identity_authenticated"):
        assert forecast[key] is False
    assert all(row["micro_usd"] is None for row in forecast["missing_costs"].values())
    assert forecast["selection"]["selected_candidate"] is None
    assert forecast["selection"]["execute_both_candidates"] is False
    assert forecast["common_roles"]["sum_of_role_turn_caps"] == 97
    assert forecast["envelope_for_one_selected_candidate_12_cells"]["measured_tokens"] == 960000
    assert forecast["envelope_for_one_selected_candidate_12_cells"]["max_model_requests"] == 1536
    assert forecast["envelope_for_one_selected_candidate_12_cells"]["tool_calls"] == 768
    assert forecast["envelope_for_one_selected_candidate_12_cells"]["active_seconds"] == 64800
    assert forecast["envelope_for_one_selected_candidate_12_cells"]["W_local_elapsed_seconds"] is None
    return {"rows": rows, "conditional_model_only": True, "unknown_costs_not_imputed_zero": True}


def audit(label: str, output: Path) -> dict:
    sys.path.insert(0, str(ROOT / "scripts"))
    import coordinated_prototype_runtime as runtime
    import plan_coordinated_development as planner
    import prepare_coordinated_development as preparer

    root_report = load(DOSSIER / "checks" / f"build{label}_attempt01/report.json")
    assert Path(sys.executable) == Path(root_report["python"])
    assert list(sys.version_info[:3]) == root_report["version"]
    before = baseline()
    candidate_paths = sorted((DOSSIER / "candidates").rglob("*.json"))
    source_paths = [ROOT / "scripts/prepare_coordinated_development.py",
                    ROOT / "scripts/plan_coordinated_development.py",
                    ROOT / "scripts/coordinated_prototype_runtime.py",
                    ROOT / "scripts/managed_token_ledger.py", DOSSIER / "capture_checks.py", DOSSIER / "forecast.json",
                    DOSSIER / "plan.md", DOSSIER / "planning_clarification.md", DOSSIER / "readiness.md",
                    DOSSIER / "sources.json", *candidate_paths]
    pins_before = [file_record(path) for path in source_paths]
    results = []
    for row in root_report["results"]:
        option = row["option"]
        original = DOSSIER / "checks" / f"build{label}_attempt01" / option
        bundle = Path(row["verify"]["result"]["bundle"])
        snap_before = snapshot(bundle)
        receipt = load(bundle / "bundle.json")
        assert receipt["source_freeze_sha256"] == SPEC_SHA
        assert receipt["tool_interpreter"] == sys.executable
        assert len(receipt["inventory"]["files"]) == 105
        assert len(receipt["inventory"]["directories"]) == 4
        assert len(snap_before) == 111
        for command in ("build", "verify"):
            stored = load(original / f"{command}.command.json")
            raw = read(original / f"{command}.stdout")
            err = read(original / f"{command}.stderr")
            assert stored["argv"] == row[command]["argv"]
            assert stored["exit_code"] == row[command]["exit_code"] == 0
            assert stored["stdout_sha256"] == row[command]["stdout_sha256"] == sha(raw)
            assert stored["stderr_sha256"] == row[command]["stderr_sha256"] == sha(err)
            assert err == b"" and json.loads(raw) == row[command]["result"]
        actual = capture(row["verify"]["argv"], output / option / "verify")
        assert actual["result"] == row["verify"]["result"]
        assert actual["stdout_sha256"] == row["verify"]["stdout_sha256"]
        for name in ("bundle.json", "schedule.json", "assets.json", "price_profile.json"):
            assert read(original / name) == read(bundle / name)
        assert read(original / "runtime_policy.json") == read(bundle / "assets/runtime_policy.json")
        configuration = load(DOSSIER / "candidates" / option / "configuration.json")
        assert configuration == load(bundle / "configuration.json")
        schedule = planner.validate_schedule(load(bundle / "schedule.json"))
        assert canonical(schedule) == canonical(planner.compile_schedule(schedule["manifest"]))
        coordinates = [(cell["case_id"], cell["replica"], cell["arm"]) for cell in schedule["runs"]]
        assert len(coordinates) == 12 and set(coordinates) == COORDINATES
        ids = [cell["run_id"] for cell in schedule["runs"]]
        assert len(set(ids)) == 12
        blocks = collections.defaultdict(list)
        descriptors = []
        runtime_config = load(DOSSIER / "candidates" / option / "runtime_configuration.json")
        for cell in schedule["runs"]:
            blocks[cell["block_id"]].append(cell)
            descriptor = planner.runtime_descriptor(schedule, cell["run_id"])
            validated = runtime.validate_configuration(runtime_config, descriptor)
            assert validated == runtime_config
            descriptors.append(descriptor)
        assert len(blocks) == 4
        for cells in blocks.values():
            assert {cell["arm"] for cell in cells} == set("ABC") and len(cells) == 3
            assert [cell["order_position"] for cell in cells] == [1, 2, 3]
            assert len({(cell["case_id"], cell["replica"], cell["release_block_order"]) for cell in cells}) == 1
        assert schedule["seed"] == 122
        assert schedule["per_run_limits"] == {"active_seconds": 5400, "measured_tokens": 80000, "tool_calls": 64}
        assert schedule["max_model_requests"] == 128
        assert schedule["provider_route"] == {"provider": "openai", "api": "responses", "version": "v1", "service_tier": "default"}
        assert receipt["source_records"] == preparer._source_records(Path(receipt["contract_dir"]))
        material = {}
        for name, entry in snap_before.items():
            if entry["kind"] == "regular" and name.startswith("assets/"):
                material[name] = entry["sha256"]
        tool_policy = load(bundle / "assets/tool_policy")
        for tool in tool_policy["generic_tools"]:
            assert tool["executable_sha256"] == sha(read(bundle / "assets" / (tool["id"] + "_tool")))
        policy = load(bundle / "assets/runtime_policy.json")
        semantic_policy = copy.deepcopy(policy)
        del semantic_policy["model"], semantic_policy["cost_limit_micro_usd"]
        semantic_tool_policy = copy.deepcopy(tool_policy)
        for tool in semantic_tool_policy["generic_tools"]:
            del tool["executable_sha256"]
        snap_after = snapshot(bundle)
        assert snap_before == snap_after
        assert "run.json" not in snap_after and "publication.json" not in snap_after
        result = {"label": label, "option": option, "bundle": str(bundle),
                  "verify": actual, "whole_inventory_before_after_equal": True,
                  "inventory_sha256": sha(canonical(snap_before)), "inventory": snap_before,
                  "source_records": receipt["source_records"], "schedule_sha256": schedule["schedule_sha256"],
                  "run_ids": ids, "coordinates": coordinates, "runtime_configurations_pure_validated": len(descriptors),
                  "release_sequence": [{key: cell[key] for key in ("case_id", "replica", "arm", "order_position", "release_block_order")}
                                       for cell in schedule["runs"]],
                  "material_sha256": material, "runtime_configuration": runtime_config,
                  "semantic_runtime_policy": semantic_policy, "semantic_tool_policy": semantic_tool_policy}
        results.append(result)
    after = baseline()
    assert before["D121_records_live_digest"] == after["D121_records_live_digest"]
    pins_after = [file_record(path) for path in source_paths]
    assert pins_before == pins_after
    report = {"schema": 1, "classification": "independent_offline_proposal_audit_not_R1",
              "python": sys.executable, "version": list(sys.version_info[:3]), "source_pins": pins_before,
              "source_candidate_bytes_before_after_equal": True, "baseline_before": before, "baseline_after": after,
              "original_verifies_rerun_readonly": 2, "builds_rerun": 0, "results": results,
              "forecast": forecast_check(), "provider_calls_performed": 0,
              "runtime_prepare_step_release_claim_performed": False, "formal_cells_executed": 0}
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return {"report": str(output / "report.json"), "verified_existing_bundles": 2, "pure_validated_cells": 24}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", choices=("311", "312"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert args.output.resolve().is_relative_to(DOSSIER / "review")
    print(json.dumps(audit(args.label, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
