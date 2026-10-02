# Compatibilidad de Python: alcance comprobado

El paquete declara `requires-python = ">=3.11"`. Esa declaración permite la
instalación; no demuestra que cada versión futura ni todas las capacidades del
host funcionen. El 2026-10-02 se verificó el núcleo local en Linux x86_64 con
CPython 3.12.14 y 3.13.5, a partir de `main`
`bc8861d9c9a569ccce5cf52928b8b98c9a607f58` (árbol
`0115aa850ac1847860ebd7a80cec6575de633a8d`). No se encontró un defecto del
núcleo atribuible a Python 3.13 en estas rutas. La suite completa no pasó en
este entorno; el resultado no acredita compatibilidad total del repositorio.

Se probó un wheel recién construido del código actual. El wheel publicado en
`releases/mvp-local-20261002/` está fijado por separado al commit
`824d9f37a98d4940a1140cb8bfb5d7fb9f435645`; sus bytes no se probaron en 3.13
en esta ejecución. El resultado nuevo no valida retroactivamente ese paquete.

## Repetir la comprobación acotada

Se requieren Linux, `uv` y el intérprete ya instalado. Desde el repositorio:

```sh
python3 scripts/check_python_compatibility.py --python python3.12 --output /tmp/organon-check-312
python3 scripts/check_python_compatibility.py --python python3.13 --output /tmp/organon-check-313
```

Cada salida debe ser nueva y externa al árbol fuente. El script deshabilita
las descargas de Python. Puede descargar dependencias declaradas; `--offline`
exige que ya estén en la caché de `uv`. No cambia `uv.lock`, instala otro
runtime ni actualiza los paquetes históricos de `releases/`.

El modo offline se activa con `--offline` o un `UV_OFFLINE` heredado verdadero
(`1`, `true`, `yes`, `on`, sin distinguir mayúsculas). Una caché explícita en
`UV_CACHE_DIR` se conserva, anclando las rutas relativas al directorio de
invocación sin resolver enlaces simbólicos. Sin caché explícita, el modo
offline deja que `uv` use su caché habitual de XDG/HOME; el modo online usa
una caché aislada en `SALIDA/uv-cache`. Las rutas relativas de `--python`
también se interpretan desde el directorio donde se invoca el script.

Construye un wheel nuevo, exporta las dependencias de desarrollo de `uv.lock`
con hashes y lo instala sin modo editable en un entorno vacío. Comprueba
dependencias e importación desde `site-packages`, y ejecuta los procesos desde
fuera del repositorio. Conserva el wheel, versiones instaladas, XML de pytest,
comandos, códigos de salida, timeouts, streams y hashes en `summary.json` y
archivos adyacentes. Un comando fallido devuelve un código distinto de cero y
conserva la evidencia; nunca convierte una prueba fallida en éxito.

| Comprobación | 3.12.14 | 3.13.5 |
| --- | --- | --- |
| Wheel limpio y dependencias fijadas | Pasó | Pasó |
| `clean_smoke.py`: CLI y cliente MCP stdio real | Pasó | Pasó |
| Inventario MCP / operaciones compartidas verificadas | 24 / 15 | 24 / 15 |
| Nueve fases sintéticas, replay sin duplicados y reanudación tras SIGKILL | Pasó | Pasó |
| Tests locales, informe, ledger y runner | 81 pasaron | 81 pasaron |

Los tests locales comprueban las nueve fases por el motor con un recibo de
subproceso medido; las interfaces recorren una fase local, decisiones,
reanudación, igualdad CLI/MCP del informe JSON y Markdown, y reapertura.
También comprueban que `signed` siga siendo la política inicial. Son casos,
aprobaciones y etiquetas de revisión sintéticos. El transporte MCP es real;
eso no representa revisión por agentes nativos, consentimiento humano real,
una evaluación de modelos ni impacto científico o de campo.

## Límites observados

- Python 3.11 no estaba disponible y no se instaló. Se conserva la evidencia
  histórica de 3.11 citada en el README, sin presentarla como una ejecución nueva.
- MCP con `ORGANON_ROOT` y las repeticiones con sandbox requieren Landlock.
  Este host devolvió `errno=38` (función no implementada). El smoke existente
  y los tests locales usan casos temporales sin `ORGANON_ROOT`; no verifican
  confinamiento. No se relajó la política del servidor.
- `/usr/bin/pdftotext` tuvo SHA-256
  `7fe3559cac3ba61dd93650a1ba90499b9fc488184ef8d0f2f1305ddf52c0378b`,
  distinto del pin revisado
  `0fb98ea179e19154a90202608c164f2a319b79f16576fa6534b2d601033565e7`.
  El auditor rechazó esos bytes en 3.12 y 3.13. No se cambió el pin.
- La suite amplia de 3.13 produjo 3086 tests aprobados, 300 fallos, 228 errores
  y 237 omitidos (además de 9 subtests aprobados). Incluye los límites
  anteriores, historia Git ausente en el clon superficial, rutas de runtime
  fijas y precondiciones de paquetes/directorios. No se atribuyen todos esos
  fallos a una versión de Python ni se afirma haber diagnosticado cada uno.
- La prueba instalada de evidencia PDF ahora incluye 3.13 junto a 3.11/3.12.
  Su ejecución en este host quedó bloqueada por Landlock tanto en 3.12 como
  en 3.13; no constituye evidencia de éxito de esa ruta.

La suite amplia se invoca desde la raíz con `uv run python -m pytest -q tests`.
La invocación anterior `uv run pytest -q` falló al recolectar tres módulos que
importan `scripts`; ejecutar pytest como módulo incluye la raíz en la ruta de
importación. Se corrigió la instrucción, sin cambiar el código del toolkit,
el modo firmado inicial, las conclusiones científicas ni los bytes históricos.
