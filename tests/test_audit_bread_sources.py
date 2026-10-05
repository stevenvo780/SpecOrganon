"""D100 verifies editable transcriptions against independently extracted PDF passages."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from scripts import audit_bread_sources as auditor
from specorganon.source_passages import SourceAuditError, SourceSpec, read_pdf_pages

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "cases/bread_development/source_claims.json"
TABLE = ROOT / "cases/bread_norway/survey_table1.json"
PDFS = ROOT / "cases/bread_norway"


@pytest.fixture
def packet(tmp_path):
    claims = json.loads(CLAIMS.read_bytes())
    table = json.loads(TABLE.read_bytes())
    claims_path = tmp_path / "claims.json"
    table_path = tmp_path / "table.json"

    def run(*, altered_claims=None, altered_table=None, pdf_root=PDFS):
        # No transcription hash is used as an oracle. Even coherent reserialization
        # must be checked against the pinned published PDF bytes.
        claims_path.write_text(json.dumps(claims if altered_claims is None else altered_claims))
        table_path.write_text(json.dumps(table if altered_table is None else altered_table))
        return auditor.audit_bread_sources(claims_path, table_path, pdf_root)

    return claims, table, run


def _claim(claims, key):
    return next(claim for claim in claims["claims"] if claim["key"] == key)


@pytest.mark.parametrize("token", ["736.00000000000000001", "7.3600000000000000001e2"])
def test_decimal_claim_cannot_be_rounded_into_a_published_value(tmp_path, token):
    # Parsing through float must not erase a numerically distinct transcription.
    claims = tmp_path / "precision.json"
    original = CLAIMS.read_text()
    assert '"value": 736,' in original
    claims.write_text(original.replace('"value": 736,', f'"value": {token},', 1))
    with pytest.raises(SourceAuditError, match="precision|PDF value"):
        auditor.audit_bread_sources(claims_path=claims)


def test_real_archives_and_reserialized_transcriptions_are_verified(packet):
    claims, table, run = packet
    result = run()
    assert result["passed"] is True
    assert result["verified_claims"] == 17 == len(result["claims"])
    assert result["verified_survey_rows"] == 7 == len(result["survey_rows"])
    assert result["base_validation"] == "reviewed_contract_consistency"
    assert result["Q"] is None and result["global_acceptance"] == "0/5"
    assert result["field_intervention"] is False
    assert set(result["claims"]) == {claim["key"] for claim in claims["claims"]}
    extracted = {}
    for source, pin in claims["sources"].items():
        pdf = read_pdf_pages(PDFS / pin["visible_file"], SourceSpec(pin["bytes"], pin["sha256"]))
        extracted[pin["sha256"]] = pdf
        record = result["source_extraction"][source]
        assert record["sha256"] == pin["sha256"] == pdf.source_sha256
        assert record["bytes"] == pin["bytes"]
        assert record["text_sha256"] == pdf.text_sha256
        assert record["pages"] == len(pdf.pages)
        assert record["extractor_version"] == pdf.extractor_version
        assert record["extractor_path"] == pdf.extractor_path
        assert record["extractor_sha256"] == pdf.extractor_sha256
        assert record["extractor_execution"] == "sealed_memfd_verified_binary"
        assert record["host_shared_libraries_authenticated"] is False
    for passage in result["passages"].values():
        pdf = extracted[passage["source_sha256"]]
        page = pdf.pages[passage["page"] - 1]
        assert passage["page_sha256"] == hashlib.sha256(page.encode()).hexdigest()
        assert passage["matched_sha256"] == hashlib.sha256(passage["matched_text"].encode()).hexdigest()
        assert len(passage["passage_sha256"]) == 64
        assert passage["normalization"] == "whitespace_only"
    for claim in claims["claims"]:
        record = result["claims"][claim["key"]]
        passage = result["passages"][record["passage"]]
        assert record["passed"] is True
        assert passage["source_sha256"] == claims["sources"][claim["source"]]["sha256"]
        assert passage["page"] == claim["locator"]["pdf_page"]
        assert Decimal(record["value"]) == Decimal(str(claim["value"]))
        assert record["value"] == passage["groups"][claim["key"]]
    for row, expected in zip(result["survey_rows"], table["categories"], strict=True):
        assert row["passed"] is True
        assert {key: row[key] for key in expected} == expected
        passage = result["passages"][row["passage"]]
        assert passage["source_sha256"] == table["source"]["sha256"]
        assert int(passage["groups"]["count"]) == row["count"]
        assert passage["groups"]["percent"] == row["reported_percent"]
    warnings = json.dumps(result["warnings"], ensure_ascii=False).casefold()
    assert "3" in warnings and "4" in warnings
    assert "table" in warnings or "tabla" in warnings


@pytest.mark.parametrize("key,value", [
    ("piece_mass", 737), ("mill_electricity", 130),
    ("wheat_bran_mass_share", 19.2), ("mill_to_baker_distance", 439),
    ("bakery_electricity", 0.298), ("bakery_natural_gas", 0.116),
    ("retail_bread_waste", 11.5), ("consumer_bread_waste_estimate", 8.3),
    ("survey_respondents", 1001),
])
def test_changed_numeric_claim_is_rejected_after_json_rewrite(packet, key, value):
    claims, _, run = packet
    changed = copy.deepcopy(claims)
    _claim(changed, key)["value"] = value
    with pytest.raises(SourceAuditError):
        run(altered_claims=changed)


@pytest.mark.parametrize("value", [True, "736", None, float("nan"), float("inf")])
def test_invalid_numeric_representation_cannot_be_coerced_into_evidence(packet, value):
    claims, _, run = packet
    changed = copy.deepcopy(claims)
    _claim(changed, "piece_mass")["value"] = value
    with pytest.raises(SourceAuditError):
        run(altered_claims=changed)


def test_path_shim_cannot_change_numeric_audit_outcome(tmp_path, monkeypatch, packet):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shim = bindir / "pdftotext"
    shim.write_text("#!/bin/sh\nexit 99\n")
    shim.chmod(0o700)
    monkeypatch.setenv("PATH", str(bindir))
    claims, _, run = packet
    assert run()["verified_claims"] == 17
    changed = copy.deepcopy(claims)
    _claim(changed, "piece_mass")["value"] = 737
    with pytest.raises(SourceAuditError, match="PDF value differs from transcription: piece_mass"):
        run(altered_claims=changed)


def test_coherent_origin_percentages_cannot_replace_pdf_values(packet):
    claims, _, run = packet
    changed = copy.deepcopy(claims)
    _claim(changed, "norway_wheat_share")["value"] = 66
    _claim(changed, "poland_wheat_share")["value"] = 34
    with pytest.raises(SourceAuditError):
        run(altered_claims=changed)


@pytest.mark.parametrize("key,field,value", [
    ("mill_electricity", "unit", "kWh/t_wheat"),
    ("bakery_electricity", "unit", "kWh/kg_bread"),
    ("retail_bread_waste", "base", "Bread entering retail only"),
    ("wheat_refined_flour_economic_allocation", "base", "Mass fraction of flour output"),
    ("consumer_bread_waste_estimate", "provenance", "weighed_household_operational_observations"),
    ("survey_respondents", "provenance", "identified_product_consumers"),
    ("piece_mass", "source", "survey"),
    ("piece_mass", "classification", "causally_identified"),
])
def test_claim_semantics_are_checked_separately_from_numbers(packet, key, field, value):
    claims, _, run = packet
    changed = copy.deepcopy(claims)
    _claim(changed, key)[field] = value
    with pytest.raises(SourceAuditError):
        run(altered_claims=changed)


@pytest.mark.parametrize("key,field,value", [
    ("piece_mass", "pdf_page", 7), ("piece_mass", "printed_page", 7),
    ("piece_mass", "section", "4.3"),
    ("mill_electricity", "table", "3"),
    ("mill_electricity", "row", "Transport from mill to baker"),
    ("mill_electricity", "column", "Unreported"),
    ("survey_respondents", "pdf_page", 3),
])
def test_wrong_locator_does_not_pass_on_nearby_matching_number(packet, key, field, value):
    claims, _, run = packet
    changed = copy.deepcopy(claims)
    _claim(changed, key)["locator"][field] = value
    with pytest.raises(SourceAuditError):
        run(altered_claims=changed)


def test_coherent_survey_counts_and_percentages_are_extracted_not_memorized(packet):
    _, table, run = packet
    changed = copy.deepcopy(table)
    first, second = changed["categories"][:2]
    first["count"] += 1
    second["count"] -= 1
    first["reported_percent"] = "43.0"
    second["reported_percent"] = "30.0"
    assert sum(row["count"] for row in changed["categories"]) == changed["reported_total"]
    with pytest.raises(SourceAuditError):
        run(altered_table=changed)


@pytest.mark.parametrize("defect", ["row_swap", "label_swap", "closed_open", "bounded_unknown", "known_unknown", "unknown_key"])
def test_survey_rows_and_open_unknown_bounds_cannot_be_reinterpreted(packet, defect):
    _, table, run = packet
    changed = copy.deepcopy(table)
    categories = changed["categories"]
    if defect == "row_swap":
        categories[0], categories[1] = categories[1], categories[0]
    elif defect == "label_swap":
        categories[0]["label"], categories[1]["label"] = categories[1]["label"], categories[0]["label"]
    elif defect == "closed_open":
        categories[-2]["max_slices"] = 24
    elif defect == "bounded_unknown":
        categories[-1]["max_slices"] = 0
    elif defect == "known_unknown":
        categories[-1]["min_slices"] = 0
    else:
        categories[0]["key"] = "not_reported"
    with pytest.raises(SourceAuditError):
        run(altered_table=changed)


@pytest.mark.parametrize("field,value", [
    ("measure", "Observed grams of waste per person per day"),
    ("reported_total", 1001),
])
def test_survey_measure_and_denominator_remain_reported_contract(packet, field, value):
    _, table, run = packet
    changed = copy.deepcopy(table)
    changed[field] = value
    with pytest.raises(SourceAuditError):
        run(altered_table=changed)


@pytest.mark.parametrize("document,field,value", [
    ("claims", "doi", "https://doi.org/10.0000/unsupported"),
    ("claims", "visible_file", "source_survey.pdf"),
    ("table", "doi", "10.0000/unsupported"),
    ("table", "locator", "Table 1, printed page 3 of 15 (PDF page 3)"),
    ("table", "archive", "source_lca.pdf"),
])
def test_source_provenance_metadata_is_validated(packet, document, field, value):
    claims, table, run = packet
    if document == "claims":
        changed = copy.deepcopy(claims)
        changed["sources"]["lca"][field] = value
        kwargs = {"altered_claims": changed}
    else:
        changed = copy.deepcopy(table)
        changed["source"][field] = value
        kwargs = {"altered_table": changed}
    with pytest.raises(SourceAuditError):
        run(**kwargs)


@pytest.mark.parametrize("defect", ["duplicate", "missing", "unknown"])
def test_claim_set_has_exact_unique_registered_keys(packet, defect):
    claims, _, run = packet
    changed = copy.deepcopy(claims)
    if defect == "duplicate":
        changed["claims"].append(copy.deepcopy(changed["claims"][0]))
    elif defect == "missing":
        changed["claims"].pop()
    else:
        changed["claims"][0]["key"] = "unsupported_fact"
    with pytest.raises(SourceAuditError):
        run(altered_claims=changed)


def test_duplicate_json_key_is_rejected_before_semantic_audit(tmp_path):
    claims_path = tmp_path / "claims.json"
    raw = CLAIMS.read_text()
    claims_path.write_text(raw.replace('"schema": 1', '"schema": 1, "schema": 1', 1))
    with pytest.raises(SourceAuditError):
        auditor.audit_bread_sources(claims_path, TABLE, PDFS)


def test_pdf_alteration_remains_rejected_when_local_metadata_is_rehashed(tmp_path, packet):
    claims, table, run = packet
    pdf_root = tmp_path / "pdfs"
    pdf_root.mkdir()
    for name in ("source_lca.pdf", "source_survey.pdf"):
        shutil.copyfile(PDFS / name, pdf_root / name)
    altered = (pdf_root / "source_lca.pdf").read_bytes() + b"\nchanged archived bytes\n"
    (pdf_root / "source_lca.pdf").write_bytes(altered)
    changed = copy.deepcopy(claims)
    changed["sources"]["lca"]["sha256"] = hashlib.sha256(altered).hexdigest()
    changed["sources"]["lca"]["bytes"] = len(altered)
    with pytest.raises(SourceAuditError):
        run(altered_claims=changed, altered_table=table, pdf_root=pdf_root)


def test_cli_positive_creates_explicit_json_result(tmp_path):
    output = tmp_path / "result.json"
    process = subprocess.run([sys.executable, str(ROOT / "scripts/audit_bread_sources.py"),
        "--claims", str(CLAIMS), "--table", str(TABLE), "--pdf-root", str(PDFS),
        "--output", str(output)], capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stderr
    assert json.loads(output.read_bytes())["passed"] is True
