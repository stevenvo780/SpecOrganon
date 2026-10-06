# Backup verificable — V1

Entrega para Python 3.12 en Linux, solo biblioteca estándar. Conserva árboles
de archivos regulares, bytes arbitrarios, nombres Unicode/espacios y directorios
vacíos. El repositorio contiene todo lo necesario para restaurar.

## Uso

Desde `/trial`, con fuente y repositorio separados:

```sh
python3 solution/backup.py create --source /trial/datos --repo /trial/repo --id V1 --max-bytes 1000000
python3 solution/backup.py verify --repo /trial/repo --id V1
python3 solution/backup.py restore --repo /trial/repo --id V1 --dest /trial/restaurado
python3 solution/backup.py list --repo /trial/repo
```

Los resultados de éxito son respectivamente `{"id":"V1"}`,
`{"id":"V1","valid":true}`, `{"id":"V1"}` y
`{"snapshots":["V1"]}`: código 0 y un objeto JSON en stdout.
Los errores dan código distinto de 0, stdout vacío y diagnóstico en stderr.
Los IDs siguen `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`; list los ordena.
Un repositorio ausente o vacío produce `{"snapshots":[]}` sin inicializarlo.

## Límite de capacidad

`--max-bytes N` es opcional en create. N es un entero decimal no negativo,
en bytes; omitirlo permite crear sin límite. El límite cuenta la suma de
`st_size` de todos los archivos regulares del repositorio después del éxito:
datos, manifiestos, sellos y archivos preexistentes, incluidos snapshots
incompletos. No se comprime ni deduplica. Una fuente vacía también requiere
espacio para sus metadatos.

Si el uso inicial ya supera N, create falla sin cambiar archivos del repo.
En otros casos limpia restos abandonados de `.staging`, prepara el snapshot
y mide el árbol completo antes de publicarlo. Si no cabe, elimina su preparación
y rechaza sin invalidar snapshots anteriores ni dejar nuevos archivos
permanentes. La copia puede ocupar más de N transitoriamente. Un rechazo en
un repo nuevo puede dejar directorios vacíos, con cero bytes de archivos.

## Integridad y recuperación

El formato es `snapshots/ID/{data/,manifest.json,manifest.sha256}`. El manifiesto
regular contiene ID, versión, rutas de directorios y rutas/tamaños/SHA-256 de
archivos; su sello también es regular y cuenta en el presupuesto. verify
comprueba estructura exacta, esquema, manifiesto y todos los bytes. list incluye
solo snapshots publicados que superan esas comprobaciones.

create prepara el árbol en `.staging` y publica por rename atómico. Un bloqueo
`fcntl.flock` transitorio sobre el directorio del repo serializa los procesos
create, sin metadata de bloqueo persistente. Tras SIGKILL, los snapshots previos
siguen disponibles; el siguiente create limpia staging abandonado y permite
repetir un ID que no llegó a publicarse. Con límite, N debe cubrir también el
uso existente al iniciar el reintento. Un ID publicado nunca se sobrescribe,
incluso si sus bytes están corruptos.

restore verifica antes de preparar un directorio privado hermano del destino,
comprueba de nuevo los bytes copiados y publica por rename. Acepta destino
ausente o directorio vacío; rechaza uno no vacío preservando sus bytes.
Rechaza symlinks y archivos especiales en rutas gestionadas, incluidos sus
ancestros, y solapamientos fuente/repo o repo/destino.

No preserva UID, ACL, permisos, tiempos ni identidad de hardlinks. La fuente
debe permanecer estable. Los hashes detectan corrupción accidental, sin
autenticación contra reemplazo coordinado de datos y metadatos. No se promete
protección frente a sustituciones concurrentes maliciosas de rutas ni frente a
fallos de energía; fsync se usa antes y después de publicar.

## Verificación reproducible

```sh
cd /trial
python3 solution/tests/run_checks.py
```

El ejecutor conserva comandos exactos, versión de Python, salidas y códigos en
[evidence/](evidence/). Resultado: 28 pruebas descubiertas, 27 aprobadas y una
omitida porque el contenedor impide `AF_UNIX bind`; ejemplo y compilación con
código 0. Se prueban límites exactos, metadata, snapshots anteriores, rechazo
sin crecimiento, corrupción, SIGKILL y dos creates concurrentes. El ejemplo
usa 723 bytes con límite 100000 y rechaza 722 sin cambiar el repositorio.

[SPEC.md](docs/SPEC.md), [PLAN.md](docs/PLAN.md) y [TASKS.md](docs/TASKS.md)
registran especificación, plan y tareas. [IMPLEMENTATION.md](docs/IMPLEMENTATION.md)
explica la implementación y [VERIFICATION.md](docs/VERIFICATION.md) traza
criterios a pruebas y resultados. CONTRACT.md se conservó sin cambios.
