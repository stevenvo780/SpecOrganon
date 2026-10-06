# Evaluador prospectivo v3: alcance verificado, registro pendiente

Se implementaron250recetas deterministas antes de admitir autores:84FractionMix,
82PolicyPick y84ListPatch, con dos ejemplos públicos por tarea. reserved.py genera
el inventario y compara salidas exactas con tipos JSON estrictos; subjects.py
ejecuta snapshots de entrega en Docker sin red ni credenciales, liga imagen,
fuentes, receta y archivos, y conserva cada handle/recibo para reconciliación.

Los enteros grandes se comparan como números JSON con representación decimal
exacta interna; una string numérica, float o bool no satisface el contrato.
La entrada FractionMix de1000términos produce un denominador7331dígitos y concuerda
con una segunda construcción aritmética independiente. ListPatch usa únicamente
índices base0 del estado vigente, incluidas eliminaciones. No inferir dificultad
equivalente ni exhaustividad a partir del inventario finito.

Pasaron73controles en host Python3.12.13 y Docker Python3.12.3 de imagen fijada,
con fuente readonly. Esta imagen todavía contiene la wheel anterior schema8;
esta ejecución verifica las fuentes montadas, no una wheel nueva instalada.
Los50controles del evaluador,12de rúbricas y11de análisis incluyen negativos de
tipos/framing/digests y desconocidos. La procedencia sustantiva aún requiere harness.

El preflight02 cerró37controles con28sujetos Docker reales:13salidas conformes
pasaron y15fallos deliberados fueron rechazados. Otros9controles verificaron replay
cerrado y rechazo de receta/archivos cambiados sin nuevo sujeto. Son fixtures de
transporte/observación; salidas preparadas no prueban un programa generado ni la
corrección universal del oráculo. Preflight01(31/22) se conserva separado, antes
del fortalecimiento UTF8; no se reemplazan recibos bajo la misma identidad.

El sondeo UTF8 prefixa0xff a JSON válido: detecta decode(errors='ignore'), que
lo convertiría indebidamente en entrada válida. No demuestra detectar cualquier
decodificación con reemplazo. El observador strace vigila un conjunto finito de
syscalls de stdin; es instrumentación de conformidad, sin prueba anti-tamper.

Gemini3.8Flash revisó nueve fuentes completas y aceptó el alcance del evaluador;
la segunda revisión corresponde al sondeo UTF8 actual. tests_executed=false.
Las nuevas rubric.py/analysis.py no pertenecen a esas nueve fuentes y aún no están
aceptadas por revisión nativa. Las frases de la primera revisión sobre índices
base1/base0 no cambian el contrato base0. La revisión posterior sobre ignore/replace
excede lo que prueba ese sondeo; esta limitación permanece explícita.

Muse recibió una revisión independiente de fuentes completas y terminó por
timeout180s, sin output/veredicto. Se conserva el recibo; no se interpreta como
aceptación ni fallo del software. Un fallo inicial unitario con imagen ficticia
y un fallo de importación del preflight ocurrieron antes de los controles finales;
no se ocultan ni se confunden con ejecuciones de la cohorte.

El diseño de secuencia revisado conserva el primerT prefijado como candidato
primario9fases, sin presupuesto extra. Todas42generaciones deben cerrar antes de
liberar evaluación reservada y debe existir unT elegible9/9. Estas compuertas
todavía requieren implementación/revisión conjunta. Cero autores, cero entregas
nativas nuevas9/9, cero resultados de comparación y registro aún no aprobado.
