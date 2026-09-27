# Interfaces CLI y MCP

Ambas interfaces llaman las mismas funciones de `specorganon.engine` y `specorganon.runner`. El directorio de un caso contiene `organon.json`, un registro de eventos versionado. Los resultados de la CLI se imprimen como JSON; los errores salen por stderr con código distinto de cero.

## CLI

Tras `uv sync --extra dev`, usa `uv run organon --help` y `uv run organon <comando> --help` para ver los argumentos. Hay 16 operaciones públicas:

| CLI | MCP | Función |
| --- | --- | --- |
| `init` | `init` | Crear el caso con `approval_policy="signed"` por defecto y un `case_id` UUID. |
| `put` | `put` | Añadir o revisar un ítem. |
| `status` | `status` | Leer estado y confianza de aprobaciones. |
| `review` | `review` | Revisar un ítem. |
| `approval-challenge` | `approval_challenge` | Obtener el mensaje exacto para una firma offline. |
| `approve` | `approve` | Registrar una aprobación normativa verificada. |
| `field-attestation-challenge` | `field_attestation_challenge` | Preparar los bytes de una declaración de evaluador externo sobre fuentes de campo. |
| `attest-field` | `attest_field` | Registrar esa declaración firmada; no habilita un veredicto decisivo de campo. |
| `challenge` | `challenge` | Registrar una contradicción. |
| `resolve-challenge` | `resolve_challenge` | Resolver una contradicción. |
| `gate` | `gate` | Consultar una compuerta sin avanzar. |
| `review-phase` | `review_phase` | Revisar una fase. |
| `advance` | `advance` | Avanzar una fase si la compuerta lo permite. |
| `trace` | `trace` | Recorrer dependencias de un ítem. |
| `next-task` | `next_task` | Pedir el siguiente encargo acotado. |
| `run` | `run` | Aplicar un manifiesto reanudable. |

Ejemplo inicial para un caso real:

```sh
uv run organon init ./mi-caso --title "Cadena alimentaria" --domain alimentos --actor agent:analista
uv run organon put ./mi-caso problema --kind problem --text "Pérdida de valor por definir" --actor agent:analista
uv run organon status ./mi-caso
uv run organon trace ./mi-caso problema
```

`put` acepta `--ref ID` repetible y `--data '{"clave":"valor"}'` para campos estructurados. `--data` debe ser un objeto JSON. La CLI analiza `--data`, `--roles`, `--expected-deps` y el manifiesto de `run` como JSON estricto: rechaza claves duplicadas incluso en objetos anidados, `NaN`, `Infinity`, `-Infinity`, exponentes que producen infinito y números no nulos que se convertirían en cero. La relectura del ledger rechaza también claves duplicadas, valores no finitos y literales con ese subdesbordamiento; el registro externo de aprobadores rechaza claves duplicadas. Así la CLI no puede informar éxito mientras persiste JSON inválido, ambiguo o un cero creado por la conversión. Los decimales ordinarios siguen la precisión de coma flotante binaria de Python: una medición que requiera exactitud decimal debe usar una representación explícita revisada. Para escribir sobre un caso compartido, indica `--expected-version 0` al crear un ID (o la versión actual al revisarlo) y `--expected-deps '{"problema":1}'` con la versión de **cada** referencia. Si otra escritura cambió el ID o una referencia, `put` rechaza la operación sin crear una revisión inesperada. Con ambas precondiciones completas, reintenta de forma acotada únicamente conflictos de secuencia causados por eventos ajenos a esos ítems. Una llamada sin las precondiciones conserva el comportamiento anterior y puede necesitar un reintento coordinado por el llamador; no declara qué versión del caso vio quien preparó el contenido. Las versiones directas tampoco fijan cambios semánticos de otras partes del caso: un contenido que depende de un snapshot mayor necesita coordinación explícita. En MCP, `put` acepta los objetos opcionales `expected_version` y `expected_deps` con el mismo contrato. `gate` consulta sin avanzar; `advance` aplica la decisión del motor. `next-task` muestra versiones, entradas y bloqueos. `run` lee un manifiesto JSON y se detiene ante aprobaciones o revisiones pendientes:

