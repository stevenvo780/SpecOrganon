# LedgerFold

CLI de consolidación de movimientos enteros por cuenta. Requiere Python 3 y utiliza únicamente su biblioteca estándar. No requiere instalación de paquetes. Coloque ledger_fold.py en /input/delivery y ejecútelo con:

```sh
/opt/specorganon/venv/bin/python /input/delivery/ledger_fold.py
```

Proporcione la entrada por stdin; cada línea NDJSON UTF-8 contiene un objeto con exactamente entries, una lista de movimientos con exactamente account y delta. Termine la entrada con EOF. La última línea puede carecer de newline. La entrada completamente vacía representa cero peticiones.

Ejemplo contractual de entrada:

```json
{"entries":[{"account":"cash","delta":7},{"account":"cash","delta":-7},{"account":"bank","delta":3}]}
```

Salida especificada, seguida de newline:

```json
{"balances":{"cash":0,"bank":3},"total":3,"count":3,"zero_accounts":["cash"]}
```

Estos ejemplos describen el contrato; no son registros de ejecución. Cada respuesta contiene exactamente balances, total, count y zero_accounts. Se conservan todas las cuentas mencionadas, incluso las canceladas. zero_accounts se ordena lexicográficamente. Los movimientos duplicados, negativos y cero son válidos. entries vacío produce balances vacío, total y count cero y zero_accounts vacío.

Límites: 131072 bytes en todo stdin, hasta 2000 movimientos por petición, cuentas ASCII que satisfacen [a-z][a-z0-9_]{0,31} y deltas enteros JSON de valor absoluto hasta 1000000000000. Booleanos y floats no son deltas válidos. El límite del delta se aplica a cada movimiento; los saldos y el total usan enteros exactos y pueden superar ese límite.

Se rechazan líneas vacías, UTF-8 inválido, JSON mal formado, constantes no finitas, claves duplicadas en cualquier objeto, campos extra o ausentes y valores fuera de los límites. Se valida y prepara todo el lote antes de emitir. Si cualquier petición es inválida, stdout queda vacío, stderr contiene exactamente `ledger-fold: invalid input` seguido de newline y el código de salida es 2. Un lote válido tiene código 0 y stderr vacío.

El programa lee únicamente stdin y escribe stdout y stderr; no usa red ni archivos externos. Esta entrega corresponde a la etapa program. Las pruebas de entrega y sus resultados no se incluyen en esta etapa.
