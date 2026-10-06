# RangeAudit

RangeAudit normaliza intervalos enteros semiabiertos de un lote NDJSON. Requiere Python 3.8 o posterior y solo su biblioteca estándar. El programa utiliza stdin, stdout y stderr; no usa red, archivos externos ni modifica el entorno.

## Interfaz y límites

Ejecutar `python3 -I -B range_audit.py < entrada.ndjson`. Cada línea contiene un objeto JSON con exactamente `intervals`, una lista de hasta 2000 pares `[inicio,fin]`. Los extremos deben ser enteros JSON, excluyendo booleanos y flotantes, con valor absoluto como máximo 1000000000000 e inicio estrictamente menor que fin. Se permiten duplicados y orden arbitrario.

Todo stdin puede ocupar como máximo 131072 bytes, incluyendo separadores. Se exige UTF-8 válido. Las líneas vacías o con solo espacios son inválidas, al igual que las claves duplicadas, claves extra y JSON mal formado. Un stdin de cero bytes representa cero peticiones. Se admite una última línea sin newline y líneas terminadas en LF o CRLF. Un newline final termina la última petición; un segundo newline introduce una línea vacía inválida.

Cada resultado contiene exactamente `merged`, `covered`, `span` y `gaps`. Se fusionan solapamientos y adyacencias; los huecos son interiores. Todos los cálculos usan enteros exactos. Cada resultado se escribe como JSON UTF-8 seguido de newline.

## Ejemplos reproducibles

Desde el directorio que contiene el programa:

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

Estos resultados son expectativas públicas, no ejecuciones observadas.

## Errores y atomicidad

Si cualquier petición es inválida, stdout queda completamente vacío, stderr contiene exactamente `range-audit: invalid input\n` y el estado de salida es 2. El programa prepara todo el resultado en memoria antes de escribir stdout. Un lote válido produce estado 0 y stderr vacío; stdin vacío también produce stdout vacío. Esta atomicidad cubre la validación del lote; no promete recuperación ante fallos del sistema operativo al escribir una salida válida.

## Verificación y alcance

La batería separada se preparará después de esta revisión del programa y README. Su comando fijo será:

```sh
/opt/specorganon/venv/bin/python -I -B /input/delivery/test_range_audit.py
```

El script cargará `/input/delivery/range_audit.py` mediante una ruta absoluta y la biblioteca estándar, sin depender de sys.path. La batería todavía no está incluida y no hay recibos de ejecución ni feedback independiente suministrados. Los criterios previos están en `documents/criteria.md` dentro del paquete documental.

Se prevén comprobaciones de ejemplos, propiedades mediante un oráculo independiente en un dominio pequeño, límites de tamaño y errores con atomicidad. Una batería finita no demuestra ausencia de todos los defectos ni efectos de campo o superioridad entre métodos. El coste temporal de ordenar una petición con n intervalos es O(n log n); el programa conserva entrada y resultados del lote en memoria. No se han medido tiempo, memoria, rendimiento del entorno ni costes monetarios.
