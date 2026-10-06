"""Offline DEVELOPMENT sensitivity simulation for the adjusted field G candidate.

The input is an unverified empirical distribution of independent historical
groups. Reusing their paired no-treatment outcomes is an explicit modeling
assumption. No result authenticates a site, calibrates a confidence interval,
approves an allocation, or assesses actual field impact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

from .field_adjusted_candidate import (
    INTERVAL,
    MIN_VALID_BOOTSTRAP_DRAWS,
    MODEL,
    RESAMPLING,
    RNG,
    FieldAdjustedCandidateError,
    _calculate_groups,
    _decimal_text,
    _denominator,
    _Group,
)
from .field_flows import FieldFlowError, _array, _number, _object, _text
from .field_guardrails import _invalid_json_constant, _unique_json_pairs


CLASSIFICATION = "field_power_sensitivity_inputs_development"
REPORT_CLASSIFICATION = "field_power_sensitivity_development_only"
SUCCESS_THRESHOLD = Decimal("0.10")
MAX_GROUPS = 200
MAX_TOTAL_FITS = 1_000_000
MAX_ESTIMATED_WORK_UNITS = 1_000_000_000


class FieldPowerSensitivityError(ValueError):
    """Invalid declared sensitivity inputs or impossible simulation budget."""


@dataclass(frozen=True)
class _Profile:
    group_id: str
    stratum: str
    pre_v: Fraction
    post_v_no_treatment: Fraction
    volume: Decimal


def _seed(value: Any, label: str) -> int:
    if type(value) is not int or not 0 <= value < 2**64:
        raise FieldPowerSensitivityError(f"{label} must be an unsigned 64-bit integer")
    return value


def _count(value: Any, label: str, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise FieldPowerSensitivityError(f"{label} must be an integer between 1 and {maximum}")
    return value


def _v(value: Any, label: str) -> Fraction:
    number = _number(value, label, nonnegative=False)
    if not 0 <= number <= 1:
        raise FieldPowerSensitivityError(f"{label} must be within [0,1]")
    return Fraction(number)


def _inputs(value: Any) -> tuple[
    dict[str, list[_Profile]], dict[str, dict[str, int]], list[Decimal],
    int, int, int, int,
]:
    try:
        item = _object(value, "input", {
            "schema", "classification", "profiles", "planned_cells", "scenarios_true_g", "simulation",
        })
        if type(item["schema"]) is not int or item["schema"] != 1:
            raise FieldPowerSensitivityError("input.schema must be 1")
        if item["classification"] != CLASSIFICATION:
            raise FieldPowerSensitivityError("input.classification is unsupported")

        profiles: dict[str, list[_Profile]] = {}
        seen_ids: set[str] = set()
        raw_profiles = _array(item["profiles"], "input.profiles")
        if len(raw_profiles) > 10_000:
            raise FieldPowerSensitivityError("input.profiles exceeds 10000 groups")
        for index, raw in enumerate(raw_profiles):
            label = f"input.profiles[{index}]"
            row = _object(raw, label, {
                "group_id", "stratum", "pre_v", "post_v_no_treatment", "baseline_input_volume",
            })
            group_id = _text(row["group_id"], f"{label}.group_id")
            if group_id in seen_ids:
                raise FieldPowerSensitivityError(f"{label}.group_id is duplicated")
            seen_ids.add(group_id)
            stratum = _text(row["stratum"], f"{label}.stratum")
            profile = _Profile(
                group_id, stratum, _v(row["pre_v"], f"{label}.pre_v"),
                _v(row["post_v_no_treatment"], f"{label}.post_v_no_treatment"),
                _number(row["baseline_input_volume"], f"{label}.baseline_input_volume",
                        positive=True),
            )
            profiles.setdefault(stratum, []).append(profile)
        for stratum, members in profiles.items():
            if len(members) < 2:
                raise FieldPowerSensitivityError(
                    f"input.profiles needs at least two independent groups in stratum {stratum}"
                )
            members.sort(key=lambda profile: profile.group_id)

        planned: dict[str, dict[str, int]] = {}
        seen_cells: set[tuple[str, str]] = set()
        for index, raw in enumerate(_array(item["planned_cells"], "input.planned_cells")):
            label = f"input.planned_cells[{index}]"
            cell = _object(raw, label, {"arm", "stratum", "groups"})
            arm = _text(cell["arm"], f"{label}.arm")
            if arm not in {"control", "intervention"}:
                raise FieldPowerSensitivityError(f"{label}.arm is unsupported")
            stratum = _text(cell["stratum"], f"{label}.stratum")
            if (arm, stratum) in seen_cells:
                raise FieldPowerSensitivityError(f"{label} duplicates an arm-stratum cell")
            seen_cells.add((arm, stratum))
            count = _count(cell["groups"], f"{label}.groups", MAX_GROUPS)
            if count < 2:
                raise FieldPowerSensitivityError(f"{label}.groups must be at least 2")
            planned.setdefault(stratum, {})[arm] = count
        if planned.keys() != profiles.keys() or any(
            set(arms) != {"control", "intervention"} for arms in planned.values()
        ):
            raise FieldPowerSensitivityError(
                "planned_cells must contain both arms for exactly the profile strata"
            )
        if sum(sum(arms.values()) for arms in planned.values()) > MAX_GROUPS:
            raise FieldPowerSensitivityError(f"planned_cells exceeds {MAX_GROUPS} total groups")

        scenarios = [_number(raw, f"input.scenarios_true_g[{index}]", nonnegative=False)
                     for index, raw in enumerate(_array(item["scenarios_true_g"],
                                                        "input.scenarios_true_g"))]
        if len(scenarios) > 20 or len(set(scenarios)) != len(scenarios):
            raise FieldPowerSensitivityError("scenarios_true_g must have 1 to 20 unique values")

        simulation = _object(item["simulation"], "input.simulation", {
            "outer_draws", "outer_seed", "bootstrap_draws", "bootstrap_seed",
        })
        outer_draws = _count(simulation["outer_draws"], "simulation.outer_draws", 10_000)
        bootstrap_draws = _count(simulation["bootstrap_draws"],
                                 "simulation.bootstrap_draws", 100_000)
        outer_seed = _seed(simulation["outer_seed"], "simulation.outer_seed")
        bootstrap_seed = _seed(simulation["bootstrap_seed"], "simulation.bootstrap_seed")
        if outer_draws * bootstrap_draws * len(scenarios) > MAX_TOTAL_FITS:
            raise FieldPowerSensitivityError(
                f"outer_draws * bootstrap_draws * scenario count exceeds {MAX_TOTAL_FITS}"
            )
        return profiles, planned, scenarios, outer_draws, outer_seed, bootstrap_draws, bootstrap_seed
    except FieldFlowError as exc:
        raise FieldPowerSensitivityError(str(exc)) from exc


def _assigned_groups(profiles: dict[str, list[_Profile]], planned: dict[str, dict[str, int]],
                     rng: random.Random, outer_index: int) -> list[_Group]:
    groups: list[_Group] = []
    for stratum_index, stratum in enumerate(sorted(planned)):
        source = profiles[stratum]
        control = planned[stratum]["control"]
        total = control + planned[stratum]["intervention"]
        selected = [source[math.floor(rng.random() * len(source))] for _ in range(total)]
        rng.shuffle(selected)
        for slot, profile in enumerate(selected):
            groups.append(_Group(
                f"sim-{stratum_index}-{outer_index}-{slot}",
                "control" if slot < control else "intervention", stratum,
                profile.pre_v, profile.post_v_no_treatment, profile.volume,
            ))
    return sorted(groups, key=lambda group: group.group_id)


def _estimated_work(planned: dict[str, dict[str, int]], scenario_count: int,
                    outer_draws: int, bootstrap_draws: int) -> tuple[int, int, int]:
    """Conservative matrix-work proxy; it cannot predict elapsed wall time."""
    groups = sum(sum(arms.values()) for arms in planned.values())
    columns = 3 + len(planned) - 1  # Same intercept, arm, strata FE and volume as _fit.
    per_fit = groups * columns * columns + columns**3
    units = outer_draws * scenario_count * (bootstrap_draws + 1) * per_fit
    return groups, columns, units


def _event(count: int, draws: int) -> dict[str, Any]:
    """Wilson uncertainty covers finite Monte Carlo draws, not site uncertainty."""
    probability = count / draws
    standard_error = math.sqrt(probability * (1 - probability) / draws)
    z = 1.959963984540054
    divisor = 1 + z * z / draws
    center = (probability + z * z / (2 * draws)) / divisor
    half_width = z * math.sqrt(
        probability * (1 - probability) / draws + z * z / (4 * draws * draws)
    ) / divisor
    return {
        "count": count,
        "denominator_all_outer_draws": draws,
        "probability": _decimal_text(probability),
        "monte_carlo_standard_error": _decimal_text(standard_error),
        "monte_carlo_wilson_95_bounds": [
            _decimal_text(max(0.0, center - half_width)),
            _decimal_text(min(1.0, center + half_width)),
        ],
    }


def analyze_field_power_sensitivity(value: Any, *, input_byte_sha256: str | None = None) -> dict[str, Any]:
    """Estimate conditional simulation frequencies; leave assignment and impact NO-GO."""
    (profiles, planned, scenarios, outer_draws, outer_seed, bootstrap_draws,
     bootstrap_seed) = _inputs(value)
    planned_groups, design_columns, estimated_work_units = _estimated_work(
        planned, len(scenarios), outer_draws, bootstrap_draws
    )
    if estimated_work_units > MAX_ESTIMATED_WORK_UNITS:
        raise FieldPowerSensitivityError(
            "dimension-weighted work estimate "
            f"{estimated_work_units} exceeds {MAX_ESTIMATED_WORK_UNITS} units; "
            "reduce draws, groups, strata or scenarios"
        )
    accumulators = [{
        "detect_positive": 0,
        "meet_success_threshold": 0,
        "cover_true_g": 0,
        "defined_intervals": 0,
        "undefined_intervals": 0,
        "post_v_out_of_bounds": 0,
        "estimator_failure": 0,
        "bootstrap_invalid_draws_total": 0,
    } for _ in scenarios]
    outer_rng = random.Random(outer_seed)
    bootstrap_rng = random.Random(bootstrap_seed)
    for outer_index in range(outer_draws):
        assigned = _assigned_groups(profiles, planned, outer_rng, outer_index)
        denominator = _denominator(assigned)
        inner_seed = bootstrap_rng.getrandbits(64)
        for scenario_index, true_g in enumerate(scenarios):
            counts = accumulators[scenario_index]
            shift = Fraction(true_g) * denominator
            if any(not 0 <= group.post_v + shift <= 1
                   for group in assigned if group.arm == "intervention"):
                counts["post_v_out_of_bounds"] += 1
                counts["undefined_intervals"] += 1
                continue
            shifted = [
                _Group(group.group_id, group.arm, group.stratum, group.pre_v,
                       group.post_v + shift if group.arm == "intervention" else group.post_v,
                       group.volume)
                for group in assigned
            ]
            try:
                calculation = _calculate_groups(shifted, inner_seed, bootstrap_draws)
            except FieldAdjustedCandidateError:
                counts["estimator_failure"] += 1
                counts["undefined_intervals"] += 1
                continue
            counts["bootstrap_invalid_draws_total"] += len(calculation.invalid)
            if calculation.bounds is None:
                counts["undefined_intervals"] += 1
                continue
            counts["defined_intervals"] += 1
            lower, upper = (Decimal(bound) for bound in calculation.bounds)
            counts["detect_positive"] += lower > 0
            counts["meet_success_threshold"] += lower >= SUCCESS_THRESHOLD
            counts["cover_true_g"] += lower <= true_g <= upper

    results = []
    for true_g, counts in zip(scenarios, accumulators, strict=True):
        results.append({
            "true_g": format(true_g, "f"),
            "outer_draws": outer_draws,
            "defined_intervals": counts["defined_intervals"],
            "undefined_intervals": counts["undefined_intervals"],
            "failed_replicates": (counts["post_v_out_of_bounds"]
                                  + counts["estimator_failure"]),
            "failure_counts": {
                "post_v_out_of_bounds": counts["post_v_out_of_bounds"],
                "estimator_failure": counts["estimator_failure"],
            },
            "bootstrap_invalid_draws_total": counts["bootstrap_invalid_draws_total"],
            "events": {
                "ci_lower_gt_zero": _event(counts["detect_positive"], outer_draws),
                "ci_lower_ge_0_10": _event(counts["meet_success_threshold"], outer_draws),
                "ci_covers_true_g": _event(counts["cover_true_g"], outer_draws),
            },
        })

    return {
        "schema": 1,
        "classification": REPORT_CLASSIFICATION,
        "input_byte_sha256": input_byte_sha256,
        "declared_profile_groups": sum(map(len, profiles.values())),
        "planned_cells": [
            {"arm": arm, "stratum": stratum, "groups": planned[stratum][arm]}
            for stratum in sorted(planned) for arm in ("control", "intervention")
        ],
        "simulation": {
            "outer_draws": outer_draws, "outer_seed": outer_seed,
            "bootstrap_draws": bootstrap_draws, "bootstrap_seed": bootstrap_seed,
            "work_budget": {
                "planned_groups": planned_groups,
                "design_columns": design_columns,
                "estimated_units": estimated_work_units,
                "maximum_estimated_units": MAX_ESTIMATED_WORK_UNITS,
                "maximum_bootstrap_fits": MAX_TOTAL_FITS,
                "formula": "outer_draws*scenarios*(bootstrap_draws+1)*(n*p*p+p**3)",
                "heuristic_not_wall_time_guarantee": True,
            },
            "model": MODEL, "bootstrap_resampling": RESAMPLING,
            "bootstrap_rng": RNG, "interval": INTERVAL,
            "minimum_valid_bootstrap_draws": MIN_VALID_BOOTSTRAP_DRAWS,
        },
        "assumptions": {
            "profile_groups_independent": "declared_only_unverified",
            "profile_resampling": "whole_historical_group_with_replacement_within_stratum",
            "assignment": "random_shuffle_within_stratum_to_planned_arm_counts",
            "common_outer_samples_and_bootstrap_seeds_across_scenarios": True,
            "untreated_post_v": "paired_historical_no_treatment_outcome_stable_under_future_assignment",
            "treated_post_v_shift": "true_g_times_one_minus_intervention_pre_mean_v",
            "constant_treatment_effect": True,
            "attrition_contamination_and_measurement_error_modeled": False,
            "undefined_intervals_and_failures_count_as_no_event": True,
            "monte_carlo_uncertainty_excludes_profile_and_site_model_error": True,
            "success_threshold_event": "ci_lower_ge_0.10_from_current_protocol_not_power_event_approved",
        },
        "scenarios": results,
        "assignment_ready": False,
        "source_authenticity": False,
        "site_power_validated": False,
        "criterion_3": {"status": "not_assessed"},
        "notice": (
            "Development-only conditional sensitivity under declared, unverified historical "
            "profiles. Synthetic fixtures do not estimate a real site's power. Nominal "
            "percentile intervals remain uncalibrated; competent prospective review and "
            "authentic site data are required before any assignment."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path)
    args = parser.parse_args(argv)
    try:
        raw = args.input.read_bytes()
        value = json.loads(
            raw.decode("utf-8"), parse_float=Decimal,
            parse_constant=_invalid_json_constant, object_pairs_hook=_unique_json_pairs,
        )
        report = analyze_field_power_sensitivity(
            value, input_byte_sha256=hashlib.sha256(raw).hexdigest()
        )
    except (OSError, UnicodeError, ValueError, RecursionError, ArithmeticError) as exc:
        print(f"Field power sensitivity failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
