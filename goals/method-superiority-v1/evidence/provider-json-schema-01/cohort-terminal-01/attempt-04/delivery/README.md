# RangeAudit

CLI Python para normalizar intervalos enteros semiabiertos [inicio, fin). Requiere Python 3 y únicamente su biblioteca estándar; no requiere instalar paquetes. Coloque range_audit.py en /input/delivery y ejecútelo con:

    /opt/specorganon/venv/bin/python /input/delivery/range_audit.py

La entrada llega exclusivamente por stdin en UTF-8 y formato NDJSON: cada línea contiene un objeto con exactamente la clave intervals. Puede terminar la última línea con newline. Una entrada de cero bytes representa cero peticiones; una línea vacía o formada sólo por espacios es inválida.

Ejemplo de invocación:

    printf '%s\n' '{"intervals":[[1,3],[3,7],[10,12]]}' | /opt/specorganon/venv/bin/python /input/delivery/range_audit.py

Salida contractual:

    {"merged":[[1,7],[10,12]],"covered":8,"span":[1,12],"gaps":[[7,10]]}

Otros controles públicos del contrato, sin ejecución declarada:

- [[4,8],[1,2],[2,6],[4,8]] produce merged=[[1,8]], covered=7, span=[1,8], gaps=[].
- [] produce merged=[], covered=0, span=null, gaps=[].
- [[-5,-2],[0,1]] produce merged=[[-5,-2],[0,1]], covered=4, span=[-5,1], gaps=[[-2,0]].

Los intervalos se ordenan y fusionan por solapamiento o adyacencia. covered suma longitudes exactas; gaps incluye sólo huecos interiores. El orden de claves JSON no es significativo. Cada respuesta termina en newline.

Límites: 131072 bytes para todo stdin, hasta 2000 pares por petición y extremos de valor absoluto <=10^12, con inicio<fin. Los extremos deben ser enteros JSON: bool y float se rechazan. Se admiten duplicados de intervalos y orden arbitrario. Se rechazan claves JSON duplicadas o extra, estructuras incorrectas, JSON mal formado, UTF-8 inválido y líneas vacías.

Se valida todo el lote antes de emitir. Si alguna petición es inválida, stdout queda vacío, stderr contiene exactamente `range-audit: invalid input` seguido de newline y el código de salida es 2. Un lote válido termina con código 0 y stderr vacío.

Comando de pruebas para la entrega de la etapa tests:

    /opt/specorganon/venv/bin/python /input/delivery/test_range_audit.py

Esta entrega de la etapa program contiene únicamente programa y README. El archivo de pruebas corresponde a la siguiente etapa, después del sellado de estos dos archivos. No se declara ejecución ni resultado de pruebas, rendimiento, superioridad o beneficio de campo.
