"""Check declared field-effect arithmetic without certifying field impact.

``audit_field_effect_analysis`` accepts the four inputs of the field guardrail
preflight and one exact-schema analysis declaration. It recomputes every group
period service ratio V, the unadjusted difference-in-differences G in the food
protocol, and descriptive post-period harm differences from declared rows.
Rational values use canonical ``numerator/denominator`` strings so repeating
ratios are compared exactly, with no rounding tolerance.

The adjusted estimator and its bootstrap interval cannot be reconstructed
from these inputs: there is no authenticated input-volume series, sealed
assignment, resampling algorithm or primary-record custody. A structurally
valid declaration therefore always returns ``decision_ready: false`` and
``criterion_3.status: not_assessed``. In particular, a passing descriptive
margin comparison is not a safety or causal verdict.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

from .field_flows import FieldFlowError, _number, _text
from .field_guardrails import FieldGuardrailError, _read_json, audit_field_guardrails, canonical_sha256


CLASSIFICATION = "field_effect_analysis_declaration"
MARGIN_DIRECTION = "max_absolute_increase"
NOT_READY_REASONS = (
    "adjusted stratum/input-volume estimator and group-bootstrap interval are not reproducible",
    "primary source custody and prospective approvals are not authenticated",
    "declared margins and textual stop conditions are not independently approved or assessed",
)


class FieldEffectAnalysisError(ValueError):
    """A field analysis declaration contradicts its declared inputs or schema."""


def _object(value: Any, label: str, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise FieldEffectAnalysisError(f"{label} must have exactly {sorted(keys)}")
    return value


def _rows(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise FieldEffectAnalysisError(f"{label} must be an array")
    return value


def _fraction(value: Any, expected: Fraction, label: str) -> None:
    rendered = f"{expected.numerator}/{expected.denominator}"
    if type(value) is not str or value != rendered:
        raise FieldEffectAnalysisError(f"{label} differs from exact declared-input arithmetic")


def _numeric(value: Any, label: str, *, nonnegative: bool = False) -> Decimal:
    return _number(value, label, nonnegative=nonnegative)


def _declared_ci(value: Any) -> dict[str, Any]:
    effect = _object(value, "analysis.adjusted_effect", {
        "estimate", "ci95", "estimator", "resampling_unit", "input_volume_source_id",
    })
    if effect["estimator"] != "stratum_and_input_volume_adjusted":
        raise FieldEffectAnalysisError("adjusted estimator must identify stratum and input-volume adjustment")
    if effect["resampling_unit"] != "group":
        raise FieldEffectAnalysisError("adjusted interval must declare group resampling")
    _text(effect["input_volume_source_id"], "analysis.adjusted_effect.input_volume_source_id")
    ci = _object(effect["ci95"], "analysis.adjusted_effect.ci95", {
        "level", "sidedness", "lower", "upper",
    })
    if _numeric(ci["level"], "analysis.adjusted_effect.ci95.level") != Decimal("0.95"):
        raise FieldEffectAnalysisError("adjusted interval must declare 95% confidence")
    if ci["sidedness"] != "two_sided":
        raise FieldEffectAnalysisError("adjusted interval must be unambiguously two-sided")
    estimate = _numeric(effect["estimate"], "analysis.adjusted_effect.estimate")
    lower = _numeric(ci["lower"], "analysis.adjusted_effect.ci95.lower")
    upper = _numeric(ci["upper"], "analysis.adjusted_effect.ci95.upper")
    # A percentile bootstrap interval can exclude its point estimate.
    if lower >= upper:
        raise FieldEffectAnalysisError("adjusted interval is empty or inverted")
    return {"estimate": str(estimate), "ci95": [str(lower), str(upper)]}


def _service_ratios(field: dict[str, Any], analysis: dict[str, Any]) -> tuple[
    dict[tuple[str, str], Fraction], Fraction, dict[tuple[str, str], Fraction],
]:
    groups = {group["id"]: group["arm"] for group in field["groups"]}
    ratios: dict[tuple[str, str], Fraction] = {}
    for row in field["service"]["rows"]:
        key = (row["group_id"], row["period"])
        consumed = _numeric(row["consumed_service"]["value"], "service.consumed_service", nonnegative=True)
        feasible = _numeric(row["feasible_max_service"]["value"], "service.feasible_max_service",
                            nonnegative=True)
        # The field preflight already requires a strictly positive denominator.
        if feasible == 0:
            raise FieldEffectAnalysisError("service feasible maximum is zero")
        ratios[key] = Fraction(consumed) / Fraction(feasible)

    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(_rows(analysis["v_rows"], "analysis.v_rows")):
        label = f"analysis.v_rows[{index}]"
        row = _object(raw, label, {"group_id", "period", "v_fraction"})
        key = (_text(row["group_id"], f"{label}.group_id"),
               _text(row["period"], f"{label}.period"))
        if key not in ratios or key in seen:
            raise FieldEffectAnalysisError(f"{label} is unknown or duplicated")
        seen.add(key)
        _fraction(row["v_fraction"], ratios[key], f"{label}.v_fraction")
    if seen != ratios.keys():
        raise FieldEffectAnalysisError("analysis.v_rows does not cover every group-period service ratio")

    means: dict[tuple[str, str], Fraction] = {}
    for arm in ("control", "intervention"):
        for period in ("pre", "post"):
            values = [ratio for (group, observed_period), ratio in ratios.items()
                      if groups[group] == arm and observed_period == period]
            if not values:
                raise FieldEffectAnalysisError(f"no service ratios for {arm}/{period}")
            means[(arm, period)] = sum(values, Fraction()) / len(values)
    initial_loss = 1 - means[("intervention", "pre")]
    if initial_loss <= 0:
        raise FieldEffectAnalysisError("unadjusted G is not applicable when intervention pre V is 1")
    g = ((means[("intervention", "post")] - means[("intervention", "pre")])
         - (means[("control", "post")] - means[("control", "pre")])) / initial_loss
    _fraction(analysis["unadjusted_g_fraction"], g, "analysis.unadjusted_g_fraction")
    return ratios, g, means


def _harm_outcomes(field: dict[str, Any], registry: dict[str, Any],
                   measurements: dict[str, Any], analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups = {group["id"]: group["arm"] for group in field["groups"]}
    measured_cells = {cell["id"]: cell for cell in registry["cells"]
                      if cell["status"] == "measured"}
    post_values: dict[tuple[str, str], list[Fraction]] = defaultdict(list)
    for row in measurements["rows"]:
        if row["period"] == "post":
            post_values[(row["cell_id"], groups[row["group_id"]])].append(
                Fraction(_numeric(row["value"], "measurements.rows.value")))
    outcomes: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for index, raw in enumerate(_rows(analysis["harm_outcomes"], "analysis.harm_outcomes")):
        label = f"analysis.harm_outcomes[{index}]"
        if type(raw) is not dict:
            raise FieldEffectAnalysisError(f"{label} must be an object")
        cell_id = _text(raw.get("cell_id"), f"{label}.cell_id")
        if cell_id not in measured_cells or cell_id in seen:
            raise FieldEffectAnalysisError(f"{label} names an unknown or duplicated measured cell")
        seen.add(cell_id)
        cell = measured_cells[cell_id]
        intervention = post_values[(cell_id, "intervention")]
        control = post_values[(cell_id, "control")]
        if not intervention or not control:
            raise FieldEffectAnalysisError(f"{label} lacks both post arms")
        if "margin" in cell:
            row = _object(raw, label, {
                "cell_id", "kind", "post_arm_difference_fraction", "margin_direction",
                "margin_value", "descriptive_within_margin",
            })
            margin = cell["margin"]
            if row["kind"] != "margin" or margin["direction"] != MARGIN_DIRECTION:
                raise FieldEffectAnalysisError(f"{label} has an ambiguous or unsupported margin direction")
            if row["margin_direction"] != MARGIN_DIRECTION:
                raise FieldEffectAnalysisError(f"{label} direction differs from registry")
            allowed = _numeric(margin["value"], f"registry.cells[{cell_id}].margin.value",
                               nonnegative=True)
            claimed = _numeric(row["margin_value"], f"{label}.margin_value", nonnegative=True)
            if claimed != allowed:
                raise FieldEffectAnalysisError(f"{label} margin value differs from registry")
            difference = (sum(intervention, Fraction()) / len(intervention)
                          - sum(control, Fraction()) / len(control))
            _fraction(row["post_arm_difference_fraction"], difference,
                      f"{label}.post_arm_difference_fraction")
            within = difference <= Fraction(allowed)
            if type(row["descriptive_within_margin"]) is not bool or row["descriptive_within_margin"] != within:
                raise FieldEffectAnalysisError(f"{label} descriptive margin comparison is incorrect")
            outcomes[cell_id] = {"kind": "margin", "post_arm_difference_fraction":
                                 f"{difference.numerator}/{difference.denominator}",
                                 "descriptive_within_margin": within}
        else:
            row = _object(raw, label, {
                "cell_id", "kind", "post_intervention_total_fraction", "assessment",
            })
            if row["kind"] != "stop_condition" or row["assessment"] != "not_assessed":
                raise FieldEffectAnalysisError(f"{label} textual stop condition cannot be assessed here")
            if any(value < 0 for value in intervention):
                raise FieldEffectAnalysisError(f"{label} stop-condition measure is negative")
            total = sum(intervention, Fraction())
            _fraction(row["post_intervention_total_fraction"], total,
                      f"{label}.post_intervention_total_fraction")
            outcomes[cell_id] = {"kind": "stop_condition", "assessment": "not_assessed",
                                 "post_intervention_total_fraction":
                                 f"{total.numerator}/{total.denominator}"}
    if seen != measured_cells.keys():
        raise FieldEffectAnalysisError("analysis.harm_outcomes does not cover every measured registry cell")
    return outcomes


def audit_field_effect_analysis(
    plan: Any, field: Any, registry: Any, measurements: Any, analysis: Any,
) -> dict[str, Any]:
    """Validate declared arithmetic, and report explicitly unassessed field impact.

    This routine checks internal consistency only. Its output must never be
    treated as approval of criterion 3 or authorization to run a field trial.
    """
    try:
        preflight = audit_field_guardrails(
            plan, field, registry, measurements,
            plan_sha256=canonical_sha256(plan), registry_sha256=canonical_sha256(registry),
        )
        root = _object(analysis, "analysis", {
            "schema", "classification", "study_id", "v_rows", "unadjusted_g_fraction",
            "adjusted_effect", "harm_outcomes",
        })
        if type(root["schema"]) is not int or root["schema"] != 1:
            raise FieldEffectAnalysisError("analysis.schema must be 1")
        if root["classification"] != CLASSIFICATION:
            raise FieldEffectAnalysisError("analysis.classification is unsupported")
        if _text(root["study_id"], "analysis.study_id") != preflight["study_id"]:
            raise FieldEffectAnalysisError("analysis and preflight study_id differ")
        adjusted = _declared_ci(root["adjusted_effect"])
        ratios, g, means = _service_ratios(field, root)
        harms = _harm_outcomes(field, registry, measurements, root)
    except (FieldFlowError, FieldGuardrailError) as exc:
        raise FieldEffectAnalysisError(f"field analysis preflight or declaration failed: {exc}") from exc

    return {
        "schema": 1,
        "classification": "field_effect_arithmetic_declared_only",
        "study_id": preflight["study_id"],
        "service_ratios_recomputed": len(ratios),
        "unadjusted_g_fraction": f"{g.numerator}/{g.denominator}",
        "unadjusted_arm_means": {
            f"{arm}_{period}": f"{value.numerator}/{value.denominator}"
            for (arm, period), value in sorted(means.items())
        },
        "adjusted_effect_declared": adjusted,
        "measured_harm_cells_checked": len(harms),
        "descriptive_margin_cells_within": sum(
            outcome.get("descriptive_within_margin") is True for outcome in harms.values()),
        "textual_stop_cells_unassessed": sum(
            outcome["kind"] == "stop_condition" for outcome in harms.values()),
        "decision_ready": False,
        "not_ready_reasons": list(NOT_READY_REASONS),
        "criterion_3": {"status": "not_assessed", "reason": "; ".join(NOT_READY_REASONS)},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("plan", "field", "registry", "measurements", "analysis"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit_field_effect_analysis(*(
            _read_json(getattr(args, name))
            for name in ("plan", "field", "registry", "measurements", "analysis")
        ))
    except (FieldEffectAnalysisError, FieldGuardrailError) as exc:
        print(f"Field effect analysis preflight failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
