# Implementación V2, etapa dos

Contrato leído completo; se conserva su archivo original. La adaptación parte
de `backup.py` y de la suite propia existentes en `/trial/solution`.

## AC01–AC14: comportamiento conservado

`directory_path`, `inventory` y `kind` validan componentes y tipos sin resolver
symlinks; `regular_reader` abre archivos con O_NOFOLLOW/O_NONBLOCK y comprueba
su tipo. Los IDs se validan antes de escribir. El repo usa bloqueo exclusivo
`fcntl.flock`. No se escribe en la fuente.

Cada versión es una copia completa con manifiesto JSON canónico que registra
ID, rutas, directorios, tamaños y hashes. `manifest.sha256` contiene 65 bytes
(SHA-256 ASCII más newline). Ambos son archivos regulares. El manifiesto incluye
los nombres de directorios vacíos; el formato no esconde inventario en nombres
de directorios ni usa xattrs o archivos especiales para almacenar metadata.

Create escribe en `.staging/create-*`, sincroniza y publica por rename.
Verify comprueba checksum, estructura, rutas y todo el inventario y contenido.
Restore verifica antes de copiar, vuelve a comprobar hashes durante la copia
y publica un temporal hermano del destino. List verifica los IDs publicados,
ignora temporales y omite snapshots incompletos/corruptos.

## AC15–AC18: adaptación del límite

- `nonnegative_bytes`: valida N como dígitos decimales ASCII no negativos.
  La CLI añade la opción exclusivamente a create. `create_snapshot` conserva
  su API anterior mediante un cuarto parámetro opcional `max_bytes=None`.
- `repository_bytes`: recorre TODO el repo y suma `lstat().st_size` de cada
  archivo regular, incluyendo `.lock`, snapshots previos y staging. El
  inventario rechaza symlinks y tipos especiales. Se cuentan las entradas de
  archivos regulares por ruta, sin deduplicación de inodos.
- Create adquiere el bloqueo, comprueba que el ID no exista y limpia huérfanos.
  Si los bytes previos superan N, falla antes de preparar un nuevo snapshot.
- Después de copiar y escribir metadata se vuelve a contar todo el repo.
  Si el total supera N, `finally` elimina el temporal y sincroniza staging.
  Si cabe, rename solo cambia entradas de directorios y mantiene exactamente
  la suma de archivos comprobada. El bloqueo cubre conteo y publicación.
- N no se guarda como cuota permanente. Es una condición de cada create;
  verify, restore y list conservan su interfaz y garantías.

El límite exige tamaño final; se permite una copia transitoria superior a N.
No hay compresión ni deduplicación. Este diseño acepta límites alcanzables
para el formato y rechaza límites insuficientes sin alterar versiones previas.

## Pruebas y adaptación al entorno

Los siete nuevos casos de límite usan conteo independiente de `st_size`,
subprocess para la CLI, comparación de árboles/bytes y ejecución concurrente.
El caso previo de SIGKILL ahora interrumpe create con límite y reintenta con
límite. Las pruebas anteriores sin N conservan cobertura de compatibilidad.

La ejecución de base encontró EPERM al preparar un socket Unix. Se extrajo
ese caso a una prueba separada con skip explícito solo para PermissionError;
el caso de archivos especiales mantiene pruebas reales de FIFO en fuente,
snapshot y destino. La implementación sigue rechazando sockets por tipo.

Las tareas y criterios se enlazan con pruebas en SPECIFICATION.md/TASKS.md.
VERIFICATION.md y los registros conservan comandos, resultados y limitaciones.
