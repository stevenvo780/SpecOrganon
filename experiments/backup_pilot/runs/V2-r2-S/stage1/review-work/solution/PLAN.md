# Plan de entrega — V2

1. Fijar especificación y criterios trazables antes del código.
2. Implementar validación de rutas, inventario y formato de snapshot.
3. Implementar create con hashes, sincronización y publicación atómica.
4. Implementar verify y list con validación estricta del formato/datos.
5. Implementar restore mediante preparación, comprobación y publicación.
6. Ejecutar ejemplo V2 y pruebas funcionales, de protección, corrupción e interrupción; conservar comandos y salidas.
7. Revisar código y documentar uso, formato, límites y resultados.

La implementación no requiere deduplicación. Se privilegian aislamiento entre versiones y comprobaciones explícitas de integridad. Cualquier ajuste de diseño se registra en IMPLEMENTATION.md y las tareas correspondientes.

