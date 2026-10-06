# RangeAudit

CLI Python 3 para normalizar intervalos enteros semiabiertos [inicio, fin). Usa solamente biblioteca estándar. No requiere instalación de paquetes: coloque range_audit.py en /input/delivery y ejecútelo con Python. El programa lee stdin y escribe stdout/stderr; no usa red, archivos externos ni modifica el entorno.

## Uso y NDJSON

Cada línea contiene un objeto JSON con exactamente la clave intervals. Puede enviarse más de una petición por stdin. Ejemplo de comando:

    printf '%s\n' '{"intervals":[[1,3],[3,7],[10,12]]}' | /opt/specorganon/venv/bin/python /input/delivery/range_audit.py

Salida esperada según el contrato:

    {"merged":[[1,7],[10,12]],"covered":8,"span":[1,12],"gaps":[[7,10]]}

Para {"intervals":[]} la respuesta esperada es:

    {"merged":[],"covered":0,"span":null,"gaps":[]}

Estos ejemplos son controles públicos de contrato, sin observaciones de ejecución. merged une solapamientos y adyacencias; covered suma longitudes exactas; span contiene los extremos exteriores; gaps contiene únicamente huecos interiores. Cada respuesta termina en newline. El orden de claves no es significativo.

## Errores y límites

Todo stdin debe ser UTF-8 y ocupar como máximo 131072 bytes. Cada lista admite hasta 2000 pares, con extremos enteros JSON de valor absoluto <=10^12 e inicio<fin. Se permiten duplicados y cualquier orden. Se rechazan bool, float, claves duplicadas o adicionales, JSON mal formado y líneas vacías. Se admite una última línea sin newline; un newline final termina la última petición. Stdin completamente vacío representa cero peticiones.

El lote completo se valida antes de producir salida. Cualquier petición inválida causa stdout vacío, stderr exactamente `range-audit: invalid input` seguido de newline y código 2. Un lote válido termina con código 0 y stderr vacío.

## Pruebas posteriores

El archivo de pruebas corresponde a la etapa tests, posterior al sellado del programa y este README. Su comando previsto es:

    /opt/specorganon/venv/bin/python /input/delivery/test_range_audit.py

Este paquete de etapa program no contiene pruebas ni resultados de ejecución. La conformidad permanece sin demostrar.
