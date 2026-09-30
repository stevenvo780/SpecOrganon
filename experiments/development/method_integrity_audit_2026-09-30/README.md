# D-104 · Integridad de desarrollo y diagnóstico posterior de programas

Plan registrado en `cfcaea4`, banco/auditor congelados en `c9d8744` y
sonda de programas en `85c9c0d`, antes de sus ejecuciones respectivas.
GOAL y la matriz de aceptación permanecen intactos.
**Aceptación actual: 1/5; C1 técnico cumplido, C2–C5 No demostrados.**

## Banco actual instalado

El mismo wheel D-102 `e155d010…` pasó los **21 escenarios originales en
Python 3.11.15 y 3.12.3**, sin fallos, skips o xfails. Se invocó directamente
`tests/test_injection_bank.py::run_case`, fijado a su SHA histórico
`2be3c999…`: seis contradicciones, seis insuficiencias de evidencia, seis
cambios de supuestos y tres normas/decisiones sin aprobación por entorno.
Se comprobaron antes y después los seis inputs, los 24 módulos instalados,
sus orígenes y su igualdad con el wheel y el código actual.

Los [resultados 3.11](bank_311.json) y [3.12](bank_312.json) conservan
clasificación, bloqueos y cabezas de los **42 ledgers**. Los dos archivos
comprimidos conservan 218 archivos regulares, incluidos ledgers, resultados
y streams. La revisión independiente recalculó las 42 cadenas completas.
Las aprobaciones son fixtures sintéticas; no se ejecutó su supuesto test
externo ni se acreditó identidad humana.

**Negativo conservado E06:** `study.ready=true` aun sin evidencia enlazada
al indicador; el rechazo explícito aparece en `specify`. No se redefinió la
puerta a partir de este resultado. El banco es expuesto y de desarrollo;
no sustituye las 21 inyecciones selladas independientes del criterio 2.
El reporte histórico de septiembre 26 no se sobrescribió: tres de sus
seis pines ya diferían del árbol actual.

## Inventario de linaje

El [auditor](../../../scripts/audit_development_indicator_lineage.py)
leyó los casos retenidos bread64 y Citi42 desde el wheel instalado, sin
escribir en ellos. El [JSON](lineage.json) conserva 15 objetivos, 31 pines,
cabezas y versiones, rutas a problema/normas/protocolos y clasificación de
candidatos por coincidencia de métrica/unidad.

| Indicador | Candidatos con métrica y unidad exactas | Límite observado |
| --- | ---: | --- |
| Pan: `i_r_capture`, `i_r_basis`, `i_r_safety`, `i_r_service` | 0 cada uno | Cuatro bundles ancestrales tienen metadata provisional; las 17 cantidades documentales tienen otras métricas/unidades. Normas/decisión pendientes, cuatro umbrales nulos, sin medición de campo. |
| Pan: `i_doc_mass` | 1: `e_piece_mass` | Control documental positivo: 736 g/piece publicado. No demuestra conservación de servicio alimentario o resultado actual. |
| Citi Bike: `i_rows` | 0 | Cinco evidencias son conteos/huecos, mientras el indicador declara fracciones; `e_archive` carece de tipo exacto y queda provisional. Norma/decisión sin aprobar, sin criterio cuantitativo final. |

La coincidencia exacta sólo clasifica metadata. No prueba verdad, población,
derivación, custodia, aprobación ni soporte completo de las compuertas.
Las rutas estructurales existen; ambos casos conservan cero fases aceptadas.
No se considera una futura métrica aún pendiente como un resultado observado.

## SHA contradictorio en tres programas conservados

