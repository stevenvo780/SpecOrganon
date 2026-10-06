# RangeAudit

RangeAudit normaliza intervalos enteros semiabiertos en lotes NDJSON. Requiere Python 3.8 o posterior y solo la biblioteca estándar. El programa utiliza stdin, stdout y stderr; no usa red, archivos externos ni modifica el entorno.

## Interfaz y límites

Ejecutar `python3 -I -B range_audit.py < entrada.ndjson`. Cada línea contiene un objeto JSON con exactamente la clave `intervals`, cuyo valor es una lista de hasta 2000 pares `[inicio,fin]`. Los extremos deben ser enteros JSON, sin booleanos ni flotantes, con valor absoluto como máximo 1000000000000 e inicio estrictamente menor que fin. Se admiten duplicados y orden arbitrario.

Todo stdin puede ocupar como máximo 131072 bytes, incluidos separadores. Se exige UTF-8 válido. Se rechazan claves duplicadas, claves extra, JSON mal formado y líneas vacías o con solo espacios. Cero bytes representan cero peticiones. Se admiten LF, CRLF y una última línea sin newline. Un newline final termina la última petición; otro newline introduce una línea vacía inválida.

Cada resultado contiene exactamente `merged`, `covered`, `span` y `gaps`. Se fusionan solapamientos y adyacencias, se suma la longitud exacta de los componentes y se enumeran únicamente los huecos interiores. Para una lista vacía, `merged` y `gaps` son listas vacías, `covered` es 0 y `span` es null. Cada resultado se escribe como una línea JSON UTF-8 terminada en newline; los cálculos y las salidas numéricas usan enteros exactos.

## Ejemplos reproducibles

Desde el directorio que contiene el programa, en una shell POSIX:

```sh
printf '%s\n' '{"intervals":[[1,3],[3,7],[10,12]]}' | python3 -I -B range_audit.py
```

Salida esperada, exit 0 y stderr vacío:

```json
{"merged":[[1,7],[10,12]],"covered":8,"span":[1,12],"gaps":[[7,10]]}
```

```sh
printf '%s\n' '{"intervals":[[4,8],[1,2],[2,6],[4,8]]}' | python3 -I -B range_audit.py
```

Salida esperada, exit 0 y stderr vacío:

```json
{"merged":[[1,8]],"covered":7,"span":[1,8],"gaps":[]}
```

Estos ejemplos indican expectativas públicas; no son transcripciones de ejecuciones observadas.

## Errores y atomicidad

Si cualquier petición es inválida, stdout queda completamente vacío, stderr contiene exactamente `range-audit: invalid input` seguido de un newline y el estado de salida es 2. El programa valida y prepara todo el lote antes de escribir stdout. Un lote válido produce estado 0 y stderr vacío; stdin vacío también produce stdout vacío. La atomicidad cubre errores de validación, no fallos del sistema operativo al escribir una salida válida.

## Pruebas y evidencia disponible

La batería separada está incluida en `test_range_audit.py`. En el entorno de evaluación, el comando fijo es:

```sh
/opt/specorganon/venv/bin/python -I -B /input/delivery/test_range_audit.py
```

El script utiliza solo stdlib y ejecuta el programa mediante `runpy` con la ruta absoluta `/input/delivery/range_audit.py`, en procesos Python con `-I -B`, sin depender de sys.path. No requiere fixtures ni configuración adicionales. Ese comando presupone las rutas del entorno de evaluación.

La batería comprueba ejemplos, protocolo de salida y tipos, límites de bytes y cantidad de intervalos, extremos grandes, errores de JSON y UTF-8, claves duplicadas y atomicidad ante errores tardíos. Compara casos de dominio pequeño con un oráculo de posiciones enteras cubiertas, incluyendo combinaciones exhaustivas de dos intervalos y casos pseudoaleatorios reproducibles. El timeout de diez segundos por proceso es un límite operativo de las pruebas.

Los criterios anteriores a la primera medida están en `documents/criteria.md` y su concreción está en `documents/verification.md`, dentro del paquete documental. El feedback suministrado `neutral-0002-feedback` aceptó implementación y criterios, sin ejecutar tests. El recibo suministrado `neutral-0004-measure` registra `passed: true`, exit 0, stderr de cero bytes y stdout de 62 bytes, sin timeout ni streams truncados. El contenido de stdout no está suministrado aquí; no se atribuyen valores al resumen de pruebas ni aceptación semántica G a partir del recibo. Esta edición del README requiere una nueva medida antes de auditar el paquete vigente.

Una batería finita no demuestra ausencia de todos los defectos, F independiente, efectos de campo ni superioridad entre métodos. Ordenar una petición de n intervalos cuesta O(n log n); el programa conserva entrada y resultados del lote en memoria. El recibo anterior registra una duración del trabajo host de aproximadamente 1.936 segundos, que no es una medición aislada del rendimiento del programa. No se suministran mediciones de memoria ni costes monetarios.
