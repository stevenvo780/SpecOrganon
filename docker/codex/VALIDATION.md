# Revisión y validación — 2026-10-03

## Alcance

Revisión de empaquetado, CLI, servidor MCP, confinamiento de rutas, workflow local,
autenticación de Codex y pruebas existentes. Entorno Docker Linux/amd64 con
Python 3.12.15, Codex CLI 0.160.0, uv 0.12.22 y MCP SDK 2.2.0.

## Resultados observados

- `docker compose build`: imagen `specorganon-codex:local` construida; wheel instalado
  con dependencias fijadas por `uv.lock`.
- `docker compose run --rm -T codex codex mcp list --json`: servidor `specorganon`
  habilitado, stdio, raíz `/workspace` y tiempos de espera configurados.
- `python /opt/codex-lab/smoke.py` dentro del contenedor: pasa. Descubre 24 herramientas,
  crea un caso local y tres artefactos enlazados, consulta estado/compuerta/informe/
  siguiente tarea, rechaza actualización obsoleta y ruta externa sin mutación,
  recupera el estado al reiniciar y verifica paridad CLI/MCP. Landlock permanece
  activado con seccomp predeterminado, usuario sin privilegios y capabilities vacías.
  Recibo en el volumen: `/workspace/results/mcp-smoke-4327b7eef83f40cbb316c2e93385e399.json`.
- `python /opt/specorganon/scripts/clean_smoke.py /opt/specorganon`: pasa sobre el wheel
  instalado. 24 herramientas descubiertas, 15 operaciones CLI/MCP, 29 artefactos,
  nueve fases sintéticas, replay, recuperación de SIGKILL, firmas sintéticas y
  revocación. La prueba habilita fixtures únicamente en sus procesos hijos.
- Tests del núcleo dentro de Docker: **94 passed, 46 subtests passed**, 14.24 s.
  Comando reproducible:

```sh
docker compose run --rm -T codex python -m pytest -q -p no:cacheprovider \
  /opt/specorganon/tests/test_local_workflow.py \
  /opt/specorganon/tests/test_ledger.py \
  /opt/specorganon/tests/test_runner.py \
  /opt/specorganon/tests/test_runner_manifest_schema.py \
  /opt/specorganon/tests/test_mcp_strict_json_boundary.py \
  /opt/specorganon/tests/test_approval_security.py
```

## Hallazgo previo del proyecto

La suite completa en el host no queda validada. La ejecución inicial se interrumpió
tras múltiples fallos; una repetición con `-x --tb=short` aisló el primero después
de 279 tests y cuatro subtests pasados:

```text
tests/test_audit_bread_sources.py::test_real_archives_and_reserialized_transcriptions_are_verified
SourceAuditError: extractor bytes differ from reviewed digest
```

`src/specorganon/source_passages.py` fija un hash específico de
`/usr/bin/pdftotext`. El binario instalado en este host difiere de ese pin.
El contrato rechaza correctamente el extractor no revisado, pero los tests
que dependen de esa instalación no son portables automáticamente. No se alteró
el pin ni se afirma que ese único hallazgo explique todos los fallos restantes.
La imagen del laboratorio no incorpora históricos de casos/experimentos ni el
extractor PDF revisado; valida la integración y el núcleo seleccionado.

## Prueba con inferencia real de Codex

El operador inició sesión con ChatGPT en el volumen del laboratorio. La primera
prueba real terminó con código 0 en Codex, pero el verificador la rechazó: las
nueve llamadas requerían aprobación y `approval_policy="never"` las bloqueó.
Se conserva el recibo adverso en
`/workspace/results/codex-trial-0f22c2f8905b43de9c90a2ce19e75145/receipt.json`.

Se corrigió `trial.py` para limitar el catálogo a sus siete herramientas necesarias
y configurar `tools.<tool>.approval_mode="approve"` solo durante ese comando.
La configuración de las sesiones interactivas permanece intacta. La política por
herramienta está documentada en [MCP en Codex](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

La repetición **pasó**: nueve llamadas MCP exitosas (`init`, tres `put`, `status`,
`gate`, `trace`, `next_task`, `report`), siete herramientas distintas, tres
artefactos persistidos y frame pendiente de revisión independiente. El recibo
registra código de retorno 0, ausencia de timeout, argumentos y hash del JSONL.
Resultados en el volumen:

- `/workspace/results/codex-trial-8e5f7a7d1e1a460cb48e0349f521441c/receipt.json`
- `/workspace/results/codex-trial-8e5f7a7d1e1a460cb48e0349f521441c/events.jsonl`
- `/workspace/cases/codex-trial-8e5f7a7d1e1a460cb48e0349f521441c/organon.json`

Se exportaron ambos intentos y el ledger al host bajo
`experiment-runs/docker-codex-20261003/`, ignorado por Git. La exportación no
incluye el volumen de autenticación.

Las pruebas de transporte y las fixtures no prueban impacto de campo, eficacia
del método ni revisión humana independiente.
