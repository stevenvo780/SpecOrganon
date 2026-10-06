# Autonomía N v2: implementación parcial dev7

Este snapshot verifica ingeniería del controlador libre durable, su integración
al driver instalado N/S y los canales CLI/MCP. No mide competencia del método,
no admite sujetos nativos y no demuestra superioridad.

`engineering-receipt.json` resume resultados y límites. `source-review-01.json`
fija las 13 fuentes entregadas a la revisión estática independiente.
`review-source-check-01.json` confirma que seguían iguales al cerrar la revisión;
`review-source-current-01.json` conserva la única modificación posterior: mover
el contador de un test antes de su aserción deliberadamente fallida. Las fuentes
de producción no cambiaron. `current-installation-source-check-01.json` compara
los 40 módulos actuales con wheel, imagen de release e imagen Codex.

## Pruebas y fallos conservados

`tests-01.*`: 56 passed / 1 failed. El fixture de crash se activaba también al
reconstruir un resultado anterior, antes de la medida que pretendía interrumpir.
Se restringió la inyección al stage measure y se exigió su resultado cerrado.
`tests-02.*`: 186 passed en ocho archivos afectados; no es el suite completo.

`docker-01.*`: 19 passed / 1 failed en 20 controles. El contador estaba después
de una aserción que debía fallar en el primer intento, por lo que no contaba esa
medida real fallida. `docker-tests-submitted-01.py` conserva el test original.
`docker-02.*`: se repitieron únicamente los tres nuevos controles afectados:
3 passed, incluida reparación con la misma batería y recuperación sin volver
a medir. Los otros 17 controles aprobados no se repitieron. No sumar estas
corridas ni declarar 20/20 en un snapshot nuevo.

`docker-01-raw/` y `docker-02-raw/` conservan archivos regulares de los journals,
solicitudes, recibos y resultados, incluidos fallos; sus índices declaran SHA256,
bytes y symlinks excluidos. Son autores/revisores sintéticos con ejecución propia
real y offline. Las imágenes mecánicas son las históricas fijadas en los tests,
no las nuevas imágenes instaladas dev7.

## Instalación verificada

`install_runtime.py` construye wheel y entorno privado con dependencias del lock.
`probe_installed.py` comprueba inventario, consola y cinco guards. `probe_mcp.py`
comprueba un caso sintético, 24 herramientas, rechazos, persistencia y paridad CLI.
El plan `report-only-plan-01.json` es una prueba de registro schema 2 y reporte:
su runtime nunca se creó ni se ejecutó. `source_commit` refiere al HEAD previo;
los SHA del plan fijan las fuentes dev7 entonces sin commit. No usar este plan
para una campaña ni presentarlo como freeze. Solo contiene rutas y digests de
perfiles; no se copiaron credenciales.

`probe_docker_installed.py` y `probe_codex_installed.py` verifican byte a byte los
40 módulos, CLI y MCP en las imágenes reales dev7. Corren sin red, con filesystem
read-only, sin capacidades y con workspace sintético privado. El laboratorio
Codex verifica además `codex-cli 0.160.0`; omite el entrypoint de login y no monta
el volumen autenticado. Recibos `docker-installed-receipt-01.json` y
`docker-codex-installed-receipt-01.json` fijan identidades y comandos. Wheel y
ambas imágenes son locales; no se publicó un release ni se subieron a un registro.
`local-install/` está ignorado: contiene venv, wheel y workspaces privados.

## Reproducción seleccionada

Desde la raíz del checkout:

```bash
uv run --frozen --extra dev python -m pytest tests/test_neutral_autonomy.py tests/test_free_control_policy.py tests/test_neutral_controller.py tests/test_neutral_pilot.py tests/test_neutral_snapshot_guards.py tests/test_staged_review_regressions.py tests/test_closed_native_role.py tests/test_native_invocation_consistency.py -q
SPECORGANON_AUTONOMY_DOCKER=1 uv run --frozen --extra dev python -m pytest tests/test_neutral_autonomy_docker.py -q
```

Consultar `tests-02.command.json` y `docker-02.command.json` para argv y entorno
observados; scripts de instalación/probe fijan sus rutas y prerrequisitos locales.
Los logs de build e instalación son evidencia de ejecución, no un benchmark.
La revisión `code-review-01.json` usó Gemini 3.8 Flash, access=read, Kratos,
perfil configurado por defecto (cuenta exacta no devuelta), job
`380838baeec748cbaf5652505f28f7f7`, 395.6 s; no ejecutó tests ni admitió pilotos.

Pendientes: registro y admisión prospectiva de seis pilotos públicos N/S sin
reemplazos; T con D/G comunes y F externo; freeze completo y diez T propios con
>=9 completos; primaria reservada y réplica independiente. Nuevas generaciones
experimentales: cero. F, entrega completa común y superioridad: no medidos.
