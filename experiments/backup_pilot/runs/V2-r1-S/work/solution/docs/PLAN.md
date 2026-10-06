# Plan de construcción y adaptación V2

## Etapa dos: plan previo a la adaptación

1. Leer íntegramente contrato actualizado y AGENTS; conservar contrato y AC01–AC14.
2. Especificar AC15–AC18, decisiones sobre N y trazabilidad antes del código.
3. Ejecutar la suite existente como línea base y conservar comando/resultado.
4. Añadir validación CLI del límite opcional y conteo de todos los regulares.
5. Bajo bloqueo: limpiar huérfanos, comprobar tamaño previo y tamaño completo
   preparado; rechazar con limpieza antes del rename si supera N.
6. Ampliar pruebas con límites exactos, metadata, rechazos repetidos, versiones
   sucesivas, temporales, SIGKILL y concurrencia; mantener suite anterior.
7. Ejecutar suite completa y ejemplos CLI reproducibles con Python 3.12;
   revisar resultados y documentar implementación, verificación y README.

## Plan de la etapa inicial (conservado como trazabilidad)

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
