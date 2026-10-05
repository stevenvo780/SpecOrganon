# Rúbrica de evaluación v1 — borrador anterior a generación

Esta rúbrica deberá congelarse con el protocolo y el harness. No es un resultado.
La funcionalidad, documentación, requisitos comunes y adherencia se presentan
por separado; no se obtiene un ganador sumando dimensiones distintas.

## Comportamiento reservado

Una invocación puede pasar, fallar o quedar inconclusa por infraestructura.
Cada tarea tiene su propio denominador congelado: RoutePlan 61 invocaciones;
TreeMap 52 invocaciones más un probe independiente de acceso a contenidos/destino
de symlink. El probe no prueba todos los accesos posibles. Se publican los grupos
y el detalle de cada invocación, además del conteo global.

Una entrega sin programa tiene cero pases y estado `sin_entrega`. No se ejecuta
un programa sustituto. Una celda no iniciada conserva `no_iniciada`; una ausencia
de medición por infraestructura conserva `inconclusa`, sin imputar cero ni éxito.
El porcentaje conservador divide pases por todas las invocaciones previstas
para una entrega iniciada, mostrando por separado inconclusas y fallidas. También
se muestra el intervalo descriptivo [pases/n, (pases+inconclusas)/n]. No es un
intervalo estadístico de confianza. Una tarea cumple comportamiento sólo con
todas sus invocaciones y el probe pertinente pasados, sin faltantes.

## README: diez puntos binarios con localizadores

Cada punto requiere evidencia en el archivo y en los comandos cuando procede.
El evaluador documenta sí/no/inconcluso, localizador y motivo. No otorga puntos
por extensión del texto ni por afirmar una prueba inexistente.

1. Instalación reproducible: Python3.12 y biblioteca estándar, sin dependencias omitidas.
2. Comando de inicio compatible con el programa y sus argumentos contractuales.
3. Primer ejemplo público completo: preparación/entrada, invocación y salida esperada.
4. Segundo ejemplo público completo: preparación/entrada, invocación y salida esperada.
5. Descripción de entradas, opciones y valores por defecto de la tarea.
6. Descripción del resultado, claves, tipos y orden/desempate pertinente.
7. Manejo de errores: exit2, objeto invalid_input y separación stdout/stderr.
8. Límites contractuales: capacidad de grafo/entrada o recorrido/paths/conteo, según tarea.
9. Comando reproducible de tests propios que corresponde al recibo público conservado.
10. Alcance local, restricciones y limitaciones; no atribuye beneficios de campo medidos.

Se publica puntuación confirmada /10 junto a faltantes e inconclusos. Los dos
ejemplos documentados se reejecutan después del sellado, en un proceso sin
perfiles/red y sin devolver feedback al autor. Código y README conservan hashes.

## Requisitos comunes: seis puntos separados

1. Programa contractual, tests propios y README están presentes en la entrega sellada.
2. No requiere dependencias externas ni capacidades ajenas al entorno fijado.
3. Tests públicos reales pasan y su recibo se vincula a los bytes actuales.
4. Tests propios examinan defectos plausibles, límites y errores; el juicio cita casos concretos.
5. Las afirmaciones de ejecución, aprobación y alcance corresponden a evidencia conservada.
6. La revisión final independiente recibió el snapshot final y emitió un veredicto válido.

El punto6 registra que ocurrió una revisión; su veredicto accept/reject/inconclusive
se publica por separado. Un rechazo no se convierte en aceptación por tener
los seis puntos. La corrección funcional la mide el conjunto reservado.

## Adherencia: no comparar porcentajes entre guías diferentes

N no prescribe un proceso: adherencia `no_aplica`. Se conserva el proceso
voluntario del autor, sin premiar o penalizar que use una guía por iniciativa
propia. Las etapas comunes sólo sellan programa y tests y miden el resultado.

S tiene ocho comprobaciones: SPEC anterior al código; requisitos identificados;
criterios observables con vínculos; casos normales/límites/errores; DESIGN
anterior al código; alternativas sustantivas con elección justificada; TASKS
anterior al código con dependencias/cierre; interpretación del test público y
cambios explicados sin rebajar criterios retrospectivamente. Especificación,
diseño y tareas permanecen como artefactos originales de proceso.

T tiene nueve comprobaciones, una por fase frame/critique/study/observe/explain/
compare/specify/build/validate. Una fase recibe punto sólo si sus artefactos
vigentes satisfacen el propósito sustantivo, tienen revisión nativa separada
registrada sobre su snapshot y aceptación vigente del motor. Build además exige
tests realmente medidos; validate limita sus inferencias al alcance local.
El criterio de nueva entrega exige nueve fases, trazas válidas, pruebas reales,
documentación y gate del paquete, además del veredicto final conservado.

A evalúa los nueve propósitos en documentos y construcción propuestos, sin
exigir revisión intermedia ni aceptación del motor. Sus ocho documentos son
borradores sin aprobación; build son programa/tests/medición. La ablación
retira conjuntamente revisión, registro y compuertas intermedias. Por tanto,
el contraste T–A no identifica el efecto puro de una sola compuerta.

Todos los juicios de documentación, requisitos y adherencia incluyen evidencia
localizable y no se llaman ciegos. El evaluador funcional sólo recibe ID opaco,
programa y entrada actual. Una misma familia revisora no es una tercera familia;
la separación física de procesos/datos se describe explícitamente.
