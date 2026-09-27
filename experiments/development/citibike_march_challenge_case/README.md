# Citi Bike marzo: derivación adversarial de desarrollo

[`organon.json`](organon.json) conserva el prefijo de 24 eventos del [caso histórico](../../../cases/citibike_march2024/organon.json) y añade once eventos de la sonda D-084. [`manifest.json`](manifest.json) fija hashes de la fuente, la semilla y esta derivación; el [recibo](../citibike_march_challenge_2026-09-27.json) describe la secuencia y los bloqueos observados. La afirmación de usar 1.812.548 filas brutas como denominador fue **inyectada deliberadamente**; no es un resultado de la fuente.

Se puede reproducir la lógica con:

```sh
uv run python scripts/probe_citibike_march_challenge.py
uv run --locked --extra dev python -m pytest -q tests/test_probe_citibike_march_challenge.py
```

Una ejecución nueva genera marcas de tiempo y hashes propios. Los nombres de actor son etiquetas del script, no personas autenticadas. Este ledger no es un caso reservado ni contiene una aprobación normativa, una intervención o un efecto de campo. Criterio 5: **no demostrado**.
