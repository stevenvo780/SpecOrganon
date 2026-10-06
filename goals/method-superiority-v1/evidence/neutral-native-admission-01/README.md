# Preflight y solicitud de admisión nativa N/S dev7

La publicación dev7 anterior verificó CLI/MCP y 40 módulos en la imagen Codex
`7fcab03…`; no había ejecutado el puente nativo. El preflight encontró que
DockerRoles exige `/opt/specorganon/.venv/bin/python`, mientras esa imagen solo
ofrecía `venv`. El runtime histórico `aa4eae…` sí tenía la ruta. Se añadió un alias
local en docker/codex/Dockerfile; no se modificaron módulos, protocolo ni cuotas.
La imagen nueva `982382…` es un artefacto local distinto. Se preservan los recibos
de ambas imágenes anteriores; no se les atribuye esta verificación nueva.

`probe_native_image.py` verifica imagen nueva, 40 módulos instalados iguales a
las fuentes actuales, CLI/MCP stdio con 24 herramientas y Codex CLI 0.160.0.
`probe_bridge.py` prepara inputs reales de DockerRoles, ejecuta `bridge.py --help`
con su interpreter exacto, compara 40 módulos capturados, comprueba las features
Codex desactivadas y mide una prueba Docker offline real cuyo recibo se recupera
sin segunda ejecución. No monta perfiles originales ni realiza inferencias.
El borrador `bridge-help-only/launch.json` nunca fue ejecutado como rol; la prueba
usa comandos de preflight explícitos sin montajes de credenciales.

El primer preflight de features falló por CODEX_HOME apuntando a un directorio
vacío inexistente en tmpfs. Se conservan script, comandos y streams en
`failed-preflight-01-*`; se corrigió solo la configuración del probe a `/tmp`.
No fue un error de autenticación ni una generación experimental fallida.

Estos controles son ingeniería; no admiten pilotos por sí solos. La solicitud
independiente examinará contrato, controlador y driver ya revisados, evidencia
actual y un registro nuevo prospectivo de seis posiciones N/S, tres tipos, sin
reemplazos. Las fuentes se fijan por inventario SHA completo, commit y plan SHA;
imágenes por ID; perfiles originales permanecen separados sin copias. Quota del
volumen Docker Codex sigue UNKNOWN, sin polling local ni cambio de cuenta. El
revisor Gemini conserva el perfil original. F externo, common_complete,
competencia, calificación T y superioridad no se imputan de estos pilotos.

Los resultados públicos posteriores no se muestran al autor ni permiten reparar
su intento. Todos los errores, presupuestos consumidos y posiciones no iniciadas
se preservan. La admisión, si llega, se limita a seis pilotos públicos de desarrollo,
no a una comparación reservada ni a la congelación completa de la meta.
