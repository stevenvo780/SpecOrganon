# Informe de Factibilidad y Protocolo Prospectivo (Brazo T · SpecOrganon)

## 1. Registro del Caso y Gobernanza (Fases 1 y 2: Problema, Actores y Juicios de Valor)

### 1.1 Definición del Problema y Delimitación
El objetivo planteado es evaluar qué intervención concreta merecería un ensayo prospectivo para reducir el consumo eléctrico de electrodomésticos en una vivienda unifamiliar sin transferir perjuicios a confort térmico, calidad del aire, seguridad, rutinas de trabajo ni costes operativos.

### 1.2 Actores y Criterios de Valor
* **Habitantes del hogar:** Priorizan confort ambiental ($19\text{--}23^\circ\text{C}$), operatividad de electrodomésticos para labores domésticas y preservación de su privacidad e intimidad.
* **Gestor energético / Investigador:** Busca reducir el consumo agregado ($\text{kWh}$) y mitigar picos de demanda.
* **Entidad reguladora / Comité ético:** Exige consentimiento informado, salvaguarda de seguridad eléctrica y gobernanza de datos.

### 1.3 Estado de Gobernanza y Bloqueo Normativo (`policy: signed`)
Bajo la política estricta `signed` de SpecOrganon y sin recurrir a simulaciones o firmas sintéticas (`fixtures`), se registra un **bloqueo normativo en compuerta de autorización**. Al tratarse de un conjunto de datos observacionales secundarios sin canal de aprobación explícito ni presencia de los habitantes reales, **no se autoriza ninguna intervención física o contractual en la vivienda**. El presente documento constituye exclusivamente un estudio de factibilidad analítica y diseño experimental prospectivo.

---

## 2. Base Empírica y Límites Observacionales (Fases 3, 4 y 5: Pregunta, Fuentes e Incertidumbre)

### 2.1 Mediciones Verificadas en el Archivo (`sample_first_complete_week.csv`)
* **Periodo:** 7 días completos ($1008$ intervalos de $10\text{ min}$, continuidad $100\%$ sin huecos), del 12/01/2016 00:00 al 18/01/2016 23:50.
* **Consumo total electrodomésticos (`Appliances`):** $118{,}280\text{ Wh} = 118{,}280\text{ kWh}$.
* **Consumo total iluminación (`lights`):** $5{,}320\text{ Wh} = 5{,}320\text{ kWh}$.
* **Totales diarios (`Appliances`):**
  * Mar 12/01: $12{,}340\text{ kWh}$ ($T_{\text{ext\_avg}} = 5{,}57^\circ\text{C}$, $T_{1\_\text{avg}} = 20{,}09^\circ\text{C}$)
  * Mié 13/01: $13{,}970\text{ kWh}$ ($T_{\text{ext\_avg}} = 4{,}86^\circ\text{C}$, $T_{1\_\text{avg}} = 19{,}20^\circ\text{C}$)
  * Jue 14/01: $21{,}800\text{ kWh}$ ($T_{\text{ext\_avg}} = 3{,}43^\circ\text{C}$, $T_{1\_\text{avg}} = 20{,}37^\circ\text{C}$)
  * Vie 15/01: $18{,}050\text{ kWh}$ ($T_{\text{ext\_avg}} = 2{,}67^\circ\text{C}$, $T_{1\_\text{avg}} = 22{,}28^\circ\text{C}$)
  * Sáb 16/01: $18{,}040\text{ kWh}$ ($T_{\text{ext\_avg}} = 2{,}19^\circ\text{C}$, $T_{1\_\text{avg}} = 22{,}12^\circ\text{C}$)
  * Dom 17/01: $20{,}550\text{ kWh}$ ($T_{\text{ext\_avg}} = 0{,}39^\circ\text{C}$, $T_{1\_\text{avg}} = 21{,}76^\circ\text{C}$)
  * Lun 18/01: $13{,}530\text{ kWh}$ ($T_{\text{ext\_avg}} = -2{,}94^\circ\text{C}$, $T_{1\_\text{avg}} = 20{,}09^\circ\text{C}$)
* **Distribución de demanda por intervalo:**
  * Mínimo: $20\text{ Wh}$ | Mediana: $60\text{ Wh}$ | Percentil 90: $350\text{ Wh}$ | Máximo: $1080\text{ Wh}$.
  * Consumo base/standby ($\le 60\text{ Wh}$): $57{,}5\%$ del tiempo.
  * Picos intensivos ($> 200\text{ Wh}$): $16{,}4\%$ del tiempo, concentrados entre las 17:00 y las 21:59 (promedios horarios de $185\text{--}244\text{ Wh/intervalo}$).

