# D107 · Retiro versionado y reproducción enlazada

Desarrollo del 30 de septiembre de 2026. **Aceptación global: 1/5.** C1 conserva
evidencia en el alcance técnico inventariado; C2–C5 siguen No demostrados.
GOAL y matriz no cambian.

## Cambio

Nueva operación `retire_indicator` por motor/CLI/MCP. Exige un indicador
rechazado, vigente, sin consumidores, revisión y reemplazos fijados por versión.
Guarda origen, rechazo, motivo e historia. Reemplazos necesitan evidencia
numérica tipada y conservación de problemas/normas. La cobertura estructural
no autentica equivalencia semántica. [Contrato](../../../docs/retiro_indicadores.md).

Revisión, rechazo, desafío, archivo inválido o nuevo consumidor pueden invalidar
el retiro. No cuenta para mínimos ni concede aprobación humana. En casos signed,
la revisión negativa excluye autores históricos; los actores del retiro cuentan
para la independencia de study. Replay histórico y archivos vivos se comprueban
por separado: estado y traza siguen legibles tras corrupción. Restaurar bytes
exactos sin evento duradero puede recuperar snapshots/avances previos; el motor
no recuerda intervalos de alteración que nadie registra.

## Registro y preparación

Plan `667a04b`; revisión preventiva y de implementación cierra ocultación de
issues, confusión de replay/archivos, dos P2 de independencia y timeout de hijos.
Los grupos de procesos se terminan al timeout y conservan streams.

Fallo inicial de preparación: capturador trató alias público de uv como archivo
regular. Cero builds/instalaciones ejecutados. Fuente/error intactos; reparación
acotada `a26b15b` anterior al único build corregido. Preparación offline13comandos;
build/instalación corregidos7, todos exit0. Dependencias33/1521archivos originales
intactos; instalado34/1555 por entorno. El build invocó el alias de uv: destino y
bytes comprobados antes/después, sin atestación atómica del exec.
[Alcance](executable_resolution_scope.json).

Fuentes/instrumentos `a071ab8`; freeze **`474ed13`**,432 hashes de archivos vivos
y24módulos, anterior a cuatro lanzamientos. El commit conservó430 de esos432
archivos: el `.gitignore` generado por el build excluyó ese mismo archivo y el
wheel. La verificación final detectó la omisión; ambos se incorporan después,
con sus bytes originales, en la publicación que contiene
[commit_preservation_repair.json](commit_preservation_repair.json). Ningún
experimento se repite ni se reescribe el freeze. Un intento por
instrumento/Python, sin retry.
Wheel137581B SHA256
`63c58a91c3f174d41b8ca8b6ce21122f9aeb8f156005ad59767db4960c9f88e3`:
[package](installed_repaired/specorganon-0.1.0-py3-none-any.whl).

## Ejecuciones reales

| Verificación | Python 3.11.15 | Python 3.12.3 |
|---|---:|---:|
| Exit de sonda de retiro | 0 | 0 |
| Capturas / pares CLI-MCP | 182 / 52 | 182 / 52 |
| Prefijo / eventos finales | 52 / 62 | 52 / 62 |
| Controles de invalidación | 6 | 6 |
| Operaciones instaladas CLI/MCP | 23 / 23 | 23 / 23 |
| signed_report: fases/eventos | 9 / 50 | 9 / 50 |
| signed_observed: fases/eventos | 9 / 51 | 9 / 51 |

C1 combina smoke15, firmadas6, auditor1 y retiro1, con discovery23,
wheel/origins/entrypoints y efectos comprobados. El capturador firmado histórico
se ejecutó desde sus bytes fijados con overrides explícitos de digest del wheel
y clasificación; no se atribuye rerun histórico D103. Smoke conserva resumen y
fuente; otras capturas retienen streams y modelos SDK, sin afirmar framing raw.

Cuatro workflows usan claves sintéticas en memoria. Replay no añade eventos;
controles de firmas, revocaciones y archivos reabren. signed_observed repite
realmente la sonda local LandlockABI9. La evaluación field permanece
`no_demostrado`, aun con nueve fases sintéticas aceptadas.

Suite global del núcleo actual: **2674 passed en287,98s**, sin skips/xfails.
Tests nuevos74 de método y40 de interfaces. Python global3.12 sin MCP omitió13
tests de interfaz; las instalaciones nuevas ejecutaron el transporte real.
Fallos de fixtures/expectativas y streams finales conservados; fuentes de los
primeros tests fallidos no archivadas separadamente. Ruff/compile33 pasan;
archivador final también pasa sus checks. 2560 sigue siendo resultado D102.

## Caso y archivo

[Citi62 publicado](../../../cases/citibike_march2024_reproduced/README.md) copia
nueve archivos del MCP positivo3.12, sin locks. Proyecto/UUID y52eventos heredados.
Añade receipt/código/reporte D106, inferencia y revisiones de cinco descendientes.
`i_rows:3` mantiene contenido/tipo/rechazo y se retira con ambos escalares existentes.
Los flags históricos D105 no se reinterpretan. Normas/decisión siguen sin aprobar,
**cero fases aceptadas**; study/explain conservan el bloqueo previo para los dos
defectos abordados. Guards incorrectos y duplicado rechazan sin escritura.

En copias, revisión idéntica de reemplazo, rechazo, desafío, archivo cambiado/
eliminado y nuevo consumidor invalidan el retiro. Lecturas/trazas permanecen
disponibles; restauración devuelve sólo estado técnico. Cuatro tar/596regulares
(228+228+70+70); seis symlinks de pytest son sólo metadatos. Todos los miembros
se reabrieron. Revisión independiente `/root/source_gate_review` recalcula bytes,
cadenas/prefijos,52pares por entorno,1555archivos por venv,23operaciones,
workflows y publicación. Ningún P1/P2 abierto en ese alcance.
[Revisión atribuida](postrun_review.json) · [Recibo](receipt.json).

Reproducir exige las430 fuentes del commit474ed13, más los dos archivos públicos
omitidos restaurados en esta publicación y verificados contra el freeze; el
commit474ed13 por sí solo no contiene todos los inputs. Usar nuevos destinos:
markers impiden repetir estos intentos. Rutas/entornos son de esta máquina;
otra repetición debe registrar prospectivamente su checkout combinado,
destinos y recibo, y conservar hashes/código/datos. Las comprobaciones que exigen
un HEAD congelado necesitarán ese nuevo registro antes de ejecutar.

## Límites y siguiente

Sin rerun de filas D106, modelos experimentales, Luna nuevo, Q, campo, identidad
humana/custodia externas autenticadas ni reserva24. D106 prueba una máscara del
archivo ya expuesto; no verdad física ni acceso. El motor no verifica semánticamente
claims del receipt. C2–C5 no reciben PASS por funcionamiento técnico.

Siguiente derivación documental propuesta: energía del pan
`(0,297+0,115)/(736/1000)=103/184 kWh/kg`. Sólo explorada en
[next_food_evidence.json](next_food_evidence.json), sin ejecutar ni inventar umbral.
Faltan evaluación final independiente, autoridad/métricas competentes, baseline/
campo y comparaciones de modelos/agentes.
