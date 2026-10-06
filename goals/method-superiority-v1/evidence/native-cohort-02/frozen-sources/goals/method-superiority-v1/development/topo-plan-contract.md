# TopoPlan: desarrollo técnico público

Construir topo_plan.py, una CLI Python estándar para planificar un grafo dirigido acíclico. Esta tarea pertenece al desarrollo de fiabilidad; no es una evaluación reservada ni una prueba de superioridad.

Entrada NDJSON UTF-8 por stdin. Cada línea tiene un objeto con exactamente nodes y edges. nodes es una lista de hasta 120 nombres distintos; cada nombre es ASCII y satisface [a-z][a-z0-9_]{0,15}. edges es una lista de hasta 2000 pares [origen,destino] de nombres presentes en nodes. Se permiten aristas duplicadas: contarlas una sola vez. Rechazar bucles, ciclos, nodos repetidos, nombres desconocidos y pares con otra longitud o tipos. El total de stdin no debe superar 131072 bytes. Entrada completamente vacía: cero peticiones. Rechazar líneas vacías, JSON mal formado, constantes no finitas, claves duplicadas, campos extra y UTF-8 inválido.

Salida por petición con exactamente order, layers y roots. order es el orden topológico obtenido eligiendo en cada paso el menor nombre lexicográfico de TODOS los nodos disponibles; no es la concatenación de layers. layers es una lista de listas: en la ronda inicial, todos los nodos sin predecesores; en cada ronda posterior, todos los que quedan disponibles al quitar la ronda anterior. Ordenar lexicográficamente cada ronda. roots es la primera ronda o [] si no hay nodos. No modificar el grafo entre el cálculo independiente de order y layers. Emitir un objeto JSON por petición, seguido de newline. Orden de claves de objeto no significativo.

Ejemplos:
- {"nodes":["z","b","a"],"edges":[["a","b"]]} -> {"order":["a","b","z"],"layers":[["a","z"],["b"]],"roots":["a","z"]}
- {"nodes":["c","a","b"],"edges":[["a","c"],["b","c"],["a","c"]]} -> {"order":["a","b","c"],"layers":[["a","b"],["c"]],"roots":["a","b"]}
- {"nodes":[],"edges":[]} -> {"order":[],"layers":[],"roots":[]}

Si cualquier petición es inválida, validar el lote completo antes de emitir: stdout vacío, stderr exactamente "topo-plan: invalid input\n", exit 2. Lote válido: exit 0 y stderr vacío. Solo biblioteca estándar, sin red, dependencias externas ni lectura/escritura de archivos externos.

Entrega: programa, README útil con instalación, entrada, ejemplos, errores y límites, y test_topo_plan.py con pruebas pertinentes. El programa y README se sellan antes de escribir las pruebas. El argv de pruebas empieza con /opt/specorganon/venv/bin/python y ejecuta /input/delivery/test_topo_plan.py. Solo el ejecutor aislado genera resultados y recibos. Conservar las nueve fases, contenido sustantivo, trazabilidad y revisión independiente. Los ejemplos del contrato son controles públicos, no resultados nativos del producto ni medidas de trabajo libre o SDD.
