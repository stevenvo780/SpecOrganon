#!/usr/bin/env python3
"""
Analysis of energy consumption dataset (sample_first_complete_week.csv).
Development-only feasibility run (Arm T / SpecOrganon).
Uses only the Python standard library.
"""

import csv
import datetime
import math
import os
import sys

def parse_iso_datetime(dt_str):
    return datetime.datetime.strptime(dt_str.strip(), "%Y-%m-%d %H:%M:%S")

def run_analysis(csv_path="sample_first_complete_week.csv"):
    if not os.path.exists(csv_path):
        print(f"Error: CSV file '{csv_path}' not found.", file=sys.stderr)
        sys.exit(1)

    records = []
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    total_records = len(records)
    print(f"=== REVISIÓN DE INTERVALOS Y CONTINUIDAD ===")
    print(f"Total de registros leídos: {total_records} (esperados: 1008)")

    # Check temporal continuity (every 10 minutes)
    timestamps = [parse_iso_datetime(r["date"]) for r in records]
    continuity_ok = True
    gap_count = 0
    expected_delta = datetime.timedelta(minutes=10)

    for i in range(1, len(timestamps)):
        delta = timestamps[i] - timestamps[i - 1]
        if delta != expected_delta:
            continuity_ok = False
            gap_count += 1
            print(f"Discontinuidad detectada entre {timestamps[i-1]} y {timestamps[i]}: delta={delta}")

    if continuity_ok and total_records == 1008:
        print(f"Continuidad temporal: PERFECTA (1008 intervalos consecutivos de 10 minutos)")
        print(f"Rango temporal: desde {timestamps[0]} hasta {timestamps[-1]} inclusive (7 días completos)")
    else:
        print(f"Continuidad temporal: FALLIDA ({gap_count} discontinuidades encontradas)")

    # Daily aggregation of Appliances (Wh -> kWh) and lights (Wh -> kWh)
    # Appliances is energy per 10-min interval in Wh. Total energy = sum(Wh) / 1000 kWh.
    daily_appliances_wh = {}
    daily_lights_wh = {}
    daily_t_out = {}
    daily_t_in = {}  # T1 (kitchen/living area)

    total_appliances_wh = 0.0
    total_lights_wh = 0.0

    # Hourly distribution to analyze load patterns
    hourly_appliances_wh = {h: 0.0 for h in range(24)}
    hourly_counts = {h: 0 for h in range(24)}

    for r in records:
        dt = parse_iso_datetime(r["date"])
        day_str = dt.strftime("%Y-%m-%d")
        day_name = dt.strftime("%A")
        
        app_wh = float(r["Appliances"].strip())
        lights_wh = float(r["lights"].strip())
        t_out = float(r["T_out"].strip())
        t1_in = float(r["T1"].strip())

        total_appliances_wh += app_wh
        total_lights_wh += lights_wh

        hourly_appliances_wh[dt.hour] += app_wh
        hourly_counts[dt.hour] += 1

        if day_str not in daily_appliances_wh:
            daily_appliances_wh[day_str] = 0.0
            daily_lights_wh[day_str] = 0.0
            daily_t_out[day_str] = []
            daily_t_in[day_str] = []

        daily_appliances_wh[day_str] += app_wh
        daily_lights_wh[day_str] += lights_wh
        daily_t_out[day_str].append(t_out)
        daily_t_in[day_str].append(t1_in)

    total_appliances_kwh = total_appliances_wh / 1000.0
    total_lights_kwh = total_lights_wh / 1000.0

    print(f"\n=== RESULTADOS DE CONSUMO ENERGÉTICO ===")
    print(f"Total semanal de Appliances: {total_appliances_kwh:.3f} kWh ({total_appliances_wh:.1f} Wh)")
    print(f"Total semanal de Lights:     {total_lights_kwh:.3f} kWh ({total_lights_wh:.1f} Wh)")
    print(f"Total combinado medido:      {(total_appliances_kwh + total_lights_kwh):.3f} kWh")

    print(f"\n=== DESGLOSE DIARIO ===")
    print(f"{'Fecha':<12} {'Día':<12} {'Appliances (kWh)':<18} {'Lights (kWh)':<14} {'T_out media (°C)':<18} {'T1 media (°C)':<15}")
    print("-" * 89)
    for day_str in sorted(daily_appliances_wh.keys()):
        dt = datetime.datetime.strptime(day_str, "%Y-%m-%d")
        d_name = dt.strftime("%A")
        app_kwh = daily_appliances_wh[day_str] / 1000.0
        lig_kwh = daily_lights_wh[day_str] / 1000.0
        avg_tout = sum(daily_t_out[day_str]) / len(daily_t_out[day_str])
        avg_tin = sum(daily_t_in[day_str]) / len(daily_t_in[day_str])
        print(f"{day_str:<12} {d_name:<12} {app_kwh:<18.3f} {lig_kwh:<14.3f} {avg_tout:<18.2f} {avg_tin:<15.2f}")

    # Additional pertinent observation: Basal vs Peak power & Hourly concentration
    # Basal load estimation: minimum observed consumption per interval
    app_values = [float(r["Appliances"].strip()) for r in records]
    min_app = min(app_values)
    max_app = max(app_values)
    median_app = sorted(app_values)[len(app_values) // 2]
    mean_app = total_appliances_wh / total_records

    # Basal load (standby / background load)
    # If 10-min consumption is min_app Wh, average equivalent power = min_app * 6 W.
    basal_intervals = sum(1 for v in app_values if v <= min_app * 1.5)
    basal_kwh = sum(v for v in app_values if v <= min_app * 1.5) / 1000.0

    print(f"\n=== OBSERVACIONES ADICIONALES PERTINENTES ===")
    print(f"Rango de consumo por intervalo de 10 min: mín = {min_app:.1f} Wh ({min_app*6:.1f} W equiv.), máx = {max_app:.1f} Wh ({max_app*6:.1f} W equiv.)")
    print(f"Media por intervalo: {mean_app:.2f} Wh | Mediana: {median_app:.1f} Wh")
    print(f"Carga base/espera estimada (≤ {min_app*1.5:.1f} Wh): {basal_intervals}/{total_records} intervalos ({basal_intervals/total_records*100:.1f}%), aportando {basal_kwh:.3f} kWh ({basal_kwh/total_appliances_kwh*100:.1f}% del total).")

    # Peak hour analysis
    print(f"\nPerfil horario promedio de Appliances (Wh por intervalo de 10 min):")
    sorted_hours = sorted(hourly_appliances_wh.keys(), key=lambda h: hourly_appliances_wh[h], reverse=True)
    top_3_hours = sorted_hours[:3]
    for h in range(24):
        avg_h_wh = hourly_appliances_wh[h] / hourly_counts[h]
        marker = " <-- PICO" if h in top_3_hours else ""
        print(f"  Hora {h:02d}:00-{h:02d}:59: media = {avg_h_wh:6.2f} Wh/intervalo ({avg_h_wh*6:6.1f} W equiv. medio){marker}")

    # Note on non-causal variables
    print(f"\nNota metodológica: Las columnas 'rv1' y 'rv2' no se han utilizado en el análisis por ser variables aleatorias de diagnóstico sin relevancia causal o física.")

if __name__ == "__main__":
    run_analysis()
