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
from specorganon.field_guardrails import canonical_sha256


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


def _volume_case() -> tuple[tuple[dict, dict, dict, dict, list[dict[str, str]]], dict]:
    case = _case()
    digest = _sha("baseline input volume bytes")
    analysis = {
        "schema": 2,
        "baseline_input_volume_manifest": {
            "rows": [
                {"source": {"record_sha256": digest, "locator": "volume/group-1"}},
                {"source": {"record_sha256": digest, "locator": "volume/group-2"}},
            ],
        },
    }
    case[4].append({"role": "source_record", "sha256": digest})
    return case, analysis


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
    assert "service_v_input_byte_bound" not in report
    assert canonical_sha256(report) == (
        "816495cd01f95d752e176b020ec33ab1e4e47c3d00f019a16087e38759b7de41"
    )
    assert report["criterion_3"]["status"] == "not_assessed"


def test_schema1_analysis_preserves_exact_legacy_report() -> None:
    case = _case()
    legacy = _audit(case)
    report = audit_field_source_digest_coverage(*case, analysis={"schema": 1})
    assert report == legacy
    assert "baseline_volume_input_byte_bound" not in report
    assert canonical_sha256(report) == (
        "816495cd01f95d752e176b020ec33ab1e4e47c3d00f019a16087e38759b7de41"
    )


def test_schema2_volume_digest_coverage_counts_each_row_without_claiming_content() -> None:
    case, analysis = _volume_case()
    before = copy.deepcopy((case, analysis))
    report = audit_field_source_digest_coverage(*case, analysis=analysis)
    assert (case, analysis) == before
    assert report["exact_primary_source_coverage"] is True
    assert report["counts"]["required_references"] == 9
    assert report["counts"]["unique_required_role_digests"] == 6
    assert report["counts"]["repeated_references"] == 3
    assert report["by_role"]["source_record"]["required_references"] == 6
    assert report["baseline_volume_input_byte_bound"] is False
    assert report["source_truth_authenticated"] is False
    assert report["criterion_3"]["status"] == "not_assessed"


@pytest.mark.parametrize("change, expected", [
    ("missing", "missing_references"),
    ("wrong_role", "wrong_role_unique_digests"),
    ("extra", "extra_unique_role_digests"),
    ("duplicate_opened", "duplicate_opened_entries"),
])
def test_schema2_volume_missing_wrong_role_extra_or_duplicate_opened_digest(
    change: str, expected: str,
) -> None:
    case, analysis = _volume_case()
    if change == "missing":
        case[4].pop()
    elif change == "wrong_role":
        case[4][-1]["role"] = "approval_record"
    elif change == "extra":
        case[4].append({"role": "source_record", "sha256": _sha("unreferenced volume bytes")})
    else:
        case[4].append(copy.deepcopy(case[4][-1]))
    report = audit_field_source_digest_coverage(*case, analysis=analysis)
    assert report["exact_primary_source_coverage"] is False
    assert report["counts"][expected] > 0
    assert report["baseline_volume_input_byte_bound"] is False
    if change in {"missing", "wrong_role"}:
        missing = next(example for example in report["missing_examples"]
                       if example["sha256"] == _sha("baseline input volume bytes"))
        assert missing["reference_count"] == 2
        assert missing["reference_examples"] == [
            "analysis.baseline_input_volume_manifest.rows[0].source.record_sha256",
            "analysis.baseline_input_volume_manifest.rows[1].source.record_sha256",
        ]


