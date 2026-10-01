# D112 — casos públicos y prototipos en el ejecutor común

Este corte integra preparación de desarrollo A/B/C con el stage, sandbox,
claim, ledger y contexto de D111. **No ejecuta ninguna de las 24 celdas
formales.** La aceptación sigue **1/5 en alcance técnico C1 D107**;
C2–C5 no demostrado. Modelo, esfuerzo, precio y runtime son declaraciones,
no identidad autenticada, factura o imagen certificada.

## Cambios y evidencia

- `scripts/plan_development_round.py`: esquema DEV explícito y reproducción
  exacta de las 12 preparaciones de ronda1 (A/B/C × D-F/D-E × rep1/2).
  Casos, prompts, core, modelo/esfuerzo, precio declarado, orden y topes quedan
  ligados por digest. Ronda2 se rechaza hasta disponer de evidencia de ronda1
  y congelar su adaptación. El inventario completo pendiente sigue siendo24.
- `scripts/prepare_development_round.py`: fija 12 fuentes de Git98a1403 antes
  de crear salida y nuevamente al copiar; paquete D-F con seis inputs
  originales, D-E con tres. Sólo añade case.json; no expone referencias
  ocultas ni reserva real. Builder/prepare CLI probados sin solicitudes.
- `scripts/development_method_tool.py`: ejecutable0500 con bytes exactos del
  core original embebidos. A=sequential, B=graph, C=risk fijados por prompt.
  init/status/revise/review/advance/plan reales; lectura acotada de fuentes
  enumeradas y escritura por bloques de entregables. Estado/propuesta no
  escribibles por esas operaciones. **approve y analyze rechazados.**
- `preflight_assets.py`: routing exclusivo por esquema nuevo; la validación
  confirmatoria permanece estricta y el DEV no usa su gate. Team/bridge
  comprueban precio y topes de costo/solicitudes antes de crear directorios;
  DEV solo permite segmentos de leader porque declara solo.

Plan2063a05 precede gates; enmienda272cd12 evita ejecutar código arbitrario
in-process junto al estado normativo. [Enmienda de bindings](binding_amendment.md)
registra procedencia, límites y reparación de sandbox. Freeze de código
**1c3cbf49f64f5d8b74e696ea2da7b1714955217a**, [pins](source_freeze.json).
Los 38 pins de [baseline](baseline_pins.json) permanecen intactos: GOAL,
protocolo, 24 módulos de producción, wheel y fuentes públicas originales.
No rebuild/install ni suite global nueva.

[Revisión independiente](review.md): sin P1/P2 abierto en este alcance;
pins contra Git/archivos vivos, siete gates y los1650 mappings de archivos
archivados cotejados también contra sus originales retenidos. El
[recibo final](receipt.json) fija dossier y dependencias; excluye sólo su propio
hash. Aceptación del estudio sigue pendiente de todas las condiciones de GOAL.

## Gates finales sobre ese freeze

| Gate | Resultado |
|---|---|
| Python3.11, nuevo adaptador + regresión preflight/team/bridge | 233passed, 163.67s, exit0 |
| Python3.12, nuevo adaptador + relevo común existente | 142passed, 102.17s, exit0 |
| Ruff, compile en memoria3.11/3.12 y diff de código | exit0 |
| CLI build/prepare, configuración fake explícita | exit0, prepared, 0 solicitudes |

Capturas en [gates](gates), con command/duración/exit/streams y 18 copias de
fuente por gate; bytes antes/después idénticos. Hay 19 pruebas de integración:
seis combinaciones de métodos/casos, fuentes alteradas, invocación directa con
precio/costo/request cap distintos, rol no declarado y preservación de datos.
El resto de los nuevos tests incluye108 del planner y14 del driver.

