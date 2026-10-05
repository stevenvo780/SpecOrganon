# Integración v3 y revisión antes de autores

El candidato vive en `/home/stev/.codex/worktrees/comparison-v3-budget/SpecOrganon`,
commit5ff7c8ea. registration.py valida fuentes, imágenes, perfiles originales,
presupuesto, mapping original y revisión nativa completa; campaign.py conecta
el orden fijo de42celdas con recibos físicos; evaluation.py conserva el gate
global, exports opacos, idempotencia, F/D/G/H y pares completos por tarea/familia.
El checkout principal sólo registra seguimiento; no contiene esos módulos nuevos.

Pasan177controles v3 y45controles de contratos/recursos:222 en host y222 en
Docker aislado, con fuente readonly. Son controles del mecanismo, no42entregas.
Una solicitud inválida real fue rechazada por Docker antes de arrancar el CLI
nativo; ese fixture comprueba clasificación de errores, no una llamada a un modelo.
Las dos pruebas nativas históricas se releen sin modificar162archivos anteriores.
Se verifican306bindings históricos, GOAL.md original y dos ledgers cerrados intactos.

La primera revisión completa51cff9f2fe464d7e86bdb435f0a2c2b8 devolvió accept
dentro de un bloque JSON, pero antepuso prosa y una afirmación de pruebas en
background contradictoria con tests_executed=false. El parser estricto la rechaza:
se conserva íntegra y no se transforma retrospectivamente en aceptación válida.
El bridge no suministra traza de herramientas o un handle de esas pruebas.

Se agregaron estratos por tarea y familia antes de todo autor, sin cambiar
protocolo, tareas, modelos, mapping, reglas ni presupuestos. La nueva revisión
estática6a274c1b408643f98051490b98c7ba25 corresponde al manifest
a4d31cd31a527666085bb1b4b4d231f65d439d48ebcf965ee96e37f77f1ca02f,
72fuentes. Sigue pendiente un recibo admisible y su registro inmutable.

No hay nueva entrega real de nueve fases ni resultado comparativo v3.
No se reabren ensayos cerrados. La instalación final CLI/MCP y la publicación
de resultados de esta campaña continúan pendientes; la goal sigue activa.

## Estado posterior: registro real y primera celda

El candidato final vive en el mismo checkout, commit37480281. Se añadió la
dependencia importada scripts/study_cell_budget.py al snapshot y al guard de
procedencia del módulo. La revisión estática03 aceptó ese snapshot, pero el
primer registro real03 falló: usaba safe_file de entregas sobre .agents y uv.lock.
El archivo y el recibo del fracaso se conservan; no se admitieron autores entonces.

Se corrigió únicamente el validador de rutas de fuentes, manteniendo las reglas
de entrega. Las pruebas completas sintéticas de registro distinguen su juicio
inventado de un recibo nativo real. Pasan235controles en host yDocker. La revisión
estática nativa04 de Gemini aceptó las73fuentes actuales con SHA
4334e828602dcb9eeaa403ffa3d47211cbccd533481eda6911c1e6867aa1cfae.

El registro inmutable04 valida y liga74archivos (73fuentes+recibo de revisión),
SHA0bc7182ab4713080db3120183e11ca45ad1f6f1ed752c856dc4028b24b728ed5,
registrado2026-10-05T19:09:10.925366Z antes de la primera admisión. La consulta
de status no invoca modelos ni libera evaluadores. El mapping original sigue
privado e intacto; los42outputs aún deben materializarse bajo el protocolo.

La primera celdaT FractionMix/Codex/r1 ya tiene un autor nativo de frame con
recibo físico cerrado verificado. La revisión separada Gemini está en curso.
No se ha demostrado todavía una entrega nueva9fases ni liberado evaluación
reservada. Consultar checkpoint.json y recibos posteriores para la evolución;
esta aceptación estática demuestra preparación de ingeniería, con ejecución
y resultados metodológicos pendientes.

