# Especificación derivada — V3

Fecha: 2026-10-04. Autoridad: `/trial/CONTRACT.md`, que permanece intacto.
Etapa actualizada: `create --max-bytes N`, Python 3.12 y biblioteca estándar. Solo datos de
prueba en `/trial`; no red, dependencias, credenciales ni intervención humana.

## Criterios previos a la implementación

| ID | Criterio verificable | Prueba prevista |
| --- | --- | --- |
| C01 | Cuatro comandos contractuales; éxito con código 0 y exactamente un objeto JSON; errores con código no cero | CLI y ejemplos |
| C02 | Copia exacta de bytes, nombres Unicode/espacios y todos los directorios vacíos; fuente sin modificaciones | Comparación recursiva antes/después |
| C03 | Repositorio autosuficiente y versiones independientes; lista ordenada y solo snapshots completos | Eliminar fuente, restaurar varias versiones, listar |
| C04 | IDs limitados a la expresión contractual; ID existente no se sobrescribe; ID ausente rechazado | Casos de frontera y comparación del repo |
| C05 | Rechazo de symlinks y archivos especiales en fuente, repo, snapshots y destino, sin seguirlos | Enlaces en raíz, ancestros y descendientes; FIFO/socket |
| C06 | Rechazo de fuente/repo solapados, en ambas direcciones | Rutas iguales, descendientes y ancestros |
| C07 | Destino preexistente no vacío intacto incluso cuando falla la restauración | Bytes antes/después; snapshot corrupto |
| C08 | Verificar todos los datos y metadatos; alteración, truncamiento, eliminación o incorporación inesperada produce rechazo | Mutaciones individuales de archivos del snapshot |
| C09 | Corrupción no publica una restauración; destino ausente o vacío queda como estaba si falla la validación | Restaurar cada corrupción con ambos tipos de destino |
| C10 | Publicación atómica de create; SIGKILL conserva snapshots anteriores y permite repetir el mismo ID | Interrupción real durante copia y antes de publicación |
| C11 | Fuente nunca modificada; fallos no afirman éxito y temporales no aparecen en list | Comparaciones y fallos inducidos |
| C12 | Documentos SDD, trazabilidad y comandos/resultados de ejemplos y pruebas conservados | Revisión de artefactos |
| C13 | `create --max-bytes N` acepta un entero decimal no negativo; omitirlo conserva la interfaz anterior | CLI, cero y entradas inválidas |
| C14 | Tras un create exitoso, la suma de `st_size` de **todos** los archivos regulares del repo es ≤ N; incluye datos, manifiestos, checksums y bloqueo | Conteo independiente, límite exacto y límite alto |
| C15 | Un límite insuficiente rechaza sin alterar snapshots previos ni dejar crecimiento permanente en archivos regulares | Límite inferior a bytes existentes; falta de espacio para datos o metadata; comparación completa antes/después |
| C16 | La recuperación elimina staging huérfano antes de calcular el presupuesto; las operaciones propias se serializan para respetar N | SIGKILL seguido de reintento con límite; creates concurrentes |

## Cambio de alcance, registrado antes de implementar

Se conserva el formato 1 y C01–C12. No se requiere migrar snapshots previos.
`--max-bytes` es opcional para mantener la CLI inicial; cuando aparece limita la
suma lógica de tamaños, no bloques físicos ni el tamaño de los directorios.
Toda metadata persistente continúa en archivos regulares. No se emplean xattrs
ni otras ubicaciones para eludir el conteo. Los nombres de directorios sirven
solo para organizar el formato; ID y rutas están también en el manifiesto.

Después de tomar el bloqueo y limpiar staging abandonado, create cuenta
recursivamente todos los archivos regulares. Si ya exceden N, rechaza antes de
copiar. Un presupuesto incremental limita cada escritura nueva, tanto de datos
como de metadata. Antes del renombrado se repite el conteo íntegro. Cualquier
fallo previo a publicación elimina el staging de esa operación. SIGKILL puede
dejar staging temporal, pero nunca se lista como snapshot; el siguiente create
lo recupera. No se exige que la suma respete N durante una operación fallida.

## Decisiones del formato y comportamiento

Repositorio dedicado: `.lock`, `snapshots/`, `.staging/`. Cada snapshot publicado
contiene `manifest.json`, `manifest.sha256` y `data/` con archivos numerados.
El manifiesto contiene versión de formato, ID, rutas relativas de directorios,
y rutas/tamaños/SHA-256 de archivos. Su propio SHA-256 se guarda en el segundo
archivo. Se exige el conjunto exacto de entradas del snapshot. Esto detecta
corrupción accidental de cualquiera de sus archivos regulares; no pretende
autenticar frente a reescritura coordinada del repositorio por un atacante.

`create` copia en un directorio temporal privado, sincroniza archivos y
directorios y renombra al nombre final bajo un bloqueo liberado por el kernel
incluso tras SIGKILL. Una nueva operación puede limpiar temporales huérfanos.
Se usa bloqueo POSIX mediante `fcntl` (entorno de entrega Linux/Python 3.12).

`verify` valida esquema, rutas, estructura, tamaños y todos los hashes.
`list` comprueba los snapshots publicados y enumera solo los que pasan la
validación completa. Los temporales no son snapshots. Las rutas inseguras
(enlaces o especiales) provocan error en vez de ser ignoradas.

`restore` valida antes de copiar y comprueba también los bytes copiados en un
temporal contiguo al destino. Solo después publica mediante renombrado atómico.
El destino puede estar ausente o ser un directorio vacío. Se rechaza también
destino/repo solapados para no alterar el repositorio.

Se abren directorios y archivos sin seguir enlaces. No se preservan permisos,
propietario, ACL, tiempos ni identidad de hardlinks. La fuente es estable durante
create, tal como establece el contrato. Las operaciones propias del repositorio
se serializan. No se promete resistencia a modificaciones concurrentes de los
directorios por programas externos ni reparación de corrupción.
