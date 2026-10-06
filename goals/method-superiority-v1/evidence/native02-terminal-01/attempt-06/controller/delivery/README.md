# TopoPlan

CLI Python para obtener dos planes independientes de un grafo dirigido acíclico. Usa únicamente la biblioteca estándar; recibe datos por stdin y no abre archivos externos ni utiliza red.

## Instalación y ejecución

Coloque topo_plan.py en /input/delivery. No requiere paquetes adicionales. Ejecute con Python 3:

    /opt/specorganon/venv/bin/python /input/delivery/topo_plan.py

Envíe las peticiones por stdin y cierre el flujo para procesar el lote. La salida se produce después de validar y calcular todas las peticiones.

## Entrada

NDJSON UTF-8: un objeto JSON por línea, con exactamente las claves nodes y edges. nodes contiene nombres distintos que cumplen [a-z][a-z0-9_]{0,15}; edges contiene listas de dos nombres presentes. Las aristas duplicadas cuentan una sola vez. Se admite newline final y terminación CRLF; una línea vacía o compuesta solo de espacios es inválida. Un flujo completamente vacío representa cero peticiones.

## Ejemplos

Entrada:

    {"nodes":["z","b","a"],"edges":[["a","b"]]}

Salida prescrita:

    {"order":["a","b","z"],"layers":[["a","z"],["b"]],"roots":["a","z"]}

Entrada:

    {"nodes":["c","a","b"],"edges":[["a","c"],["b","c"],["a","c"]]}

Salida prescrita:

    {"order":["a","b","c"],"layers":[["a","b"],["c"]],"roots":["a","b"]}

Para {"nodes":[],"edges":[]}, las tres listas de salida están vacías. Estos ejemplos son expectativas contractuales, no registros de ejecución.

## Semántica

order elige en cada paso el menor nombre entre todos los nodos disponibles, mediante una cola de prioridad. layers elimina rondas completas y ordena cada ronda. roots es la primera ronda o []. Ambos cálculos utilizan copias independientes de los grados de entrada y conservan las mismas aristas originales; order no se obtiene concatenando layers.

## Límites y errores

Máximo 131072 bytes de stdin, 120 nodos por petición y 2000 aristas antes de deduplicar. Se rechazan ciclos, bucles, nombres desconocidos o repetidos, tipos incorrectos, pares de longitud distinta de dos, campos extra, claves JSON duplicadas, constantes no finitas, JSON mal formado y UTF-8 inválido.

Un lote válido termina con código 0, stderr vacío y un objeto JSON seguido de newline por petición. Ante cualquier petición inválida, stdout queda vacío, el código es 2 y stderr contiene exactamente `topo-plan: invalid input` seguido de newline. La lectura está acotada a un byte por encima del límite para detectar exceso.

## Estado de entrega

Esta entrega corresponde a la etapa program: programa y documentación, sin pruebas adjuntas ni resultados. La etapa posterior requiere el sellado de estos archivos antes de aportar test_topo_plan.py. No se afirma conformidad medida ni corrección universal.
