"""Synthetic arithmetic controls; no field effect or causal claim is tested."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from specorganon.field_effect_analysis import (
    CLASSIFICATION,
    MARGIN_DIRECTION,
    FieldEffectAnalysisError,
    audit_field_effect_analysis,
)
from specorganon.field_guardrails import canonical_sha256
from test_audit_field_guardrails import _synthetic_inputs


def _case() -> tuple[dict, dict, dict, dict, dict]:
    plan, field, registry, measurements = _synthetic_inputs()
    for row in field["service"]["rows"]:
        if row["group_id"].startswith("i") and row["period"] == "post":
            row["consumed_service"]["value"] = 80
    for cell in registry["cells"]:
        if "margin" in cell:
            cell["margin"]["direction"] = MARGIN_DIRECTION
    measurements["registry_sha256"] = canonical_sha256(registry)
    analysis = {
        "schema": 1,
        "classification": CLASSIFICATION,
        "study_id": plan["study_id"],
        "v_rows": [
            {
                "group_id": row["group_id"], "period": row["period"],
                "v_fraction": "8/9" if row["group_id"].startswith("i") and row["period"] == "post"
                else "7/9",
            }
            for row in field["service"]["rows"]
        ],
        "unadjusted_g_fraction": "1/2",
        "adjusted_effect": {
            "estimate": 0.5,
            "ci95": {"level": 0.95, "sidedness": "two_sided", "lower": 0.2, "upper": 0.7},
            "estimator": "stratum_and_input_volume_adjusted",
            "resampling_unit": "group",
            "input_volume_source_id": "synthetic-unverified-input-volume",
        },
        "harm_outcomes": [
            ({"cell_id": cell["id"], "kind": "margin", "post_arm_difference_fraction": "0/1",
              "margin_direction": MARGIN_DIRECTION, "margin_value": 0.25,
              "descriptive_within_margin": True}
             if "margin" in cell else
             {"cell_id": cell["id"], "kind": "stop_condition",
              "post_intervention_total_fraction": "6/1", "assessment": "not_assessed"})
            for cell in registry["cells"]
        ],
    }
    return plan, field, registry, measurements, analysis


def _audit(case: tuple[dict, dict, dict, dict, dict]) -> dict:
    return audit_field_effect_analysis(*case)


def test_exact_v_and_unadjusted_g_are_checked_but_decision_is_not_ready() -> None:
    report = _audit(_case())
    assert report["service_ratios_recomputed"] == 24
    assert report["unadjusted_arm_means"] == {
        "control_post": "7/9", "control_pre": "7/9",
        "intervention_post": "8/9", "intervention_pre": "7/9",
    }
    assert report["unadjusted_g_fraction"] == "1/2"
    assert report["measured_harm_cells_checked"] == 30
    assert report["descriptive_margin_cells_within"] == 25
    assert report["textual_stop_cells_unassessed"] == 5
    assert report["adjusted_effect_declared"]["ci95"] == ["0.2", "0.7"]
    assert report["decision_ready"] is False
    assert report["criterion_3"]["status"] == "not_assessed"
    assert "not reproducible" in report["not_ready_reasons"][0]


@pytest.mark.parametrize("change,match", [
    ("bad_v", "v_fraction differs"),
    ("missing_v", "does not cover every"),
    ("duplicate_v", "unknown or duplicated"),
    ("bad_g", "unadjusted_g_fraction differs"),
    ("wrong_study", "study_id differ"),
    ("extra_field", "analysis must have exactly"),
])
def test_analysis_rejects_missing_or_incorrect_primary_arithmetic(change: str, match: str) -> None:
    case = _case()
    analysis = case[4]
    if change == "bad_v":
        analysis["v_rows"][0]["v_fraction"] = "0/1"
    elif change == "missing_v":
        analysis["v_rows"].pop()
    elif change == "duplicate_v":
        analysis["v_rows"].append(copy.deepcopy(analysis["v_rows"][0]))
    elif change == "bad_g":
        analysis["unadjusted_g_fraction"] = "499999999/1000000000"
    elif change == "wrong_study":
        analysis["study_id"] = "other-study"
    else:
        analysis["free_text_success"] = True
    with pytest.raises(FieldEffectAnalysisError, match=match):
        _audit(case)


@pytest.mark.parametrize("change,match", [
    ("missing", "must have exactly"),
    ("empty", "must be a finite number"),
    ("nonfinite_estimate", "finite"),
    ("nonfinite_lower", "finite"),
    ("nonfinite_upper", "finite"),
    ("zero_width", "empty or inverted"),
    ("inverted", "empty or inverted"),
    ("one_sided", "unambiguously two-sided"),
    ("wrong_level", "95% confidence"),
    ("wrong_resampling", "group resampling"),
])
def test_ci_claim_must_be_present_typed_and_structurally_valid(change: str, match: str) -> None:
    case = _case()
    adjusted = case[4]["adjusted_effect"]
    ci = adjusted["ci95"]
    if change == "missing":
        del ci["lower"]
    elif change == "empty":
        ci["lower"] = ""
    elif change == "nonfinite_estimate":
        adjusted["estimate"] = float("nan")
    elif change == "nonfinite_lower":
        ci["lower"] = float("-inf")
    elif change == "nonfinite_upper":
        ci["upper"] = float("inf")
    elif change == "zero_width":
        ci["lower"] = ci["upper"] = 0.5
    elif change == "inverted":
        ci["lower"], ci["upper"] = 0.7, 0.2
    elif change == "one_sided":
        ci["sidedness"] = "one_sided_upper"
    elif change == "wrong_level":
        ci["level"] = 0.9
    else:
        adjusted["resampling_unit"] = "row"
    with pytest.raises(FieldEffectAnalysisError, match=match):
        _audit(case)


def test_nonempty_ci_excluding_estimate_is_declared_only() -> None:
    case = _case()
    case[4]["adjusted_effect"]["estimate"] = 0.9
    report = _audit(case)
    assert report["classification"] == "field_effect_arithmetic_declared_only"
    assert report["adjusted_effect_declared"] == {"estimate": "0.9", "ci95": ["0.2", "0.7"]}
    assert report["decision_ready"] is False
    assert report["criterion_3"]["status"] == "not_assessed"


def test_descriptive_harm_margin_is_recomputed_and_can_fail() -> None:
    case = _case()
    _, _, _, measurements, analysis = case
    cell_id = next(row["cell_id"] for row in measurements["rows"] if row["cell_id"].endswith(":cost"))
    for row in measurements["rows"]:
        if (row["cell_id"] == cell_id and row["period"] == "post"
                and row["group_id"].startswith("i")):
            row["value"] = 1.5
    harm = next(row for row in analysis["harm_outcomes"] if row["cell_id"] == cell_id)
    with pytest.raises(FieldEffectAnalysisError, match="post_arm_difference_fraction differs"):
        _audit(case)
    harm["post_arm_difference_fraction"] = "1/2"
    with pytest.raises(FieldEffectAnalysisError, match="descriptive margin comparison is incorrect"):
        _audit(case)
    harm["descriptive_within_margin"] = False
    report = _audit(case)
    assert report["descriptive_margin_cells_within"] == 24
    assert report["decision_ready"] is False


@pytest.mark.parametrize("change,match", [
    ("missing_harm", "does not cover every"),
    ("duplicate_harm", "unknown or duplicated"),
    ("wrong_margin", "margin value differs"),
    ("wrong_stop", "textual stop condition cannot be assessed"),
    ("ambiguous_direction", "ambiguous or unsupported margin direction"),
])
def test_harm_cells_require_unique_typed_outcomes_and_exact_margins(change: str, match: str) -> None:
    case = _case()
    registry, analysis = case[2], case[4]
    margin = next(row for row in analysis["harm_outcomes"] if row["kind"] == "margin")
    stop = next(row for row in analysis["harm_outcomes"] if row["kind"] == "stop_condition")
    if change == "missing_harm":
        analysis["harm_outcomes"].pop()
    elif change == "duplicate_harm":
        analysis["harm_outcomes"].append(copy.deepcopy(margin))
    elif change == "wrong_margin":
        margin["margin_value"] = 0.2500000000001
    elif change == "wrong_stop":
        stop["assessment"] = "passed"
    else:
        cell = next(cell for cell in registry["cells"] if cell["id"] == margin["cell_id"])
        cell["margin"]["direction"] = "synthetic upper bound"
        case[3]["registry_sha256"] = canonical_sha256(registry)
    with pytest.raises(FieldEffectAnalysisError, match=match):
        _audit(case)


def test_g_is_not_applicable_when_intervention_pre_service_has_no_loss() -> None:
    case = _case()
    field, analysis = case[1], case[4]
    for row in field["service"]["rows"]:
        if row["group_id"].startswith("i") and row["period"] == "pre":
            row["consumed_service"]["value"] = 90
    for row in analysis["v_rows"]:
        if row["group_id"].startswith("i") and row["period"] == "pre":
            row["v_fraction"] = "1/1"
    with pytest.raises(FieldEffectAnalysisError, match="G is not applicable"):
        _audit(case)


def test_installed_module_cli_reports_non_decisive_arithmetic(tmp_path: Path) -> None:
    names = ("plan", "field", "registry", "measurements", "analysis")
    paths = []
    case = _case()
    for name, value in zip(names, case, strict=True):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        paths.append(str(path))
    result = subprocess.run(
        [sys.executable, "-m", "specorganon.field_effect_analysis", *paths],
        text=True, capture_output=True, check=True,
    )
    assert json.loads(result.stdout) == _audit(case)
    assert result.stderr == ""
