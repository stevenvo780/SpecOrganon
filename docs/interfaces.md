# Interfaces CLI y MCP

Ambas interfaces comparten el motor, runner y auditor de lotes. El directorio de un caso contiene `organon.json`, un registro de eventos versionado. Los resultados de la CLI se imprimen como JSON; los errores salen por stderr con código distinto de cero.

## CLI

Tras `uv sync --extra dev`, usa `uv run organon --help` y `uv run organon <comando> --help` para ver los argumentos. Hay 22 operaciones públicas:

| CLI | MCP | Función |
| --- | --- | --- |
| `init` | `init` | Crear el caso con `approval_policy="signed"` y `test_gate_policy="signed_report"` por defecto y un `case_id` UUID. |
| `put` | `put` | Añadir o revisar un ítem. |
| `status` | `status` | Leer estado y confianza de aprobaciones. |
| `review` | `review` | Revisar un ítem. |
| `approval-challenge` | `approval_challenge` | Obtener el mensaje exacto para una firma offline. |
| `approve` | `approve` | Registrar una aprobación normativa verificada. |
| `test-execution-challenge` | `test_execution_challenge` | Obtener los bytes exactos de un reporte de ejecución de prueba para firma offline. |
| `record-test-execution` | `record_test_execution` | Registrar el reporte firmado por un ejecutor externo de un test `signed`. |
| `test-observation-challenge` | `test_observation_challenge` | Obtener los bytes exactos de una repetición local para firma de observador. |
| `record-test-observation` | `record_test_observation` | Registrar una repetición firmada, vinculada al reporte y a sus bytes conservados. |
| `field-attestation-challenge` | `field_attestation_challenge` | Preparar los bytes de una declaración de evaluador externo sobre fuentes de campo. |
| `attest-field` | `attest_field` | Registrar esa declaración firmada; no habilita un veredicto decisivo de campo. |
| `challenge` | `challenge` | Registrar una contradicción. |
| `resolve-challenge` | `resolve_challenge` | Resolver una contradicción. |
| `gate` | `gate` | Consultar una compuerta sin avanzar. |
| `phase-review-challenge` | `phase_review_challenge` | Obtener los bytes exactos de una revisión de fase para firma offline. |
| `review-phase` | `review_phase` | Revisar una fase; en un caso firmado exige `--signature`. |
| `advance` | `advance` | Avanzar una fase si la compuerta lo permite. |
| `trace` | `trace` | Recorrer dependencias de un ítem. |
| `next-task` | `next_task` | Pedir el siguiente encargo acotado. |
| `run` | `run` | Aplicar un manifiesto reanudable. |
| `audit-lot-journal` | `audit_lot_journal` | Auditar balances incrementales declarados; lectura sin caso o ledger. |

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
      },
      "phase_reviewers": {
        "agent:revisor": "BASE64_DE_32_BYTES_DE_OTRA_CLAVE_PUBLICA"
      },
      "test_executors": {
        "executor:pruebas": "BASE64_DE_32_BYTES_DE_UNA_TERCERA_CLAVE_PUBLICA"
      },
      "test_observers": {
        "observer:repeticion": "BASE64_DE_32_BYTES_DE_UNA_CUARTA_CLAVE_PUBLICA"
      }
    }
  }
}
```

Todos los marcadores se reemplazan por el UUID, la ruta canónica absoluta, el digest de 64 caracteres hexadecimales y las claves públicas reales del caso. `phase_reviewers`, `test_executors` y `test_observers` son opcionales para leer un expediente antiguo; sin la clave correspondiente no se acepta una nueva revisión de fase, un test `signed` o una observación estricta. Las claves de esos roles no se reutilizan entre actores. El operador protege la integridad de ese archivo y verifica por un proceso externo la identidad, custodia de clave, competencia y separación de cada revisor, ejecutor y observador, así como la facultad de decisión de cada aprobador. Un registro para otro UUID, otra ruta o metadatos distintos no da confianza a las firmas. No se guardan claves privadas en el caso, el repositorio, comandos, logs ni solicitudes MCP.

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

### Evidencia con archivo local y SHA-256

En un caso `signed`, un ítem `evidence` que declare `data.archive` o `data.source_sha256` activa un contrato de bytes: debe aportar ambos campos. `archive` es una ruta relativa canónica dentro del caso, sin componentes vacíos, `.` o `..`, barras invertidas ni ruta absoluta; `source_sha256` contiene exactamente 64 caracteres hexadecimales minúsculos. Por ejemplo:

```json
{"archive":"fuentes/estudio.pdf","source_sha256":"<SHA-256 calculado sobre el archivo conservado>"}
```

Cada cálculo de estado o compuerta comprueba el archivo actual en Linux. La apertura usa descriptores de directorio y `O_NOFOLLOW`; exige un archivo regular con un solo enlace físico y un máximo de 32 MiB, y coteja su identidad antes y después del hash. Si varias evidencias declaran digests diferentes para una misma ruta, todas quedan bloqueadas antes de leerla. Un archivo ausente, alterado, demasiado grande, enlazado o un contrato incompleto genera `issues` en la evidencia y sus dependientes transitivos. Las incidencias cambian la instantánea de las fases afectadas y bloquean su aceptación y avance, incluso si el ledger conserva una revisión firmada anterior. CLI, MCP, desafíos de revisión y el runner consultan el mismo motor. Las lecturas y avances rechazados no reescriben el ledger.

Restaurar exactamente los bytes declarados recupera la instantánea anterior y puede volver a hacer efectiva su revisión. Para sustituir legítimamente una fuente, publica una nueva versión de la evidencia con el archivo y digest nuevos y vuelve a revisar las dependencias afectadas. La evidencia que no declara ninguno de los dos campos conserva el contrato previo; los casos `fixture` no aplican esta comprobación. Un expediente externo que utilizaba `source_sha256` como metadato libre sin archivo debe completar el par o revisar ese campo: ahora queda bloqueado. El cotejo verifica bytes locales: la correspondencia entre texto, datos y documento sigue requiriendo auditoría de contenido, como [la del caso del pan](../scripts/verify_bread_frame.py). Tampoco prueba autenticidad de la publicación, observación de campo, custodia independiente o ausencia de cambios entre la lectura y una escritura posterior por otro proceso del mismo UID.

### Revisión firmada de una fase

En un caso `signed`, una revisión que permita avanzar requiere la clave pública del actor en `phase_reviewers` y un actor distinto de los autores de los ítems de esa fase. Tras comprobar el contenido y la instantánea, el revisor pide `phase-review-challenge RUTA FASE --verdict accept --reason MOTIVO --actor ACTOR`. El resultado incluye `message_base64` y `message_sha256`. El revisor comprueba el mensaje canónico y firma **sus bytes decodificados** fuera del entorno del agente; incluye propósito, UUID, ruta, metadatos, cabeza previa del ledger, fase, hash de la instantánea, veredicto, motivo y actor. Después registra `review-phase RUTA FASE --verdict accept --reason MOTIVO --actor ACTOR --signature FIRMA_BASE64` y comprueba `gate` antes de `advance`. CLI y MCP usan el mismo contrato.

Una nueva escritura entre el desafío y la revisión cambia la cabeza y exige otro desafío. Una firma inválida, ausente o retirada se rechaza al escribir o queda `review_signature_verified:false` al releer; los eventos de revisión antiguos sin firma permanecen visibles como `review_provenance:legacy_unverified`, pero no habilitan `advance` ni mantienen aceptada una fase. Una clave puede demostrar control criptográfico del actor configurado; la diferencia de etiquetas y claves no demuestra independencia real de personas o competencia para evaluar. La firma tampoco valida el juicio ni las fuentes. La política `fixture` admite revisiones sin firma solo para pruebas sintéticas.

### Ejecución firmada de un test

Cada ítem `test` de un caso `signed` declara `data.argv` como lista no vacía de argumentos y `data.command` como el texto exacto `shlex.join(argv)`. `data.passed` no habilita la compuerta. Un ejecutor externo ejecuta `argv` sin shell, recoge el código de salida y los bytes completos de stdout, stderr y artefactos, y prepara un reporte JSON exacto de esquema 1:

```json
{"schema":1,"argv":["python","-m","unittest"],"exit_code":0,"timed_out":false,"stdout_sha256":"<64 hex minúsculos>","stderr_sha256":"<64 hex minúsculos>","artifacts":[]}
```

Cada artefacto opcional declara `{"path":"ruta/relativa/canónica","sha256":"<64 hex minúsculos>"}`. El motor comprueba formato, argumentos y firma; **no** ejecuta el comando ni vuelve a abrir stdout, stderr o archivos para verificar su contenido. El ejecutor es responsable de calcular esos digests a partir de los bytes observados.

Con `ORGANON_APPROVERS_FILE` configurado, solicita `organon test-execution-challenge RUTA ID --report 'JSON' --actor executor:pruebas`, verifica fuera del agente `message_base64` y `message_sha256`, y firma los bytes decodificados con la clave privada del ejecutor. El mensaje canónico tiene propósito `specorganon.test_execution` y liga UUID, ruta y metadatos del caso, cabeza previa del ledger, ID, versión, hash y dependencias del test, actor y reporte completo. Registra con `organon record-test-execution RUTA ID --report 'EL_MISMO_JSON' --actor executor:pruebas --signature FIRMA_BASE64`. Las herramientas MCP `test_execution_challenge` y `record_test_execution` reciben el reporte como objeto JSON y siguen el mismo contrato; ninguna ejecuta el comando.

`status` expone el historial y el estado del test; `next-task` señala `execute_test` cuando falta una ejecución válida. Solo el último reporte **firmado y verificable** de la versión vigente permite pasar si `exit_code` es 0 y `timed_out` es falso. Un fallo firmado posterior bloquea; una firma inválida posterior no reemplaza el último reporte válido. Cambiar el test, retirar la clave o registrar una nueva ejecución vigente puede invalidar `build`, `validate` y sus revisiones anteriores. Los ledgers `signed` antiguos siguen legibles, pero un test sin `argv` o recibo queda bloqueado. La política `fixture` conserva su semántica sintética. La firma acredita el control de la clave configurada y lo que esa clave declaró; no prueba identidad del ejecutor, honestidad del reporte, integridad de su host, validez del test ni una intervención real.

### Repetición observada optativa

Al crear un caso nuevo, `init --test-gate-policy signed_observed` fija una compuerta más estricta para **todos** sus tests. El valor por defecto y los ledgers anteriores mantienen `signed_report` sin añadir un campo a sus metadatos ni cambiar sus firmas. No se activa el modo nuevo editando a mano un caso antiguo: cambiaría la huella registrada y exigiría un caso y firmas nuevos. El modo estricto requiere `data.executable_sha256` y `data.input_tree_sha256` fijados en el ítem antes del reporte, además de `argv` absoluto canónico y `command`.

Tras el reporte firmado, el observador prepara un directorio absoluto nuevo, privado (0700), con `input/` también privado. El SHA-256 del árbol de entrada usa la lista canónica ordenada de directorios y archivos regulares con ruta, digest y tamaño; puede calcularse con `specorganon.test_observation.hash_input_tree`. El [auditor local](../scripts/audit_signed_test_execution.py) repite el comando con el ejecutable sellado bajo Landlock y seccomp, coteja ambos pines antes del lanzamiento y la entrada después, y devuelve un objeto `receipt` de esquema 1 con procedencia del reporte, ruta del bundle, resultado del sandbox y hashes medidos. En este modo el pin de CLI se toma del ítem; si se proporciona `--executable-sha256`, debe coincidir. El auditor conserva el modo anterior con ese argumento obligatorio. `argv[0]` se sustituye por una ruta `procfd` dentro del hijo.

El observador registrado verifica el recibo y los bytes conservados, obtiene `test-observation-challenge RUTA ID --receipt 'JSON' --actor observer:repeticion`, coteja `message_base64` y su SHA-256, firma los bytes decodificados fuera del agente y registra `record-test-observation` con el mismo recibo y `--signature FIRMA_BASE64`. En MCP, `receipt` es un objeto JSON real. CLI/MCP solo registran la firma; **no ejecutan el comando**. El motor reabre de forma acotada y sin seguir enlaces el ejecutable, la entrada, stdout, stderr y los artefactos declarados del bundle al registrar y al releer el caso. Un reporte con hashes inventados, una observación negativa vigente, una entrada o salida alterada, un bundle perdido, una clave retirada o un reporte nuevo bloquean `build` y los usos decisivos del test. El último recibo autenticado del reporte vigente prevalece incluso si luego se pierden sus bytes, por lo que borrar una observación negativa no restaura una positiva antigua. Una nueva observación exige revisión y avance nuevos de las fases dependientes; `next-task` pide `observe_test` para repetirla.

La firma acredita la declaración de una clave configurada y el motor comprueba los bytes **actualmente disponibles**; un observador que controla clave y bundle puede fabricarlos sin ejecutar nada. La diferencia de claves tampoco prueba independencia personal. El auditor local no prueba la corrida histórica, no descarta cambios transitorios de otro proceso del mismo UID, solo hashea artefactos declarados y requiere el sandbox disponible. Custodia de claves, registro, bundle y ancla externa del ledger, así como juicio sobre la validez del test, siguen siendo tareas externas.

Para `signed`, el control de independencia incluye autores de versiones anteriores del mismo ítem aunque otro actor publique una versión vigente idéntica. El snapshot de revisión incluye la identidad del último evento de aprobación **verificado** de cada norma o decisión pertinente. Por eso, revocar una clave y sustituir una aprobación válida requiere revisar y avanzar de nuevo la fase dependiente; la revisión vieja no revive al registrar una segunda aprobación de la misma versión. Una firma inválida posterior no reemplaza la aprobación verificada, ni una aprobación ajena invalida otra fase. El formato nuevo puede dejar una revisión firmada histórica como obsoleta si dependía de aprobaciones cuya procedencia no figuraba en su snapshot anterior; consulta `gate` y consigue una revisión nueva antes de avanzar. Los eventos del ledger no se reescriben.

### Declaración firmada de fuentes de campo

`field-attestation-challenge` y `attest-field` registran una **declaración**, vinculada a los bytes de un manifiesto, cinco fuentes mínimas, un reporte y las revisiones vigentes de la evaluación y sus antecedentes. `ORGANON_FIELD_ASSESSORS_FILE` apunta a un JSON externo de esquema 1: `cases[case_id]` contiene `path`, `project_sha256` y `assessors`, mapa de actores `assessor:<nombre>` a claves públicas Ed25519 crudas de 32 bytes en base64. El archivo y cada fuente deben tener ruta absoluta canónica, sin enlace simbólico y con un solo enlace físico. El evaluador debe ser distinto del autor de la evaluación y su clave debe diferir de las claves de aprobación normativa. Retirar su clave hace que la firma histórica aparezca sin verificar al releer el caso.

El manifiesto JSON usa `schema:1`, `classification:"field_attestation_sources"` y `sources`, lista de `{role,path,sha256}`. Debe contener exactamente un `plan`, `field`, `registry`, `measurements` y `analysis`; también puede incluir `source_record` y `approval_record`, hasta 2048 entradas y 256 MiB de fuentes en total. El motor coteja hashes de bytes y vuelve a ejecutar el preflight estructural de perjuicios sobre los primeros cuatro JSON. Antes de emitir un desafío firmado exige que los hashes primarios de asignación, equivalencia, exclusiones y mediciones estén presentes exactamente una vez entre los registros fuente abiertos, con el rol correspondiente. Un archivo agregado puede satisfacer varias referencias al mismo hash. El `analysis` debe cumplir el esquema cerrado de [`field_effect_analysis.py`](../src/specorganon/field_effect_analysis.py): el auditor recalcula cada `V` declarado, el `G` **sin ajuste**, y comparaciones descriptivas por celda con márgenes numéricos tipados. El esquema 2 del análisis añade un candidato ajustado reproducible y un intervalo percentilar nominal a partir de un manifiesto de volumen basal; [su contrato](preparacion_campo.md#aritmética-declarada-y-candidato-ajustado) exige registro declarado antes de la ventana `pre`. El auditor de análisis solo comprueba el volumen declarado; para emitir una atestación nueva de esquema 2, el motor exige además sus extractos abiertos. Rechaza declaraciones vacías, faltantes y cifras incoherentes; ambos esquemas conservan `decision_ready:false`. **Ni los hashes ni el cotejo de extractos autentican custodia o veracidad de las fuentes, cobertura y potencia del intervalo ajustado, aprobación de márgenes o condiciones de parada.** El reporte JSON usa `schema:1`, `classification:"independent_field_assessment"`, `case_id`, `assessment_id`, `assessment_version`, `verdict`, `source_manifest_sha256`, `preflight_sha256`, `analysis_sha256` y los campos textuales `source_custody`, `causal_attribution`, `value_metric`, `harms_by_actor_stage`, `costs`, `uncertainty`, `limitations` y `conclusion`. Se comprueban el vínculo de hashes y la presencia de esos campos, no la verdad ni coherencia semántica de su texto.

Cada `source_record` o `approval_record` debe ser un extracto JSON UTF-8 de esquema 1 y clasificación `field_primary_source_content_extract`, con `records` no vacío. Se coteja exactamente un registro tipado por referencia declarada: `allocation`, `baseline_release`, `measurement`, `equivalence` o `excluded_cell`; con `field.service.schema:2`, también `service_row` para cada grupo y período. Para **cada** fila de `baseline_input_volume_manifest` cuando `analysis.schema:2`, se exige un `source_record` abierto cuyo SHA-256 corresponda a `row.source.record_sha256` y un registro `kind:"volume_row"` identificado por `row.source.locator`. Cada par `(record_sha256, locator)` debe ser único. Las filas de volumen deben concordar exactamente en `study_id`, `definition_sha256`, grupo, período, valor numérico, unidad, ventana de inicio y fin, fecha observada, método y locator. Esta obligación es independiente de `field.service.schema:2`. Las mediciones deben concordar en localizador, grupo, período, celda, valor decimal, fecha, método, unidad, denominador e ID de fuente. Las filas `service_row` deben concordar en flujos consumidos, servicio consumido, máximo factible, equivalencia y metadatos de fuente. Los registros extra, ausentes, duplicados o discordantes bloquean el desafío. El [cotejo de extractos](../src/specorganon/field_source_content_audit.py) informa `baseline_volume_input_byte_bound:true` solo tras la coincidencia completa; el cotejo previo de digests informa `false`. Impide aceptar bytes `{}` con hashes rehechos, pero un extracto inventado y autoconsistente todavía puede pasar. No valida documentos originales, captura física, custodia independiente, autoridad de aprobadores ni impacto causal. El gate decisivo firmado sigue bloqueado.

Una declaración firmada queda visible en `status.field_attestations` con `signature_verified` y `binding_current`. El primero se refiere exclusivamente a la firma; el segundo coteja las versiones actuales de los ítems, sin autenticar los archivos fuente actuales. Los análisis y reportes históricos de esquema 1 mantienen su contrato y sus firmas. Una firma histórica de esquema 2 emitida antes del cotejo de `volume_row` no acredita volumen basal vinculado a bytes: hay que aportar los extractos de volumen y emitir y firmar un nuevo desafío para esa afirmación. El gate de `validate` de un caso `signed` **sigue bloqueando** `field/cumplido` y `field/incumplido`, incluso si ambos son verdaderos. El protocolo exige antes un análisis reproducible del efecto ajustado, intervalo y daños, fuentes bajo custodia y aprobación prospectiva de los márgenes; una fixture o un reporte del evaluador no los suplen. `field/no_demostrado` permanece disponible.

`status.field_attestations[].baseline_volume_input_byte_bound` solo es `true` cuando la firma se verifica y los materiales firmados incluyen explícitamente `baseline_volume_input_byte_bound:true`. Una atestación anterior de esquema 2 puede conservar `signature_verified:true` y mostrar `baseline_volume_input_byte_bound:false`; su firma sigue siendo criptográficamente válida para lo que declaró entonces, sin adquirir retroactivamente el cotejo de volumen. El estado no vuelve a abrir las fuentes ni convierte ese indicador en prueba de custodia o de impacto.

Las firmas cubren la cabeza del ledger **anterior** a cada aprobación o revisión de fase firmada. Los hashes de eventos detectan roturas de la cadena, pero no hacen al archivo resistente a escritura maliciosa: quien puede editarlo directamente puede borrar eventos o restaurar un prefijo firmado válido y recalcular los hashes. El campo `at` del evento de revisión y el actor del evento `phase_advance` no forman parte del mensaje firmado; tras una revisión válida, un escritor directo también puede añadir un avance y rehacer la cadena local. Por eso `accepted` acredita que hay una revisión de contenido firmada y una secuencia local compatible, no custodia autónoma de la fecha o del avance. Las claves registradas autentican el control de los actores configurados; el evento `review` de un ítem todavía usa una etiqueta autodeclarada. Para auditar producción, registra fuera del caso la secuencia y cabeza de **cada transición autorizada**, o usa almacenamiento append-only bajo custodia independiente. Protege también el archivo de confianza, cuyo cambio altera la verificación histórica.

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

El ejecutable es `.venv/bin/organon-mcp` (o `uv run organon-mcp`). Configúralo como servidor MCP con transporte `stdio`. Publica las 22 herramientas de la tabla. Los parámetros tienen los mismos nombres que las funciones del motor: `init` acepta `approval_policy` y `test_gate_policy`; `approval_challenge`, `phase_review_challenge`, `test_execution_challenge` y `test_observation_challenge` devuelven mensajes canónicos; `approve`, `review_phase`, `record_test_execution` y `record_test_observation` aceptan `signature`. `refs` es una lista de IDs; `data`, `report` y `receipt` son objetos JSON. En MCP, `run` recibe el objeto JSON `manifest` directamente, mientras que la CLI lo lee de `--manifest`. `audit_lot_journal` recibe `journal` sin ruta de caso y sólo comprueba declaraciones; [contrato de lectura](diario_lotes.md). El servidor usa los mismos registros externos de aprobación y evaluación que la CLI para comprobar firmas; el cliente MCP no debe recibir una clave privada.

El [control de frontera stdio](../experiments/development/mcp_strict_wire_2026-09-27.json) lee cada línea en bytes, con un límite de 8 MiB, y rechaza UTF-8 inválido, claves duplicadas incluso anidadas o escapadas, valores no finitos, subdesbordamiento y pérdida decimal antes del parser del SDK. Comprueba la forma del sobre JSON-RPC y rechaza solicitudes que mezclen `method` con campos de respuesta, lotes, IDs inválidos y campos de sobre extra. En `tools/call`, `put.data`, `put.expected_deps`, `run.manifest`, `next_task.roles` y `test_execution_challenge.report`/`record_test_execution.report` deben llegar como objetos reales, y `put.refs` como lista; las versiones y `challenge_seq` requieren enteros reales, sin conversión de booleanos. Los rechazos se envían como errores JSON-RPC y no ejecutan la herramienta; una línea inválida no impide una petición válida posterior. Los valores de texto dentro de `data` siguen siendo contenido del caso y no se vuelven a interpretar como JSON. El control usa partes internas de `mcp==2.2.0`, versión fijada en el paquete y comprobada con cliente real y wheel instalado en Python 3.11 y 3.12. No autentica el origen del mensaje ni la evidencia que contiene.

Con una topología de directorios estable, el servidor MCP limita los casos a su directorio de trabajo. Para fijar otra raíz, establece `ORGANON_ROOT` con la ruta de un directorio existente al lanzar `organon-mcp`. Las rutas relativas de las herramientas se interpretan desde esa raíz; una ruta absoluta o con `..` se acepta si su destino canónico permanece dentro de ella. Se permiten alias simbólicos estables que resuelvan dentro de la raíz; los que resuelvan fuera se rechazan. En Linux, el servidor abre la raíz y cada componente canónico del caso mediante descriptores de directorio y `O_NOFOLLOW`, y mantiene abierto el descriptor del caso durante la operación MCP mediante `/proc/self/fd`. Cuando `ORGANON_ROOT` está configurado **explícitamente**, el servidor stdio instala antes de atender peticiones una regla Landlock para nuevas escrituras bajo esa raíz; exige ABI 5 o superior y falla al arrancar si no puede imponerla. El [control con cliente MCP real](../experiments/development/mcp_landlock_root_write_2026-09-27.json) confirma que `init`, `put`, `run` y `status` siguen funcionando dentro y que una escritura por el descriptor de un caso trasladado fuera de la raíz se rechaza sin alterar el ledger. Sin `ORGANON_ROOT` explícito se conserva el modo de desarrollo anterior, sin esta regla de escritura. `organon.json`, `.organon.lock` y `.organon.runner.lock` deben ser archivos regulares con un solo enlace físico: se rechazan enlaces simbólicos, archivos con más de un enlace físico, FIFO y otros tipos de archivo. Estas comprobaciones de archivos también se aplican a la CLI, aunque la CLI no restringe los casos a `ORGANON_ROOT`.

La regla Landlock restringe solo al proceso MCP y a sus descendientes: no revoca descriptores de escritura ya abiertos ni restringe a otro proceso del mismo UID. El control nuevo cierra la escritura MCP probada cuando un **caso** fijado se traslada fuera de la raíz; no demuestra seguridad si se mueve la raíz entera o se alteran enlaces físicos internos entre comprobaciones. Por ello la raíz y sus ancestros aún requieren control del operador y ausencia de escritores locales no confiables con el mismo UID. La firma de una aprobación y el ancla externa del ledger verifican otras propiedades del caso, pero no sustituyen esa custodia del sistema de archivos.
