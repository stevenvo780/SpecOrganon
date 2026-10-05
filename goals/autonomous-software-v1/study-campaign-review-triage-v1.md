# Campaña y evaluación: revisión negativa y cambios antes de generación

Gemini3.1ProHigh, sesión primaria en Kratos, job0263f69679ac46e0bbb0b583620c315d,
emitió reject sobre texto. No ejecutó tests. Se conserva el resultado original;
los cambios posteriores no convierten ese rechazo en aceptación.

1. Fallo nativo no clasificable: ahora infra_inconclusive, grade=null, admisión
   realmente consumida, campaña detenida, siguiente índice intacto. No se adopta
   la propuesta de olvidar el envío real o repetir la misma celda con otra cuenta.
2. Exportación parcial inválida: conserva raw y registra export inconclusive antes
   del checkpoint terminal. No inicia otra generación. Un error de filesystem
   permite recuperar los mismos bytes cerrados, sin sustituir la llamada.
3. Diferencia real en historial: la revisión final T recibe los dos intentos públicos,
   incluido el fallido, como N/S/A. Sólo el test vigente valida la entrega final.
   Cada recibo histórico se verifica contra su propio snapshot y se identifica si
   corresponde a los archivos actuales. Sus streams aparecen una sola vez.
4. Discontinuidad del reloj: pausa sin nueva admisión ni presupuesto renovado.
   No se afirma recuperación entre boots: el journal del transport también requiere
   continuidad. La recuperación SIGKILL previamente medida era dentro del mismo boot.
5. Límite individual: el supuesto faltante no se reprodujo; render_prompt ya
   rechazaba más de128000 bytes. Se añade comprobación explícita y un control de
   exceso real antes del dispatch, sin cambiar el techo.
6. T persiste terminal-failure.json antes del checkpoint externo. Releer ese
   fallo no ejecuta otra llamada, incluso si el checkpoint externo fue interrumpido.
7. Diagnóstico de stderr: se mantiene comparación exacta de errores controlados.
   Logs desconocidos detienen la campaña. Substrings podrían confundir texto ajeno
   con una clasificación autorizada. Este límite conservador se declara.

También se integran juicios tipados de documentación10/comunes6/adherenciaN0,S8,T9,A9.
Faltantes o formatos inválidos quedan inconclusos, sin retry ni puntuación imputada.
El driver funcional sólo admite campaña terminal; recibe entrega opaca separada,
ejecuta denominadores reservados61/52 y probe TreeMap, conserva cada invocación
incierta y no devuelve feedback durante generación. D3/D4 requieren juicio README
y recetas públicas ejecutadas; no se ejecuta shell arbitrario del documento.

Verificación03:90 controles host y90 en imagen limpia instalada, sin red/perfiles.
Cuatro invocaciones Docker negativas reales de ejemplos públicos y cuatro lecturas
del mismo recibo, con programa deliberadamente inválido. Cero soluciones del estudio
y cero entregas nuevas de nueve fases. Los máximos sintéticos de revisión final
son110862 bytes RoutePlan y112054 TreeMap; el acumulado de38 inputs admitidos por
la fixture es2491074/2536370 bytes. 3MiB sigue siendo propuesta previa a generación.

Revisión conjunta01: jobbcf0bf4e8cc4449e91e0b21c13f7858e falló antes de iniciar
Gemini con OSError Argument list too long. Sin veredicto ni sustitución de fuente.
Revisión conjunta02 usa una copia de texto de sólo lectura en directorio separado,
job8967f8896007429db22b3062b1c4fa03. Emitió accept, scope conjunto, tests_executed=false,
sin hallazgos y con el mapa exacto de45 fuentes intactas. La aceptación no demuestra
recuperación entre boots ni ejecución literal de comandos shell del README.

Prerregistro registrado2026-10-05T09:08:06.094635+00:00, antes de generación:
experiments/software_comparison_v1/frozen/registration.json, SHA
a21fd1b83c94607f6e11637f94c69a18aa0cb44effee5996e37a52baab6dc113.
Incluye45 fuentes más recibo aceptado,28 celdas fijas,40 llamadas/3MiB/6000s,
imágenes originales y regla de parada. La primera celda N RoutePlan Codex se
lanza después de esta congelación. Todavía no hay veredicto comparativo ni una
entrega T nueva de nueve fases; la goal permanece activa.

## Primer arranque real: fallo anterior al proveedor

La primera admisión del bridge terminó inmediatamente con invalid public model
catalog. Se había enlazado comparison-current-public-catalog.json, un registro de
rutas MCP, donde Codex necesita models[] del catálogo público original. La revisión
conjunta no detectó esta integración errónea. El bridge rechazó antes de feature
preflight o ejecución del proveedor: una admisión de proceso, cero dispatches
observados al modelo y cero archivos de solución. No se atribuye el error a cuota.

La campaña01 se conserva terminal: una fila infra_inconclusive,27 no_iniciadas,
28 filas completas en study-campaign-results-01.json. La primera funcionalidad
queda61 inconclusas, sin imputar ceros como fallos del modelo. No se reabre ese
envío ni se reemplaza su población. Se conserva snapshot de46 fuentes congeladas
y121 archivos raw en study-campaign-startup-01.tar.gz con índice verificable.

Reparación de ingeniería: validar models[], slug único y esfuerzo low antes de
crear la campaña/admitir una llamada. La metadata pública correcta ya utilizada
en controles anteriores se copia con SHA fd219bd9f061278275f528939f82f54d2eb97df4b25c23b022adbe48813d920b,
472512 bytes, sin sesiones ni credenciales. El registro MCP sigue separado e intacto.
La nueva verificación local del catálogo pasó11 controles. Cualquier versión
prospectiva posterior requiere otra revisión y congelación, con las mismas tareas,
identidades, orden, cuentas y presupuestos. No hay solución ni puntuación observada
para seleccionar una réplica favorable; no se declara completada la goal.

Revisión conjunta03 job92561c8419d04e83801a82705aae90fd: accept sobre47fuentes,
tests_executed=false; guard nuevo y selección de metadata pública original. No
garantiza ausencia de otros fallos de pipeline ni acepta una entrega de software.
Verificación limpia posterior:91 controles pasados; preflight real de catálogo y
features en la imagen nativa original pasó sin llamadas a modelos. Prerregistro02
2026-10-05T09:17:56.237379+00:00,48fuentes incluido recibo, SHA
231dbf966a2155c283e671c6de0c3340793b1eaccd19ba30112bcfbb7df30be7.
La primera llamada real de autor usa la misma primera identidad de la población
antes de cualquier solución generada; el intento previo permanece cerrado.
