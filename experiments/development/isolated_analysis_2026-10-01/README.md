# D113 — análisis aislado sobre los dos casos originales

Plan e5dd6fe; [precisiones prospectivas](contract_amendment.md); freeze de
fuentes **c7979a8ccbd97fbbee939ea61ec4839eb8489b52**,49pins. Se preservan
38pins de base: GOAL, protocolo, producción, wheel D107, core y datos originales.
Este corte añade capacidades preparatorias: **cero celdas formales, cero
solicitudes reales a proveedores, sin Q ni aprobación normativa humana**.

## Cambios

- Configuración optativa `schema:2,analysis_profile:"read_only_v1"`, calendario
  DEV2 y política2. Método y analizador tienen nombre/id/ejecutable/perfil
  distintos, comprobados antes de reserva, despacho y replay. Comparten sesión,
  claim, ledger y contadores. Bridge/team legacy exige una función/política1.
- `analysis_readonly` lee case/inputs/work, cero raíces de escritura. Ejecuta
  los bytes SHA fijados de work/analysis.py con argv `[analysis.py,case_dir]`,
  biblioteca estándar, sin fork/red. Host comprueba inventario protegido y
  publica metrics.json/procedencia SHA sólo tras objeto JSON estricto finito≤128KiB.
- Código no cero y JSON inválido consumen llamada y devuelven feedback.
  Raw stdout/stderr se conservan; Unicode inválido/exceso no contaminan contexto.
  replace CAS permite corregir un entregable con digest esperado y chunk≤8192B;
  append posterior también cuenta. No toca estados/métricas. Un análisis nuevo
  inválido retira métricas anteriores del host. Señal/timeout/launch/tamper bloquean.
- DEV2 fija prospectivamente hasta64tools/128requests iguales para A/B/C;
  tokens≤80k/tiempo≤5400s se conservan. V1 sigue16/32. No repone intentos abiertos.
- D-F conserva6 originales y añade38 derivados comunes: dos textos completos,
 35páginas y manifest separado con versión/hashes/licencias. Extractor/PDF se
  fijan por bytes; la extracción actual reproduce el texto archivado. D-E
  conserva3 originales. Cápsulas visibles no incluyen soluciones/código/reportes.
- D-E usa la fixture D099T exacta. D-F adapta NUEVAMENTE lectura de textos del
  script público D094B; [historia y hashes](fixtures/fixture_history.json).
  Originales/outputs históricos no se reparan; el oráculo no ejecuta participantes.

## Gates congelados

| Gate | Resultado |
| --- | --- |
| Python3.11, regresión proporcional de15 archivos | **470 passed**,534.36s |
| Python3.12, integración/perfiles/sesión/inputs/oráculo | **178 passed**,231.24s |
| Ruff/compile, ambos intérpretes | exit0, fuentes before/after idénticas |
| CLI real build + prepare D-F/A, ambos intérpretes | cuatro exit0, prepared; sin execute |
| D-F/D-E × A/B/C, cada intérprete | seis trazas de fixture verificadas independientemente |

[Capturas](integration_checks/), [CLI](cli_checks/artifact_verification.json),
[doce trazas](verified_traces.json), [evidencia](evidence.json) y
[revisión independiente](review.md). Se conservan comandos/tiempo/exit/streams
y copias exactas de fuentes. La selección3.12 difiere de3.11; no sumar como
suite global ni atribuir a un modelo experimental. Suite global/wheel no se repitieron.

Las seis trazas por intérprete usan herramientas locales reales y FakeTransport.
D-F:6tools/8requests falsos; D-E:3tools/5requests falsos. Mismo ledger entre
segmentos; norma N pending. Scripts calculan fuentes originales y el oráculo
coteja números/unidades/bases,1008intervalos,17claims y7filas/pasajes. No demuestra
que un modelo crease el programa, recorriera todo el método o mejorara Q.

[Archivo de runtimes](archives/final_runtimes.tar.gz):27610regulares/4482blobs,
15223334B, SHA256 `256b972e44db94ae3ecacaa2a5037e440e14ced3cc5aa633471465bbbd691a69`.
Incluye gates finales, dos exploratorios y dos preparaciones CLI. Root y revisor
reabrieron todos los blobs y cotejaron mappings con originales conservados.
Symlinks/no regulares sólo metadata, sin seguirlos; no es imagen completa ni
restaura sesiones. Cero nombres sensibles necesitaron exclusión.
[Captura](archive_checks/receipt.json).

## Negativos y alcance

- Integración01:17passed/2failed. Guard detectó edición durante segmento;
  otra fixture intentó segunda sesión sobre stage anclado. Raw/fuente previa
  preservados; se corrige preparación del test.
- Integración02:9passed/17deselected, compile0, **Ruff1** por estilo original
  de fixtures. No se modifican fixtures para lint. Gate final Ruff cubre
  implementación/tests/capturador; compile también incluye fixtures.
- Unidades conservan errores iniciales de replay/contrato. Tres P2 (functions
  legacy, policy legacy, salida79) cerrados antes del freeze. El índice inicial
  incluyó una traza legacy sin oráculo: [error/corrección](evidence_index_history.json)
  conservados sin alterar gates.
- Rechazo transitorio del launcher puede etiquetarse participant_failed;
  stderr se conserva y siguiente llamada revalida. Etiquetas no autentican
  runtime/modelo/persona. Sandbox local para código revisado: no contenedor,
  no garantía contra kernel/otro proceso hostil del UID. Imagen/dependencias
  dinámicas/modelo/tarifa/factura/custodia no autenticados.
- Oráculo fija nombres/unidades/bases de estas fixtures: **no validador genérico
  de cualquier output válido de tarea ni Q**. Antes de R1 real fijar/entregar a
  todas las ramas contrato común sin respuestas y rúbrica/evaluación independiente,
  antes de observar salidas. Adaptación argv/JSON D-E nueva; tarea histórica no la fija.

## Pendientes obligatorios

C1 técnico D107 permanece1/5; C2–C5 No demostrado. Faltan C paralelo bajo un
presupuesto común; contrato/rúbrica/modelo/ruta/telemetría/autorización operativos;
12reales R1→adaptación/freezeR2→12reales R2, selección de candidato; luego reserva
custodiada, panel confirmatorio, jueces/autoridades competentes, banco sellado,
intervención alimentaria causal y transferencia completa a problemas nuevos.
Preparar no autoriza gasto/campo. No cerrar GOAL con este corte.

## Reproducir sin proveedor

Comandos/configuración sintética/versiones exactos en [cli_checks](cli_checks/).
Para repetir con destinos nuevos y entornos compatibles:

```sh
python3 experiments/development/isolated_analysis_2026-10-01/capture_checks.py \
  nueva-captura --python /ruta/python3.11 --basetemp /ruta/privada/nuevo-temp \
  tests/test_isolated_development_analysis.py
```

El helper conserva fuentes/streams/hashes. El CLI preparador sólo construye y
prepara; estos comandos no llaman proveedores.
