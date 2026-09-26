#!/usr/bin/env python3
"""
analysis.py - Análisis observacional de consumo eléctrico de electrodomésticos (Brazo T)

Dataset: sample_first_complete_week.csv (UCI Appliances Energy Prediction, Candanedo et al.)
Periodo: 2016-01-12 00:00:00 a 2016-01-18 23:50:00 (7 días completos)
"""

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path


def analyze_energy_data(csv_path: str) -> dict:
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"No se encontró el archivo: {csv_path}")

    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    num_rows = len(rows)
    if num_rows == 0:
        raise ValueError("El archivo CSV está vacío.")

    # Parse timestamps
    timestamps = []
    for i, r in enumerate(rows):
        dt = datetime.strptime(r["date"].strip(), "%Y-%m-%d %H:%M:%S")
        timestamps.append(dt)

    # Verification of continuity and interval count
    expected_rows = 7 * 24 * 6  # 7 days * 24 hours * 6 intervals per hour = 1008
    intervals_ok = (num_rows == expected_rows)

    step_diffs = []
    discontinuities = []
    for i in range(len(timestamps) - 1):
        diff = (timestamps[i + 1] - timestamps[i]).total_seconds() / 60.0
        step_diffs.append(diff)
        if diff != 10.0:
            discontinuities.append((i, timestamps[i], timestamps[i + 1], diff))

    continuity_ok = (len(discontinuities) == 0)

    # Energy calculations
    appliances_wh = [float(r["Appliances"]) for r in rows]
    lights_wh = [float(r["lights"]) for r in rows]

    total_appliances_wh = sum(appliances_wh)
    total_appliances_kwh = total_appliances_wh / 1000.0

    total_lights_wh = sum(lights_wh)
    total_lights_kwh = total_lights_wh / 1000.0

    # Daily breakdown
    daily_stats = {}
    for dt, app_wh, lgt_wh in zip(timestamps, appliances_wh, lights_wh):
        day_key = dt.strftime("%Y-%m-%d")
        if day_key not in daily_stats:
            daily_stats[day_key] = {
                "appliances_wh": 0.0,
                "lights_wh": 0.0,
                "count": 0,
                "max_app_wh": 0.0,
                "min_app_wh": float("inf"),
            }
        daily_stats[day_key]["appliances_wh"] += app_wh
        daily_stats[day_key]["lights_wh"] += lgt_wh
        daily_stats[day_key]["count"] += 1
        if app_wh > daily_stats[day_key]["max_app_wh"]:
            daily_stats[day_key]["max_app_wh"] = app_wh
        if app_wh < daily_stats[day_key]["min_app_wh"]:
            daily_stats[day_key]["min_app_wh"] = app_wh

    # Additional pertinent observations:
    # 1. Nocturnal base-load (01:00 - 05:50) vs Active daytime/evening load (06:00 - 23:50)
    night_wh = [app_wh for dt, app_wh in zip(timestamps, appliances_wh) if 1 <= dt.hour < 6]
    day_wh = [app_wh for dt, app_wh in zip(timestamps, appliances_wh) if not (1 <= dt.hour < 6)]

    night_total_kwh = sum(night_wh) / 1000.0
    day_total_kwh = sum(day_wh) / 1000.0
    night_mean_wh = sum(night_wh) / len(night_wh) if night_wh else 0.0
    day_mean_wh = sum(day_wh) / len(day_wh) if day_wh else 0.0

    # 2. Distribution / extremes
    min_app_wh = min(appliances_wh)
    max_app_wh = max(appliances_wh)
    mean_app_wh = total_appliances_wh / num_rows

    results = {
        "num_rows": num_rows,
        "expected_rows": expected_rows,
        "intervals_ok": intervals_ok,
        "continuity_ok": continuity_ok,
        "start_time": timestamps[0].strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": timestamps[-1].strftime("%Y-%m-%d %H:%M:%S"),
        "total_appliances_wh": total_appliances_wh,
        "total_appliances_kwh": total_appliances_kwh,
        "total_lights_wh": total_lights_wh,
        "total_lights_kwh": total_lights_kwh,
        "daily_stats": daily_stats,
        "night_total_kwh": night_total_kwh,
        "day_total_kwh": day_total_kwh,
        "night_mean_wh_per_10min": night_mean_wh,
        "day_mean_wh_per_10min": day_mean_wh,
        "min_appliances_wh_per_10min": min_app_wh,
        "max_appliances_wh_per_10min": max_app_wh,
        "mean_appliances_wh_per_10min": mean_app_wh,
    }

    return results


def print_report(results: dict):
    print("=" * 70)
    print("REPORTE DE ANÁLISIS OBSERVACIONAL DE ENERGÍA (analysis.py)")
    print("=" * 70)
    print(f"Intervalos observados:    {results['num_rows']} (esperados: {results['expected_rows']})")
    print(f"Verificación continuidad: {'CORRECTA (10 min exactos sin huecos)' if results['continuity_ok'] else 'ERROR'}")
    print(f"Rango temporal:           {results['start_time']} -> {results['end_time']}")
    print("-" * 70)
    print(f"Total semanal Appliances: {results['total_appliances_kwh']:.3f} kWh ({results['total_appliances_wh']:.1f} Wh)")
    print(f"Total semanal Lights:     {results['total_lights_kwh']:.3f} kWh ({results['total_lights_wh']:.1f} Wh)")
    print("-" * 70)
    print("DESGLOSE DIARIO DE APPLIANCES:")
    for day, st in results["daily_stats"].items():
        kwh = st["appliances_wh"] / 1000.0
        print(f"  {day}: {kwh:6.3f} kWh ({st['appliances_wh']:8.1f} Wh) | "
              f"Min: {st['min_app_wh']:4.0f} Wh, Max: {st['max_app_wh']:4.0f} Wh | "
              f"Lights: {st['lights_wh']/1000.0:5.3f} kWh")
    print("-" * 70)
    print("OBSERVACIONES ADICIONALES PERTINENTES:")
    print(f"  - Carga base nocturna (01:00-05:50): {results['night_total_kwh']:.3f} kWh "
          f"({results['night_mean_wh_per_10min']:.1f} Wh/intervalo de 10 min, eq. {results['night_mean_wh_per_10min']*6:.1f} W de potencia media continua).")
    print(f"  - Carga diurna/vespertina (06:00-00:50): {results['day_total_kwh']:.3f} kWh "
          f"({results['day_mean_wh_per_10min']:.1f} Wh/intervalo de 10 min, eq. {results['day_mean_wh_per_10min']*6:.1f} W de potencia media continua).")
    print(f"  - Consumo mínimo de intervalo: {results['min_appliances_wh_per_10min']:.0f} Wh "
          f"(eq. {results['min_appliances_wh_per_10min']*6:.0f} W continuos de standby).")
    print(f"  - Consumo máximo de intervalo: {results['max_appliances_wh_per_10min']:.0f} Wh "
          f"(eq. {results['max_appliances_wh_per_10min']*6:.0f} W pico medio en 10 min).")
    print(f"  - Media global por intervalo:  {results['mean_appliances_wh_per_10min']:.1f} Wh "
          f"(eq. {results['mean_appliances_wh_per_10min']*6:.1f} W de potencia media constante).")
    print("=" * 70)


def main():
    csv_file = "sample_first_complete_week.csv"
    try:
        results = analyze_energy_data(csv_file)
        print_report(results)
    except Exception as e:
        print(f"Error ejecutando el análisis: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
