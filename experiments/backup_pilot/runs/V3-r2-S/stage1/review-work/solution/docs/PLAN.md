# Plan de entrega — V3

1. Fijar especificación y criterios C01–C09 a partir del contrato.
2. Implementar CLI, validación de rutas y tipos mediante descriptores, y
   operaciones de repositorio bloqueadas. Cubrir C01, C04, C05 y C06.
3. Implementar copia, manifiesto/sello, publicación atómica y limpieza de
   temporales abandonados. Cubrir C02, C03, C07 y C08.
4. Implementar verificación completa, listado y restauración mediante temporal.
   Cubrir C03, C07 y C09.
5. Escribir pruebas propias por criterio, ejecutar ejemplos reales y una prueba
   de interrupción por SIGKILL, conservar comandos/salidas y corregir defectos.
6. Completar README, diseño, matriz de trazabilidad y estado de tareas;
   comprobar Python 3.12 y que el contrato no ha cambiado.

No se necesitan dependencias, internet, credenciales, otras soluciones ni
intervención humana. No se usarán agentes adicionales. Cualquier cambio de
alcance se reflejará aquí, en SPEC y en TASKS antes de implementarlo.
