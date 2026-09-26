# Corrección de instrumentación T2 · piloto de desarrollo

El primer intento T declaró que no encontraba SpecOrganon. Una comprobación externa posterior confirmó que el paquete se había instalado en `.venv/bin/organon` dentro del directorio aislado del brazo. Esta instrucción operativa se fijó antes de T2; T1 se conserva como fallo y T2 es una repetición exploratoria, no un reemplazo ciego de T1.

Ejecuta `.venv/bin/organon --help` y usa `.venv/bin/organon init <directorio-del-caso> --title ... --domain ... --actor ... --approval-policy signed`. El ejecutable ya está instalado localmente; no se requiere instalar dependencias, buscar MCP ni leer directorios externos. Registra en `report.md` los comandos que realmente ejecutes, los IDs generados y el estado real de la compuerta. Conserva el directorio del caso y su ledger. No presentes una firma o aprobación que no exista.
