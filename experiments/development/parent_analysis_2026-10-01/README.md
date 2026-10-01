# D117 — un runtime desde work vacío hasta el merge

Corte mecánico optativo de C. El líder crea el grafo mediante un `init` real
del driver sellado; después trabajan dos ramas privadas, se consulta al reviewer
y se integran sus entregables. Todas las requests, herramientas y reservas
consumen un único ledger, contexto y claim, incluidos los turnos del líder.

Plan previo: [`plan.md`](plan.md), commits `4783701` y `c887f7e`.
Freeze: `25f8730`, [`source_freeze.json`](source_freeze.json), 55 pines.
Base: [`baseline_pins.json`](baseline_pins.json), 90 rutas inventariadas con
Luna y cotejadas de nuevo por root y un revisor independiente.
GOAL, protocolo, core, casos originales y módulos/dossiers D113/D115/D116
conservan sus bytes. No se rehace la suite global, wheel ni instalación D107.

## Flujo y controles

1. `prepare` crea work vacío para el líder y slots vacíos para las ramas. No
   recibe estado, grafo ni propuesta del caller, ni adquiere un claim.
2. El primer segmento adquiere el claim padre. En las trazas, el líder lee un
   bloque del caso con la herramienta sellada, ejecuta `init` y publica su
   texto final. El broker
   permite un único líder; no hay ownership ficticio ni rama dummy.
3. Durante el intervalo activo se verifica el init y su recibo, se congela el
   estado original y se selecciona trabajo independiente con el core/risk
   original. La transición liga seed, plan, manifiestos, fuentes y recibos.
   No se llama al preparador de otra sesión ni se convierte o repone el ledger.
4. Las requests de los workers se reservan por lote y se solapan; sus
   herramientas se ejecutan en serie. Cada historial bruto es privado. Las
   ramas reciben fuentes, grafo y texto público del líder. Análisis readonly,
   publicación de métricas y reparación CAS conservan el contrato D116.
5. El reviewer posterior recibe sólo entregables públicos, sin herramientas.
   El merge exige estado y tres recibos fijados por ruta y SHA; devolver `{}`
   desde un callback no permite finalizar. Sólo `finish` y un marcador válido
   habilitan publicación. Consultar un run terminado vuelve a validar el merge.

Replay y checkpoint CAS comprueban ambas fases, ordinals globales, ledger,
contexto, claim, fuentes e historias. Un efecto incierto, transición incompleta,
timeout o alteración bloquea publicación y reejecución automática. El límite
local de tiempo incluye el bootstrap y conserva las pausas; no autentica la
suma de actividad de los agentes dentro de un proveedor.

El preparador rechaza solapes físicos entre fuentes, run, stages y registro de
admisión antes de crear archivos, incluidos aliases y roots elegidos por defecto.
La cache de descubrimiento de fuentes revalida bytes e imports candidatos;
evita repetir AST sin omitir detección de cambios o nuevos módulos locales.

APIs: [`c_parent_analysis.py`](../../../scripts/c_parent_analysis.py),
[`managed_parent_analysis.py`](../../../scripts/managed_parent_analysis.py) y
[`parent_analysis_broker.py`](../../../scripts/parent_analysis_broker.py).
La CLI ofrece `prepare`, `status` y `step`, sin argumento de estado inicial.
Su transporte acepta fixtures HTTP locales; consultar desde otro proceso
requiere el intérprete registrado al generar el launcher.

## Evidencia y alcance

Los resultados, comandos, fuentes before/after y fallos conservados se detallan
en [`evidence.md`](evidence.md); el veredicto independiente está en
[`review.md`](review.md) y la cobertura de archivos en [`receipt.json`](receipt.json).
Las trazas usan fuentes públicas originales D-F/D-E, herramientas reales y
respuestas sintéticas de modelo. No se reclasifica ningún fallo como positivo
ni se cuentan enlaces `current` como ejecuciones nuevas.

El recibo padre declara `caller_graph_required:false`. El recibo D116 interno
mantiene su contrato histórico `true`: esa wave consume el seed creado por el
líder del padre, no un grafo entregado externamente. `completed` describe el
cierre de este mecanismo, no aceptación metodológica o resolución del caso.

**C1 técnico D107 conserva su evidencia; C2–C5: No demostrado. Formales: 0/24.**
Este corte no ejecuta las nueve fases completas ni fija un contrato comparable
A/B/C. Los tokens reportados por fixtures, precios declarados y cálculos
documentales no acreditan identidad, esfuerzo efectivo, uso/factura, Q,
soporte empírico, autoridad normativa ni impacto causal. El sandbox local no
aísla completamente de otro proceso hostil con el mismo UID; los snapshots
conservan evidencia y no restauran autoridad.

Siguiente: recorrido completo y coordinación/contrato/rúbrica comunes A/B/C
fijados prospectivamente. Después, ruta y telemetría autenticadas, autorización,
12 R1 reales, adaptación y freeze R2, 12 R2 y selección. Custodia, reserva,
panel, jueces y autoridades independientes, campo alimentario y transferencia
siguen pendientes. Protocolo §2 permite coordinación; el solo del compilador
D112 es una decisión local y sus calendarios existentes no se reinterpretan.

Luna ayudó con un inventario acotado de 90 archivos. Ese uso real de un
subagente de ingeniería no es una comparación de calidad entre modelos ni
una ejecución experimental de las 24 celdas.
