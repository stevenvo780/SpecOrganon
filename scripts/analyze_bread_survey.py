"""Reproduce descriptive bounds from Table 1 of the archived Norwegian bread survey.

The table contains household-level estimates reported by respondents. Its categories
do not measure waste of the separate LCA product, provide a field baseline, or
identify an intervention effect. Run from anywhere with no third-party packages:
``python scripts/analyze_bread_survey.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TABLE = ROOT / "cases/bread_norway/survey_table1.json"
DEFAULT_OUTPUT = ROOT / "experiments/development/bread_survey_bounds_2026-09-27.json"
SOURCE_SHA256 = "61b3b63cc7b5748138335fa2eaebde2f4ab0e454750e4592582fb80a5043dcee"
SOURCE_DOI = "10.3390/su10072251"
SOURCE_LOCATOR = "Table 1, printed page 4 of 15 (PDF page 4)"
SOURCE_TITLE = (
    "Wasting of Fresh-Packed Bread by Consumers—Influence of Shopping Behavior, "
    "Storing, Handling, and Consumer Preferences"
)
MEASURE = "Respondent-estimated slices of fresh bread wasted from household per week"
CATEGORY_FIELDS = {"key", "label", "count", "reported_percent", "min_slices", "max_slices"}
CATEGORIES = (
    ("zero", "Zero slices", 0, 0),
    ("one_to_three", "1–3 slices", 1, 3),
    ("four_to_six", "4–6 slices", 4, 6),
    ("seven_to_nine", "7–9 slices", 7, 9),
    ("ten_to_twelve", "10–12 slices", 10, 12),
    ("more_than_twelve", "More than 12 slices", 13, None),
    ("do_not_know", "Do not know", None, None),
)
# Audited against Table 1 of the pinned PDF. A matching PDF digest alone does
# not prove that the separately transcribed JSON contains these frequencies.
PUBLISHED_COUNTS = (429, 301, 140, 56, 22, 19, 33)


class SurveyTableError(ValueError):
    """The source table or its pinned PDF does not match the analysis contract."""


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SurveyTableError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _path_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise SurveyTableError(f"cannot read source file: {path}") from exc


def _percent(count: int, total: int) -> str:
    return f"{Decimal(count) * 100 / Decimal(total):.1f}"


def validate_table(table: Any) -> dict[str, int]:
    """Reject schema drift, invalid bins, inconsistent totals and printed percentages."""
    if type(table) is not dict or set(table) != {
        "schema", "source", "measure", "reported_total", "categories"
    }:
        raise SurveyTableError("table must have exactly the expected top-level fields")
    if type(table["schema"]) is not int or table["schema"] != 1:
        raise SurveyTableError("table schema must be 1")
    if table["measure"] != MEASURE:
        raise SurveyTableError("table measure differs from the source transcription")
    source = table["source"]
    if type(source) is not dict or source != {
        "title": SOURCE_TITLE,
        "doi": SOURCE_DOI,
        "archive": "source_survey.pdf",
        "sha256": SOURCE_SHA256,
        "locator": SOURCE_LOCATOR,
    }:
        raise SurveyTableError("source identity or locator differs from the pinned PDF")
    total = table["reported_total"]
    if type(total) is not int or total != 1000:
        raise SurveyTableError("reported total must be 1000 respondents")
    categories = table["categories"]
    if type(categories) is not list or len(categories) != len(CATEGORIES):
        raise SurveyTableError("table must contain exactly seven categories")

    counts: dict[str, int] = {}
    for index, (row, (key, label, lower, upper)) in enumerate(
        zip(categories, CATEGORIES, strict=True), start=1
    ):
        if type(row) is not dict or set(row) != CATEGORY_FIELDS:
            raise SurveyTableError(f"category {index} has missing or extra fields")
        lower_value, upper_value = row["min_slices"], row["max_slices"]
        lower_valid = lower_value is None if lower is None else (
            type(lower_value) is int and lower_value == lower
        )
        upper_valid = upper_value is None if upper is None else (
            type(upper_value) is int and upper_value == upper
        )
        if row["key"] != key or row["label"] != label or not lower_valid or not upper_valid:
            raise SurveyTableError(f"category {index} does not match the published bin")
        count = row["count"]
        if type(count) is not int or count < 0:
            raise SurveyTableError(f"category {index} count must be a nonnegative integer")
        printed = row["reported_percent"]
        if type(printed) is not str or re.fullmatch(r"(?:0|[1-9][0-9]*)\.[0-9]", printed) is None:
            raise SurveyTableError(f"category {index} percentage must have one decimal place")
        if printed != _percent(count, total):
            raise SurveyTableError(f"category {index} percentage disagrees with count")
        counts[key] = count
    if sum(counts.values()) != total:
        raise SurveyTableError("category counts do not sum to 1000")
    if tuple(counts[key] for key, _, _, _ in CATEGORIES) != PUBLISHED_COUNTS:
        raise SurveyTableError("category counts differ from the archived Table 1")
    return counts


def analyze_table(table_path: Path) -> dict[str, Any]:
    """Read a transcription, verify its archived source, and compute exact bounds."""
    try:
        table = json.loads(table_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SurveyTableError(f"cannot read valid JSON table: {table_path}") from exc
    counts = validate_table(table)
    pdf = table_path.parent / "source_survey.pdf"
    observed_sha256 = _sha256(pdf)
    if observed_sha256 != SOURCE_SHA256:
        raise SurveyTableError("archived survey PDF SHA-256 differs from the pinned source")

    total = table["reported_total"]
    unknown = counts["do_not_know"]
    high = sum(counts[key] for key in (
        "seven_to_nine", "ten_to_twelve", "more_than_twelve"
    ))
    minimum_slices = sum(
        counts[key] * lower for key, _, lower, _ in CATEGORIES if lower is not None
    )
    return {
        "schema": 1,
        "analysis": "secondary_descriptive_bounds",
        "input": {
            "table": _path_label(table_path),
            "table_sha256": _sha256(table_path),
            "pdf": _path_label(pdf),
            "pdf_sha256": observed_sha256,
            "doi": SOURCE_DOI,
            "locator": SOURCE_LOCATOR,
        },
        "denominator": {
            "all_respondents": total,
            "known_category_responses": total - unknown,
            "do_not_know_responses": unknown,
        },
        "at_least_7_slices_per_week": {
            "known_responses": high,
            "possible_responses": [high, high + unknown],
            "possible_percent_of_all_respondents": [
                _percent(high, total), _percent(high + unknown, total)
            ],
        },
        "zero_slices_per_week": {
            "known_responses": counts["zero"],
            "possible_responses": [counts["zero"], counts["zero"] + unknown],
            "possible_percent_of_all_respondents": [
                _percent(counts["zero"], total), _percent(counts["zero"] + unknown, total)
            ],
        },
        "weekly_slices_across_respondent_households": {
            "lower_bound": minimum_slices,
            "finite_upper_bound": None,
            "lower_bound_rule": (
                "Use the minimum integer in each reported bin and assign zero to Do not know."
            ),
            "upper_bound_reason": (
                "More than 12 slices is open-ended with positive count; Do not know is also unbounded."
            ),
        },
        "interpretation_limits": [
            "Respondent estimates of weekly household fresh-bread waste, not measured slices or mass.",
            "This survey does not identify purchasers of the separate 736 g bread in the LCA.",
            "These historical responses are not a linked or prospective field baseline.",
            "No intervention, comparator, or causal effect is observed here.",
            "Ranges assign Do not know responses to endpoints; they are not confidence intervals.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        report = analyze_table(args.table)
    except SurveyTableError as exc:
        print(f"bread survey analysis: {exc}", file=sys.stderr)
        return 2
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
