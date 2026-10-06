# TopoPlan

CLI Python para obtener un orden topológico, capas simultáneas y raíces de un grafo dirigido acíclico. Solo utiliza la biblioteca estándar.

## Instalación y ejecución

Coloque topo_plan.py en /input/delivery. No requiere instalar paquetes. Ejecute:

    /opt/specorganon/venv/bin/python /input/delivery/topo_plan.py

Envíe la entrada por stdin y termine con EOF. El programa no consulta la red ni lee o escribe archivos externos.

## Entrada y límites

Use NDJSON UTF-8: un objeto por línea, con exactamente nodes y edges. nodes debe ser una lista de hasta 120 nombres distintos, ASCII, con patrón [a-z][a-z0-9_]{0,15}. edges admite hasta 2000 pares [origen,destino] cuyos nombres estén presentes. Las aristas repetidas cuentan una sola vez; el límite se aplica a la lista recibida antes de deduplicarla. El lote completo puede ocupar hasta 131072 bytes, incluidos espacios y saltos de línea. Stdin completamente vacío representa cero peticiones. El salto de línea final es opcional; las líneas vacías se rechazan.

## Ejemplo contractual

Entrada:

    {"nodes":["z","b","a"],"edges":[["a","b"]]}

Salida esperada según el contrato:

    {"order":["a","b","z"],"layers":[["a","z"],["b"]],"roots":["a","z"]}

order selecciona el menor nombre disponible en cada paso. layers elimina simultáneamente cada ronda y ordena sus miembros; su concatenación puede diferir de order. roots es la primera capa, o [] para un grafo vacío. Los cálculos usan grados independientes.

## Salida y errores

Para un lote válido se emite un objeto por petición seguido de newline, con exactamente order, layers y roots; exit 0 y stderr vacío. Se valida y resuelve todo el lote antes de emitir respuestas.

Cualquier petición inválida produce stdout vacío, exit 2 y stderr exactamente `topo-plan: invalid input` seguido de newline. Se rechazan ciclos, bucles, nodos repetidos, nombres desconocidos, tipos o pares incorrectos, campos extra, claves duplicadas, JSON mal formado, constantes no finitas y UTF-8 inválido, además de los excesos de límites.

Esta entrega contiene programa y documentación de la etapa program. No incluye pruebas ni registros de ejecución; el ejemplo expresa una expectativa contractual.
