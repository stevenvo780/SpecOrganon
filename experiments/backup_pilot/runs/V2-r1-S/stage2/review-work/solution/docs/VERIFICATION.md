# Verificación de entrega V2, etapa dos

Directorio de trabajo: `/trial`. Intérprete: `/usr/local/bin/python3.12`,
Python 3.12.15. Se ejecutaron pruebas propias y ejemplos, sin dependencias,
red, credenciales, intervención humana o resultados de evaluación reservada.
Las pruebas generan sus datos en `solution/tests/.work` y eliminan sus
temporales al terminar.

## Comandos y resultados conservados

| Ejecución | Comando ejecutado desde `/trial` | Resultado | Registro |
| --- | --- | --- | --- |
| Línea base antes de adaptar código | `/usr/local/bin/python3.12 -m unittest discover -s solution/tests -v` | 18 casos en 7.696 s: 17 pasan, 1 error al preparar socket Unix (EPERM); salida 1 | [baseline.log](../tests/baseline.log) |
| Suite ampliada de etapa dos | `/usr/local/bin/python3.12 -m unittest discover -s solution/tests -v` | 26 casos en 7.729 s: 25 pasan, 1 omitido explícitamente por socket Unix prohibido; salida 0 | [results-v2.log](../tests/results-v2.log) |
| Ejemplos CLI V2 | `/usr/local/bin/python3.12 solution/tests/examples.py` | Todas las comprobaciones pasan; salida 0 | [examples-v2.log](../tests/examples-v2.log) |

Los registros incluyen el comando, versión de Python, stdout/stderr y código
de salida. El registro de ejemplos incluye además cada invocación CLI concreta,
sus argumentos, respuestas JSON y errores esperados. `tests/results.log` es
un registro parcial recibido de la etapa previa y no se usa como evidencia
de éxito de la entrega actual.

## Evidencia por criterios

- AC01–AC14: se conservan casos de interfaz inicial sin N, Unicode/espacios,
  bytes arbitrarios, directorios vacíos, versiones con adición/modificación/
  eliminación, fuente intacta, eliminación de fuente antes de restaurar,
  IDs inválidos/existentes, solapamientos, symlinks y destinos protegidos.
  La corrupción de cada archivo regular del snapshot se ensaya con alteración,
  truncado, eliminación y adición de bytes; verify y restore deben rechazar.
  Se comprueban inventarios y manifiestos inválidos, errores de copia y SIGKILL.
- AC15: formato inválido de N y argumento ausente fallan como errores de uso
  antes de crear repo; cero es sintaxis válida pero no cubre la metadata.
  La suite anterior sigue usando create sin N.
- AC16: el límite exacto se deriva de un repo de control independiente;
  N = tamaño - 1 rechaza y N = tamaño acepta. Un límite que solo cubre datos
  rechaza. Un `.lock` no vacío se conserva y cuenta en la admisión.
  El oráculo suma `lstat().st_size` sin usar funciones del producto.
- AC17: límites inferiores al repo previo o a la nueva copia se prueban
  repetidamente con comparación de todos los bytes del repo y fuente;
  no aparece el ID rechazado ni quedan bytes nuevos. El mismo ID se reintenta
  con límite suficiente y restaura correctamente la nueva versión.
- AC18: se limpian huérfanos tanto ante rechazo como ante éxito. SIGKILL real
  interrumpe una copia de 128 MiB con límite; versiones previas siguen exactas
  y retry cumple N. Dos procesos simultáneos con capacidad para una sola
  versión producen exactamente un éxito, el total correcto y staging vacío.

Los nombres de las pruebas por criterio se conservan en SPECIFICATION.md.

## Resultados observables de los ejemplos

1. V1 consume 662 bytes (datos y metadata) con N = 100000.
2. Tras V2, el repositorio consume 1082 bytes.
3. Create V3 con N = 1081 retorna código 1 y JSON de error. La comparación
   comprueba árbol y bytes íntegros del repo, sin crecimiento residual.
4. Retry V3 con N = 100000 retorna `{"id":"v3"}`. Total final: 1361 bytes.
5. List devuelve `v1`, `v2`, `v3` ordenados. Después de eliminar la fuente,
   verify y restore de las tres versiones retornan éxito y sus árboles
   coinciden exactamente con los inventarios y bytes esperados.
6. Restaurar sobre V1 no vacía se rechaza y conserva todos los bytes.

## Límites de la evidencia

El sandbox permite FIFO pero rechaza `socket.bind` con EPERM. Ese único caso
queda omitido de forma explícita, sin afirmar que se probó con socket real.
El código rechaza todos los tipos ajenos a directorios/archivos regulares.
No se atribuyen resultados a pruebas externas o reservadas.

El hash SHA-256 de CONTRACT.md leído al comienzo y comprobado al cierre es
`8adcc50d4a0b8411195837403c0f8cbc5327e1e3e8da3ac943ec4d708a0019c1`.
La comprobación final, presencia de documentos y sintaxis de los scripts
se registran en [delivery-check.log](../tests/delivery-check.log).
