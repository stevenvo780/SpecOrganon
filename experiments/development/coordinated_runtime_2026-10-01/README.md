# D119 — runtime persistente de prototipos coordinados

Plan prospectivo `5f5f44d`; freeze inicial `a343154` conservado junto con sus
resultados y el hallazgo de binding entre intérpretes. La revisión corregida
`7de98c9` se congeló antes de repetir los gates finales: 82 fuentes y extractor
externo, 125 rutas históricas preservadas. GOAL y protocolo conservan sus requisitos. La aceptación sigue en
**C1 técnico D107 preservado; C2–C5 No demostrado; 0/24 celdas formales**.

## Capacidades implementadas

El líder empieza con work vacío y ejecuta init real del core original. Puede
delegar varias veces, reunir efectos por replay y volver a trabajar con los
resultados públicos. Un solo WaveLedger, RunContext, claim attempt1 y binding
inmutable mantienen presupuesto, reloj local, herramientas, historias y
contadores durante todo el run. Los IDs de requests no se reinician por epoch.

Los cuatro roles permanecen disponibles; cada lote selecciona uno o dos
workers realmente elegibles. A usa orden de fase/ID y readiness local, con un
worker por lote. B usa cierre de dependencias y orden de fase/ID; C conserva
su cola de riesgo. B/C pueden solapar requests de workers independientes.
Es la política declarada del adaptador; revise nativo sigue sin un gate de
fases anteriores. Se conservan advance/review e invalidaciones originales,
incluido el audit de downstream inseguro de A.

Ownership disjunto de nodos y archivos; workers sin init/advance/approve.
El broker usa las herramientas originales y aplica su scope en el host antes
de reservar y lanzar. Hay tres copias fijas de case/inputs, una por cada rol
con herramientas: el executable original exige fuentes y work hermanos.
Las delegaciones reciclan sólo work mediante transiciones documentadas y
guardan estado base/merge y recibos nuevos; no duplican fuentes por epoch.

El análisis participante ejecuta bajo sandbox local readonly. El host publica
o retira metrics.json y exige script, métricas y todo work vigente. Merge
retira las métricas del líder; las métricas de ramas no se convierten en las
de la entrega final. El reviewer posterior, sin herramientas, recibe textos
públicos, estado, estructura, métricas y el contenido real de analysis.py,
report.md y sources.json cuando aplica, con tamaños y SHA. Las historias RAW
y el contenido privado de razonamiento no se comparten entre roles.

La publicación requiere análisis final vigente, checker estructural D118 y
finish exitoso. Pausas CAS permiten reanudación desde otro proceso; una
reserva, transporte, herramienta o transición incierta bloquea efectos y
no habilita resend ni repone saldo. Normas quedan pending; terminar el runtime
y entregar archivos no significa aceptar las cuatro fases del prototipo.
El parser aislado valida estructura e historia declarada; no sustituye el
replay nativo completo de readiness y transiciones. El broker integrado
reconstruye los efectos con el core original y coteja el estado observado.

## Entrada pública y ejecución local

`scripts/coordinated_prototype_runtime.py` comprueba el bundle original,
calendario, descriptor, inputs y publicación específica D118 antes de crear
run/inputs o adquirir claim. Liga además las fuentes nuevas del runtime,
incluidos los módulos cargados dinámicamente. La cache conserva nombres de
imports por digest; cada guard vuelve a leer/hashar bytes y a comprobar si
aparecieron imports locales nuevos.

La API inferior `managed_coordinated_prototype` controla declaraciones y
journals locales. **La garantía del paquete D118 requiere el wrapper y su
guard**; un descriptor o digest declarado no autentica custodia ni autoriza
solicitudes pagadas. El CLI sólo admite una ruta declarada fixture y HTTP
127.0.0.1 con puerto explícito. No toma credenciales de proveedores.

