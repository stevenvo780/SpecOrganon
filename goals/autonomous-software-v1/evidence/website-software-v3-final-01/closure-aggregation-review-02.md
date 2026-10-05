### Dictamen: **ACCEPT**

**Metadatos de la revisión**:
- **Decisión**: `ACCEPT`
- **tests_executed**: `false` *(revisión estática/metodológica de código y especificación de datos; ejecución exit 0 reportada por el entorno)*
- **Alcance**: Companion de agregación posterior (`report-posthoc-v1.json`). **No** constituye cierre primario limpio del pipeline ni demuestra la tesis de campo/general.

---

### Análisis de Conformidad y Seguridad Metodológica

#### 1. Dualidad Estricta de Estados (`native_assertions` vs. `verified_status`)
- **Implementación**: El script mantiene íntegro el payload original del auditor (`audit`) dentro de `qualitative['native_assertions']`, sin mutar retroactivamente la aserción histórica.
- **Verificación**: En el bucle de auditoría (`points[group]`), cada aserción `pass` es sometida a `resolve(locator, request['documents'])`. Ante `EvidenceError`, el estado verificado (`verified_status`) se degrada a `fail` con score `0` bajo la regla de evidencia faltante pre-registrada, registrándose en `dual[group + '/' + identity]` y en el arreglo `invalid`.
- **Resultado en auditorías presentes**:
  - `cell01` y `cell06` (T), `cell07` y `cell15` (N): 0 errores de evidencia; aserciones auditadas preservadas.
  - `cell26` y `cell36` (N): Cada una con 1 locator inválido en `G/g4` (`public-streams-0.json#/stdout` vacío). El script registra `auditor_status: 'pass'`, `verified_status: 'fail'` y `score: 0`, neutralizando cualquier intento de imputación espuria.

#### 2. Conservación Rigurosa de Denominadores y Estratificación
- **Denominador de diseño**: Fijo en `design_denominator: 42` y `generation_cells: 42`. No se descartan celdas fallidas de la generación (36 celdas sin auditoría preservadas como `fail` o `inconclusive` según el snapshot de infraestructura).
- **Consistencia funcional**: Se verifica la suma exacta de 3500 filas (`sum(len(p['rows']) ...) == 3500`) y `len(outcomes) == len(recipes(row['task']))`.
- **Estructura de comparación**: `comparison_groups` se calcula sobre la totalidad de las 42 filas con los bloques intactos (`nst_blocks=12`, `a_blocks=6`), así como en los estratos por tarea y familia.
- **Métricas resultantes documentadas**: 2 paquetes completos para `T`, 0 para `N`, `S` y `A`. Medias funcionales (`N` 75%, `T` 16.67%, `S`/`A` 0%) sin victorias selectivas ni enmascaramiento por selección posterior.

#### 3. Aislamiento Posthoc y Preservación del Fallo Primario
- **Inexistencia de `report.json`**: Se asegura mediante `assert not target.exists() and not (run/'report.json').exists()` que el artefacto canónico primario no fue creado ni sobreescrito.
- **Rastro de auditoría y excepciones**: El objeto `aggregation` registra con total transparencia:
  - `original_report_exit_code: 1`
  - `original_report_present: False`
  - `original_exception: 'EvidenceError: empty evidence cannot support pass'`
  - `rule: 'missing evidence zero, registered before generation; exhaustive pass-locator verification'`
  - `scope: 'companion closure after native report failure; not a clean primary pipeline completion'`
  - `field_or_general_thesis_proven: False`

#### 4. Inmutabilidad Criptográfica de Fuentes y Ejecución Cero
- **Validación de hash**: Se valida `registration.sha == '0bc7182ab4713080db3120183e11ca45ad1f6f1ed752c856dc4028b24b728ed5'` tanto al inicio como al final.
- **Comprobación antes/después**: Se computan los digests SHA-256 de todos los ficheros de preparación, cuotas, progreso, snapshots terminales y deliveries (`before`), y se verifica `assert before == {str(p): digest(p.read_bytes()) for p in original_paths}` tras la agregación.
- **Cero llamadas secundarias**: Sin reinvocación de modelos, sin nuevos procesos de Subject ni repeticiones (`new_model_calls: 0`, `new_subject_calls: 0`).

---

### Conclusión
El script cumple exhaustivamente con todas las salvaguardas solicitadas: dualidad de estados sin pérdida histórica, aplicación estricta de la regla de evidencia faltante = 0, respeto total de denominadores pre-registrados, conservación de fallos originales e inmutabilidad de artefactos previos. El artefacto acompañante (`report-posthoc-v1.json`) es metodológicamente sólido y auditable.
