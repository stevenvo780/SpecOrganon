# Informe de Factibilidad y Diseño de Ensayo Prospectivo (Brazo S · SDD)

## 1. Ciclo SDD: Requisitos, Verificación y Decisiones

Siguiendo el ciclo de Desarrollo Dirigido por Especificación (SDD), se fijaron cuatro requisitos verificables a partir de `task.md`:
1. **Verificación de integridad:** El archivo debe contener 1008 registros decaminutales continuos y sin huecos temporales entre el 12/01/2016 00:00 y el 18/01/2016 23:50.
2. **Cálculo de magnitudes energéticas:** Computar consumo semanal y diario de `Appliances` en kWh, explicitando unidades y excluyendo `rv1`/`rv2` de deducciones causales.
3. **Observación complementaria:** Caracterizar el régimen de carga base (standby) y la distribución diurna/nocturna de la demanda.
4. **Delimitación epistemológica:** Separar estrictamente medidas observadas, inferencias, supuestos y decisiones sujetas a autorización humana.

### Resultado de la Verificación Técnica (`analysis.py`)
- **Integridad:** 1008 filas procesadas; paso constante de 10 minutos (600 s); sin datos faltantes ni solapamientos.
- **Totales semanales:**
  - Electrodomésticos (`Appliances`): **118,280 kWh** (118.280 Wh).
  - Iluminación (`lights`): **5,320 kWh** (5.320 Wh).
- **Desglose diario de electrodomésticos (kWh):**
  - Martes 12/01: 12,340 kWh
  - Miércoles 13/01: 13,970 kWh
  - Jueves 14/01: 21,800 kWh
  - Viernes 15/01: 18,050 kWh
  - Sábado 16/01: 18,040 kWh
  - Domingo 17/01: 20,550 kWh
  - Lunes 18/01: 13,530 kWh
- **Distribución intradiaria:**
  - Noche (00:00–06:00): 12,470 kWh (10,5% del total semanal).
  - Día (06:00–18:00): 64,300 kWh (54,4%).
  - Tarde-noche (18:00–24:00): 41,510 kWh (35,1%).
- **Carga base y dispersión:** Mediana decaminutal de 60,0 Wh; percentil 10 (carga base residual) de 40,0 Wh; media de 117,3 Wh (desviación estándar: 137,8 Wh); máximo puntual de 1080,0 Wh.

---

## 2. Clasificación Epistemológica del Análisis

- **Medidas del archivo (hechos empíricos):** Series temporales de potencia activa agregada, iluminación y condiciones higrotérmicas interiores ($T_1 \dots T_9$, $RH_1 \dots RH_9$) y exteriores ($T_{out} = 2,31\ ^\circ\text{C}$ media, rango $[-4,90; 7,50]\ ^\circ\text{C}$).
- **Inferencias:** La demanda presenta picos marcados en horarios vespertinos y fines de semana (domingo 20,55 kWh vs. martes 12,34 kWh), coexistiendo con una carga base nocturna persistente ($\approx 40\text{ Wh/intervalo} = 240\text{ W}$ constantes).
- **Supuestos:** Suponer qué electrodoméstico concreto causa cada pico (p. ej., lavadora, horno, bomba de calor o termo) o presumir que la ocupación fue constante es un supuesto no verificado, ya que el conjunto UCI carece de submedición desagregada por circuito o registro de presencia.
- **Decisiones que requieren aprobación:** Cualquier intervención física, modificación de horarios de uso, reconfiguración de enchufes o alteración de consignas térmicas en una vivienda real exige consentimiento informado explícito de sus residentes.

---

## 3. Actores, Criterios de Valor y Comparación de Intervenciones

### Matriz de Criterios por Actor
1. **Habitantes:** Confort térmico/lumínico, ausencia de ruidos nocturnos, mínima carga de trabajo doméstico y preservación de rutinas.
2. **Gestor Energético / Analista:** Reducción verificable de kWh totales y minimización de picos en horas de alta demanda.
3. **Comercializadora / Red:** Estabilidad de carga y optimización económica bajo tarifas horarias.

### Comparación de Alternativas de Intervención

