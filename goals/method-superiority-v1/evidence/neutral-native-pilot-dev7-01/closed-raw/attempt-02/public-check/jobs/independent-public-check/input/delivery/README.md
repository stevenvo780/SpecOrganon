# RangeAudit

CLI para normalizar intervalos enteros semiabiertos `[inicio, fin)`. Usa ordenación y barrido, fusionando solapamientos y adyacencias. El desarrollo es público; esta entrega no acredita efectos de campo ni superioridad.

## Entorno y ejecución

Entorno objetivo: Python 3.8 o posterior, únicamente biblioteca estándar. No hay dependencias instalables. La versión concreta del intérprete del host no consta en la evidencia suministrada; no se ha ejecutado este programa en esta entrega.

Con el artefacto situado en `/input/delivery/range_audit.py`:

```sh
python3 -I -B /input/delivery/range_audit.py
```

La CLI lee stdin binario hasta EOF y escribe stdout/stderr binarios. No ofrece opciones; los argumentos adicionales no se interpretan. No usa red, archivos externos de datos ni modifica el entorno. `-B` evita la generación de bytecode por el intérprete.

## Entrada y límites

Entrada NDJSON UTF-8 estricta, separada exclusivamente por LF. Cada registro debe ser un objeto JSON con exactamente la clave `intervals`. Su valor es una lista de entre 0 y 2000 pares, cada uno una lista de exactamente dos enteros JSON. Se exige `abs(inicio) <= 1000000000000`, `abs(fin) <= 1000000000000` e `inicio < fin`. Se permiten negativos, duplicados y orden arbitrario.

Se rechazan bool, float incluso integral, notación exponencial, cadenas, null, constantes NaN/Infinity, claves extra o ausentes, claves duplicadas en cualquier objeto —también equivalentes tras decodificar escapes—, JSON incompleto y valores adicionales en una misma línea.

El límite de todo stdin es 131072 bytes, incluidos espacios y separadores. Se leen como máximo 131073 bytes para detectar exceso, continuando tras lecturas cortas. La entrada de cero bytes representa cero peticiones válidas. Una línea vacía o de solo espacios es inválida. Se acepta espacio JSON alrededor del objeto, CRLF y un último registro sin LF. Un LF terminal cierra el registro; dos LF consecutivos contienen una línea vacía inválida. No se acepta BOM UTF-8. Los separadores Unicode no dividen registros.

## Salida

Por petición válida se escribe un objeto JSON compacto UTF-8 seguido de LF, en el orden de entrada, con exactamente estos campos:

- `merged`: intervalos ordenados y fusionados por solapamiento o adyacencia.
- `covered`: suma exacta de las longitudes fusionadas.
- `span`: `[mínimo inicio, máximo fin]`, o `null` para una lista vacía.
- `gaps`: huecos estrictamente positivos entre intervalos fusionados, en orden; no incluye el exterior del span.

No se generan flotantes. Para `{"intervals":[]}` el resultado es `{"merged":[],"covered":0,"span":null,"gaps":[]}` seguido de LF. El orden de claves no es significativo. La aritmética usa enteros Python; covered y longitud del span no superan 2000000000000.

## Dos ejemplos reproducibles

Son expectativas públicas del contrato, no ejecuciones observadas. Los comandos usan un shell con `printf` y el artefacto en la ruta indicada.

Ejemplo 1, adyacencia y hueco:

```sh
printf '%s\n' '{"intervals":[[1,3],[3,7],[10,12]]}' | python3 -I -B /input/delivery/range_audit.py
```

Stdout esperado, con LF final:

```json
{"merged":[[1,7],[10,12]],"covered":8,"span":[1,12],"gaps":[[7,10]]}
```

Stderr esperado: vacío. Código esperado del proceso Python: 0.

Ejemplo 2, extremos negativos:

