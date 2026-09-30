# D-096 · Compatibilidad del host y checkpoint inicial

La ronda D-095 produjo una propuesta pendiente, pero un error de arranque
impidió crear el checkpoint. Este estudio registra una modificación concreta
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
la llamada futura determinará si desaparece ese error.

Por separado se corrigió el helper de uso de Codex: los eventos explícitos
`error`, incluidos ítems de error antes/después del turno, impiden
`terminal_success`/`complete`. Los contadores se conservan. La regresión usa
el stream real D-095 sin modificarlo; sus flags históricos siguen archivados
con la versión que los produjo. Esta corrección no declara éxito de D-095.

## Interpretación

La ronda comprueba operatividad del checkpoint, sin puntuar calidad ni elegir
método/modelo. El host puede modificar contexto interno de la CLI; un prompt
igual no acredita igualdad del contexto completo. Tokens, versión efectiva
y coste siguen sin atestación externa y no se imponen caps globales. No
cuenta entre las 24 corridas, no prueba recuperación científica ni impacto
de campo y mantiene el veredicto **0/5**. Resultado real todavía pendiente de
la congelación y ejecución.
