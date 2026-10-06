# LedgerFold

CLI para consolidar movimientos enteros por cuenta. Requiere Python 3 y usa exclusivamente su biblioteca estándar. Instalación: colocar ledger_fold.py en el directorio de trabajo; no se instalan paquetes. Invocar con `python3 ledger_fold.py` y suministrar la entrada por stdin. No usa red ni lee o escribe archivos externos.

## Entrada y uso

Cada línea UTF-8 contiene un objeto JSON con exactamente `entries`, una lista de objetos con exactamente `account` y `delta`. Ejemplo de invocación desde una shell:

```sh
printf '%s\n' '{"entries":[{"account":"cash","delta":7},{"account":"cash","delta":-7},{"account":"bank","delta":3}]}' | python3 ledger_fold.py
```

Salida contractual esperada para ese ejemplo:

```json
{"balances":{"cash":0,"bank":3},"total":3,"count":3,"zero_accounts":["cash"]}
```

`{"entries":[]}` corresponde a `{"balances":{},"total":0,"count":0,"zero_accounts":[]}`. Dos movimientos de 1000000000000 para `a` corresponden a saldo y total de 2000000000000, count 2 y zero_accounts vacío. Estos ejemplos son expectativas del contrato, no registros de ejecución.

## Límites y errores

El máximo de stdin es 131072 bytes, incluidos espacios y saltos de línea; cada petición admite hasta 2000 movimientos. Las cuentas cumplen `[a-z][a-z0-9_]{0,31}` en ASCII. Cada delta debe ser un entero JSON de valor absoluto como máximo 10^12; bool y float se rechazan. Las sumas usan enteros exactos y no tienen ese límite individual. Se admiten movimientos duplicados, negativos y cero; se conservan todas las cuentas y zero_accounts se ordena lexicográficamente.

Entrada completamente vacía significa cero peticiones. La última línea puede terminar con newline o directamente con EOF. Se rechazan líneas vacías, UTF-8 inválido, JSON mal formado, constantes no finitas, claves duplicadas a cualquier profundidad, campos extra y estructuras o valores incompatibles.

Se prepara toda la salida antes de emitirla. Ante entrada inválida: stdout vacío, stderr exactamente `ledger-fold: invalid input` seguido de newline y exit 2. Un lote válido produce un objeto por petición seguido de newline, stderr vacío y exit 0. Esta entrega contiene programa y documentación; no incluye resultados de ejecución.