Cada una de las seis trazas positivas usa **un ledger**, dos segmentos de
leader, ocho herramientas y diez respuestas del proveedor **falso**;
150 tokens y150microUSD **sintéticos**. Entrega21KB por tres bloques contados,
reanuda el mismo contexto y termina cursor2 sin nueva cuota. N queda pending
y filosofía bloqueada en estas trazas. Otros tests del core pueden producir
phase_status=accepted: es aceptación mecánica del prototipo, sin aprobación
humana ni autoridad normativa. No hay Q ni análisis científico ejecutado.

## Originales y negativos preservados

1. `unit_method_checks/attempt_01`: expectativa del test omitía review de un
   nodo stale tras revisión de su padre. Fuente y fallo originales guardados;
   se corrige el fixture, conservando el comportamiento del core.
2. `gates/integration_attempt_01`: el fixture inicial proponía nodos supported;
   el wrapper exige todos pending y rechazó init. Se corrigen fixture y guía.
3. `gates/integration_attempt_02`: init intenta fchmod dentro del sandbox,
   EPERM, proposal vacío, ejecución incierta sin retry. Se elimina la llamada
   redundante, manteniendo creación0600 y comprobación por fstat. Se conserva
   fuente negativa y se añade prueba **dentro del sandbox real**. Core y
   reglas de sandbox intactos. attempt03 posterior:19passed exploratorios.

Todos los intentos focales de workers y root están conservados, incluidos los
anteriores al freeze; no se reinterpretan como gates finales.

## Archivos de trazas

`archives/final311_blobs.tar.gz` y `final312_blobs.tar.gz` conservan cada uno
los825 archivos regulares originales de seis fixtures mediante484 blobs
únicos y una tabla path→blob/SHA/bytes. Se reabren todos los blobs para comprobar
bytes exactos. Absolutos de recibos se preservan. Directorios vacíos no se
archivan, entradas no regulares sólo metadata; **no es imagen de restauración
ejecutable de sesión**. No se siguen symlinks. Tamaños5821358/5821548bytes;
hashes y mappings en los JSON correspondientes.

El primer contenedor312 repetía blobs y ocupaba57060203bytes. Sus bytes se
conservan fuera de Git en el path de [archive_history.json](archive_history.json),
y su mapping original en `archives/final312.json`. La deduplicación pierde
cero bytes de archivos, reduce el artefacto final a5821548bytes y no altera
tests, logs, fuentes ni recibos.

## Uso preparatorio

Crear un padre privado y un destino nuevo. La configuración incluida es
**falsa**, con tasas inventadas para probar el ledger; nunca usarla como
precio/modelo real:

```sh
python3 scripts/prepare_development_round.py build \
  experiments/development/development_round_adapter_2026-10-01/fixture_configuration.json \
  /ruta/privada/nuevo-bundle
python3 scripts/prepare_development_round.py prepare \
  /ruta/privada/nuevo-bundle dev-ID-DEL-SCHEDULE /ruta/privada/nuevo-intento
```

El CLI sólo prepara, no ejecuta proveedor ni autoriza gasto. El stage utiliza
development_unsequenced para estas comprobaciones; el orden fijado no equivale
a barrera experimental prospectiva que ya habilite ensayos formales.

## Trabajo pendiente que impide las celdas completas

1. Análisis del participante aislado del estado del método; contrato de
   salida/evaluación sin reparar archivos desde el evaluador.
2. Lectura común de pasajes PDF congelados para D-F y análisis de CSV D-E;
   chunks8192 sobre612KB requieren más de16 llamadas si se lee todo el CSV.
   Los topes no se amplían silenciosamente y los hashes no son cotejo de fuentes.
3. Ejecución realmente paralela de C con presupuesto global; aquí sólo cola
   y tandas potenciales, solicitudes seriales y actor único.
4. Modelo/ruta/telemetría efectivos, autorización y presupuesto; resultados
   reales de ronda1, mejoras de ronda2, 24celdas completas y selección/freeze.
5. Custodia independiente y casos nuevos, jueces/autoridades humanas, ensayo
   confirmatorio y de campo alimentario, transferencia y todos los criterios
   restantes de GOAL. No actividad externa ni publicación en este corte.
