# Banco de inyecciones de desarrollo

El [protocolo experimental](protocolo_experimental.md) prevé **21 inyecciones selladas** y auditoría independiente para el criterio 2 de GOAL.md. Este banco tiene la misma distribución de clases, pero se construyó con los autores del toolkit viendo el código y ajustando las pruebas. Por tanto es **regresión técnica de desarrollo**, no la reserva confirmatoria ni una evaluación independiente. Usa un expediente sintético completo; ninguna cifra representa observación de campo.

## Ejecución

Desde la raíz del repositorio:

```bash
uv sync --extra dev
uv run pytest -q tests/test_injection_bank.py
uv run python tests/test_injection_bank.py --report experiments/development/injection_bank_2026-09-26.json
```

El [reporte JSON](../experiments/development/injection_bank_2026-09-26.json) conserva los 21 resultados, fragmentos de bloqueos, número y hash final de eventos de cada ledger efímero, hallazgos negativos y SHA-256 de los archivos de código probados. Un fallo no se oculta: el generador lo registra y sale con código distinto de cero. `pytest` y el generador invocan los mismos escenarios. La fecha y los hashes finales de eventos pueden variar al repetir porque el ledger registra la hora; el conteo, clasificación y comportamiento esperado deben reproducirse. Si cambia cualquiera de los archivos cuyo hash figura en el reporte, se ejecuta de nuevo el banco antes de usarlo como evidencia del estado actual.

| Clase | Casos | Efecto observado en este banco |
| --- | --- | --- |
| Contradicciones | C01–C06 | Desacuerdo cuantitativo, cálculo inconsistente, disputa explícita de encuadre o supuesto y resolución revisada cierran puertas; una resolución obsoleta reabre el desafío. |
| Evidencia insuficiente | E01–E06 | Fuente, fecha, localizador, método de observación o comparación faltantes bloquean fases; el indicador sin evidencia se bloquea al especificar. |
| Cambios de supuesto | A01–A06 | Seis puntos distintos del grafo pierden vigencia en su rama; un nodo hermano no dependiente permanece vigente, mientras las fases posteriores requieren nueva aceptación. |
| Norma/decisión sin aprobación | N01–N03 | La ausencia de aprobación o revisión de versión bloquea la fase y deja obsoletas decisiones y requisitos dependientes. |

Cada caso verifica estado de ítems (`stale`, `contested`, `issues` o `approved`), el bloqueo o pérdida de aceptación de la fase, rechazo de `advance` **sin añadir evento**, y lectura íntegra de la cadena hash del ledger. Los seis cambios de supuesto verifican **todos** los descendientes del supuesto en la fixture y un nodo no dependiente que permanece vigente. El expediente base marca una prueba como aprobada con texto de fixture; **no ejecuta esa supuesta prueba externa**. Los casos se crean explícitamente con `approval_policy="fixture"`; el banco habilita `ORGANON_ALLOW_FIXTURES=1` solo durante cada escenario y restaura su valor anterior al terminar. `human:fixture` prueba solo la mecánica de versiones, sin atribuir decisión a una persona real. N01 comprueba además que tanto `agent:...` como un `human:` ficticio son rechazados y que, al quitar la variable, el replay deja la aprobación de fixture sin verificar y vuelve a bloquear la puerta, sin mutar el ledger.

## Resultado y límites

En esta ejecución, **21/21 controles de regresión pasaron**. Esto respalda el comportamiento mecánico probado bajo entradas sintéticas, con un hallazgo negativo:

1. **E06:** `study.ready` sigue verdadero cuando un indicador ya no enlaza evidencia; el bloqueo explícito aparece en `specify`. La secuencia final impide aceptarlo como criterio de éxito, pero la puerta temprana no lo detecta.

N01 mostró el bloqueo esperado de un actor ficticio en modo fixture. **No probó una aprobación humana real ni el modo firmado**: ese modo exige una firma Ed25519 y una clave pública confiable configurada por el operador; la custodia de claves y la identidad del firmante requieren comprobación externa.

También quedan sin evaluar la autenticidad de fuentes, si dos registros numéricos pertenecen realmente a la misma población, falsedad sustantiva en texto libre, conflictos no cuantitativos que nadie declare, cobertura de **todos** los requisitos e indicadores de R-F/R-M, y el criterio de campo. La detección cuantitativa automática depende de coincidencia exacta de clave de métrica, alcance y unidad. Una salida verde aquí no cambia el veredicto «no demostrado» del criterio 2 completo de [validación actual](validacion_actual.md).
