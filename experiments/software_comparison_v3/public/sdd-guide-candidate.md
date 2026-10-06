# Guía SDD concreta v3 — candidata anterior a autores

Esta es la variante S del estudio local. No representa todas las prácticas
denominadas SDD. Contrato, presupuesto, ejecución aislada y revisión final
son comunes a los métodos; esta guía añade tres documentos anteriores al código y VERIFY.md posterior a la medición real.
El harness y el protocolo deberán congelar su formato y sus límites antes de
cualquier generación. No se ha iniciado ninguna celda con esta guía.

## 1. Especificación

Antes de construir, redacta `SPEC.md`. Explica el problema concreto y su alcance;
convierte el contrato público en requisitos identificados R1, R2, etc., y
criterios de aceptación observables C1, C2, etc. Cada criterio enlaza requisitos
y describe entrada, resultado y error o límite comprobable. Distingue lo que
promete la herramienta de beneficios de campo que este estudio no mide.

Incluye casos normales, límites y errores. Examina los puntos que podrían
interpretarse mal: framing/UTF8/duplicados/tipos JSON, exactitud y conversión de enteros grandes,
prioridad y desempate Unicode literal, sets de tags y edición atómica en índices
del estado vigente. No cambiar el contrato público ni normalizar strings por inferencia.
Explicita supuestos operativos y restricciones. No inventes usuarios consultados,
datos, mediciones, aprobaciones o pruebas ejecutadas. El contrato público gobierna
la entrega: una interpretación no puede cambiarlo.

## 2. Diseño

En una llamada propia anterior al código, redacta `DESIGN.md`. Describe componentes, flujo de datos,
validación, manejo de errores y estrategia para límites. Enlaza decisiones con
requisitos de SPEC.md. Compara al menos dos estrategias sustantivas, con sus
compromisos de simplicidad, corrección y recursos; elige una y justifica su
adecuación a la herramienta pequeña. No basta cambiar el nombre de un algoritmo.

Describe cómo se comprobarán los riesgos que podrían producir una salida
aparentemente correcta pero contraria al contrato, y qué permanece incierto.
Usa únicamente fuentes y evidencias suministradas o razonamiento explícito;
no atribuyas una ejecución al revisor o al executor antes de recibir un recibo.

## 3. Tareas

En la llamada siguiente anterior al código, redacta `TASKS.md`: lista finita de tareas identificadas,
dependencias, requisitos cubiertos y condición observable de cierre. Incluye
validación de entradas, funcionalidad, errores, tests propios y documentación
de uso. El orden debe permitir comprobar incrementos y producir una entrega
pequeña reproducible. No declares tareas terminadas sólo por enumerarlas.

## 4. Construcción

Produce programa y README siguiendo la especificación y el diseño. Después
añade tests propios pertinentes manteniendo el programa y el README sellados,
según las etapas comunes del harness. Los documentos SDD son artefactos de
proceso conservados por separado; no son sustitutos del programa y sus tests.

El README permite a otro usuario instalar lo necesario y reproducir los dos
ejemplos públicos. Explica entrada/salida, errores, límites y ejecución de tests.
Evita dependencias externas. Los tests deben fallar ante defectos plausibles;
no basta verificar que un archivo existe o repetir una constante del programa.

## 5. Verificación y cierre

El executor común ejecuta los tests en un contenedor aislado y conserva argv,
salidas, código de retorno y timeout. Examina ese resultado frente a los criterios
previos. Si el presupuesto y la regla común permiten una reparación, explica
el defecto y cambia código ejecutable antes de una segunda medición. Conserva
la primera medición, incluso si fue negativa. No marques pasado sin ejecución.

Después de la medición real, redacta VERIFY.md frente a los criterios previos;
no inventes un resultado ni borres fallos. Conserva la especificación original anterior al código. Registra cualquier
corrección posterior como cambio con motivo, alcance y vínculos; no rebajes
retroactivamente un criterio para declarar éxito. La revisión final independiente
examinará contrato, documentos, entrega y evidencias públicas. La evaluación
reservada se realiza después y no habilita nuevas reparaciones.

La rúbrica puntuará por separado comportamiento, README, criterios comunes
y adherencia a esta guía, incluida la precedencia real de los documentos.
Un programa que pase pruebas no demuestra por sí mismo adherencia SDD.

Cada mapa de documentos de una etapa tiene como máximo6elementos y6000bytes
JSON canónico vuelto a codificar como string JSON, incluidos nombres/escapes.
Los archivos de entrega/test usan por separado el techo común20000bytes.
La reparación común sigue a un primer test fallido y exige cambio ejecutable;
se conservan los documentos previos. La revisión final no permite reparación.
Esta guía sigue candidata y todavía no registra ni ejecuta la campaña.
