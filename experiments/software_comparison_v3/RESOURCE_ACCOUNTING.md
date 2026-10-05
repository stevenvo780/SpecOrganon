# Contabilidad prospectiva schema9: candidato de ingeniería

El ensayo LotLedger permanece cerrado con su límite original y su resultado
adverso. Este checkout separado cambia la guía de futuras ejecuciones; no admite
retrospectivamente su respuesta, no modifica sus49 fuentes ni migra su ledger.

El límite por fase sigue siendo6 elementos y6000bytes. Se mide el mapa COMPLETO
de elementos que `engine.get_state` devuelve después del replay privado: claves,
deps/versiones, autor, secuencia y flags derivados, además de texto/data. La medida
es `len(canonical(canonical(value).decode('utf-8')))`, es decir JSON canónico UTF8
vuelto a codificar como string JSON. Contar sólo el manifiesto o el texto no basta.

Cada petición incluye `resource-accounting.json` con columnas declaradas y el
recuento/coste actual de las nueve fases, el mapa de archivos y sus límites. Es
información del snapshot, sin garantía de aceptación de un manifiesto futuro.
Los reemplazos, referencias y flags posteriores pueden cambiar el coste completo.
La admisión privada sigue rechazando exceso antes de writes/puts de producción;
no concede llamadas, reinicios o presupuesto adicionales.

La política nueva es schema9 y fija el hash de software_controller.py. Las
políticas anteriores fallan antes de recrear la entrega o alterar el caso. Los
ensayos anteriores conservan su checkout/política para reproducirse. Este código
no es todavía una nueva wheel instalada ni una release final.

Verificación:65 controles sintéticos pertinentes pasan en host Python3.12.13 y
Docker fijado Python3.12.3, con fuente montada readonly y sin red. Cubren precisión
de costes/escapes/Unicode, diferencia response-vs-stored, rechazo atómico, política,
contexto máximo, compuertas y recuperación SIGKILL. Tres intentos de verificación
conservaron fallos por contexto máximo; se compactó la guía, sin acortar el estado,
archivos ni streams ni aumentar110000bytes por request/128000renderizados.

Muse Code nativo revisó diez fuentes completas y aceptó este cambio de alcance
limitado; tests_executed=false en su revisión. Los tests los ejecutó el coordinador.
La revisión NO acepta una nueva entrega9/9, registro42celdas, instalación limpia o
tesis. Evidencias y hashes están en evidence/.

Los contratos candidatos FractionMix/PolicyPick/ListPatch se precisaron tras
revisión de diseño Gemini3.8Flash. La prueba aritmética independiente en Docker
confirma una entrada válida de38836bytes/1000 términos con denominador7331dígitos:
la conversión predeterminada4300 falla y ambas formas de suma exacta concuerdan.
Es un diagnóstico de dominio/entorno, no un programa entregado o una receta F60
evaluada. Faltan180recetas, harnesses/rubricas/análisis y revisión/registro conjunto.

La selección de tareas/orden anterior a outputs sigue fija; no se ha generado una
celda. Antes de generar debe resolverse también la secuencia del objetivo: una
entrega nueva real9/9 precede a la evaluación comparativa. No se autoriza perseguir
una victoria mediante sustituciones del ensayo cerrado.
