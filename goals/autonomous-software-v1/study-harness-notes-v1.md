# Harness de celdas: borrador de ingeniería sin generación

Las clases BasicCell y ToolkitCell separan proceso, programa, tests y revisión
final. BasicCell tiene rutas N, S y A. S conserva SPEC anterior a DESIGN/TASKS
y todos ellos anteriores al programa. A conserva ocho borradores no aceptados
y el build común; no escribe un ledger de aceptación ni simula revisiones.
ToolkitCell envuelve el controlador schema6 para T y añade revisión final común.
La CLI bloquea generación hasta implementar admission de campaña y auditar/
congelar el protocolo completo. No se ha ejecutado ToolkitCell como celda real.

CellBudget cuenta bytes de prompts realmente renderizados y llamadas admitidas,
sin devolver presupuesto tras fallos. Pruebas públicas y roles comparten reloj;
dos mediciones como máximo, con cambio ejecutable/argv para la segunda.
Un callback puede revalidar fuentes antes de cada dispatch o lectura cerrada.
Este digest/guard no constituye por sí mismo un prerregistro ni autentica al host.

## Revisión01 y tratamiento de sus hallazgos

Gemini3.1ProHigh job3a717f41f89041d48725a7e22ea0d060 emitió reject, sólo
inspección de texto, sin ejecutar tests. Su rechazo queda conservado.

Los tres primeros hallazgos identifican falta de cierre explícito de celda
ante formato inválido, exceso del contexto de logs o presupuesto agotado.
Ahora se registra terminal_failure con motivo/etapa y sin puntuación inventada.
Una nueva lectura devuelve el mismo fallo, sin otro job. Fallos de escritura
siguen propagándose para recuperar el mismo packet cerrado tras una interrupción.
Los controles verifican conservación del programa sellado, raw logs y contador.

Para logs grandes se conserva el guard común de4000 bytes codificados en vez
de truncar el feedback: cambiarlo sólo en N/S/A rompería la regla del controlador
T ya fijada. El efecto ahora es cierre explícito; la evidencia raw permanece.
El protocolo debe congelar esta regla y contabilizar esos fallos por método.

El cuarto hallazgo afirma que el estado T incluye todos los tests históricos.
No se reprodujo: engine.get_state contiene la versión actual del único test ID
sellado; las mediciones anteriores están en history. El control de reparación
verifica dos recibos [fallo,paso], un solo t1 vigente y su vínculo al árbol final.
El gate del controlador ya exige ese mismo vínculo antes de completar.
No se cambió esa verificación a require_current=false ni se relajó el gate.

## Contexto y límites

El control de máximos con GOAL largo más contratos públicos falló dos veces
por superar110000 bytes de request. La corrida negativa y fuente hash se
conservan. El mandato específico del estudio registra el encargo ya autorizado,
sin nuevas aprobaciones, y ambos contratos caben con ese mandato. Los prompts
máximos observados fueron109140 bytes RoutePlan y110332 TreeMap, bajo128000;
los requests fueron106508 y107700, bajo110000. Son fixtures sintéticas de nueve
grupos de artefactos, archivos y dos streams, no nueve fases de software aceptadas.

Pendientes: admission de orden/cuota/cuenta, acumulado de entradas nativas,
load check de revisión final/rúbrica y conjunto de reparaciones, exportación
del snapshot final, análisis/rúbricas ejecutables y auditoría conjunta. Los
archivos protocol-draft.md y assessment-rubric.md permanecen borradores, con
28 filas previstas y cero celdas generadas. No son resultados empíricos.
