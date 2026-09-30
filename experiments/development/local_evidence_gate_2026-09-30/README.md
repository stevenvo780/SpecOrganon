# D-093: compuerta de evidencia archivada

Los [recibos de Python 3.11](python3.11.json) y [3.12](python3.12.json) proceden de un wheel construido e instalado sin red. La [sonda](../../../scripts/probe_local_evidence_gate.py) usa su CLI y un cliente MCP stdio real; copia los dos PDF públicos del caso del pan a un caso temporal y registra una revisión sintética de `frame` con Ed25519.

Cada ejecución conserva 19 ítems y 21 eventos. Alterar, borrar o sustituir por un symlink `source_lca.pdf` invalida ocho evidencias y diez dependientes; revoca la aceptación, rechaza `advance` y deja `run` esperando sin añadir eventos. El segundo PDF conserva su validez. Restituir los bytes originales recupera el estado completo y el replay no escribe. Los nueve pares de `status`/`gate` coinciden entre CLI y MCP.

El [recibo de verificación](receipt.json) liga los archivos fuente, el wheel y los recibos a sus hashes. Registra las pruebas focales y globales, la revisión independiente y la comparación de estado de los cinco casos versionados con el motor anterior. No contiene claves privadas, firmas, mensajes para firmar ni rutas temporales. Los casos, bundles y claves de la sonda son temporales; estos archivos son resúmenes reproducibles y no atestaciones bajo custodia independiente.

## Reproducción

Desde la raíz del repositorio, con `uv`, `ruff`, las dependencias en la caché offline de `uv` y Python 3.11 y 3.12 instalados:

```sh
uv run --offline --extra dev pytest -q tests/test_local_evidence_archive_gate.py tests/test_local_evidence_gate_installed.py
uv run --offline --extra dev pytest -q
ruff check .
```

La prueba instalada crea entornos nuevos, construye un wheel, ejecuta `uv pip check` y luego la sonda. Si falta un intérprete o dependencia offline, registra un skip explícito; en este corte ambas instalaciones se ejecutaron sin skips. También se puede ejecutar la sonda con el Python de un wheel ya instalado:

```sh
/ruta/al/entorno/bin/python scripts/probe_local_evidence_gate.py . --output /ruta/al/recibo.json
```

## Alcance

La sonda instalada acepta solo `frame` y modifica un PDF. La prueba focal cubre rutas inválidas, contrato parcial, enlaces, tipos no regulares, límite de 32 MiB e incompatibilidad de digests para una misma ruta. La revisión adversarial encontró que dos versiones de un archivo podían satisfacer por separado dos evidencias durante una sola consulta; el motor ahora bloquea esas declaraciones antes de leer, y la regresión comprueba cero lecturas.

El control verifica bytes locales. No juzga las afirmaciones del PDF, autentica su publicador, acredita identidad o competencia humana, establece custodia ni observa impacto de campo. No impide cambios posteriores por otro proceso del mismo UID. El auditor de contenido del pan conserva su función separada. No hubo llamadas a modelos ni gasto; los cinco criterios de GOAL permanecen **No demostrados**.
