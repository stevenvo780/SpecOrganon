# Componentes de ejecución — versión de ingeniería 2026-10-05

Estos componentes están en desarrollo. No forman todavía el controlador de
nueve fases ni una entrega LogLens. La revisión independiente
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
deben caber en el límite; un prompt Gemini en argv puede quedar rechazado antes
de ejecutar por el overhead del envelope. Codex recibe stdin duplex acotado.
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
acciones denegadas. Se usa el parser JSON estricto del motor, que rechaza claves
duplicadas, no finitos y pérdida decimal; no extrae JSON de narrativas. Usage
faltante permanece desconocido y no se inventa un coste.

## Pendientes que mantienen la fase abierta

- Launcher Docker con admisión, journal host inaccesible a roles, límites,
  configuración efectiva y recuperación de contenedores después de SIGKILL.
- Resolver explícitamente el modo nativo de herramientas/Code Mode: la ausencia
  del host emitió un error de arranque en el follow-up; no se suprime el evento
  para aparentar éxito ni se acepta su respuesta automáticamente.
- Loop de fases, manifests con precondiciones, juicio de decisiones delegadas,
  registro de revisiones reales y medición de tests fuera del autor.
- Entrega real LogLens y controles C1–C8, con veredictos individuales.
- Nueva revisión independiente de los cambios y del controlador completo.
- Protocolo reservado N/S/T de dos familias, ablación, paquetes y publicación.

La especificación prospectiva original, los rechazos y resultados antiguos no
se reescriben para ajustar su criterio a lo que ahora pasa.
