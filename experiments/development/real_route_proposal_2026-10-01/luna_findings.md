# Aporte interno acotado de Luna

El explorer nativo `/root/d119_next_measurement_intake`, con modelo interno
solicitado `gpt-6-luna`, realizó dos lecturas de código. No ejecutó celdas,
proveedores ni herramientas de participante y no cambió archivos.

1. Inventarió schema de preparación, ruta fixture de `step`, declaración de
   versión/effort, igualdad de modelo servido, topes, cache/usage y endpoint de
   conteo. Root cotejó esas diferencias con fuentes actuales y documentación
   oficial; el revisor independiente confirmó los gates concretos.
2. Comprobó una duda sobre reinicio de límites entre épocas:
   `managed_coordinated_prototype.py` conserva `turns` por rol, lo valida al
   cargar y lo incrementa por respuesta; al iniciar otra época reinicia
   `finished`, no `turns`. Localizadores: líneas 355, 530 y 732 de la fuente
   preservada. Así 32+32+32+1 es la suma de topes persistentes del perfil;
   el forecast conserva la envolvente preventiva global de 128 solicitudes.

No es una ejecución de desarrollo R1, una comparación de calidad de modelos,
telemetría de Responses ni prueba de snapshot/effort/factura de un proveedor.
La integración y el veredicto local permanecen en root y el revisor. La
elección de modelo experimental sigue pendiente, independiente de este uso
de Luna como apoyo para inventarios delimitados.
