# Pan comercial en Noruega · expediente de selección

Este expediente selecciona **una sola cadena real**: un pan comercial de 736 g, entre los más vendidos en Noruega, estudiado con datos de su molino, panadería y distribución. La unidad funcional del [estudio primario](https://doi.org/10.3390/su11010043) es 1 kg de pan producido, distribuido y consumido en Noruega. La marca y los lotes no se publican. La [auditoría de fuentes](source_audit.md) distingue lo observado de lo estimado en cada etapa.

La cadena sirve como **caso de desarrollo para formular y auditar el problema**, porque el estudio incluye insumos agrícolas, almacenamiento, transporte, molienda, panificación, venta, consumo y salidas como salvado y pan desviado a pienso. Es un modelo de ciclo de vida construido con fuentes de distinto alcance, no un seguimiento de los mismos lotes desde las fincas hasta los hogares. No se han descargado ni redistribuido datos empresariales o bases comerciales.

Las tablas públicas permiten reconstruir parte del inventario físico y contrastar supuestos. No permiten reproducir exactamente el cálculo ambiental, observar el consumo de ese pan en hogares ni medir el efecto de una intervención. Las alternativas de reducción de residuos del artículo son escenarios calculados; las pruebas de envases miden frescura, no una disminución atribuible de desperdicio en la cadena. El criterio 3, «Resolución efectiva», de [GOAL.md](../../GOAL.md) queda **no demostrado**: faltan línea base, comparador y resultados de campo para una intervención definida con métricas y umbrales previos.

Para pasar de selección a evaluación se necesitarían registros enlazables de producción, almacenamiento, transporte, transformación, venta y consumo, permisos de uso y un diseño prospectivo con comparador. Las variables, solicitudes y decisiones pendientes están en la [auditoría](source_audit.md). Este expediente no autoriza contactar a participantes ni implantar una intervención.

## Encuadre ejecutado en el toolkit

El [manifiesto fijado](frame_manifest.json) registra nueve datos de los PDF archivados y diez ítems de formulación. `organon run` escribió los 19 ítems en un caso con política de aprobación `signed` y se detuvo antes del avance de `frame`. Un revisor distinto de su autor registró `accept` para el **encuadre documental**; al reanudar el mismo manifiesto, `frame` avanzó y `critique` se detuvo porque `n_bread_harm` carece de aprobación humana verificada. El nombre del revisor es una etiqueta del ledger, no una identidad autenticada.

La [sonda reproducible](../../scripts/verify_bread_frame.py) coteja los SHA-256 de los PDF con el manifiesto y compara CLI con un cliente MCP real en `status`, `gate`, `trace`, `next_task` y replay. Comprueba además que un manifiesto inválido no cambia el ledger. Su [recibo](../../experiments/development/bread_frame_cli_mcp_2026-09-27.json) conserva hashes, revisión, recuentos y el bloqueo pendiente. Para repetir la verificación local:

```sh
uv run python scripts/verify_bread_frame.py
```

La revisión de `frame` no aprueba los valores propuestos ni convierte porcentajes históricos en una línea base de campo. Las fases posteriores, el ensayo y el criterio 3 siguen pendientes.

## Análisis secundario de la encuesta

La [transcripción de la tabla 1](survey_table1.json) fija la fuente archivada y sus siete frecuencias. El [analizador reproducible](../../scripts/analyze_bread_survey.py) comprueba el hash del PDF y recalcula el [recibo](../../experiments/development/bread_survey_bounds_2026-09-27.json): 97 de 1.000 respuestas declaran al menos siete rebanadas desechadas por semana; si las 33 respuestas «no sabe» pertenecieran a ese grupo, serían 130. El intervalo descriptivo es 9,7–13,0 % de las respuestas. La cota inferior de las categorías declaradas suma 1.720 rebanadas semanales en esos hogares; no hay cota superior finita porque «más de 12» es una categoría abierta. Estas cifras son estimaciones autodeclaradas sobre pan fresco en general, sin identificación del pan del ACV, incertidumbre muestral calculada ni efecto de intervención. Tampoco habilitan el avance de `critique`.

```sh
uv run python scripts/analyze_bread_survey.py
uv run pytest -q tests/test_analyze_bread_survey.py
```
