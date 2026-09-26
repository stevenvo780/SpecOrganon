# Workflow operativo y reanudación

`specorganon.runner` usa las mismas fases y compuertas que `specorganon.engine`. El caso vive en `organon.json`; sus eventos versionados son el checkpoint. Una interrupción no exige restaurar un estado paralelo: vuelve a llamar al runner con el mismo manifiesto.

## Pedir la siguiente tarea

```python
from specorganon.runner import next_task

task = next_task("./mi-caso", roles={
    "analyst": "agent:analista",
    "specialist": "agent:especialista",
    "reviewer": "agent:revisor",
    "human": "human:responsable",
})
```

`next_task(path, roles=None)` es de solo lectura. Identifica la primera fase sin avance vigente y devuelve `phase`, `front`, `purpose`, `action`, `task`, `role`, `role_label` y `actor`. `actor` es `null` si no se entregó un mapeo de roles; el runner no presupone la identidad de una persona. Las acciones son `create_artifacts`, `repair_artifacts`, `resolve_contradiction`, `human_approval`, `review_phase`, `advance_phase` y `complete`.

Desde la CLI, `organon next-task ./mi-caso --roles '{"reviewer":"agent:revisor"}'` devuelve la misma estructura. En MCP, la herramienta se llama `next_task` y recibe `path` y el objeto opcional `roles`.

También entrega `inputs` de fases anteriores y `artifacts` de la fase actual. Cada ítem lleva ID, tipo, versión, referencias versionadas, texto y datos resumidos, además de señales de obsolescencia, contradicción y problemas. `missing` enumera mínimos pendientes por tipo; `approval_targets` indica versión exacta que requiere decisión humana. `criteria` contiene salida, revisión y detención; `gate` y `blockers` provienen del motor. El contexto muestra hasta 24 ítems de entrada y 24 actuales, con recuentos `omitted`; trunca textos y datos largos. Para inspección completa usa `engine.trace(path, id)` o el registro del caso.

La recomendación de rol no ejecuta una decisión. La aprobación de normas y decisiones exige `engine.approve` con actor `human:<nombre>` y motivo. Ese prefijo es una autodeclaración; la autenticación de identidad corresponde al proceso externo del caso.

## Ejecutar un manifiesto

```python
import json
from specorganon import engine
from specorganon.runner import run_manifest

path = "./mi-caso"
manifest = json.load(open("./workflow.json", encoding="utf-8"))
result = run_manifest(path, manifest, actor="agent:ejecutor")
print(result["status"], result["reason"], result["next"])
```

El caso debe existir antes de ejecutar el manifiesto (`engine.create_case`). El esquema es JSON `{"schema": 1, "steps": [...]}`. Cada paso tiene uno de estos formatos:

La CLI ejecuta `organon run ./mi-caso --manifest ./workflow.json --actor agent:ejecutor`; la herramienta MCP `run` recibe el objeto `manifest` directamente. Los dos caminos comparten los mismos checkpoints y se pueden alternar durante una reanudación.

```json
{"op":"put","id":"p1","kind":"problem","text":"Problema delimitado por el caso","refs":[],"data":{}}
{"op":"advance","phase":"frame"}
```

`put` solo registra contenido declarado por quien entrega el manifiesto; el runner no genera hallazgos, fuentes, resultados ni veredictos. `refs` apunta a IDs ya presentes o a pasos anteriores del mismo manifiesto. Un paso `put` nuevo espera versión 0; para una revisión explícita se añade `"expected_version": 1` (o la versión vigente). Una repetición del paso acepta únicamente la versión siguiente si tipo, texto, datos y versiones de referencias coinciden exactamente. Si el ledger diverge, `ManifestError` obliga a revisar el plan en vez de sobrescribir el trabajo ajeno. Los IDs y avances de fase no pueden repetirse dentro de un manifiesto.

`advance` actúa solo cuando la compuerta está lista y existe una revisión aceptada e independiente del snapshot actual. El runner **no** admite operaciones `approve` ni `review_phase` dentro del manifiesto. Los pasos `put` pueden reparar artefactos obsoletos o preparar ramas independientes mientras otra fase tiene una objeción; se conservan como borradores y no se confunden con un avance justificado. Un `advance` se detiene con `status: "waiting"` ante aprobación humana, revisión, contradicción, artefacto inválido u obsoleto, o fase anterior sin aceptar. El resultado contiene `cursor` (índice del siguiente paso), `applied`, `skipped`, `reason` y `next`. Tras registrar la decisión o corregir el caso, ejecuta de nuevo el mismo manifiesto, incluso desde otro proceso. Los pasos ya materializados se omiten sin añadir eventos. `status: "complete"` requiere que todas las fases estén aceptadas; un manifiesto agotado antes de eso queda `waiting` con la razón pendiente, o `manifest_exhausted` si solo faltan pasos no declarados.

La validación estructural del manifiesto y sus referencias adelantadas ocurre antes de cualquier escritura. Un fallo semántico en un paso posterior puede dejar pasos anteriores como checkpoint válido; nunca hay rollback implícito. El runner serializa invocaciones concurrentes del mismo manifiesto mediante `.organon.runner.lock`; las ediciones directas con el motor siguen requiriendo coordinación entre actores. Editar un manifiesto después de ejecutarlo exige una nueva revisión consciente del caso. El runner no autentica actores, no sustituye medición de campo y no convierte valores simulados en impacto observado.

## Fixture reproducible

[`workflows/synthetic_full.json`](../workflows/synthetic_full.json) contiene entradas **inventadas y etiquetadas como sintéticas** para probar la mecánica de las nueve fases. Incluye dos compromisos que requieren una aprobación etiquetada como humana en la fixture y una revisión independiente por fase. `tests/test_runner.py` lo reanuda desde procesos nuevos, comprueba ausencia de eventos duplicados, examina artefactos persistidos y fuerza divergencia e interrupción por contradicción. `tests/test_interruption.py` mata realmente el proceso runner con `SIGKILL` después de un checkpoint y comprueba que la repetición completa los pasos sin duplicados. `scripts/clean_smoke.py` verifica las nueve fases mediante un wheel instalado fuera del repositorio y un cliente MCP real. Las etiquetas de la fixture no autentican a nadie ni sirven como evidencia de una intervención real.
