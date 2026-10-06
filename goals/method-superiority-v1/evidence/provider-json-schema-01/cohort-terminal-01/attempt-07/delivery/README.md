# RangeAudit

CLI Python de biblioteca estándar para normalizar intervalos enteros semiabiertos [inicio, fin). Coloque range_audit.py en /input/delivery; no requiere paquetes adicionales. Ejecute:

```sh
/opt/specorganon/venv/bin/python /input/delivery/range_audit.py < solicitudes.ndjson
```

La CLI lee únicamente stdin. Cada línea NDJSON debe contener un objeto con exactamente la clave intervals y una lista de pares. Un newline final es opcional; las líneas vacías son inválidas. Stdin completamente vacío representa cero peticiones. Se admite UTF-8 estricto y terminación LF o CRLF.

Control público del contrato, sin ejecución del producto:

Entrada:
```json
{"intervals":[[1,3],[3,7],[10,12]]}
```
Salida contractual esperada:
```json
{"merged":[[1,7],[10,12]],"covered":8,"span":[1,12],"gaps":[[7,10]]}
```

Para {"intervals":[]} la salida esperada es {"merged":[],"covered":0,"span":null,"gaps":[]}. Se admiten duplicados, negativos y orden arbitrario. Se fusionan solapamientos y adyacencias; covered suma longitudes exactas, span delimita los extremos y gaps contiene únicamente huecos interiores.

Límites: 131072 bytes en todo stdin, hasta 2000 pares por petición, extremos enteros JSON de magnitud máxima 10^12 e inicio menor que fin. Se rechazan bool, float, pares inválidos, claves duplicadas o adicionales, UTF-8 inválido y JSON mal formado, incluidas constantes no JSON.

Se valida todo el lote antes de emitir. Cualquier petición inválida produce stdout vacío, stderr exactamente `range-audit: invalid input` seguido de newline y código 2. Un lote válido produce una línea JSON con newline por petición, código 0 y stderr vacío. Los enteros se conservan exactamente.

El programa y este README corresponden a la etapa program; test_range_audit.py corresponde a la etapa posterior, tras el sellado. El comando previsto para esa entrega es:

```sh
/opt/specorganon/venv/bin/python /input/delivery/test_range_audit.py
```

No se aportan resultados de ejecución. Los ejemplos son controles públicos documentales del contrato.
