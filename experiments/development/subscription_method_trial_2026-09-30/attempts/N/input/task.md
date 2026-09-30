# D-E · Paquete visible de desarrollo: energía de un edificio

**Pregunta común:** Con la muestra observacional adjunta, ¿qué intervención concreta merecería un ensayo prospectivo para reducir el consumo eléctrico de electrodomésticos de esta vivienda sin trasladar perjuicios a confort, seguridad, trabajo o coste? Si los datos no permiten elegir con fundamento, explica la decisión y diseña la medición que resolvería la incertidumbre.

## Datos disponibles para los tres métodos

- [`sample_first_complete_week.csv`](sample_first_complete_week.csv): las 1008 observaciones originales cada diez minutos entre el 12 y el 18 de enero de 2016, inclusive. Son los primeros siete días completos después del inicio parcial del archivo, elegidos por fecha antes de analizar desenlaces.
- [`source_manifest.json`](source_manifest.json): procedencia, licencia, regla de selección, columnas y hashes. El [archivo completo de UCI](https://archive.ics.uci.edu/dataset/374/appliances%2Benergy%2Bprediction) cubre unos 4,5 meses, pero este paquete entrega solo la semana indicada. `Appliances` y `lights` son energía en Wh por intervalo; `T*` y `RH_*` son sensores de temperatura y humedad. Las variables `rv1` y `rv2` son aleatorias y no representan palancas de intervención. Las marcas de tiempo del CSV no declaran zona horaria.

El hogar, su ocupación, operación de aparatos y costos individuales no están descritos con suficiente detalle para inferir efectos causales. No hay asignación, intervención ni seguimiento posterior en este paquete. No se autoriza actuar sobre una vivienda real ni fijar compromisos normativos por sus habitantes.

## Entrega común

1. Un `analysis.py` ejecutable con la biblioteca estándar de Python que lea este CSV, verifique el número y la continuidad de intervalos y calcule al menos el total semanal de `Appliances` en kWh, totales por día y una observación adicional pertinente. Debe informar sus unidades y no usar `rv1`/`rv2` como predictores causales.
2. Un `report.md` de hasta 1200 palabras que distinga medidas del archivo, inferencias, supuestos y decisiones que requieren aprobación. Delimita actores y criterios de valor; compara al menos dos intervenciones posibles y sus perjuicios; recomienda una o explica por qué todavía no es responsable elegir.
3. En ese informe, especifica cómo probar prospectivamente la recomendación frente a una línea base/control: unidad de asignación, datos y duración necesarios, métrica primaria, salvaguardas de confort/seguridad y costes por actor, regla de faltantes, incertidumbre y condición que haría retirar la recomendación. Separa factibilidad de eficacia observada.

Todas las cifras utilizadas deben proceder del CSV, del manifiesto o de una fuente adicional accesible por igual a los tres métodos y citada explícitamente. No inventes resultados de intervención. La corrección de los cálculos, la justificación de afirmaciones y el reconocimiento de límites importan más que la cantidad de documentos.

**Clasificación:** desarrollo expuesto D-E. No es R-F, R-M ni R-S, no es reserva ciega y no produce un veredicto del criterio 3 o 4.
