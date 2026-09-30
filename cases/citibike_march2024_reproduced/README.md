# Citi Bike · Reproducción documental y retiro explícito

Variante de desarrollo D107, copiada byte exactamente del caso MCP positivo de
Python 3.12. Conserva el proyecto/UUID y los 52 eventos de
[`citibike_march2024_fractions`](../citibike_march2024_fractions/README.md).
Añade nueve puts con guards y un evento de retiro: **62 eventos**.

`i_rows:3` mantiene tipo, texto, dependencias y rechazo originales. Su retiro
declara como reemplazos `i_rental_fraction:1` e `i_return_fraction:1`.
Las revisiones, rechazos, desafíos, fallos de archivo y nuevos consumidores
pueden invalidar esa declaración; el rechazo e historial siguen visibles.

El grafo añade receipt D106, código y reporte como evidencias documentales
archivadas; una inferencia liga su reproducción a la síntesis del par. D106
verificó las filas de la máscara declarada del archivo público. El motor
comprueba hashes y vínculos; no autentica por sí mismo las declaraciones del
receipt ni el estado físico de las estaciones.

Los racionales y decimales de D105 permanecen iguales. Sus flags históricos
no se reescriben como si D105 hubiera cotejado filas: la comprobación posterior
pertenece a evidencias nuevas. Fechas de la muestra son marzo de 2024;
reproducción exploratoria fue el 30 de septiembre de 2026, con datos ya expuestos.

**Cero fases aceptadas.** `study` y `explain` conservan el bloqueo de la fase
anterior; el retiro y enlace de inferencia eliminan sólo los dos defectos
específicos de D105. Normas y decisiones siguen sin aprobación humana.
No demuestra acceso vivido, cobertura temporal, intervención, causalidad,
comparación independiente de implementación o aceptación global C2/C5.

[`manifest.json`](manifest.json) conserva nueve puts para preparación/replay.
El retiro se ejecuta por separado con CLI/MCP, según
[`retiro_indicadores.md`](../../docs/retiro_indicadores.md). No se copiaron locks.
Un registro de confianza externo debe comprobar UUID, ruta y metadatos de
esta variante antes de registrar firmas reales.

Las capturas, controles, hashes, fallos de preparación y alcance están en el
[dossier D107](../../experiments/development/indicator_retirement_2026-09-30/).
