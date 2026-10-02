# Resultado del MVP local

## Veredicto

**Listo para uso técnico local en un workspace de confianza.** El toolkit
ofrece entrada para agentes, nueve fases, CLI/MCP, compuertas, trazabilidad,
revisión técnica declarada, recibos de pruebas reales, reanudación e informe
legible. La sesión nativa aporta razonamiento y ejecución; no necesita una
API adicional.

Los dos proyectos de desarrollo expuestos terminaron con nueve fases
aceptadas después de revisiones reales de otro subagente. No son pruebas
reservadas ni comparaciones confirmatorias. C2–C5 de GOAL siguen sin
demostrar; el corte técnico D107 permanece como evidencia histórica.

## Proyectos y controles

| Verificación | Resultado observado | Evidencia |
| --- | --- | --- |
| Entrada del método, del encargo a su implementación | 9 fases aceptadas; revisión final 58; 28 artefactos. | [Informe](run01/entry/report.md), [medición previa real](run01/entry/completion_measurement.json). |
| Mismo núcleo aplicado al análisis escolar | 9 fases aceptadas; revisión 68; salida idéntica al JSON histórico. | [Informe](run01/school/report.md), [hashes y comparación](run01/school/source_checks.json). |
| Reanudación en procesos CLI nuevos | Nueve continuaciones por proyecto; replay terminal sin eventos nuevos. | [Entry](run01/entry/completed_round02.json), [school](run01/school/completed_round02.json). |
| Cambio de hipótesis en una copia | De 9 a 2 fases aceptadas; requisitos y criterio obsoletos; avance build rechazado; original intacto. | [Control](run01/invalidation_control/result.json). |
| Wheel instalado fuera del árbol | Smoke con 24 herramientas descubiertas; 15 operaciones CLI/MCP, firma sintética, entradas inválidas e interrupción SIGKILL de fixture. | [Control instalado](checks/verification.json). |
| Reporte y replay de los proyectos con ese wheel | Informes CLI/MCP iguales, nueve fases por proyecto, replay sin mutación. | [Paridad instalada](run01/installed_local_parity.json). |

## Revisión y correcciones

Se conservaron dos rondas. La [primera revisión](review_round01.md) rechazó
una mezcla de snapshots del reporte y evidencias escolares mal formuladas.
Se corrigieron mediante un estado único y versiones nuevas de los
artefactos, sin ajustar el criterio previo ni borrar el resultado negativo.
La revisión independiente posterior aceptó las correcciones. Una última
revisión de build/validate comprobó la medición de nueve fases en entry.

El primer resultado de entry fue `no_demostrado`: aún faltaban revisiones y
avances. Tras observar realmente nueve fases en revisión 51, se registró la
medición, se reabrieron correctamente build/validate y se obtuvieron nuevas
revisiones antes del cierre 58. El resultado no se adelantó a su observación.

## Pruebas

Las nuevas suites reúnen 52 controles de política local, interfaces reales
y reporte. La pasada de regresión final cubrió 263 pruebas de esas suites y
de ledger, método, aprobaciones, firmas, archives, runner y transportes.
El revisor ejecutó controles independientes y verificó los bytes escolares.
Ruff, sintaxis y validador de skill pasaron.

Las pruebas de mecánica usan datos etiquetados como pruebas. Los proyectos
conservan observaciones de comandos realmente ejecutados, sin claves o
aprobaciones humanas sintéticas. La firma sintética del smoke instalado se
informa por separado y no representa consentimiento humano.

## Alcance

`local_declared` expresa confianza del operador en su workspace. No
autentica identidades, independencia personal, custodia ni el historial de
una ejecución. El contenido de una fuente requiere revisión. Los comandos
de prueba se ejecutan con las herramientas del agente fuera del motor.

El caso escolar comprueba reproducción técnica de un análisis descriptivo;
no demuestra una reducción causal de residuos. El contraste de entrada
firmada sin registro frente a modo local prueba una capacidad bajo distintas
políticas, sin atribuir una mejora al método frente a N/SDD.

No hubo llamadas a API adicionales, publicación externa ni intervención de
campo. Tokens y coste total de las suscripciones no se midieron; no se
declaran equivalencia de calidad ni ahorro entre modelos.
