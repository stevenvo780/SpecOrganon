"""Synthetic sensitivity checks; no fixture represents authentic site data."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from specorganon.field_power_sensitivity import (
    CLASSIFICATION,
    FieldPowerSensitivityError,
    analyze_field_power_sensitivity,
)


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "analyze_field_power_sensitivity.py"


def _case(*, outer_draws: int = 12, bootstrap_draws: int = 400) -> dict:
    profiles = []
    for stratum in ("A", "B"):
        for index in range(6):
            profiles.append({
                "group_id": f"{stratum}{index}", "stratum": stratum,
                "pre_v": 0.40 + index * 0.025,
                "post_v_no_treatment": 0.38 + index * 0.035 + (0.015 if stratum == "B" else 0),
                "baseline_input_volume": 90 + index * 15 + (10 if stratum == "B" else 0),
            })
    return {
        "schema": 1, "classification": CLASSIFICATION, "profiles": profiles,
        "planned_cells": [
            {"arm": arm, "stratum": stratum, "groups": 3}
            for stratum in ("A", "B") for arm in ("control", "intervention")
        ],
        "scenarios_true_g": [0, 0.10, 0.20],
        "simulation": {
            "outer_draws": outer_draws, "outer_seed": 719,
            "bootstrap_draws": bootstrap_draws, "bootstrap_seed": 3201,
        },
    }


def test_repeated_seed_is_exact_and_events_use_every_outer_replicate() -> None:
    value = _case()
    report = analyze_field_power_sensitivity(value)
    assert report == analyze_field_power_sensitivity(copy.deepcopy(value))
    assert report["assignment_ready"] is False
    assert report["source_authenticity"] is False
    assert report["site_power_validated"] is False
    assert report["criterion_3"]["status"] == "not_assessed"
    assert report["simulation"]["outer_seed"] == 719
    assert report["simulation"]["bootstrap_seed"] == 3201
    budget = report["simulation"]["work_budget"]
    assert budget["planned_groups"] == 12
    assert budget["design_columns"] == 4
    assert budget["estimated_units"] == 12 * 3 * 401 * (12 * 4 * 4 + 4**3)
    assert budget["estimated_units"] <= budget["maximum_estimated_units"]
    assert budget["heuristic_not_wall_time_guarantee"] is True
    assert report["input_byte_sha256"] is None
    for scenario in report["scenarios"]:
        assert scenario["defined_intervals"] + scenario["undefined_intervals"] == 12
        assert scenario["failed_replicates"] <= scenario["undefined_intervals"]
        for event in scenario["events"].values():
            assert event["denominator_all_outer_draws"] == 12
            assert float(event["probability"]) == event["count"] / 12
            assert 0 <= float(event["monte_carlo_wilson_95_bounds"][0]) <= 1
            assert 0 <= float(event["monte_carlo_wilson_95_bounds"][1]) <= 1

    reordered = copy.deepcopy(value)
    reordered["profiles"].reverse()
    reordered["planned_cells"].reverse()
    assert analyze_field_power_sensitivity(reordered) == report
    reordered["scenarios_true_g"].reverse()
    assert list(reversed(analyze_field_power_sensitivity(reordered)["scenarios"])) == report["scenarios"]


def test_detection_and_decision_events_diverge_under_same_estimator() -> None:
    report = analyze_field_power_sensitivity(_case(outer_draws=40))
    scenario = next(row for row in report["scenarios"] if row["true_g"] == "0.1")
    events = scenario["events"]
    assert events["ci_lower_gt_zero"]["count"] > events["ci_lower_ge_0_10"]["count"]
    assert events["ci_lower_ge_0_10"]["count"] <= scenario["defined_intervals"]
    assert events["ci_covers_true_g"]["count"] <= scenario["defined_intervals"]


def test_undefined_intervals_and_impossible_shift_stay_in_denominator() -> None:
    value = _case(outer_draws=7, bootstrap_draws=1)
    value["scenarios_true_g"] = [0, 2]
    report = analyze_field_power_sensitivity(value)
    for scenario in report["scenarios"]:
        assert scenario["undefined_intervals"] == 7
        assert scenario["defined_intervals"] == 0
        for event in scenario["events"].values():
            assert event["count"] == 0
            assert event["denominator_all_outer_draws"] == 7
            assert event["probability"] == "0"
    assert report["scenarios"][1]["failed_replicates"] == 7
    assert report["scenarios"][1]["failure_counts"]["post_v_out_of_bounds"] == 7
    assert report["scenarios"][0]["failed_replicates"] == 0


def test_singular_original_fit_is_counted_in_every_outer_denominator() -> None:
    value = _case(outer_draws=5, bootstrap_draws=400)
    value["scenarios_true_g"] = [0]
    for profile in value["profiles"]:
        profile["baseline_input_volume"] = 100
    scenario = analyze_field_power_sensitivity(value)["scenarios"][0]
    assert scenario["failed_replicates"] == 5
    assert scenario["failure_counts"]["estimator_failure"] == 5
    assert scenario["undefined_intervals"] == 5
    assert scenario["events"]["ci_covers_true_g"]["denominator_all_outer_draws"] == 5


def test_many_group_strata_configuration_fails_weighted_budget_before_execution() -> None:
    value = _case()
    value["profiles"] = [
        {
            "group_id": f"g{stratum}-{index}", "stratum": f"s{stratum}",
            "pre_v": 0.4, "post_v_no_treatment": 0.5,
            "baseline_input_volume": 100 + index,
        }
        for stratum in range(50) for index in range(2)
    ]
    value["planned_cells"] = [
        {"arm": arm, "stratum": f"s{stratum}", "groups": 2}
        for stratum in range(50) for arm in ("control", "intervention")
    ]
    value["scenarios_true_g"] = [0]
    value["simulation"].update(outer_draws=5_000, bootstrap_draws=200)
    assert 5_000 * 200 == 1_000_000  # Previous absolute bootstrap-fit cap allowed this.
    with pytest.raises(FieldPowerSensitivityError, match="dimension-weighted work estimate"):
        analyze_field_power_sensitivity(value)


@pytest.mark.parametrize("mutation,pattern", [
    ("duplicate_profile", "duplicated"),
    ("missing_profile", "at least two independent groups"),
    ("pre_out_of_bounds", r"within \[0,1\]"),
    ("post_out_of_bounds", r"within \[0,1\]"),
    ("zero_volume", "positive"),
    ("missing_cell", "both arms"),
    ("singleton_cell", "at least 2"),
    ("negative_draws", "between 1"),
    ("boolean_seed", "unsigned 64-bit"),
    ("duplicate_scenario", "unique values"),
    ("huge_budget", "exceeds"),
    ("extra_key", "unexpected keys"),
])
def test_bad_inputs_fail_closed(mutation: str, pattern: str) -> None:
    value = _case(outer_draws=1, bootstrap_draws=1)
    if mutation == "duplicate_profile":
        value["profiles"].append(copy.deepcopy(value["profiles"][0]))
    elif mutation == "missing_profile":
        value["profiles"] = value["profiles"][:1]
        value["planned_cells"] = value["planned_cells"][:2]
    elif mutation == "pre_out_of_bounds":
        value["profiles"][0]["pre_v"] = 1.01
    elif mutation == "post_out_of_bounds":
        value["profiles"][0]["post_v_no_treatment"] = -0.01
    elif mutation == "zero_volume":
        value["profiles"][0]["baseline_input_volume"] = 0
    elif mutation == "missing_cell":
        value["planned_cells"].pop()
    elif mutation == "singleton_cell":
        value["planned_cells"][0]["groups"] = 1
    elif mutation == "negative_draws":
        value["simulation"]["outer_draws"] = -1
    elif mutation == "boolean_seed":
        value["simulation"]["outer_seed"] = True
    elif mutation == "duplicate_scenario":
        value["scenarios_true_g"] = [0, 0.0]
    elif mutation == "huge_budget":
        value["simulation"]["outer_draws"] = 10_000
        value["simulation"]["bootstrap_draws"] = 100_000
    else:
        value["unknown"] = True
    with pytest.raises(FieldPowerSensitivityError, match=pattern):
        analyze_field_power_sensitivity(value)


def test_cli_hashes_exact_input_bytes_and_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "sensitivity.json"
    raw = json.dumps(_case(outer_draws=2, bootstrap_draws=1), indent=2).encode("utf-8")
    path.write_bytes(raw)
    completed = subprocess.run([sys.executable, str(SCRIPT), str(path)],
                               text=True, capture_output=True, check=True)
    report = json.loads(completed.stdout)
    assert report["input_byte_sha256"] == hashlib.sha256(raw).hexdigest()
    assert completed.stderr == ""
    path.write_text('{"schema":1,"schema":1}', encoding="utf-8")
    completed = subprocess.run([sys.executable, str(SCRIPT), str(path)],
                               text=True, capture_output=True)
    assert completed.returncode == 2
    assert "duplicate" in completed.stderr.lower()
    path.write_text('{"schema":NaN}', encoding="utf-8")
    completed = subprocess.run([sys.executable, str(SCRIPT), str(path)],
                               text=True, capture_output=True)
    assert completed.returncode == 2
    assert "non-finite" in completed.stderr.lower()