Se ejecutaron los bytes originales N/S/T de D-099 en tres paquetes nuevos.
Se cambió **exclusivamente el valor SHA de 64 bytes** de
`selection.sample_sha256`, conservando serialización, CSV, filas, unidades
y timestamps. Los 147 originales D-099 se cotejaron antes y después.
Python 3.12.3 se selló por SHA; tres ejecuciones Landlock ABI 9/seccomp,
30 s cada una como techo, inputs de sólo lectura, ningún root escribible,
cero timeout o error de lanzamiento. Las duraciones locales fueron
0,064742 / 0,110045 / 0,067882 s para N/S/T.

| Programa | Exit | Señal observada | Agregados |
| --- | ---: | --- | --- |
| N | 1 | `ValueError` por SHA distinto | No, stdout vacío |
| SDD | 0 | `sample_hash_matches_manifest=false` | Sí, descriptivos |
| T | 1 | `ValueError` por SHA distinto | No, stdout vacío |

El [comparador](programs.json) excluye los tres paquetes de admisión
decisoria y declara integridad no verificada. Son políticas del comparador;
no se atribuyen a los programas como aprobación científica. El contrato
común no exigía salida distinta de cero ni prohibía agregados diagnósticos:
la salida 0 de S con una señal falsa **no demuestra por sí sola incumplimiento**.
Su propia propuesta impide interpretar esos resultados para decidir antes
de resolver la discrepancia. Las magnitudes originales 18/18 permanecen
históricas; esa métrica no evaluaba el comportamiento ante fuente contradictoria.

[programs.tar.gz](programs.tar.gz) conserva 47 archivos regulares:
programas, inputs/copias, mutaciones, revisión AST, metadatos, pins y streams.
El revisor cotejó los 47, cada cambio de una propiedad y los bytes ejecutados
mediante `-c`. No hubo nueva generación, reparación de candidato o repetición
de la condición original. La condición negativa se eligió tras leer el código:
no es ciega, reservada, Q, ranking causal o una de las 24 corridas requeridas.
La [auditoría semántica](semantic_audit.md) registra inferencias, propuestas
normativas y metadata pendiente, incluida trazabilidad propuesta en N y S.

## Reproducción y archivo

Usar un entorno instalado fuera del árbol con este wheel y pytest ya
disponible, inputs originales y rutas nuevas. Los comandos exactos están en
[source_freeze.json](source_freeze.json) y su
[enmienda](source_freeze_amendment.json); cambiar las rutas temporales de
salida no permite cambiar los pines. Los ejecutores rechazan inputs distintos.
Los logs originales y retorno están en `executions/`; tres tar conservan
**265 archivos regulares**, sin enlaces. Los inventarios permiten cotejar
miembros sin extraer a rutas externas. `archive_executed.py` conserva bytes;
`archive_bank_stage_executed.py` es su versión anterior usada para los bancos.

La revisión previa cerró referencias autopinadas que permitían sustituir
escenarios/ledgers, una relectura modificable del sandbox en el padre y
llamadas originales ausentes en la lista permitida. Todos se corrigieron
antes de congelar y ejecutar; no hubo falla de ejecución ni rerun D-104.
`archive_lineage_before_review.py` conserva el auditor inicial no ejecutado.
Ruff y compilación de los tres instrumentos pasaron en ambos Python.
No se repitió la suite global: 2560 passed sigue siendo evidencia D-102.

## Límites y siguiente trabajo

El mismo UID, runtime/bibliotecas del host, inputs leídos por ruta y hashes
locales no aportan custodia externa ni impiden toda sustitución transitoria
durante lecturas. No hubo CLI/MCP nuevo, proveedor, norma humana, intervención
o impacto de campo. C1 conserva su alcance D-103 sobre producción sin cambios.

Siguiente desarrollo: una variante nueva de Citi Bike con fracciones
explícitamente derivadas, numeradores/denominador y controles de invalidación;
evidencia técnica de captura del pan separada de mediciones de servicio aún
pendientes. Para aceptación final siguen pendientes reserva independiente,
fuentes y autoridad competentes, baseline/efecto de campo y comparación
multi-familia/esfuerzo/agentes con repeticiones, ablaciones y calidad verificable.
