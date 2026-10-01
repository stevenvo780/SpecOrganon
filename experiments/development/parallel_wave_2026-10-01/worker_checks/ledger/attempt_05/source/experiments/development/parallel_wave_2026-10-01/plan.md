# D114 — propuestas C en paralelo con un presupuesto común

## Registro prospectivo

Base: `b02539ff43c7792c7656239d799adbb7ee1ea149` (D113), árbol limpio al inicio.
GOAL.md completo y protocolo §2–3/§8 conservados. C1 técnico demostrado;
C2–C5 no demostrados y cero de las 24 corridas de desarrollo formales.
Este corte construye un mecanismo; los transportes de prueba no son modelos.

## Elección y alcance

Añadir hilos al dispatcher actual falla: TokenLedger permite una sola reserva
pendiente. Cambiar sus esquemas 1/2 reinterpretaría recibos anteriores.
Se elige un WaveLedger separado (schema 3), conectado mediante un contexto
schema 2 optativo. Una wave reserva todos sus requests en una escritura
durable antes de enviar cualquiera. Una sola instancia coordinadora administra
ledger, claim, deadline y journals; los workers sólo producen resultados.

El ejecutor `parallel_wave_v1` lanza entre dos y cuatro propuestas textuales
con contextos privados y luego un reviewer serial bajo el mismo presupuesto,
modelo y esfuerzo. Compartir artefactos excluye razonamiento privado. Los
workers no reciben tools ni permiso de editar estado. El wrapper C selecciona
trabajo risk elegible, vuelve a comprobar dependencias y fija el snapshot y
los hechos comunes. Conserva propuestas como artefactos; ni una propuesta ni
el reviewer autorizan normas o convierten afirmaciones en evidencia.

La identidad del experimento es nueva y explícitamente exploratoria. No se
reutiliza un run ID DEV solo, no se modifica la matriz de 24 celdas y no se
reinterpretan los tríos confirmatorios. La integración futura de tools en
branches y publicación de cambios queda pendiente antes de declarar el C
completo para esa matriz. Este corte debe ofrecer ejecución paralela real y
usable, además de pruebas de contabilidad.

## Workflow y ownership

1. Diseño y contratos: root, agentes nativos Codex; acceso directo al repo.
   Cuota Codex sin sonda fiable; agentes nativos disponibles. Gemini informa
   98% en sus ventanas; no se requiere envío externo.
2. `acceptance_gap_priority_0927`: exclusivamente
   `scripts/managed_wave_ledger.py`, `tests/test_managed_wave_ledger.py`.
3. `prototype_checkpoint_supervisor`: exclusivamente
   `scripts/managed_parallel_wave.py`, `tests/test_managed_parallel_wave.py`.
4. Root: selector de contexto, wrapper/CLI C, pruebas de integración y dossier.
5. Barrera: integrar sólo con contratos consistentes; source freeze anterior
   a gates finales. `source_gate_review` revisa en modo read-only y deja veredicto.

Máximo cuatro agentes activos incluyendo root, profundidad dos. Writers
disjuntos; nadie revierte cambios de otros. Una reparación acotada por hallazgo
confirmado precede una nueva ejecución del gate afectado, conservando fallos.

## Contratos

- WaveLedger schema 3 fija modelo/esfuerzo/tarifas y tres topes globales.
  Reserva atómica de 1–4 requests, IDs y SHA de payload; permiso de envío sólo
  en memoria de la reserva original y marca inflight antes del efecto.
  Apertura posterior no concede reenvío. Conciliación individual fuera de
  orden; reservas indeterminadas conservan tokens y coste completos.
- Contexto schema 1 selecciona exclusivamente TokenLedger. Contexto schema 2
  exige `ledger_kind=wave_v1` y schema 3, ambos ligados al checkpoint/bindings.
  Nunca se crea un ledger espejo con saldo ficticio.
- Plan de wave estricto, roles/IDs/ownership disjuntos, datos comunes fijados,
  modelo/effort iguales, zero tools. Claim publicado antes de count/send.
  Rechazar function_call, response incompleta y resultado terminal inválido.
- Daemon threads en el mismo runtime: Queue hacia el host; no escriben journals
  ni reservas. Un deadline monotónico común limita count, send y reviewer.
  El host devuelve fallo al deadline sin esperar callbacks no cooperativos.
  No se promete cancelar consumo remoto: toda incertidumbre conserva reservas;
  resultados tardíos no publican ni concilian. Sin copiar auth entre runtimes.
- Artifacts publicados sólo tras reconciliar toda la wave y guards de fuente,
  base, claim y plazo. Son propuestas; no publicación al core ni avance de fase.

## Definición de terminado y gates

- Reserva de toda la wave anterior al primer envío; evidencia de solapamiento
  de dos sends mediante barrera y HTTP local real, sin proveedor ni gasto.
- C eligibilidad, ownership, mismo contexto factual/modelo/effort, privacidad
  del razonamiento y reviewer sin tools bajo el mismo techo, en D-F y D-E
  sintéticos explícitos. No abrir reserva ni entradas/respuestas escondidas.
- Negativos: insuficiencia de cada techo (cero sends), schema/role/digest
  cruzados, crash antes/después de envío, usage inválida, conciliación fuera
  de orden, deadline/count bloqueado/respuesta tardía, source/base/claim
  cambiado, tools/reviewer inválidos, norm/dependencia no elegible.
- Regresión proporcional de ledger y contexto legacy, bridge/team afectados;
  tests nuevos e integración en Python 3.11 y 3.12, Ruff, compile y diff-check.
  No repetir suite global ni rebuild del wheel de producción sin riesgo nuevo.
- Preservar fuentes fijadas, streams, runtime journals públicos sintéticos,
  negativos y recibos; revisión independiente de evidencia, no sólo tests.

## Límites y siguientes obligaciones

No llamadas a proveedor, gasto, publicación externa, normas humanas ni campo.
Precio declarado y usage de fixtures no autentican identidad, esfuerzo, versión
o factura. Este mecanismo no puntúa Q ni demuestra ventaja de C o del método.
Siguen pendientes el contrato común sin respuestas, C con herramientas por
branches, telemetría/proveedores autorizados, 12 R1 reales, adaptación/freeze
R2 y 12 R2, selección; reserva/custodia/autoridades/jueces, C2 completo, campo
causal y transferencia completa de GOAL.md. No se ajustan sus umbrales.
