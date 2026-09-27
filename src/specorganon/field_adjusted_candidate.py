"""Reproduce a DEVELOPMENT candidate for the adjusted, group-level ITT G.

This read-only calculator accepts four JSON objects. The exact version-1
candidate specification is::

    {"schema": 1,
     "classification": "field_adjusted_itt_g_candidate_spec_development",
     "study_id": "...", "plan_sha256": "canonical SHA-256 of plan",
     "registered_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
     "service": {"unit": "...", "equivalence_record_sha256": "..."},
     "baseline_input_volume": {
         "unit": "...", "definition": "prospective positive input-volume definition",
         "definition_sha256": "canonical SHA-256 of {unit, definition}"},
     "estimator": {
         "outcome": "post_minus_pre_v", "model": "ols_assigned_arm_stratum_fe_centered_log_volume",
         "group_weight": "equal", "denominator": "one_minus_intervention_pre_mean_v"},
     "bootstrap": {
         "resampling": "whole_group_within_arm_stratum",
         "rng": "python_mt19937_random_floor", "seed": 0,
         "draws": 1000, "interval": "two_sided_percentile_type7",
         "confidence_level": 0.95}}

The matching exact version-1 volume manifest is::

    {"schema": 1,
     "classification": "field_baseline_input_volume_manifest_unsealed",
     "study_id": "...", "plan_sha256": "...",
     "candidate_spec_sha256": "canonical SHA-256 of candidate specification",
     "unit": "...", "definition_sha256": "...",
     "rows": [{"group_id": "...", "period": "pre", "value": 1,
               "unit": "...", "window_start_utc": "...",
               "window_end_utc": "...",
               "source": {"record_sha256": "...", "locator": "...",
                          "observed_at_utc": "...", "method": "..."}}]}

Each source time declares a completed pre-window aggregate before that group's
assignment. Digests, timestamps, measurement coverage, registration and source
truth are declarations, not authenticated evidence. The percentile interval is
descriptive and uncalibrated for 12 clusters. No result can approve a site,
establish a causal effect, or assess criterion 3.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

from .field_flows import FieldFlowError, _number, _object, _text, _utc
from .field_guardrails import FieldGuardrailError, _digest, _read_json, canonical_sha256
from .field_trial_design import FieldTrialDesignError, audit_field_trial_design


SPEC_CLASSIFICATION = "field_adjusted_itt_g_candidate_spec_development"
MANIFEST_CLASSIFICATION = "field_baseline_input_volume_manifest_unsealed"
REPORT_CLASSIFICATION = "field_adjusted_itt_g_candidate_development_only"
OUTCOME = "post_minus_pre_v"
MODEL = "ols_assigned_arm_stratum_fe_centered_log_volume"
RESAMPLING = "whole_group_within_arm_stratum"
RNG = "python_mt19937_random_floor"
INTERVAL = "two_sided_percentile_type7"
MIN_VALID_BOOTSTRAP_DRAWS = 200
NOTICE = (
    "Development-only adjusted ITT G candidate from declared inputs. The nominal "
    "95% percentile interval is uncalibrated, especially with few groups; invalid "
    "draws are reported and its bounds use only valid draws. Registration, "
    "randomization, source custody, coverage, service calibration, power, safety "
    "and field impact are not authenticated or assessed."
)


class FieldAdjustedCandidateError(ValueError):
    """The declared candidate inputs cannot identify the requested calculation."""


class _SingularFit(Exception):
    """The specified regression has less than full numerical column rank."""


@dataclass(frozen=True)
class _Group:
    group_id: str
    arm: str
    stratum: str
    pre_v: Fraction
    post_v: Fraction
    volume: Decimal


def _decimal_text(value: float) -> str:
    if not math.isfinite(value):
        raise FieldAdjustedCandidateError("computed value is not finite")
    rendered = format(Decimal(repr(value)), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _fraction_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def _spec(value: Any, plan: dict[str, Any], field: dict[str, Any]) -> tuple[dict[str, Any], int, int]:
    item = _object(value, "candidate_spec", {
        "schema", "classification", "study_id", "plan_sha256", "registered_at_utc",
        "service", "baseline_input_volume", "estimator", "bootstrap",
    })
    if type(item["schema"]) is not int or item["schema"] != 1:
        raise FieldAdjustedCandidateError("candidate_spec.schema must be 1")
    if item["classification"] != SPEC_CLASSIFICATION:
        raise FieldAdjustedCandidateError("candidate_spec.classification is unsupported")
    if _text(item["study_id"], "candidate_spec.study_id") != plan["study_id"]:
        raise FieldAdjustedCandidateError("candidate_spec study_id differs from plan")
    if _digest(item["plan_sha256"], "candidate_spec.plan_sha256") != canonical_sha256(plan):
        raise FieldAdjustedCandidateError("candidate_spec plan_sha256 differs from canonical plan")
    registration = _utc(item["registered_at_utc"], "candidate_spec.registered_at_utc")
    plan_registration = _utc(plan["registered_at_utc"], "plan.registered_at_utc")
    pre = next(period for period in plan["periods"] if period["id"] == "pre")
    pre_start = _utc(pre["start_utc"], "plan.periods.pre.start_utc")
    if not plan_registration <= registration < pre_start:
        raise FieldAdjustedCandidateError(
            "candidate spec registration must follow plan registration and predate the pre window"
        )

    service = _object(item["service"], "candidate_spec.service",
                      {"unit", "equivalence_record_sha256"})
    if _text(service["unit"], "candidate_spec.service.unit") != field["service"]["equivalence"]["service_unit"]:
        raise FieldAdjustedCandidateError("candidate_spec service unit differs from field equivalence")
    if _digest(service["equivalence_record_sha256"], "candidate_spec.service.equivalence_record_sha256") != field["service"]["equivalence"]["record_sha256"]:
        raise FieldAdjustedCandidateError("candidate_spec service equivalence digest differs from field")

    volume = _object(item["baseline_input_volume"], "candidate_spec.baseline_input_volume",
                     {"unit", "definition", "definition_sha256"})
    unit = _text(volume["unit"], "candidate_spec.baseline_input_volume.unit")
    definition = _text(volume["definition"], "candidate_spec.baseline_input_volume.definition")
    expected = canonical_sha256({"unit": unit, "definition": definition})
    if _digest(volume["definition_sha256"], "candidate_spec.baseline_input_volume.definition_sha256") != expected:
        raise FieldAdjustedCandidateError("baseline input-volume definition digest differs from unit and definition")

    estimator = _object(item["estimator"], "candidate_spec.estimator",
                        {"outcome", "model", "group_weight", "denominator"})
    if estimator != {
        "outcome": OUTCOME, "model": MODEL, "group_weight": "equal",
        "denominator": "one_minus_intervention_pre_mean_v",
    }:
        raise FieldAdjustedCandidateError("candidate_spec.estimator is unsupported")
    bootstrap = _object(item["bootstrap"], "candidate_spec.bootstrap",
                        {"resampling", "rng", "seed", "draws", "interval", "confidence_level"})
    if (bootstrap["resampling"] != RESAMPLING or bootstrap["rng"] != RNG
            or bootstrap["interval"] != INTERVAL
            or type(bootstrap["confidence_level"]) not in (int, float, Decimal)
            or Decimal(str(bootstrap["confidence_level"])) != Decimal("0.95")):
        raise FieldAdjustedCandidateError("candidate_spec.bootstrap method or confidence level is unsupported")
    seed, draws = bootstrap["seed"], bootstrap["draws"]
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise FieldAdjustedCandidateError("candidate_spec.bootstrap.seed must be an unsigned 64-bit integer")
    if type(draws) is not int or not 1 <= draws <= 100_000:
        raise FieldAdjustedCandidateError("candidate_spec.bootstrap.draws must be between 1 and 100000")
    return item, seed, draws


def _volume_rows(manifest: Any, plan: dict[str, Any], field: dict[str, Any],
                 spec: dict[str, Any]) -> dict[str, Decimal]:
    item = _object(manifest, "baseline_input_volume_manifest", {
        "schema", "classification", "study_id", "plan_sha256", "candidate_spec_sha256",
        "unit", "definition_sha256", "rows",
    })
    if type(item["schema"]) is not int or item["schema"] != 1:
        raise FieldAdjustedCandidateError("baseline_input_volume_manifest.schema must be 1")
    if item["classification"] != MANIFEST_CLASSIFICATION:
        raise FieldAdjustedCandidateError("baseline_input_volume_manifest.classification is unsupported")
    if _text(item["study_id"], "baseline_input_volume_manifest.study_id") != plan["study_id"]:
        raise FieldAdjustedCandidateError("volume manifest study_id differs from plan")
    if _digest(item["plan_sha256"], "baseline_input_volume_manifest.plan_sha256") != canonical_sha256(plan):
        raise FieldAdjustedCandidateError("volume manifest plan_sha256 differs from canonical plan")
    if _digest(item["candidate_spec_sha256"], "baseline_input_volume_manifest.candidate_spec_sha256") != canonical_sha256(spec):
        raise FieldAdjustedCandidateError("volume manifest candidate_spec_sha256 differs from canonical spec")
    declared_volume = spec["baseline_input_volume"]
    if _text(item["unit"], "baseline_input_volume_manifest.unit") != declared_volume["unit"]:
        raise FieldAdjustedCandidateError("volume manifest unit differs from candidate spec")
    if _digest(item["definition_sha256"], "baseline_input_volume_manifest.definition_sha256") != declared_volume["definition_sha256"]:
        raise FieldAdjustedCandidateError("volume manifest definition digest differs from candidate spec")
    if type(item["rows"]) is not list:
        raise FieldAdjustedCandidateError("baseline_input_volume_manifest.rows must be an array")

    pre = next(period for period in plan["periods"] if period["id"] == "pre")
    pre_end = _utc(pre["end_utc"], "plan.periods.pre.end_utc")
    assignments = {g["id"]: _utc(g["assigned_at_utc"], "field.groups.assigned_at_utc")
                   for g in field["groups"]}
    registration = _utc(spec["registered_at_utc"], "candidate_spec.registered_at_utc")
    seen_sources: set[tuple[str, str]] = set()
    result: dict[str, Decimal] = {}
    for index, raw in enumerate(item["rows"]):
        label = f"baseline_input_volume_manifest.rows[{index}]"
        row = _object(raw, label, {
            "group_id", "period", "value", "unit", "window_start_utc", "window_end_utc", "source",
        })
        group_id = _text(row["group_id"], f"{label}.group_id")
        if group_id not in assignments or group_id in result:
            raise FieldAdjustedCandidateError(f"{label} has unknown or duplicated group_id")
        if row["period"] != "pre" or row["window_start_utc"] != pre["start_utc"] or row["window_end_utc"] != pre["end_utc"]:
            raise FieldAdjustedCandidateError(f"{label} must aggregate exactly the declared pre window")
        if _text(row["unit"], f"{label}.unit") != declared_volume["unit"]:
            raise FieldAdjustedCandidateError(f"{label}.unit differs from candidate spec")
        amount = _number(row["value"], f"{label}.value", positive=True)
        source = _object(row["source"], f"{label}.source",
                         {"record_sha256", "locator", "observed_at_utc", "method"})
        digest = _digest(source["record_sha256"], f"{label}.source.record_sha256")
        locator = _text(source["locator"], f"{label}.source.locator")
        _text(source["method"], f"{label}.source.method")
        timestamp = _utc(source["observed_at_utc"], f"{label}.source.observed_at_utc")
        if not max(pre_end, registration) <= timestamp < assignments[group_id]:
            raise FieldAdjustedCandidateError(f"{label}.source must be pre-window-complete and preassignment")
        source_key = digest, locator
        if source_key in seen_sources:
            raise FieldAdjustedCandidateError("volume manifest reuses the same source digest and locator")
        seen_sources.add(source_key)
        result[group_id] = amount
    if result.keys() != assignments.keys():
        raise FieldAdjustedCandidateError("volume manifest must have exactly one preassignment aggregate per group")
    return result


def _fit(groups: list[_Group], strata: list[str]) -> tuple[float, float, float, float]:
    """Equal-group OLS; return arm coefficient, log center, RSS and min pivot."""
    n = len(groups)
    log_volume = [math.log(float(g.volume)) for g in groups]
    if not all(math.isfinite(v) for v in log_volume):
        raise FieldAdjustedCandidateError("baseline input volume log is not finite")
    center = math.fsum(log_volume) / n
    x = [[1.0, float(g.arm == "intervention"),
          *(float(g.stratum == stratum) for stratum in strata[1:]),
          log_volume[i] - center] for i, g in enumerate(groups)]
    y = [float(g.post_v - g.pre_v) for g in groups]
    p = len(x[0])
    norms = [math.sqrt(math.fsum(row[j] * row[j] for row in x)) for j in range(p)]
    if any(norm <= 1e-13 for norm in norms):
        raise _SingularFit
    a = [[math.fsum(row[i] * row[j] for row in x) / (norms[i] * norms[j])
          for j in range(p)] for i in range(p)]
    b = [math.fsum(row[i] * outcome for row, outcome in zip(x, y, strict=True)) / norms[i]
         for i in range(p)]
    min_pivot = 1.0
    for col in range(p):
        pivot_row = max(range(col, p), key=lambda r: abs(a[r][col]))
        pivot = abs(a[pivot_row][col])
        if not math.isfinite(pivot) or pivot <= 1e-10:
            raise _SingularFit
        min_pivot = min(min_pivot, pivot)
        a[col], a[pivot_row] = a[pivot_row], a[col]
        b[col], b[pivot_row] = b[pivot_row], b[col]
        for row in range(col + 1, p):
            factor = a[row][col] / a[col][col]
            for j in range(col, p):
                a[row][j] -= factor * a[col][j]
            b[row] -= factor * b[col]
    scaled = [0.0] * p
    for i in reversed(range(p)):
        scaled[i] = (b[i] - math.fsum(a[i][j] * scaled[j] for j in range(i + 1, p))) / a[i][i]
    coefficients = [scaled[i] / norms[i] for i in range(p)]
    residual_sum_squares = math.fsum(
        (outcome - math.fsum(v * beta for v, beta in zip(row, coefficients, strict=True))) ** 2
        for row, outcome in zip(x, y, strict=True)
    )
    if not all(math.isfinite(v) for v in (coefficients[1], residual_sum_squares)):
        raise _SingularFit
    return coefficients[1], center, residual_sum_squares, min_pivot


def _denominator(groups: list[_Group]) -> Fraction:
    intervention = [g.pre_v for g in groups if g.arm == "intervention"]
    return 1 - sum(intervention, Fraction()) / len(intervention)


def _percentile(values: list[float], proportion: float) -> float:
    ordered = sorted(values)
    location = (len(ordered) - 1) * proportion
    lower = math.floor(location)
    upper = math.ceil(location)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (location - lower)


def analyze_field_adjusted_candidate(
    plan: Any, field: Any, candidate_spec: Any, baseline_input_volume_manifest: Any,
) -> dict[str, Any]:
    """Calculate a declared candidate; the report is never decision-ready."""
    try:
        design = audit_field_trial_design(plan, field)
        spec, seed, draws = _spec(candidate_spec, plan, field)
        volumes = _volume_rows(baseline_input_volume_manifest, plan, field, spec)
        service: dict[tuple[str, str], Fraction] = {}
        for row in field["service"]["rows"]:
            consumed = _number(row["consumed_service"]["value"], "service.consumed_service.value")
            feasible = _number(row["feasible_max_service"]["value"],
                               "service.feasible_max_service.value", positive=True)
            service[(row["group_id"], row["period"])] = Fraction(consumed) / Fraction(feasible)
        members = sorted(field["groups"], key=lambda group: group["id"])
        groups = [_Group(g["id"], g["arm"], g["stratum"],
                         service[(g["id"], "pre")], service[(g["id"], "post")], volumes[g["id"]])
                  for g in members]
        strata = sorted({g.stratum for g in groups})
        cells: dict[tuple[str, str], list[_Group]] = {}
        for group in groups:
            cells.setdefault((group.arm, group.stratum), []).append(group)
        for (arm, stratum), cell in sorted(cells.items()):
            if len(cell) < 2:
                raise FieldAdjustedCandidateError(
                    f"cannot bootstrap singleton arm-stratum cell: {arm}/{stratum}"
                )
        try:
            tau, log_center, rss, min_pivot = _fit(groups, strata)
        except _SingularFit as exc:
            raise FieldAdjustedCandidateError("original adjusted group-level OLS fit is nonidentifiable or numerically singular") from exc
        denominator = _denominator(groups)
        if denominator <= 0:
            raise FieldAdjustedCandidateError("original G denominator is zero; intervention pre V has no initial loss")
        g_value = tau / float(denominator)
        if not math.isfinite(g_value):
            raise FieldAdjustedCandidateError("original adjusted G is not finite")

        rng = random.Random(seed)
        valid: list[float] = []
        singular_draws: list[int] = []
        zero_denominator_draws: list[int] = []
        nonfinite_draws: list[int] = []
        for draw in range(draws):
            sample: list[_Group] = []
            for cell in sorted(cells):
                members_in_cell = cells[cell]
                count = len(members_in_cell)
                sample.extend(members_in_cell[math.floor(rng.random() * count)]
                              for _ in range(count))
            sampled_denominator = _denominator(sample)
            if sampled_denominator <= 0:
                zero_denominator_draws.append(draw)
            try:
                sampled_tau, _center, _rss, _pivot = _fit(sample, strata)
            except _SingularFit:
                singular_draws.append(draw)
                continue
            if sampled_denominator <= 0:
                continue
            sampled_g = sampled_tau / float(sampled_denominator)
            if not math.isfinite(sampled_g):
                nonfinite_draws.append(draw)
                continue
            valid.append(sampled_g)
        invalid = sorted(set(singular_draws) | set(zero_denominator_draws) | set(nonfinite_draws))
        enough_draws = len(valid) >= MIN_VALID_BOOTSTRAP_DRAWS
        bounds = ([_decimal_text(_percentile(valid, 0.025)),
                   _decimal_text(_percentile(valid, 0.975))] if enough_draws else None)
    except (FieldFlowError, FieldTrialDesignError, FieldGuardrailError) as exc:
        raise FieldAdjustedCandidateError(f"field adjusted candidate preflight failed: {exc}") from exc

    return {
        "schema": 1,
        "classification": REPORT_CLASSIFICATION,
        "study_id": design["study_id"],
        "input_canonical_sha256": {
            "plan": canonical_sha256(plan), "field": canonical_sha256(field),
            "candidate_spec": canonical_sha256(spec),
            "baseline_input_volume_manifest": canonical_sha256(baseline_input_volume_manifest),
        },
        "candidate_point": {
            "tau_adjusted_change": _decimal_text(tau),
            "intervention_pre_mean_v": _decimal_text(float(1 - denominator)),
            "one_minus_intervention_pre_mean_v": _decimal_text(float(denominator)),
            "one_minus_intervention_pre_mean_v_fraction": _fraction_text(denominator),
            "g_adjusted": _decimal_text(g_value),
        },
        "candidate_interval": {
            "method": INTERVAL, "level": "0.95", "bounds": bounds,
            "defined": bounds is not None, "nominal_only": True,
            "calibrated_for_design": False, "valid_draws_only": True,
            "minimum_valid_draws": MIN_VALID_BOOTSTRAP_DRAWS,
            "undefined_reason": (None if bounds is not None else
                                 "fewer than 200 valid whole-group bootstrap draws"),
        },
        "diagnostics": {
            "groups": len(groups), "service_group_period_ratios": len(service),
            "positive_preassignment_input_volume_rows": len(volumes),
            "strata": strata,
            "arm_stratum_cell_counts": [
                {"arm": arm, "stratum": stratum, "groups": len(cells[(arm, stratum)])}
                for arm, stratum in sorted(cells)
            ],
            "model": MODEL, "group_weight": "equal", "assigned_arm_used": True,
            "reference_stratum": strata[0],
            "design_columns": 3 + len(strata) - 1,
            "residual_degrees_of_freedom": len(groups) - (3 + len(strata) - 1),
            "log_volume_center": _decimal_text(log_center),
            "residual_sum_squares": _decimal_text(rss),
            "minimum_scaled_elimination_pivot": _decimal_text(min_pivot),
            "bootstrap": {
                "resampling": RESAMPLING, "rng": RNG, "seed": seed,
                "draws_requested": draws, "valid_draws": len(valid),
                "invalid_draws": len(invalid), "invalid_draw_indices_zero_based": invalid,
                "singular_fit_draws": len(singular_draws),
                "singular_fit_draw_indices_zero_based": singular_draws,
                "zero_denominator_draws": len(zero_denominator_draws),
                "zero_denominator_draw_indices_zero_based": zero_denominator_draws,
                "nonfinite_g_draws": len(nonfinite_draws),
                "nonfinite_g_draw_indices_zero_based": nonfinite_draws,
                "percentile_definition": "type7_linear_at_p_times_n_minus_1",
            },
        },
        "decision_ready": False,
        "criterion_3": {"status": "not_assessed", "reason": NOTICE},
        "registration_authenticated": False,
        "randomization_verified": False,
        "source_records_authenticated": False,
        "input_volume_source_authenticated": False,
        "complete_measurement_coverage_verified": False,
        "service_calibration_verified": False,
        "confidence_interval_calibrated": False,
        "notice": NOTICE,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("plan", "field", "candidate_spec", "baseline_input_volume_manifest"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args(argv)
    try:
        values = [_read_json(getattr(args, name))
                  for name in ("plan", "field", "candidate_spec", "baseline_input_volume_manifest")]
        report = analyze_field_adjusted_candidate(*values)
    except (OSError, FieldAdjustedCandidateError, FieldGuardrailError) as exc:
        print(f"Field adjusted candidate failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
