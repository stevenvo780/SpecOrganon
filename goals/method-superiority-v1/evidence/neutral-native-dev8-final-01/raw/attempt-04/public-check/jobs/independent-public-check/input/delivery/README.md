# LedgerFold

CLI que consolida movimientos enteros por cuenta, independientemente para cada petición NDJSON. Implementación de biblioteca estándar, sin dependencias, red ni operaciones sobre archivos externos: el programa utiliza únicamente stdin, stdout y stderr.

## Entorno e invocación

Requiere Python 3.8 o posterior y streams estándar binarios normales. No se ha ejecutado el programa en este turno; no se acredita una versión concreta del entorno anfitrión.

Desde el directorio que contiene el programa:

```sh
python3 -I -B ledger_fold.py
```

Enviar las peticiones por stdin y cerrar el stream para terminar el lote. No hay opciones CLI; los argumentos adicionales no se interpretan. Para usar la ubicación prevista de entrega:

```sh
python3 -I -B /input/delivery/ledger_fold.py
```

## Entrada y límites exactos

stdin contiene como máximo 131072 bytes, incluidos espacios y terminadores. Se admite exactamente ese límite; cualquier exceso se rechaza. El programa lee como máximo 131073 bytes para detectar exceso, sin necesitar consumir el resto de una entrada demasiado larga. La decodificación es UTF-8 estricta; no se acepta BOM.

Cada línea contiene un objeto JSON con exactamente la clave `entries`. Su valor es una lista de 0 a 2000 objetos, cada uno con exactamente `account` y `delta`:

- `account`: cadena ASCII que coincide completamente con `[a-z][a-z0-9_]{0,31}`, de 1 a 32 caracteres. Se valida después de interpretar escapes JSON.
- `delta`: entero JSON con valor absoluto menor o igual a 1000000000000. Se excluyen booleanos, floats y notación decimal o exponencial, incluso si representan un entero matemático. Se permiten cero, negativos y movimientos duplicados.

LF delimita peticiones. CRLF se admite porque CR es espacio JSON; un CR aislado no delimita líneas. Otros separadores Unicode tampoco delimitan peticiones. Se permite espacio JSON alrededor de cada objeto y una última petición sin LF. Un LF final termina la petición anterior; un LF adicional crea una línea vacía y causa rechazo. Las líneas vacías o solo de espacios se rechazan. Cero bytes representan cero peticiones válidas.

Se rechazan JSON mal formado, texto adicional en la línea, constantes `NaN`, `Infinity` y `-Infinity`, claves duplicadas en cualquier objeto, campos ausentes o extra y tipos incorrectos. Las claves duplicadas se comparan después de decodificar escapes. Los errores del parser por enteros excesivamente largos o profundidad excesiva también se rechazan; esas estructuras no satisfacen el esquema válido.

## Salida

Por cada petición válida se emite un objeto JSON ASCII, compatible con UTF-8, seguido de LF. Las peticiones mantienen su orden y no comparten saldos. Cada resultado contiene exactamente:

- `balances`: todas las cuentas mencionadas y sus saldos enteros exactos, incluidas las cuentas con saldo cero.
- `total`: suma exacta de todos los movimientos de esa petición.
- `count`: número de movimientos, incluidos duplicados y movimientos cero.
- `zero_accounts`: todas las cuentas con saldo cero, ordenadas lexicográficamente.

El límite de 1000000000000 corresponde a cada movimiento, no a saldos ni totales. El orden de claves de objetos no es significativo. `entries` vacío produce `{"balances":{},"total":0,"count":0,"zero_accounts":[]}`.

## Dos ejemplos reproducibles

Los comandos siguientes asumen un shell POSIX, Python disponible como `python3` y el directorio del programa como directorio actual. Las salidas son expectativas públicas, no resultados de ejecuciones realizadas.

### Cancelación y conservación de una cuenta cero

Comando que suministra una línea de entrada:

```sh
printf '%s\n' '{"entries":[{"account":"cash","delta":7},{"account":"cash","delta":-7},{"account":"bank","delta":3}]}' | python3 -I -B ledger_fold.py
```

stdout esperado, con LF final:

```json
{"balances":{"cash":0,"bank":3},"total":3,"count":3,"zero_accounts":["cash"]}
```

stderr esperado: vacío. Código de salida esperado del programa: 0.

### Suma superior al límite individual

Comando que suministra una línea de entrada:

```sh
printf '%s\n' '{"entries":[{"account":"a","delta":1000000000000},{"account":"a","delta":1000000000000000}]}' | python3 -I -B ledger_fold.py
```

Para el ejemplo válido, utilizar ambos movimientos con el límite individual exacto:

```sh
printf '%s\n' '{"entries":[{"account":"a","delta":1000000000000},{"account":"a","delta":1000000000000}]}' | python3 -I -B ledger_fold.py
```

stdout esperado para este último comando, con LF final:

```json
{"balances":{"a":2000000000000},"total":2000000000000,"count":2,"zero_accounts":[]}
```

stderr esperado: vacío. Código de salida esperado del programa: 0. El primer comando de esta sección contiene deliberadamente un movimiento fuera de rango y tendría el rechazo descrito a continuación.

## Errores, exit y atomicidad

Si cualquier petición es inválida, stdout queda completamente vacío, stderr contiene exactamente `ledger-fold: invalid input` seguido de LF y el código de salida es 2. No se emiten resultados de líneas válidas anteriores. Un lote válido termina con código 0 y stderr vacío. Para stdin de cero bytes, ambos streams de salida quedan vacíos.

El lote completo se valida y la salida completa se prepara en memoria antes de escribir stdout. La atomicidad cubre el rechazo de entrada inválida; no garantiza una escritura física indivisible frente a fallos del sistema. Fallos de lectura/escritura, pipes rotos y agotamiento de memoria no se convierten en errores de entrada: no se promete para ellos mensaje, código ni atomicidad. El tamaño de salida puede superar el de entrada.

## Pruebas y límites de evidencia

No se entrega `test_ledger_fold.py` en esta etapa. Programa y README deben recibir el sello anfitrión antes de elaborar esa batería separada. El comando fijado para la batería posterior es:

```sh
/opt/specorganon/venv/bin/python -I -B /input/delivery/test_ledger_fold.py
```

La batería deberá usar solo biblioteca estándar, cargar `/input/delivery/ledger_fold.py` mediante `runpy` o `importlib` con ruta absoluta y no depender de `sys.path`. La guarda principal permite cargar el módulo sin ejecutar la CLI. Las pruebas de CLI deberán comprobar stdin binario, bytes exactos de stdout/stderr y códigos de salida, además de resultados semánticos.

El alcance previsto es V01–V08 de TASKS.md: límites de bytes y elementos, UTF-8, delimitación, esquema, duplicados, tipos y extremos numéricos, consolidación, orden y rechazo atómico de lotes mixtos. Esa cobertura propuesta no demuestra exhaustividad, tolerancia a fallos del sistema, rendimiento ni ausencia de efectos externos por sí sola. Los tests originales, fixtures y configuración deben permanecer inmutables. El presupuesto suministrado indica dos medidas restantes y un máximo de 4000 bytes JSON por stream de pruebas; los reportes deben ser completos y compactos, sin truncar evidencia ni ampliar cuotas.

La historia suministrada registra aceptación del plan y `tests_executed: false`. No contiene mediciones del programa ni un sello de estos archivos. Solo evidencia posterior del host podrá acreditar esos hechos. H permanece separado de D/G; esta entrega no demuestra superioridad ni funcionalidad reservada.
