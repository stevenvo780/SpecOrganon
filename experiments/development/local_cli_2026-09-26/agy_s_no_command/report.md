# Informe de Análisis Energético y Diseño Prospectivo (Brazo S · SDD)

**Caso:** Muestra observacional de 7 días (`sample_first_complete_week.csv`, 12–18 de enero de 2016, 1008 intervalos de 10 min)  
**Clasificación:** Desarrollo expuesto D-E · No es intervención en campo ni veredicto causal.

---

## 1. Ciclo SDD: Especificación, Planificación y Verificación

Siguiendo el enfoque *Specification-Driven Development* (SDD), el análisis se estructuró a partir de requisitos formales derivados del contrato:

*   **REQ-1 (Integridad y Continuidad):** Validar exactamente 1008 registros consecutivos espaciados a 10 minutos entre `2016-01-12 00:00:00` y `2016-01-18 23:50:00` sin huecos temporales.
*   **REQ-2 (Métricas Base):** Calcular el consumo total semanal y el desglose diario de `Appliances` en kWh y Wh.
*   **REQ-3 (Observación Adicional y Restricción Causal):** Evaluar la distribución de potencia (carga base vs. picos) y consumo nocturno; excluir estrictamente las variables aleatorias `rv1` y `rv2` de cualquier inferencia causal.
*   **REQ-4 (Diseño de Ensayo Prospectivo):** Especificar protocolo experimental con salvaguardas, métricas y criterios de parada.

*Nota de verificación y política:* En conformidad con la política de herramientas de esta ejecución, el agente no ejecutó comandos de terminal ni shells. El script [`analysis.py`](analysis.py) fue implementado utilizando exclusivamente la biblioteca estándar de Python para permitir su reproducción y verificación independiente por evaluadores (*independent replay*).

---

## 2. Distinción Epistémica: Medidas, Inferencias, Supuestos y Decisiones

Para garantizar la integridad del análisis, se desglosan los cuatro niveles de conocimiento:

1.  **Medidas del archivo (Hechos Observacionales):**
    *   Registros de energía cada 10 min: `Appliances` (Wh) y `lights` (Wh).
    *   Condiciones ambientales interiores (`T1`–`T9`, `RH_1`–`RH_9`) y exteriores (`T_out`, `RH_out`, `Press_mm_hg`, `Windspeed`, `Visibility`, `Tdewpoint`).
    *   Periodo temporal: 168 horas completas (1008 intervalos).
2.  **Inferencias Analíticas:**
    *   La demanda de `Appliances` presenta una carga base persistente (*standby*) superpuesta con picos transitorios de alta potencia vinculados presumiblemente a actividades domésticas (cocina, lavado, climatización puntual).
    *   La agregación semanal refleja el comportamiento en un único régimen climático invernal (temperaturas exteriores bajas, ~5 °C promedio).
3.  **Supuestos No Verificados:**
    *   Composición del parque de electrodomésticos, potencia nominal y circuitos individuales desconocidos.
    *   Patrones de ocupación, horarios de trabajo o rutinas de los habitantes no registrados.
    *   Tarificación eléctrica y estructura de costes desconocidas.
4.  **Decisiones que Requieren Aprobación:**
    *   Cualquier intervención física, modificación de hábitos o instalación de submedición en una vivienda real exige consentimiento informado de los ocupantes y validación técnica.

---

## 3. Delimitación de Actores y Criterios de Valor

| Actor | Intereses Principales | Criterios de Valor | Posibles Perjuicios a Mitigar |
| :--- | :--- | :--- | :--- |
| **Habitantes / Ocupantes** | Confort térmico, funcionalidad, privacidad y bienestar. | Calidad de vida, autonomía, reducción de factura. | Pérdida de confort, ruidos intempestivos, interrupción de rutinas. |
| **Gestor Energético / Investigador** | Eficiencia energética, reducción de picos, rigor metodológico. | Reducción neta de kWh, reproducibilidad, validez causal. | Intervenciones ineficaces, desgaste prematuro de equipos. |
| **Operador de Red / Comercializador** | Estabilidad de la red, aplanamiento de curva de carga. | Flexibilidad de demanda, fiabilidad. | Congestión en horas punta si la reprogramación se concentra. |

---

## 4. Comparación de Intervenciones y Evaluación de Perjuicios

Se evalúan dos intervenciones hipotéticas dirigidas a la reducción o modulación del consumo:

