# D113 — revisión independiente del aislamiento de análisis

Revisión de lectura sobre las fuentes congeladas en `c7979a8ccbd97fbbee939ea61ec4839eb8489b52`. No se ejecutaron proveedores, celdas del estudio ni pruebas adicionales durante esta revisión.

## Hallazgos de admisión, resueltos antes del freeze

1. **P2 — compatibilidad v1 de funciones.** La primera versión de `run_managed_tool_conversation.py` aceptaba varias funciones selladas con un calendario anterior a DEV v2. Una preparación directa podía ampliar el contrato histórico sin la opción nueva. La versión congelada exige exactamente una función fuera de DEV v2 (`:162-166`); el negativo `tests/test_isolated_development_analysis.py:263-279` exige rechazo sin crear el destino.
2. **P2 — compatibilidad v1 de política.** La primera versión permitía una política con perfil `analysis_readonly` junto a un calendario v1. La versión congelada exige política v1 para esos calendarios (`run_managed_tool_conversation.py:192-203`), y `prepare_development_round.py:323-337` coteja esquema, herramientas y perfiles antes de crear el intento. El negativo `tests/test_isolated_development_analysis.py:281-306` verifica ambos caminos.
3. **P2 — salida 79 del participante.** El launcher usaba 79 para su rechazo, aunque `os._exit(79)` del script del participante produce el mismo código y elude `except SystemExit`. La versión congelada clasifica cualquier código normal distinto de cero como `participant_failed` únicamente tras confirmar lanzamiento sellado, ausencia de timeout y bytes protegidos intactos (`staged_tool_session.py:1364-1398`). `tests/test_staged_tool_session.py:1560-1579` cubre `sys.exit(79)` y `os._exit(79)`, el consumo de la llamada y la reparación posterior en el mismo ledger. El código de salida, por sí solo, no autentica la causa; `contract_amendment.md` declara expresamente el posible rechazo transitorio del launcher etiquetado como fallo del participante.

No quedan P1/P2 confirmados en el código y los recibos revisados. Los intentos exploratorios negativos permanecen negativos: `integration_checks/attempt_01` registra cambio de fuente durante la integración y `attempt_02` conserva Ruff exit 1 sobre estilo de fixtures históricos, aunque su pytest focal terminó con exit 0.

## Evidencia final cotejada

- `source_freeze.json`: 49/49 rutas tienen tamaño, SHA-256 y bytes idénticos en el árbol actual y en `git show c7979a8:path`. `baseline_pins.json` separa 38 pines históricos.
- `integration_checks/final311/receipt.json`: `passed:true`, 48 fuentes copiadas iguales antes/después; Ruff, compilación y pytest con exit 0. Su stdout registra **470 passed** en 534,36 s.
- `integration_checks/final312/receipt.json`: `passed:true`, 41 fuentes copiadas iguales antes/después; los mismos tres controles con exit 0. Su stdout registra **178 passed** en 231,24 s.
- Para ambos gates cotejé cada copia `sources_before` contra su SHA/tamaño, los pines del freeze y los bytes actuales. También cotejé los SHA-256 de los seis streams por gate con sus archivos capturados: ninguna discrepancia.

La sesión comparte reservas, límites y journal entre herramienta de método y analizador. El sandbox de análisis sólo tiene raíces de lectura para `case`, `inputs` y `work`; el host revalida inventario y stdout JSON estricto antes de publicar `metrics.json`. Las pruebas focales cubren salida inválida, error normal, retiro de métricas anteriores, reanudación, mutación y restricciones de política. Esta evidencia prueba esas rutas mecánicas en los entornos locales probados, no la calidad de resultados de un agente real.

## Límites del dictamen

- La terminación por señal, timeout, fallo de lanzamiento y mutación bloquean. Una señal deliberada del participante no se distingue aquí de un límite del host; la recuperabilidad probada comprende códigos normales y JSON inválido.
- El verificador de contenido fija un contrato prospectivo de métricas D-F/D-E basado en fixtures públicos. No es evaluador genérico de todo programa o informe válido, ni una rúbrica Q. Antes de una ronda comparable, ese contrato común sin respuestas debe congelarse y entregarse por igual, sin ajustarlo después de observar resultados.
- El aislamiento Landlock/seccomp, los pines de bytes y la comparación de inventario no autentican el kernel, bibliotecas compartidas ni procesos del mismo UID. La política v2 de bajo nivel es capacidad explícita nueva; bridge/team conservan la admisión v1 estricta.
- Estos positivos son seis ejecuciones mecánicas de fixtures sobre fuentes públicas originales. No son las 24 celdas formales, no acreditan autoría/modelo, aprobación normativa o humana, custodia, campo, Q ni cumplimiento de C2–C5. C1 técnico permanece en el corte ya documentado.

**Veredicto:** sin defecto P1/P2 abierto para congelar este corte técnico; su uso en una ronda formal requiere resolver los límites de evaluación y autoridad anteriores.

## Verificación posterior del archivo de ejecución

Reabrí `archives/final_runtimes.tar.gz`: 15.223.334 bytes y SHA-256 `256b972e44db94ae3ecacaa2a5037e440e14ced3cc5aa633471465bbbd691a69`. Sus 4.483 miembros regulares son 4.482 blobs y `mapping.json`, sin nombres duplicados. Cotejé el contenido y el SHA de **todos** los blobs. El mapa contiene 34.280 registros de seis raíces (`final311`, `final312`, `exploratory01`, `exploratory02`, `cli311`, `cli312`): **27.610 archivos regulares** comparados byte a byte con sus originales, 6.343 directorios, 325 enlaces simbólicos y dos entradas no regulares conservadas sólo como metadatos. Para los regulares comprobé ancestros directorio, apertura final sin seguir enlaces, tamaño, SHA y contenido del blob. Ninguna discrepancia. Este archivo conserva contenido deduplicado y metadatos; el propio mapa declara `complete_session_restore_supported:false`, por lo que no certifica restauración íntegra de las sesiones.

`verified_traces.json` contiene 12 trazas, seis por intérprete, con D-F/D-E y A/B/C una vez por intérprete; reporta cero solicitudes a proveedor real y cero celdas formales. Cotejé para cada traza los SHA de `analysis.py`, `metrics.json` y el informe del verificador contra los archivos de su intento: 36/36 coinciden. Los cuatro recibos CLI de build/prepare (dos por intérprete) y el chequeo de artefactos tienen exit 0, `passed:true`, fuentes sin cambio y stdout/stderr cuyos SHA coinciden con los streams conservados. `cli_checks/artifact_verification.json` declara sólo estado `prepared`, 12 celdas preparadas por calendario y ninguna invocación de herramienta o proveedor. Son capturas mecánicas locales, no resultados de modelos.
