# TopoPlan

CLI para planificar grafos dirigidos acíclicos a partir de un lote NDJSON. Usa Python 3.8 o posterior y únicamente biblioteca estándar. No necesita instalación, dependencias, red ni archivos de datos externos. El programa utiliza exclusivamente stdin, stdout y stderr; la carga normal del intérprete y del módulo corresponde al entorno Python.

## Uso e interfaz

Desde el directorio que contiene el programa:

```sh
python3 -I -B topo_plan.py
```

Enviar las peticiones por stdin y cerrar el stream para completar el lote. La interfaz definida no tiene opciones ni argumentos posicionales; el programa no interpreta argumentos. `-I -B` son opciones del intérprete para aislamiento y ausencia de escritura de bytecode.

La entrada es UTF-8 estricto, con una petición JSON por línea delimitada por LF. Se admite CRLF y una última petición sin LF. Solo un LF final termina la última petición: líneas vacías intermedias o adicionales al final son inválidas. También son inválidas las líneas de solo espacios. Se permiten espacios JSON alrededor del objeto. Cero bytes representan cero peticiones, con ambos streams de salida vacíos y exit 0. Un BOM no se acepta.

Cada objeto tiene exactamente `nodes` y `edges`:

- `nodes`: lista de 0 a 120 cadenas distintas, ASCII, que coinciden íntegramente con `[a-z][a-z0-9_]{0,15}`; longitud de 1 a 16 caracteres. Los escapes JSON que decodifican a un nombre válido se aceptan.
- `edges`: lista de 0 a 2000 pares originales, cada uno una lista de exactamente dos cadenas `[origen,destino]` presentes en `nodes`. Las aristas duplicadas cuentan una sola vez en el grafo, pero todas cuentan para el límite de 2000 pares.
- Stdin completo: máximo 131072 bytes, incluidos espacios y delimitadores, medidos antes de decodificar. Se consumen como máximo 131073 bytes para detectar exceso.

Se rechazan tipos incorrectos, nodos repetidos, nombres desconocidos, bucles y ciclos, incluso en componentes desconectados. Se rechazan JSON mal formado, contenido adicional en una línea, claves duplicadas en cualquier objeto, campos extra o ausentes, constantes `NaN`, `Infinity`, `-Infinity`, números que desbordan a infinito y UTF-8 inválido. Ningún campo admite números, booleanos ni null. Los límites internos del parser para anidamiento y conversión numérica se traducen a entrada inválida; no se cambia la configuración del intérprete.

Por cada petición se emite un objeto JSON compacto con exactamente estas claves y un LF final:

- `order`: orden topológico que elige siempre el menor nombre lexicográfico entre todos los nodos disponibles, incluidos los recién liberados.
- `layers`: rondas independientes, cada una con todos los nodos disponibles al inicio de la ronda, ordenados lexicográficamente. Los liberados durante una ronda pasan a la siguiente.
- `roots`: primera ronda, o `[]` si no hay nodos.

El orden de las claves no es significativo. `order` se calcula con un min-heap y `layers` con otra copia de los grados iniciales. Ambos recorridos preservan el grafo base. Para `{"nodes":[],"edges":[]}`, la salida es `{"order":[],"layers":[],"roots":[]}` seguida de LF.

## Dos ejemplos reproducibles

Estos comandos para un shell POSIX describen entradas y salidas esperadas; no son registros de ejecución. Ejecutarlos desde el directorio del programa.

Ejemplo 1: un nodo recién liberado precede a otro que ya estaba disponible.

```sh
python3 -I -B topo_plan.py <<'EOF'
{"nodes":["z","b","a"],"edges":[["a","b"]]}
EOF
```

Stdout esperado, con LF final:

```json
{"order":["a","b","z"],"layers":[["a","z"],["b"]],"roots":["a","z"]}
```

Ejemplo 2: deduplicación y convergencia de dos predecesores.

```sh
python3 -I -B topo_plan.py <<'EOF'
{"nodes":["c","a","b"],"edges":[["a","c"],["b","c"],["a","c"]]}
EOF
```

Stdout esperado, con LF final:

```json
{"order":["a","b","c"],"layers":[["a","b"],["c"]],"roots":["a","b"]}
```

En ambos ejemplos se espera stderr vacío y exit 0.

## Errores, salida y atomicidad

Un lote válido termina con exit 0 y stderr vacío. Si cualquier petición es inválida, incluso la última, stdout queda vacío, exit es 2 y stderr contiene exactamente los bytes `topo-plan: invalid input\n` (un LF real al final).

Se decodifica el lote completo y se validan, resuelven y serializan todas sus peticiones antes de escribir stdout. No se publica ningún resultado anterior a un error tardío. La atomicidad corresponde a la validación del contenido; una escritura final puede fragmentarse físicamente. Fallos de dispositivos de entrada/salida, interrupciones o agotamiento de recursos quedan fuera de esa garantía y no se convierten en el diagnóstico de entrada inválida; pueden producir errores del intérprete y salida parcial durante una escritura fallida.

## Carga y verificación posterior

Importar el módulo no ejecuta la CLI. `plan_request(request)` recibe un objeto ya decodificado y devuelve el resultado sin modificar la petición. `process_batch(data)` recibe bytes y devuelve bytes sin escribir streams. Ambas funciones lanzan `InvalidInput` por contenido inválido. La interfaz contractual principal es la CLI.

La batería separada `test_topo_plan.py` todavía no se entrega. Después del sellado del programa y README por el host y de la creación de esa batería, el comando previsto es:

```sh
/opt/specorganon/venv/bin/python -I -B /input/delivery/test_topo_plan.py
```

La batería deberá cargar `/input/delivery/topo_plan.py` por ruta absoluta con runpy/importlib, sin depender de sys.path, y usar solo stdlib. Los tests originales, fixtures y configuración deben permanecer inmutables.

Alcance previsto: bytes y fronteras de tamaño; JSON estricto y tipos; límites antes de deduplicar; ciclos y componentes desconectados; independencia de order/layers; códigos de salida, streams y atomicidad de lotes. Para grafos de hasta tres nodos se prevé comparar con enumeración de permutaciones topológicas y rondas por predecesores restantes; para grafos mayores, casos deterministas. Esa cobertura finita no demuestra corrección de todos los grafos ni tolerancia a fallos externos de I/O. El flujo suministrado limita las medidas a dos y los informes propios a 4000 bytes JSON por stream, completos y sin truncar fallos; no son límites de la salida de esta CLI.

No se afirma ejecución de código, resultados de pruebas, sellado ni auditoría independiente. La revisión previa suministrada aceptó los documentos y declaró `tests_executed: false`. Criterios y diseño: [SPEC.md](SPEC.md), [DESIGN.md](DESIGN.md), [TASKS.md](TASKS.md). Trazabilidad de esta entrega: [PROGRAM-TRACE.md](PROGRAM-TRACE.md).
