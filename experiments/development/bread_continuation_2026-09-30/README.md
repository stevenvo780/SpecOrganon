# D-097 · Análisis alimentario desde el checkpoint pendiente

Esta ronda continúa el trabajo propuesto por D-096. Conserva su checkpoint
inicial y prepara un análisis nuevo de los dos artículos alimentarios
archivados, con código y fuentes inspeccionables. Las decisiones normativas
y las cuatro fases permanecen pendientes; no se interviene en campo.

## Diseño anterior a la generación

El [plan](plan.json) fija una generación con gpt-6-luna medio solicitado,
240 segundos locales y autenticación ChatGPT existente reportada. Una
propuesta válida contiene código Python, fuentes e informe como strings;
sus bytes originales se conservan. No se admiten herramientas observadas,
errores de CLI, fallback API, reparación o segunda generación.

Los seis archivos del paquete original conservan sus pins. Los [textos
crudos completos](raw_texts/text_manifest.json) se obtuvieron mediante el
`pdftotext -layout` local fijado antes de generar. Conservan delimitadores
de página y procedencia hacia ambos PDF. No incluyen referencia aritmética,
código anterior, métricas previas ni rúbrica. La inspección independiente
reprodujo la extracción y verificó nueve insumos y tres pins D-096.

El workflow se detiene en `awaiting_review` antes de ejecutar el código.
La ejecución exige el SHA exacto revisado; esa declaración local no
autentica una persona o custodia externa. El código original queda intacto;
se añade únicamente el prefijo de intérprete registrado para ejecutarlo
mediante un memfd sellado. Landlock/seccomp aplican límites de lectura,
red y procesos descendientes; no se conceden directorios de escritura.
La ejecución basal dispone de 30 segundos, CPU de 10 segundos, espacio
virtual de 512 MiB y 2 MiB por stream/archivo. Runtime e intérprete no están
sellados, no hay cgroup o cuota agregada y se mantienen los límites del
sandbox ante acciones concurrentes del mismo UID.

Después, el [evaluador congelado](evaluate.py) permite una ejecución por
cada condición: PDF alterado, PDF ausente y unidad contradictoria con
manifiesto actualizado. Comparten 45 segundos locales; nunca se reemplaza
un resultado. La condición de rechazo observa salida no cero, stderr y
ausencia de métricas válidas. **La causa del error requiere revisión
separada**: el cambio de unidad/manifiesto no aísla por sí solo una
detección semántica. La pausa de revisión queda fuera de ambos presupuestos;
tokens, coste, concurrencia global y cancelación remota siguen sin cap o
atestación externa.

## Evaluación e interpretación

Se fijan antes de observar el nuevo análisis 25 cotejos aritméticos con la
referencia expuesta D-094 y 23 contratos cuantitativos de valor, unidad y
base no vacía. La aritmética no verifica el significado de la base, los
pasajes, la calidad del informe, autoridad humana o impacto. Un revisor
distinto examinará código antes del replay y fuentes/límites posteriormente.
Es una revisión técnica nativa; no equivale a dos jueces humanos ciegos.

El paquete usa datos secundarios de artículos publicados; la encuesta es
descarte autodeclarado, sin ingesta pesada o identidad entre hogares y
producto del ACV. Siguen faltando registros enlazables de lotes, calidad,
almacenamiento, transporte, transformaciones, consumo y perjuicios por
actor, además de sitio, decisiones humanas y diseño causal aprobado.

Esta ronda no calcula Q, no selecciona modelo/método, no acredita calidad
equivalente de Luna y no cuenta entre las 24 corridas. El veredicto global
continúa **0/5**. El resultado real se incorporará tras congelar el workflow,
sus pruebas y este diseño previo, ejecutar y conservar los artefactos.

## Brecha adicional observada

