"""Prepare D108 documentary energy lineage; never apply puts or approve norms.

Usage: python -I -B SCRIPT REPO NEWOUTPUT. Inputs and their committed Git blobs
are checked before creating any output. Division is audited here, not delegated
to the toolkit's generic put or its product-only calculation field.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import sys

DOSSIER = "experiments/development/bread_energy_derivation_2026-09-30"
CASE_FILES = ("organon.json", "source_claims.json", "source_lca.pdf", "source_survey.pdf",
              "survey_table1.json", "audit_contract.json", "audit_report.json")
KEYS = ("piece_mass", "bakery_electricity", "bakery_natural_gas")
NEW_IDS = ("pr_energy_documentary", "inf_energy_documentary", "e_energy_documentary", "i_energy_documentary")
POPULATION = "commercial bread product studied in the published Norwegian article"
METRIC = "documentary_bakery_carrier_energy_per_produced_bread_kg"
UNIT = "kWh/kg produced bread"
DATE = "2018-12-21"
UNCERTAINTY = "not quantified by the public record; reported decimal inputs treated as exact only for documentary arithmetic"
EXPECTED = {
    "piece_mass": ("736", "g/piece", "One commercial loaf, bread mass after baking",
                   {"pdf_page": 6, "printed_page": 6, "section": "4.2", "table": None, "row": "First paragraph", "column": None}),
    "bakery_electricity": ("0.297", "kWh/piece", "One commercial loaf of the studied bread",
                          {"pdf_page": 8, "printed_page": 8, "section": "4.6", "table": "5", "row": "Baker energy consumption", "column": "Data"}),
    "bakery_natural_gas": ("0.115", "kWh/piece", "One commercial loaf of the studied bread",
                          {"pdf_page": 8, "printed_page": 8, "section": "4.6", "table": "5", "row": "Baker energy consumption", "column": "Data"}),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= 16 * 1024 * 1024, "input is not bounded regular public file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(16 * 1024 * 1024 + 1)
        require(len(raw) <= 16 * 1024 * 1024, "input exceeds byte bound")
        return raw
    finally:
        os.close(descriptor)


def decode(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, "duplicate JSON key: " + key)
            result[key] = value
        return result

    def constant(value):
        raise ValueError("nonfinite JSON constant: " + value)

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def git_bytes(repo, name):
    return subprocess.check_output(["git", "--no-optional-locks", "show", "HEAD:" + name],
                                   cwd=repo, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})


def inputs(repo):
    plan_raw, record_raw = read(repo / DOSSIER / "plan.json"), read(repo / DOSSIER / "plan_inputs.json")
    require(plan_raw == git_bytes(repo, DOSSIER + "/plan.json") and record_raw == git_bytes(repo, DOSSIER + "/plan_inputs.json"),
            "prospective plan/input record differs from committed HEAD")
    plan, record = decode(plan_raw), decode(record_raw)
    source = {}
    for name, row in record["files"].items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "noncanonical source path")
        path = repo / name
        require(path.resolve(strict=True).is_relative_to(repo), "source escapes repository")
        raw = read(path)
        require(pin(raw) == {k: row[k] for k in ("bytes", "sha256")} and raw == git_bytes(repo, name), "live/Git source pin differs: " + name)
        source[name] = raw
    base = record["source_case"]["path"]
    require(all(base + "/" + name in source for name in CASE_FILES), "seven public source-case files required")
    return plan, record, source


def number(value):
    require(not isinstance(value, bool) and isinstance(value, (str, int, float)), "unsupported documentary number")
    if isinstance(value, float):
        require(math.isfinite(value), "nonfinite documentary number")
    result = Decimal(str(value))
    require(result.is_finite(), "nonfinite documentary number")
    return result


def derive(items, claims_document, pdf_pin, scope):
    """Pure contract validation and exact arithmetic; no filesystem/engine writes."""
    require(scope["population"] == POPULATION and scope["publication_date"] == DATE
            and scope["business_record_date"] == "unknown" and scope["metric"] == METRIC
            and scope["unit"] == UNIT and scope["measurement_and_aggregation_uncertainty"] == UNCERTAINTY,
            "documentary date/population/metric/unit/uncertainty scope differs")
    require(scope["formula"] == "(0.297 + 0.115) / (736 / 1000)"
            and scope["representation_error_limit"] == "5e-25"
            and scope["representation_limit_is_physical_uncertainty_or_efficacy_threshold"] is False
            and scope["piece_mass_unit"] == "g/piece" and scope["carrier_energy_unit"] == "kWh/piece"
            and scope["representation"] == "24 decimal places, ROUND_HALF_EVEN; exact rational retained"
            and scope["not_inferred"] == ["observed lot", "current baseline", "emissions", "cost", "useful energy", "causal effect", "value equivalence"],
            "formula or representation-only contract differs")
    require(type(scope["numerator"]) is int and type(scope["denominator"]) is int
            and (scope["numerator"], scope["denominator"]) == (103, 184), "expected exact fraction differs")
    claim_list = claims_document["claims"]
    require(isinstance(claim_list, list), "source claims must remain a keyed list")
    claims = {row["key"]: row for row in claim_list}
    require(len(claims) == len(claim_list), "duplicate source claim key")
    publication = claims_document["sources"]["lca"]
    require(publication["visible_file"] == "source_lca.pdf" and publication["sha256"] == pdf_pin["sha256"]
            and publication["bytes"] == pdf_pin["bytes"], "published PDF metadata/hash differs")
    source_records = []
    for key in KEYS:
        item = items["e_" + key]
        claim = claims[key]
        data = item["data"]
        value, unit, base, locator = EXPECTED[key]
        require(item["kind"] == "evidence" and type(item["version"]) is int and item["version"] == 1,
                "source item kind/version differs: " + key)
        require(claim["source"] == "lca" and claim["classification"] == "reported"
                and number(claim["value"]) == Decimal(value) and number(data["value"]) == Decimal(value),
                "source claim/evidence value differs: " + key)
        require(claim["unit"] == data["unit"] == unit and claim["base"] == data["base"] == base,
                "source unit/base differs: " + key)
        require(claim["locator"] == data["audited_locator"] == locator and decode(data["locator"]) == locator,
                "source localizer differs: " + key)
        require(data["origin"] == "published" and data["classification"] == "reported"
                and data["metric_key"] == key and data["source"] == publication["doi"]
                and data["archive"] == "source_lca.pdf" and data["source_sha256"] == pdf_pin["sha256"]
                and data["date"] == DATE and data["scope"] == "published_historical_documentary_quantity_not_current_lot"
                and data["provenance"] == claim["provenance"],
                "source provenance/date/scope differs: " + key)
        source_records.append({"item_id": "e_" + key, "version": 1, "claim_key": key, "value": value,
                               "unit": unit, "base": base, "locator": locator, "source_sha256": pdf_pin["sha256"],
                               "archive": "source_lca.pdf", "publication_date": DATE, "business_record_date": "unknown",
                               "provenance": claim["provenance"], "origin": "published"})
    for key in ("pr_docs", "q_docs", "h_docs", "n_harm", "p_refined"):
        require(type(items[key]["version"]) is int and items[key]["version"] == 1, "original graph version differs: " + key)
    mass = Fraction(number(claims["piece_mass"]["value"])) / 1000
    electricity = Fraction(number(claims["bakery_electricity"]["value"]))
    gas = Fraction(number(claims["bakery_natural_gas"]["value"]))
    exact = (electricity + gas) / mass
    require(exact == Fraction(103, 184), "independent arithmetic does not yield 103/184")
    with localcontext() as context:
        context.prec = 80
        rounded = (Decimal(exact.numerator) / Decimal(exact.denominator)).quantize(Decimal("1e-24"), rounding=ROUND_HALF_EVEN)
    value = format(rounded, ".24f")
    error = abs(Fraction(value) - exact)
    require(error <= Fraction(5, 10**25), "rounded representation exceeds 5e-25")
    return {"schema": 1, "classification": "exposed_documentary_bakery_energy_derivation", "sources": source_records,
            "source_claims_pin": pin(encode(claims_document)), "pdf_pin": pdf_pin,
            "context": copy.deepcopy(scope), "formula": scope["formula"],
            "mass_kg_per_piece": {"numerator": mass.numerator, "denominator": mass.denominator, "unit": "kg/piece"},
            "carrier_energy_sum_per_piece": {"numerator": (electricity + gas).numerator, "denominator": (electricity + gas).denominator, "unit": "kWh/piece"},
            "exact_ratio": {"numerator": exact.numerator, "denominator": exact.denominator},
            "representation": {"value": value, "decimal_places": 24, "rounding": "ROUND_HALF_EVEN",
                 "actual_abs_error": {"numerator": error.numerator, "denominator": error.denominator},
                 "maximum_abs_error": "5e-25", "bound_is_representation_only": True},
            "metric": METRIC, "unit": UNIT, "population": POPULATION, "publication_date": DATE,
            "business_record_date": "unknown", "physical_uncertainty": UNCERTAINTY,
            "generic_put_checks_this_arithmetic_semantically": False,
            "physical_source_truth_authenticated": False, "external_custody_authenticated": False,
            "intervention_thresholds_set": False, "field_efficacy_or_safety_demonstrated": False,
            "supports_existing_four_intervention_indicators": False}


def prepare_manifest(items, derivation, archive_sha):
    performed = datetime.fromisoformat(derivation["derivation_performed_at_utc"])
    require(performed.tzinfo is not None and performed.utcoffset().total_seconds() == 0,
            "actual derivation timestamp must be UTC")
    versions = {key: item["version"] for key, item in items.items()}
    require(not any(key in items for key in NEW_IDS), "new documentary IDs already exist")
    steps = []

    def put(item_id, kind, text, refs, data):
        require(len(refs) == len(set(refs)) and all(ref in versions for ref in refs), "invalid prospective dependencies")
        steps.append({"op": "put", "id": item_id, "kind": kind, "text": text, "refs": refs,
                      "data": data, "expected_version": 0, "expected_deps": {ref: versions[ref] for ref in refs}})
        versions[item_id] = 1

    sources = ["e_" + key for key in KEYS]
    put(NEW_IDS[0], "protocol", "Documentary derivation for the published commercial bread: normalize carrier energy by produced bread mass; do not interpret arithmetic precision as physical accuracy or intervention benefit.",
        ["pr_docs", "q_docs", "h_docs", *sources],
        {"population": POPULATION, "method": "Validate three version-pinned published quantities, units, bases and PDF localizers; recompute exact rational and 24-place HALF_EVEN representation in this pinned builder.",
         "comparison": "Published electricity plus gas per loaf, normalized by the same studied loaf's after-baking mass; no intervention comparator",
         "uncertainty": UNCERTAINTY, "publication_date": DATE, "business_record_date": "unknown"})
    put(NEW_IDS[1], "inference", "Published literals yield (0.297+0.115)/(736/1000)=103/184 kWh/kg produced bread. This documentary sum is not useful energy, emissions, cost, a current lot baseline or causal efficacy.",
        [*sources, NEW_IDS[0]], {"classification": "documentary_arithmetic_inference", "population": POPULATION,
                             "publication_date": DATE, "business_record_date": "unknown", "physical_uncertainty": UNCERTAINTY})
    representation = derivation["representation"]
    shared = {"value": representation["value"], "unit": UNIT, "exact_ratio": derivation["exact_ratio"],
              "decimal_places": 24, "rounding": "ROUND_HALF_EVEN", "tolerance": "5e-25",
              "max_abs_representation_error": "5e-25", "actual_abs_representation_error": representation["actual_abs_error"],
              "representation_precision_is_not_measurement_accuracy": True,
              "representation_limit_is_physical_uncertainty_or_efficacy_threshold": False,
              "population": POPULATION, "publication_date": DATE, "business_record_date": "unknown",
              "physical_uncertainty": UNCERTAINTY, "scope": "published_studied_product_documentary_energy_per_produced_bread_kg",
              "base": "One kg of after-baking produced bread of the studied commercial product",
              "not_inferred": copy.deepcopy(derivation["context"]["not_inferred"])}
    put(NEW_IDS[2], "evidence", "Derived documentary carrier-energy intensity, with exact rational and rounded representation bound to derivation.json. Generic put does not audit division or authenticate physical sources.",
        [NEW_IDS[0], NEW_IDS[1], *sources],
        {**shared, "origin": "derived", "source": "derivation.json", "archive": "derivation.json",
         "source_sha256": archive_sha, "date": performed.date().isoformat(),
         "source_publication_date": DATE, "derivation_performed_at_utc": performed.isoformat(),
         "locator": "/representation/value", "exact_ratio_locator": "/exact_ratio", "metric_key": METRIC,
         "physical_source_truth_authenticated": False, "field_impact_assessed": False})
    put(NEW_IDS[3], "indicator", "Documentary scalar for bakery carrier energy per kg produced bread; no intervention target, efficacy threshold, useful-energy or value-equivalence claim.",
        [NEW_IDS[2], NEW_IDS[0], "n_harm", "p_refined"], {**shared, "metric": METRIC, "classification": "documentary_development_indicator"})
    return {"schema": 1, "steps": steps}


def build(repo, output):
    repo = repo.resolve(strict=True)
    plan, record, source = inputs(repo)
    base = record["source_case"]["path"]
    ledger_raw = source[base + "/organon.json"]
    ledger = decode(ledger_raw)
    require(len(ledger["events"]) == plan["source_events"] == 64 and ledger["events"][-1]["hash"] == record["source_case"]["head"]
            and ledger["project"] == record["source_case"]["project"] and ledger["project"]["approval_policy"] == "signed",
            "source64 prefix/head/signed project differs")
    items = {e["payload"]["id"]: copy.deepcopy(e["payload"]) for e in ledger["events"] if e["kind"] == "item_put"}
    require(all(items[key]["version"] == version for key, version in plan["source_versions"].items()), "source versions differ from plan")
    derivation = derive(items, decode(source[base + "/source_claims.json"]), pin(source[base + "/source_lca.pdf"]), plan["derivation"])
    derivation["source_claims_pin"] = pin(source[base + "/source_claims.json"])
    derivation["source_ledger_pin"] = pin(ledger_raw)
    derivation["source_publication_date"] = DATE
    derivation["derivation_performed_at_utc"] = datetime.now(timezone.utc).isoformat()
    archive_raw = encode(derivation)
    manifest = prepare_manifest(items, derivation, pin(archive_raw)["sha256"])
    require([step["id"] for step in manifest["steps"]] == list(NEW_IDS), "four additions differ")
    require(not output.exists() and not output.is_symlink(), "builder output must be new")
    output = output.parent.resolve(strict=True) / output.name
    require(not output.is_relative_to(repo), "builder output must be outside repository")
    output.mkdir(mode=0o700)
    case = output / "case"
    case.mkdir(mode=0o700)
    for name in CASE_FILES:
        with (case / name).open("xb") as stream:
            stream.write(source[base + "/" + name])
    for path, raw in [(case / "derivation.json", archive_raw), (output / "manifest.json", encode(manifest))]:
        with path.open("xb") as stream:
            stream.write(raw)
    receipt = {"schema": 1, "study_id": "D108", "state": "prepared", "puts_applied": 0,
               "source_case": record["source_case"], "source_pins": {name: pin(raw) for name, raw in source.items()},
               "derivation_pin": pin(archive_raw), "manifest_pin": pin(encode(manifest)),
               "builder_source_pin": pin(read(Path(__file__))), "constraints": plan["scope_limits"],
               "no_cli_mcp_or_engine_execution": True, "norms_approved": False}
    with (output / "receipt.json").open("xb") as stream:
        stream.write(encode(receipt))
    require(read(case / "organon.json") == ledger_raw, "preparation altered source64 ledger")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        receipt = build(args.repo, args.output)
        print(json.dumps({"state": receipt["state"], "derivation_pin": receipt["derivation_pin"]}))
        return 0
    except Exception as exc:
        print(json.dumps({"state": "failed", "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
