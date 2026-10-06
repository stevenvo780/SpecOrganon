# Revisiones de infraestructura v3: alcance y cambios conservados

Gemini3.8Flash01 presupuesto, jobcc64818d95b9419db68717d2d5f46bb7,
146.5s, revise, tests_executed=false. Se aplicaron un contrato explícito para el
callback de registro completo, comprobación de policy vigente y reloj tras esperar
cuota, y la retención sin sellado ante un hito inconcluso. Las dos alertas sobre
render_prompt eran incorrectas: la función real recibe bytes canónicos, retorna
request parseado y texto único con todas las instrucciones. Se comprobó con el
puente completo y un control de bytes UTF8; no se cambió su API ni inventó un
system prompt adicional. Documents null falla antes de admisión en ese puente.
La auditoría final usa rol review y consume llamadas comunes. Una entrega ausente
se exporta como mapa vacío con digest real, sin aceptar None como digest.

Gemini3.8Flash02 presupuesto, jobb21fc32b799c4be2820e8553d3163452,
126.2s, revise, tests_executed=false; respuesta original cercada con markdown
conservada como texto, sin hacerla pasar por packet válido de fase. Se aplicaron
rechazo de cualquier dispatch tras sellado, bandera explícita de evaluación
permitida y plazo global al cerrar una generación completa. El backend original
ya impide reiniciar handles cerrados; la comprobación adicional evita siquiera
volver a llamarlo en una celda sellada. Los outcomes tampoco pueden sobrescribirse.
Las modificaciones tienen controles pero aún no nueva aceptación conjunta.

Gemini3.8Flash01 rutas/rúbrica, jobfca14ca8908041018704a059854cb55e,
142.9s, accept scoped, tests_executed=false y registration_ready=false. Se aplicaron
retención de al menos un test propio en reparaciones, un formato de fallo consistente
y eliminación de documentos duplicados en contexto final. Se rechazó su propuesta
de convertir UncertainJob en terminal failure: una observación incierta requiere
comprobar/reconciliar ese handle, no inferir fin o crear reemplazo. Basic propaga
la excepción y Toolkit ahora hace lo mismo. Un control conserva mismo job/index
en dos observaciones y no inventa terminal. No se afirma que los tests del revisor
se ejecutaran ni que esas rutas ya formen un runner42completo.

Integración local corrigió una rúbrica candidata que decía choose y omitía explain;
se liga ahora al workflow real frame/critique/study/observe/explain/compare/specify/
build/validate. El fixture A inicial también confundía kinds con fases y reveló
que ControllerError faltaba en su wrapper; los kinds del fixture se corrigieron
y errores de puts se registran sin aplicar el candidato parcialmente. Se conservan
los resultados iniciales6pass/3fail. Un fixture aritmético de bytes de presupuesto
esperaba exceder el techo un llamado antes; la función midió correctamente menos
bytes, se corrigió el fixture a31llamados y se conserva11pass/1fail. Un primer
comando usó una venv inexistente en el worktree y no ejecutó tests; se usó después
la venv existente del checkout principal, sin crear ni copiar perfiles.

La última admisión estricta N/S rechaza schema booleano y campos de resultados
inventados; los locators se resuelven sólo en documentos efectivamente suministrados.
Resolver presencia no verifica verdad semántica, modelo o test: audit_evidence.py
lo declara y no admite el hito. Ninguna de estas fixtures constituye autor nativo,
programa de la cohorte, fase aceptada o superioridad comparativa.

Quedan pendientes el verificador físico/semántico del hito, reconciliación nativa
con cierre inconcluso comprobado, runner registrado/orden/mapping/export/evaluación
opaca, pruebas de integración pertinentes y revisión conjunta del snapshot final.
Las fuentes efectivamente revisadas y el último código distinto se ligan por
hashes en evidence/harness-review-bindings-01.json; no se reaplica un accept viejo
a fuentes nuevas. No se han admitido autores ni reabierto campañas anteriores.
