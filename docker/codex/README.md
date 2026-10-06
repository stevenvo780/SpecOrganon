# Build experimental de fuentes dev9 y laboratorio Codex/MCP

Desde la carpeta del paquete fuente extraído:

```sh
docker build -f docker/release/Dockerfile -t specorganon-release:0.2.0rc3.dev10 .
docker compose build codex
docker compose run --rm -T codex codex --version
docker compose run --rm -T codex python /opt/codex-lab/smoke.py
docker compose run --rm codex codex login --device-auth
docker compose run --rm codex
```

Compose busca compose.yaml en la carpeta actual. Para ejecutarlo desde otra
carpeta, pasa `docker compose -f /RUTA/DEL/PAQUETE/compose.yaml ...`.

El smoke usa transporte MCP stdio real, descubre 24 herramientas, escribe un
caso sintético local acotado, verifica enlaces, compuerta e informe, rechaza una
versión obsoleta y una ruta externa, reinicia el servidor y compara con la CLI.
No llama a modelos, no acepta las nueve fases y no acredita eficacia del método.

El login crea una sesión nueva en el volumen de este laboratorio. No copies
auth.json de otra cuenta o contenedor. El proyecto Compose tiene un nombre
distinto del laboratorio histórico y de la campaña activa. Docker no añade cuota.
La sesión conserva approval_policy=on-request y sandbox_mode=workspace-write;
el smoke no cambia esas políticas. No se incluye ni se monta una cuenta del host.

El build fija la base Node amd64 por digest y Codex CLI 0.160.0. SpecOrganon viene
del build de Ubuntu, CPython y pdftotext fijados en docker/release/Dockerfile.
Las dependencias Python se verifican con hashes de uv.lock. npm y los repositorios
apt requieren red durante el build; no se promete una reconstrucción bit a bit de
todo el sistema operativo. Consulta los recibos de build y del smoke medidos.

Linux y Landlock ABI 5+ son requisitos del servidor. Compose conserva el seccomp
del laboratorio, cap_drop ALL y no-new-privileges. El perfil permite los namespaces
y montajes de Bubblewrap; apparmor:unconfined se limita a este servicio. No se
monta el socket Docker ni se cambian los permisos del trabajo principal.

`docker compose down` conserva casos, resultados y sesión. `down -v` los elimina;
úsalo únicamente si deseas borrar este laboratorio.

Este Docker permite pruebas nuevas. El registro privado de la campaña original
está vinculado a sus fuentes y rutas originales. No sirve para continuar esa
campaña desde un checkout nuevo ni para sustituir sus resultados adversos.

La validación histórica de la primera integración con inferencia real está en [VALIDATION.md](VALIDATION.md). Para una prueba nueva acotada después de autenticar el volumen propio:

```sh
docker compose run --rm -T codex python /opt/codex-lab/trial.py
```

El driver usa siete herramientas MCP autorizadas para su caso técnico, sin pedir aceptación de las nueve fases. Conserva los eventos y rechaza una inferencia sin llamadas MCP verificadas. Consume cuota de la cuenta autenticada.

El nombre Compose `specorganon-main-dev2` se mantiene para conservar los volúmenes
existentes del laboratorio main; la etiqueta del build experimental es dev7. La cohorte histórica
sigue en su checkout, imagen y volumen registrados. Dev3 conserva un smoke del wheel
instalado en Docker; su corrección opt-in no ha sido evaluada en una cohorte nativa
nueva. [Recibos y límites](../../goals/method-superiority-v1/development/BOUNDED_ADMISSION.md).

Dev5 verifica el wheel instalado y tres controles Docker de recuperación sin modelos, con pérdida de respuesta inyectada; no reproduce el timeout natural ni cuenta como una cohorte nativa. La imagen del recibo es local y no se afirma publicada en un registry. Las fuentes, rechazos y [recibo final](../../goals/method-superiority-v1/evidence/docker-create-recovery-01/engineering-receipt.json) se conservan.

El hito histórico dev6 conserva su probe de wheel local con CLI y MCP stdio en
el host; ese recibo no acreditaba MCP instalado en una imagen dev6. No se reetiqueta
como prueba dev7. [Controles N/S por etapas y límites](../../goals/method-superiority-v1/development/STAGED_CONTROLS_V1.md).

La candidata dev7 integra N con decisiones autónomas y S con su proceso por etapas,
con presupuesto común de cinco autores, cuatro revisores y dos medidas. Su imagen
local y wheel se comprueban con 40 módulos iguales a las fuentes, CLI y MCP stdio
offline (caso sintético, 24 herramientas); los recibos se conservan en
[evidencia de integración](../../goals/method-superiority-v1/evidence/neutral-autonomy-controller-01/).
La imagen no está publicada en un registry ni constituye freeze completo, calificación
T o admisión de los seis pilotos. Las nueve fases, T/común y evaluación independiente
F reservada siguen siendo requisitos de la meta. No inferir superioridad de los controles
Docker con roles sintéticos ni de una instalación correcta.


## Candidata dev8: referencias de contexto

El build actual contiene el contexto lossless compartido N/S. Las comprobaciones
offline de solicitudes fallidas se registran separadamente; no son nuevas
generaciones, prueba de competencia ni una versión completa congelada. El piloto
dev7 original sigue cerrado con sus seis fallos por presupuesto de solicitud.
Los límites request/prompt permanecen110000/128000bytes.
[Diseño y límites de la corrección](../../goals/method-superiority-v1/development/REQUEST_CONTENT_V1.md).
