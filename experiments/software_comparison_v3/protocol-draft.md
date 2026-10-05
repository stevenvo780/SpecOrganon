# Comparación prospectiva nueva v3: candidato, no registrado

Identidad software-comparison-v3, anterior a contratos definitivos/registro/autores.
No reabre la campaña02 ni reutiliza sus RoutePlan/TreeMap/LogLens/IntervalDesk,
CSVShape, LotLedger o inputs del piloto backup. Sus resultados adversos permanecen.
No se inicia por un éxito LotLedger; estas tres tareas se seleccionan ahora por
tipos de trabajo, antes de observar outputs de sus autores, sin pilotarlas.

## Pregunta, tareas y validez

Comparar trabajo libre N, guía SDD S, paquete SpecOrganon T y ablación A al entregar
software pequeño, midiendo contrato, documentación, adherencia, recursos y fallos.
Las diferencias reflejan el paquete (secuencia, herramienta, revisiones/compuertas),
no un efecto puro de la filosofía. No inferir ventaja universal, impacto de campo
o eficacia en personas. No adaptar dificultad/recetas después de generar.

Tres familias propuestas, un contrato por familia para todos los métodos/modelos:

| Tarea nueva | Tipo | Núcleo que deberá fijarse antes del registro |
|---|---|---|
| FractionMix | aritmética exacta | Sumar racionales con numeradores/denominadores enteros; resultado canónico reducido, límites y errores exactos |
| PolicyPick | reglas de decisión | Elegir regla coincidente por prioridad y desempate, tags/strings exactos, reglas sin match y forma JSON |
| ListPatch | edición de secuencias | Aplicar insert/replace/delete en índices del estado vigente; resultado atómico y errores por índice/tipo |

La tabla selecciona ámbitos, no contratos completos ni oráculos. Contratos exactos,
2ejemplos públicos y60recetas por tarea se fijarán y revisarán antes de la primera
celda. Si un contrato no supera revisión de diseño, no generar ni cambiar su nombre
para ocultar fracaso. No cambiar la selección a partir de resultados LotLedger.
Sesenta recetas = cobertura determinista finita, sin garantía de equivalencia de
dificultad. Normalizar proporciones dentro de tarea y dar igual peso a cada tarea.
Las recetas no son repeticiones independientes ni unidades de inferencia estadística.

## Diseño fijo propuesto y repeticiones

3tareas ×2familias ×2repeticiones ×3métodos N/S/T =36celdas principales.
Familias autoras: Codex gpt-6.1-sol medium (volumen ORIGINAL specorganon-lab_codex-home)
y Gemini3.8Flash (Medium) (perfil ORIGINAL /home/stev/.gemini). Revisor la otra familia,
con modelos/esfuerzos fijos; sin cuentas adicionales, mezcla de perfiles o sustituciones.
No afirmar que una licencia se duplica por usar otro contenedor/máquina.

Las dos repeticiones son sesiones/outputs nuevos sin compartir entregas ni feedback
entre celdas, para describir variabilidad. No se fijan seeds de modelos cuando el
proveedor no lo permite; el orden se congela con seed731 para el programador, no
para inferencia del modelo. Cada bloque tarea/familia/repetición contiene N/S/T.
Orden balanceado por las seis permutaciones de N/S/T, cada una dos veces entre los
12bloques; la asignación a bloques se fija antes de generar. Autor/revisor pueden
compartir familia con otras celdas, sin usar historia/sesiones entre celdas.

6celdas A, una por tarea/familia en repetición1. Total42. A conserva guía de9fases,
puts/versions/trazas, tests aislados y auditoría final; retira conjuntamente revisión
intermedia y bloqueo por aceptación. Su ledger conserva borradores, sin inventar
review/advance/accepted. Un plan externo secuencia fases candidatas para A y se
audita al final. Comparar T-A identifica el paquete revisión+compuerta, no cada
componente, y tiene6pares descriptivos, sin potencia para generalizar.

## Tratamientos concretos, artefactos y techos comunes

N recibe contrato, formato de entrega y criterios comunes; elige su proceso.
S recibe además guía fija especificación→diseño→tareas→construcción→verificación:
requisitos/criterios antes de medir, alternativas/decisiones, tareas trazables y
tests/README. La guía íntegra se congelará; no representa todas las prácticas SDD.
T usa engine/controller schema9 (candidato prospectivo separado), guía9fases y revisiones/mandatos separados.
A usa la misma guía/código de registro de borradores de T sin revisión/gate intermedio.
No fabricar aceptación en A para satisfacer un checklist exclusivo de T.

Todos: techo40llamadas nativas incluyendo revisión/auditoría finales,180s/llamada,
6000s desde primera admisión,128000bytes renderizados/llamada,3145728 acumulados,
2MiB/stream, archivos<=20000bytes JSON escapados. Hasta2tests propios120s, segunda
tras cambio ejecutable/argv provocado por fallo/rechazo. Entrega/tests readonly,
sin red/credenciales,2CPU/1GiB/128pids. Para T y A,6artefactos/6000bytes JSON por
fase; para N y S, mismo límite por paquete de cambios para no darles mayor entrega.
Secuencias específicas de N/S/A deben implementarse y comprobarse antes del freeze;
el mismo techo no exige idéntico uso y no equipara bytes con tokens.