```sh
uv run organon next-task ./mi-caso --roles '{"reviewer":"agent:revisor"}'
ORGANON_ALLOW_FIXTURES=1 uv run organon run ./caso-sintetico --manifest workflows/synthetic_full.json --actor agent:ejecutor
```

Además se rechaza un literal como `0.1234567890123456789` si pasarlo por `float` y reserializarlo cambiaría su valor decimal. `0.1`, `1.00`, `1e20` y ceros explícitos siguen admitidos; el cotejo conserva el valor decimal visible del JSON, no exactitud binaria en los cálculos.

El manifiesto de ejemplo es una fixture inventada. Créala en un entorno de prueba con `ORGANON_ALLOW_FIXTURES=1 uv run organon init ./caso-sintetico --title "Prueba" --domain fixture --actor agent:ejecutor --approval-policy fixture`; sus decisiones `human:fixture` no son aprobaciones humanas. Mantén esa variable activa en los procesos de prueba que registren aprobaciones o evalúen compuertas. Las fases son `frame`, `critique`, `study`, `observe`, `explain`, `compare`, `specify`, `build` y `validate`. Los tipos de ítem y requisitos por fase están en [`workflow.py`](../src/specorganon/workflow.py).

## Aprobación firmada de un caso real

Al crear el caso, `init` guarda un `case_id` UUID y devuelve `project_sha256`, el digest de sus metadatos canónicos. `status` también lo expone. El operador comprueba de forma independiente el UUID, esos metadatos y la ruta absoluta canónica del caso antes de registrarlos fuera del repositorio. Configura `ORGANON_APPROVERS_FILE` con la **ruta absoluta** del archivo JSON de confianza en el entorno del proceso CLI o MCP. El esquema 2 registra cada caso por UUID, su ruta y `project_sha256`, y dentro de él mapea cada actor `human:<nombre>` a los 32 bytes crudos de su clave pública Ed25519 codificados en base64:

```json
{
  "schema": 2,
  "cases": {
    "UUID_DEL_CASO": {
      "path": "/ruta/absoluta/canonica/mi-caso",
      "project_sha256": "SHA256_HEX_DE_METADATA_CANONICA",
      "approvers": {
        "human:responsable": "BASE64_DE_32_BYTES_DE_CLAVE_PUBLICA"
      }
    }
  }
}
```

Todos los marcadores se reemplazan por el UUID, la ruta canónica absoluta, el digest de 64 caracteres hexadecimales y la clave pública real del caso. El operador protege la integridad de ese archivo y verifica por un proceso externo la identidad, custodia de clave y facultad de decisión de cada actor. Un registro para otro UUID, otra ruta o metadatos distintos no da confianza a la aprobación. No se guardan claves privadas en el caso, el repositorio, comandos, logs ni solicitudes MCP.

1. Tras revisar la versión vigente de la norma o decisión, solicita el desafío con el actor y el motivo exactos:

   ```sh
   uv run organon approval-challenge ./mi-caso norma1 --actor human:responsable --reason "Decisión y registro externo"
   ```

2. El resultado contiene `algorithm: "Ed25519"`, `encoding: "base64"`, `message_base64`, `message_sha256`, `case_path`, `project_sha256`, `ledger_head_sha256`, `actor`, `item_id` e `item_version`. En un entorno separado bajo control de la persona responsable, decodifica `message_base64`, comprueba su SHA-256 y **lee el mensaje** antes de firmar los bytes originales sin reconstruir el JSON. El mensaje canónico incluye propósito y esquema, decisión `approve`, UUID, ruta canónica y digest de metadatos del caso, cabeza previa del ledger, ID, versión y hash SHA-256 del ítem, actor y motivo. La persona coteja esos datos con el expediente y el registro de confianza, decide según su autoridad y firma. El agente no firma en su nombre.
3. La persona devuelve únicamente la firma Ed25519 de 64 bytes codificada en base64. Registra la decisión con el **mismo** ID, actor y motivo:

   ```sh
   uv run organon approve ./mi-caso norma1 --actor human:responsable --reason "Decisión y registro externo" --signature "BASE64_DE_LA_FIRMA"
   ```

