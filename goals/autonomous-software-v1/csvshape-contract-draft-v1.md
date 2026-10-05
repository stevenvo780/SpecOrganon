# CSVShape: contrato propuesto de una entrega nueva

Estado: borrador anterior a prerregistro, generación o aceptación. Una nueva
identidad de ingeniería; no reemplaza las celdas no iniciadas ni reabre LogLens,
IntervalDesk, RoutePlan o TreeMap. Su resultado se conservará aun si falla.

## Necesidad y utilidad observables

El operador necesita comprobar que SpecOrganon puede entregar software pequeño
con todas sus fases, revisión separada y pruebas reales. CSVShape propone un
producto utilizable para inspeccionar estructura de tablas antes de importarlas:
detectar filas incompatibles y resumir vacíos/valores distintos por columna.
Se verificará sobre entradas locales de prueba explícitas, sin afirmar demanda
de clientes, mejoras comerciales o calidad semántica de los valores. Es un tipo
de tarea distinto del grafo de rutas, inventario de archivos, logs e intervalos
de intentos anteriores. La novedad corresponde a contrato, identidad y datos
nuevos; no acredita una innovación general.

## CLI e interpretación

Entrega `csvshape.py`, Python3.12, sólo biblioteca estándar. Lee CSV de stdin;
invocación `python csvshape.py [--delimiter TOKEN]`. El único argumento opcional
aparece como máximo una vez y requiere un token separado de un carácter: coma,
punto y coma o TAB. Por defecto coma. Rechazar opciones desconocidas, duplicadas,
posicionales, valores ausentes y formas `--delimiter=...` antes de leer stdin.

La interpretación contractual es csv.reader de Python3.12, dialecto excel,
delimiter explícito, strict=True, sin conversión de tipos, sobre texto abierto
con newline vacío. El dialecto queda fijo, sin heurísticas de detección. La
biblioteca devuelve campos como strings por defecto y dispone de dialectos y
modo estricto; referencia primaria consultada el 2026-10-05:
[documentación Python3.12 csv](https://docs.python.org/3.12/library/csv.html).
El contrato añade límites y validaciones de forma explícita; no afirma cubrir
todos los dialectos CSV ni sustituir la especificación de otros productores.

## Validación y límites

- Input UTF-8 estricto, sin BOM ni byte NUL; máximo65536 bytes inclusive.
- Primera fila es encabezado obligatorio, entre1 y32 campos. Cada nombre es
  no vacío, único por igualdad exacta, máximo64 bytes UTF-8, sin CR/LF/NUL.
  Los espacios y TAB son significativos; no recortar ni normalizar Unicode.
- Entre0 y1000 filas de datos. Cada una tiene exactamente tantos campos como
  el encabezado. No omitir filas vacías: una fila interpretada como lista vacía
  es incompatible. Un encabezado solo es válido.
- Cada campo de datos admite4096 bytes UTF-8 inclusive. Comas, comillas escapadas
  y saltos de línea dentro de campos citados se interpretan mediante el dialecto
  fijado; conservar el valor devuelto sin transformarlo. No inferir números,
  fechas, booleanos o nulos, ni corregir datos silenciosamente.
- Vacío significa string de longitud0. Distintos cuenta valores exactos,
  incluyendo el string vacío. Unicode compuesto/descompuesto permanece distinto.
- Un error de lectura, decodificación, sintaxis CSV o validación invalida todo
  el resultado. No emitir un resumen parcial.
- Completar en3s, entorno2CPU/1GiB, sin red, perfiles o credenciales. No modificar
  archivos de entrada o entrega. Sólo se leen datos de stdin para la tabla.

## Resultado

Éxito: exit0, stderr vacío; stdout es un único objeto JSON UTF-8 terminado en
newline, sin claves extra: rows (entero no booleano, filas de datos), columns
(lista en el orden original). Cada columna tiene name (string), empty (entero
no booleano) y distinct (entero no booleano). Error: exit2, stdout vacío, stderr
es únicamente `{"error":"invalid_input"}` seguido de newline.

## Dos ejemplos públicos

Input1: `id,name\na,Ana\nb,\n`. Resultado:

```json
{"rows":2,"columns":[{"name":"id","empty":0,"distinct":2},{"name":"name","empty":1,"distinct":2}]}
```

Input2: `tag,note\nx,"uno,dos"\ny,"línea1\nlínea2"\n`. Resultado:

```json
{"rows":2,"columns":[{"name":"tag","empty":0,"distinct":2},{"name":"note","empty":0,"distinct":2}]}
```

El README debe reproducir ambos ejemplos con comandos completos, explicar
instalación, errores, límites y semántica. Tests propios ejecutables en entrega
readonly con argv absoluto `/opt/specorganon/venv/bin/python`, cubriendo éxito,
errores y bordes. Se registran recibos reales; el autor no declara passed ni
inventa mediciones.

## Pendientes antes de generar

Definir y revisar el protocolo completo: criterios falsables por fase, evidencia
observacional accesible y límites de su inferencia, separación autor/revisor,
techo40 roles y sus límites por función, presupuesto de contexto/archivos/tiempo,
matriz de pruebas de contrato con recetas nuevas reservadas, documentos y regla
de parada. Congelar estos elementos y su revisión antes de la primera llamada
que genere artefactos de caso. Una entrega necesita9fases aceptadas, trazas
vigentes, alternativas sustantivas, pruebas/README comprobados y veredicto por
criterio; no basta completar campos, hashes o controles sintéticos.

Este borrador no registra una nueva campaña comparativa, aceptación de fase,
consentimiento personal o éxito de la goal. La comparación N/S/T multitype con
dos familias y ablación permanece un requisito posterior independiente.
