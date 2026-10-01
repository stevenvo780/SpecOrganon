# D115 — herramientas privadas e integración C

Perfil optativo `parallel_tool_wave_v2`, separado de las celdas DEV solo/trio.
Plan [prospectivo](plan.md), commit `11b6b73`; código congelado `9a6c4d8`.
34 pines de fuentes y 38 de base, incluidos GOAL, protocolo, core, producción,
wheel y fuentes originales. Este perfil sigue siendo experimental.

## Capacidad

- Dos a cuatro conversaciones privadas, con requests paralelos por turno.
- Una delegación, claim padre, WaveLedger, reloj activo y tope de herramientas.
- Herramientas reales selladas en stages físicamente separados; workspace y
  analysis_readonly tienen perfiles cerrados. Driver C de ownership fijo.
- Historial completo privado por worker; reviewer posterior sólo con textos
  públicos. Replays de modelo/recibo/ledger/historia antes de efectos.
- Checkpoints reconciliados y CAS entre pasos, sin reponer ningún saldo.
- Integración serial obligatoria: reproduce las operaciones reales con el core
  original, coteja cada rama y crea un estado nuevo con invalidaciones correctas.
- Marcador de publicación después del cierre de RunContext. Merge parcial,
  reserva sin recibo, reloj agotado o cierre incierto impiden publicar/reanudar.

El wrapper C expone el driver de método. La capacidad analysis_readonly del
broker se comprueba con una herramienta sintética: este corte no integra el
validador de métricas D113 en un workflow comparativo completo de C.

## Uso

Preparar con estado C válido, case público y inputs cuya `arm_prompt` declare
`alternative=C, mode=risk`:

```sh
python3 scripts/c_parallel_tools.py prepare --run-dir /absolute/new-run \
  --state /absolute/state.json --case-dir /absolute/case \
  --inputs-dir /absolute/inputs --config /absolute/config.json \
  --admission-root /absolute/private-admission
python3 scripts/c_parallel_tools.py status --run-dir /absolute/new-run
python3 scripts/c_parallel_tools.py step --run-dir /absolute/new-run \
  --expected-checkpoint CHECKPOINT_SHA256 \
  --local-http-fixture http://127.0.0.1:PORT
```

Cada `step` consume un turno real por worker activo, incluidas respuestas a
herramientas, y puede devolver `paused`. El último reúne revisión/integración.
La fixture HTTP es explícitamente sintética y no lee autenticación del operador.
La ruta `--provider openai` necesita autenticación y autorización de gasto;
no se ejecutó en este corte.

Config contiene los campos de D114 más `max_model_turns`, `max_tool_calls` y
`tool_wall_seconds`; identidad nueva `tool-wave-…`. Topes máximos 80k tokens,
128 requests, 64 tools, 5400 segundos activos; hasta32 turnos por worker.
Cada stage se prepara en un sibling privado `RUN-basename-branches`.
Errores escalares se rechazan antes de crear ese árbol. Un fallo I/O posterior
puede dejar preparación parcial: no existe rollback o retry universal.

## Evidencia y alcance

Gates finales sobre el freeze indicado: **272 passed en Python 3.11 y272 en
3.12**, Ruff/compilación/diff exit0;41 fuentes antes/después idénticas. Seis
trazas físicas distintas HTTP/CLI verificadas: tres waves paralelas, cuatro
tools, siete requests,91 tokens reportados por fixture, merge real de dos nodos
y reportes con normas pendientes. Archivo12.671 regulares/4.352.826B reabierto
y cotejado; los enlaces quedan sólo como metadata. [Registro](evidence.md),
[revisión](review.md) y [trazas](verified_traces.json).

**C1 técnico D107 vigente; C2–C5 No demostrado; cero de24 celdas formales.**
Fixtures y tokens reportados por fixtures no acreditan identidad/versión del
modelo, effort efectivo, factura, Q, juicio humano ni impacto. No hubo modelos
experimentales, APIs de pago, campo, custodia externa o aprobación normativa.
Landlock/seccomp/sellos son una frontera local limitada; procesos del mismo UID
y swaps transitorios no están completamente aislados. No hay cancelación remota
garantizada ni restauración de una sesión completa.
