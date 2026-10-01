# D118 — contrato común prospectivo de desarrollo A/B/C

Base verificada: D117 `e2f76688ecd64d286f266d305d28fb256d377111`, árbol limpio.
El turno anterior fue progreso: añadió y selló bootstrap real desde work vacío,
98 pruebas por intérprete, seis trazas y revisión independiente. GOAL se leyó
íntegro al reanudar; sigue obligatorio y no se modifica. C1 técnico D107
conservado; C2–C5 No demostrado; formales 0/24.

## Decisión y alcance completo del corte

El calendario existente fija solo y sus hashes/IDs; D117 C tiene cuatro roles
con dos workers, sin binding a ese calendario. Mezclarlos confundiría método
y coordinación. Protocolo §2 permite coordinación DEV y exige 24 futuras
ejecuciones de prototipos; §3 reserva solo/trío para N/S/T confirmatorios.
Las cuatro fases de prototipos no se reinterpretan como las nueve del toolkit.

Se fija un perfil NUEVO para R1: líder, worker-1, worker-2 y reviewer, mismo
modelo/version/esfuerzo, acceso, permisos y presupuesto total A/B/C. Bootstrap
con work vacío e init real del líder; selección y orden por el modo original
sequential/graph/risk. Máximo dos requests de workers concurrentes permitido
por igual; el orden metodológico es parte de cada alternativa. RAW privado,
sólo artefactos públicos al compartir y reviewer posterior sin herramientas.
Normas pendientes, sin aprobación delegada al modelo ni Q autoasignada.

Este corte implementa y valida: schema/compilador exacto de 12 celdas R1 con
IDs nuevos; paquete común real de fuentes originales, herramientas, prompts,
entregables y rúbrica pública sin valores resueltos; verificación completa de
bytes; chequeo estructural de entregas sin ejecutar código participante ni
puntuar calidad; binding prospectivo que rechaza metadata/runtime distintos.
No basta con redactar el contrato: se crean y verifican paquetes reales y se
ejercitan CLI, alteraciones y las seis combinaciones caso/alternativa.

No declara disponibles runtimes A/B de cuatro roles: están pendientes, y D117
C aún no tiene el binding nuevo. El compilador no autoriza una ejecución ni
autentica proveedor/custodia/uso/actividad/factura. La implementación de esos
adaptadores y ejecución completa es la siguiente dependencia; no se reduce
la meta a los artefactos de este corte ni se cuentan preparaciones como runs.

## APIs y formato acordados antes de implementar

`scripts/plan_coordinated_development.py`:

- `COORDINATION`: objeto fijo de perfil `leader_two_workers_reviewer_v1`,
  roles `[leader,worker-1,worker-2,reviewer]`, workers 2, concurrencia máxima 2,
  reviewer serial sin tools, sharing público, bootstrap vacío/leader init,
  presupuesto padre único. Exportado para construir inputs sin duplicación.
- Manifest `specorganon.coordinated_development_manifest.v1`, keys exactas:
  `schema,base,coordination,shared_contract,runtime_policy,provider_route,source_freeze_sha256`.
  `base` es manifest DEV v2 validado por su API original; sólo sirve como
  estructura común de casos/modelo/topes/prompts, nunca se ejecuta o relabela
  su calendario solo. Ronda1 únicamente; R2 necesita R1/adaptación congeladas.
- `shared_contract`: refs SHA exactas `delivery,rubric,coordination_prompt`.
  `runtime_policy`: ref SHA; `source_freeze_sha256`: digest hex.
  `provider_route`: keys exactas `provider,api,version,service_tier`, strings
  acotados; provider `openai|google|minimax|fixture`, sin URL/auth/secreto.
  Son declaraciones, no acceso ni autorización.
- `validate_manifest`, `compile_schedule`, `validate_schedule`: reproducción
  exacta; 12 celdas y cuatro bloques R1; prefijo `dev-coord-`, IDs que ligan el
  manifest completo, coordinación, modelo, fuentes, contrato/rúbrica y topes.
  No acepta `agents=solo`, ni flags de autorización o resultados del caller.
- `validate_runtime_binding(schedule,run_id,descriptor)`: esquema cerrado de
  metadata declarada; exige las coordenadas, modelo/route/topes/inputs/roles/
  bootstrap/budget del contrato y perfil `coordinated_development_parent_v1`.
  Devuelve sólo comprobación local de binding; nunca ejecución/telemetría/Q.
  El descriptor exacto y el modelo de schedule se documentan por el worker
  en su handoff antes de integrarlos.

