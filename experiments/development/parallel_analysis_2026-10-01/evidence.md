# D116 — evidencia y pendientes

## Secuencia conservada

Plan `f51026b` precede implementación. Freeze `088bd2a` fija 52 fuentes;
71 rutas anteriores coinciden con D115 `d27936cd`. Root y revisor cotejaron
los pines contra bytes actuales y Git. No hay edición de GOAL o protocolo.

Los modelos experimentales son fixtures HTTP, no modelos autenticados. Los
agentes nativos de construcción son una actividad distinta. Luna produjo el
inventario de preservación; root lo verificó nuevamente, sin inferir calidad
relativa, uso real de API ni factura a partir de esa tarea.

## Intentos previos al freeze

- Broker 3.12 inicial: 31 passed, 49.11 s. Broker 3.11 inicial: 40 passed,
  57.45 s, incluidos nueve tests legacy. Estas versiones preceden el ajuste
  de frescura de todos los archivos no métricos.
- Broker final: 34 passed en 3.11, 66.60 s; 34 passed en 3.12, 63.94 s.
  Ruff y compilación aprobados. Fuentes, stdout/stderr y artefactos se conservan
  directamente en `worker_checks/broker-*`; handoff `broker_handoff.json`.
- Runner estático inicial del broker falló por una ruta de entorno inexistente;
  intento y probes preservados. El segundo runner completó sus gates. No se
  registra el error de entorno como una ejecución de pytest aprobada.
- Adapter/C inicial: 11 passed y 2 failed en 3.11, 237.73 s. Faltaba
  `inputs/tool_policy` schema 2 en el fixture: el CAS no reemplazó el script y
  el siguiente análisis fue bloqueado por SHA distinto. Tras corregir sólo
  el fixture: 13 passed, 206.69 s, fuente estable.
- Integración root `integration01`: 3 failed, 137.11 s. El mismo defecto del
  fixture dejó el stderr real `ToolError: required regular file is absent`.
  Los tres intentos quedaron indeterminate con ocho requests y seis tools;
  no hubo reejecución automática de esos directorios.
- Integración root `integration02`: los tres runtimes cerraron completed con
  once requests y ocho tools; el gate falló por la aserción root que buscaba
  `admissions/claims/*.json`, en vez de los claims reales en
  `admissions/*.json`. La fuente y todos los streams permanecen conservados;
  el gate sigue clasificado fallido, aunque produjo efectos positivos reales.
- Después se añadió preflight al wrapper nuevo: política regular/no-follow,
  JSON estricto ≤128 KiB y esquema entero 2 antes de crear run/branches.
  Seis negativos finales pasaron en ambos intérpretes. El gate final unificado
  debe probar también positivos sobre esa última fuente, no sólo su versión
  anterior. Handoff `engine_handoff.json` registra versiones y comandos.

Ningún intento anterior se sustituye por el posterior. Los snapshots capturan
las fuentes efectivamente usadas. Los runtimes anteriores pueden rechazar
consulta con fuentes actuales distintas: preservar bytes no autoriza restaurar
un claim ni reanudar automáticamente una ejecución con otro cierre de fuentes.

## Gate final y revisión

- Fuente final `088bd2a`: **114 passed en 3.11**, 459.84 s, y **114 passed en
  3.12**, 447.65 s. Ruff, compilación y diff proporcional: exit 0. Las 50 fuentes
  de cada gate permanecen iguales antes/después y concuerdan con el freeze.
- `verified_traces.json` coteja seis corridas físicas distintas: D-F y D-E por
  HTTP más D-E por CLI en cada intérprete. Once requests, ocho herramientas y
  143 tokens reportados por fixtures por corrida; no son uso ni tarifa reales.
  Dos métricas frescas por merge, un claim padre flat, cinco waves con overlap,
  reviewer serial sin razonamiento privado y reparación real del JSON inválido.
- Cálculos documentales: D-F suma 1.000 respuestas de la tabla publicada y
  conserva el manifiesto de 35 páginas; D-E cuenta 1.008 filas y 118.280 Wh de
  la columna Appliances. Son comprobaciones de este fixture, no Q ni efecto
  causal, norma aprobada o resolución de las tareas completas.
- La primera consulta externa usó otro Python y rechazó el launcher exacto
  creado con 3.11. Su traceback original está en la conversación de tools;
  la reproducción capturada exit 1 está en `verification_attempts/`. Las
  verificaciones con cada intérprete declarado dieron exit 0/0. Se conservan
  sus tres filas por separado antes de reunir las seis, sin sobrescribirlas
  ni presentar el primer comando como aprobado. La afinidad del launcher con
  el intérprete registrado es una condición de consulta/reproducción.
- `archives/runtime_manifest.json` y `runtimes.tar.gz`: ocho raíces `/tmp`
  explícitas, 9.739 archivos regulares, 3.580 blobs deduplicados, 4.899 entradas
  de directorio/enlace. Archivo 8.445.310 B, SHA256
  `faaa70c21c2c4b95aee5da8faec2cd35aab5de83e914df4eaefea50d19f3ce07`.
  Root y revisor abrieron todos los blobs; el revisor cotejó cada mapping y
  metadato con las rutas originales. Los artefactos del broker se conservan
  directamente en `worker_checks/`; cachés generadas no forman autoridad ni
  entregables. No hay imagen de sesiones o entorno ni restauración de claims.
- `review.md`: revisión independiente sin P1/P2 abierto en este alcance,
  52/52 fuentes y 71/71 base verificadas, seis trazas y archivo íntegro sin
  diferencias. No es una evaluación externa ciega de los casos.
- El diff staged amplio da exit 2 por whitespace en stderr/tracebacks
  preservados y archivos que los negativos alteran deliberadamente. El diff
  acotado de código, tests, documentación y helpers da exit 0. Se conservan
  bytes originales y ambos resultados en `publication_checks/`; no se presenta
  el control amplio como aprobado ni se normalizan los artefactos alterados.

## Alcance del resultado

C1 técnico D107 conserva su evidencia. C2–C5: No demostrado. Celdas formales
ejecutadas: 0/24. Estas pruebas no autentican modelo/esfuerzo, telemetría
facturada, competencia humana ni Q; no observan una intervención de campo.

El perfil permite sellos y replay en un host cooperativo. No demuestra
aislamiento frente a un atacante con el mismo UID ni custodia externa. Los
archivos conservados son evidencia y no una imagen portátil de autoridad.

Antes de las 24 ejecuciones siguen pendientes el runtime padre desde work
vacío y bootstrap real del líder sin reset, comparabilidad de coordinación,
contrato/rúbrica sin respuestas y ruta/telemetría/autorización. Después R1,
adaptación/freeze R2, selección y evaluación independiente; también campo y
transferencia reales, autoridades competentes y custodia de la nueva reserva.
