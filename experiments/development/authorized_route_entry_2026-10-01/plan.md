# D123 — entrada Responses controlada y lectura de desenlaces rechazados

Registro previo sobre `cd97b23c979f30d9e451f9064e70e334224e7143` (D122).
GOAL leído íntegramente; turno anterior fue progreso verificable. C1 técnico
D107; C2–C5 No demostrado; 0/24 formales. No hay autorización de gasto.

## Propósito y alcance

Cerrar el bloqueo local de entrada para un transporte OpenAI real conservando
los guards/budget/claim/observación originales. Hacer visible el uso/coste
declarado de respuestas rechazadas, especialmente `incomplete`, sin inventar
una entrega exitosa ni reparar/liquidar/reliberar el ledger indeterminado.
No se ejecutarán proveedores reales, no se leerán credenciales del operador,
no se abrirá reserva/campo y no se modificarán fuentes D118–D122 selladas.

La comparación metodológica, varios modelos/familias/esfuerzos, rondas y
evaluación independiente siguen pendientes de resultados reales. Los ensayos
de esta unidad verifican el transporte y controles locales, no Q o impacto.

## Diseño y ownership

- Root: `scripts/authorized_coordinated_runtime.py`, su test específico,
  dossier y docs activos. CLI preflight/step/outcomes sobre runs nuevos del
  preparador original. Preflight no lee clave ni construye transporte.
- Worker nativo: `scripts/provider_outcome_accounting.py` y
  `tests/test_provider_outcome_accounting.py`, exclusivamente. API de lectura
  bajo el lock nativo y guard, incluyendo estados indeterminados. Uso validado
  y coste declarado se muestran separados de reservas/settlements nativos.
- Luna explorer: lectura acotada de superficies de fallo/lectura y fixtures;
  no escritura ni proveedor. Su lectura se coteja al implementar.
- Revisor independiente: sólo `review/` de este dossier; verifica negativa de
  permisos/ruta/binding, efectos originales, contabilidad y claims de alcance.

Máximo cuatro ramas contando root, profundidad dos, ownership disjunto.
Nadie revierte cambios ajenos; escritores de docs sólo root.

## Contrato de la entrada

1. Plan/bundle/schedule/contratos/fuentes/intérprete y checkpoint se cotejan
   mediante el guard original antes de efectos. Se requiere journal D121
   liberado correctamente. No parchear módulos ni sustituir guards.
2. Step real exige flag explícito de gasto y declaración privada del operador
   ligada exactamente a run/path/plan/schedule/observación/route/model/effort,
   límites y digests del controlador. Esta declaración local no autentica
   identidad/autoridad humana ni es por sí sola autorización de esta sesión.
   No generar una declaración aprobada a partir de una plantilla.
3. Route real limitada a OpenAI Responses v1/default y origen HTTPS oficial
   fijo; no URL configurable, redirecciones ni autenticación en argv/artifacts.
   Cargar `OPENAI_API_KEY` sólo tras todos los gates y antes del envío aprobado.
   Errores allowlist; no claves, headers o texto de excepciones en salida.
4. Perfil de prueba HTTP sólo loopback, provider fixture declarado y token
   público sintético, separado de step real. Nunca aceptar OpenAI como fixture.
5. Un proxy de protocolo conserva payload exacto count/send, fija timeout
   finito ≤90 segundos por operación y ≤deadline nativo, sin mutar adapters.
   Cotejar declaración/digests antes de cada operación sin tomar run lock en
   threads HTTP. El guard activo original permanece vigente.
6. No retry automático. Fallo/timeout/incomplete/mismatch conserva respuesta
   y reserva cuando el nativo lo haga; estado indeterminate no reejecuta.
   Reporte de desenlace es de lectura, no cambia lifecycle, claim, historia,
   publicación, budget o observación. No reescribir respuesta como completed.

## Contabilidad de desenlaces

- Cotejar request SHA, response SHA/identidad/estado, counted input, maxoutput,
  usage entero input+output=total y detalles/cache/razonamiento una sola vez.
- Reutilizar semántica de precios original; residual input al máximo declarado.
  Uso o identidad inválidos/desconocidos quedan nulos con motivo, no cero.
- Coste derivado de uso reportado y compromiso preventivo del ledger son
  columnas alternativas: no sumar el uso de una reserva indeterminada otra vez
  al compromiso preventivo. No llamarlos factura ni costo completo.
- API pura no afirma guard; CLI/lector nativo puede indicar guard verificado.
  No autenticar snapshot/effort/proveedor/precio sólo por un ID declarado.

## Gates previstos y rechazo

- Tests proporcionales de permisos antes de transporte/env, binding cambiado,
  rutas cruzadas, timeouts/secret markers y contabilidad de cache/incomplete,
  uso inválido, response faltante y reservas retenidas. No tests de documentos.
- Integración real CLI sobre fuentes nuevas del fixture original en ambos
  Python exactos: A/B/C para recorrido completo, más un incomplete observado
  que no publica ni reejecuta y un control de ruta real rechazado sin env/red.
  Conservar comandos/streams/fuentes de intentos negativos y bytes/modes de
  runtimes; no declarar llamadas locales como evidencia del proveedor real.
- Guardia de preservación D122 y baseline antes/después; originalmutable cuatro
  docs sólo avanzan tras capturas, con blobs Git anteriores conservados.
- Ruff/sintaxis/diff; no suite histórica completa ni apertura de datos reservados.
- Revisión independiente y recibo live/índice/HEAD antes de cierre, commit con
  pathspec explícito, sin push. No declarar R1 listo por estos gates.

## Pendientes que esta unidad no puede acreditar

Acceso y elección/autorización del dueño, snapshot/effort efectivo, conteo/uso
e invoice reales, suficiencia de 8192 para high, revisión independiente/Q/H
y costes completos. Después: freeze real, 12 R1, adaptación/freeze, 12 R2,
confirmación N/S/T con factores/ablaciones, campo causal y transferencia real.
GOAL permanece activo e incompleto.
