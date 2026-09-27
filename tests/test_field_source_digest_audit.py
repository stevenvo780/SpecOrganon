"""Synthetic digest-link controls; no field record or custody is authenticated."""

from __future__ import annotations

import copy
import hashlib
import re

import pytest

from specorganon.field_source_digest_audit import (
    MAX_EXAMPLES,
    FieldSourceDigestAuditError,
    audit_field_source_digest_coverage,
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _case() -> tuple[dict, dict, dict, dict, list[dict[str, str]]]:
    plan = {
        "allocation_record_sha256": _sha("allocation bytes"),
        "baseline_release": {"record_sha256": _sha("baseline release bytes")},
    }
    field = {"service": {"equivalence": {"record_sha256": _sha("equivalence approval")}}}
    registry = {"cells": [
        {"status": "measured"},
        {"status": "excluded", "approval_record_sha256": _sha("exclusion approval")},
        {"status": "excluded", "approval_record_sha256": _sha("exclusion approval")},
    ]}
    measurements = {"rows": [
        {"source": {"record_sha256": _sha("measurement ledger bytes"), "locator": "row-1"}},
        {"source": {"record_sha256": _sha("measurement ledger bytes"), "locator": "row-2"}},
    ]}
    sources = [
        {"role": "plan", "sha256": _sha("plan JSON bytes")},
        {"role": "field", "sha256": _sha("field JSON bytes")},
        {"role": "source_record", "sha256": plan["allocation_record_sha256"]},
        {"role": "source_record", "sha256": plan["baseline_release"]["record_sha256"]},
        {"role": "source_record", "sha256": _sha("measurement ledger bytes")},
        {"role": "approval_record", "sha256": field["service"]["equivalence"]["record_sha256"]},
        {"role": "approval_record", "sha256": _sha("exclusion approval")},
    ]
    return plan, field, registry, measurements, sources


def _audit(case: tuple[dict, dict, dict, dict, list[dict[str, str]]]) -> dict:
    return audit_field_source_digest_coverage(*case)


def test_exact_role_coverage_counts_repeated_references_without_claiming_field_truth() -> None:
    case = _case()
    before = copy.deepcopy(case)
    report = _audit(case)
    assert case == before
    assert report["exact_primary_source_coverage"] is True
    assert report["counts"] == {
        "required_references": 7,
        "unique_required_role_digests": 5,
        "repeated_references": 2,
        "opened_primary_entries": 5,
        "missing_unique_role_digests": 0,
        "missing_references": 0,
        "wrong_role_unique_digests": 0,
        "extra_unique_role_digests": 0,
        "duplicate_opened_entries": 0,
    }
    assert report["by_role"]["source_record"]["required_references"] == 4
    assert report["by_role"]["approval_record"]["required_references"] == 3
    assert report["non_primary_manifest_entries"] == 2
    assert report["source_truth_authenticated"] is False
    assert report["physical_custody_authenticated"] is False
    assert report["approval_authenticated"] is False
    assert report["execution_ready"] is False
    assert report["criterion_3"]["status"] == "not_assessed"


def test_wrong_role_is_both_missing_and_extra_even_when_digest_matches() -> None:
    case = _case()
    source = next(item for item in case[4]
                  if item["sha256"] == _sha("measurement ledger bytes"))
    source["role"] = "approval_record"
    report = _audit(case)
    assert report["exact_primary_source_coverage"] is False
    assert report["counts"]["missing_unique_role_digests"] == 1
    assert report["counts"]["missing_references"] == 2
    assert report["counts"]["extra_unique_role_digests"] == 1
    assert report["counts"]["wrong_role_unique_digests"] == 1
    assert report["wrong_role_examples"] == [{
        "expected_role": "source_record", "found_role": "approval_record",
        "sha256": _sha("measurement ledger bytes"),
    }]
    assert report["missing_examples"][0]["reference_count"] == 2


def test_approval_digest_under_source_role_does_not_count_as_approval() -> None:
    case = _case()
    approval = next(item for item in case[4]
                    if item["sha256"] == _sha("equivalence approval"))
    approval["role"] = "source_record"
    report = _audit(case)
    assert report["exact_primary_source_coverage"] is False
    assert report["counts"]["wrong_role_unique_digests"] == 1
    assert report["wrong_role_examples"] == [{
        "expected_role": "approval_record", "found_role": "source_record",
        "sha256": _sha("equivalence approval"),
    }]


def test_omission_extra_and_duplicate_manifest_entries_each_prevent_exact_coverage() -> None:
    case = _case()
    case[4].remove(next(item for item in case[4]
                        if item["sha256"] == case[0]["allocation_record_sha256"]))
    case[4].append({"role": "source_record", "sha256": _sha("unreferenced bytes")})
    case[4].append(copy.deepcopy(case[4][-1]))
    report = _audit(case)
    assert report["exact_primary_source_coverage"] is False
    assert report["counts"]["missing_unique_role_digests"] == 1
    assert report["counts"]["extra_unique_role_digests"] == 1
    assert report["counts"]["duplicate_opened_entries"] == 1
    assert report["missing_examples"][0]["reference_examples"] == [
        "plan.allocation_record_sha256"
    ]
    assert report["extra_examples"] == [{"role": "source_record", "sha256": _sha("unreferenced bytes")}]
    assert report["duplicate_opened_examples"][0]["entry_count"] == 2


def test_missing_examples_are_bounded_while_counts_include_every_reference() -> None:
    case = _case()
    case[3]["rows"] = [
        {"source": {"record_sha256": _sha(f"ledger-{index}")}}
        for index in range(MAX_EXAMPLES + 7)
    ]
    case[4][:] = [item for item in case[4]
                  if item["sha256"] != _sha("measurement ledger bytes")]
    report = _audit(case)
    assert report["exact_primary_source_coverage"] is False
    assert report["counts"]["missing_unique_role_digests"] == MAX_EXAMPLES + 7
    assert report["counts"]["missing_references"] == MAX_EXAMPLES + 7
    assert report["counts"]["required_references"] == MAX_EXAMPLES + 7 + 5
    assert len(report["missing_examples"]) == MAX_EXAMPLES
    assert report["missing_example_limit"] == MAX_EXAMPLES


def test_absent_optional_baseline_service_and_exclusions_require_no_approval_record() -> None:
    case = _case()
    del case[0]["baseline_release"]
    case[1].clear()
    case[2]["cells"] = [{"status": "measured"}]
    case[4][:] = [item for item in case[4]
                  if item["role"] != "approval_record"
                  and item["sha256"] != _sha("baseline release bytes")]
    report = _audit(case)
    assert report["exact_primary_source_coverage"] is True
    assert report["by_role"]["approval_record"]["required_references"] == 0


@pytest.mark.parametrize("change, message", [
    ("bad_reference", "plan.allocation_record_sha256"),
    ("missing_source", "measurements.rows[0].source"),
    ("bad_status", "registry.cells[0].status"),
    ("bad_manifest_digest", "sources[0].sha256"),
    ("unknown_manifest_role", "sources[0].role"),
    ("unprojected_manifest_record", "exactly role and sha256"),
])
def test_malformed_inputs_fail_closed(change: str, message: str) -> None:
    case = _case()
    if change == "bad_reference":
        case[0]["allocation_record_sha256"] = "A" * 64
    elif change == "missing_source":
        del case[3]["rows"][0]["source"]
    elif change == "bad_status":
        case[2]["cells"][0]["status"] = "hidden"
    elif change == "bad_manifest_digest":
        case[4][0]["sha256"] = "invalid"
    elif change == "unknown_manifest_role":
        case[4][0]["role"] = "unknown"
    else:
        case[4][0]["path"] = "/somewhere"
    with pytest.raises(FieldSourceDigestAuditError, match=re.escape(message)):
        _audit(case)
