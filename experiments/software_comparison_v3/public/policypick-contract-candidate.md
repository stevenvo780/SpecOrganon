# PolicyPick — contrato candidato, no registrado

Tarea seleccionada antes del resultado de LotLedger. No se ha generado un programa,
ni admitido una celda comparativa. Este texto debe revisarse junto con las82 recetas,
rubricas, transportes y análisis definitivos antes del freeze.

Entregar policypick.py para Python3.12, sólo stdlib. Invocación sin argumentos:
/opt/specorganon/venv/bin/python -E -s -B /input/delivery/policypick.py.
Lee todo stdin (máximo65536bytes); con argumentos, incluso --help, falla antes de
leer. JSON UTF8 estricto, sin BOM ni NUL crudo, claves repetidas o NaN/Infinity.
Permite whitespace JSON alrededor y dentro del único objeto, incluidos LF/CR/tab;
no permite objetos concatenados. Todo el documento debe validarse antes de decidir.

Objeto exacto {"rules":[...],"queries":[...]}; cada lista máximo1000elementos.
Regla exacta {"name":string,"priority":int,"requires":[strings]}.
Consulta exacta {"id":string,"tags":[strings]}.
Cada requires/tags tiene máximo1000elementos. Strings no vacíos, máximo64bytes UTF8
después de escapes, sin NUL/CR/LF ni surrogates no codificables. Espacios/tab,
mayúsculas y Unicode son literales, sin trim/normalización. Enteros JSON de
-1000000000 a1000000000, sin bool/float/string. Names de reglas e IDs de consultas
deben ser únicos por igualdad literal; sus espacios de nombres son independientes.
Duplicados tanto en requires como en tags son válidos: cada lista se compara como
conjunto, sin duplicar pertenencias ni invalidar por repetición.

Una regla coincide si su conjunto requires es subconjunto de los tags de consulta.
Requires vacío coincide siempre. Elegir la prioridad más alta; si hay empate,
el name mínimo en orden de puntos de código Unicode. El orden de rules no influye.
Tags desconocidos son válidos. Sin coincidencia, rule es null. Con rules=[] todas
las consultas producen rule=null. Con queries=[] el resultado es {"decisions":[]}.

Éxito exit0, stderr vacío y exactamente un objeto stdout seguido por un LF, sin
whitespace externo: {"decisions":[{"id":id,"rule":name_o_null},...]}. Cada consulta
produce una decisión en el mismo orden de entrada. Claves adicionales, omitidas o
repetidas no son válidas; whitespace/orden de claves internos están permitidos.
Error exit2, stdout vacío, stderr exacto {"error":"invalid_input"}\n. Un error en
cualquier regla/consulta invalida todo, aunque esa regla no pudiera ganar.

Ejemplo1, stdin {"rules":[{"name":"default","priority":0,"requires":[]},{"name":"staff","priority":2,"requires":["internal"]}],"queries":[{"id":"q1","tags":["internal","internal"]},{"id":"q2","tags":[]}]}:
stdout {"decisions":[{"id":"q1","rule":"staff"},{"id":"q2","rule":"default"}]}\n.
Ejemplo2, stdin {"rules":[{"name":"z","priority":3,"requires":["x"]},{"name":"A","priority":3,"requires":["x"]}],"queries":[{"id":"yes","tags":["x"]},{"id":"no","tags":[]}]}:
stdout {"decisions":[{"id":"yes","rule":"A"},{"id":"no","rule":null}]}\n.
Ambos ejemplos exigen comandos completos en README, además de instalación,
interfaz, error, límites, semántica literal/empates y tests ejecutables con alcance.

Sujetos:3s/2CPU/1GiB/128pids, red none, entrega readonly, sin credenciales ni oráculos,
2MiB por stream. F82 recetas del evaluador, D8, G6 y adherencia por método se fijarán
antes de autores. Este contrato define semántica local, no eficacia en control de
acceso real ni cumplimiento legal. Valores/tokens/dinero desconocidos explícitos.

Matriz candidata: 82 recetas, incluidas dos re-mediciones de ejemplos públicos; 80 entradas reservadas. Conteo ampliado antes de0generaciones; sin garantía de cobertura universal.
