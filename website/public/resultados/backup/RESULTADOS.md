# Resultado del piloto autónomo de backups

**El experimento terminó y produjo un backup utilizable. La tesis general de
SpecOrganon no queda demostrada.** La asignación al paquete SpecOrganon obtuvo
mejores puntuaciones funcionales en esta serie, pero no se observó aplicación
completa del método y hubo incumplimientos documentales en sus doce entregas.

Se entrega la implementación de trabajo libre `V1-r1-N`, etapa dos, sin reparar
ni modificar sus bytes después de compararla. Pasó la comprobación adicional de
entrega en V1/V2/V3 y conserva README, pruebas, ejemplos y procedencia en
[product](/resultados/backup/product/README.html).

## Diseño y evidencia

Se completaron 18 ejecuciones: tres variantes × N/trabajo libre,
S/esta guía SDD y T/paquete SpecOrganon × dos repeticiones. Cada una tuvo dos
etapas: contrato base y cambio común `--max-bytes`. La unidad de comparación
es la ejecución, con seis unidades por brazo; los checks no son réplicas.
Se usaron seis bloques pareados y las seis permutaciones del orden N/S/T.

El contrato, protocolo, evaluador, calendario, imágenes y otros insumos se
congelaron antes de generar: `2026-10-03T22:37:45.556870+00:00`. La primera etapa
empezó a `22:37:45.606484+00:00`. El marcador final declara cierre de 18 ejecuciones
y 36 etapas a `2026-10-04T05:20:07.902811+00:00`. Las 36 evaluaciones reservadas
comenzaron únicamente después de cerrar todas las entregas. No hubo corrección
de una entrega usando sus resultados reservados ni reintentos favorables.

Todos recibieron el contrato y los mismos datos esenciales, modelo configurado
`gpt-6.1-sol`, esfuerzo high y CLI 0.160.0. El límite por etapa fue 600 segundos
de autor/método: N/S autor 600; T autor 480 y revisor del método 120. Cada brazo
tuvo además hasta 120 segundos de revisión funcional neutral en solo lectura,
sin retroalimentación al autor. T incorporó el MCP real y la skill. La comparación
evalúa ese paquete, no aísla un efecto filosófico puro ni representa toda forma
de SDD. No se verificó un snapshot inmutable de pesos ni igualdad de tokens.

La [auditoría](/resultados/backup/analysis/provenance-audit.json) verificó hashes, entradas, imágenes,
comandos, inventarios, recibos, streams y orden temporal: válida, sin incidencias
de consistencia, 84 IDs de sesión distintos y cero streams truncados. Esto es
consistencia local, no identidad ni custodia externa autenticadas. Los controles
de desarrollo incluyen una referencia verificada y controles defectuosos; no se
cuentan como ejecuciones ni como producto ganador. La suite congelada del evaluador
pasó 21 pruebas antes de la campaña.

## Resultados funcionales

| Brazo | Etapa | Media | Mediana | Rango | Comprobaciones perfectas |
| --- | --- | ---: | ---: | --- | ---: |
| N | Inicial | 78,33 % | 100 % | 35–100 % | 4/6 |
| S | Inicial | 78,33 % | 100 % | 35–100 % | 4/6 |
| T | Inicial | 100 % | 100 % | 100–100 % | 6/6 |
| N | Cambio | 54,55 % | 31,82 % | 31,82–100 % | 2/6 |
| S | Cambio | 77,27 % | 100 % | 31,82–100 % | 4/6 |
| T | Cambio | 98,48 % | 100 % | 90,91–100 % | 5/6 |

Las etapas tienen denominadores 20 y 22. No se interpreta la diferencia bruta
entre etapas como adaptación: [report.md](/resultados/backup/analysis/report.html) conserva el cambio
de los veinte checks comunes y las dos pruebas de cuota aparte, además de las
36 puntuaciones, seis diferencias pareadas por comparación y sus rangos.

En etapa dos, la diferencia media T−N fue **43,94 puntos porcentuales**,
mediana 68,18 y rango −9,09 a 68,18. T−S fue **21,21 puntos**, mediana cero y
el mismo rango. La mediana cero frente a S y el caso negativo impiden describir
una ventaja uniforme. Son diferencias descriptivas de este piloto, sin inferencia
poblacional ni prueba de superioridad general.

