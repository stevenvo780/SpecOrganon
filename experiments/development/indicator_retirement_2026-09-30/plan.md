# D-107 · Retiro explícito de indicadores y enlace de reproducción

Registro prospectivo de desarrollo, 2026-09-30 UTC. Base: commit
`167e4bf2d630e9f4195a1af1623e3b063db909ef`. GOAL y matriz de aceptación
permanecen sin modificaciones. D105 y D106 son evidencia histórica inmutable.

## Problema y alternativas

D105 conserva `i_rows:3` rechazado, sin consumidores actuales. Su sustitución
por dos indicadores escalares conserva el problema y la norma, pero el motor
sigue exigiendo el indicador rechazado en study/specify. Además, la síntesis
del par carece de inferencia y D106 todavía no pertenece a su grafo.

1. Revisar `i_rows` con un único escalar: soportado, pero daría al identificador
   del par el significado de sólo uno de sus componentes.
2. Cambiarlo a synthesis: prohibido por la inmutabilidad del tipo.
3. Borrarlo, ocultarlo o aceptar de nuevo el rechazo: elimina evidencia o da una
   impresión falsa de reparación.
4. **Elegido:** operación general y acotada de retiro de un indicador rechazado,
   sin consumidores actuales, con reemplazos y revisión fijados por versión.
   Se conserva toda la historia y se explicita el estado del retiro.

## Contrato del retiro

- Sólo indicadores; jamás problemas, normas, decisiones, criterios o requisitos.
- API `retire_indicator(path, id, replacements, reason, actor,
  expected_version, expected_review_seq)`, CLI `retire-indicator`, MCP
  `retire_indicator`. replacements es un objeto no vacío de IDs/versiones
  enteras positivas, hasta 32 entradas. Guards obligatorios, sin coerción de bool.
- La versión actual del origen debe tener una última revisión negativa cuyo
  número de secuencia coincide con expected_review_seq. El motivo debe ser
  explícito. Esta acción técnica no autentica identidad humana ni aprueba normas.
  En casos signed, el revisor negativo debe ser distinto de todos los autores
  históricos del indicador. Los autores de retiros también cuentan como autores
  de study para la independencia de su revisión firmada, aun si el retiro caduca.
- El origen no puede estar stale/contested ni tener consumidores actuales,
  incluso consumidores con referencias desactualizadas. Sus ancestros deben
  estar vigentes, sin errores. Su único issue debe ser el rechazo vigente: no
  ocultar errores estructurales propios. Sus problemas y normas deben conservarse entre
  los ancestros actuales de los reemplazos; esta cobertura estructural no prueba
  equivalencia semántica.
- Cada reemplazo es un indicador actual, sin stale/contested/issues, con evidencia
  numérica de la misma métrica/unidad y cadena normativa/protocolo/problema válida.
  No puede depender directa o transitivamente del origen, ser el origen ni estar
  retirado. No se reescriben consumidores ni se resuelven desafíos.
- Evento append-only `indicator_retire` contiene versión del origen, versiones de
  reemplazos, review_seq y motivo. El reducer valida forma/guards/grafo históricos;
  jamás invalida la lectura de toda la historia por el estado vivo de un archivo.
  La vigencia actual se calcula aparte, conservando status/trace legibles.
- El retiro deja de ser efectivo si cambia origen/revisión/reemplazo, aparece un
  consumidor, una contradicción o un error de evidencia/archivo. Origen, rechazo,
  eventos y motivos siguen visibles. Un reemplazo retirado tampoco sirve.
- Gates y next_task omiten sólo retiros efectivos; no cuentan para mínimos de
  indicadores. La instantánea de la fase liga historia y estado del retiro para
  exigir revisión/advance nuevos. Ledgers sin retiros conservan sus snapshots.
  La restauración exacta de un archivo sin ningún evento duradero puede recuperar
  el snapshot anterior y sus reviews/advances: el motor no registra intervalos
  de corrupción que nadie ancla. Los cambios con evento (revisión, desafío,
  consumidor o nueva declaración) sí dejan historia y exigen review vigente.
