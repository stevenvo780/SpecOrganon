# Evidencia D117

Clasificación: integración mecánica de desarrollo, con modelos sintéticos y
herramientas reales. **Cero celdas formales de las 24; C2–C5 No demostrado.**
La evidencia técnica D107 se conserva; no se vuelve a ejecutar su instalación
ni se presenta este corte como una nueva evaluación global de C1.

## Fuentes y gates finales

Plan prospectivo `4783701`, aclarado en `c887f7e`, anterior a la implementación.
Freeze `25f87304794721cd7a1ab68816aeadf91a566410`: 55 pines.
Inventario de preservación: 90 pines de D116, preparado por un subagente
`gpt-6-luna` con esfuerzo high y verificado de nuevo por root y revisor.
GOAL, protocolo, core, fuentes originales y árboles D113/D115/D116 coinciden
con la base `ee26beb4cc7cb8788e130f0b0225f32b57a8cd3e`.

| Gate | Python | Resultado pytest | Ruff / syntax / diff | Fuentes before/after |
| --- | --- | --- | --- | --- |
| [`final311`](checks/final311/report.json) | 3.11.15 | 98 passed, 564.41 s | 0 / 0 / 0 | 52 idénticas |
| [`final312`](checks/final312/report.json) | 3.12.3 | 98 passed, 553.74 s | 0 / 0 / 0 | 52 idénticas |

Cada reporte fija commit, intérprete, argv, duración, exit codes y streams.
Los snapshots preservan los bytes usados. Las 98 pruebas son: broker padre 24,
wrapper C 24, engine padre 13, regresiones del broker D116 34 e integración 3.
Se prueban límites globales consumidos por el líder, transporte de fase
equivocada antes de I/O, fuentes/contexto/checkpoint alterados, cierre vacío,
transición y ownership, cache con bytes/imports nuevos y solapes de fuentes/
salidas/registro de admisión. No se repite la suite global, wheel ni instalación.

## Seis trazas físicas de fuentes originales

[`verified_traces.json`](verified_traces.json) reúne D-F HTTP, D-E HTTP con
status CLI y D-E CLI de cada intérprete. Son seis directorios diferentes; los
enlaces `current` no cuentan. Cada verificación usó el intérprete exacto que
generó su launcher: [`trace311`](checks/trace311/report.json),
[`trace312`](checks/trace312/report.json). Sus resultados de tres filas se
conservan además del conjunto de seis.

Por ejecución:

- Work inicial vacío, sin estado/propuesta del caller. El líder hace tres
  requests: lectura real de los primeros 4.096 bytes de `task.md`, init real
  de seis nodos y texto final público. No se afirma que un modelo haya leído
  o comprendido todo el paquete.
- 14 requests, 10 herramientas reales y 182 tokens reportados por fixture,
  bajo un único ledger/contexto/claim. Las tres requests y dos herramientas
  del líder consumen el mismo saldo usado después por los workers y reviewer.
- Cinco lotes de dos requests con overlap HTTP observado y reserva global
  completa antes de los sends. El reviewer es posterior, sin tools ni RAW
  privado ajeno. Los contadores/roles/bindings no se reinician al activar ramas.
- Cuatro análisis readonly: tres JSON válidos y uno inválido corregido por
  reemplazo CAS; la escritura posterior de un reporte vuelve obsoletas sus
  métricas y exige analizar de nuevo. Se exportan dos métricas vigentes con
  fuentes, streams, recibos y procedencia verificables.
- El grafo creado por init coincide con el estado reunido; las normas y fases
  siguen pendientes. Los ordinals globales de herramientas son 1–10. No hay
  claims por rama ni un segundo ledger.

El oráculo documental lee las fuentes públicas originales: D-F conserva
conteo/total de encuesta 1.000 y derivación de 35 páginas PDF; D-E conserva
1.008 filas y 118.280 Wh de appliances en el período. Los scripts, unidades y
contrato de cálculo son fixtures expuestos. Estos cotejos comprueban efectos
del mecanismo, no una solución genérica, Q, causalidad ni autoridad normativa.

## Intentos y correcciones conservados

