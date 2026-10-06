# CSVShape: contrato propuesto de una entrega nueva

Estado: propuesta congelable anterior a registro, generación o aceptación. Una nueva
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



# CSVShape v1: protocolo prospectivo de ingeniería

Estado: propuesta; no habilita generación sin registro congelado y revisión.
Identidad única `csvshape-delivery-v1`; caso nuevo `cases/csvshape_v1`.
No reemplaza ningún caso o celda anterior. Esta entrega es un hito de ingeniería,
no una nueva campaña N/S/T ni evidencia de superioridad metodológica.

## Autoridad y roles

Se aplica el mandato existente de software autónomo del operador. Codex escogió
CSVShape como decisión técnica delegada; el usuario no escogió personalmente la
tarea o arquitectura. La aprobación local `human:owner` registra esa delegación,
sin autenticar identidad. Autor nativo Gemini 3.8 Flash (Medium), perfil original
`/home/stev/.gemini`; revisor nativo Codex gpt-6.1-sol, esfuerzo low, volumen original
`specorganon-lab_codex-home`. Cada llamada usa un contenedor separado y sólo el
perfil propio del proveedor. Los perfiles no se copian ni se cambian por fallos.
El controlador externo aplica decisiones y ejecuta pruebas, no escribe los
argumentos ni inventa la aceptación. El evaluador contractual no usa modelos.

Los roles reciben contrato, mandato, estado, reporte, tarea y datos públicos
actuales. No reciben recetas reservadas, respuestas esperadas ni diarios privados.
Las pruebas propias usan un contenedor sin credenciales/red con entrega readonly.
Las invocaciones reservadas sólo reciben código y stdin/argv: el host conserva
expectativas, recetas y recibos fuera de los montajes. El operador y el daemon de
Docker son autoridad confiable; el aislamiento no constituye certificación frente
a un operador hostil ni prueba de independencia estadística entre modelos.

## Condiciones previas y presupuesto

Revisión independiente de contrato, protocolo, controlador de admisión y evaluador
antes de registrar. Congelar hashes de los cuatro documentos públicos, todos los
módulos de src/specorganon, scripts ejecutados, evaluador, tests pertinentes,
catálogo público y revisión. Registrar imágenes inmutables y rutas originales
antes de inicializar caso o generar artefactos. Consultar cuotas actuales y catálogo
antes de delegar; cuotas ausentes quedan desconocidas, sin habilitar sondeo local
Codex ni cambiar cuentas. Admisión con observación de cuota de antigüedad <=600s.
Una cuota explícitamente agotada o lectura vencida pausa antes de nuevas llamadas;
obtener otra observación no renueva tiempos, presupuesto ni llamadas consumidas.

Controlador schema7: <=40 llamadas nativas; <=2 autores por fase excepto build
<=3 (programa, tests, reparación sólo tras fallo/rechazo real); <=2 revisiones por
fase; <=2 juicios de conformidad de aprobación por fase, contados separadamente.
El recorrido sin rechazos requiere unas 23 llamadas (9 autores, 9 revisores,
3 conformidades, segundo autor build y auditoría final); 40 permite correcciones acotadas, no éxito
garantizado. <=6000s desde primera admisión, <=180s por llamada nativa, <=120s
por prueba propia y <=2 pruebas, segunda sólo con Python/argv ejecutable cambiado.
<=128000 bytes UTF-8 de prompt renderizado por llamada; <=3145728 acumulados.
<=6 artefactos y <=6000 bytes de contribución JSON escapada por fase; <=20000
bytes de contribución JSON escapada de todos los archivos; <=4000 bytes escapados
de salida de pruebas. Estos límites mantienen contexto y entrega pequeños; no
están calibrados para demostrar ventaja y pueden ocasionar fallo de generación.
Los roles deben contar la serialización y producir argumentos breves sustantivos.
No se aumentarán estos límites tras ver outputs. Tokens y dinero desconocidos
permanecen null; bytes, duraciones, códigos y uso declarado se registran aparte.

## Criterios de las nueve fases

Cada fase necesita aceptación real del revisor separado, trazas vigentes y ausencia
de contradicciones abiertas. El revisor debe juzgar estos criterios, no sólo forma
JSON. Debe rechazar evidencia ausente, argumentos circulares o mediciones inventadas.

1. Frame: problema operativo preimportación, actor delegado y frontera explícita
   (estructura local, no semántica, demanda o utilidad comercial demostrada).
