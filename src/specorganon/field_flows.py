"""Read-only preflight for declared food-chain field observations.

Usage: ``python scripts/audit_field_flows.py field.json`` (``-`` reads stdin).
The JSON object has ``schema: 1``, ``schema: 2`` or ``schema: 3``, ``study_id``, ``balance_tolerance_kg``,
``tolerance_source``, ``currency``, and arrays ``actors``, ``groups``,
``periods``, ``lots``, ``flows``, ``burdens``. ``service`` is optional.

An evidence object has ``source_id``, ``locator``, ``observed_at_utc`` and
``method``. A mass is ``{value, unit, uncertainty}``, where unit is kg, g or t
and uncertainty has the same unit. Every group has ``id``, ``arm`` (control or
intervention), ``stratum``, ``assigned_at_utc``, ``actor_ids`` and ``source``.
Periods are exactly pre and post, each with ``start_utc``, ``end_utc`` and
``source``; assignment falls strictly between the intervals. Actors have
``id`` and ``role``. Numeric inputs must be finite, have at most 80 stored
decimal digits, and be within 1e-18 to 1e18 in absolute magnitude when
nonzero; these are parser bounds, not scientific acceptance thresholds.

Each lot is one observed operation: ``id``, ``group_id``, ``period``, ``stage``,
``source``, ``input_flow_ids``, ``output_flow_ids``,
``observed_input_load_ids`` and ``observed_output_load_ids``. Schema 2 also
requires ``stage_role``: production, storage, transport, transformation or
other. For every declared human-consumption flow, it requires one continuous
path from an externally fed production lot that visits storage, transport and
at least two transformation lots. Their relative order is not fixed; the two
transformations occur in series along the same path, possibly with other
operations between them.
``scope_status`` distinguishes this schema-2/3 witness check from schema 1's
unchecked stage coverage; ``stage_witnesses`` lists one lot path per declared
terminal consumption flow for schema 2/3, or is empty for schema 1.
The witness is a path of linked operations: a lot with multiple inputs and
outputs does not identify which input material became a given output. These
declarations do not certify undeclared branches or households. Schema 1 remains
accepted without this stage coverage check. Schema 3 retains schema-2 stage
roles, terminal load-bound evidence and lot-path witnesses, and requires each
lot to declare nonempty ``allocations`` of ``{input_flow_id, output_flow_id,
mass, source}``. Allocation ``mass`` uses the same mass shape. Its ``source``
adds ``input_load_id`` and ``output_load_id`` to the standard evidence fields;
the IDs must match the linked physical loads, and the observation must occur
within the period at or after the output flow. Positive rows must cover each
incident flow, have unique input-output pairs, and sum to each input and
output's *nominal* mass exactly in rational kg. This strict, opt-in nominal
reconciliation avoids demanding impossible exact equality of uncertain
marginals. Schema 3 propagates conservative mass lower bounds for minimum
stage requirements through these allocations and requires a positive complete-stage
bound for every declared human-consumption flow. ``lineage_bounds`` reports
those declared lower bounds; they are not authenticated physical provenance.
Each flow has
``id``, globally unique physical ``load_id``, ``group_id``, ``period``,
``from_lot_id`` and ``to_lot_id`` (one may be null), ``kind``, ``mass``,
``source``, ``destination`` and ``outcome``. External inputs use kind feed,
ingredient or water_addition. Outputs use product, coproduct, residue or
moisture. Internal transfers are a *single* flow referenced by both lots.
Moisture leaving the measured system must be an explicit moisture flow;
added water and ingredients must be explicit incoming flows. A terminal
output needs ``destination: {kind, source}`` and ``outcome: {status, mass,
source, safety: {status, source}, nutrition}``, including a second mass
measurement. In schema 2, destination and outcome ``source`` each require the
terminal flow's globally unique physical ``load_id``; schema 1 keeps its
original unbound evidence shape. Nonhuman destinations are animal_feed,
compost, fuel, landfill,
wastewater, evaporation and industrial_use; their outcome status is
observed_other and nutrition is null. Human consumption needs
observed_consumed, ``safety.status: safe`` and ``nutrition: {status: useful,
source}``. For human consumption, the safety and nutrition ``source`` objects
each also declare the terminal flow's physical ``load_id``. This identifier is
checked for consistency, not authenticated. Retail sale or an unknown outcome
is not a terminal observation.
Nonterminal flows have null destination and outcome.
Observation times must follow input flow → lot operation → output flow →
terminal destination → observed outcome within the declared period.
For human consumption, safety and nutrition evidence must not predate the
output flow; retrospective evidence after consumption remains permitted within
the declared period.

Each burden row has ``group_id``, ``period``, ``actor_id``, ``source``,
``net_income`` (in top-level currency), and nonnegative ``cost``,
``work_hours``, ``energy_kwh``, ``water_l``, ``emissions_kg_co2e``. Exactly one
row is required for every declared group-period-actor combination. Optional
``service`` has ``equivalence: {id, service_unit, approved_at_utc,
approved_by_actor_ids, verified_by, record_sha256, source}`` and ``rows`` with
``group_id``, ``period``, ``consumption_flow_ids``, ``consumed_service``,
``feasible_max_service`` and ``source``. The two service measurements have
``value``, ``unit`` and ``uncertainty``. A row is required for every
group-period; IDs exactly cover observed human-consumption flows. The
equivalence approval is only declared, never authenticated. Denominator and
upper-bound errors are rejected, but this tool never calculates V or G.
Opt-in ``service.schema: 2`` requires each row's ``source`` to add a lowercase
``record_sha256`` and requires distinct ``(record_sha256, locator)`` references.
Opt-in ``service.schema: 3`` additionally requires approved-equivalence-declared
``denominator_rules`` of ``{id, material_id, classification, basis,
max_service_per_kg}`` and each
row's ``denominator_inputs`` of ``{input_flow_id, rule_id}``. Every external
input declares ``material_id`` and is assigned exactly once to its material rule.
Eligible feed/ingredient
mass contributes its positive coefficient; unsuitable feed/ingredient and added
water have zero coefficients. Both feasible service and its uncertainty must
equal the exact rational sums over eligible input masses and uncertainties.
The approval and input classifications remain declarations. This preflight
does not open source bytes; a separate content audit binds them.
Tolerance evidence and the declared equivalence approval record must predate
the first assignment; the latter cannot predate its declared approval.

This is a structural audit of supplied JSON. It cannot authenticate sources,
load identity, weighing calibration, safety tests, approval signatures,
representativeness, causal assignment, actor coverage, equivalence content,
or field impact. ``stage`` is free text; schema-2/3 ``stage_role`` is also only a
declaration. Full production-to-consumption scope and observed household
coverage require an external audit. Its worst-case
balance allowance sums declared measurement uncertainties and a declared
tolerance; that is not a confidence interval. Even a passing preflight leaves
criterion 3 unassessed. FAO's distinct tracked loads and stage percentages
cannot be turned into one continuous lot here.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict, deque
from datetime import datetime
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any


CLASSIFICATION = "field_flow_preflight_declared_only"
NOTICE = (
    "Valid means only that the declared graph is internally consistent. Schema 2 "
    "checks a declared stage-role witness path for every human-consumption "
    "flow; schema 1 does not check stage coverage. Neither checks full "
    "population, undeclared branches or within-lot input-output lineage. "
    "Declared JSON only: physical identity, stage truth, source truth, calibration, safety, "
    "nutrition, independent approval, causal design and observed impact are not "
    "authenticated. No V or G is calculated; criterion 3 is not assessed."
)
NOTICE_SCHEMA3 = (
    "Valid means only that the declared graph and nominal allocations are internally "
    "consistent. Schema 3 checks a conservative lower bound of complete-stage mass "
    "lineage for every declared human-consumption flow. Lot-path witnesses are only "
    "context and do not prove within-lot physical lineage. Declared JSON only: "
    "physical identity, allocation truth, stage truth, source truth, calibration, "
    "safety, nutrition, independent approval, causal design and observed impact are "
    "not authenticated. Undeclared branches and households are not checked. "
    "No V or G is calculated; criterion 3 is not assessed."
)
NOTICE_SERVICE_SCHEMA3 = (
    " Service schema 3 reconciles only a declared additive ceiling under the "
    "declared approved-equivalence rules; it does not establish true physical "
    "feasibility or validate material classifications."
)
MASS_FACTORS = {"kg": Fraction(1), "g": Fraction(1, 1000), "t": Fraction(1000)}
MAX_ABS_NUMBER = Decimal("1e18")
MIN_ABS_NONZERO = Decimal("1e-18")
MAX_DECIMAL_DIGITS = 80
INPUT_KINDS = {"feed", "ingredient", "water_addition"}
OUTPUT_KINDS = {"product", "coproduct", "residue", "moisture"}
STAGE_ROLES = {"production", "storage", "transport", "transformation", "other"}
NONHUMAN_DESTINATIONS = {
    "animal_feed", "compost", "fuel", "landfill", "wastewater",
    "evaporation", "industrial_use",
}
UTC_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class FieldFlowError(ValueError):
    """Malformed or internally inconsistent declared field observations."""


def _object(value: Any, label: str, required: set[str], optional: set[str] | None = None) -> dict[str, Any]:
    if type(value) is not dict:
        raise FieldFlowError(f"{label} must be an object")
    missing = required - value.keys()
    extra = value.keys() - required - (optional or set())
    if missing or extra:
        raise FieldFlowError(f"{label} has missing keys {sorted(missing)} or unexpected keys {sorted(extra)}")
    return value


def _array(value: Any, label: str, *, nonempty: bool = True) -> list[Any]:
    if type(value) is not list or (nonempty and not value):
        raise FieldFlowError(f"{label} must be {'a nonempty' if nonempty else 'an'} array")
    return value


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise FieldFlowError(f"{label} must be nonempty trimmed text")
    return value


def _choice(value: Any, label: str, choices: set[str]) -> str:
    item = _text(value, label)
    if item not in choices:
        raise FieldFlowError(f"{label} must be one of {sorted(choices)}")
    return item


def _number(value: Any, label: str, *, positive: bool = False, nonnegative: bool = True) -> Decimal:
    if type(value) not in (int, float, Decimal):
        raise FieldFlowError(f"{label} must be a finite number")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise FieldFlowError(f"{label} must be a finite number") from exc
    if not result.is_finite() or (positive and result <= 0) or (nonnegative and result < 0):
        bound = "positive" if positive else "nonnegative" if nonnegative else "finite"
        raise FieldFlowError(f"{label} must be {bound} and finite")
    if len(result.as_tuple().digits) > MAX_DECIMAL_DIGITS:
        raise FieldFlowError(f"{label} has too many decimal digits")
    if result != 0:
        exponent = result.adjusted()
        if exponent > 18 or exponent < -18:
            raise FieldFlowError(f"{label} magnitude is outside supported numeric range")
        magnitude = result.copy_abs()
        if magnitude > MAX_ABS_NUMBER or magnitude < MIN_ABS_NONZERO:
            raise FieldFlowError(f"{label} magnitude is outside supported numeric range")
    return result


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not str or UTC_TIMESTAMP.fullmatch(value) is None:
        raise FieldFlowError(f"{label} must be a UTC timestamp ending in Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FieldFlowError(f"{label} is not a valid UTC timestamp") from exc


def _evidence(value: Any, label: str) -> datetime:
    row = _object(value, label, {"source_id", "locator", "observed_at_utc", "method"})
    for key in ("source_id", "locator", "method"):
        _text(row[key], f"{label}.{key}")
    return _utc(row["observed_at_utc"], f"{label}.observed_at_utc")


def _period_evidence(value: Any, label: str, interval: tuple[datetime, datetime]) -> datetime:
    observed_at = _evidence(value, label)
    if not interval[0] <= observed_at < interval[1]:
        raise FieldFlowError(f"{label}.observed_at_utc falls outside declared period")
    return observed_at


def _load_bound_period_evidence(value: Any, label: str, interval: tuple[datetime, datetime],
                                expected_load_id: str) -> datetime:
    source = _object(value, label, {"source_id", "locator", "observed_at_utc", "method", "load_id"})
    evidence = {key: source[key] for key in ("source_id", "locator", "observed_at_utc", "method")}
    observed_at = _period_evidence(evidence, label, interval)
    declared_load_id = _text(source["load_id"], f"{label}.load_id")
    if declared_load_id != expected_load_id:
        raise FieldFlowError(f"{label}.load_id does not match terminal flow.load_id")
    return observed_at


def _allocation_period_evidence(value: Any, label: str, interval: tuple[datetime, datetime],
                                input_load_id: str, output_load_id: str) -> datetime:
    source = _object(value, label, {
        "source_id", "locator", "observed_at_utc", "method", "input_load_id", "output_load_id",
    })
    evidence = {key: source[key] for key in ("source_id", "locator", "observed_at_utc", "method")}
    observed_at = _period_evidence(evidence, label, interval)
    for field, expected in (("input_load_id", input_load_id), ("output_load_id", output_load_id)):
        if _text(source[field], f"{label}.{field}") != expected:
            raise FieldFlowError(f"{label}.{field} does not match linked flow.load_id")
    return observed_at


def _mass(value: Any, label: str) -> tuple[Fraction, Fraction]:
    row = _object(value, label, {"value", "unit", "uncertainty"})
    unit = _choice(row["unit"], f"{label}.unit", set(MASS_FACTORS))
    mass = _number(row["value"], f"{label}.value", positive=True)
    uncertainty = _number(row["uncertainty"], f"{label}.uncertainty")
    return Fraction(mass) * MASS_FACTORS[unit], Fraction(uncertainty) * MASS_FACTORS[unit]


def _exact_decimal(value: Fraction) -> str:
    """Render finite-decimal mass arithmetic without context rounding."""
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        twos += 1
        denominator //= 2
    while denominator % 5 == 0:
        fives += 1
        denominator //= 5
    if denominator != 1:
        return str(value)
    places = max(twos, fives)
    scale = 10 ** places
    digits = abs(value.numerator) * (scale // value.denominator)
    whole, fraction = divmod(digits, scale)
    sign = "-" if value < 0 else ""
    if fraction == 0:
        return sign + str(whole)
    return sign + str(whole) + "." + str(fraction).zfill(places).rstrip("0")


def _ids(value: Any, label: str, *, nonempty: bool = True) -> list[str]:
    result = [_text(item, f"{label}[{index}]") for index, item in enumerate(_array(value, label, nonempty=nonempty))]
    if len(result) != len(set(result)):
        raise FieldFlowError(f"{label} contains duplicate IDs")
    return result


def _unique_id(value: Any, label: str, seen: set[str]) -> str:
    item = _text(value, label)
    if item in seen:
        raise FieldFlowError(f"duplicate ID: {item}")
    seen.add(item)
    return item


def _validate_destination(flow: dict[str, Any], label: str, mass: tuple[Fraction, Fraction],
                          interval: tuple[datetime, datetime],
                          flow_at: datetime, schema: int) -> tuple[str | None, datetime | None]:
    terminal = flow["to_lot_id"] is None
    destination = flow["destination"]
    outcome = flow["outcome"]
    if not terminal:
        if destination is not None or outcome is not None:
            raise FieldFlowError(f"{label} internal or input flow cannot have terminal destination/outcome")
        return None, None
    dest = _object(destination, f"{label}.destination", {"kind", "source"})
    kind = _choice(dest["kind"], f"{label}.destination.kind", NONHUMAN_DESTINATIONS | {"human_consumption"})
    if schema >= 2:
        destination_at = _load_bound_period_evidence(
            dest["source"], f"{label}.destination.source", interval, flow["load_id"]
        )
    else:
        destination_at = _period_evidence(dest["source"], f"{label}.destination.source", interval)
    observed = _object(outcome, f"{label}.outcome", {"status", "mass", "source", "safety", "nutrition"})
    status = _choice(observed["status"], f"{label}.outcome.status", {"observed_consumed", "observed_other"})
    observed_mass = _mass(observed["mass"], f"{label}.outcome.mass")
    if schema >= 2:
        outcome_at = _load_bound_period_evidence(
            observed["source"], f"{label}.outcome.source", interval, flow["load_id"]
        )
    else:
        outcome_at = _period_evidence(observed["source"], f"{label}.outcome.source", interval)
    if not flow_at <= destination_at <= outcome_at:
        raise FieldFlowError(f"{label} terminal chronology must be flow <= destination <= outcome")
    if abs(mass[0] - observed_mass[0]) > mass[1] + observed_mass[1]:
        raise FieldFlowError(f"{label} terminal mass differs from observed destination mass beyond uncertainty")
    safety = _object(observed["safety"], f"{label}.outcome.safety", {"status", "source"})
    safety_status = _choice(safety["status"], f"{label}.outcome.safety.status", {"safe", "unsafe", "not_assessed"})
    if kind == "human_consumption":
        safety_at = _load_bound_period_evidence(safety["source"], f"{label}.outcome.safety.source",
                                                interval, flow["load_id"])
    else:
        _period_evidence(safety["source"], f"{label}.outcome.safety.source", interval)
    if kind == "human_consumption":
        if status != "observed_consumed" or safety_status != "safe":
            raise FieldFlowError(f"{label} human consumption requires observed ingestion and safe evidence")
        if safety_at < flow_at:
            raise FieldFlowError(f"{label}.outcome.safety.source.observed_at_utc predates terminal output flow")
        nutrition = _object(observed["nutrition"], f"{label}.outcome.nutrition", {"status", "source"})
        if nutrition["status"] != "useful":
            raise FieldFlowError(f"{label} human consumption requires useful nutrition evidence")
        nutrition_at = _load_bound_period_evidence(nutrition["source"], f"{label}.outcome.nutrition.source",
                                                   interval, flow["load_id"])
        if nutrition_at < flow_at:
            raise FieldFlowError(f"{label}.outcome.nutrition.source.observed_at_utc predates terminal output flow")
        if flow["kind"] not in {"product", "coproduct"}:
            raise FieldFlowError(f"{label} residue or moisture cannot be classified as consumed food")
    elif status != "observed_other" or observed["nutrition"] is not None:
        raise FieldFlowError(f"{label} nonhuman destination requires observed_other and null nutrition")
    if flow["kind"] == "moisture" and kind not in {"evaporation", "wastewater"}:
        raise FieldFlowError(f"{label} moisture must end at evaporation or wastewater")
    if kind in {"evaporation", "wastewater"} and flow["kind"] != "moisture":
        raise FieldFlowError(f"{label} evaporation or wastewater must be explicit moisture flow")
    return kind, outcome_at


def _validate_service(service: Any, groups: dict[str, dict[str, Any]], periods: set[str],
                      actors: set[str], consumed: dict[tuple[str, str], set[str]],
                      period_times: dict[str, tuple[datetime, datetime]],
                      consumed_outcome_at: dict[str, datetime],
                      flows: dict[str, dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    if service is None:
        return "not_assessed_no_declared_equivalence", []
    row = _object(service, "service", {"equivalence", "rows"}, {"schema"})
    service_schema = row.get("schema")
    if "schema" in row and (type(service_schema) is not int or service_schema not in {2, 3}):
        raise FieldFlowError("service.schema must be integer 2 or 3 when present")
    eq = _object(row["equivalence"], "service.equivalence", {
        "id", "service_unit", "approved_at_utc", "approved_by_actor_ids",
        "verified_by", "record_sha256", "source",
    } | ({"denominator_rules"} if service_schema == 3 else set()))
    _text(eq["id"], "service.equivalence.id")
    unit = _text(eq["service_unit"], "service.equivalence.service_unit")
    approved_at = _utc(eq["approved_at_utc"], "service.equivalence.approved_at_utc")
    approved_by = _ids(eq["approved_by_actor_ids"], "service.equivalence.approved_by_actor_ids")
    if not set(approved_by) <= actors:
        raise FieldFlowError("service equivalence approval names an unknown actor")
    verifier = _text(eq["verified_by"], "service.equivalence.verified_by")
    if verifier in approved_by:
        raise FieldFlowError("service equivalence verifier must be distinct from approving actors")
    digest = _text(eq["record_sha256"], "service.equivalence.record_sha256")
    if SHA256.fullmatch(digest) is None:
        raise FieldFlowError("service.equivalence.record_sha256 must be lowercase SHA-256")
    equivalence_source_at = _evidence(eq["source"], "service.equivalence.source")
    first_assignment_at = min(group["assigned_at"] for group in groups.values())
    if approved_at >= first_assignment_at:
        raise FieldFlowError("service equivalence approval must predate every group assignment")
    if equivalence_source_at < approved_at:
        raise FieldFlowError("service.equivalence.source predates its declared approval")
    if equivalence_source_at >= first_assignment_at:
        raise FieldFlowError("service.equivalence.source must predate first group assignment")
    rules: dict[str, tuple[str, str, str, Fraction]] = {}
    if service_schema == 3:
        seen_materials: set[str] = set()
        for index, raw_rule in enumerate(_array(eq["denominator_rules"],
                                                "service.equivalence.denominator_rules")):
            rule_label = f"service.equivalence.denominator_rules[{index}]"
            rule = _object(raw_rule, rule_label,
                           {"id", "material_id", "classification", "basis",
                            "max_service_per_kg"})
            rule_id = _text(rule["id"], f"{rule_label}.id")
            if rule_id in rules:
                raise FieldFlowError(f"{rule_label}.id repeats a denominator rule")
            material_id = _text(rule["material_id"], f"{rule_label}.material_id")
            if material_id in seen_materials:
                raise FieldFlowError(f"{rule_label}.material_id repeats a material")
            seen_materials.add(material_id)
            basis = _text(rule["basis"], f"{rule_label}.basis")
            classification = _choice(rule["classification"],
                                     f"{rule_label}.classification",
                                     {"eligible", "unsuitable", "water"})
            coefficient = _number(rule["max_service_per_kg"],
                                  f"{rule_label}.max_service_per_kg")
            if (classification == "eligible" and coefficient <= 0) or (
                classification != "eligible" and coefficient != 0
            ):
                raise FieldFlowError(f"{rule_label}.max_service_per_kg must be positive for eligible material and zero for unsuitable or water")
            rules[rule_id] = material_id, classification, basis, Fraction(coefficient)
    seen: set[tuple[str, str]] = set()
    seen_source_refs: set[tuple[str, str]] = set()
    reconciliations: list[dict[str, Any]] = []
    for index, raw in enumerate(_array(row["rows"], "service.rows")):
        label = f"service.rows[{index}]"
        item = _object(raw, label, {
            "group_id", "period", "consumption_flow_ids", "consumed_service",
            "feasible_max_service", "source",
        } | ({"denominator_inputs"} if service_schema == 3 else set()))
        key = (_text(item["group_id"], f"{label}.group_id"), _text(item["period"], f"{label}.period"))
        if key[0] not in groups or key[1] not in periods:
            raise FieldFlowError(f"{label} references unknown group or period")
        if key in seen:
            raise FieldFlowError(f"duplicate service group-period row: {key}")
        seen.add(key)
        flow_ids = _ids(item["consumption_flow_ids"], f"{label}.consumption_flow_ids", nonempty=False)
        if set(flow_ids) != consumed[key]:
            raise FieldFlowError(f"{label} consumption_flow_ids must exactly cover observed consumed flows")
        quantities: list[Decimal] = []
        uncertainties: list[Decimal] = []
        for field in ("consumed_service", "feasible_max_service"):
            measure = _object(item[field], f"{label}.{field}", {"value", "unit", "uncertainty"})
            if measure["unit"] != unit:
                raise FieldFlowError(f"{label}.{field}.unit differs from approved service unit")
            quantities.append(_number(measure["value"], f"{label}.{field}.value",
                                      positive=field == "feasible_max_service"))
            uncertainties.append(_number(measure["uncertainty"], f"{label}.{field}.uncertainty"))
        if quantities[0] > quantities[1]:
            raise FieldFlowError(f"{label} observed service exceeds feasible maximum (V > 1)")
        if not flow_ids and quantities[0] != 0:
            raise FieldFlowError(f"{label} positive consumed service has no observed consumption flow")
        source = item["source"]
        if service_schema == 3:
            inputs = _array(item["denominator_inputs"], f"{label}.denominator_inputs")
            actual_inputs = {flow_id for flow_id, flow in flows.items()
                             if flow["from"] is None and
                             (flow["group_id"], flow["period"]) == key}
            seen_inputs: set[str] = set()
            total = Fraction(0)
            total_uncertainty = Fraction(0)
            excluded_mass: dict[str, Fraction] = {"unsuitable": Fraction(0),
                                                  "water": Fraction(0)}
            contributions: list[dict[str, str]] = []
            for input_index, raw_input in enumerate(inputs):
                input_label = f"{label}.denominator_inputs[{input_index}]"
                input_item = _object(raw_input, input_label, {"input_flow_id", "rule_id"})
                input_id = _text(input_item["input_flow_id"], f"{input_label}.input_flow_id")
                rule_id = _text(input_item["rule_id"], f"{input_label}.rule_id")
                if input_id in seen_inputs:
                    raise FieldFlowError(f"{input_label} double counts an external input")
                seen_inputs.add(input_id)
                if input_id not in actual_inputs:
                    raise FieldFlowError(f"{input_label} must reference an external input in the same group-period")
                if rule_id not in rules:
                    raise FieldFlowError(f"{input_label}.rule_id is not an approved denominator rule")
                flow = flows[input_id]
                material_id, classification, basis, coefficient = rules[rule_id]
                if (flow["kind"] == "water_addition") != (classification == "water"):
                    raise FieldFlowError(f"{input_label} flow kind and denominator classification disagree")
                if flow["material_id"] != material_id:
                    raise FieldFlowError(f"{input_label} material_id differs from approved denominator rule")
                contribution = flow["mass"][0] * coefficient
                contribution_uncertainty = flow["mass"][1] * coefficient
                if classification == "eligible":
                    total += contribution
                    total_uncertainty += contribution_uncertainty
                else:
                    excluded_mass[classification] += flow["mass"][0]
                contributions.append({
                    "input_flow_id": input_id, "flow_kind": flow["kind"],
                    "material_id": material_id, "rule_id": rule_id,
                    "classification": classification, "basis": basis,
                    "mass_kg": _exact_decimal(flow["mass"][0]),
                    "mass_uncertainty_kg": _exact_decimal(flow["mass"][1]),
                    "max_service_per_kg": _exact_decimal(coefficient),
                    "service_contribution": _exact_decimal(contribution),
                    "service_uncertainty_contribution": _exact_decimal(contribution_uncertainty),
                })
            if seen_inputs != actual_inputs:
                raise FieldFlowError(f"{label}.denominator_inputs missing external inputs: {sorted(actual_inputs - seen_inputs)}")
            if Fraction(quantities[1]) != total:
                raise FieldFlowError(f"{label}.feasible_max_service differs from exact external-input denominator")
            if Fraction(uncertainties[1]) != total_uncertainty:
                raise FieldFlowError(f"{label}.feasible_max_service.uncertainty differs from exact eligible-input uncertainty")
            reconciliations.append({"group_id": key[0], "period": key[1],
                                    "recomputed_feasible_max_service": _exact_decimal(total),
                                    "recomputed_uncertainty": _exact_decimal(total_uncertainty),
                                    "excluded_unsuitable_mass_kg": _exact_decimal(excluded_mass["unsuitable"]),
                                    "excluded_water_mass_kg": _exact_decimal(excluded_mass["water"]),
                                    "inputs": sorted(contributions,
                                                     key=lambda item: item["input_flow_id"]),
                                    "unit": unit, "status": "declared_only_additive_ceiling"})
        if service_schema in {2, 3}:
            source = _object(source, f"{label}.source", {
                "source_id", "locator", "observed_at_utc", "method", "record_sha256",
            })
            source_digest = source["record_sha256"]
            if type(source_digest) is not str or SHA256.fullmatch(source_digest) is None:
                raise FieldFlowError(f"{label}.source.record_sha256 must be lowercase SHA-256")
            locator = _text(source["locator"], f"{label}.source.locator")
            reference = source_digest, locator
            if reference in seen_source_refs:
                raise FieldFlowError(f"{label}.source repeats a service digest and locator reference")
            seen_source_refs.add(reference)
            source = {field: source[field] for field in
                      ("source_id", "locator", "observed_at_utc", "method")}
        row_at = _period_evidence(source, f"{label}.source", period_times[key[1]])
        if any(row_at < consumed_outcome_at[flow_id] for flow_id in flow_ids):
            raise FieldFlowError(f"{label} service observation predates a covered consumption outcome")
    expected = {(group, period) for group in groups for period in periods}
    if seen != expected:
        raise FieldFlowError(f"service.rows missing group-period combinations: {sorted(expected - seen)}")
    return ("declared_external_input_denominator_reconciled_approval_unverified" if service_schema == 3
            else "declared_service_inputs_bounded_approval_unverified"), sorted(
                reconciliations, key=lambda item: (item["group_id"], item["period"]))


def _stage_witness_paths(lots: dict[str, dict[str, Any]], flows: dict[str, dict[str, Any]],
                         consumed: dict[tuple[str, str], set[str]], adjacency: dict[str, set[str]],
                         group_periods: set[tuple[str, str]]) -> list[dict[str, Any]]:
    """Find an uninterrupted stage sequence for each consumed flow in schema 2."""
    def advance(lot_id: str, stored: bool, transported: bool,
                transformations: int) -> tuple[str, bool, bool, int]:
        role = lots[lot_id]["stage_role"]
        stored = stored or role == "storage"
        transported = transported or role == "transport"
        if role == "transformation":
            transformations = min(2, transformations + 1)
        return lot_id, stored, transported, transformations

    production_roots: dict[tuple[str, str], set[str]] = defaultdict(set)
    for flow in flows.values():
        target = flow["to"]
        if flow["from"] is None and flow["kind"] == "feed" and target is not None:
            if lots[target]["stage_role"] == "production":
                production_roots[(flow["group_id"], flow["period"])].add(target)

    witnesses: list[dict[str, Any]] = []
    for key in sorted(group_periods):
        roots = production_roots[key]
        consumed_by_lot: dict[str, list[str]] = defaultdict(list)
        for flow_id in sorted(consumed[key]):
            source = flows[flow_id]["from"]
            if source is not None:
                consumed_by_lot[source].append(flow_id)

        # A separate valid branch must not hide an untraced consumed output.
        reachable = set(roots)
        queue = deque(sorted(roots))
        while queue:
            for child in sorted(adjacency[queue.popleft()]):
                if child not in reachable:
                    reachable.add(child)
                    queue.append(child)
        untraced = [flow_id for lot_id, flow_ids in consumed_by_lot.items()
                    if lot_id not in reachable for flow_id in flow_ids]
        if untraced:
            raise FieldFlowError(
                f"group-period {key} has human-consumption flows not reachable from "
                f"externally fed production: {sorted(untraced)}"
            )

        # The search state follows one path. Summing roles over all reachable
        # nodes would falsely join stages on disjoint branches or coproducts.
        start_states = [advance(root, False, False, 0) for root in sorted(roots)]
        candidates = deque(start_states)
        parents: dict[tuple[str, bool, bool, int], tuple[str, bool, bool, int] | None] = {
            state: None for state in start_states
        }
        witnesses_for_key: dict[str, dict[str, Any]] = {}
        while candidates:
            state = candidates.popleft()
            lot_id, stored, transported, transformations = state
            if stored and transported and transformations == 2 and consumed_by_lot[lot_id]:
                path = []
                cursor: tuple[str, bool, bool, int] | None = state
                while cursor is not None:
                    path.append(cursor[0])
                    cursor = parents[cursor]
                for flow_id in consumed_by_lot[lot_id]:
                    witnesses_for_key.setdefault(
                        flow_id,
                        {"group_id": key[0], "period": key[1], "lot_ids": path[::-1],
                         "consumption_flow_id": flow_id},
                    )
                if len(witnesses_for_key) == len(consumed[key]):
                    break
            for child in sorted(adjacency[lot_id]):
                child_state = advance(child, stored, transported, transformations)
                if child_state not in parents:
                    parents[child_state] = state
                    candidates.append(child_state)
        missing = consumed[key] - witnesses_for_key.keys()
        if not witnesses_for_key or missing:
            raise FieldFlowError(
                f"group-period {key} lacks a continuous declared path from externally fed "
                "production to human consumption visiting storage, transport, and two "
                f"transformations in series (no fixed stage order) for flows: {sorted(missing)}"
            )
        witnesses.extend(witnesses_for_key[flow_id] for flow_id in sorted(witnesses_for_key))
    return witnesses


def _validate_allocations(lots: dict[str, dict[str, Any]], flows: dict[str, dict[str, Any]],
                          period_times: dict[str, tuple[datetime, datetime]],
                          ) -> dict[str, list[tuple[str, str, Fraction, Fraction]]]:
    """Check schema-3 load-bound rows and exact nominal incident-flow totals."""
    result: dict[str, list[tuple[str, str, Fraction, Fraction]]] = {}
    for lot_id, lot in lots.items():
        label = f"lot {lot_id}.allocations"
        rows: list[tuple[str, str, Fraction, Fraction]] = []
        pairs: set[tuple[str, str]] = set()
        input_totals: dict[str, Fraction] = defaultdict(Fraction)
        output_totals: dict[str, Fraction] = defaultdict(Fraction)
        for index, raw in enumerate(_array(lot["allocations"], label)):
            row_label = f"{label}[{index}]"
            row = _object(raw, row_label, {"input_flow_id", "output_flow_id", "mass", "source"})
            input_id = _text(row["input_flow_id"], f"{row_label}.input_flow_id")
            output_id = _text(row["output_flow_id"], f"{row_label}.output_flow_id")
            if input_id not in lot["inputs"] or output_id not in lot["outputs"]:
                raise FieldFlowError(f"{row_label} must reference local input and output flows")
            pair = input_id, output_id
            if pair in pairs:
                raise FieldFlowError(f"{row_label} duplicates allocation pair {pair}")
            pairs.add(pair)
            mass, uncertainty = _mass(row["mass"], f"{row_label}.mass")
            observed_at = _allocation_period_evidence(
                row["source"], f"{row_label}.source", period_times[lot["period"]],
                flows[input_id]["load_id"], flows[output_id]["load_id"],
            )
            if observed_at < flows[output_id]["observed_at"]:
                raise FieldFlowError(f"{row_label}.source predates its output flow")
            rows.append((input_id, output_id, mass, uncertainty))
            input_totals[input_id] += mass
            output_totals[output_id] += mass
        if set(input_totals) != lot["inputs"] or set(output_totals) != lot["outputs"]:
            raise FieldFlowError(f"{label} must cover every local input and output flow")
        for side, totals, flow_ids in (("input", input_totals, lot["inputs"]),
                                      ("output", output_totals, lot["outputs"])):
            for flow_id in sorted(flow_ids):
                nominal = flows[flow_id]["mass"][0]
                if totals[flow_id] != nominal:
                    raise FieldFlowError(
                        f"{label} {side} flow {flow_id} has nominal allocation sum "
                        f"{_exact_decimal(totals[flow_id])} kg, expected {_exact_decimal(nominal)} kg; "
                        "schema 3 requires exact nominal reconciliation because uncertain "
                        "marginals may not reconcile exactly"
                    )
        result[lot_id] = rows
    return result


def _lineage_bounds(lots: dict[str, dict[str, Any]], flows: dict[str, dict[str, Any]],
                    consumed: dict[tuple[str, str], set[str]], lot_order: list[str],
                    allocations: dict[str, list[tuple[str, str, Fraction, Fraction]]],
                    ) -> list[dict[str, str]]:
    """Propagate conservative mass meeting each minimum stage requirement."""
    StageState = tuple[bool, bool, int]
    incident_limits: dict[str, list[tuple[Fraction, Fraction]]] = defaultdict(list)
    row_limits: dict[str, list[tuple[Fraction, Fraction]]] = {}
    for lot_id, rows in allocations.items():
        input_bounds: dict[str, list[Fraction]] = defaultdict(lambda: [Fraction(0), Fraction(0)])
        output_bounds: dict[str, list[Fraction]] = defaultdict(lambda: [Fraction(0), Fraction(0)])
        row_limits[lot_id] = []
        for input_id, output_id, nominal, uncertainty in rows:
            lower, upper = max(Fraction(0), nominal - uncertainty), nominal + uncertainty
            row_limits[lot_id].append((lower, upper))
            for totals, flow_id in ((input_bounds, input_id), (output_bounds, output_id)):
                totals[flow_id][0] += lower
                totals[flow_id][1] += upper
        for totals in (input_bounds, output_bounds):
            for flow_id, (lower, upper) in totals.items():
                incident_limits[flow_id].append((lower, upper))

    flow_limits: dict[str, tuple[Fraction, Fraction]] = {}
    for flow_id, flow in flows.items():
        nominal, uncertainty = flow["mass"]
        lower = max(Fraction(0), nominal - uncertainty)
        upper = nominal + uncertainty
        for incident_lower, incident_upper in incident_limits[flow_id]:
            lower = max(lower, incident_lower)
            upper = min(upper, incident_upper)
        if lower > upper:
            raise FieldFlowError(f"schema 3 flow {flow_id} has inconsistent mass intervals")
        flow_limits[flow_id] = lower, upper

    allocation_lowers: dict[str, list[Fraction]] = {}
    for lot_id, rows in allocations.items():
        by_input: dict[str, list[int]] = defaultdict(list)
        by_output: dict[str, list[int]] = defaultdict(list)
        for index, (input_id, output_id, _, _) in enumerate(rows):
            by_input[input_id].append(index)
            by_output[output_id].append(index)
        tightened = [list(limits) for limits in row_limits[lot_id]]
        for groups in (by_input, by_output):
            for flow_id, indices in groups.items():
                flow_lower, flow_upper = flow_limits[flow_id]
                sum_lower = sum((row_limits[lot_id][i][0] for i in indices), Fraction(0))
                sum_upper = sum((row_limits[lot_id][i][1] for i in indices), Fraction(0))
                for index in indices:
                    original_lower, original_upper = row_limits[lot_id][index]
                    tightened[index][0] = max(tightened[index][0],
                                              flow_lower - (sum_upper - original_upper))
                    tightened[index][1] = min(tightened[index][1],
                                              flow_upper - (sum_lower - original_lower))
        if any(lower > upper for lower, upper in tightened):
            raise FieldFlowError(f"schema 3 lot {lot_id} has inconsistent allocation intervals")
        allocation_lowers[lot_id] = [lower for lower, _ in tightened]

    thresholds: list[StageState] = [
        (stored, transported, transformations)
        for stored in (False, True)
        for transported in (False, True)
        for transformations in (0, 1, 2)
    ]
    bounds: dict[str, dict[StageState, Fraction]] = defaultdict(lambda: defaultdict(Fraction))
    for flow_id, flow in flows.items():
        target = flow["to"]
        if flow["from"] is None and flow["kind"] == "feed" and target is not None:
            if lots[target]["stage_role"] == "production":
                bounds[flow_id][(False, False, 0)] = flow_limits[flow_id][0]
    for lot_id in lot_order:
        role = lots[lot_id]["stage_role"]
        for index, (input_id, output_id, _, _) in enumerate(allocations[lot_id]):
            allocation_lower = allocation_lowers[lot_id][index]
            input_upper = flow_limits[input_id][1]
            for stored, transported, transformations in thresholds:
                # The preimage of an "at least" threshold is itself one
                # threshold. Keep the mass of all qualifying input states
                # together before taking the conservative intersection.
                required_before: StageState = (
                    stored and role != "storage",
                    transported and role != "transport",
                    max(0, transformations - (role == "transformation")),
                )
                guaranteed = bounds[input_id].get(required_before, Fraction(0))
                successor = max(Fraction(0), guaranteed + allocation_lower - input_upper)
                if successor == 0:
                    continue
                bounds[output_id][(stored, transported, transformations)] += successor
    result: list[dict[str, str]] = []
    missing: list[str] = []
    for group_id, period in sorted(consumed):
        for flow_id in sorted(consumed[(group_id, period)]):
            guaranteed = bounds[flow_id].get((True, True, 2), Fraction(0))
            if guaranteed <= 0:
                missing.append(flow_id)
            else:
                result.append({
                    "group_id": group_id, "period": period,
                    "consumption_flow_id": flow_id,
                    "guaranteed_stage_mass_kg": _exact_decimal(guaranteed),
                })
    if missing:
        raise FieldFlowError(
            "schema 3 has no positive conservative complete-stage mass lineage "
            f"from externally fed production for human-consumption flows: {missing}"
        )
    return result


def audit_field_flows(data: Any) -> dict[str, Any]:
    """Validate declarations and return a structural report, never an impact estimate."""
    root = _object(data, "field data", {
        "schema", "study_id", "balance_tolerance_kg", "tolerance_source", "currency",
        "actors", "groups", "periods", "lots", "flows", "burdens",
    }, {"service"})
    if type(root["schema"]) is not int or root["schema"] not in {1, 2, 3}:
        raise FieldFlowError("schema must be integer 1, 2 or 3")
    schema = root["schema"]
    service_schema3 = (type(root.get("service")) is dict
                       and root["service"].get("schema") == 3)
    study_id = _text(root["study_id"], "study_id")
    tolerance = Fraction(_number(root["balance_tolerance_kg"], "balance_tolerance_kg"))
    tolerance_source_at = _evidence(root["tolerance_source"], "tolerance_source")
    _text(root["currency"], "currency")
    ids: set[str] = {study_id}
    actors: set[str] = set()
    for index, raw in enumerate(_array(root["actors"], "actors")):
        label = f"actors[{index}]"
        item = _object(raw, label, {"id", "role"})
        actors.add(_unique_id(item["id"], f"{label}.id", ids))
        _text(item["role"], f"{label}.role")
    groups: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_array(root["groups"], "groups")):
        label = f"groups[{index}]"
        item = _object(raw, label, {"id", "arm", "stratum", "assigned_at_utc", "actor_ids", "source"})
        group_id = _unique_id(item["id"], f"{label}.id", ids)
        _choice(item["arm"], f"{label}.arm", {"control", "intervention"})
        _text(item["stratum"], f"{label}.stratum")
        assigned_at = _utc(item["assigned_at_utc"], f"{label}.assigned_at_utc")
        actor_ids = _ids(item["actor_ids"], f"{label}.actor_ids")
        if not set(actor_ids) <= actors:
            raise FieldFlowError(f"{label}.actor_ids references unknown actor")
        assignment_evidence_at = _evidence(item["source"], f"{label}.source")
        groups[group_id] = {"arm": item["arm"], "actor_ids": set(actor_ids),
                            "assigned_at": assigned_at, "assignment_evidence_at": assignment_evidence_at}
    if tolerance_source_at >= min(group["assigned_at"] for group in groups.values()):
        raise FieldFlowError("tolerance_source must predate first group assignment")
    periods: set[str] = set()
    period_times: dict[str, tuple[datetime, datetime]] = {}
    for index, raw in enumerate(_array(root["periods"], "periods")):
        label = f"periods[{index}]"
        item = _object(raw, label, {"id", "start_utc", "end_utc", "source"})
        period = _choice(item["id"], f"{label}.id", {"pre", "post"})
        if period in periods:
            raise FieldFlowError(f"duplicate period: {period}")
        periods.add(period)
        start = _utc(item["start_utc"], f"{label}.start_utc")
        end = _utc(item["end_utc"], f"{label}.end_utc")
        if start >= end:
            raise FieldFlowError(f"{label} start_utc must precede end_utc")
        period_times[period] = start, end
        _evidence(item["source"], f"{label}.source")
    if periods != {"pre", "post"} or period_times["pre"][1] > period_times["post"][0]:
        raise FieldFlowError("periods must contain nonoverlapping pre and post intervals")
    for group_id, group in groups.items():
        if not period_times["pre"][1] < group["assigned_at"] < period_times["post"][0]:
            raise FieldFlowError(f"group {group_id} assignment must fall after pre and before post")
        if not period_times["pre"][1] < group["assignment_evidence_at"] < period_times["post"][0]:
            raise FieldFlowError(f"group {group_id} assignment source falls outside assignment interval")
    lots: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_array(root["lots"], "lots")):
        label = f"lots[{index}]"
        item = _object(raw, label, {
            "id", "group_id", "period", "stage", "source", "input_flow_ids",
            "output_flow_ids", "observed_input_load_ids", "observed_output_load_ids",
        } | ({"stage_role"} if schema >= 2 else set())
          | ({"allocations"} if schema == 3 else set()))
        lot_id = _unique_id(item["id"], f"{label}.id", ids)
        group_id = _text(item["group_id"], f"{label}.group_id")
        period = _text(item["period"], f"{label}.period")
        if group_id not in groups or period not in periods:
            raise FieldFlowError(f"{label} references unknown group or period")
        _text(item["stage"], f"{label}.stage")
        stage_role = (_choice(item["stage_role"], f"{label}.stage_role", STAGE_ROLES)
                      if schema >= 2 else None)
        lot_at = _period_evidence(item["source"], f"{label}.source", period_times[period])
        inputs = _ids(item["input_flow_ids"], f"{label}.input_flow_ids")
        outputs = _ids(item["output_flow_ids"], f"{label}.output_flow_ids")
        if set(inputs) & set(outputs):
            raise FieldFlowError(f"{label} counts a flow as both input and output")
        lots[lot_id] = {
            "group_id": group_id, "period": period, "inputs": set(inputs), "outputs": set(outputs),
            "input_loads": set(_ids(item["observed_input_load_ids"], f"{label}.observed_input_load_ids")),
            "output_loads": set(_ids(item["observed_output_load_ids"], f"{label}.observed_output_load_ids")),
            "observed_at": lot_at, "stage_role": stage_role,
            "allocations": item["allocations"] if schema == 3 else None,
        }
    flows: dict[str, dict[str, Any]] = {}
    load_ids: set[str] = set()
    incoming: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)
    incoming_loads: dict[str, set[str]] = defaultdict(set)
    outgoing_loads: dict[str, set[str]] = defaultdict(set)
    consumed: dict[tuple[str, str], set[str]] = defaultdict(set)
    consumed_outcome_at: dict[str, datetime] = {}
    roots: dict[tuple[str, str], int] = defaultdict(int)
    terminals: dict[tuple[str, str], int] = defaultdict(int)
    for index, raw in enumerate(_array(root["flows"], "flows")):
        label = f"flows[{index}]"
        item = _object(raw, label, {
            "id", "load_id", "group_id", "period", "from_lot_id", "to_lot_id",
            "kind", "mass", "source", "destination", "outcome",
        }, {"material_id"} if service_schema3 else None)
        flow_id = _unique_id(item["id"], f"{label}.id", ids)
        load_id = _unique_id(item["load_id"], f"{label}.load_id", load_ids)
        group_id = _text(item["group_id"], f"{label}.group_id")
        period = _text(item["period"], f"{label}.period")
        key = group_id, period
        if group_id not in groups or period not in periods:
            raise FieldFlowError(f"{label} references unknown group or period")
        source_lot = item["from_lot_id"]
        target_lot = item["to_lot_id"]
        if source_lot is None and target_lot is None:
            raise FieldFlowError(f"{label} needs a source or target lot")
        for endpoint, value in (("from_lot_id", source_lot), ("to_lot_id", target_lot)):
            if value is not None:
                lot_id = _text(value, f"{label}.{endpoint}")
                if lot_id not in lots:
                    raise FieldFlowError(f"{label}.{endpoint} references unknown lot {lot_id}")
                if (lots[lot_id]["group_id"], lots[lot_id]["period"]) != key:
                    raise FieldFlowError(f"{label} crosses group, arm or period boundary")
        if source_lot == target_lot:
            raise FieldFlowError(f"{label} cannot loop to the same lot")
        kind = _choice(item["kind"], f"{label}.kind", INPUT_KINDS | OUTPUT_KINDS)
        if source_lot is None:
            if kind not in INPUT_KINDS:
                raise FieldFlowError(f"{label} external input must be feed, ingredient or water_addition")
            if service_schema3:
                if "material_id" not in item:
                    raise FieldFlowError(f"{label}.material_id is required for service.schema 3 external input")
                _text(item["material_id"], f"{label}.material_id")
            roots[key] += 1
        elif kind not in OUTPUT_KINDS:
            raise FieldFlowError(f"{label} output or transfer must be product, coproduct, residue or moisture")
        elif "material_id" in item:
            raise FieldFlowError(f"{label}.material_id is only for external inputs")
        if source_lot is not None and target_lot is not None and kind == "moisture":
            raise FieldFlowError(f"{label} moisture loss must have an observed terminal destination")
        mass = _mass(item["mass"], f"{label}.mass")
        flow_at = _period_evidence(item["source"], f"{label}.source", period_times[period])
        destination_kind, outcome_at = _validate_destination(item, label, mass,
                                                             period_times[period], flow_at, schema)
        if target_lot is None:
            terminals[key] += 1
        if destination_kind == "human_consumption":
            consumed[key].add(flow_id)
            if outcome_at is None:
                raise FieldFlowError(f"{label} lacks observed consumption time")
            consumed_outcome_at[flow_id] = outcome_at
        flows[flow_id] = {"from": source_lot, "to": target_lot, "kind": kind, "load_id": load_id,
                          "mass": mass, "group_id": group_id, "period": period,
                          "observed_at": flow_at, "outcome_at": outcome_at,
                          "material_id": item.get("material_id")}
        if source_lot is not None:
            outgoing[source_lot].add(flow_id)
            outgoing_loads[source_lot].add(load_id)
        if target_lot is not None:
            incoming[target_lot].add(flow_id)
            incoming_loads[target_lot].add(load_id)
    balances: list[dict[str, str]] = []
    adjacency: dict[str, set[str]] = defaultdict(set)
    indegree = {lot_id: 0 for lot_id in lots}
    for flow in flows.values():
        if flow["from"] is not None and flow["to"] is not None:
            if flow["to"] not in adjacency[flow["from"]]:
                adjacency[flow["from"]].add(flow["to"])
                indegree[flow["to"]] += 1
    queue = deque(lot_id for lot_id, degree in indegree.items() if degree == 0)
    visited = 0
    lot_order: list[str] = []
    while queue:
        parent = queue.popleft()
        visited += 1
        lot_order.append(parent)
        for child in adjacency[parent]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(lots):
        raise FieldFlowError("lot graph contains a cycle")
    for flow_id, flow in flows.items():
        if flow["from"] is not None and lots[flow["from"]]["observed_at"] > flow["observed_at"]:
            raise FieldFlowError(f"flow {flow_id} precedes its source lot operation")
        if flow["to"] is not None and flow["observed_at"] > lots[flow["to"]]["observed_at"]:
            raise FieldFlowError(f"flow {flow_id} arrives after its target lot operation")
    for lot_id, lot in lots.items():
        if lot["inputs"] != incoming[lot_id] or lot["outputs"] != outgoing[lot_id]:
            raise FieldFlowError(f"lot {lot_id} input/output flow linkage is incomplete or double counted")
        if lot["input_loads"] != incoming_loads[lot_id] or lot["output_loads"] != outgoing_loads[lot_id]:
            raise FieldFlowError(f"lot {lot_id} observed physical load IDs do not match linked flows")
        input_mass = sum((flows[flow_id]["mass"][0] for flow_id in lot["inputs"]), Fraction(0))
        output_mass = sum((flows[flow_id]["mass"][0] for flow_id in lot["outputs"]), Fraction(0))
        uncertainty = sum((flows[flow_id]["mass"][1] for flow_id in lot["inputs"] | lot["outputs"]), Fraction(0))
        allowed = tolerance + uncertainty
        residual = input_mass - output_mass
        if abs(residual) > allowed:
            raise FieldFlowError(f"lot {lot_id} mass balance residual {_exact_decimal(residual)} kg exceeds allowance {_exact_decimal(allowed)} kg; check additions, moisture and destinations")
        balances.append({"lot_id": lot_id, "input_kg": _exact_decimal(input_mass),
                         "output_kg": _exact_decimal(output_mass),
                         "residual_kg": _exact_decimal(residual), "allowance_kg": _exact_decimal(allowed)})
    expected_gp = {(group_id, period) for group_id in groups for period in periods}
    actual_gp = {(lot["group_id"], lot["period"]) for lot in lots.values()}
    if actual_gp != expected_gp or any(not roots[key] or not terminals[key] for key in expected_gp):
        raise FieldFlowError("every group-period needs a complete observed path from external input to terminal destination")
    allocations = _validate_allocations(lots, flows, period_times) if schema == 3 else {}
    stage_witnesses = (_stage_witness_paths(lots, flows, consumed, adjacency, expected_gp)
                       if schema >= 2 else [])
    lineage_bounds = (_lineage_bounds(lots, flows, consumed, lot_order, allocations)
                      if schema == 3 else [])
    burden_keys: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(_array(root["burdens"], "burdens")):
        label = f"burdens[{index}]"
        item = _object(raw, label, {
            "group_id", "period", "actor_id", "source", "net_income", "cost",
            "work_hours", "energy_kwh", "water_l", "emissions_kg_co2e",
        })
        group_id = _text(item["group_id"], f"{label}.group_id")
        period = _text(item["period"], f"{label}.period")
        actor_id = _text(item["actor_id"], f"{label}.actor_id")
        if group_id not in groups or period not in periods or actor_id not in groups[group_id]["actor_ids"]:
            raise FieldFlowError(f"{label} references unknown group-period actor")
        key = group_id, period, actor_id
        if key in burden_keys:
            raise FieldFlowError(f"duplicate burden row for group-period actor: {key}")
        burden_keys.add(key)
        _period_evidence(item["source"], f"{label}.source", period_times[period])
        _number(item["net_income"], f"{label}.net_income", nonnegative=False)
        for metric in ("cost", "work_hours", "energy_kwh", "water_l", "emissions_kg_co2e"):
            _number(item[metric], f"{label}.{metric}")
    expected_burdens = {(group_id, period, actor_id)
                        for group_id, group in groups.items() for period in periods
                        for actor_id in group["actor_ids"]}
    if burden_keys != expected_burdens:
        raise FieldFlowError(f"missing actor-specific burden rows: {sorted(expected_burdens - burden_keys)}")
    service_status, service_reconciliation = _validate_service(
        root.get("service"), groups, periods, actors, consumed,
        period_times, consumed_outcome_at, flows)
    notice = NOTICE_SCHEMA3 if schema == 3 else NOTICE
    if service_schema3:
        notice += NOTICE_SERVICE_SCHEMA3
    return {
        "schema": schema, "classification": CLASSIFICATION, "valid": True,
        "study_id": study_id, "notice": notice,
        "counts": {"groups": len(groups), "lots": len(lots), "flows": len(flows),
                   "terminal_flows": sum(terminals.values()),
                   "consumed_flows": sum(map(len, consumed.values())), "burden_rows": len(burden_keys)},
        "balances": sorted(balances, key=lambda item: item["lot_id"]),
        "scope_status": ("declared_conservative_mass_lineage_per_consumed_flow" if schema == 3
                         else "declared_stage_witness_per_consumed_flow_only" if schema == 2
                         else "declared_graph_only_full_chain_not_checked"),
        "stage_witnesses": stage_witnesses,
        **({"lineage_bounds": lineage_bounds} if schema == 3 else {}),
        "service_status": service_status,
        **({"service_denominator_reconciliation": service_reconciliation,
            "service_denominator_rule_approval_byte_bound": False,
            "service_denominator_input_byte_bound": False}
           if service_schema3
           else {}),
        **({"service_v_input_byte_bound": False}
           if type(root.get("service")) is dict and root["service"].get("schema") == 2
           else {}),
        "criterion_3": {"status": "not_assessed", "reason": notice},
    }


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FieldFlowError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise FieldFlowError(f"non-JSON numeric constant: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("field_data", help="schema-1, schema-2 or schema-3 field observation JSON path, or - for stdin")
    args = parser.parse_args(argv)
    try:
        source = sys.stdin.read() if args.field_data == "-" else Path(args.field_data).read_text(encoding="utf-8")
        data = json.loads(source, parse_float=Decimal, object_pairs_hook=_unique_pairs,
                          parse_constant=_invalid_constant)
        result = audit_field_flows(data)
    except (ValueError, RecursionError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": 1, "classification": CLASSIFICATION, "valid": False,
                          "error": str(exc)}, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
