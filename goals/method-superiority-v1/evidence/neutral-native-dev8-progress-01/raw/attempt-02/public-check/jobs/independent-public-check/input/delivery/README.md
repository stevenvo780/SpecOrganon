# RangeAudit

CLI de biblioteca estándar que normaliza intervalos enteros semiabiertos `[inicio, fin)`. Esta entrega es desarrollo técnico público; no demuestra efectos de campo ni superioridad.

## Entorno e invocación

Python 3.8 o posterior, con flujos estándar binarios normales. No necesita paquetes adicionales. Ejecutar desde el directorio que contiene el programa:

```sh
python3 -I -B range_audit.py < entrada.ndjson
```

La interfaz de peticiones es exclusivamente stdin; no hay opciones implementadas. El programa no interpreta argumentos adicionales. Durante su ejecución no abre archivos de datos, usa red ni modifica el entorno. La redirección del ejemplo la realiza el shell.

## Entrada y límites

Todo stdin debe ser un lote finito UTF-8 estricto de como máximo **131072 bytes**, incluyendo espacios y separadores. El lector continúa ante lecturas cortas y lee como máximo 131073 bytes para detectar exceso. Cero bytes representa cero peticiones: salida vacía, stderr vacío y exit0.

Cada línea contiene un único objeto JSON con exactamente la clave `intervals`. Su valor es una lista de entre 0 y **2000** pares `[inicio, fin]`. Cada par es una lista de exactamente dos enteros JSON, con valor absoluto <= **1000000000000** e inicio < fin. Se admiten duplicados, negativos y orden arbitrario. Bool, float —incluida notación exponencial—, cadenas y null no son extremos válidos. No se convierten tipos.

Se rechazan claves duplicadas, incluso en objetos anidados, claves adicionales, raíces diferentes de objeto, JSON mal formado, valores concatenados, NaN, Infinity y BOM. El separador de líneas es LF. CRLF funciona porque el CR es espacio JSON; CR por sí solo no separa peticiones. Se admite la última línea sin LF. Un LF final termina la última petición; dos LF finales contienen una línea vacía inválida. También son inválidas las líneas vacías iniciales, intermedias y las que solo contienen espacios. No se omiten líneas.

## Salida

Por petición válida se emite una línea JSON UTF-8 terminada en LF, en el orden de entrada, con exactamente estas claves:

- `merged`: pares ordenados y fusionados por solapamiento o adyacencia.
- `covered`: suma exacta de las longitudes de los intervalos fusionados.
- `span`: `[mínimo inicio, máximo fin]`, o null para la lista vacía.
- `gaps`: huecos entre intervalos fusionados, ordenados, sin regiones exteriores.

Todos los números emitidos son enteros exactos. El orden de claves no es significativo. La longitud del span y covered pueden alcanzar 2000000000000. La lista vacía produce `{"merged":[],"covered":0,"span":null,"gaps":[]}`.

## Dos ejemplos reproducibles

Son expectativas públicas, no ejecuciones observadas. Ejecutar desde el directorio del programa con un shell que tenga `printf` y Python 3.

Ejemplo 1:

```sh
printf '%s\n' '{"intervals":[[1,3],[3,7],[10,12]]}' | python3 -I -B range_audit.py
```

stdout esperado, con LF final:

```json
{"merged":[[1,7],[10,12]],"covered":8,"span":[1,12],"gaps":[[7,10]]}
```

stderr esperado: vacío. Estado esperado del programa: 0.

Ejemplo 2:

```sh
printf '%s\n' '{"intervals":[[4,8],[1,2],[2,6],[4,8]]}' | python3 -I -B range_audit.py
```

stdout esperado, con LF final:

```json
{"merged":[[1,8]],"covered":7,"span":[1,8],"gaps":[]}
```

stderr esperado: vacío. Estado esperado del programa: 0.

## Errores, estados y atomicidad

Con flujos operativos, cualquier error de entrada hace que stdout permanezca completamente vacío, stderr sea exactamente `range-audit: invalid input\n` y el estado sea **2**. Esto incluye exceso de bytes, UTF-8 inválido, errores de análisis, límites internos de conversión numérica o profundidad del analizador y violaciones de estructura o intervalos. Un lote enteramente válido termina con **0** y stderr vacío.

Se lee y valida todo el lote antes de normalizar y serializar todos los resultados en memoria. Solo después se publica stdout. Así, una petición inválida posterior a otra válida invalida todo el lote sin publicar resultados parciales.

La atomicidad cubre errores de entrada. No garantiza una transacción física frente a errores de E/S, interrupciones o falta de memoria. Los errores operativos no se traducen al mensaje de entrada inválida: se propagan al intérprete, que normalmente termina con estado 1 y diagnóstico. Una escritura fallida puede haber publicado bytes antes del fallo.

La ordenación y barrido cuestan O(n log n) tiempo y O(n) memoria por petición, con n <= 2000. Se conservan el lote validado y su salida serializada en memoria; no se enumeran puntos del rango ni se utilizan archivos temporales.

## Verificación y límites de evidencia

La evidencia suministrada contiene aceptación de la revisión previa de SPEC.md, DESIGN.md y TASKS.md, con `tests_executed=false`. No contiene ejecución del programa, medición, sello de programa/README ni revisión favorable de esta implementación. Esta respuesta no aporta tests.

Después del sellado de programa y README por el host, corresponde preparar la batería separada `test_range_audit.py`, con biblioteca estándar y carga del programa por ruta absoluta mediante runpy/importlib, sin depender de sys.path. El comando fijado para esa fase es:

```sh
/opt/specorganon/venv/bin/python -I -B /input/delivery/test_range_audit.py
```

La batería aún no se entrega; el comando documenta una fase posterior. Su alcance previsto comprende límites de bytes y cardinalidad, transporte y separadores, rechazos de JSON/tipos, fusión, métricas, orden de resultados y atomicidad del lote. Para dominios pequeños se prevé un oráculo independiente por conjuntos; para extremos grandes, expectativas aritméticas. Los tests originales, fixtures y configuración se conservan inmutables. El presupuesto suministrado indica dos medidas restantes y streams completos de máximo 4000 bytes JSON por stream; no se afirma haber consumido medidas ni generado recibos. Estos controles no prueban disponibilidad bajo fallos operativos, efectos de campo o superioridad.

La trazabilidad de esta entrega se registra en [IMPLEMENTATION.md](IMPLEMENTATION.md); los criterios y alternativas originales permanecen en el contexto suministrado.