4. Comprueba `status` y `gate`: para el ítem aprobado, `approval_status` pasa a `signed_verified` si la firma corresponde a la revisión y cabeza previa del ledger y si el caso y la clave pública siguen confiados. `approval_trust` indica si la confianza está `configured` o `unavailable`. Si cambia el ledger entre desafío y aprobación, genera un desafío nuevo; lo mismo si cambia el ítem, el caso, el actor o el motivo. Si falta el archivo, se retira la clave del actor o se cambia por otra, la relectura marca la aprobación histórica como `unverified` y las compuertas que la necesitan quedan bloqueadas. Copiar el ledger a otra ruta o alterar sus metadatos tampoco conserva la confianza del registro externo.

La firma prueba control de la clave configurada para ese actor. No prueba por sí sola quién sostuvo la clave, si recibió toda la información ni si tenía competencia para decidir. Esas verificaciones y el registro de autorización pertenecen al proceso humano externo.

### Declaración firmada de fuentes de campo

`field-attestation-challenge` y `attest-field` registran una **declaración**, vinculada a los bytes de un manifiesto, cinco fuentes mínimas, un reporte y las revisiones vigentes de la evaluación y sus antecedentes. `ORGANON_FIELD_ASSESSORS_FILE` apunta a un JSON externo de esquema 1: `cases[case_id]` contiene `path`, `project_sha256` y `assessors`, mapa de actores `assessor:<nombre>` a claves públicas Ed25519 crudas de 32 bytes en base64. El archivo y cada fuente deben tener ruta absoluta canónica, sin enlace simbólico y con un solo enlace físico. El evaluador debe ser distinto del autor de la evaluación y su clave debe diferir de las claves de aprobación normativa. Retirar su clave hace que la firma histórica aparezca sin verificar al releer el caso.

