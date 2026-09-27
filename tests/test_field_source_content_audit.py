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
