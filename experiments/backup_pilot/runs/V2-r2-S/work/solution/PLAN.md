# Plan de entrega — V2

1. Fijar especificación y criterios trazables antes del código.
2. Implementar validación de rutas, inventario y formato de snapshot.
3. Implementar create con hashes, sincronización y publicación atómica.
4. Implementar verify y list con validación estricta del formato/datos.
5. Implementar restore mediante preparación, comprobación y publicación.
6. Ejecutar ejemplo V2 y pruebas funcionales, de protección, corrupción e interrupción; conservar comandos y salidas.
7. Revisar código y documentar uso, formato, límites y resultados.

La implementación no requiere deduplicación. Se privilegian aislamiento entre versiones y comprobaciones explícitas de integridad. Cualquier ajuste de diseño se registra en IMPLEMENTATION.md y las tareas correspondientes.

## Adaptación al contrato actualizado (etapa dos)

8. Derivar C12–C15 y documentar reglas de presupuesto antes del código.
9. Añadir validación de `--max-bytes`, suma de archivos regulares y controles
   antes de escribir y antes de publicar, conservando limpieza y atomicidad.
10. Adaptar el ejemplo V2 y añadir pruebas de límites exactos, metadata, todos
    los bytes preexistentes, rechazo sin residuo y repetición tras interrupción.
11. Ejecutar suite completa y ejemplo, registrar comandos, salidas y códigos;
    revisar invariantes y completar README, tareas, implementación y verificación.

El contrato permanece intacto. No hay consultas ni resultados de evaluación externa.
