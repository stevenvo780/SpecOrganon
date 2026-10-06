# RangeAudit

CLI Python para normalizar intervalos enteros semiabiertos [inicio, fin). Usa solamente la biblioteca estándar. No necesita paquetes, red ni configuración del entorno; el programa consume stdin y escribe stdout/stderr.

## Instalación y uso

Coloque range_audit.py y este README en /input/delivery. Se requiere Python 3. Ejecute:

```sh
/opt/specorganon/venv/bin/python /input/delivery/range_audit.py
```

Suministre NDJSON por stdin: un objeto JSON por línea, con exactamente la clave intervals. Puede terminar la última línea con newline o con fin de entrada. Las líneas vacías, incluidas las que sólo contienen espacios, son inválidas. Una entrada de cero bytes contiene cero peticiones y no produce salida.

Ejemplo con entrada por tubería:

```sh
printf '%s\n' '{"intervals":[[1,3],[3,7],[10,12]]}' | /opt/specorganon/venv/bin/python /input/delivery/range_audit.py
```

Salida esperada según el contrato:

```json
{"merged":[[1,7],[10,12]],"covered":8,"span":[1,12],"gaps":[[7,10]]}
```

Otros ejemplos públicos de contrato, expresados como entrada y salida esperada:

```text
{"intervals":[[4,8],[1,2],[2,6],[4,8]]}
{"merged":[[1,8]],"covered":7,"span":[1,8],"gaps":[]}

{"intervals":[]}
{"merged":[],"covered":0,"span":null,"gaps":[]}

{"intervals":[[-5,-2],[0,1]]}
{"merged":[[-5,-2],[0,1]],"covered":4,"span":[-5,1],"gaps":[[-2,0]]}
```

Los ejemplos son controles públicos de contrato, no mediciones de esta implementación. El orden de las claves de salida no es significativo. Los intervalos se ordenan y se fusionan cuando se solapan o son adyacentes; covered suma sus longitudes, span delimita sus extremos y gaps enumera sólo huecos interiores.

## Errores y límites

Todo stdin debe ser UTF-8 y tener como máximo 131072 bytes, incluidos separadores y espacios. Cada petición admite hasta 2000 pares. Ambos extremos deben ser enteros JSON, excluyendo bool y float, con valor absoluto como máximo 1000000000000 y con inicio menor que fin. Se permiten orden arbitrario y duplicados de intervalos.

Se rechazan claves JSON duplicadas, claves extra, JSON mal formado, constantes no JSON, líneas vacías, tipos incorrectos y excesos de los límites. Un lote que contiene cualquier petición inválida produce stdout completamente vacío, stderr exactamente `range-audit: invalid input` seguido de newline y código de salida 2. El lote se valida y su salida se prepara antes de escribir resultados. Un lote válido produce una línea JSON terminada en newline por petición, código de salida 0 y stderr vacío.

## Pruebas

Esta entrega contiene programa y documentación; test_range_audit.py corresponde a la etapa posterior, después del sellado de ambos archivos. El comando previsto para esa entrega es:

```sh
/opt/specorganon/venv/bin/python /input/delivery/test_range_audit.py
```

No se aportan resultados de ejecución en esta entrega. La conformidad técnica y cualquier efecto sobre SpecOrganon requieren evidencia adicional.
