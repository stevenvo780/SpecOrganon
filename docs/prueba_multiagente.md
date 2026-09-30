# Pruebas de coordinación de agentes reales

## D-103: dos agentes sobre el wheel actual en ambos intérpretes

[Dossier y recibos](../experiments/development/installed_complete_interface_2026-09-30/).
Los threads nativos existentes `/root/subscription_method_broker_099` y
`/root/source_gate_review` ejecutaron el CLI instalado del mismo wheel D-102
en Python 3.11.15 y 3.12.3, en casos nuevos con política signed. Cada agente
creó un actor y un límite con IDs disjuntos, versión esperada 0 y dependencias
en versión 1. Antes de liberar los FIFOs, el supervisor verificó procesos
vivos bloqueados en `wait_for_partner`, identidad del FIFO y ausencia de
llamadas o cambios previos. Los cuatro ítems persisten una sola vez por
entorno: cinco eventos con cadena válida, cuatro pares CLI/MCP de lectura
sin escritura y descubrimiento real de 22 herramientas.

Actividad de los procesos se solapó 184922046 ns en 3.11 y 173400743 ns en
3.12; las mayores intersecciones de llamadas CLI fueron 64283469 y
57624802 ns. El solapamiento fue inducido por la barrera, sin pausas
artificiales entre puts. No mide calidad, coste, velocidad del modelo o
ventaja frente a un agente. Modelo y esfuerzo efectivos no autenticados.
Los recibos verifican 24 módulos y wheel antes/después; entorno mínimo
conserva HOME original sin heredar tokens o copiar configuración.

Los agentes sólo publicaron ítems pendientes: cero aprobaciones, revisiones
o avances. La prueba separada signed_observed recorrió nueve fases con
firmas sintéticas, ejecución/repetición real y artefactos conservados. GOAL
y la matriz permiten separar esas coberturas. Una revisión independiente
de `/root/prototype_checkpoint_supervisor` auditó ambas autorías y cerró C1
en alcance técnico; la revisión de código de `/root/source_gate_review`
excluyó sus propias escrituras B. No hay autoridad humana, impacto de campo
ni comparación confirmatoria. **Aceptación actual: 1/5**, demás criterios
No demostrados. Los registros siguientes conservan sus cortes históricos.

**Corte:** 2026-09-26 UTC. Este registro documenta operaciones de subagentes nativos sobre ledgers reales del toolkit. No representa una comparación de modelos ni mide impacto de una intervención.

## Autor y revisor en un workflow completo

Un agente `multiagent_writer` creó [`cases/synthetic_multiagent/organon.json`](../cases/synthetic_multiagent/organon.json) mediante `run_manifest`, con los 29 pasos `put` de [`workflows/synthetic_full.json`](../workflows/synthetic_full.json). El caso se creó explícitamente con `approval_policy="fixture"` en una ruta no registrada: solo admite `human:fixture` y no pide firma cuando el entorno de prueba tiene `ORGANON_ALLOW_FIXTURES=1`. Terminó con 29 ítems, ninguna revisión y `next_task.action=review_phase` para `frame`. El agente principal añadió dos aprobaciones `human:fixture` cuyo motivo dice explícitamente que son decisiones **simuladas por el harness de IA, sin consentimiento humano real**. Un segundo agente nativo, `case_reviewer`, inspeccionó los gates y registró revisión aceptada y avance de las nueve fases, incluida `validate`.

Lectura del ledger con `read_project` y `get_state` en el entorno sintético habilitado: **49 eventos**: 29 `item_put` de `agent:multiagent_writer`, dos `approval` de fixture, nueve `phase_review` y nueve `phase_advance` de `agent:case_reviewer`. Hay 29 ítems y las nueve fases figuran `accepted=true` e `independent_review=true`. Sin `ORGANON_ALLOW_FIXTURES=1`, el ledger sigue legible pero ninguna fase fixture queda aceptada y sus aprobaciones tampoco satisfacen compuertas. `ass1.verdict=no_demostrado` para campo; la prueba de `build` es un comando declarado de fixture, no una ejecución externa. Esta corrida documentó división de escritura y revisión, gates entre agentes y persistencia junto con trazas de ejecución de los subagentes. Las etiquetas `actor` del ledger por sí solas no autentican a un revisor. No demuestra aprobación humana, validez empírica ni la utilidad de añadir un agente frente a uno solo. El carril de aprobaciones firmadas de casos reales requiere una prueba independiente: estas aprobaciones de fixture no lo ejercen.

