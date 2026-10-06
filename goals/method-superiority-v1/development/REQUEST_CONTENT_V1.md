# Desarrollo dev8: contexto lossless compartido

Alcance prospectivo: corregir duplicación observada en el piloto público dev7,
sin alterar ese piloto, inventar éxito, reducir contenido o ampliar presupuestos.
La versión completa sigue sin congelar; T/DG/fiabilidad/reservada/réplica pendientes.

En seis posiciones originales de dev7 el controlador falló antes de la auditoría
D/G al exceder 110000bytes de solicitud. Todas las entregas pasaron sus pruebas
públicas: un dato descriptivo distinto del paquete completo. La historia transmite
reiteradamente texto de archivos/documentos dentro del paquete y de cada captura.

`lossless-package-context-v1` contiene files/documents/history (metadatos, paquetes
íntegros, resultados, capturas y orden originales) en un documento. El codec
`specorganon-content-refs-v1` sustituye únicamente strings grandes repetidos por
null en posiciones explícitas y los incluye una sola vez en content_by_sha256.
Las referencias apuntan a esas posiciones, no a objetos con nombres reservados,
para preservar también diccionarios literales que parezcan referencias. Antes de
usar el formato el host verifica identidad canónica exacta tras reconstrucción.
Si el envelope crece, usa JSON original con marcador explícito plain-json. No se
leen ficheros externos ni se presupone que el modelo disponga de herramientas.

La auditoría mantiene todos sus localizadores, bytes e identidades físicas. Para
JSON ya canónico del host puede transmitir el árbol equivalente, cuya serialización
canónica es exactamente el original; el resto se conserva como texto UTF8 exacto.
Eso permite factorizar strings internos repetidos sin recortar recibos, criterios,
checkpoints, streams o evidencia. Las referencias no acreditan verdad semántica.
No cambian read_snapshot/validate_bound_audit ni las decisiones D/G/H.

Los presupuestos N/S y las nueve fases T permanecen. Los request/prompt se miden
sobre el contenido realmente enviado (110000/128000), no sobre una estimación del
ahorro. Los originales se conservan íntegros y los límites de files/documentos y
streams todavía se aplican al admitir una entrega; referencias no aumentan esos
límites. La nueva identidad de versión, fuente codec en policy y fuentes instaladas
registradas impiden reabrir silenciosamente una campaña anterior.

La prueba offline de solicitudes archivadas debe reconstruir sus seis solicitudes
fallidas usando los mismos criterios/resultados reales y demostrar identidad del
contexto. Esto prueba transporte, no lectura correcta por modelos ni competencia:
requiere revisión independiente, instalación real y nuevo registro prospectivo
antes del siguiente piloto, sin reemplazar ninguno de los seis anteriores.

La prueba hipotética de auditoría N detectó otro duplicado en criterios de la
primera medida e historial operativo. Se conservó ese primer fallo offline y se
agrupó todo controller_context en el mismo índice, preservando partición, binding,
criterios originales y decisiones; ninguna operación histórica se reabrió.
Los tres paquetes hipotéticos N ahora caben y mantienen sus localizadores byte a
byte. Un paquete hipotético no es revisión sustantiva ni evidencia de competencia.
Los casos con poco contenido repetido o historia mayor todavía pueden exceder
los límites estrictos: no se promete admitir cualquier solicitud ni evitar todo
fallo de transporte. Antes de registros nativos se necesita revisión del snapshot
final, con nueva instalación que coincida con sus fuentes.
