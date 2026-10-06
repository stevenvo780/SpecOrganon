# Procedencia de TopoPlan

Copia exacta de la entrega del intento06 de la cohorte pública nativa dev4,
registro923d5f1d6dac9b9271d1f311c5c714c848782e0bd40afe6f49ef87ba87552055.
El original conserva las nueve fases aceptadas,25 receipts de trabajos y
105/105 checks públicos independientes. El observador del corte03:43UTC
verificó package_gate, cierres y recibos físicos usando las45 fuentes congeladas.
Este ejemplo no es una nueva generación dev5 ni una comparación reservada.

El README es el documento original sellado en la etapa program; por eso su
último párrafo describe aquella etapa anterior a tests. Se conserva sin edición
para mantener el sello. test_topo_plan.py pertenece a la etapa posterior.

Uso local desde esta carpeta, Python3 sin dependencias:

```sh
python3 topo_plan.py <<'JSON'
{"nodes":["compilar","probar","publicar"],"edges":[["compilar","probar"],["probar","publicar"]]}
JSON
```

Los tests generados documentan las rutas del contenedor original. El programa
recibe stdin y emite stdout; no requiere aquellas rutas para el uso local.
outcome y outcome-closure son copias históricas y mantienen las referencias
absolutas del laboratorio. No se reinterpretaron ni se reescribieron receipts
para fingir una ejecución local. source-sha256 vincula los archivos copiados.
