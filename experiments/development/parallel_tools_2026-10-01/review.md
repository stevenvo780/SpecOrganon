# Revisión independiente D115

Revisión read-only de código, pruebas y evidencia final. No ejecuté proveedores,
modelos, herramientas del caso ni nuevas pruebas; mis verificaciones posteriores
leyeron bytes y recibos existentes. Freeze revisado:
`9a6c4d83b00efb753622bd0398f9f134317c3370`.

## Hallazgos y cierre

**Sin P1/P2 abierto en el alcance mecánico revisado.** Antes del freeze señalé
tres P2 y comprobé sus cierres:

1. `c_parallel_tools.py` podía dejar un merge aparentemente publicado si fallaba
   `RunContext.finish`. Ahora `merge/.pending.json` sigue en el journal y el motor
   crea `publication.json` fuera del journal sólo después del cierre. El negativo
   de `tests/test_c_parallel_tools.py` inyecta el fallo: no hay marcador público.
2. Una configuración escalar inválida podía consumir la ruta de preparación tras
   crear el árbol de ramas. El wrapper llama al validador puro antes de crearla;
   el negativo exige que la ruta permanezca libre.
3. La API genérica permitía `merge=None` y aun así terminaba/publicaba. En
   `managed_parallel_tools.py:400-403` ahora exige callback antes de comenzar el
   contexto o adquirir claim; `:499-509` lo ejecuta antes de finish/publicación.
   El negativo `tests/test_managed_parallel_tools.py:396-407` comprueba estado
   preparado, cero requests/count/send, cero reservas y ningún claim.

El parche final `managed_parallel_tools.py:245-258,447-474` liga request,
respuesta RAW, recibo y ledger settled antes de efectos locales. El guard
activo comprueba SHA de historias privadas contra los cursores durables
(`:421-424`). Los negativos alteran RAW+recibo y una historia durante send y
bloquean antes de reservar herramienta. La reconstrucción de `_audit` liga
historia, operaciones y artefactos a recibos (`:261-340`); el broker reserva un
ordinal durable y coteja claim, delegación, cap y streams antes de devolver el
resultado (`parallel_tool_broker.py:421-720`). No observé una vía adicional de
publicación o efecto que eluda esas guardas dentro de los límites declarados.

## Evidencia comprobada

- `source_freeze.json`: 34/34 pines de tamaño/SHA iguales a Git HEAD y al árbol
  actual. `baseline_pins.json`: 38/38 iguales, incluidos GOAL, protocolo, core,
  módulos de producción, casos y wheel. Los dos reportes `checks/final311` y
  `checks/final312` conservan 41/41 copias de fuentes iguales a los bytes
  actuales y `sources_before == sources_after`. Sus streams registran 272
  pruebas aprobadas por intérprete, Ruff, compilación y `git diff --check`
  con salida 0; no repetí la suite.
- Reabrí seis directorios físicos distintos de `verified_traces.json`, sin contar
  alias `current`: HTTP D-F/D-E y CLI D-F sintéticos en Python 3.11 y 3.12.
  En cada uno cotejé SHA de estado, recibo, marcador y traza; ledger con siete
  requests settled y 91 tokens **reportados por la fixture**, cuatro reservas y
  cuatro recibos de herramienta. Los tres pares de send por turno se solapan;
  el reviewer comienza después, no recibe `SYNTHETIC-PRIVATE:` ni tools.
- Los seis originales base conservan su SHA. Cada recibo de merge registra
  revisiones de P1 y P2; el estado nuevo tiene ambos en versión 2, N/E/R/V
  stale, N pending y fases iguales al original. Los dos reportes reunidos
  coinciden con sus SHA. Esto prueba replay estructural de la fixture, no soporte
  empírico de esos nodos.
- `archives/runtimes.tar.gz`: SHA256
  `180b527eacdc2137b55cbb658bf2c0c6d714b722b5d1d950e91a7f785c39e2e1`,
  4.352.826 bytes. Reabrí **12.671/12.671** miembros regulares de diez raíces;
  cada tamaño, SHA y modo coincide con `runtime_manifest.json` y con el archivo
  regular original. El tar contiene sólo esos miembros regulares. Los 9.087
  directorios/enlaces del manifiesto son metadatos; no seguí sus destinos.

Los negativos exploratorios anteriores permanecen identificados: el primer
gate del engine falló por un deadline de fixture antes del callback, y
`integration_01` tuvo dos expectativas con ruta equivocada y un cupo de fixture
agotado. Sus resultados no se presentan como aprobados retrospectivos. Las
pruebas finales usan fuentes congeladas; las raíces tempranas con pytest por
defecto y el negativo compuesto `engine_07` no están completos en este tar;
hay fuentes, streams y recibos separados para ellos. El tar no es una imagen
restaurable de sesión.

## Veredicto y límites

El objetivo mecánico D115 queda respaldado para **ramas privadas sintéticas,
herramientas selladas, presupuesto común, pausa/CAS y merge serial del core**.
Se conserva C1 técnico D107; C2–C5 siguen **No demostrado** y se ejecutaron
**0/24 celdas formales**. No se autenticaron identidad, versión, esfuerzo,
usage o factura de modelos; no hubo API pagada, Q, juicio humano, aprobación
normativa, custodia externa ni campo. El análisis de métricas D113 no está
integrado en esta rama C. La frontera local no garantiza aislamiento frente a
procesos del mismo UID, ni cancelación remota o atomicidad universal ante
carreras posteriores al último cotejo.
