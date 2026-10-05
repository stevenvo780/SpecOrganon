# Evaluador reservado v1: implementación de borrador

Este trabajo añade infraestructura para la comparación prospectiva. No es una
entrega RoutePlan/TreeMap ni satisface el criterio de una nueva entrega de nueve
fases. El estudio mantiene cero celdas generadas; contratos, protocolo, harness,
rúbricas, orden y límites siguen pendientes de auditoría y congelación conjunta.

El borrador revisado contiene 61 entradas RoutePlan y 52 árboles/invocaciones TreeMap.
RoutePlan usa enumeración de caminos simples para obtener esperados, con guard
contra fixtures demasiado densas; no ejecuta código del autor para definirlos.
TreeMap obtiene esperados de una descripción declarativa independiente del
recorrido del programa. Ambos comprueban tipos y conjuntos de claves JSON,
enmarcado de streams y códigos de salida, conservando incertidumbre de infra.

En invocaciones ordinarias Docker sólo monta entrega opaca y fixture actual, ambos readonly. No monta
esperados, suite, evaluador, ledger, perfiles, journal ni daemon. Usa imagen
inmutable, red none, UID1000, cap-drop ALL, 1GiB/2CPU/128pids y scratch tmpfs.
El límite de ejecución se impone con timeout3s dentro del contenedor; el host
limita attachment a10s. Exit137 indica cierre con SIGKILL, compatible con límite
o salida137 del programa, y siempre falla; no se inventa causalidad exacta.
OOM y el timeout de attachment conservan sus observaciones propias.

Un probe de strace está diseñado para observar acceso a contenido y lectura
del destino de un link. Los opens incluyen anotación de descriptores para detectar
rutas relativas y acceso a través de symlink. Readlink usa cwd/dirfd observados;
una resolución relativa desconocida queda inconclusa. Esta prueba no demuestra
ausencia de acceso prohibido para todos los árboles ni resistencia a código
hostil que controle su tracer. El stderr ordinario se mide sin trazado.

Los programas de control son respuestas fijas/defectos deliberados, nunca
soluciones de los proyectos. Control01 pasó12 checks reales. Control02 detectó
una falsa aceptación de readlink relativo tras chdir; la corrida fallida sigue
conservada. Control03 pasó15 checks tras corregir la resolución y reutilizó un
recibo cerrado sin reiniciar el sujeto. La captura de journal/planes/streams está
en evidence/study-evaluator-controls-01-03.tar.gz y su índice SHA por archivo.

La prueba unitaria inicial también detectó un supuesto incorrecto en una fixture:
`Z` precede a `a` en ASCII. El oráculo produjo el resultado correcto; se corrigió
el grafo del test antes de congelar. La corrida negativa se conserva. Hay23
checks unitarios actuales. Ninguna cifra es una puntuación de estudio.

La revisión independiente del transporte con esfuerzo explícito fue accept
(Gemini3.1ProHigh job76f57831568c490eb8aff580293af184, sólo texto, tests no
ejecutados por revisor). Host138 y cleanDocker138 habían pasado. La comparación
directa de bytes de controller/docker_roles/role_jobs confirma el wheel instalado
de image11; no equivale a una release final. La revisión de evaluador con MiniMax
job940b0b429d6c4603818cba2414d1affc terminó por timeout360s sin veredicto; no se
transforma en aceptación ni se reinicia ese job. Posteriormente se aisló el
defecto en fixtures de nodos/arcos: antes podían fallar también por referencias
inexistentes/duplicación, ocultando el defecto de capacidad. Se añaden ID de16
caracteres, paths de512/513 bytes UTF-8 y conteo de entradas no regulares. Estos
cambios y el evaluador completo requieren auditoría explícita, junto con
harness/protocolo, antes de prerregistrar.

La revisión de transporte03 fue reject. Control04 reprodujo falsa aceptación
por stderr/traza compartidos y falso rechazo por substring. Control05 ahora
queda inconcluso: se eliminó usar stderr como traza. En ese punto faltaba un
recolector separado que el sujeto no pudiera alterar; control05 no acepta la medición.
Los15 controles históricos03 no son prueba de robustez ante esos defects.
Los23 checks unitarios actuales pasan host y cleanDocker02; no suplen esa
medición pendiente. Ver study-evaluator-review-triage-v1.md y archivos de
evidence/study-evaluator-findings-04-05.tar.gz para la evidencia preservada.

## Recolector aislado posterior: aceptación acotada del borrador

El probe auxiliar ahora usa un recolector/trazador UID0 y sujeto UID65534,
sin capacidades efectivas. Sólo ese contenedor añade DAC_OVERRIDE, SETUID,
SETGID y SYS_PTRACE sobre cap-drop ALL; mantiene red none y root readonly.
La captura de stdout/stderr/traza ocurre en archivos y pipes separados. El
sujeto no puede acceder al directorio del recolector, alterar su traza ni
matar al trazador. Los sujetos ordinarios conservan UID1000/cap-drop ALL.
No se montan perfiles, esperados, evaluador, método, ledger ni Docker daemon.

Control06 falló por permisos de directorios afectados por umask027. Se
conservó antes de fijar explícitamente0755 en directorios declarativos y0644
en el probe. Control07 pasó los15 controles reales y reutilizó un recibo
cerrado. Isolation08 pasó seis controles reales: frontera de UID/capacidades,
spoof de stderr rechazado, ruta similar en scratch admitida, metadata O_PATH
permitida, readlinkat detectado y timeout. El archivo raw tiene349 archivos,
incluida la corrida negativa06; las fixtures se reconstruyen desde sus recetas.

Gemini3.1ProHigh job415dab7d34ea4d6aae94ef34f9119e38 emitió accept_draft sin
hallazgos, tests_executed=false. Los bytes de su input coinciden con las fuentes
actuales del trazador. Esa revisión no acepta el harness/protocolo ni una entrega
de software. La traza CLONE_FS de resolución desconocida queda inconclusa; no
se afirma custodia criptográfica o resistencia frente a todos los programas.

El harness de celdas y su presupuesto común ya tienen controles sintéticos,
pero su revisión01 fue reject y se corrigieron cierres terminales después.
La auditoría conjunta, gate de campaña, presupuesto acumulado y prerregistro
permanecen pendientes. No hay soluciones nuevas generadas.
