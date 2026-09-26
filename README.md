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

Para probar el wheel fuera del árbol de desarrollo, crea un entorno temporal, instala `dist/specorganon-0.1.0-py3-none-any.whl` y ejecuta `scripts/clean_smoke.py` con el Python de ese entorno. El script crea fixtures sintéticas, invoca los 14 comandos CLI y las 14 herramientas de un cliente MCP stdio real, recorre las nueve fases, comprueba `organon.json`, rechaza entradas JSON no finitas y números que se perderían por subdesbordamiento sin mutar el ledger, y verifica una repetición sin duplicados. Interrumpe con `SIGKILL` un runner CLI tras un checkpoint, reanuda el mismo manifiesto por MCP y coteja estado y replay. Libera dos procesos CLI escritores con precondiciones de versión y verifica ambos ítems; la barrera no demuestra una colisión de lecturas. Además ejercita una aprobación Ed25519 **sintética** con clave generada en memoria y comprueba rechazo de firma inválida y bloqueo al retirar el registro de confianza:

```sh
uv venv /tmp/organon-check
uv pip install --python /tmp/organon-check/bin/python dist/specorganon-0.1.0-py3-none-any.whl
/tmp/organon-check/bin/python scripts/clean_smoke.py "$PWD"
```

El smoke también rechaza un decimal largo que perdería valor al serializarse; la [regla numérica de las interfaces](docs/interfaces.md) describe el alcance de esta comprobación.

El script crea explícitamente un caso con `--approval-policy fixture` y habilita `ORGANON_ALLOW_FIXTURES=1` solo para la prueba. Sus aprobaciones y resultados son **inventados para pruebas**. Tampoco la firma sintética representa consentimiento humano. No prueban decisiones humanas reales ni eficacia de una intervención. El entorno de producción debe omitir esa variable.

El smoke compara el resultado observable de las 14 operaciones compartidas CLI/MCP: 13 sobre casos gemelos con entradas iguales y `approval-challenge` sobre el mismo caso firmado. También verifica por separado una firma válida aceptada mediante `approve --signature` y otra mediante MCP. Los tiempos y hashes de eventos de casos distintos no son iguales; cada evento se coteja con su propio ledger y se verifica que su tiempo UTC corresponda a la operación.

## Trabajar en un caso

```sh
uv run organon init ./mi-caso --title "Problema delimitado" --domain ejemplo --actor agente:analista
uv run organon put ./mi-caso p1 --kind problem --text "Problema y afectados por delimitar" --actor agente:analista
uv run organon next-task ./mi-caso
uv run organon gate ./mi-caso frame
uv run organon status ./mi-caso
```

`init` usa `approval_policy="signed"` por defecto y asigna al caso un `case_id` UUID. `next-task` indica la fase pendiente, entradas, artefactos, versiones, revisión y bloqueos. `put` enlaza artefactos con `--ref ID` repetible y acepta datos estructurados con `--data '{"clave":"valor"}'`; la CLI rechaza `NaN`, `Infinity`, desbordamiento a infinito y subdesbordamiento de un número no nulo a cero. En casos compartidos usa `--expected-version` y `--expected-deps` para fijar las versiones que autorizó el autor del contenido. `trace` muestra antecesores y descendientes. Para aprobar una norma o decisión en un caso real, el operador registra previamente UUID, ruta canónica, digest de metadatos y clave pública en el archivo externo `ORGANON_APPROVERS_FILE`; el responsable obtiene `approval-challenge`, verifica el caso y la cabeza del ledger, firma fuera del entorno del agente los bytes indicados por `message_base64` y entrega la firma Ed25519 en base64 a `approve --signature`. La revisión de fase se registra con `review-phase` y el avance con `advance`. El runner `organon run RUTA --manifest ARCHIVO.json --actor ACTOR` aplica pasos declarados, permite borradores de ramas independientes y detiene el avance ante decisiones o contradicciones; se reanuda con el mismo manifiesto. El esquema, ejemplos y semántica de checkpoint están en [workflow_operativo.md](docs/workflow_operativo.md); los 14 comandos, el flujo seguro de aprobación, el anclaje externo opcional del ledger y el transporte MCP están en [interfaces.md](docs/interfaces.md).

