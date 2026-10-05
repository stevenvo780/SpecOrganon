# Entorno Docker candidato para la release autónoma

La imagen instala el wheel y las dependencias de `uv.lock` sobre Ubuntu 24.04.
Su Python tiene `memfd_create`; Poppler reproduce el binario del contrato
histórico. La construcción falla si el SHA-256 de `pdftotext` difiere.
No necesita seleccionar el perfil CachyOS ni modificar el contrato D100.

Desde cualquier directorio del host:

```sh
docker build \
  -f /datos/workspaces/personal/SpecOrganon/docker/release/Dockerfile \
  -t specorganon-release:candidate-05 \
  /datos/workspaces/personal/SpecOrganon

docker run --rm --network none specorganon-release:candidate-05 organon --help
```

La imagen verificada tiene ID
`sha256:696cff48caf2c54fe8243d85df096f441d5628165b8f0b9a4dc84bd3b06f8fd5`.
El ID identifica bytes construidos. El Dockerfile fija la base y versiones
principales; las dependencias Debian transitivas dependen del repositorio APT
disponible al reconstruir. Una construcción posterior debe registrar su propio
ID, inventario y resultado, sin asumir identidad histórica.

## Auditoría de las fuentes históricas

```sh
docker run --rm --network none --read-only \
  --mount type=bind,src=/datos/workspaces/personal/SpecOrganon,dst=/workspace/SpecOrganon,readonly \
  --tmpfs /tmp:rw,nosuid,size=256m \
  -e PYTHONPATH=/workspace/SpecOrganon/src \
  -w /workspace/SpecOrganon \
  specorganon-release:candidate-05 \
  python -m scripts.audit_bread_sources
```

El extractor fijado es `/usr/bin/pdftotext`, Poppler 24.02.0, SHA-256
`0fb98ea179e19154a90202608c164f2a319b79f16576fa6534b2d601033565e7`.
La comparación ejecutada en la imagen candidata anterior con este mismo binario
reprodujo las 17 cifras, siete filas y ambos hashes de texto completo. Recibo:
`goals/autonomous-software-v1/evidence/docker-extraction-comparison.json`.
Esto autentica los bytes del extractor y compara resultados; no autentica las
bibliotecas ni el kernel de la ejecución histórica.

## Casos persistentes y MCP

La imagen usa el UID 1000 de Ubuntu. Crea una carpeta del host escribible por ese
UID y móntala en `/runs`. Ejemplo para un caso nuevo:

```sh
mkdir -p /datos/workspaces/personal/specorganon-validation/manual-cases
docker run --rm --network none \
  --mount type=bind,src=/datos/workspaces/personal/specorganon-validation/manual-cases,dst=/runs \
  specorganon-release:candidate-05 \
  organon init /runs/mi-caso --title 'Prueba local' --domain desarrollo \
  --approval-policy local --actor human:owner
```

`organon-mcp` está instalado en el mismo entorno. Un cliente stdio debe mantener
abierta la entrada usando `docker run --rm -i`, montar el caso y establecer
`ORGANON_ROOT=/runs`. Consulta [interfaces.md](interfaces.md) para los límites de
acceso. Las etiquetas locales no autentican identidades ni sustituyen revisión.

El laboratorio Codex conserva su imagen y volumen de sesión separados. Desde
`~`, indica el archivo Compose explícitamente:

```sh
docker compose -f /datos/workspaces/personal/SpecOrganon/compose.yaml run --rm codex
```

No copies `auth.json` a la imagen de release. Docker aísla procesos y volúmenes,
pero no agrega cuota al proveedor.

## Comprobaciones y límites actuales

`goals/autonomous-software-v1/evidence/docker-release-final-receipt.json` fija
comando, ID de imagen, hashes de todos los tests seleccionados y módulos,
`uv.lock` y streams: 201 pruebas aprobadas y cuatro integraciones exclusivas de
CachyOS omitidas. Incluye CLI de la receta, recuperación después de SIGKILL,
cliente MCP real, observación con `strace`, extracción y sandbox.

Es una imagen candidata con verificaciones técnicas. El caso nuevo todavía debe
completar sus nueve fases; la comparación prospectiva sigue pendiente. Los
tests sintéticos del runtime usan una autoridad nueva para los bytes actuales;
D118 conserva su congelación y rechaza compiladores modificados.
La captura PDF comprueba el tamaño después de recolectar la salida: no promete
una cota estricta de memoria.
