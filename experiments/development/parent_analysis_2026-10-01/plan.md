# D117 — inicialización y ramas bajo un runtime padre

Plan prospectivo anterior a los cambios de código. Base D116 final:
`ee26beb4cc7cb8788e130f0b0225f32b57a8cd3e`. GOAL, protocolo, fuentes y dossiers
D113/D115/D116 permanecen intactos. Las nuevas capacidades son opt-in.

## Diferencia que se cierra

Preparar D111 y después D116 crea otro ledger, contexto y claim. Tampoco admite
el replay D115 las requests previas del líder ni su broker un único workspace
de bootstrap. Encadenar ambos no es una corrida con presupuesto común.

D117 crea desde el principio un WaveLedger schema3, un RunContext y un claim
padre. El líder empieza con work vacío y crea el grafo mediante `init` real del
driver de método sellado. Sus requests, herramientas, tiempo y coste declarado
consumen los mismos topes usados después por los workers, reviewer y merge.
No se convierte TokenLedger, no se abre una sesión hija ni se repone saldo.

El corte implementa C desde work vacío hasta una wave y su merge, con respuestas
de modelo sintéticas y herramientas locales reales. No implementa todavía los
nueve pasos metodológicos, ni una comparación A/B/C, ni las 24 celdas formales.
La coordinación común A/B/C y contrato/rúbrica deben fijarse prospectivamente
antes de esas ejecuciones. Protocolo§2 permite coordinación: solo es una
decisión local del compilador D112, no una obligación del protocolo.

## Contrato

- Plan padre inmutable, modelo/esfuerzo/topes únicos, cierre de fuentes completo
  antes de enviar. Journal roots y slots de work se crean vacíos al preparar;
  inputs y grafo de ramas sólo se materializan durante el intervalo activo de
  transición. Los roots de work no implican un grafo ni ramas preparadas.
- Un único líder con historial privado. Se permiten init/status/read/write/
  replace/plan y análisis readonly D113; revise/review/advance/approve se
  rechazan en bootstrap. No hay nodos de ownership ficticios ni rama dummy.
- El texto final público del líder, un init exitoso autenticado por su request,
  respuesta y recibo, y el estado real con normas/fases pendientes habilitan la
  transición. El caller no aporta estado, seed ni propuesta de nodos.
- Transición append-only ligada al plan, recibos del bootstrap, work y SHA del
  estado líder. Selección independiente usa el core/risk original. Congela el
  manifest de branches, ownership y wave plan derivados; no cambia los
  bindings inmutables del contexto ni crea otro ledger/contexto/claim.
- Broker de fases: herramientas con ordinals globales continuos, mismas
  reservas/recibos planos; before/after-child/after-host y métricas D116. Fase
  bootstrap sólo acepta líder, fase wave sólo workers. Sólo una transición.
- Workers reciben fuentes comunes, grafo y artefacto público; nunca el historial
  privado del líder o de otro worker. Reviewer serial sólo recibe artefactos
  públicos y no tiene herramientas. Merge reproduce cambios con el core
  original y conserva normas pendientes y provenance de métricas vigentes.
- Replay reconstruye ambos historiales de fases y todos los requests/recibos/
  operaciones bajo el ledger común. Checkpoint CAS tras cada lote. Fuentes,
  descriptor de fase, claim, lease y deadline se verifican antes/después de I/O
  y efectos. Estado activo incierto, efecto sin recibo, timeout/señal/tamper o
  publicación incompleta bloquean reejecución automática y publicación.
- Sólo finish real permite publication.json; ningún flag prepared/completed,
  callback del caller o plan sustituto puede simular el cierre.

## Ownership y barreras

- Broker: nuevos `scripts/parent_analysis_broker.py` y
  `tests/test_parent_analysis_broker.py`. API preparada con root/leader y slots,
  broker invoke/verify/operations/branch/current_metrics/activate/journal_roots.
- Wrapper C: nuevos `scripts/c_parent_analysis.py` y
  `tests/test_c_parent_analysis.py`. prepare/guard/bootstrap_to_wave/status/step;
  prepara fuentes y work vacío, valida init real, deriva branches y merge.
- Root: nuevo `scripts/managed_parent_analysis.py`, sus tests e integración,
  dossier, freeze/gates, registros, documentación y recibo.
- Revisión independiente tras barrera de implementación y gates finales.

No se comparten archivos de escritura; todos preservan cambios ajenos. Modelos
nativos Codex continúan tareas que ya conocen; no se escogen por ahorro. Sonda
de cuota del 2026-10-01 08:30 UTC: Codex sin dato fiable, Gemini 92% ventana5h /
97% semanal; no se usa un proveedor externo. Máximo cuatro ramas incluyendo
root y profundidad dos. Luna puede encargarse de inventarios acotados; la
integración, replay y veredicto requieren comprobación independiente.

## Gates proporcionales

1. Prepare deja work líder vacío y no crea grafo/branch manifest/claim. Primer
   init real consume una request/tool del único ledger/contexto/claim.
2. Dos workers después de bootstrap, solapamiento de HTTP real por lote,
   reviewer posterior y merge. Mismo grafo creado por init, fuentes originales
   D-F/D-E, dos métricas frescas y reparación CAS sin reset.
3. Requests/tool/token/coste/tiempo acumulados incluyen líder y workers; límite
   insuficiente, errores ordinarios y transición incierta no se reetiquetan.
4. Init ausente/duplicado/inválido, mutación de seed/transition/manifests/
   fuentes/historias/streams, llamadas de fase equivocada, checkpoint viejo,
   ownership cruzado, métricas obsoletas, lease revocado y crash bloquean.
5. Consultar desde proceso nuevo con el intérprete exacto registrado. Fuentes
   congeladas antes de gates finales 3.11/3.12, Ruff/compilación/diff acotados y
   regresiones pertinentes, sin suite global, wheel o instalación repetidos.
6. Conservar intentos negativos, snapshots, comandos y streams originales;
   archivar únicamente roots registrados, verificar pins live/index/HEAD y
   revisión independiente sin normalizar bytes forenses.

## Límites

Sin claves, proveedores auténticos, gasto de API, publicación externa o campo.
Tokens de fixture y precios declarados no acreditan telemetría/factura. La
continuidad del reloj activo local no acredita actividad real ni suma de
tiempos de agentes dentro del proveedor; esa contabilidad debe cerrarse antes
de la comparación formal, con esperas API/humanas declaradas y sin imputación.
frontera local no protege contra un actor hostil del mismo UID. Ningún cálculo
documental prueba verdad empírica, autoridad normativa, Q o causalidad.

C1 técnico D107 conserva su evidencia; C2–C5 No demostrado, formales 0/24.
Después: workflow completo y coordinación/contrato/rúbrica comunes A/B/C,
autorización y rutas/modelo/esfuerzo/versión/telemetría reales, 12R1, adaptación
y freeze R2, 12R2 y selección; custodia/panel/jueces/autoridades/reserva/campo y
transferencia siguen pendientes. No se convierten simulaciones en aceptación.
