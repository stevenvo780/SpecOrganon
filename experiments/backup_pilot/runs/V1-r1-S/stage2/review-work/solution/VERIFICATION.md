# Verificación y trazabilidad — V1 actualizada

Todas las acciones y fixtures de trabajo estuvieron dentro de `/trial`. No se
instalaron dependencias, consultaron credenciales ni investigaron otros proyectos
o internet. No se usaron resultados de evaluación reservada. CONTRACT.md se
preservó. El alcance es el contrato completo, incluidas las garantías base de
las otras variantes y el cambio común de presupuesto.

## Comandos ejecutados y resultados retenidos

Directorio de trabajo: `/trial`. Python observado: **3.12.15**.

Antes de editar la implementación se ejecutó:

```sh
python3 -m unittest discover -s solution -p test_backup.py -v > solution/verification/baseline-tests.log 2>&1
```

Código 0; 25 pruebas, 24 correctas y 1 omitida, 4.774 segundos de unittest.
Salida completa: [baseline-tests.log](verification/baseline-tests.log).
Se conservó el registro previo parcial en
[initial-commands.log](verification/initial-commands.log), y el diagnóstico
previo del socket en [INITIAL_CHECK.md](INITIAL_CHECK.md).

Después de actualizar implementación, pruebas y ejemplos se ejecutó:

```sh
python3 solution/run_checks.py
```

Código 0. El runner conserva los comandos internos con rutas exactas y salidas
en [commands.log](verification/commands.log):

| Comando interno (abreviado a python3) | Resultado | Tiempo de proceso |
| --- | --- | --- |
| `python3 --version` | 0, Python 3.12.15 | 0.001 s |
| `python3 -m py_compile solution/backup.py solution/test_backup.py solution/examples.py solution/run_checks.py` | 0 | 0.023 s |
| `python3 -m unittest discover -s solution -p test_backup.py -v` | 0, **35 correctas + 1 omitida / 36** | 8.043 s |
| `python3 solution/examples.py` | 0, **14 ejemplos CLI correctos** | 0.503 s |

La prueba omitida intenta bind de un socket AF_UNIX real: el contenedor devuelve
EPERM. La clasificación de socket/dispositivo/FIFO/symlink y los FIFO reales sí
se comprobaron. No se afirma que el test omitido haya pasado.

El ejemplo midió 1636 bytes totales: 1067 de payload y 569 de metadata. Un
presupuesto alto de 1000000 permitió crear. Un presupuesto 1635 rechazó tanto
un segundo ID en el repo existente como un create en un repo nuevo; este último
dejó cero bytes regulares. Repetir el ID con 1636 funcionó y midió exactamente
1636. Estas medidas y respuestas JSON constan en el log, no son estimaciones.

## Matriz de trazabilidad

Los nombres completos y resultados de cada test figuran en commands.log.

| Criterio SPEC | Implementación | Pruebas y evidencia |
| --- | --- | --- |
| C01 | main y respuestas de comandos | `C01_C02_C03_exact_round_trip_without_source`, helper CLI valida objeto único/esquema, ejemplos |
| C02 | inventory, file_data, manifest_entries | round trip, fuente vacía, destino vacío, archivo multibloque, Unicode/espacios/backslash y directorios vacíos |
| C03 | snapshot autosuficiente sin rutas de fuente | round trip borra fuente; comparación de fuente antes/después; ejemplos |
| C04 | valid_id, rechazo de duplicado/ausente | IDs válidos y ordenados, inválidos, ausentes, duplicado |
| C05 | safe_path, kind, inventory, open_regular | enlaces en cada ruta y ancestros, FIFO reales, clasificación de todos los tipos; socket real omitido por EPERM; create limitado con enlace en staging |
| C06 | overlap de fuente y repo | ascendencia, descendencia, igualdad y normalización con `..` |
| C07 | empty_destination, checks de ID/solapamiento | bytes protegidos de destino y snapshot; fallo de publicación de restore inyectado |
| C08 | staging + rename + finally | SIGKILL real tras copiar al menos 4 MiB de archivo de 128 MiB; reintento; fallo de copia inyectado; staging oculto |
| C09 | checksums y validación exacta + restore temporal | alterar/eliminar **cada archivo regular** del snapshot (datos, manifest.json y COMMIT); destino ausente y vacío; extras, directorio vacío eliminado y truncado |
| C10 | Parser, validación de JSON/schema | argumentos/rutas erróneos y manifiesto inseguro incluso recalculando COMMIT; stdout vacío en errores |
| C11 | list_snapshots | repo inexistente/vacío, staging y directorio incompleto ocultos, orden de IDs |
| C12 | documentación SDD y runner | SPEC, PLAN, TASKS, IMPLEMENTATION, README y este informe; logs conservados |
| C13 | argumento opcional y byte_limit | interfaz original en tests base; decimal con ceros; signos/fracciones/Unicode/hex/NaN rechazados sin crear repo |
| C14 | repository_bytes antes de publicar | medición independiente os.walk/lstat; presupuesto exacto; solo metadata en fuente vacía; archivos ajenos anidados y hardlinks; varios snapshots; ejemplos medidos |
| C15 | comprobación de límite + limpieza finally | un byte menos; N inferior/exacto a bytes existentes; rechazos repetidos sin acumulación; snapshot y fuente preservados; reintento del mismo ID; duplicado con límite |
| C16 | flock + clean_staging | SIGKILL y reintento con presupuesto exacto, ausencia de restos; limpieza de staging abandonado incluso con presupuesto bajo; dos create concurrentes con sitio para uno solo |

También se restauraron dos versiones con archivos añadidos, modificados y
eliminados, comprobando la independencia de sus snapshots. Esta entrega no
depende de la revisión técnica externa posterior.
