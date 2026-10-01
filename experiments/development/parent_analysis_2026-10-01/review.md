# Revisión independiente D117

**Dictamen acotado:** no encontré un P1/P2 abierto en el código congelado ni en la evidencia mecánica revisada. D117 demuestra continuidad local desde work vacío hasta líder, dos workers, reviewer y merge con un ledger, contexto y claim. No acredita una celda formal, calidad de modelo ni aceptación metodológica.

## Código y conservación

- Revisé `scripts/parent_analysis_broker.py`, `scripts/managed_parent_analysis.py`, `scripts/c_parent_analysis.py`, el plan y las pruebas focales. El solape físico de run/stages/admission con fuentes queda rechazado antes de crear archivos (`c_parent_analysis.py:110-123`); los caches de fuentes revalidan bytes y candidatos de importación; el merge exige cuatro journals fijados por ruta y SHA, seed, manifiesto, fases y normas pendientes antes de `context.finish` (`managed_parent_analysis.py:418-468,656-663`). Los negativos de solape y callback vacío están en las pruebas conservadas. Estos controles locales no protegen frente a un actor hostil del mismo UID.
- Cotejé `source_freeze.json`: 55/55 rutas únicas coinciden en tamaño y SHA con los bytes actuales y con Git `25f87304794721cd7a1ab68816aeadf91a566410`. Cotejé `baseline_pins.json`: 90/90 rutas únicas coinciden con los bytes actuales y Git `ee26beb4cc7cb8788e130f0b0225f32b57a8cd3e`. Los árboles Git completos de los dossiers D113, D115 y D116 tienen los mismos IDs en ambos commits; GOAL, protocolo y core conservan sus bytes.

## Gates, trazas y archivo

- Los reportes `checks/final311` y `checks/final312` registran 98 pruebas aprobadas cada uno, en 564,41 s y 553,74 s de pytest; Ruff, compilación y `git diff --check` salieron 0. Los 52 pines de fuentes capturados antes y después de cada gate son idénticos y coinciden con los archivos actuales. No repetí las pruebas.
- Las verificaciones por intérprete conservaron tres trazas cada una; `verified_traces.json` concatena exactamente esas seis rutas físicas distintas. En cada run comprobé directamente estado completado, 14 envíos/model requests, 10 herramientas, tres requests y dos herramientas del líder, init en el estado semilla, merge del mismo grafo, reviewer final, un claim y `formal_cell_executed=false`. Los recibos describen tres análisis válidos, uno inválido reparado y dos métricas vigentes por run. Los 182 tokens por run son los reportados por el fixture, sin autenticación de proveedor.
- Reabrí **todos** los miembros de `archives/runtimes.tar.gz` y comparé el manifiesto con los originales mediante `lstat` y lectura de regulares: 13 raíces existentes, 23.985 archivos regulares, 5.682 directorios y 145 symlinks conservados sólo como metadata; 3.568 blobs únicos. Verifiqué pertenencia, SHA, tamaño y modo de cada blob y SHA/tamaño del tar (`cf0a15f817ee35ece3efe438b906c497c066632b6e455afad8e02e6e76a47834`, 10.026.409 bytes). Cero discrepancias. La raíz ausente del primer gate de colección fallido figura explícitamente entre los 14 reportes; los negativos del broker fuera de esas raíces se conservan en `worker_checks`. El tar no es una imagen restaurable de sesión ni contiene una identidad autenticada.

## Límite del dictamen

Estas trazas usan respuestas sintéticas y herramientas locales sobre fuentes públicas D-F/D-E. No prueban proveedor, uso o coste facturado, actividad real dentro del proveedor, nueve fases completas, comparación A/B/C, rúbrica/Q, normas aprobadas, custodia humana o campo. Las celdas formales ejecutadas siguen en **0/24**; C2–C5 permanecen **No demostrado**. La evidencia de C1 técnico procede de su corte previo y no se vuelve a adjudicar aquí.
