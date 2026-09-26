# Informe de Evaluación y Factibilidad: Consumo Energético en Edificación

## 1. Resumen Ejecutivo y Hallazgos Observacionales

El presente informe analiza la serie temporal observacional de 7 días completos (12 al 18 de enero de 2016, 1008 intervalos de 10 minutos) procedente del repositorio UCI (*Appliances Energy Prediction*). 

### Medidas Directas del Archivo
- **Registros e integridad:** 1008 intervalos continuos sin saltos temporales (inicio: 2016-01-12 00:00:00; fin: 2016-01-18 23:50:00).
- **Consumo eléctrico semanal de electrodomésticos (`Appliances`):** 118,280 kWh (118.280 Wh acumulados).
- **Consumo semanal de iluminación (`lights`):** 5,320 kWh (5.320 Wh acumulados).
- **Consumo total combinado:** 123,600 kWh.
- **Rango de potencia instantánea equivalente (`Appliances`):** Mínimo de 20 Wh/intervalo (120 W continuos) hasta un pico máximo de 1080 Wh/intervalo (6.480 W).

### Inferencias Estadísticas Descriptivas
- **Estructura de carga:** La mediana es de 60 Wh/intervalo (360 W), con una media de 117,3 Wh (704 W), reflejando una asimetría positiva pronunciada.
- **Carga base vs. picos:** Los intervalos de baja demanda ($\le 50$ Wh, $\le 300$ W) representan el 47,7% del tiempo pero solo el 17,2% del consumo total (20,360 kWh). Los picos activos ($>50$ Wh) concentran el 82,8% de la energía consumida (97,920 kWh) en el 52,3% del tiempo.
- **Distribución temporal:** El 85,9% del consumo (101,650 kWh) ocurre en horario diurno (07:00–23:00) y el 14,1% (16,630 kWh) en horario nocturno (23:00–07:00).

---

## 2. Supuestos, Actores y Criterios de Decisión

### Supuestos no Verificados en los Datos
1. La variable `Appliances` agrega múltiples circuitos sin submedición desagregada de aparatos específicos (refrigeración, cocción, lavado, climatización auxiliar).
2. Se desconoce la ocupación real, calendarios laborales y hábitos de los residentes durante esa semana de invierno.
3. No se dispone de estructura tarifaria (precio fijo vs. discriminación horaria) ni de costos marginales.

### Actores y Criterios de Valor
- **Residentes/Hogar:** Priorizan el confort térmico ($19^\circ\text{C}-22^\circ\text{C}$), la disponibilidad de servicios esenciales (cocina, higiene, trabajo) y la mínima fricción operativa.
- **Gestor del Edificio / Propietario:** Busca reducir el gasto energético total, evitar degradación prematura de equipos y garantizar la seguridad eléctrica.
- **Operador de Red / Analista:** Valora la predictibilidad, el aplanamiento de picos de demanda y la validez metodológica de cualquier cambio.

### Decisiones que Requieren Aprobación Previa
Cualquier modificación en rutinas, control domótico o apagado programado exige el consentimiento informado explícito de los ocupantes y la supervisión del instalador técnico.

---

## 3. Comparación de Intervenciones Potenciales y Riesgos

| Dimensión | Intervención A: Gestión de Cargas Base / Standby | Intervención B: Desplazamiento y Modulación de Picos Activos |
| :--- | :--- | :--- |
| **Mecanismo** | Regletas inteligentes y corte automático de aparatos en espera nocturna y ausencias. | Reprogramación horaria (lavado/lavavajillas) y precalentamiento térmico coordinado. |
| **Potencial teórico** | Afecta al 17,2% del consumo (hasta ~20,4 kWh/semana). | Afecta al 82,8% del consumo (hasta ~97,9 kWh/semana). |
| **Perjuicios a Confort** | Riesgo nulo o muy bajo si no interfiere con equipos críticos. | Riesgo moderado de desajuste térmico o retraso en disponibilidad de ropa/vajilla. |
| **Perjuicios a Seguridad/Higiene** | **Peligro crítico** si desconecta involuntariamente refrigeración, ventilación forzada o alarmas. | Riesgo de fallos si se operan electrodomésticos de alta potencia sin supervisión nocturna. |
| **Perjuicios al Trabajo/Rutinas** | Desconexión accidental de routers, servidores domésticos o puestos de teletrabajo. | Fricción por pérdida de autonomía temporal en el uso de electrodomésticos. |
| **Coste de Implementación** | Bajo (enchufes inteligentes estándar y configuración básica). | Medio-Alto (automatización, electrodomésticos conectados o incentivos dinámicos). |

