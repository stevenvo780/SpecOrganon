# Candidata dev5: recuperación del control Docker

Dev4 registró tres fallos `Docker control deadline exceeded`. Una inspección
posterior encontró sus contenedores con estado `created` y StartedAt cero:
role-09-observe-review del intento01, role-08-observe-author del03 y
role-01-frame-author del04. No se reanudaron ni cambiaron sus resultados.
El fallo restante del02 agotó dos autores de compare con mapas de6436 y6150
bytes frente al límite6000; tampoco se convirtió en aceptación.

Dev5 añade excepción de deadline tipada, intento persistido antes de create,
nonce por trabajo, identidad/fecha de creación y comprobación común de que
el contenedor nunca arrancó. Cada creación tiene una sola oportunidad:
un crash incluso antes de invocar Docker mantiene la incertidumbre si falta
un handle recuperable. El CID y el hash de la observación se guardan juntos
antes de start. Reanudar exige marcas históricas intactas, también con un
recibo cerrado. La política schema5 impide reutilizar raíces schema4.

La revisión de diseño Gemini rechazó el primer diseño; Codex rechazó dos
implementaciones intermedias. Los hallazgos, fuentes finales entregadas y
aceptación estática quedan en design-review-01 y code-review-01/02/03.
El recibo review-source-verification verifica siete fuentes de producción,
versión y pruebas contra el snapshot aceptado. El script auxiliar revisado
era el del control03; el control04 usa otros destinos y se archiva separado.
Ningún revisor ejecutó pruebas ni aprobó una fase metodológica.

Verificación final:328 controles locales (tests-06),328 sobre el wheel
instalado sin red (installed-tests),31 módulos idénticos byte a byte,
CLI exit0 y MCP stdio real con24 herramientas (installed-runtime-02).
Los controles Docker reales finales son tres, con respuesta de create perdida
por inyección: recuperación, contenedor ya ejecutado rechazado e interrupción
antes de guardar CID reanudada. Cada uno hizo una sola creación y el contador
del programa quedó en1. No hubo modelos, credenciales ni fases en estos controles.
Esto no reproduce el timeout natural15s ni prueba fiabilidad nativa general.

Se preservan los errores iniciales: ruta errónea /opt/specorganon/.venv en
component-01, y workspace ausente para el smoke MCP en installed-runtime.
Las salidas tests-03 conservan el error de ruta del módulo de pruebas.
Los runs01/02/03/04, incluidos los intermedios, conservan sus inventarios.
wheel-01 es una compilación intermedia anterior al cierre de las revisiones;
solo el wheel de releases/method-superiority/dev5 es la candidata final.

Cada llamada de control Docker vence a15s. JobStore limita la admisión de
payload por6000s transcurridos, contando preparación previa; no reserva el
coste de preparación Docker ni garantiza un deadline estricto de extremo
a extremo. Un rechazo de admisión puede dejar un contenedor propio nunca
arrancado. La eficiencia debe calcularse con wall_seconds total de cada
intento, no con la suma de duraciones de receipts.

El observador native02 usa los45 hashes registrados y compila exactamente
el driver y paquete dev4 congelados. Verifica cierres, package_gate y recibos
de los checkers sin invocar run/step/call/measure ni reemplazar report.json.
Al corte03:43:23UTC había6/10 cerrados:2 completos, LedgerFold104 y TopoPlan105
checks públicos,4 fallidos. La cohorte sigue;9/10 ya es inalcanzable. Cero
sujetos reservados y cero generaciones dev5. La meta permanece activa.