La exploración encontró que `scripts/verify_bread_frame.py:319` todavía
espera aceptación e independencia históricas, mientras el README del caso
y el motor actuales consideran esa revisión `legacy_unverified`. Sus
funciones documentales verificaron las nueve cifras originales, pero su
`main` requiere reconciliar esas expectativas antes de reutilizarlo como
sonda de aceptación actual. D-097 usa un workflow propio y conserva esa
brecha como pendiente; no atribuye aceptación al auditor histórico.

## Resultado posterior al diseño congelado

Las secciones anteriores registran el estado prospectivo del commit
`6a8018c`, anterior a la generación. Este apartado incorpora la evidencia
observada; no cambia el plan, evaluador, criterios ni candidato.

Una sola CLI solicitó Luna medio y terminó sin errores ni herramientas
observadas. Dejó el [script original](attempt/analysis.py), [fuentes](attempt/sources.json)
y [reporte de 780 palabras](attempt/report.md). El modelo duró 134,356 s;
el supervisor de generación, 134,488 s dentro de los 240 s registrados.
Uso informado por la CLI local: 57.670 tokens de entrada y 7.206 de salida,
incluidos 443 de razonamiento como desglose. Coste, modelo efectivo y
telemetría carecen de atestación externa.

La [revisión anterior al replay](script_review.json) declaró seguro el
script para el sandbox offline, pero rechazó su viabilidad. Dos extractos
de Tabla 1 exigen un espacio más del presente en el texto fijado. Se consumió
el único replay registrado para observar ese negativo, sin editar el código:
código **2**, sin error de lanzamiento o timeout, stdout vacío y [stderr](attempt/baseline.stderr.txt)
`analysis error: survey Table 1 passage audit failed`. Duración del sandbox:
0,076 s; supervisor del replay: 0,099 s. El prefijo de intérprete registrado
y el script original coinciden con el payload sellado.

No se creó `metrics.json`: los **25 cotejos y 23 contratos quedaron sin
medir**, con puntuaciones nulas. Las tres variantes negativas quedaron sin
ejecutar porque el evaluador exige `replayed`; no se atribuye rechazo
semántico al fallo basal. La revisión estática también observó una unidad
distinta del contrato y comprobación directa de sólo tres de siete filas,
sin convertir estos hallazgos en una puntuación hipotética.

El [archivo](archive_receipt.json) conserva 27 archivos públicos y salidas
originales, byte idénticos. `run.lock` y `work/.gitkeep` son dos archivos
operativos vacíos creados para releer el archivo desde Git; se registran
por separado y no son outputs originales del modelo. Un proceso nuevo y un revisor verificaron los
pins, `failed`, replay/relanzamiento bloqueados y ausencia de métricas o
evaluaciones adicionales. El [resultado](outcome_inspection.json) distingue
generación completada de análisis fallido. No hubo reparación, reemplazo,
segunda llamada ni cambio del checkpoint inicial D-096. GOAL, motor,
cinco ledgers y 113 archivos de dossiers anteriores siguen intactos.

Las 53 pruebas previas del workflow/evaluador pasaron con CLI falsa y
sandbox local real; no prueban la calidad del candidato. La aceptación
permanece **0/5**, Q nulo y ninguna corrida de las 24. Luna produjo una
propuesta inspeccionable, pero esta ronda no demuestra calidad equivalente.
Para un diseño posterior queda planteado contrastar auditoría documental
robusta ante espacios, todos los valores/unidades y siete filas, con errores
cuya causa se pueda aislar. Este candidato no se relanza.

La brecha adicional del auditor histórico se corrigió después en D-098,
commit `c971090`: [sonda actual](../bread_legacy_probe_2026-09-30.json) y
[validación independiente](../bread_legacy_probe_validation_2026-09-30.json).
CLI/MCP operan sobre copia temporal, conservan nueve archivos originales
y reconocen `legacy_unverified`, siguiente `review_phase` y falta de firma.
Pasaron 16 pruebas; este fix no acepta fases o normas del caso alimentario.
