# D119 preservation intake

Unión de los 62 registros de repositorio del `source_freeze.json` D118 y los
103 registros del `baseline_pins.json` D118: 125 rutas únicas; 40 aparecen en
ambos. No hubo pins contradictorios. Cada ruta existe y sus bytes y SHA-256
coinciden con el árbol actual y con
`0f57890b00f236c553cbf24ec6f97fe4fdff8f33`.

Método: unir los manifiestos por ruta y verificar tamaño/SHA-256 de los bytes
locales y del contenido de `git show <HEAD>:<ruta>`. Errores: ninguno; sin
rutas ausentes ni diferencias. El extractor externo separado del freeze no se
incluye como registro de repositorio.

Clasificación: `preservation_inventory_only`; celdas formales ejecutadas: 0.
Modelo solicitado: `gpt-6-luna/high`. Este inventario mecánico no es benchmark
ni evidencia de calidad, coste, tokens o identidad de proveedor.
