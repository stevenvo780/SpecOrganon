# D-099 · resultado observado del puente por suscripción

Plan registrado en `3ab2982`; broker y pruebas congelados en
`842d618` antes de las respuestas. Se solicitaron seis invocaciones CLI
con `gpt-6-luna`, esfuerzo `medium`, en orden S → T → N. Cada brazo
terminó antes de iniciar el siguiente. Un revisor nativo separado y la
raíz inspeccionaron el SHA de cada propuesta antes de su único replay.
La revisión fue de seguridad local por Codex, sin evaluación humana Q,
aprobación normativa, corrección de contenido o reparación del candidato.

## Resultados locales

| Brazo | Cotejos numéricos y de formato | Segundos activos | Tokens entrada / salida | Palabras finales | Comandos toolkit |
|---|---:|---:|---:|---:|---:|
| N | 18/18 | 66,305 | 30.980 / 3.280 | 506 | 0 |
| SDD | 18/18 | 68,574 | 31.050 / 3.371 | 575 | 0 |
| T inicial | 18/18 | 76,085 | 41.874 / 3.813 | 735 | 11 |

Cada brazo consumió dos invocaciones CLI y un replay sellado, sin timeout,
errores o herramientas de modelo observadas. El reloj activo incluye
preflight, generación, replay y comandos T; excluye preparación e
inspección de seguridad. El límite local solicitado fue 360 s por brazo.
Los 733 tokens de razonamiento son parte de los 10.464 tokens de salida;
los 6.912 tokens cacheados de T son parte de sus tokens de entrada.
Estas cifras proceden de JSONL local, sin recibo autenticado del proveedor.

Los tres replays produjeron 1008 filas continuas, separación de diez
minutos, 118,28 kWh de `Appliances`, los siete totales diarios y 5,32 kWh
de `lights`. El scorer fijado antes de las respuestas coteja esos valores
y unidades contra los bytes CSV verificados. El techo 18/18 no mide
calidad global, validez causal ni superioridad de método. Los pequeños
errores de representación flotante de N permanecen en su stdout y cumplen
la tolerancia absoluta predefinida de `1e-9`.

## Respuestas reales de T y defectos conservados

T ejecutó `init`, siete `put`, `status`, `gate frame` y `gate critique`.
El caso nuevo conserva siete eventos `item_put`, política `signed` y
ninguna aprobación o revisión de fase. `frame.ready=true`, aceptación
falsa. `critique` conserva cuatro bloqueos: falta un concepto, faltan dos
opciones de encuadre, la norma requiere aprobación humana verificada y
la fase previa no está aceptada. El bloqueo tiene varias causas.

La evidencia propuesta omitió origen, fuente, fecha y localizador.
`status.phases.specify` también señala un bloqueo compuesto de la ruta
problema/norma/evidencia/decisión y del vínculo con evidencia fundamentada
en protocolo. **Sí existen rutas estructurales al problema** en el grafo;
su presencia no satisface esos requisitos de validez. Esta precisión
acompaña al informe original, cuya expresión «ruta válida al problema»
abrevia el bloqueo compuesto. Los ítems y el informe permanecen intactos.

S captura excepciones y podría producir un objeto `error` con salida 0;
por ello el booleano del broker `analysis_successful` no basta para inferir
éxito científico. En la ejecución observada sí produjo todas las métricas
previstas y pasó los 18 cotejos. La frase de su informe sobre coste
«nulo» corresponde a JSON `null`: **coste desconocido**, sin declaración
de gasto cero ni evaluación humana igual a cero.

Los informes suspenden la selección de una intervención y proponen
medición futura con salvaguardas. Son propuestas: no hubo ensayo en una
vivienda ni consentimiento o decisiones de sus habitantes.

## Conservación y lectura reproducible

[receipt.json](receipt.json) vincula 147 archivos originales copiados
byte por byte, 12 marcadores operativos vacíos regenerados y 272 archivos
protegidos intactos, incluidos GOAL, casos y negativos anteriores. Se
conservaron inputs, prompts, schemas, streams, propuestas, código, informes,
feedback, ledger T, estados y registros del operador; ningún archivo de
autenticación, configuración o salida cruda del login.

Un proceso nuevo y el revisor verificaron `completed` para los tres
archivos; generación, feedback y finalización quedan deshabilitados.
Para leer el estado, desde la raíz del repositorio:

```sh
.venv/bin/python scripts/run_subscription_method_trial.py status experiments/development/subscription_method_trial_2026-09-30/attempts/S
.venv/bin/python scripts/run_subscription_method_trial.py status experiments/development/subscription_method_trial_2026-09-30/attempts/T
.venv/bin/python scripts/run_subscription_method_trial.py status experiments/development/subscription_method_trial_2026-09-30/attempts/N
```

La validación anterior al lanzamiento pasó 35 pruebas en Python 3.11 y
3.12 y Ruff. Los modelos de esas pruebas fueron falsos; sandbox y toolkit
eran procesos reales. La revisión posterior cotejó bytes, cronología,
estados y textos sin nuevas generaciones o ejecución de los candidatos.

## Alcance y próximo trabajo

El puente permite devolver a un modelo resultados numéricos y respuestas
reales de las compuertas iniciales mediante la CLI de suscripción existente.
El orden entre brazos fue aplicado por el operador; el broker impone
límites de cada brazo y admisión local cooperativa, sin prevenir otros
órdenes. Tiempo, tokens, coste humano, llamadas remotas, identidad efectiva
y custodia no tienen atestación externa o control global común.

Un caso expuesto, un modelo solicitado, sin réplicas ni jueces ciegos y
un tratamiento T inicial no completan la comparación del paquete de nueve
fases. **Q nulo, sin ganador, sin equivalencia de calidad, ninguna corrida
de las 24 y aceptación de GOAL 0/5.** D-097 permanece como negativo.

El siguiente frente es cotejar las 17 claims y siete filas alimentarias
desde los pasajes PDF, con unidades y bases explícitas y negativos
aislables. También siguen pendientes el panel confirmatorio, familias y
esfuerzos efectivos, autoridad humana competente y validación de campo
del objetivo completo.
