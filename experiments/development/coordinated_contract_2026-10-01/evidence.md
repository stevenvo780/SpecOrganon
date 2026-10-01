# Evidencia D118

## Decisión prospectiva y fuentes

Plan `4abc46f27977f3e245eef0cbd20ce91da2dee916`; freeze FINAL
`6a3619708eaf6be0d83c8a53cc5cb8869f8a88d2`, digest del archivo de freeze
`6724df13d881e46b08c17213e440a5e231eca16c5541abc283f06ae101f4a044`.
62 fuentes del repositorio y extractor externo fijados. Las 103 rutas de
preservación inventariadas por Luna coinciden con live y D117 `e2f76688`;
root y revisor lo verificaron independientemente. GOAL íntegro y protocolo
no se modifican, ni core, casos, producción, wheel o dossiers anteriores.

La coordinación DEV nueva permite por igual líder, dos workers y reviewer
posterior sin tools, datos públicos compartidos y un saldo padre desde init
real sobre work vacío. Los modos sequential/graph/risk y sus cuatro fases
originales son tratamientos distintos. No se ejecuta/relabela el calendario
solo D112; no se cambia el solo/trío N/S/T del protocolo confirmatorio.

## Gates conjuntos sobre el freeze final

| Gate | Python | Pruebas/controles | Resultado |
| --- | --- | --- | --- |
| [final311](checks/final311/report.json) | 3.11.15 | 265 pruebas en 50.04s | pytest/Ruff/compile/diff exit0; fuentes estables |
| [final312](checks/final312/report.json) | 3.12.3 | 265 pruebas en 47.41s | pytest/Ruff/compile/diff exit0; fuentes estables |
| [integration311](checks/integration311/report.json) | 3.11.15 | diez CLI reales y comprobaciones locales | todos exit0; fuentes estables |
| [integration312](checks/integration312/report.json) | 3.12.3 | diez CLI reales y comprobaciones locales | todos exit0; fuentes estables |

265 = 87 scheduler +39 preparer +31 checker +108 regresiones del planner
anterior. Los gates de tests tienen 63 registros before/after y las CLI 62,
con snapshots del repositorio; el extractor externo se fija sin copiar una
imagen del sistema. No hay skips ni repetición de global2674, wheel o install.
Cada gate conserva intérprete, HEAD, argv, exit, duración y stdout/stderr.

Se prueban recompilación exacta/IDs/roles/topes/modelo/casos, cambios de metadata,
R2 prematura, preflight sin mkdir inválido, solapes/symlinks, inventario cerrado,
tamper de fuentes/precios/tools/políticas/ZIP incluso rehasheado, JSON finito,
unidades/nulos/denominadores, claims acíclicos y citas SHA, palabra límite,
fuente original omitida/sustituida o cambiada durante checker y CLI aislada.
Los controles establecen concordancia local de bytes y forma; no autoridad.

## Preparación CLI con originales, sin celdas de modelo

Cada integración crea un paquete real independiente con 6+3 originales y
38 derivados comunes de todas las 35 páginas PDF. Build y dos verify cotejan
106 archivos; validate verifica contrato/rúbrica. Los 12 IDs nuevos R1
cubren A/B/C×D-F/D-E×dos repeticiones en cuatro bloques, mismas fuentes y
contratos, modo distinto. Doce descriptores concuerdan, manteniendo false
runtime_authenticated/execution_authorized. Tres descriptores incompatibles
y R2 prematura se rechazan.

- Calendario 3.11: `801648a9fc0d97eaca884976378fde3d94640dca65797492ebac5d03f432300e`.
- Calendario 3.12: `66901df09f4ffc01c02e8deae43285cd850a897aba86d832d73a514537b6c0c3`.