`scripts/prepare_coordinated_development.py`:

- `build_coordinated_round(destination,configuration,contract_dir,source_freeze_sha256)`:
  configuration exacta `schema,seed,model,price_profile,per_run_limits,max_model_requests,cost_limit_micro_usd,provider_route`;
  schema int1; model como configuración D113 sin price digest suministrado.
  contract_dir con `delivery_contract.json,rubric.json,coordination_prompt.md`
  públicos; builder valida sus contratos por la API root. Usa `_capsules`
  original con análisis común, builders sellados de método/análisis y
  capacidades originales sin copiar respuestas/código/informes históricos.
- `verify_coordinated_bundle(bundle)`: recompila calendario, coteja TODOS los
  assets fijados, paquetes/cápsulas y manifiestos originales/derivaciones,
  fuentes/herramientas/precios/contratos, sin ejecutar participante/proveedor.
- CLI `build` y `verify`, no prepare/execute de una celda ni claim.
  Preflight configuration/contratos/fuentes/salidas antes de mkdir. Roots
  nuevos, privados, no symlinks ni solapes con fuentes. Cero efectos ante
  configuración inválida; errores tras creación conservan artefactos fallidos.

Root `scripts/development_delivery_contract.py`:

- `validate_delivery_contract`, `validate_rubric`: schemas públicos cerrados
  ligados a tareas originales D-F/D-E, sus SHA y adaptación argv/JSON D113;
  no cifras resueltas ni soluciones en rúbrica. Cinco dimensiones 0–20 con
  anclas 0/10/20 y evaluación humana independiente pendiente, sin puntuar Q.
- `check_delivery(case_dir,work_dir,contract)`: lectura acotada regular sin
  symlinks; presencia/forma/wordcount/JSON finito/unidades-bases/citas-digests,
  diferenciando ausencia de archivo de valor null motivado. No ejecución de
  analysis.py, no aprobación normativa, verificación semántica o verdad causal.
  Reporta fallos locales y `quality_assessed:false`, nunca aceptación global.
- CLI `validate`/`check`; fixtures de entregas sólo prueban estructura. Los
  valores reales requieren ejecución aislada y revisión sustantiva posterior.

## Fases, ownership y gates

1. Intake read-only en dos agentes nativos conocidos, sin duplicar la pregunta
   nueve fases. Cuota 2026-10-01 10:26 UTC: Codex sin dato fiable; Gemini98%5h/
   96%semana, no utilizado. Máximo cuatro activos incluyendo root, profundidad2.
2. Worker calendario: SOLO nuevo scheduler y su test/handoff.
3. Worker preparador: SOLO nuevo builder/verificador y su test/handoff.
4. Root: delivery checker/test, assets contract/rubric/coordination prompt,
   fixtures/integración, dossier/freezes/recibo/docs. Escritores disjuntos.
   Se acuerdan las APIs y esperan barrera de fuentes estables antes de gates.
5. Freeze antes de gates finales: ambos Python3.11/3.12, Ruff/syntax/diff
   acotados, regresiones pertinentes; sin repetir global/wheel/instalación.
6. Casos originales D-F/D-E y A/B/C: mismos hashes de fuentes/contrato/rúbrica,
   modos originales distintos, init vacío/roles sólo declarados aquí; CLI
   build/verify/check reales, tamper/solape/mixed solo-quartet/R2 bloqueados.
   Registrar por separado comprobación estructural y capacidades pendientes.
7. Revisor independiente de código/evidencia/coverage, reparación acotada de
   hallazgos, preservar fallos/snapshots/streams, pins live/index/HEAD y commit.

Sin proveedores externos, gasto, campo, reserva, secretos ni autorización
inventada. Calendarios/runtimes/dossiers anteriores, GOAL, protocolo, core y
producción conservan sus bytes. El reloj local no autentica SUM de actividad
remota; telemetría/cache/reasoning/coste y autoridad pendientes siguen siendo
datos faltantes, nunca cero. No se cambia el presupuesto ni el criterio de
parada del protocolo. Próximo: runtimes A/B/C ligados a este contrato,
contabilidad efectiva, rutas autorizadas,12R1→adaptación/freeze→12R2/selección;
después confirmación/custodia/jueces/autoridades/campo y transferencia.
