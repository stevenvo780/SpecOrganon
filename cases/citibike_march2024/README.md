# Citi Bike: muestra de estados de marzo de 2024

Este expediente aplica el mismo motor del caso alimentario a una muestra publicada de movilidad. Su frontera es el Parquet histórico de la [oficina del contralor de Nueva York](https://github.com/NYCComptroller/citi-bike-gbfs/tree/4c36513cf3842efe9a2940a78974bf45cb13fc0b), entre el 12 y el 23 de marzo de 2024. Es un reanálisis **retrospectivo de desarrollo**: el protocolo del ledger se escribió después de conocer la muestra. No es una reserva ciega ni un prerregistro.

[`seed.json`](seed.json) declara problema, actores, alternativas de encuadre, pregunta, hipótesis, protocolo, indicador, evidencias derivadas, inferencia y límites. [`organon.json`](organon.json) conserva 22 cargas y dos eventos posteriores: revisión independiente por un agente nativo y avance de `frame`. La norma `n_scope` no tiene aprobación humana; por eso `critique` está bloqueada y las fases siguientes no están aceptadas. La revisión de un agente no acredita identidad o autoridad humana.

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
