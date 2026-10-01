# D119 — padre persistente de prototipos coordinados A/B/C

Base D118 `0f57890b00f236c553cbf24ec6f97fe4fdff8f33`, árbol limpio al intake.
El turno anterior fue progreso: contrato/calendario/bundle/checker reales,
265 pruebas por Python, archivo/revisión/722 pines sellados. GOAL se relee
íntegro y no se reduce. C1 técnico D107 conservado; C2–C5 No demostrado;0/24.

## Hallazgos y decisión antes de implementar

Dos exploradores read-only verifican límites concretos: D117 sólo admite
bootstrap→una delegación→reviewer/merge/finish, no retorno al líder. Broker,
selección, parser y merge están ligados a C/risk y rechazan cambios de fases
incluso si son invalidaciones legítimas. Encadenar preparadores abre otro
ledger/contexto/claim; cambiar C/risk en un prompt tampoco crea un runtime A/B.

Se implementan módulos NUEVOS con continuidad de delegaciones y binding al
calendario/contrato D118. El core original y herramientas previas quedan
intactos. Los cuatro roles persisten durante todo el run; una delegación
contiene uno o dos workers, nunca actores ficticios ni una exigencia artificial
de dos nodos listos. RAW e histories privados; sólo artefactos públicos y
recibos/estado del método van al feedback del líder/reviewer.

No hay scheduler nativo A/B. Se declara la política del adaptador: A ordena
por fase/ID usando readiness local, sin scoring/invalidación de descendientes;
B ordena por fase/ID con cierre de dependencias; C usa risk_plan original y
su desempate. Como decisión de coordinación, A manda un worker por lote y
B/C pueden mandar hasta dos independientes. El máximo permitido común es2;
esa política de selección/orden es parte del tratamiento, no una regla
añadida al kernel. `revise` nativo sigue sin gates de fases anteriores.

El líder realiza init real desde work vacío y luego integra/consulta/revisa/
avanza usando el modo original. Workers sólo revise/review owned y archivos
disjuntos; sin init/approve/advance. Normas permanecen pending: no hay actor
competente autorizado. A conserva su invalidación local y el control negativo
de downstream inseguro; registrar ese resultado no lo transforma en B.
Completar runtime/entrega no afirma aceptar las cuatro fases del prototipo,
ni las nueve fases del toolkit ni resolución real.

## Superficies y APIs de integración

### Kernel — `scripts/coordinated_prototype_kernel.py`

Modo fijado por descriptor; schema/fases/nodos/versiones/grafo validados sin
asumir que un audit A inseguro es corrupción. No acepta normas approved.

- `parse_state(raw:bytes, *, mode:str, case_id:str|None=None)->dict`.
- `validate_initialization(proposal:dict,state_raw:bytes,*,mode:str,case_id:str,proposal_path:Path)->dict`:
  todos pending, init original exacto y dependencia normativa en ingeniería.
- `select_work(state:dict,limit:int=2)->list[dict]`: filas `id,phase,action`;
  action revise/review; casos uno/ninguno, propiedad del adaptador documentada.
- `apply_operations(base_raw:bytes,operations:list[dict],*,mode:str)->bytes`:
  rows `global_ordinal,role,arguments,success`; reproduce sólo operaciones
  exitosas de método con core.run(mode), never approve. Sin cambiar core.
- `merge_operations(base_raw:bytes,branches:list[dict],*,mode:str)->bytes`:
  cada branch `task_id,owned_node_ids,state_raw,operations`; replay individual
  igual a bytes/semántica observada, después replay global por ordinal; fases
  e invalidaciones deben igualar el replay, no el snapshot de init.

### Broker — `scripts/coordinated_prototype_broker.py`

Controles de lectura/escritura/sandbox/análisis y journaling reales; sin
reutilizar validators risk-only como si fueran genéricos. Puede componer las
primitivas anteriores sin mutar sus globals o permitir metrics participant.

- `prepare_broker(run_dir:Path,case_dir:Path,inputs_dir:Path,*,mode:str)->dict`:
  binding `path,sha256`; leader stage vacío, sources/read-only/tools sellados,
  roots amplias predeterminadas y metadata versionada por delegación.
- `CoordinatedPrototypeBroker(run_dir:Path,binding:dict)`.
- `invoke(task_id,request_id,call,context,guard)` y `verify()/operations()`;
  stream global de tools sin reset, verificación de claim por schedule+run.
- `leader_stage()->Path`; `current_metrics(task_id)->dict|None`.
- `activate_epoch(epoch:int,assignments:list[dict],*,guard)->dict`:
  assignments `task_id,owned_node_ids,owned_files`; uno/dos roles worker-1/2,
  snapshot base de leader, scope inmutable y copies aisladas para esa epoch.
- `merge_epoch(epoch:int,*,guard)->dict`: replay real por kernel y copia
  controlada a work del líder; conflictos de archivos no se silencian;
  métricas de branch no son métricas del work integrado. Recibo durable de
  host transition e inventario antes/después, nunca efectos ocultos al replay.
- `public_state()->dict`: estado/audit original y digest; no RAW.

Workers tienen scope de archivos disjunto: worker-1 analysis.py y auxiliares
propios públicos; worker-2 report.md/sources.json y auxiliares propios. Líder
puede integrar esos entregables por herramientas contadas. Claims/IDs de
tools/requests, ownership, sources, manifests y before/after se revalidan al
reanudar. Crash con intent/reserva/lease incierta bloquea, no resend ciego.

