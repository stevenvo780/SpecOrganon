# Sensibilidad temporal exploratoria · residuos de comedor escolar

Este análisis **posterior a la observación** amplía de forma descriptiva el [análisis fijado](../cases/school_waste/README.md). No modifica el [plan previo](plan_escuela_residuos.md), no selecciona una ventana para reemplazar su estimador y no constituye una evaluación confirmatoria. El XLSX original tiene SHA-256 `2ffad746b7ed5d536a0c99c37d8e249230d95d5fb2d041d85d01b69499f99624`; el plan tiene SHA-256 `49ce977aebb5fa6ddbd26bc008b9ffa4e094a4d81e4fe5f4785ee3e3895e9f66`. El [script](../scripts/school_waste_temporal.py) exige ambos anclajes mediante el lector existente.

Para reproducir la salida JSON desde la raíz del repositorio, solo se necesita Python 3 y la biblioteca estándar:

```sh
python3 scripts/school_waste_temporal.py > /tmp/school_waste_temporal.json
python3 -m json.tool /tmp/school_waste_temporal.json > /dev/null
```

El JSON incluye cada ventana, filas y fechas, kg sumados, días elegibles, comensales denominadores y g/comensal para PW (plato), KSW (cocina y servicio) y su total. Las cifras se calculan como `1000 × suma(kg) / suma(comensales)` sobre días elegibles, con decimales y redondeo final a seis posiciones.

## Cortes examinados

- La base original son 135 jornadas registradas entre el 8 de agosto de 2024 y el 14 de marzo de 2025. Se forman todas las ventanas **móviles de 20 jornadas registradas consecutivas**, sin completar días del calendario ausentes. De 116 candidatas, 18 contienen la fila 19 (2 de septiembre de 2024), que carece de KSW; se excluyen completas para que PW, KSW y total compartan los mismos 20 días y comensales. Quedan **98 ventanas completas**. El JSON identifica las 18 excluidas y la posición de la fila faltante.
- La ventana completa más cercana al período final comprende filas 117–136, del 10 de febrero al 14 de marzo de 2025. Es una referencia temporal exploratoria, no una base elegida antes de ver los resultados.
- El período final conserva sus 20 jornadas, filas 137–156, del 17 de marzo al 11 de abril de 2025. Se divide cronológicamente en cuatro semanas de lunes a viernes, cinco jornadas cada una; los cuatro conceptos aplicados fueron distintos según el [caso documentado](../cases/school_waste/README.md).
- Una sensibilidad aparte retira **la jornada entera** de las filas 137 y 152 por discordancias en columnas derivadas. Quedan 18 jornadas finales. No se sustituyen las masas fuente con las celdas calculadas: la discordancia no permite saber cuál dato original es correcto.

## Resultados descriptivos

| Período | Días PW/KSW/total | Comensales PW/KSW/total | PW g/comensal | KSW g/comensal | Total g/comensal |
| --- | ---: | ---: | ---: | ---: | ---: |
| Base completa original | 135/134/134 | 54 237/53 818/53 818 | 23,327452 | 21,756290 | 45,095972 |
| Última ventana basal completa | 20/20/20 | 7 661/7 661/7 661 | 21,346691 | 18,562851 | 39,909542 |
| Período final, 20 jornadas | 20/20/20 | 7 415/7 415/7 415 | 19,223601 | 9,844909 | 29,068510 |
| Final sin filas 137 y 152 | 18/18/18 | 6 798/6 798/6 798 | 18,299500 | 9,767579 | 28,067079 |

En la base original, PW usa 135 días, mientras KSW y total usan 134 porque falta KSW en la fila 19; por ello la suma de las dos tasas publicadas de componentes no coincide exactamente con la tasa de total, calculada sobre los 134 días compartidos.

