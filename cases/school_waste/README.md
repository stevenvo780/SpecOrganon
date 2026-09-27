# Residuos de comedor escolar · análisis de desarrollo

## Fuente y reproducción

El archivo [source.xlsx](source.xlsx) es una copia sin cambios de *Food waste dataset: secondary school in Finland 2024-2025*, de Arja Kuusisto, Jenni Latva y Ella Wilén, publicado el 24 de junio de 2026 con DOI [10.5281/zenodo.20825233](https://zenodo.org/records/20825233) y licencia [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). SHA-256 del XLSX: `2ffad746b7ed5d536a0c99c37d8e249230d95d5fb2d041d85d01b69499f99624`. El depósito informa MD5 `3f7e610fedc1810f7e8bc1bd47103ee7`, que coincide con esta copia. El crédito y la licencia corresponden a las autoras; este análisis y su documentación son nuestros cambios, no parte del archivo original.

El [plan](../../docs/plan_escuela_residuos.md) se comprometió en `57be093` antes de leer los valores de resultado locales. Su SHA-256, fijado por el [analizador](../../scripts/analyze_school_waste.py), es `49ce977aebb5fa6ddbd26bc008b9ffa4e094a4d81e4fe5f4785ee3e3895e9f66`. El [JSON derivado](../../experiments/development/school_waste_2026-09-26.json) conserva fuente, plan, reglas, denominadores, exclusiones y discrepancias de columnas calculadas. Para reproducirlo desde la raíz del repositorio:

```sh
UV_LINK_MODE=copy uv run python scripts/analyze_school_waste.py --output /tmp/school_waste_recheck.json
cmp /tmp/school_waste_recheck.json experiments/development/school_waste_2026-09-26.json
```

El script rechaza cambios en el XLSX o en el plan y no sobrescribe una salida diferente. Lee las primeras ocho columnas de la hoja indicada en el plan, usa masas en kg y comensales para recalcular g/comensal con decimales, y trata las columnas por comensal ya calculadas como control de calidad.

## Resultado observado

La línea base comprende 135 días (8 de agosto de 2024 al 14 de marzo de 2025) y la intervención 20 días (17 de marzo al 11 de abril de 2025). La [descripción del depósito](https://zenodo.org/records/20825233) fija ese corte. La [descripción del proyecto](https://blogit.uniarts.fi/kirjoitus/artistic-expertise-in-solving-food-waste-issues/) indica que se aplicaron cuatro conceptos artísticos distintos, uno por semana: las 20 jornadas no representan un tratamiento único homogéneo.

| Residuo | Base, g/comensal | Intervención, g/comensal | Diferencia | Cambio relativo | Días base/intervención |
| --- | ---: | ---: | ---: | ---: | ---: |
| Plato (PW) | 23,327452 | 19,223601 | −4,103851 | −17,592367 % | 135 / 20 |
| Cocina y servicio (KSW) | 21,756290 | 9,844909 | −11,911381 | −54,749136 % | 134 / 20 |
| PW + KSW | 45,095972 | 29,068510 | −16,027462 | −35,540784 % | 134 / 20 |

El estimador divide la suma de kg por la suma de comensales de los días elegibles. Para PW, los denominadores son 54.237 y 7.415 comensales. KSW falta el 2 de septiembre de 2024, fila 19 del XLSX: KSW y total excluyen ese día sin imputación, con denominadores 53.818 y 7.415. Ambos componentes bajan en el agregado; no se observa el desplazamiento específico «total baja mientras PW sube» previsto en el plan.

La sensibilidad de 20 menús compartidos, con igual peso por menú y medias diarias internas, da diferencias de −3,804844 g/comensal para PW, −12,615255 para KSW y −16,476715 para total. Los rangos por menú incluyen valores positivos: PW −13,342612 a +2,817900, KSW −33,619071 a +11,795370 y total −41,962585 a +3,453752 g/comensal. Cinco menús de la línea base no aparecen en el período final. Esta comprobación descriptiva no resuelve estacionalidad, asistencia ni cambios simultáneos.

La [sensibilidad temporal posterior](../../docs/sensibilidad_temporal_escuela.md) deja visibles las ventanas basales de 20 jornadas, los faltantes y los resultados semanales. Un control negativo compara también mitades de 20 jornadas dentro de bloques enteramente basales: nueve de 78 cortes completos muestran caídas de PW+KSW al menos tan grandes como el contraste final frente a la última ventana basal. Son exploraciones posteriores a la observación; no cambian el estimador ni el alcance causal del plan anterior.

## Calidad y alcance

El cotejo de columnas derivadas detecta valores discordantes el 17 de marzo de 2025 (fila 137, g/comensal de PW y KSW) y el 7 de abril de 2025 (fila 152, PW en g y PW g/comensal). El cálculo usa las columnas fuente en kg según el plan, sin corregirlas. Una discordancia derivada no permite saber si también hay un error en la masa fuente; para atribuirlo harían falta aclaración de las autoras o registros primarios.

Es un único centro, con períodos sucesivos, asistencia diferente, 20 días finales y cuatro conceptos semanales. No hay grupo no tratado simultáneo ni asignación que separe los conceptos del tiempo. Por eso el contraste no es un efecto causal ni una estimación de ahorro transferible. Tampoco contiene producción, almacenamiento, transporte, compras, dos transformaciones encadenadas, inocuidad, costes o perjuicios por actor. Aporta datos reales de consumo y servicio para probar reglas analíticas; el criterio alimentario 3 de [GOAL.md](../../GOAL.md) permanece **no demostrado**.
