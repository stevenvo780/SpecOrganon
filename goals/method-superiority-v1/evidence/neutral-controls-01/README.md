# Dev6: formatos neutrales y evidencia común, candidata en desarrollo

Este bloque añade infraestructura para comparar trabajo libre (N), SDD (S) y
SpecOrganon (T). No ejecuta una comparación ni acredita fiabilidad de dev6. Las
nueve fases y los formatos admitidos por el controlador del motor se conservan.

`files-v1` es un formato explícito del puente para autores de los controles N/S:
archivos y documentos, sin pasos del motor, resultados, revisiones o aprobaciones
inferidas. La ausencia de declaración sigue usando el formato anterior. La tabla
D/G es común y admite notas en prosa; H se evalúa aparte y no entra por definición
en el indicador común. El modelo puede aceptar, rechazar o declarar incertidumbre.

`common_evidence.read_snapshot` captura bytes referenciados por un manifiesto con
hash guardado fuera del autor/revisor. Comprueba archivos regulares, rutas,
digests, namespaces y cadena de checkpoints; enlaza el último checkpoint con
los archivos actuales capturados. Leer un receipt.json no acredita ejecución:
`validate_bound_audit` exige un verificador del transporte/diario host para cada
locator de recibo declarado. Conserva el juicio original. Estos helpers no
devuelven `common_complete`, ni prueban verdad semántica, etapas, independencia
del revisor o F. El operador host sigue siendo parte de la confianza.

El protocolo está en [STRONG_CONTROLS_V1.md](../../development/STRONG_CONTROLS_V1.md).
La primera revisión de diseño rechazó la propuesta y se conserva en
`design-review-01.json`. Las reglas documentadas responden a sus hallazgos; no se
presentan como controladores ya implementados. Siguen pendientes: máquina de
etapas N/S, cronología y revisiones previas, contabilidad efectiva de presupuestos
y tiempo, verificación de recibos integrada, indicador común final y protocolo
estadístico reservado. Después se congelará la versión completa antes de sus
generaciones; no se atribuyen a dev6 los resultados dev4 ni dev5.

## Comprobaciones

Los logs tests-01 a tests-04 conservan comprobaciones intermedias de formatos.
Tests-05 y tests-06 registran 380 passed y tres skipped sobre fuentes intermedias.
La revisión source-review-01 rechazó el helper porque su entrada directa admitía
`schema: 1.0`. Se corrigió sin coerción y se añadieron nueve negativos. Tests-07
registra el conjunto completo corregido: 389 passed y tres pruebas Docker
omitidas porque requieren el experimento explícito de sus imágenes antiguas.
Son pruebas de software, muchas con fixtures; no son casos generados ni pruebas
de superioridad. No se afirma que la suite global histórica del repositorio pase.

Build-01 e installed-01 corresponden a la fuente anterior a la corrección del
tipado; build-02 e installed-02, a la corregida. `probe_installed.py` verifica
importaciones desde esa wheel, bytes de sus 34 módulos iguales a las
fuentes y CLI `--help` con exit0. Esta wheel es una prueba local de empaquetado,
no una versión completa liberada ni un experimento nativo.

`native02-observation-01.json` conserva la observación física de dev4 realizada a
las 04:14:09 UTC del 6 de octubre: nueve intentos cerrados, cuatro completos,
cinco fallidos y el décimo aún pendiente. Se verificaron las 45 fuentes congeladas
y los recibos/puertas del driver original, con cero nuevas llamadas de autor,
revisor o tests. Es un snapshot fechado, no el resultado final.
