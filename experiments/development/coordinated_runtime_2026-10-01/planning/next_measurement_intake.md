# Siguiente unidad: recibos y medición comparables de R1

Intake acotado del subagente nativo `/root/d119_next_measurement_intake`,
modelo solicitado `gpt-6-luna`, esfuerzo high; lectura sin cambios o llamadas
a proveedores. Root revisó referencias y pidió corregir el caller D119:
`dispatch_response` pertenece a otros runners. Este mapa no es un benchmark
de calidad, una autorización ni una ejecución formal.

## Cobertura local y brechas

| Variable | Control existente D119 | Evidencia pendiente |
| --- | --- | --- |
| Tokens | `execute_coordinated_prototype_step` llama `wave._batch`; `_response` coteja recibo, petición, respuesta y ledger liquidado por ID/rol/digests. | Recibos de la ruta real, componentes facturados sin doble conteo, cobertura completa y faltantes explícitos. |
| Coste | WaveLedger conserva reservas/liquidaciones bajo un perfil de precios declarado y un techo global. | Procedencia de tarifa y conciliación con coste real; herramientas/reintentos y revisión humana se registran por separado y después se agregan según el protocolo. |
| Tiempo | RunContext limita un reloj local; timeline vincula rol/turno/request. | Pared W desde liberación hasta entrega, desglose de esperas y herramientas, intervalos de actividad atribuibles y completos, y minutos de intervención humana. |

Referencias: `scripts/managed_coordinated_prototype.py:_response`,
`execute_coordinated_prototype_step`, `_status`;
`scripts/managed_wave_ledger.py:WaveLedger.create/settle/snapshot`;
`docs/protocolo_experimental.md` §5.1 y límites DEV.
Deadline local, pared W y suma de actividad son medidas diferentes.
Intervalos de HTTP de fixture no autentican actividad del proveedor.
Un digest liga bytes locales; no convierte declaraciones en datos externos.

## Trabajo propuesto, todavía sin implementar

1. Definir un recibo de medición que enlace corrida, brazo, rol, request,
   ledger, respuesta y herramientas; separar solicitado, observado y faltante.
2. Capturar límites y duración de operaciones locales con procedencia y
   límites del reloj; distinguir esas observaciones de actividad remota.
3. Verificar cobertura y agregación sin doble conteo, coste calculado y coste
   conciliado separados; cualquier hueco mantiene la comparación pendiente.
4. Conectar una ruta real autorizada y conservar sus recibos, tarifas y
   revisión humana antes de abrir R1. Ningún campo declarativo autoriza gasto.

La autenticidad requiere procedencia verificable apropiada a cada fuente;
no se añade una exigencia de atestación criptográfica remota al protocolo.
C1 técnico D107 permanece cumplido; MCP no se introduce como nueva puerta de
R1. Continúan pendientes uso/coste/actividad real, autorización y presupuesto,
12 R1 → adaptación/freeze → 12 R2, evaluación independiente, reserva/campo y
transferencia. Este intake conserva los requisitos de GOAL.
