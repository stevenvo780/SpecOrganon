#!/usr/bin/env python3
"""
Analysis script for the Appliances Energy Prediction observational pilot sample.
Standard library only.
"""

import csv
from datetime import datetime, timedelta

CSV_PATH = "sample_first_complete_week.csv"

def parse_iso_datetime(dt_str):
    return datetime.strptime(dt_str.strip(), "%Y-%m-%d %H:%M:%S")

def main():
    rows = []
    with open(CSV_PATH, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    
    total_rows = len(rows)
    print(f"--- 1. VERIFICACIÓN DE INTERVALOS Y CONTINUIDAD ---")
    print(f"Total de registros leídos: {total_rows}")
    expected_rows = 1008
    if total_rows != expected_rows:
        print(f"[ERROR] Se esperaban {expected_rows} filas, pero hay {total_rows}.")
    else:
        print(f"[OK] El recuento de intervalos coincide exactamente con los 7 días completos (1008 intervalos de 10 min).")
    
    # Check timestamp continuity
    start_dt = parse_iso_datetime(rows[0]["date"])
    end_dt = parse_iso_datetime(rows[-1]["date"])
    print(f"Primer intervalo: {start_dt}")
    print(f"Último intervalo: {end_dt}")
    
    step = timedelta(minutes=10)
    gaps = []
    for i in range(1, total_rows):
        prev_dt = parse_iso_datetime(rows[i-1]["date"])
        curr_dt = parse_iso_datetime(rows[i]["date"])
        diff = curr_dt - prev_dt
        if diff != step:
            gaps.append((i, prev_dt, curr_dt, diff))
            
    if not gaps:
        print(f"[OK] Continuidad temporal perfecta: delta de exactamente 10 minutos en todos los registros.")
    else:
        print(f"[ALERTA] Se encontraron {len(gaps)} discontinuidades temporales: {gaps}")
        
    print(f"\n--- 2. CÁLCULO DE CONSUMO DE ELECTRODOMÉSTICOS (APPLIANCES) ---")
    # Wh per 10 min interval. Sum of Wh gives total Wh for the period.
    # Total kWh = Sum(Wh) / 1000
    daily_wh = {}
    daily_lights_wh = {}
    appliance_values = []
    
    for r in rows:
        dt = parse_iso_datetime(r["date"])
        day_str = dt.strftime("%Y-%m-%d (%A)")
        app_wh = float(r["Appliances"])
        light_wh = float(r["lights"])
        
        appliance_values.append(app_wh)
        
        daily_wh[day_str] = daily_wh.get(day_str, 0.0) + app_wh
        daily_lights_wh[day_str] = daily_lights_wh.get(day_str, 0.0) + light_wh
        
    total_app_wh = sum(appliance_values)
    total_app_kwh = total_app_wh / 1000.0
    total_lights_wh = sum(daily_lights_wh.values())
    total_lights_kwh = total_lights_wh / 1000.0
    
    print(f"Total semanal Appliances: {total_app_wh:.1f} Wh ({total_app_kwh:.3f} kWh)")
    print(f"Total semanal Lights:     {total_lights_wh:.1f} Wh ({total_lights_kwh:.3f} kWh)")
    print(f"Total semanal Combinado:  {(total_app_wh + total_lights_wh):.1f} Wh ({(total_app_kwh + total_lights_kwh):.3f} kWh)")
    
    print("\nDesglose diario de Appliances:")
    for day, wh in daily_wh.items():
        kwh = wh / 1000.0
        l_kwh = daily_lights_wh[day] / 1000.0
        pct = (wh / total_app_wh) * 100.0
        print(f"  - {day}: {wh:8.1f} Wh | {kwh:6.3f} kWh ({pct:5.1f}% del total semanal) | Lights: {l_kwh:.3f} kWh")
        
    print(f"\n--- 3. OBSERVACIONES ADICIONALES PERTINENTES ---")
    # Baseline standby vs active peak analysis
    sorted_apps = sorted(appliance_values)
    min_val = min(appliance_values)
    max_val = max(appliance_values)
    mean_val = total_app_wh / total_rows
    
    # Median, quartiles
    q25 = sorted_apps[int(total_rows * 0.25)]
    q50 = sorted_apps[int(total_rows * 0.50)]
    q75 = sorted_apps[int(total_rows * 0.75)]
    q90 = sorted_apps[int(total_rows * 0.90)]
    
    print(f"Distribución del consumo de Appliances (Wh por intervalo de 10 min):")
    print(f"  - Mínimo: {min_val:.1f} Wh (potencia continua equivalente: {min_val * 6:.1f} W)")
    print(f"  - Percentil 25 (Q1): {q25:.1f} Wh ({q25 * 6:.1f} W)")
    print(f"  - Mediana (Q2): {q50:.1f} Wh ({q50 * 6:.1f} W)")
    print(f"  - Media: {mean_val:.1f} Wh ({mean_val * 6:.1f} W)")
    print(f"  - Percentil 75 (Q3): {q75:.1f} Wh ({q75 * 6:.1f} W)")
    print(f"  - Percentil 90: {q90:.1f} Wh ({q90 * 6:.1f} W)")
    print(f"  - Máximo: {max_val:.1f} Wh ({max_val * 6:.1f} W)")
    
    # Standby base estimation: intervals <= 50 Wh (<= 300 W)
    standby_threshold = 50.0 # Wh per 10 min
    standby_intervals = [x for x in appliance_values if x <= standby_threshold]
    active_intervals = [x for x in appliance_values if x > standby_threshold]
    
    standby_wh = sum(standby_intervals)
    active_wh = sum(active_intervals)
    
    print(f"\nEstructura de carga (descomposición base vs picos activos):")
    print(f"  - Intervalos base/standby (<= 50 Wh / <= 300 W): {len(standby_intervals)} / {total_rows} ({len(standby_intervals)/total_rows*100:.1f}% del tiempo)")
    print(f"    Consumo base acumulado: {standby_wh/1000.0:.3f} kWh ({standby_wh/total_app_wh*100:.1f}% del consumo total)")
    print(f"  - Intervalos con picos activos (> 50 Wh / > 300 W): {len(active_intervals)} / {total_rows} ({len(active_intervals)/total_rows*100:.1f}% del tiempo)")
    print(f"    Consumo en picos acumulado: {active_wh/1000.0:.3f} kWh ({active_wh/total_app_wh*100:.1f}% del consumo total)")
    
    # Night vs Day consumption (assuming 23:00 to 07:00 as night/rest)
    night_wh = 0.0
    day_wh = 0.0
    for r in rows:
        dt = parse_iso_datetime(r["date"])
        app = float(r["Appliances"])
        if dt.hour >= 23 or dt.hour < 7:
            night_wh += app
        else:
            day_wh += app
    
    print(f"\nConsumo por franja horaria:")
    print(f"  - Nocturno (23:00 - 07:00, 8h/día): {night_wh/1000.0:.3f} kWh ({night_wh/total_app_wh*100:.1f}%)")
    print(f"  - Diurno (07:00 - 23:00, 16h/día):   {day_wh/1000.0:.3f} kWh ({day_wh/total_app_wh*100:.1f}%)")

if __name__ == "__main__":
    main()