2. Critique: norma basada en actor/problema, supuesto discutible, dos encuadres
   distintos; confrontar inspección previa versus reparación silenciosa, declarar
   límites de la necesidad delegada. No aprobar utilidad de campo por etiqueta.
3. Study: pregunta falsable sobre conformidad técnica, hipótesis, protocolo que
   fija población/colección/comparación/incertidumbre; indicador(es) para los tres
   criterios siguientes, unidades y fuentes. Puede compartir métrica porcentual
   de comprobaciones cumplidas con denominadores específicos F/D/M; no mezclar
   poblaciones ni compensar criterios. Evidencia documental y la observación real
   de seis probes públicos del parser fundamentan el indicador antes de specify.
   La medición del parser no es medición de CSVShape/D/M; no inventar valores.
   Recetas reservadas no accesibles.
4. Observe: evidencia publicada/observada accesible con source/date/locator y
   enlace al protocolo; inferencia vinculada. Fuente primaria pública Python3.12
   csv y contrato delegado sustentan elección de validación estructural. No afirmar
   usuarios reales ni mejoras observadas; si no existen, registrar ese límite.
5. Explain: síntesis que separa garantías del parser, obligaciones añadidas y
   errores detectables; incertidumbre por corpus finito y demanda no estudiada.
6. Compare: >=2 opciones sustantivas vinculadas a norma/síntesis, comparación que
   refiere ambas y riesgo. Incluir opción viable sin software nuevo, por ejemplo
   revisión manual con una herramienta existente; justificar decisión por criterios
   técnicos, no superioridad ya medida. No basta renombrar variantes idénticas.
7. Specify: decisión trazada a comparación/norma/evidencia; requirement(s) y tres
   criterios trazados a problema/norma/evidencia/protocolo/decisión/indicador.
   Deben registrarse antes de medir: F conformidad contractual, D documentación,
   M método/trazas. F: propia suite realmente pasada y contrato/ejemplos correctos,
   sin inferir aceptación reservada todavía. D: README reproduce ambos ejemplos
   y documenta instalación/argv/errores/límites/semántica, checklist 8/8. M: 9/9
   fases revisadas separadamente, trazas vigentes, alternativas reales, recibos
   verificados y ninguna cuestión abierta. Umbrales no compensables; rechazar
   incumplimiento y declarar no_demostrado ante incertidumbre. El umbral reservado
   externo posterior es 100% de recetas, ambos ejemplos y documentación 8/8.
8. Build: programa y README reales como primera etapa; tests reales como segunda.
   Un único implementation actualizado, un único test con argv absoluto, ligados
   a requisitos/criterios. Tests cubren éxitos, errores y límites, invocando el CLI
   real; el controlador mide y registra recibos, nunca acepta passed del autor.
   Posible tercera etapa de reparación sólo tras fallo o rechazo semántico actual.
9. Validate: baseline/result con valores realmente suministrados y alcance explícito,
   assessments vinculados a criterio, baseline, result y riesgo; incertidumbre,
   efectos adversos y coste desconocido. Sólo F puede tener un juicio decisivo
   apoyado por pruebas propias reales: cada assessment decisivo debe trazar UN
   criterio, UN baseline y UN result, con test pasado que refiera directamente ese
   criterio e implementación. No combinar tres criterios en ese result; superaría
   las obligaciones del motor. D y M quedan no_demostrado en el ledger si no existe
   una medición propia pertinente. La auditoría separada posterior emite sus juicios
   D/M sin completar retrospectivamente el ledger. M9/9 todavía no se ha medido
   dentro de validate; no afirmar la aceptación futura de esta fase. Una proporción
   absoluta de conformidad no es una diferencia causal; baseline del parser conserva
   otra población y se usa sólo como contexto, sin imputar una baseline de programa
   inexistente. La reserva posterior puede refutar F y se conserva aparte.

Checklist D fijado: (1) Python3.12/stdlib/instalación sin dependencias; (2) stdin y
forma exacta argv/delimitadores; (3) comando ejecutable y resultado ejemplo1;
(4) comando ejecutable y resultado ejemplo2; (5) exit2/stdout vacío/error exacto;
(6) límites de bytes/filas/columnas/campos; (7) vacíos/distintos/Unicode exacto;
(8) alcance y uso real de tests. Revisor puntuará cada punto, no una media subjetiva.
Tras la puerta de paquete, una llamada nativa separada del mismo revisor, dentro
del techo40 y reloj6000s, debe emitir D8/8 y checklist M6/6 estructurados sobre
archivos, ledger, historia y recibos reales. Un punto ausente/incierto falla, sin
otra generación o reparación; la auditoría se conserva aun si rechaza. No sustituye
ejecutar ambos ejemplos, incluido en las 48 recetas después del cierre. El evaluator
externo exige auditoría positiva, nueve fases y reserva48/48 para completed_technical.

