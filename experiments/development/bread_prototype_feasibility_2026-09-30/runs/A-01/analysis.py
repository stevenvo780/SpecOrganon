#!/usr/bin/env python3
"""Reproduce this archived case. Calculation uses Python's standard library.

Passage auditing additionally requires the local pdftotext executable. No network.
"""
import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def measure(value, unit, base, **extra):
    return {"value": value, "unit": unit, "base": base, **extra}


def extract(path, first, last):
    completed = subprocess.run(
        ["pdftotext", "-layout", "-f", str(first), "-l", str(last), str(path), "-"],
        text=True, capture_output=True, check=True, timeout=20)
    return completed.stdout


def main(root):
    manifest = load(root / "source_manifest.json")
    rows = manifest["files"]
    names = [row["visible_file"] for row in rows]
    require(len(names) == len(set(names)), "duplicate manifest filename")
    required = {"task.md", "source_claims.json", "source_lca.pdf",
                "source_survey.pdf", "survey_table1.json"}
    require(set(names) == required, "manifest visible file set differs from case")
    integrity = []
    for row in rows:
        name = row["visible_file"]
        require(Path(name).name == name, "manifest path must be a visible flat filename")
        path = root / name
        require(path.is_file() and not path.is_symlink(), "missing or linked input: " + name)
        digest = sha(path)
        require(path.stat().st_size == row["bytes"], "byte length mismatch: " + name)
        require(digest == row["sha256"], "SHA-256 mismatch: " + name)
        integrity.append({"file": name, "sha256": digest, "bytes": row["bytes"],
                          "result": "verified_bytes_only"})
    claims_doc = load(root / "source_claims.json")
    table = load(root / "survey_table1.json")
    claims = {row["key"]: row for row in claims_doc["claims"]}
    require(len(claims) == len(claims_doc["claims"]), "duplicate quantitative claim")
    for source in claims_doc["sources"].values():
        path = root / source["visible_file"]
        require(source["visible_file"] in required, "unknown source file")
        require(sha(path) == source["sha256"] and path.stat().st_size == source["bytes"],
                "claim source metadata differs from archived bytes")
    require(table["source"]["archive"] == "source_survey.pdf" and
            table["source"]["sha256"] == sha(root / "source_survey.pdf"),
            "table source metadata differs from archived bytes")

    texts = {("lca", p): extract(root / "source_lca.pdf", p, p) for p in (6, 7, 8)}
    texts.update({("survey", p): extract(root / "source_survey.pdf", p, p) for p in (3, 4)})
    mass = r"Wheat flour products \(% w/w\)\s+([\d.]+)% refined flour, ([\d.]+)% whole flour, ([\d.]+)% bran"
    allocation = r"Wheat, economic allocation factors\s+Refined flour ([\d.]+)%, whole flour ([\d.]+)%, bran ([\d.]+)%"
    origin = r"average of ([\d.]+)% of the wheat has been coming from Norway and the\s+remaining ([\d.]+)% from Poland"
    bakery = r"Baker energy consumption\s+([\d.]+) kWh electricity and ([\d.]+) kWh natural gas per bread"
    specs = {
        "piece_mass": ("lca", 6, "g/piece", r"total mass of the bread itself was ([\d.]+) grams", 1),
        "norway_wheat_share": ("lca", 6, "%", origin, 1),
        "poland_wheat_share": ("lca", 6, "%", origin, 2),
        "mill_electricity": ("lca", 7, "kWh/t_flour", r"Mill energy consumption\s+([\d.]+) kWh electricity per ton of flour produced", 1),
        "wheat_refined_flour_mass_share": ("lca", 7, "% w/w", mass, 1),
        "wheat_whole_flour_mass_share": ("lca", 7, "% w/w", mass, 2),
        "wheat_bran_mass_share": ("lca", 7, "% w/w", mass, 3),
        "wheat_refined_flour_economic_allocation": ("lca", 7, "%", allocation, 1),
        "wheat_whole_flour_economic_allocation": ("lca", 7, "%", allocation, 2),
        "wheat_bran_economic_allocation": ("lca", 7, "%", allocation, 3),
        "mill_to_baker_distance": ("lca", 8, "km", r"Transport from mill to baker\s+([\d.]+) km on >32 tonne truck", 1),
        "bakery_electricity": ("lca", 8, "kWh/piece", bakery, 1),
        "bakery_natural_gas": ("lca", 8, "kWh/piece", bakery, 2),
        "bakery_bread_waste": ("lca", 8, "%", r"Bakery waste\s+([\d.]+)\s+Baking company", 1),
        "retail_bread_waste": ("lca", 8, "%", r"Retail waste\s+([\d.]+)\s+Baking company", 1),
        "consumer_bread_waste_estimate": ("lca", 8, "%", r"Consumer waste\s+([\d.]+)", 1),
        "survey_respondents": ("survey", 4, "respondents", r"Total\s+([\d]+)\s+100\.0", 1),
    }
    require(set(claims) == set(specs), "unexpected or missing quantitative claims")
    audits = []
    values = {}
    for key, (source, page, unit, pattern, group) in specs.items():
        claim = claims[key]
        require(claim["source"] == source and claim["locator"]["pdf_page"] == page,
                "source/page mismatch: " + key)
        require(claim["unit"] == unit and isinstance(claim["base"], str) and claim["base"],
                "unit/base mismatch: " + key)
        require(isinstance(claim["value"], (int, float)) and not isinstance(claim["value"], bool)
                and math.isfinite(claim["value"]), "invalid numeric claim: " + key)
        match = re.search(pattern, texts[(source, page)], re.I)
        require(match is not None, "passage not located: " + key)
        observed = float(match.group(group))
        require(math.isclose(observed, claim["value"], rel_tol=0, abs_tol=1e-9),
                "passage/transcription value mismatch: " + key)
        values[key] = claim["value"]
        audits.append({"key": key, "value": observed, "unit": unit, "base": claim["base"],
                       "file": claims_doc["sources"][source]["visible_file"],
                       "sha256": claims_doc["sources"][source]["sha256"],
                       "locator": claim["locator"], "matched_passage": match.group(0),
                       "result": "matched_archived_pdf_passage", "discrepancy": None,
                       "provenance": claim["provenance"]})

    expected = [
        ("zero", "Zero slices", 0, 0),
        ("one_to_three", "1–3 slices", 1, 3),
        ("four_to_six", "4–6 slices", 4, 6),
        ("seven_to_nine", "7–9 slices", 7, 9),
        ("ten_to_twelve", "10–12 slices", 10, 12),
        ("more_than_twelve", "More than 12 slices", 13, None),
        ("do_not_know", "Do not know", None, None)]
    categories = table["categories"]
    require(len(categories) == len(expected), "unexpected category count")
    total = table["reported_total"]
    require(isinstance(total, int) and not isinstance(total, bool) and total > 0,
            "invalid respondent denominator")
    table_audit = []
    for row, (key, label, lower, upper) in zip(categories, expected):
        require((row["key"], row["label"], row["min_slices"], row["max_slices"]) ==
                (key, label, lower, upper), "category boundary/label mismatch: " + key)
        count = row["count"]
        require(isinstance(count, int) and not isinstance(count, bool) and count >= 0,
                "invalid category count: " + key)
        pct = float(row["reported_percent"])
        require(math.isfinite(pct) and math.isclose(100 * count / total, pct, abs_tol=0.05),
                "count/percentage mismatch: " + key)
        pattern = re.escape(label) + r"\s+(\d+)\s+([\d.]+)"
        match = re.search(pattern, texts[("survey", 4)])
        require(match is not None and int(match.group(1)) == count and
                math.isclose(float(match.group(2)), pct, abs_tol=1e-9),
                "table row differs from archived PDF: " + key)
        table_audit.append({"key": key, "count": count, "reported_percent": pct,
                            "locator": {"pdf_page": 4, "table": "1", "row": label},
                            "matched_passage": match.group(0), "result": "matched_pdf_row"})
    require(sum(row["count"] for row in categories) == total == values["survey_respondents"],
            "respondent counts do not sum to reported total")
    prose_match = re.search(r"categories ranging from 0, 1–3, 4–6, 7–10, and more than 10 per week",
                            texts[("survey", 3)])
    require(prose_match is not None, "methodological interval discrepancy not located")

    products = ("refined_flour", "whole_flour", "bran")
    shares = {p: values["wheat_" + p + "_mass_share"] / 100 for p in products}
    economic = {p: values["wheat_" + p + "_economic_allocation"] / 100 for p in products}
    require(all(0 <= v <= 1 for v in shares.values()), "invalid milling mass fraction")
    require(all(0 <= v <= 1 for v in economic.values()), "invalid economic allocation")
    require(math.isclose(sum(shares.values()), 1, abs_tol=1e-9), "milling fractions fail balance")
    require(math.isclose(sum(economic.values()), 1, abs_tol=1e-9), "allocation factors fail total")
    require(values["norway_wheat_share"] + values["poland_wheat_share"] == 100,
            "wheat origin shares fail total")
    output = {p: round(1000 * shares[p], 9) for p in products}
    milling = {
        "wheat_input": measure(1000, "kg_wheat", "Normalization: 1 metric tonne wheat into mill"),
        "outputs": {p: measure(output[p], "kg", "1 t wheat input") for p in products},
        "outputs_sum": measure(sum(output.values()), "kg", "1 t wheat input"),
        "balance_residual": measure(1000 - sum(output.values()), "kg", "input minus reported outputs"),
        "mass_fractions": {p: measure(shares[p], "kg/kg_wheat", "mill wheat input") for p in products},
        "economic_allocation_factors": {p: measure(economic[p], "dimensionless",
            "fraction of allocated milling inventory; economic allocation, not mass") for p in products},
        "electricity_original": measure(values["mill_electricity"], "kWh/t_flour",
            claims["mill_electricity"]["base"]),
        "electricity_per_t_wheat": measure(None, "kWh/t_wheat", "1 t wheat input",
            reason="No unconditional change of base: flour definition and common intensity across outputs would require an assumption."),
        "interpretation": "Zero arithmetic residual of rounded published fractions is not a measured process loss. Bran is a coproduct, not 191 kg of discarded wheat."
    }
    kg = values["piece_mass"] / 1000
    require(kg > 0 and values["bakery_electricity"] >= 0 and values["bakery_natural_gas"] >= 0,
            "invalid piece mass or bakery energy")
    energy = {"piece_mass_original": measure(values["piece_mass"], "g/piece", claims["piece_mass"]["base"]),
              "piece_mass": measure(kg, "kg/piece", "bread after baking"),
              "conversion": "kg/piece = g/piece / 1000; kWh/kg = kWh/piece / kg/piece"}
    for key, claim_key in (("electricity", "bakery_electricity"), ("natural_gas", "bakery_natural_gas")):
        energy[key + "_per_piece"] = measure(values[claim_key], "kWh/piece", claims[claim_key]["base"])
        energy[key + "_per_kg"] = measure(values[claim_key] / kg, "kWh/kg_bread", "mass of bread after baking")
    energy["sum_per_piece"] = measure(values["bakery_electricity"] + values["bakery_natural_gas"],
                                     "kWh/piece", "electricity plus reported natural gas energy")
    energy["sum_per_kg"] = measure(energy["sum_per_piece"]["value"] / kg,
                                  "kWh/kg_bread", "final bakery bread mass; not primary energy or GHG")
    unknown = sum(r["count"] for r in categories if r["min_slices"] is None)
    opened = sum(r["count"] for r in categories if r["min_slices"] is not None and r["max_slices"] is None)
    closed = [r for r in categories if r["max_slices"] is not None]
    closed_n = sum(r["count"] for r in closed)
    known = total - unknown
    known_lower = sum(r["count"] * r["min_slices"] for r in categories if r["min_slices"] is not None)
    closed_lower = sum(r["count"] * r["min_slices"] for r in closed)
    closed_upper = sum(r["count"] * r["max_slices"] for r in closed)
    require(known > 0 and closed_n > 0, "mean denominator is zero")
    survey = {"total_respondents": total, "known_respondents": known,
              "unknown_respondents": unknown, "open_category_respondents": opened,
              "closed_category_respondents": closed_n,
              "lower_bound_total_all": measure(known_lower, "slices/week", "sum of household discard estimates across all respondents",
                  reason="Unknown quantities are nonnegative and contribute zero only to this lower bound, not as observed zero."),
              "lower_bound_total_known": measure(known_lower, "slices/week", "sum across known category respondents"),
              "lower_bound_mean_all": measure(known_lower / total, "slices/household/week", f"{total} respondent household estimates"),
              "lower_bound_mean_known": measure(known_lower / known, "slices/household/week", f"{known} known category respondents"),
              "closed_total_interval": {"lower": measure(closed_lower, "slices/week", f"{closed_n} closed category respondents"),
                                        "upper": measure(closed_upper, "slices/week", f"{closed_n} closed category respondents")},
              "closed_mean_interval": {"lower": measure(closed_lower / closed_n, "slices/household/week", f"{closed_n} closed category respondents"),
                                       "upper": measure(closed_upper / closed_n, "slices/household/week", f"{closed_n} closed category respondents")},
              "finite_upper_bound_all": False, "finite_upper_bound_known": False,
              "upper_bound_all": measure(None, "slices/household/week", "all respondents", reason="Positive count in >12 category and unknown quantities have no supplied finite cap."),
              "upper_bound_known": measure(None, "slices/household/week", "known respondents", reason="19 respondents in >12 category; no finite cap supplied."),
              "interpretation": "Integer slices make >12 at least 13. Inclusive endpoints, no midpoint imputation. A category-frequency identification interval, not a confidence interval; no personal intake, population projection or slice-to-kg conversion."}
    return {"schema": 1, "case_id": "D-F-A-01", "integrity": integrity,
            "milling": milling, "baking_energy": energy, "survey": survey,
            "source_audit": {"method": "Local pdftotext -layout extraction, row/phrase regex anchored to page, numeric and unit comparison; byte integrity checked separately.",
                "quantities_audited": len(audits), "claims": audits, "table1_rows": table_audit,
                "discrepancies": [{"source": "source_survey.pdf", "sha256": sha(root / "source_survey.pdf"),
                    "prose_locator": {"pdf_page": 3, "section": "3"}, "prose": prose_match.group(0),
                    "table_locator": {"pdf_page": 4, "table": "1"},
                    "result": "Published prose 7–10/>10 conflicts with Table 1 7–9/10–12/>12; use Table 1, no silent repair."}],
                "overall": "17 transcribed values and seven table rows agree with archived passages; one methodological interval discrepancy preserved."},
            "unidentified": {"currency_value_lost": measure(None, "currency", "bread and coproduct value chain", reason="No usable unit prices and linked sold/discarded masses across actors."),
                "causal_packaging_waste_effect": measure(None, "g/household/week", "prospective packaging comparison", reason="Reviewed inventory and survey passages do not identify randomized measured household discard for a proposed new package."),
                "linked_chain_total_loss": measure(None, "kg", "single lot tracked through chain", reason="Table 7 is aggregated on its published common system base, not observed sequential conditional rates.")}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input_directory", type=Path)
    args = parser.parse_args()
    try:
        result = main(args.input_directory.resolve())
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
        sys.stdout.write("\n")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print("analysis error: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
