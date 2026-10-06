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
