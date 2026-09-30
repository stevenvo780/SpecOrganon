#!/usr/bin/env python3
"""Reproducible archival calculations; pdftotext is required for passage audit."""
import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path


EXPECTED_UNITS = {
    "piece_mass": "g/piece", "norway_wheat_share": "%", "poland_wheat_share": "%",
    "mill_electricity": "kWh/t_flour", "mill_to_baker_distance": "km",
    "bakery_electricity": "kWh/piece", "bakery_natural_gas": "kWh/piece",
    "survey_respondents": "respondents", "bakery_bread_waste": "%",
    "retail_bread_waste": "%", "consumer_bread_waste_estimate": "%",
    **{f"wheat_{p}_mass_share": "% w/w" for p in ("refined_flour", "whole_flour", "bran")},
    **{f"wheat_{p}_economic_allocation": "%" for p in ("refined_flour", "whole_flour", "bran")},
}
CATEGORIES = [
    ("zero", "Zero slices", 0, 0), ("one_to_three", "1–3 slices", 1, 3),
    ("four_to_six", "4–6 slices", 4, 6), ("seven_to_nine", "7–9 slices", 7, 9),
    ("ten_to_twelve", "10–12 slices", 10, 12),
    ("more_than_twelve", "More than 12 slices", 13, None),
    ("do_not_know", "Do not know", None, None),
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    def reject_constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def quantity(value, unit, base, reason=None):
    result = {"value": value, "unit": unit, "base": base}
    if reason is not None:
        result["reason"] = reason
    return result


def norm(text):
    return re.sub(r"\s+", " ", text.replace("−", "-")).strip()


def calculate(root):
    root = Path(root).resolve()
    manifest = read_json(root / "source_manifest.json")
    require(manifest.get("schema") == 1, "unsupported manifest schema")
    names = set()
    verified = []
    for entry in manifest["files"]:
        name = entry["visible_file"]
        require(isinstance(name, str) and Path(name).name == name and name not in names,
                "manifest visible names must be unique flat relative names")
        names.add(name)
        path = root / name
        require(path.resolve().parent == root and path.is_file(), f"unavailable or unsafe input: {name}")
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        require(len(payload) == entry["bytes"] and digest == entry["sha256"], f"integrity mismatch: {name}")
        verified.append({"file": name, "sha256": digest, "bytes": len(payload), "result": "matched"})
    require({"task.md", "source_claims.json", "survey_table1.json", "source_lca.pdf", "source_survey.pdf"} <= names,
            "manifest missing required inputs")
    files = {item["file"]: item for item in verified}
    claims_doc = read_json(root / "source_claims.json")
    table = read_json(root / "survey_table1.json")
    require(claims_doc.get("schema") == 1 and table.get("schema") == 1, "unsupported transcription schema")
    claims = {item["key"]: item for item in claims_doc["claims"]}
    require(len(claims) == len(claims_doc["claims"]) and set(claims) == set(EXPECTED_UNITS),
            "unexpected, missing or duplicate quantitative claims")
    for key, claim in claims.items():
        require(claim["unit"] == EXPECTED_UNITS[key] and bool(claim["base"]), f"unit/base mismatch: {key}")
        value = claim["value"]
        require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0,
                f"invalid numeric claim: {key}")
        source = claims_doc["sources"][claim["source"]]
        require(source["visible_file"] in files and files[source["visible_file"]]["sha256"] == source["sha256"]
                and files[source["visible_file"]]["bytes"] == source["bytes"], f"source identity mismatch: {key}")
        require(isinstance(claim["locator"]["pdf_page"], int) and claim["locator"]["pdf_page"] > 0,
                f"invalid page locator: {key}")
    v = {key: Decimal(str(item["value"])) for key, item in claims.items()}
    require(v["piece_mass"] > 0 and v["survey_respondents"] == int(v["survey_respondents"]), "invalid mass/count")
    for suffix in ("mass_share", "economic_allocation"):
        require(sum(v[f"wheat_{p}_{suffix}"] for p in ("refined_flour", "whole_flour", "bran")) == 100,
                f"wheat {suffix} does not sum to 100 percent")
    require(v["norway_wheat_share"] + v["poland_wheat_share"] == 100, "origin shares do not sum to 100")
    require(table["source"]["archive"] in files and table["source"]["sha256"] == files[table["source"]["archive"]]["sha256"],
            "survey source identity mismatch")
    require(len(table["categories"]) == len(CATEGORIES), "unexpected category count")
    total = table["reported_total"]
    require(isinstance(total, int) and not isinstance(total, bool) and total > 0, "invalid survey total")
    for row, expected in zip(table["categories"], CATEGORIES):
        require((row["key"], row["label"], row["min_slices"], row["max_slices"]) == expected,
                f"category boundaries/labels mismatch: {row.get('key')}")
        require(isinstance(row["count"], int) and not isinstance(row["count"], bool) and row["count"] >= 0,
                "category count must be a nonnegative integer")
        require(Decimal(row["reported_percent"]) == Decimal(100) * row["count"] / total,
                f"category percentage/count mismatch: {row['key']}")
    require(sum(row["count"] for row in table["categories"]) == total == v["survey_respondents"],
            "category/claim totals disagree")

    pages = {}
    for filename in ("source_lca.pdf", "source_survey.pdf"):
        result = subprocess.run(["pdftotext", "-layout", str(root / filename), "-"], capture_output=True, text=True, check=False)
        require(result.returncode == 0, f"pdftotext failed for {filename}: {result.stderr.strip()}")
        pages[filename] = result.stdout.split("\f")
    snippets = {
        "piece_mass": r"total mass of the bread itself was .*? grams",
        "norway_wheat_share": r"average of .*? from Poland",
        "poland_wheat_share": r"average of .*? from Poland",
        "mill_electricity": r"Mill energy consumption.*?flour produced\.",
        "mill_to_baker_distance": r"Transport from mill to baker.*?Mill company",
        "bakery_electricity": r"Baker energy consumption.*?Baking company",
        "bakery_natural_gas": r"Baker energy consumption.*?Baking company",
        "bakery_bread_waste": r"Bakery waste.*?Baking company",
        "retail_bread_waste": r"Retail waste.*?Baking company",
        "consumer_bread_waste_estimate": r"Consumer waste.*?\[3\] and wastage data in Reference \[9\]",
        "survey_respondents": r"Total\s+\d+\s+100\.0",
        **{f"wheat_{p}_mass_share": r"Wheat flour products \(% w/w\).*?bran\."
           for p in ("refined_flour", "whole_flour", "bran")},
        **{f"wheat_{p}_economic_allocation": r"Wheat, economic allocation factors.*?bran .*?%\."
           for p in ("refined_flour", "whole_flour", "bran")},
    }
    audit = []
    for key, claim in claims.items():
        filename = claims_doc["sources"][claim["source"]]["visible_file"]
        page_number = claim["locator"]["pdf_page"]
        require(page_number <= len(pages[filename]), f"page outside PDF: {key}")
        content = norm(pages[filename][page_number - 1])
        match = re.search(snippets[key], content, re.I)
        require(match is not None, f"published row/passage not located: {key}")
        passage = match.group(0)
        number = str(claim["value"])
        require(re.search(r"(?<![\d.])" + re.escape(number) + r"(?![\d.])", passage) is not None,
                f"quantity not matched within source passage: {key}")
        if key == "mill_electricity":
            require("per ton of flour produced" in passage, "mill electricity base not confirmed")
        if key.startswith("bakery_") and key in ("bakery_electricity", "bakery_natural_gas"):
            require("natural gas per bread" in passage and "electricity" in passage, "bakery energy base not confirmed")
        if key in ("bakery_bread_waste", "retail_bread_waste", "consumer_bread_waste_estimate"):
            require("Bread Entering the System" in content, "Table 7 common denominator not confirmed")
        audit.append({"key": key, "file": filename, "sha256": files[filename]["sha256"],
                      "locator": claim["locator"], "quantity": quantity(claim["value"], claim["unit"], claim["base"]),
                      "method": "pdftotext -layout; matched number in identified original row/passage; executor read pages 6–8/4",
                      "passage": passage, "result": "matched_original_passage"})
    survey_page = norm(pages["source_survey.pdf"][3])
    for row in table["categories"]:
        pattern = re.escape(row["label"]) + r"\s+" + str(row["count"]) + r"\s+" + re.escape(row["reported_percent"])
        require(re.search(pattern, survey_page) is not None, f"survey row mismatch against PDF: {row['key']}")
        audit.append({"key": f"survey_row_{row['key']}", "file": "source_survey.pdf",
                      "sha256": files["source_survey.pdf"]["sha256"], "locator": {"pdf_page": 4, "table": "1", "row": row["label"]},
                      "quantity": quantity(row["count"], "respondents", "Table 1 respondents"),
                      "reported_percent": row["reported_percent"], "result": "matched_label_count_percent_original_row"})
    methodology = norm(pages["source_survey.pdf"][2])
    require("0, 1–3, 4–6, 7–10, and more than 10 per week" in methodology, "methodology discrepancy passage missing")
    discrepancies = [{"id": "survey_intervals", "file": "source_survey.pdf", "pdf_pages": [3, 4],
                      "description": "Section 3 prose: 0, 1–3, 4–6, 7–10, >10; Table 1: 0, 1–3, 4–6, 7–9, 10–12, >12 plus unknown.",
                      "resolution": "Use Table 1 labels and categories for bounds; Appendix A question 7 on page 14 also lists 7–9, 10–12, >12."}]
    waste_sum = sum(v[key] for key in ("bakery_bread_waste", "retail_bread_waste", "consumer_bread_waste_estimate"))
    discussion = norm(pages["source_lca.pdf"][14])
    if "21.3% wasted in Norway" in discussion:
        discrepancies.append({"id": "lca_waste_total", "file": "source_lca.pdf", "pdf_pages": [8, 15],
                              "description": f"Table 7 shares sum to {waste_sum}%; discussion section 6.1 says 21.3% wasted in Norway.",
                              "resolution": "Retain table-based accounting scenario; no correction of published text or identified cohort is inferred."})

    closed = [row for row in table["categories"] if row["max_slices"] is not None]
    known = [row for row in table["categories"] if row["min_slices"] is not None]
    closed_n = sum(row["count"] for row in closed)
    known_n = sum(row["count"] for row in known)
    minimum = sum(row["count"] * row["min_slices"] for row in known)
    closed_min = sum(row["count"] * row["min_slices"] for row in closed)
    closed_max = sum(row["count"] * row["max_slices"] for row in closed)
    mass_kg = v["piece_mass"] / 1000
    product_keys = ("refined_flour", "whole_flour", "bran")
    milling = {
        "wheat_input": quantity(1000, "kg_wheat", "normalization: one tonne wheat entering mill"),
        "mass_fractions": {p: quantity(float(v[f"wheat_{p}_mass_share"]), "% w/w", "wheat input") for p in product_keys},
        "outputs": {p: quantity(float(10 * v[f"wheat_{p}_mass_share"]), "kg", "per 1000 kg wheat input; published average fractions") for p in product_keys},
        "sum_outputs": quantity(1000, "kg", "per 1000 kg wheat input"),
        "balance_residual": quantity(0, "kg", "wheat input minus summed outputs; balance at reported precision"),
        "combined_flour": quantity(float(10 * (v["wheat_refined_flour_mass_share"] + v["wheat_whole_flour_mass_share"])), "kg_flour", "per 1000 kg wheat input"),
        "economic_allocation": {p: quantity(float(v[f"wheat_{p}_economic_allocation"]), "%", "economic share of milling inventory burdens; not mass or observed price") for p in product_keys},
        "economic_allocation_sum": quantity(100, "%", "economic shares of milling inventory"),
        "electricity_original": quantity(float(v["mill_electricity"]), "kWh/t_flour", "one tonne flour produced"),
        "electricity_per_t_wheat": quantity(None, "kWh/t_wheat", "one tonne wheat input", "Not rebased: applying the average flour energy intensity to this wheat output mix would require an additional allocation/intensity assumption."),
    }
    baking = {
        "piece_mass_original": quantity(float(v["piece_mass"]), "g/piece", "commercial bread after baking"),
        "piece_mass": quantity(float(mass_kg), "kg/piece", "commercial bread after baking"),
        "electricity_per_piece": quantity(float(v["bakery_electricity"]), "kWh/piece", "commercial bread of 0.736 kg"),
        "natural_gas_per_piece": quantity(float(v["bakery_natural_gas"]), "kWh/piece", "commercial bread of 0.736 kg"),
        "total_per_piece": quantity(float(v["bakery_electricity"] + v["bakery_natural_gas"]), "kWh/piece", "sum of reported input energy carriers per loaf"),
        "electricity_per_kg": quantity(float(v["bakery_electricity"] / mass_kg), "kWh/kg_bread", "kg produced bread, excluding consumer/retail losses"),
        "natural_gas_per_kg": quantity(float(v["bakery_natural_gas"] / mass_kg), "kWh/kg_bread", "kg produced bread, excluding consumer/retail losses"),
        "total_per_kg": quantity(float((v["bakery_electricity"] + v["bakery_natural_gas"]) / mass_kg), "kWh/kg_bread", "sum of delivered carrier energy; not primary energy demand or CO2"),
        "conversion": "kg/piece = g/piece / 1000; kWh/kg = kWh/piece divided by kg/piece; sum carriers on the reported kWh basis",
    }
    respondent_base = "respondents reporting household discard per week; households are not established as unique"
    survey = {
        "total_respondents": quantity(total, "respondents", respondent_base),
        "known_respondents": quantity(known_n, "respondents", "all categories except do not know"),
        "unknown_respondents": quantity(total - known_n, "respondents", "do not know category"),
        "open_category_respondents": quantity(known_n - closed_n, "respondents", "More than 12 slices category"),
        "closed_category_respondents": quantity(closed_n, "respondents", "categories Zero through 10–12 only"),
        "all_total_lower_bound": quantity(minimum, "slices/week", "sum of all 1000 respondent-specific household reports; unknowns constrained only nonnegative"),
        "known_total_lower_bound": quantity(minimum, "slices/week", "sum of 967 known respondent-specific household reports"),
        "all_mean_lower_bound": quantity(minimum / total, "slices/(respondent_household_report·week)", "all 1000 respondents"),
        "known_mean_lower_bound": quantity(minimum / known_n, "slices/(respondent_household_report·week)", "967 known category respondents"),
        "closed_total_interval": {"lower": quantity(closed_min, "slices/week", "948 closed-category reports"), "upper": quantity(closed_max, "slices/week", "948 closed-category reports")},
        "closed_mean_interval": {"lower": quantity(closed_min / closed_n, "slices/(respondent_household_report·week)", "948 closed-category respondents"), "upper": quantity(closed_max / closed_n, "slices/(respondent_household_report·week)", "948 closed-category respondents")},
        "all_total_upper_bound": quantity(None, "slices/week", "1000 respondents", "No finite cap for >12 category or unknown quantities."),
        "known_total_upper_bound": quantity(None, "slices/week", "967 known respondents", "19 responses in >12 category have no finite upper cap."),
        "all_mean_upper_bound": quantity(None, "slices/(respondent_household_report·week)", "1000 respondents", "Unbounded open category and unknowns; not Infinity."),
        "known_mean_upper_bound": quantity(None, "slices/(respondent_household_report·week)", "967 respondents", "Unbounded open category; not Infinity."),
        "finite_upper_bound_all": False, "finite_upper_bound_known": False,
        "interpretation": "Whole slices, inclusive closed endpoints, >12 implies at least 13. Unknowns may contribute zero to a mathematical infimum, but zero is not observed. Bounds describe category-constrained reports, not actual weighed waste, intake or national population uncertainty.",
        "categories": table["categories"],
    }
    loss_keys = ("bakery_bread_waste", "retail_bread_waste", "consumer_bread_waste_estimate")
    losses = {
        "reported": {key: quantity(float(v[key]), "%", claims[key]["base"]) for key in loss_keys},
        "normalized_common_base": {key: quantity(float(v[key]), "kg_bread", "scenario per 100 kg Bread Entering the System, Table 7") for key in loss_keys},
        "sum": quantity(float(waste_sum), "kg_bread", "scenario per 100 kg common Table 7 base; not sequential conditional losses"),
        "arithmetic_remainder": quantity(float(100 - waste_sum), "kg_bread", "scenario common base minus Table 7 rows; not observed intake or linked lot"),
        "monetary_value_lost": quantity(None, "currency", "bread loss and coproduct value across actors", "No aligned prices, intervention costs, sale quantities or linked loss observations in the supplied quantitative packet."),
        "wheat_to_bread_yield": quantity(None, "kg_bread/kg_wheat", "linked wheat lot to bread output", "Recipe moisture, other ingredients and aggregate stage data do not define a linked lot conversion."),
    }
    return {"schema": 1, "case": "D-F/C-01", "classification": "development_exposed_documentary_analysis",
            "integrity": {"method": "bytes and SHA-256 against manifest using visible relative filenames", "files": verified,
                          "manifest_sha256": hashlib.sha256((root / "source_manifest.json").read_bytes()).hexdigest(), "result": "matched"},
            "milling": milling, "baking_energy": baking, "survey": survey, "value_losses": losses,
            "source_audit": {"method": "original archived PDF text extraction and row/passage cotejo; separate from byte integrity",
                             "quantitative_claims_checked": len(claims), "survey_rows_checked": len(table["categories"]),
                             "checks": audit, "discrepancies": discrepancies, "result": "transcribed quantities matched; published inconsistencies retained"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_directory", type=Path)
    args = parser.parse_args()
    try:
        metrics = calculate(args.input_directory)
        json.dump(metrics, sys.stdout, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        sys.stdout.write("\n")
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError, ZeroDivisionError) as error:
        print(f"analysis error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
