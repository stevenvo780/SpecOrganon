#!/usr/bin/env python3
"""Local documentary calculation; standard Python, with pdftotext for passage checks.

Usage: python3 analysis.py input > metrics.json
No observations of field efficacy or approval are created by this program.
"""
import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    def reject_constant(value):
        raise ValueError("nonfinite JSON constant: " + value)
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def quantity(value, unit, base, **extra):
    return {"value": value, "unit": unit, "base": base, **extra}


def calculate(directory):
    root = directory.resolve(strict=True)
    require(root.is_dir(), "input must be a directory")
    manifest_path = root / "source_manifest.json"
    manifest = load(manifest_path)
    require(manifest.get("schema") == 1, "unsupported source manifest schema")
    files = {}
    required_names = {"task.md", "source_claims.json", "survey_table1.json",
                      "source_lca.pdf", "source_survey.pdf"}
    for entry in manifest["files"]:
        name = entry["visible_file"]
        require(isinstance(name, str) and Path(name).name == name,
                "manifest names must be visible relative basenames")
        require(name not in files, "duplicate manifest name: " + name)
        path = (root / name).resolve(strict=True)
        require(path.parent == root, "input escapes declared directory: " + name)
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        require(len(data) == entry["bytes"], "byte count mismatch: " + name)
        require(digest == entry["sha256"], "SHA-256 mismatch: " + name)
        files[name] = {"sha256": digest, "bytes": len(data), "match": True}
    require(set(files) == required_names, "unexpected or missing manifest inputs")
    files["source_manifest.json"] = {
        "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "bytes": manifest_path.stat().st_size,
        "match": None,
        "reason": "manifest has no independent hash anchor inside this package",
    }
    claims_doc = load(root / "source_claims.json")
    table = load(root / "survey_table1.json")
    require(claims_doc.get("schema") == table.get("schema") == 1,
            "unsupported transcription schema")
    claims = {}
    units = {
        "piece_mass": "g/piece", "norway_wheat_share": "%",
        "poland_wheat_share": "%", "mill_electricity": "kWh/t_flour",
        "mill_to_baker_distance": "km", "bakery_electricity": "kWh/piece",
        "bakery_natural_gas": "kWh/piece", "bakery_bread_waste": "%",
        "retail_bread_waste": "%", "consumer_bread_waste_estimate": "%",
        "survey_respondents": "respondents",
        **{"wheat_" + product + "_mass_share": "% w/w"
           for product in ("refined_flour", "whole_flour", "bran")},
        **{"wheat_" + product + "_economic_allocation": "%"
           for product in ("refined_flour", "whole_flour", "bran")},
    }
    for key, source in claims_doc["sources"].items():
        name = source["visible_file"]
        require(name in files, "unmanifested source: " + name)
        require(source["sha256"] == files[name]["sha256"] and
                source["bytes"] == files[name]["bytes"], "source metadata mismatch: " + key)
    for claim in claims_doc["claims"]:
        key, value = claim["key"], claim["value"]
        require(key in units and key not in claims, "unknown or duplicate claim: " + key)
        require(claim["unit"] == units[key], "unit mismatch: " + key)
        require(isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and value >= 0, "invalid number: " + key)
        require(claim["source"] in claims_doc["sources"], "unknown source: " + key)
        require(claim["base"] and claim["classification"] == "reported",
                "missing base or unexpected classification: " + key)
        require(isinstance(claim["locator"]["pdf_page"], int)
                and claim["locator"]["pdf_page"] > 0, "invalid page: " + key)
        if claim["unit"].startswith("%"):
            require(value <= 100, "percentage out of range: " + key)
        claims[key] = claim
    require(set(claims) == set(units), "required claims missing")
    require(claims["piece_mass"]["value"] > 0, "nonpositive loaf mass")
    require(claims["norway_wheat_share"]["value"] +
            claims["poland_wheat_share"]["value"] == 100, "origin shares do not sum to 100")

    page_cache = {}
    def page(file_name, number):
        cache_key = (file_name, number)
        if cache_key not in page_cache:
            result = subprocess.run(
                ["pdftotext", "-layout", "-f", str(number), "-l", str(number),
                 str(root / file_name), "-"], capture_output=True, text=True,
                timeout=20, check=False)
            require(result.returncode == 0,
                    "PDF extraction failed: " + file_name + ": " + result.stderr.strip())
            page_cache[cache_key] = re.sub(r"\s+", " ", result.stdout).strip()
        return page_cache[cache_key]

    number = r"([0-9]+(?:\.[0-9]+)?)"
    mass_row = r"Wheat flour products \(% w/w\)\s+" + number + r"% refined flour,\s+" + number + r"% whole flour,\s+" + number + r"% bran"
    allocation_row = r"Wheat, economic allocation factors\s+Refined flour " + number + r"%, whole flour " + number + r"%, bran " + number + r"%"
    bakery_row = r"Baker energy consumption\s+" + number + r" kWh electricity and " + number + r" kWh natural gas per bread"
    patterns = {
        "piece_mass": (r"total mass of the bread itself was " + number + r" grams", 1),
        "norway_wheat_share": (r"average of " + number + r"% of the wheat has been coming from Norway", 1),
        "poland_wheat_share": (r"remaining " + number + r"% from Poland", 1),
        "mill_electricity": (r"Mill energy consumption\s+" + number + r" kWh electricity per ton of flour produced", 1),
        "mill_to_baker_distance": (r"Transport from mill to baker\s+" + number + r" km on >32 tonne truck", 1),
        "bakery_electricity": (bakery_row, 1), "bakery_natural_gas": (bakery_row, 2),
        "bakery_bread_waste": (r"Bakery waste\s+" + number, 1),
        "retail_bread_waste": (r"Retail waste\s+" + number, 1),
        "consumer_bread_waste_estimate": (r"Consumer waste\s+" + number, 1),
        "survey_respondents": (r"Total\s+" + number + r"\s+100\.0", 1),
    }
    for index, product in enumerate(("refined_flour", "whole_flour", "bran"), 1):
        patterns["wheat_" + product + "_mass_share"] = (mass_row, index)
        patterns["wheat_" + product + "_economic_allocation"] = (allocation_row, index)
    audited = []
    for key, claim in claims.items():
        file_name = claims_doc["sources"][claim["source"]]["visible_file"]
        pattern, group = patterns[key]
        match = re.search(pattern, page(file_name, claim["locator"]["pdf_page"]), re.I)
        require(match is not None, "quantity passage not located: " + key)
        observed = Decimal(match.group(group))
        require(observed == Decimal(str(claim["value"])), "quantity differs from PDF passage: " + key)
        audited.append({"key": key, "result": "passage_matched",
                        "reported_value": claim["value"], "observed_value": float(observed),
                        "unit": claim["unit"], "base": claim["base"],
                        "file": file_name, "sha256": files[file_name]["sha256"],
                        "locator": claim["locator"], "matched_passage": match.group(0),
                        "provenance": claim["provenance"]})

    require(table["source"]["archive"] == "source_survey.pdf" and
            table["source"]["sha256"] == files["source_survey.pdf"]["sha256"],
            "survey source metadata mismatch")
    expected = {
        "zero": ("Zero slices", 0, 0), "one_to_three": ("1–3 slices", 1, 3),
        "four_to_six": ("4–6 slices", 4, 6), "seven_to_nine": ("7–9 slices", 7, 9),
        "ten_to_twelve": ("10–12 slices", 10, 12),
        "more_than_twelve": ("More than 12 slices", 13, None),
        "do_not_know": ("Do not know", None, None),
    }
    rows = {}
    table_audit = []
    for row in table["categories"]:
        key = row["key"]
        require(key in expected and key not in rows, "invalid or repeated survey category")
        require((row["label"], row["min_slices"], row["max_slices"]) == expected[key],
                "category boundaries differ from Table 1: " + key)
        count = row["count"]
        require(isinstance(count, int) and not isinstance(count, bool) and count >= 0,
                "invalid category count: " + key)
        require(Decimal(row["reported_percent"]) == Decimal(count) * 100 / Decimal(table["reported_total"]),
                "count/percentage disagreement: " + key)
        match = re.search(re.escape(row["label"]) + r"\s+(\d+)\s+([0-9.]+)",
                          page("source_survey.pdf", 4))
        require(match is not None and int(match.group(1)) == count and
                Decimal(match.group(2)) == Decimal(row["reported_percent"]),
                "survey row differs from PDF: " + key)
        rows[key] = row
        table_audit.append({"key": key, "result": "label_count_percent_passage_matched",
                            "locator": {"pdf_page": 4, "table": "1", "row": row["label"]},
                            "matched_passage": match.group(0)})
    require(set(rows) == set(expected), "missing survey category")
    total = sum(row["count"] for row in rows.values())
    require(total == table["reported_total"] == claims["survey_respondents"]["value"],
            "survey total mismatch")
    require(total > 0, "empty survey")
    unknown = rows["do_not_know"]["count"]
    open_count = rows["more_than_twelve"]["count"]
    known = total - unknown
    closed = [row for row in rows.values() if row["max_slices"] is not None]
    closed_count = sum(row["count"] for row in closed)
    require(known > 0 and closed_count > 0, "empty known or closed denominator")
    lower_closed = sum(row["count"] * row["min_slices"] for row in closed)
    upper_closed = sum(row["count"] * row["max_slices"] for row in closed)
    lower_known = sum(row["count"] * row["min_slices"]
                      for row in rows.values() if row["min_slices"] is not None)
    prose = page("source_survey.pdf", 3)
    require("0, 1–3, 4–6, 7–10, and more than 10 per week" in prose,
            "methodology interval discrepancy could not be verified")

    value = lambda key: claims[key]["value"]
    wheat_kg = 1000
    products = ("refined_flour", "whole_flour", "bran")
    masses = {product: wheat_kg * value("wheat_" + product + "_mass_share") / 100
              for product in products}
    require(math.isclose(sum(masses.values()), wheat_kg, abs_tol=1e-9), "milling mass shares do not close")
    require(math.isclose(sum(value("wheat_" + product + "_economic_allocation")
                             for product in products), 100, abs_tol=1e-9),
            "economic allocation shares do not sum to 100")
    loaf_kg = value("piece_mass") / 1000
    all_base = "1000 surveyed respondents; household weekly discard, including unknown responses"
    known_base = "967 respondents choosing a known category; household weekly discard"
    closed_base = "948 respondents in closed Table 1 categories; household weekly discard"
    upper_reason = "open category has no finite cap; unknown responses also have no finite cap"
    reported_losses = {key: quantity(value(key), "%", claims[key]["base"],
                                     provenance=claims[key]["provenance"])
                       for key in ("bakery_bread_waste", "retail_bread_waste", "consumer_bread_waste_estimate")}
    return {
        "schema": 1, "case": "D-F", "classification": "exposed_documentary_development",
        "integrity": {"method": "bytes and SHA-256 against local manifest", "files": files,
                      "scope": "integrity does not establish passage correctness, field observations, or independent custody"},
        "milling": {
            "wheat_input": quantity(wheat_kg, "kg", "normalized 1 t wheat entering mill; analyst-selected base"),
            "outputs": {product: quantity(masses[product], "kg", "normalized 1 t wheat input") for product in products},
            "sum_outputs": quantity(sum(masses.values()), "kg", "normalized 1 t wheat input"),
            "balance_residual": quantity(wheat_kg - sum(masses.values()), "kg", "input minus reported output fractions; rounding-level accounting"),
            "mass_fractions": {product: quantity(value("wheat_" + product + "_mass_share") / 100, "kg/kg_wheat", "physical output fraction of wheat input") for product in products},
            "economic_allocation_factors": {product: quantity(value("wheat_" + product + "_economic_allocation") / 100, "share", "economic allocation of milling inventory; not physical loss or market price") for product in products},
            "electricity_original": quantity(value("mill_electricity"), "kWh/t_flour", claims["mill_electricity"]["base"]),
            "electricity_per_t_wheat": quantity(None, "kWh/t_wheat", "normalized wheat input", reason="not rebased: whether published flour denominator encompasses both products and allocated mill operations is not confirmed"),
            "monetary_loss": quantity(None, "currency/t_wheat", "normalized wheat input", reason="absolute prices and transaction flows are not supplied")},
        "baking_energy": {
            "piece_mass_original": quantity(value("piece_mass"), "g/piece", claims["piece_mass"]["base"]),
            "piece_mass": quantity(loaf_kg, "kg/piece", "commercial loaf after baking"),
            "electricity_per_piece": quantity(value("bakery_electricity"), "kWh/piece", claims["bakery_electricity"]["base"]),
            "natural_gas_per_piece": quantity(value("bakery_natural_gas"), "kWh/piece", claims["bakery_natural_gas"]["base"]),
            "sum_per_piece": quantity(value("bakery_electricity") + value("bakery_natural_gas"), "kWh/piece", "sum of reported energy carriers; not primary energy or GHG"),
            "electricity_per_kg": quantity(value("bakery_electricity") / loaf_kg, "kWh/kg_bread", "mass of studied bread after baking"),
            "natural_gas_per_kg": quantity(value("bakery_natural_gas") / loaf_kg, "kWh/kg_bread", "mass of studied bread after baking"),
            "sum_per_kg": quantity((value("bakery_electricity") + value("bakery_natural_gas")) / loaf_kg, "kWh/kg_bread", "sum of reported energy carriers for studied bread"),
            "conversion": "kg/piece = g/piece / 1000; carrier kWh/kg = carrier kWh/piece / kg/piece"},
        "survey": {
            "total_respondents": quantity(total, "respondents", "Table 1 total"),
            "known_respondents": quantity(known, "respondents", "Table 1 except Do not know"),
            "unknown_respondents": quantity(unknown, "respondents", "Table 1 Do not know"),
            "open_category_respondents": quantity(open_count, "respondents", "Table 1 More than 12 slices"),
            "closed_category_respondents": quantity(closed_count, "respondents", "Table 1 zero through 10–12"),
            "lower_total_all": quantity(lower_known, "slices/week", all_base),
            "lower_mean_all": quantity(lower_known / total, "slices/(respondent_household*week)", all_base),
            "lower_total_known": quantity(lower_known, "slices/week", known_base),
            "lower_mean_known": quantity(lower_known / known, "slices/(respondent_household*week)", known_base),
            "closed_total_interval": {"lower": quantity(lower_closed, "slices/week", closed_base), "upper": quantity(upper_closed, "slices/week", closed_base)},
            "closed_mean_interval": {"lower": quantity(lower_closed / closed_count, "slices/(respondent_household*week)", closed_base), "upper": quantity(upper_closed / closed_count, "slices/(respondent_household*week)", closed_base)},
            "finite_upper_bound_all": open_count == unknown == 0,
            "finite_upper_bound_known": open_count == 0,
            "upper_total_all": quantity(None, "slices/week", all_base, reason=upper_reason),
            "upper_mean_all": quantity(None, "slices/(respondent_household*week)", all_base, reason=upper_reason),
            "upper_total_known": quantity(None, "slices/week", known_base, reason="19 responses above 12 without finite cap"),
            "upper_mean_known": quantity(None, "slices/(respondent_household*week)", known_base, reason="19 responses above 12 without finite cap"),
            "interpretation": "whole nonnegative slices; More than 12 starts at 13. Unknowns contribute zero only to mathematical lower bound, never to observed discard. Bounds constrain declared categories, not weighed real waste; no conversion to kg, intake, or consumption percentage."},
        "published_waste_percentages": reported_losses,
        "linked_chain_loss": quantity(None, "%", "one lot across production, retail and household", reason="Table 7 aggregates and secondary estimates do not identify sequential conditional rates or a tracked lot"),
        "source_audit": {
            "method": "current pdftotext -layout passage extraction, contextual numeric matching, manual reading of cited passages; distinct from hash checks",
            "quantities_audited": len(audited), "quantities": audited,
            "survey_rows": table_audit,
            "discrepancies": [{"file": "source_survey.pdf", "sha256": files["source_survey.pdf"]["sha256"],
                                "prose_locator": {"pdf_page": 3, "section": "3"},
                                "prose_intervals": ["0", "1–3", "4–6", "7–10", ">10"],
                                "table_locator": {"pdf_page": 4, "table": "1"},
                                "table_intervals": ["0", "1–3", "4–6", "7–9", "10–12", ">12", "unknown"],
                                "resolution": "Table 1 categories determine bounds; no repair of original questionnaire is claimed"}],
            "scope": "17 supplied claims on LCA PDF pages 6–8 and survey page 4; all seven Table 1 labels/counts/percentages and methodology intervals on survey page 3. Proposal interpretation also reads LCA pages 9, 12–15 and survey pages 11–13."},
        "causal_effect_of_packaging": quantity(None, "g_discard/(household*week)", "future randomized comparator", reason="reviewed studies provide inventories, observational associations and freshness tests/scenarios, not the proposed trial outcome"),
        "normative_approval": {"status": "pending", "authority": "competent human owner plus responsible food safety and consent authorities; no authority exercised in this run"},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_directory", type=Path)
    args = parser.parse_args()
    try:
        metrics = calculate(args.input_directory)
        print(json.dumps(metrics, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print("analysis error: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
