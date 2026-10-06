# Plan de entrega — V3

1. Leer el contrato completo actualizado y fijar C01–C11; preservar C01–C09.
2. Implementar CLI, validación de rutas y tipos mediante descriptores, y
   operaciones de repositorio bloqueadas. Cubrir C01, C04, C05 y C06.
3. Implementar copia, manifiesto/sello, publicación atómica y limpieza de
   temporales abandonados. Cubrir C02, C03, C07 y C08.
4. Implementar verificación completa, listado y restauración mediante temporal.
   Cubrir C03, C07 y C09.
5. Añadir el argumento opcional y conteo de todos los archivos regulares bajo
   bloqueo, antes de copiar y antes de publicar; limpiar el temporal al rechazar.
   Cubrir C10 y C11 sin cambiar el formato de snapshots existentes.
6. Escribir pruebas propias por criterio, ejecutar ejemplos reales y una prueba
   de interrupción por SIGKILL, conservar comandos/salidas y corregir defectos.
7. Completar README, diseño, matriz de trazabilidad y estado de tareas;
   comprobar Python 3.12 y que el contrato no ha cambiado.

No se necesitan dependencias, internet, credenciales, otras soluciones ni
intervención humana. No se usarán agentes adicionales. Cualquier cambio de
alcance se reflejará aquí, en SPEC y en TASKS antes de implementarlo. El cambio
de presupuesto ya se refleja en estos documentos; no requiere intervención.
