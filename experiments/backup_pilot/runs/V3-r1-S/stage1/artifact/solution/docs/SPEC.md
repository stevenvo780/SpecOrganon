# Especificación derivada — V3

Fecha: 2026-10-04. Autoridad: `/trial/CONTRACT.md`, que permanece intacto.
Primera versión funcional, Python 3.12 y biblioteca estándar. Solo datos de
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
