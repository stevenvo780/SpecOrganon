# LedgerFold

CLI que consolida movimientos enteros por cuenta. Implementación para Python 3.8 o posterior, solo biblioteca estándar. Requiere stdin, stdout y stderr binarios convencionales y bloqueantes. No usa red, dependencias externas ni abre archivos de datos. La compatibilidad declarada no constituye una ejecución verificada.

## Uso e interfaz

Desde el directorio que contiene el programa:

```sh
python3 -I -B ledger_fold.py
```

Enviar NDJSON UTF-8 por stdin y cerrar la entrada para procesar el lote. No hay opciones de CLI; el programa no interpreta argumentos adicionales. stdout contiene exclusivamente resultados y stderr exclusivamente el diagnóstico de entrada inválida cuando corresponda. También puede importarse sin ejecutar la CLI. `main(stdin=None, stdout=None, stderr=None)` admite streams binarios bloqueantes y devuelve el código de salida; los valores omitidos usan los streams estándar. `fold_batch(data)` recibe bytes, devuelve los bytes de salida y lanza `InvalidInput` ante una entrada inválida.

Cada línea debe contener un objeto con exactamente `entries`, una lista de 0 a 2000 objetos con exactamente `account` y `delta`:

- `account`: cadena ASCII de 1 a 32 caracteres que coincide completamente con `[a-z][a-z0-9_]{0,31}`. Los escapes JSON se decodifican antes de comprobarla.
- `delta`: token entero JSON entre -1000000000000 y 1000000000000, ambos incluidos. No admite bool, float, null ni cadenas. `1.0` y `1e0` se rechazan. Se permiten negativos, duplicados, cero y `-0`.
- El lote completo no puede superar 131072 bytes, incluidos espacios y separadores. No hay un límite adicional al número de peticiones.

Se separan las peticiones únicamente por LF. Se admite CRLF y la última petición sin newline. CR aislado no separa peticiones, aunque puede aparecer como espacio JSON fuera de cadenas. Un LF final no agrega una petición; dos LF finales incluyen una línea vacía y se rechazan. Cero bytes significa cero peticiones. Se permiten los espacios JSON alrededor de cada objeto; una línea vacía o solo de espacios es inválida.

Se rechazan UTF-8 inválido, BOM inicial, JSON mal formado, comentarios, contenido adicional en una línea, campos extra, claves duplicadas en cualquier objeto y constantes NaN/Infinity/-Infinity. Los nombres duplicados se comparan después de interpretar escapes. JSON no permite ceros iniciales repetidos: `00` y `-00` son inválidos. Tokens enteros demasiado grandes se rechazan sin convertirlos a enteros enormes ni modificar opciones globales de Python. Los tokens flotantes se rechazan antes de convertirlos.

Cada petición produce un objeto con exactamente `balances`, `total`, `count` y `zero_accounts`, seguido de LF. `balances` conserva todas las cuentas mencionadas, incluso las de saldo cero. `total` suma los movimientos y `count` cuenta sus elementos. `zero_accounts` contiene las cuentas de saldo cero ordenadas lexicográficamente. Los saldos y el total son enteros exactos; el límite de 10^12 se aplica a cada movimiento, no a los acumuladores. Las peticiones se procesan independientemente y se emiten en su orden de entrada. El orden de claves de los objetos no es parte del contrato.

## Dos ejemplos reproducibles

Estos ejemplos indican comandos y salidas esperadas, no ejecuciones observadas. Los comandos usan un shell POSIX y el directorio del programa.

Ejemplo 1: cancelación y una petición vacía en el mismo lote.

```sh
printf '%s\n' '{"entries":[{"account":"cash","delta":7},{"account":"cash","delta":-7},{"account":"bank","delta":3}]}' '{"entries":[]}' | python3 -I -B ledger_fold.py
```

stdout esperado, con LF después de cada objeto:

```json
{"balances":{"cash":0,"bank":3},"total":3,"count":3,"zero_accounts":["cash"]}
{"balances":{},"total":0,"count":0,"zero_accounts":[]}
```

stderr esperado: vacío. Código de salida esperado: 0.

Ejemplo 2: suma mayor que el límite por movimiento y última línea sin newline.

```sh
printf '%s' '{"entries":[{"account":"a","delta":1000000000000},{"account":"a","delta":1000000000000}]}' | python3 -I -B ledger_fold.py
```

stdout esperado, con LF final:

```json
{"balances":{"a":2000000000000},"total":2000000000000,"count":2,"zero_accounts":[]}
```

stderr esperado: vacío. Código de salida esperado: 0.

## Errores, códigos y atomicidad

Un lote válido termina con código 0 y stderr vacío. Con stdin de cero bytes, stdout también queda vacío.

Si cualquier petición es inválida, hay UTF-8 inválido o el lote supera el límite, el código es 2, stdout queda vacío y stderr contiene exactamente los bytes ASCII `ledger-fold: invalid input\n`, donde `\n` representa un único LF. No se emite traceback por esos errores. Una profundidad JSON excesiva que provoca `RecursionError` se trata como entrada inválida, pues ninguna petición válida requiere tal profundidad.

La lectura admite lecturas cortas y continúa hasta EOF o hasta detectar el byte 131073. Al detectar exceso puede dejar el resto de stdin sin consumir. Toda la validación y serialización concluye antes de escribir stdout, por lo que un prefijo válido seguido de una petición inválida no produce salida parcial.

Esta atomicidad cubre fallos de validación, no fallos del sistema durante una escritura. Errores de E/S, streams no bloqueantes, memoria insuficiente y errores de programación no se convierten en el diagnóstico de entrada inválida; sus códigos y diagnósticos no están definidos por este contrato. Una escritura del lote no garantiza indivisibilidad física.

## Pruebas y límites de evidencia

No se incluye todavía `test_ledger_fold.py` y no se afirma ejecución de ejemplos o pruebas. Primero deben sellarse programa y README mediante el flujo anfitrión; no se aporta un recibo de sello. Después podrá elaborarse la batería separada, sin modificar tests originales, fixtures ni configuración.

Comando fijo previsto para esa batería:

```sh
/opt/specorganon/venv/bin/python -I -B /input/delivery/test_ledger_fold.py
```

La batería deberá cargar `/input/delivery/ledger_fold.py` por ruta absoluta con runpy/importlib, sin depender de sys.path. Su alcance previsto es el contrato C1–C11: transporte y límites, encuadre, JSON estricto, esquema, tipos, consolidación, salida y atomicidad. Incluye límites exactos de bytes y movimientos, tokens numéricos largos inválidos, claves escapadas duplicadas, lotes con fallo final y streams con lecturas cortas. No pretende acreditar rendimiento, resistencia a fallos de infraestructura, compatibilidad medida en todas las versiones de Python ni superioridad o evaluación independiente F. Solo los recibos suministrados por el host podrán acreditar ejecución. Las verificaciones previstas se enlazan en TASKS.md; H permanece separado de D/G.
