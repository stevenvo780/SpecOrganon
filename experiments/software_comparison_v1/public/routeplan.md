# RoutePlan — contrato público v1 (borrador, sin generación)

Entrega una CLI `routeplan.py` para Python3.12, sólo biblioteca estándar. Calcula
una ruta mínima en un grafo dirigido de costes positivos. Es una herramienta
local pequeña; no predice tráfico, seguridad vial ni utilidad de campo.

## Entrada

Invocación: `python routeplan.py`, sin argumentos adicionales. Lee stdin binario
hasta EOF. Admite hasta65536 bytes inclusive, JSON UTF-8 sin BOM. Espacios JSON
iniciales/finales son válidos. Exige exactamente un objeto JSON; rechaza claves
repetidas a cualquier nivel, floats, NaN/Infinity y contenido adicional tras el
objeto. Todo fallo de parseo, incluidos límites de enteros del intérprete o
decodificación UTF-8, es entrada inválida. No imprime mensajes de progreso.

El objeto tiene exactamente `nodes`, `edges`, `query`:

- `nodes`: lista de1..32 strings únicos. Cada ID cumple
  `[A-Za-z][A-Za-z0-9_]{0,15}`. El orden de entrada no tiene significado.
- `edges`: lista de0..128 objetos. Cada uno tiene exactamente `source`, `target`,
  `cost`; ambos extremos son IDs existentes. Cost es un entero JSON de1..1000,
  nunca un booleano o decimal. Un par dirigido source/target no se repite.
  Los arcos inversos son distintos; los bucles propios positivos son válidos.
- `query`: objeto con exactamente `source`, `target`, ambos IDs existentes.

## Resultado

En entrada válida, exit0, stderr vacío y stdout con un único objeto JSON UTF-8
terminado en newline. Sus únicas claves son `reachable`, `cost`, `path`:

- Ruta alcanzable: reachable es true, cost un entero y path una lista de IDs.
  Incluye origen y destino. Minimiza la suma de costes dirigidos.
- Entre rutas de coste mínimo, elige la lista completa de IDs
  lexicográficamente menor: se comparan strings ASCII desde el primer ID que
  difiere; si una lista es prefijo de otra, la más corta precede. No desempates
  por número de saltos, orden de nodos/arcos ni destino inmediato solamente.
- Si source==target, cost0 y path=[source], incluso si existen bucles propios.
- Sin ruta: reachable=false, cost=null, path=[].

Los costes positivos permiten que una ruta óptima sea simple. El programa puede
usar cualquier algoritmo correcto; la implementación no tiene formato interno
prescrito. El orden de claves y los espacios de salida son libres. Los tipos
JSON y el conjunto de claves son estrictos; un booleano no equivale a un entero.

Entrada o argumentos inválidos: exit2, stdout vacío, stderr exactamente un
objeto JSON `{"error":"invalid_input"}`, terminado en newline; espacios son libres.
No traceback ni mensajes adicionales. No abrir/redactar archivos de usuario,
usar red o instalar dependencias. La entrega debe completar cada invocación en
3s dentro del entorno fijado de2CPU/1GiB. Son límites de evaluación local.

## Ejemplos públicos

```json
{"nodes":["A","B","C","D"],"edges":[{"source":"A","target":"D","cost":4},{"source":"A","target":"C","cost":2},{"source":"C","target":"D","cost":2},{"source":"A","target":"B","cost":1},{"source":"B","target":"D","cost":3}],"query":{"source":"A","target":"D"}}
```

Resultado: `{"reachable":true,"cost":4,"path":["A","B","D"]}`.

```json
{"nodes":["West","East"],"edges":[],"query":{"source":"West","target":"East"}}
```

Resultado: `{"reachable":false,"cost":null,"path":[]}`.

## Entrega común

Programa, tests propios pertinentes y README.md con instalación, comandos
reproducibles para ambos ejemplos, formato de entrada/salida, errores y límites.
Los tests propios deben tener argv absoluto para el executor público, con Python
`/opt/specorganon/venv/bin/python` y entrega readonly `/input/delivery`. Pueden
usar `/tmp` para trabajo temporal. No declarar passed o inventar recibos.

El evaluador reservado se congelará antes de cualquier solución y nunca se
entregará al autor o revisor de soluciones. Sus resultados no alimentan una
reparación. Los ejemplos públicos pueden usarse durante generación. Este
contrato todavía requiere auditoría y prerregistro junto con el harness.
