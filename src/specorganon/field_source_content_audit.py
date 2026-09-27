"""Compare declared field facts with caller-opened primary source extracts.

This pure audit is intended to run after field guardrails and source digest
coverage have passed. Each source_record or approval_record byte string is a
UTF-8 JSON object with exactly ``schema``, ``classification`` and ``records``.
Schema 1 classifies it as ``field_primary_source_content_extract``. A record
array may contain one or several typed records, but every declared reference
must find exactly one record under the expected role and file SHA-256. The
format is deliberately a constrained extract, not an arbitrary field document.
Opt-in ``field.service.schema: 2`` also requires one ``service_row`` record per
declared row under its ``source_record`` digest. The extract omits that digest
from the row's ``source`` to avoid a self-referential file hash.
Opt-in ``analysis.schema: 2`` likewise requires one ``volume_row`` record per
baseline input-volume manifest row, with the source digest omitted from the
extract record.

Matching these extracts does not authenticate their truth, custody, the
authority of an approver, or real-world impact.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any


CLASSIFICATION = "field_primary_source_content_extract"
REPORT_CLASSIFICATION = "field_primary_source_content_match_declared_only"
PRIMARY_ROLES = frozenset({"source_record", "approval_record"})
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
UTC_FRACTION = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 256 * 1024 * 1024
MAX_SOURCE_COUNT = 2048
MAX_RECORDS_PER_SOURCE = 100_000
MAX_TOTAL_RECORDS = 1_000_000
MAX_EXAMPLES = 5
MAX_NUMBER = Decimal("1e18")
MIN_NONZERO_NUMBER = Decimal("1e-18")
MAX_NUMBER_DIGITS = 80
SOURCE_FIELDS = {"source_id", "locator", "observed_at_utc", "method"}
VOLUME_SOURCE_FIELDS = {"locator", "observed_at_utc", "method"}
VOLUME_ROW_FIELDS = {
    "group_id", "period", "value", "unit", "window_start_utc", "window_end_utc", "source",
}
VOLUME_RECORD_FIELDS = VOLUME_ROW_FIELDS | {"kind", "study_id", "definition_sha256"}
VOLUME_MANIFEST_FIELDS = {
    "schema", "classification", "study_id", "plan_sha256", "candidate_spec_sha256",
    "unit", "definition_sha256", "rows",
}
NOTICE = (
    "Only declared facts in caller-opened, digest-checked JSON extracts were "
    "compared. Source truth, physical custody, approval authority, population "
    "coverage, causal attribution and field impact are not authenticated; "
    "criterion 3 is not assessed."
)


class FieldSourceContentAuditError(ValueError):
    """A declared reference or source extract violates the supported schema."""


def _object(value: Any, label: str, keys: set[str] | None = None) -> dict[str, Any]:
    if type(value) is not dict or (keys is not None and set(value) != keys):
        detail = "an object" if keys is None else f"an object with exactly {sorted(keys)}"
        raise FieldSourceContentAuditError(f"{label} must be {detail}")
    return value


def _array(value: Any, label: str, *, nonempty: bool = False) -> list[Any]:
    if type(value) is not list or (nonempty and not value):
        raise FieldSourceContentAuditError(f"{label} must be an array" + (
            " with at least one item" if nonempty else ""
        ))
    return value


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise FieldSourceContentAuditError(f"{label} must be nonempty trimmed text")
    return value


def _utc(value: Any, label: str, *, allow_fraction: bool = False) -> str:
    _text(value, label)
    pattern = UTC_FRACTION if allow_fraction else UTC
    if pattern.fullmatch(value) is None:
        raise FieldSourceContentAuditError(f"{label} must be a UTC timestamp ending in Z")
    try:
        from datetime import datetime

        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FieldSourceContentAuditError(f"{label} is not a valid UTC timestamp") from exc
    return value


def _digest(value: Any, label: str) -> str:
    if type(value) is not str or SHA256.fullmatch(value) is None:
        raise FieldSourceContentAuditError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _number(value: Any, label: str) -> Decimal:
    if type(value) not in (int, float, Decimal):
        raise FieldSourceContentAuditError(f"{label} must be a finite bounded JSON number")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise FieldSourceContentAuditError(f"{label} must be a finite bounded JSON number") from exc
    if not number.is_finite() or len(number.as_tuple().digits) > MAX_NUMBER_DIGITS:
        raise FieldSourceContentAuditError(f"{label} must be a finite bounded JSON number")
    if number and not MIN_NONZERO_NUMBER <= abs(number) <= MAX_NUMBER:
        raise FieldSourceContentAuditError(f"{label} is outside the supported numeric range")
    return number


def _ids(value: Any, label: str) -> list[str]:
    items = [_text(item, f"{label}[{index}]")
             for index, item in enumerate(_array(value, label, nonempty=True))]
    if len(items) != len(set(items)):
        raise FieldSourceContentAuditError(f"{label} repeats an ID")
    return sorted(items)


def _source(value: Any, label: str, *, allow_fraction: bool = False) -> dict[str, str]:
    item = _object(value, label, SOURCE_FIELDS)
    return {
        "source_id": _text(item["source_id"], f"{label}.source_id"),
        "locator": _text(item["locator"], f"{label}.locator"),
        "observed_at_utc": _utc(item["observed_at_utc"], f"{label}.observed_at_utc",
                                allow_fraction=allow_fraction),
        "method": _text(item["method"], f"{label}.method"),
    }


def _volume_source(value: Any, label: str) -> dict[str, str]:
    item = _object(value, label, VOLUME_SOURCE_FIELDS)
    return {
        "locator": _text(item["locator"], f"{label}.locator"),
        "observed_at_utc": _utc(item["observed_at_utc"], f"{label}.observed_at_utc",
                                allow_fraction=True),
        "method": _text(item["method"], f"{label}.method"),
    }


def _service_quantity(value: Any, label: str) -> dict[str, Any]:
    item = _object(value, label, {"value", "unit", "uncertainty"})
    return {
        "value": _number(item["value"], f"{label}.value"),
        "unit": _text(item["unit"], f"{label}.unit"),
        "uncertainty": _number(item["uncertainty"], f"{label}.uncertainty"),
    }


def _service_flow_ids(value: Any, label: str) -> list[str]:
    ids = [_text(item, f"{label}[{index}]")
           for index, item in enumerate(_array(value, label))]
    if len(ids) != len(set(ids)):
        raise FieldSourceContentAuditError(f"{label} repeats an ID")
    return sorted(ids)


def _normalize_record(
    value: Any, label: str, *, allow_volume: bool = False,
) -> tuple[str, str, dict[str, Any]]:
    item = _object(value, label)
    kind = _text(item.get("kind"), f"{label}.kind")
    if kind == "measurement":
        _object(item, label, {
            "kind", "locator", "group_id", "period", "cell_id", "value",
            "observed_at_utc", "method", "unit", "denominator", "source_id",
        })
        identifier = _text(item["locator"], f"{label}.locator")
        normalized = {
            "kind": kind, "locator": identifier,
            "group_id": _text(item["group_id"], f"{label}.group_id"),
            "period": _text(item["period"], f"{label}.period"),
            "cell_id": _text(item["cell_id"], f"{label}.cell_id"),
            "value": _number(item["value"], f"{label}.value"),
            "observed_at_utc": _utc(item["observed_at_utc"], f"{label}.observed_at_utc"),
            "method": _text(item["method"], f"{label}.method"),
            "unit": _text(item["unit"], f"{label}.unit"),
            "denominator": _text(item["denominator"], f"{label}.denominator"),
            "source_id": _text(item["source_id"], f"{label}.source_id"),
        }
    elif kind == "volume_row" and allow_volume:
        _object(item, label, VOLUME_RECORD_FIELDS)
        source = _volume_source(item["source"], f"{label}.source")
        identifier = source["locator"]
        normalized = {
            "kind": kind,
            "study_id": _text(item["study_id"], f"{label}.study_id"),
            "definition_sha256": _digest(item["definition_sha256"],
                                         f"{label}.definition_sha256"),
            "group_id": _text(item["group_id"], f"{label}.group_id"),
            "period": _text(item["period"], f"{label}.period"),
            "value": _number(item["value"], f"{label}.value"),
            "unit": _text(item["unit"], f"{label}.unit"),
            "window_start_utc": _utc(item["window_start_utc"],
                                     f"{label}.window_start_utc", allow_fraction=True),
            "window_end_utc": _utc(item["window_end_utc"],
                                   f"{label}.window_end_utc", allow_fraction=True),
            "source": source,
        }
    elif kind == "service_row":
        _object(item, label, {
            "kind", "group_id", "period", "consumption_flow_ids", "consumed_service",
            "feasible_max_service", "source", "equivalence_id",
        })
        source = _source(item["source"], f"{label}.source", allow_fraction=True)
        identifier = source["locator"]
        normalized = {
            "kind": kind,
            "group_id": _text(item["group_id"], f"{label}.group_id"),
            "period": _text(item["period"], f"{label}.period"),
            "consumption_flow_ids": _service_flow_ids(item["consumption_flow_ids"],
                                                      f"{label}.consumption_flow_ids"),
            "consumed_service": _service_quantity(item["consumed_service"],
                                                   f"{label}.consumed_service"),
            "feasible_max_service": _service_quantity(item["feasible_max_service"],
                                                       f"{label}.feasible_max_service"),
            "source": source,
            "equivalence_id": _text(item["equivalence_id"], f"{label}.equivalence_id"),
        }
    elif kind == "allocation":
        _object(item, label, {"kind", "study_id", "allocation_method", "groups"})
        identifier = _text(item["study_id"], f"{label}.study_id")
        groups: dict[str, dict[str, Any]] = {}
        for index, raw_group in enumerate(_array(item["groups"], f"{label}.groups", nonempty=True)):
            group_label = f"{label}.groups[{index}]"
            group = _object(raw_group, group_label, {
                "id", "arm", "stratum", "assigned_at_utc", "actor_ids", "source",
            })
            group_id = _text(group["id"], f"{group_label}.id")
            if group_id in groups:
                raise FieldSourceContentAuditError(f"{label}.groups repeats an ID")
            groups[group_id] = {
                "id": group_id,
                "arm": _text(group["arm"], f"{group_label}.arm"),
                "stratum": _text(group["stratum"], f"{group_label}.stratum"),
                "assigned_at_utc": _utc(group["assigned_at_utc"],
                                        f"{group_label}.assigned_at_utc"),
                "actor_ids": _ids(group["actor_ids"], f"{group_label}.actor_ids"),
                "source": _source(group["source"], f"{group_label}.source"),
            }
        normalized = {
            "kind": kind, "study_id": identifier,
            "allocation_method": _text(item["allocation_method"], f"{label}.allocation_method"),
            "groups": [groups[group_id] for group_id in sorted(groups)],
        }
    elif kind == "baseline_release":
        _object(item, label, {"kind", "study_id", "first_access_at_utc", "custodian_id"})
        identifier = _text(item["study_id"], f"{label}.study_id")
        normalized = {
            "kind": kind, "study_id": identifier,
            "first_access_at_utc": _utc(item["first_access_at_utc"],
                                        f"{label}.first_access_at_utc"),
            "custodian_id": _text(item["custodian_id"], f"{label}.custodian_id"),
        }
    elif kind == "equivalence":
        _object(item, label, {
            "kind", "id", "service_unit", "approved_at_utc", "approved_by_actor_ids",
            "verified_by", "source",
        })
        identifier = _text(item["id"], f"{label}.id")
        normalized = {
            "kind": kind, "id": identifier,
            "service_unit": _text(item["service_unit"], f"{label}.service_unit"),
            "approved_at_utc": _utc(item["approved_at_utc"], f"{label}.approved_at_utc"),
            "approved_by_actor_ids": _ids(item["approved_by_actor_ids"],
                                          f"{label}.approved_by_actor_ids"),
            "verified_by": _text(item["verified_by"], f"{label}.verified_by"),
            "source": _source(item["source"], f"{label}.source"),
        }
    elif kind == "excluded_cell":
        _object(item, label, {
            "kind", "cell_id", "actor_id", "stage", "metric", "reason",
            "approved_by", "approved_at_utc",
        })
        identifier = _text(item["cell_id"], f"{label}.cell_id")
        normalized = {
            "kind": kind, "cell_id": identifier,
            "actor_id": _text(item["actor_id"], f"{label}.actor_id"),
            "stage": _text(item["stage"], f"{label}.stage"),
            "metric": _text(item["metric"], f"{label}.metric"),
            "reason": _text(item["reason"], f"{label}.reason"),
            "approved_by": _text(item["approved_by"], f"{label}.approved_by"),
            "approved_at_utc": _utc(item["approved_at_utc"], f"{label}.approved_at_utc"),
        }
    else:
        raise FieldSourceContentAuditError(f"{label}.kind is unsupported")
    return kind, identifier, normalized


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FieldSourceContentAuditError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise FieldSourceContentAuditError(f"invalid JSON numeric constant: {value}")


def _extract(raw: bytes, label: str) -> list[Any]:
    if len(raw) > MAX_SOURCE_BYTES:
        raise FieldSourceContentAuditError(f"{label} exceeds the supported byte limit")
    try:
        value = json.loads(raw.decode("utf-8"), parse_float=Decimal,
                           parse_constant=_reject_constant, object_pairs_hook=_json_pairs)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise FieldSourceContentAuditError(f"{label} is invalid UTF-8 JSON: {exc}") from exc
    root = _object(value, label, {"schema", "classification", "records"})
    if type(root["schema"]) is not int or root["schema"] != 1:
        raise FieldSourceContentAuditError(f"{label}.schema must be 1")
    if root["classification"] != CLASSIFICATION:
        raise FieldSourceContentAuditError(f"{label}.classification is unsupported")
    records = _array(root["records"], f"{label}.records", nonempty=True)
    if len(records) > MAX_RECORDS_PER_SOURCE:
        raise FieldSourceContentAuditError(f"{label}.records exceeds the supported count")
    return records


def _volume_manifest(analysis: Any) -> dict[str, Any] | None:
    if analysis is None:
        return None
    root = _object(analysis, "analysis")
    schema = root.get("schema")
    if type(schema) is not int or schema not in (1, 2):
        raise FieldSourceContentAuditError("analysis.schema must be integer 1 or 2")
    if schema == 1:
        return None
    manifest = _object(root.get("baseline_input_volume_manifest"),
                       "analysis.baseline_input_volume_manifest", VOLUME_MANIFEST_FIELDS)
    if type(manifest["schema"]) is not int or manifest["schema"] != 1:
        raise FieldSourceContentAuditError("baseline_input_volume_manifest.schema must be 1")
    if manifest["classification"] != "field_baseline_input_volume_manifest_unsealed":
        raise FieldSourceContentAuditError(
            "baseline_input_volume_manifest.classification is unsupported"
        )
    _digest(manifest["plan_sha256"], "baseline_input_volume_manifest.plan_sha256")
    _digest(manifest["candidate_spec_sha256"],
            "baseline_input_volume_manifest.candidate_spec_sha256")
    _text(manifest["unit"], "baseline_input_volume_manifest.unit")
    _digest(manifest["definition_sha256"], "baseline_input_volume_manifest.definition_sha256")
    _array(manifest["rows"], "baseline_input_volume_manifest.rows", nonempty=True)
    return manifest


def _declared_records(
    plan: dict[str, Any], field: dict[str, Any], registry: dict[str, Any],
    measurements: dict[str, Any], volume_manifest: dict[str, Any] | None = None,
) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    expected: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    def add(role: str, digest: Any, record: dict[str, Any], label: str) -> None:
        digest = _digest(digest, f"{label}.record_sha256")
        kind, identifier, normalized = _normalize_record(
            record, label, allow_volume=volume_manifest is not None,
        )
        key = role, digest, kind, identifier
        if key in expected:
            raise FieldSourceContentAuditError(f"{label} repeats a declared source reference")
        expected[key] = normalized

    study_id = _text(plan.get("study_id"), "plan.study_id")
    if _text(field.get("study_id"), "field.study_id") != study_id:
        raise FieldSourceContentAuditError("plan and field study_id differ")
    field_groups: dict[str, dict[str, Any]] = {}
    for index, raw_group in enumerate(_array(field.get("groups"), "field.groups", nonempty=True)):
        label = f"field.groups[{index}]"
        group = _object(raw_group, label)
        group_id = _text(group.get("id"), f"{label}.id")
        if group_id in field_groups:
            raise FieldSourceContentAuditError(f"{label}.id repeats a field group ID")
        field_groups[group_id] = group
    plan_groups = _array(plan.get("groups"), "plan.groups", nonempty=True)
    groups = []
    plan_group_ids: set[str] = set()
    for index, group in enumerate(plan_groups):
        label = f"plan.groups[{index}]"
        item = _object(group, label)
        group_id = _text(item.get("id"), f"{label}.id")
        if group_id in plan_group_ids:
            raise FieldSourceContentAuditError(f"{label}.id repeats a plan group ID")
        plan_group_ids.add(group_id)
        observed = _object(field_groups.get(group_id), f"field.groups[{group_id}]")
        if item.get("arm") != observed.get("arm") or item.get("stratum") != observed.get("stratum"):
            raise FieldSourceContentAuditError(f"{label} arm or stratum differs from field group")
        groups.append({
            "id": group_id,
            "arm": item.get("arm"), "stratum": item.get("stratum"),
            "assigned_at_utc": observed.get("assigned_at_utc"),
            "actor_ids": observed.get("actor_ids"), "source": observed.get("source"),
        })
    if plan_group_ids != set(field_groups):
        raise FieldSourceContentAuditError("plan and field group IDs differ")

    if volume_manifest is not None:
        volume_study_id = _text(volume_manifest["study_id"],
                                "baseline_input_volume_manifest.study_id")
        if volume_study_id != study_id:
            raise FieldSourceContentAuditError("volume manifest study_id differs from plan")
        for index, raw_row in enumerate(volume_manifest["rows"]):
            label = f"baseline_input_volume_manifest.rows[{index}]"
            row = _object(raw_row, label, VOLUME_ROW_FIELDS)
            source = _object(row["source"], f"{label}.source",
                             VOLUME_SOURCE_FIELDS | {"record_sha256"})
            if row["unit"] != volume_manifest["unit"]:
                raise FieldSourceContentAuditError(f"{label}.unit differs from volume manifest")
            add("source_record", source["record_sha256"], {
                "kind": "volume_row",
                "study_id": volume_study_id,
                "definition_sha256": volume_manifest["definition_sha256"],
                **{key: row[key] for key in VOLUME_ROW_FIELDS if key != "source"},
                "source": {key: source[key] for key in VOLUME_SOURCE_FIELDS},
            }, label)

    add("source_record", plan.get("allocation_record_sha256"), {
        "kind": "allocation", "study_id": study_id,
        "allocation_method": plan.get("allocation_method"), "groups": groups,
    }, "plan.allocation")
    if "baseline_release" in plan:
        release = _object(plan["baseline_release"], "plan.baseline_release")
        add("source_record", release.get("record_sha256"), {
            "kind": "baseline_release", "study_id": study_id,
            "first_access_at_utc": release.get("first_access_at_utc"),
            "custodian_id": release.get("custodian_id"),
        }, "plan.baseline_release")

    service = field.get("service")
    if service is not None:
        service = _object(service, "field.service")
        service_schema = service.get("schema")
        if "schema" in service and (type(service_schema) is not int or service_schema != 2):
            raise FieldSourceContentAuditError("field.service.schema must be integer 2 when present")
        equivalence = _object(service.get("equivalence"), "field.service.equivalence")
        add("approval_record", equivalence.get("record_sha256"), {
            "kind": "equivalence", "id": equivalence.get("id"),
            "service_unit": equivalence.get("service_unit"),
            "approved_at_utc": equivalence.get("approved_at_utc"),
            "approved_by_actor_ids": equivalence.get("approved_by_actor_ids"),
            "verified_by": equivalence.get("verified_by"),
            "source": equivalence.get("source"),
        }, "field.service.equivalence")
        if service_schema == 2:
            for index, raw_row in enumerate(_array(service.get("rows"), "field.service.rows",
                                                  nonempty=True)):
                label = f"field.service.rows[{index}]"
                row = _object(raw_row, label)
                source = _object(row.get("source"), f"{label}.source",
                                 SOURCE_FIELDS | {"record_sha256"})
                add("source_record", source["record_sha256"], {
                    "kind": "service_row",
                    "group_id": row.get("group_id"),
                    "period": row.get("period"),
                    "consumption_flow_ids": row.get("consumption_flow_ids"),
                    "consumed_service": row.get("consumed_service"),
                    "feasible_max_service": row.get("feasible_max_service"),
                    "equivalence_id": equivalence.get("id"),
                    "source": {key: source[key] for key in SOURCE_FIELDS},
                }, label)

    cells: dict[str, dict[str, Any]] = {}
    for index, raw_cell in enumerate(_array(registry.get("cells"), "registry.cells")):
        label = f"registry.cells[{index}]"
        cell = _object(raw_cell, label)
        cell_id = _text(cell.get("id"), f"{label}.id")
        if cell_id in cells:
            raise FieldSourceContentAuditError(f"{label}.id repeats a registry cell ID")
        cells[cell_id] = cell
        if cell.get("status") == "excluded":
            add("approval_record", cell.get("approval_record_sha256"), {
                "kind": "excluded_cell", "cell_id": cell_id,
                "actor_id": cell.get("actor_id"), "stage": cell.get("stage"),
                "metric": cell.get("metric"), "reason": cell.get("reason"),
                "approved_by": cell.get("approved_by"),
                "approved_at_utc": cell.get("approved_at_utc"),
            }, label)
        elif cell.get("status") != "measured":
            raise FieldSourceContentAuditError(f"{label}.status is unsupported")

    for index, raw_row in enumerate(_array(measurements.get("rows"), "measurements.rows")):
        label = f"measurements.rows[{index}]"
        row = _object(raw_row, label)
        source = _object(row.get("source"), f"{label}.source")
        cell_id = _text(row.get("cell_id"), f"{label}.cell_id")
        cell = _object(cells.get(cell_id), f"registry.cells[{cell_id}]")
        if cell.get("status") != "measured":
            raise FieldSourceContentAuditError(f"{label} references an excluded cell")
        add("source_record", source.get("record_sha256"), {
            "kind": "measurement", "locator": source.get("locator"),
            "group_id": row.get("group_id"), "period": row.get("period"),
            "cell_id": cell_id, "value": row.get("value"),
            "observed_at_utc": source.get("observed_at_utc"),
            "method": source.get("method"), "unit": cell.get("unit"),
            "denominator": cell.get("denominator"), "source_id": cell.get("source_id"),
        }, label)
    return expected


def audit_field_source_content(
    plan: dict[str, Any], field: dict[str, Any], registry: dict[str, Any],
    measurements: dict[str, Any], opened_sources: list[dict[str, Any]],
    *, analysis: Any = None,
) -> dict[str, Any]:
    """Check each declared primary reference against one JSON extract record.

    ``opened_sources`` contains ``{role, sha256, raw}`` entries from the caller's
    already byte-verified source manifest. Raw must be ``bytes``. Malformed
    extract files are reported as a failed match; malformed declarations raise
    ``FieldSourceContentAuditError``. Optional schema-2 ``analysis`` binds every
    baseline input-volume row to a typed extract. No file is opened here.
    """
    volume_manifest = _volume_manifest(analysis)
    expected = _declared_records(
        _object(plan, "plan"), _object(field, "field"),
        _object(registry, "registry"), _object(measurements, "measurements"),
        volume_manifest,
    )
    opened = _array(opened_sources, "opened_sources")
    if len(opened) > MAX_SOURCE_COUNT:
        raise FieldSourceContentAuditError("opened_sources exceeds the supported count")
    total_bytes = 0
    actual: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    seen_files: set[tuple[str, str]] = set()
    problems: list[str] = []
    duplicate_records = 0
    duplicate_files = 0
    malformed_files = 0
    total_records = 0
    for index, raw_entry in enumerate(opened):
        label = f"opened_sources[{index}]"
        entry = _object(raw_entry, label, {"role", "sha256", "raw"})
        role = entry["role"]
        if type(role) is not str or role not in PRIMARY_ROLES:
            raise FieldSourceContentAuditError(f"{label}.role must be a primary role")
        digest = _digest(entry["sha256"], f"{label}.sha256")
        raw = entry["raw"]
        if type(raw) is not bytes:
            raise FieldSourceContentAuditError(f"{label}.raw must be bytes")
        total_bytes += len(raw)
        if total_bytes > MAX_TOTAL_SOURCE_BYTES:
            raise FieldSourceContentAuditError("opened_sources exceeds the supported total byte limit")
        file_key = role, digest
        if file_key in seen_files:
            duplicate_files += 1
            problems.append(f"{label} repeats an opened role and digest")
            continue
        seen_files.add(file_key)
        if hashlib.sha256(raw).hexdigest() != digest:
            malformed_files += 1
            problems.append(f"{label}.raw differs from its SHA-256")
            continue
        try:
            records = _extract(raw, label)
        except FieldSourceContentAuditError as exc:
            malformed_files += 1
            problems.append(str(exc))
            continue
        total_records += len(records)
        if total_records > MAX_TOTAL_RECORDS:
            raise FieldSourceContentAuditError("opened_sources exceeds the supported total record count")
        try:
            for record_index, record in enumerate(records):
                kind, identifier, normalized = _normalize_record(
                    record, f"{label}.records[{record_index}]",
                    allow_volume=volume_manifest is not None,
                )
                key = role, digest, kind, identifier
                if key in actual:
                    duplicate_records += 1
                    problems.append(f"{label}.records[{record_index}] repeats a record key")
                    continue
                actual[key] = normalized
        except FieldSourceContentAuditError as exc:
            malformed_files += 1
            problems.append(str(exc))

    expected_keys = set(expected)
    actual_keys = set(actual)
    missing = sorted(expected_keys - actual_keys)
    extra = sorted(actual_keys - expected_keys)
    mismatched = sorted(key for key in expected_keys & actual_keys
                        if expected[key] != actual[key])
    exact = not (missing or extra or mismatched or problems)

    def example(key: tuple[str, str, str, str]) -> dict[str, str]:
        role, digest, kind, identifier = key
        return {"role": role, "sha256": digest, "kind": kind, "id_or_locator": identifier}

    return {
        "schema": 1,
        "classification": REPORT_CLASSIFICATION,
        "exact_declared_content_match": exact,
        **({"service_v_input_byte_bound": exact}
           if type(field.get("service")) is dict and field["service"].get("schema") == 2
           else {}),
        **({"baseline_volume_input_byte_bound": exact} if volume_manifest is not None else {}),
        "counts": {
            "declared_references": len(expected),
            "opened_primary_entries": len(opened),
            "parsed_records": len(actual),
            "matched_records": len(expected_keys & actual_keys) - len(mismatched),
            "missing_records": len(missing),
            "extra_records": len(extra),
            "mismatched_records": len(mismatched),
            "duplicate_records": duplicate_records,
            "duplicate_opened_entries": duplicate_files,
            "malformed_source_files": malformed_files,
        },
        "missing_examples": [example(key) for key in missing[:MAX_EXAMPLES]],
        "extra_examples": [example(key) for key in extra[:MAX_EXAMPLES]],
        "mismatched_examples": [example(key) for key in mismatched[:MAX_EXAMPLES]],
        "problem_examples": sorted(problems)[:MAX_EXAMPLES],
        "example_limit": MAX_EXAMPLES,
        "source_truth_authenticated": False,
        "physical_custody_authenticated": False,
        "approval_authenticated": False,
        "execution_ready": False,
        "criterion_3": {"status": "not_assessed", "reason": NOTICE},
        "notice": NOTICE,
    }
