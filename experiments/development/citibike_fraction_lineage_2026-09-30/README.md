# D-105 · Fracciones tipadas y correcciones de linaje

Desarrollo expuesto con el wheel D-102 sin reconstruir el motor. Plan
`a259da2`, constructor `ae7656a`, freeze inicial `d45dcbb`, fallos y reparación
prospectiva `ab316f4`, fuentes corregidas congeladas en `401d402`.

## Resultados y errores conservados

| Intento | Python | Resultado | Puts | Archivos regulares en tar |
|---|---|---|---:|---:|
| installed_311 | 3.11.15 | Failed, exit2 antes de preparar caso | 0 | 7 |
| installed_312 | 3.12.3 | Failed, exit2 antes de preparar caso | 0 | 7 |
| repaired_311 | 3.11.15 | Pass, exit0 | 9 | 113 |
| repaired_312 | 3.12.3 | Pass, exit0 | 9 | 113 |

El error inicial fue del constructor: suponía que los 42 eventos originales
eran `item_put`; son 40 escrituras, una revisión y un avance históricos.
La revisión estática inicial no detectó esa suposición. La corrección admite
únicamente esos eventos de fase por posición/tipo/hash, conserva el prefijo
completo y calcula versiones desde las escrituras. Ningún original fue
reparado, reemplazado o aprobado. `initial_sources/`, dos archivos tar y
`executions/` conservan los intentos fallidos; `repaired_*` y
`executions_repaired/` contienen las dos tentativas adicionales autorizadas
por el plan de reparación, en destinos nuevos. No hubo repetición automática.

Cada positivo conserva 52 eventos, con prefijo42 idéntico: nueve puts
guardados y una revisión técnica negativa de `i_rows` v3. CLI aplica9;
MCP descubre22 herramientas reales y releyó0/9. Cada entorno retiene88
registros: preparación1, CLI32, MCP30 y comparación25. Estas comparaciones
incluyen estado, cinco trazas, nueve compuertas y controles; los objetos SDK
originales no son frames del protocolo de transporte.

Dos pares evidencia/indicador usan métricas literales distintas, unidad
`fraction`, operandos versionados y un archivo local compartido. Los
racionales exactos son431312/452259 y841193/904518, junto a decimales
HALF_EVEN24 con error≤5e-25 y tolerancia1e-24. Ese error sólo describe la
representación, sin fijar incertidumbre empírica o umbral normativo.

Revisar el denominador con contenidos idénticos invalida nueve descendientes
nuevos, conservando vigentes exclusiones/huecos. Alterar o eliminar el archivo
de razones provoca issues y rechazos por CLI/MCP sin añadir eventos; recuperar
los bytes restaura el estado previo. Cuatro negativos contractuales por
entorno son rechazados. El cambio de contrato con pin anterior verifica
binding, sin probar verdad semántica de un contrato alternativo.

## Publicación y revisión

[Caso reproducible](../../../cases/citibike_march2024_fractions/): ocho archivos
copiados byte a byte del positivo3.12, más README. No se copian locks.
[publication.json](publication.json) conserva las correspondencias.
[postrun_review.json](postrun_review.json) atribuye la revisión independiente:
240 miembros de cuatro tar, cadenas52, prefijo42,25pares por entorno,
24módulos y dos entrypoints por instalación, copias y controles verificados.

Ruff y compilación de instrumentos pasan en ambos Python. No nueva suite
global: 2560 pruebas sigue siendo evidencia anterior D-102. En la captura
final de preservación root resolvió inicialmente un path D099 contra la raíz
incorrecta; el error está conservado y el cotejo corregido no cambió originales.
73/76 archivos D104 intactos, tres documentos activos actualizados con bytes
previos verificados en57a0081; 147 originales D099,12marcadores y36pines fijos
siguen idénticos.

## Límites y trabajo pendiente

El rechazo de `i_rows` no lo retira del inventario de `study`; esa fase sigue
bloqueada. `explain` requiere además enlazar `s_rows_pair` con inferencia y
evidencia. No se declara síntesis completa ni aceptación de ninguna fase;
normas y decisión siguen sin aprobación humana verificada. La revisión de
fase histórica es legacy_unverified y permanece íntegra.

D-105 deriva cifras desde JSON ya publicado y conserva flags de fuente/filas
sin autenticar. La reproducción posterior [D-106](../citibike_raw_count_audit_2026-09-30/)
no reescribe sus artefactos ni está adjunta a este ledger. Resolver retiro,
soporte de síntesis y enlace de la repetición son próximos pasos explícitos.
Sin nuevas generaciones experimentales, Q, norma humana, campo o corrida24;
no causalidad, custodia externa o resultado final C2/C5. GOAL, matriz,
umbrales y24módulos de producción intactos. **Aceptación1/5; C2–C5 No demostrados**.

Se intentó un subagente Luna para hashes, pero el lanzamiento falló por
límite de threads y no retornó agent_id. La tarea se hizo con un agente
existente; no se atribuye al modelo solicitado una ejecución inexistente.
