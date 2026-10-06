# RangeAudit

CLI de Python para normalizar intervalos enteros semiabiertos [inicio, fin). Requiere Python 3 y sólo su biblioteca estándar; no requiere instalar paquetes. Coloque range_audit.py en /input/delivery.

## Uso e instalación

Ejecute el programa con el intérprete disponible:

```sh
/opt/specorganon/venv/bin/python /input/delivery/range_audit.py
```

Introduzca NDJSON por stdin: un objeto JSON por línea, con exactamente la clave intervals. Termine stdin para procesar el lote completo. También puede conectarlo a la salida de otro proceso:

```sh
printf '%s\n' '{"intervals":[[1,3],[3,7],[10,12]]}' | /opt/specorganon/venv/bin/python /input/delivery/range_audit.py
```

Salida contractual esperada para ese ejemplo:

```json
{"merged":[[1,7],[10,12]],"covered":8,"span":[1,12],"gaps":[[7,10]]}
```

Para {"intervals":[]} se espera {"merged":[],"covered":0,"span":null,"gaps":[]}. Estos ejemplos son controles públicos de contrato, no observaciones de ejecución.

## Formato y límites

El lote admite hasta 131072 bytes en UTF-8. Cada petición admite hasta 2000 pares de enteros JSON, sin bool ni float, con valor absoluto hasta 10^12 e inicio menor que fin. Se permiten duplicados y orden arbitrario. Se fusionan solapamientos y adyacencias; covered es la longitud exacta de la unión, span su envolvente y gaps sus huecos interiores.

Una newline final termina la última petición; una línea adicional vacía se rechaza. La última petición también puede terminar directamente con EOF. Stdin completamente vacío representa cero peticiones. Se rechazan claves duplicadas o extra, JSON mal formado, codificación inválida y líneas vacías.

El programa valida todas las peticiones antes de emitir respuestas. Un lote inválido produce stdout vacío, stderr exactamente `range-audit: invalid input` seguido de newline y código 2. Un lote válido produce una línea JSON con newline por petición, stderr vacío y código 0. Los cálculos usan enteros, sin flotantes. El programa no utiliza red, ficheros externos ni modifica el entorno.

## Pruebas

Programa y README corresponden a la etapa program. El archivo de pruebas corresponde a la etapa posterior, una vez sellados estos archivos. El comando previsto para esa entrega es:

```sh
/opt/specorganon/venv/bin/python /input/delivery/test_range_audit.py
```

Este paquete no contiene pruebas ni resultados de ejecución.
