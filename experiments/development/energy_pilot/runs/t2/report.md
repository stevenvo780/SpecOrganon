# Reporte de Factibilidad e Intervención Energética (Brazo T · SpecOrganon)

## 1. Identificación del Caso y Metodología
- **Caso SpecOrganon ID:** `9f9116c7-0457-410e-b5bd-7e05bacb7032`
- **Dominio / Política:** `building_energy` | Política de aprobación: `signed` (documental estricta).
- **Fuente:** `sample_first_complete_week.csv` (UCI Machine Learning Repository, Candanedo et al., CC BY 4.0).
- **Ventana temporal:** 2016-01-12 00:00:00 a 2016-01-18 23:50:00 (primeros 7 días completos, 1008 observaciones a 10 min).

---

## 2. Medidas del Archivo, Inferencias y Supuestos

### Medidas Directas Verificadas (`analysis.py`)
- **Continuidad temporal:** 1008 intervalos continuos de 10 minutos (100% de integridad, 0 discontinuidades).
- **Consumo eléctrico total (`Appliances`):** **118.280 kWh** (118.280 Wh).
- **Consumo total iluminación (`lights`):** **5.320 kWh** (4,3% del consumo medido).
- **Desglose diario (`Appliances`):**
  - 2016-01-12 (Mar): 12.340 kWh (mín 20 Wh, máx 500 Wh)
  - 2016-01-13 (Mié): 13.970 kWh (mín 20 Wh, máx 520 Wh)
  - 2016-01-14 (Jue): 21.800 kWh (mín 20 Wh, máx 910 Wh)
  - 2016-01-15 (Vie): 18.050 kWh (mín 30 Wh, máx 500 Wh)
  - 2016-01-16 (Sáb): 18.040 kWh (mín 20 Wh, máx 1080 Wh)
  - 2016-01-17 (Dom): 20.550 kWh (mín 30 Wh, máx 800 Wh)
  - 2016-01-18 (Lun): 13.530 kWh (mín 20 Wh, máx 740 Wh)
- **Carga base nocturna (01:00 a 05:50):** 10.040 kWh totales (media 47,8 Wh/intervalo de 10 min, equivalente a ~287 W continuos).
- **Carga diurna/activa (06:00 a 00:50):** 108.240 kWh totales (media 135,6 Wh/intervalo, equivalente a ~814 W continuos).
- **Extremos de intervalo:** Mínimo de 20 Wh (potencia base de 120 W); máximo de 1080 Wh (pico de 6,48 kW medios en 10 min).

### Inferencias
- La carga nocturna sostenida (~120–300 W continuos) representa consumos pasivos basales permanentes (*standby* de electrónica, equipos auxiliares, ventilación y refrigeración cíclica).
- Los picos superiores a 500 Wh/10-min corresponden a eventos discretos de alta potencia (cocina eléctrica, lavado/secado o calentadores).

### Supuestos no Verificados y Límites
- **Ausencia de sub-metering:** No existe desagregación por circuito ni por aparato individual.
- **Sin datos de ocupación ni costes:** No se dispone de tarifas horarias reales, composición del hogar ni presencia física de habitantes.
- **Variables `rv1`/`rv2`:** Son variables aleatorias de diagnóstico del dataset y se excluyen de cualquier análisis causal.

---

## 3. Delimitación de Actores y Criterios de Valor

| Actor | Interés Principal | Criterios de Valor y Restricciones |
| :--- | :--- | :--- |
| **Habitantes del Hogar** | Confort, habitabilidad, no interrupción de rutinas | No perder confort térmico (19–23 °C), sin riesgo para conservación de alimentos, sin sobrecarga de trabajo doméstico. |
| **Gestor / Investigador** | Eficiencia energética verificable y reproducible | Ahorro neto en kWh/semana, validez estadística, costo acotado de instrumentación (<150 €). |

---

## 4. Comparación de Intervenciones Candidatas

### Opción 1: Gestión Automatizada de Cargas Fantasma / Standby
- **Mecanismo:** Instalación de regletas inteligentes y temporizadores para desconectar automáticamente receptores no esenciales (entretenimiento, oficina, cargadores) durante horarios nocturnos (01:00–06:00) o inactividad.
- **Ahorro potencial estimado:** 5 a 8 kWh/semana (reduciendo 40–60% de la carga base nocturna y de espera).
- **Perjuicios y riesgos:** Riesgo de corte inadvertido en aparatos críticos (frigorífico, router, alarmas) si no se delimitan circuitos adecuadamente. Coste de hardware.

