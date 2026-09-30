# D-E: energía de electrodomésticos

## Alcance y resultados observados

El manifiesto identifica la fuente como el conjunto UCI *Appliances Energy Prediction* (Candanedo; DOI 10.24432/C5VC8G; CC BY 4.0). La muestra seleccionada antes de analizar desenlaces cubre los siete días completos del 12 al 18 de enero de 2016. El replay verificó el hash SHA-256 de la muestra (`c7f66ffa…f05e6ba`), 1008 filas y continuidad a intervalos de diez minutos. Las marcas van de `2016-01-12 00:00:00` a `2016-01-18 23:50:00`; la zona horaria no está especificada.

La suma observada de `Appliances` fue **118.28 kWh**; los totales diarios fueron 12.34, 13.97, 21.80, 18.05, 18.04, 20.55 y 13.53 kWh, respectivamente. `lights` sumó **5.32 kWh**. El manifiesto especifica energía en Wh por intervalo para ambas columnas. Son medidas de este extracto, no estimaciones de ahorro ni de efecto causal. No se convirtió energía en potencia. `rv1` y `rv2` son variables aleatorias diagnósticas, no palancas de intervención.

La evidencia describe una semana observacional de una vivienda, sin asignación, intervención, seguimiento, ocupación ni costos individuales. No permite determinar qué consumo es evitable ni qué acción sería segura y aceptable. Habitantes, personas que realizan trabajo doméstico, pagadores, operadores y responsables del ensayo pueden tener intereses o cargas diferentes; sus identidades y autoridad no constan.

## Recomendación y medición necesaria

No recomiendo elegir ahora una intervención concreta. Desconectar cargas en espera podría interrumpir funciones o configuraciones necesarias; cambiar horarios podría interferir con rutinas, trabajo, disponibilidad o confort. Son opciones que podrían evaluarse, no resultados ni instrucciones de actuación. La factibilidad de una prueba tampoco demostraría eficacia.

Tras co-diseño y aprobación de las personas competentes, un ensayo prospectivo podría comparar una acción acordada con la práctica habitual. Antes, habría que inventariar equipos y funciones, medir consumos por equipo o circuito con instrumentos calibrados, y acordar datos de ocupación y eventos que sea necesario registrar. Si participan varios hogares voluntarios comparables, se podrían asignar hogares al azar a acción o control; con un solo hogar, considerar periodos alternados aleatorizados cuando el lavado y los efectos residuales lo permitan. La duración y el tamaño de muestra deben fijarse según la variación observada en una línea base y una meta de precisión, no suponerse a partir de esta semana.

La métrica primaria propuesta, pendiente de acuerdo, es kWh diarios de electrodomésticos por hogar, con diferencia e intervalo de incertidumbre entre acción y control. Acordar previamente salvaguardas y límites de confort, seguridad, trabajo y costo; registrar costos de medición, tiempo y cargas por actor. Definir cuánto dato faltante invalida una unidad o periodo, no contar días ausentes como ahorro e informar pérdidas por grupo y análisis de sensibilidad. Suspender ante incidentes o al exceder límites convenidos. Retirar la recomendación si no hay reducción compatible con el umbral acordado o si la incertidumbre incluye perjuicios relevantes. Umbrales, duración, consentimiento y criterios de valor permanecen pendientes.

## Traza y estado de las compuertas

El supervisor ejecutó `init`, siete operaciones `put`, `status` y las compuertas `frame` y `critique`; todos los comandos terminaron con código 0. Se registraron siete ítems: problema, actor, boundary, evidencia, supuesto, norma pendiente y requisito. `frame` quedó listo (`ready: true`) y no aceptado; no hubo revisión independiente. `critique` no quedó listo ni aceptado: faltan un concepto y dos opciones de encuadre, requiere aprobación humana verificada de `norm_pending` y la fase anterior no está aceptada.

En `status`, la evidencia tiene problemas de procedencia: faltan origen válido, fuente, fecha y localizador. El requisito carece de ruta válida al problema y de un problema compartido entre norma y evidencia fundamentada en protocolo. La propuesta inicial no incluyó esos campos o ítems, y las compuertas no los completaron. No se registró aprobación normativa; ninguna fase se completó. La traza inicial y el feedback no prueban consentimiento, eficacia ni superioridad de método.

## Límites de evaluación

El replay genérico tuvo éxito, sin error ni timeout, en 0.099 segundos; el ejecutable sellado no escribió archivos. Los controles reportan costo desconocido y límite de costo no aplicado. La revisión fue solo de seguridad de la propuesta cruda. Identidad del proveedor y llamadas al modelo no fueron autenticadas de forma independiente; tampoco se verificaron cancelación remota ni límites preventivos de tokens o herramientas. El orden se aplicó operacionalmente, no se hizo cumplir preventivamente. No hubo intervención de campo: autorización falsa. Aceptaciones normativas: 0; fases completadas: 0; aceptación global: 0/5; criterio 4 no evaluado; no se seleccionó ganador. Este desarrollo expuesto no es una comparación confirmatoria ni produce aceptación global.