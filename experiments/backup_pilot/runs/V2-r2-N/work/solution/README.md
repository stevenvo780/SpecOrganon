# Backup verificable — variante V2, con límite de bytes

Implementación para Python 3.12, biblioteca estándar y Linux/POSIX. No necesita
dependencias ni acceso a red. Conserva la interfaz original; `--max-bytes N` es
opcional y acepta un entero no negativo.

Desde `/trial`:

```sh
python3 solution/backup.py create --source DIR --repo REPO --id v1 --max-bytes 1000000
python3 solution/backup.py verify --repo REPO --id v1
python3 solution/backup.py restore --repo REPO --id v1 --dest DEST
python3 solution/backup.py list --repo REPO
```

Un éxito retorna código 0 y un único objeto JSON en stdout. Los resultados son,
respectivamente, `{"id":"v1"}`, `{"id":"v1","valid":true}`,
`{"id":"v1"}` y `{"snapshots":["v1"]}`. Los errores retornan código distinto
de cero, no emiten éxito en stdout y explican el motivo en stderr. Un repositorio
nuevo vacío o inexistente se lista como vacío. Los IDs siguen exactamente
`[A-Za-z0-9][A-Za-z0-9_-]{0,63}` y nunca se sobrescriben.

## Formato, integridad y recuperación

Cada versión es independiente y se almacena en `snapshots/ID.bkp`. Contiene una
cabecera de 16 bytes, un índice JSON ASCII, los bytes de todos los archivos y un
SHA-256 de 32 bytes que cubre cabecera, índice y contenido. El índice almacena ID,
rutas, tipos y tamaños, incluidos todos los directorios vacíos. El repositorio
es autosuficiente y admite cambios, añadidos, eliminaciones y cambios de tipo
entre versiones. No comprime ni deduplica.

`verify` lee y comprueba todo el snapshot, incluidos los límites, las rutas y el
checksum. `list` enumera en orden solamente snapshots íntegros. `restore` valida
antes de preparar el destino y vuelve a validar mientras extrae a un directorio
temporal hermano; publica el árbol completo con un rename. Rechaza destinos
preexistentes no vacíos sin alterar sus bytes. No preserva UID, ACL, tiempos,
permisos originales ni relaciones entre hardlinks.

`create` copia a un archivo privado dentro de `staging`, sincroniza sus datos y
publica con un enlace atómico que no reemplaza IDs existentes. Los lectores y
creadores usan un bloqueo del directorio raíz con `fcntl.flock`; los creadores
se serializan. SIGKILL libera ese bloqueo. La siguiente creación elimina los
temporales `.create-` seguidos de 32 dígitos hexadecimales, antes de calcular el
presupuesto. Se puede repetir el mismo ID si no llegó a publicarse. Si llegó a
publicarse completo, se conserva y se rechaza el ID duplicado.

Todos los componentes de rutas se abren mediante descriptores de directorio y
`O_NOFOLLOW`, incluso antes de un componente `..`. Se rechazan enlaces simbólicos
y archivos especiales en fuente, repositorio, snapshots y destino; se rechaza el
solapamiento fuente/repositorio. La fuente debe permanecer estable durante la
operación. Los bloqueos coordinan las operaciones de esta CLI.

## Contabilidad de `--max-bytes`

Se suma `st_size` de cada entrada de archivo regular en el repositorio: snapshots
íntegros o corruptos y archivos regulares que permanezcan en staging. Los
temporales abandonados reconocidos se eliminan bajo bloqueo exclusivo. Las
entradas ajenas al formato en la raíz o snapshots provocan rechazo.

Toda metadata persistente está dentro de archivos regulares y cuenta: cabecera,
índice con nombres y directorios, contenido y checksum. Los nombres de archivos
solo reflejan IDs que también están almacenados en el índice. No se utilizan
xattrs ni archivos especiales ni archivos de bloqueo persistentes.

Antes de escribir, se calcula exactamente:

```text
tamaño nuevo = 16 + longitud del índice JSON + suma de tamaños de fuente + 32
total final = suma de st_size ya existentes + tamaño nuevo
```

Si el total final excede N, se rechaza sin publicar ni dejar nuevos archivos
regulares. También se comprueba el tamaño realmente escrito antes de publicar.
El temporal y el snapshot comparten brevemente un inode durante la publicación;
el temporal se elimina antes de devolver éxito. El límite se aplica al estado
final, conforme al contrato. Sin `--max-bytes` se mantiene la creación original
sin cuota. Incluso un snapshot vacío requiere espacio para su metadata.

## Pruebas y resultados conservados

Ejecutadas con Python 3.12.15 desde `/trial`:

```sh
python3 solution/test_backup.py > solution/test-results-v2.txt 2>&1
python3 solution/run_examples.py > solution/example-results-v2.txt 2>&1
```

La suite completó 26 pruebas, con 25 aprobadas y una omitida porque el sandbox
impide crear sockets Unix. Se prueban versiones sucesivas exactas, Unicode,
archivos binarios y vacíos, streaming, IDs, solapamiento, enlaces y FIFO,
destinos protegidos, corrupción de cabecera/índice/datos/checksum, truncamiento,
eliminación, publicación concurrente y recuperación real tras SIGKILL.

Las pruebas nuevas comprueban límites exactos con toda metadata, límites
inferiores al espacio ya utilizado, ausencia de crecimiento tras rechazo,
contabilidad de archivos no listados, recuperación de temporales y dos creadores
compitiendo por un presupuesto que solo admite uno. SIGKILL también se prueba
con cuota y reintento con el mismo ID.

Los ejemplos ejercitan tres versiones, rechazo por presupuesto sin cambios,
listado, verificación y restauración exacta después de retirar la fuente. Los
comandos CLI y sus códigos/stdout/stderr quedan en `example-results-v2.txt`;
los resultados individuales de pruebas, en `test-results-v2.txt`. Los scripts
usan directorios temporales debajo de `solution` y eliminan sus datos al terminar.
