"""Real original-source CLI preparation and synthetic structure; no model runs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

DOSSIER = Path(__file__).resolve().parent
ROOT = DOSSIER.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import plan_coordinated_development as planner  # noqa: E402
import prepare_coordinated_development as preparer  # noqa: E402
from test_development_delivery_contract import structural_fixture  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--source-freeze", required=True, type=Path)
    args = parser.parse_args()
    destination = args.destination
    assert destination.is_absolute() and destination.is_dir() and not destination.is_symlink()
    assert not any(destination.iterdir()), "integration must preserve its new empty destination"
    freeze_raw = args.source_freeze.read_bytes()
    freeze = json.loads(freeze_raw)
    for row in freeze["records"]:
        raw = (ROOT / row["path"]).read_bytes()
        assert len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"], row["path"]
    for row in freeze["external_tools"]:
        raw = Path(row["path"]).read_bytes()
        assert len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"], row["path"]
    freeze_sha = hashlib.sha256(freeze_raw).hexdigest()
    config = destination / "configuration.json"
    config.write_bytes((DOSSIER / "fixture_configuration.json").read_bytes())
    bundle = destination / "bundle"
    public = DOSSIER / "public_contract"
    records = []

    def invoke(argv: list[str]) -> dict:
        number = len(records) + 1
        start = time.monotonic()
        process = subprocess.run([sys.executable, "-I", "-B", *argv], cwd=ROOT,
                                 capture_output=True, timeout=120, check=False)
        (destination / f"{number:02d}.stdout").write_bytes(process.stdout)
        (destination / f"{number:02d}.stderr").write_bytes(process.stderr)
        row = {"argv": [sys.executable, "-I", "-B", *argv], "exit_code": process.returncode,
               "wall_seconds": time.monotonic() - start, "stdout": f"{number:02d}.stdout",
               "stderr": f"{number:02d}.stderr"}
        records.append(row)
        (destination / f"{number:02d}.json").write_text(json.dumps(row, indent=2) + "\n")
        assert process.returncode == 0, process.stderr.decode(errors="replace")
        return json.loads(process.stdout)

    script = str(ROOT / "scripts/prepare_coordinated_development.py")
    built = invoke([script, "build", "--destination", str(bundle), "--configuration", str(config),
                    "--contract-dir", str(public), "--source-freeze-sha256", freeze_sha])
    verified_before = invoke([script, "verify", "--bundle", str(bundle)])
    contract = bundle / "assets/delivery_contract.json"
    validated = invoke([str(ROOT / "scripts/development_delivery_contract.py"), "validate", str(contract),
                        "--rubric", str(bundle / "assets/rubric.json")])
    assert validated["quality_assessed"] is False and validated["execution_authorized"] is False
    schedule = planner.validate_schedule(json.loads((bundle / "schedule.json").read_bytes()))
    assert schedule["source_freeze_sha256"] == freeze_sha
    assert schedule["run_count"] == 12 and schedule["block_count"] == 4
    assert {(row["arm"], row["case_id"], row["replica"]) for row in schedule["runs"]} == {
        (arm, case, replica) for arm in "ABC" for case in ("D-F", "D-E") for replica in (1, 2)}
    assert {row["mode"] for row in schedule["runs"]} == {"sequential", "graph", "risk"}
    bindings = []
    for row in schedule["runs"]:
        descriptor = planner.runtime_descriptor(schedule, row["run_id"])
        bound = planner.validate_runtime_binding(schedule, row["run_id"], descriptor)
        assert bound["binding_matches"] and not bound["runtime_authenticated"] and not bound["execution_authorized"]
        bindings.append({"descriptor": descriptor, "binding": bound})
    rejected = []
    for field, value in [("coordination", {"profile": "solo", "roles": ["leader"]}),
                         ("execution_profile", "legacy_solo"), ("max_model_requests", 129)]:
        descriptor = copy.deepcopy(bindings[0]["descriptor"])
        descriptor[field] = value
        try:
            planner.validate_runtime_binding(schedule, schedule["runs"][0]["run_id"], descriptor)
        except ValueError as exc:
            rejected.append({"field": field, "error": str(exc)})
        else:
            raise AssertionError("mixed or changed runtime descriptor was accepted")
    round_two = copy.deepcopy(schedule["manifest"])
    round_two["base"]["round"] = 2
    try:
        planner.compile_schedule(round_two)
    except ValueError as exc:
        rejected.append({"field": "round", "error": str(exc)})
    else:
        raise AssertionError("R2 was compiled before R1 and adaptation freeze")
    structures = []
    for case_id, names in preparer.original.CASE_INPUTS.items():
        for name in names:
            assert (bundle / "assets" / case_id / Path(name).name).read_bytes() == (ROOT / name).read_bytes()
        rows = [row for row in schedule["runs"] if row["case_id"] == case_id]
        assert len({row["case_package_sha256"] for row in rows}) == 1
        for arm in "ABC":
            work = destination / f"structure-{case_id}-{arm}"
            work.mkdir(mode=0o700)
            case = bundle / "assets" / case_id
            structural_fixture(case, work)
            result = invoke([str(ROOT / "scripts/development_delivery_contract.py"),
                             "check", str(contract), str(case), str(work)])
            assert result["structural_checks_passed"] and result["unresolved_quantity_fields"] > 0
            for key in ["participant_executed", "quality_assessed", "formal_cell_executed", "normative_approval",
                        "source_passages_verified", "metric_generation_authenticated", "causal_impact_assessed"]:
                assert result[key] is False
            assert not (work / "execution-marker").exists()
            structures.append({"case_id": case_id, "arm_label": arm, "work": str(work), "report": result})
    verified_after = invoke([script, "verify", "--bundle", str(bundle)])
    assert verified_before == verified_after
    summary = {"schema": 1, "classification": "original_source_preparation_and_synthetic_structure_not_model_runs",
               "source_freeze_sha256": freeze_sha, "runtime_root": str(destination),
               "interpreter": sys.executable, "bundle": str(bundle), "build": built,
               "verification_before": verified_before, "verification_after": verified_after,
               "schedule_sha256": schedule["schedule_sha256"], "prepared_ids": [row["run_id"] for row in schedule["runs"]],
               "bindings": bindings, "rejections": rejected, "structural_fixtures": structures,
               "commands": records, "same_case_bytes_across_arms": True,
               "shared_contract_rubric_and_coordination_bytes": True, "participant_execution": False,
               "model_requests": 0, "formal_cells_executed": 0, "quality_assessed": False,
               "runtime_authenticated": False, "execution_authorized": False}
    (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({key: summary[key] for key in ["classification", "schedule_sha256", "prepared_ids",
                     "model_requests", "formal_cells_executed", "quality_assessed", "execution_authorized"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