N/S/A pueden usar hasta2author slots por etapa propia,3build, y revisiones sólo
finales; T consume revisiones/conformidades intermedias dentro de esos40. La
asignación concreta y el número de etapas se congelan en sus harnesses antes de
generar. Ninguna llamada o feedback del revisor queda fuera del coste del tratamiento.
Documentar esperas/paradas/tiempo sin equiparar suscripciones con precio marginal.

Límite de campaña42celdas,1680llamadas,132120576bytes de entrada,252000s sumados
de relojes de celda. Es una cota máxima, no uso previsto ni capacidad garantizada;
la campaña tendrá deadline monotónico global de252000s desde primera admisión.
No contratar ni cambiar cuentas para completarla. Cuotas/catálogo actuales antes
de workflow paralelo y cuota<=600s antes de cada nueva admisión. Codex sin sondeo
observable queda unknown; cuota agotada/vencida pausa sin renovar ningún reloj.
Tras fallos nativos de causa account/quota desconocida detener esa ruta y conservar
la celda, sin fallback. Reconciliar el mismo handle cuando siga vivo/incierto.

## Custodia, puntuación y análisis anteriores a los autores

Autor, revisor y evaluador en procesos/directorios/containers separados. El revisor
final ve contrato/entrega/recibos públicos; ninguna fase recibe recetas/resultados
reservados. Una auditoría final nativa y una evaluación reservada después del cierre,
sin reparaciones posteriores. El evaluador conductual recibe ID opaco y entrega,
sin método/ledger/modelo. El auditor de adherencia ve artefactos/historia y no se
llama ciego. La matriz y mapping IDs se custodian fuera del snapshot de sujetos.

Métricas separadas, sin un total que compense ausencia de método por código:
F=recetas pasadas/60 y conformidad completa60/60; D=checklist8/8 específico del
contrato; G=requisitos comunes de grounding/criterios previos/trazas/pruebas/alcance,
checklist6; H=adherencia específica a guía (N no tiene guía impuesta, no tratarlo
como fallo por omitir9fases). Para T, H exige9fases vigentes con revisión independiente;
para A exige9fases candidatas sustantivas/trazas/recibos y no exige los mecanismos
retirados; para S exige sus5etapas/trazas. Las rúbricas completas se congelan.
Veredicto full_package por celda exige F,D,G,H aplicables; publicar código que
pase con método incompleto como tal. Revisión de forma no sustituye sustancia.

Faltantes: programa ausente/contrato incorrecto =0/60; evidencia/doc/guía ausentes
=0en punto aplicable. Infraestructura desconocida se conserva inconclusa y se
presenta rango descriptivo mínimo-máximo posible, sin imputarla como pass.
No iniciada se distingue de fallida, manteniendo denominador de diseño42;
una campaña incompleta no satisface el cierre de la goal. No eliminar fallos,
seleccionar mejor repetición ni reiniciar con nuevo seed/tarea para ganar.

Mostrar cada celda y los12bloques pareados N/S/T; diferencias T-N y T-S dentro
de bloque, media/mediana/rango sobre esos12 y estratos tarea/familia.6pares T-A.
No contar60recetas como60réplicas. Con2repeticiones/estrato no se hacen afirmaciones
confirmatorias de significancia ni eficacia general; registrar incertidumbre de
variabilidad/selección/corpus/modelo y límites de extrapolación. Uso nativo exacto
cuando esté declarado, otherwise null; nunca tokens inferidos de bytes ni coste
monetario fabricado. Reportar intervenciones reales del coordinador por celda.

## Requisitos de registro y publicación

Antes de iniciar42celdas: contratos y ejemplos definitivos, recetas/oráculos,
harnesses N/S/T/A, rúbricas, análisis, orden completo/opaque mapping, imágenes,
fuentes y revisión aceptada con hashes; controles sintéticos de aislamiento,
sentinelas/timeout/ausencia/idempotencia y presupuestos. No medir outputs nativos
de las tareas como calibración. Los controles son ajenos a estas celdas.
Esta versión sigue candidata; no afirmar campaña abierta ni revisión aceptada.

Publicar las42filas y veredictos aun adversos, muestras públicas/contratos/rúbricas/
código/recibos no sensibles, uso desconocido y fallos históricos conservados.
La goal requiere la entrega NUEVA9fases, campaña completa y release final limpia/
publicada. Una comparación adversa completa puede cumplir su requisito; una
campaña detenida, hashes o sólo una CLI verde no lo cumplen.

## Revisión de diseño y contabilidad prospectiva

Los tres contratos candidatos en public/ concretan los ámbitos seleccionados;
revisión nativa Gemini3.8Flash01 exige clarificar conversión decimal grande,
duplicados de requires/tags y delete. La revisión no ejecutó pruebas ni aceptó
registro/harnesses/recetas. No se han admitido celdas. El nuevo controlador candidato
schema9 explica el coste completo almacenado y muestra mediciones del snapshot.
Conserva6 items/6000bytes por fase,40llamadas/20000bytes de archivos; no es una
migración ni una reapertura del LotLedger cerrado. La guía compacta debe superar
los controles de contexto máximo sin aumentar110000bytes de request/128000render.

La revisión conjunta definitiva debe verificar también el orden de hitos de la
goal: entrega nueva real de9fases antes de la evaluación comparativa. Este borrador
no autoriza un caso de sustitución para perseguir victoria ni iniciar42generaciones
antes de resolver ese orden. Los contratos/oráculos pueden prepararse sin autores.
