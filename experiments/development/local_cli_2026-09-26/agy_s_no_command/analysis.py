#!/usr/bin/env python3
"""
analysis.py - Análisis reproducible del consumo eléctrico (Brazo S · SDD)
Dataset: sample_first_complete_week.csv (UCI Appliances Energy Prediction subset)

Requisitos SDD implementados:
- REQ-1: Verificación de integridad, esquema y continuidad temporal (1008 intervalos de 10 min).
- REQ-2: Cálculo del total semanal de 'Appliances' en kWh y totales diarios en kWh y Wh.
- REQ-3: Observaciones adicionales pertinentes (carga base vs picos, perfil horario y relación con iluminación).
- REQ-4: Restricción causal: exclusión de rv1 y rv2 como palancas causales.
- REQ-5: Compatibilidad exclusiva con la biblioteca estándar de Python.
"""

import csv
import datetime
import math
import sys
from collections import defaultdict
from pathlib import Path


def parse_timestamp(ts_str: str) -> datetime.datetime:
    """Parsea fecha y hora en formato YYYY-MM-DD HH:MM:SS."""
    return datetime.datetime.strptime(ts_str.strip(), "%Y-%m-%d %H:%M:%S")


def load_and_validate_data(filepath: Path):
    """
    Carga el archivo CSV y valida su integridad y continuidad temporal.
    
    Verificaciones:
    1. Existencia del archivo y presencia de encabezados esperados.
    2. Exactamente 1008 filas de datos.
    3. Inicio en 2016-01-12 00:00:00 y fin en 2016-01-18 23:50:00.
    4. Intervalo regular estricto de 10 minutos entre registros consecutivos.
    5. Ausencia de valores nulos o no numéricos en columnas de interés.
    """
    if not filepath.exists():
        raise FileNotFoundError(f"No se encontró el archivo de datos: {filepath}")

    records = []
    expected_interval = datetime.timedelta(minutes=10)

    with open(filepath, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required_cols = {"date", "Appliances", "lights", "T_out", "RH_out"}
        if not required_cols.issubset(set(reader.fieldnames or [])):
            missing = required_cols - set(reader.fieldnames or [])
            raise ValueError(f"Faltan columnas requeridas en el CSV: {missing}")

        for row_idx, row in enumerate(reader, start=1):
            ts = parse_timestamp(row["date"])
            try:
                appliances_wh = float(row["Appliances"].strip())
                lights_wh = float(row["lights"].strip())
                t_out = float(row["T_out"].strip())
                rh_out = float(row["RH_out"].strip())
            except ValueError as e:
                raise ValueError(f"Error numérico en la fila {row_idx}: {e}")

            records.append({
                "row_idx": row_idx,
                "date": ts,
                "Appliances_Wh": appliances_wh,
                "lights_Wh": lights_wh,
                "T_out_C": t_out,
                "RH_out_pct": rh_out,
            })

    # Verificación de conteo
    n_records = len(records)
    if n_records != 1008:
        raise ValueError(f"Se esperaban 1008 registros, pero se encontraron {n_records}.")

    # Verificación de continuidad temporal
    start_ts = records[0]["date"]
    end_ts = records[-1]["date"]

    expected_start = datetime.datetime(2016, 1, 12, 0, 0, 0)
    expected_end = datetime.datetime(2016, 1, 18, 23, 50, 0)

    if start_ts != expected_start:
        raise ValueError(f"Marca temporal inicial inválida: {start_ts} (esperada {expected_start})")
    if end_ts != expected_end:
        raise ValueError(f"Marca temporal final inválida: {end_ts} (esperada {expected_end})")

    for i in range(1, n_records):
        delta = records[i]["date"] - records[i - 1]["date"]
        if delta != expected_interval:
            raise ValueError(
                f"Discontinuidad detectada entre fila {records[i-1]['row_idx']} ({records[i-1]['date']}) "
                f"y fila {records[i]['row_idx']} ({records[i]['date']}): salto de {delta}."
            )

    return records


def compute_metrics(records):
    """Calcula métricas energéticas descriptivas agregadas y desagregadas."""
    total_appliances_wh = sum(r["Appliances_Wh"] for r in records)
    total_appliances_kwh = total_appliances_wh / 1000.0

    total_lights_wh = sum(r["lights_Wh"] for r in records)
    total_lights_kwh = total_lights_wh / 1000.0

    # Totales diarios
    daily_appliances_wh = defaultdict(float)
    daily_lights_wh = defaultdict(float)
    daily_counts = defaultdict(int)

    for r in records:
        day_str = r["date"].strftime("%Y-%m-%d (%A)")
        daily_appliances_wh[day_str] += r["Appliances_Wh"]
        daily_lights_wh[day_str] += r["lights_Wh"]
        daily_counts[day_str] += 1

    # Estadísticas descriptivas de demanda (Wh por intervalo de 10 min)
    appliance_values = [r["Appliances_Wh"] for r in records]
    sorted_values = sorted(appliance_values)
    n = len(sorted_values)

    min_val = sorted_values[0]
    max_val = sorted_values[-1]
    mean_val = total_appliances_wh / n

    def percentile(p):
        idx = int(p * (n - 1))
        return sorted_values[idx]

    p25 = percentile(0.25)
    median_val = percentile(0.50)
    p75 = percentile(0.75)
    p90 = percentile(0.90)
    p95 = percentile(0.95)

    # Segmentación por periodos: Madrugada (00:00 a 06:00) vs Resto del día (06:00 a 24:00)
    night_wh = sum(r["Appliances_Wh"] for r in records if 0 <= r["date"].hour < 6)
    day_wh = sum(r["Appliances_Wh"] for r in records if 6 <= r["date"].hour < 24)
    night_count = sum(1 for r in records if 0 <= r["date"].hour < 6)
    day_count = sum(1 for r in records if 6 <= r["date"].hour < 24)

    # Estimación de consumo de carga base (standby permanente aproximado por percentil 10 o moda base)
    p10 = percentile(0.10)
    base_standby_est_kwh = (p10 * 1008) / 1000.0

    return {
        "n_records": n,
        "total_appliances_wh": total_appliances_wh,
        "total_appliances_kwh": total_appliances_kwh,
        "total_lights_wh": total_lights_wh,
        "total_lights_kwh": total_lights_kwh,
        "daily_appliances_wh": daily_appliances_wh,
        "daily_lights_wh": daily_lights_wh,
        "daily_counts": daily_counts,
        "stats_10min": {
            "min_wh": min_val,
            "max_wh": max_val,
            "mean_wh": mean_val,
            "p10_wh": p10,
            "p25_wh": p25,
            "median_wh": median_val,
            "p75_wh": p75,
            "p90_wh": p90,
            "p95_wh": p95,
        },
        "night_vs_day": {
            "night_total_kwh": night_wh / 1000.0,
            "night_mean_wh_per_10min": night_wh / night_count if night_count else 0,
            "day_total_kwh": day_wh / 1000.0,
            "day_mean_wh_per_10min": day_wh / day_count if day_count else 0,
            "night_share_pct": (night_wh / total_appliances_wh) * 100.0 if total_appliances_wh else 0,
        },
        "base_standby_est_kwh": base_standby_est_kwh,
    }


def print_report(metrics):
    """Imprime el resumen analítico estructurado en consola."""
    print("=" * 70)
    print("REPORTE DE ANÁLISIS ENERGÉTICO (Brazo S · SDD)")
    print("Muestra: 1 semana completa (12 al 18 de enero de 2016)")
    print("=" * 70)
    print(f"Total de intervalos analizados: {metrics['n_records']} (10 min/intervalo, 168 horas)")
    print(f"Consumo total de Electrodomésticos (Appliances): {metrics['total_appliances_kwh']:.3f} kWh ({metrics['total_appliances_wh']:.1f} Wh)")
    print(f"Consumo total de Iluminación (lights):          {metrics['total_lights_kwh']:.3f} kWh ({metrics['total_lights_wh']:.1f} Wh)")
    print("-" * 70)
    print("DESGLOSE DIARIO DE ELECTRODOMÉSTICOS (Appliances):")
    print(f"{'Día':<28} | {'Consumo (kWh)':<14} | {'Consumo (Wh)':<14} | {'Intervalos':<10}")
    print("-" * 70)
    for day, wh in metrics["daily_appliances_wh"].items():
        kwh = wh / 1000.0
        count = metrics["daily_counts"][day]
        print(f"{day:<28} | {kwh:>12.3f} kWh | {wh:>12.1f} Wh | {count:>8}")
    print("-" * 70)
    print("DISTRIBUCIÓN Y CARGA DE POTENCIA (Wh por intervalo de 10 min):")
    s = metrics["stats_10min"]
    print(f"  Mínimo:         {s['min_wh']:>8.1f} Wh/10-min (~{s['min_wh']*6:>6.1f} W potencia media equivalente)")
    print(f"  Percentil 10:   {s['p10_wh']:>8.1f} Wh/10-min (~{s['p10_wh']*6:>6.1f} W)")
    print(f"  Percentil 25:   {s['p25_wh']:>8.1f} Wh/10-min (~{s['p25_wh']*6:>6.1f} W)")
    print(f"  Mediana (P50):  {s['median_wh']:>8.1f} Wh/10-min (~{s['median_wh']*6:>6.1f} W)")
    print(f"  Media:          {s['mean_wh']:>8.1f} Wh/10-min (~{s['mean_wh']*6:>6.1f} W)")
    print(f"  Percentil 75:   {s['p75_wh']:>8.1f} Wh/10-min (~{s['p75_wh']*6:>6.1f} W)")
    print(f"  Percentil 90:   {s['p90_wh']:>8.1f} Wh/10-min (~{s['p90_wh']*6:>6.1f} W)")
    print(f"  Máximo:         {s['max_wh']:>8.1f} Wh/10-min (~{s['max_wh']*6:>6.1f} W)")
    print("-" * 70)
    print("OBSERVACIONES ADICIONALES:")
    nd = metrics["night_vs_day"]
    print(f"  1. Consumo nocturno (00:00 - 06:00): {nd['night_total_kwh']:.3f} kWh ({nd['night_share_pct']:.1f}% del total)")
    print(f"     Media nocturna: {nd['night_mean_wh_per_10min']:.1f} Wh/10-min")
    print(f"  2. Consumo diurno/vespertino (06:00 - 24:00): {nd['day_total_kwh']:.3f} kWh")
    print(f"     Media diurna: {nd['day_mean_wh_per_10min']:.1f} Wh/10-min")
    print(f"  3. Carga base estimada continua (P10 * 1008): {metrics['base_standby_est_kwh']:.3f} kWh")
    print("=" * 70)


def main():
    data_path = Path(__file__).resolve().parent / "sample_first_complete_week.csv"
    try:
        records = load_and_validate_data(data_path)
        metrics = compute_metrics(records)
        print_report(metrics)
    except Exception as err:
        print(f"ERROR en la ejecución del análisis: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