Build, prepare, step y status deben usar la ruta exacta del intérprete
registrado en `bundle.json.tool_interpreter`. Cambiarla modifica el shebang
y los bytes de las herramientas originales. El wrapper rechaza esa diferencia
antes de crear inputs/run; el broker coteja los dos SHA declarados en
tool_policy con los launchers esperados, los ejecutables efectivos y cada
reapertura. Los bundles de Python 3.11 y 3.12 se preparan por separado.

Ejemplo de preparación, usando rutas nuevas fuera del checkout:

Crear `configuracion-runtime.json` con estos campos; el bundle del ejemplo
tiene límites compatibles. `ID_DEL_CALENDARIO` debe ser un run_id existente
en el schedule.json generado.

```json
{
  "schema": 1,
  "role_config": {
    "leader": {"max_output_tokens": 128, "max_model_turns": 32},
    "worker-1": {"max_output_tokens": 128, "max_model_turns": 32},
    "worker-2": {"max_output_tokens": 128, "max_model_turns": 32},
    "reviewer": {"max_output_tokens": 128, "max_model_turns": 1}
  },
  "max_epochs": 8,
  "tool_wall_seconds": 5
}
```

```sh
mkdir -m 700 /tmp/mi-runtime
python -I -B scripts/prepare_coordinated_development.py build \
  --destination /tmp/mi-runtime/bundle \
  --configuration experiments/development/coordinated_runtime_2026-10-01/fixture_configuration.json \
  --contract-dir "$PWD/experiments/development/coordinated_contract_2026-10-01/public_contract" \
  --source-freeze-sha256 6724df13d881e46b08c17213e440a5e231eca16c5541abc283f06ae101f4a044
python -I -B scripts/coordinated_prototype_runtime.py prepare \
  --run-dir /tmp/mi-runtime/run --bundle /tmp/mi-runtime/bundle --run-id ID_DEL_CALENDARIO \
  --configuration /tmp/mi-runtime/configuracion-runtime.json --admission-root /tmp/mi-runtime/registro
python -I -B scripts/coordinated_prototype_runtime.py status --run-dir /tmp/mi-runtime/run
```

El padre de las rutas de salida debe ser privado. La configuración cerrada
contiene schema1, role_config (los cuatro roles, max_output_tokens y
max_model_turns), max_epochs y tool_wall_seconds. Límites salen del descriptor.
`tests/coordinated_runtime_fixture.py` aporta un ejemplo completo sintético;
`integration_checks.py` ejecuta los comandos reales con servidor loopback.
Se puede repetir fuera del checkout creando un directorio privado nuevo y
ejecutando `python -I -B integration_checks.py --destination RUTA_NUEVA`
desde este dossier. Ese helper usa el mismo intérprete en build y cada CLI;
conserva todos los argv, streams y trazas de HTTP en la ruta indicada.

## Evidencia y fallos conservados

Los gates `checks/final311_02` y `checks/final312_02` pasan 317 pruebas cada
uno, sin skips: kernel77 + broker33 + engine24 + wrapper26 + planner87 +
builder39 + delivery31. Python3.11:1338.38s; Python3.12:1298.73s.
Ruff, sintaxis y diff pasan en ambos; los 83 registros antes/después son
idénticos, incluidos los 82 del freeze y el propio source_freeze.json.
Los gates `checks/integration311_02` y `checks/integration312_02` completan
los seis pares A/B/C × D-F/D-E por entorno:112 invocaciones CLI,113 respuestas
fixture,791 tokens declarados y69 herramientas cada uno. Ambas capturas pasan
los cuatro comandos y conservan83registros exactos. Son las mismas seis
coordenadas brazo/caso/réplica1 sintética en dos entornos; los IDs y calendarios
son distintos porque los SHA de herramientas en tool_policy incluyen el
shebang con la ruta del intérprete.
No son12celdas R1 formales.

