# LedgerFold: desarrollo técnico público

Construir ledger_fold.py, una CLI Python estándar para consolidar movimientos enteros por cuenta. Esta tarea pertenece al desarrollo de fiabilidad; no es una evaluación reservada ni una prueba de superioridad.

Entrada NDJSON UTF-8 por stdin. Cada línea contiene un objeto con exactamente entries, una lista de hasta 2000 objetos con exactamente account y delta. account es una cadena ASCII que satisface [a-z][a-z0-9_]{0,31}; delta es un int JSON, excluidos bool y float, de valor absoluto <=10^12. Se permiten movimientos duplicados, negativos y de importe cero. El límite de 10^12 se aplica a cada movimiento, no a la suma. El total de stdin no debe superar 131072 bytes. Entrada completamente vacía: cero peticiones. Rechazar líneas vacías, JSON mal formado, constantes no finitas, claves duplicadas en cualquier objeto, campos extra y UTF-8 inválido.

Salida por petición con exactamente balances, total, count y zero_accounts. balances es un objeto con todas las cuentas mencionadas, incluso las que suman cero, y sus saldos enteros exactos. total suma todos los movimientos; count es su número. zero_accounts es una lista ordenada lexicográficamente de cuentas con saldo cero. Emitir un objeto JSON por línea, seguido de newline. El orden de claves de los objetos no afecta el resultado.

Ejemplos:
- {"entries":[{"account":"cash","delta":7},{"account":"cash","delta":-7},{"account":"bank","delta":3}]} -> {"balances":{"cash":0,"bank":3},"total":3,"count":3,"zero_accounts":["cash"]}
- {"entries":[]} -> {"balances":{},"total":0,"count":0,"zero_accounts":[]}
- {"entries":[{"account":"a","delta":1000000000000},{"account":"a","delta":1000000000000}]} -> {"balances":{"a":2000000000000},"total":2000000000000,"count":2,"zero_accounts":[]}

Si cualquier petición es inválida, validar el lote completo antes de emitir: stdout vacío, stderr exactamente "ledger-fold: invalid input\n", exit 2. Lote válido: exit 0 y stderr vacío. Solo biblioteca estándar, sin red, dependencias externas ni lectura/escritura de archivos externos.

Entrega: programa, README útil con instalación, entrada, ejemplos, errores y límites, y test_ledger_fold.py con pruebas pertinentes. El programa y README se sellan antes de escribir las pruebas. El argv de pruebas empieza con /opt/specorganon/venv/bin/python y ejecuta /input/delivery/test_ledger_fold.py. Solo el ejecutor aislado genera resultados y recibos. Conservar las nueve fases, contenido sustantivo, trazabilidad y revisión independiente. Cualquier evidencia de ejemplos es control público del contrato, no una ejecución observada del producto ni una línea base medida de otros métodos.
