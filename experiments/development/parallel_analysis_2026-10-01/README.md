# D116 — análisis en ramas privadas de C

Extensión opt-in del ensayo mecánico D115. El participante ejecuta el launcher
real D113 en un sandbox de lectura; el host valida y publica métricas con
provenance. Un único ledger, contexto, claim y presupuesto cubre todas las
ramas, reparación CAS, reviewer y merge.

Plan previo: [`plan.md`](plan.md), commit `f51026b`. Fuentes congeladas:
`088bd2a`, [`source_freeze.json`](source_freeze.json), 52 pines.
Preservación: [`baseline_pins.json`](baseline_pins.json), 71 rutas anteriores.
Los módulos originales D113/D115, GOAL, protocolo, core, producción, wheel y
fuentes originales no se modifican.

## Capacidades

- Manifest v2 identifica el contrato de análisis y fija launcher y cierre de
  fuentes. El perfil v1 sigue intacto.
- Los recibos conservan inventarios reales antes del análisis, después del
  participante y después de la publicación del host. Sólo el host modifica
  `metrics.json`; JSON debe ser un objeto estricto finito de hasta 128 KiB.
- Error ordinario o JSON inválido consume recursos y entrega feedback. El
  modelo puede reemplazar su código mediante CAS y analizarlo nuevamente sin
  reponer límites. Análisis inválido retira las métricas previas.
- Las métricas sólo se exportan si permanecen vigentes el script y todos los
  archivos/directorios no métricos que el análisis podía leer.
- Señal, timeout, fuente alterada, guard perdido o efectos sin recibo bloquean
  publicación y reejecución. Un cierre incierto no se transforma en éxito.
- El preparador C rechaza una política de reparación ausente, irregular,
  demasiado grande, JSON inválido o de esquema distinto de entero 2 antes de
  crear la corrida y sus ramas. La política mínima del fixture es sólo un
  discriminante; los sellos y límites se comprueban por mecanismos distintos.

APIs y CLI: [`c_parallel_analysis.py`](../../../scripts/c_parallel_analysis.py),
[`managed_parallel_analysis.py`](../../../scripts/managed_parallel_analysis.py),
[`parallel_analysis_broker.py`](../../../scripts/parallel_analysis_broker.py).
La CLI ofrece `prepare`, `status` y `step`; el transporte de esta entrega acepta
únicamente fixtures HTTP locales. `status` funciona desde un proceso nuevo y
comprueba fuentes, recibos y checkpoint. No cambia constructores globales.

## Evidencia y límites

**114 pruebas aprobadas por intérprete** (3.11/3.12), Ruff/compilación/diff
correctos; seis trazas verificadas y revisión sin P1/P2 abierto. Detalles en
[`evidence.md`](evidence.md), [`review.md`](review.md) y `receipt.json`. Los intentos
previos, incluidos fallos de fixtures y aserciones, se conservan en `checks/`
y `worker_checks/` con fuentes y streams. Una prueba fallida no se renombra.

La integración emplea los paquetes originales públicos D-F y D-E, herramientas
reales y respuestas de modelo sintéticas. Sus cálculos documentales comprueban
efectos mecánicos; no miden calidad de un modelo, impacto causal ni Q.
El grafo inicial sigue aportado por el caller. `completed` indica cierre de la
wave y publicación controlada, no aceptación del caso ni resolución de GOAL.
La consulta de cada runtime exige el intérprete registrado al generar su
launcher. El archivo de evidencia no permite recrear o transferir su autoridad.

**C1 técnico D107 conserva su evidencia. C2–C5: No demostrado. Ejecuciones
formales de desarrollo: 0/24.** Agentes nativos reales ayudaron a construir esta
extensión; no sustituyen las ejecuciones experimentales pendientes. Luna se
usó para un inventario acotado de preservación, verificado nuevamente por root;
su resultado no es una comparación de calidad entre modelos.

Siguiente dependencia: runtime padre que arranque con work vacío y construya
el grafo mediante `init` del líder, manteniendo desde el primer request el
mismo presupuesto y claim. Coordinación, fuentes y contrato deben declararse
prospectivamente para A/B/C. Siguen pendientes contrato/rúbrica sin respuestas,
ruta y telemetría autorizadas, R1, adaptación/freeze R2, selección, custodia,
jueces y autoridades independientes, campo alimentario y transferencia real.
No se redefine el calendario solo existente ni se modifica GOAL o protocolo.
