"""Synthetic extract comparisons do not authenticate field facts or approval."""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from specorganon.field_source_content_audit import (
    CLASSIFICATION,
    FieldSourceContentAuditError,
    audit_field_source_content,
)
import specorganon.field_source_content_audit as content_audit
from specorganon.field_guardrails import canonical_sha256


def _raw(records: list[dict]) -> bytes:
    return json.dumps({
        "schema": 1, "classification": CLASSIFICATION, "records": records,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _opened(role: str, raw: bytes) -> dict:
    return {"role": role, "sha256": hashlib.sha256(raw).hexdigest(), "raw": raw}


def _case(*, aggregate: bool = True) -> tuple[dict, dict, dict, dict, list[dict]]:
    source = {
        "source_id": "assignment-ledger", "locator": "assignment/one",
        "observed_at_utc": "2026-02-01T00:00:00Z", "method": "synthetic ledger",
    }
    eq_source = {
        "source_id": "equivalence-approval", "locator": "approval/one",
        "observed_at_utc": "2025-12-02T00:00:00Z", "method": "synthetic signature",
    }
    plan = {
        "study_id": "synthetic-study", "allocation_method": "stratified_random",
        "allocation_record_sha256": "",
        "groups": [{"id": "c1", "arm": "control", "stratum": "S1"}],
        "baseline_release": {
            "first_access_at_utc": "2025-12-30T00:00:00Z",
            "custodian_id": "synthetic-custodian", "record_sha256": "",
        },
    }
    field = {
        "study_id": "synthetic-study",
        "groups": [{
            "id": "c1", "arm": "control", "stratum": "S1",
            "assigned_at_utc": "2026-02-01T12:00:00Z",
            "actor_ids": ["actor:processor", "actor:farmer"], "source": source,
        }],
        "service": {"equivalence": {
            "id": "equivalence-one", "service_unit": "servings",
            "approved_at_utc": "2025-12-01T00:00:00Z",
            "approved_by_actor_ids": ["actor:processor", "actor:farmer"],
            "verified_by": "synthetic-verifier", "source": eq_source,
            "record_sha256": "",
        }},
    }
    registry = {"cells": [{
        "id": "cell-cost", "status": "measured", "unit": "hours",
        "denominator": "one service unit", "source_id": "cost-ledger",
    }, {
        "id": "cell-safety", "status": "excluded", "actor_id": "actor:farmer",
        "stage": "harvest", "metric": "safety", "reason": "synthetic omission",
        "approved_by": "synthetic-reviewer", "approved_at_utc": "2025-12-21T00:00:00Z",
        "approval_record_sha256": "",
    }]}
    measurements = {"rows": [{
        "group_id": "c1", "period": "pre", "cell_id": "cell-cost", "value": 1.25,
        "source": {"record_sha256": "", "locator": "ledger/pre/c1",
                   "observed_at_utc": "2026-01-15T12:00:00Z", "method": "meter"},
    }, {
        "group_id": "c1", "period": "post", "cell_id": "cell-cost", "value": 0.1,
        "source": {"record_sha256": "", "locator": "ledger/post/c1",
                   "observed_at_utc": "2026-03-15T12:00:00Z", "method": "meter"},
    }]}

    allocation = {
        "kind": "allocation", "study_id": "synthetic-study",
        "allocation_method": "stratified_random",
        "groups": [{
            "id": "c1", "arm": "control", "stratum": "S1",
            "assigned_at_utc": "2026-02-01T12:00:00Z",
            "actor_ids": ["actor:farmer", "actor:processor"], "source": source,
        }],
    }
    baseline = {
        "kind": "baseline_release", "study_id": "synthetic-study",
        "first_access_at_utc": "2025-12-30T00:00:00Z",
        "custodian_id": "synthetic-custodian",
    }
    equivalence = {
        "kind": "equivalence", "id": "equivalence-one", "service_unit": "servings",
        "approved_at_utc": "2025-12-01T00:00:00Z",
        "approved_by_actor_ids": ["actor:farmer", "actor:processor"],
        "verified_by": "synthetic-verifier", "source": eq_source,
    }
    excluded = {
        "kind": "excluded_cell", "cell_id": "cell-safety",
        "actor_id": "actor:farmer", "stage": "harvest", "metric": "safety",
        "reason": "synthetic omission", "approved_by": "synthetic-reviewer",
        "approved_at_utc": "2025-12-21T00:00:00Z",
    }
    measurement_records = [{
        "kind": "measurement", "locator": row["source"]["locator"],
        "group_id": row["group_id"], "period": row["period"],
        "cell_id": row["cell_id"], "value": row["value"],
        "observed_at_utc": row["source"]["observed_at_utc"],
        "method": row["source"]["method"], "unit": "hours",
        "denominator": "one service unit", "source_id": "cost-ledger",
    } for row in measurements["rows"]]

    source_records = [allocation, baseline, *measurement_records]
    approval_records = [equivalence, excluded]
    opened = []
    for role, records in (("source_record", source_records),
                          ("approval_record", approval_records)):
        chunks = [records] if aggregate else [[record] for record in records]
        for chunk in chunks:
            entry = _opened(role, _raw(chunk))
            opened.append(entry)
            for record in chunk:
                if record["kind"] == "allocation":
                    plan["allocation_record_sha256"] = entry["sha256"]
                elif record["kind"] == "baseline_release":
                    plan["baseline_release"]["record_sha256"] = entry["sha256"]
                elif record["kind"] == "equivalence":
                    field["service"]["equivalence"]["record_sha256"] = entry["sha256"]
                elif record["kind"] == "excluded_cell":
                    registry["cells"][1]["approval_record_sha256"] = entry["sha256"]
                else:
                    row = next(row for row in measurements["rows"]
                               if row["source"]["locator"] == record["locator"])
                    row["source"]["record_sha256"] = entry["sha256"]
    return plan, field, registry, measurements, opened


@pytest.mark.parametrize("aggregate", [True, False])
def test_all_declared_records_match_aggregate_or_single_record_files(aggregate: bool) -> None:
    case = _case(aggregate=aggregate)
    before = copy.deepcopy(case)
    report = audit_field_source_content(*case)
    assert case == before
    assert report["exact_declared_content_match"] is True
    assert report["counts"] == {
        "declared_references": 6,
        "opened_primary_entries": 2 if aggregate else 6,
        "parsed_records": 6,
        "matched_records": 6,
        "missing_records": 0,
        "extra_records": 0,
        "mismatched_records": 0,
        "duplicate_records": 0,
        "duplicate_opened_entries": 0,
        "malformed_source_files": 0,
    }
    assert report["source_truth_authenticated"] is False
    assert "service_v_input_byte_bound" not in report
    assert canonical_sha256(report) == (
        "684c6ea351182c3a9661288343bffcb12b475dfdba4e2d942f958cf264b4f172"
        if aggregate else
        "3299b0d643918d404e8f3a205c51e09ad6a2c3d6f3cf9c269990da38e33ede42"
    )
    assert report["physical_custody_authenticated"] is False
    assert report["approval_authenticated"] is False
    assert report["criterion_3"]["status"] == "not_assessed"


def _replace_aggregate_source(case: tuple, raw: bytes) -> None:
    entry = _opened("source_record", raw)
    case[4][0] = entry
    case[0]["allocation_record_sha256"] = entry["sha256"]
    case[0]["baseline_release"]["record_sha256"] = entry["sha256"]
    for row in case[3]["rows"]:
        row["source"]["record_sha256"] = entry["sha256"]
    if case[1].get("service", {}).get("schema") in {2, 3}:
        for row in case[1]["service"]["rows"]:
            row["source"]["record_sha256"] = entry["sha256"]


def _v2_case(*, aggregate: bool = True) -> tuple[dict, dict, dict, dict, list[dict]]:
    case = _case(aggregate=aggregate)
    service = case[1]["service"]
    service["schema"] = 2
    service["rows"] = []
    records = []
    for period, observed_at in (("pre", "2026-01-15T12:00:00Z"),
                                ("post", "2026-03-15T12:00:00Z")):
        source = {
            "source_id": "service-ledger", "locator": f"service/{period}/c1",
            "observed_at_utc": observed_at, "method": "synthetic service count",
        }
        row = {
            "group_id": "c1", "period": period,
            "consumption_flow_ids": [f"flow/{period}/consumed"],
            "consumed_service": {"value": 7, "unit": "servings", "uncertainty": 0.1},
            "feasible_max_service": {"value": 10, "unit": "servings", "uncertainty": 0.2},
            "source": {**source, "record_sha256": ""},
        }
        service["rows"].append(row)
        records.append({
            "kind": "service_row", "equivalence_id": "equivalence-one",
            **{key: value for key, value in row.items() if key != "source"},
            "source": source,
        })
    if aggregate:
        body = json.loads(case[4][0]["raw"])
        body["records"].extend(records)
        _replace_aggregate_source(case, json.dumps(body).encode("utf-8"))
    else:
        for row, record in zip(service["rows"], records, strict=True):
            entry = _opened("source_record", _raw([record]))
            case[4].append(entry)
            row["source"]["record_sha256"] = entry["sha256"]
    return case


def _v3_case() -> tuple[dict, dict, dict, dict, list[dict]]:
    case = _v2_case()
    _, field, registry, _, opened = case
    service = field["service"]
    service["schema"] = 3
    rules = [
        {"id": "food", "material_id": "synthetic-food", "classification": "eligible",
         "basis": "Synthetic declared ceiling", "max_service_per_kg": 1},
        {"id": "inedible", "material_id": "synthetic-inedible",
         "classification": "unsuitable", "basis": "Synthetic exclusion",
         "max_service_per_kg": 0},
        {"id": "water", "material_id": "synthetic-water",
         "classification": "water", "basis": "Synthetic added water exclusion",
         "max_service_per_kg": 0},
    ]
    service["equivalence"]["denominator_rules"] = rules
    approval_body = json.loads(opened[1]["raw"])
    approval_equivalence = next(record for record in approval_body["records"]
                                if record["kind"] == "equivalence")
    approval_equivalence["denominator_rules"] = copy.deepcopy(rules)
    opened[1] = _opened("approval_record", _raw(approval_body["records"]))
    service["equivalence"]["record_sha256"] = opened[1]["sha256"]
    registry["cells"][1]["approval_record_sha256"] = opened[1]["sha256"]

    source_body = json.loads(opened[0]["raw"])
    field["flows"] = []
    for row in service["rows"]:
        period = row["period"]
        record = next(item for item in source_body["records"]
                      if item["kind"] == "service_row" and item["period"] == period)
        inputs = []
        for suffix, material_id, rule_id, kind, mass in (
            ("raw", "synthetic-food", "food", "feed", 10),
            ("inedible", "synthetic-inedible", "inedible", "ingredient", 2),
            ("water", "synthetic-water", "water", "water_addition", 3),
        ):
            flow_id = f"flow/{period}/{suffix}"
            declared_mass = {"value": mass, "unit": "kg", "uncertainty": 0.2}
            field["flows"].append({"id": flow_id, "group_id": "c1", "period": period,
                                   "from_lot_id": None, "kind": kind,
                                   "material_id": material_id, "mass": declared_mass})
            row.setdefault("denominator_inputs", []).append({"input_flow_id": flow_id,
                                                               "rule_id": rule_id})
            inputs.append({"input_flow_id": flow_id, "material_id": material_id,
                           "rule_id": rule_id, "mass": declared_mass})
        record["denominator_inputs"] = inputs
    _replace_aggregate_source(case, _raw(source_body["records"]))
    return case


def test_service_schema3_rules_inputs_and_mass_match_opened_bytes() -> None:
    case = _v3_case()
    report = audit_field_source_content(*case)
    assert report["exact_declared_content_match"] is True
    assert report["service_denominator_rule_approval_byte_bound"] is True
    assert report["service_denominator_input_byte_bound"] is True
    assert "service_v_input_byte_bound" not in report


@pytest.mark.parametrize("change", ["coefficient", "basis", "rule_material",
                                     "input_rule", "input_mass", "flow_mass"])
def test_schema3_rehashed_declaration_cannot_hide_rule_or_input_change(change: str) -> None:
    case = _v3_case()
    service = case[1]["service"]
    if change == "coefficient":
        service["equivalence"]["denominator_rules"][0]["max_service_per_kg"] = 2
    elif change == "basis":
        service["equivalence"]["denominator_rules"][0]["basis"] = "changed"
    elif change == "rule_material":
        service["equivalence"]["denominator_rules"][0]["material_id"] = "changed"
    elif change == "input_rule":
        service["rows"][0]["denominator_inputs"][0]["rule_id"] = "inedible"
    elif change == "input_mass":
        body = json.loads(case[4][0]["raw"])
        record = next(item for item in body["records"] if item["kind"] == "service_row")
        record["denominator_inputs"][0]["mass"]["value"] = 11
        _replace_aggregate_source(case, _raw(body["records"]))
    else:
        case[1]["flows"][0]["mass"]["value"] = 11
    report = audit_field_source_content(*case)
    assert report["exact_declared_content_match"] is False
    rule_changed = change in {"coefficient", "basis", "rule_material"}
    assert report["service_denominator_rule_approval_byte_bound"] is not rule_changed
    assert report["service_denominator_input_byte_bound"] is rule_changed


@pytest.mark.parametrize("aggregate", [True, False])
def test_service_schema2_matches_aggregate_or_per_row_extracts(aggregate: bool) -> None:
    case = _v2_case(aggregate=aggregate)
    before = copy.deepcopy(case)
    report = audit_field_source_content(*case)
    assert case == before
    assert report["exact_declared_content_match"] is True
    assert report["service_v_input_byte_bound"] is True
    assert report["counts"]["declared_references"] == 8
    assert report["counts"]["parsed_records"] == 8
    assert report["counts"]["matched_records"] == 8


def test_rederived_field_hash_does_not_hide_changed_service_v_input() -> None:
    case = _v2_case()
    before_hash = hashlib.sha256(json.dumps(case[1], sort_keys=True).encode()).hexdigest()
    case[1]["service"]["rows"][0]["consumed_service"]["value"] = 8
    after_hash = hashlib.sha256(json.dumps(case[1], sort_keys=True).encode()).hexdigest()
    assert before_hash != after_hash
    report = audit_field_source_content(*case)
    assert report["exact_declared_content_match"] is False
    assert report["service_v_input_byte_bound"] is False
    assert report["counts"]["mismatched_records"] == 1
    assert report["mismatched_examples"][0]["kind"] == "service_row"


def test_service_schema2_extract_accepts_matching_fractional_source_time() -> None:
    case = _v2_case()
    observed_at = "2026-01-15T12:00:00.123456Z"
    case[1]["service"]["rows"][0]["source"]["observed_at_utc"] = observed_at
    body = json.loads(case[4][0]["raw"])
    record = next(item for item in body["records"] if item["kind"] == "service_row")
    record["source"]["observed_at_utc"] = observed_at
    _replace_aggregate_source(case, json.dumps(body).encode("utf-8"))
    report = audit_field_source_content(*case)
    assert report["exact_declared_content_match"] is True
    assert report["service_v_input_byte_bound"] is True


@pytest.mark.parametrize("path", [
    ("group_id",), ("period",), ("consumption_flow_ids",),
    ("consumed_service", "value"), ("consumed_service", "unit"),
    ("consumed_service", "uncertainty"),
    ("feasible_max_service", "value"), ("feasible_max_service", "unit"),
    ("feasible_max_service", "uncertainty"),
    ("source", "source_id"), ("source", "observed_at_utc"),
    ("source", "method"), ("equivalence_id",),
])
def test_rehashed_service_extract_must_match_every_declared_fact(path: tuple[str, ...]) -> None:
    case = _v2_case()
    body = json.loads(case[4][0]["raw"])
    record = next(item for item in body["records"] if item["kind"] == "service_row")
    target = record
    for key in path[:-1]:
        target = target[key]
    key = path[-1]
    if key == "consumption_flow_ids":
        target[key] = ["different-flow"]
    elif key == "observed_at_utc":
        target[key] = "2026-01-16T12:00:00Z"
    elif key in {"value", "uncertainty"}:
        target[key] = 5
    else:
        target[key] = "changed"
    _replace_aggregate_source(case, json.dumps(body).encode("utf-8"))
    report = audit_field_source_content(*case)
    assert report["exact_declared_content_match"] is False
    assert report["service_v_input_byte_bound"] is False
    assert report["counts"]["mismatched_records"] == 1


def test_rehashed_service_extract_with_changed_source_locator_loses_reference() -> None:
    case = _v2_case()
    body = json.loads(case[4][0]["raw"])
    record = next(item for item in body["records"] if item["kind"] == "service_row")
    record["source"]["locator"] = "service/different"
    _replace_aggregate_source(case, json.dumps(body).encode("utf-8"))
    report = audit_field_source_content(*case)
    assert report["exact_declared_content_match"] is False
    assert report["service_v_input_byte_bound"] is False
    assert report["counts"]["missing_records"] == 1
    assert report["counts"]["extra_records"] == 1


@pytest.mark.parametrize("change, counter", [
    ("missing", "missing_records"),
    ("wrong_role", "missing_records"),
    ("duplicate", "duplicate_records"),
])
def test_service_schema2_missing_wrong_role_or_duplicate_record_fails(
    change: str, counter: str,
) -> None:
    case = _v2_case(aggregate=False)
    if change == "missing":
        case[4].pop()
    elif change == "wrong_role":
        case[4][-1]["role"] = "approval_record"
    else:
        body = json.loads(case[4][-1]["raw"])
        body["records"].append(copy.deepcopy(body["records"][0]))
        entry = _opened("source_record", json.dumps(body).encode("utf-8"))
        case[4][-1] = entry
        case[1]["service"]["rows"][-1]["source"]["record_sha256"] = entry["sha256"]
    report = audit_field_source_content(*case)
    assert report["exact_declared_content_match"] is False
    assert report["service_v_input_byte_bound"] is False
    assert report["counts"][counter] > 0


def _volume_case(*, aggregate: bool = True) -> tuple[tuple, dict]:
    case = _case()
    plan, field, _, _, opened = case
    second_plan_group = copy.deepcopy(plan["groups"][0])
    second_plan_group["id"] = "c2"
    plan["groups"].append(second_plan_group)
    second_field_group = copy.deepcopy(field["groups"][0])
    second_field_group["id"] = "c2"
    field["groups"].append(second_field_group)

    body = json.loads(opened[0]["raw"])
    allocation = next(record for record in body["records"]
                      if record["kind"] == "allocation")
    second_allocation_group = copy.deepcopy(allocation["groups"][0])
    second_allocation_group["id"] = "c2"
    allocation["groups"].append(second_allocation_group)

    unit = "kg_eligible_input"
    definition_sha256 = canonical_sha256({
        "unit": unit, "definition": "all eligible pre-window input",
    })
    rows = []
    records = []
    for group_id, value in (("c1", 100), ("c2", 120.125)):
        source = {
            "locator": f"volume/pre/{group_id}",
            "observed_at_utc": "2026-02-01T10:00:00.123456Z",
            "method": "synthetic scale aggregate",
        }
        row = {
            "group_id": group_id, "period": "pre", "value": value, "unit": unit,
            "window_start_utc": "2026-01-01T00:00:00Z",
            "window_end_utc": "2026-01-31T23:59:59.123456Z",
            "source": {**source, "record_sha256": ""},
        }
        rows.append(row)
        records.append({
            "kind": "volume_row", "study_id": plan["study_id"],
            "definition_sha256": definition_sha256,
            **{key: value for key, value in row.items() if key != "source"},
            "source": source,
        })

    if aggregate:
        body["records"].extend(records)
        _replace_aggregate_source(case, _raw(body["records"]))
        for row in rows:
            row["source"]["record_sha256"] = opened[0]["sha256"]
    else:
        _replace_aggregate_source(case, _raw(body["records"]))
        for row, record in zip(rows, records, strict=True):
            entry = _opened("source_record", _raw([record]))
            opened.append(entry)
            row["source"]["record_sha256"] = entry["sha256"]

    analysis = {
        "schema": 2,
        "baseline_input_volume_manifest": {
            "schema": 1,
            "classification": "field_baseline_input_volume_manifest_unsealed",
            "study_id": plan["study_id"],
            "plan_sha256": canonical_sha256(plan),
            "candidate_spec_sha256": hashlib.sha256(b"synthetic candidate spec").hexdigest(),
            "unit": unit,
            "definition_sha256": definition_sha256,
            "rows": rows,
        },
    }
    return case, analysis


def _replace_aggregate_volume_source(case: tuple, analysis: dict, records: list[dict]) -> None:
    _replace_aggregate_source(case, _raw(records))
    digest = case[4][0]["sha256"]
    for row in analysis["baseline_input_volume_manifest"]["rows"]:
        row["source"]["record_sha256"] = digest


@pytest.mark.parametrize("aggregate", [True, False])
def test_analysis_schema2_volume_rows_match_aggregate_or_per_row_extracts(
    aggregate: bool,
) -> None:
    case, analysis = _volume_case(aggregate=aggregate)
    before = copy.deepcopy((case, analysis))
    report = audit_field_source_content(*case, analysis=analysis)
    assert (case, analysis) == before
    assert report["exact_declared_content_match"] is True
    assert report["baseline_volume_input_byte_bound"] is True
    assert "service_v_input_byte_bound" not in report
    assert report["counts"]["declared_references"] == 8
    assert report["counts"]["opened_primary_entries"] == (2 if aggregate else 4)
    assert report["counts"]["parsed_records"] == 8
    assert report["counts"]["matched_records"] == 8


def test_omitted_or_schema1_analysis_preserves_pinned_legacy_report() -> None:
    case = _case()
    omitted = audit_field_source_content(*case)
    schema1 = audit_field_source_content(*case, analysis={"schema": 1})
    assert schema1 == omitted
    assert "baseline_volume_input_byte_bound" not in schema1
    assert canonical_sha256(schema1) == (
        "684c6ea351182c3a9661288343bffcb12b475dfdba4e2d942f958cf264b4f172"
    )


def test_volume_extract_kind_requires_schema2_analysis_opt_in() -> None:
    case, _ = _volume_case()
    for kwargs in ({}, {"analysis": {"schema": 1}}):
        report = audit_field_source_content(*case, **kwargs)
        assert "baseline_volume_input_byte_bound" not in report
        assert report["exact_declared_content_match"] is False
        assert report["counts"]["malformed_source_files"] == 1
        assert report["counts"]["extra_records"] == 0


def test_changed_declared_volume_value_cannot_pass_with_rederived_analysis() -> None:
    case, analysis = _volume_case()
    analysis["baseline_input_volume_manifest"]["rows"][0]["value"] = 101
    report = audit_field_source_content(*case, analysis=analysis)
    assert report["exact_declared_content_match"] is False
    assert report["baseline_volume_input_byte_bound"] is False
    assert report["counts"]["mismatched_records"] == 1
    assert report["mismatched_examples"][0]["kind"] == "volume_row"


def test_volume_row_numbers_compare_as_decimals() -> None:
    case, analysis = _volume_case()
    body = json.loads(case[4][0]["raw"])
    record = next(item for item in body["records"] if item["kind"] == "volume_row")
    record["value"] = 100.0
    _replace_aggregate_volume_source(case, analysis, body["records"])
    report = audit_field_source_content(*case, analysis=analysis)
    assert report["exact_declared_content_match"] is True
    assert report["baseline_volume_input_byte_bound"] is True


@pytest.mark.parametrize("path, replacement", [
    (("study_id",), "changed-study"),
    (("definition_sha256",), "a" * 64),
    (("group_id",), "changed-group"),
    (("period",), "post"),
    (("value",), 101),
    (("unit",), "changed-unit"),
    (("window_start_utc",), "2026-01-02T00:00:00Z"),
    (("window_end_utc",), "2026-01-30T23:59:59.123456Z"),
    (("source", "observed_at_utc"), "2026-02-01T11:00:00.123456Z"),
    (("source", "method"), "changed method"),
])
def test_rehashed_volume_extract_must_match_every_declared_fact(
    path: tuple[str, ...], replacement: object,
) -> None:
    case, analysis = _volume_case()
    body = json.loads(case[4][0]["raw"])
    record = next(item for item in body["records"] if item["kind"] == "volume_row")
    target = record
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    _replace_aggregate_volume_source(case, analysis, body["records"])
    report = audit_field_source_content(*case, analysis=analysis)
    assert report["exact_declared_content_match"] is False
    assert report["baseline_volume_input_byte_bound"] is False
    assert report["counts"]["mismatched_records"] == 1
    assert report["mismatched_examples"][0]["kind"] == "volume_row"


def test_rehashed_volume_extract_with_changed_locator_loses_reference() -> None:
    case, analysis = _volume_case()
    body = json.loads(case[4][0]["raw"])
    record = next(item for item in body["records"] if item["kind"] == "volume_row")
    record["source"]["locator"] = "volume/pre/different"
    _replace_aggregate_volume_source(case, analysis, body["records"])
    report = audit_field_source_content(*case, analysis=analysis)
    assert report["baseline_volume_input_byte_bound"] is False
    assert report["counts"]["missing_records"] == 1
    assert report["counts"]["extra_records"] == 1


@pytest.mark.parametrize("change, counter", [
    ("missing", "missing_records"),
    ("duplicate", "duplicate_records"),
    ("self_digest", "malformed_source_files"),
    ("extra_record_key", "malformed_source_files"),
    ("seven_digit_fraction", "malformed_source_files"),
])
def test_volume_extract_missing_duplicate_or_malformed_record_fails(
    change: str, counter: str,
) -> None:
    case, analysis = _volume_case()
    body = json.loads(case[4][0]["raw"])
    record = next(item for item in body["records"] if item["kind"] == "volume_row")
    if change == "missing":
        body["records"].remove(record)
    elif change == "duplicate":
        body["records"].append(copy.deepcopy(record))
    elif change == "self_digest":
        record["source"]["record_sha256"] = "a" * 64
    elif change == "extra_record_key":
        record["extra"] = "unsupported"
    else:
        record["source"]["observed_at_utc"] = "2026-02-01T10:00:00.1234567Z"
    _replace_aggregate_volume_source(case, analysis, body["records"])
    report = audit_field_source_content(*case, analysis=analysis)
    assert report["exact_declared_content_match"] is False
    assert report["baseline_volume_input_byte_bound"] is False
    assert report["counts"][counter] > 0


def test_volume_extract_under_wrong_role_loses_reference() -> None:
    case, analysis = _volume_case(aggregate=False)
    case[4][-1]["role"] = "approval_record"
    report = audit_field_source_content(*case, analysis=analysis)
    assert report["baseline_volume_input_byte_bound"] is False
    assert report["counts"]["missing_records"] == 1
    assert report["counts"]["extra_records"] == 1


def test_duplicate_declared_volume_digest_and_locator_is_rejected() -> None:
    case, analysis = _volume_case()
    second = analysis["baseline_input_volume_manifest"]["rows"][1]
    second["source"]["locator"] = analysis["baseline_input_volume_manifest"]["rows"][0]["source"]["locator"]
    with pytest.raises(FieldSourceContentAuditError, match="repeats a declared source reference"):
        audit_field_source_content(*case, analysis=analysis)


def test_rehashed_empty_extract_is_not_a_false_green() -> None:
    case = _case()
    _replace_aggregate_source(case, b"{}")
    report = audit_field_source_content(*case)
    assert report["exact_declared_content_match"] is False
    assert report["counts"]["missing_records"] == 4
    assert report["counts"]["malformed_source_files"] == 1


def test_rehashed_wrong_decimal_value_is_rejected() -> None:
    case = _case()
    body = json.loads(case[4][0]["raw"])
    body["records"][3]["value"] = 0.10000000000000002
    _replace_aggregate_source(case, json.dumps(body).encode())
    report = audit_field_source_content(*case)
    assert report["exact_declared_content_match"] is False
    assert report["counts"]["mismatched_records"] == 1
    assert report["mismatched_examples"][0]["kind"] == "measurement"


def test_duplicate_missing_and_extra_records_fail_closed() -> None:
    case = _case()
    body = json.loads(case[4][0]["raw"])
    body["records"].append(copy.deepcopy(body["records"][-1]))
    _replace_aggregate_source(case, json.dumps(body).encode())
    report = audit_field_source_content(*case)
    assert report["exact_declared_content_match"] is False
    assert report["counts"]["duplicate_records"] == 1

    case = _case()
    body = json.loads(case[4][0]["raw"])
    body["records"].pop()
    _replace_aggregate_source(case, json.dumps(body).encode())
    report = audit_field_source_content(*case)
    assert report["counts"]["missing_records"] == 1
    assert report["exact_declared_content_match"] is False

    case = _case()
    body = json.loads(case[4][0]["raw"])
    extra = copy.deepcopy(body["records"][-1])
    extra["locator"] = "ledger/extra"
    body["records"].append(extra)
    _replace_aggregate_source(case, json.dumps(body).encode())
    report = audit_field_source_content(*case)
    assert report["counts"]["extra_records"] == 1
    assert report["exact_declared_content_match"] is False


@pytest.mark.parametrize("raw", [
    b'{"schema":1,"schema":1,"classification":"field_primary_source_content_extract","records":[]}',
    b'{"schema":1,"classification":"field_primary_source_content_extract","records":[{"kind":"measurement","value":NaN}]}',
])
def test_duplicate_json_keys_and_nan_fail_closed(raw: bytes) -> None:
    case = _case()
    _replace_aggregate_source(case, raw)
    report = audit_field_source_content(*case)
    assert report["exact_declared_content_match"] is False
    assert report["counts"]["malformed_source_files"] == 1


@pytest.mark.parametrize("value", [True, 1e19, 1e-19, float("inf")])
def test_ambiguous_or_out_of_range_numbers_fail_closed(value: object) -> None:
    case = _case()
    body = json.loads(case[4][0]["raw"])
    body["records"][2]["value"] = value
    _replace_aggregate_source(case, json.dumps(body).encode())
    report = audit_field_source_content(*case)
    assert report["exact_declared_content_match"] is False
    assert report["counts"]["malformed_source_files"] == 1


def test_wrong_role_and_declared_duplicate_reference_fail_closed() -> None:
    case = _case()
    case[4][0]["role"] = "approval_record"
    report = audit_field_source_content(*case)
    assert report["exact_declared_content_match"] is False
    assert report["counts"]["missing_records"] == 4
    assert report["counts"]["extra_records"] == 4

    case = _case()
    case[3]["rows"].append(copy.deepcopy(case[3]["rows"][0]))
    with pytest.raises(FieldSourceContentAuditError, match="repeats a declared source reference"):
        audit_field_source_content(*case)


def test_total_record_limit_rejects_cumulative_files_before_matching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(aggregate=False)
    monkeypatch.setattr(content_audit, "MAX_TOTAL_RECORDS", 5)
    with pytest.raises(FieldSourceContentAuditError, match="total record count"):
        audit_field_source_content(*case)
