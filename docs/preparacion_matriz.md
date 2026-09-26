# Preparación ejecutable de la matriz N/SDD/toolkit

Los scripts de esta página preparan y comprueban **candidatos de desarrollo** para el diseño de [protocolo_experimental.md](protocolo_experimental.md). No contienen casos reservados, no ejecutan modelos, no cobran, no sellan un registro y no reemplazan evaluadores independientes. El [panel de modelos](panel_modelos_preliminar.md) sigue sin congelar.

## Calendario candidato

[`scripts/plan_confirmatory.py`](../scripts/plan_confirmatory.py) lee un manifiesto JSON de esquema 1 y escribe el calendario en stdout. Requiere cuatro modelos declarados en dos familias con nivel de capacidad bajo y alto, al menos uno **declarado** configurable para esfuerzo bajo/alto por familia, tres hashes de paquetes **visibles** R-F/R-M/R-S y tres hashes separados de soluciones de referencia bajo **custodia propuesta**, digests de contrato, prompts, rúbrica, política de herramientas, guía SDD y toolkit, semilla y un límite común de llamadas a herramientas. Acepta solo formatos y estructura; no lee los archivos ni verifica que un proveedor, control real de esfuerzo, precio, licencia, caso reservado o versión exista. El custodio debe comprobar bytes, capacidades, accesos y autorización antes de cualquier registro.

```sh
uv run python scripts/plan_confirmatory.py MANIFIESTO.json > /ruta/de/desarrollo/calendario-candidato.json
```

El resultado lleva `classification: candidate_schedule_unsealed`, hashes del manifiesto y calendario, IDs de bloque y ejecución, y los límites 80 000 tokens medidos, 5 400 segundos activos y el máximo común de herramientas entregado por el operador. No impone esos límites sobre proveedores; solo los declara para la futura ejecución. Con cuatro modelos de dos esfuerzos genera 432 filas; cada modelo sin control resta 54, siempre conservando casos, brazos, agentes y tres réplicas. En cada estrato modelo × esfuerzo × agente × caso, N, S y T ocupan una vez cada posición a lo largo de las tres réplicas. Los bloques completos se mezclan con una semilla registrada, y cada bloque conserva sus tres brazos en el orden asignado. El calendario completo, que incluye hashes de referencias selladas, es material del custodio y **no se entrega íntegro a los ejecutores**.

## Análisis de calidad pareada

[`scripts/analyze_confirmatory.py`](../scripts/analyze_confirmatory.py) recibe ese calendario y un JSON con un registro por **cada** ID previsto: `q` entre 0 y 100, o estado explícito `missing`/`truncated`. Una ejecución truncada con artefactos puntuables conserva su `q`; una sin puntuación deja su terna incompleta. El script rechaza IDs omitidos, duplicados o ajenos, puntuaciones inválidas y digests que no coinciden **dentro de los archivos aportados**; todavía no coteja un registro bajo custodia externa.

```sh
uv run python scripts/analyze_confirmatory.py calendario-candidato.json puntuaciones-sinteticas.json > /ruta/de/desarrollo/analisis.json
```

Solo las ternas N/S/T completas entran en las diferencias `Q(T)−Q(S)` y `Q(T)−Q(N)`. Cuando todas las ternas están completas, el efecto medio promedia réplicas por estrato, casos y configuraciones con igual peso, esfuerzos dentro de cada modelo y por último los cuatro modelos con un cuarto cada uno. El IC percentil del 95 % remuestrea **ternas** dentro de cada estrato 10 000 veces con semilla registrada. Si falta una puntuación, publica pares disponibles como descriptivos y omite el estimador principal; nunca sustituye ni imputa. La salida siempre dice `development_analysis_unsealed` y `criterion_4.status: not_assessed`: Q sola no demuestra el aporte sin puntuación ciega doble, errores, trazabilidad, recuperación, intervención humana, tiempo, tokens, coste, ablaciones y custodia externa.

Ambos scripts son de solo lectura. `uv run pytest -q tests/test_plan_confirmatory.py tests/test_analyze_confirmatory.py` prueba cobertura exacta, contrabalanceo, reproducción, pesos iguales, remuestreo, faltantes, truncamiento e identidades inválidas con **modelos, hashes y puntuaciones inventados para desarrollo**. Ninguna de esas pruebas abre la reserva ni aporta observaciones confirmatorias. Los próximos contratos ejecutables necesarios son el registro externo de bytes y versiones, ejecutor aislado con límites reales y telemetría, recibos por ejecución, doble evaluación ciega, costes y análisis completo de todos los umbrales.
