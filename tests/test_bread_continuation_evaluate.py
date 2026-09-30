from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "bread_continuation_evaluate",
    ROOT / "experiments/development/bread_continuation_2026-09-30/evaluate.py",
)
assert SPEC and SPEC.loader
evaluator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluator)


def material():
    base = ROOT / "experiments/development/bread_prototype_feasibility_2026-09-30"
    metrics = json.loads((base / "runs/B-01/metrics.json").read_text())
    metrics["milling"]["outputs_sum"] = metrics["milling"].pop("sum_outputs")
    for key in ("total_all", "total_known", "mean_all", "mean_known"):
        metrics["survey"]["lower_bound_" + key] = metrics["survey"].pop("lower_" + key)
    table = json.loads((ROOT / "cases/bread_norway/survey_table1.json").read_text())
    reference = json.loads((base / "reference.json").read_text())
    return metrics, table, reference


def test_projection_matches_independently_replayed_historical_arithmetic():
    result = evaluator.project(*material())
    assert result["arithmetic_agreements"] == result["arithmetic_check_count"] == 25
    assert result["quantity_contract_check_count"] == 23
    assert result["Q"] is None and not result["source_passages_verified_by_this_projection"]


@pytest.mark.parametrize("bad_value", [True, float("inf"), 10 ** 1000, None, "1000"])
def test_projection_rejects_wrong_numeric_types_without_crash(bad_value):
    metrics, table, reference = material()
    metrics["milling"]["wheat_input"]["value"] = bad_value
    result = evaluator.project(metrics, table, reference)
    assert result["arithmetic_agreements"] == 24


def test_equal_numbers_do_not_hide_wrong_unit_or_empty_base():
    metrics, table, reference = material()
    metrics["milling"]["wheat_input"]["unit"] = "%"
    metrics["milling"]["outputs"]["bran"]["base"] = " "
    result = evaluator.project(metrics, table, reference)
    assert result["arithmetic_agreements"] == 25
    by_path = {c["path"]: c for c in result["checks"]}
    assert not by_path["milling.wheat_input"]["unit_and_nonempty_base_contract"]
    assert not by_path["milling.outputs.bran"]["unit_and_nonempty_base_contract"]


def test_empty_metrics_and_numeric_zero_do_not_pass_as_boolean_false():
    metrics, table, reference = material()
    assert evaluator.project({}, table, reference)["arithmetic_agreements"] == 0
    metrics["survey"]["finite_upper_bound_all"] = 0
    assert evaluator.project(metrics, table, reference)["arithmetic_agreements"] == 24


def test_real_sandbox_rejects_false_green_negative_and_blocks_second_evaluation(tmp_path, monkeypatch):
    import run_bread_continuation as workflow

    monkeypatch.setattr(workflow, "status", lambda _: {"state": "replayed"})
    stage = tmp_path / "stage"
    stage.mkdir()
    inputs = stage / "input"
    inputs.mkdir()
    plan = json.loads(workflow.PLAN.read_text())
    for name, record in plan["source_files"].items():
        shutil.copyfile(ROOT / record["path"], inputs / name)
    (stage / "analysis.py").write_text('print(\'{"milling":{},"baking_energy":{},"survey":{}}\')\n')
    (stage / "metrics.json").write_text('{}\n')
    result = evaluator.evaluate(stage)
    assert len(result["negative_cases"]) == 3
    assert not result["all_negatives_rejected"]
    for case in result["negative_cases"]:
        assert case["exit_code"] == 0 and case["landlock_abi"] >= 5
        assert case["valid_metrics_emitted"] and not case["rejected_invalid_input"]
    with pytest.raises(FileExistsError):
        evaluator.evaluate(stage)
