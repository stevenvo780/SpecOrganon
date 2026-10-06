# Usar SpecOrganon en un proyecto local

El MVP combina filosofía, ciencia, ingeniería y validación con el agente y
las herramientas que ya tengas. El toolkit conserva el expediente y sus
compuertas; el agente aporta la investigación, implementación y ejecución.

## Empezar

Desde este repositorio:

```sh
uv sync --locked
uv run organon init ./mi-proyecto --title "Mi problema" --domain desarrollo --approval-policy local --actor human:owner
uv run organon next-task ./mi-proyecto
```

Entrega al agente este encargo, completando problema y límites:

> Usa la skill de SpecOrganon en `.agents/skills/specorganon/SKILL.md` para
> resolver este proyecto: [problema]. Trabaja en `./mi-proyecto` con los
> recursos actuales y dentro de estos límites: [límites autorizados].
> Investiga, compara alternativas y fija criterios antes de implementar.
> Ejecuta las pruebas, pide revisión técnica a otro agente y conserva un
> resultado reproducible y el siguiente trabajo pendiente.

## Cómo avanza el agente

1. Formula el problema, actores y frontera; examina supuestos y fines.
2. Registra el mandato existente del dueño y las decisiones que éste haya
   delegado. Una aprobación local documenta ese mandato; no crea un permiso
   que no exista. Las decisiones normativas fuera del encargo siguen
   requiriendo al dueño.
3. Diseña una investigación verificable, recoge datos accesibles y registra
   fuentes, método e incertidumbre.
4. Compara soluciones, deriva requisitos y criterios, implementa y ejecuta
   pruebas reales con sus herramientas.
5. Otro agente lee los artefactos y resultados y emite un juicio técnico.
   El ejecutor puede registrar ese juicio real con `review-phase`; la
   separación de etiquetas representa esa distribución de trabajo.
6. Usa `advance` o un manifiesto `run` para aceptar las fases revisadas.
   Evalúa la solución y entrega el informe.

La guía de campos está en [metodologia.md](metodologia.md) y el manifiesto
reanudable en [workflow_operativo.md](workflow_operativo.md). `put` permite
preparar borradores de ramas independientes mientras otra fase está
pendiente. Si cambia una premisa, las dependencias antiguas quedan obsoletas
y requieren reparación y revisión.

Para un test local, conserva el `argv`, `command=shlex.join(argv)` y el
resultado del proceso. Su `receipt` contiene `argv`, `exit_code`,
`timed_out`, `stdout_sha256`, `stderr_sha256` y `result_sha256`; calcula este
último con `engine.local_test_result_sha256(data)`. Los campos son un recibo
declarado del workspace: conserva los streams medidos para que otro agente
los compruebe. Un fallo o recibo inválido bloquea el avance. El motor no
ejecuta el comando por ti.

## Consultar y reanudar

```sh
uv run organon report ./mi-proyecto --format markdown
uv run organon trace ./mi-proyecto ID_DEL_REQUISITO
uv run organon run ./mi-proyecto --manifest workflow.json --actor agent:ejecutor
```

El ledger es el checkpoint. Volver a ejecutar el mismo manifiesto omite sus
pasos ya materializados. Una divergencia exige revisar el plan; no sobrescribe
el trabajo ajeno. El informe muestra artefactos, dependencias, bloqueos,
alcance y siguiente tarea.

## Ejemplos comprobados

- [Entrada del MVP](../experiments/development/mvp_local_2026-10-01/run01/entry/report.md):
  problema de uso, investigación del bloqueo inicial, alternativas,
  implementación del modo local y reporte, pruebas y nueve fases revisadas.
- [Reproducción escolar](../experiments/development/mvp_local_2026-10-01/run01/school/report.md):
  mismo núcleo en un análisis local, con comparación de alternativas y
  reproducción byte por byte del JSON existente. El resultado es técnico y
  descriptivo, sin atribución causal.

Son registros de ejecuciones de desarrollo expuestas. Para otro proyecto
crea un caso nuevo; copiar esos registros no representa una ejecución nueva.

## Elegir la política

| Política | Uso | Aprobación y revisión |
| --- | --- | --- |
| `local` | Proyectos reales de desarrollo en un workspace de confianza. | Dueño creado como `human:<owner>`; mandato y revisión técnica declarados, sin autenticación externa. Tests con recibos estructurados. |
| `signed` | Casos que necesitan el registro externo y las firmas del contrato existente. Valor inicial. | Firmas y claves registradas; consultar la confianza vigente. |
| `fixture` | Pruebas con datos y decisiones inventados. | Consentimiento sintético explícito; exige habilitación de fixture. |

El modo local no cambia un caso firmado registrado ni permite un veredicto
decisivo de campo. El resultado de este MVP justifica su uso local; el aporte
frente a otros métodos y la eficacia material mantienen sus evaluaciones
pendientes.
