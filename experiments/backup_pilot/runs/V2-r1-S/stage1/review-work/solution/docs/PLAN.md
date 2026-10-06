# Plan de construcción

1. Fijar criterios AC01–AC14 y el formato privado antes de implementar.
2. Implementar validación de rutas/tipos, CLI JSON y bloqueo del repositorio.
3. Implementar snapshots independientes, manifiestos y publicación atómica.
4. Implementar verificación exhaustiva, list y restore por temporal.
5. Construir pruebas trazables y ejecutar ejemplos V2 y fallos propios.
6. Revisar resultados, corregir fallos y registrar la entrega final.

No se modifica el contrato. No hay dependencias externas ni intervención humana.
Se priorizan integridad y conservación de datos sobre deduplicación/velocidad.

## Estrategia de verificación

Pruebas de caja negra mediante subprocess para la interfaz y filesystem temporal
dentro de `/trial`; inyección acotada de errores de copia en pruebas unitarias;
SIGKILL real durante create; comparación de inventarios y bytes para versiones
sucesivas. Los comandos y resultados exactos se conservan en `VERIFICATION.md`
y en los registros de `tests/`. La ejecución usa el Python 3.12 disponible.
