# D-111 — presupuesto común y relevos locales

Estado: implementación y controles locales verificados. El plan prospectivo es
`7ea1cd5`; la revisión preventiva y enmienda es `d9e89e2`. Base técnica
`053894a8b725224dfa6b603e85dbc7784c07f41f` (D-110).

## Contrato y alcance

Un runner de desarrollo optativo con plan schema:2 comparte un único ledger
de tokens, solicitudes y costo declarado, una única sesión de herramientas y
un único claim local. Ejecuta segmentos secuenciales; pausa explícita y relevo
por checkpoint. Cada rol mantiene su historial; comparte únicamente los
entregables textuales seleccionados por el plan. Las etiquetas líder,
especialista y revisor no prueban identidades o independencia de personas.

El tiempo activo se acumula; cambiar de proceso o rol no repone presupuesto.
La espera pausada se registra aparte y no se llama automáticamente espera
humana. Un segmento activo sin cierre conciliado no puede reanudarse. El
checkpoint rechaza alteraciones, incorporaciones y pérdidas de journals.
El guard del segmento revocado bloquea procesos anteriores; se comprueba el
deadline antes y después de operaciones y al cerrar el segmento.

El conteo HTTP de entrada puede ocurrir antes de conocer que tokens/costo no
permiten una reserva. El límite de solicitudes Responses se comprueba antes
de ese conteo. Sigue sin existir un techo autenticado de facturación remota,
cancelación remota o custodia independiente. El control es cooperativo del
mismo UID, con directorios privados y locks locales.

## Resultados

Fuente congelada antes de las capturas finales en
`0498de32a26b59d99c54477bb342aac551801947`: siete pines de fuente/herramientas.
`gates/` conserva comando, duración, código, ocho copias de fuente por gate,
stdout/stderr y SHA. Todos los bytes de fuente permanecieron iguales.

| Gate | Resultado |
|---|---|
| Python 3.11: contexto, equipo, bridge v1 y ledger | 89 passed, 54.85s |
| Python 3.12: contexto, equipo y positivo sellado v1 | 36 passed, 48.66s |
| Ruff: cinco fuentes del cambio y dos capturadores | exit0 |
| Compilación en memoria 3.11/3.12 | exit0 / exit0 |
| diff --check de fuentes/docs/metadata | exit0; logs crudos excluidos |

Los errores impresos en stderr311 son los dos guards CLI esperados
(`execute requires --allow-paid-requests`, `OPENAI_API_KEY is unavailable`),
ejecutados por pruebas con mocks; no son una sonda de credenciales reales.
stderr312 está vacío. No se repitió la suite global; 2674 sigue siendo D-107.

La traza positiva ejecuta cuatro segmentos entre tres roles: un único ledger,
cinco solicitudes conciliadas, 75 tokens y 75 microUSD **declarados** con
precios sintéticos. Una herramienta sellada escribe `report.md`. El líder
recupera su razonamiento propio; el especialista y el revisor reciben los
textos seleccionados, sin el razonamiento de otros roles. Otros controles
cubren resume en nuevo proceso, CAS entre procesos, checkpoint viejo,
alteración de fuentes/journals, lease revocado, tokens/costo/solicitudes/
herramientas consumidos, reloj y reserva incierta. No son generaciones reales.

La revisión independiente verificó los siete pines contra Git y árbol actual,
los cinco gates, todas sus fuentes y streams y todos los miembros regulares
de los dos tar. Sin P1/P2 abierto confirmado en ese alcance local.

## Fallos y conservación

La revisión inicial halló dos P2 del runner, corregidos antes de pytest:
validación de todos los segmentos y claim diferido al primer segmento. Sus
bytes originales están en `static_review_initial/` y en el snapshot del worker.
La primera integración exploratoria dio 25 passed con contexto `29765a4…`.
La revisión encontró después un P2 de tiempo: el cierre podía persistir
active_seconds mayor al tope y volver ilegible el estado.

`unit_context_checks/attempt_01` reproduce ambos bordes contra los bytes
originales: **2 failed/8 deselected, exit1 esperado**. Después del arreglo,
attempt02/03 dan 10 passed en 3.11/3.12; sources, comandos, streams y fallos
están intactos. `.closing` bloquea resume si falla el cierre o su compensación;
no hay reparación automática ni liberación de reservas. Una lectura fresca
de estado active se expone conservadoramente indeterminate; no diagnostica
si el proceso original vive.

| Archivo de fixtures públicas | Regulares | Bytes | SHA256 |
|---|---:|---:|---|
| archives/final311.tar.gz | 3095 | 1755354 | df8b224f9459901c0e44015a0fa2bf402be69491ad9d9bd0ebeb22f85e29d72b |
| archives/final312.tar.gz | 1554 | 873871 | 421e2ef79a1e745de9932461d73412959a3d035080ec7bc7b9e857cbaad2de11 |

Los inventarios verifican todos los bytes reabiertos y las fuentes tras el
archivo. 1301/676 directorios y 69/30 symlinks son solo metadata de nombre/tipo;
no se siguieron links ni guardaron sus destinos o una imagen de directorios
vacíos. Los tar conservan evidencia de archivos regulares; no son una imagen
completa o una restauración ejecutable de esas sesiones.

`baseline_pins.json` fija 36 entradas: GOAL, protocolo, nueve dependencias del
runner/controles, wheel D-107 y 24 módulos de producción. 35 siguen idénticas;
el helper `_invoke_tool` del bridge añade deliberadamente callback opcional
antes/después del lanzamiento. Su valor por omisión mantiene v1, verificado
por los gates. `quota_routing.json` es snapshot de 00:45:42 UTC, sin acceso,
factura o generación autenticados; no se lanzó otro subagente Luna.
Los pines de archivo no son una atestación atómica de bytes ejecutados.

El primer recibo de root omitía las capturas del dossier por filtrar la ruta
absoluta `/workspace`. Se conserva con sus 44 pines en
`receipt_initial_incomplete.json`; `receipt_history.json` describe la reparación
con filtro relativo. El recibo final incluye 166 pines y toda la evidencia
publicada, sin cambiar fuentes, pruebas, streams o archivos comprimidos.

## Aceptación pendiente

**1/5 en el alcance técnico de C1 D-107; C2–C5 No demostrados.** Este cambio
no ejecuta las 24 celdas A/B/C × D-F/D-E × dos rondas × dos repeticiones,
la matriz confirmatoria, ablaciones o Q. No abre material reservado real,
credenciales o historias de otros runtimes; no autoriza gasto, normas,
evaluadores, sitio de campo o publicación externa.

Después del contrato común siguen pendientes la configuración operativa y
telemetría de proveedores de las 24 celdas, dos rondas y selección congelada,
custodia independiente y liberación de reserva nueva, jueces y recursos
humanos autorizados, y baseline e intervención alimentaria reales.
