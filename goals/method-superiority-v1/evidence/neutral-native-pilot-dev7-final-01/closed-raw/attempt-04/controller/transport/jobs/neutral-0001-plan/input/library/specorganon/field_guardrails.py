"""Fail-closed structural audit of declared prospective field-harm guardrails.

Run ``python scripts/audit_field_guardrails.py PLAN.json FIELD.json
REGISTRY.json MEASUREMENTS.json`` or call ``audit_field_guardrails(plan, field,
registry, measurements, *, plan_sha256, registry_sha256)``. Hash arguments are
SHA-256 of each object's canonical JSON: UTF-8, sorted keys, compact
separators, Unicode unescaped, and normalized exact decimal values within
1e-18 to 1e18 when nonzero. ``canonical_sha256`` computes this digest equally
for equivalent Python floats and JSON decimals. The auditor recomputes
both hashes, then requires ``registry.plan_sha256`` and
``measurements.registry_sha256`` to match. It first runs the existing trial
design preflight; passing here does not authorize execution.

The separate registry is a JSON object with exactly these fields::

  {"schema": 1, "classification": "field_guardrail_registry_unsealed",
   "study_id": "...", "plan_sha256": "64 lowercase hex digits",
   "registered_at_utc": "YYYY-MM-DDTHH:MM:SSZ", "approved_by": "declared name",
   "participation": [{"actor_id": "...", "stage": "..."}],
   "planned_group_actors": [{"group_id": "...", "actor_id": "..."}],
   "planned_stages": [{"group_id": "...", "period": "pre|post",
                       "stage": "..."}],
   "cells": [{"id": "...", "actor_id": "...", "stage": "...",
              "metric": "cost|time|water|emissions|burden|safety",
              "status": "measured", "unit": "...", "denominator": "...",
              "comparator": {"reference_arm": "control",
                             "target_arm": "intervention", "method": "..."},
              "window": {"periods": ["pre", "post"], "aggregation": "..."},
              "source_id": "...", "missing_rule": "...",
              "margin": {"direction": "...", "value": 0.0}}]}

A measured cell uses exactly one of ``margin`` or ``stop_condition`` (text).
An excluded cell instead has ``status: excluded``, ``reason``, ``approved_by``,
``approved_at_utc`` and ``approval_record_sha256``; it has no measurement row.
Every declared actor-stage participation needs exactly one cell per metric.

``measurements`` has ``schema: 1``, classification
``field_guardrail_measurements_unsealed``, matching ``study_id`` and
``registry_sha256``, and ``rows`` of::

  {"group_id": "...", "period": "pre|post", "cell_id": "...",
   "value": 0.0,
   "source": {"record_sha256": "64 lowercase hex digits", "locator": "...",
              "observed_at_utc": "YYYY-MM-DDTHH:MM:SSZ", "method": "..."}}

Exactly one row is required for each relevant group-period-measured-cell.
Relevance means the actor is in that group's declared ``actor_ids`` and the
stage appears in that group's declared lots during that period. Participation
is declared separately because the field graph does not bind lots to actors.
The registry must precede the start of the pre window. This conservative rule
does not evaluate a blinded ``baseline_release`` route. The registry must cover
every declared group-period actor and stage. Its prospective
``planned_group_actors`` and ``planned_stages`` sets must exactly match the
field group memberships and graph. This
does not establish the physically complete actor-stage population. Sources,
dates, numeric values, margins, approval names and record digests remain
self-declared. No substantive margin is supplied by this module, no effect is
estimated, and no approval is authenticated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from .field_flows import FieldFlowError, _array, _number, _object, _text, _utc
from .field_trial_design import FieldTrialDesignError, audit_field_trial_design


REGISTRY_CLASSIFICATION = "field_guardrail_registry_unsealed"
MEASUREMENTS_CLASSIFICATION = "field_guardrail_measurements_unsealed"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
METRICS = frozenset({"cost", "time", "water", "emissions", "burden", "safety"})
MAX_NUMBER = Decimal("1e18")
MIN_NONZERO_NUMBER = Decimal("1e-18")
MAX_NUMBER_DIGITS = 80
CELL_BASE = {"id", "actor_id", "stage", "metric", "status"}
MEASURED_FIELDS = {
    "unit", "denominator", "comparator", "window", "source_id", "missing_rule"
}
EXCLUDED_FIELDS = {"reason", "approved_by", "approved_at_utc", "approval_record_sha256"}
NOTICE = (
    "Only declared graph and registry structure matched. Actor-stage participation, "
    "source truth, registration, approvals, margins, measurements, safety and causal "
    "effects are not authenticated. Undeclared actors, branches and harms are not "
    "covered. A blinded baseline_release route is not evaluated here. External "
    "signatures and field validation are required before execution; "
    "criterion 3 is not assessed."
)


class FieldGuardrailError(ValueError):
    """A declared guardrail registry or measurement manifest failed structural audit."""


def _canonical_number(value: int | float | Decimal) -> str:
    if type(value) is int and abs(value) > 10**18:
        raise FieldGuardrailError("JSON number magnitude is outside supported range")
    try:
        number = Decimal(str(value))
    except (ValueError, ArithmeticError) as exc:
        raise FieldGuardrailError("JSON number is invalid") from exc
    if not number.is_finite():
        raise FieldGuardrailError("JSON number must be finite")
    if len(number.as_tuple().digits) > MAX_NUMBER_DIGITS:
        raise FieldGuardrailError("JSON number has too many decimal digits")
    if number == 0:
        return "0"
    magnitude = number.copy_abs()
    if magnitude > MAX_NUMBER or magnitude < MIN_NONZERO_NUMBER:
        raise FieldGuardrailError("JSON number magnitude is outside supported range")
    rendered = format(number, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _canonical_json(value: Any) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) in (int, float, Decimal):
        return _canonical_number(value)
    if type(value) is str:
        return json.dumps(value, ensure_ascii=False)
    if type(value) is list:
        return "[" + ",".join(_canonical_json(item) for item in value) + "]"
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise FieldGuardrailError("JSON object keys must be strings")
        return "{" + ",".join(
            f"{json.dumps(key, ensure_ascii=False)}:{_canonical_json(value[key])}"
            for key in sorted(value)
        ) + "}"
    raise FieldGuardrailError("input is not canonicalizable JSON")


def canonical_sha256(value: Any) -> str:
    """Digest the bounded, exact-decimal canonical JSON representation."""
    try:
        raw = _canonical_json(value).encode("utf-8")
    except (RecursionError, UnicodeError) as exc:
        raise FieldGuardrailError("input is not canonicalizable JSON") from exc
    return hashlib.sha256(raw).hexdigest()


def _digest(value: Any, label: str) -> str:
    if type(value) is not str or SHA256.fullmatch(value) is None:
        raise FieldGuardrailError(f"{label} must be lowercase SHA-256")
    return value


def _registry_cells(registry: dict[str, Any], field: dict[str, Any],
                    first_assignment: Any) -> tuple[dict[str, dict[str, Any]], set[tuple[str, str]]]:
    actors = {actor["id"] for actor in field["actors"]}
    graph_stages = {lot["stage"] for lot in field["lots"]}
    pairs: set[tuple[str, str]] = set()
    for index, raw in enumerate(_array(registry["participation"], "registry.participation")):
        label = f"registry.participation[{index}]"
        item = _object(raw, label, {"actor_id", "stage"})
        pair = (_text(item["actor_id"], f"{label}.actor_id"),
                _text(item["stage"], f"{label}.stage"))
        if pair[0] not in actors or pair[1] not in graph_stages:
            raise FieldGuardrailError(f"{label} names an actor or stage absent from the field graph")
        if pair in pairs:
            raise FieldGuardrailError(f"duplicate actor-stage participation: {pair}")
        pairs.add(pair)

    if type(registry["cells"]) is not list:
        raise FieldGuardrailError("registry.cells must be an array")
    cells: dict[str, dict[str, Any]] = {}
    metrics_by_pair: dict[tuple[str, str], set[str]] = defaultdict(set)
    registered_at = _utc(registry["registered_at_utc"], "registry.registered_at_utc")
    for index, raw in enumerate(registry["cells"]):
        label = f"registry.cells[{index}]"
        if type(raw) is not dict:
            raise FieldGuardrailError(f"{label} must be an object")
        status = raw.get("status")
        if status == "measured":
            item = _object(raw, label, CELL_BASE | MEASURED_FIELDS, {"margin", "stop_condition"})
            if ("margin" in item) == ("stop_condition" in item):
                raise FieldGuardrailError(f"{label} needs exactly one margin or stop_condition")
            for name in ("unit", "denominator", "source_id", "missing_rule"):
                _text(item[name], f"{label}.{name}")
            comparator = _object(item["comparator"], f"{label}.comparator",
                                 {"reference_arm", "target_arm", "method"})
            if (comparator["reference_arm"], comparator["target_arm"]) != (
                "control", "intervention"
            ):
                raise FieldGuardrailError(f"{label}.comparator must compare control with intervention")
            _text(comparator["method"], f"{label}.comparator.method")
            window = _object(item["window"], f"{label}.window", {"periods", "aggregation"})
            if (type(window["periods"]) is not list or len(window["periods"]) != 2
                    or any(type(period) is not str for period in window["periods"])
                    or set(window["periods"]) != {"pre", "post"}):
                raise FieldGuardrailError(f"{label}.window must cover pre and post")
            _text(window["aggregation"], f"{label}.window.aggregation")
            if "margin" in item:
                margin = _object(item["margin"], f"{label}.margin", {"direction", "value"})
                _text(margin["direction"], f"{label}.margin.direction")
                _number(margin["value"], f"{label}.margin.value", nonnegative=False)
            else:
                _text(item["stop_condition"], f"{label}.stop_condition")
        elif status == "excluded":
            item = _object(raw, label, CELL_BASE | EXCLUDED_FIELDS)
            for name in ("reason", "approved_by"):
                _text(item[name], f"{label}.{name}")
            approved_at = _utc(item["approved_at_utc"], f"{label}.approved_at_utc")
            if not registered_at <= approved_at < first_assignment:
                raise FieldGuardrailError(f"{label} exclusion approval must follow registration and predate assignment")
            _digest(item["approval_record_sha256"], f"{label}.approval_record_sha256")
        else:
            raise FieldGuardrailError(f"{label}.status must be measured or excluded")

        cell_id = _text(item["id"], f"{label}.id")
        pair = (_text(item["actor_id"], f"{label}.actor_id"),
                _text(item["stage"], f"{label}.stage"))
        metric = _text(item["metric"], f"{label}.metric")
        if metric not in METRICS or pair not in pairs:
            raise FieldGuardrailError(f"{label} names an unregistered pair or metric")
        if cell_id in cells:
            raise FieldGuardrailError(f"duplicate guardrail cell ID: {cell_id}")
        if metric in metrics_by_pair[pair]:
            raise FieldGuardrailError(f"duplicate guardrail metric for actor-stage: {pair}, {metric}")
        metrics_by_pair[pair].add(metric)
        cells[cell_id] = item
    for pair in sorted(pairs):
        if metrics_by_pair[pair] != METRICS:
            raise FieldGuardrailError(
                f"actor-stage {pair} lacks metric cells: {sorted(METRICS - metrics_by_pair[pair])}"
            )
    return cells, pairs


def audit_field_guardrails(
    plan: Any, field: Any, registry: Any, measurements: Any, *,
    plan_sha256: str, registry_sha256: str,
) -> dict[str, Any]:
    """Validate declarations and exact group-period-cell measurement presence."""
    try:
        design = audit_field_trial_design(plan, field)
        plan_digest = _digest(plan_sha256, "plan_sha256")
        registry_digest = _digest(registry_sha256, "registry_sha256")
        if plan_digest != canonical_sha256(plan):
            raise FieldGuardrailError("plan_sha256 differs from exact canonical plan JSON")
        if registry_digest != canonical_sha256(registry):
            raise FieldGuardrailError("registry_sha256 differs from exact canonical registry JSON")
        root = _object(registry, "registry", {
            "schema", "classification", "study_id", "plan_sha256", "registered_at_utc",
            "approved_by", "participation", "planned_group_actors",
            "planned_stages", "cells",
        })
        if type(root["schema"]) is not int or root["schema"] != 1:
            raise FieldGuardrailError("registry.schema must be 1")
        if root["classification"] != REGISTRY_CLASSIFICATION:
            raise FieldGuardrailError("registry.classification is not an unsealed guardrail registry")
        study_id = _text(root["study_id"], "registry.study_id")
        if study_id != design["study_id"]:
            raise FieldGuardrailError("registry and plan study_id differ")
        if _digest(root["plan_sha256"], "registry.plan_sha256") != plan_digest:
            raise FieldGuardrailError("registry plan_sha256 differs from exact plan hash")
        _text(root["approved_by"], "registry.approved_by")
        registered_at = _utc(root["registered_at_utc"], "registry.registered_at_utc")
        first_assignment = min(_utc(group["assigned_at_utc"], "field.groups.assigned_at_utc")
                               for group in field["groups"])
        if registered_at >= first_assignment:
            raise FieldGuardrailError("guardrail registration must predate first assignment")
        pre_start = next(_utc(period["start_utc"], "field.periods.pre.start_utc")
                         for period in field["periods"] if period["id"] == "pre")
        if registered_at >= pre_start:
            raise FieldGuardrailError("guardrail registration must predate start of pre window")

        cells, pairs = _registry_cells(root, field, first_assignment)
        groups = {group["id"]: set(group["actor_ids"]) for group in field["groups"]}
        declared_actors = {actor["id"] for actor in field["actors"]}
        planned_group_actors: set[tuple[str, str]] = set()
        for index, raw in enumerate(_array(root["planned_group_actors"],
                                           "registry.planned_group_actors")):
            label = f"registry.planned_group_actors[{index}]"
            actor_row = _object(raw, label, {"group_id", "actor_id"})
            key = (_text(actor_row["group_id"], f"{label}.group_id"),
                   _text(actor_row["actor_id"], f"{label}.actor_id"))
            if key[0] not in groups or key[1] not in declared_actors:
                raise FieldGuardrailError(f"{label} names an unknown group or actor")
            if key in planned_group_actors:
                raise FieldGuardrailError(f"duplicate planned group-actor: {key}")
            planned_group_actors.add(key)
        field_group_actors = {(group_id, actor_id)
                              for group_id, actor_ids in groups.items() for actor_id in actor_ids}
        if planned_group_actors != field_group_actors:
            raise FieldGuardrailError(
                "field group actors differ from registry planned_group_actors: "
                f"missing {sorted(planned_group_actors - field_group_actors)[:5]}, "
                f"unexpected {sorted(field_group_actors - planned_group_actors)[:5]}"
            )
        periods = {
            period["id"]: (
                _utc(period["start_utc"], "field.periods.start_utc"),
                _utc(period["end_utc"], "field.periods.end_utc"),
            ) for period in field["periods"]
        }
        gp_stages: dict[tuple[str, str], set[str]] = defaultdict(set)
        for lot in field["lots"]:
            gp_stages[(lot["group_id"], lot["period"])].add(lot["stage"])
        planned_stages: set[tuple[str, str, str]] = set()
        for index, raw in enumerate(_array(root["planned_stages"], "registry.planned_stages")):
            label = f"registry.planned_stages[{index}]"
            stage_row = _object(raw, label, {"group_id", "period", "stage"})
            key = tuple(_text(stage_row[name], f"{label}.{name}")
                        for name in ("group_id", "period", "stage"))
            if key[0] not in groups or key[1] not in periods:
                raise FieldGuardrailError(f"{label} names an unknown group or period")
            if key in planned_stages:
                raise FieldGuardrailError(f"duplicate planned group-period-stage: {key}")
            planned_stages.add(key)
        graph_stages = {(group_id, period, stage)
                        for (group_id, period), stages in gp_stages.items()
                        for stage in stages}
        if planned_stages != graph_stages:
            raise FieldGuardrailError(
                "field stages differ from registry planned_stages: "
                f"missing {sorted(planned_stages - graph_stages)[:5]}, "
                f"unexpected {sorted(graph_stages - planned_stages)[:5]}"
            )

        relevant: set[tuple[str, str, str]] = set()
        used_pairs: set[tuple[str, str]] = set()
        for group_id, actor_ids in groups.items():
            for period in periods:
                stages = gp_stages[(group_id, period)]
                active_pairs = {(actor, stage) for actor, stage in pairs
                                if actor in actor_ids and stage in stages}
                if {actor for actor, _ in active_pairs} != actor_ids:
                    raise FieldGuardrailError(f"registry misses declared actors in {group_id}/{period}")
                if {stage for _, stage in active_pairs} != stages:
                    raise FieldGuardrailError(f"registry misses declared stages in {group_id}/{period}")
                used_pairs.update(active_pairs)
                for cell_id, cell in cells.items():
                    if cell["status"] == "measured" and (
                        cell["actor_id"], cell["stage"]
                    ) in active_pairs:
                        relevant.add((group_id, period, cell_id))
        if used_pairs != pairs:
            raise FieldGuardrailError(f"registry has unused actor-stage participation: {sorted(pairs - used_pairs)}")

        manifest = _object(measurements, "measurements", {
            "schema", "classification", "study_id", "registry_sha256", "rows",
        })
        if type(manifest["schema"]) is not int or manifest["schema"] != 1:
            raise FieldGuardrailError("measurements.schema must be 1")
        if manifest["classification"] != MEASUREMENTS_CLASSIFICATION:
            raise FieldGuardrailError("measurements.classification is not an unsealed manifest")
        if _text(manifest["study_id"], "measurements.study_id") != study_id:
            raise FieldGuardrailError("measurements and plan study_id differ")
        if _digest(manifest["registry_sha256"], "measurements.registry_sha256") != registry_digest:
            raise FieldGuardrailError("measurements.registry_sha256 differs from exact registry hash")
        rows = _array(manifest["rows"], "measurements.rows", nonempty=False)
        seen: set[tuple[str, str, str]] = set()
        sources: set[tuple[str, str]] = set()
        for index, raw in enumerate(rows):
            label = f"measurements.rows[{index}]"
            row = _object(raw, label, {"group_id", "period", "cell_id", "value", "source"})
            key = (_text(row["group_id"], f"{label}.group_id"),
                   _text(row["period"], f"{label}.period"),
                   _text(row["cell_id"], f"{label}.cell_id"))
            if key not in relevant:
                raise FieldGuardrailError(f"{label} is not a relevant measured group-period-cell: {key}")
            if key in seen:
                raise FieldGuardrailError(f"duplicate group-period-cell measurement: {key}")
            seen.add(key)
            _number(row["value"], f"{label}.value", nonnegative=False)
            source = _object(row["source"], f"{label}.source",
                             {"record_sha256", "locator", "observed_at_utc", "method"})
            reference = (_digest(source["record_sha256"], f"{label}.source.record_sha256"),
                         _text(source["locator"], f"{label}.source.locator"))
            if reference in sources:
                raise FieldGuardrailError(f"measurement source reference reused: {reference}")
            sources.add(reference)
            _text(source["method"], f"{label}.source.method")
            observed_at = _utc(source["observed_at_utc"], f"{label}.source.observed_at_utc")
            start, end = periods[key[1]]
            if not start <= observed_at < end:
                raise FieldGuardrailError(f"{label}.source date falls outside its declared period")
        if seen != relevant:
            raise FieldGuardrailError(
                f"measurements missing {len(relevant - seen)} group-period-cell rows: "
                f"{sorted(relevant - seen)[:5]}"
            )
    except (FieldFlowError, FieldTrialDesignError) as exc:
        raise FieldGuardrailError(f"guardrail or design preflight failed: {exc}") from exc

    return {
        "schema": 1,
        "classification": "field_guardrail_preflight_declared_only",
        "study_id": study_id,
        "plan_sha256": plan_digest,
        "registry_sha256": registry_digest,
        "structural_match_at_read": True,
        "declared_participation_pairs": len(pairs),
        "planned_group_actors": len(planned_group_actors),
        "planned_group_period_stages": len(planned_stages),
        "metric_cells": len(cells),
        "measured_cells": sum(cell["status"] == "measured" for cell in cells.values()),
        "excluded_cells": sum(cell["status"] == "excluded" for cell in cells.values()),
        "group_period_cell_rows": len(seen),
        "measurement_source_references_unique": True,
        "actor_stage_participation_authenticated": False,
        "registration_authenticated": False,
        "approval_authenticated": False,
        "measurement_sources_authenticated": False,
        "execution_ready": False,
        "criterion_3": {"status": "not_assessed", "reason": NOTICE},
        "notice": NOTICE,
    }


def _unique_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FieldGuardrailError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _invalid_json_constant(value: str) -> None:
    raise FieldGuardrailError(f"non-finite JSON numeric constant: {value}")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"), parse_float=Decimal,
            parse_constant=_invalid_json_constant, object_pairs_hook=_unique_json_pairs,
        )
    except (OSError, UnicodeError, ValueError, RecursionError, ArithmeticError) as exc:
        raise FieldGuardrailError(f"invalid JSON in {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan", type=Path)
    parser.add_argument("field", type=Path)
    parser.add_argument("registry", type=Path)
    parser.add_argument("measurements", type=Path)
    args = parser.parse_args(argv)
    try:
        plan = _read_json(args.plan)
        field = _read_json(args.field)
        registry = _read_json(args.registry)
        measurements = _read_json(args.measurements)
        report = audit_field_guardrails(
            plan, field, registry, measurements,
            plan_sha256=canonical_sha256(plan),
            registry_sha256=canonical_sha256(registry),
        )
    except FieldGuardrailError as exc:
        print(f"Field guardrail preflight failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