## Pruebas y cierre

Matriz reservada nueva, definida antes de generación en `reserved.py`: entradas
vacías, encabezados y anchuras, delimitadores/argv, CSV estricto/citas/nuevas líneas,
UTF-8/BOM/NUL, nombres/límites, filas/campos/bytes en límite y límite+1, valores
vacíos y Unicode sin normalización. Incluye dos ejemplos públicos identificados
por separado. Expectativas explícitas, sin invocar el programa entregado ni
consultar sus outputs para construir el oráculo. No corpus seleccionado por éxito.
Por receta un contenedor readonly/networknone/2CPU/1GiB, timeout3s, stream2MiB.
Misma identidad lógica sólo reutiliza recibo cerrado; cambio de receta o entrega
se rechaza antes de ejecutar. Timeout de sujeto es fallo contractual; incertidumbre
de montaje/lanzamiento/recibo es inconcluso. Todas las recetas quedan contabilizadas
si no hay programa, si falta una o si la infraestructura impide cerrar la ejecución.

Parada: error de proveedor, formato, techo, rechazo persistente, recibo incierto
o fuente modificada cierra esta identidad; no reemplazar, renovar o repetir hasta
ganar. Pausa de cuota/boot antes de nuevo despacho conserva el mismo pendiente,
presupuesto y artefactos; sólo continuidad probada permite proseguir. Interrupción
del observador se reconcilia con el mismo handle, jamás nueva llamada. Incluso
entrega fallida conserva programa parcial/ledger/recibos y recibe evaluación
reservada sin reparar después de ver recetas. Resultado: completed_technical sólo
con 9 fases, puerta de paquete, F/D/M y reserva completa; delivery_failed,
infra_inconclusive o not_started en otro caso. Publicar también fallos y límites.

Después de este caso siguen pendientes comparación prospectiva nueva de varios
tipos y dos familias con repeticiones/ablación, instalación limpia de versión
integrada y actualización de Vercel. CSVShape no satisface por sí solo toda la goal.


# Fuentes públicas disponibles antes de generación

Fecha de recopilación: 2026-10-05. Fuente primaria:
https://docs.python.org/3.12/library/csv.html, apartados csv.reader,
Dialect.strict y ejemplos. La lectura documental previa confirmó que reader
devuelve strings sin conversión por defecto, acepta dialecto/delimiter explícitos,
requiere manejo de newline apropiado y dispone de modo strict que eleva errores
de parseo. Esto permite una interpretación operacional reproducible; no demuestra
que todos los productores de CSV, usuarios o dialectos deban usar este contrato.

Fuente de alcance: contract.md y mandate.md de esta identidad, seleccionados por
Codex dentro de la autorización de pruebas reales y proyecto pequeño. Son evidencia
de obligaciones delegadas, no observación de demanda de clientes ni ensayo de campo.
Los dos ejemplos públicos del contrato son datos de prueba propuestos; sus salidas
esperadas son expectativas, todavía no mediciones de programa.

Hipótesis técnica susceptible de refutación: una entrega puede aplicar el contrato
local exactamente, con documentación reproducible, revisión independiente y recibos
reales. La observación posterior de tests propios debe conservar comandos, bytes y
retornos reales. La evaluación reservada es posterior y el autor no accede al corpus.
No existen mediciones preexistentes de CSVShape ni mejoras comparativas demostradas.

## Observación pública del parser, anterior al caso

`parser-observation.json` conserva seis probes deterministas especificados antes
de ejecutar `scripts/csvshape_parser_preflight.py` en Docker/Python3.12.3 sin red
ni perfiles. Resultado real 6/6 (100%, metric `checks_passed_percent`, unit `percent`):
coma citada, newline citado, comilla escapada, rechazo strict de cita sin cierre,
CRLF y strings sin casts. Source, argv, datos, resultados, fecha y recibo reales
constan en ese archivo. Es una medición finita del parser estándar, útil para
fundamentar un indicador del protocolo; no prueba las restricciones añadidas,
CSVShape, documentación, nueve fases, demanda ni un efecto frente a otro método.
La proporción enumerada es exacta para estos seis probes; un punto o intervalo
degenerado no representa un intervalo estadístico ni cobertura de todos los CSV.
No transportar el 100% a otra población, ni usarlo como resultado de la entrega.


