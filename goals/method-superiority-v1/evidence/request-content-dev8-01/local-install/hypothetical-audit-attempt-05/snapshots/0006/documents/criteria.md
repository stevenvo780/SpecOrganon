# Criterios previos a cualquier medida propia

Estado observado: los documentos suministrados muestran archivos e historial vacíos, ninguna medida y ningún revisor consumido. Este parche aporta programa y README para feedback independiente; no aporta resultados de ejecución.

C1. Un lote válido produce exactamente una línea JSON por petición, claves exactamente order/layers/roots, exit 0 y stderr vacío. Cero bytes produce stdout vacío; un grafo vacío produce tres listas vacías.

C2. order debe coincidir con una referencia que, en cada paso, busca desde cero todos los nodos restantes cuyos predecesores ya salieron y selecciona el mínimo. En particular, a->b con z aislado exige [a,b,z], mientras layers exige [[a,z],[b]].

C3. layers debe coincidir con una referencia que busca todos los nodos disponibles al comienzo de cada ronda y elimina la ronda completa. Cada ronda está ordenada, roots coincide con la primera y todos los nodos aparecen exactamente una vez. Los duplicados de aristas no cambian resultados. Permutar nodes o edges no cambia resultados.

C4. Rechazar cada categoría pública: nombres no ASCII o fuera del patrón; nodos repetidos; tipos incorrectos; pares de longitud distinta de dos; extremos desconocidos; bucles; ciclos, incluidos componentes cíclicos junto a componentes acíclicos; campos ausentes o extra; claves duplicadas; constantes no finitas; JSON incorrecto; líneas vacías; UTF-8 inválido. Comprobar además 120 frente a 121 nodos, 2000 frente a 2001 pares y exactamente 131072 frente a 131073 bytes.

C5. Para cada lote inválido, comprobar conjuntamente código 2, stdout de cero bytes y stderr exactamente b'topo-plan: invalid input\n'. Incluir una primera petición válida seguida de una inválida, también UTF-8 inválido al final, para comprobar atomicidad real de la CLI.

C6. La batería separada debe cargar el programa mediante ruta absoluta con runpy/importlib, funcionar con Python -I -B, usar solo stdlib y contener todos sus datos y referencias. Las referencias deben derivar disponibilidad de conjuntos de predecesores, sin reutilizar el algoritmo del programa. Los casos deterministas pequeños pueden cubrir exhaustivamente subconjuntos de aristas y validar ciclos y DAGs contra estas referencias.

Razonamiento de implementación: la validación de formas precede a operaciones de conjuntos sobre extremos. Se conservan aristas deduplicadas y grados originales; cada recorrido copia los grados. El heap implementa la prioridad global; las rondas solo avanzan tras retirar toda la ronda actual. La serialización del lote termina antes de escribir stdout. Capturar errores de parseo y profundidad evita trazas para entradas inválidas profundamente anidadas.

Límites de evidencia: ninguna ejecución, tiempo, coste, aceptación semántica G, auditoría independiente F o superioridad está demostrada por este parche. Una futura medida solo respaldará los casos realmente ejecutados y el contenido vigente correspondiente.
