"""Independent arithmetic and malformed-transcription checks for survey Table 1."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "cases/bread_norway/survey_table1.json"
RECEIPT = ROOT / "experiments/development/bread_survey_bounds_2026-09-27.json"
SCRIPT = ROOT / "scripts/analyze_bread_survey.py"
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_bread_survey import SurveyTableError, analyze_table, validate_table  # noqa: E402


def _table() -> dict:
    return json.loads(TABLE.read_text(encoding="utf-8"))


def test_published_counts_and_independent_bound_arithmetic() -> None:
    table = _table()
    counts = [row["count"] for row in table["categories"]]
    assert counts == [429, 301, 140, 56, 22, 19, 33]
    assert [row["reported_percent"] for row in table["categories"]] == [
        "42.9", "30.1", "14.0", "5.6", "2.2", "1.9", "3.3"
    ]
    assert sum(counts) == 1000

    # Manual arithmetic oracle, independent of the analysis implementation.
    known_high = 56 + 22 + 19
    minimum_weekly_slices = 301 + 4 * 140 + 7 * 56 + 10 * 22 + 13 * 19
    assert known_high == 97
    assert minimum_weekly_slices == 1720

    report = analyze_table(TABLE)
    assert report["denominator"] == {
        "all_respondents": 1000,
        "known_category_responses": 967,
        "do_not_know_responses": 33,
    }
    assert report["at_least_7_slices_per_week"] == {
        "known_responses": 97,
        "possible_responses": [97, 130],
        "possible_percent_of_all_respondents": ["9.7", "13.0"],
    }
    assert report["zero_slices_per_week"] == {
        "known_responses": 429,
        "possible_responses": [429, 462],
        "possible_percent_of_all_respondents": ["42.9", "46.2"],
    }
    total = report["weekly_slices_across_respondent_households"]
    assert total["lower_bound"] == minimum_weekly_slices
    assert total["finite_upper_bound"] is None
    assert report["input"]["locator"] == "Table 1, printed page 4 of 15 (PDF page 4)"
    assert "critique_accepted" not in report


@pytest.mark.parametrize(("change", "error"), [
    ("wrong_schema", "schema must be 1"),
    ("wrong_source", "source identity or locator"),
    ("missing_category", "exactly seven categories"),
    ("bad_bin", "published bin"),
    ("boolean_bin_endpoint", "published bin"),
    ("negative_count", "nonnegative integer"),
    ("boolean_count", "nonnegative integer"),
    ("fractional_count", "nonnegative integer"),
    ("wrong_percent", "percentage disagrees"),
    ("inconsistent_total", "do not sum to 1000"),
    ("compensated_counts", "differ from the archived Table 1"),
    ("extra_field", "missing or extra fields"),
])
def test_malformed_transcription_is_rejected(change: str, error: str) -> None:
    table = copy.deepcopy(_table())
    if change == "wrong_schema":
        table["schema"] = True
    elif change == "wrong_source":
        table["source"]["locator"] = "Table 2"
    elif change == "missing_category":
        table["categories"].pop()
    elif change == "bad_bin":
        table["categories"][5]["max_slices"] = 15
    elif change == "boolean_bin_endpoint":
        table["categories"][1]["min_slices"] = True
    elif change == "negative_count":
        table["categories"][0]["count"] = -1
    elif change == "boolean_count":
        table["categories"][0]["count"] = True
    elif change == "fractional_count":
        table["categories"][0]["count"] = 429.5
    elif change == "wrong_percent":
        table["categories"][0]["reported_percent"] = "43.0"
    elif change == "inconsistent_total":
        table["categories"][0]["count"] = 430
        table["categories"][0]["reported_percent"] = "43.0"
    elif change == "compensated_counts":
        table["categories"][0]["count"] = 430
        table["categories"][0]["reported_percent"] = "43.0"
        table["categories"][1]["count"] = 300
        table["categories"][1]["reported_percent"] = "30.0"
    elif change == "extra_field":
        table["categories"][0]["invented"] = 1
    with pytest.raises(SurveyTableError, match=error):
        validate_table(table)


def test_duplicate_json_key_is_rejected(tmp_path: Path) -> None:
    malformed = tmp_path / "survey_table1.json"
    malformed.write_text(TABLE.read_text(encoding="utf-8").replace(
        '"schema": 1,', '"schema": 1, "schema": 1,', 1
    ), encoding="utf-8")
    with pytest.raises(SurveyTableError, match="duplicate JSON key"):
        analyze_table(malformed)


def test_pdf_hash_mismatch_prevents_receipt(tmp_path: Path) -> None:
    table = tmp_path / "survey_table1.json"
    table.write_bytes(TABLE.read_bytes())
    (tmp_path / "source_survey.pdf").write_bytes(b"wrong archived source")
    output = tmp_path / "receipt.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--table", str(table), "--output", str(output)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "PDF SHA-256 differs" in result.stderr
    assert not output.exists()


def test_cli_recreates_exact_receipt(tmp_path: Path) -> None:
    output = tmp_path / "receipt.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(output)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_bytes() == RECEIPT.read_bytes()
