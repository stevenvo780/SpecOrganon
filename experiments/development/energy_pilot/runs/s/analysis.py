#!/usr/bin/env python3
"""
Analysis script for appliances energy dataset (Feasibility Run - SDD Arm S).
Uses only Python Standard Library.
"""

import csv
import datetime
import math
import sys
from collections import defaultdict
from pathlib import Path


def parse_row(row):
    """Parses a CSV row into appropriate Python data types."""
    dt = datetime.datetime.strptime(row["date"].strip(), "%Y-%m-%d %H:%M:%S")
    appliances = float(row["Appliances"].strip())
    lights = float(row["lights"].strip())
    t_out = float(row["T_out"].strip())
    rh_out = float(row["RH_out"].strip())
    wind = float(row["Windspeed"].strip())
    press = float(row["Press_mm_hg"].strip())
    t_indoor = {f"T{i}": float(row[f"T{i}"].strip()) for i in range(1, 10)}
    rh_indoor = {f"RH_{i}": float(row[f"RH_{i}"].strip()) for i in range(1, 10)}
    
    return {
        "date": dt,
        "Appliances": appliances,
        "lights": lights,
        "T_out": t_out,
        "RH_out": rh_out,
        "Windspeed": wind,
        "Press_mm_hg": press,
        "T_indoor": t_indoor,
        "RH_indoor": rh_indoor,
    }


def verify_dataset(data):
    """Verifies row count, time range, and continuity of 10-minute intervals."""
    n_records = len(data)
    expected_rows = 1008
    status = {"valid_count": n_records == expected_rows, "count": n_records}
    
    if n_records == 0:
        status["continuous"] = False
        status["error"] = "Dataset is empty"
        return status

    start_dt = data[0]["date"]
    end_dt = data[-1]["date"]
    expected_start = datetime.datetime(2016, 1, 12, 0, 0, 0)
    expected_end = datetime.datetime(2016, 1, 18, 23, 50, 0)
    
    status["start_dt"] = start_dt
    status["end_dt"] = end_dt
    status["valid_range"] = (start_dt == expected_start and end_dt == expected_end)
    
    continuity_ok = True
    gaps = []
    for i in range(1, n_records):
        delta = data[i]["date"] - data[i-1]["date"]
        if delta != datetime.timedelta(minutes=10):
            continuity_ok = False
            gaps.append((data[i-1]["date"], data[i]["date"], delta))
            
    status["continuous"] = continuity_ok
    status["gaps"] = gaps
    return status