@pytest.mark.parametrize("change, message", [
    ("missing_manifest", "analysis.baseline_input_volume_manifest is required"),
    ("bad_manifest", "analysis.baseline_input_volume_manifest must be an object"),
    ("missing_rows", "analysis.baseline_input_volume_manifest.rows is required"),
    ("bad_rows", "analysis.baseline_input_volume_manifest.rows must be an array"),
    ("empty_rows", "analysis.baseline_input_volume_manifest.rows must be nonempty"),
    ("bad_row", "analysis.baseline_input_volume_manifest.rows[0] must be an object"),
    ("missing_source", "analysis.baseline_input_volume_manifest.rows[0].source is required"),
    ("bad_source", "analysis.baseline_input_volume_manifest.rows[0].source must be an object"),
    ("missing_digest", "record_sha256 is required"),
    ("bad_digest", "lowercase SHA-256"),
    ("missing_locator", "locator must be nonempty trimmed text"),
    ("duplicate_reference", "repeats a volume digest and locator reference"),
])
def test_schema2_volume_malformed_reference_fails_closed(change: str, message: str) -> None:
    case, analysis = _volume_case()
    manifest = analysis["baseline_input_volume_manifest"]
    rows = manifest["rows"]
    if change == "missing_manifest":
        del analysis["baseline_input_volume_manifest"]
    elif change == "bad_manifest":
        analysis["baseline_input_volume_manifest"] = None
    elif change == "missing_rows":
        del manifest["rows"]
    elif change == "bad_rows":
        manifest["rows"] = {}
    elif change == "empty_rows":
        rows.clear()
    elif change == "bad_row":
        rows[0] = None
    elif change == "missing_source":
        del rows[0]["source"]
    elif change == "bad_source":
        rows[0]["source"] = None
    elif change == "missing_digest":
        del rows[0]["source"]["record_sha256"]
    elif change == "bad_digest":
        rows[0]["source"]["record_sha256"] = "A" * 64
    elif change == "missing_locator":
        del rows[0]["source"]["locator"]
    else:
        rows[1]["source"]["locator"] = rows[0]["source"]["locator"]
    with pytest.raises(FieldSourceDigestAuditError, match=re.escape(message)):
        audit_field_source_digest_coverage(*case, analysis=analysis)


def _v2_case() -> tuple[dict, dict, dict, dict, list[dict[str, str]]]:
    case = _case()
    digest = _sha("service ledger bytes")
    case[1]["service"].update({
        "schema": 2,
        "rows": [
            {"source": {"record_sha256": digest, "locator": "service/pre"}},
            {"source": {"record_sha256": digest, "locator": "service/post"}},
        ],
    })
    case[4].append({"role": "source_record", "sha256": digest})
    return case


def test_service_schema3_digest_coverage_only_links_declared_rules_and_inputs() -> None:
    case = _v2_case()
    case[1]["service"]["schema"] = 3
    report = _audit(case)
    assert report["exact_primary_source_coverage"] is True
    assert report["service_denominator_rule_approval_byte_bound"] is False
    assert report["service_denominator_input_byte_bound"] is False
    assert "service_v_input_byte_bound" not in report
    case[4][-1]["role"] = "approval_record"
    report = _audit(case)
    assert report["exact_primary_source_coverage"] is False
    assert report["service_denominator_input_byte_bound"] is False


def test_service_schema2_digest_coverage_counts_each_row_without_claiming_content() -> None:
    case = _v2_case()
    before = copy.deepcopy(case)
    report = _audit(case)
    assert case == before
    assert report["exact_primary_source_coverage"] is True
    assert report["counts"]["required_references"] == 9
    assert report["counts"]["repeated_references"] == 3
    assert report["by_role"]["source_record"]["required_references"] == 6
    assert report["service_v_input_byte_bound"] is False


@pytest.mark.parametrize("change, expected", [
    ("missing", "missing_references"),
    ("wrong_role", "wrong_role_unique_digests"),
    ("duplicate_opened", "duplicate_opened_entries"),
])
def test_service_schema2_missing_wrong_role_or_duplicate_source_fails_coverage(
    change: str, expected: str,
) -> None:
    case = _v2_case()
    if change == "missing":
        case[4].pop()
    elif change == "wrong_role":
        case[4][-1]["role"] = "approval_record"
    else:
        case[4].append(copy.deepcopy(case[4][-1]))
    report = _audit(case)
    assert report["exact_primary_source_coverage"] is False
    assert report["counts"][expected] > 0
    assert report["service_v_input_byte_bound"] is False


@pytest.mark.parametrize("change, message", [
    ("missing_digest", "record_sha256 is required"),
    ("bad_digest", "lowercase SHA-256"),
    ("duplicate_reference", "repeats a service digest and locator reference"),
])
def test_service_schema2_malformed_row_reference_fails_closed(change: str, message: str) -> None:
    case = _v2_case()
    sources = case[1]["service"]["rows"]
    if change == "missing_digest":
        del sources[0]["source"]["record_sha256"]
    elif change == "bad_digest":
        sources[0]["source"]["record_sha256"] = "A" * 64
    else:
        sources[1]["source"]["locator"] = sources[0]["source"]["locator"]
    with pytest.raises(FieldSourceDigestAuditError, match=message):
        _audit(case)


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