En los casos documentales reales, un agente con etiqueta distinta del autor revisó y avanzó históricamente `frame` de [mango](../cases/mango/organon.json) y [Citi Bike](../cases/citibike/organon.json). El revisor examinó alcance y fuentes para ese encuadre; las normas siguen sin aprobación y las fases siguientes bloqueadas. Esas revisiones no tienen firma, por lo que el replay actual conserva los eventos pero informa `review_provenance=legacy_unverified` y `frame.accepted=false`. Ayudaron a encontrar límites de los datos, pero no prueban identidad o independencia real; tampoco se midieron minutos, tokens o coste marginal de la revisión.

## Dos escritores asignados en paralelo

En [`cases/synthetic_concurrent/organon.json`](../cases/synthetic_concurrent/organon.json), el agente principal creó `p0`. Se lanzaron dos agentes nativos para escribir ítems **disjuntos**: `concurrent_a` insertó 20 `actor` y `concurrent_b` 20 `boundary`, todos referenciando `p0`. Cada uno reportó cero conflictos; `read_project` verificó 41 eventos, 41 ítems válidos y 20 eventos por escritor. La secuencia de autores es `root → concurrent_a (20) → concurrent_b (20)`, con solo dos cambios de autor. Por tanto, el ledger demuestra que ambas asignaciones persistieron sin pérdida, **pero no demuestra solapamiento temporal de sus escrituras** ni mejora de tiempo por paralelismo. El [test de replays simultáneos](../tests/test_runner.py) comprueba aparte que dos procesos que ejecutan el mismo manifiesto no duplican eventos, con resultado aplicado `[0,3]`; son procesos, no agentes de modelo.

El resultado negativo de ese caso es útil: lanzar dos agentes no garantiza paralelismo efectivo cuando la preparación y la serialización del ledger dominan una tarea pequeña. Para estimar beneficio de especialización, revisión o exploración paralela harán falta tareas más sustantivas, telemetría de tiempo/tokens/coste, configuraciones iguales salvo la coordinación, réplicas y evaluadores externos, según el [protocolo](protocolo_experimental.md). No se atribuye calidad superior a estos ejemplos.

## Solapamiento medido: una prueba sintética de desarrollo

Se hizo una prueba adicional con dos agentes nativos sobre un caso compartido, cada uno con 40 IDs disjuntos. La [primera ronda](../cases/synthetic_overlap/organon.json) conservó **41 eventos**: el problema `p1` del controlador y `a_001`–`a_040` de A. B terminó con código 1 tras `ConflictError: revision conflict: expected 40, current 41`, antes de persistir un ítem. El ledger confirma B=0; la salida de error de B fue observada durante esa ejecución, pero no quedó archivada para comprobarla de nuevo. Ese fallo se conserva como resultado negativo, no se descarta por el éxito posterior.

Para la [segunda ronda](../cases/synthetic_overlap_round2/organon.json), [`concurrent_agent_writer.py`](../scripts/concurrent_agent_writer.py) reintentó `ConflictError` hasta 100 veces por ítem, con pausa creciente acotada a 15 ms, y dejó 3 ms tras cada inserción para dar turno al otro proceso. Los [registros de A](../experiments/development/native_overlap_round2_a.json) y [B](../experiments/development/native_overlap_round2_b.json) indican 39 y 40 conflictos de revisión reintentados, respectivamente. Sus intervalos monotónicos activos se solapan **487 098 218 ns** (aprox. 0,487 s). El ledger tiene **81 eventos**: uno del controlador, 40 de A y 40 de B, con los 80 IDs esperados una sola vez, cadena de hashes válida y **80 cambios de actor**. Los eventos de A y B alternan en las 80 inserciones. Los intervalos prueban actividad concurrente de los procesos bajo el reloj local; las inserciones al ledger siguieron serializadas.

