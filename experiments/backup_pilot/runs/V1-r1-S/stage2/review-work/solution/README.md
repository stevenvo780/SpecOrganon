# Backup verificable — V1

Entrega conforme a `/trial/CONTRACT.md`, incluido el cambio `--max-bytes`.
Python 3.12 y biblioteca estándar; entorno POSIX/Linux del piloto. No requiere
instalación ni acceso a internet. El contrato permanece sin modificaciones.

## Uso

Desde `/trial`:

```sh
python3.12 solution/backup.py create --source 'datos fuente' --repo repositorio --id V1 --max-bytes 1000000
python3.12 solution/backup.py verify --repo repositorio --id V1
python3.12 solution/backup.py restore --repo repositorio --id V1 --dest restaurado
python3.12 solution/backup.py list --repo repositorio
```

`--max-bytes N` es opcional; omitirlo conserva la interfaz original sin límite.
N es un entero decimal no negativo, sin signo. Se aceptan ceros iniciales.
El presupuesto cubre **todo el repositorio**, sumando `st_size` de cada archivo
regular por ruta: contenido de todos los snapshots, manifiestos, COMMIT y
cualquier otro archivo existente. Los hardlinks se cuentan por cada ruta y los
archivos dispersos por tamaño lógico. Los directorios no añaden bytes a esa
suma. Toda metadata persistente del formato está en archivos regulares.

Si no cabe, create termina con error, elimina su temporal y conserva los
snapshots anteriores. Puede repetirse el mismo ID con un presupuesto suficiente.
El presupuesto limita el tamaño tras el éxito; durante la preparación puede
hacer falta espacio adicional. No se comprime ni se deduplica. Un repositorio
nuevo rechazado puede conservar directorios vacíos, con cero bytes regulares.

Cada comando exitoso devuelve código 0 y un único objeto JSON en stdout:

| Comando | Respuesta |
| --- | --- |
| create | `{"id": "V1"}` |
| verify | `{"id": "V1", "valid": true}` |
| restore | `{"id": "V1"}` |
| list | `{"snapshots": ["V1"]}` (ordenados) |

Los errores devuelven código 1, stdout vacío y un objeto `{"error": "..."}`
en stderr. El ID debe cumplir `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`.

## Garantías y formato

Se conservan archivos regulares, bytes arbitrarios, nombres Unicode/espacios y
directorios vacíos. La creación no modifica la fuente y la restauración funciona
sin ella. Se rechazan enlaces simbólicos y archivos especiales, incluidos los
componentes de las rutas. Fuente y repositorio no pueden solaparse. Restore
también rechaza el solapamiento con el repositorio. Un destino existente no vacío
se rechaza sin modificarlo; un ID existente no se sobrescribe.

```text
repositorio/
  snapshots/
    V1/
      data/             árbol de archivos y directorios
      manifest.json     ID, versión, rutas, tipos, tamaños y SHA-256
      COMMIT            SHA-256 del manifiesto, seguido de LF
  .staging/             trabajo privado no publicado
```

El manifiesto es JSON canónico ASCII (Unicode escapado). Verify comprueba
esquema, checksum del manifiesto, inventario exacto, tamaños y hashes de todos
los archivos. Las alteraciones y eliminaciones de datos o metadata se rechazan.
Restore verifica antes de copiar y vuelve a comprobar cada archivo copiado;
publica el árbol completo mediante rename desde un temporal hermano del destino.

Create publica mediante rename dentro del repositorio. `.staging/` está reservado
al programa: el siguiente create elimina sus restos abandonados antes de medir
el presupuesto. Un bloqueo transitorio `flock` del descriptor del directorio del
repo serializa los create y se libera al terminar o ante SIGKILL; no añade
archivos ni metadata persistente. List ignora los temporales y directorios de
snapshot sin COMMIT, y verifica los snapshots publicados antes de devolverlos.
Un snapshot publicado con corrupción detectable provoca error. List de un repo
inexistente o vacío devuelve `{"snapshots": []}` sin crearlo.

No se preservan UID, ACL, tiempos, permisos ni identidad de hardlinks. Se supone
una fuente estable durante la operación, como exige el contrato. El formato
detecta corrupción accidental; los checksums no autentican un repositorio que
alguien reescribe coordinadamente. Se usa filesystem POSIX local con rename y
flock; no se garantiza operar mientras terceros modifican directamente el repo.

## Pruebas y documentación SDD

Para reproducir la verificación completa y conservar comandos/resultados:

```sh
python3.12 solution/run_checks.py
```

El runner ejecuta compilación, unittest y ejemplos. Guarda las salidas completas
en [verification/commands.log](verification/commands.log). Los ejemplos conservan
sus fixtures bajo `solution/example-data/` y regeneran solamente ese directorio.
Las pruebas temporales usan `solution/.test-work/` y se limpian al terminar.

Resultado de esta entrega: **35 pruebas correctas y 1 omitida de 36**;
**14 ejemplos CLI correctos**. La omisión corresponde a un socket Unix real cuyo
bind prohíbe el contenedor; se verifican los tipos especiales mediante
clasificación y FIFO reales. Se comprobaron corrupción de cada archivo regular
del snapshot, SIGKILL real y reintento con límite exacto, rechazo sin crecimiento
residual y dos create concurrentes con presupuesto para uno solo.

El ejemplo usa 1636 bytes: 1067 de contenido y 569 de metadata. El límite 1636
permite crear; 1635 rechaza sin bytes regulares residuales. Un límite inferior al
repo existente también rechaza sin modificar sus snapshots.

- [SPEC.md](SPEC.md): criterios derivados y decisiones actualizadas antes del cambio.
- [PLAN.md](PLAN.md) y [TASKS.md](TASKS.md): plan y tareas de la etapa.
- [IMPLEMENTATION.md](IMPLEMENTATION.md): implementación y justificación técnica.
- [VERIFICATION.md](VERIFICATION.md): trazabilidad, comandos y resultados.

No se recibieron resultados de evaluación reservada; estos resultados proceden
exclusivamente de las pruebas propias conservadas.
