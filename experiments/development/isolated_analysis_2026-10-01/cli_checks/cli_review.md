# D113 — CLI real de preparación, sin ejecución del participante

Fuentes de referencia: c7979a8ccbd97fbbee939ea61ec4839eb8489b52.
Los cuatro comandos `build`/`prepare` salieron con código0: build3.11
0.567s, prepare3.11 0.820s, build3.12 0.465s, prepare3.12 0.565s.
Comandos exactos, entorno mínimo sin credenciales, streams crudos, duración,
exit y hashes antes/después están en cada subdirectorio `311_build`,
`311_prepare`, `312_build` y `312_prepare`. Los50 archivos de fuente
capturados permanecieron iguales a sus pins antes/después de cada comando.
`sources_before/` conserva sus bytes; incluye el helper de staging cotejado
directamente con Git, además de los archivos del freeze publicado.

Configuración2 común y sintética: offline-fixture-model, read_only_v1,
1000tokens/120s/64tools/128requests, techo1000microUSD y tarifa declarada
de1000000microUSD por millón para las cuatro categorías. No es tarifa ni
identidad autenticada de un proveedor. Misma configuración para A/B/C.

Cada build produjo un schedule de12 celdas R1 y4 bloques, con ambas cápsulas
D-F/D-E. Se preparó una celda D-F/A por intérprete. Ambas quedaron `prepared`:
contexto revision0/cursor0, tiempo activo/pausado0 y allowance120s;
requests/reservas/recibos/calls vacíos, tokens/costo comprometidos0.
Dos funciones fijadas: development_method→method/workspace y
development_analysis→analysis/analysis_readonly. El hash de cada ejecutable
coincide con política y binding, y su shebang señala el intérprete usado
para ese build. Por eso los ejecutables y schedules de ambos intérpretes
tienen hashes distintos; los originales y textos comunes coinciden.

Verificación de artefactos con exit0, streams y pins en `artifact_check/`:
los6 originales D-F y3 D-E coinciden byte a byte con las fuentes fijadas,
sus cápsulas y ZIP. También se cotejan los6 originales D-F en staging.
Dos textos completos,35 páginas y manifest —38 archivos derivados— tienen
sus hashes esperados, páginas idénticas a los segmentos de los textos
completos, y bytes iguales entre extracción, cápsula, ZIP y staging D-F.
La membresía exacta es44 archivos públicos D-F y3 D-E, más case.json en
cada ZIP; no se incorporó código fixture ni respuestas históricas.
`artifact_verification.json` conserva resultados y bindings;
`capsule_membership_check.json` conserva el cotejo adicional de membresía.

Workspaces conservados con padres propios0700:

- /tmp/specorganon-D113-cli-311-urs_uzl4
- /tmp/specorganon-D113-cli-312-480acnej

`inventory_311.json` e `inventory_312.json` contienen tipos/modos,
hashes y tamaños; no se copiaron casos completos al dossier. Los recibos
de preparación y streams JSON quedan en sus ubicaciones originales y en
las capturas CLI. Ruff y compile en memoria de los helpers de captura y
verificación pasaron. No se modificaron runtime ni tests.

Alcance: se comprobó el entrypoint CLI real de build y prepare. No se
ejecutaron modelo, análisis ni herramienta del participante; no se probó
ejecución de D-E mediante este CLI. Cero celdas formales nuevas, llamadas
de proveedor o pagos. No implica C paralelo,24 ejecuciones, Q, aprobación
normativa/humana o cierre de GOAL.
