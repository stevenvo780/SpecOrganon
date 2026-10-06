# Plan previo al cambio, 2026-10-04

Contrato leído completo; SHA-256:
`8adcc50d4a0b8411195837403c0f8cbc5327e1e3e8da3ac943ec4d708a0019c1`.
Implementación recibida, SHA-256:
`b10e934b4ad2e32de58aa653dee3a15ad3345d9b3f1ca91e8fb07a44833c8261`.

La suite propia se ejecutará primero sobre los bytes recibidos y después sobre
el cambio. Criterio: todas las pruebas locales pasan, ningún éxito falso por
corrupción ni mutación de fuente/destino protegido. El oráculo compara nombres,
directorios y bytes independientemente y suma `lstat().st_size` de todos los
archivos regulares. Cuotas: alta, exacta, un byte menos, inferior a existentes,
payload sin metadata, 0 y valores inválidos; varios snapshots, lock con bytes,
rechazo sin residuos, SIGKILL real y serialización de comandos cooperantes.
Regresión: cuatro interfaces, árboles Unicode/espacios/bytes/vacíos, fuente
ausente al restaurar, ID, solapamientos, symlinks/especiales y corrupción de
cada archivo regular del snapshot. Se conservarán comandos, streams, códigos
de salida y timeouts incluso cuando fallen.

Elección técnica delegada: mantener árbol+manifiesto+sello SHA-256 y medir
exactamente el repo completo antes del rename; limpiar staging abandonado
bajo flock. Frente a estimar sólo payload, esto incluye toda metadata pero
requiere espacio temporal de copia. Sin compresión ni deduplicación.
Validación técnica local finita, sin eficacia de campo, revisión independiente
ni acceso a resultados de evaluación reservada. Los gates quedan pendientes.
