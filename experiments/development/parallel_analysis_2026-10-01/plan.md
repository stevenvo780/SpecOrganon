# D116 — análisis protegido en ramas privadas

Plan prospectivo escrito antes de implementar esta extensión. Base: D115,
`d27936cd1cd25c8ac2abacb6070f291655a983b5`. GOAL y protocolo no se modifican.

## Objetivo y alcance

Cerrar la diferencia entre el analizador D113 y las conversaciones privadas
D115: ejecutar el mismo launcher protegido, validar JSON finito, publicar o
retirar métricas desde el host, conservar provenance y permitir reparación por
`replace` CAS dentro del mismo ledger, claim, deadline y límite de herramientas.

Este perfil opt-in sigue recibiendo un grafo inicial del caller. Es un ensayo
mecánico de integración, no una preparación comparable ni una ejecución de las
24 celdas. El protocolo §2 no exige solo: esa restricción procede del compilador
D112. Encadenar un bootstrap separado con D115 reiniciaría los presupuestos y
queda prohibido como sustituto del runtime padre pendiente.

La preparación comparable requiere un perfil prospectivo distinto: fuentes y
contrato comunes; work vacío; líder que construye los nodos mediante `init` real;
un solo ledger/contexto/claim desde ese primer request hasta reviewer y merge;
coordinación explícita y comparable de líder, especialista y reviewer en A/B/C.
No se relabelan calendarios solo, no se aporta a C un seed exclusivo y no se
confunde selección de una wave con un workflow metodológico completo. R2 sólo
se prepara tras registrar y congelar las modificaciones justificadas por R1.

## Ownership y barrera

- Rama broker: `scripts/parallel_analysis_broker.py` y
  `tests/test_parallel_analysis_broker.py`. Manifest y receipts nuevos, helpers
  D113 reutilizados, replay cerrado y delta host permitido exclusivamente para
  `metrics.json`. Fuentes nuevas incluidas en el binding.
- Rama adapter/C: `scripts/managed_parallel_analysis.py`,
  `scripts/c_parallel_analysis.py` y sus tests. Inyección del broker en el
  engine D115, preparación/status opt-in y merge con métricas frescas/provenance.
- Root: dossier, integración HTTP/CLI, evidencia, estado y decisiones.
- Revisión independiente después de la barrera de implementación y validación.

Los escritores conservan cambios ajenos. Módulos originales D113/D115 y sus
contratos permanecen byte-idénticos. No se promete portabilidad de un runtime
que detecte cambios de su cierre de fuentes.

## Contrato nuevo

Manifest v2 identifica explícitamente el contrato del analizador D113; el
nombre `analysis_readonly` por sí solo no lo activa. Pin del launcher generado,
identidad y fuentes. Receipts distinguen inventarios reales `before`,
`after_child` y `after_host`. El participante no escribe en work; el host sólo
puede publicar, reemplazar o retirar `metrics.json` con provenance verificable.

Streams de análisis limitados explícitamente a 8 MiB; JSON de métricas a
128 KiB. V1 conserva 256 KiB y sus bytes. Fallo ordinario/JSON inválido retira
métricas anteriores y entrega feedback reparable. Señal, timeout, guard perdido,
fuentes modificadas o efectos sin receipt bloquean continuación/publicación.
Cambiar `analysis.py` vuelve obsoletas sus métricas anteriores; el merge no las
exporta como frescas. No se inventan inventarios ni SHA para ocultar el delta.

## Gates necesarios

1. Dos ramas privadas con análisis real, métricas canónicas, reconstrucción y
   replay; callback reviewer recibe artefactos públicos, sin razonamiento privado.
2. Fallo ordinario y JSON inválido seguido de reemplazo CAS y reparación bajo
   el mismo presupuesto global; análisis válido seguido de inválido retira métricas.
3. SHA/argumentos/CAS inválidos, JSON duplicado/no finito/UTF-8/exceso,
   mutación de launcher, streams, inventarios, provenance y métricas.
4. Timeout/señal/crash/guard perdido impiden publicar o reintentar efectos inciertos.
5. Merge sólo exporta métricas actuales vinculadas a branch, source y ordinal.
6. Gates proporcionales Python 3.11 y 3.12, Ruff, compilación y regresiones
   pertinentes D113/D115. Conservación explícita de módulos y dossiers previos.

Se preservan intentos fallidos y fuentes/streams de cada gate, se fija el cierre
de fuentes antes del gate final y se revisa el manifiesto final contra Git.
No se repiten suite global, instalación/wheel o campo por esta extensión local.

## Límites de evidencia

Sólo transportes sintéticos/local HTTP y herramientas reales revisadas; sin
credenciales, gasto de API, publicación externa ni intervención de campo.
No autentica modelo/esfuerzo/telemetría ni puntúa Q. C1 técnico D107 conserva su
evidencia; C2–C5 siguen No demostrado y celdas formales ejecutadas siguen 0/24.
La siguiente dependencia es el runtime padre comparable desde work vacío,
además de contrato/rúbrica sin respuestas, autorización y proveedores reales,
R1/R2, selección independiente, custodia y campo/transferencia reales.