### Engine — `scripts/managed_coordinated_prototype.py`

- `prepare_coordinated_prototype(run_dir:Path,plan:dict,*,admission_root:Path|None=None)->dict`.
- `read_coordinated_prototype_status(run_dir:Path,*,guard=None)->dict`.
- `execute_coordinated_prototype_step(run_dir:Path,transports:dict,*,expected_checkpoint:str,guard=None)->dict`.

Plan cerrado fijado ANTES de IO: schema1, execution_profile
`coordinated_development_parent_v1`, run_id, schedule, descriptor,
case_dir,inputs_dir, runtime model string/effort/price_profile, functions,
role_config (leader/worker-1/worker-2/reviewer: max_output_tokens,max_model_turns),
max_epochs, limits derivados de descriptor, context público, journal_roots y
runtime_source_digests. Engine valida compile/binding y topes, no atributos
de permiso suministrados por caller. Todos usan mismo modelo/esfuerzo.

Estado persistente separado de fases del kernel: runtime_stage,
epoch/assignments, turn counters GLOBAL por rol, histories y artefactos
privados/públicos, lista de delegaciones y merges append-only. Requests IDs
nunca se reutilizan al cambiar epoch. Bootstrap líder→selección→workers
(uno/dos)→replay/merge→feedback líder→siguiente delegación o entrega→reviewer
serial sin tools→checker/finish/publicación. Texto de líder tras init anuncia
continuar/entregar mediante envelope JSON público cerrado, no instrucciones
host arbitrarias. El engine define/entrega ese formato antes de que root
escriba fixtures. Mensajes de coordinación incluyen sólo públicas con SHA.

Un único WaveLedger schema3/RunContext schema2/claim attempt1 por scheduleSHA
+runID; límites y bindings en plan/recibo único durable antes del primer IO.
No expira ni libera claim. Pausas CAS limpias reabren sin reponer saldo;
inflight/reserva/historia/merge inciertos no se repiten. La publicación liga
entregables, gráfico y métricas del análisis readonly final VIGENTE; checker
D118 sólo estructura y reviewer textual no aprueba normas ni puntúa Q.

### Wrapper root — `scripts/coordinated_prototype_runtime.py`

Preflight bundle original verificado, source_freeze/contrato públicos exactos,
calendario/descriptor/arm/mode/caps, outputs disjuntos y no symlinks, config
cerrada común antes de mkdir/claim. Construye inputs comunes/arm y plan API
engine, fuentes nuevas fijadas aparte sin reescribir D118. CLI prepare,
step/status; integración HTTP/CLI local con proveedor fixture y casos originales.
Transports programáticos conservan el mismo contrato de count/send;
ninguna ruta real pagada/autorización/custodia se autentica aquí.

## Fases, ownership y gates

1. Intake dos exploradores read-only, quota2026-10-01 12:00UTC: Codex sin dato
   fiable; Gemini97%5h/96%semana, no usado. Máximo4 activos incluyendo root.
2. Luna sólo baseline125paths unionD11862/103, live/Git verificados; root y
   revisor vuelven a cotejar. No benchmark ni medición coste/identidad.
3. Worker kernel: SÓLO kernel/test/handoff propio. Worker broker: SÓLO broker/
   test/handoff propio. Worker engine: SÓLO engine/test/handoff propio.
   Root wrapper/tests/fixtures/helpers/dossier/docs. No escritores solapados.
   APIs acordadas antes de code; aclaraciones por mensajes internos, sin bus.
4. Barrera de fuentes estables, freeze antes de gates finales, Python3.11/3.12,
   Ruff/syntax/diff acotados; no repetir global/wheel/install D107.
5. Pruebas reales del control: diferencial A/B/C (advance/revise/review),
   ≥2delegaciones por run, upstream habilita downstream, singleton/empty
   selection, un padre/mismo saldo/modelo/caps, ownership, fuentes/claim/replay/
   CAS/restart/caídas, reviewer posterior privado, análisis protegido final
   y entrega estructural. C solapa donde el grafo lo permite; A serial.
   Seis combinaciones D-F/D-E×A/B/C con HTTP y CLI/consultas nuevas, originales
   reales pero respuestas/telemetría sintéticas claramente separadas de Q.
6. Revisor independiente de código/pins/gates/journals/archivo/coverage;
   reparación sólo de hallazgos, preservar fallos/snapshots/streams y commit
   local (sin push). No sustituir entrega real por un manifest de intención.

## Límites que no se borran

R2 no se compila hasta R1+adaptación/freeze. SUM de intervalos de send locales
no es actividad efectiva de agentes/proveedor; count waits/latencia/cache/
reasoning/factura/effort efectivo faltantes no se convierten en cero. Casos,
preparación y herramientas reales con respuestas fixture no son celdas
formales ni Q. Roles del harness no certifican jueces o humanos competentes.
Sin gasto/modelos externos/reserva/intervención campo/secretos. Siguen12R1
reales→adaptación/freeze→12R2/selección, panel/custodia/jueces/autoridades,
banco sellado21, campo causal y transferencia. GOAL/protocolo/core/wheel/
producción/casos/dossiers anteriores conservan sus bytes y scopes históricos.
