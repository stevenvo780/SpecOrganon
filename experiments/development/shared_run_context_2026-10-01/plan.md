# D-111 — contexto común y relevos con checkpoint

Plan prospectivo. GOAL y protocolo no se modifican. C1 conserva su alcance
técnico D-107; C2–C5 siguen `No demostrado`. Las 24 celdas de desarrollo no
se ejecutan con esta prueba de controles.

## Cambio y alcance

Crear un runner optativo `scripts/run_managed_team.py`, plan `schema:2`,
con segmentos de líder, especialista o revisor, un solo directorio de corrida,
TokenLedger, sesión sellada y claim local por intento. Conservar el bridge
schema:1. Las solicitudes y herramientas se serializan. Las etiquetas de rol
no autentican identidades ni demuestran calidad multiagente.

El runner se detiene tras cada segmento textual conciliado. Un nuevo proceso
continúa únicamente con el checkpoint vigente; conserva solicitudes, tokens,
costo declarado, herramientas y tiempo activo. La espera pausada se mide aparte.
Una caída activa permanece no reanudable. No se comparte el historial bruto ni
razonamiento privado entre roles; el plan puede seleccionar entregables textuales
previos, identificados y preservados, y el historial propio se reconstruye completo.

## Contrato de implementación

`managed_run_context.RunContext` usa un subdirectorio privado `context/` y
reutiliza el ledger del padre. `create(context_dir, ledger_dir, bindings,
active_limit_seconds, max_tool_calls, roles, journal_roots)` crea estado prepared.
Los bindings y las rutas quedan congelados. `status()` devuelve estado,
checkpoint, cursor, revisión y tiempo acumulado. `begin(expected_checkpoint,
role)` compara checkpoint e inventario bajo lock, marca active durable y obtiene
deadline monotónico con el saldo restante. `require_active()` exige la instancia
que abrió ese segmento y comprueba deadline. `pause(cursor)` y `finish(cursor)`
exigen ledger y herramientas conciliados, fijan inventario y tiempo acumulado.
`abort(reason)` marca indeterminate; nunca libera reservas ni vuelve a prepared.
No se inventa tiempo preciso tras una muerte activa: no hay resume.

Los journals incluidos en checkpoint son requests, responses, receipts,
tool_reservations, tool_receipts, histories, artifacts, ledger y tool_session,
además de work y fuentes fijas. Se rechazan symlinks y cambios/addiciones/borrados
entre pausas. El runner valida schedule, plan, sesión, ejecutable, presupuesto,
claim, recibos y cursor antes de efectos. Antes de count se verifica max_requests;
send sigue precedido por la reserva autoritativa de TokenLedger. Ese límite cuenta
solicitudes Responses, no cada operación HTTP de conteo.

## Ownership

- Contexto y tests del contexto: prototype_checkpoint_supervisor.
- Runner schema:2 y tests de integración: acceptance_gap_priority_0927.
- Plan, dossier, revisión, integración, capturas y freeze: root.
- Revisión independiente del cambio estable: source_gate_review.

No revertir cambios ajenos. No editar GOAL, protocolo, módulos de producción,
historial de D-110 ni pruebas del bridge anterior. No commits desde workers.

## Verificación prevista y detenciones

Pruebas con transporte determinista local y herramientas selladas reales de
fixtures públicas: relevos entre procesos, CAS viejo/concurrente y tampering;
presupuesto agregado de solicitudes/tokens/costo/herramientas/tiempo; tiempo de
espera separado; aislamiento de razonamiento y reconstrucción del historial
propio; caída activa/reserva incierta no reanudable; claim validado antes de
count/send/tool. Compatibilidad focal schema:1, Python 3.11/3.12, Ruff y sintaxis.
Conservar fallos y sus fuentes; corregir por evidencia, sin suites globales ni
reconstrucción del wheel. Fijar fuente antes de la captura final.

No llamadas pagadas, generación cloud, credenciales, material reservado real,
evaluadores humanos, aprobación normativa, campo ni publicación externa.
Cuota consultada 2026-10-01T00:45:42.358Z: Codex sin lectura válida; Gemini 98%
restante en ventanas consultadas. Se reutilizan agentes nativos; no se afirma
una identidad de modelo o esfuerzo autenticada de esos agentes.
