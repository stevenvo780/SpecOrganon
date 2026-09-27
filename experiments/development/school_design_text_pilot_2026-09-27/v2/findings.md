# Piloto de diseño alimentario: lectura de desarrollo

**Corte:** 2026-09-27 UTC. Este expediente compara la calidad de nueve textos generados para una sola tarea escolar conocida. `A-M` es una instrucción **manual** de filosofía, ciencia e ingeniería; ningún brazo ejecutó el toolkit, CLI, MCP ni el brazo `T` de la matriz confirmatoria. Son tres configuraciones de ruta de dos familias: Gemini 3.8 Flash Low y High, y MiniMax M3. El bridge no aportó recibos de tokens, coste ni configuración efectiva del proveedor.

## Secuencia y desviaciones

El [protocolo original](../README.md) y sus prompts/rúbrica se fijaron en `436065e`. La primera ruta Gemini fue rechazada por el bridge antes de obtener respuesta y se archivó en `d001784`. La [revisión v2](../revision_v2.json), fijada en `379a4cb` antes de cualquier respuesta sustantiva, cambió las rutas Gemini al nombre visible que acepta el bridge y reinició la matriz. **Esa decisión incumple la regla original de no sustituir una ruta fallida**: v2 es un piloto exploratorio revisado, no una ejecución conforme del plan inicial. En total se registraron diez intentos de bridge y nueve respuestas de proveedor en v2.

Las nueve [respuestas crudas](outputs/) se fijaron en `9d8d450`; sus [copias anonimizadas](blind/manifest.json), en `6badc4c`. Dos juezas recibieron la tarea común, la rúbrica y textos con IDs opacos. Sus [fichas](ratings/) se fijaron en `f7ff9c4`; el [mapa de identidades](blind/reveal_map.json) se publicó después, en `f1c2e7e`. Los archivos y hashes permiten comprobar ese orden dentro de este repositorio, pero no acreditan la independencia de las juezas, qué archivos pudieron consultar ni el aislamiento de las llamadas. Las respuestas identificadas ya estaban en el repositorio antes de puntuar. Un texto usa lenguaje distintivo de una instrucción de especificación, por lo que el brazo pudo inferirse a partir del contenido.

El [protocolo](../README.md) excluye del `Q` comparativo las respuestas que excedan 900 palabras y pide puntuar solo textos conformes. El `A-M` de Gemini High tiene **917 segmentos contables** tras excluir marcadores Markdown compuestos solo de signos; el manifiesto registra 923 segmentos separados por espacios. Ambas juezas lo puntuaron de todos modos (`75` y `82`). Se conservan esas fichas como observación suplementaria, pero **no** se calcula `Q` primario ni diferencias emparejadas para esa celda. Esta puntuación fuera del procedimiento es otra desviación visible.

## Resultado descriptivo

`Q` es la media de las dos fichas ciegas conformes, sobre 100 puntos. No hubo fallos críticos marcados, discrepancias superiores a 10 puntos ni arbitraje requerido. El [resultado JSON](analysis.json) se reproduce desde la raíz del repositorio con [el analizador](../../../../scripts/analyze_school_design_text_pilot.py):

```bash
python3 scripts/analyze_school_design_text_pilot.py \
  --base experiments/development/school_design_text_pilot_2026-09-27 \
  --mapping experiments/development/school_design_text_pilot_2026-09-27/v2/blind/reveal_map.json \
  --ratings-a experiments/development/school_design_text_pilot_2026-09-27/v2/ratings/judge_a.json \
  --ratings-b experiments/development/school_design_text_pilot_2026-09-27/v2/ratings/judge_b.json
```

| Ruta declarada | N | S | A-M | A-M−N | A-M−S |
|---|---:|---:|---:|---:|---:|
| Gemini 3.8 Flash Low | 73,5 | 72 | 80,5 | +7 | +8,5 |
| MiniMax M3 | 51,5 | 65 | 61 | +9,5 | −4 |
| Gemini 3.8 Flash High | 77 | 78,5 | excluido | sin par | sin par |

Hay ocho `Q` primarios de nueve respuestas y cuatro pares completos de seis posibles. El resultado es mixto incluso entre los pares disponibles. Gemini Low y High son variantes declaradas de una misma familia; `effort_argument` fue `null`, y las etiquetas de ruta no son un recibo independiente del esfuerzo aplicado. Las llamadas conservaron el orden previsto de brazos y directorios de trabajo distintos, pero los archivos locales no autentican los bytes que recibió el proveedor ni prueban que no hubiera contexto externo.

Una tarea expuesta, una respuesta por celda, longitud de prompt distinta entre brazos, límite de salida solicitado pero no impuesto y ausencia de telemetría comparable impiden estimar variabilidad o separar efectos de método, modelo y esfuerzo. El caso escolar solo observa servicio y consumo, sin las etapas anteriores de una cadena completa y sin atribución causal. Este piloto **no** demuestra los criterios 3 o 4 de `GOAL.md`.