### Juicio de Decisión Responsable
Con únicamente 7 días de datos agregados observacionales, **no es metodológicamente responsable elegir una intervención cerrada ni prometer ahorros causales**. La agregación en un único canal `Appliances` oculta qué fracción de los 120–300 W basales corresponde a refrigeración vital o ventilación higiénica y qué fracción es consumo prescindible. 

**Recomendación responsable:** Proceder con un **ensayo prospectivo preliminar de baja invasividad y desagregación por submedición**, antes de imponer controles automatizados.

---

## 4. Diseño del Ensayo Prospectivo

Para verificar empíricamente la efectividad sin comprometer confort ni seguridad, se define el siguiente protocolo experimental:

```
+-------------------------------------------------------------------------------+
|                        DISEÑO PROSPECTIVO (4 SEMANAS)                         |
|                                                                               |
|  Semana 1: Línea Base con Submedición Desagregada (Sin intervención)          |
|  Semanas 2-3: Ensayos Cruzados A/B (Standby Inteligente vs. Control Activo)   |
|  Semana 4: Evaluación Post-Intervención y Encuesta de Confort                |
+-------------------------------------------------------------------------------+
```

1. **Unidad de asignación:**  
   Asignación cruzada temporal por bloques (*crossover trial* intra-vivienda) de semanas alternas (control habitual vs. intervención de gestión de cargas no esenciales), complementada si es posible con viviendas gemelas de control.

2. **Datos requeridos y duración:**  
   - Submedición por circuito/enchufe a resolución $\le 10$ minutos durante 4 semanas continuas.
   - Sensores de temperatura/humedad interior ($T_1 \dots T_9$) y exterior ($T_{\text{out}}$).
   - Registro continuo de eventos de anulación manual (*override*).

3. **Métrica primaria:**  
   Consumo eléctrico diario normalizado por grado-día de calefacción ($HDD = \max(0, 18.5 - T_{\text{out}})$):
   $$\text{Consumo Normalizado} = \frac{\text{kWh}_{\text{electrodomésticos}}}{\text{HDD}_\text{día}}$$

4. **Salvaguardas de confort y seguridad:**  
   - *Límites estrictos:* Temperatura interior en estancias ocupadas $\ge 19^\circ\text{C}$; humedad relativa entre 35% y 65%.
   - *Exclusión obligatoria de corte:* Circuitos de refrigerador, congelador, ventilación mecánica, router y seguridad.
   - *Botón de anulación física (*override*):* El residente puede reactivar cualquier enchufe inmediatamente sin penalización.

5. **Costes por actor:**  
   - *Residente:* Esfuerzo cognitivo inicial ($\le 1$ hora de inducción) y registro de incidencias.
   - *Investigador/Gestor:* Coste de sensores/submedidores (~150–300 €) y procesamiento de datos.

6. **Regla de tratamiento de faltantes:**  
   - Gaps $< 30$ min: interpolación lineal.
   - Gaps $\ge 30$ min o pérdida acumulada $> 5\%$ en un día: invalidación del bloque diario completo en el análisis por protocolo.

7. **Condición de parada y retirada de la intervención (*Stopping Rule*):**  
   - Activación de más de 3 anulaciones manuales por semana debidas a fricción de uso.
   - Excursión térmica por debajo de $18^\circ\text{C}$ durante $> 2$ horas en estancias principales.
   - Cualquier alarma de pérdida de frío en alimentos o fallo de seguridad eléctrica.

---

## 5. Separación entre Factibilidad y Eficacia

- **Factibilidad demostrada:** La captura de series a 10 minutos con sensores estándar es técnica y operativamente viable, con continuidad completa comprobada en el archivo.
- **Eficacia causal no probada:** Los patrones de consumo observados representan correlaciones históricas en condiciones no controladas; solo el ensayo prospectivo con salvaguardas podrá determinar si la intervención produce un ahorro neto estadísticamente significativo y socialmente aceptable.
