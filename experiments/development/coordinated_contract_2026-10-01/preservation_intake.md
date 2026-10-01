# D118 preservation intake

Unión de los `records` de `source_freeze.json` (D117, 55 registros) y
`baseline_pins.json` (D117, 90 registros): 103 rutas únicas, sin contradicciones.
Cada tamaño y SHA-256 coincide con los bytes actuales y con
`e2f76688ecd64d286f266d305d28fb256d377111`.

Método: parsear ambos manifiestos, unir por ruta, y cotejar tamaño/SHA-256 local
y el contenido de `git show <HEAD D117>:<ruta>`. Errores: ninguno; sin rutas
ausentes ni diferencias.

Alcance: inventario de preservación solamente. Celdas formales ejecutadas: 0.
No constituye evidencia de benchmark ni afirma calidad de modelo o coste.