Los launchers incorporan el intérprete registrado; ambos paquetes tienen
identidades distintas por esa diferencia legítima. No se convierten en 24
ejecuciones. Los seis check CLI por intérprete reciben fixtures con campos
pendientes/nulos motivados, código de marker que NO se ejecuta y texto sin
hallazgos. Sólo pasan estructura; metric_generation_authenticated,
source_passages_verified, participant_executed, quality_assessed,
normative_approval, formal_cell_executed y causal_impact_assessed son false.
Modelo/ruta/precio son fixture; **requests de modelo0, formales0/24**.
Los [resúmenes](checks/integration311/summary.json) y
[resumen 3.12](checks/integration312/summary.json) son copias byte exactas de
los originals archivados, junto a cada argv/stdout/stderr y paquete completo.

## Negativos e historia conservada

- Workers: scheduler87 por intérprete; preparer39 por intérprete con snapshots
  propios. Son checks históricos previos a la revisión final del checker y
  no sustituyen los gates conjuntos. Handoffs y SHA originales permanecen.
- [delivery01](checks/delivery01/report.json): 30pass/1fail; CLI con `-I`
  no encontraba prepare_development_round. Se añadió scripts/ explícito antes
  del import. [delivery02](checks/delivery02/report.json): 31pass, todos gates0.
  Ambos tienen fuentes exactas y runtimes conservados.
- [source_freeze01](checks/source_freeze01/report.json): el freeze `1d78ee6`
  no se ejecutó; check de whitespace exit2 por una línea vacía EOF del test
  nuevo. Snapshot/freeze/streams conservados y commit histórico accesible.
  Sólo esa línea se elimina antes de freeze FINAL y de los gates conjuntos.
- Los negativos deliberados de tests quedan intactos: CSV/PDF/JSON/código
  cambiado, alias de symlink y FIFO no se normalizan ni borran.

## Archivo completo y límites

[Manifest](archives/runtime_manifest.json): ocho raíces explícitas/ocho recibos,
16.448 regulares como 262 blobs; 1.328 metadata =1210 directorios +114
symlinks +4 FIFO. Symlinks/FIFO sólo lstat/mode/target, nunca se siguen ni
abren streams. Archivo 8.745.453 B SHA
`5af3b0996b19dc89bda178645544a95c07badcb9f0bf7fb998c8389731f04aca`.
Root reabrió/cotejó todos los blobs y originales:
[resultado](checks/archive_verification.json), stdout/stderr/argv conservados.
Los dos roots de tests scheduler están directamente en worker_checks, no
duplicados en el tar. El fallo de estilo sin runtime permanece fuera del tar.
Archivo, metadata y recibos no restauran autorización, claim ni aislamiento.

[Publicación local](checks/publication/report.json): diff/check acotado de
fuentes, contrato y documentos frente a D117 da exit0. El chequeo que incluye
todo el material crudo da exit2 (12.113 líneas diagnósticas retenidas), por
whitespace de textos originales, snapshots previos y negativos. No se corrige
ese material para ocultar la historia ni se anuncia un diff global verde.

El source_freeze_sha256 y coordination_prompt son inputs declarados al builder;
sus bytes se ligan al calendario, sin autenticar custodia ni disponibilidad
de un runtime. La futura admisión debe exigir este freeze/contrato publicado,
no aceptar el binding como permiso. Checker no valida causalidad, verdad de
pasajes, fórmulas/cálculos, completitud o producción auténtica de métricas.
Compartir hash no demuestra resultados; null motivado no significa aprobado.

## Veredicto y continuación

**C1 técnico D107 preservado; C2–C5 No demostrado; 0/24 formales.** Contrato
común/preparación quedan implementados, pero runtimes coordinados A/B,
continuidad/binding C, consumo y suma de actividad auténticos y autorización
siguen pendientes. Después:12R1→adaptación/freeze→12R2/selección, y panel,
reserva/custodia/jueces/autoridades/banco sellado, campo causal y transferencia.
La revisión independiente final y coverage están en [review.md](review.md)
y el recibo final; ninguna prueba de este corte puntúa Q o cierra GOAL.
