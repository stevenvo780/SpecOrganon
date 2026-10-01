# D113 — precisiones anteriores al freeze final

Plan original e5dd6fe conservado. La revisión previa al freeze identificó:

- Múltiples funciones y política2 requieren calendario DEV2 en bridge/team.
  El builder y los helpers directos rechazan combinaciones legacy antes de
  preparar el ejecutor. La sesión de bajo nivel soporta la política2 explícita
  por separado; no declara compatibilidad de nuevos perfiles con un bridge v1.
- La salida79 del participante no prueba un rechazo de fuente. Tanto sys.exit
  como os._exit ordinarios son feedback reparable si el preflight de script,
  lanzamiento sellado e inventario protegido pasan. Los checks del host y su
  replay ligan esos bytes; ningún código de salida autentica por sí mismo la
  ejecución. Un rechazo transitorio del launcher puede recibir la etiqueta
  participant_failed; stderr se preserva y el siguiente intento valida otra vez.
- Terminación por señal, timeout, fallo de lanzamiento o mutación conservan
  estado bloqueante: no se distingue automáticamente una señal deliberada
  de un límite de recursos o una intervención del host. La recuperabilidad
  comprobada se limita a códigos de salida normales y salida JSON inválida.
- replace es una operación nueva optativa de la herramienta del método:
  política2, digest esperado, sólo analysis.py/report.md/sources.json,
  8192bytes iniciales y append contado posterior. Nunca escribe estados ni
  métricas desde una ruta suministrada por el participante.
- El JSON de métricas D-F y D-E fija nombres/unidades/bases para esta nueva
  preparación mecánica. D-E conserva el código público D099 exacto; D-F es
  una adaptación nueva de lectura. No son una nueva celda formal ni evaluación
  de Q. Originales, manifests/tareas y outputs históricos no se modifican.

Negativos previos se conservan: integración01 (fuente cambió durante un
segmento y fixture intentaba abrir otra sesión sobre stage anclado), y Ruff
de integración02 (estilo histórico de fixtures inmutables). El freeze final
fija el alcance Ruff en fuentes de implementación/tests/capturador; compila
también fixtures sin modificar sus bytes. No reetiquetar esos intentos verdes.
