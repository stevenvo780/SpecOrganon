# Evidencia D115

## Cronología y fuentes

- Plan escrito antes de la implementación; commit del plan `11b6b73`.
- Revisión encontró y cerró tres P2: publicación antes del cierre, configuración
  escalar inválida que consumía el path de preparación y API con merge ausente.
- El motor añadió cotejo RAW/recibo/ledger antes de cada herramienta y cotejo
  de historia privada contra cursor. Fuente congelada `9a6c4d83b00efb753622bd0398f9f134317c3370`.
- [source_freeze.json](source_freeze.json):34 pines; [baseline_pins.json](baseline_pins.json):38
  pines heredados intactos, sin reescribir el dossier anterior.
- [preservation_check.json](preservation_check.json) verifica esos bytes y la
  ausencia de diferencias en D114 contra su commit final.

## Gates finales

| Python | pytest | Tiempo pytest | Fuentes antes/después | Ruff/compile/diff |
|---|---:|---:|---:|---|
|3.11.15|272 passed|182,65s|41 iguales|exit0|
|3.12.3|272 passed|177,11s|41 iguales|exit0|

Comandos y streams exactos en [final311/report.json](checks/final311/report.json)
y [final312/report.json](checks/final312/report.json). Incluyen los tres archivos
nuevos de pruebas y los diez gates afectados de D114; no se ejecutó una nueva
suite global ni se reconstruyó/instaló el wheel.

## Efectos reales con modelos sintéticos

[verified_traces.json](verified_traces.json) reabre seis corridas **distintas**:
HTTP D-F/D-E sintéticos y CLI D-F sintético, por cada intérprete. No cuenta alias
`current` y no convierte estas corridas en seis modelos o celdas formales.

Cada corrida: dos workers, tres turnos por worker con overlap HTTP observado,
cuatro herramientas selladas reales, reviewer posterior y siete requests
totales. Los91 tokens proceden de usage ficticio, no del conteo auténtico del
proveedor. Un ledger/contexto/claim aplica el cupo conjunto. Pausas/CAS conservan
requests, herramientas, coste declarado y tiempo; el reviewer no recibe
razonamiento privado ni herramientas.

Los drivers revisan P1/P2 en work privado y escriben report.md. El merge
reproduce exactamente las operaciones contra el core original, comprueba las
ramas y crea un estado nuevo: ambos nodos version2, descendientes N/E/R/V
stale, N pending, ninguna fase aceptada. El original permanece byteidéntico.
Los reportes reunidos mantienen task y SHA. `supported` en estas fixtures es
una aserción sintética de control; no es soporte empírico verificado.

Negativos finales comprueban ownership cruzado/normas/init/avance con el driver
sellado, branches aisladas, analysis_readonly sin escritura, cupo global,
claim/delegación/recibos/RAW/historia alterados, duplicados, reserva interrumpida,
reanudación obsoleta y resultados tardíos. Fallar finish después del merge deja
`.pending.json` y ningún publication.json; faltar merge bloquea antes de claim
y count/send. Una publicación fallida después de finish no cambia los journals
congelados ni expone resultados.

## Negativos y reparaciones conservados

- `dossier/root_checks/integration_01`:3 failed/2 passed. Dos expectativas leían
  active_seconds en el nivel incorrecto; el negativo de finish agotó el cupo
  global30s antes de llegar al punto inyectado. Se corrigió el acceso a context
  y el fixture pasó a60s, sin modificar el máximo del runner. Su CLI positivo
  ya ejecutaba herramientas e integración reales.
- `dossier/root_checks/integration_02`:5 passed después de esas reparaciones.
- `worker_checks/engine_01`:51 passed/1 failed; el fixture de deadline2s no
  alcanzaba el callback. Se evitó reparsear AST cuando los SHA/imports siguen
  iguales, manteniendo rehash y validación de closure; el negativo posterior
  sí llega al callback y bloquea todo efecto tardío.
- `worker_checks/engine_02` y siguientes conservan fuentes y streams de cada
  ampliación de replay y cierre de merge obligatorio. `engine_07` revalida
  el claim flat real después de corregir un glob vacuo del negativo.
- `dossier/worker_checks/broker_01`…`06` conservan las versiones de la reserva,
  bloqueo pending, concurrencia, readonly y JSON/streams acotados.
- El primer generador de base comparó listas con orden distinto y falló un
  assert, aunque los38 archivos coincidían. Los siguientes add/commit también
  fallaron y no crearon commit. Se verificó cada pin conservando el orden del
  manifiesto anterior antes del freeze correcto. El stderr de este intento
  quedó en la entrega de tools, no como stream bruto del repositorio; no se
  reconstruye un log presentado como captura original.

## Archivo y límites

[runtime_manifest.json](archives/runtime_manifest.json):12.671 archivos regulares,
4.352.826B comprimidos, SHA
`180b527eacdc2137b55cbb658bf2c0c6d714b722b5d1d950e91a7f785c39e2e1`.
El archivador reabre cada miembro y coteja bytes/SHA/modo con manifiesto y
original. Sólo raíces explícitas de fixtures públicas: captures de root/finales
y receipts de engine. Directorios y enlaces son metadata, nunca targets.
Unitarios tempranos del broker con defaultpytest y el negativo compuesto
engine_07 no forman parte de esas raíces; se preservan fuentes/streams.
No es imagen de runtime ni restauración portátil de sesión.

**C1 técnico D107 vigente; C2–C5 No demostrado;0/24 celdas formales.**
No hubo identidad/versión/esfuerzo/usage/coste/Q de modelos autenticados, API de
pago, juez externo, aprobación humana, custodia reservada, campo o transferencia
final. GOAL/protocolo/producción/wheel/core/casos originales intactos. La rama
C expone el driver de método; integrar el análisis/métricas D113 y un contrato
común para la comparación sigue pendiente. La mecánica no demuestra una
ventaja frente a A/B ni reemplaza esas evaluaciones.