### 2.2 Límites de Inferencia Causal e Incertidumbres
1. **Agregación de señal:** `Appliances` suma múltiples cargas sin desagregación por circuito individual (p. ej., bomba de calor, lavadora, cocina, refrigeración).
2. **Ausencia de variables de ocupación:** No se dispone de marcas directas de presencia ni de horarios de uso activo.
3. **Variables espurias:** `rv1` y `rv2` son secuencias numéricas idénticas entre sí sin plausibilidad física causal.
4. **Distinción epistemológica:** La correlación observada entre descensos térmicos exteriores o picos horarios no demuestra causalidad ni predice el efecto de una modificación en el comportamiento o equipamiento.

---

## 3. Comparación de Alternativas (Fase 6)

| Alternativa | Mecanismo Propuesto | Ahorro Potencial Estimado | Riesgos y Perjuicios |
| :--- | :--- | :--- | :--- |
| **A: Automatización de desconexión standby** | Apagado automatizado de cargas pasivas en horario nocturno (00:00–06:00). | Bajo a moderado ($\approx 20\text{--}40\text{ Wh}$ por intervalo en base). | Riesgo de desconfiguración de equipos, interrupción de routers/sensores o desgaste de componentes. |
| **B: Desplazamiento y optimización de cargas térmicas/flexibles en horario punta** | Reprogramación y gestión de consignas de climatización/lavado fuera del pico vespertino (17:00–21:00). | Moderado a alto sobre potencia pico y costes con tarifa por periodos. | Riesgo de disconfort térmico transitorio o colisión con horarios laborales y de descanso. |

---

## 4. Decisión Provisional y Requisitos (Fase 7)

### 4.1 Posición Responsable
**No es metodológicamente responsable declarar una alternativa ganadora sobre la base de esta muestra de 7 días.** Se selecciona la **Alternativa B (Gestión de cargas flexibles y consignas con salvaguardas)** únicamente como *hipótesis prioritaria para diseño experimental prospectivo*.

---

## 5. Diseño del Protocolo Prospectivo de Validación (Fases 8 y 9)

Para resolver la incertidumbre sin inducir sesgos de selección ni trasladar perjuicios, se formula el siguiente protocolo de ensayo controlado:

1. **Unidad de Asignación:**
   * Bloque temporal en diseño cruzado aleatorizado (*crossover trial* AB/BA) en la vivienda, o asignación aleatoria por grupos (*cluster-RCT*) si se extiende a una cohorte representativa de $N \ge 30$ hogares unifamiliares homogéneos.
2. **Duración y Fases de Medición:**
   * 4 semanas de línea base observacional (submedición desagregada por circuito).
   * 8 semanas de ensayo prospectivo (4 semanas intervención / 4 semanas control balanceadas estacionalmente).
3. **Métrica Primaria:**
   * Consumo eléctrico diario en electrodomésticos y climatización ($\text{kWh/día}$) normalizado por grados-día de calefacción/refrigeración ($\text{HDD/CDD}$).
4. **Métricas Secundarias y Salvaguardas Obligatorias:**
   * **Confort térmico:** Temperatura interior mantenida estrictamente entre $19^\circ\text{C}$ y $23^\circ\text{C}$; humedad relativa entre $30\%$ y $65\%$.
   * **Seguridad y operatividad:** Disponibilidad ininterrumpida de equipos esenciales (refrigeración, conectividad y seguridad).
   * **Costes por actor:** Registro del coste de monitorización ($< 150\,\text{€}$ por vivienda) frente a la variación real en la factura de los habitantes.
5. **Regla de Tratamiento de Datos Faltantes:**
   * Intervalos perdidos $\le 30\text{ min}$: interpolación lineal conservadora.
   * Pérdidas $> 30\text{ min}$: imputación por modelo autoregresivo multivariante con exclusión de días incompletos ($> 10\%$ faltantes) bajo análisis por intención de tratar (*ITT*).
6. **Condiciones de Interrupción y Retirada:**
   * Disconfort persistente ($T < 18^\circ\text{C}$ durante $> 2$ horas consecutivas).
   * Incremento neto de costes o solicitud explícita de cualquier habitante.

---

## 6. Dictamen Final de Factibilidad
* **Factibilidad Analítica:** Totalmente confirmada (procesamiento estandarizado, trazabilidad de datos y consistencia física).
* **Eficacia Causal:** **No observada ni afirmable** a partir de datos observacionales retrospectivos.
* **Gobernanza:** Expediente retenido en fase de diseño a la espera de autorización formal firmada de las partes competentes.
