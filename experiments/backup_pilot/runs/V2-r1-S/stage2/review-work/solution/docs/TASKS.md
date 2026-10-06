# Tareas y trazabilidad

Estado inicial: criterios y plan fijados antes del código.

| Tarea | Criterios | Estado inicial |
| --- | --- | --- |
| T01: CLI, validación de ID/rutas y errores | AC01, AC04–AC07 | Pendiente |
| T02: inventario, copia y manifiesto | AC02, AC03, AC09, AC12, AC13 | Pendiente |
| T03: publicación atómica y recuperación | AC04, AC10, AC14 | Pendiente |
| T04: verify, restore y list | AC01, AC08, AC09, AC11–AC14 | Pendiente |
| T05: pruebas propias y ejemplos V2 | AC01–AC14 | Pendiente |
| T06: README, implementación y evidencia | Todos | Pendiente |

## Adaptación de etapa dos (registrada antes del código)

| Tarea | Criterios | Estado inicial |
| --- | --- | --- |
| T07: especificación, plan y pruebas previstas para límite | AC15–AC18 | Completada antes del código |
| T08: validar N, contar repo y rechazar antes de publicar | AC15–AC17 | Pendiente |
| T09: ampliar pruebas y conservar las anteriores | AC01–AC18 | Pendiente |
| T10: ejecutar suite, ejemplos, completar documentos y entrega | Todos | Pendiente |

## Estado final

| Tarea | Estado final | Evidencia |
| --- | --- | --- |
| T01–T04: interfaz, snapshots, integridad, recuperación | Completadas y revisadas | `backup.py`, suite anterior conservada en `tests/test_backup.py` |
| T05: pruebas y ejemplos V2 | Completada | `tests/results-v2.log`, `tests/examples-v2.log` |
| T06: documentación inicial y entrega | Completada, adaptada al cambio | `README.md`, `docs/IMPLEMENTATION.md`, `docs/VERIFICATION.md` |
| T07: derivar especificación/plan de etapa dos | Completada antes del código | AC15–AC18 en `SPECIFICATION.md`, plan de etapa dos |
| T08: límite opcional, conteo y rechazo con limpieza | Completada | `nonnegative_bytes`, `repository_bytes`, `create_snapshot` |
| T09: ampliar pruebas preservando garantías | Completada | 26 casos: 25 pasan y uno omitido por bind EPERM |
| T10: ejecutar, registrar y entregar | Completada | Registros de comandos/resultados y verificación final del contrato |

La omisión del socket es una limitación del entorno de prueba documentada;
las comprobaciones reales de FIFO en fuente, snapshot y destino pasan.
No queda una tarea de implementación pendiente ni se espera revisión externa
para completar esta etapa.
