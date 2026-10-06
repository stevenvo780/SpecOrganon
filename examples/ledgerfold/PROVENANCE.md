# LedgerFold: entrega original del intento08

Estos tres archivos son una copia byte a byte de la entrega nativa dev2 del
intento08 de la cohorte01, sin correcciones ni selección para reemplazar fallos.
Codex redactó el programa y pruebas; Gemini revisó las nueve fases. El controlador
registró pruebas propias en Docker y un comprobador público independiente pasó
104/104 observaciones. Es desarrollo público, no comparación reservada ni efecto
causal ni validación de superioridad. La cohorte completa quedó en 3/10 y siete fallos.

Desde esta carpeta se pueden ejecutar los tests originales:

```sh
python3 -B -m unittest -q test_ledger_fold.py
```

La versión publicada actual del toolkit difiere de la versión congelada de esta
entrega. El ledger y recibos preservados corresponden al checkout original.
