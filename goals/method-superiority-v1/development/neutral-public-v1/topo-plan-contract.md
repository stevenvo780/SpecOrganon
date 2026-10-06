# TopoPlan: desarrollo técnico público

Construir topo_plan.py, una CLI Python estándar para planificar un grafo dirigido acíclico. Esta tarea pertenece al desarrollo de fiabilidad; no es una evaluación reservada ni una prueba de superioridad.

Entrada NDJSON UTF-8 por stdin. Cada línea tiene un objeto con exactamente nodes y edges. nodes es una lista de hasta 120 nombres distintos; cada nombre es ASCII y satisface [a-z][a-z0-9_]{0,15}. edges es una lista de hasta 2000 pares [origen,destino] de nombres presentes en nodes. Se permiten aristas duplicadas: contarlas una sola vez. Rechazar bucles, ciclos, nodos repetidos, nombres desconocidos y pares con otra longitud o tipos. El total de stdin no debe superar 131072 bytes. Entrada completamente vacía: cero peticiones. Rechazar líneas vacías, JSON mal formado, constantes no finitas, claves duplicadas, campos extra y UTF-8 inválido.

Salida por petición con exactamente order, layers y roots. order es el orden topológico obtenido eligiendo en cada paso el menor nombre lexicográfico de TODOS los nodos disponibles; no es la concatenación de layers. layers es una lista de listas: en la ronda inicial, todos los nodos sin predecesores; en cada ronda posterior, todos los que quedan disponibles al quitar la ronda anterior. Ordenar lexicográficamente cada ronda. roots es la primera ronda o [] si no hay nodos. No modificar el grafo entre el cálculo independiente de order y layers. Emitir un objeto JSON por petición, seguido de newline. Orden de claves de objeto no significativo.

Ejemplos:
- {"nodes":["z","b","a"],"edges":[["a","b"]]} -> {"order":["a","b","z"],"layers":[["a","z"],["b"]],"roots":["a","z"]}
- {"nodes":["c","a","b"],"edges":[["a","c"],["b","c"],["a","c"]]} -> {"order":["a","b","c"],"layers":[["a","b"],["c"]],"roots":["a","b"]}
- {"nodes":[],"edges":[]} -> {"order":[],"layers":[],"roots":[]}

Si cualquier petición es inválida, validar el lote completo antes de emitir: stdout vacío, stderr exactamente "topo-plan: invalid input\n", exit 2. Lote válido: exit 0 y stderr vacío. Solo biblioteca estándar, sin red, dependencias externas ni lectura/escritura de archivos externos.


Entrega común de desarrollo N/S: programa indicado, README útil con entorno, interfaz, límites, dos ejemplos completos, errores, atomicidad y comando de pruebas; criterios y trazas en la estructura elegida por el método. N elige notas y estrategia propias. S prepara SPEC.md, DESIGN.md y TASKS.md con alternativas y enlaces, revisados antes del programa. H se audita aparte de D/G. El flujo provisional registra notas/criterios antes del programa; no representa trabajo libre irrestricto.

Programa y README se sellan antes de una batería separada test_topo_plan.py. Solo stdlib; se ejecuta /opt/specorganon/venv/bin/python -I -B /input/delivery/test_topo_plan.py. Cargar el programa por ruta absoluta usando runpy/importlib; no depender de sys.path. Los tests originales/fixtures/config quedan inmutables. El host genera los recibos; no afirmar ejecución previa ni F independiente. El autor conserva autonomía de estrategia y descomposición dentro de estos límites. Ninguna fase del engine T se exige a N/S. Los ejemplos son expectativas públicas, no ejecuciones medidas.
