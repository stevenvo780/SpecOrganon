"""Fixed-source checks for adjacent school-waste placebo cutoffs."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_school_waste import DEFAULT_INPUT, SchoolWasteError  # noqa: E402
from school_waste_placebo_cutoffs import _ordering, analyze_placebo_cutoffs  # noqa: E402


def test_fixed_source_excludes_all_and_only_cutoffs_touching_missing_ksw() -> None:
    result = analyze_placebo_cutoffs()

    assert result["source"]["sha256"] == (
        "2ffad746b7ed5d536a0c99c37d8e249230d95d5fb2d041d85d01b69499f99624"
    )
    assert result["prior_plan"]["sha256"] == (
        "49ce977aebb5fa6ddbd26bc008b9ffa4e094a4d81e4fe5f4785ee3e3895e9f66"
    )
    assert (result["candidate_count"], result["included_count"], result["excluded_count"]) == (96, 78, 18)
    assert result["quality"]["baseline_missing_ksw_rows"] == [19]
    assert result["quality"]["baseline_missing_pw_rows"] == []
    assert [item["cutoff_index"] for item in result["excluded_cutoffs"]] == list(range(1, 19))
    assert [item["cutoff_index"] for item in result["cutoffs"]] == list(range(19, 97))
    assert {
        (missing["xlsx_row"], missing["date"], missing["window"])
        for item in result["excluded_cutoffs"]
        for missing in item["missing_ksw"]
    } == {(19, "2024-09-02", "before")}
    assert result["excluded_cutoffs"][0]["before_last_date"] == "2024-09-04"
    assert result["excluded_cutoffs"][-1]["after_first_date"] == "2024-09-30"
    assert all(
        item["before"]["observed_days"] == item["after"]["observed_days"] == 20
        and "missing KSW kg" in item["reason"]
        for item in result["excluded_cutoffs"]
    )


def test_fixed_source_uses_diner_weighted_ratios_on_common_complete_days() -> None:
    result = analyze_placebo_cutoffs()
    first = result["cutoffs"][0]
    last = result["cutoffs"][-1]

    assert (first["before_last_date"], first["after_first_date"]) == (
        "2024-09-30", "2024-10-01"
    )
    assert (first["before"]["first_xlsx_row"], first["after"]["last_xlsx_row"]) == (20, 59)
    for metric in ("pw", "ksw", "total"):
        assert first["before"]["metrics"][metric]["eligible_days"] == 20
        assert first["after"]["metrics"][metric]["eligible_days"] == 20
        assert first["before"]["metrics"][metric]["denominator_diners"] == 8384
        assert first["after"]["metrics"][metric]["denominator_diners"] == 8033
    assert first["before"]["metrics"]["total"]["sum_kg"] == "403.590000"
    assert first["after"]["metrics"]["total"]["sum_kg"] == "401.316000"
    assert first["after_minus_before_g_per_diner"] == {
        "pw": "1.745892", "ksw": "0.074409", "total": "1.820301"
    }
    assert (last["before_last_date"], last["after_first_date"]) == (
        "2025-02-07", "2025-02-10"
    )
    assert last["before"]["metrics"]["total"]["denominator_diners"] == 7909
    assert last["after"]["metrics"]["total"]["denominator_diners"] == 7661
    assert result["reference"]["final_minus_latest_baseline_20_g_per_diner"] == {
        "pw": "-2.123090", "ksw": "-8.717942", "total": "-10.841032"
    }
    assert result["descriptive_comparison"]["total"]["comparison_counts"] == {
        "more_negative_than_final_delta": 9,
        "equal_to_final_delta": 0,
        "less_negative_than_final_delta": 69,
    }


def test_comparison_uses_unrounded_decimals() -> None:
    reference = Decimal("-1.0000003")
    assert _ordering(Decimal("-1.0000004"), reference) == "more_negative_than_final_delta"
    assert _ordering(Decimal("-1.0000002"), reference) == "less_negative_than_final_delta"
    assert _ordering(reference, reference) == "equal_to_final_delta"


def test_changed_workbook_is_rejected_before_placebo_analysis(tmp_path: Path) -> None:
    changed = tmp_path / "source.xlsx"
    changed.write_bytes(DEFAULT_INPUT.read_bytes() + b"altered copy")
    with pytest.raises(SchoolWasteError, match="source SHA-256 differs"):
        analyze_placebo_cutoffs(changed)
