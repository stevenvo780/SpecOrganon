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

`put` acepta `--ref ID` repetible y `--data '{"clave":"valor"}'` para campos estructurados. `--data` debe ser un objeto JSON. `gate` consulta sin avanzar; `advance` aplica la decisión del motor. `next-task` muestra versiones, entradas y bloqueos. `run` lee un manifiesto JSON y se detiene ante aprobaciones o revisiones pendientes:

```sh
uv run organon next-task ./mi-caso --roles '{"reviewer":"agent:revisor"}'
ORGANON_ALLOW_FIXTURES=1 uv run organon run ./caso-sintetico --manifest workflows/synthetic_full.json --actor agent:ejecutor
```

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

Para pruebas sintéticas se exige crear el caso explícitamente con `--approval-policy fixture` en una ruta no registrada y habilitar `ORGANON_ALLOW_FIXTURES=1` en los procesos de prueba. Solo acepta aprobaciones de `human:fixture`, sin `--signature`; son simulaciones y no autorizan trabajo real. Si la variable falta, el ledger de fixture sigue siendo legible, pero sus aprobaciones no satisfacen las compuertas. Una ruta registrada como caso firmado no puede degradarse a fixture aunque se alteren sus metadatos. El entorno de producción debe omitir esa variable. Un caso firmado rechaza aprobaciones sin firma válida y sin registro externo del caso y su clave pública.

## MCP por stdio

El ejecutable es `.venv/bin/organon-mcp` (o `uv run organon-mcp`). Configúralo como servidor MCP con transporte `stdio`. Publica las 14 herramientas de la tabla. Los parámetros tienen los mismos nombres que las funciones del motor: `init` acepta `approval_policy`, `approval_challenge` devuelve el mensaje canónico y `approve` acepta `signature`. `refs` es una lista de IDs y `data` es un objeto JSON. En MCP, `run` recibe el objeto JSON `manifest` directamente, mientras que la CLI lo lee de `--manifest`. El servidor usa el mismo `ORGANON_APPROVERS_FILE` externo que la CLI para comprobar firmas; el cliente MCP no debe recibir una clave privada.

El servidor solo permite casos dentro de su directorio de trabajo. Para fijar otra raíz, establece `ORGANON_ROOT` con la ruta de un directorio existente al lanzar `organon-mcp`. Las rutas relativas de las herramientas se interpretan desde esa raíz; las absolutas también deben quedar dentro de ella. El servidor resuelve symlinks antes de validar la ruta, por lo que rechaza `..`, rutas absolutas y symlinks que salgan de la raíz. La CLI no aplica este límite, ya que opera directamente sobre las rutas que le entrega el usuario local.
