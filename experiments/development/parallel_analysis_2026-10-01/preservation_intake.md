# D116 preservation intake

Inventario de preservación derivado de la unión de `source_freeze.json` y
`baseline_pins.json` de D115 (`parallel_tools_2026-10-01`): 71 rutas únicas,
ordenadas por ruta. Cada tamaño y SHA-256 coincide con el árbol de trabajo y
con `d27936cd1cd25c8ac2abacb6070f291655a983b5`.

Verificación ejecutada: lectura JSON de ambos manifiestos; para cada ruta,
cálculo de SHA-256 y bytes locales y de `git show <HEAD>:<ruta>`. Sin conflictos,
rutas ausentes ni diferencias.

Alcance: solo inventario de preservación de fuentes anteriores para D116. No
aporta resultados de model quality, no ejecuta ni evalúa celdas formales, no
altera el protocolo y no cambia el conteo formal de 0/24.
