# Propuesta de comparación prospectiva: pendiente de revisar y congelar

Este documento es un diseño de ingeniería, no un prerregistro ni una autorización
para generar soluciones. Primero deben quedar fijados contratos, evaluador,
guía SDD, harness, imágenes, orden y presupuesto con sus hashes. LogLens,
IntervalDesk y los 30 inputs del piloto anterior quedan excluidos del estudio.

## Pregunta y alcance

Comparar el paquete operativo de SpecOrganon con trabajo libre y una guía SDD
concreta para entregar dos herramientas pequeñas nuevas. Medir conformidad,
documentación, adherencia y recursos observados. Los resultados no estimarán
impacto de campo, superioridad general ni un efecto puro de la filosofía:
el paquete también cambia secuencia, compuertas y revisión intermedia.

Se proponen dos tipos: un algoritmo sobre un grafo dirigido ponderado
(`RoutePlan`, caminos mínimos con desempate contractual) y una CLI de inventario
de un árbol de archivos (`TreeMap`, lectura acotada, sin seguir enlaces ni
modificar entradas). Son nombres y ámbitos propuestos: el contrato público y
los casos reservados se diseñarán y congelarán antes de cualquier autoría.
No se reinterpretará una tarea después de ver su dificultad o resultados.

## Celdas, familias y repeticiones

Dos tareas × dos familias (Codex gpt-6.1-sol y Gemini 3.1 Pro High, perfiles
primarios originales) × dos repeticiones independientes × tres métodos:
24 celdas principales. Dos repeticiones permiten mostrar variabilidad dentro
de cada celda; no ofrecen potencia para generalizar sobre modelos o proyectos.
Se mostrarán los ocho bloques tarea/familia/repetición y sus diferencias,
medias, rangos, fallos y denominadores, sin selección de mejores corridas.

Cuatro celdas adicionales, una por tarea/familia y en la primera repetición,
aplicarán la ablación propuesta: misma guía de nueve fases, sin revisión
intermedia ni bloqueo por aceptación de cada fase, conservando revisión final
y pruebas aisladas. No se inventarán revisiones aceptadas en su ledger. El
contraste identifica el conjunto revisión/compuerta, no cada componente.
Total propuesto: 28 celdas; el orden balanceado se fijará antes de generar.

## Métodos concretos

- N: contrato público y formato común de entrega; el autor decide el proceso.
- S: contrato y guía fija de especificación → diseño → tareas → construcción
  → verificación. Se exige especificación con requisitos y criterios antes
  de construir, diseño con decisiones/alternativas y tareas trazables. La guía
  se publicará íntegra; no se equiparará con todas las variantes de SDD.
- T: contrato y toolkit/guía de nueve fases vigente, con autorías y revisiones
  independientes, criterios anteriores a medir y recibos reales. Un paquete
  incompleto sigue siendo incompleto aunque el programa pase pruebas.

Todos tendrán revisión final por la otra familia y el mismo techo total de
recursos. Sólo T añade las revisiones intermedias prescritas por su método.
El presupuesto consumido por esas revisiones formará parte del tratamiento
y del coste observado, nunca se excluirá para aparentar igualdad de gasto.

## Separación y medición

Autor, revisor y evaluador usarán snapshots/directorios separados. Ningún
autor/revisor recibirá los tests, fixtures ni resultados reservados durante
generación o reparación. Los tests del autor se ejecutarán en Docker sin
red/perfiles; el evaluador reservado será otro proceso limpio. La revisión
final verá contrato, entrega y pruebas públicas reales; se hará una vez y no
regenerará una entrega después de evaluar el conjunto reservado.

El evaluador de comportamiento recibirá un ID opaco y archivos de entrega;
no recibirá el método o ledger. La evaluación de adherencia necesariamente
verá el proceso y no se llamará ciega. Rúbricas separadas: funcionalidad,
README/uso/errores/límites, adherencia exigida a cada guía y cumplimiento de
un conjunto común de requisitos. Ausencia de un artefacto significa ausencia,
sin imputar cumplimiento por una puntuación alta de código.

## Presupuesto propuesto y detenciones

Por celda: máximo 40 llamadas nativas totales, 180 s por llamada, 6000 s
globales desde la primera admisión, 128000 bytes por entrada, 2 MiB de salida
por stream y 1 MiB acumulado de entradas nativas; hasta dos ejecuciones por
test público, cada una 120 s, 1 GiB/2 CPU/128 pids. Una segunda medición exige
cambio material de código/argv. Es necesario verificar si estos límites
admiten el recorrido completo antes de congelarlos; no se aumentarán durante
las celdas. Reparaciones sólo con feedback público dentro del presupuesto.

Antes de generar se registrarán límite total de campaña, orden exacto, hashes
y regla de cuota. Falta todavía justificar y fijar esos valores con el consumo
de ingeniería y la capacidad actual; esta propuesta no inicia ninguna celda.
No habrá reemplazo de tareas, modelos, cuentas o seeds por fallo. Un error de
cliente o formato tendrá recibo y resultado terminal de su celda; un proceso
incierto se reconciliará sin duplicarlo. Una negativa de cuota detendrá nuevos
envíos a esa cuenta; se distinguirán celdas fallidas, pendientes y no iniciadas.
Un estudio incompleto no cumplirá el criterio de cierre de la goal.

Se conservarán tiempos, llamadas, bytes, ejecuciones, intervenciones y uso
nativo cuando esté disponible. Tokens, dinero o capacidad no observables
seguirán siendo desconocidos. Las cuotas actuales son una lectura previa,
no una garantía de acabar 28 celdas. No se comprarán servicios ni se usarán
resets/créditos/cuentas secundarias para suplir una detención.

## Pendientes para un protocolo ejecutable

Definir contratos y ejemplos públicos; crear y auditar evaluador privado;
fijar rúbricas y regla de agregación de faltantes; implementar las tres rutas
y la ablación sin fabricar aprobaciones; verificar sus presupuestos con
fixtures ajenas al estudio; revisión separada del protocolo y manifiesto
inmutable antes de la primera generación. Publicar también ambos intentos
de ingeniería y todas las celdas adversas, junto a límites del estudio.
