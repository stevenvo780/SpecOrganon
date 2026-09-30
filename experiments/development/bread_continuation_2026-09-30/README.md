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
