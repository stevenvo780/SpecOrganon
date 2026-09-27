"""Exploratory baseline-only placebo cutoffs for the pinned Finnish school XLSX.

Usage: ``python3 scripts/school_waste_placebo_cutoffs.py > /tmp/school_placebos.json``.
This is a descriptive temporal check, not a causal test or a p-value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

from analyze_school_waste import DEFAULT_INPUT, SOURCE_SHA256, Day, SchoolWasteError, read_days
from school_waste_temporal import METRICS, _decimal, _period, _rate, analyze_temporal


WINDOW_DAYS = 20
BASELINE_DAYS = 135


def _span(days: list[Day]) -> dict[str, Any]:
    """Describe an excluded window without calculating an ineligible ratio."""
    return {
        "first_date": days[0].day.isoformat(),
        "last_date": days[-1].day.isoformat(),
        "first_xlsx_row": days[0].xlsx_row,
        "last_xlsx_row": days[-1].xlsx_row,
        "observed_days": len(days),
        "observed_diners": sum(day.diners for day in days),
    }


def _ordering(value: Decimal, reference: Decimal) -> str:
    if value < reference:
        return "more_negative_than_final_delta"
    if value > reference:
        return "less_negative_than_final_delta"
    return "equal_to_final_delta"


def analyze_placebo_cutoffs(path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    """Compare adjacent complete 20+20 recorded baseline days with the final cut."""
    temporal = analyze_temporal(path)
    with localcontext() as context:
        context.prec = 50
        days = read_days(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_SHA256:
            raise SchoolWasteError("source SHA-256 changed during placebo cutoff read")
        baseline, final = days[:BASELINE_DAYS], days[BASELINE_DAYS:]
        latest = baseline[-WINDOW_DAYS:]
        prior = temporal["descriptive"]
        if (
            _period(latest) != prior["baseline_20_day_windows"]["latest_complete_window"]
            or _period(final) != prior["final_post_20"]
        ):
            raise SchoolWasteError("placebo reference differs from fixed temporal analysis")

        final_deltas = {
            metric: _rate(final, metric) - _rate(latest, metric)
            for metric in METRICS
        }
        for metric, delta in final_deltas.items():
            if _decimal(delta) != prior["post_20_minus_latest_baseline_window"][metric][
                "post_minus_baseline_g_per_diner"
            ]:
                raise SchoolWasteError(f"{metric} final contrast differs from fixed temporal analysis")

        included: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        raw_deltas: dict[str, list[Decimal]] = {metric: [] for metric in METRICS}
        comparison_counts: dict[str, dict[str, int]] = {
            metric: {
                "more_negative_than_final_delta": 0,
                "equal_to_final_delta": 0,
                "less_negative_than_final_delta": 0,
            }
            for metric in METRICS
        }
        for cut in range(WINDOW_DAYS, len(baseline) - WINDOW_DAYS + 1):
            before = baseline[cut - WINDOW_DAYS : cut]
            after = baseline[cut : cut + WINDOW_DAYS]
            common = {
                "cutoff_index": cut - WINDOW_DAYS + 1,
                "before_last_date": before[-1].day.isoformat(),
                "after_first_date": after[0].day.isoformat(),
            }
            missing = [
                {"date": day.day.isoformat(), "xlsx_row": day.xlsx_row, "window": name}
                for name, window in (("before", before), ("after", after))
                for day in window
                if day.ksw_kg is None
            ]
            if missing:
                excluded.append({
                    **common,
                    "before": _span(before),
                    "after": _span(after),
                    "missing_ksw": missing,
                    "reason": "missing KSW kg in the 40 observed days; exclude the whole cutoff for PW, KSW, and total to keep the same days",
                })
                continue

            deltas = {
                metric: _rate(after, metric) - _rate(before, metric)
                for metric in METRICS
            }
            comparisons = {
                metric: _ordering(delta, final_deltas[metric])
                for metric, delta in deltas.items()
            }
            for metric, delta in deltas.items():
                raw_deltas[metric].append(delta)
                comparison_counts[metric][comparisons[metric]] += 1
            included.append({
                **common,
                "before": _period(before),
                "after": _period(after),
                "after_minus_before_g_per_diner": {
                    metric: _decimal(delta) for metric, delta in deltas.items()
                },
                "comparison_to_final_delta": comparisons,
            })

        return {
            "schema": 1,
            "classification": "exploratory_descriptive_baseline_placebo_cutoffs",
            "source": temporal["source"],
            "prior_plan": temporal["prior_plan"],
            "rules": {
                "candidate_cutoffs": "every split with 20 recorded baseline observations before and 20 after, in worksheet/date order; adjacent observations need not be consecutive calendar dates",
                "complete_case": "include a cutoff only when all 40 observations have KSW kg; PW, KSW, and total then use identical days and diner denominators",
                "estimator": temporal["rules"]["estimator"],
                "delta": "after minus before in g per diner; compare unrounded Decimal deltas with final 20 minus latest complete baseline 20, then round displayed values to six places",
            },
            "quality": {
                "baseline_missing_ksw_rows": temporal["quality"]["baseline_missing_ksw_rows"],
                "baseline_missing_pw_rows": [],
                "missing_pw_rule": "PW kg is required by the pinned reader; a missing PW value rejects the workbook before this analysis",
            },
            "reference": {
                "latest_complete_baseline_20": _period(latest),
                "final_20": _period(final),
                "final_minus_latest_baseline_20_g_per_diner": {
                    metric: _decimal(delta) for metric, delta in final_deltas.items()
                },
            },
            "candidate_count": len(included) + len(excluded),
            "included_count": len(included),
            "excluded_count": len(excluded),
            "cutoffs": included,
            "excluded_cutoffs": excluded,
            "descriptive_comparison": {
                metric: {
                    "placebo_delta_range_g_per_diner": [
                        _decimal(min(raw_deltas[metric])),
                        _decimal(max(raw_deltas[metric])),
                    ],
                    "comparison_counts": comparison_counts[metric],
                }
                for metric in METRICS
            },
            "inference": {
                "status": "not_estimated",
                "reason": "Adjacent 40-day cuts overlap heavily, and a single-school baseline can drift with calendar time, menus, and attendance; these are dependent descriptive contrasts, not an independent null distribution or causal p-value.",
            },
            "criterion_3": "not_demonstrated",
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args(argv)
    try:
        result = analyze_placebo_cutoffs(args.input)
    except (OSError, SchoolWasteError) as exc:
        parser.exit(2, f"school-waste placebo cutoffs failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
