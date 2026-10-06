# SpecOrganon0.2.0rc1: candidato de ingeniería

Este paquete incluye el controlador schema8 y orientación de campos/referencias.
La nueva entrega real de nueve fases y la comparación completa siguen pendientes.
Los fixtures del smoke no demuestran autonomía ni superioridad metodológica.
El release histórico0.1.0 se conserva aparte.

Entorno limpio verificado: Ubuntu/Python3.12.3, imagen
sha256:98723123de528a5f0201a1c341fe044f88d885345b2e1bedd6a89574c4796d92.
29módulos instalados coinciden con las fuentes;68controles pertinentes pasaron.
Smoke:24herramientas MCP descubiertas,15operaciones ejercidas por CLI y15por
MCP stdio real, rechazo de JSON/firma inválida, replay y reanudación SIGKILL.
Sus actores/aceptaciones son sintéticos. No se afirma una suite completa de todas
las plataformas. El extractor fijado pasó extracción real y rechazó pins falsos.

## Instalar wheel

Desde esta carpeta, con uv0.12.22 y Python3.12 disponibles:

```sh
uv venv --python python3.12 ./venv
uv pip install --python ./venv/bin/python --require-hashes -r runtime-requirements.txt
uv pip install --python ./venv/bin/python --no-deps specorganon-0.2.0rc1-py3-none-any.whl
uv pip check --python ./venv/bin/python
./venv/bin/organon --help
./venv/bin/python -c 'import specorganon; print(specorganon.__version__)'
```

La instalación necesita acceso al índice o un caché/wheelhouse que contenga las
versiones/hashes fijados. La imagen de verificación se construyó sin red usando
su caché previamente conservado; el ZIP no incluye ese caché ni una imagen OCI.
Para MCP, configurar el cliente para ejecutar la ruta absoluta
`venv/bin/organon-mcp` por stdio. No requiere un proveedor de modelos para usar
las herramientas del toolkit.

## Fuentes y controlador externo

`source/` contiene src, tres launchers, documentos y el workflow sintético.
Instalar con el wheel anterior y ejecutar desde source:

```sh
../venv/bin/python scripts/autonomous_software_controller.py --help
../venv/bin/python scripts/clean_smoke.py .
```

El smoke crea fixtures temporales. El controlador exige caso local existente,
contrato/mandato previos, catálogo público, imágenes inspeccionadas y perfiles
originales separados. Su `--help` no genera casos, inicia autenticación o copia
credenciales. Este paquete no registra por sí solo experimentos ni incluye
recetas reservadas. Conservar los límites y recibos de cada registro prospectivo.

## Reproducir build

Desde source, crear un venv de construcción, instalar con requirements-build.txt
las seis versiones fijadas y usar uv build --wheel --offline --no-build-isolation
con ese Python. SOURCE_DATE_EPOCH está en build-reproducibility.json. Dos builds
locales independientes produjeron el mismo hash de wheel; no se afirma un rebuild
independiente en otra máquina. El manifiesto lista los archivos del paquete.