- El runner no añade acciones de retiro a manifests en esta iteración; el agente
  debe ejecutar la operación explícita CLI/MCP y después continuar el workflow.

## Ownership interno

- prototype_checkpoint_supervisor: engine.py y tests/test_indicator_retirement.py.
- subscription_method_broker_099: cli.py, server.py, runner.py y tests nuevos de
  interfaces/next_task; no escribir engine.py ni tests del primer agente.
- root: plan, instrumentos de caso/probe, artefactos, documentación e integración.
- source_gate_review: revisión independiente read-only después de implementación.
  Máximo root + tres agentes; no bus, proveedores externos ni modelos nuevos.

## Validación previa al caso

Tests sintéticos de ciclo/versiones/revisión/consumidores/negativos/archivo/
desafíos/cobertura/minimums/snapshot y parser/transporte/next_task; Ruff y compile.
Una suite global por cambio de núcleo y regresión firmada existente. Wheel nuevo
con inventario de producción y dos instalaciones externas 3.11/3.12. La evidencia
C1 de D103 permanece ligada a su wheel anterior: no extrapolar al nuevo package.

### Refresco del inventario C1, antes de declarar cobertura del wheel nuevo

Se actualizará únicamente la lista pública de discovery del smoke existente para
admitir retire_indicator. Sus 15 operaciones originales se repetirán una vez en
cada entorno, conservando stdout/stderr y el script ejecutado. Un derivado explícito
del capturador firmado D103 cambiará sólo pin/default de wheel y clasificación:
repetirá los tres tests/seis operaciones firmadas por CLI/MCP con respuestas y
efectos retenidos. Una llamada positiva al auditor de lotes por CLI/MCP con el
mismo input completa las 22 operaciones previas; D107 aporta el retiro número 23.
Se repetirán asimismo los workflows firmados signed_report/signed_observed con
workspace retenido en ambos Python para comprobar fases, firmas y reapertura.
Todos los instrumentos, tests/imports locales y nuevo wheel se fijan antes del
lanzamiento. Un intento por instrumento/intérprete/modo; conservar fallos y no
extrapolar a permisos, identidad humana o custodia externos. Completar cobertura
requiere inspeccionar los efectos y revisión independiente, no sólo exit0.

## Variante Citi y controles prospectivos

Preservar prefix de 52 eventos D105 y todos sus archivos. Nueva variante añade:
3 evidencias documentales byte exactas de receipt D106, código y reporte;
inferencia de reproducción; revisiones de síntesis, opción, comparación, decisión
y requisito (9 puts con guards), y un retiro explícito de i_rows:3 (1 evento).
Receipt/report son documentos; no fabricar una métrica escalar para su contenido.
Conservar flags históricos D105 y expresar la máscara D106 sólo en la evidencia
de reproducción. Normas/decisiones siguen sin aprobación y fases sin aceptar.

Antes de ejecutar, fijar código, wheel, datos, entorno, plan y scripts por hash en
un freeze comprometido. Una ejecución por intérprete/transportes previstos, nuevos
destinos y streams/argv/efectos reales archivados. Controles en copias separadas:
revisión de reemplazo, rechazo, desafío, archivo alterado/eliminado, consumidor
añadido y versión/revisión incorrecta; asegurar ausencia de eventos en rechazo.
Comparar estado/gates/traces CLI frente a MCP y verificar cadenas/prefijo/archivos.
No rerun automático: fallo terminal conservado y reparación con plan/freeze nuevos.

## Interpretación y salida

El retiro es una decisión técnica declarada, no evidencia de equivalencia semántica,
eficacia, aprobación humana o verdad física. Reproducir D106 no vuelve prospectivo
el estudio expuesto ni aporta una implementación independiente. No nuevas corridas
de modelos, Q, intervención alimentaria o reserva final de 24 ensayos. C2–C5 siguen
No demostrados salvo evidencia adicional específica; la meta global sigue activa.
Publicar cambios, pruebas, fallos, límites y pendientes sin inventar porcentaje.
