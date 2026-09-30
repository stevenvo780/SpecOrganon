"""Compare exposed native metrics with pretrial arithmetic; never assign Q.

Aliases project equivalent output keys after execution without changing the
frozen factual reference, rubric, original metrics or executor artifacts.
Usage: python check_arithmetic.py REPOSITORY
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path


def value(item):
    return item["value"] if isinstance(item, dict) else item


def first(group: dict, keys: list):
    return next(group[key] for key in keys if key in group)


def check(repo: Path) -> dict:
    location = repo / "experiments/development/bread_prototype_feasibility_2026-09-30"
    reference_raw = (location / "reference.json").read_bytes()
    reference = json.loads(reference_raw)
    table = json.loads((repo / "cases/bread_norway/survey_table1.json").read_text())
    closed = [row for row in table["categories"] if row["max_slices"] is not None]
    known = [row for row in table["categories"] if row["min_slices"] is not None]
    lower = sum(row["count"] * row["min_slices"] for row in known)
    closed_lower = sum(row["count"] * row["min_slices"] for row in closed)
    closed_upper = sum(row["count"] * row["max_slices"] for row in closed)
    total = table["reported_total"]
    known_n = sum(row["count"] for row in known)
    closed_n = sum(row["count"] for row in closed)
    assert lower == reference["survey"]["minimum_slices_under_reported_categories"]
    result = []
    for trial_id in ["A-01", "B-01", "C-01"]:
        raw = (location / "runs" / trial_id / "metrics.json").read_bytes()
        metrics = json.loads(raw)
        checks = []

        def compare(name, actual, expected):
            actual = value(actual)
            agrees = (type(actual) is bool and actual is expected) if type(expected) is bool else (
                isinstance(actual, (int, float)) and not isinstance(actual, bool)
                and math.isfinite(actual) and math.isclose(actual, float(expected), rel_tol=1e-12, abs_tol=1e-12))
            checks.append({"name": name, "actual": actual, "expected": str(expected), "agrees": agrees})

        mill, bake, survey = metrics["milling"], metrics["baking_energy"], metrics["survey"]
        compare("wheat_input_kg", mill["wheat_input"], 1000)
        for product in ["refined_flour", "whole_flour", "bran"]:
            compare(product + "_kg", mill["outputs"][product], Fraction(reference["milling"][product + "_kg"]))
        compare("milling_outputs_kg", first(mill, ["outputs_sum", "sum_outputs"]), 1000)
        compare("milling_arithmetic_residual_kg", mill["balance_residual"], 0)
        compare("piece_mass_kg", bake["piece_mass"], Fraction(reference["baking"]["bread_piece_mass_kg"]))
        elec = reference["baking"]["electricity_kwh_per_kg_exact"]
        gas = reference["baking"]["natural_gas_kwh_per_kg_exact"]
        electricity = Fraction(elec["numerator"], elec["denominator"])
        natural_gas = Fraction(gas["numerator"], gas["denominator"])
        compare("electricity_kwh_per_kg", bake["electricity_per_kg"], electricity)
        compare("gas_kwh_per_kg", bake["natural_gas_per_kg"], natural_gas)
        compare("reported_energy_sum_kwh_per_kg", first(bake, ["sum_per_kg", "total_per_kg"]), electricity + natural_gas)
        for name, expected in [("total", total), ("known", known_n), ("unknown", total - known_n),
                               ("open_category", known_n - closed_n), ("closed_category", closed_n)]:
            compare(name + "_respondents", survey[name + "_respondents"], expected)
        aliases = {
            "lower_total_all": ["lower_bound_total_all", "lower_total_all", "all_total_lower_bound"],
            "lower_total_known": ["lower_bound_total_known", "lower_total_known", "known_total_lower_bound"],
            "lower_mean_all": ["lower_bound_mean_all", "lower_mean_all", "all_mean_lower_bound"],
            "lower_mean_known": ["lower_bound_mean_known", "lower_mean_known", "known_mean_lower_bound"],
        }
        for name, expected in [("lower_total_all", lower), ("lower_total_known", lower),
                               ("lower_mean_all", Fraction(lower, total)), ("lower_mean_known", Fraction(lower, known_n))]:
            compare(name, first(survey, aliases[name]), expected)
        for bound, expected in [("lower", closed_lower), ("upper", closed_upper)]:
            compare("closed_total_" + bound, survey["closed_total_interval"][bound], expected)
            compare("closed_mean_" + bound, survey["closed_mean_interval"][bound], Fraction(expected, closed_n))
        compare("finite_upper_bound_all", survey["finite_upper_bound_all"], False)
        compare("finite_upper_bound_known", survey["finite_upper_bound_known"], False)
        counts_without_unit_base = [name + "_respondents" for name in
                                   ["total", "known", "unknown", "open_category", "closed_category"]
                                   if not isinstance(survey[name + "_respondents"], dict)]
        result.append({"trial_id": trial_id, "metrics_sha256": hashlib.sha256(raw).hexdigest(),
                       "checks": checks, "agreements": sum(row["agrees"] for row in checks),
                       "check_count": len(checks), "survey_counts_without_value_unit_base": counts_without_unit_base})
    return {"schema": 1, "classification": "exposed_development_arithmetic_projection_not_Q",
            "reference_sha256": hashlib.sha256(reference_raw).hexdigest(),
            "reference_frozen_commit": "7f8a344d56b467d032e449883074feb977f5a2c7",
            "projection_keys_defined_after_outputs": True,
            "arithmetic_reference_changed_after_outputs": False,
            "numeric_tolerance": {"relative": 1e-12, "absolute": 1e-12},
            "Q": None, "method_winner": None, "counts_toward_required_24_runs": False,
            "trials": result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.repository.resolve(strict=True)), indent=2, sort_keys=True))
