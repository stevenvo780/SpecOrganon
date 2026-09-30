"""Audit the exposed bread transcription against pinned PDF passages.

The published numbers are extracted, never taken from a numeric answer table.
Semantic bases/provenance are checked against an explicitly reviewed contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

from specorganon.source_passages import (
    ExtractorSpec, SourceAuditError, SourceSpec, extract_passage, read_pdf_pages,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLAIMS = ROOT / "cases/bread_development/source_claims.json"
DEFAULT_TABLE = ROOT / "cases/bread_norway/survey_table1.json"
DEFAULT_PDFS = ROOT / "cases/bread_norway"
CONTRACT = ROOT / "experiments/development/bread_source_audit_2026-09-30/contract.json"


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SourceAuditError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise SourceAuditError(f"nonfinite JSON number: {value}")


def _load(path: Path) -> tuple[dict, dict]:
    try:
        raw = path.read_bytes()
        if len(raw) > 131_072:
            raise SourceAuditError("JSON input too large")
        value = json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceAuditError(f"cannot read valid JSON: {path.name}") from exc
    if type(value) is not dict:
        raise SourceAuditError("JSON input must be an object")
    return value, {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _same(actual: object, expected: object, label: str) -> None:
    # JSON serialization also distinguishes booleans from integers in metadata.
    if json.dumps(actual, sort_keys=True, allow_nan=False) != json.dumps(
        expected, sort_keys=True, allow_nan=False,
    ):
        raise SourceAuditError(f"reviewed unit/base/locator/provenance differs: {label}")


def _numeric(value: object, label: str) -> Decimal:
    if type(value) not in (int, float):
        raise SourceAuditError(f"numeric claim has invalid type: {label}")
    result = Decimal(str(value))
    if not result.is_finite():
        raise SourceAuditError(f"numeric claim not finite: {label}")
    return result


def audit_bread_sources(
    claims_path: Path = DEFAULT_CLAIMS, table_path: Path = DEFAULT_TABLE,
    pdf_root: Path = DEFAULT_PDFS,
) -> dict:
    contract, contract_pin = _load(CONTRACT)
    claims, claims_pin = _load(claims_path)
    table, table_pin = _load(table_path)
    expected_claim_fields = set(contract["claim_document_metadata"]) | {"sources", "claims"}
    if set(claims) != expected_claim_fields:
        raise SourceAuditError("claim document fields differ")
    _same({k: claims[k] for k in contract["claim_document_metadata"]},
          contract["claim_document_metadata"], "claim document")
    _same(claims["sources"], contract["sources"], "PDF source identity")
    if set(table) != set(contract["survey_metadata"]) | {"reported_total", "categories"}:
        raise SourceAuditError("survey document fields differ")
    _same({k: table[k] for k in contract["survey_metadata"]},
          contract["survey_metadata"], "survey identity/measure")

    if type(claims["claims"]) is not list:
        raise SourceAuditError("claims must be a list")
    indexed = {}
    for item in claims["claims"]:
        if type(item) is not dict or type(item.get("key")) is not str:
            raise SourceAuditError("claim shape/key invalid")
        key = item["key"]
        if key in indexed or key not in contract["claims"]:
            raise SourceAuditError("claim key duplicate or unregistered")
        metadata = contract["claims"][key]["metadata"]
        if set(item) != set(metadata) | {"key", "value"}:
            raise SourceAuditError("claim fields differ")
        _same({k: item[k] for k in metadata}, metadata, key)
        _numeric(item["value"], key)
        indexed[key] = item
    if set(indexed) != set(contract["claims"]):
        raise SourceAuditError("claim set incomplete")

    categories = table["categories"]
    expected_categories = contract["survey_categories"]
    if type(categories) is not list or len(categories) != len(expected_categories):
        raise SourceAuditError("survey categories incomplete")
    for row, expected in zip(categories, expected_categories, strict=True):
        if type(row) is not dict or set(row) != set(expected) | {"count", "reported_percent"}:
            raise SourceAuditError("survey row fields differ")
        _same({k: row[k] for k in expected}, expected, "survey row/bounds")
        if type(row["count"]) is not int or row["count"] < 0:
            raise SourceAuditError("survey count must be a nonnegative integer")
        if (type(row["reported_percent"]) is not str
                or re.fullmatch(r"\d+\.\d", row["reported_percent"]) is None):
            raise SourceAuditError("survey percentage must be a printed decimal string")
    if type(table["reported_total"]) is not int or table["reported_total"] <= 0:
        raise SourceAuditError("survey total must be a positive integer")

    pdfs = {
        name: read_pdf_pages(pdf_root / identity["visible_file"],
                             SourceSpec(identity["bytes"], identity["sha256"]),
                             ExtractorSpec(Path(contract["extractor"]["path"]),
                                           contract["extractor"]["sha256"]))
        for name, identity in contract["sources"].items()
    }
    passages = {}
    for name, selector in contract["selectors"].items():
        pdf = pdfs[selector["source"]]
        page = selector["page"]
        # These fixed articles have physical and printed pagination in agreement.
        if re.search(rf"\b{page} of \d+\b", pdf.pages[page - 1].splitlines()[0]) is None:
            raise SourceAuditError("printed and physical page disagree")
        try:
            passages[name] = extract_passage(
                pdf, page, selector["start"], selector["end"], selector["pattern"],
                tuple(selector["required"]),
            )
        except SourceAuditError as exc:
            raise SourceAuditError(f"{name}: {exc}") from exc
    verified = {}
    for key, binding in contract["claims"].items():
        passage = passages[binding["selector"]]
        extracted = Decimal(passage["groups"][binding["group"]])
        if _numeric(indexed[key]["value"], key) != extracted:
            raise SourceAuditError(f"PDF value differs from transcription: {key}")
        verified[key] = {
            **binding["metadata"], "value": str(extracted),
            "passage": binding["selector"], "passed": True,
        }
    total_groups = passages["survey_total"]["groups"]
    extracted_total = int(total_groups["survey_respondents"])
    if table["reported_total"] != extracted_total:
        raise SourceAuditError("survey total differs from PDF")
    verified_rows = []
    for row in categories:
        selector_name = "survey_" + row["key"]
        groups = passages[selector_name]["groups"]
        if row["count"] != int(groups["count"]) or row["reported_percent"] != groups["percent"]:
            raise SourceAuditError(f"survey row differs from PDF: {row['key']}")
        if Decimal(row["reported_percent"]) != Decimal(row["count"]) * 100 / extracted_total:
            raise SourceAuditError("survey printed percentage inconsistent with count")
        verified_rows.append({**row, "passage": selector_name, "passed": True})
    if (sum(row["count"] for row in categories) != extracted_total
            or sum(Decimal(row["reported_percent"]) for row in categories)
            != Decimal(total_groups["total_percent"])
            or Decimal(total_groups["total_percent"]) != 100):
        raise SourceAuditError("survey totals inconsistent")

    prose = passages["survey_prose"]["groups"]["bins"]
    prose_intervals = re.findall(r"\d+–\d+|more than \d+", prose)
    table_intervals = [re.sub(r" slices$", "", row["label"]).casefold()
                       for row in categories if "–" in row["label"] or "More than" in row["label"]]
    warnings = []
    if prose_intervals != table_intervals:
        warnings.append({
            "code": "survey_prose_table_category_disagreement", "source": "survey",
            "prose_page": 3, "table_page": 4, "prose_bins": prose,
            "table_bins": [row["label"] for row in categories],
            "decision": "transcribe Table 1; preserve disagreement, no silent reconciliation",
        })
    prose_table = passages["waste_cross_reference"]["groups"]["table"]
    waste_table = contract["claims"]["retail_bread_waste"]["metadata"]["locator"]["table"]
    if prose_table != waste_table:
        warnings.append({
            "code": "lca_prose_table_cross_reference_disagreement", "source": "lca",
            "prose_page": 7, "prose_table": prose_table, "verified_table": waste_table,
            "decision": "locate Table 7 on page 8; preserve prose cross-reference error",
        })
    return {
        "schema": 1, "study_id": "D100", "passed": True,
        "scope": "published transcription fidelity, not field resolution or causal validity",
        "verified_claims": len(verified), "verified_survey_rows": len(verified_rows),
        "base_validation": "reviewed_contract_consistency",
        "input_pins": {"claims": claims_pin, "table": table_pin, "contract": contract_pin},
        "source_extraction": {
            name: {"bytes": pdf.source_bytes, "sha256": pdf.source_sha256,
                   "text_sha256": pdf.text_sha256, "pages": len(pdf.pages),
                   "extractor_version": pdf.extractor_version,
                   "extractor_path": pdf.extractor_path,
                   "extractor_sha256": pdf.extractor_sha256,
                   "extractor_execution": "sealed_memfd_verified_binary",
                   "host_shared_libraries_authenticated": False}
            for name, pdf in pdfs.items()
        },
        "claims": verified, "survey_rows": verified_rows, "passages": passages,
        "survey_total": extracted_total, "warnings": warnings, "limits": contract["limits"],
        "Q": None, "field_intervention": False, "global_acceptance": "0/5",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--pdf-root", type=Path, default=DEFAULT_PDFS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = audit_bread_sources(args.claims, args.table, args.pdf_root)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(rendered)
        else:
            sys.stdout.write(rendered)
    except (SourceAuditError, OSError) as exc:
        print(f"source audit rejected: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
