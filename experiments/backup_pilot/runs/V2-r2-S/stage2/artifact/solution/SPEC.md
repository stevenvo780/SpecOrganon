# Especificación derivada — V2

El contrato de referencia es `/trial/CONTRACT.md`, que permanece intacto.
Entrega actualizada para V2 y el cambio común de etapa dos. Utiliza Python 3.12
y únicamente su biblioteca estándar. C01–C11 se conservan; C12–C15 se derivan
del contrato actualizado antes de implementar el nuevo argumento.

## Criterios de aceptación, derivados antes de implementar

| ID | Requisito observable | Verificación prevista |
| --- | --- | --- |
| C01 | Las cuatro órdenes y sus argumentos contractuales funcionan; éxito produce un objeto JSON y código 0; error nunca afirma éxito. | CLI, argumentos y JSON. |
| C02 | Crear conserva bytes arbitrarios, nombres Unicode/espacios y directorios vacíos; no cambia la fuente. | Inventarios antes/después y restauración. |
| C03 | V2: versiones con adiciones, cambios y eliminaciones se restauran exactamente y de forma independiente, incluso eliminada la fuente. | Ejemplo reproducible de tres versiones y prueba de autosuficiencia. |
| C04 | Solo se admiten IDs `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`; no se sobrescribe un ID existente y los IDs inexistentes fallan. | Casos válidos, límites, traversal y duplicado. |
| C05 | Listar un repositorio vacío da `[]`; los IDs completos se ordenan; los temporales no aparecen. | Vacío, orden, incompletos y corrupción. |
| C06 | Se rechazan enlaces simbólicos, incluidos componentes de las rutas, y archivos especiales en fuente, repositorio, snapshot y destino, sin seguirlos. | Enlaces en cada ámbito, ancestros y FIFO/socket. |
| C07 | Fuente y repositorio no se solapan; un destino no vacío falla sin mutación; tampoco se restaura sobre el repositorio. | Solapamientos en ambos sentidos e inventarios protegidos. |
| C08 | Verificar comprueba todo el manifiesto y los datos; bytes alterados, ausentes o adicionales impiden éxito. | Corrupción de cada clase de archivo y manifiestos malformados. |
| C09 | La publicación de create es atómica; SIGKILL conserva versiones publicadas y permite repetir el ID interrumpido. | Interrupción observada durante la copia y repetición con verificación. |
| C10 | Restaurar verifica antes de publicar; una corrupción no produce una restauración declarada correcta. | Destinos ausentes/vacíos, corrupción y fallo durante la copia. |
| C11 | No se necesitan dependencias, red, credenciales ni la fuente original. | Revisión del código y ejecución local aislada. |
| C12 | `create` acepta `--max-bytes N` opcional; N es un entero decimal no negativo. Sin la opción se conserva la interfaz inicial. | Argumentos válidos, inválidos y ausencia de opción. |
| C13 | Tras éxito limitado, la suma recursiva de `st_size` de TODOS los archivos regulares del repositorio es <= N, incluidos objetos, manifiestos, sellos y temporales previos. Toda metadata persistente reside en archivos regulares. | Medición independiente, igualdad exacta, metadata de fuente vacía y temporal previo. |
| C14 | Un límite insuficiente rechaza con código distinto de 0, sin éxito, sin alterar snapshots/fuente y sin crecimiento residual del intento. También rechaza si N es menor que los bytes preexistentes. Puede repetirse el mismo ID con un límite suficiente. | Inventarios y tamaños antes/después, repetición de rechazos y recuperación. |
| C15 | V2 conserva versiones exactas con el límite activo; corrupción, rutas protegidas e interrupción siguen teniendo las garantías C02–C10. | Tres versiones limitadas, SIGKILL limitado/repetición y rechazos protegidos con opción. |

## Decisiones y límites

- Cada snapshot contiene un manifiesto JSON, su sello SHA-256 y objetos numerados independientes. El manifiesto enumera todas las rutas como listas de componentes, todos los directorios y el tamaño/hash de cada archivo.
- Las rutas se validan sin aceptar componentes vacíos, `.` o `..`; se comprueban duplicados, colisiones y padres. SHA-256 detecta corrupción accidental; no pretende autenticar repositorios frente a alguien que reescribe coherentemente datos y sellos.
- La construcción utiliza directorios temporales dentro del repositorio. Un directorio de snapshot solo se publica cuando todos sus archivos están escritos y sincronizados. Los temporales abandonados se ignoran al listar y no bloquean repetir un ID.
- `list` comprueba los snapshots y enumera solo los completos e íntegros. Rechaza enlaces/archivos especiales en el repositorio, incluso dentro de temporales. Un snapshot incompleto o corrupto queda excluido; `verify` y `restore` lo rechazan explícitamente.
- La restauración se prepara en un directorio hermano del destino y verifica sus copias antes de publicar. Se admiten destinos ausentes o vacíos. Se rechaza cualquier solapamiento destino/repositorio.
- La fuente debe ser estable, como establece el contrato. No se exige resolver modificaciones concurrentes hostiles de rutas o del repositorio. No se preservan permisos, UID, ACL, tiempos ni hardlinks. Los temporales de un SIGKILL pueden consumir espacio, pero no se necesitan para recuperar ni repetir operaciones.
- Los errores se comunican por stderr; stdout queda reservado para el JSON de éxito. No se modifica la fuente y no se depende de sus rutas al restaurar.

## Diseño del cambio de límite, anterior al código

- La opción es propia de `create`, opcional para conservar compatibilidad. Rechazar
  números negativos, signos, fracciones, espacios y texto. Cero es admisible como
  argumento, pero no cabe ni un snapshot vacío: necesita manifiesto y sello.
- Contar mediante inventario sin seguir enlaces y `lstat().st_size`, sin estimar
  por tamaños de fuente ni por bloques asignados. Los enlaces duros, si un tercero
  los introduce, cuentan por cada entrada regular. No usar compresión/deduplicación.
- Comprobar los bytes preexistentes antes de crear un temporal. Si ya superan N,
  rechazar sin escrituras. Después de escribir datos y metadata, volver a contar
  todo el repositorio incluyendo el nuevo temporal; si supera N, eliminar solo
  ese temporal. El renombrado de publicación no cambia la suma de archivos.
- Temporales de un SIGKILL no se eliminan automáticamente y cuentan íntegramente
  en el límite. Reintentar sigue siendo posible con presupuesto suficiente o sin
  límite. Un rechazo ordinario no acumula temporales nuevos. El límite contractual
  se aplica al resultado exitoso; durante la construcción puede superarse.
- Se mantiene la decisión de una operación a la vez por repositorio; no se exige
  coordinación con escritores concurrentes externos. No se cambian formato ni
  comportamiento de verify/restore/list.
