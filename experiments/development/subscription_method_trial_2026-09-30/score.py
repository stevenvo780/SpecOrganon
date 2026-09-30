"""Frozen numerical projection for the exposed D099 bridge, not a Q judge."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CSV = ROOT / "cases/building_energy/sample_first_complete_week.csv"
CSV_SHA = "c7f66ffaadc4e38375a7edf03091bae4fc861880510867903487eec83f05e6ba"


def reference() -> dict:
    raw = CSV.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CSV_SHA:
        raise ValueError("reference source differs from the pinned public CSV")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True))
    if not rows:
        raise ValueError("empty source")
    dates = [datetime.strptime(row["date"], "%Y-%m-%d %H:%M:%S") for row in rows]
    appliances = [Decimal(row["Appliances"]) for row in rows]
    lights = [Decimal(row["lights"]) for row in rows]
    if any(not value.is_finite() or value < 0 for value in appliances + lights):
        raise ValueError("invalid source energy quantity")
    daily = defaultdict(Decimal)
    for stamp, quantity in zip(dates, appliances, strict=True):
        daily[stamp.date().isoformat()] += quantity
    return {
        "rows": len(rows),
        "first_timestamp": rows[0]["date"],
        "last_timestamp": rows[-1]["date"],
        "interval_minutes": 10,
        "continuous": all(right - left == timedelta(minutes=10)
                          for left, right in zip(dates, dates[1:])),
        "appliances_total_kwh": float(sum(appliances) / 1000),
        "daily_appliances_kwh": {day: float(value / 1000) for day, value in sorted(daily.items())},
        "lights_total_kwh": float(sum(lights) / 1000),
        "units": {key: "kWh" for key in
                  ("appliances_total_kwh", "daily_appliances_kwh", "lights_total_kwh")},
    }


def _number(value, expected) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and math.isclose(value, expected, rel_tol=0, abs_tol=1e-9)
    except (OverflowError, ValueError):
        return False


def project(metrics: dict, expected: dict) -> dict:
    if type(metrics) is not dict:
        raise ValueError("metrics must be an object")
    checks = {
        "rows": type(metrics.get("rows")) is int and metrics["rows"] == expected["rows"],
        "first_timestamp": metrics.get("first_timestamp") == expected["first_timestamp"],
        "last_timestamp": metrics.get("last_timestamp") == expected["last_timestamp"],
        "interval_minutes": _number(metrics.get("interval_minutes"), expected["interval_minutes"]),
        "continuous": type(metrics.get("continuous")) is bool
                      and metrics["continuous"] == expected["continuous"],
        "appliances_total_kwh": _number(metrics.get("appliances_total_kwh"),
                                        expected["appliances_total_kwh"]),
        "lights_total_kwh": _number(metrics.get("lights_total_kwh"), expected["lights_total_kwh"]),
    }
    daily = metrics.get("daily_appliances_kwh")
    if type(daily) is not dict:
        daily = {}
    checks["daily_date_set"] = daily.keys() == expected["daily_appliances_kwh"].keys()
    for day, value in expected["daily_appliances_kwh"].items():
        checks["daily_appliances_kwh." + day] = _number(daily.get(day), value)
    units = metrics.get("units")
    if type(units) is not dict:
        units = {}
    for key in expected["units"]:
        checks["units." + key] = units.get(key) == "kWh"
    return {
        "checks": checks, "passed": sum(checks.values()), "total": len(checks),
        "classification": "exposed_CSV_numerical_and_output_contract_projection",
        "source_integrity_checked_by_this_projection": False,
        "report_quality_measured": False, "causal_claims_verified": False,
        "normative_authority_verified": False, "Q": None,
        "counts_toward_required_24_runs": False, "global_acceptance": "0/5",
    }


if __name__ == "__main__":
    print(json.dumps(reference(), ensure_ascii=False, indent=2))
