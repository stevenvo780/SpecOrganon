# MVP local — 2 de octubre de 2026

Este paquete permite trabajar con proyectos locales, agentes nativos y las
herramientas existentes, sin una API adicional de modelos.

- [ZIP con wheel, guía inicial, metodología y skill](specorganon-mvp-local-20261002.zip).
- [Wheel independiente](specorganon-0.1.0-py3-none-any.whl), idéntico al incluido en el ZIP.
- [SHA256SUMS](SHA256SUMS), para comprobar los bytes descargados.

Descarga el ZIP mediante **Download raw file** en GitHub, extráelo y sigue
`INICIO.md`. También puedes instalar directamente el wheel en un entorno
Python 3.11 o superior:

```sh
uv venv .venv
uv pip install --python .venv/bin/python specorganon-0.1.0-py3-none-any.whl
.venv/bin/organon --help
```

La [guía de uso local](../../docs/uso_local.md) explica cómo iniciar un caso,
revisarlo con otro agente y reanudarlo. El
[dossier del MVP](../../experiments/development/mvp_local_2026-10-01/)
conserva los proyectos, ejecuciones y revisión independiente. El código
empaquetado corresponde al commit `824d9f37a98d4940a1140cb8bfb5d7fb9f435645`.

El hito acredita funcionamiento local. Los criterios finales de integridad,
resolución real, aporte comparativo y generalización siguen pendientes según
el [estado del proyecto](../../docs/estado.md).
