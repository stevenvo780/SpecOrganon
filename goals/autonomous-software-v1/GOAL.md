# Goal: versión autónoma de SpecOrganon para software pequeño

Estado: hito local entregado y verificado, con comparación adversa y reparación
posterior de agregación documentada. Autorización: petición del dueño «crea una goal para lograrlo»,
2026-10-04. La goal nativa de este chat es la referencia de estado de ejecución.

## Resultado que se entregará

Una versión reproducible del toolkit que permita a agentes investigar, comparar,
construir y validar proyectos pequeños de software, con las nueve fases
justificadas, revisión técnica separada, pruebas reales registradas y una entrega
utilizable. Su aporte frente a trabajo libre y una guía SDD se evaluará con
criterios previos y casos nuevos; un resultado comparativo adverso se publicará.

Esta goal cierra un hito local de software. No sustituye el GOAL.md de la raíz,
la intervención alimentaria de campo ni una demostración general de la tesis.

## Orden y criterios de aceptación

| Fase | Trabajo | Evidencia necesaria para cerrar |
| --- | --- | --- |
| 1. Base técnica | Reproducir fallos, revisar el extractor fijado y establecer un entorno reproducible. No eliminar el control de integridad. | Recibos antes/después, pruebas pertinentes aprobadas, instalación limpia y revisión del cambio. |
| 2. Método operable | Investigar por qué faltaron vínculos, fases, recibos y README en el piloto. Comparar soluciones antes de implementar una. | Caso NUEVO con nueve fases justificadas y aceptación vigente; pruebas y recibos reales, README y revisión técnica de otro agente. |
| 3. Controles del método | Introducir una contradicción, evidencia insuficiente y un cambio de premisa. Probar interrupción y reanudación. | Rechazo verificable del avance injustificado, dependencias reabiertas y replay sin duplicados; historial íntegro. |
| 4. Comparación prospectiva | Preparar tareas nuevas reservadas de varios tipos, N/S/T, dos familias de modelos autorizadas y una ablación acotada. | Protocolo, rúbrica, presupuesto, repeticiones justificadas y regla de parada fijados antes de generar; separación física de solución y revisor/evaluador. |
| 5. Evaluación y transferencia | Ejecutar el plan sin sustituir fallos según resultados. Aplicar el toolkit a otro tipo de problema sin reconstruir el método. | Calidad, documentación, adherencia, trazabilidad, recuperación, intervención, tiempos y recursos con denominadores; veredictos positivos/adversos y límites explícitos. |
| 6. Release y publicación | Empaquetar, identificar versión, sincronizar documentación e integrar resultados en la web existente. | Fuentes versionadas, instalación limpia CLI/MCP, paquetes y hashes, instrucciones comprobadas, descarga y página pública verificadas. |

## Condiciones de ejecución

- Usar las cuentas y proveedores ya autorizados. No contratar servicios ni
  copiar credenciales, cambiar automáticamente de cuenta o reactivar proveedores
  retirados. Consultar cuotas actuales y catálogo antes de trabajo paralelo.
- Registrar antes del experimento los límites de llamadas, recursos y tiempo y
  qué costes pueden observarse. Uso no informado y coste desconocido permanecen
  desconocidos. Las cuotas inyectadas de septiembre no acreditan disponibilidad.
- No imponer un número grande de corridas sin justificar primero qué pregunta
  responden y qué recursos hay. Una fase de ingeniería y un estudio comparativo
  tienen criterios de cierre distintos.
- Mantener un solo escritor por archivo. Revisores técnicos locales diferentes
  del ejecutor leen evidencia y emiten juicio; etiquetas de actor diferentes no
  crean independencia. No forzar aceptación ni inventar firmas o aprobaciones.
- No hay intervención humana por corrida dentro del mandato técnico existente.
  Una nueva decisión normativa fuera de ese mandato o acceso al campo requiere
  su autorización y evidencia reales.
- No modificar los 30 inputs congelados, las entregas, los resultados o los
  ledgers del piloto de backups para mejorar su aceptación retrospectiva.
  Las nuevas fases usan directorios, casos y protocolos nuevos.
- No afirmar superioridad del método solo por más artefactos, llamadas MCP,
  hashes válidos, aceptación mecánica de fases o mejores puntuaciones de código.
- El cierre depende de entregar y evaluar el alcance definido, conservando
  veredictos adversos; no de repetir hasta conseguir una victoria.

## Línea base inicial

La comprobación ejecutada al activar esta goal reproduce los tres fallos
conocidos: `3 failed, 49 passed` en `tests/test_audit_bread_sources.py`, por
`extractor bytes differ from reviewed digest`.

Recibos: `evidence/source-audit-baseline.stdout` y
`evidence/source-audit-baseline.stderr`. Código de retorno real de pytest: 1.

SHA-256 del GOAL.md original al iniciar:
`e8341bea380cc357ad9e02ec4689a4ed47fe198ba06e4c98639f29264c314c36`.

Al iniciar, el siguiente trabajo era localizar la fijación y evidencia de revisión del extractor,
explicar la diferencia de bytes y decidir una reparación reproducible sin
debilitar el auditor. No se ha declarado reparado ni ejecutada una nueva campaña.


Cierre del hito local: [auditoría final](completion-audit-final.md) y
[criterios con recibo público](completion-audit-final.json). El informe primario
falló; su reparación complementaria y los resultados adversos están publicados.
La goal nativa del chat conserva el estado de ejecución definitivo.
