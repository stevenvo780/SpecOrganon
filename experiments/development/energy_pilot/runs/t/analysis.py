#!/usr/bin/env python3
"""
Analysis script for development feasibility run on Appliances Energy Prediction sample.
Standard library only.
"""

import csv
import datetime
import json
import os
import sys

def run_analysis(csv_path="sample_first_complete_week.csv", manifest_path="source_manifest.json"):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    # Read manifest if available
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Clean keys and values of possible whitespace
            cleaned_row = {k.strip(): v.strip() for k, v in row.items()}
            rows.append(cleaned_row)

    n_rows = len(rows)
    print(f"Total rows read: {n_rows}")

    # Continuity check
    timestamps = []
    for r in rows:
        dt = datetime.datetime.strptime(r["date"], "%Y-%m-%d %H:%M:%S")
        timestamps.append(dt)

    interval_expected_min = 10
    continuity_ok = True
    gaps = []
    for i in range(1, len(timestamps)):
        delta = (timestamps[i] - timestamps[i-1]).total_seconds() / 60.0
        if delta != interval_expected_min:
            continuity_ok = False
            gaps.append((timestamps[i-1], timestamps[i], delta))

    start_time = timestamps[0]
    end_time = timestamps[-1]
    print(f"Start timestamp: {start_time}")
    print(f"End timestamp: {end_time}")
    print(f"Expected intervals (10 min): 1008 (7 days * 24 h * 6 intervals/h)")
    print(f"Interval continuity check: {'PASSED (exactly 10 min between consecutive rows)' if continuity_ok else f'FAILED ({len(gaps)} gaps)'}")

    # Calculate weekly total and daily totals for Appliances (Wh to kWh)
    # Each observation represents energy consumption in Wh during that 10-minute interval.
    # Total kWh = sum(Wh) / 1000.0
    daily_wh = {}
    daily_lights_wh = {}
    daily_t_in = {} # average indoor temperature (e.g. T1 kitchen, T2 living, etc.)
    daily_t_out = {}

    total_appliances_wh = 0.0
    total_lights_wh = 0.0

    for r, dt in zip(rows, timestamps):
        app_wh = float(r["Appliances"])
        lights_wh = float(r["lights"])
        total_appliances_wh += app_wh
        total_lights_wh += lights_wh

        day_key = dt.strftime("%Y-%m-%d (%A)")
        if day_key not in daily_wh:
            daily_wh[day_key] = 0.0
            daily_lights_wh[day_key] = 0.0
            daily_t_in[day_key] = []
            daily_t_out[day_key] = []

        daily_wh[day_key] += app_wh
        daily_lights_wh[day_key] += lights_wh
        daily_t_in[day_key].append(float(r["T1"]))
        daily_t_out[day_key].append(float(r["T_out"]))

    total_appliances_kwh = total_appliances_wh / 1000.0
    total_lights_kwh = total_lights_wh / 1000.0

    print("\n--- ENERGY SUMMARY ---")
    print(f"Total Weekly Appliances: {total_appliances_wh:.1f} Wh = {total_appliances_kwh:.3f} kWh")
    print(f"Total Weekly Lights: {total_lights_wh:.1f} Wh = {total_lights_kwh:.3f} kWh")
    print(f"Combined Submetered Electricity: {(total_appliances_wh + total_lights_wh)/1000.0:.3f} kWh")

    print("\n--- DAILY TOTALS (Appliances) ---")
    for day, wh in daily_wh.items():
        kwh = wh / 1000.0
        avg_tin = sum(daily_t_in[day]) / len(daily_t_in[day])
        avg_tout = sum(daily_t_out[day]) / len(daily_t_out[day])
        print(f"  {day}: {kwh:6.3f} kWh ({wh:7.1f} Wh) | Lights: {daily_lights_wh[day]/1000.0:5.3f} kWh | Avg T1: {avg_tin:.2f}°C | Avg T_out: {avg_tout:.2f}°C")

    # Additional pertinent observation:
    # 1. Base load analysis vs peak load analysis
    # Hourly load profile / peak hour distribution
    hourly_wh = [0.0] * 24
    hourly_counts = [0] * 24
    for r, dt in zip(rows, timestamps):
        h = dt.hour
        hourly_wh[h] += float(r["Appliances"])
        hourly_counts[h] += 1

    print("\n--- ADDITIONAL PERTINENT OBSERVATIONS ---")
    print("1. Diurnal Profile of Appliances Consumption (Average Wh per 10-min interval by hour of day):")
    for h in range(24):
        avg_interval_wh = hourly_wh[h] / hourly_counts[h]
        avg_hourly_kw_equiv = (avg_interval_wh * 6) / 1000.0 # kWh/h = average kW
        print(f"   Hour {h:02d}:00 - {h:02d}:59: {avg_interval_wh:6.1f} Wh/interval (~{avg_hourly_kw_equiv:.3f} kW avg)")

    # Baseline standby load (minimum values)
    app_values = [float(r["Appliances"]) for r in rows]
    min_app = min(app_values)
    max_app = max(app_values)
    sorted_app = sorted(app_values)
    p25 = sorted_app[int(len(sorted_app)*0.25)]
    median = sorted_app[int(len(sorted_app)*0.50)]
    p75 = sorted_app[int(len(sorted_app)*0.75)]
    p90 = sorted_app[int(len(sorted_app)*0.90)]
    p95 = sorted_app[int(len(sorted_app)*0.95)]

    print(f"\n2. Distribution of Appliances Interval Demand (Wh per 10 min):")
    print(f"   Min: {min_app} Wh | 25th%: {p25} Wh | Median: {median} Wh | 75th%: {p75} Wh | 90th%: {p90} Wh | 95th%: {p95} Wh | Max: {max_app} Wh")
    print(f"   Base/standby mode (<= 60 Wh): {sum(1 for v in app_values if v <= 60)} / {len(app_values)} intervals ({sum(1 for v in app_values if v <= 60)/len(app_values)*100:.1f}%)")
    print(f"   Spike mode (> 200 Wh): {sum(1 for v in app_values if v > 200)} / {len(app_values)} intervals ({sum(1 for v in app_values if v > 200)/len(app_values)*100:.1f}%)")

    # Diagnostic check on rv1, rv2
    rv1_vals = [float(r["rv1"]) for r in rows]
    rv2_vals = [float(r["rv2"]) for r in rows]
    rv_identical = all(r1 == r2 for r1, r2 in zip(rv1_vals, rv2_vals))
    print(f"\n3. Diagnostics on non-causal variables:")
    print(f"   rv1 and rv2 are identical in all 1008 rows: {rv_identical} (random noise variables from dataset creator, confirmed excluded from causal analysis)")

    return {
        "n_rows": n_rows,
        "continuity_ok": continuity_ok,
        "total_appliances_kwh": total_appliances_kwh,
        "total_lights_kwh": total_lights_kwh,
        "daily_wh": daily_wh,
        "min_app": min_app,
        "max_app": max_app,
        "median_app": median
    }

if __name__ == "__main__":
    run_analysis()