El manifiesto JSON usa `schema:1`, `classification:"field_attestation_sources"` y `sources`, lista de `{role,path,sha256}`. Debe contener exactamente un `plan`, `field`, `registry`, `measurements` y `analysis`; también puede incluir `source_record` y `approval_record`, hasta 2048 entradas y 256 MiB de fuentes en total. El motor coteja hashes de bytes y vuelve a ejecutar el preflight estructural de perjuicios sobre los primeros cuatro JSON. Antes de emitir un desafío firmado exige que los hashes primarios de asignación, equivalencia, exclusiones y mediciones estén presentes exactamente una vez entre los registros fuente abiertos, con el rol correspondiente. Un archivo agregado puede satisfacer varias referencias al mismo hash. El `analysis` debe cumplir el esquema cerrado de [`field_effect_analysis.py`](../src/specorganon/field_effect_analysis.py): el auditor recalcula cada `V` declarado, el `G` **sin ajuste**, y comparaciones descriptivas por celda con márgenes numéricos tipados. El esquema 2 del análisis añade un candidato ajustado reproducible y un intervalo percentilar nominal a partir de un manifiesto de volumen basal; [su contrato](preparacion_campo.md#aritmética-declarada-y-candidato-ajustado) exige registro declarado antes de la ventana `pre`. El auditor de análisis solo comprueba el volumen declarado; para emitir una atestación nueva de esquema 2, el motor exige además sus extractos abiertos. Rechaza declaraciones vacías, faltantes y cifras incoherentes; ambos esquemas conservan `decision_ready:false`. **Ni los hashes ni el cotejo de extractos autentican custodia o veracidad de las fuentes, cobertura y potencia del intervalo ajustado, aprobación de márgenes o condiciones de parada.** El reporte JSON usa `schema:1`, `classification:"independent_field_assessment"`, `case_id`, `assessment_id`, `assessment_version`, `verdict`, `source_manifest_sha256`, `preflight_sha256`, `analysis_sha256` y los campos textuales `source_custody`, `causal_attribution`, `value_metric`, `harms_by_actor_stage`, `costs`, `uncertainty`, `limitations` y `conclusion`. Se comprueban el vínculo de hashes y la presencia de esos campos, no la verdad ni coherencia semántica de su texto.

Cada `source_record` o `approval_record` debe ser un extracto JSON UTF-8 de esquema 1 y clasificación `field_primary_source_content_extract`, con `records` no vacío. Se coteja exactamente un registro tipado por referencia declarada: `allocation`, `baseline_release`, `measurement`, `equivalence` o `excluded_cell`; con `field.service.schema:2`, también `service_row` para cada grupo y período. Para **cada** fila de `baseline_input_volume_manifest` cuando `analysis.schema:2`, se exige un `source_record` abierto cuyo SHA-256 corresponda a `row.source.record_sha256` y un registro `kind:"volume_row"` identificado por `row.source.locator`. Cada par `(record_sha256, locator)` debe ser único. Las filas de volumen deben concordar exactamente en `study_id`, `definition_sha256`, grupo, período, valor numérico, unidad, ventana de inicio y fin, fecha observada, método y locator. Esta obligación es independiente de `field.service.schema:2`. Las mediciones deben concordar en localizador, grupo, período, celda, valor decimal, fecha, método, unidad, denominador e ID de fuente. Las filas `service_row` deben concordar en flujos consumidos, servicio consumido, máximo factible, equivalencia y metadatos de fuente. Los registros extra, ausentes, duplicados o discordantes bloquean el desafío. El [cotejo de extractos](../src/specorganon/field_source_content_audit.py) informa `baseline_volume_input_byte_bound:true` solo tras la coincidencia completa; el cotejo previo de digests informa `false`. Impide aceptar bytes `{}` con hashes rehechos, pero un extracto inventado y autoconsistente todavía puede pasar. No valida documentos originales, captura física, custodia independiente, autoridad de aprobadores ni impacto causal. El gate decisivo firmado sigue bloqueado.

Una declaración firmada queda visible en `status.field_attestations` con `signature_verified` y `binding_current`. El primero se refiere exclusivamente a la firma; el segundo coteja las versiones actuales de los ítems, sin autenticar los archivos fuente actuales. Los análisis y reportes históricos de esquema 1 mantienen su contrato y sus firmas. Una firma histórica de esquema 2 emitida antes del cotejo de `volume_row` no acredita volumen basal vinculado a bytes: hay que aportar los extractos de volumen y emitir y firmar un nuevo desafío para esa afirmación. El gate de `validate` de un caso `signed` **sigue bloqueando** `field/cumplido` y `field/incumplido`, incluso si ambos son verdaderos. El protocolo exige antes un análisis reproducible del efecto ajustado, intervalo y daños, fuentes bajo custodia y aprobación prospectiva de los márgenes; una fixture o un reporte del evaluador no los suplen. `field/no_demostrado` permanece disponible.

`status.field_attestations[].baseline_volume_input_byte_bound` solo es `true` cuando la firma se verifica y los materiales firmados incluyen explícitamente `baseline_volume_input_byte_bound:true`. Una atestación anterior de esquema 2 puede conservar `signature_verified:true` y mostrar `baseline_volume_input_byte_bound:false`; su firma sigue siendo criptográficamente válida para lo que declaró entonces, sin adquirir retroactivamente el cotejo de volumen. El estado no vuelve a abrir las fuentes ni convierte ese indicador en prueba de custodia o de impacto.

La firma cubre la cabeza del ledger **anterior** a la aprobación. Los hashes de eventos detectan roturas de la cadena, pero no hacen al archivo resistente a escritura maliciosa: quien puede editarlo directamente puede borrar eventos posteriores o añadir falsas revisiones y avances de fase, y recalcular los hashes. La firma protege la decisión y el prefijo previo; los actores de `review` y `review-phase` siguen siendo etiquetas autodeclaradas. Para auditar producción, registra fuera del caso la secuencia y cabeza de **cada transición autorizada**, o usa almacenamiento append-only bajo custodia independiente. Protege también el archivo de confianza, cuyo cambio altera la verificación de aprobaciones históricas.

### Ancla externa opcional del ledger

`ORGANON_LEDGER_ANCHORS_FILE` activa la comprobación de una cabeza externa **exacta** en cada lectura CLI, MCP o del motor. Su valor es la ruta absoluta de un JSON separado del directorio del caso. El esquema 1 contiene un registro por UUID:

```json
{
  "schema": 1,
  "cases": {
    "UUID_DEL_CASO": {
      "path": "/ruta/absoluta/canonica/mi-caso",
      "project_sha256": "SHA256_HEX_DE_METADATA_CANONICA",
      "seq": 0,
      "head_hash": "0000000000000000000000000000000000000000000000000000000000000000"
    }
  }
}
```

Para iniciar un caso, deja esa variable sin configurar durante `init`; la CLI rechaza cualquier inicialización si ya está configurada, sin crear el caso. Obtén después una propuesta de registro con `uv run python scripts/ledger_anchor_candidate.py ./mi-caso`. El script valida la cadena local y muestra un `entry` para revisión, pero omite la comprobación del ancla externa solo para poder proponer una cabeza nueva: **no escribe el registro ni autoriza el evento**. Un custodio independiente coteja identidad del caso, intención y legitimidad de cada transición, conserva el archivo fuera del caso con controles de integridad y publica el registro inicial. Solo entonces activa la variable en los procesos CLI y MCP.

Cada escritura autorizada deja el ledger en la secuencia siguiente. La llamada que añadió el evento devuelve su resultado, pero una lectura o escritura posterior falla con `ledger anchor verification failed` hasta que el custodio compruebe esa transición y publique la nueva cabeza. Ejecuta de nuevo el comando pendiente tras la actualización; para un manifiesto, vuelve a llamar a `run` con el mismo archivo y se omiten los pasos ya registrados. **Nunca copies automáticamente la cabeza propuesta al ancla**: un evento insertado directamente y una cadena recalculada también podrían producir una propuesta sintácticamente válida. El verificador rechaza archivos ausentes, malformados o desactualizados y casos firmados no registrados. Una fixture no registrada solo se omite con `ORGANON_ALLOW_FIXTURES=1`; un caso registrado no puede rebajarse a fixture por cambiar metadatos. Si se falsifican o restauran juntos el ledger y el archivo de anclas, este verificador por sí solo no lo detecta: su valor depende de custodia y frescura independientes. Tampoco autentica revisores ni sustituye la aprobación humana.

Para pruebas sintéticas se exige crear el caso explícitamente con `--approval-policy fixture` en una ruta no registrada y habilitar `ORGANON_ALLOW_FIXTURES=1` en los procesos de prueba. Solo acepta aprobaciones de `human:fixture`, sin `--signature`; son simulaciones y no autorizan trabajo real. Si la variable falta, el ledger de fixture sigue siendo legible, pero sus aprobaciones no satisfacen las compuertas. Una ruta registrada como caso firmado no puede degradarse a fixture aunque se alteren sus metadatos. El entorno de producción debe omitir esa variable. Un caso firmado rechaza aprobaciones sin firma válida y sin registro externo del caso y su clave pública.

## MCP por stdio

El ejecutable es `.venv/bin/organon-mcp` (o `uv run organon-mcp`). Configúralo como servidor MCP con transporte `stdio`. Publica las 16 herramientas de la tabla. Los parámetros tienen los mismos nombres que las funciones del motor: `init` acepta `approval_policy`, `approval_challenge` devuelve el mensaje canónico y `approve` acepta `signature`. `refs` es una lista de IDs y `data` es un objeto JSON. En MCP, `run` recibe el objeto JSON `manifest` directamente, mientras que la CLI lo lee de `--manifest`. El servidor usa los mismos registros externos de aprobación y evaluación que la CLI para comprobar firmas; el cliente MCP no debe recibir una clave privada.

El [control de frontera stdio](../experiments/development/mcp_strict_wire_2026-09-27.json) lee cada línea en bytes, con un límite de 8 MiB, y rechaza UTF-8 inválido, claves duplicadas incluso anidadas o escapadas, valores no finitos, subdesbordamiento y pérdida decimal antes del parser del SDK. Comprueba la forma del sobre JSON-RPC y rechaza solicitudes que mezclen `method` con campos de respuesta, lotes, IDs inválidos y campos de sobre extra. En `tools/call`, `put.data`, `put.expected_deps`, `run.manifest` y `next_task.roles` deben llegar como objetos reales, y `put.refs` como lista; las versiones y `challenge_seq` requieren enteros reales, sin conversión de booleanos. Los rechazos se envían como errores JSON-RPC y no ejecutan la herramienta; una línea inválida no impide una petición válida posterior. Los valores de texto dentro de `data` siguen siendo contenido del caso y no se vuelven a interpretar como JSON. El control usa partes internas de `mcp==2.2.0`, versión fijada en el paquete y comprobada con cliente real y wheel instalado en Python 3.11 y 3.12. No autentica el origen del mensaje ni la evidencia que contiene.

Con una topología de directorios estable, el servidor MCP limita los casos a su directorio de trabajo. Para fijar otra raíz, establece `ORGANON_ROOT` con la ruta de un directorio existente al lanzar `organon-mcp`. Las rutas relativas de las herramientas se interpretan desde esa raíz; una ruta absoluta o con `..` se acepta si su destino canónico permanece dentro de ella. Se permiten alias simbólicos estables que resuelvan dentro de la raíz; los que resuelvan fuera se rechazan. En Linux, el servidor abre la raíz y cada componente canónico del caso mediante descriptores de directorio y `O_NOFOLLOW`, y mantiene abierto el descriptor del caso durante la operación MCP mediante `/proc/self/fd`. Cuando `ORGANON_ROOT` está configurado **explícitamente**, el servidor stdio instala antes de atender peticiones una regla Landlock para nuevas escrituras bajo esa raíz; exige ABI 5 o superior y falla al arrancar si no puede imponerla. El [control con cliente MCP real](../experiments/development/mcp_landlock_root_write_2026-09-27.json) confirma que `init`, `put`, `run` y `status` siguen funcionando dentro y que una escritura por el descriptor de un caso trasladado fuera de la raíz se rechaza sin alterar el ledger. Sin `ORGANON_ROOT` explícito se conserva el modo de desarrollo anterior, sin esta regla de escritura. `organon.json`, `.organon.lock` y `.organon.runner.lock` deben ser archivos regulares con un solo enlace físico: se rechazan enlaces simbólicos, archivos con más de un enlace físico, FIFO y otros tipos de archivo. Estas comprobaciones de archivos también se aplican a la CLI, aunque la CLI no restringe los casos a `ORGANON_ROOT`.

La regla Landlock restringe solo al proceso MCP y a sus descendientes: no revoca descriptores de escritura ya abiertos ni restringe a otro proceso del mismo UID. El control nuevo cierra la escritura MCP probada cuando un **caso** fijado se traslada fuera de la raíz; no demuestra seguridad si se mueve la raíz entera o se alteran enlaces físicos internos entre comprobaciones. Por ello la raíz y sus ancestros aún requieren control del operador y ausencia de escritores locales no confiables con el mismo UID. La firma de una aprobación y el ancla externa del ledger verifican otras propiedades del caso, pero no sustituyen esa custodia del sistema de archivos.
