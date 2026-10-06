# Backup verificable — V2, contrato actualizado

`backup.py` crea snapshots independientes y autosuficientes, comprueba su
integridad y restaura cada versión exacta. Usa Python 3.12 y biblioteca estándar.
La entrega se verifica en Linux; usa renombrado y sincronización de directorios
POSIX. Ejecutar desde `/trial`:

```bash
python3 solution/backup.py create --source DIR --repo REPO --id v1
python3 solution/backup.py create --source DIR --repo REPO --id v2 --max-bytes 1000000
python3 solution/backup.py verify --repo REPO --id v1
python3 solution/backup.py restore --repo REPO --id v1 --dest DEST
python3 solution/backup.py list --repo REPO
```

Éxito retorna código 0 y un único objeto JSON en stdout: `{"id":"v1"}` para
create/restore, `{"id":"v1","valid":true}` para verify y
`{"snapshots":["v1","v2"]}` para list (ordenados). Los errores retornan código 1,
stdout vacío y `{"error":"..."}` en stderr; una interrupción por teclado retorna
130. `--help` muestra ayuda textual. Un repositorio vacío o aún ausente se lista
como `{"snapshots":[]}`. Los IDs deben coincidir con
`[A-Za-z0-9][A-Za-z0-9_-]{0,63}`; no se sobrescriben.

## Límite de bytes

`--max-bytes N` es opcional y exclusivo de create. N es un entero decimal no
negativo, sin signo ni espacios. Si se omite, se conserva create sin límite.
La suma recursiva de `st_size` de **todos** los archivos regulares del repositorio
tras el éxito debe ser <= N. Incluye datos, manifiestos, sellos, otras versiones
y archivos de temporales abandonados. Toda metadata persistente del snapshot
está en archivos regulares: incluso una fuente vacía necesita bytes de metadata.
No hay compresión ni deduplicación; cada versión guarda sus propios datos.

Se comprueba la suma antes de construir y después de escribir datos y metadata,
antes del renombrado final. Un límite insuficiente rechaza y elimina el temporal
del intento, conservando snapshots anteriores y bytes de la fuente. Puede
repetirse el mismo ID con un límite suficiente. Si N ya es inferior a los bytes
existentes, el rechazo ocurre sin escrituras. El límite se refiere al resultado
exitoso; la construcción temporal puede usar más bytes que N.

## Garantías y formato

Se conservan archivos regulares con bytes arbitrarios, nombres Unicode/espacios
y todos los directorios, incluidos los vacíos. La fuente debe permanecer estable
y no se modifica. Fuente/repositorio no pueden solaparse. Se rechazan symlinks
en entradas y componentes de rutas, y FIFO, sockets y dispositivos. No se
preservan UID, ACL, tiempos, permisos ni relaciones de hardlinks.

Cada `REPO/ID/` contiene `manifest.json`, `manifest.sha256` y `data/` con archivos
numerados. El manifiesto guarda ID, formato, rutas, directorios, tamaños y hashes
SHA-256. El sello comprueba el manifiesto y verify comprueba todos los objetos,
sus tamaños/hashes y la estructura completa. SHA-256 detecta corrupción
accidental; el formato no autentica cambios coherentes de datos y sellos.
list comprueba integridad y muestra solo snapshots completos e íntegros.

create prepara `.incomplete-*` dentro del repositorio, sincroniza sus archivos
y publica mediante un único renombrado. Un SIGKILL puede dejar un temporal;
las versiones publicadas permanecen utilizables y puede repetirse el ID sin
reiniciar el repositorio. Los temporales abandonados se ignoran al listar,
cuentan en `--max-bytes` y no se borran automáticamente: el reintento requiere
presupuesto para los bytes existentes más la nueva versión, o puede hacerse
sin límite. Un error ordinario elimina el temporal de su propio intento.

restore comprueba primero el snapshot completo, prepara un directorio hermano
del destino, comprueba nuevamente las copias y publica mediante renombrado.
Admite destinos ausentes o vacíos. Rechaza un destino no vacío sin cambiar sus
bytes y rechaza solapamiento con el repositorio. No necesita la fuente original.
Una corrupción detectada impide declarar validez o restaurar con éxito.

Las operaciones se ejecutan de una en una por repositorio. No se coordina con
escritores simultáneos ni cambios hostiles de rutas. La recuperación consiste
en repetir operaciones fallidas; no se reparan bytes corruptos desconocidos.

## Ejemplo y verificación reproducible

```bash
cd /trial
python3 solution/examples/v2.py
python3 -m unittest discover -s solution/tests -v
python3 solution/verify_local.py
```

El ejemplo crea tres versiones con adiciones, cambios y eliminaciones, cada una
con `--max-bytes`, elimina la fuente y verifica/restaura las tres exactamente.
Las pruebas utilizan datos sintéticos y temporales privados bajo `/trial/solution`.
`verify_local.py` conserva comandos, códigos y stdout/stderr completos en
[`evidence/`](evidence/), comprueba sintaxis y verifica que CONTRACT.md/AGENTS.md
mantienen los hashes registrados antes de editar. No instala dependencias ni
consulta servicios externos.

La especificación y criterios derivados están en [SPEC.md](SPEC.md), el plan en
[PLAN.md](PLAN.md), las tareas en [TASKS.md](TASKS.md), las decisiones de código en
[IMPLEMENTATION.md](IMPLEMENTATION.md) y los resultados y trazabilidad en
[VERIFICATION.md](VERIFICATION.md). El contrato se conserva intacto.
