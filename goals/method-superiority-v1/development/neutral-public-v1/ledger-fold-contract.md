# LedgerFold: desarrollo técnico público

Construir ledger_fold.py, una CLI Python estándar para consolidar movimientos enteros por cuenta. Esta tarea pertenece al desarrollo de fiabilidad; no es una evaluación reservada ni una prueba de superioridad.

Entrada NDJSON UTF-8 por stdin. Cada línea contiene un objeto con exactamente entries, una lista de hasta 2000 objetos con exactamente account y delta. account es una cadena ASCII que satisface [a-z][a-z0-9_]{0,31}; delta es un int JSON, excluidos bool y float, de valor absoluto <=10^12. Se permiten movimientos duplicados, negativos y de importe cero. El límite de 10^12 se aplica a cada movimiento, no a la suma. El total de stdin no debe superar 131072 bytes. Entrada completamente vacía: cero peticiones. Rechazar líneas vacías, JSON mal formado, constantes no finitas, claves duplicadas en cualquier objeto, campos extra y UTF-8 inválido.

Salida por petición con exactamente balances, total, count y zero_accounts. balances es un objeto con todas las cuentas mencionadas, incluso las que suman cero, y sus saldos enteros exactos. total suma todos los movimientos; count es su número. zero_accounts es una lista ordenada lexicográficamente de cuentas con saldo cero. Emitir un objeto JSON por línea, seguido de newline. El orden de claves de los objetos no afecta el resultado.

Ejemplos:
- {"entries":[{"account":"cash","delta":7},{"account":"cash","delta":-7},{"account":"bank","delta":3}]} -> {"balances":{"cash":0,"bank":3},"total":3,"count":3,"zero_accounts":["cash"]}
- {"entries":[]} -> {"balances":{},"total":0,"count":0,"zero_accounts":[]}
- {"entries":[{"account":"a","delta":1000000000000},{"account":"a","delta":1000000000000}]} -> {"balances":{"a":2000000000000},"total":2000000000000,"count":2,"zero_accounts":[]}

Si cualquier petición es inválida, validar el lote completo antes de emitir: stdout vacío, stderr exactamente "ledger-fold: invalid input\n", exit 2. Lote válido: exit 0 y stderr vacío. Solo biblioteca estándar, sin red, dependencias externas ni lectura/escritura de archivos externos.


Entrega común de desarrollo N/S: programa indicado, README útil con entorno, interfaz, límites, dos ejemplos completos, errores, atomicidad y comando de pruebas; criterios y trazas en la estructura elegida por el método. N elige notas y estrategia propias. S prepara SPEC.md, DESIGN.md y TASKS.md con alternativas y enlaces, revisados antes del programa. H se audita aparte de D/G. El flujo provisional registra notas/criterios antes del programa; no representa trabajo libre irrestricto.

Programa y README se sellan antes de una batería separada test_ledger_fold.py. Solo stdlib; se ejecuta /opt/specorganon/venv/bin/python -I -B /input/delivery/test_ledger_fold.py. Cargar el programa por ruta absoluta usando runpy/importlib; no depender de sys.path. Los tests originales/fixtures/config quedan inmutables. El host genera los recibos; no afirmar ejecución previa ni F independiente. El autor conserva autonomía de estrategia y descomposición dentro de estos límites. Ninguna fase del engine T se exige a N/S. Los ejemplos son expectativas públicas, no ejecuciones medidas.
