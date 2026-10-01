# Puertas antes de un envío real

Esta propuesta fija entradas revisables; no declara que R1 pueda comenzar.
Las dos opciones usan las mismas doce coordenadas y recursos. Sólo una podrá
elegirse: el uso interno de Luna como explorer no selecciona el modelo R1.

| Puerta | Estado y siguiente acción concreta |
| --- | --- |
| Recursos y tarifas | Propuestos y calculados en `forecast.json`; refrescar tarifas al fijar la ruta y comprobar si aplican premiums. No es coste completo. |
| Modelo | ID público literal, `high` solicitado. `version` repite el alias; no acredita snapshot servido, esfuerzo efectivo ni disponibilidad de cuenta. Fijar evidencia de identidad antes de R1. |
| Acceso | CLI/cuota no prueban Responses API. El operador deberá disponer del acceso en su entorno; no enviar credenciales al chat ni incorporarlas al dossier. |
| Transporte | La CLI coordinada publicada `step` exige fixture. La API Python admite transportes compatibles, pero hace falta un entrypoint para ruta real que conserve los guards D119 y la observación D121. No saltar esos controles para usar HTTP. |
| Conteo | `/responses/input_tokens` está documentado; falta comprobar payload exacto y concordancia del conteo con uso para modelo/cuenta/ruta aprobados. No asumir gratuidad del conteo ni sumarla como cero. |
| Telemetría | Responses documenta `cached_tokens` y `cache_write_tokens`, que particionan input. Exigir uso entero completo y precios aplicables; discrepancias/ausencias dejan operación indeterminada. No usar la limitación de uso del Agents API como si fuera de Responses. |
| Incomplete | El dispatcher simple y el coordinado no tienen el mismo comportamiento. La ruta coordinada decodifica y exige `completed`/modelo exacto antes de liquidar; un rechazo podría dejar reserva sin conciliar aunque el proveedor cobre. Asegurar que un envío truncado/fallido conserve su coste/reserva y evidencia sin permitir un reintento favorable o resets. No se reprodujo una respuesta remota. |
| Capacidad de respuesta | 8.192 cubre también razonamiento y formato. Es el máximo del runtime actual y menor que la recomendación inicial de 25.000 de la guía; declarar riesgo. Una futura política nueva requiere nuevo freeze previo, sin modificar fuentes D119/D121 ni elegir tras ver resultados. |
| Evaluación | La rúbrica estructural existe; no demuestra Q ni verdad de cálculos/citas. Definir evaluación verificable o independiente, cegado, identidad y coste/tiempo antes del resultado. H, herramientas y evaluación siguen pendientes de coste completo. |
| Autorización | Ningún gasto aprobado. El dueño debe elegir modelo/ruta y autorizar el alcance y topes concretos por su canal. Una elección o aprobación no constituye por sí sola evidencia de las demás puertas. |
| Freeze real | Después de cerrar las puertas, fijar una ruta y un intérprete, las doce identidades/orden, evaluación y recursos. Sólo entonces ejecutar 12 R1; adaptación/freeze posterior habilita 12 R2. |

## Opciones de gasto del modelo

Con tarifas Standard de texto/contexto corto, sin premium, y el límite común
de 80.000 tokens totales por celda, el techo conservador incluye hasta un
microUSD de redondeo por cada una de 128 solicitudes:

| Opción | Techo condicional de modelo, doce R1 | Saldo local propuesto, doce R1 |
| --- | ---: | ---: |
| Astra `high` | USD 48,001536 | USD 60 (USD 5/celda) |
| Luna `high` | USD 0,481536 | USD 0,60 (USD 0,05/celda) |

El saldo local es una restricción propuesta del ledger, no un límite remoto
de facturación. La cota usa tokens realmente medidos, incluidas caché y
razonamiento una sola vez; depende de semántica/telemetría/precio concordantes.
No añade ni imputa cero a impuestos, conteo, tools, revisión humana,
evaluación, actividad remota o campo. No suma ambas opciones: se elige una.

Las tarifas son datos oficiales observados el 1 de octubre de 2026; las
cotas son inferencias aritméticas nuestras. [Astra](https://developers.openai.com/api/docs/models/gpt-6-astra),
[Luna](https://developers.openai.com/api/docs/models/gpt-6-luna),
[caché](https://developers.openai.com/api/docs/guides/prompt-caching),
[conteo](https://developers.openai.com/api/docs/guides/token-counting) y
[razonamiento](https://developers.openai.com/api/docs/guides/reasoning).

## Alcance de calidad

Luna realizó un inventario acotado de código, cotejado por root. El revisor
independiente conserva el veredicto local. No se midió calidad relativa
Astra/Luna ni se justifica reemplazar un ejecutor exigente sólo por ahorro.
Los costes no son un criterio de éxito metodológico. C1 técnico D107 sigue;
C2–C5 No demostrado; 0/24 ejecuciones formales.
