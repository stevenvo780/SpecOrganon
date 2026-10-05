# ListPatch — contrato candidato, no registrado

Tarea seleccionada antes del resultado de LotLedger. No hay programa generado ni
celda comparativa admitida. Faltan revisión conjunta con84 recetas, rubricas,
transportes y análisis definitivos antes de congelar y generar.

Entregar listpatch.py para Python3.12 sólo stdlib. Invocación sin argumentos:
/opt/specorganon/venv/bin/python -E -s -B /input/delivery/listpatch.py.
Lee todo stdin máximo65536bytes; argv no vacío, incluso --help, falla antes de leer.
JSON UTF8 estricto sin BOM/NUL crudo, claves repetidas ni NaN/Infinity. Whitespace
JSON externo e interno permitido; un único objeto, nunca objetos concatenados.

Objeto exacto {"items":[integers],"operations":[objects]}, listas máximo1000elementos
cada una. Valores items y value: int JSON entre -1000000000 y1000000000, sin
bool/float/string. Index: int JSON entre0 y1000, sin bool/float/string. Validar tipos,
claves y límites de todo el documento antes de aplicar operaciones.

Operaciones exactas:
- {"op":"insert","index":i,"value":v}: inserta v antes de posición i; índice
  válido0<=i<=longitud actual. i==longitud agrega al final. No puede llevar longitud
  por encima de1000, ni temporalmente.
- {"op":"replace","index":i,"value":v}: sustituye posición i;0<=i<longitud actual.
- {"op":"delete","index":i}: elimina posición i;0<=i<longitud actual.

Op es literal sensible a mayúsculas, sin normalización. La única operación de
eliminación es delete: remove es inválida. Delete sólo admite op/index; agregar
value u otra propiedad también es error, incluso si el índice sería válido. Aplicar secuencialmente
en orden; cada índice se refiere a la lista tras operaciones anteriores. No hay
idempotencia ni eliminación de duplicados: cada operación cuenta. Un índice que
sólo sería válido después de otra operación sigue siendo inválido en su turno.
Cualquier fallo invalida todo, aunque operaciones posteriores pudieran compensarlo.
No emitir estado parcial. Input no puede mutarse externamente.

Éxito exit0, stderr vacío, stdout un único objeto con un LF final y sin whitespace
externo: {"items":[resultado],"applied":numero_de_operaciones}. applied int JSON
exacto, no bool/float. No claves adicionales/omitidas/repetidas. Orden de claves y
whitespace internos permitidos. Error exit2, stdout vacío, stderr exacto
{"error":"invalid_input"}\n.

Ejemplo1 stdin {"items":[10,20],"operations":[{"op":"insert","index":1,"value":15},{"op":"replace","index":0,"value":9},{"op":"delete","index":2}]}:
stdout {"items":[9,15],"applied":3}\n.
Ejemplo2 stdin {"items":[],"operations":[{"op":"insert","index":0,"value":-2},{"op":"delete","index":0}]}:
stdout {"items":[],"applied":2}\n.
README: instalación, interfaz, dos ejemplos con comandos completos, error exacto,
todos los límites, semántica secuencial/atomicidad y tests ejecutables con alcance.

Sujetos3s/2CPU/1GiB/128pids, red none, entrega readonly, sin perfiles/oráculos,
2MiB/stream. F84 del evaluador,D8,G6 y adherencia propia de cada método se registrarán
antes de autores. Es una transformación local de listas, sin evidencia de eficacia
de un editor real ni superioridad universal. Tokens/dinero desconocidos explícitos.

Matriz candidata: 84 recetas, incluidas dos re-mediciones de ejemplos públicos; 82 entradas reservadas. Conteo ampliado antes de0generaciones; sin garantía de cobertura universal.
