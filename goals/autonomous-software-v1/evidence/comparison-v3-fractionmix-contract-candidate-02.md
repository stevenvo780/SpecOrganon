# FractionMix: contrato candidato anterior a generación

Tarea ya seleccionada en el protocolo v3. Este documento fija su interfaz candidata;
no es un registro aceptado, un programa generado ni una evaluación realizada.
Se revisará junto con sus sesenta recetas antes de admitir cualquier celda v3.
La tarea será idéntica para N, S, T y A y para las dos familias de modelos.

## Propósito y entrega

Sumar racionales sin redondeo de punto flotante y devolver una fracción canónica.
Entregar `fractionmix.py` y README con tests ejecutables propios, Python 3.12,
biblioteca estándar. Se evalúa una utilidad técnica en entradas sintéticas finitas;
no hay evidencia de utilidad en personas o superioridad general de un método.

Invocación fijada: `/opt/specorganon/venv/bin/python -E -s -B /input/delivery/fractionmix.py`.
Leer datos exclusivamente de stdin. Cualquier argumento, incluido `--help`, produce
error antes de leer stdin. No consultar datos por archivos auxiliares, red o entorno.

## Entrada y validación

Leer como máximo 65536 bytes inclusive, incluyendo whitespace final. UTF-8 estricto,
sin BOM inicial ni byte NUL. Un único objeto JSON estricto; whitespace JSON exterior
permitido, pero ningún segundo valor. Vacío o sólo whitespace es error. Rechazar
claves duplicadas en cualquier objeto y constantes no JSON NaN/Infinity/-Infinity.

Claves superiores exactamente `terms`. Su valor es una lista de 0 a 1000 elementos
inclusive. Cada elemento es un objeto con exactamente `numerator` y `denominator`.
Numerator es entero JSON exacto, sin bool/float/string, entre -1000000000 y
1000000000 inclusive. Denominator es entero JSON exacto, sin bool/float/string,
entre 1 y 1000000000 inclusive. No aceptar denominadores negativos o cero.
El orden de claves no importa; claves se comparan tras decodificar escapes JSON.
No hay coerción ni tolerancia a propiedades extra. Un término inválido invalida
la entrada completa, incluso si su numerador es cero o otro término lo cancelaría.

## Cálculo y resultado

Cada término representa exactamente numerator/denominator. Sumar usando aritmética
entera exacta; los enteros de resultado pueden exceder los límites individuales de
entrada. El orden de términos no afecta la suma. `term_count` cuenta todos los
términos, incluidos ceros, duplicados y cancelaciones; no deduplicar términos.

Devolver un numerador entero con signo y un denominador entero estrictamente
positivo, reducidos por su máximo común divisor. Para resultado cero, devolver
exactamente numerator=0 y denominator=1. La lista vacía produce cero y term_count=0.

Un resultado válido puede superar4300 dígitos decimales. La entrega debe poder
serializarlo sin perder exactitud, por ejemplo habilitando explícitamente la
conversión mediante `sys.set_int_max_str_digits(0)`; no se exige esa implementación
concreta. El límite decimal predeterminado de CPython no reduce el dominio del
contrato. Oráculos y evaluadores también deben manejar estos enteros válidos.
Con1000 términos, el denominador reducido tiene a lo sumo9001 dígitos y el numerador
a lo sumo9013: el producto de denominadores está acotado por10^9000 y el valor
absoluto de la suma por10^12. Estas cotas se derivan del contrato; no son límites
adicionales para facilitar la tarea. Mantener límites de entrada/streams/recursos.

Éxito: exit 0, stderr vacío, stdout UTF-8 empieza con `{` y termina con `}\n`, un
solo objeto JSON estricto, sin whitespace exterior, prefijos, sufijos ni BOM.
Whitespace interior y orden de claves son insignificantes, incluido pretty printing.
El evaluador comprueba los bytes `{` inicial y `}\n` final y parsea el cuerpo como
un solo JSON; no admite bytes antes de `{` ni después del LF terminal.
Claves exactamente `numerator`, `denominator`, `term_count`; todos enteros JSON
exactos, no booleanos. Sus valores deben corresponder a las reglas anteriores.

Cualquier error contractual: exit 2, stdout vacío, stderr exactamente
`{"error":"invalid_input"}\n`. No emitir resultados parciales. Timeout/OOM/crash
se conserva como fallo de ejecución, sin imputarlo como el error contractual.
Cada invocación: 3 segundos, 2 CPU, 1 GiB, 128 procesos, entrega readonly, sin red
ni credenciales; stream máximo 2 MiB. No modificar archivos de entrega.

## Dos ejemplos públicos

Ejemplo 1, estas entradas equivalentes admiten whitespace exterior:

```json
{"terms":[{"numerator":1,"denominator":2},{"numerator":1,"denominator":3}]}
```

Resultado:

```json
{"numerator":5,"denominator":6,"term_count":2}
```

Ejemplo 2:

```json
{"terms":[{"numerator":2,"denominator":4},{"numerator":-1,"denominator":2}]}
```

Resultado:

```json
{"numerator":0,"denominator":1,"term_count":2}
```

## Documentación, pruebas y alcance

README: Python/instalación; stdin e invocación sin argumentos; comandos completos
para ambos ejemplos con sus resultados; error exacto; límites de bytes/términos/
enteros/recursos; suma exacta/reducción/cero/duplicados; tests reproducibles y alcance.
Tests propios usan el intérprete absoluto fijado y casos de éxito, error y bordes.
Sus recibos los crea el ejecutor externo; el autor no inventa ejecución ni resultados
reservados. Las sesenta recetas reservadas se medirán después del cierre de entrega,
sin feedback para corregir el programa. Este contrato no suministra implementación,
argumentos de nueve fases ni evidencia inventada de eficacia.