### Opción 2: Intervención Conductual y Reprogramación Horaria
- **Mecanismo:** Notificaciones y recomendaciones a ocupantes para agrupar ciclos de lavado/secado y cocinar en franjas eficientes.
- **Ahorro potencial estimado:** 3 a 7 kWh/semana (optimización de cargas pico).
- **Perjuicios y riesgos:** Fatiga de decisión, fricción intrafamiliar, intrusión en la privacidad y pérdida de adherencia a medio plazo.

---

## 5. Decisión Provisional y Criterio de Responsabilidad

**Dictamen:** *No es metodológicamente responsable implementar una intervención directa definitiva sin una fase previa de medición desagregada.* 

Sin embargo, como propuesta para un **ensayo prospectivo controlado**, se recomienda prioritariamente la **Opción 1 (Gestión selectiva de standby no crítico)** debido a su carácter pasivo (no exige esfuerzo conductual continuo), supeditada a las salvaguardas y al consentimiento formal del hogar.

---

## 6. Diseño del Ensayo Prospectivo

- **Unidad de asignación:** La vivienda individual en diseño longitudinal cruzado (*crossover* A/B-B/A) consigo misma para controlar estacionalidad.
- **Duración y fases:** 4 semanas totales:
  1. *Semanas 1 y 2 (Línea base):* Medición continua con sub-metering en 6 circuitos/enchufes principales sin intervención.
  2. *Semanas 3 y 4 (Intervención):* Activación de regletas inteligentes en circuitos de entretenimiento y periféricos de oficina.
- **Métrica primaria:** Consumo eléctrico semanal en kWh (`Appliances`), medido cada 10 min.
- **Salvaguardas de confort y seguridad:**
  - Monitoreo continuo de temperaturas interiores $T_1$ a $T_9$ (umbral admisible: 19 °C a 23 °C) y humedades $RH_1$ a $RH_9$ (40% a 65%).
  - Circuito de refrigeración y comunicaciones excluido formalmente de cualquier corte automático.
  - Pulsador físico de anulación manual (*override*) inmediato en cada enchufe inteligente.
- **Costes por actor:** ~120 € en hardware asumidos por el proyecto de investigación; 0 € de coste para los habitantes; tiempo de reporte < 5 min/semana.
- **Regla de datos faltantes:** Si se pierden >5% de intervalos de 10 min en un día, se descarta el día; si faltan <5%, se imputa por interpolación lineal en series meteorológicas, pero nunca en consumo de potencia activa.
- **Condición de retirada (*Stop rule*):** Retiro inmediato de la intervención si los ocupantes reportan más de 1 falso apagado molesto por semana o si la temperatura/humedad interior sale de los rangos de confort establecidos.

---

## 7. Trazabilidad en SpecOrganon (Brazo T)

### Comandos Ejecutados
1. `organon init case --title "Feasibility study of appliance energy intervention" --domain "building_energy" --actor "agent_t2" --approval-policy signed`
2. `organon put` para registrar los 31 artefactos en el ledger:
   - *Fase 1 (Frame):* `prob-01`, `actor-01`, `bound-01`
   - *Fase 2 (Critique):* `concept-01`, `assump-01`, `opt-frame-01`, `opt-frame-02`, `norm-01`
   - *Fase 3 (Study):* `quest-01`, `hypo-01`, `ind-01`, `proto-01`
   - *Fase 4 (Observe):* `evid-01`, `infer-01`
   - *Fase 5 (Explain):* `synth-01`, `uncert-01`
   - *Fase 6 (Compare):* `opt-01`, `opt-02`, `risk-01`, `comp-01`
   - *Fase 7 (Specify):* `crit-01`, `dec-01`, `req-01`
   - *Fase 8 (Build):* `impl-01`, `test-01`
   - *Fase 9 (Validate):* `base-01`, `res-01`, `assess-01`
3. `organon review-phase case frame --verdict accept ...` y `organon advance case frame` (Fase 1 completada y avanzada).
4. `organon gate case critique` y `organon next-task case`.

### Estado Real de la Compuerta Normativa
- **Fase de bloqueo:** `critique` (Fase 2).
- **Motivo de bloqueo:** `norm-01 requires a verified human approval`.
- **Estado de compuerta:** Bloqueada (`ready: false`, `accepted: false`).
- **Resolución ética y metodológica:** En estricto cumplimiento de la política `signed` y el contrato común, **no se sintetizó ninguna firma artificial ni clave falsa**. El bloqueo por falta de autorización de una persona competente queda debidamente registrado en el ledger inmutable (`case/ledger.jsonl`).
- **Conclusión:** Se verifica la **factibilidad técnica y analítica**, delimitando con precisión la imposibilidad de atribuir eficacia causal sin el ensayo prospectivo validado.
