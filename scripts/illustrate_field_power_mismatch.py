"""Illustrate two different power questions under a fixed-SE normal model.

This is not a field-trial power calculation. It neither estimates the standard
error from site data nor reproduces the planned cluster-bootstrap interval.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from decimal import Decimal, InvalidOperation
from statistics import NormalDist


class IllustrationError(ValueError):
    """An illustrative normal-model input cannot be evaluated safely."""


def _finite_float(raw: str, name: str) -> float:
    try:
        exact = Decimal(raw)
        result = float(exact)
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise IllustrationError(f"{name} must be a finite decimal") from exc
    if not exact.is_finite() or not math.isfinite(result) or (exact != 0 and result == 0):
        raise IllustrationError(f"{name} must be a representable finite decimal")
    return result


def illustrate(*, standard_error: float, true_g: float, success_threshold: float,
               detect_null: float, ci_level: float, target_power: float) -> dict[str, object]:
    if not all(math.isfinite(value) for value in (
        standard_error, true_g, success_threshold, detect_null, ci_level, target_power,
    )):
        raise IllustrationError("all inputs must be finite")
    if standard_error <= 0:
        raise IllustrationError("standard_error must be positive")
    if not 0 < ci_level < 1 or not 0 < target_power < 1:
        raise IllustrationError("ci_level and target_power must be strictly between 0 and 1")

    normal = NormalDist()
    ci_quantile = (1 + ci_level) / 2
    if ci_quantile >= 1:
        raise IllustrationError("ci_level is too close to 1 for the normal approximation")
    z = normal.inv_cdf(ci_quantile)
    delta_detect = (true_g - detect_null) / standard_error
    delta_success = (true_g - success_threshold) / standard_error
    if not math.isfinite(delta_detect) or not math.isfinite(delta_success):
        raise IllustrationError("effect divided by standard_error is outside supported range")
    def upper_tail(x: float) -> float:
        return 0.5 * math.erfc(x / math.sqrt(2))
    detect_probability = upper_tail(z - delta_detect) + upper_tail(z + delta_detect)
    success_probability = upper_tail(z - delta_success)
    required_true_g = success_threshold + standard_error * (
        z + normal.inv_cdf(target_power)
    )
    if not math.isfinite(required_true_g):
        raise IllustrationError("required illustrative effect is outside supported range")
    required_cutoff = z - (required_true_g - success_threshold) / standard_error
    achieved_success = upper_tail(required_cutoff)
    achieved_failure = upper_tail(-required_cutoff)
    if not (
        math.isclose(achieved_success, target_power, rel_tol=1e-9, abs_tol=0)
        and math.isclose(achieved_failure, 1 - target_power, rel_tol=1e-9, abs_tol=0)
    ):
        raise IllustrationError("required illustrative effect is not representable at float precision")

    return {
        "schema": 1,
        "classification": "normal_fixed_se_power_illustration_not_field_power",
        "assumptions": {
            "standard_error": standard_error,
            "assumed_true_g": true_g,
            "detect_null": detect_null,
            "success_threshold": success_threshold,
            "two_sided_ci_level": ci_level,
            "target_probability": target_power,
            "model": "normal estimator with known, fixed standard error and symmetric two-sided CI",
        },
        "illustrative_probability_detect_difference_from_null": detect_probability,
        "illustrative_probability_lower_ci_meets_success_threshold": success_probability,
        "illustrative_true_g_for_target_success_probability": required_true_g,
        "same_numeric_threshold": detect_null == success_threshold,
        "decision_events_equivalent": False,
        "site_prior_data_used": False,
        "cluster_bootstrap_simulated": False,
        "field_power_assessed": False,
        "assignment_ready": False,
        "criterion_3": "not_assessed",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--standard-error", required=True)
    parser.add_argument("--true-g", required=True)
    parser.add_argument("--success-threshold", required=True)
    parser.add_argument("--detect-null", required=True)
    parser.add_argument("--ci-level", required=True)
    parser.add_argument("--target-power", required=True)
    args = parser.parse_args(argv)
    try:
        values = {
            key: _finite_float(getattr(args, key), key)
            for key in (
                "standard_error", "true_g", "success_threshold", "detect_null",
                "ci_level", "target_power",
            )
        }
        report = illustrate(**values)
    except IllustrationError as exc:
        print(f"Power illustration failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
