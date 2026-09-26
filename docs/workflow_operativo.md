# Workflow operativo y reanudación

`specorganon.runner` usa las mismas fases y compuertas que `specorganon.engine`. El caso vive en `organon.json`; sus eventos versionados son el checkpoint. Una interrupción no exige restaurar un estado paralelo: vuelve a llamar al runner con el mismo manifiesto. Para auditoría de producción, la secuencia y cabeza de cada transición autorizada deben anclarse externamente o custodiarse en almacenamiento append-only: los hashes internos no impiden borrar eventos posteriores a una aprobación firmada ni añadir falsas revisiones y avances mediante escritura directa. El verificador opcional `ORGANON_LEDGER_ANCHORS_FILE` compara cada lectura con la cabeza externa exacta. En ese modo, una ejecución de `run` que escribe un evento queda detenida para la siguiente lectura hasta que un custodio independiente verifique y actualice el ancla; por ello un manifiesto de varios pasos exige esa coordinación por transición y reanudación. Las etiquetas de revisores en el ledger tampoco autentican su identidad.

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

La recomendación de rol no ejecuta una decisión. Los casos reales se crean con `approval_policy="signed"` y un `case_id` UUID. Antes de aprobar, el operador registra UUID, ruta canónica, `project_sha256` y clave pública del actor en el archivo externo `ORGANON_APPROVERS_FILE`. Cuando `next_task` indica `human_approval`, se revisa la norma o decisión vigente, se solicita `engine.approval_challenge(path, id, reason, actor)` y se entrega su `message_base64` a la persona autorizada para firmar fuera del entorno del agente. El mensaje canónico liga ruta y metadatos del caso, cabeza previa del ledger, versión y hash del ítem, actor y motivo. Luego `engine.approve(path, id, reason, actor, signature)` comprueba la firma Ed25519 en base64 con la clave pública registrada. Si ocurre otro evento antes de registrar la aprobación, se pide un desafío nuevo. CLI y MCP exponen los mismos pasos como `approval-challenge`/`approval_challenge` y `approve`; el [flujo seguro y el formato del archivo](interfaces.md#aprobación-firmada-de-un-caso-real) están documentados allí. Una clave ausente o revocada, un caso copiado a otra ruta o metadatos alterados vuelven no verificada la aprobación durante el replay y bloquean la compuerta correspondiente. La firma acredita control de la clave configurada; identidad, custodia y autoridad para decidir requieren verificación humana externa.

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

`advance` actúa solo cuando la compuerta está lista y existe una revisión aceptada e independiente del snapshot actual. El runner **no** admite operaciones `approve` ni `review_phase` dentro del manifiesto. Los pasos `put` pueden reparar artefactos obsoletos o preparar ramas independientes mientras otra fase tiene una objeción; se conservan como borradores y no se confunden con un avance justificado. Un `advance` se detiene con `status: "waiting"` ante aprobación humana, revisión, contradicción, artefacto inválido u obsoleto, o fase anterior sin aceptar. El resultado contiene `cursor` (índice del siguiente paso), `applied`, `skipped`, `reason` y `next`. Tras registrar la aprobación firmada y verificada o corregir el caso, ejecuta de nuevo el mismo manifiesto, incluso desde otro proceso. Los pasos ya materializados se omiten sin añadir eventos. `status: "complete"` requiere que todas las fases estén aceptadas; un manifiesto agotado antes de eso queda `waiting` con la razón pendiente, o `manifest_exhausted` si solo faltan pasos no declarados.

La validación estructural del manifiesto y sus referencias adelantadas ocurre antes de cualquier escritura. Un fallo semántico en un paso posterior puede dejar pasos anteriores como checkpoint válido; nunca hay rollback implícito. El runner serializa invocaciones concurrentes del mismo manifiesto mediante `.organon.runner.lock`; las ediciones directas con el motor siguen requiriendo coordinación entre actores. Editar un manifiesto después de ejecutarlo exige una nueva revisión consciente del caso. El runner no autentica actores, no sustituye medición de campo y no convierte valores simulados en impacto observado.

## Fixture reproducible

[`workflows/synthetic_full.json`](../workflows/synthetic_full.json) contiene entradas **inventadas y etiquetadas como sintéticas** para probar la mecánica de las nueve fases. Sus casos se crean explícitamente con `--approval-policy fixture` y se ejecutan en rutas no registradas, con `ORGANON_ALLOW_FIXTURES=1` en el entorno de prueba: solo `human:fixture` puede aprobar, sin firma, y esa etiqueta no representa autorización humana. Sin la variable, el ledger se lee pero sus aprobaciones no satisfacen compuertas. Incluye dos compromisos que requieren esa aprobación simulada y una revisión independiente por fase. `tests/test_runner.py` lo reanuda desde procesos nuevos, comprueba ausencia de eventos duplicados, examina artefactos persistidos y fuerza divergencia e interrupción por contradicción. `tests/test_interruption.py` mata realmente el proceso runner con `SIGKILL` después de un checkpoint y comprueba que la repetición completa los pasos sin duplicados. `scripts/clean_smoke.py` verifica las nueve fases mediante un wheel instalado fuera del repositorio y un cliente MCP real. La fixture no sirve como evidencia de una intervención real.
