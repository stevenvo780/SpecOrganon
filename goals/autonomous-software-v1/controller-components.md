# Componentes de ejecución — versión de ingeniería 2026-10-05

Estos componentes están en desarrollo. Ya existe el loop externo de fases,
el transporte Docker y el ejecutor, pero no hay entrega LogLens ni aceptación
del controlador completo. La revisión independiente
`component-review-03` rechazó la versión inicial; su transcripción y los fallos
reproducidos se conservan. El follow-up `component-review-04` devolvió otro rechazo
textual, con una validación de tipos malformados luego reparada. Su cliente nativo
también produjo un evento error de arranque de Code Mode antes de `turn.started`:
el adaptador lo rechazó y quedó inconcluso, sin aceptación ni repetición del rol.
El texto real se conserva por separado para inspeccionar el hallazgo; no es una
respuesta aceptada por el adaptador. Pasar pruebas no acepta `build`.

## Journal externo

`specorganon.role_jobs.JobStore` ejecuta un argv explícito y conserva request,
inicio, streams, registro de cierre y recibo. Su política actual es schema 3;
los journals anteriores permanecen intactos y no se migran silenciosamente.
Un cierre coincidente reutiliza los bytes verificados; cualquier divergencia
bloquea la reutilización. Un inicio sin recibo es inconcluso y no relanza.
Los callers reciben `stdout`/`stderr` como bytes: para serializar metadatos deben
seleccionar `receipt` y `reused`, sin convertir los streams en texto implícito.

El almacenamiento es privado del operador/controlador y debe quedar **fuera**
de los montajes de los roles. Descriptores de directorio, archivos sin enlaces,
flock, escrituras atómicas/fsync y un registro de cierre detectan divergencias.
Un operador que controla todos los archivos puede falsificar un journal
coherente; estos hashes no autentican personas ni ejecuciones frente a él.

Cada admisión fija argv, cwd, ambiente completo mediante digest sin publicar sus
valores, metadata, stdin y timeout. Los límites son 40 jobs, 6000 segundos,
128000 bytes de envelope y 2 MiB por stream por defecto. El límite global usa
el reloj monotónico de Linux y el identificador del arranque: reiniciar el
proceso no reinicia el presupuesto; después de un reboot se bloquean nuevas
admisiones en ese run. Se reservan 10 segundos para limpieza antes del dispatch.
La fecha de pared se conserva sólo como contexto. No es una garantía contra
bloqueos del kernel o almacenamiento malicioso.

Se supervisan proceso y pipes separadamente. Timeout/truncamiento mata el grupo
propio, drena de forma acotada y recoge su código. Toda falla tras Popen pasa por
la limpieza, incluido un error al guardar el PID. Cancelación recibe stdin vacío,
cwd/env fijados y su propio grupo con espera acotada. Un descendiente que escape
del grupo, o SIGKILL del dueño, requiere contención y recuperación del transporte
Docker/cgroup: el journal conserva incertidumbre y no afirma haberlo limpiado.
La prueba de SIGKILL antes del recibo hace limpieza externa explícita; no acredita
la futura limpieza automática de contenedores.

## Adaptador nativo

`scripts/controller_native_role.py` se ejecuta dentro de un contenedor de rol.
El launcher suministra `/input` RO, un output privado, el perfil **original** de
la cuenta autorizada y `SPECORGANON_ROLE_IMAGE_ID=sha256:...` obtenido por inspect.
Nunca copia auth.json, elige otra cuenta, escribe el ledger o registra revisión.
El image ID, bytes del ejecutable y hash de la configuración conocida se ligan
al journal. Se comprueban nuevamente antes/después de dispatch. Sólo se lee
`config.toml` Codex o `settings.json` Gemini, nunca credenciales; otras fuentes de
configuración siguen siendo una frontera de confianza del launcher/cliente.

La entrada nueva tiene este contrato (los pedidos históricos quedan intactos):

```json
{"schema":1,"role":"review","role_instructions":"Juzga los documentos entregados y devuelve el contrato indicado.","documents":{"documento.md":"Contenido completo"}}
```

`role` permite `review` o `author`. El reader limita tamaño antes de leer,
rechaza enlaces y valida tipos. El prompt renderizado y el envelope **completo**
deben caber en el límite. Ambos clientes reciben stdin duplex acotado; Gemini
usa un único mensaje `event=user` por `stream-json`. El payload codificado
tiene límite de 128000 bytes. Los documentos no se colocan en argv.
Las instrucciones exactas del contrato de salida deben incluirse en el pedido.

Una revisión devuelve schema 1, verdict accept/reject/inconclusive, reason no
vacío y findings como lista de objetos. El autor devuelve exactamente schema,
manifest, files y reason. Este filtro no verifica semántica del trabajo ni da
permiso para aplicar manifest/files: esa verificación corresponde al controlador.

