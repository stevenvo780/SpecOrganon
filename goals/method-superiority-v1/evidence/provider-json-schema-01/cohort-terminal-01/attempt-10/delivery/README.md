# RangeAudit

CLI de biblioteca estándar para normalizar intervalos enteros semiabiertos [inicio, fin). Instalación: colocar range_audit.py en /input/delivery; no requiere paquetes adicionales. Ejecutar con /opt/specorganon/venv/bin/python /input/delivery/range_audit.py y proporcionar NDJSON por stdin.

Cada línea contiene un objeto con exactamente la clave intervals y una lista de pares [inicio,fin]. Se admiten duplicados y cualquier orden. Una entrada completamente vacía representa cero peticiones. La última línea puede terminar en newline; las líneas vacías son inválidas.

Ejemplo de uso:

```sh
printf '%s\n' '{"intervals":[[1,3],[3,7],[10,12]]}' | /opt/specorganon/venv/bin/python /input/delivery/range_audit.py
```

Salida contractual esperada:

```json
{"merged":[[1,7],[10,12]],"covered":8,"span":[1,12],"gaps":[[7,10]]}
```

Otros controles públicos de contrato:

- {"intervals":[[4,8],[1,2],[2,6],[4,8]]} produce merged [[1,8]], covered 7, span [1,8] y gaps [].
- {"intervals":[]} produce merged [], covered 0, span null y gaps [].
- {"intervals":[[-5,-2],[0,1]]} produce merged [[-5,-2],[0,1]], covered 4, span [-5,1] y gaps [[-2,0]].

merged une solapamientos y adyacencias. covered suma sus longitudes; span abarca sus extremos exteriores; gaps contiene únicamente huecos interiores. La salida contiene exactamente esas cuatro claves, una línea JSON UTF-8 con newline por petición.

Límites: 131072 bytes para todo stdin, hasta 2000 pares por petición y extremos enteros JSON con valor absoluto máximo 10^12 e inicio menor que fin. No se admiten bool, float, claves duplicadas o extra, estructuras incorrectas, UTF-8 inválido ni JSON mal formado.

El lote se valida completo antes de emitir resultados. Cualquier petición inválida exige stdout vacío, stderr exactamente `range-audit: invalid input` seguido de newline y código de salida 2. Un lote válido exige código 0 y stderr vacío. El programa no usa red, archivos externos ni modifica el entorno.

Comando de pruebas de entrega, cuando test_range_audit.py se aporte tras sellar programa y README:

```sh
/opt/specorganon/venv/bin/python /input/delivery/test_range_audit.py
```

Esta entrega corresponde a la etapa program y no incluye pruebas ni resultados de ejecución. Los ejemplos anteriores son expectativas contractuales públicas, sin mediciones de funcionamiento ni afirmaciones de efectos de campo.