def compute_statistics(data):
    """Computes totals, daily breakdowns, and additional observations."""
    appliances_wh = [d["Appliances"] for d in data]
    lights_wh = [d["lights"] for d in data]
    
    # Weekly totals in kWh
    weekly_appliances_kwh = sum(appliances_wh) / 1000.0
    weekly_lights_kwh = sum(lights_wh) / 1000.0
    
    # Daily breakdown
    daily_appliances_wh = defaultdict(float)
    daily_lights_wh = defaultdict(float)
    daily_counts = defaultdict(int)
    
    # Diurnal breakdown (Night: 00:00-06:00, Day: 06:00-18:00, Evening: 18:00-24:00)
    diurnal_appliances_wh = defaultdict(float)
    
    for d in data:
        day_str = d["date"].strftime("%Y-%m-%d")
        daily_appliances_wh[day_str] += d["Appliances"]
        daily_lights_wh[day_str] += d["lights"]
        daily_counts[day_str] += 1
        
        hour = d["date"].hour
        if 0 <= hour < 6:
            period = "Night (00:00-06:00)"
        elif 6 <= hour < 18:
            period = "Daytime (06:00-18:00)"
        else:
            period = "Evening Peak (18:00-24:00)"
        diurnal_appliances_wh[period] += d["Appliances"]

    daily_appliances_kwh = {k: v / 1000.0 for k, v in sorted(daily_appliances_wh.items())}
    daily_lights_kwh = {k: v / 1000.0 for k, v in sorted(daily_lights_wh.items())}
    
    # Summary stats for Appliances
    sorted_app = sorted(appliances_wh)
    n = len(sorted_app)
    mean_app = sum(sorted_app) / n
    variance = sum((x - mean_app) ** 2 for x in sorted_app) / (n - 1)
    std_app = math.sqrt(variance)
    median_app = sorted_app[n // 2] if n % 2 != 0 else (sorted_app[n // 2 - 1] + sorted_app[n // 2]) / 2.0
    q1_app = sorted_app[n // 4]
    q3_app = sorted_app[(3 * n) // 4]
    min_app = sorted_app[0]
    max_app = sorted_app[-1]
    
    # Baseload / Standby estimation: lowest 10% quantile
    baseload_q10 = sorted_app[int(n * 0.10)]
    
    # Temperatures summary
    t_out_vals = [d["T_out"] for d in data]
    mean_t_out = sum(t_out_vals) / len(t_out_vals)
    min_t_out = min(t_out_vals)
    max_t_out = max(t_out_vals)
    
    t_in_means = {}
    for i in range(1, 10):
        vals = [d["T_indoor"][f"T{i}"] for d in data]
        t_in_means[f"T{i}"] = sum(vals) / len(vals)
        
    return {
        "weekly_appliances_kwh": weekly_appliances_kwh,
        "weekly_lights_kwh": weekly_lights_kwh,
        "daily_appliances_kwh": daily_appliances_kwh,
        "daily_lights_kwh": daily_lights_kwh,
        "daily_counts": dict(daily_counts),
        "diurnal_appliances_kwh": {k: v / 1000.0 for k, v in diurnal_appliances_wh.items()},
        "diurnal_pct": {k: (v / sum(appliances_wh)) * 100.0 for k, v in diurnal_appliances_wh.items()},
        "appliances_stats_wh": {
            "mean": mean_app,
            "std": std_app,
            "median": median_app,
            "q1": q1_app,
            "q3": q3_app,
            "min": min_app,
            "max": max_app,
            "q10_baseload": baseload_q10,
        },
        "temperature_stats_c": {
            "mean_t_out": mean_t_out,
            "min_t_out": min_t_out,
            "max_t_out": max_t_out,
            "indoor_means": t_in_means,
        }
    }


def main():
    csv_path = Path(__file__).resolve().parent / "sample_first_complete_week.csv"
    if not csv_path.exists():
        print(f"Error: File not found at {csv_path}", file=sys.stderr)
        sys.exit(1)
        
    raw_rows = []
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            raw_rows.append(parse_row(r))
            
    # Step 1: Verification
    verif = verify_dataset(raw_rows)
    print("=" * 60)
    print("DATASET VERIFICATION RESULTS (SDD Requirement 1)")
    print("=" * 60)
    print(f"Total rows read: {verif['count']} (Expected: 1008) -> Valid: {verif['valid_count']}")
    print(f"Start date: {verif['start_dt']} | End date: {verif['end_dt']} -> Valid: {verif['valid_range']}")
    print(f"Continuity check (10-min step): {'PASSED (No gaps)' if verif['continuous'] else 'FAILED'}")
    if not verif['continuous']:
        print(f"Gaps found: {verif['gaps']}")
    print()

    # Step 2: Statistics Computation
    stats = compute_statistics(raw_rows)
    print("=" * 60)
    print("ENERGY METRICS (Appliances & Lights)")
    print("=" * 60)
    print(f"Total Weekly Appliances Energy: {stats['weekly_appliances_kwh']:.3f} kWh ({stats['weekly_appliances_kwh']*1000:.1f} Wh)")
    print(f"Total Weekly Lights Energy:     {stats['weekly_lights_kwh']:.3f} kWh ({stats['weekly_lights_kwh']*1000:.1f} Wh)")
    print()
    print("Daily Appliances Consumption Breakdown (kWh/day):")
    for day, val in stats["daily_appliances_kwh"].items():
        weekday = datetime.datetime.strptime(day, "%Y-%m-%d").strftime("%A")
        print(f"  - {day} ({weekday:9s}): {val:7.3f} kWh (Intervals: {stats['daily_counts'][day]})")
    print()
    print("Daily Lights Consumption Breakdown (kWh/day):")
    for day, val in stats["daily_lights_kwh"].items():
        print(f"  - {day}: {val:6.3f} kWh")
    print()
    print("=" * 60)
    print("ADDITIONAL PERTINENT OBSERVATIONS")
    print("=" * 60)
    app_s = stats["appliances_stats_wh"]
    print("Appliances Interval Distribution (Wh per 10-min interval):")
    print(f"  - Min:    {app_s['min']:.1f} Wh")
    print(f"  - Q1:     {app_s['q1']:.1f} Wh")
    print(f"  - Median: {app_s['median']:.1f} Wh")
    print(f"  - Mean:   {app_s['mean']:.1f} Wh (Std: {app_s['std']:.1f} Wh)")
    print(f"  - Q3:     {app_s['q3']:.1f} Wh")
    print(f"  - Max:    {app_s['max']:.1f} Wh")
    print(f"  - 10th Percentile (Baseload / Standby indicator): {app_s['q10_baseload']:.1f} Wh")
    print()
    print("Diurnal Appliances Consumption Breakdown:")
    for period, kwh in stats["diurnal_appliances_kwh"].items():
        pct = stats["diurnal_pct"][period]
        print(f"  - {period:26s}: {kwh:7.3f} kWh ({pct:5.1f}%)")
    print()
    t_s = stats["temperature_stats_c"]
    print("Outdoor Temperature (°C):")
    print(f"  - Mean: {t_s['mean_t_out']:.2f} °C, Min: {t_s['min_t_out']:.2f} °C, Max: {t_s['max_t_out']:.2f} °C")
    print("Indoor Mean Temperatures (°C):")
    for room, temp in t_s["indoor_means"].items():
        print(f"  - {room}: {temp:.2f} °C")
    print("=" * 60)
    print("Note: rv1 and rv2 random variables were excluded from predictive/causal logic.")
    print("=" * 60)


if __name__ == "__main__":
    main()
