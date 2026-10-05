# Rutas y presupuesto candidatos v3: sin admisiones

budget.py conserva un diario único de las42celdas prefijadas, llamados/bytes y
relojes de campaña/celda; registra consumo antes de dispatch y liga source/policy/
registration. Un callback obligatorio debe verificar el registro completo y las
fuentes, no sólo devolver un hash sin leerlos. Otro valida cuota actual antes de
cada admisión nueva. Estos callbacks y el runner de registro aún deben conectarse.
Construir la clase no registra el estudio. No hay CLI de generación v3.

Los handles admitidos conservan sus bindings y se reconcilian sin renovar relojes
ni asignar reemplazos. Quedan pendientes hasta comprobar su outcome; una excepción
incierta bloquea cierre. Falta conectar reconciliación y clasificación nativa de
fallos con recibos reales; el diario no fabrica un outcome para permitir avanzar.
La cuota se comprueba antes de reservar y se reevalúa el tiempo tras esa espera.
Una ventana restante menor que180s/120s retiene una nueva llamada/test.

Todos los roles, incluida la auditoría final bajo rol review, consumen el mismo
techo40/celda. La suma renderizada usa exactamente el texto que el puente recibe,
con instrucciones y request; render_prompt recibe bytes y retorna request parseado
más un texto único. No se inventa un system prompt adicional, tokens o dinero.
Los tests tienen techo2 y la segunda admisión necesita tanto ejecutable/argv
cambiados como fallo previo o rechazo semántico ligado a aquella entrega.

cells.py conserva los mecanismos previos de snapshots, programas sellados y
replay de packets, adaptados a las tres tareas nuevas. N elige proceso y puede
registrar notas opcionales; tiene llamadas program/tests/final-review y un test.
S tiene spec/design/tasks/program/tests/verification/final-review, con especificación,
diseño y tareas anteriores al código y VERIFY.md posterior a la medición. A tiene
siete fases candidatas anteriores al build, dos llamadas de construcción, test,
validate y auditoría final. Un fallo del primer test puede añadir una reparación
con el segundo test. La revisión final es única y no produce feedback reparable.

A reutiliza la preparación de puts del controlador T: kinds de fase, IDs/versiones/
refs actuales, prohibición de resultados/approval/advance inventados, presupuesto
completo almacenado y programa/README sellados antes de añadir tests. Guarda sólo
status=candidate, sin eventos de aceptación/revisión/advance. El juicio semántico
intermedio se retira; la auditoría final juzgará sustancia/trazas/candidatos. Sus
mediciones quedan en el diario real aparte del borrador test, sin convertir una
fixture o documento en ejecución. No se imponen aprobaciones retiradas al puntuar A.

T reutiliza el engine/controller schema9 vigente, incluido paquete/trace/test gate,
y añade la misma auditoría final D8/G6/H. La historia/snapshot y mediciones se envían
una sola vez para evitar repetir estado. La rúbrica deriva las nueve fases canónicas:
frame, critique, study, observe, explain, compare, specify, build, validate. Las
decisiones se registran en specify; la versión candidata anterior de rúbrica con
choose era incorrecta y se conserva en el commit previo, sin autores afectados.

Pasaron142controles en host y Docker source-mounted. Son controles mecánicos, no
programas nativos correctos ni nueve fases nuevas reales. provenance.py añade
verificación física de receipts/autores/revisores y auditoría/locators actuales;
su preflight cotejó dos roles históricos separados y dos tests físicos de fixtures.
Véase PROVENANCE_STATUS.md. Falta conectar ese verificador al registro/runner,
runner de campaña con fuentes/images/orden/mapping privado ligadas, export/evaluación
opaca única, reconciliación/fallo nativo y revisión conjunta/registro inmutable.
Las guías/mandato públicos son candidatos y no cambian el orden ya generado.

La compuerta global exige42generaciones admitidas y cerradas; no admite un row
not_started como completo. Verifica todas lasT prefijadas mediante el verificador
registrado. Una prueba inconclusa retiene evaluación sin sellar un falso fallo.
CeroT elegibles concluyentes sella not_evaluated_by_prerequisite; al menos unaT
verificable permite released_once. Ninguno de estos estados autoriza una cohorte
nueva o un reintento. Los callbacks sintéticos de los tests nunca son evidencia
que satisfaga el hito9fases de la goal. Cero autores y cero entregas9/9 actuales.

El último código aplica correcciones de dos revisiones nativas de presupuesto
(revise) y una revisión de rutas/rúbrica (accept de alcance anterior a correcciones
menores). Todavía no tiene aceptación conjunta del snapshot actual; véase
HARNESS_REVIEW_TRIAGE.md. Los116controles intermedios Docker también se conservan.
