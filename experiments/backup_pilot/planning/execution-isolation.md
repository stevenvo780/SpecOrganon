# Diseño de aislamiento antes del freeze

Autor: contenedor no privilegiado con volumen/árbol propio montado en /trial.
Se usa --entrypoint para evitar el AGENTS y la skill comunes de /workspace, y
--ignore-user-config para evitar configuración/herencia de herramientas en N/S.
CODEX_HOME conserva el volumen ya autenticado, nunca se copia auth.json. Las
corridas son --ephemeral para no añadir conversaciones de otros brazos al home.
N/S no tienen MCP. T lo configura explícitamente con raíz /trial.
Las fuentes del evaluador y los controles de referencia no se montan al autor.

Evaluación: imagen derivada sin autenticación, sin red, raíz filesystem readonly.
El controlador tiene UID0 únicamente dentro del contenedor; sus fuentes y casos
reservados son root:root y 0700. El código candidato es readonly y las operaciones
candidatas se ejecutan en procesos UID1000/GID1000 con solo su árbol temporal
accesible. El controlador crea/chown archivos de prueba. Así puede matar con
SIGKILL el proceso candidato real, sin que un wrapper Docker huérfano siga escribiendo.
No se monta socket Docker ni fuentes/credenciales del host. Caps limitadas a
SETUID, SETGID, CHOWN, KILL, DAC_OVERRIDE, FOWNER necesarias para controlador y descenso de privilegios.

Tiempo experimental común por etapa: techo de 10 minutos incluido el trabajo
exclusivo del método, más 2 minutos de revisión funcional neutral idéntica por brazo.
T divide su techo de 10 minutos entre autor (8) y auditor del método (2); N/S
pueden dedicar los 10 minutos al autor. El mayor coste de revisión del tratamiento
no se otorga como presupuesto extra. La evaluación automática no entrega resultados
reservados al autor ni entra como asistencia de generación. Sus tiempos se reportan
por separado de la elaboración de la solución.

N/S utilizan una imagen sin /opt/specorganon ni /opt/codex-lab. Solo los contenedores
del modelo requieren la excepción AppArmor y el seccomp específico; el sandbox
Codex permanece activo. El evaluador no usa esa excepción. Evidencia positiva y
negativa de escrituras: development/preflight2-{N,S,T}.jsonl. El preflight de T
detectó una ruta de configuración de aprobaciones MCP incorrecta; debe comprobarse
la corrección antes del freeze.
