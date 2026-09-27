# Citi Bike: muestra de estados de marzo de 2024

Este expediente aplica el mismo motor del caso alimentario a una muestra publicada de movilidad. Su frontera es el Parquet histórico de la [oficina del contralor de Nueva York](https://github.com/NYCComptroller/citi-bike-gbfs/tree/4c36513cf3842efe9a2940a78974bf45cb13fc0b), entre el 12 y el 23 de marzo de 2024. Es un reanálisis **retrospectivo de desarrollo**: el protocolo del ledger se escribió después de conocer la muestra. No es una reserva ciega ni un prerregistro.

[`seed.json`](seed.json) declara problema, actores, alternativas de encuadre, pregunta, hipótesis, protocolo, indicador, evidencias derivadas, inferencia y límites. [`organon.json`](organon.json) conserva 22 cargas y dos eventos posteriores: revisión por un agente nativo con etiqueta distinta y avance histórico de `frame`. Esa revisión carece de firma; el replay vigente informa `review_provenance=legacy_unverified` y `frame.accepted=false`. La norma `n_scope` tampoco tiene aprobación humana, por lo que `critique` está bloqueada. La etiqueta de un agente no acredita identidad, competencia o independencia real.

La [salida archivada](../../experiments/development/citibike_sample_status_2026-09-27.json) contiene 1.812.548 filas estación-instantánea, 820 capturas irregulares y 3.512 filas excluidas por el control conservador de capacidad. Entre las 1.809.036 filas restantes, 1.725.248 registran alquiler habilitado con bicicleta y 1.682.386 devolución habilitada con anclaje. Son conteos de filas, no estación-minutos, intentos de viaje ni impacto causal. El [registro de ejecución](../../experiments/development/citibike_march_ledger_2026-09-27.json) fija los hashes y las compuertas observadas.

Para reproducir el cálculo se necesita una copia local del Parquet cuyo SHA-256 es `661221e1f6fc01ba6475cee61597e432fc0858689195b6c12255a6c005b52fc4`. La [política de datos de Citi Bike](https://citibikenyc.com/data-sharing-policy) rige su uso; el archivo bruto no se redistribuye aquí.

```sh
uv run --no-project --with 'pyarrow==21.0.0' --with 'tzdata==2026.4' python cases/citibike/analyze_sample_status.py /ruta/local/dataset.parquet
uv run organon status cases/citibike_march2024
uv run organon trace cases/citibike_march2024 e_rental
uv run organon gate cases/citibike_march2024 critique
uv run pytest -q tests/test_citibike_march_transfer.py
```

Un caso nuevo se puede sembrar con `uv run python scripts/seed_case.py cases/citibike_march2024/seed.json /ruta/nueva`. La siembra produce solo los 22 ítems: no reproduce automáticamente la revisión y el avance de `frame`. El [expediente de junio de 2026](../citibike/organon.json) permanece separado e intacto.

El [probe de workflow](../../scripts/verify_citibike_march_workflow.py) construye de forma determinista un manifiesto de 23 pasos desde esa semilla y lo ejecuta en un caso temporal con CLI instalada, cliente MCP stdio real y reintento CLI. Detiene `frame` para una revisión emitida por el mismo script con otra etiqueta de actor, reanuda el avance por MCP, comprueba eventos y trazas y deja `critique` bloqueada por la aprobación humana ausente de `n_scope`. El [registro](../../experiments/development/citibike_march_workflow_replay_2026-09-27.json) contiene hashes, cursores y resultados instalados en Python 3.11.15 y 3.12.3. Ese probe compara el JSON derivado y sus locators con la semilla, pero no vuelve a procesar el Parquet ni evalúa sustantivamente el problema. No modifica los ledgers archivados y el criterio 5 sigue **no demostrado**.

Por separado, el [recálculo desde la fuente publicada](../../experiments/development/citibike_march_source_recalculation_2026-09-27.json) descargó el Parquet del commit fijado a un archivo temporal, cotejó sus 10.853.196 bytes y SHA-256 con la copia local anterior y ejecutó `analyze_sample_status.py` en un entorno nuevo con Python 3.11.15, `pyarrow==21.0.0` y `tzdata==2026.4`. El JSON recalculado fue idéntico byte a byte al archivado; una copia de hash distinto salió con código 2 antes de leer el Parquet. Esto refuerza la reproducibilidad del cálculo histórico, sin observar viajes frustrados ni efectos de una intervención. Los datos brutos permanecen fuera del repositorio.

```sh
uv run python scripts/verify_citibike_march_workflow.py
uv run pytest -q tests/test_citibike_march_workflow.py
```