| Intento | Resultado y corrección |
| --- | --- |
| Broker attempt01 | 18 passed / 1 failed: `os.kill` del fixture produjo PermissionError bajo la política disponible. El negativo de señal se cambió a `os.abort`; no se oculta el resultado original. |
| Broker attempt02 | 20 passed por intérprete, sobre la versión anterior a cache. Snapshots y handoff originales conservados. |
| Broker attempt03-cache | 5 passed / 19 deselected por intérprete: cache revalida bytes e imports candidatos, devuelve mapas separados y conserva init/ordinals. El gate final cubre los 24. |
| C py311 attempt01 | 8 passed / 1 failed: las trazas originales completaron, pero una aserción esperaba que no existiera el directorio privado de admisión. Se corrigió a cero archivos JSON de claim. |
| C attempts02/03 | Negativos de solape físico y cache en ambos intérpretes. No mutan fuentes originales ni árboles de otros agentes. |
| C py311 attempt04 / py312 attempt03 | 9 passed / 15 deselected por intérprete: admission root explícito, alias, defaults y ancestro rechazados antes de mkdir/descriptor/claim. El gate final cubre los 24. |
| Root engine01 | Error de colección: import antes de instalar el path de scripts. No se creó su runtime root; el archivo conserva esa ausencia explícitamente. |
| Root engine02 / engine03 | 12 y 13 passed, respectivamente. El segundo incluye el rechazo del callback de merge que devuelve `{}` tras efectos reales. |
| Root integration01 | Tres fallos de implementación tras 14 requests/10 tools y efectos de merge: el validador exigía JSON canónico al estado original pretty JSON del core. No hubo publicación válida ni reejecución automática de esos runs. |
| Root integration02 | Tres passed tras leer los estados del core con su parser original; journals host siguen canónicos. Los runtimes fallidos y fuentes previas permanecen intactos. |
| Final311 / final312 | 98 passed cada uno sobre el freeze, con Ruff/compile/diff 0 y 52 fuentes estables. |

La revisión independiente cerró solapes de salidas y registro de admisión, y
comprobó la validación de merge antes de finish y al consultar completed.
La fuente final conserva las correcciones; fallos tempranos no se renombraron.
Los stdout/stderr vacíos se conservan como archivos, no como ausencia de datos.

## Archivo completo y cobertura

El archivo [`runtimes.tar.gz`](archives/runtimes.tar.gz) reúne las 13 raíces
temporales existentes señaladas por 14 reportes. La raíz ausente de engine01
es un fallo de colección explícito, no una ejecución positiva vacía.

- 23.985 archivos regulares, 3.568 blobs únicos, 5.827 entradas de metadata.
- 145 symlinks guardados sólo como target/mode, sin seguirlos.
- 10.026.409 bytes; SHA-256
  `cf0a15f817ee35ece3efe438b906c497c066632b6e455afad8e02e6e76a47834`.
- Root reabrió todos los blobs y cotejó todo el inventario, bytes, modos y
  targets contra los originales: [`archive_verification.json`](checks/archive_verification.json).

Los runtimes de negativos del broker se guardan directamente en
`worker_checks/`, fuera del tar. El recibo raíz incluye todos los paths
indexados del dossier salvo exactamente su propio path, incluidos recibos
anidados, snapshots, RAW, fuentes y streams. Los symlinks se fijan por bytes
del target, sin convertir aliases en ejecuciones. La revisión y la verificación
de live/index/HEAD se hacen antes y después del commit final.

## Límites y dependencia siguiente

No hay proveedor experimental autenticado, API externa pagada, campo, reserva,
aprobaciones competentes, factura ni Q. Los subagentes nativos que construyen
el código no son participantes de las 24 celdas. El inventario de Luna no
establece equivalencia de calidad o ventaja de coste.

D117 sólo termina bootstrap, una wave, reviewer y merge del prototipo. El
prototipo y el motor metodológico de nueve fases son modelos distintos; no se
reinterpretan sus fases. Falta integración de continuidad y un contrato común
A/B/C prospectivo. El reloj activo local compartido no acredita actividad
remota ni suma de tiempo de agentes; antes del ensayo deben fijarse medición,
esperas, herramientas y consumo auténticos. Sin aislamiento/custodia externos,
otro actor con el mismo UID puede fabricar o alterar archivos; el archivo
conserva evidencia y no transfiere ni restaura autoridad.

Después siguen rutas/modelos/esfuerzo/versiones/telemetría y autorización,
12 R1, adaptación y freeze R2, 12 R2 y selección; custodia/panel/jueces,
autoridades, banco sellado, campo y transferencia. Este corte no modifica
GOAL/protocolo ni sus umbrales y no habilita las ejecuciones externas.
