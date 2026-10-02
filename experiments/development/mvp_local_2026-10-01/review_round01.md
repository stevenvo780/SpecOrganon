# Revisión independiente de la ronda 1

El subagente nativo `mvp_independent_review` rechazó el corte inicial por:

1. El reporte leía estado y siguiente tarea por separado; una variación de
   confianza externa podía cambiar compuertas sin cambiar el número de
   eventos. Confirmó un resultado incoherente con el ledger intacto.
2. El expediente escolar declaraba `exact_reproduction=0` como observación
   anterior sin haber medido una comparación fallida. También citaba una
   fuente inadecuada para su línea base.
3. Una inferencia escolar hablaba del bloqueo firmado pero sólo enlazaba
   fuentes del análisis escolar.

El revisor comprobó que el análisis escolar sí se reproducía exactamente:
fuente, plan, JSON histórico y JSON actual coincidían con sus hashes. Los
streams y recibos originales de ambas ejecuciones también coincidían.

Aceptó el contenido de entry hasta specify; rechazó build hasta corregir el
reporte. Su validate con `no_demostrado` era una conclusión provisional
fiel, pero no cerraba el criterio de nueve fases. En school aceptó frame y
critique y rechazó study y descendientes hasta corregir evidencias.

La primera prueba del renderer también detectó una referencia a head_hash
no expuesta por get_state; se eliminó ese acceso. El validador de skill no
estaba disponible en el entorno del proyecto por falta de PyYAML; el mismo
validador pasó con el Python del sistema, sin añadir dependencias.

Las correcciones conservan el ledger original mediante versiones nuevas y
los manifests/capturas anteriores sin sobrescribirlos. Ningún resultado
rechazado se cuenta como cierre del hito.
