# Candidato autónomo 0.2.0rc2

Esta preparación parte del commit congelado 3748028166ad1d4ac722f62f4ebf90701d397622.
El cambio de versión ocurre en un checkout separado; no cambia las fuentes de
la campaña activa, sus presupuestos ni sus modelos. Las dependencias de uv.lock
conservan exactamente sus entradas anteriores.

El wheel contiene SpecOrganon y los entrypoints organon y organon-mcp. Los
ejecutores de campañas son módulos del paquete fuente, bajo experiments; no se
instalan como entrypoints del wheel. Su registro vincula el checkout original
y no se puede trasladar a este checkout para seguir una campaña ya iniciada.

La instalación CLI/MCP se verifica con contenido sintético de control y
transporte stdio real. Ese control no cuenta como caso autónomo ni como resultado
comparativo. La entrega real FractionMix de nueve fases se conserva por separado;
la campaña completa y su evaluación reservada siguen pendientes.

Este candidato no acredita eficacia de campo ni la tesis general. La publicación
final requiere cerrar y comunicar todos los resultados del protocolo registrado,
incluidos fallos y mediciones desconocidas.

## Verificación técnica realizada

En Docker con CPython 3.12.3 y una nueva venv se verificaron los hashes de los
29 módulos instalados, 69 controles del controlador y los recursos, y 15
operaciones de CLI y 15 de MCP sobre transporte stdio real. Se comprobaron
reanudación tras SIGKILL, rechazo de firmas inválidas y preservación del ledger.
Los contenidos de esos casos son fixtures sintéticos. Cinco controles de
vinculación al checkout se excluyeron de la prueba del wheel: exigen la fuente
registrada y tienen evidencia separada. No se declara verde toda la plataforma.

La extracción del PDF fijado produjo 20 páginas y rechazó los hashes de fuente y
extractor incorrectos, además de un perfil desconocido. Los dos builds del wheel
fueron idénticos en el mismo entorno fijado y con SOURCE_DATE_EPOCH=1791230400.
La construcción usó el cache offline de una imagen local fijada y una nueva venv;
no equivale a reconstruir independientemente todo el sistema operativo.

## Reproducción de la interfaz

Con el paquete fuente extraído, `docker build -f docker/release/Dockerfile -t
specorganon-release:0.2.0rc2 .` construye desde la base de Ubuntu fijada. Requiere
acceso a los repositorios de paquetes; los digests y versiones se comprueban
durante el build. Para probar la interfaz, ejecuta `docker run --rm
specorganon-release:0.2.0rc2 organon --help`.

En un entorno Linux compatible con el extractor fijado, instala el wheel en una
venv nueva con `python3 -m venv .venv` y `.venv/bin/pip install
specorganon-0.2.0rc2-py3-none-any.whl`. Usa `.venv/bin/organon --help` para la CLI
y `.venv/bin/organon-mcp` como comando stdio del cliente MCP. El PDF necesita
pdftotext con el digest revisado; una instalación diferente se rechaza.

Desde esa venv, `.venv/bin/python scripts/clean_smoke.py .` verifica CLI/MCP con
fixtures, sin consultar proveedores. Las 69 pruebas instaladas usan los cuatro
archivos test_software_controller, test_software_controller_resources,
test_prospective_software_repairs y test_artifact_guidance, con el filtro
`-k "not registered and not guidance_source_digest"`. Ejecuta las pruebas fuera
de `src` y confirma que specorganon se importa desde site-packages.

El paquete fuente no incluye perfiles, credenciales ni un registro portátil de
la campaña activa. Su manifest liga los bytes exportados; el registro privado
original permanece separado.
