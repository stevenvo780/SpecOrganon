# LotLedger v1: contrato prospectivo de entrega

Estado: contrato candidato, anterior a revisión final, registro o generación.
Identidad única `lotledger-delivery-v1`. No reemplaza resultados anteriores.

## Propósito y alcance

Conciliar eventos de existencias por lote y ubicación, detectar doble aplicación,
conflictos de identidad y saldo insuficiente antes de importar datos. Se evalúa
una herramienta técnica sobre entradas de prueba. No hay evidencia de utilidad
humana, reducción de pérdidas, eficacia alimentaria o superioridad metodológica.

## Interfaz y entrada

Entregar `lotledger.py`, Python 3.12, biblioteca estándar. Invocación sin argumentos:
`/opt/specorganon/venv/bin/python -E -s -B /delivery/lotledger.py`.
Leer sólo stdin; cualquier argumento, incluido `--help`, produce error antes de
leer stdin. No leer perfiles, red, archivos auxiliares ni variables para los datos.

Máximo **65536 bytes de stdin inclusive**, incluidos whitespace y LF final;
65537 bytes es error contractual. UTF-8 estricto, sin BOM inicial ni byte NUL.
LF separa eventos JSON. Después del último evento se permiten cero o un LF final:
un evento completo sin LF final es válido. Vacío es válido y tiene
cero eventos; LF solo, líneas vacías, una línea de whitespace o dos LF finales
son errores. CR antes de LF cuenta como whitespace JSON y es permitido.
Whitespace JSON alrededor del objeto en su línea es permitido. Un objeto debe
ocupar una línea; escapes JSON de caracteres siguen siendo parte de esa línea.
Máximo **1000 eventos inclusive**, contando todas las ocurrencias duplicadas.

Cada línea contiene un objeto JSON estricto: rechazar sintaxis inválida, claves
duplicadas en cualquier objeto y constantes no JSON como NaN o Infinity.
Claves exactas, sin extras:

| op | Claves |
|---|---|
| receive | id, op, lot, site, quantity |
| consume | id, op, lot, site, quantity |
| move | id, op, lot, from, to, quantity |

`op` es uno de los tres strings exactos. id/lot/site/from/to son strings no vacíos
de hasta **64 bytes UTF-8 inclusive**, sin NUL/CR/LF después de interpretar escapes.
Cada string debe poder codificarse en UTF-8 estricto; rechazar surrogates aislados.
Espacios, TAB, mayúsculas y Unicode son significativos; no recortar ni normalizar.
quantity es un entero JSON exacto, no booleano, float ni string, entre 1 y
1000000000 inclusive. Los saldos resultantes pueden exceder ese límite individual.
En move, from y to son strings distintos por igualdad exacta.

## Procesamiento y duplicados

Estado inicialmente vacío, indexado por el par exacto (lot, site), con saldo cero
para pares ausentes. Procesar eventos en su orden de aparición. receive suma;
consume resta; move resta de from y suma a to en el mismo lot. No ordenar eventos
ni permitir saldo negativo transitorio. Saldo insuficiente invalida todo stdin,
aunque un evento posterior pudiera aportar fondos. No emitir resultados parciales.

Validar la forma y los tipos de cada evento **antes de comprobar su id**. Si un id
ya apareció, el mismo objeto validado —mismas claves, tipos y valores, ignorando
sólo el orden de claves— es un duplicado: no comprobar stock ni aplicar efectos
de nuevo. Un objeto distinto con ese id invalida todo stdin. Una repetición de
un consume/move válido después de agotar el origen sigue siendo idempotente.
unique_events cuenta ids distintos; duplicate_events cuenta todas las ocurrencias
posteriores idénticas. No omitir un objeto inválido alegando que su id es conocido.

## Salida exacta y recursos

Éxito: exit 0, stderr vacío, stdout UTF-8 empieza con `{` y termina en `}\n`.
Contiene un solo objeto JSON estricto; no whitespace exterior, prefijos, sufijos,
otro valor JSON, BOM ni claves duplicadas. Orden de claves y whitespace **interior**
JSON son insignificantes, incluido pretty printing. Claves superiores exactamente
unique_events (entero no bool), duplicate_events (entero no bool), stocks (lista).
Cada fila stocks tiene sólo lot (string), site (string), quantity (entero no bool).
Omitir cantidades cero; todas las filas son positivas, sin pares repetidos, ordenadas
por (lot, site) con comparación por Unicode codepoints de strings de Python 3.12,
independiente de locale. Valores y tipos deben corresponder al procesamiento anterior.

Cualquier error contractual: exit 2, stdout vacío y stderr exactamente estos bytes:
`{"error":"invalid_input"}\n`. Un timeout/OOM/crash observado por el evaluador se
registra como fallo de ejecución; no se imputa el código 2. Límite 3 segundos por
invocación, 2 CPU, 1 GiB, 128 procesos, sin red ni credenciales, entrega readonly.
No modificar los datos ni archivos de entrega. El tmpfs de runtime no autoriza
persistencia ni lectura de fuentes fuera de la biblioteca estándar y la entrega.

## Dos ejemplos públicos

Ejemplo 1: stdin vacío. Salida:

```json
{"unique_events":0,"duplicate_events":0,"stocks":[]}
```

Ejemplo 2: estas cuatro líneas, terminadas en LF:

```jsonl
{"id":"r1","op":"receive","lot":"L","site":"A","quantity":7}
{"id":"c1","op":"consume","lot":"L","site":"A","quantity":2}
{"id":"m1","op":"move","lot":"L","from":"A","to":"B","quantity":3}
{"quantity":2,"site":"A","lot":"L","op":"consume","id":"c1"}
```

Salida:

```json
{"unique_events":3,"duplicate_events":1,"stocks":[{"lot":"L","site":"A","quantity":2},{"lot":"L","site":"B","quantity":3}]}
```

README usable: Python/instalación, invocación/stdin/sin argumentos, comandos completos
para ambos ejemplos y salidas correctas, error exacto, límites de bytes/eventos/strings/
quantity/recursos, orden/duplicados/Unicode y alcance técnico. Tests propios ejecutables
con argv absoluto del intérprete fijado, cubriendo éxito/error/bordes. El controlador
conserva recibos reales; el autor no inventa `passed`, datos de ejecución o reservados.

Este contrato no suministra implementación ni artefactos de las nueve fases.