Dos N perdieron trece checks comunes tras el cambio. `V1-r1-T` mantuvo exactamente
el mismo código de la etapa inicial y falló las dos pruebas de cuota. En las
entregas con 7/20 o 7/22, el rechazo temprano por permisos sobre el ancestro
privado `control` impidió operaciones básicas; varios fallos posteriores son
consecuencias del prerrequisito fallido, no defectos independientes. La referencia
y otras soluciones funcionaron en ese mismo entorno. Este detalle de permisos
limita la extrapolación a otros entornos de ejecución.

No se registraron fallos críticos de corrupción silenciosa o mutación protegida,
ni observaciones inconclusas. Eso no acredita seguridad completa: una entrega
que rechaza la operación básica tampoco puede producir determinados fallos
críticos, y las instancias son finitas. En la segunda etapa pasaron la recuperación
tras SIGKILL 2/6 N, 4/6 S y 6/6 T; se conservaron comando, salida, señal real y
reintento. El producto seleccionado pasó también esas pruebas en las tres variantes.

## Documentación y método

El evaluador funcional congelado no puntuó el README exigido por el contrato.
La inspección posterior registra esa limitación sin modificar sus puntuaciones:
ninguna entrega inicial tenía README; en etapa dos lo tenían 4/6 N, 4/6 S y 0/6 T.
Al combinar puntuación funcional perfecta con README presente, quedan **2/6 N,
4/6 S y 0/6 T**. Este indicador separado no sustituye el score congelado ni prueba
que todos los otros requisitos se cumplan en cada solución.

El [observador de ledgers](/resultados/backup/analysis/method/method-report.json) leyó las doce
entregas T mediante el motor de la imagen congelada, sin red, autenticación o
escrituras. Ninguna registró `test_execution_records` mediante el mecanismo del
método. Esto no equivale a ausencia de pruebas propias: varias las ejecutaron y
guardaron por otras vías. Todas las primeras etapas tenían únicamente `frame`
aceptada. En etapa dos, cuatro ledgers no tenían fases actualmente aceptadas,
uno conservaba `frame` y otro tenía siete fases; ninguno tenía las nueve.
Las revisiones históricas no equivalen a aceptación vigente después de cambios.

Se inspeccionaron los 124 comandos registrados de los doce revisores del método:
lectura de archivos, consultas y cálculo de hashes/metadata, sin escrituras
observadas en código ni items de parche de fuentes. El montaje permitía escritura
para operar el ledger y no hubo captura de código previa a esa revisión; la
evidencia de eventos no sustituye una prohibición física de editar la solución.
La identidad de aprobaciones y revisiones fue local declarada, no autenticada.

El caso raíz del orquestador conserva **1/9 fases aceptadas y bloqueos pendientes**.
Su revisión de frame fue posterior al inicio de generación. Se informa ese
incumplimiento y no se inventan aprobaciones retrospectivas para cerrar el caso.
El protocolo técnico sí estaba congelado antes de medir. Este experimento aporta
una comparación de entregas con el paquete asignado; no demuestra que completar
los cuatro frentes o todas las compuertas cause mejores resultados.

## Entorno, incidencias y costes

Se preservaron 46 timeouts de presupuesto; no se interpretan como rechazo de API.
Las 84 sesiones emitieron el mismo aviso de función experimental
`skip_host_skill_discovery`. Los logs también conservan cierres del host local de
code-mode: dos en el autor `V3-r1-N` etapa uno y uno en el revisor metodológico
`V1-r1-T` etapa uno. Son desviaciones de herramientas y limitan la atribución a
condiciones ideales de disponibilidad. Un parche fallido por líneas no coincidentes
en `V1-r2-S` etapa dos es una edición fallida, no un rechazo de API. No se observaron
rechazos de autenticación/cuota/API; no se cambió cuenta o modelo para ocultar fallos.

Las imágenes del autor necesitaron una excepción local de AppArmor y un perfil
seccomp acotado antes de congelar; mantuvieron el sandbox de Codex, UID1000,
capabilities eliminadas y recursos limitados. Las pruebas fuera de `/trial`
fueron rechazadas. El evaluador no montó autenticación ni socket Docker, usó red
deshabilitada, código en solo lectura y candidato UID1000. Véase el protocolo
para los permisos del controlador. T disponía del toolkit adicional; las llamadas
MCP son dosis observadas, no prueba de cumplimiento semántico.

