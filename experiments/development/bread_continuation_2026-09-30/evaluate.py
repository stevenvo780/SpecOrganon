"""Frozen development projection and three one-use offline input negatives; not Q."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from local_replay_sandbox import default_python_runtime_roots, run_sandboxed  # noqa: E402
from run_prototype_checkpoint import _artifact_record, _atomic, _json, _read  # noqa: E402


def project(metrics: dict, table: dict, reference: dict) -> dict:
    """Check predeclared values and unit/nonnull base separately, without editing metrics."""
    rows = table["categories"]
    known = [r for r in rows if r["min_slices"] is not None]
    closed = [r for r in rows if r["max_slices"] is not None]
    total, known_n, closed_n = table["reported_total"], sum(r["count"] for r in known), sum(r["count"] for r in closed)
    lower = sum(r["count"] * r["min_slices"] for r in known)
    closed_lower = sum(r["count"] * r["min_slices"] for r in closed)
    closed_upper = sum(r["count"] * r["max_slices"] for r in closed)
    expected = [
        ("milling.wheat_input", 1000, "kg"),
        *[(f"milling.outputs.{name}", Fraction(reference["milling"][name + "_kg"]), "kg")
          for name in ("refined_flour", "whole_flour", "bran")],
        ("milling.outputs_sum", 1000, "kg"), ("milling.balance_residual", 0, "kg"),
        ("baking_energy.piece_mass", Fraction(reference["baking"]["bread_piece_mass_kg"]), "kg"),
        ("baking_energy.electricity_per_kg", Fraction(297, 736), "kWh/kg_bread"),
        ("baking_energy.natural_gas_per_kg", Fraction(5, 32), "kWh/kg_bread"),
        ("baking_energy.sum_per_kg", Fraction(103, 184), "kWh/kg_bread"),
        *[(f"survey.{name}_respondents", count, "respondents") for name, count in
          (("total", total), ("known", known_n), ("unknown", total - known_n),
           ("open_category", known_n - closed_n), ("closed_category", closed_n))],
        ("survey.lower_bound_total_all", lower, "slices/week"),
        ("survey.lower_bound_total_known", lower, "slices/week"),
        ("survey.lower_bound_mean_all", Fraction(lower, total), "slices/household/week"),
        ("survey.lower_bound_mean_known", Fraction(lower, known_n), "slices/household/week"),
        ("survey.closed_total_interval.lower", closed_lower, "slices/week"),
        ("survey.closed_mean_interval.lower", Fraction(closed_lower, closed_n), "slices/household/week"),
        ("survey.closed_total_interval.upper", closed_upper, "slices/week"),
        ("survey.closed_mean_interval.upper", Fraction(closed_upper, closed_n), "slices/household/week"),
        ("survey.finite_upper_bound_all", False, None),
        ("survey.finite_upper_bound_known", False, None),
    ]
    checks = []
    for path, number, unit in expected:
        observed = metrics
        for part in path.split("."):
            observed = observed.get(part) if type(observed) is dict else None
        actual = observed.get("value") if type(observed) is dict else observed
        try:
            agrees = (type(actual) is bool and actual is number) if type(number) is bool else (
                type(actual) in {int, float} and math.isfinite(actual)
                and math.isclose(actual, float(number), rel_tol=1e-12, abs_tol=1e-12))
        except OverflowError:
            agrees = False
        quantity = unit is None or (
            type(observed) is dict and observed.get("unit") == unit
            and type(observed.get("base")) is str and bool(observed["base"].strip()))
        checks.append({"path": path, "expected": str(number), "expected_unit": unit, "arithmetic_agrees": agrees,
                       "unit_and_nonempty_base_contract": quantity})
    return {"classification": "predeclared_exposed_projection_not_quality_score",
            "arithmetic_agreements": sum(c["arithmetic_agrees"] for c in checks),
            "arithmetic_check_count": len(checks),
            "quantity_contract_agreements": sum(c["unit_and_nonempty_base_contract"] for c in checks if c["expected_unit"] is not None),
            "quantity_contract_check_count": sum(c["expected_unit"] is not None for c in checks), "checks": checks,
            "base_semantics_verified": False, "source_passages_verified_by_this_projection": False,
            "Q": None, "method_winner": None, "counts_toward_required_24_runs": False}


def evaluate(directory: Path) -> dict:
    import run_bread_continuation as workflow

    directory = directory.resolve(strict=True)
    checked = workflow.status(directory)
    if checked["state"] != "replayed":
        raise ValueError("baseline has not completed its one-use reviewed replay")
    plan = _json(_read(workflow.PLAN))
    reference_path = ROOT / plan["evaluation"]["reference_record"]["path"]
    raw = _read(reference_path)
    if _artifact_record(reference_path) != {k: plan["evaluation"]["reference_record"][k] for k in ("bytes", "sha256")}:
        raise ValueError("predeclared reference bytes changed")
    metrics = _json(_read(directory / "metrics.json"))
    table = _json(_read(directory / "input/survey_table1.json"))
    projection = project(metrics, table, _json(raw))
    output = directory / "evaluation"
    output.mkdir(mode=0o700)  # Existing directory is a consumed attempt, never replaced.
    _atomic(output / "admission.json", {"state": "started", "cases": plan["evaluation"]["negative_script_runs"]})
    script = _read(directory / "analysis.py", 32768)
    payload = plan["payload_prefix"].encode() + script
    payload_sha = hashlib.sha256(payload).hexdigest()
    deadline = time.monotonic() + plan["evaluation"]["negative_total_active_seconds"]
    results = []
    for name in plan["evaluation"]["negative_script_runs"]:
        case = output / name
        case.mkdir(mode=0o700)
        inputs = case / "input"
        shutil.copytree(directory / "input", inputs)
        if name == "corrupt_pdf":
            with (inputs / "source_lca.pdf").open("ab") as stream:
                stream.write(b"\nD097 declared integrity-negative byte\n")
        elif name == "missing_pdf":
            (inputs / "source_lca.pdf").unlink()
        elif name == "unit_conflict_rehashed":
            claims = _json(_read(inputs / "source_claims.json"))
            next(c for c in claims["claims"] if c["key"] == "bakery_electricity")["unit"] = "kg"
            _atomic(inputs / "source_claims.json", claims)
            manifest = _json(_read(inputs / "source_manifest.json"))
            entry = next(c for c in manifest["files"] if c["visible_file"] == "source_claims.json")
            entry.update(_artifact_record(inputs / "source_claims.json"))
            _atomic(inputs / "source_manifest.json", manifest)
        else:
            raise ValueError("unknown predeclared negative")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            results.append({"case": name, "rejected_invalid_input": False, "error": "shared negative deadline exhausted"})
            continue
        out, err = case / "stdout.json", case / "stderr.txt"
        captured = run_sandboxed(
            argv=[str(case / "launch.py"), str(inputs)], cwd=inputs, read_roots=[inputs],
            write_roots=[], runtime_roots=(*default_python_runtime_roots(), Path("/usr/bin/python3.12").resolve(strict=True)),
            stdout_path=out, stderr_path=err, timeout_seconds=min(30.0, remaining),
            cpu_seconds=plan["evaluation"]["negative_cpu_seconds_each"],
            address_space_bytes=plan["replay"]["address_space_bytes"],
            file_bytes_per_file=plan["evaluation"]["negative_file_limit_bytes"],
            env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"},
            sealed_executable_bytes=payload, sealed_executable_sha256=payload_sha)
        valid_metrics = False
        try:
            value = _json(_read(out))
            valid_metrics = all(k in value for k in ("milling", "baking_energy", "survey"))
        except (ValueError, OSError):
            pass
        rejection = (captured.launch_error is None and not captured.timed_out
                     and captured.exit_code not in {None, 0} and err.stat().st_size > 0 and not valid_metrics)
        results.append({"case": name, **asdict(captured), "rejected_invalid_input": rejection,
                        "valid_metrics_emitted": valid_metrics,
                        "stdout": _artifact_record(out), "stderr": _artifact_record(err),
                        "coherence_cause_isolated": False,
                        "input_records": {p.name: _artifact_record(p) for p in inputs.iterdir() if p.is_file()}})
    workflow.status(directory)  # Recheck baseline and parent after executing the reviewed code.
    result = {"schema": 1, "decision": "D-097", "projection": projection,
              "negative_cases": results, "all_negatives_rejected": all(r["rejected_invalid_input"] for r in results),
              "source_and_report_quality": "requires_separate_review", "field_impact": "not_observed",
              "criterion_4": "not_assessed", "global_acceptance": "0/5"}
    _atomic(output / "result.json", result)
    _atomic(output / "admission.json", {"state": "complete", "cases_run": len(results),
                                       "result": _artifact_record(output / "result.json")})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.directory), ensure_ascii=False, sort_keys=True))
