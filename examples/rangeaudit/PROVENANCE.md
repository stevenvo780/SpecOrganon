# RangeAudit: entrega original de desarrollo

Estos tres archivos se extrajeron sin modificar de la [entrega pública sellada](../../website/public/resultados/software/rangeaudit-desarrollo-01-entrega.zip). El README original conserva las rutas del contenedor en que se generó y no se reescribió después de evaluar.

Para usarlo desde este checkout, con Python 3 disponible:

```sh
printf '%s\n' '{"intervals":[[1,3],[3,7],[10,12]]}' | python3 examples/rangeaudit/range_audit.py
python3 examples/rangeaudit/run_local_tests.py
```

El programa y el test utilizan sólo la biblioteca estándar. El adaptador local carga el test original y sustituye sólo las rutas del intérprete y del programa en memoria, sin cambiar sus bytes. La generación nativa y sus revisiones completaron nueve fases; las 115 comprobaciones adicionales fueron públicas y de desarrollo. No son casos reservados ni prueban ventaja frente a otros métodos. [Recibo de ingeniería y entrega](../../goals/method-superiority-v1/evidence/engineering-02-receipt.json).