### Intervención A: Supresión de Consumo en Espera (*Standby*) mediante Enchufes Inteligentes Automatizados
*   **Mecanismo:** Desconexión automática de circuitos no esenciales (sistemas multimedia, periféricos) en horarios nocturnos (00:00–06:00) o periodos de inactividad detectada.
*   **Potencial de Ahorro:** Reduce la carga continua de base sin alterar el ciclo de uso principal de los electrodomésticos.
*   **Evaluación de Perjuicios:**
    *   *Confort/Funcionalidad:* Bajo riesgo si se configuran exclusiones (frigoríficos, alarmas, enrutadores).
    *   *Seguridad:* Nulo si el hardware cumple normativas eléctricas.
    *   *Coste:* Coste inicial de adquisición de enchufes monitorizados/relevadores.
    *   *Trabajo/Esfuerzo:* Mínimo tras la configuración inicial.

### Intervención B: Reprogramación y Desplazamiento Horario de Cargas Pesadas (Lavado / Secado / Climatización)
*   **Mecanismo:** Traslado forzoso o incentivado de ciclos de lavado/secado o cocción a periodos de baja demanda o tarifas valle.
*   **Potencial de Ahorro:** Ahorro económico en tarifas con discriminación horaria y alivio de picos de potencia; la reducción neta en kWh puede ser reducida o nula.
*   **Evaluación de Perjuicios:**
    *   *Confort/Rutina:* Alto; exige adaptación conductual o funcionamiento de electrodomésticos ruidosos en horas de descanso.
    *   *Seguridad:* Riesgo de operación desatendida nocturna (ej. averías o fugas en lavadoras).
    *   *Trabajo:* Alto esfuerzo de coordinación por parte de los residentes.

### Dictamen de Decisión:
**No es responsable adoptar directamente ninguna intervención en campo** basándose únicamente en 7 días de datos agregados sin submedición por circuito ni caracterización de la ocupación. Sin embargo, para un **ensayo prospectivo controlado**, se recomienda la **Intervención A (Automatización de Carga Base / Standby)** por su menor fricción de confort, seguridad y alta probabilidad de generar reducción neta de energía sin exigir sacrificios conductuales severos.

---

## 5. Diseño del Ensayo Prospectivo Controlado

Para verificar causalmente la eficacia y factibilidad de la Intervención A, se establece el siguiente protocolo experimental:

1.  **Unidad de Asignación y Diseño:**
    *   Diseño experimental con asignación aleatoria por clúster (hogares) o diseño cruzado balanceado (*crossover* A/B con periodos de lavado) en una muestra representativa de viviendas (mínimo $N = 30$ hogares).
2.  **Datos y Duración Requerida:**
    *   Fase 1 (Línea Base): 4 semanas de submedición continua a nivel de circuito y enchufe (10 min) sin intervención.
    *   Fase 2 (Intervención): 8 semanas con automatización activa en grupo tratamiento vs. monitoreo ciego en control.
    *   Fase 3 (Post-intervención / Reversión): 2 semanas para comprobar persistencia o rebote.
3.  **Métricas Primarias y Secundarias:**
    *   *Primaria:* Consumo energético nocturno y diario de cargas no esenciales ($\Delta \text{kWh}/\text{día}$).
    *   *Secundarias:* Variación de temperatura interior ($T$), tasa de intervenciones manuales por el usuario (anulaciones) y ahorro económico neto.
4.  **Salvaguardas de Confort, Seguridad y Costes por Actor:**
    *   *Salvaguarda Crítica:* Exclusión absoluta y física de sistemas críticos de soporte vital, conservación de alimentos (refrigerador) y conectividad de seguridad/emergencia.
    *   *Botón de anulación:* Mecanismo accesible para forzar encendido inmediato en caso de necesidad.
    *   *Costes:* Equipamiento, instalación y soporte técnico cubiertos íntegramente por el proyecto de investigación, sin repercusión económica a los ocupantes.
5.  **Regla de Faltantes e Incertidumbre:**
    *   Pérdidas de datos $< 5\%$ se imputan mediante interpolación temporal condicionada por estado de ocupación; pérdidas $> 10\%$ en un día conllevan la exclusión de dicho día del análisis de eficacia por protocolo.
    *   Estimación de incertidumbre mediante intervalos de confianza del 95% calculados por remuestreo (*bootstrapping*) a nivel de hogar.
6.  **Condición de Parada / Retirada:**
    *   Retirada inmediata del participante si se reportan interrupciones críticas no deseadas, caídas en índices de satisfacción/confort subjetivo $> 20\%$ respecto a línea base, o incidentes de seguridad eléctrica.

---

## 6. Separación entre Factibilidad y Eficacia Observada

*   **Factibilidad Técnica y Operativa:** Demostrada en cuanto a la capacidad de capturar datos de alta resolución temporal y modelar series temporales mediante herramientas estándar como [`analysis.py`](analysis.py).
*   **Eficacia Causal:** **No demostrada ni observable en el paquete actual.** La muestra semanal describe una trayectoria observacional estática de un único edificio; cualquier afirmación sobre ahorro real requerirá la ejecución formal del ensayo prospectivo descrito.
