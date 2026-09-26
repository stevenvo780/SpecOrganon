# Interfaces CLI y MCP

Ambas interfaces llaman las mismas funciones de `specorganon.engine` y `specorganon.runner`. El directorio de un caso contiene `organon.json`, un registro de eventos versionado. Los resultados de la CLI se imprimen como JSON; los errores salen por stderr con código distinto de cero.

## CLI

Tras `uv sync --extra dev`, usa `uv run organon --help` y `uv run organon <comando> --help` para ver todos los argumentos. Ejemplo inicial:

```sh
uv run organon init ./mi-caso --title "Cadena alimentaria" --domain alimentos --actor humano
uv run organon put ./mi-caso problema --kind problem --text "Pérdida de valor por definir" --actor investigador
uv run organon status ./mi-caso
uv run organon trace ./mi-caso problema
```

`put` acepta `--ref ID` repetible y `--data '{"clave":"valor"}'` para campos estructurados. `--data` debe ser un objeto JSON. Los demás comandos son `review`, `approve`, `challenge`, `resolve-challenge`, `gate`, `review-phase`, `advance`, `next-task` y `run`. La compuerta `gate` consulta sin avanzar; `advance` aplica la decisión del motor. `next-task` muestra un encargo acotado con versiones, entradas y bloqueos. `run` lee un manifiesto JSON y se detiene ante aprobaciones o revisiones pendientes:

```sh
uv run organon next-task ./mi-caso --roles '{"reviewer":"agent:revisor"}'
uv run organon run ./mi-caso --manifest workflows/synthetic_full.json --actor agent:ejecutor
```

El manifiesto de ejemplo es una fixture inventada para verificar la mecánica; sus decisiones `human:fixture` en pruebas no son aprobaciones de un caso real.

Las fases son `frame`, `critique`, `study`, `observe`, `explain`, `compare`, `specify`, `build` y `validate`. Los tipos de ítem permitidos y sus requisitos por fase están en `src/specorganon/workflow.py`; un tipo o fase desconocidos son rechazados por el motor.

## MCP por stdio

El ejecutable es `.venv/bin/organon-mcp` (o `uv run organon-mcp`). Configúralo como servidor MCP con transporte `stdio`. Publica las herramientas `init`, `put`, `status`, `review`, `approve`, `challenge`, `resolve_challenge`, `gate`, `review_phase`, `advance`, `trace`, `next_task` y `run`. Los nombres con guion en la CLI usan guion bajo en MCP. Los parámetros tienen los mismos nombres que las funciones del motor; `refs` es una lista de IDs y `data` es un objeto JSON. En MCP, `run` recibe el objeto JSON `manifest` directamente, mientras que la CLI lo lee de `--manifest`.

El servidor solo permite casos dentro de su directorio de trabajo. Para fijar otra raíz, establece `ORGANON_ROOT` con la ruta de un directorio existente al lanzar `organon-mcp`. Las rutas relativas de las herramientas se interpretan desde esa raíz; las absolutas también deben quedar dentro de ella. El servidor resuelve symlinks antes de validar la ruta, por lo que rechaza `..`, rutas absolutas y symlinks que salgan de la raíz. La CLI no aplica este límite, ya que opera directamente sobre las rutas que le entrega el usuario local.

El campo `actor` registra quién declara una acción; no autentica identidad ni convierte por sí solo una decisión normativa en aprobación humana verificable. `approve` exige la forma auto declarada `human:<nombre>` y un motivo, pero la autenticación requiere un proceso externo cuando el caso lo necesite.
