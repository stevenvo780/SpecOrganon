# Backup verificable — variante V1

Entrega para el contrato actualizado de `/trial/CONTRACT.md`. Usa Python 3.12
y exclusivamente la biblioteca estándar. Ejecutable en Linux/Unix con `fcntl`,
`O_NOFOLLOW` y sincronización de directorios; validado con Python 3.12.15.

Desde `/trial`:

```sh
python3 solution/backup.py create --source DIR --repo REPO --id ID --max-bytes N
python3 solution/backup.py verify --repo REPO --id ID
python3 solution/backup.py restore --repo REPO --id ID --dest DEST
python3 solution/backup.py list --repo REPO
```

`--max-bytes` acepta un entero decimal no negativo. Es opcional para conservar
la interfaz inicial: omitirlo deja la creación sin límite. Con el argumento,
el total de `st_size` de **todos** los archivos regulares del repositorio al
terminar con éxito es como máximo N. Incluye snapshots anteriores, datos,
manifiestos, sellos y archivos regulares de otras entradas internas, aunque no
correspondan al snapshot solicitado. No usa compresión ni deduplicación.
Los directorios vacíos y los archivos de tamaño cero también necesitan metadata
y pueden no caber en un límite de cero.

El código 0 devuelve un solo objeto JSON por stdout: `{"id":"ID"}` para crear
y restaurar, `{"id":"ID","valid":true}` para verificar y
`{"snapshots":["IDs ordenados"]}` para listar. Los errores devuelven código
distinto de cero, stdout vacío y diagnóstico por stderr. Los errores de uso
los presenta `argparse`. Los IDs admitidos son
`[A-Za-z0-9][A-Za-z0-9_-]{0,63}`; nunca se sobrescribe un ID existente.

## Almacenamiento e integridad

Cada snapshot publicado está en `REPO/snapshots/ID/`. Contiene `manifest.json`,
su sello SHA-256 en `manifest.sha256` y los archivos independientes `data/0`,
`data/1`, etc. El manifiesto registra versión, ID, rutas originales, todos los
directorios, tamaños y hashes SHA-256. Toda la metadata persistente se almacena
en archivos regulares y cuenta para el límite; no usa xattrs ni archivos
especiales. Los nombres originales se guardan como componentes de ruta en JSON,
incluidos Unicode y espacios, sin interpretarlos como rutas absolutas.

`verify` comprueba el sello, el esquema completo del manifiesto, las rutas,
las entradas exactas del snapshot y el tamaño/hash de cada archivo. `list`
realiza esas mismas comprobaciones y solo anuncia snapshots completos e
íntegros. La restauración copia y verifica cada archivo en un directorio
temporal hermano del destino y publica el árbol mediante un renombrado.
Una corrupción o eliminación de datos o metadata produce rechazo. Los hashes
detectan corrupción; no constituyen autenticación frente a quien pueda
reescribir simultáneamente datos, manifiesto y sello.

## Publicación, límite y recuperación

Las operaciones usan un bloqueo exclusivo sobre el directorio del repositorio,
sin archivo de bloqueo persistente. Dos procesos que usan esta herramienta
serializan sus operaciones y comparten el mismo presupuesto total.

`create` valida la fuente y rechaza el solapamiento antes de copiar. Dentro del
bloqueo elimina copias abandonadas en `REPO/.staging/`: ninguna pertenece a un
snapshot publicado. Luego suma los bytes existentes, limita los bytes copiados,
incluye el tamaño exacto del manifiesto y el sello, verifica la copia y vuelve
a sumar los `st_size` reales de todo el repositorio antes de publicar. El
renombrado a `snapshots/ID` no altera esa suma. Si no cabe, elimina el temporal;
los snapshots previos conservan sus bytes. Pueden quedar directorios internos
vacíos, que no aportan bytes regulares.

Los datos y directorios de publicación se sincronizan. Ante SIGKILL puede quedar
una copia privada en `.staging`, nunca listada como snapshot. El bloqueo se
libera al terminar el proceso; se puede repetir `create` con el mismo ID. La
siguiente creación limpia los temporales abandonados, incluidos sus bytes,
antes de calcular el presupuesto disponible. Si la publicación ya ocurrió,
el ID existe completo y una repetición se rechaza sin sobrescribirlo.

La fuente debe permanecer estable durante la operación, conforme al contrato.
El repositorio es autosuficiente y no necesita conservar la fuente. Se rechazan
symlinks y archivos especiales en las rutas gestionadas, incluidos ancestros
de las rutas proporcionadas. Un destino existente no vacío se rechaza antes de
escribir; un destino nuevo o vacío solo se publica tras verificar la copia.
No se preservan UID, ACL, tiempos ni identidad de hardlinks.

## Ejemplos y pruebas ejecutadas

Todos los datos temporales de los ejemplos y pruebas se crean bajo `/trial` y
se eliminan al terminar. Comandos ejecutados desde `/trial`:

```sh
python3 --version
python3 solution/test_backup.py > solution/test-results-v1-max-bytes.txt 2>&1
python3 solution/examples.py > solution/example-results-v1-max-bytes.txt 2>&1
python3 -m py_compile solution/backup.py solution/test_backup.py solution/examples.py
```

Resultados: Python 3.12.15; **32 pruebas, OK**, código 0; ejemplo **PASS**,
código 0. Los registros conservan cada comando CLI, código de salida, stdout
y stderr. La comprobación de compilación también terminó con código 0 y su
registro está en `compile-results-v1-max-bytes.txt`. Las pruebas cubren bytes
arbitrarios, Unicode, directorios vacíos,
fuente intacta, restauración sin fuente, versiones, IDs, solapamiento,
destino protegido, enlaces, FIFO, corrupción/eliminación de cada archivo del
snapshot, metadata inválida, interrupción y concurrencia. Para el nuevo
requisito comprueban el límite exacto, un byte menos, metadata sin datos,
límites inferiores a bytes existentes, rechazo sin crecimiento regular,
archivos internos adicionales, limpieza de temporales, argumentos inválidos
y el presupuesto compartido entre creaciones concurrentes.

El ejemplo crea con N=4096 un repositorio de **775 bytes**, verifica y lista,
rechaza una segunda creación con N=774 sin cambiar el repositorio, elimina la
fuente y restaura exactamente los archivos y directorios originales.

Archivos de evidencia:

- [test-results-v1-max-bytes.txt](test-results-v1-max-bytes.txt)
- [example-results-v1-max-bytes.txt](example-results-v1-max-bytes.txt)
- [test_backup.py](test_backup.py)
- [examples.py](examples.py)

Los registros de la etapa anterior permanecen conservados. Los resultados
indicados son de pruebas propias; no se recibieron resultados de evaluación
reservada.
