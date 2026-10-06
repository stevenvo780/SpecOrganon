# Especificación derivada — V3

Contrato de referencia: `/trial/CONTRACT.md`, sin modificaciones. Esta es la
primera versión funcional; Python 3.12, exclusivamente biblioteca estándar.

## Criterios de aceptación definidos antes de implementar

| ID | Comportamiento observable | Verificación prevista |
| --- | --- | --- |
| C01 | Cuatro comandos contractuales; éxito con código 0 y un solo objeto JSON; errores con código no cero, sin éxito declarado. | CLI, argumentos inválidos y ejemplos conservados. |
| C02 | Copia exacta de archivos binarios, vacíos, nombres Unicode/espacios y todos los directorios, incluidos los vacíos; fuente sin mutaciones. | Comparación de árboles y bytes antes/después. |
| C03 | Repositorio autosuficiente y snapshots sucesivos independientes; listado ordenado de snapshots completos; repo vacío devuelve lista vacía. | Eliminar fuente, restaurar versiones y comparar; listado. |
| C04 | Solo IDs `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`; rechazar ausentes y no sobrescribir IDs existentes. | IDs inválidos, ID duplicado y comparación del snapshot original. |
| C05 | Rechazar symlinks y archivos especiales en fuente, repo, destino y snapshots; no seguirlos, también en componentes de rutas. | Enlaces a archivos/directorios, enlaces rotos, FIFO y socket; centinelas intactos. |
| C06 | Rechazar fuente/repo solapados en ambas direcciones, antes de crear el repo; destino no vacío conserva sus bytes. | Solapamientos, destino protegido y árbol antes/después. |
| C07 | Comprobar todos los bytes y la estructura del snapshot; cualquier archivo regular alterado/eliminado provoca fallo de verify y restore, sin publicar destino. | Alteración, truncado y borrado de datos, manifiesto y sello; entradas extras, metadatos inválidos. |
| C08 | create publica atómicamente; SIGKILL no invalida snapshots anteriores ni incluye temporales en list; un create incompleto se puede repetir con el mismo ID. | Observar copia en curso, parar/matar proceso, comprobar list/verify y repetir create. |
| C09 | Fallos ordinarios no dejan una restauración publicada como correcta ni sobrescriben datos; el contrato permanece intacto. | Inyección de corrupción y fallos de validación; hash del contrato. |

## Decisiones de formato y alcance

- Repo = directorios de snapshots cuyo nombre es el ID, más temporales privados
  `.pending-<UUID hexadecimal>`. No hay dependencia de la fuente original.
- Snapshot = `data/` con el árbol copiado, `manifest.json` con versión, ID,
  directorios, tamaños y SHA-256 de archivos, y `seal` con el SHA-256 de los
  bytes exactos del manifiesto. El sello tiene un formato exacto comprobable.
  No se promete autenticidad frente a un atacante que reescribe todos los hashes.
- La validación exige inventario exacto, esquemas estrictos, rutas relativas
  formadas por componentes seguros, padres declarados y hashes/tamaños coincidentes.
- list comprueba cada candidato y omite snapshots incompletos/corruptos; un tipo
  de archivo inseguro en el repo causa error. verify/restore rechazan el ID corrupto.
- create limpia temporales de create anteriores bajo bloqueo exclusivo del repo;
  no borra snapshots publicados, ni siquiera si están corruptos.
- Operaciones de archivos con descriptores, `O_NOFOLLOW`, tipos comprobados y
  rutas recorridas componente a componente. Plataforma de entrega: Python 3.12
  sobre POSIX/Linux, con `flock`, `fsync` y renombrado atómico en un filesystem local.
- restore verifica antes de copiar, comprueba de nuevo los archivos durante la
  copia y valida el snapshot antes de publicar un temporal hermano del destino.
  También rechaza el solapamiento repo/destino para proteger el propio repositorio.
- Fuente estable según contrato. No se preservan UID, ACL, tiempos ni hardlinks.
  No se requiere recuperación de un corte eléctrico, pero se sincronizan archivos
  y directorios antes y después de la publicación. SIGKILL libera el bloqueo;
  puede quedar un temporal de restore sin publicar, con nombre privado aleatorio.

## Trazabilidad

La matriz de pruebas y los resultados finales se completarán en
`VERIFICATION.md`; el diseño implementado se describirá en `IMPLEMENTATION.md`.
Los criterios C01–C09 son la base de las tareas, no una conclusión posterior.
