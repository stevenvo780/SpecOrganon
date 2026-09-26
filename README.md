# SpecOrganon

Metodología operativa y toolkit para formular un problema con sus actores y valores, investigarlo, comparar intervenciones, construir una solución mediante SDD y validar sus efectos. El caso alimentario sirve para probar el método; los artefactos y comandos son reutilizables en otros dominios. [GOAL.md](GOAL.md) fija el objetivo y [metodologia.md](docs/metodologia.md) describe los contratos de las nueve fases.

**Estado:** versión de trabajo. El funcionamiento técnico de las rutas probadas tiene evidencia en tests y en una instalación limpia; el aporte frente a otros métodos y el impacto real de una intervención permanecen sin demostrar. [Estado y veredictos](docs/estado.md).

## Instalar y verificar

Se requiere Python 3.11 o superior y [`uv`](https://docs.astral.sh/uv/). Desde la raíz del repositorio:

```sh
uv sync --locked --extra dev
uv run pytest -q
uv build --wheel
```

Para probar el wheel fuera del árbol de desarrollo, crea un entorno temporal, instala `dist/specorganon-0.1.0-py3-none-any.whl` y ejecuta `scripts/clean_smoke.py` con el Python de ese entorno. El script crea una fixture sintética, descubre e invoca el servidor MCP por stdio, alterna CLI/MCP, recorre las nueve fases, comprueba `organon.json`, rechaza una entrada inválida y verifica una repetición sin duplicados:

```sh
uv venv /tmp/organon-check
uv pip install --python /tmp/organon-check/bin/python dist/specorganon-0.1.0-py3-none-any.whl
/tmp/organon-check/bin/python scripts/clean_smoke.py "$PWD"
```

Las aprobaciones y los resultados de ese script son **inventados para pruebas**. No prueban decisiones humanas reales ni eficacia de una intervención.

## Trabajar en un caso

```sh
uv run organon init ./mi-caso --title "Problema delimitado" --domain ejemplo --actor agente:analista
uv run organon put ./mi-caso p1 --kind problem --text "Problema y afectados por delimitar" --actor agente:analista
uv run organon next-task ./mi-caso
uv run organon gate ./mi-caso frame
uv run organon status ./mi-caso
```

`next-task` indica la fase pendiente, entradas, artefactos, versiones, revisión y bloqueos. `put` enlaza artefactos con `--ref ID` repetible y acepta datos estructurados con `--data '{"clave":"valor"}'`. `trace` muestra antecesores y descendientes. Una norma o decisión necesita aprobación registrada con `approve`; la revisión de fase se registra con `review-phase` y el avance con `advance`. El runner `organon run RUTA --manifest ARCHIVO.json --actor ACTOR` aplica pasos declarados, permite borradores de ramas independientes y detiene el avance ante decisiones o contradicciones; se reanuda con el mismo manifiesto. El esquema, ejemplos y semántica de checkpoint están en [workflow_operativo.md](docs/workflow_operativo.md); todos los comandos y el transporte MCP están en [interfaces.md](docs/interfaces.md).

Para conectar un cliente MCP stdio, usa `uv run organon-mcp` (o el ejecutable instalado). Fija `ORGANON_ROOT` a un directorio existente para limitar los casos accesibles al servidor. Las herramientas publicadas son `init`, `put`, `status`, `review`, `approve`, `challenge`, `resolve_challenge`, `gate`, `review_phase`, `advance`, `trace`, `next_task` y `run`. La CLI y MCP comparten motor, ledger y runner.

## Artefactos y evidencia

- [Antecedentes](docs/antecedentes.md), [tres alternativas y resultados negativos](docs/alternativas.md), [prototipos ejecutables](prototypes/), [decisiones](docs/decisiones.md) y [protocolo prospectivo de comparación](docs/protocolo_experimental.md).
- [Investigación del mango](docs/caso_alimentos_investigacion.md), [caso documental versionado](cases/mango/organon.json) y [seed reproducible](cases/mango/seed.json). Las cifras de FAO provienen de un estudio de 2016; el caso conserva una inconsistencia aritmética publicada como control negativo. No hay medición propia hasta consumo ni piloto de campo.
- [Segundo dominio](docs/segundo_caso_desarrollo.md): disponibilidad de estaciones Citi Bike. Su demostración documental de transferencia se informa por separado de cualquier comparación confirmatoria.
- [Prueba multiagente](docs/prueba_multiagente.md): autor y revisor nativos recorrieron las nueve fases de una fixture; la asignación de dos escritores disjuntos conservó todos los eventos, aunque no evidenció solapamiento temporal.
- [Tests](tests/) de invalidación, contradicciones, gates, cliente MCP real, runner, concurrencia e interrupción por `SIGKILL`; la fixture [synthetic_full.json](workflows/synthetic_full.json) no es evidencia empírica.

El ledger enlaza eventos mediante hashes, escribe de forma atómica y rechaza revisiones concurrentes obsoletas. Los hashes detectan alteración accidental, pero no autentican actores ni fuentes. El prefijo `human:<nombre>` de `approve` es una autodeclaración técnica: una aprobación normativa real requiere un canal humano verificable. El gate puede exigir estructura de medición y umbral previo; la autenticidad, atribución causal y daños reales requieren revisión y datos externos.
