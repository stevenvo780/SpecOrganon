# Estado de reanudación

**Corte:** 2026-09-26 UTC. Objetivo íntegro en [GOAL.md](../GOAL.md), SHA-256 inicial `e8341bea380cc357ad9e02ec4689a4ed47fe198ba06e4c98639f29264c314c36`. Rama `work/toolkit-foundation`; no se alteró GOAL.md. El [veredicto por criterio](validacion_actual.md) conserva los requisitos todavía no demostrados.

## Implementado y verificado

- La [metodología](metodologia.md) define filosofía, investigación empírica, comparación y SDD, validación, entradas, salidas, revisión, parada y retorno para nueve fases. `src/specorganon` implementa ledger versionado, invalidación de dependencias, contradicciones, compuertas, runner reanudable, CLI y MCP 2.2 stdio. La aprobación `human:<nombre>` queda etiquetada como autodeclaración y los casos reales no contienen aprobaciones normativas.
- Los [antecedentes](antecedentes.md), [tres prototipos](../prototypes/) y [comparación de 33 escenarios mecánicos](alternativas.md) sustentan provisionalmente un grafo; conservan el fallo del flujo secuencial y el coste de reparación mayor del grafo. No hay ensayo controlado entre modelos o métodos completos.
- `uv run pytest -q` pasó **26 tests**. Incluye cliente MCP real con descubrimiento e invocación de las 13 herramientas, invalidación/revisión, runner entre procesos, escritura atómica y un `SIGKILL` durante el manifiesto seguido de reanudación sin duplicados. Los tests usan entradas sintéticas para la mecánica.
- `uv build --wheel` produjo `specorganon-0.1.0-py3-none-any.whl`. Instalado fuera del repo en dos entornos limpios, Python 3.11.15 y 3.12.3, `scripts/clean_smoke.py` terminó con nueve fases aceptadas, 29 ítems, 49 eventos, once decisiones de fixture, los 13 comandos CLI, cliente MCP real, entrada inválida sin mutación y replay idempotente en ambos. `tests/test_interfaces.py` pasó 3/3 en cada instalación y ejerció las 13 herramientas MCP. Ninguna decisión etiquetada `human:fixture` representa aprobación humana real.
- La [prueba multiagente](prueba_multiagente.md) usó un agente nativo para escribir 29 ítems con el runner y otro para revisar y avanzar las nueve fases. Dos agentes adicionales escribieron ítems disjuntos en un ledger común sin pérdida, aunque sus eventos quedaron serializados por escritor y no demuestran solapamiento temporal.
- El [expediente documental de mango](caso_alimentos_investigacion.md) conserva datos publicados de 2016, rutas separadas y una inconsistencia aritmética de FAO. Su ledger contiene una revisión independiente de `frame` vigente; `critique` requiere decisión humana.
- El [expediente documental de Citi Bike](caso_citibike_ejecucion.md) reutiliza el mismo núcleo con 30 ítems. La revisión de `s_proxy` hizo obsoletos 12 descendientes, incluyendo decisión y requisito candidatos. Un segundo agente revisó y avanzó `frame`; `critique` espera aprobación humana. El paquete de junio de 2026 quedó expuesto y se trata como desarrollo, no reserva confirmatoria.
- La auditoría adversarial encontró ocho fallos de integridad/runner; se corrigieron con regresiones: rechazo tardío, resolución antigua, éxito de campo sin estructura, indicador sin evidencia, resolución modificada, métrica divergente, autoevaluación final y reparación bloqueada. Los tests no demuestran que no existan otros fallos.

## Pendiente para GOAL.md

La [matriz prospectiva](protocolo_experimental.md) aún requiere concurrencia temporal demostrada entre agentes de modelo y autenticación/procedencia externa; banco sellado de 21 inyecciones; observación hasta consumo, valor aprobado y ensayo de campo alimentario; comparación N/SDD/toolkit por modelos, esfuerzos y configuraciones con réplicas/ablaciones; y un nuevo caso reservado de movilidad y otras transferencias completas. Ninguna de esas evidencias se sustituye por las fixtures o por las dos revisiones de `frame`.

El protocolo propone hasta 540 ejecuciones, 48 millones de tokens y presupuestos humanos y monetarios; **no están autorizados**. Antes de lanzar la matriz o un piloto se necesitan sitio, actores competentes, aprobación de valores y umbrales, acceso/telemetría de modelos, evaluación independiente, reserva sellada y aprobación de recursos. Si alguna capacidad no se consigue, el criterio afectado permanece `no demostrado`.

## Reanudar

1. Leer [GOAL.md](../GOAL.md), [validacion_actual.md](validacion_actual.md), [plan.md](plan.md) y [protocolo_experimental.md](protocolo_experimental.md).
2. Verificar rama, `git status`, `uv run pytest -q`, `uv build --wheel` y el smoke en un entorno nuevo antes de concluir sobre funcionamiento técnico.
3. Mantener separados datos publicados, ficción de tests y observaciones de campo. No usar Citi Bike junio de 2026 como reserva ciega ni cambiar umbrales por resultados favorables.