El [verificador reproducible](../scripts/check_native_overlap.py) coteja ambos ledgers, IDs, autores, secuencia y hashes con los dos registros de la segunda ronda y el [informe JSON](../experiments/development/native_overlap_2026-09-26.json). Se ejecuta con `python3 scripts/check_native_overlap.py`. Es **una sola prueba sintética de desarrollo, con dos rondas**: no compara con una condición de un solo agente, no demuestra ventaja de tiempo, coste o calidad, y no constituye validación de campo ni confirmatoria. Las etiquetas `actor` y los registros locales tampoco autentican por sí solos la identidad de los agentes.

La corrección posterior añadió precondiciones de versión a `put` y reintentos acotados solo para cambios ajenos al ítem y sus referencias. [Una prueba separada](../tests/test_put_concurrency.py) fuerza a dos **procesos locales** a leer la misma secuencia antes de escribir: uno inserta en la secuencia 2 y el otro reintenta e inserta en la 3, sin reintento del llamador. El ledger conserva los tres IDs esperados. También se comprueban rechazos ante cambios del mismo ítem o de una referencia y ante errores del ancla externa. El [registro de desarrollo](../experiments/development/guarded_put_2026-09-26.json) conserva los gates. Esta nueva prueba es de concurrencia del software, no una ejecución de dos agentes de modelo ni una medición de ventaja de coordinación.

## CLI instalada invocada por dos subagentes nativos

En una nueva corrida sintética, las respuestas de `spawn_agent` observadas en este turno devolvieron las tareas canónicas `/root/native_direct_a` y `/root/native_direct_b`. Cada subagente ejecutó el CLI de un wheel instalado en un entorno temporal nuevo, con actor declarado distinto, `expected_version=0` y dependencia `p1=1`, y dejó [recibo A](../experiments/development/native_direct_a_2026-09-26.json) o [recibo B](../experiments/development/native_direct_b_2026-09-26.json). El [ledger](../cases/synthetic_native_direct/organon.json) conservó primero `p1` y ocho ítems disjuntos. **Resultado negativo de la primera ronda:** A terminó sus cuatro llamadas antes de que B empezara; la brecha monotónica fue 9,177 s. Los agentes fueron lanzados en paralelo, pero esa ronda no mostró escrituras simultáneas.

En la segunda ronda, el controlador observó ambos procesos bloqueados en lecturas de FIFO separadas y los liberó juntos; esa maniobra consta en el turno, no se demuestra solo con los archivos. Los [recibos A](../experiments/development/native_direct_overlap_a_2026-09-26.json) y [B](../experiments/development/native_direct_overlap_b_2026-09-26.json) registran diez llamadas `organon put` por agente, con una pausa deliberada de 5 ms tras cada éxito para permitir intercalación. Los intervalos declarados se solaparon **387 033 229 ns**. El ledger terminó con 29 eventos: los veinte nuevos ítems son únicos y sus autores alternan en las secuencias 10–29, con 19 cambios de actor. Los recibos archivan una llamada exitosa por ID, sin reintentos declarados; todos los comandos registrados salieron con código 0. El [verificador de recibos y ledger](../scripts/check_native_direct.py) y el [informe](../experiments/development/native_direct_2026-09-26.json) conservan las comprobaciones reproducibles.

El registro del turno muestra las respuestas de lanzamiento y las llamadas de los subagentes, pero los archivos del repositorio por sí solos **no autentican** esas tareas: el campo `actor` y los recibos son autodeclarados. Tampoco certifican la instalación limpia, el mecanismo de barrera o la ausencia de llamadas omitidas; el hash del wheel y las rutas son datos a cotejar, no atestaciones externas. El solapamiento mide intervalos de procesos CLI declarados y fue inducido por la barrera y las pausas; no demuestra ventaja de tiempo, calidad o coste ni conflicto de lectura específico. La fixture no sustituye autorización humana o ensayo confirmatorio.
