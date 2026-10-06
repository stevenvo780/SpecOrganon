# Backup verificable — variante V2, etapa dos

Python 3.12, biblioteca estándar, entorno POSIX/Linux. Cada ID conserva una
versión independiente de archivos y directorios, incluidos los vacíos. Los
snapshots permiten restaurar sin disponer de la fuente original.

Desde `/trial`:

```sh
python3.12 solution/backup.py create --source /trial/datos --repo /trial/repo --id v1 --max-bytes 10000000
python3.12 solution/backup.py verify --repo /trial/repo --id v1
python3.12 solution/backup.py restore --repo /trial/repo --id v1 --dest /trial/restaurado
python3.12 solution/backup.py list --repo /trial/repo
```

La fuente debe existir. `create --max-bytes N` es opcional; sin esa opción
se conserva la interfaz inicial sin límite. N contiene dígitos decimales ASCII
y debe ser no negativo. El límite se aplica a esa operación y cuenta la suma
de `st_size` de **todos los archivos regulares del repositorio final**, incluidos
versiones anteriores, manifiestos, checksums y bloqueo. No equivale a `du` ni
al espacio físico ocupado. El ajuste exacto se acepta. Si no cabe, se rechaza
sin publicar el ID ni dejar bytes temporales permanentes; puede reintentarse
con un límite suficiente. El tamaño transitorio durante create puede superar N.

Los éxitos retornan código 0 y un objeto JSON en stdout: `{"id":"v1"}`
para create/restore, `{"id":"v1","valid":true}` para verify y
`{"snapshots":["v1"]}` para list, con IDs ordenados. Los errores usan stderr
con un objeto `{"error":"..."}` y código 1; los argumentos inválidos, código 2.

Los IDs cumplen `[A-Za-z0-9][A-Za-z0-9_-]{0,63}` y nunca se sobrescriben.
Se rechazan enlaces simbólicos, archivos especiales, fuente/repo solapados y
destino/repo solapados. Un destino preexistente no vacío se conserva intacto.
Se verifican inventario, tamaño y SHA-256 de todos los datos antes de restaurar;
la restauración se publica desde un temporal. `list` comprueba los snapshots
y omite los incompletos o corruptos. Enlaces o archivos especiales en el repo
producen error. Un repositorio vacío o inexistente devuelve una lista vacía.

Formato: `snapshots/ID/data/`, `manifest.json` y `manifest.sha256`.
Toda metadata persistente está en archivos regulares y cuenta para N.
`.lock` serializa las operaciones y `.staging/` contiene temporales de create.
Tras SIGKILL, se mantienen versiones publicadas y el siguiente create limpia
temporales abandonados antes de reintentar. Se requieren árboles estables
durante las operaciones; no se preservan permisos, UID, ACL, tiempos o hardlinks.

Pruebas y ejemplos reproducibles (todos los datos se generan dentro de `/trial`):

```sh
python3.12 -m unittest discover -s solution/tests -v
python3.12 solution/tests/examples.py
```

Los documentos SDD están en [docs/SPECIFICATION.md](docs/SPECIFICATION.md),
[docs/PLAN.md](docs/PLAN.md), [docs/TASKS.md](docs/TASKS.md),
[docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md) y
[docs/VERIFICATION.md](docs/VERIFICATION.md). Los comandos y resultados se
conservan en `tests/baseline.log`, `tests/results-v2.log` y
`tests/examples-v2.log`. El caso de socket Unix se omite si el sandbox
prohíbe `bind`; los casos de FIFO permanecen activos.
