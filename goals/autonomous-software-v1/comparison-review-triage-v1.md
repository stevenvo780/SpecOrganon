# Revisión del borrador comparativo, antes de prerregistrar

Se conserva íntegra la respuesta real de MiniMax M3, job
`0b1cae72b929493c9adb9be7f756ea2e`, OpenCode en Kratos, access=text,
122 segundos. Su `accept_draft` está condicionado a correcciones: no es
aprobación del protocolo ejecutable ni del resultado de una campaña. No leyó
el harness, no ejecutó pruebas y no recibió contratos o soluciones reservadas.

## Hallazgos que requieren acción

Antes de congelar se deben fijar presupuesto total y orden, medir factibilidad
del contexto/tiempo con fixtures ajenas al estudio, asignar explícitamente toda
revisión al presupuesto de su celda y aislar sesiones sin memoria entre celdas.
El evaluador de comportamiento debe recibir entrega e ID opaco, mientras el
de adherencia debe declarar que puede inferir el método. Hay que anclar todos
los contratos/guías/toolkit/imágenes/fixtures a hashes, fijar recursos de los
tests reservados y reglas por celda para fallo, ausencia y no inicio, y publicar
las revisiones intermedias y los recibos completos que no contengan secretos.

La ablación de cuatro celdas será exploratoria, con una repetición por bloque
tarea/familia: no permite estimar variabilidad propia ni atribuir efectos
causales fuertes. Sigue formando parte de la evaluación y publicación exigida
por la goal; no se elimina de su cierre. Sólo separa conjuntamente revisión
intermedia y compuerta, no cada mecanismo individual.

La cuota no convierte porcentajes en tokens o en un número fiable de celdas.
Se registrará un techo de consumo observable y una regla fija de pausa por
negativa de cuota, sin reordenar según calidad, comprar servicios, usar resets
o cambiar cuentas. La propuesta de 28 aún no está congelada y puede revisarse
antes de generar si su viabilidad no se demuestra. No se podrá reducir después
para borrar celdas pendientes o adversas. Un estudio sin las familias/tipos/
repeticiones exigidos permanece incompleto.

## Afirmaciones del revisor que no se aceptan como hechos

El revisor afirma que gpt-6.1-sol no corresponde a rutas actuales y que sólo
están disponibles variantes gpt-5.6. Es incorrecto para este checkout: el
catálogo actual contiene `codex/gpt-6.1-sol` → `gpt-6.1-sol` y la ingeniería
ejecutó esa ruta en Docker. El catálogo actual y los recibos reales de las
llamadas se conservan; no se cambiará de modelo por esa afirmación sin fuente.
Gemini está vinculado por el adaptador y los eventos nativos a
`gemini-3.1-pro-high`, aunque el alias del puente sea `gemini/pro`.

La participación de MiniMax en el piloto histórico es una conjetura del
revisor, no un hecho: el manifiesto congelado del piloto declara
`model=gpt-6.1-sol`, effort=high. La razón propuesta para usar Codex/Gemini es
que son las dos rutas ya integradas y probadas en el controlador aislado;
MiniMax requiere otro adaptador y verificación. No se excluye por puntuaciones
previas. Su cuota actual tampoco acredita esa integración.

Exigir un autor del contrato distinto del autor del evaluador o una firma de
no-recepción no demuestra por sí solo independencia. La condición operativa
es separar físicamente generadores de soluciones, revisores y evaluación
reservada, verificar los montajes/inputs y auditar el oráculo. Debe incorporarse
una revisión distinta del evaluador y conservar evidencia real; no se inventará
custodia firmada o identidad autenticada para este modo local.

Tampoco se adoptará la propuesta de impedir el cierre ante todo resultado de
celda fallido: la goal permite un veredicto comparativo adverso. Se distinguirán
**campaña evaluada con fallos terminales** y **campaña no ejecutada o con evidencia
insuficiente**. Fallar una celda no equivale a entregar su programa; ejecutar
28 llamadas tampoco equivale a satisfacer el objetivo técnico completo.

## Estado

Cero celdas comparativas generadas. El borrador v1 permanece íntegro como entrada
de la revisión. El protocolo definitivo necesita contratos, evaluador auditado,
rúbricas, harness y presupuesto ejecutables antes de congelar y despachar.
