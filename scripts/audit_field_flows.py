"""Read-only, schema-1 preflight for declared food-chain field observations.

Usage: ``python scripts/audit_field_flows.py field.json`` (``-`` reads stdin).
The JSON object has ``schema: 1``, ``study_id``, ``balance_tolerance_kg``,
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
``observed_input_load_ids`` and ``observed_output_load_ids``. Each flow has
``id``, globally unique physical ``load_id``, ``group_id``, ``period``,
``from_lot_id`` and ``to_lot_id`` (one may be null), ``kind``, ``mass``,
``source``, ``destination`` and ``outcome``. External inputs use kind feed,
ingredient or water_addition. Outputs use product, coproduct, residue or
moisture. Internal transfers are a *single* flow referenced by both lots.
Moisture leaving the measured system must be an explicit moisture flow;
added water and ingredients must be explicit incoming flows. A terminal
output needs ``destination: {kind, source}`` and ``outcome: {status, mass,
source, safety: {status, source}, nutrition}``, including a second mass
measurement. Nonhuman destinations are animal_feed, compost, fuel, landfill,
wastewater, evaporation and industrial_use; their outcome status is
observed_other and nutrition is null. Human consumption needs
observed_consumed, ``safety.status: safe`` and ``nutrition: {status: useful,
source}``. Retail sale or an unknown outcome is not a terminal observation.
Nonterminal flows have null destination and outcome.
Observation times must follow input flow → lot operation → output flow →
terminal destination → observed outcome within the declared period.

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

This is a structural audit of supplied JSON. It cannot authenticate sources,
load identity, weighing calibration, safety tests, approval signatures,
representativeness, causal assignment, actor coverage, equivalence content,
or field impact. ``stage`` is free text: a passing graph may omit production,
storage, transport or successive transformations. Full production-to-consumption
scope and observed household coverage require an external audit. Its worst-case
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
    "Valid means only that the declared graph is internally consistent; required "
    "stages and full production-to-consumption scope are not checked. Declared "
    "JSON only: physical identity, source truth, calibration, safety, "
    "nutrition, independent approval, causal design and observed impact are not "
    "authenticated. No V or G is calculated; criterion 3 is not assessed."
)
MASS_FACTORS = {"kg": Fraction(1), "g": Fraction(1, 1000), "t": Fraction(1000)}
MAX_ABS_NUMBER = Decimal("1e18")
MIN_ABS_NONZERO = Decimal("1e-18")
MAX_DECIMAL_DIGITS = 80
INPUT_KINDS = {"feed", "ingredient", "water_addition"}
OUTPUT_KINDS = {"product", "coproduct", "residue", "moisture"}
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
                          flow_at: datetime) -> tuple[str | None, datetime | None]:
    terminal = flow["to_lot_id"] is None
    destination = flow["destination"]
    outcome = flow["outcome"]
    if not terminal:
        if destination is not None or outcome is not None:
            raise FieldFlowError(f"{label} internal or input flow cannot have terminal destination/outcome")
        return None, None
    dest = _object(destination, f"{label}.destination", {"kind", "source"})
    kind = _choice(dest["kind"], f"{label}.destination.kind", NONHUMAN_DESTINATIONS | {"human_consumption"})
    destination_at = _period_evidence(dest["source"], f"{label}.destination.source", interval)
    observed = _object(outcome, f"{label}.outcome", {"status", "mass", "source", "safety", "nutrition"})
    status = _choice(observed["status"], f"{label}.outcome.status", {"observed_consumed", "observed_other"})
    observed_mass = _mass(observed["mass"], f"{label}.outcome.mass")
    outcome_at = _period_evidence(observed["source"], f"{label}.outcome.source", interval)
    if not flow_at <= destination_at <= outcome_at:
        raise FieldFlowError(f"{label} terminal chronology must be flow <= destination <= outcome")
    if abs(mass[0] - observed_mass[0]) > mass[1] + observed_mass[1]:
        raise FieldFlowError(f"{label} terminal mass differs from observed destination mass beyond uncertainty")
    safety = _object(observed["safety"], f"{label}.outcome.safety", {"status", "source"})
    safety_status = _choice(safety["status"], f"{label}.outcome.safety.status", {"safe", "unsafe", "not_assessed"})
    _period_evidence(safety["source"], f"{label}.outcome.safety.source", interval)
    if kind == "human_consumption":
        if status != "observed_consumed" or safety_status != "safe":
            raise FieldFlowError(f"{label} human consumption requires observed ingestion and safe evidence")
        nutrition = _object(observed["nutrition"], f"{label}.outcome.nutrition", {"status", "source"})
        if nutrition["status"] != "useful":
            raise FieldFlowError(f"{label} human consumption requires useful nutrition evidence")
        _period_evidence(nutrition["source"], f"{label}.outcome.nutrition.source", interval)
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
                      consumed_outcome_at: dict[str, datetime]) -> str:
    if service is None:
        return "not_assessed_no_declared_equivalence"
    row = _object(service, "service", {"equivalence", "rows"})
    eq = _object(row["equivalence"], "service.equivalence", {
        "id", "service_unit", "approved_at_utc", "approved_by_actor_ids",
        "verified_by", "record_sha256", "source",
    })
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
    _evidence(eq["source"], "service.equivalence.source")
    if any(approved_at >= group["assigned_at"] for group in groups.values()):
        raise FieldFlowError("service equivalence approval must predate every group assignment")
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(_array(row["rows"], "service.rows")):
        label = f"service.rows[{index}]"
        item = _object(raw, label, {
            "group_id", "period", "consumption_flow_ids", "consumed_service",
            "feasible_max_service", "source",
        })
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
        for field in ("consumed_service", "feasible_max_service"):
            measure = _object(item[field], f"{label}.{field}", {"value", "unit", "uncertainty"})
            if measure["unit"] != unit:
                raise FieldFlowError(f"{label}.{field}.unit differs from approved service unit")
            quantities.append(_number(measure["value"], f"{label}.{field}.value",
                                      positive=field == "feasible_max_service"))
            _number(measure["uncertainty"], f"{label}.{field}.uncertainty")
        if quantities[0] > quantities[1]:
            raise FieldFlowError(f"{label} observed service exceeds feasible maximum (V > 1)")
        if not flow_ids and quantities[0] != 0:
            raise FieldFlowError(f"{label} positive consumed service has no observed consumption flow")
        row_at = _period_evidence(item["source"], f"{label}.source", period_times[key[1]])
        if any(row_at < consumed_outcome_at[flow_id] for flow_id in flow_ids):
            raise FieldFlowError(f"{label} service observation predates a covered consumption outcome")
    expected = {(group, period) for group in groups for period in periods}
    if seen != expected:
        raise FieldFlowError(f"service.rows missing group-period combinations: {sorted(expected - seen)}")
    return "declared_service_inputs_bounded_approval_unverified"


def audit_field_flows(data: Any) -> dict[str, Any]:
    """Validate declarations and return a structural report, never an impact estimate."""
    root = _object(data, "field data", {
        "schema", "study_id", "balance_tolerance_kg", "tolerance_source", "currency",
        "actors", "groups", "periods", "lots", "flows", "burdens",
    }, {"service"})
    if type(root["schema"]) is not int or root["schema"] != 1:
        raise FieldFlowError("schema must be integer 1")
    study_id = _text(root["study_id"], "study_id")
    tolerance = Fraction(_number(root["balance_tolerance_kg"], "balance_tolerance_kg"))
    _evidence(root["tolerance_source"], "tolerance_source")
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
        })
        lot_id = _unique_id(item["id"], f"{label}.id", ids)
        group_id = _text(item["group_id"], f"{label}.group_id")
        period = _text(item["period"], f"{label}.period")
        if group_id not in groups or period not in periods:
            raise FieldFlowError(f"{label} references unknown group or period")
        _text(item["stage"], f"{label}.stage")
        lot_at = _period_evidence(item["source"], f"{label}.source", period_times[period])
        inputs = _ids(item["input_flow_ids"], f"{label}.input_flow_ids")
        outputs = _ids(item["output_flow_ids"], f"{label}.output_flow_ids")
        if set(inputs) & set(outputs):
            raise FieldFlowError(f"{label} counts a flow as both input and output")
        lots[lot_id] = {
            "group_id": group_id, "period": period, "inputs": set(inputs), "outputs": set(outputs),
            "input_loads": set(_ids(item["observed_input_load_ids"], f"{label}.observed_input_load_ids")),
            "output_loads": set(_ids(item["observed_output_load_ids"], f"{label}.observed_output_load_ids")),
            "observed_at": lot_at,
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
        })
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
            roots[key] += 1
        elif kind not in OUTPUT_KINDS:
            raise FieldFlowError(f"{label} output or transfer must be product, coproduct, residue or moisture")
        if source_lot is not None and target_lot is not None and kind == "moisture":
            raise FieldFlowError(f"{label} moisture loss must have an observed terminal destination")
        mass = _mass(item["mass"], f"{label}.mass")
        flow_at = _period_evidence(item["source"], f"{label}.source", period_times[period])
        destination_kind, outcome_at = _validate_destination(item, label, mass,
                                                             period_times[period], flow_at)
        if target_lot is None:
            terminals[key] += 1
        if destination_kind == "human_consumption":
            consumed[key].add(flow_id)
            if outcome_at is None:
                raise FieldFlowError(f"{label} lacks observed consumption time")
            consumed_outcome_at[flow_id] = outcome_at
        flows[flow_id] = {"from": source_lot, "to": target_lot, "kind": kind,
                          "mass": mass, "group_id": group_id, "period": period,
                          "observed_at": flow_at, "outcome_at": outcome_at}
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
    while queue:
        parent = queue.popleft()
        visited += 1
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
    service_status = _validate_service(root.get("service"), groups, periods, actors, consumed,
                                       period_times, consumed_outcome_at)
    return {
        "schema": 1, "classification": CLASSIFICATION, "valid": True,
        "study_id": study_id, "notice": NOTICE,
        "counts": {"groups": len(groups), "lots": len(lots), "flows": len(flows),
                   "terminal_flows": sum(terminals.values()),
                   "consumed_flows": sum(map(len, consumed.values())), "burden_rows": len(burden_keys)},
        "balances": sorted(balances, key=lambda item: item["lot_id"]),
        "scope_status": "declared_graph_only_full_chain_not_checked",
        "service_status": service_status,
        "criterion_3": {"status": "not_assessed", "reason": NOTICE},
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
    parser.add_argument("field_data", help="schema-1 field observation JSON path, or - for stdin")
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
