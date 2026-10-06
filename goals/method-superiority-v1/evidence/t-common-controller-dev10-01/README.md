# Integración común T dev10 — ingeniería parcial

El candidato `0.2.0rc3.dev10` añade un controlador T con reloj desde antes de
preparar el caso, reservas anteriores al dispatch, capturas completas por
transición y auditoría común independiente de las nueve revisiones del motor.
La recuperación conserva la operación original. Sus capturas incluyen el estado
completo, delivery, progreso, sellos de build, criterios previos y sus ancestros.

La fixture llega a las nueve fases y a la auditoría común dentro de los límites
originales: 40 roles, dos mediciones propias, 54 000 bytes de documentos,
110 000 de petición y 128 000 de entrada nativa. La representación DAG conserva
todos los valores mediante referencias legibles. Cada localizador auditado se
reconstruye y compara con sus bytes originales. Los fallos previos por tamaño se
conservan en `synthetic-before-dedup-*` y `synthetic-cas-*`; no se aumentaron los
límites ni se reinterpretaron esos fallos.

Los controles verifican D/G separados de H, recuperación tras cortes, alteración
de evidencia, trabajo inicial ajeno, reservas y clocks, cambios posteriores al
cierre y mutaciones durante exportación. El cierre interno incluye una captura
anterior al commit del progreso y replay de bookkeeping sobre el ledger original:
compara cada evento semántico y los archivos con la operación medida. Ese replay
no ejecuta código de la entrega ni sustituye pruebas externas.

La suite ampliada tiene 232 pruebas sintéticas aprobadas; los logs registran
cada corte y los seguimientos tras cambios. Los recuentos se solapan y no son
intentos nativos. Ambas imágenes locales contienen los mismos 45 módulos que
el candidato. La imagen de release verificó CLI y 24 herramientas MCP por stdio,
con red deshabilitada y sin credenciales. La otra verificó Codex 0.160.0. Esto
comprueba instalación y componentes, sin invocar modelos dentro de Docker.

La revisión estática independiente de Codex encontró seis problemas en un corte
anterior. Hay correcciones con pruebas para el estado actual al auditar, la
custodia del cierre, el baseline inicial y las entradas mutables de exportación.
El cierre posterior a 6000 s pierde readiness. **Continúan abiertos** el deadline
absoluto compartido a través del transporte/preparación/cleanup y la recuperación
verificada de ciertos fallos nativos cerrados con salida no cero. El código final,
incluidos codec e integración, necesita nueva revisión independiente. La revisión
anterior no constituye aceptación de este corte.

No hay nueva generación nativa ni admisión T, versión completa congelada,
calificación de diez intentos, F externo o comparación reservada. La goal sigue
activa. Los originales dev7/dev8 y cohortes cerradas conservan sus resultados.

Recibos principales: `engineering-receipt.json`, `installed-release-receipt.json`,
`independent-custody-review.json`, fuentes y pins de los cortes revisado e
instalado. `probe_installed.py` reproduce la comprobación local de componentes;
las imágenes deben construirse desde el corte exacto antes de usarlo.