```sh
printf '%s\n' '{"intervals":[[-5,-2],[0,1]]}' | python3 -I -B /input/delivery/range_audit.py
```

Stdout esperado, con LF final:

```json
{"merged":[[-5,-2],[0,1]],"covered":4,"span":[-5,1],"gaps":[[-2,0]]}
```

Stderr esperado: vacío. Código esperado del proceso Python: 0.

## Errores, salida y atomicidad

Si todo el lote es válido: exit 0, stderr vacío y una línea por petición; para cero bytes, ambos streams quedan vacíos.

Si cualquier registro es inválido, incluidos exceso de tamaño o UTF-8 inválido: exit 2, stdout completamente vacío y stderr exactamente los bytes ASCII/UTF-8 `range-audit: invalid input\n`, donde `\n` representa un único LF. No se imprime traceback para esos errores. La profundidad excesiva del JSON y los errores de conversión de enteros del parser se tratan como entrada inválida sin cambiar límites globales de Python.

Se valida todo el lote antes de normalizarlo y se prepara toda la salida antes de su primera escritura. Por tanto, un registro inválido al final tampoco deja resultados anteriores en stdout. La atomicidad cubre errores de entrada. Fallos de lectura/escritura del sistema, interrupciones y agotamiento de recursos no tienen código o diagnóstico contractual y no se capturan como entrada inválida; pueden impedir completar la salida. stdout no es una transacción del dispositivo.

## Interfaz para la batería posterior

El bloque `if __name__ == "__main__"` permite cargar el programa por ruta absoluta con `runpy.run_path('/input/delivery/range_audit.py')` o importlib sin arrancar la CLI, siempre que no se use el nombre `__main__` para esa carga.

`read_limited(stream)` recibe un stream binario bloqueante y devuelve bytes acotados. `parse_batch(data)` recibe bytes y devuelve las listas de intervalos de todas las peticiones validadas. `normalize(intervals)` recibe una lista ya validada y devuelve los cuatro campos; no modifica la entrada y no valida argumentos arbitrarios. `prepare_output(data)` recibe bytes y devuelve los bytes completos de salida. Las funciones de lectura/validación señalan incumplimientos mediante `InvalidInput`. `main()` usa los streams del proceso y devuelve 0 o 2.

La normalización cuesta O(n log n) tiempo y O(n) memoria por petición, n <= 2000. Se conserva el lote validado y la salida completa en memoria para la atomicidad; el límite de stdin no constituye un límite idéntico de memoria o de bytes de salida.

## Pruebas posteriores y límites de evidencia

No se entrega `test_range_audit.py` todavía. Programa y README deben ser sellados por el host antes de redactar esa batería. No se aporta recibo de sellado ni ejecución del programa. El historial suministrado sí contiene aceptación de la revisión del plan, con `tests_executed=false`; esa revisión no valida la implementación.

Comando fijo previsto, solo cuando exista la batería separada:

```sh
/opt/specorganon/venv/bin/python -I -B /input/delivery/test_range_audit.py
```

La batería deberá usar solo stdlib y cargar el programa por ruta absoluta mediante runpy/importlib, sin depender de sys.path. Se conservarán los tests originales, fixtures y configuración. La cobertura prevista en TASKS.md incluye límites de bytes/cantidad/extremos, formato y duplicados JSON, encuadre, precisión entera, normalización y atomicidad de lotes. Para dominios pequeños se prevén oráculos independientes mediante conjuntos de puntos; para extremos grandes, expectativas analíticas. No será una prueba exhaustiva de todas las entradas ni de fallos del dispositivo, rendimiento o efectos de campo. El presupuesto suministrado indica dos medidas restantes y un máximo de 4000 bytes JSON por stream propio; se conservará evidencia completa, sin truncarla para aparentar cumplimiento.

Criterios y alternativas: SPEC.md y DESIGN.md del plan suministrado. Estado de esta entrega y correspondencia con el programa: PROGRAM-TRACE.md.
