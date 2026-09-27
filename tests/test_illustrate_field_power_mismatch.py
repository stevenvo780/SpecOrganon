"""Normal-model counterexample is not an estimate of food-trial power."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "illustrate_field_power_mismatch.py"
sys.path.insert(0, str(SCRIPT.parent))
from illustrate_field_power_mismatch import illustrate  # noqa: E402


def _args(*, standard_error: str = "0.0357", true_g: str = "0.10") -> list[str]:
    return [
        "--standard-error", standard_error,
        "--true-g", true_g,
        "--success-threshold", "0.10",
        "--detect-null", "0",
        "--ci-level", "0.95",
        "--target-power", "0.80",
    ]


def test_same_true_effect_as_success_threshold_has_only_tail_probability() -> None:
    for standard_error in (0.01, 0.0357, 0.1):
        report = illustrate(
            standard_error=standard_error, true_g=0.10, success_threshold=0.10,
            detect_null=0.0, ci_level=0.95, target_power=0.80,
        )
        assert report["illustrative_probability_lower_ci_meets_success_threshold"] == pytest.approx(
            0.025, abs=1e-12
        )
        assert not report["same_numeric_threshold"]
        assert not report["decision_events_equivalent"]
        assert not report["field_power_assessed"]
        assert not report["assignment_ready"]
        assert report["criterion_3"] == "not_assessed"


def test_normal_detection_power_does_not_imply_success_rule_power() -> None:
    report = illustrate(
        standard_error=0.0357, true_g=0.10, success_threshold=0.10,
        detect_null=0.0, ci_level=0.95, target_power=0.80,
    )
    assert report["illustrative_probability_detect_difference_from_null"] == pytest.approx(
        0.80, abs=0.002
    )
    assert report["illustrative_probability_lower_ci_meets_success_threshold"] < 0.03
    assumed_effect_for_80_percent_success = report[
        "illustrative_true_g_for_target_success_probability"
    ]
    assert 0.19 < assumed_effect_for_80_percent_success < 0.21
    at_required_effect = illustrate(
        standard_error=0.0357, true_g=assumed_effect_for_80_percent_success,
        success_threshold=0.10, detect_null=0.0, ci_level=0.95, target_power=0.80,
    )
    assert at_required_effect["illustrative_probability_lower_ci_meets_success_threshold"] == (
        pytest.approx(0.80, abs=1e-12)
    )


def test_cli_reports_illustration_without_claiming_site_power() -> None:
    result = subprocess.run([sys.executable, str(SCRIPT), *_args()],
                            capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report["classification"] == "normal_fixed_se_power_illustration_not_field_power"
    assert report["assumptions"]["standard_error"] == 0.0357
    assert not report["site_prior_data_used"]
    assert not report["cluster_bootstrap_simulated"]
    assert not report["field_power_assessed"]
    assert not report["assignment_ready"]
    assert report["criterion_3"] == "not_assessed"


@pytest.mark.parametrize("value,field", [
    ("0", "standard-error"),
    ("-1", "standard-error"),
    ("NaN", "standard-error"),
    ("1e-9999", "standard-error"),
    ("1e9999", "standard-error"),
    ("not-a-number", "standard-error"),
    ("1", "ci-level"),
    ("0.9999999999999999", "ci-level"),
    ("0", "target-power"),
])
def test_cli_rejects_invalid_inputs_without_success_json(value: str, field: str) -> None:
    arguments = _args()
    index = arguments.index(f"--{field}") + 1
    arguments[index] = value
    result = subprocess.run([sys.executable, str(SCRIPT), *arguments],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert not result.stdout
    assert "Power illustration failed:" in result.stderr


def test_extreme_effect_over_standard_error_fails_cleanly() -> None:
    with pytest.raises(ValueError, match="effect divided by standard_error"):
        illustrate(
            standard_error=1e-308, true_g=1e308, success_threshold=0.1,
            detect_null=0.0, ci_level=0.95, target_power=0.8,
        )


def test_required_effect_that_rounds_to_threshold_fails_cleanly() -> None:
    arguments = _args(standard_error="1e-20")
    result = subprocess.run([sys.executable, str(SCRIPT), *arguments],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert not result.stdout
    assert "required illustrative effect is not representable" in result.stderr


def test_near_certain_target_checks_failure_tail_precision() -> None:
    arguments = _args(standard_error="1.74e-18")
    index = arguments.index("--target-power") + 1
    arguments[index] = "0.9999999999999999"
    result = subprocess.run([sys.executable, str(SCRIPT), *arguments],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert not result.stdout
    assert "required illustrative effect is not representable" in result.stderr


def test_numeric_outputs_are_finite() -> None:
    report = illustrate(
        standard_error=0.0357, true_g=0.10, success_threshold=0.10,
        detect_null=0.0, ci_level=0.95, target_power=0.80,
    )
    for key in (
        "illustrative_probability_detect_difference_from_null",
        "illustrative_probability_lower_ci_meets_success_threshold",
        "illustrative_true_g_for_target_success_probability",
    ):
        assert math.isfinite(report[key])
