# TopoPlan

CLI para planificar grafos dirigidos acíclicos mediante NDJSON. Implementación para Python 3.8 o posterior, únicamente con biblioteca estándar. Requiere stdin, stdout y stderr binarios disponibles. No instala dependencias ni incorpora acceso a red o archivos externos; los datos se intercambian por los streams estándar.

## Uso e interfaz

Desde el directorio que contiene el programa:

```sh
python3 -I -B topo_plan.py
```

El programa lee stdin hasta EOF o hasta detectar exceso de tamaño. No tiene opciones de CLI; los argumentos adicionales no se interpretan. Cada línea UTF-8 debe contener un objeto JSON con exactamente las claves `nodes` y `edges`. Se admite whitespace JSON alrededor del objeto, LF y CRLF, y una última línea sin terminador. CR aislado no delimita peticiones. Una entrada de cero bytes representa cero peticiones; una línea vacía o solo whitespace es inválida. Un LF final no añade una petición, pero otro LF consecutivo sí introduce una línea vacía.

Límites inclusivos:

- Stdin completo: 131072 bytes, incluidos whitespace y terminadores. La adquisición lee como máximo 131073 bytes para detectar exceso.
- `nodes`: lista de 0 a 120 nombres distintos. Cada nombre decodificado es ASCII y satisface completamente `[a-z][a-z0-9_]{0,15}`: de 1 a 16 caracteres. Los escapes JSON que producen nombres válidos se aceptan.
- `edges`: lista de 0 a 2000 pares JSON `[origen,destino]`, contados antes de deduplicar. Ambos extremos deben ser cadenas presentes en `nodes`. Las aristas repetidas cuentan una sola vez en el grafo.

Se rechazan bucles, ciclos incluso desconectados, nodos repetidos, extremos desconocidos, tipos incorrectos, pares de longitud distinta de dos, claves ausentes o extra, claves duplicadas en cualquier objeto, JSON mal formado, constantes `NaN`, `Infinity` y `-Infinity`, BOM y UTF-8 inválido. Los rechazos de conversión numérica o profundidad del decodificador también usan el error común; no se eleva el límite de recursión.

Cada petición válida produce exactamente `order`, `layers` y `roots`, en JSON compacto seguido de un byte LF. Se conserva el orden de las peticiones; el orden de las claves no es significativo.

`order` elige en cada paso el menor nombre lexicográfico de todos los nodos disponibles, incluyendo inmediatamente los recién liberados. `layers` agrupa todos los disponibles al comienzo de cada ronda y ordena cada ronda lexicográficamente. Ambos cálculos usan copias independientes de los grados originales y no modifican la adyacencia. `roots` es la primera ronda o `[]`. Para `{"nodes":[],"edges":[]}`, la respuesta es `{"order":[],"layers":[],"roots":[]}`.

## Dos ejemplos reproducibles

Ejecutar estos comandos desde el directorio del programa en un shell POSIX. Las salidas son expectativas del contrato, no resultados de ejecuciones realizadas para esta entrega.

Ejemplo 1: selección lexicográfica global, diferente de concatenar rondas.

```sh
printf '%s\n' '{"nodes":["z","b","a"],"edges":[["a","b"]]}' | python3 -I -B topo_plan.py
```

Stdout esperado, con LF final:

```json
{"order":["a","b","z"],"layers":[["a","z"],["b"]],"roots":["a","z"]}
```

Stderr esperado: vacío. Código de salida esperado: 0.

Ejemplo 2: arista duplicada y convergencia de dos raíces.

```sh
printf '%s\n' '{"nodes":["c","a","b"],"edges":[["a","c"],["b","c"],["a","c"]]}' | python3 -I -B topo_plan.py
```

Stdout esperado, con LF final:

```json
{"order":["a","b","c"],"layers":[["a","b"],["c"]],"roots":["a","b"]}
```

Stderr esperado: vacío. Código de salida esperado: 0.

## Errores y atomicidad

Un lote válido devuelve 0 y deja stderr vacío. Con stdin de cero bytes, también deja stdout vacío.

Si cualquier petición es inválida, stdout queda vacío, el código de salida es 2 y stderr contiene exactamente los 25 bytes ASCII `topo-plan: invalid input\n`, donde `\n` representa un único LF. No se emiten respuestas de peticiones anteriores ni traceback por entradas inválidas.

El programa valida y calcula todo el lote y prepara toda su serialización antes de escribir stdout. Esta atomicidad cubre el rechazo de entrada. No garantiza una transacción ante fallos externos de lectura, escritura, dispositivo o recursos; esos fallos no se convierten en diagnósticos de entrada inválida y no tienen código de salida ni mensaje contractual. Una escritura fallida puede haber emitido parte de una salida ya validada.

## Verificación posterior y límites

Esta entrega no incluye `test_topo_plan.py` y no se ha ejecutado el programa ni una batería. La evidencia suministrada registra aceptación de la revisión del plan, no validación del código. Sellado, revisión del programa, mediciones y auditorías siguen sin acreditarse aquí.

Después del sello del programa y README, el comando fijo previsto para la batería separada es:

```sh
/opt/specorganon/venv/bin/python -I -B /input/delivery/test_topo_plan.py
```

La disponibilidad de ese ejecutable no se ha comprobado. La futura batería deberá cargar el programa por ruta absoluta mediante `runpy` o `importlib`, sin depender de `sys.path`; importar `topo_plan.py` no activa la CLI.

El alcance previsto es V01–V07 de TASKS.md: semántica pública, oráculo independiente para DAG pequeños, independencia y determinismo, esquema y tipos, límites inclusivos, transporte y JSON, ciclos, atomicidad e interfaz. No representa una prueba exhaustiva de todos los grafos o bytes posibles ni una medición de rendimiento. La ausencia de acceso externo requiere también revisión del código. Quedan dos ejecuciones disponibles según el presupuesto suministrado, con timeout de 120 segundos y máximo de 4000 bytes JSON por stream de pruebas; no deben truncarse evidencias ni ampliarse cuotas para aprobar. No se modifican ni se entregan aquí tests originales, fixtures o configuración.