Para Codex 0.160.0 se deshabilitan rutas de shell/exec/browser/media/delegación,
plugins/apps/hooks y MCP con claves literales seguras, además de web_search.
La lista procede del catálogo real del cliente, conservado como evidencia.
El cliente 0.160.0 fuerza `unified_exec=true` aun con opt-out ordinario: el
probe inicial conserva 23/24 flags apagados y su fallo. El control de registro
de shell es `shell_tool=false`, según
[spec_plan.rs](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/core/src/tools/spec_plan.rs);
[managed_features.rs](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/core/src/config/managed_features.rs)
explica el backend forzado. La nueva admisión mide 23 controles efectivos con
`features list`, registra el valor de unified_exec y bloquea si alguno de los
controles requeridos sigue activo. El probe no llama al modelo; el journal
interior admite dos comandos (preflight y una llamada), no dos réplicas del rol.
El sandbox nativo sigue en read-only. Esto no garantiza aislamiento contra un
cliente malicioso ni independencia de cuentas; autores/revisores comparten
cuota cuando usan la misma suscripción. La separación física y las fuentes
efectivas de configuración todavía necesitan pruebas del launcher final.

El parser Codex exige thread.started → turn.started → ítems de texto válidos →
turn.completed, un único mensaje final asociado a ese turno y ningún evento
posterior/desconocido/herramienta. Un formato nativo nuevo queda inconcluso hasta
adaptarlo explícitamente. AGY exige SUCCESS, respuesta no vacía y ausencia de
acciones denegadas. La ruta Gemini de producción exige init, un user_input,
un agent_response cerrado y result coincidente de un solo turno. Rechaza pasos
de herramientas, eventos desconocidos, turnos duplicados y texto de cierre
distinto de los deltas observados. Los fixtures JSON históricos quedan separados
de esa ruta. Se usa el parser JSON estricto del motor, que rechaza claves
duplicadas, no finitos y pérdida decimal; no extrae JSON de narrativas. Usage
faltante permanece desconocido y no se inventa un coste.

## Controlador y contenedores actuales

`specorganon.software_controller.Controller` conserva su checkpoint privado,
consulta la siguiente tarea, aplica puts guardados del autor, solicita juicios
separados de conformidad con el mandato y de fase, y mide tests con el ejecutor.
Un rechazo conserva la fase pendiente y exige cambio material antes de otro
juicio. Una prueba fallida requiere trabajo nuevo del autor antes de medir otra
vez. Aprobaciones y revisiones comparten el máximo de dos juicios por fase.

`specorganon.docker_roles.DockerRoles` fija imágenes por ID, snapshots RO,
journal del host inaccesible a los roles y perfiles originales montados sólo
en su cliente. Los tests usan otro contenedor sin red ni perfiles. Nombre,
etiqueta e intención se guardan antes de crear, y el ID antes de arrancar.
Un attach interrumpido sin recibo mata el contenedor propio al reconciliar y
sigue inconcluso; no infiere un recibo perdido desde el exit del contenedor.
El launcher explícito es `scripts/autonomous_software_controller.py --help`.
Su compuerta final exige nueve fases vigentes, trazas, recibos de test verificados,
bytes revisados y README. No publica ni despliega implícitamente.

`controller-04-receipt.json` mide **81 pruebas host**, incluidos SIGKILL tras
cierre y después de puts/review/advance con contenido sintético. Las dos pruebas
reales Docker están en `docker-controller-01-receipt.json` y
`controller-02-receipt.json`: cierre reutilizado sin repetir y dueño muerto
antes del recibo que queda inconcluso tras parar su contenedor. Son controles
de ingeniería; C1–C8 siguen sin veredicto formal. Candidate07 es la base limpia
de tests y todavía no contiene estos módulos nuevos en su wheel.

`controller-review-05` fue un rechazo real de Gemini. El bloqueo de fingerprint
no se reprodujo en los puntos ensayados, porque `applying` ya usa operaciones
idempotentes. El prompt Gemini por argv fue reemplazado por stdin. Los intentos
de texto sin argumento/vacío fallaron antes de generar; guion produjo una
respuesta nativa que el parser rechazó porque no había recibido el pedido.
El stream se descubrió con dos errores de entrada sin turnos y una observación
nativa; `gemini-stdin-surface-04` probó luego el adaptador completo con nonce,
usage y juicio deliberadamente inconcluso. Los fallos y rechazos se conservan.

Codex conserva el evento de arranque antiguo. La ruta nueva selecciona un
catálogo público de la versión 0.160.0 fijado por commit; cambia sólo el modo
local de herramientas del modelo, sin cambiar modelo remoto, cuenta o perfil.
`native-surface-01` midió un turno nativo sin errores/herramientas, con juicio
deliberadamente inconcluso. Ningún probe de transporte acepta una fase.

## Pendientes que mantienen la fase abierta

- Cerrar revisión independiente y recuperación de aplicación parcial/temporales
  de escritura después de SIGKILL; no basta con los puntos probados.
- Verificar una nueva wheel limpia con módulos y launcher actuales y precisar
  fuentes efectivas de configuración más allá del archivo conocido.
- Entrega real LogLens y controles C1–C8, con veredictos individuales.
- Nueva revisión independiente de los cambios y del controlador completo.
- Protocolo reservado N/S/T de dos familias, ablación, paquetes y publicación.

La especificación prospectiva original, los rechazos y resultados antiguos no
se reescriben para ajustar su criterio a lo que ahora pasa.
