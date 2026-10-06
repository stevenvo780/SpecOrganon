# Plan de entrega V1

1. Derivar criterios del contrato y fijar formato e invariantes en SPEC.md.
2. Implementar helpers de rutas/tipos, inventario, hash y esquema (C05, C08).
3. Implementar create y publicación atómica (C02, C03, C04, C06, C09).
4. Implementar verify, restore privado y list (C01, C07, C08, C10).
5. Construir pruebas de integración con procesos CLI y datos sintéticos:
   roundtrip, rechazos, corrupción, preservación e interrupción real con SIGKILL.
6. Ejecutar ejemplo y suite con Python 3.12; conservar comandos, salida y códigos.
7. Revisar trazabilidad, documentar implementación/limitaciones y cerrar tareas.

No se modifica CONTRACT.md; no se usan red, dependencias ni datos externos.
No se requiere intervención humana. La evaluación externa ocurre después.

## Plan ajustado: límite global de bytes

8. Derivar C12–C15 y actualizar decisiones antes de tocar la implementación.
9. Añadir parsing decimal no negativo, medición st_size del árbol completo,
   bloqueo de create, limpieza de staging abandonado y comprobación previa
   a publicar. Mantener formato/JSON y garantías C01–C11.
10. Adaptar pruebas: capacidades exactas e insuficientes, metadata de fuente
    vacía, snapshots previos, restos de interrupción, rechazo sin crecimiento,
    argumentos inválidos y dos creaciones concurrentes bajo presupuesto global.
11. Ejecutar toda la regresión y ejemplos; guardar comandos, resultados y
    restricciones del entorno. Completar README y documentos de implementación
    y verificación con trazabilidad C01–C15.
12. Ajuste de verificación del entorno: tras comprobar que mknod(S_IFSOCK)
    está permitido, usar ese inode real para el caso de socket cuando bind
    falla. Conservar la primera corrida y repetir la suite por ese cambio.
