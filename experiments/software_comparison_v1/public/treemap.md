# TreeMap — contrato público v1 (borrador, sin generación)

Entrega una CLI `treemap.py` para Python3.12, sólo biblioteca estándar. Produce
un inventario determinista de tamaños de archivos, sin abrir sus contenidos,
seguir symlinks ni modificar el árbol. No es un backup o análisis de seguridad.

## Invocación

`python treemap.py --root PATH [--max-depth D] [--suffix EXT]`.

Las opciones pueden aparecer en cualquier orden, como tokens separados. Cada
opción admite exactamente un valor y aparece como máximo una vez; root es
obligatoria. Rechaza opciones desconocidas, duplicadas, valores faltantes,
argumentos posicionales o formas `--root=...`. No lee stdin.

- PATH es un string no vacío que designa un directorio existente y accesible.
  Puede ser absoluto o relativo al cwd. Para detectar el tipo de root, se
  normaliza léxicamente eliminando componentes `.` y barras finales/repetidas,
  sin resolver symlinks. Se rechaza si esa entrada root normalizada misma es un
  symlink, archivo u otro tipo (también para `link/` o `link/.`).
  Los padres de la ruta explícita pueden resolverse por el sistema; esa ruta
  declara la raíz autorizada. No se admite `..` como componente de PATH.
- D tiene exactamente un carácter ASCII de1 a8. Por defecto4. Es profundidad
  relativa de entrada: un archivo directamente en root tiene profundidad1,
  `sub/file` tiene2. No se listan hijos de directorios a profundidad D.
- EXT, si aparece, cumple `\.[A-Za-z0-9]{1,12}`. Selecciona archivos regulares cuyo
  nombre base (basename) termina en EXT, sensible a mayúsculas. Sin EXT, incluye todos.
  Este filtro no cambia recorrido, conteo de entradas ni inventario de symlinks.

## Recorrido y límites

Usa el tipo de cada entrada sin seguir enlaces. Nunca atraviesa symlinks a
archivos o directorios, aunque apunten dentro de root. Registra el camino
relativo de cada symlink encontrado, sin leer su destino. Ignora otros tipos
no regulares (p. ej. FIFO/socket), sin abrirlos. Incluye nombres ocultos.

El árbol evaluado permanece estático durante la invocación. Root misma no
cuenta como entrada visitada. Cada hijo listado dentro de la profundidad
permitida cuenta una vez, sea archivo, directorio, symlink u otro tipo; máximo
256 entradas visitadas inclusive. Directorios a profundidad D cuentan pero sus
hijos no se visitan. Exceder256 es error, incluso con un filtro que excluya todo.

Los nombres deben ser representables en UTF-8 estricto. Cada camino relativo
visitado, con separador `/`, admite como máximo512 bytes UTF-8. Nombres con
espacios, caracteres Unicode o saltos de línea válidos se admiten y escapan en
JSON. Cualquier error de lstat/listado/tamaño, nombre inválido o límite excedido
aborta toda la operación: no se devuelve un inventario parcial. Un archivo
regular ilegible puede inventariarse si su metadata es accesible; no se abre.

## Resultado

En éxito: exit0, stderr vacío y stdout con un único objeto JSON UTF-8 terminado
en newline, cuyas únicas claves son `files`, `total_bytes`, `symlinks`:

- files es una lista de objetos con sólo `path` (camino relativo POSIX, nunca
  absoluto ni prefijo root) y `bytes` (entero no negativo, nunca booleano).
- Incluye los archivos regulares seleccionados. Su tamaño es el número de bytes
  de metadata, no longitud de texto o tamaño de bloques asignados.
- Ordena files por path y symlinks por sus strings, usando orden lexicográfico de
  caracteres Unicode. No normaliza, cambia mayúsculas ni omite caracteres.
- total_bytes es un entero, suma exacta de bytes de files. Directorios, symlinks
  y tipos ignorados no aportan tamaños. Cada entrada se lista una sola vez.

Argumentos/raíz/recorrido inválidos: exit2, stdout vacío, stderr con sólo el
objeto JSON `{"error":"invalid_input"}` terminado en newline, sin traceback o
mensajes adicionales. Orden de claves/espacios JSON libres; tipos y claves
estrictos. No usar red, perfiles, dependencias externas o escrituras en root.
Cada invocación debe completar en3s dentro del entorno fijado de2CPU/1GiB.

## Ejemplos públicos

Árbol: `a.txt` contiene los dos bytes `hi`, `z.bin` contiene un byte, `sub/b.txt`
contiene tres bytes y `shortcut` es un symlink a `sub`. No hay otras entradas.

`python treemap.py --root /input/tree --max-depth 2 --suffix .txt` produce:

```json
{"files":[{"path":"a.txt","bytes":2},{"path":"sub/b.txt","bytes":3}],"total_bytes":5,"symlinks":["shortcut"]}
```

Con `--max-depth 1`, mismo filtro:

```json
{"files":[{"path":"a.txt","bytes":2}],"total_bytes":2,"symlinks":["shortcut"]}
```

Un root vacío produce `{"files":[],"total_bytes":0,"symlinks":[]}`.

## Entrega común

Programa, tests propios pertinentes y README.md con instalación, comandos que
crean un árbol de ejemplo temporal y reproducen ambos resultados, formato de
salida, errores y límites. Los tests propios deben tener argv absoluto para
Python `/opt/specorganon/venv/bin/python` y entrega readonly `/input/delivery`;
pueden construir fixtures propias en `/tmp`. No declarar passed o recibos.

El evaluador reservado se congelará antes de soluciones y permanecerá separado
de autor/revisor de soluciones. No se reparará a partir de sus resultados. Este
contrato todavía requiere auditoría y prerregistro junto con el harness.
