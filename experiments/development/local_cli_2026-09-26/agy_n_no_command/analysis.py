#!/usr/bin/env python3
"""
analysis.py - Analisis observacional de consumo electrico residencial (Brazo N - D-E)

Proposito:
  Lectura, verificacion de integridad temporal y computo de estadisticos de consumo
  energetico para el conjunto de datos semanal de 10 minutos (Appliances Energy Prediction).

Entrada:
  sample_first_complete_week.csv (1008 observaciones de 10 min entre 2016-01-12 00:00 y 2016-01-18 23:50)

Salidas / Computos:
  - Verificacion de continuidad temporal y completitud de intervalos (10 min).
  - Consumo total semanal de electrodomesticos (Appliances) en Wh y kWh.
  - Desglose de consumo diario de electrodomesticos en kWh y Wh.
  - Consumo diario y semanal de iluminacion (lights) en Wh y kWh.
  - Estimacion de carga basal / consumo en reposo (minimo y percentiles nocturnos).
  - Perfil horario promedio de consumo.

Restricciones metodologicas:
  - Solo biblioteca estandar de Python.
  - Las variables rv1 y rv2 se excluyen explicitamente de cualquier analisis o interpretacion.
  - No se infieren relaciones causales directas de sub-aparatos debido a la agregacion de la metrica Appliances.
"""

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Tuple


def parse_row(row: Dict[str, str]) -> Dict[str, Any]:
    """Parsea y limpia los tipos de datos de una fila del CSV."""
    parsed: Dict[str, Any] = {}
    parsed["date"] = datetime.strptime(row["date"].strip(), "%Y-%m-%d %H:%M:%S")
    parsed["Appliances"] = float(row["Appliances"].strip())
    parsed["lights"] = float(row["lights"].strip())
    
    # Temperaturas y humedades
    for k, v in row.items():
        if k in ("date", "Appliances", "lights"):
            continue
        if k in ("rv1", "rv2"):
            # Excluir de analisis causal / modelado
            continue
        try:
            parsed[k] = float(v.strip())
        except (ValueError, TypeError):
            parsed[k] = None
    return parsed


def verify_intervals(records: List[Dict[str, Any]], expected_step_minutes: int = 10) -> Tuple[bool, List[str]]:
    """Verifica el recuento y la continuidad temporal estricta de las observaciones."""
    issues: List[str] = []
    if not records:
        return False, ["El archivo no contiene registros."]
    
    expected_rows = 1008  # 7 dias * 24 horas * 6 intervalos/hora
    if len(records) != expected_rows:
        issues.append(f"Recuento de filas ({len(records)}) difiere del esperado ({expected_rows}).")
    
    step = timedelta(minutes=expected_step_minutes)
    for i in range(1, len(records)):
        prev_dt = records[i - 1]["date"]
        curr_dt = records[i]["date"]
        diff = curr_dt - prev_dt
        if diff != step:
            issues.append(f"Discontinuidad detectada entre {prev_dt} y {curr_dt} (delta = {diff}).")
            
    is_valid = len(issues) == 0
    return is_valid, issues


