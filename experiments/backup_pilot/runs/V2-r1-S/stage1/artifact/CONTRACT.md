# Contrato del piloto: backup verificable

Estado: contrato fijado antes de las corridas experimentales, tras controles de desarrollo. Piloto de ingeniería de
software autorizado por el dueño el 2026-10-03; no modifica GOAL.md ni el protocolo
confirmatorio histórico. Solo archivos de prueba en contenedores y directorios
privados del experimento. No cuentas adicionales ni copias de credenciales.

## Producto y formato común

Cada ejecución entrega `/trial/solution/backup.py`, ejecutable con Python 3.12 y
biblioteca estándar, y `/trial/solution/README.md`. La implementación es libre.
Interfaz contractual inicial:

- `python backup.py create --source DIR --repo DIR --id ID`
- `python backup.py verify --repo DIR --id ID`
- `python backup.py restore --repo DIR --id ID --dest DIR`
- `python backup.py list --repo DIR`

Código 0 indica éxito y stdout contiene un único objeto JSON. Los errores retornan
código distinto de 0 y nunca afirman éxito. `create` devuelve `{"id": ID}`;
`verify` devuelve `{"id": ID, "valid": true}` solo tras comprobar todos los datos;
`restore` devuelve `{"id": ID}`; `list` devuelve `{"snapshots": [IDs...]}` ordenados. `list` incluye solo snapshots completos; un repositorio nuevo vacío
devuelve una lista vacía. Un ID inexistente se rechaza al verificar o restaurar.
El formato privado del repositorio queda a elección del implementador.

Ámbito: archivos regulares, directorios vacíos, nombres Unicode/espacios, bytes
arbitrarios y rutas relativas dentro de una fuente. No requiere preservar UID,
ACL, tiempos ni hardlinks. Rechazar symlinks en fuente, repo, destino y snapshots;
no seguirlos. Rechazar IDs distintos de `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`.
No admite fuente/repositorio solapados. Rechaza archivos especiales (FIFO, sockets,
dispositivos) en las rutas gestionadas. Fuente estable durante la operación; no
se exige un snapshot atómico de archivos que un tercero modifica simultáneamente. El repositorio debe ser autosuficiente: restaurar sin acceso a la fuente original.
Un destino preexistente no vacío se rechaza
sin cambiar sus bytes. Un ID existente no se sobrescribe. No debe modificar la fuente.

Una operación incompleta no puede aparecer como snapshot válido: la publicación es
atómica; después de SIGKILL se preservan snapshots anteriores y puede repetirse
un create incompleto con el mismo ID sin reiniciar o destruir el repositorio.
Una corrupción detectada impide afirmar validez o publicar restauraciones como
correctas. La recuperación requerida es repetir operaciones fallidas, no reparar
bytes corruptos desconocidos. Controles de corrupción eligen archivos regulares
del snapshot y alteran o eliminan bytes; deben producir rechazo, no éxito falso.

## Tres variantes

V1: árboles de documentos con bytes variados y directorios vacíos.
V2: instantáneas sucesivas con archivos añadidos, modificados y eliminados;
restaurar cada versión exacta. No exige deduplicación.
V3: integridad y recuperación de snapshots ante corrupción e interrupción de create.
Todos reciben la interfaz y garantías base anteriores. La variante enfatiza la
carga medida; ninguna recibe información esencial exclusiva.

## Criterios

Primario: proporción de comprobaciones funcionales/fallos que pasan por ejecución,
antes y después del cambio. Una corrupción silenciosa o mutación de fuente/destino
protegido es un fallo crítico explícito: se informa además de la proporción y no se
compensa con velocidad. Secundarios: bytes utilizados, tiempos de create/restore,
recuperación, tokens declarados por CLI, tiempo total y cumplimiento del límite.
No se evalúa por páginas de documentación ni por opinión del propio ejecutor.
