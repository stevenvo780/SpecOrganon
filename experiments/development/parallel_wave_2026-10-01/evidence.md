# Alcance de evidencia D114

## Cronología

- Base D113 `b02539ff`, limpia; lectura completa de GOAL y diseño de presupuesto
  y coordinación antes de editar. Plan prospectivo `bce12de`.
- Implementación disjunta: ledger y motor en dos agentes nativos; root integró
  contexto, selección C y CLI. Revisor independiente examinó código y resultados.
  Los agentes de construcción no se cuentan como ejecuciones experimentales.
- Freeze `4e9de575`: 24 pines de código/tests/especificación. Capturas finales
  [3.11](checks/final311/report.json) y [3.12](checks/final312/report.json)
  fijan comandos, stdout/stderr y las 21 fuentes antes/después. Ambas prueban
  231 casos sobre diez archivos; no se repite la suite global ni se reconstruye
  el wheel. Helper de archivo/verificador ejecutados después, sin editar fuentes.
- Seis rutas positivas distintas en [verified_traces.json](verified_traces.json):
  cuatro HTTP de dominios sintéticos y dos subprocess CLI. Tres requests/traza,
  usage y precios sintéticos, overlap local positivo, review posterior,
  contexto factual idéntico, cero items de reasoning privado compartidos,
  norma pending, grafo y hechos byteidénticos a sus pines.
- 7.875 regulares archivados en nueve roots; root y revisor reabrieron todos y
  compararon cada hash/tamaño contra manifest y originales. Symlinks/directorios
  son sólo metadata. No se archivan venvs, env, sesiones ni auth del operador.

## Negativos preservados

| Intento | Observación | Corrección |
| --- | --- | --- |
| worker ledger attempt_01 | expectativa aritmética de coste incorrecta | expectativa corregida; fuente y streams originales retenidos |
| root context_01 | 16 passed / 1 failed; esperaba key held_tokens | assertion usa reserved_tokens del snapshot real; fuente/streams retenidos |
| worker engine attempt_01 | 16 passed / 11 failed | registry explícito necesitaba override al acquire/require; test de JSON no canónico admite rechazo ValueError |
| root integration_01 | 24 passed / 1 failed | CLI separa config JSON público de journals privados/canónicos |
| root integration_02 | 24 passed / 1 failed | fixture de HTTP count añade el object requerido por adapter real; producto rechazó antes de sends |
| control normativo prepatch | norma approved no verificada habilitaba E/R | perfil C rechaza ese estado; control sintético y original en review_inputs |
| enumeración inicial | alias current cambió owner lexical y fue rechazado | verificador/revisor cuentan sólo directorios físicos; primer stderr sólo visible en tool, no se reconstruye como stream |

Otros hallazgos prospectivos P2 no recibieron una ejecución favorable inventada:
se cerraron conservación de respuesta tras guard y publicación tras finish,
con negativos ejecutados sobre el código congelado. [Revisión](review.md).
La inspección inicial que decía que RunContext no necesitaba cambios era errónea;
create/capture/abort dependían de TokenLedger, corregidos con selector durable.

## Inferencias permitidas

Reserva común anterior al primer send, true overlap local mediante threads y
HTTP, conciliación durable, same model/effort solicitado, revisión de artefactos
y bloqueo ante incertidumbre están comprobados en este entorno. El costo es
calculado con tarifas declaradas; no es facturación autenticada. Los cuerpos
conservados son JSON recibido y serializado canónicamente, no TLS/wire packets.

Una respuesta o reviewer textual no establece verdad, calidad o autoridad.
Callbacks no cooperativos pueden seguir activos tras retornar el host; ningún
resultado tardío concilia ni publica. Respuestas remotas nunca observadas o
retornadas después del plazo no se prometen conservar. El claim protege
procesos cooperativos del mismo UID y registry, sin custodia independiente.

El nuevo motor trabaja propuestas sin tools ni publicación al core. No demuestra
C completo para las 24 corridas y no modifica sus calendarios solo. No hubo
proveedor experimental, modelo nuevo, gasto, norma humana, Q, reserva o campo.
Aceptación permanece C1 técnico cumplido, C2–C5 no demostrados.
