# TopoPlan

Python 3.8+; solo biblioteca estándar. CLI: `python3 -I -B topo_plan.py < entrada.ndjson`. Lee stdin UTF-8 y escribe NDJSON en stdout; no usa red ni archivos de datos externos.

Cada línea contiene exactamente `nodes` y `edges`: hasta 120 nombres distintos ASCII `[a-z][a-z0-9_]{0,15}` y hasta 2000 pares de nombres presentes. Los pares duplicados cuentan para el límite y después se deduplican. Máximo 131072 bytes por lote, incluidos espacios y separadores. Cero bytes produce cero respuestas. Admite LF, CRLF y última línea sin newline; rechaza líneas vacías.

Cada respuesta tiene exactamente `order`, `layers`, `roots`. `order` selecciona el mínimo lexicográfico entre todos los disponibles en cada paso. `layers` elimina rondas completas, ordenadas lexicográficamente. `roots` es la primera ronda o []. Ambos cálculos conservan las aristas y parten de los grados originales.

Ejemplos reproducibles desde el directorio de entrega:

```sh
printf '%s\n' '{"nodes":["z","b","a"],"edges":[["a","b"]]}' | python3 -I -B topo_plan.py
```

Salida esperada:
```json
{"order":["a","b","z"],"layers":[["a","z"],["b"]],"roots":["a","z"]}
```

```sh
printf '%s\n' '{"nodes":["c","a","b"],"edges":[["a","c"],["b","c"],["a","c"]]}' | python3 -I -B topo_plan.py
```

Salida esperada:
```json
{"order":["a","b","c"],"layers":[["a","b"],["c"]],"roots":["a","b"]}
```

Son expectativas, no trazas de ejecución. Un lote válido termina con exit 0, stderr vacío y newline tras cada respuesta. Cualquier entrada inválida produce stdout vacío, stderr exactamente `topo-plan: invalid input\n` y exit 2. Se rechazan ciclos, bucles, tipos/formas/nombres incorrectos, nodos repetidos, extremos desconocidos, campos ausentes o extra, claves duplicadas, constantes no finitas, JSON incorrecto, UTF-8 inválido y exceso de límites. Se valida y serializa el lote completo antes de emitir. La atomicidad cubre errores de entrada, no fallos del sistema operativo o de escritura.

Pruebas separadas:
```sh
/opt/specorganon/venv/bin/python -I -B /input/delivery/test_topo_plan.py
```

La batería contiene todos sus datos y referencias, carga el programa mediante runpy por ruta absoluta y comprueba procesos CLI aislados. Enumera todos los grafos sin bucles sobre cuatro nodos; además cubre ejemplos, permutaciones, duplicados, límites y categorías inválidas con comprobación de atomicidad. No cubre exhaustivamente entradas mayores, rendimiento ni fallos del sistema operativo. El feedback suministrado neutral-0002-feedback aceptó sin ejecutar pruebas. No hay recibos de medidas suministrados. Criterios: documents/criteria.md; alcance: documents/measurement-scope.md. Estas pruebas no acreditan aceptación semántica G, auditoría final F ni superioridad.

Lee como máximo 131073 bytes. Cada recorrido cuesta O(E + V log V), con E aristas únicas. Mantiene el lote acotado y las respuestas en memoria. Los costes reales de tiempo, memoria y arranque son desconocidos.
