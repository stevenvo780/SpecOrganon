"""Regression checks for the fixed workbook's exploratory temporal cuts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_school_waste import DEFAULT_INPUT, SchoolWasteError  # noqa: E402
from school_waste_temporal import analyze_temporal  # noqa: E402


def test_fixed_source_windows_weeks_and_discordance_exclusion() -> None:
    result = analyze_temporal()
    descriptive = result["descriptive"]
    baseline = descriptive["baseline_20_day_windows"]

    assert (
        result["source"]["sha256"]
        == "2ffad746b7ed5d536a0c99c37d8e249230d95d5fb2d041d85d01b69499f99624"
    )
    assert result["quality"]["baseline_missing_ksw_rows"] == [19]
    assert result["quality"]["post_derived_discordance_rows"] == [137, 152]
    assert baseline["candidate_count"] == 116
    assert baseline["excluded_incomplete_count"] == 18
    assert baseline["complete_count"] == 98
    assert {
        tuple(item["missing_ksw_rows"])
        for item in baseline["excluded_incomplete_windows"]
    } == {(19,)}
    assert baseline["complete_windows"][0]["window_index"] == 19
    assert baseline["latest_complete_window_index"] == 116
    latest = baseline["latest_complete_window"]
    assert (latest["first_xlsx_row"], latest["last_xlsx_row"]) == (117, 136)
    assert (latest["first_date"], latest["last_date"]) == ("2025-02-10", "2025-03-14")
    assert latest["metrics"]["total"] == {
        "eligible_days": 20,
        "denominator_diners": 7661,
        "sum_kg": "305.747000",
        "g_per_diner": "39.909542",
    }
    assert all(
        item["period"]["metrics"][metric]["eligible_days"] == 20
        for item in baseline["complete_windows"]
        for metric in ("pw", "ksw", "total")
    )

    post = descriptive["final_post_20"]
    assert (post["first_xlsx_row"], post["last_xlsx_row"]) == (137, 156)
    assert post["metrics"]["total"]["g_per_diner"] == "29.068510"
    assert (
        descriptive["post_20_minus_latest_baseline_window"]["total"][
            "post_minus_baseline_g_per_diner"
        ]
        == "-10.841032"
    )
    weeks = descriptive["post_weeks"]
    assert [
        (
            week["iso_week"],
            week["observed"]["first_xlsx_row"],
            week["observed"]["last_xlsx_row"],
        )
        for week in weeks
    ] == [
        ("2025-W12", 137, 141),
        ("2025-W13", 142, 146),
        ("2025-W14", 147, 151),
        ("2025-W15", 152, 156),
    ]
    assert [week["observed"]["metrics"]["total"]["g_per_diner"] for week in weeks] == [
        "27.258982",
        "27.807551",
        "27.237204",
        "34.615886",
    ]
    assert [
        week["excluding_discordant_rows"]["period"]["days"]
        if week["excluding_discordant_rows"]
        else None
        for week in weeks
    ] == [4, None, None, 4]

    exclusion = descriptive["discordance_exclusion"]
    assert exclusion["excluded_xlsx_rows"] == [137, 152]
    assert exclusion["post_remaining"]["days"] == 18
    assert exclusion["post_remaining"]["metrics"]["total"] == {
        "eligible_days": 18,
        "denominator_diners": 6798,
        "sum_kg": "190.800000",
        "g_per_diner": "28.067079",
    }
    assert (
        exclusion["post_remaining_minus_full_baseline"]["total"][
            "post_minus_baseline_g_per_diner"
        ]
        == "-17.028893"
    )
    assert result["inference"]["status"] == "not_estimated"
    assert result["criterion_3"] == "not_demonstrated"


def test_temporal_script_rejects_workbook_with_changed_bytes(tmp_path: Path) -> None:
    changed = tmp_path / "source.xlsx"
    changed.write_bytes(DEFAULT_INPUT.read_bytes() + b"altered copy")
    with pytest.raises(SchoolWasteError, match="source SHA-256 differs"):
        analyze_temporal(changed)