| Modo | D-F requests/tools | D-E requests/tools | Delegaciones | Solapamiento HTTP local |
| --- | --- | --- | --- | --- |
| A | 20/12 | 19/11 | 3 | No |
| B | 19/12 | 18/11 | 2 | Sí |
| C | 19/12 | 18/11 | 2 | Sí |

La revisión independiente reabre los doce runs con sus intérpretes exactos,
verifica publicación/replay, claim inmutable, IDs/saldos globales, métricas
vigentes, todo el inventario original y archivos públicos reales del reviewer.
El archivo conserva37raíces,53.857regulares,12.643blobs y18.735entradas de
metadata (18.234directorios,499symlinks,2FIFO). Tamaño47.929.387B;
SHA256 `f7c7c884c51aefe222e7cc978377a93598d2a456dedb815bffa52f9a8ac6aff7`.
Root coteja todos los bytes/modos/targets y membresía/contenido Tar contra
los originales, sin seguir enlaces ni abrir FIFO. Ver manifest y verificaciones
en `archives/`, `checks/archive_verification.json` y `review/`.

`checks/` registra argv, código de salida, stdout/stderr, intérprete y copia
exacta de fuentes antes/después. `worker_checks/` conserva todos los intentos,
incluidos fallos de fixture, cambios de fuente durante intake y la carrera
reproducida al hacer replay desde dos hilos. Un RLock local en el kernel
serializa core.run y captura/parse de sus streams; el core original no cambia.
Los gates finales y el archivo se detallan en el recibo de este dossier.

La revisión independiente reprodujo prepare aceptado con bundle3.11 y
runtime3.12, sin count/send/claim pero con hashes de tools diferentes de la
política. El probe original y el rechazo después del fix se conservan en
`review/`. Las primeras suites completas alcanzaron el timeout de 1200s;
sus streams parciales permanecen intactos y no cuentan como PASS. La captura
corregida registra TimeoutExpired y exit124, continúa los gates estáticos y
usa un límite de 2400s en la repetición, con menor concurrencia.

Un intake manual falló antes de pytest por `No module named pytest`; su argv
referencia una raíz que no existe. Error y ausencia quedan explícitos en
`worker_checks/engine_intake_failures.json` y `archive_inputs.json`, sin
atribuirle ejecución o archivo. La primera invocación del archiver usó reportes
relativos y falló antes de crear salida; el reintento con rutas absolutas pasó.
El diff de código/docs pasa. El diagnóstico de toda la evidencia conserva
las advertencias por CRLF de fuentes copiadas, sin normalizar esos bytes.

La prueba de integración usa D-F/D-E y sus originales, derivados PDF comunes
y herramientas reales. Respuestas, usage y tarifas de fixture son sintéticos.
Las cantidades quedan nulas con motivo; count0 y flags del control no son
observaciones. El script verifica
efectivamente tamaños/digests del inventario de fuentes y emite JSON finito.
Checker estructural, ejecución readonly y revisión textual no evalúan Q ni
autentican interpretaciones de fuentes, actividad remota, esfuerzo o facturas.

## Límites y siguiente trabajo

El sandbox protege el replay local de código revisado; no aísla completamente
procesos hostiles del mismo UID ni autentica tenants/proveedores. El reloj
compartido y los intervalos de HTTP locales no son la suma de actividad efectiva
de agentes. Los artefactos archivados conservan evidencia, nunca autoridad
reutilizable para claims, leases, firmas o solicitudes.

Siguen pendientes uso/coste/actividad y rutas/modelos/esfuerzos autenticados,
autorización y proyección de gasto; 12 R1 reales, adaptación/freeze y 12 R2,
selección con evaluación independiente, panel/reserva/custodia/jueces y
autoridades competentes, campo causal y transferencia a otro problema real.
Luna realizó únicamente el inventario de 125 rutas históricas, cotejado por
root y revisor; no fue un benchmark de calidad ni una celda experimental.