PUBLIC PARSER OBSERVATION:
{"collected_at":"2026-10-05T10:57:22.450121+00:00","observation":{"measurements":{"denominator":6,"metric":"checks_passed_percent","passed":6,"sample_size":6,"unit":"percent","value":100.0},"python":"3.12.3","rows":[{"expected":[["x","y"],["a,b","c"]],"id":"quoted-comma","input":"x,y\n\"a,b\",c\n","observed":[["x","y"],["a,b","c"]],"passed":true},{"expected":[["x"],["a\nb"]],"id":"quoted-newline","input":"x\n\"a\nb\"\n","observed":[["x"],["a\nb"]],"passed":true},{"expected":[["x"],["a\"b"]],"id":"escaped-quote","input":"x\n\"a\"\"b\"\n","observed":[["x"],["a\"b"]],"passed":true},{"expected":"csv.Error","id":"strict-unclosed","input":"x\n\"a\n","observed":"csv.Error","passed":true},{"expected":[["x","y"],["a","b"]],"id":"crlf","input":"x,y\r\na,b\r\n","observed":[["x","y"],["a","b"]],"passed":true},{"expected":[["x","y"],["1","True"]],"id":"strings-without-casts","input":"x,y\n1,True\n","observed":[["x","y"],["1","True"]],"passed":true}],"schema":1,"scope":"Six deterministic public stdlib parser probes; no CSVShape programme, field effect or reserved result","uncertainty":"Exact enumerated probe proportion; no sampling confidence interval or population estimate"},"receipt":{"argv":["/usr/bin/docker","run","--rm","--read-only","--network","none","--cap-drop=ALL","--security-opt","no-new-privileges","--memory","1g","--cpus","2","--pids-limit","128","--tmpfs","/tmp:rw,nosuid,size=64m","--mount","type=bind,src=/home/stev/.codex/worktrees/prospective-software-repairs/SpecOrganon/scripts/csvshape_parser_preflight.py,dst=/probe.py,readonly","--entrypoint","/opt/specorganon/venv/bin/python","sha256:62ad297a92f147e335bc026906f98ead9807edfea0a96337defd926801b1ec41","-I","-B","/probe.py"],"cancel_exit_code":null,"cwd":"/datos/workspaces/personal/specorganon-validation/autonomous-software-v1/csvshape-parser-preflight-01","duration_seconds":0.37451676299679093,"exit_code":0,"finished_epoch":1791197842.4441879,"job_id":"public-parser-probes","metadata":null,"request_sha256":"798d78d4fefc39f7dddc1fe7838ff1f0238445a67ba63db3b8d6fe8f7b65436b","schema":1,"stderr_bytes":0,"stderr_sha256":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","stdin_bytes_expected":0,"stdin_bytes_sent":0,"stdin_complete":true,"stdout_bytes":1219,"stdout_sha256":"45f76eb710d25080c1f9bc9dd53037a4a164b2832dc47ed4ec8c91c3f434b0d5","timed_out":false,"truncated_streams":[]},"registration":{"argv":["/usr/bin/docker","run","--rm","--read-only","--network","none","--cap-drop=ALL","--security-opt","no-new-privileges","--memory","1g","--cpus","2","--pids-limit","128","--tmpfs","/tmp:rw,nosuid,size=64m","--mount","type=bind,src=/home/stev/.codex/worktrees/prospective-software-repairs/SpecOrganon/scripts/csvshape_parser_preflight.py,dst=/probe.py,readonly","--entrypoint","/opt/specorganon/venv/bin/python","sha256:62ad297a92f147e335bc026906f98ead9807edfea0a96337defd926801b1ec41","-I","-B","/probe.py"],"native_calls":0,"registered_at":"2026-10-05T10:57:22.057167+00:00","scope":"Public stdlib observation, not generated CSVShape","source_sha256":"71829049939b54e1ac3a9f4a4c5de307ff0bf95ca5e7bb61cfe1e29b015f8a85"},"scope":"Public stdlib observation, not generated CSVShape","stderr_utf8":""}