# D-110 — admisión antes de la primera solicitud de modelo

Fecha: 2026-10-01 UTC. Base D-109:
`0e31be06615ebfff2c794a31c329f039d7373412`.

## Defecto y alcance

El bridge de desarrollo prepara una sesión inicialmente sin claim y comienza
`count_input/send`. La exclusión del intento solo se adquiere al llamar una
herramienta. Dos copias del mismo intento pueden producir respuestas textuales
con ledgers distintos antes de esa exclusión.

Reutilizar el registro de admisión existente para adquirir el claim antes del
primer conteo/envío y comprobar su identidad antes de solicitudes posteriores.
No crear un segundo registro de autoridad ni convertirlo en custodia externa.
La identidad es calendario/run/attempt y el owner staged ya definido.

## Ownership y límites

- Worker existente: `scripts/run_managed_tool_conversation.py` y
  `tests/test_run_managed_tool_conversation.py`; capturas de pruebas en
  `unit_checks/` de este dossier. Preservar cambios ajenos.
- Root: plan, conservación, documentación y commit por rutas explícitas.
- Revisor existente: revisión independiente de código y regresiones.

No ampliar ahora a pausas/relevos, otro esquema, otro proveedor, un agente real
adicional ni el control completo de la matriz. No tocar el motor de producción,
los recibos D-109, GOAL, protocolo o casos históricos. Proveedor falso para todas
las comprobaciones; ninguna solicitud API facturable o decisión normativa.

## Verificación y parada

Conservar un negativo que reproduce el defecto en los bytes originales antes
de corregirlo. Después verificar que dos copies del mismo intento solo dejan
una llegar al transporte de conteo/envío, incluso si no usa herramientas; que
un claim ajeno o alterado bloquea sin llamadas al proveedor; y que siguen
funcionando la conversación y el puente con herramienta sellada existentes.
El rechazo de la copia perdedora no debe cambiar su presupuesto ni producir
respuestas. Revisar la política de estados y el no reintento al interrumpir.

Pruebas focales del bridge y admisión existentes, Ruff y compilación; ampliar
solo ante una regresión concreta. Parar al cerrar el defecto y la revisión.
El resultado demuestra exclusión cooperativa local, sin autenticar proveedor,
factura o cancelación remota, ni cerrar C4 o ejecutar alguna de las 24 celdas.
