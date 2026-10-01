# D115 — herramientas en ramas privadas de C

Plan prospectivo, 2026-10-01. Base: D114, commit
`549da8fca9719a0ef84175cf50678be5c83a38aa`.

## Hipótesis y alcance

Un runner optativo con conversaciones independientes puede ejecutar herramientas
reales en dos a cuatro ramas privadas y reunir sus operaciones sobre un único
estado metodológico, conservando presupuesto, tiempo, ownership e invalidación
de dependencias. El perfil textual D114 y las preparaciones DEV solo/trio
mantienen sus contratos. Esta prueba mecánica utiliza transportes sintéticos;
no demuestra la calidad de modelos, una celda formal ni impacto en campo.

## Decisiones antes de implementar

- Perfil `parallel_tool_wave_v2`, plan schema 2 e identidad `tool-wave-…` nueva.
- Un WaveLedger, un RunContext y un claim padre `oneshot(run_dir, run_dir)`.
  El SHA del plan liga una delegación durable a todos los stages privados;
  cada efecto requiere ese claim. No hay claims o presupuestos por rama.
- Dos a cuatro stages físicamente separados. Case/inputs inmutables y work
  privado por task. La delegación fija identidad, ownership, snapshot, bytes
  del ejecutable y perfil de acceso. Los ejecutables revisados se sellan
  mediante `local_replay_sandbox.run_sandboxed`; no se amplían permisos del
  sandbox ni se afirma aislamiento completo frente a procesos del mismo UID.
- El broker host reserva y fsync un ordinal global antes de cada herramienta;
  un recibo terminal liga task/request/call, ordinal global y número local.
  Workspace y analysis_readonly reciben exclusivamente los roots declarados.
  Un efecto incierto permanece pendiente; nunca se repite automáticamente.
- Cada request de modelo tiene ID único por task/turn. Count/reserve/send y
  conciliación reutilizan D114. Todo follow-up comparte los mismos topes.
- La historia completa permanece privada por worker. El reviewer recibe
  solamente artefactos públicos, sin herramientas ni razonamiento privado.
- Un paso termina en checkpoint solamente después de conciliar modelos y
  herramientas. Resume usa CAS; crash activo o reserva pendiente bloquea.
- El driver de rama prohíbe init, advance, approve y mutación directa fuera
  del ownership. Las invalidaciones de descendientes siguen el core original.
- La integración reproduce operaciones exitosas sobre copias del estado base,
  coteja cada estado de rama con su replay y produce un nuevo estado reunido.
  No reemplaza el original. Un marcador durable y recibo final distinguen
  preparación parcial de publicación válida; nunca se publica al fallar.

## Ownership

- acceptance_gap_priority_0927: nuevo broker, delegación y pruebas asociadas.
- prototype_checkpoint_supervisor: runner v2, seam mínimo de `_batch` y sus
  pruebas. Coordina el contrato del broker antes de integrar.
- root: builder del driver, wrapper CLI, replay/integración y pruebas integradas;
  dossier, freeze y documentación de estado.
- source_gate_review: revisión independiente read-only posterior.

Los agentes comparten checkout; no revierten trabajo ajeno. Máximo cuatro
hilos incluyendo root y ownership de archivos disjunto. No se ejecutan APIs
de pago, publicaciones externas ni acciones de campo.

## Gates y criterio de parada

1. Dos workers con al menos dos requests cada uno; herramientas reales cambian
   work separado y el estado integrado conserva ambas operaciones y sus
   invalidaciones. Normas pendientes y ninguna fase nueva aceptada.
2. Overlap de requests, reviewer posterior, privacidad de historias y un
   único presupuesto de requests/tokens/coste declarado/tools/tiempo.
3. Pausa/reanudación sin reinicio; checkpoint obsoleto, reserva incompleta,
   claim/delegación/source/estado alterados, ownership cruzado y timeout
   impiden efectos o publicación. Aislamiento de paths comprobado con tools.
4. Regresión proporcional de v1, RunContext, WaveLedger y conversación legada;
   Ruff y compilación. Python 3.11 y 3.12, conservando intentos negativos.
5. CLI real sobre HTTP local sintético y sandbox real. Revisión independiente
   y freeze de fuentes antes de capturas finales; pines de evidencias exactos.

La reparación se limita a fallos concretos de estos gates. No se reconstruye
el wheel ni se repite la suite global salvo regresión demostrada. Al cerrar
los gates se conserva el alcance mecánico y se avanza al siguiente pendiente
del objetivo; C2–C5 y las 24 celdas siguen sin demostración formal.
