# Backup verificable — V3

Entrega para Python 3.12 en Linux/POSIX, usando únicamente la biblioteca estándar.
Ejecutar desde `/trial`; las rutas de fuente, repositorio y destino pueden ser
absolutas o relativas. No requiere instalación ni acceso a la red.

## Interfaz

```sh
python3.12 solution/backup.py create --source DIR --repo REPO --id ID --max-bytes N
python3.12 solution/backup.py verify --repo REPO --id ID
python3.12 solution/backup.py restore --repo REPO --id ID --dest DEST
python3.12 solution/backup.py list --repo REPO
```

`--max-bytes` es opcional para conservar la interfaz inicial. Al omitirlo no se
impone un límite; al indicarlo acepta un entero decimal no negativo, incluido 0.
El límite se aplica al repositorio **completo**, no solo al snapshot nuevo.

Un éxito devuelve código 0 y exactamente un objeto JSON en stdout:

| Operación | Resultado |
| --- | --- |
| `create` | `{"id": "ID"}` |
| `verify` | `{"id": "ID", "valid": true}` |
| `restore` | `{"id": "ID"}` |
| `list` | `{"snapshots": ["IDs ordenados"]}` |

Los errores de operación devuelven código 1, un objeto `{"error": "..."}` en
stderr y stdout vacío. Los errores de sintaxis de argumentos usan el diagnóstico
y código 2 de argparse. `list` acepta un repositorio inexistente o vacío y
devuelve `{"snapshots": []}`; los IDs inexistentes fallan en verify y restore.

## Datos, integridad y publicación

El formato privado de esta entrega usa `snapshots/ID/objects/` para los archivos
copiados sin compresión ni deduplicación. Dos archivos regulares contienen toda
la metadata del snapshot: `manifest.json` (formato 2, ID, rutas por componentes,
directorios, tamaños, nombres de objetos y SHA-256) y `manifest.sha256` (hash del
manifiesto, 64 caracteres hexadecimales y un salto de línea). El hash del
manifiesto está en el contenido del archivo, no en su nombre.

Se preservan bytes, nombres Unicode/espacios y directorios vacíos; no se
preservan UID, permisos originales, ACL, tiempos ni relaciones de hardlinks.
Cada snapshot es autosuficiente. La fuente se abre solo para lectura y debe
permanecer estable durante create. Los IDs cumplen
`[A-Za-z0-9][A-Za-z0-9_-]{0,63}` y nunca se sobrescriben. Se rechazan el solapamiento
fuente/repositorio y destino/repositorio, symlinks (incluidos componentes de
rutas) y archivos especiales en los árboles gestionados.

`verify` comprueba el manifiesto y su checksum, valida rutas y estructura,
exige el conjunto exacto de objetos y lee todos los bytes para comprobar tamaño
y SHA-256. `list` realiza esas mismas comprobaciones antes de incluir un ID;
omite snapshots incompletos o corruptos. Un symlink o archivo especial en el
repositorio produce rechazo de la operación.

Create trabaja en `.staging/create-UUID`, sincroniza los archivos, comprueba
integridad y publica mediante un único rename del directorio. Usa un bloqueo
exclusivo sobre el descriptor del repositorio; las lecturas toman un bloqueo
compartido. No hay archivo de bloqueo ni metadata persistente fuera de archivos
regulares. Los procesos de esta utilidad respetan esos bloqueos.

Tras SIGKILL, el bloqueo se libera automáticamente. Antes de cada create se
eliminan las etapas abandonadas con el patrón reservado `create-` seguido de
32 dígitos hexadecimales. Esto permite repetir un ID interrumpido y recuperar
su espacio sin borrar snapshots publicados. Si SIGKILL ocurre después del
rename, el snapshot ya está completo y repetir el ID se rechaza normalmente.
`.staging` es un espacio reservado de la utilidad.

Restore verifica el snapshot antes de crear el árbol de salida, copia a un
directorio temporal hermano del destino, verifica los bytes copiados y vuelve
a comprobar el snapshot antes del rename final. Un destino existente no vacío
se rechaza sin modificar sus bytes. Un destino vacío se reemplaza al publicar.
Los fallos ordinarios limpian los temporales; una corrupción no publica la
restauración. No se requiere acceso a la fuente original.

## Límite de bytes

Con `--max-bytes N`, después de recuperar etapas abandonadas se suma `st_size`
de **cada archivo regular** encontrado recursivamente en el repositorio,
incluidos snapshots anteriores, metadata y archivos regulares ajenos al formato.
Cada entrada de hardlink cuenta por su tamaño. No se usan bloques asignados,
xattrs ni nombres de archivos/directorios para ocultar metadata al cómputo.

Si los bytes existentes superan N, create rechaza antes de copiar. Durante la
copia se controla el presupuesto restante y se cargan también los bytes del
manifiesto y del checksum. Antes de publicar se vuelve a medir todo el árbol,
incluida la etapa: el rename no cambia esa suma. El resultado exitoso satisface
`suma(st_size de archivos regulares del repo) <= N`, también en el límite exacto.

Un rechazo elimina la etapa nueva y conserva los snapshots previos. Puede dejar
directorios estructurales vacíos, que no añaden bytes regulares. La recuperación
puede reducir el tamaño al eliminar etapas abandonadas. No se eliminan snapshots
previos para hacer sitio y no se exige que un límite físicamente imposible quepa.

## Ejemplos y pruebas ejecutadas

```sh
python3.12 solution/run_examples.py
python3.12 -m unittest discover -s solution -p test_backup.py -v
```

El primer comando genera datos privados temporales en `/trial`, ejecuta las
cuatro operaciones, restaura dos versiones sin la fuente y comprueba rechazo
por límite, protección del destino y corrupción de metadata. El segundo cubre
integridad de todos los archivos del snapshot, errores de escritura, límites
exactos, fuente vacía, archivos adicionales, hardlinks, SIGKILL en cinco puntos
antes de publicar y después de publicar, reintentos con presupuesto ajustado y
creadores concurrentes. No hay dependencias externas.

Los comandos y resultados se conservan en `TEST_COMMANDS.jsonl`,
`EXAMPLE_COMMANDS.jsonl`, `TEST_RUN_STAGE2.log`, `TEST_RUN_FINAL.log`,
`EXAMPLES.log` y `TEST_RESULTS.md`. Estos archivos pertenecen a la entrega;
no se almacenan dentro de los repositorios de prueba. Los datos temporales se
eliminan al terminar los ejemplos y las pruebas. CONTRACT.md permanece intacto.