Para conectar un cliente MCP stdio, usa `uv run organon-mcp` (o el ejecutable instalado). Fija `ORGANON_ROOT` a un directorio existente para limitar los casos accesibles al servidor. Las 14 herramientas publicadas son `init`, `put`, `status`, `review`, `approval_challenge`, `approve`, `challenge`, `resolve_challenge`, `gate`, `review_phase`, `advance`, `trace`, `next_task` y `run`. La CLI y MCP comparten motor, ledger y runner.

## Artefactos y evidencia

- [Antecedentes](docs/antecedentes.md), [tres alternativas y resultados negativos](docs/alternativas.md), [prototipos ejecutables](prototypes/), [decisiones](docs/decisiones.md) y [protocolo prospectivo de comparación](docs/protocolo_experimental.md). La [preparación ejecutable de la matriz](docs/preparacion_matriz.md) genera calendarios candidatos, verifica archivos, comprueba firmas, audita recibos y juicios declarados, enlaza puntuaciones ciegas con corridas y calcula métricas secundarias e intervalos pareados **sobre declaraciones** sin evaluar el criterio 4. La [preparación de campo](docs/preparacion_campo.md) coteja flujos alimentarios declarados; su esquema 3 opcional acota masa con etapas completas por consumo sin atribuir impacto. El [panel de modelos](docs/panel_modelos_preliminar.md) aún no está congelado.
- [Investigación del mango](docs/caso_alimentos_investigacion.md), [fuentes públicas candidatas y sus vacíos](docs/caso_alimentos_fuentes_candidatas.md), [tres cargas publicadas separadas](cases/mango/fao_table15_loads.json), [caso documental versionado](cases/mango/organon.json) y [seed reproducible](cases/mango/seed.json). Las cifras de FAO provienen de un estudio de 2016; el caso conserva una inconsistencia aritmética publicada como control negativo. No hay medición propia hasta consumo ni piloto de campo.
- [Segundo dominio](docs/segundo_caso_desarrollo.md): disponibilidad de estaciones Citi Bike. Su demostración documental de transferencia se informa por separado de cualquier comparación confirmatoria.
- [Prueba multiagente](docs/prueba_multiagente.md): autor y revisor nativos recorrieron las nueve fases de una fixture. Una ronda de escritores falló por conflicto de revisión; la siguiente, con reintentos, conservó 80 ítems disjuntos y mostró 487 098 218 ns de actividad solapada, sin demostrar ventaja de tiempo, calidad o coste.
- [Tests](tests/) de invalidación, contradicciones, gates, cliente MCP real, runner, concurrencia e interrupción por `SIGKILL`; la fixture [synthetic_full.json](workflows/synthetic_full.json) no es evidencia empírica.

El ledger enlaza eventos mediante hashes, escribe de forma atómica y rechaza revisiones concurrentes obsoletas. La firma demuestra control de la clave pública configurada para `human:<nombre>` y queda ligada al UUID, ruta y metadatos del caso, la cabeza previa del ledger, la versión y el contenido del ítem, el actor y el motivo. La identidad humana, custodia de la clave y competencia para decidir se verifican fuera del toolkit. Una clave ausente o revocada, una ruta distinta o metadatos alterados vuelven la aprobación no verificada al releer el ledger y bloquean las compuertas que la requieren. Los hashes de eventos no garantizan que el ledger sea append-only frente a alguien con escritura directa: puede borrar eventos posteriores a una aprobación válida o añadir falsas revisiones y avances de fase, y recalcular la cadena. El verificador opcional de `ORGANON_LEDGER_ANCHORS_FILE` compara cada lectura con una cabeza externa exacta, pero requiere que un custodio independiente valide y actualice el registro tras **cada** transición legítima; tampoco autentica a revisores. Ninguna clave privada debe entrar en este repositorio, comandos o logs. El gate puede exigir estructura de medición y umbral previo; la autenticidad de fuentes, atribución causal y daños reales requieren revisión y datos externos.
