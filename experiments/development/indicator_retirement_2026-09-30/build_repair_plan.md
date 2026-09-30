# D107 · Reparación acotada de la preparación del wheel

2026-09-30 UTC, registrada después del fallo y antes de la nueva preparación.
El primer preparador falló antes de ejecutar uv/build/install:

`ValueError: not a regular public file: /home/dev/.local/bin/uv`

La ruta conocida de uv es un enlace al ejecutable público. El preparador intentó
fijarla como archivo regular sin resolver ese enlace. Cero comandos de build o
instalación se ejecutaron; quedaron directorios vacíos y se conserva el error.

Se conserva el código inicial y su recibo. Se autoriza una ejecución nueva del
preparador corregido, que resolverá y fijará el ejecutable público de uv antes de
usarlo. Nuevos destinos `installed_repaired/` y `environment_install_repaired/`
separan wheel y streams; los entornos D107 previamente preparados permanecen como
destinos de instalación porque no recibieron ningún package SpecOrganon.

Mismo plan de dependencias offline, sin configuración, keyring, credenciales,
descargas de Python o modificaciones de los entornos D102. Capturar fuente
real ejecutada, fuentes de producción y wheel antes/después. Un intento nuevo,
sin bucle de reparación ni ejecución experimental de CLI/MCP. El freeze del
experimento se creará sólo tras concluir y verificar esta preparación.
