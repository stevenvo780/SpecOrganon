# Informe de Evaluación Energética y Diseño de Medición Prospectiva

## 1. Distinción entre Medidas, Inferencias, Supuestos y Decisiones

### Medidas del archivo
Los datos provienen de `sample_first_complete_week.csv`, correspondiente al estudio *Appliances Energy Prediction* (Candanedo, UCI / CC BY 4.0). El registro comprende exactamente 1008 intervalos regulares de 10 minutos (7 días completos: del 12 al 18 de enero de 2016 inclusive). Se verifican mediciones de potencia integrada por intervalo en Wh para `Appliances` y `lights`, junto con 9 sensores interiores de temperatura (`T1`–`T9`) y humedad relativa (`RH_1`–`RH_9`), y variables meteorológicas exteriores. Las columnas `rv1` y `rv2` contienen variables aleatorias sintéticas sin contenido físico. Los totales calculados por `analysis.py` procesan estas mediciones agregadas directamente.

### Inferencias
Se infiere que la demanda eléctrica de `Appliances` presenta una componente basal permanente durante la noche (horas 00:00 a 05:50) atribuible a cargas continuas (ej. standby, frigorífico o ventilación mecánica) y picos diurnos intermitentes de alta potencia correspondientes a ciclos de operación activa de electrodomésticos pesados o cocción.

### Supuestos
1. Las marcas de tiempo reflejan la hora local de operación del hogar, aunque el archivo carece de especificación explícita de zona horaria.
2. Los sensores `T1`–`T9` representan estancias diferenciadas con dinámicas térmicas acopladas a la envolvente y al uso de calefacción/ventilación.
3. Las mediciones de `Appliances` agregan todas las cargas distintas a los circuitos de iluminación (`lights`).

### Decisiones que requieren aprobación
Cualquier modificación en los circuitos eléctricos de la vivienda, instalación de actuadores, alteración de consignas térmicas o compromiso vinculante con los residentes requiere consentimiento informado y autorización formal. Al ser un conjunto de desarrollo estrictamente observacional, no se autoriza ninguna intervención real.

---

## 2. Actores y Criterios de Valor

| Actor | Criterios de Valor Primarios | Riesgos y Restricciones |
| :--- | :--- | :--- |
| **Habitantes / Ocupantes** | Confort térmico, preservación de rutinas, autonomía y privacidad. | Disconfort por desconexiones involuntarias; intrusión en hábitos cotidianos. |
| **Investigador / Gestor Energético** | Reducción de consumo (kWh), reproducibilidad y rigor causal. | Sesgo de confusión si no se controla ocupación o clima; inferencias espurias. |
| **Propietario / Financiador** | Coste de capital (CAPEX), retorno de inversión y seguridad de instalaciones. | Sobrecoste de sensores o fallos en equipos por ciclos de conmutación agresivos. |

---

## 3. Comparación de Intervenciones y Dictamen Responsable

### Intervención A: Supresión de Cargas Standby / Basales
- **Mecanismo:** Desconexión automática de cargas no críticas en reposo (electrónica de consumo, periféricos, transformadores) mediante enchufes inteligentes durante horario nocturno y ausencias.
- **Perjuicios potenciales:** Interrupción de servicios de red doméstica, pérdida de programaciones, fatiga de componentes electrónicos por ciclos frecuentes de encendido/apagado.

### Intervención B: Desplazamiento y Modulación de Picos de Potencia (*Load Shifting*)
- **Mecanismo:** Gestión de demanda en grandes electrodomésticos (lavadora, lavavajillas) para evitar picos simultáneos y aprovechar periodos de menor tarifa o menor tensión térmica.
- **Perjuicios potenciales:** Fricción con los horarios de los usuarios, necesidad de reprogramación manual o equipos conectados, potencial afectación de la higiene o descanso si operan de noche con ruido.

### Dictamen de Selección
**No es responsable elegir ni implementar una intervención definitiva en este momento.** La métrica `Appliances` está completamente agregada; el conjunto observacional abarca solo 7 días de una única vivienda de bajo consumo en invierno sin submedición por aparato, sin registro de ocupación ni datos de encuestas de uso. Proceder a una intervención sin desagregación previa conllevaría un alto riesgo de ineficacia o perjuicio innecesario al confort.

---

## 4. Diseño del Ensayo Prospectivo para Resolver la Incertidumbre

Para fundamentar responsablemente una intervención futura, se diseña un protocolo de medición y ensayo prospectivo:

### Unidad de Asignación y Diseño Experimental
- **Unidad:** Circuito / sub-aparato dentro de la vivienda (diseño intra-sujeto de series temporales interrumpidas con fases A-B-A-B) o aleatorización por conglomerados (hogares) en una cohorte representativa.
- **Duración mínima:** 8 semanas (4 semanas de línea base observacional continua + 4 semanas de fase experimental activa).

### Datos y Requisitos de Medición
1. **Submedición individualizada:** Monitorización de potencia activa y reactiva por enchufe/circuito (frecuencia $\le 1$ min) para frigorífico, lavavajillas, lavadora, cocina y tomas auxiliares.
2. **Monitoreo ambiental y confort:** Mantenimiento de registros de $T$ y $RH$ en cada estancia, registrando eventos de desviación de la banda de confort térmico (ISO 7730 / ASHRAE 55).
3. **Registro de ocupación:** Detección pasiva no invasiva (sensores PIR o balance de $CO_2$) sin cámaras.

### Métrica Primaria y Secundarias
- **Métrica primaria:** Consumo diario neto de electrodomésticos ($\text{kWh/día}$), ajustado por Grados-Día de Calefacción (HDD) y presencia de ocupantes.
- **Métricas secundarias:** Potencia de pico horario (kW), índice de disconfort reportado (escala 1–5), y tasa de desconexiones no deseadas.

### Salvaguardas y Asignación de Costes
- **Seguridad y confort:** Exclusión absoluta de automatismos sobre sistemas de refrigeración de alimentos, equipos médicos o de telecomunicaciones críticas. Consigna interior mínima garantizada $\ge 19^\circ\text{C}$.
- **Costes:** Los costes de hardware, instalación, conectividad y mantenimiento serán asumidos íntegramente por el proyecto experimental; no se transferirán costes de inversión a los residentes.

### Regla de Tratamiento de Datos Faltantes
- Intervalos perdidos aislados ($\le 30$ min) se imputarán mediante interpolación lineal o splines estacionales.
- Días con más del 5% de datos no recuperables se excluirán del cálculo primario diario, realizándose análisis de sensibilidad por intención de tratar (*Intention-to-Treat*).

### Incertidumbre y Criterio de Retiro / Cancelación
Se retirará la intervención y se restablecerá el estado basal si se cumple alguna de las siguientes condiciones:
1. Incremento de reportes de disconfort o quejas de residentes superior al 10% de los intervalos de uso activo.
2. Incidencias técnicas reiteradas (fallo de rearme de enchufes, disparo de protecciones térmicas).
3. Ahorro energético medio observado inferior al error de medición instrumental ($\pm 3\%$) o insuficiente para amortizar el consumo parásito del propio hardware de control en 12 meses.

---

## 5. Separación entre Factibilidad y Eficacia Observada

La **factibilidad técnica** de registrar variables a 10 minutos y computar balances energéticos globales queda demostrada mediante el script `analysis.py` sobre los datos disponibles. No obstante, la **eficacia de cualquier medida de ahorro energético permanece estrictamente no observada e indeterminada** hasta que se ejecute el ensayo prospectivo controlado aquí especificado.
