---
name: specorganon
description: Resuelve un proyecto con filosofía, investigación verificable, comparación de intervenciones, SDD y validación usando el toolkit SpecOrganon. Úsalo al trabajar un caso del método; para una corrección pequeña sin caso conserva su alcance habitual.
---

# Trabajar con SpecOrganon

Usa los comandos `organon` o las herramientas MCP equivalentes. El agente
razona, investiga y ejecuta pruebas con sus herramientas disponibles; el
toolkit conserva artefactos, versiones, dependencias y compuertas. No hace
llamadas a modelos por sí solo. En este repositorio, invoca la CLI mediante
`uv run organon`.

## Encargo y política

Lee el encargo y los límites autorizados. Si existe un caso, consulta
`status`, `report` y `next-task` antes de escribir. Si falta una decisión,
prepara trabajo que no dependa de ella y presenta el pendiente concreto.

Para un proyecto de desarrollo en un workspace de confianza, elige
explícitamente `init RUTA --approval-policy local --actor human:owner`
con título y dominio. `human:owner` es una etiqueta declarativa del dueño;
usa la etiqueta real elegida por el operador cuando esté disponible. El
modo local conserva normas y decisiones aprobadas, pero no autentica
identidades ni custodia. Los demás casos conservan el modo firmado inicial.
Usa fixtures únicamente para datos y aprobaciones inventadas de pruebas.

Registra como norma el propósito y los límites que el dueño haya aprobado.
Una aprobación local documenta ese mandato existente con su motivo y actor
del dueño; no inventes consentimiento. Una elección técnica delegada debe
indicar esa delegación, sin afirmar que el dueño eligió personalmente la
opción. Un conflicto de valor fuera del mandato exige una decisión nueva.

## Recorrido de trabajo

Aplica los cuatro frentes al proyecto, con la profundidad que requiera:

- Filosofía: delimita problema, actores y frontera; examina conceptos,
  supuestos, encuadres rivales y fines.
- Ciencia: formula preguntas e hipótesis, fija un protocolo y criterios
  antes de medir. Recoge evidencia accesible con fuente, fecha, localizador
  y método; distingue observaciones, inferencias, supuestos y simulaciones.
- Ingeniería: compara alternativas sustanciales, registra costes y riesgos,
  deriva requisitos trazables, construye y ejecuta pruebas.
- Validación: contrasta con la línea base y los criterios previos, conserva
  resultados adversos y limita el veredicto al alcance observado.

Consulta los contratos y campos de cada fase en
[metodologia.md](../../../docs/metodologia.md) y
[workflow_operativo.md](../../../docs/workflow_operativo.md) desde la raíz
del repositorio. Las rutas de estos enlaces son relativas a este archivo.

Cada `put` enlaza IDs existentes mediante `--ref`. Al editar trabajo
compartido, fija `--expected-version` y `--expected-deps`. Usa `trace` para
comprobar la ruta de un requisito hasta problema, norma y evidencia.
Una premisa revisada puede dejar descendientes obsoletos: repáralos de
acuerdo con los hallazgos y solicita nueva revisión, conservando la historia.

## Revisión, pruebas y entrega

Otro agente puede revisar las fases técnicas locales. Debe leer los
artefactos y resultados reales, informar hallazgos y decidir aceptación o
rechazo; cambiar la etiqueta del autor no crea una revisión independiente.
Registra su juicio con `review-phase` antes de `advance`. Para un caso
firmado, conserva el registro y las firmas que exija su política.

Ejecuta las pruebas fuera del motor con un `argv` explícito y conserva
comando, salida, código de retorno y timeout. Para un test local, registra
`passed`, `command`, `argv` y un `receipt` con `argv`, `exit_code`,
`timed_out`, `stdout_sha256`, `stderr_sha256` y `result_sha256`.
`specorganon.engine.local_test_result_sha256(data)` calcula este último
digest sobre los campos del recibo; no ejecuta ni autentica la prueba.
Usa la interfaz del motor o un manifiesto para esos datos estructurados.
Una prueba fallida o un recibo inválido mantiene bloqueado el avance.

El ledger es el checkpoint. Reanuda un manifiesto con `run` sin repetir ni
reescribir sus pasos ya materializados. El runner puede registrar borradores
de ramas independientes antes de una aceptación; no añade revisiones ni
consentimiento al manifiesto.

Entrega `report RUTA --format markdown`, el resultado utilizable y una
instrucción reproducible. Explica qué verificaste y qué falta. En modo local,
un resultado técnico puede quedar cumplido; una mejora de campo necesita
otra evidencia y política. No conviertas una entrega local en una prueba de
superioridad frente a SDD ni en una evaluación reservada.
