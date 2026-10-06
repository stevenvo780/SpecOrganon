# Tareas V1

- [x] T01 Leer AGENTS.md/CONTRACT.md; derivar C01–C11 y plan antes de código.
- [x] T02 Helpers y esquema: C05, C08, C11.
- [x] T03 Create y atomicidad: C02–C06, C09.
- [x] T04 Verify, restore, list y CLI: C01, C04, C07, C08, C10.
- [x] T05 Pruebas reproducibles de C01–C11 y ejemplo.
- [x] T06 Ejecutar, guardar resultados, corregir desviaciones y volver a verificar.
- [x] T07 README, implementación, matriz de evidencias y revisión de entrega.

## Cambio solicitado: --max-bytes

- [x] T08 Releer contrato actualizado completo y derivar C12–C15 antes de código.
- [x] T09 Implementar presupuesto global, bloqueo y recuperación de staging.
- [x] T10 Añadir pruebas C12–C15 y adaptar ejemplos sin perder regresión.
- [x] T11 Ejecutar verificaciones, conservar evidencias y registrar limitaciones.
- [x] T12 Completar documentación/README y comprobar contrato intacto.

Cambios de alcance: create acepta --max-bytes N. Las decisiones y criterios
ajustados figuran en SPEC.md y PLAN.md; se conserva el formato de snapshots.

- [x] T13 Derivar el ajuste para ejercer sockets mediante inode S_IFSOCK real
  cuando el contenedor prohíbe bind.
- [ ] T14 Ejecutar la prueba ajustada y actualizar las evidencias finales.

Primera corrida ajustada: 27 pruebas aprobadas y una omitida por restricción
AF_UNIX; se conserva como tests-max-bytes-initial.txt. No se requirió
intervención humana ni evaluación externa.
