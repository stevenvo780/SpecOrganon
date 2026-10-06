# Plan V1 actualizado para --max-bytes

1. Fijar criterios y formato en SPEC.md antes de programar.
2. Conservar formato, validación, hashes, protección de destino y publicación
   atómica de la implementación existente; inspeccionar pruebas propias actuales.
3. Añadir argumento opcional y cómputo completo st_size. Serializar create,
   limpiar staging abandonado, rechazar antes de publicar y eliminar temporales
   al fallar. No agregar metadata persistente fuera de archivos regulares.
4. Adaptar y ampliar pruebas de CLI, límite exacto, metadata, datos ajenos,
   crecimiento residual, concurrencia e interrupción real. Volver a ejecutar
   todas las garantías base. Ampliar ejemplos reproducibles bajo /trial.
5. Ejecutar con Python 3.12, conservar comandos/resultados, cerrar trazabilidad
   y documentar formato, uso, decisiones y limitaciones en README.md.

No se consultarán otros proyectos, credenciales ni internet. No se instalarán
dependencias. La revisión posterior no es una dependencia de esta entrega.
