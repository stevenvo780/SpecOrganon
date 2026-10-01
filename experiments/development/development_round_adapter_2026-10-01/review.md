# D112 — revisión independiente de código y evidencia

**Veredicto:** no queda un P1/P2 confirmado en el alcance preparatorio congelado en `1c3cbf49f64f5d8b74e696ea2da7b1714955217a`. Esta revisión no acredita ninguna de las 24 celdas formales, calidad de resultados ni aceptación humana.

## Hallazgos y cierres

1. **P2 de procedencia, cerrado antes del freeze.** El builder inicial copiaba los bytes públicos vivos y luego los declaraba originales; una alteración anterior a `build` podía convertirse en la nueva referencia. `scripts/prepare_development_round.py` fija ahora 12 SHA256 del commit `98a1403ea972f328a86a114f207716978fd98a98` y los comprueba antes de crear el destino y al copiar. Recalculé los 12 contra Git y los archivos actuales: coinciden. `tests/test_prepare_development_round.py::test_source_alteration_rejected_before_output` cubre CSV, core y protocolo alterados con salida ausente.
2. **P2 de límites por invocación directa, cerrado.** La preparación común de team y bridge valida contra el schedule DEV el perfil de precios exacto, el techo de costo y el de solicitudes antes de crear `run_dir`. La regresión de seis combinaciones precio/costo/solicitudes × team/bridge comprueba que no aparece directorio ni claim. DEV impide también presentar la corrida `solo` como relevo de roles. Estas guardas son por corrida; no constituyen presupuesto global del estudio.
3. **Incompatibilidad con sandbox, cerrada.** La llamada redundante a `fchmod` falló con `EPERM` en el intento exploratorio 02 y quedó preservada. La herramienta crea archivos modo `0600` y comprueba el modo mediante `fstat`; la prueba posterior ejecuta `init` y `write` dentro del sandbox real. No se aflojaron sus reglas.

## Comprobaciones independientes del freeze

- Los 9 archivos de `source_freeze.json` coinciden por bytes, tamaño y SHA256 con Git en `1c3cbf49…` y el árbol actual. Los 38 de `baseline_pins.json` coinciden con Git `98a1403…` y el árbol actual.
- Recalculé los SHA256 y tamaños de stdout/stderr y las 18 copias de fuente de cada gate final; las copias coinciden con Git y los archivos actuales. Las capturas registran `233 passed` en Python 3.11, `142 passed` en 3.12, y exit 0 en Ruff, compilación, diff y CLI fake.
- Reabrí ambos tar comprimidos y comprobé **484 blobs únicos y 825 asociaciones path→blob por entorno**, cada una contra SHA256, tamaño y archivo original retenido bajo `/tmp/specorganon-D112-final{311,312}`: cero discrepancias. El contenedor 3.12 anterior de 57 060 203 bytes sigue en la ruta de `archive_history.json` con tamaño y SHA256 correctos. Estos archivos no son una imagen restaurable de sesión.
- En las 12 trazas mecánicas retenidas, seis por Python, comprobé `mode` A/B/C, norma `N` pendiente, dos segmentos, ocho herramientas y diez solicitudes por traza. Cada ledger tiene diez solicitudes liquidadas, 150 tokens y 150 microUSD **sintéticos**. El CLI fake preparó 12 coordenadas y una tentativa `prepared` con cero solicitudes.

## Límites del veredicto

`review` y `advance` pueden producir aceptación **mecánica** de fases del prototipo; no representan autoridad humana. `approve` y `analyze` están rechazados. Faltan evaluación aislada del código del participante, acceso común a pasajes PDF y al CSV completo bajo el tope de herramientas, paralelismo real de C y resultados de R1 para adaptar R2. La ejecución usa proveedor falso: no verifica identidad de modelo, factura, presupuesto global de las 24 celdas, Q, custodia, normas aprobadas ni campo. El orden `development_unsequenced` no es una barrera prospectiva de ensayos formales. El riesgo residual de carreras de otro proceso con el mismo UID sigue siendo el límite de los controles puntuales de archivos, no una garantía de custodia externa.
