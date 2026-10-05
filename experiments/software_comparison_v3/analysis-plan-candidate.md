# Análisis descriptivo candidato anterior a cualquier autor

Este documento complementa el borrador de protocolo. No registra una campaña,
admite autores ni verifica recibos. analysis.py recibe resultados cuya procedencia
deberá comprobar el harness; rubric.py valida forma de afirmaciones, sin autenticar
un revisor ni demostrar los localizadores citados. Ambos requieren revisión conjunta.

F_total conserva la métrica principal propuesta: recetas pasadas entre el total
propio de la tarea (84/82/84). Conformidad funcional completa exige todas pasadas.
Publicar además éxito en entradas válidas, rechazo de inválidas, ejemplos públicos
y entradas reservadas, cada uno con su denominador explícito. La media secundaria
equilibrada válido/inválido da mitad de peso a cada clase. Esta elección es anterior
a cero autores y no sustituye F_total ni cambia la condición de conformidad completa.

La composición incluye muchas entradas inválidas. Una fixture que siempre emite
el error exacto supera la mitad de recetas y falla todas las entradas válidas; su
puntuación secundaria es0.5 y su conformidad completa es falsa. Es un control
sintético del análisis, no un resultado de modelos ni un baseline ejecutado en
esta campaña. No presentar una proporción F alta como contrato cumplido.

Un resultado inconcluso conserva intervalo descriptivo [éxitos/total,
(éxitos+inconclusos)/total]. Si el requisito global9fases impide evaluación,
no ejecutar sujetos ni inventar fallos: todas las recetas quedan no evaluadas
con rango [0,1]. Si se evalúa, el cierre exige una fila por receta congelada,
incluida infraestructura inconclusa explícita. Un programa ausente constituye
fallo bajo el protocolo cuando la evaluación esté habilitada; distinguirlo de
evaluación retenida o una celda no admitida. No suprimir filas desconocidas.

La unidad de réplica es la celda autor/tarea/familia/repetición, no cada receta.
Mantener los12bloques fijos N/S/T y6pares T/A. Para cada métrica aplicable, mostrar
T-N y T-S sobre todos los12bloques y T-A sobre todos los6, con diferencias en
intervalos [T.inferior-C.superior,T.superior-C.inferior], media, mediana y rango.
Mostrar también estratos por tarea y familia; tres tareas tienen igual peso
por el diseño balanceado. No escoger la mejor repetición ni sólo los pares verdes.
Los extremos son límites descriptivos de datos desconocidos, no intervalos de
confianza ni significancia. Sin p-values ni afirmaciones causales generales.

D8, G6 y H se reportan separados de F. N tiene H no aplicable; S exige5etapas,
T9aceptadas vigentes con revisiones físicas nativas, A9candidatas sin inventar
los mecanismos retirados. full_package exige F,D,G,H aplicables y comprobación
real de evidencia; no sumar puntos para compensar método o contrato ausentes.
Las razones/localizadores de un auditor son afirmaciones hasta su verificación.

Tiempo, llamadas, entrada renderizada acumulada, tests, paradas e intervenciones
del coordinador se reportan por celda. Tokens sólo si hay uso nativo declarado;
coste monetario y campos desconocidos null. No convertir bytes en tokens ni
suscripciones en precio marginal. Publicar todos los estados y el límite de
extrapolación a corpus/modelos seleccionados, sin eficacia de campo o tesis general.
