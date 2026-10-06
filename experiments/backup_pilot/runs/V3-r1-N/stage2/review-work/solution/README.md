# Backup verificable — variante V3

`backup.py` usa Python 3.12 y exclusivamente la biblioteca estándar. La entrega
está destinada a Linux/POSIX: usa `fcntl.flock`, enlaces duros, `fsync` y renombrado
atómico dentro del mismo sistema de archivos. No requiere instalación.

## Interfaz

Desde `/trial`:

```sh
python3 solution/backup.py create --source DIR --repo DIR --id ID
python3 solution/backup.py create --source DIR --repo DIR --id ID --max-bytes N
python3 solution/backup.py verify --repo DIR --id ID
python3 solution/backup.py restore --repo DIR --id ID --dest DIR
python3 solution/backup.py list --repo DIR
```

`--max-bytes` es opcional para conservar la interfaz anterior. `N` debe ser un
entero decimal no negativo. El éxito devuelve código 0 y un único objeto JSON
en stdout, con las claves del contrato. Los errores devuelven código 1, stdout
vacío y un objeto JSON con `error` en stderr. `--help` muestra la ayuda usual.

Los IDs admiten `[A-Za-z0-9][A-Za-z0-9_-]{0,63}` y nunca se sobrescriben. Se conservan
bytes arbitrarios, archivos vacíos, directorios vacíos y nombres Unicode, con
espacios o saltos de línea. Se rechazan symlinks y archivos especiales, incluidos
los componentes de las rutas proporcionadas. Fuente y repositorio no pueden
solaparse. Un destino existente debe ser un directorio vacío.

## Formato e integridad

Cada snapshot es un archivo regular `REPO/snapshots/ID.snap`. Su formato se
mantiene compatible con la entrega anterior: cabecera versionada, contenido de
los archivos, manifiesto JSON, longitud del manifiesto de 8 bytes y SHA-256 de
los bytes anteriores. El manifiesto contiene rutas relativas, tipos, tamaños,
offsets y SHA-256 de cada archivo. También registra los directorios vacíos.
Toda la metadata del árbol se guarda dentro del archivo regular y cuenta en el
límite; no se usan xattrs ni se codifican contenidos en nombres de directorios.

`verify` valida la estructura completa, las rutas y relaciones entre padres e
hijos, las longitudes, todos los contenidos y ambos niveles de checksums.
Rechaza también claves JSON duplicadas y datos no declarados. `list` ordena los
IDs y omite snapshots corruptos o incompletos; `verify` y `restore` rechazan
explícitamente un ID ausente o corrupto. Un repositorio nuevo devuelve una lista
vacía. Los checksums detectan corrupción; no son una firma autenticada frente a
alguien que reescriba coherentemente todos los datos y sus hashes.

## Límite de bytes y recuperación

`create --max-bytes N` suma `st_size` de **todos** los archivos regulares bajo el
repositorio, incluidos archivos adicionales, metadata y snapshots corruptos.
Los enlaces duros con varios nombres se cuentan por cada nombre regular. No se
comprime ni deduplica; el límite se aplica a tamaños lógicos, no a bloques físicos.

Antes de crear se valida el árbol y se eliminan los archivos regulares
`REPO/.pending-*` abandonados por creaciones interrumpidas. Ese prefijo está
reservado para temporales del programa. Bajo un bloqueo exclusivo del directorio
del repositorio se calcula el tamaño existente y se limita cada escritura del
nuevo snapshot, incluida la cabecera, el manifiesto y el footer. Si no cabe, se
elimina su temporal sin añadir bytes permanentes ni modificar snapshots previos.
Un límite inferior a los bytes existentes se rechaza antes de escribir el snapshot.

Las operaciones CLI sobre un mismo repositorio se serializan. El bloqueo vive
en el kernel, no introduce metadata persistente y se libera incluso con SIGKILL.
Esta coordinación cubre procesos de este programa; el repositorio debe estar
en un directorio privado sin modificaciones externas simultáneas.

La publicación usa un enlace duro que no reemplaza un ID existente, después de
completar y sincronizar el archivo. El temporal se elimina y se sincronizan los
directorios antes de devolver éxito. Durante esa publicación puede haber dos
nombres para el mismo archivo; el límite contractual se cumple al finalizar
con éxito. Si SIGKILL ocurre antes de publicar, la siguiente creación recupera
el espacio y puede repetir el mismo ID. Si ocurre después de publicar, queda
un snapshot completo: el ID ya existe y se puede verificar/restaurar. Una
limpieza posterior elimina solo su nombre temporal.

`restore` comprueba todo el snapshot antes de escribir, construye un árbol
temporal junto al destino, comprueba nuevamente los hashes mientras copia y
publica por renombrado atómico. Una corrupción detectada no publica el destino.
Un destino preexistente no vacío se rechaza sin modificar sus bytes. Tras una
interrupción de restore puede quedar un directorio hermano `.backup-restore-*`;
no ocupa el destino y no impide repetir la operación. Se pueden eliminar esos
restos cuando no haya una restauración en curso.

## Ejemplos y pruebas ejecutados

Los comandos reproducibles son:

```sh
cd /trial
python3 solution/examples.py
python3 solution/tests.py > solution/tests-output-v3.txt 2>&1
```

El ejemplo crea un snapshot con límite alcanzable, rechaza un límite inferior
a los bytes existentes y verifica que todos los bytes del repositorio quedaron
intactos. Después elimina la fuente y restaura los bytes y el directorio vacío.
`examples-results-v3.log` conserva los comandos concretos, códigos, stdout,
stderr y comprobaciones del ejemplo.

La batería `tests.py` contiene 22 pruebas y pasó con Python 3.12.15. Comprueba
roundtrips, versiones sucesivas, rutas relativas y Unicode, destinos protegidos,
IDs, solapamiento, symlinks, archivos especiales, corrupción de datos y metadata,
truncado, borrado y metadata malformada. Para el cambio comprueba límites exactos
y un byte inferiores, metadata sin payload, archivos adicionales y corruptos,
rechazos repetidos sin residuos, límites inválidos y creaciones concurrentes.
Interrumpe dos creaciones con SIGKILL mientras copian un archivo de 128 MiB;
verifica el snapshot previo, limpia los temporales mediante un rechazo de límite
y repite correctamente el mismo ID. Comprueba también restos enlazados a un
snapshot ya publicado.

`commands-results-v3.log` conserva cada invocación CLI y su resultado;
`tests-output-v3.txt` conserva los resultados de unittest. Los registros anteriores
se conservan sin modificación. No se han recibido ni utilizado resultados de
evaluación reservada. `CONTRACT.md` y `AGENTS.md` permanecen intactos.