## Primer hito nativo completo y físicamente elegible

La celdaT primaria cerró las9fases con23llamadas nativas,1prueba propia real
pasada y1,302,492bytes renderizados acumulados; elapsed1526.46s dentro de6000.
La auditoría final Gemini aceptó D8/G6/H9 y el verificador físico confirmó
statuseligible, SHA91b38c9670666a2d725c13e7b37cdaf353b5be8505fefd1138498aba297eda98.
Hay exactamente1de42generaciones terminales y41pendientes.

La observación de cuota expiró antes del test; se conservó el mismo paso,
artefactos y reloj, se actualizó la observación y la prueba se ejecutó una vez.
validate corrigió un enlace incompleto a baseline antes de su aceptación,
manteniendo versiones e historia; no se modificó el programa sellado ni
se repitió la prueba. La evidencia de estas recuperaciones procede del flujo real.

El expediente conserva assessmentno_demostrado: la matriz reservada y la
línea base comparativa no se han medido. La auditoría nativa del paquete es
un juicio técnico; la funcionalidad completa se medirá tras cerrar las42
generaciones y liberar una sola evaluación. No existe resultado F reservado.

El reporte y los recibos de este hito están en evidence/comparison-v3-primary-T-*.
El paquete legible de tres archivos es una copia exacta de la entrega sellada
en el workspace privado, sin nueva generación ni reejecución. El registro,
software y protocolo siguen congelados. La instalación final y publicación
quedan pendientes del cierre de toda la campaña; la goal permanece activa.


## Generación fija y candidato de instalación rc2, 2026-10-05

Cinco celdas originales cerradas: T1 completa/eligible; A2 inválida por IDs con
puntos; N3 excede el límite común de entrega al generar las pruebas; S4 y S5
exceden el límite de contribución de spec. Se conservan salidas, recibos y
entregas parciales, sin reintentos ni sustituciones. T6 continúa desde su reloj
original y ya pasó su ejecución Docker propia; falta su cierre y prueba física.
No se ejecutó la evaluación reservada ni se atribuye causalidad a esos fallos.

El coordinador73031 terminó antes de una admisión por fallo de lectura de /usage.
No dejó un native handle pendiente. El coordinador33178 conserva presupuesto y
ledger; admite la observación CLI de la cuenta original del colector con su
capturedAt real y antigüedad máxima600s, o una captura directa del mismo perfil.
No usa cachedAt como fecha de observación, cambia cuenta ni activa polling Codex.
El respaldo y los fallos de lectura se conservan en el área privada.

En otro checkout, rc2 cambia únicamente la versión y documentación del candidato.
Build offline sobre imagen fijada y nueva venv: dos wheels idénticos, origen de
29 módulos verificado,69 controles instalados, CLI15/MCP15 por stdio real con
fixtures, reanudación tras SIGKILL y PDF20páginas con rechazo de pins incorrectos.
El kit fuente exportado pasó también69 controles sin montar src. Cinco controles
de vinculación al checkout se excluyen de ese perfil; no se afirma toda la
plataforma verde. El primer intento de curar el kit usó dos nombres inexistentes
de bridge: falló antes de producir el ZIP y se corrigió usando fuentes registradas.
El paquete final local tiene104entradas más manifest, no contiene perfiles ni el
registro privado portátil de la campaña. Candidato no publicado ni release final.
Los306bindings históricos, GOAL original y ledgers CSV/Lot permanecen intactos.

T6 cerró las nueve fases actuales y su auditoría final nativa; la comprobación
física produjo eligible, con deliverySHAef8072333ab051347b54aded78950c2432f4aa8c61c8d258d0eb33934bb229b4.
Tiempo original1014.271s. Ya hay dos entregas T9eligible, ambas FractionMix/Codex
en las dos repeticiones fijadas. No constituyen diversidad de tareas/familias
ni resultados F; faltan36cierres y la evaluación. No se repitió el programa
tras su prueba ni se usaron sujetos reservados.
