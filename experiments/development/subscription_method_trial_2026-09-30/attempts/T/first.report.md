# D-E: energía de electrodomésticos

## Alcance y evidencia

La fuente publicada es el conjunto UCI *Appliances Energy Prediction* (Candanedo; DOI 10.24432/C5VC8G; CC BY 4.0), según `source_manifest.json`. El paquete selecciona, antes de analizar desenlaces, los siete días completos del 12 al 18 de enero de 2016: 1008 registros nominales cada diez minutos. El CSV da energía por intervalo en Wh para `Appliances` y `lights`; sus marcas temporales no especifican zona horaria. La ejecución de análisis propuesta comprobará el hash, cantidad de filas, marcas e intervalos y calculará el total semanal y totales diarios de electrodomésticos, más el total de luces. Las cifras se informarán desde el replay; no se anticipan aquí.

Es una semana observacional de una vivienda de características y ocupación insuficientemente descritas. No hay asignación, intervención, seguimiento, costos individuales ni resultados de confort o seguridad. Por tanto, estas mediciones describen el extracto; no estiman ahorro causal ni representan otras viviendas. `rv1` y `rv2` son variables aleatorias diagnósticas, no palancas de intervención. El análisis no convierte energía de intervalo en potencia.

## Actores y cuestión pendiente

Habitantes y personas que realizan trabajo doméstico pueden recibir beneficios y soportar molestias; quien paga la energía puede tener costos distintos de quien opera los equipos. Deben participar también quien gestione el ensayo y quien pueda atender riesgos eléctricos o de seguridad. No conocemos quiénes son ni quién tiene autoridad para fijar prioridades. Ahorro, confort, seguridad, trabajo y costo son criterios relevantes, pero sus umbrales y ponderaciones son decisiones pendientes de los habitantes y responsables competentes; no se atribuye consentimiento.

La pregunta empírica es si una acción concreta reduce el consumo de electrodomésticos frente a la práctica habitual, sin perjuicios inaceptables para esos actores. La semana no permite elegir con fundamento qué equipos consumen energía evitable, qué acciones serían practicables ni cuándo hacerlo.

## Opciones y recomendación

Una opción para evaluar sería desconectar cargas en espera, con riesgo de interrumpir funciones necesarias, perder configuraciones o afectar seguridad. Otra sería cambiar horarios de uso, con posible conflicto con rutinas, trabajo, disponibilidad y confort. Ambas son hipótesis de ensayo, no hallazgos ni instrucciones para actuar. Sin inventario de equipos, conversación con habitantes, evaluación de seguridad y preferencias explícitas, recomiendo suspender la selección de una intervención. La factibilidad operativa tampoco demostraría eficacia.

## Diseño para resolver la incertidumbre

Tras aprobación y co-diseño, inventariar por equipo consumos y funciones, documentar ocupación/rutinas sin recoger datos innecesarios, y acordar salvaguardas, costos por actor y umbrales de retiro. Registrar energía de electrodomésticos con medición calibrada por circuito o equipo, estado de intervención, uso/ocupación con consentimiento, condiciones ambientales y eventos de seguridad o confort. Recoger una línea base suficiente para caracterizar variación semanal y rutinas; la duración y tamaño muestral deben fijarse con esos datos y un cálculo de precisión, sin suponer que esta sola vivienda permite generalizar.

Si hay varios hogares voluntarios comparables, asignar hogares al azar a acción acordada o control de práctica habitual; si solo participa uno, usar periodos alternados aleatorizados de intervención y control con lavado cuando sea viable, registrando tendencias y posibles efectos residuales. Métrica primaria propuesta, pendiente de aprobación: kWh diarios de electrodomésticos por hogar, comparados entre grupos/periodos y ajustados por ocupación y calendario preespecificados. Reportar diferencia e intervalo de incertidumbre, además de distribución diaria; no interpretar asociación como efecto si el diseño o faltantes impiden identificación.

Acordar antes de comenzar límites de confort, actividades que no deben interrumpirse, revisión eléctrica y contacto para incidentes. Registrar costos de medición, tiempo de habitantes, cambios de factura y carga de trabajo por actor. Definir un periodo máximo sin datos y causas; no imputar días faltantes como ahorro, informar pérdidas por grupo y hacer sensibilidad. Suspender la acción ante incidente, cruce de un límite acordado, perjuicio laboral/doméstico o costo no aceptado; retirar la recomendación si no se observa reducción compatible con el umbral acordado o la incertidumbre incluye perjuicio relevante. Umbrales, duración, consentimiento y cualquier decisión de valor siguen pendientes.

## Traza inicial y estado

La traza propuesta registra problema, actor, límites, evidencia publicada, norma propuesta pendiente y requisito dependiente de esa norma. Se someterá al tratamiento inicial indicado: las respuestas reales de `init`, `put`, `status` y compuertas `frame` y `critique` del supervisor determinan qué quedó registrado, qué referencias o dependencias requieren revisión y qué bloqueos quedan. Esta propuesta no afirma que se haya operado directamente una herramienta ni que exista aprobación o firma. El tratamiento no completa nueve fases, no sustituye deliberación humana ni valida eficacia. Toda decisión normativa permanece pendiente.