La mediana de autoría N fue 600,12 s inicialmente y 488,85 s después del cambio;
S 600,12 s en ambas etapas aproximadamente. T agotó 480,12 s de autoría y 120,12 s
de revisión del método en ambas. Las revisiones funcionales medianas fueron
89,59/85,21 s N, 86,70/96,73 s S y 92,01/86,82 s T. Rangos y tokens por función y
etapa constan en [results.json](/resultados/backup/analysis/results.json). La inicialización nativa de
los seis casos T sumó 1,983 s y se contabiliza aparte.

**46 de 84 sesiones no informaron uso de tokens.** No se imputan ceros, no se
suma la caché otra vez al input ni se infiere ahorro monetario. Las cuotas fueron
compartidas y Docker no generó licencias adicionales. Los observadores posteriores
y la verificación de entrega tienen recibos propios y no se suman al presupuesto
experimental de autor/método.

Los [resultados secundarios](/resultados/backup/analysis/secondary-outcomes.json) incluyen espacio
y tiempos con denominadores visibles, condicionados a roundtrip exitoso. En etapa
dos, medianas de espacio fueron 4672 bytes N (n=2), 3458,5 S (n=4), 4096,5 T (n=6).
Los tiempos de create/restore rondan 31 ms y están dominados por lanzamiento y
resolución del observador en cargas pequeñas. Mezclan variantes y subconjuntos de
éxito; no permiten afirmar una ventaja de velocidad o espacio entre brazos.

## Comprobación limpia y producto

El evaluador primario usaba el Python del entorno virtual del toolkit, con site
habilitado. Tras advertirlo y antes de inspeccionar resultados se registró un
addendum exploratorio para **las 36 entregas**, no solo la ganadora: Python
genérico con `-E -s -S -B`, sin paquetes del entorno. Las 36 se evaluaron y todos
los resultados individuales de checks, puntuaciones, críticos e inconclusos
coincidieron con los originales. No se reescribió la medición primaria.

El inventario de las 36 fuentes principales encuentra únicamente imports de
biblioteca estándar y ninguna llamada externa/dinámica de las categorías
inventariadas. Esa inspección AST no prueba todas las propiedades semánticas ni
la ausencia general de código incorporado. La fuente **seleccionada sí se leyó
completa**: autónoma, sin módulos locales requeridos, paquetes instalados,
comandos externos o código dinámico de ejecución; ámbito Linux/Unix.

La selección predefinida entre scores perfectos sin crítico/inconcluso desempata
por tiempo de autor+método y orden del calendario. `V1-r1-N` necesitó 331,85 s de
autoría en etapa dos. La fuente conserva SHA-256
`eaac5ef5622e77d5584474318baba62f906ff1030d6cdcad8fcf7275886e6e0a`.
Pasó 22/22 en V1/V2/V3, 32 pruebas propias y su ejemplo en contenedores aislados.
Esta verificación de ingeniería reutiliza familias/semillas conocidas después
de seleccionar; no se presenta como nuevo holdout confirmatorio.

## Veredicto y siguiente etapa

Hay una señal descriptiva favorable al paquete T en **fiabilidad funcional de
estos backups**, y resultados adversos para el cumplimiento documental y la
ejecución completa del método. No hay evidencia suficiente para validar la tesis
fuerte, atribuir la señal a un mecanismo particular, generalizar a otras familias
o declarar eficacia de campo. La entrega individual elegida proviene de N.

La ejecución fue autónoma dentro del mandato y la autenticación ya autorizados:
no requirió intervención humana por corrida, cambio de cuenta ni copia de tokens.
La autorización inicial y las licencias existentes forman parte del entorno.
No se declara que la instalación y adquisición de esas cuentas sean autónomas.

Una siguiente etapa confirmatoria requeriría otras familias/dominios, más
repeticiones, un presupuesto que permita completar método y documentación,
captura previa del código antes del revisor metodológico, restricción física de
escritura sobre la solución y criterios de documentación/adherencia registrados
antes de medir. Debe preservar comparadores concretos y seguimiento de errores
de herramientas, versiones y costes. No se ha ejecutado ni declarado cumplida.

`GOAL.md` original permanece intacto y su objetivo de campo/generalización sigue
fuera de este resultado. La suite global original del proyecto no está verde:
el control histórico de `pdftotext` produjo `SourceAuditError` por digest distinto.
Los tests del evaluador y herramientas de este piloto, y la validación del producto,
no se usan para afirmar que toda la plataforma está terminada.

Para uso y reproducción: [producto](/resultados/backup/product/README.html),
[experimento](/resultados/backup/README.html), [auditoría de cierre](/resultados/backup/planning/completion-audit.html).
