# LedgerFold

CLI Python de biblioteca estándar para consolidar movimientos enteros por cuenta.

## Instalación y uso

Coloque ledger_fold.py en /input/delivery. No requiere paquetes externos. Ejecute:

    /opt/specorganon/venv/bin/python /input/delivery/ledger_fold.py

Suministre NDJSON UTF-8 por stdin; termine la entrada con EOF. Cada línea contiene exactamente un objeto con entries. Cada movimiento contiene exactamente account y delta. No se consultan archivos externos ni se usa red.

## Ejemplos

Entrada:

    {"entries":[{"account":"cash","delta":7},{"account":"cash","delta":-7},{"account":"bank","delta":3}]}

Salida contractual esperada:

    {"balances":{"cash":0,"bank":3},"total":3,"count":3,"zero_accounts":["cash"]}

Para {"entries":[]} se espera {"balances":{},"total":0,"count":0,"zero_accounts":[]} seguido de newline. Dos movimientos de 1000000000000 en la misma cuenta producen un saldo esperado de 2000000000000: el límite se aplica a cada movimiento, no a la suma. Estos ejemplos describen expectativas, sin resultados de ejecución.

## Entrada, límites y errores

El lote admite hasta 131072 bytes y cada petición hasta 2000 movimientos. account debe cumplir [a-z][a-z0-9_]{0,31} con caracteres ASCII. delta debe ser un entero JSON, sin bool ni float, de valor absoluto como máximo 10^12. Se permiten movimientos repetidos, negativos y cero. Se conservan todas las cuentas mencionadas; zero_accounts se ordena lexicográficamente.

La entrada completamente vacía representa cero peticiones. Se admite una última petición sin newline y terminaciones CRLF. Las líneas vacías, UTF-8 inválido, JSON mal formado, claves duplicadas en cualquier objeto, constantes no finitas, campos extra y tipos incorrectos invalidan todo el lote.

El programa valida todas las peticiones antes de consolidar y preparar la salida. Un lote válido produce un objeto JSON por petición con newline, exit 0 y stderr vacío. Ante entrada inválida no emite stdout; escribe exactamente ledger-fold: invalid input seguido de newline en stderr y termina con exit 2.

## Estado de entrega

Este paquete contiene programa y documentación para la etapa program. No incluye pruebas ni evidencia de ejecución. La conformidad efectiva y el consumo de recursos permanecen sin medición.
