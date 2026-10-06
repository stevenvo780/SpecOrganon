# Implementación — V2

Diseño realizado a partir de SPEC.md y PLAN.md, antes de las pruebas externas.

- `checked_path`, `inventory` y `repository` comprueban componentes, tipos de entrada y límites de las rutas. El inventario no sigue enlaces y también inspecciona temporales abandonados.
- `create` guarda objetos independientes en `.incomplete-*`, calcula SHA-256 y tamaños durante la copia, escribe manifiesto y sello, sincroniza archivos/directorios y renombra el directorio al ID final. Los errores ordinarios eliminan solo su temporal; SIGKILL puede dejarlo, sin reservar el ID.
- `load_snapshot` valida el sello del manifiesto, campos y tipos, claves JSON duplicadas, versión/ID, componentes, padres, duplicados y colisiones. Comprueba el conjunto exacto de objetos y todos sus tamaños/hashes. `list` utiliza esta misma comprobación y excluye snapshots incompletos o corruptos.
- `restore` valida todo el snapshot antes de preparar el destino, copia en un temporal hermano, vuelve a contrastar tamaño/hash durante cada copia y renombra únicamente cuando termina. Recomprueba que el destino siga vacío inmediatamente antes de publicar; nunca elimina un destino no vacío.
- El éxito se imprime una vez al finalizar. Los errores tienen código 1 y objeto JSON en stderr; una interrupción por teclado retorna 130. La ayuda de argparse es textual.
- Los objetos no conservan hardlinks ni permisos originales; se crean como archivos ordinarios. El código no abre fuentes durante verify/restore/list.

## Decisiones concretadas durante la implementación

- No se añade bloqueo entre procesos: el contrato no exige operaciones simultáneas sobre el mismo repositorio ni cambios hostiles de rutas. Se comprueba el ID antes de construir y antes de publicar. Las garantías de interrupción se aplican a una operación por repositorio.
- Se utilizan primitivas POSIX (`rename` de directorios, `fsync` de directorios, `O_NOFOLLOW` si está disponible). La entrega se valida en el contenedor Linux con Python 3.12.
- La repetición no necesita borrar temporales abandonados. El espacio de estos temporales se conserva; no se implementa un comando de reparación o limpieza fuera de la interfaz contractual.

La trazabilidad de ejecución y resultados se completa en VERIFICATION.md.

## Adaptación al cambio común: `--max-bytes`

Implementada después de derivar C12–C15 en SPEC.md y ampliar PLAN.md/TASKS.md.
Se conserva el formato 1 y la compatibilidad de las cuatro órdenes iniciales.

- `maximum_bytes` valida la representación decimal no negativa. argparse acepta
  la opción solo para create. `create` también valida el parámetro de su API interna.
- `repository_bytes` inventaría el árbol sin seguir enlaces y suma `st_size` de
  cada archivo regular, incluidos manifiestos, sellos y cualquier archivo regular
  de temporales anteriores. No usa tamaños de bloques, xattrs ni metadata en
  nombres para reducir el conteo; todos los datos de reconstrucción e integridad
  están en manifiestos/sellos regulares.
- Hay un control antes de `mkdir`/`mkdtemp` y otro tras escribir toda la metadata,
  antes de publicar. El control final incluye el nuevo temporal. Renombrarlo no
  modifica la suma. Un rechazo activa la limpieza en `finally`, al igual que un
  error de copia o de conteo. El control inicial no genera ningún archivo.
- Se mantienen temporales abandonados de SIGKILL; sus bytes se incluyen siempre.
  No se introduce un comando de limpieza. Las pruebas de interrupción ejecutan
  create con presupuesto, rechazan un reintento con límite inferior a los bytes
  existentes y luego repiten el mismo ID con presupuesto suficiente.
- Durante la revisión se detectó un caso de C06: un componente inexistente antes
  de `..` podía impedir comprobar un ancestro simbólico de la ruta normalizada.
  `checked_path` comprueba también esa ruta antes de cualquier escritura. Se añade
  una prueba con fuente/repositorio y destino protegidos en ese caso.

La fuente estable y una operación por repositorio siguen siendo las precondiciones.
No se añade compresión, deduplicación ni coordinación entre procesos.
