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
