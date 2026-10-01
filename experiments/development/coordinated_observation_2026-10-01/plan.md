# D121 · Observación prospectiva de una ejecución coordinada

## Objetivo

Base D120: `f05bb9ca00914ac5b17b2e05c95d726522bb0a2b`. GOAL íntegro releído.
Cerrar el hueco de liberación→entrega y duración de conteos mediante una capa
optativa nueva. La ejecución sigue usando el engine y controles originales
D119; D120 concilia su resultado final. Fuentes/dossiers históricos, GOAL,
protocolo, casos, core y wheel permanecen intactos. No hay permiso de gasto,
proveedor remoto o campo otorgado por este plan.

## Alternativas

1. Reconstruir W retrospectivamente desde el lease o archivos: se rechaza;
   no contiene una liberación observada ni los conteos completos.
2. Añadir eventos al engine D119: se descarta en esta unidad para conservar
   su cierre histórico. Un cambio futuro tendría otro freeze y revisión.
3. Observador separado con journal durable y wrapper del caller: elegido.
   El transporte y una envoltura por instancia del método broker.invoke
   registran intervalos, delegando exactamente una vez a la implementación
   original. No se reemplazan clases, módulos ni funciones globales.

## Contrato de módulos y ownership

- Worker: `scripts/coordinated_observation_journal.py` y
  `tests/test_coordinated_observation_journal.py`. Journal, clocks, locks,
  persistencia y reconciliación de sus eventos.
- Root: `scripts/observed_coordinated_runtime.py`, sus pruebas y helpers del
  dossier. Wrapper, vínculo nativo, transportes e informe final.
- Luna: inventario de las interfaces existentes, read-only.
- Revisor: sólo `review/` del dossier, resto read-only.

No escritor modifica archivos de otro. Máximo cuatro agentes incluyendo root.

## API del journal fijada antes de implementar

`ObservationJournal.create(directory, binding)` crea directorio privado nuevo
y registra release. `ObservationJournal(directory)` reabre sin crear faltantes.
`driver_lock()` es EXCL no bloqueante sobre un archivo distinto del lock de
eventos: quien conduce el paso lo sostiene, pero callbacks sólo bloquean el
lock de eventos. Ninguna lectura del runtime se hace sosteniendo éste.

- `begin_step(expected_checkpoint, expected_calls)` → token opaco. Cada call
  contiene `role`, `request_id`, `request_sha256`, `count_payload_sha256`,
  `send_payload_sha256`. Marca active; un active incierto no se reanuda.
- `begin_operation(token, kind, role, request_id, payload_sha256)` → op_id.
  `kind` es count_input/send/tool; tool usa digest de call_id/name/arguments.
  Exige identidad prevista, una operación de cada tipo por request, count
  terminado antes de send y send terminado antes de tool. No copia payload.
- `end_operation(token, op_id, *, result_sha256, input_tokens=None,
  error=None)` registra fin. `error` sólo categoría fija, nunca mensaje.
  Un callback después de close devuelve false y NO escribe.
- `end_step(token, next_checkpoint, native_state)` acepta paused/completed,
  exige count/send completos. Completed es terminal para pasos posteriores.
- `fail_step(token)` conserva starts sin end y revoca el token; estado uncertain,
  sin nuevos pasos ni callback tardía que reescriba ese cierre.
- `finish(measurement_sha256)` sólo tras último paso completed y todas las
  operaciones completas; registra delivery y retorna `report()`.
- `report()` relee/coteja cadena y tipos; publica eventos sanitizados y
  métricas locales, nunca prueba guard nativo o procedencia por sí solo.

Binding cerrado: run_dir, run_id, plan_sha256, schedule_sha256,
initial_checkpoint_sha256 y observer_source_digests. El wrapper verifica
estos campos contra el runtime, source bytes actuales y resultados D120.

## Reloj, métricas e invariantes

Cada evento tiene seq/tipo, wall_ns y monotonic_ns enteros, boot SHA256 y
prev_sha256; cadena comprobada sin autoría externa. Clock Linux actual:
hash del boot_id, nunca su contenido crudo. Boot debe coincidir durante toda
la sesión. `time.get_clock_info('monotonic')` se registra de forma explícita.
W se calcula como elapsed monotónico en el mismo boot desde release hasta
delivery, e incluye pausas, I/O y observación. Wall timestamps/delta se
conservan por separado; ajustes de wall no alteran elapsed monotónico.

Se calculan sumas e intervalos unidos por tipo y total, por rol cuando aplica;
concurrencia no se convierte en W más corto por sumar tiempos incorrectos.
Son intervalos de llamadas observadas en el host, no CPU/remoto autenticado.
Host tool incluye overhead del broker; sandbox D119 es subconjunto separado.
La diferencia W−unión corresponde a tiempo local fuera de esos callbacks;
no se rotula como tiempo humano o CPU. H, cómputo remoto y costes de personas/
evaluación/factura permanecen faltantes.

Liberación sólo desde runtime preparado, cursor0 y sin requests/tools. Se
rechaza anexar tiempos a un run histórico completed. Se predicen IDs con
turn global por rol y se comprueban payloads exactos transformados por _batch:
count elimina max_output_tokens/service_tier, send añade store/stream false.
Timeout original no se amplía por persistencia. Cada efecto se delega una vez.

Una única adquisición de run lock por snapshot/check nativo; el driver lock
serializa wrappers entre procesos. No locks anidados sobre el mismo inode ni
orden eventos→run. Direct callers sin observador se detectan como huecos de
cobertura; no se afirma impedir un escritor hostil del mismo UID.

Final: D120 native snapshot/guard/replay/publicación + conjuntos exactos de
count/send y tools por request/rol/digests/resultados; count=ledger input;
response SHA concordante; intervalos send observados contenidos en receipts
nativos del mismo paso. Tool call/reserva/receipt coinciden y se conservan
sandbox/host separados. Todo intervalo dentro de release/delivery, sin tipos
bool como números, ns regresivos, duplicados, faltantes o eventos posteriores.
Cadena+hash local no autentican custodia, provider usage, modelo o esfuerzo.

## Gates y parada

1. Tests negativos/positivos de cadena, reloj, locks, BOOT distinto, ausencia,
   duplicados, callback tardía, fallo activo, identidades y cierre.
2. Wrapper: predicción de IDs/payloads, timeout no ampliado, una delegación,
   error sanitizado, no release retrospectivo, cobertura final sin faltantes.
3. Python3.11/3.12, Ruff/sintaxis/diff proporcionales sobre archivos nuevos.
4. Seis runtimes NUEVOS de fixture (A/B/C × D-E por intérprete), CLI release/
   step/report real, HTTP loopback y herramientas originales. Nada de R1 real,
   Q o nueva réplica experimental; mismos controles para cada arquitectura.
   No se repite suite global ni los doce runs históricos D119.
5. Freeze previo a gates finales; conservar errores/fuentes/streams; verificar
   D120/D119 y fuentes originales antes/después, revisión independiente.

Unidad finita: journal, wrapper y seis integraciones mecánicas. Después faltará
ruta/modelo/esfuerzo/uso/precios verificables y autorización para las12R1,
adaptación/freeze/12R2/selección, confirmación independiente, campo causal y
transferencia. C1 técnico vigente, C2–C5 No demostrado y0/24 formales.
