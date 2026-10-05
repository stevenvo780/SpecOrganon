# Evaluador nuevo v3: progreso verificado, campaña aún no admitida

El checkout independiente codex/comparison-v3-budget incorpora250recetas
(84FractionMix/82PolicyPick/84ListPatch), ejecución Docker con recibos/replay,
comparación de JSON exacta para enteros grandes, rúbricas D8/G6/H y análisis
descriptivo. Commit ab85a09cbc21b787fa10a168233b368fe0c63753. No se modifican
los ensayos cerrados ni el GOAL original.

Pasaron73controles pertinentes en host Python3.12.13 y Docker Python3.12.3
sin red, con fuente readonly. La imagen sigue conteniendo la wheel schema8;
no se atribuye esta verificación a una nueva instalación limpia. El preflight02
cerró37controles:28sujetos Docker reales,13conformes aceptados y15fallos deliberados
rechazados;9controles sin nuevo sujeto verifican replay y bindings cambiados.
Las fixtures de streams/observer no son programas de modelos ni prueban universalmente
los oráculos. Se conserva preflight01(31controles/22sujetos), anterior al sondeo
UTF8 reforzado. El sondeo detecta ignore; no demuestra toda forma de replace.

Gemini3.8Flash aceptó la segunda revisión de nueve fuentes completas actuales
del evaluador (job5dc753ad79fd49c7a0099bff6436949c). tests_executed=false y
comparison_registration_ready=false. Rúbricas/análisis posteriores no integran
esas nueve fuentes. La primera revisión queda preservada con sus imprecisiones
de índices; ListPatch exige base0. Las afirmaciones demasiado amplias sobre UTF8
se acotan en EVALUATOR_STATUS.md, conservando el dictamen nativo original.
Muse terminó a180.026s por timeout, sin output ni veredicto; no se reintentó su
handle ni se contó como aceptación. Una prueba unitaria inicialmente fallida y
un error de importación previo al preflight final también quedan documentados.

El diseño de secuencia revisado asigna al primerT ya prefijado el papel primario
del hito9fases y celda de comparación, sin presupuesto extra ni selección posterior.
Las42generaciones deben cerrarse y debe existir unT elegible9/9 antes de liberar
una sola evaluación reservada final. Si ningúnT cumple, las42evaluaciones se
conservan no evaluadas por requisito, sin imputar ejecución/fallos ni completar
la goal. Esta regla aún necesita implementación y aceptación conjunta.

Próximo trabajo: harnesses N/S/T/A con reloj/presupuesto global y por celda,
verificación de evidencia sustantiva/recibos, separación física y auditoría final,
ligadura del orden/mapping opaco fijo y revisión/registro inmutables. Después
ejecución de las42celdas, evaluación habilitada por el hito, instalación limpia
versionada CLI/MCP y publicación final. Cero autores nuevos, cero entregas9/9,
cero comparación; goal activa y aún incompleta. No sustituir el ensayo por
otro caso ni reabrir campañas cerradas para obtener victoria.

Preservación actual:30inputs backup,48bindings campaña02,179CSVShape,49LotLedger,
sus dos ledgers cerrados y GOAL.md coinciden byte a byte. Las copias de los drivers
de preflight conservan el byte final extra para coincidir con sus hashes ejecutados;
git diff --check reporta esas dos líneas vacías de evidencia, mientras el código,
contratos y documentación del commit pasan el control de espacios.
