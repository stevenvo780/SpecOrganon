# Verificador candidato de evidencia nativa y física

provenance.py lee diarios existentes por descriptor de sólo lectura y valida
request/admisión/cierre/streams. No construye diarios, copia perfiles, llama a
modelos ni cambia ledgers. Comprueba inputs y library/bridge contra fuente,
container/image/label/handle/estado final, límites 2CPU/1GiB/128pids, usuario de
imagen, montajes, comando y working directory. Tests físicos carecen de red y
credenciales. Una medición debe coincidir con el recibo entero, argv, entrega,
capturas y salida física; un fallo/timeout no se convierte en passed.

Cada rol nativo debe corresponder a la ruta original Codex o Gemini. El verificador
reconstruye el prompt y el payload stdin, coteja bytes/hashes/cierre real y parsea
el stream nativo con el puente. Codex requiere catálogo público/proyectado,
effort solicitado y preflight de features ligado a las mismas opciones. Gemini
requiere ejecutable original y el stream observado sin eventos de herramientas.
No se demuestra desactivación absoluta de herramientas internas de Gemini ni
identidad criptográfica del proveedor/pesos. SHA256 y cierres atestiguan coherencia
bajo el límite de confianza del operador y Docker; este módulo no usa HMAC.

toolkit_milestone liga historia actual, cada acción/phase/source snapshot,
autor/revisor/approval nativos y tests físicos. Exige aprobación de mandato
conforme y targets actuales, reviews aceptadas del snapshot vigente en cada fase,
autor y peer en contenedores separados y auditoría final D8/G6/H completa con
locators resueltos en los documentos suministrados. La auditoría final se coteja
con estado/files/historia/mediciones actuales reconstruidos, no sólo con su label.
La sustancia procede del juicio nativo independiente; resolver un locator no
demuestra por sí solo verdad, independencia o eficacia de campo. El módulo aún
debe conectarse al runner/registro global y no se ha ejercido sobre una entrega
nativa NUEVA de nueve fases.

Preflight02 verificó dos recibos históricos completos (autor Codex y peer Gemini)
en contenedores distintos, su replay de lectura y rechazo de request/actor
cambiados. Los162archivos del transporte histórico quedaron idénticos. Aparte,
ejecutó dos fixtures Python en el contenedor fijado: éxito y salida3, con rechazo
de promoción de fallo. Cero nuevos autores, celdas comparativas o hitos9/9. El
ensayo histórico LotLedger sigue cerrado y adverso.

Pasaron142controles v3 en host Python3.12.13 y Docker Python3.12.3, incluido un
diario Python realmente ejecutado y23controles nuevos de integridad/aislamiento.
Los records Docker simulados de tests son controles de schema/rechazo, nunca
receipts nativos o evidencia9/9. Docker monta src/tests actuales; la imagen sigue
conteniendo el wheel anterior, sin instalación de una nueva release.

Revisión Gemini3.8Flash job650f982e579943f4a363055b51f0d875: accept acotado,
tests_executed=false y registration_ready=false. Recibió105307bytes de texto,
target/dependencias principales completos y excerpts explícitos del controlador/
journal/Toolkit. Se conserva el resultado fenced original. Su mención de HMAC
en limitations se corrige arriba. Revisó13controles de provenance; los10guards
de inspección añadidos después pasaron host/Docker pero no aquella revisión.
El código de runtime revisado permanece idéntico a lo enviado. La revisión previa
access=read job5169b8b52f0c47d4a219fe04beccabba agotó240s sin veredicto; se conserva.

Diagnósticos corregidos: NameError inicial al situar el check de catálogo fuera
del branch Codex y guard de usuario que no incluía el usuario real ubuntu de la
imagen de tests fijada. Se corrigieron antes del preflight02 final; no ejecutaron
autores ni modificaron registros históricos.

Pendiente: reconciliación/fallo nativo con outcomes reales en RunJournal, runner
del orden y mapping privado42, export/evaluación opaca única, callbacks completos
de fuentes/registro/cuota, revisión conjunta y registro inmutable antes de autores,
al menos una entrega T nueva9/9 y la evaluación comparativa prevista. La goal
permanece activa; publicación final y release CLI/MCP nuevas siguen pendientes.
