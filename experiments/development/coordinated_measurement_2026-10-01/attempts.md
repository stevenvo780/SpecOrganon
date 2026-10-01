# Intentos anteriores a la congelación

- Inspección inicial: `python` no está en PATH (exit 127). Se corrigió usando
  el intérprete exacto 3.11 de D119; no se atribuyen pruebas ejecutadas a ese
  intento. La ruta de estado vigente es `docs/estado.md`.
- Control Ruff de los dos helpers nuevos, salida observada de exec chunk
  `2d128c`: exit 1, `F401 pathlib.Path imported but unused` en
  `capture_checks.py:7`. Se retiró ese import antes del freeze. No se
  confunde esta observación con una captura congelada posterior ni se
  inventan streams originales separados.

Los intentos del worker y las capturas congeladas posteriores se preservan
por separado con sus fuentes/argv/streams cuando estén disponibles.

- Worker intento01: 42pass por intérprete; hashes before/after y streams sí,
  bytes originales de fuentes no recuperados después del endurecimiento.
- Worker intento02: 45pass por intérprete y fuentes before/after preservadas.
  La revisión independiente recuperó allí la fuente exacta `19b660c5…` de
  sus probes de tres discrepancias aceptadas por la API pura. No se afirmó
  bypass CLI. Leader epoch debe ser0; workers corresponden al timeline.
- Worker intento03: 51pass por intérprete, nuevas pruebas de rechazo y bytes
  before/after; CLI sobre ruta ausente exit2 con error fijo/sin crear run.
- Finales congelados:51pass por intérprete, Ruff/sintaxis/diff0; doce CLI
  positivos, fuentes/HEAD estables e inventarios D119 idénticos. No se
  reemplazaron las corridas originales ni hubo llamadas de modelo nuevas.
