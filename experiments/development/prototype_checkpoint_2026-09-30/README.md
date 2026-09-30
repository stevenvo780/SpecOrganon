# D-095 · Checkpoint inicial con un proceso supervisado

El [plan](plan.json), supervisor y pruebas se congelaron en
**`063192217a3bf3a4a9c2bc2349532e74216d543f`** antes de una tentativa de
desarrollo sobre el paquete público del pan: Codex CLI, modelo solicitado
`gpt-6-luna`, esfuerzo `medium`, modo `graph` y 120 segundos activos locales
compartidos por preflight, generación e inicialización. No se puntúa calidad,
selecciona arquitectura ni resuelve el caso alimentario en este paso.

## Resultado real: falló, no hay checkpoint

La CLI salió con código 0 tras 20,781 s; el proceso supervisor duró 21,127 s.
La traza conserva un evento `error`: Code Mode no está disponible porque se
deshabilitó su host. Luego aparecen una propuesta de 15 nodos pendientes,
dos normativos y un turno final. La regla congelada admite únicamente ítems
`reasoning`/`agent_message`: rechazó el error antes de llamar a `init`.
**No se crearon `prototype_case.json`, `state.json` ni un checkpoint aceptado.**

La [inspección de solo lectura](outcome_inspection.json) comprueba la estructura
de la propuesta, sin inicializarla ni cambiar el fallo. El helper de uso
extrae 17.576 tokens de entrada y 956 de salida, caché y razonamiento 0; su
`terminal_success:true` ignora ese evento de error y **no representa éxito
del supervisor**. Son contadores CLI locales, con coste e identidad efectiva
sin autenticar. Se observaron cero ítems de herramientas, un ítem de error,
una invocación de generación y ningún reemplazo.

El [archivo](attempt/) conserva 17 archivos permitidos, byte idénticos al
directorio privado, con fuentes/harness, prompt, esquema, estado del intento,
propuesta y streams. No se copiaron credenciales, sesiones ni contenidos del
directorio de trabajo. El [recibo del archivo](archive_receipt.json),
[estado en otro proceso](fresh_status.json), [validación local](supervisor_validation.json)
y [revisión previa](prelaunch_review.json) separan proveedor falso y tentativa
real. Un revisor nativo separado recalculó los 17 pins y confirmó el rechazo
sin `init`. La corrección de configuración debe ir en una nueva ronda
registrada; no se reparó ni volvió a lanzar este intento.

El checkpoint debe contener un grafo inicial válido, todas sus decisiones
pendientes y un requisito de ingeniería dependiente de una norma pendiente.
El supervisor valida la propuesta y llama al `init` real del prototipo;
conserva estado y hashes para una inspección en otro proceso. Una ejecución
iniciada no se vuelve a lanzar. Fallos, streams parciales y salidas ausentes
son parte del resultado.

## Corrección del calendario

El puente managed permitía solicitar un plazo local superior al fijado en
el calendario. Ahora `prepare` rechaza antes de crear archivos; `status` y
`execute` repiten la comprobación antes de iniciar una llamada. El
[recibo](managed_validation.json) registra 172 pruebas combinadas y cinco
regresiones nuevas repetidas por un revisor nativo independiente. No hubo
proveedor real en esas pruebas.

## Inspección y alcance

En este checkout, el siguiente comando de solo lectura verifica los pins y
devuelve **código 1** con `state: failed`, `checkpoint_verified: false` y
`relaunch_allowed: false`:

```bash
python3 scripts/run_prototype_checkpoint.py status \
  experiments/development/prototype_checkpoint_2026-09-30/attempt
```

La autoridad del estudio está fijada por ruta y SHA del plan. La reserva
`O_EXCL`/fsync bloquea un segundo destino para procesos cooperantes que
comparten la misma raíz local; el mismo UID puede alterar código, registro y
manifiestos. No hay control global ni custodia independiente. Las 17 pruebas
locales cubren timeout real con salida parcial, propuesta inválida, tokens
cero, segundo destino y stream de más de 32 MiB; su CLI es falsa.

Se reutiliza la autenticación ChatGPT existente sin copiar credenciales;
una clasificación incierta o con API key se rechaza. Se solicita sandbox de
solo lectura y se ignora la configuración del usuario. Las opciones de
ejecución no constituyen aislamiento completo frente a procesos del mismo
UID. El rechazo de herramientas observadas ocurre después de recibir su
traza; no acredita una prohibición preventiva global.

La [documentación oficial del modo no interactivo](https://learn.chatgpt.com/docs/non-interactive-mode)
describe JSONL y salida con esquema; los flags empleados se cotejan además
con la CLI instalada. La telemetría de uso local no autentica al proveedor,
su versión de modelo ni el coste. El corte del proceso local no demuestra
cancelación remota. Faltan límites comunes de tokens, herramientas y coste,
repeticiones, familias/esfuerzos, casos reservados y evaluación ciega. Este
intento no cuenta entre las 24 corridas y no cambia el veredicto **0/5**.

Este resultado negativo conserva el plazo medido y una propuesta nueva,
sin demostrar checkpoint nativo, recuperación del trabajo científico, calidad
equivalente entre modelos o funcionamiento completo del toolkit.
