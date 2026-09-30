# D-100 · cotejo de pasajes alimentarios

Auditoría de desarrollo de fuentes ya expuestas, sin preregistro confirmatorio,
nuevas respuestas de modelos, aprobación normativa o intervención en campo.
GOAL permanece íntegro y sus cinco criterios finales siguen no demostrados.

## Resultado observado

- Las **17 afirmaciones** coinciden con los números extraídos de los PDF
  fijados; las **siete filas** coinciden con etiquetas, frecuencias y porcentajes
  de la Tabla 1, incluido el total de 1000 respuestas.
- Se conservan dos desacuerdos internos de las fuentes: prosa de encuesta
  p3 `7–10`/`>10` frente a Tabla 1 p4 `7–9`/`10–12`/`>12`, y remisión de
  desperdicio a Tabla 4 en prosa LCA p7 frente a Tabla 7 real en p8.
- **82 pruebas focales** pasaron en Python 3.11.15 y 3.12.3, además de Ruff.
  Las pruebas alteran números, unidades, bases, procedencia, localizadores,
  frecuencias coherentes pero falsas, categorías abiertas/desconocidas y PDFs.
- Un wheel nuevo instalado offline en entornos vacíos de ambos Python pasó
  `uv pip check`. El módulo importado provino de `site-packages` y coincidió
  por SHA con el código nuevo. El script real desde otro directorio y con
  `-I` produjo resultados byte idénticos, 17/7 y dos advertencias.
- Revisión nativa independiente de fuentes y código, sin P1/P2 pendiente
  en el alcance declarado. No equivale a juicio humano Q ni aprobación humana.

## Diseño y alternativas

Se eligió un primitivo reutilizable en
[`source_passages.py`](../../../src/specorganon/source_passages.py) y un
[adaptador alimentario](../../../scripts/audit_bread_sources.py), separados.
El primitivo exige página, inicio/final únicos, coincidencia única y contexto
de unidad/base/fuente. Sólo normaliza espacios; registra hashes de PDF,
texto extraído, página original, pasaje normalizado y coincidencia.

La lista de números constantes del analizador histórico no prueba una nueva
transcripción contra el PDF. La comparación literal de espacios falló en
D-097. La extracción anclada conserva estructura y admite diferencias de
espaciado sin convertir cifras o categorías distintas en acuerdo. OCR y
lectura semántica automática requieren evaluación propia y no se ensayaron.
No se seleccionó una metodología ganadora a partir de este cotejo.

El [contrato](contract.json) contiene metadatos, selectores y reglas de contexto,
**sin una tabla de respuestas numéricas**. Los valores y frecuencias salen
del PDF. La base «wheat input» es interpretación revisada de la fila `% w/w`;
las bases y procedencias se cotejan contra el contrato revisado por Codex,
sin inferencia semántica automática o revisión humana competente demostrada.
Se separan masa, asignación económica, energía por harina y energía por pan.
Las tres filas de desperdicio no se convierten en tasas condicionales sucesivas.

## Defectos y negativos conservados

Durante el desarrollo se corrigieron contexto de encabezados intercalados
por columnas PDF, un final de pasaje duplicado y constantes `fcntl` ausentes
en el Python 3.11 disponible. No se corrigieron cifras ni fuentes originales.

El revisor reprodujo un falso positivo con un extractor sustituido por PATH:
una transcripción de 737 g pasaba pese al PDF de 736 g. El código final fija
ruta y SHA del binario, verifica sus bytes una vez y los ejecuta mediante
memfd sellado, con entorno limpio; versión y extracción usan el mismo
descriptor. PDF y extractor cambiados después de su lectura no afectan
los snapshots. Las regresiones y la revisión verifican el cierre.
El revisor **no conservó captures originales** de sus reproducciones; el
[registro de revisión](review.json) atribuye esas observaciones a su informe.

[pre_extractor_pin/](pre_extractor_pin/) conserva el resultado, contrato,
wheel y registros reales anteriores al arreglo. Su contrato reconstruido
coincide por SHA con el recibo original. Estos positivos no cubrían el
extractor sustituido y no se presentan como evidencia del arreglo final.
D-097, D-099 y los casos históricos permanecen intactos.

## Reproducción y condiciones

Desde la raíz del repositorio, con el paquete instalado y Poppler revisado:

```sh
.venv/bin/python scripts/audit_bread_sources.py
.venv/bin/python -m pytest -q tests/test_source_passages.py tests/test_audit_bread_sources.py
PYTHONPATH=src python3 -m pytest -q tests/test_source_passages.py tests/test_audit_bread_sources.py
```

`--claims`, `--table` y `--pdf-root` permiten cotejar otras copias de las
transcripciones y fuentes fijadas; `--output` crea un archivo nuevo y no
sobrescribe resultados. Un rechazo produce código 2. El primitivo genérico
acepta otras fuentes/selectores y un `ExtractorSpec` explícito revisado.

El contrato de este corte fija `/usr/bin/pdftotext` por SHA; otro binario
requiere un nuevo pin revisado. La ejecución sellada requiere Linux con
memfd y `/proc`. Bibliotecas dinámicas, datos de Poppler y kernel siguen
siendo dependencias confiadas del host, sin atestación externa.

Los [registros de instalación](installed/operations.json),
[resultado final](result.json), [validación](validation.json) y
[recibo de conservación](receipt.json) detallan el alcance. El wheel nuevo
está en `toolkit/`; no reemplaza el wheel histórico de `dist/`.

No hubo nueva auditoría global de CLI/MCP o nueve fases, medición de Q,
comparación confirmatoria, llamada paga o corrida de las 24. Próximo frente:
vincular estos cotejos a una receta alimentaria nueva y reanudable, con
traza de evidencia y bloqueos normativos explícitos. **Aceptación global 0/5.**
