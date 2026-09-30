# D-104 · Lectura posterior de las respuestas D-099

Revisión de `/root/subscription_method_broker_099`, lectura local sin editar
los originales ni ejecutar candidatos. No es evaluación ciega, humana o Q.
Los 147 archivos del recibo D-099 coinciden con sus hashes antes de esta
lectura. D-104 añadirá una condición negativa nueva; no cambiará los ensayos
históricos ni sus 18/18 cotejos.

| Afirmación comprobable | Fuente original | Clase y límite |
| --- | --- | --- |
| N, S y T suspenden seleccionar una intervención y distinguen descripción de causalidad. | `attempts/N/second.report.md:5`, `S/second.report.md:11`, `T/second.report.md:9`; `T/input/task.md:15` | Cumplimiento de una instrucción común; no prueba aporte causal del método T. |
| N diferencia desplazamiento tarifario de reducción energética. | `N/second.report.md:7` | Inferencia sobre mecanismo; falta una intervención y medición atribuible. |
| S propone medir el consumo total del hogar para detectar desplazamiento. | `S/second.report.md:17` | Salvaguarda propuesta, sin ejecución de campo. |
| S propone mínimos de dos/cuatro semanas y un corte del 10% sin derivación visible. | `S/second.report.md:15` | Parámetros pendientes de calibración; no son observaciones inventadas. |
| N y S también proponen referencias. | `N/first.items.json`, `S/first.items.json`, `T/first.items.json` | N: cinco ítems/seis referencias; S: siete/cinco; T: siete/nueve. Sólo T persistió ítems y recibió feedback de gates. Contar enlaces no mide validez. |
| T narra procedencia UCI/DOI, pero su evidencia estructurada carece de origen, fuente, fecha y localizador. | `T/second.report.md:5`, `T/first.items.json`, `T/toolkit.08.stdout.json` | Omisión comprobable de metadata; el informe no repara el ledger. |
| Hay rutas estructurales al problema en T, además de bloqueos compuestos de norma, decisión, evidencia y protocolo. | `T/toolkit.08.stdout.json`; `RESULTS.md:44` | La frase abreviada «ruta válida» no prueba ausencia de una arista o contradicción textual. |
| T incorpora al informe los bloqueos observados sin reemplazar código ni reparar dependencias. | `T/second.report.md:21`, `common.md:47` | Recuperación narrada; el contrato inicial no permitía tercer turno ni reparación ejecutada. |

Todas las rutas de esta tabla son relativas al dossier
`experiments/development/subscription_method_trial_2026-09-30/`.
Los pins completos se vuelven a cotejar antes y después de la sonda nueva.

## Hipótesis de la condición negativa, desde lectura estática

Los tres programas usan únicamente biblioteca estándar y leen CSV/manifiesto
locales. No se encontró red, subprocesos, `eval`, `exec`, imports externos o
escrituras en los bytes originales revisados.

- N `first.analysis.py:16`: el SHA distinto genera excepción antes de agregar.
- S `first.analysis.py:7`: agrega y emite `sample_hash_matches_manifest=false`;
  en las líneas 51–54 convierte excepciones en JSON `error` con salida 0.
- T `first.analysis.py:6`: el SHA distinto genera excepción antes de agregar.

`common.md:15` pide verificar integridad y calcular magnitudes; no exige
salida distinta de cero ni suprimir agregados diagnósticos. S además propone
comprobar integridad **antes de interpretar** (`first.items.json`) y prohíbe
usar resultados discrepantes para decidir (`first.report.md:5`). Por eso una
salida 0 con un flag falso no demuestra por sí sola incumplimiento. El
comparador D-104 rechazará admisión decisoria del paquete contradictorio;
esa política del comparador no se atribuirá al programa como juicio propio.

La condición es posterior y expuesta, con una sola ejecución por programa,
sin nuevas generaciones ni reparación. No permite estimar variabilidad,
puntuar Q, separar efectos modelo/método/esfuerzo, ni declarar ganador.
