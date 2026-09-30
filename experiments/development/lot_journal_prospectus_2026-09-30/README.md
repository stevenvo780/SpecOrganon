# D-102 · Diario de lotes y borrador alimentario

Desarrollo técnico, con ejemplo sintético y propuesta sin aprobar. Los cinco
criterios de GOAL siguen **No demostrados; 0/5**. No hubo nueva generación
experimental, Q, aprobación humana o intervención de campo.

## Qué cambia

- Biblioteca `lot_journal`, comando nativo `audit-lot-journal` y herramienta MCP
  `audit_lot_journal`: operaciones incrementales declaradas, masa húmeda/seca,
  cargas transferidas y agua/coproductos, sin inventar brazos o períodos.
- Borrador nuevo de 64 puts: 54 consultas actor×dimensión, tres alternativas
  sin ranking y cuatro obligaciones de ingeniería. Umbrales, márgenes,
  permisos, población, baseline, asignación, consumo y efectos pendientes.
- Recotejo D-100 de 17 afirmaciones y siete filas, conservando dos desacuerdos.
  Una tonelada normalizada produce 671/138/191 kg según fracciones publicadas;
  no es un lote observado. La segunda operación usa cantidades inventadas
  para controles aritméticos. Energía documental 0,412 kWh/pieza y 103/184
  kWh/kg de pan, sin nueva LCA ni efecto causal.
- D-101 conserva su controlador de 37 puts y sus originales. El nuevo binding
  de 13 archivos documenta la preparación; no es admisión estricta de 64 puts.

## Pruebas y transportes

Los [recibos 3.11](installed/311/receipt.json) y
[3.12](installed/312/receipt.json) proceden del wheel instalado offline fuera
del árbol. Ambos descubren 22 herramientas: CLI publica 64 puts y MCP
reintenta 0/64 sin duplicados. Nueve pares de compuertas y cuatro de traza
coinciden. `frame` está listo sin revisión; todas las fases siguen sin aceptar.
Normas y decisión no aprobadas, criterios sin umbral, test del caso sin
ejecución firmada y validación sin baseline/result.

En cada entorno, seis negativos se rechazan en CLI y MCP: balance, ID
duplicado, base seca implícita, tiempo decreciente, transferencia alterada y
reconsumo de evaporación terminal. La falta de fracciones secas queda pendiente.
Los positivos y consultas conservan el ledger; antes de init se compara el
directorio, después sólo el hash del ledger. No se afirma snapshot completo
de todos los archivos después de cada consulta.

Los transportes originales se archivan en gzip sin cambiar sus bytes
decodificados; [procedencia y hashes](copy_provenance.json). Sus 48 líneas
por entorno incluyen respuestas de herramientas y stdout/stderr CLI. Los
22 nombres descubiertos están en el recibo, pero la respuesta cruda de
`list_tools` no se archivó. Los paths de los recibos son los del runtime
original; las copias del caso no se reubicaron ni ejecutaron desde este dossier.
Las [operaciones de instalación](installed/operations.json) registran el build
offline, las dos instalaciones, `pip check` e imports de site-packages. El
wheel se construyó antes de actualizar la documentación final.

93 pruebas de biblioteca pasan en ambos intérpretes. Interfaces/prospectus:
25 en 3.11, 23 y dos skips por falta de MCP en el Python 3.12 global; los probes
instalados sí ejecutan MCP real en 3.12. Los [logs focales](validation/validation.json)
y [recibo final](receipt.json) fijan resultados exactos, suite general, Ruff,
compilación y smoke instalado 3.11 de 15 operaciones/22 herramientas.

## Negativos y conservación

La [primera suite global](validation/global.stdout) produjo 2538 passed y
21 failed: pruebas D-099 intentaban admitir CLI actual con pins históricos.
El protocolo rechaza correctamente los bytes nuevos. Se adaptó sólo la
fixture de tests a una snapshot temporal de los 22 módulos históricos,
verificados por SHA/bytes de un commit fijo. Un test nuevo comprueba que
preparar sobre la fuente actual rechaza dos veces sin crear destino/admisión
ni cambiar plan o fuentes. Las 28 pruebas D-099 pasan en ambos intérpretes.
El broker, contratos y outputs originales no se cambiaron. Su
[status actual](validation/frozen-current-status.stderr) rechaza el árbol
nuevo; los estados archivados `completed` siguen siendo evidencia histórica.
La suite posterior está conservada por separado, sin sustituir el negativo.

[Conservación](preservation.json): 270 de 272 protegidos idénticos; dos
interfaces actualizadas deliberadamente, con sus bytes anteriores cotejados
en `0f8c651d15ccd6da99882abba901099fdae6486e`. Permanecen iguales 147 outputs
D-099, 12 marcadores, 20 módulos, 16 archivos de su dossier congelado, 21
pines de código/evidencia D-100 y 94 de D-101. Sus tres documentos activos
se actualizan y las versiones anteriores siguen en el commit padre.
GOAL, casos y negativos previos permanecen intactos.

## Alcance y pendientes

Un balance válido sólo comprueba declaraciones. Hashes de fuente son punteros;
no se abren registros ni se autentican identidad física, calibración, fracción
seca, custodia o cobertura. No se obliga a terminar la cadena hasta consumo.
La incertidumbre seca trata fracciones como coeficientes exactos. Evaporación
terminal se distingue de agua capturada para uso posterior.

La revisión independiente encontró y cerró el reconsumo de evaporación y una
carrera que podía fijar datos documentales alterados al preparar. Esas
reproducciones se informaron por el agente; no se conservan streams crudos
separados ni se reconstruyen. El reauditor rechaza cambios antes del nuevo
binding, pero queda posible una carrera por el mismo UID después del último
pin. Fuentes y ledger no forman una transacción atómica y `put` genérico no
realiza un cotejo semántico universal. [Revisión y límites](review.json).

Faltan baseline actual enlazado, autoridades y consentimiento del sitio,
equivalencias/márgenes normativos, diseño estadístico prospectivo competente
y observación de consumo/efectos. El panel y la comparación confirmatoria
de modelos también siguen pendientes. [Uso y contrato](../../../docs/diario_lotes.md).
