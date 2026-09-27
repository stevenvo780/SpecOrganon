"""Exploratory temporal sensitivity for the pinned school-meal waste workbook.

Usage: ``python3 scripts/school_waste_temporal.py > /tmp/school_waste_temporal.json``.
The JSON contains descriptive contrasts only. It does not estimate intervention
effects, causal uncertainty, or criterion 3 for the food-chain problem.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from typing import Any

from analyze_school_waste import (
    DEFAULT_INPUT,
    SOURCE_SHA256,
    Day,
    SchoolWasteError,
    analyze_xlsx,
    read_days,
)


METRICS = ("pw", "ksw", "total")
DISCORDANT_ROWS = (137, 152)
PLACES = Decimal("0.000001")


def _decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.quantize(PLACES, rounding=ROUND_HALF_EVEN), ".6f")


def _eligible(days: list[Day], metric: str) -> list[Day]:
    return days if metric == "pw" else [day for day in days if day.ksw_kg is not None]


def _mass(day: Day, metric: str) -> Decimal:
    if metric == "pw":
        return day.pw_kg
    assert day.ksw_kg is not None
    return day.ksw_kg if metric == "ksw" else day.pw_kg + day.ksw_kg


def _rate(days: list[Day], metric: str) -> Decimal:
    eligible = _eligible(days, metric)
    if not eligible:
        raise SchoolWasteError(f"{metric} has no eligible days in temporal sensitivity")
    return (
        Decimal(1000)
        * sum((_mass(day, metric) for day in eligible), Decimal(0))
        / sum(day.diners for day in eligible)
    )


def _period(days: list[Day]) -> dict[str, Any]:
    if not days:
        raise SchoolWasteError("temporal sensitivity period is empty")
    metrics = {}
    for metric in METRICS:
        eligible = _eligible(days, metric)
        metrics[metric] = {
            "eligible_days": len(eligible),
            "denominator_diners": sum(day.diners for day in eligible),
            "sum_kg": _decimal(
                sum((_mass(day, metric) for day in eligible), Decimal(0))
            ),
            "g_per_diner": _decimal(_rate(days, metric)),
        }
    return {
        "first_date": days[0].day.isoformat(),
        "last_date": days[-1].day.isoformat(),
        "first_xlsx_row": days[0].xlsx_row,
        "last_xlsx_row": days[-1].xlsx_row,
        "rows": [day.xlsx_row for day in days],
        "days": len(days),
        "metrics": metrics,
    }


def _contrast(baseline: list[Day], post: list[Day]) -> dict[str, Any]:
    result = {}
    for metric in METRICS:
        before = _rate(baseline, metric)
        after = _rate(post, metric)
        difference = after - before
        result[metric] = {
            "post_minus_baseline_g_per_diner": _decimal(difference),
            "percent_change_from_baseline": (
                _decimal(Decimal(100) * difference / before) if before else None
            ),
        }
    return result


def _window_envelope(windows: list[list[Day]], post: list[Day]) -> dict[str, Any]:
    result = {}
    for metric in METRICS:
        post_rate = _rate(post, metric)
        differences = [post_rate - _rate(window, metric) for window in windows]
        result[metric] = {
            "post_minus_window_range_g_per_diner": [
                _decimal(min(differences)),
                _decimal(max(differences)),
            ],
            "windows_with_negative_difference": sum(value < 0 for value in differences),
            "windows_with_zero_difference": sum(value == 0 for value in differences),
            "windows_with_positive_difference": sum(value > 0 for value in differences),
        }
    return result


def _post_weeks(post: list[Day], latest_window: list[Day]) -> list[dict[str, Any]]:
    result = []
    for index in range(4):
        days = post[index * 5 : (index + 1) * 5]
        if len(days) != 5 or [day.day.weekday() for day in days] != list(range(5)):
            raise SchoolWasteError(
                f"post block {index + 1} is not a Monday-Friday week"
            )
        if len({day.day.isocalendar()[:2] for day in days}) != 1:
            raise SchoolWasteError(f"post block {index + 1} crosses calendar weeks")
        without_discordance = [
            day for day in days if day.xlsx_row not in DISCORDANT_ROWS
        ]
        result.append(
            {
                "week": index + 1,
                "iso_week": f"{days[0].day.isocalendar().year}-W{days[0].day.isocalendar().week:02d}",
                "observed": _period(days),
                "observed_minus_latest_baseline_window": _contrast(latest_window, days),
                "excluding_discordant_rows": (
                    {
                        "period": _period(without_discordance),
                        "minus_latest_baseline_window": _contrast(
                            latest_window, without_discordance
                        ),
                    }
                    if len(without_discordance) != len(days)
                    else None
                ),
            }
        )
    return result


def analyze_temporal(path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    """Analyze the fixed XLSX using the existing hash, schema, and audit checks."""
    original = analyze_xlsx(path)
    with localcontext() as context:
        context.prec = 50
        days = read_days(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_SHA256:
            raise SchoolWasteError(
                "source SHA-256 changed during temporal sensitivity read"
            )
        baseline, post = days[:135], days[135:]
        observed_discordance = sorted(
            {
                discrepancy["xlsx_row"]
                for audit in original["derived_column_audit"].values()
                for discrepancy in audit["beyond_tolerance"]
            }
        )
        if observed_discordance != list(DISCORDANT_ROWS):
            raise SchoolWasteError(
                f"unexpected rows with derived-column discordance: {observed_discordance}"
            )
        for metric in METRICS:
            for name, period in (("baseline", baseline), ("intervention", post)):
                if (
                    _decimal(_rate(period, metric))
                    != original["metrics"][metric]["periods"][name]["g_per_diner"]
                ):
                    raise SchoolWasteError(
                        f"{metric} {name} does not reproduce fixed analysis"
                    )

        candidates = [
            baseline[start : start + 20] for start in range(len(baseline) - 19)
        ]
        windows = [
            (index + 1, candidate)
            for index, candidate in enumerate(candidates)
            if all(day.ksw_kg is not None for day in candidate)
        ]
        if not windows:
            raise SchoolWasteError(
                "no 20-day baseline window has complete component masses"
            )
        latest_number, latest = windows[-1]
        excluded_windows = [
            {
                "window_index": index + 1,
                "first_xlsx_row": candidate[0].xlsx_row,
                "last_xlsx_row": candidate[-1].xlsx_row,
                "missing_ksw_rows": [
                    day.xlsx_row for day in candidate if day.ksw_kg is None
                ],
            }
            for index, candidate in enumerate(candidates)
            if any(day.ksw_kg is None for day in candidate)
        ]
        post_without_discordance = [
            day for day in post if day.xlsx_row not in DISCORDANT_ROWS
        ]

        return {
            "schema": 1,
            "classification": "exploratory_descriptive_temporal_sensitivity",
            "source": original["source"],
            "prior_plan": original["prior_plan"],
            "rules": {
                "baseline_windows": "all rolling blocks of 20 consecutive recorded baseline days; retain only blocks with both source masses on every day",
                "post_final": "the 20 final recorded days, split into four chronological Monday-Friday blocks of five",
                "estimator": "1000 * sum(component kg) / sum(diners) on eligible days; Decimal arithmetic, six-place half-even output",
                "discordance_exclusion": "drop whole post rows 137 and 152 only in separately labelled sensitivity calculations; never substitute cached derived cells",
                "comparison": "post ratio minus baseline ratio; relative difference divided by baseline ratio",
            },
            "quality": {
                "baseline_missing_ksw_rows": [
                    day.xlsx_row for day in baseline if day.ksw_kg is None
                ],
                "post_derived_discordance_rows": observed_discordance,
                "derived_discordance_by_column": {
                    name: [item["xlsx_row"] for item in audit["beyond_tolerance"]]
                    for name, audit in original["derived_column_audit"].items()
                },
            },
            "descriptive": {
                "full_baseline": _period(baseline),
                "final_post_20": _period(post),
                "post_20_minus_full_baseline": _contrast(baseline, post),
                "baseline_20_day_windows": {
                    "candidate_count": len(candidates),
                    "excluded_incomplete_count": len(excluded_windows),
                    "excluded_incomplete_windows": excluded_windows,
                    "complete_count": len(windows),
                    "complete_windows": [
                        {"window_index": number, "period": _period(window)}
                        for number, window in windows
                    ],
                    "latest_complete_window_index": latest_number,
                    "latest_complete_window": _period(latest),
                },
                "post_20_minus_baseline_windows": _window_envelope(
                    [window for _, window in windows], post
                ),
                "post_20_minus_latest_baseline_window": _contrast(latest, post),
                "post_weeks": _post_weeks(post, latest),
                "discordance_exclusion": {
                    "excluded_xlsx_rows": list(DISCORDANT_ROWS),
                    "post_remaining": _period(post_without_discordance),
                    "post_remaining_minus_full_baseline": _contrast(
                        baseline, post_without_discordance
                    ),
                    "post_remaining_minus_latest_baseline_window": _contrast(
                        latest, post_without_discordance
                    ),
                    "post_remaining_minus_baseline_windows": _window_envelope(
                        [window for _, window in windows], post_without_discordance
                    ),
                },
            },
            "inference": {
                "status": "not_estimated",
                "reason": "Single school and successive periods have no contemporary untreated comparison; temporal, seasonal, attendance, and changing weekly concepts remain unseparated.",
            },
            "limits": [
                "Rolling baseline windows overlap, so their counts and ranges are descriptive, not independent replications or uncertainty intervals.",
                "Removing discordant derived rows probes dependence on those dates; it cannot determine whether source masses were also wrong.",
                "Four post weeks represent different concepts and calendar weeks; their contrasts do not isolate either concept or time.",
                "The workbook covers plate and kitchen/service waste only, not the full food chain, costs, safety, or effects by actor.",
            ],
            "criterion_3": "not_demonstrated",
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args(argv)
    try:
        result = analyze_temporal(args.input)
    except (OSError, SchoolWasteError) as exc:
        parser.exit(2, f"school-waste temporal sensitivity failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
