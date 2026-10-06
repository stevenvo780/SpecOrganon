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
