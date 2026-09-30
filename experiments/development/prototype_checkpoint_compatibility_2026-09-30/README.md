# D-096 · Compatibilidad del host y checkpoint inicial

La ronda D-095 produjo una propuesta pendiente, pero un error de arranque
impidió crear el checkpoint. Este estudio registró una modificación concreta
antes de conocer su resultado: mantener disponible el host local empaquetado
de Code Mode. La autenticación, modelo/esfuerzo solicitados, fuentes, prompt,
plazo y regla de rechazo de errores/herramientas se conservan. D-095 permanece
intacto como negativo; no es un reintento de su carpeta ni una reparación.

## Diseño previo

- [Plan fijo](plan.json): un intento D096, Luna medio solicitado, prototipo
  graph, 120 segundos activos, sin reemplazo, fallback ni llamada API paga.
- El supervisor admite únicamente estudios registrados por ruta y SHA en
  código. D095 sigue usando su autoridad original; D096 tiene otra reserva
  local de un intento. El operador del mismo UID puede alterar el registro y
  el código: no hay custodia ni un límite global entre proveedores/agentes.
- Se verifica el SHA del prompt original, los mismos seis inputs públicos y
  cuatro archivos del prototipo. La propuesta debe tener todos los nodos
  pendientes y un requisito de ingeniería dependiente de una norma pendiente.
- Antes de generar se ejecuta `--help` del host empaquetado con el tiempo
  restante. Esto prueba disponibilidad básica, **no handshake, compatibilidad
  del modelo ni prohibición preventiva de herramientas**. Se conservan los
  demás flags de desactivación y se solicita sandbox de solo lectura.
- Una generación válida debe pasar el validador congelado y `init` real
  dentro del plazo; un proceso nuevo debe cotejar estado y hashes. Un fallo
  conserva sus streams y bloquea relanzar.

## Evidencia que justifica la modificación

El [preflight local](host_preflight.json), sin modelo, instalación ni lectura
de autenticación/configuración, encontró `codex-code-mode-host` junto al
ejecutable resuelto de Codex 0.159.2; su ayuda terminó con código 0. La
[documentación oficial de app-server](https://learn.chatgpt.com/docs/app-server)
describe que inicia por defecto un host local. Su relevancia para esta ronda
es una hipótesis de compatibilidad apoyada también por el error real D-095;
la ejecución registrada abajo comprueba si aparece de nuevo ese error.

Por separado se corrigió el helper de uso de Codex: los eventos explícitos
`error`, incluidos ítems de error antes/después del turno, impiden
`terminal_success`/`complete`. Los contadores se conservan. La regresión usa
el stream real D-095 sin modificarlo; sus flags históricos siguen archivados
con la versión que los produjo. Esta corrección no declara éxito de D-095.

## Resultado real

El código, pruebas y diseño previo quedaron en `aa3e533` antes de preparar
una carpeta privada nueva. El [recibo de lanzamiento](launch_receipt.json)
registra una sola llamada `codex exec`, gpt-6-luna medio solicitado, login
ChatGPT reportado y sin fallback API. Modelo, host e `init` terminaron con
código 0; la CLI duró 27,071 s y el supervisor 27,415 s dentro de 120 s.
Los cuatro eventos contienen un mensaje de agente y ningún error/ítem de
herramienta. La ausencia del error anterior en esta traza no prueba el
handshake interno del host ni su causalidad en una comparación repetida.

La [inspección](outcome_inspection.json) registra `checkpoint_ready`,
18 nodos pendientes, dos normas sin aprobación, cuatro fases sin empezar
y un único `init` en la historia. Una [lectura desde otro proceso](fresh_status.json)
y otra del [archivo conservado](archive_status.json) verifican el estado
y sus hashes; `relaunch_allowed:false`. Se [archivaron 23 archivos](archive_receipt.json)
con bytes originales, sin copiar autenticación, sesiones o el contenido de
`work`, ni reparar propuesta o repetir llamada. Uso local: 17.576 tokens
de entrada y 1.298 de salida; coste y versión efectiva sin autenticar.

La [validación local](validation.json) pasó 281 pruebas del parser y 22 del
supervisor, Ruff, compilación y diff-check. Un revisor independiente cerró
el falso verde de `item.updated` tras 79 focales verdes; la traza D-095 sigue
intacta y el parser actual rechaza sus flags de éxito conservando tokens.
Estas pruebas usan modelo falso y procesos locales reales; están separadas
de la única generación real registrada arriba.

La [revisión posterior independiente](review.json) cotejó los 23 archivos
contra sus pins y el intento original, los diez insumos contra D-094, siete
archivos protegidos y 75 archivos de dossiers previos: cero diferencias,
sin P1/P2 abierto en el alcance. No relanzó ni llamó al proveedor. Una sola
llamada consta en artefactos locales, sin telemetría externa del proveedor.

## Interpretación

La ronda comprueba operatividad del checkpoint, sin puntuar calidad ni elegir
método/modelo. El host puede modificar contexto interno de la CLI; un prompt
igual no acredita igualdad del contexto completo. Tokens, versión efectiva
y coste siguen sin atestación externa y no se imponen caps globales. No
cuenta entre las 24 corridas, no prueba recuperación científica ni impacto
de campo y mantiene el veredicto **0/5**. El siguiente avance debe continuar
el análisis con fuentes verificadas y decisiones humanas pendientes bajo
otro plan, o registrar una comparación apta para medir calidad; este
checkpoint permanece inicial e intacto.
