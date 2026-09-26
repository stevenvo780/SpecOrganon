# Interfaces CLI y MCP

Ambas interfaces llaman las mismas funciones de `specorganon.engine` y `specorganon.runner`. El directorio de un caso contiene `organon.json`, un registro de eventos versionado. Los resultados de la CLI se imprimen como JSON; los errores salen por stderr con código distinto de cero.

## CLI

Tras `uv sync --extra dev`, usa `uv run organon --help` y `uv run organon <comando> --help` para ver los argumentos. Hay 14 operaciones públicas:

| CLI | MCP | Función |
| --- | --- | --- |
| `init` | `init` | Crear el caso con `approval_policy="signed"` por defecto y un `case_id` UUID. |
| `put` | `put` | Añadir o revisar un ítem. |
| `status` | `status` | Leer estado y confianza de aprobaciones. |
| `review` | `review` | Revisar un ítem. |
| `approval-challenge` | `approval_challenge` | Obtener el mensaje exacto para una firma offline. |
| `approve` | `approve` | Registrar una aprobación normativa verificada. |
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

`put` acepta `--ref ID` repetible y `--data '{"clave":"valor"}'` para campos estructurados. `--data` debe ser un objeto JSON. La CLI analiza `--data`, `--roles`, `--expected-deps` y el manifiesto de `run` como JSON estricto: rechaza `NaN`, `Infinity`, `-Infinity`, exponentes que producen infinito y números no nulos que se convertirían en cero. El ledger también rechaza valores no finitos enviados desde Python o encontrados al releer un archivo, así como literales con ese subdesbordamiento; así la CLI no puede informar éxito mientras persiste JSON inválido o un cero creado por la conversión. Los decimales ordinarios siguen la precisión de coma flotante binaria de Python: una medición que requiera exactitud decimal debe usar una representación explícita revisada. Para escribir sobre un caso compartido, indica `--expected-version 0` al crear un ID (o la versión actual al revisarlo) y `--expected-deps '{"problema":1}'` con la versión de **cada** referencia. Si otra escritura cambió el ID o una referencia, `put` rechaza la operación sin crear una revisión inesperada. Con ambas precondiciones completas, reintenta de forma acotada únicamente conflictos de secuencia causados por eventos ajenos a esos ítems. Una llamada sin las precondiciones conserva el comportamiento anterior y puede necesitar un reintento coordinado por el llamador; no declara qué versión del caso vio quien preparó el contenido. Las versiones directas tampoco fijan cambios semánticos de otras partes del caso: un contenido que depende de un snapshot mayor necesita coordinación explícita. En MCP, `put` acepta los objetos opcionales `expected_version` y `expected_deps` con el mismo contrato. `gate` consulta sin avanzar; `advance` aplica la decisión del motor. `next-task` muestra versiones, entradas y bloqueos. `run` lee un manifiesto JSON y se detiene ante aprobaciones o revisiones pendientes:

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

El ejecutable es `.venv/bin/organon-mcp` (o `uv run organon-mcp`). Configúralo como servidor MCP con transporte `stdio`. Publica las 14 herramientas de la tabla. Los parámetros tienen los mismos nombres que las funciones del motor: `init` acepta `approval_policy`, `approval_challenge` devuelve el mensaje canónico y `approve` acepta `signature`. `refs` es una lista de IDs y `data` es un objeto JSON. En MCP, `run` recibe el objeto JSON `manifest` directamente, mientras que la CLI lo lee de `--manifest`. El servidor usa el mismo `ORGANON_APPROVERS_FILE` externo que la CLI para comprobar firmas; el cliente MCP no debe recibir una clave privada.

El servidor solo permite casos dentro de su directorio de trabajo. Para fijar otra raíz, establece `ORGANON_ROOT` con la ruta de un directorio existente al lanzar `organon-mcp`. Las rutas relativas de las herramientas se interpretan desde esa raíz; las absolutas también deben quedar dentro de ella. El servidor resuelve symlinks antes de validar la ruta, por lo que rechaza `..`, rutas absolutas y symlinks que salgan de la raíz. La CLI no aplica este límite, ya que opera directamente sobre las rutas que le entrega el usuario local.
