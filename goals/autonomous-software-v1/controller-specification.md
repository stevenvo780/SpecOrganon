# Especificación prospectiva del controlador externo

Estado: borrador previo a implementación y medición, 2026-10-05. Vinculado al
caso `cases/autonomous_software_v1`, protocolo `pr1`, indicador `i1`. No convierte
los tests técnicos previos, el piloto backup ni los controles D118 en resultados
de esta intervención. La comparación N/S/T tendrá otro protocolo reservado.

## Decisión y alcance

Se propone `o2`: controlador externo sobre el motor y runner existentes. Mantiene
las nueve compuertas, las versiones y los juicios reales. No reemplaza al motor
con una lista de campos ni modifica sus políticas firmadas. La delegación técnica
del dueño permite seleccionar la arquitectura dentro del mandato local; registrar
esa delegación no significa que el dueño haya elegido personalmente `o2`.

El controlador recibe un caso local y un contrato de entrega antes de ejecutar.
Consulta estado e informe, envía una tarea concreta al autor, conserva su respuesta,
aplica puts con precondiciones, mide comandos y entrega snapshots al revisor.
No inventa hechos ni revisiones. Los programas de rol y las pruebas se ejecutan
en contenedores distintos, con fuentes de revisión de solo lectura. Sólo el
controlador escribe el ledger. Las cuentas nativas permanecen en sus perfiles
existentes; no se copian credenciales ni sesiones a la entrega.

Un encargo del autor puede producir código y un manifiesto de puts; no puede
aprobar normas, emitir revisiones, adelantar fases ni fabricar recibos de pruebas.
Las decisiones técnicas locales requieren un juicio separado sobre su conformidad
con el mandato aprobado. Una conformidad negativa bloquea la decisión; el
controlador no la transforma en consentimiento nuevo. La aprobación declarativa
conserva el motivo y la revisión que sustentan esa delegación y no autentica al
dueño. Después se revisa el snapshot actual de la fase, ya con sus aprobaciones.

El ensayo de entrega nuevo será **LogLens**: una CLI pequeña de Python que resume
eventos JSONL de ejecuciones por trabajo y rol, distingue éxito/rechazo/inconcluso,
detecta registros inválidos y evita duplicar trabajos cerrados. Su propia pregunta,
alternativas, fuentes, criterios y resultados se registrarán en un caso nuevo.
El autor tendrá el contrato público; la revisión no sustituye evaluación reservada.

## Requisitos verificables

1. Derivar la siguiente tarea del estado vigente. Rechazar resultados de rol cuyo
   request hash, fase o snapshot no correspondan; no escribir tras esa discrepancia.
2. Aislar autor, revisor y ejecutor de pruebas. El revisor recibe los bytes exactos
   del código, ledger y recibos que juzga en un montaje RO, sin escribir solución.
3. Registrar argv, imagen, timeout, códigos, streams y hashes medidos. Una prueba
   declarada por el autor no cuenta como ejecutada. Los fallos no habilitan avance.
4. Reanudar mediante trabajos y manifiestos idempotentes. Un trabajo terminado
   reutiliza su recibo sólo si inputs/argv coinciden; un iniciado sin recibo queda
   inconcluso, no se relanza para obtener un resultado favorable. No borrar locks.
5. Publicar paquete únicamente con nueve fases vigentes, requisitos trazables,
   pruebas pertinentes realmente medidas y README útil. La revisión semántica y
   sus límites se conservan junto con los checks mecánicos.
6. Bloquear evidencia insuficiente, contradicción vigente y premisas obsoletas.
   Reparaciones nuevas requieren nuevas versiones/revisiones y conservan historia.

## Ocho controles y reglas de veredicto

El indicador cuenta controles satisfechos sobre denominador fijo **8**. No se
promedia su importancia ni se permite compensar un control fallido con otro.
Cada control tendrá artefactos y veredicto propio: satisfecho, fallido o inconcluso.

