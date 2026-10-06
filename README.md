# SpecOrganon

Método y toolkit para formular problemas, investigar con evidencia, comparar intervenciones, construir software mediante SDD y validar resultados. Sus nueve fases conservan artefactos, dependencias, revisiones y un ledger verificable. Incluye CLI, servidor MCP stdio, laboratorio Docker con Codex y una presentación pública.

**Repositorio compartido:** [rama main](https://github.com/stevenvo780/SpecOrganon/tree/main). **Presentación y resultados:** [specorganon.stevenvallejo.com](https://specorganon.stevenvallejo.com). Las fuentes de la web están en [website/](website/README.md).

**Estado del código:** candidata en desarrollo **0.2.0rc3.dev7**, con transporte explícito `items-v1`: el autor aporta contenido y referencias; el toolkit construye el manifiesto y conserva la procedencia. [Contrato del autor](docs/software_author_contract.md) y [verificación de dev3](goals/method-superiority-v1/evidence/bounded-admission-01/engineering-receipt.json). La política schema12 añade una [corrección de admisión opt-in](goals/method-superiority-v1/development/BOUNDED_ADMISSION.md) dentro de las cuotas originales y conserva avisos de reconexión del mismo turno; exige juicios de texto sin ejecución de tests. No migra runs anteriores.

**Resultados y límites:** RangeAudit produjo una entrega nativa de nueve fases, con Codex como autor, Gemini como revisor y pruebas ejecutadas en Docker; pasó 115 comprobaciones públicas adicionales. Es un caso de desarrollo, sin evaluación reservada ni demostración de superioridad. La campaña comparativa v3 y el piloto anterior conservan sus resultados adversos y fuentes históricas: no se recalcularon con este código. La [meta para demostrar ventaja frente a libre y SDD](goals/method-superiority-v1/GOAL.md) sigue activa. El [GOAL original](GOAL.md) conserva el objetivo alimentario y sus límites de evidencia de campo.

**Cohorte de fiabilidad cerrada, versión dev2 congelada:** los diez intentos fijados terminaron: tres entregas completas (30%) y siete fallos, sin reemplazos. RangeAudit completó dos intentos con 115/115 comprobaciones públicas cada uno y LedgerFold uno con 104/104. El [informe terminal verificado](goals/method-superiority-v1/evidence/provider-json-schema-01/cohort-terminal-01/summary.json) conserva los fallos y un intervalo Wilson descriptivo de aproximadamente 10.8–60.3%; no cumple el 90%. Ninguna comparación reservada. [Protocolo y límites](goals/method-superiority-v1/development/NATIVE_COHORT.md).

**Cohorte dev4 02 cerrada:** cinco entregas completas de diez (50%), tres tipos
con nueve fases y 543/543 controles públicos sobre las cinco entregas. Los cinco
fallos se conservan, sin reemplazos: tres controles Docker, uno por admisión/cuota
de autores de compare y otro por JSON inválido. Wilson descriptivo23.66–76.34%;
no cumple 9/10 ni demuestra ventaja frente a libre o SDD. El driver original y
las 45 fuentes congeladas verificaron el cierre sin llamadas o tests nuevos.
[Informe terminal, fuentes y recibos](goals/method-superiority-v1/evidence/native02-terminal-01/README.md).

Las fuentes actuales son dev7 en desarrollo; la última wheel publicada es dev5.
Las cohortes dev2 y dev4 conservan sus checkouts y fuentes congeladas: un clon de
main no puede reanudar esos registros ni migrar sus runs. Las pruebas de una
versión distinta requieren otra ruta y otro registro.

**Corte histórico dev6, infraestructura parcial para controles competentes:** formato explícito
de archivos/documentos N/S, auditoría D/G común con H separada, y captura física
de snapshots sin promover veredictos o archivos de recibo a ejecuciones. Pasan
389 pruebas acotadas y tres quedan omitidas; wheel local con sus 34 módulos
verificados y CLI exit0. La revisión independiente rechazó un defecto de tipado,
corregido y aceptado en una revisión posterior limitada a estos helpers. En ese corte faltaban
la máquina de etapas N/S, contabilidad integrada, compuerta común y registro
estadístico; no hay generaciones dev6 ni superioridad medida.
[Fuentes, pruebas y límites](goals/method-superiority-v1/evidence/neutral-controls-01/README.md).

**Dev4 publicado como candidato de desarrollo:** guía JSON compartida entre proveedores, validación estricta local y transporte schema4 vinculado a hashes del puente y los módulos Python. El diagnóstico conserva nueve llamadas: seis fallos de formato y tres respuestas válidas de un solo turno; no son entregas de software ni demuestran eficacia. Pasan 296 controles acotados del host y la revisión independiente estática; el wheel final instalado pasó los mismos 296 controles y el smoke CLI/MCP con 24 herramientas. El driver versionado pasó 45 controles en host y Docker. La [cohorte dev4 02](goals/method-superiority-v1/development/registration-native-cohort-02.json) se registró antes de generar, con diez intentos y 45 fuentes vinculadas; su cierre es desarrollo público, sin comparación reservada. [Fuentes y recibos](goals/method-superiority-v1/evidence/provider-json-schema-01/README.md).

**Dev7, ingeniería instalada:** controlador N libre durable v2 y driver N/S schema2; 186 pruebas seleccionadas aprobadas. El primer lote Docker conserva19pass1fallo de contador; las tres pruebas nuevas afectadas corregidas pasaron y los otros17 no se repitieron. Wheel e imágenes locales verifican40 módulos idénticos, CLI0.160 yMCP24; no hay nueva release pública/registry. Revisión Gemini estática limitada, sin admisión nativa. Cero generaciones/reservados, competencia/F/comparación pendientes y meta activa. [Informe y fallos](goals/method-superiority-v1/evidence/neutral-autonomy-controller-01/engineering-receipt.json), [estado y pendientes](goals/method-superiority-v1/development/neutral-autonomy-v2/IMPLEMENTATION_STATUS.md), [hito en la web](https://specorganon.stevenvallejo.com/#avance-dev7).

**Último piloto público dev7, cerrado:** seis gates fallidos de seis por `exact canonical request exceeds budget`, sin reemplazos. Los programas pasaron648/648 comprobaciones públicas descriptivas; no acreditan D/Gfinal, paquete común, F reservado, competencia ni superioridad. [Informe final](goals/method-superiority-v1/evidence/neutral-native-pilot-dev7-final-01/summary.json), [originales y límites](goals/method-superiority-v1/evidence/neutral-native-pilot-dev7-final-01/README.md), [web actualizada](https://specorganon.stevenvallejo.com/#piloto-dev7). Report01parcial2/6 se conserva histórico; desarrollo futurocodec no cambia estas fuentes ni resultados.

**Main actual, dev8 de ingeniería parcial:** contexto N/S lossless con referencias compartidas, preservando todo el historial, metadatos, capturas, criterios y localizadores. El recibo registra156 pruebas seleccionadas,41 módulos instalados byte iguales yCLI/MCP24; dos defectos de recursos rechazados por Codex fueron corregidos y aceptados en revisión acotada. Seis reconstrucciones offline y tres auditorías hipotéticas caben dentro de110000 bytes de request y128000 de prompt; nunca se despacharon como nuevos intentos. No hay admisión, freeze completo, calificación, competencia ni superioridad. Wheel e imágenes locales; último wheel público dev5. [Informe](goals/method-superiority-v1/evidence/request-content-dev8-01/engineering-receipt.json), [fuentes y límites](goals/method-superiority-v1/evidence/request-content-dev8-01/README.md), [hito web](https://specorganon.stevenvallejo.com/#avance-dev8). El resultado dev7 de seis gates fallidos permanece intacto.

## Clonar y empezar

```sh
git clone --branch main https://github.com/stevenvo780/SpecOrganon.git
cd SpecOrganon
uv sync --frozen --extra dev
uv run organon --help
```

Requiere Linux y Python 3.11 o superior; `uv.lock` fija las dependencias. El MCP usa Landlock ABI 5+ para confinar las rutas. Para construir y comprobar la instalación, consulta la sección de verificación y el [laboratorio Docker](docker/codex/README.md).

## Entregas, campañas y reproducción

- [TopoPlan](examples/topoplan/PROVENANCE.md): entrega original dev4 del intento06, nueve fases y 105/105 controles públicos, conservada sin reparación ni nueva generación.
- [LedgerFold](examples/ledgerfold/PROVENANCE.md): entrega original del intento08, nueve fases y 104/104 comprobaciones públicas; la cohorte sigue sin cumplir fiabilidad.
- [RangeAudit](examples/rangeaudit/PROVENANCE.md): programa, README y pruebas originales sin alterar, con una guía para ejecutarlo desde este checkout. [Contrato y comprobador público](goals/method-superiority-v1/development/).
- [Producto de backups](experiments/backup_pilot/product/README.md): implementación utilizable del piloto, elegida desde trabajo libre sin reparar sus bytes. [Resultados de 18 ejecuciones y 36 evaluaciones](experiments/backup_pilot/RESULTADOS.md).
- [Campaña de software v3](goals/autonomous-software-v1/): resultados y reanálisis publicado separados de la generación original. Las rutas y digests registrados pertenecen a sus worktrees originales; clonar main no permite reabrir ni continuar esas campañas congeladas.
- [Descargas verificadas](website/public/resultados/software/descargas-manifest.json): paquetes, wheel, contratos e informes publicados, con hashes. Los [paquetes anteriores](releases/historical/dist-20261002/README.md) conservan sus versiones históricas.

## Empezar un proyecto local con un agente

Con el entorno instalado, crea un caso de desarrollo explícito y dale al
agente el encargo y la [skill de SpecOrganon](.agents/skills/specorganon/SKILL.md):

```sh
uv run organon init ./mi-proyecto --title "Problema acotado" --domain desarrollo --approval-policy local --actor human:owner
uv run organon next-task ./mi-proyecto
uv run organon report ./mi-proyecto --format markdown
```

El agente aplica filosofía, investigación verificable, comparación de
soluciones, SDD y validación. Usa sus herramientas para investigar y ejecutar
pruebas; otro agente revisa el trabajo. El ledger conserva los checkpoints y
el informe muestra resultados, dependencias y siguiente tarea.

`local` sirve para el workspace de desarrollo de confianza: registra el
mandato existente del dueño y revisiones técnicas declaradas. No autentica
personas ni acredita impacto de campo. El modo inicial sigue siendo
`signed` si se omite la opción. [Guía de uso local](docs/uso_local.md).

## Instalar y verificar

La instalación está probada en Linux con Python 3.11 y 3.12 y [`uv`](https://docs.astral.sh/uv/); el paquete declara Python 3.11 o superior. El servidor MCP usa descriptores de directorio y `/proc/self/fd`; su límite de rutas requiere una raíz bajo control del operador, sin escritores locales no confiables con el mismo UID. Desde la raíz del repositorio:

```sh
uv sync --frozen --extra dev
uv run python -m pytest -q tests
uv build --wheel
```

La suite completa del host tiene fallos conocidos y no se declara aprobada: en esta integración hubo 696 pruebas pasadas, 45 fallos y 43 errores antes de interrumpirla, incluidos conflictos con el digest del extractor PDF histórico. El candidato dev2 pasó 186 pruebas y 46 subpruebas. Dev3 pasó 193 controles específicos en el host y otros 193 contra el wheel instalado en Docker, además del smoke CLI/MCP real con 24 herramientas. Son suites delimitadas; no declaran aprobada la suite global. [Recibo y logs de integración](goals/publication-main-20261006/README.md).

Para repetir una comprobación acotada en un Python ya disponible, usa
`python3 scripts/check_python_compatibility.py --python python3.13 --output /tmp/organon-python313`.
El directorio de salida debe ser nuevo y externo al repositorio. Construye e
instala un wheel limpio con dependencias fijadas por `uv.lock`, ejecuta la CLI
y MCP stdio reales y comprueba el flujo local, informes, ledger y replay.
No descarga intérpretes. Consulta [alcance y reproducción por versión](docs/python_compatibility.md);
esta comprobación no sustituye la suite completa ni una revisión nativa.

Para probar el wheel fuera del árbol de desarrollo, crea un entorno temporal, instala `releases/method-superiority/dev5/specorganon-0.2.0rc3.dev5-py3-none-any.whl` y ejecuta `scripts/clean_smoke.py` con el Python de ese entorno. El script crea fixtures sintéticas, descubre las 24 herramientas MCP actuales e invoca 15 operaciones por CLI y cliente MCP stdio real; las otras rutas se ejercitan en las [pruebas de atestación](tests/test_approval_security.py), [ejecución firmada](tests/test_signed_test_execution_transport.py), [observación firmada](tests/test_test_observation_transport.py) y [sonda del diario de lotes](scripts/probe_bread_prospectus.py). El [inventario D-079](experiments/development/installed_public_interface_inventory_2026-09-27.json) registra su corte histórico de 19/19, antes de añadir la observación. El [dossier D-107](experiments/development/indicator_retirement_2026-09-30/README.md) conserva el wheel instalado y el inventario técnico de ese corte de 23/23 operaciones en Python 3.11 y 3.12. El smoke recorre las nueve fases, comprueba `organon.json`, rechaza entradas JSON no finitas y números que se perderían por subdesbordamiento sin mutar el ledger, y verifica una repetición sin duplicados. Interrumpe con `SIGKILL` un runner CLI tras un checkpoint, reanuda el mismo manifiesto por MCP y coteja estado y replay. Libera dos procesos CLI escritores con precondiciones de versión y verifica ambos ítems; la barrera no demuestra una colisión de lecturas. Además ejercita una aprobación Ed25519 **sintética** con clave generada en memoria y comprueba rechazo de firma inválida y bloqueo al retirar el registro de confianza:

```sh
uv venv /tmp/organon-check
uv pip install --python /tmp/organon-check/bin/python releases/method-superiority/dev5/specorganon-0.2.0rc3.dev5-py3-none-any.whl
/tmp/organon-check/bin/python scripts/clean_smoke.py "$PWD"
```

El smoke también rechaza un decimal largo que perdería valor al serializarse; la [regla numérica de las interfaces](docs/interfaces.md) describe el alcance de esta comprobación.

El script crea explícitamente un caso con `--approval-policy fixture` y habilita `ORGANON_ALLOW_FIXTURES=1` solo para la prueba. Sus aprobaciones y resultados son **inventados para pruebas**. Tampoco la firma sintética representa consentimiento humano. No prueban decisiones humanas reales ni eficacia de una intervención. El entorno de producción debe omitir esa variable; sin ella, las fases de una fixture no quedan aceptadas al releer el ledger.

La [sonda firmada de nueve fases](scripts/probe_signed_full_workflow.py) complementa ese smoke. Su [test](tests/test_signed_full_workflow.py) construye e instala un wheel nuevo en un entorno temporal y recorre el manifiesto sintético por CLI y MCP stdio. El modo por defecto `signed_report` comprueba dos aprobaciones, nueve revisiones, 29 artefactos, reporte firmado de `t1`, replay y revocación. Con `--test-gate-policy signed_observed`, crea **desde el inicio** un caso estricto, fija un ejecutable y un archivo de entrada, repite `t1` bajo sandbox, registra el recibo firmado por MCP y comprueba bloqueo al alterar insumo o artefacto o retirar la clave del observador. Los [recibos de Python 3.11 y 3.12](experiments/development/signed_observed_full_workflow_2026-09-28/) documentan esa ejecución local. Las claves y decisiones son sintéticas y comparten proceso; la repetición no acredita custodia externa, ejecución histórica, revisión humana ni impacto de campo.

El smoke compara el resultado observable de 15 operaciones compartidas CLI/MCP: 13 sobre casos gemelos con entradas iguales y los desafíos `approval-challenge` y `phase-review-challenge` sobre el mismo caso firmado. También verifica por separado una firma válida aceptada mediante `approve --signature` y otra mediante MCP. Los tiempos y hashes de eventos de casos distintos no son iguales; cada evento se coteja con su propio ledger y se verifica que su tiempo UTC corresponda a la operación.

## Trabajar en un caso

```sh
uv run organon init ./mi-caso --title "Problema delimitado" --domain ejemplo --actor agente:analista
uv run organon put ./mi-caso p1 --kind problem --text "Problema y afectados por delimitar" --actor agente:analista
uv run organon next-task ./mi-caso
uv run organon gate ./mi-caso frame
uv run organon status ./mi-caso
```

`init` usa `approval_policy="signed"` y `test_gate_policy="signed_report"` por defecto y asigna al caso un `case_id` UUID. `next-task` indica la fase pendiente, entradas, artefactos, versiones, revisión y bloqueos. `put` enlaza artefactos con `--ref ID` repetible y acepta datos estructurados con `--data '{"clave":"valor"}'`; la CLI rechaza `NaN`, `Infinity`, desbordamiento a infinito y subdesbordamiento de un número no nulo a cero. En casos compartidos usa `--expected-version` y `--expected-deps` para fijar las versiones que autorizó el autor del contenido. `trace` muestra antecesores y descendientes. Para aprobar una norma o decisión en un caso real, el operador registra previamente UUID, ruta canónica, digest de metadatos y clave pública en el archivo externo `ORGANON_APPROVERS_FILE`; el responsable obtiene `approval-challenge`, verifica el caso y la cabeza del ledger, firma fuera del entorno del agente los bytes indicados por `message_base64` y entrega la firma Ed25519 en base64 a `approve --signature`. Para revisar una fase de un caso firmado, el registro externo incluye la clave pública del revisor en `phase_reviewers`; este obtiene `phase-review-challenge` y entrega su firma a `review-phase --signature` antes de `advance`. Cada test `signed` requiere además un reporte de ejecución firmado por una clave distinta en `test_executors`, mediante `test-execution-challenge` y `record-test-execution`; una revisión histórica sin firma o un `passed:true` declarado no habilitan por sí solos una fase. Un caso nuevo puede activar `--test-gate-policy signed_observed`: exige pines de ejecutable e insumos, una repetición local y un recibo firmado por `observer:*`, comprobado de nuevo al releer los bytes conservados. El runner `organon run RUTA --manifest ARCHIVO.json --actor ACTOR` aplica pasos declarados, permite borradores de ramas independientes y detiene el avance ante decisiones o contradicciones; se reanuda con el mismo manifiesto. El esquema, ejemplos y semántica de checkpoint están en [workflow_operativo.md](docs/workflow_operativo.md); los 24 comandos, el flujo de aprobación, revisión y test, el anclaje externo opcional del ledger y el transporte MCP están en [interfaces.md](docs/interfaces.md).

Para conectar un cliente MCP stdio, usa `uv run organon-mcp` (o el ejecutable instalado). Fija `ORGANON_ROOT` a un directorio existente para limitar los casos accesibles al servidor. Las 24 herramientas publicadas son `init`, `put`, `status`, `report`, `review`, `retire_indicator`, `approval_challenge`, `approve`, `test_execution_challenge`, `record_test_execution`, `test_observation_challenge`, `record_test_observation`, `field_attestation_challenge`, `attest_field`, `challenge`, `resolve_challenge`, `gate`, `phase_review_challenge`, `review_phase`, `advance`, `trace`, `next_task`, `run` y `audit_lot_journal`. La CLI y MCP comparten motor, ledger, runner y auditor. El [diario incremental de lotes](docs/diario_lotes.md) audita masas húmedas/secas declaradas sin crear un caso ni autenticar observaciones. Las herramientas de declaración de campo registran una firma de un evaluador externo sobre fuentes; esa firma **no** libera un veredicto de impacto real. [Contrato y límite](docs/interfaces.md#declaración-firmada-de-fuentes-de-campo).

## Artefactos y evidencia

- [Antecedentes](docs/antecedentes.md), [tres alternativas y resultados negativos](docs/alternativas.md), [prototipos ejecutables](prototypes/), [decisiones](docs/decisiones.md) y [protocolo prospectivo de comparación](docs/protocolo_experimental.md). La [preparación ejecutable de la matriz](docs/preparacion_matriz.md) genera calendarios candidatos, verifica archivos, comprueba firmas, audita recibos y juicios declarados, enlaza puntuaciones ciegas con corridas y calcula métricas secundarias e intervalos pareados **sobre declaraciones** sin evaluar el criterio 4. La [preparación de campo](docs/preparacion_campo.md) coteja flujos alimentarios declarados; su esquema 3 opcional acota masa con etapas completas por consumo sin atribuir impacto. Un [cotejo de diseño](scripts/audit_field_trial_design.py) compara un plan candidato con grupos, brazos, estratos y ventanas y, opcionalmente, un manifiesto de presencia semanal declarada; no autentica asignación, prerregistro ni mediciones. El [auditor aritmético](scripts/audit_field_effect_analysis.py) recalcula `V`, `G` sin ajuste y comparaciones descriptivas de perjuicios; su esquema 2 añade un [candidato ajustado reproducible](scripts/analyze_field_adjusted_candidate.py) con intervalo percentilar nominal y datos basales declarados. Siempre deja la decisión de campo pendiente. El [panel de modelos](docs/panel_modelos_preliminar.md) aún no está congelado.
- [Investigación del mango](docs/caso_alimentos_investigacion.md), [fuentes públicas candidatas y sus vacíos](docs/caso_alimentos_fuentes_candidatas.md), [tres cargas publicadas separadas](cases/mango/fao_table15_loads.json), [caso documental versionado](cases/mango/organon.json) y [seed reproducible](cases/mango/seed.json). Las cifras de FAO provienen de un estudio de 2016; el caso conserva una inconsistencia aritmética publicada como control negativo. El [análisis abierto del comedor escolar](cases/school_waste/README.md) añade residuos diarios observados cerca del consumo, con un plan previo y anomalías conservadas; no demuestra impacto causal ni la cadena completa. No hay medición propia hasta consumo ni piloto de campo.
- [Segundo dominio](docs/segundo_caso_desarrollo.md): disponibilidad de estaciones Citi Bike. Su demostración documental de transferencia se informa por separado de cualquier comparación confirmatoria. La [sonda de recuperación de marzo](scripts/probe_citibike_march_crash_recovery.py) ensaya un `SIGKILL` tras el ítem 16 y reanuda el caso público expuesto por MCP; los [recibos](experiments/development/citibike_march_crash_recovery_2026-09-28/) conservan las ejecuciones instaladas en Python 3.11 y 3.12. Sigue siendo evidencia de desarrollo, sin caso reservado ni impacto de campo.
- [Prueba multiagente](docs/prueba_multiagente.md): autor y revisor nativos recorrieron las nueve fases de una fixture. Una ronda de escritores falló por conflicto de revisión; la siguiente, con reintentos, conservó 80 ítems disjuntos y mostró 487 098 218 ns de actividad solapada, sin demostrar ventaja de tiempo, calidad o coste.
- [Tests](tests/) de invalidación, contradicciones, gates, cliente MCP real, runner, concurrencia e interrupción por `SIGKILL`; la fixture [synthetic_full.json](workflows/synthetic_full.json) no es evidencia empírica.

El ledger enlaza eventos mediante hashes, escribe de forma atómica y rechaza revisiones concurrentes obsoletas. Las firmas demuestran control de las claves públicas configuradas y atan la aprobación o revisión al UUID, ruta y metadatos del caso, la cabeza previa del ledger y el contenido exacto firmado. La identidad humana, custodia de clave, competencia e independencia real se verifican fuera del toolkit. Una clave ausente o revocada, una ruta distinta o metadatos alterados vuelven la firma no verificada al releer el ledger y bloquean las compuertas que la requieren. Los hashes de eventos no garantizan que el ledger sea append-only frente a alguien con escritura directa: puede borrar eventos o restaurar un prefijo firmado válido y recalcular la cadena. El verificador opcional de `ORGANON_LEDGER_ANCHORS_FILE` compara cada lectura con una cabeza externa exacta, pero requiere que un custodio independiente valide y actualice el registro tras **cada** transición legítima. Ninguna clave privada debe entrar en este repositorio, comandos o logs. El gate puede exigir estructura de medición y umbral previo; la autenticidad de fuentes, atribución causal y daños reales requieren revisión y datos externos.

## Candidata dev5: recuperación del control Docker

Dev5 mantiene las nueve fases y sus cuotas. Guarda un intento y un nonce antes
de crear el contenedor; tras una respuesta perdida solo adopta el contenedor
exacto con prueba de que nunca arrancó. Un intento incierto nunca autoriza
volver a crear. La política de transporte pasa a schema5 y rechaza reanudar
raíces schema4. El cierre de ingeniería verifica 328 controles locales y 328 del wheel
instalado, 31 módulos coincidentes por SHA, CLI/MCP24 y tres controles Docker
reales con pérdida de respuesta inyectada; no son generaciones de software ni
una reproducción del timeout natural. La validación del wheel instalado se
registra por separado en el recibo de ingeniería.

La cohorte dev4 sigue con fuentes congeladas: al corte 03:43 UTC del 6 de
octubre había seis intentos cerrados, dos entregas completas (LedgerFold y
TopoPlan) y cuatro fallos. Su umbral de 9/10 ya no puede alcanzarse. El observador verificó
las 45 fuentes y los recibos físicos sin nuevas llamadas a modelos o pruebas.
La superioridad frente a libre y SDD sigue pendiente.

[Recibo final de ingeniería dev5](goals/method-superiority-v1/evidence/docker-create-recovery-01/engineering-receipt.json) y [fuentes, fallos y límites](goals/method-superiority-v1/evidence/docker-create-recovery-01/README.md). Dev5 no tiene aún una cohorte nativa. El [diseño de comparadores sólidos libre y SDD](goals/method-superiority-v1/development/STRONG_COMPARATORS.md) es una propuesta pendiente de implementación, pruebas y registro; no acredita una comparación realizada.

**Corte histórico de admisión pública N/S dev7 acotada:** una revisión Gemini acepta exclusivamente [seis posiciones prospectivas N/S](goals/method-superiority-v1/evidence/neutral-native-admission-01/pilot-plan.json), tres tipos y sin reemplazos. El driver original se inició según su checkpoint; en ese corte los resultados del piloto estaban pendientes. [Admisión y alcance](goals/method-superiority-v1/evidence/neutral-native-admission-01/admission-review.json) y [preflight corregido](goals/method-superiority-v1/evidence/neutral-native-admission-01/README.md) conservan el fallo inicial, la imagen local nueva y recibos reales del puente. No es congelación completa, competencia ni superioridad. El registro está vinculado al checkout/runtime originales y no puede continuarse desde un clon de main. En aquel hito la web conservó su corte anterior pre-piloto; no se redeployó entonces. La integración común T sigue siendo diseño futuro pendiente.

**Corte documental parcial del piloto público dev7, report-01:** dos posiciones cerradas failed de seis fijadas (N/S RangeAudit); ambas pasaron115/115 públicos pero sin auditoríaD/Gfinal ni paquete común. Las otras cuatro no tienen resultado en este corte, no es monitor vivo. [Corte y límites](goals/method-superiority-v1/evidence/neutral-native-pilot-dev7-01/README.md), [informe original](goals/method-superiority-v1/evidence/neutral-native-pilot-dev7-01/report-01.stdout), [diagnóstico](goals/method-superiority-v1/evidence/neutral-native-pilot-dev7-01/first-request-diagnostic.json) y [web](https://specorganon.stevenvallejo.com/#piloto-dev7). Fallo común exactrequestbudget131968>110000bytes, sin retry ni ampliarcuotas. No competencia ni superioridad; mantener intentos originales y corregir prospectivamente en otra versión/registro.
