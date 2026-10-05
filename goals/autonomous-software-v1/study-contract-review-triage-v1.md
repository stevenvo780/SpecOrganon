# Contratos reservados: revisión de borradores

Gemini 3.1 Pro High, job7feccda82b124823a05a8fbb084a01bb, access=text en Kratos,
revisó los dos contratos públicos originales en99.4s. Su accept_draft no es
aprobación del evaluador, del protocolo ejecutable o de una solución. Los inputs
y respuesta completos se conservan en evidence/study-contract-review-01-*.json.

Se adoptan dos aclaraciones: basename para suffix de TreeMap y fallos de parseo
como entrada inválida en RoutePlan. El ejemplo del revisor dir.txt/archivo no
sería un falso positivo con endswith('.txt') sobre el path completo; la aclaración
sigue siendo útil y no cambia los casos válidos. Los límites de parseo nativo
pueden producir ValueError; el contrato exige el error JSON, no un traceback.

El operador añadió antes de congelar una regla léxica precisa para root: no
vacío, componentes '.'/barras normalizados sin resolver symlinks, '..' prohibido
y rechazo del root normalizado si es link, incluso `link/` o `link/.`. Padres de
una ruta explícita pueden resolverse por el OS como ya declaraba el borrador.
Esta regla deberá auditarse junto con el evaluador y protocolo definitivo.

La afirmación del revisor de que3s/2CPU/1GiB es suficiente es una estimación de
factibilidad. No ejecutó tests; todavía deben medirse controles de infraestructura
/oráculo en la imagen pinneada. Tampoco confirma ausencia de todas las ambigüedades.
El comportamiento reservado y la lectura de contenidos de TreeMap requieren una
verificación específica, no sólo comparar números JSON.

Cero soluciones nuevas generadas; ninguno de los dos contratos está prerregistrado.
Todos los cambios y corpus deben congelarse antes de la primera autoría comparativa.