| ID | Criterio previo | Evidencia exigida |
| --- | --- | --- |
| C1 | El caso nuevo LogLens completa las nueve fases vigentes con juicios de un agente realmente separado. Todos los avances referencian su snapshot revisado; la entrega responde al contrato público. | Ledger completo, snapshots físicos de revisión, respuestas nativas, recibos de rol y juicio técnico final sobre argumentos/código. Las etiquetas distintas o fixtures no cumplen C1. |
| C2 | Cada requisito y criterio del caso entregado alcanza problema, norma aprobada, evidencia/protocolo y decisión vigentes; ningún descendiente está obsoleto. | `trace` de todos los requisitos/criterios, versiones y compuertas del caso nuevo. Una existencia de archivos sin esas rutas falla. |
| C3 | Al menos una prueba pertinente del contrato se ejecuta en el entorno limpio fijado; su argv y streams corresponden al recibo registrado. Los tests pertinentes cubren éxito, entradas inválidas y duplicados de la CLI entregada. | Proceso real sin perfil de proveedor, imagen fija, recibos, hashes, salidas y lectura crítica de pruebas por revisor; un `passed=true` producido por autor falla. |
| C4 | README explica instalación/ejecución, formato de entrada, errores y límites. Un tercero puede ejecutar un ejemplo desde carpeta limpia sin imports del workspace del autor. | README revisado, comando público ejecutado en contenedor limpio y su resultado; README vacío o sólo encabezados falla. |
| C5 | Retirar evidencia necesaria bloquea el avance y la publicación; un revisor que rechaza no se reemplaza automáticamente por aceptación. | Control sintético independiente con snapshots antes/después, error real y ausencia de evento de avance/paquete. No se declara evidencia real de LogLens a partir de esta simulación. |
| C6 | Una contradicción abierta bloquea al descendiente y la publicación sin reescribir historia. | Control sintético usando challenge real del motor, gate/runner y hashes anteriores; un warning con publicación exitosa falla. |
| C7 | Cambiar una premisa vuelve obsoletos descendientes/revisiones; un recibo viejo no los acepta. | Control sintético con put versionado, replay y rechazo del estado antiguo; los eventos históricos se mantienen. |
| C8 | SIGKILL después de un recibo de trabajo y antes de aplicar sus puts permite reutilizarlo y reanudar sin nueva llamada de rol ni eventos duplicados. SIGKILL antes del recibo deja el trabajo inconcluso y no lo relanza. | Procesos reales, marcadores/recibos, contadores de invocación y ledger después de reiniciar; ambos momentos forman un solo control y ambos deben pasar. |

C1–C4 proceden del caso nuevo y sus procesos reales. C5–C8 son controles adversos
sintéticos explícitos sobre el mecanismo; no estiman éxito de modelos ni causalidad.
La entrega del controlador y la transferencia LogLens se evalúan separadamente.

## Presupuesto y parada del ensayo local

- Un caso de ingeniería nuevo, con hasta **40 llamadas nativas de rol** en total.
  Se permiten hasta dos respuestas de autor y dos revisiones por fase, dentro del
  límite total; una reparación tras rechazo debe justificar un cambio de artefacto
  y conservar el rechazo. No cambiar modelo/cuenta para eludir un fallo.
- Cada llamada: timeout **180 s**, prompt máximo **128000 bytes**, hasta **2 MiB**
  por stream. Un truncamiento, timeout, permiso denegado o respuesta inválida
  queda inconcluso y no se interpreta como aceptación. Límite global **6000 s**.
- Pruebas locales: hasta **dos ejecuciones por test** y **120 s** por ejecución,
  sólo tras criterios registrados y con motivo para la segunda si cambió código.
  Contenedor sin red/perfiles, máximo 1 GiB, 2 CPU y 128 procesos. Resultados
  previos a una reparación siguen publicados como fallos de ingeniería.
- C5–C8: **un escenario por condición registrada**, timeout **120 s** por escenario.
  Una falla de implementación exige conservar el intento y declarar una nueva
  versión de ingeniería antes de comprobarla; no es una réplica confirmatoria.
- Los límites de bytes/tiempo no equivalen a presupuestos de tokens iguales.
  Registrar uso informado por cada cliente sin inventar faltantes; dinero de
  suscripción no atribuible queda desconocido. Consultar cuotas/catálogo antes
  de comenzar roles reales. No comprar recursos ni cambiar cuentas.
- Al agotar un límite se detiene esa ejecución con veredicto inconcluso o fallido.
  Los controles se informan todos con denominador 8. Para satisfacer el hito de
  entrega se requieren C1–C8; un fracaso no se oculta ni cambia el criterio.

## Fuera de esta aprobación

No se aprueba aquí el futuro estudio N/S/T ni se concluye superioridad. Antes
de sus autores habrá tareas reservadas de varios tipos, dos familias, repeticiones
justificadas, ablación y evaluadores físicamente separados, con otro presupuesto
y regla de parada. El GOAL.md original y el piloto backup quedan intactos.
