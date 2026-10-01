# D113 — análisis del participante con estado protegido

Base dec178396a74312a8cf8bb26a67bfbe134fac495, rama work/toolkit-foundation.
GOAL completo leído; D112 verificado como progreso (409 pins iguales a HEAD).
No se modifica GOAL ni protocolo. C1 técnico permanece1/5; C2–C5 pendiente.

## Contrato prospectivo

1. Segunda herramienta sellada, analysis_readonly, elegida por política
   verificada del host, nunca por una ruta/capacidad suministrada por el
   participante. Lee case/inputs/work; cero raíces de escritura. Comparte
   sesión, claim, reservas, tiempo, ledger y topes con la herramienta del método.
   El método conserva escritura de entregables; approve y analyze no se
   añaden como operaciones del driver metodológico.
2. Ejecutar los bytes fijados de work/analysis.py con biblioteca estándar,
   argv [analysis.py, case_dir], sin fork/red ni flexibilidad de sandbox. Para
   D-E es una adaptación común NUEVA y explícita: su contrato antiguo no
   fijaba argv/JSON. El host comprueba JSON estricto/finito y el inventario
   protegido después del proceso, sin confiar en validación del participante.
   Fallo del participante/JSON inválido es dato para revisión, consume cuota
   y no equivale a incertidumbre de infraestructura. Timeout, reserva incierta,
   mutación de fuente/estado o fallo de lanzamiento conservan bloqueo terminal.
3. El host publica metrics.json y proveniencia SHA sólo tras salida válida;
   no ejecuta, modifica ni repara código desde el evaluador. Un análisis
   posterior inválido no promueve métricas viejas como resultado del nuevo
   script. Fuentes y estados no pueden cambiar por el análisis. El sandbox
   local conserva sus límites documentados, no es contenedor ni garantía
   contra código hostil/kernel/otro proceso del mismo UID.
4. Política v2 con perfil fijo por tool y bridge/team con mapa de nombres
   únicos: cada request, reserva, terminal y replay valida herramienta,
   ejecutable, argumentos y perfil. Una sola numeración/cap/contexto. Mantener
   casos v1 y antiguos contratos estrictos; preparar nuevas corridas, no
   alterar recibos anteriores.
5. Configuración preparatoria v2 optativa: se fijan prospectivamente hasta
   64 herramientas/128 solicitudes, iguales para A/B/C, porque el script y
   fuentes/reportes D-F expuestos requieren múltiples bloques. Se preservan
   80k tokens/5400 segundos y techo de costo declarado; v1 sigue16/32. No
   aumenta cuota en una corrida abierta ni autoriza ninguna llamada pagada.
6. Exponer textos completos y páginas de los PDF originales como derivación
   común fija, con hashes/version/licencia y manifest separado; conservar los
   seis inputs D-F/tres D-E originales, sus manifest y tareas sin cambios.
   Nada de soluciones, código o informes históricos en la cápsula visible.
7. Fixtures POSITIVOS identificados: D-E código público D099 intacto; D-F
   fixture nuevo que adapta lectura de textos del código expuesto D094,
   conserva el original y explica cada adaptación. No es código de una
   celda formal ni reparación del participante. Verificador independiente
   recalcula desde CSV/claims/tabla y coteja pasajes; no confía en passed ni
   usa aprobación normativa o Q. Registrar negativos sin reemplazarlos.

## Ownership, gates y parada

Worker1: política/sesión/analyzer y tests propios, sin tocar bridge/team.
Worker2: inputs derivados/fixtures/oráculo y tests propios, sin tocar builder.
Root: selección/mapa/replay bridge/team, configuración/schedule/builder,
integración de ambos casos×A/B/C y registros. Reviewer read-only al estabilizar.
Máximo4 agentes inclroot, código compartido sin revertir cambios ajenos.

Fase → agentes nativos existentes → lectura/ejecución local y revisión:
cuotas2026-10-01T02:50:30.853Z, Codex sin lectura fiable, Gemini96/98%.
No modelo/effort autenticado de subagentes; cero proveedores de experimento.

Freeze de fuentes antes de gates finales. Capturar comandos, tiempos, exit,
streams y fuentes por intento. Tests significativos: aislamiento real contra
escritura de estados/fuentes/journals, dos tools compartiendo límites y replay,
errores/JSON inválido/timeout/tamper, ambas tareas con métricas verificadas,
fuentes/quantidades adulteradas rechazadas y reversión de topes/claims imposible.
Python3.11 + subset3.12, regresión necesaria de v1, Ruff/compile. No suiteglobal
ni rebuildwheel salvo riesgo concreto. Conservar evidencia original de fallos.

Este corte no satisface C paralelo, 24ejecuciones con modelos reales, selección
de candidato, reserva, jueces/autoridades humanas o campo. Siguen siendo parte
obligatoria del objetivo completo. No cerrar GOAL por gates o documentos.