El período final menos la última ventana basal completa da **−2,123090** g/comensal para PW, **−8,717942** para KSW y **−10,841032** para total. Frente a *cada una* de las 98 ventanas completas, el contraste final de 20 jornadas es negativo para los tres componentes. Los rangos de diferencias final menos ventana son PW **−7,678603 a −0,974654**, KSW **−17,149929 a −3,678232** y total **−23,076599 a −5,291220** g/comensal. Las ventanas se superponen ampliamente: 98 signos negativos no equivalen a 98 réplicas independientes ni a una medida de incertidumbre causal.

| Semana final | Fechas | PW g/comensal | KSW g/comensal | Total g/comensal |
| --- | --- | ---: | ---: | ---: |
| 1 | 17–21 marzo | 21,320858 | 5,938124 | 27,258982 |
| 2 | 24–28 marzo | 19,506555 | 8,300996 | 27,807551 |
| 3 | 31 marzo–4 abril | 17,127133 | 10,110072 | 27,237204 |
| 4 | 7–11 abril | 18,670421 | 15,945465 | 34,615886 |

KSW y total muestran variación semanal; la cuarta semana tiene el total más alto de las cuatro. Al retirar las filas discordantes, la semana 1 queda en cuatro jornadas con total **24,389423** g/comensal y la semana 4 en cuatro con **33,827660**. El período final de 18 jornadas da un contraste de total **−17,028893** g/comensal frente a la base original y de **−11,842463** frente a la última ventana basal completa. Frente a las 98 ventanas completas, su rango de contraste total es **−24,078031 a −6,292651** g/comensal. Esos cambios muestran sensibilidad a las dos fechas, no corrigen un error conocido en las masas fuente.

## Cortes placebo dentro de la línea base

El [control negativo adicional](../scripts/school_waste_placebo_cutoffs.py) examina una pregunta distinta: si caídas de tamaño similar ocurrieron **antes** de los cuatro conceptos del período final. Es un análisis posterior a la observación, sin umbral fijado en el plan previo. Forma los 96 bloques posibles de 40 jornadas basales registradas consecutivas y divide cada uno en 20 jornadas anteriores y 20 posteriores. Excluye el bloque completo cuando falta KSW en cualquiera de sus jornadas, de modo que PW, KSW y total usen los mismos días y denominadores. La fila 19 deja 18 bloques incompletos y **78 cortes completos**. El [JSON archivado](../experiments/development/school_placebo_cutoffs_2026-09-27.json) enumera fechas, filas, masas, comensales y diferencias de cada corte, además de los excluidos.

```sh
python3 scripts/school_waste_placebo_cutoffs.py > /tmp/school_waste_placebo_cutoffs.json
python3 -m json.tool /tmp/school_waste_placebo_cutoffs.json > /dev/null
cmp /tmp/school_waste_placebo_cutoffs.json experiments/development/school_placebo_cutoffs_2026-09-27.json
```

La comparación de referencia es el período final de 20 jornadas menos la última ventana basal completa de 20 jornadas: **−10,841032 g/comensal** de PW+KSW. En **9 de los 78 cortes basales completos**, la segunda mitad también presenta una caída al menos tan grande; ocho de esos nueve cortes son consecutivos y comparten casi todos sus días. Esto aporta un contraejemplo empírico a la idea de que el signo o tamaño de aquella caída, por sí solo, identifica un efecto de los conceptos. No estima cuántas caídas así cabría esperar sin intervención: los bloques se solapan, el corte real no se asignó al azar y pueden cambiar calendario, menú y asistencia. `9/78` es un recuento descriptivo, no un valor p ni un intervalo de incertidumbre.

## Inferencia y alcance

No se estima un efecto de intervención. Hay un solo centro, períodos sucesivos sin comparador contemporáneo, asistencia variable, estacionalidad posible y cuatro conceptos semanales distintos. Tampoco hay datos de producción, almacenamiento, transporte, transformaciones, costes, inocuidad o perjuicios por actor. Estas comparaciones no establecen causalidad ni satisfacen el criterio 3 de [GOAL.md](../GOAL.md), que sigue **no demostrado**.