def calculate_metrics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calcula totales semanales, diarios y estadisticas adicionales pertinentes."""
    total_appliances_wh = sum(r["Appliances"] for r in records)
    total_appliances_kwh = total_appliances_wh / 1000.0
    
    total_lights_wh = sum(r["lights"] for r in records)
    total_lights_kwh = total_lights_wh / 1000.0
    
    # Agrupacion por dia
    daily_appliances_wh: Dict[str, float] = {}
    daily_lights_wh: Dict[str, float] = {}
    daily_counts: Dict[str, int] = {}
    
    # Agrupacion por hora (perfil horario de 0 a 23)
    hourly_appliances_wh: Dict[int, List[float]] = {h: [] for h in range(24)}
    
    # Carga nocturna (00:00 a 05:50) para aproximacion de carga basal / standby
    night_appliances_wh: List[float] = []
    
    for r in records:
        day_str = r["date"].strftime("%Y-%m-%d")
        app_val = r["Appliances"]
        light_val = r["lights"]
        hour = r["date"].hour
        
        daily_appliances_wh[day_str] = daily_appliances_wh.get(day_str, 0.0) + app_val
        daily_lights_wh[day_str] = daily_lights_wh.get(day_str, 0.0) + light_val
        daily_counts[day_str] = daily_counts.get(day_str, 0) + 1
        
        hourly_appliances_wh[hour].append(app_val)
        if 0 <= hour < 6:
            night_appliances_wh.append(app_val)
            
    # Estadisticos de distribucion de Appliances
    app_values = sorted([r["Appliances"] for r in records])
    n = len(app_values)
    median_val = (app_values[n // 2] if n % 2 != 0 else (app_values[n // 2 - 1] + app_values[n // 2]) / 2.0)
    min_val = min(app_values)
    max_val = max(app_values)
    mean_val = total_appliances_wh / n
    
    # Horas punta (media por hora del dia)
    hourly_means = {h: sum(vals) / len(vals) for h, vals in hourly_appliances_wh.items()}
    peak_hour = max(hourly_means, key=hourly_means.get)
    low_hour = min(hourly_means, key=hourly_means.get)
    
    # Resumen diario en kWh
    daily_summary = []
    for day in sorted(daily_appliances_wh.keys()):
        daily_summary.append({
            "date": day,
            "intervals": daily_counts[day],
            "appliances_wh": daily_appliances_wh[day],
            "appliances_kwh": daily_appliances_wh[day] / 1000.0,
            "lights_wh": daily_lights_wh[day],
            "lights_kwh": daily_lights_wh[day] / 1000.0,
        })
        
    return {
        "record_count": n,
        "total_appliances_wh": total_appliances_wh,
        "total_appliances_kwh": total_appliances_kwh,
        "total_lights_wh": total_lights_wh,
        "total_lights_kwh": total_lights_kwh,
        "appliances_min_wh": min_val,
        "appliances_max_wh": max_val,
        "appliances_mean_wh_per_interval": mean_val,
        "appliances_median_wh_per_interval": median_val,
        "night_mean_wh_per_interval": sum(night_appliances_wh) / len(night_appliances_wh) if night_appliances_wh else 0.0,
        "daily_summary": daily_summary,
        "peak_hour": peak_hour,
        "peak_hour_mean_wh": hourly_means[peak_hour],
        "low_hour": low_hour,
        "low_hour_mean_wh": hourly_means[low_hour],
    }


def run_analysis(csv_path: Path) -> None:
    """Ejecuta el flujo completo de analisis y presenta los resultados."""
    if not csv_path.exists():
        print(f"ERROR: Archivo no encontrado: {csv_path}", file=sys.stderr)
        sys.exit(1)
        
    records: List[Dict[str, Any]] = []
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(parse_row(row))
            
    is_valid, issues = verify_intervals(records)
    metrics = calculate_metrics(records)
    
    print("=" * 70)
    print("REPORTE DE ANALISIS ENERGETICO - DATOS OBSERVACIONALES")
    print("=" * 70)
    print(f"Archivo analizado: {csv_path.name}")
    print(f"Periodo cubierto: {records[0]['date']} a {records[-1]['date']}")
    print(f"Total de intervalos leidos: {len(records)}")
    print(f"Continuidad temporal estricta (10 min): {'VALIDA' if is_valid else 'FALLIDA'}")
    if not is_valid:
        print("Incidencias detectadas:")
        for iss in issues:
            print(f"  - {iss}")
    print("-" * 70)
    print("TOTALES SEMANALES:")
    print(f"  - Consumo Electrodomesticos (Appliances): {metrics['total_appliances_kwh']:.3f} kWh ({metrics['total_appliances_wh']:.1f} Wh)")
    print(f"  - Consumo Iluminacion (lights):            {metrics['total_lights_kwh']:.3f} kWh ({metrics['total_lights_wh']:.1f} Wh)")
    print(f"  - Consumo Total Medido (App + Lights):     {(metrics['total_appliances_kwh'] + metrics['total_lights_kwh']):.3f} kWh")
    print("-" * 70)
    print("DESGLOSE DIARIO (Appliances):")
    print("  Fecha       | Intervalos | Appliances (kWh) | Lights (kWh) | Total (kWh)")
    print("  " + "-" * 62)
    for d in metrics["daily_summary"]:
        tot_d = d["appliances_kwh"] + d["lights_kwh"]
        print(f"  {d['date']}  |    {d['intervals']:4d}    |     {d['appliances_kwh']:8.3f}     |   {d['lights_kwh']:8.3f}   |   {tot_d:8.3f}")
    print("-" * 70)
    print("OBSERVACIONES ADICIONALES PERTINENTES:")
    print(f"  - Rango de Appliances por intervalo de 10 min: Min={metrics['appliances_min_wh']:.1f} Wh, Max={metrics['appliances_max_wh']:.1f} Wh")
    print(f"  - Media por intervalo: {metrics['appliances_mean_wh_per_interval']:.2f} Wh | Mediana: {metrics['appliances_median_wh_per_interval']:.2f} Wh")
    print(f"  - Media nocturna (00:00 - 06:00, carga base/standby): {metrics['night_mean_wh_per_interval']:.2f} Wh/intervalo")
    print(f"  - Hora de maxima demanda promedio: {metrics['peak_hour']:02d}:00 ({metrics['peak_hour_mean_wh']:.2f} Wh/intervalo)")
    print(f"  - Hora de minima demanda promedio: {metrics['low_hour']:02d}:00 ({metrics['low_hour_mean_wh']:.2f} Wh/intervalo)")
    print("-" * 70)
    print("NOTA METODOLOGICA:")
    print("  Variables rv1 y rv2 fueron excluidas del analisis por constituir ruido aleatorio sin valor causal.")
    print("  La agregacion de 'Appliances' no desagrega cargas individuales ni identifica ocupacion.")
    print("=" * 70)


if __name__ == "__main__":
    default_csv = Path(__file__).parent / "sample_first_complete_week.csv"
    target_csv = Path(sys.argv[1]) if len(sys.argv) > 1 else default_csv
    run_analysis(target_csv)