| Intervención | Mecanismo Propuesto | Beneficio Potencial Teórico | Riesgos y Perjuicios Asociados |
| :--- | :--- | :--- | :--- |
| **Opción A: Desconexión Inteligente de Cargas Standby / Carga Base** | Regletas inteligentes programables para cortar consumo residual nocturno (00:00–06:00) en equipos multimedia/oficina. | Ahorro estimado de hasta un 30–50% de la carga base nocturna ($\approx 3\text{--}6\text{ kWh/semana}$). | Apagado accidental de routers, reinicio forzado de equipos, degradación de conveniencia y fatiga por fallos en automatización. |
| **Opción B: Desplazamiento Horario de Grandes Electrodomésticos** | Trasladar ciclos pesados (lavado/secado/lavavajillas) desde la franja punta (18:00–22:00) a horas valle matinales o nocturnas. | Aplanamiento de la curva de demanda punta vespertina (que concentra 41,51 kWh/semana). | Molestias acústicas durante el descanso, ropa húmeda estancada (riesgo de moho/olor) y fricción organizativa para los habitantes. |

### Veredicto de Elección Responsable
**No es metodológicamente responsable imponer una intervención definitiva** a partir exclusivamente de esta muestra de 7 días. La ausencia de submedición desagregada impide conocer si el consumo nocturno responde a equipos prescindibles (standby) o esenciales (ventilación mecánica, refrigeración crítica). Seleccionar la Opción A o B a ciegas trasladaría riesgos inaceptables de confort y operatividad.

---

## 4. Especificación del Ensayo Prospectivo Controlado

Para resolver la incertidumbre sin comprometer a los usuarios, se define el siguiente protocolo experimental riguroso:

1. **Hipótesis y Recomendación Candidata:** Evaluar la *Opción A* (gestión automatizada de carga base no esencial en zonas de ocio/oficina) mediante enchufes inteligentes con monitorización individual.
2. **Unidad de Asignación y Diseño:** Diseño experimental intra-sujeto cruzado (*crossover trial*) balanceado (o aleatorización por conglomerados si participan múltiples viviendas).
   - *Fase 0 (Línea base observacional desagregada):* 3 semanas de medición continua a nivel de enchufe/circuito sin automatismos.
   - *Fase 1 (Intervención A vs. Control):* 4 semanas de desconexión automatizada de periféricos inactivos.
   - *Fase 2 (Lavado / Inversión cruzada):* 4 semanas alternando grupos.
3. **Métrica Primaria y Secundarias:**
   - *Primaria:* Reducción absoluta y porcentual de energía en kWh/día en los circuitos intervenidos.
   - *Secundarias:* Incidencia de cancelaciones manuales (*overrides*) y consumo agregado semanal del hogar.
4. **Salvaguardas y Reparto de Costes:**
   - *Confort y Seguridad:* Interruptor físico de bypass inmediato; exclusión estricta de sistemas médicos, seguridad, refrigeración de alimentos y conectividad esencial.
   - *Costes:* Coste de hardware y monitorización asumido íntegramente por el proyecto promotor (coste nulo para el habitante).
5. **Tratamiento de Incertidumbre y Regla de Faltantes:**
   - Intervalos de confianza del 95% calculados mediante modelos lineales mixtos con errores estándar robustos.
   - Regla de faltantes: Se tolera hasta un 3% de datos decaminutales perdidos aislados ($\le 30\text{ min}$), imputados por interpolación lineal local. Días con $>60\text{ min}$ consecutivos sin registro quedan excluidos del análisis por protocolo.
6. **Condición de Retirada Inmediata (Parada de Seguridad):**
   La intervención se cancelará y revertirá si:
   - Los habitantes registran $\ge 3$ incidentes de molestia/interrupción operativa en una semana.
   - La tasa de anulación manual supera el 15% de los eventos programados.
   - No se observa una reducción estadísticamente significativa ($\alpha = 0,05$, potencia $1-\beta = 0,80$) tras el periodo previsto.

---

## 5. Trazabilidad SDD y Conclusión

El análisis ejecutado en `analysis.py` valida la factibilidad matemática y la consistencia de la serie temporal (118,280 kWh electrodomésticos + 5,320 kWh iluminación). No obstante, la factibilidad técnica del cálculo no equivale a eficacia causal de una intervención en un entorno real. El diseño prospectivo propuesto establece las salvaguardas necesarias para transformar una observación correlacional en una decisión energética informada, segura y respetuosa con los habitantes.
