# D117 preservation intake

Unión de los 52 `records` de `source_freeze.json` y los 71 `records` de
`baseline_pins.json` de D116: 90 rutas únicas, sin pins contradictorios. Para
cada ruta, bytes y SHA-256 coinciden en el árbol de trabajo y en el HEAD D116
`ee26beb4cc7cb8788e130f0b0225f32b57a8cd3e`.

Comprobación: parsear ambos JSON; calcular tamaño y SHA-256 localmente; comparar
con `git show <HEAD D116>:<ruta>`. Errores: ninguno; no hubo rutas ausentes ni
diferencias. El cotejo del dossier D116 completo se hará aparte mediante Git
diff; este inventario no expande sus artefactos.

Clasificación: `preservation_inventory_only`. Celdas formales: 0/24. No aporta
afirmaciones de calidad de modelo, Q o coste.
