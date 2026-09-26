# Preparación ejecutable de la matriz N/SDD/toolkit

Los scripts de esta página preparan y comprueban **candidatos de desarrollo** para el diseño de [protocolo_experimental.md](protocolo_experimental.md). No contienen casos reservados, no ejecutan modelos, no cobran, no sellan un registro y no reemplazan evaluadores independientes. El [panel de modelos](panel_modelos_preliminar.md) sigue sin congelar.

## Calendario candidato

[`scripts/plan_confirmatory.py`](../scripts/plan_confirmatory.py) lee un manifiesto JSON de esquema 1 y escribe el calendario en stdout. Requiere cuatro modelos declarados en dos familias con nivel de capacidad bajo y alto, al menos uno **declarado** configurable para esfuerzo bajo/alto por familia, tres hashes de paquetes **visibles** R-F/R-M/R-S y tres hashes separados de soluciones de referencia bajo **custodia propuesta**, digests de contrato, prompts, rúbrica, política de herramientas, guía SDD y toolkit, semilla y un límite común de llamadas a herramientas. Acepta solo formatos y estructura; no lee los archivos ni verifica que un proveedor, control real de esfuerzo, precio, licencia, caso reservado o versión exista. El custodio debe comprobar bytes, capacidades, accesos y autorización antes de cualquier registro.

```sh
uv run python scripts/plan_confirmatory.py MANIFIESTO.json > /ruta/de/desarrollo/calendario-candidato.json
```

El resultado lleva `classification: candidate_schedule_unsealed`, hashes del manifiesto y calendario, IDs de bloque y ejecución, y los límites 80 000 tokens medidos, 5 400 segundos activos y el máximo común de herramientas entregado por el operador. No impone esos límites sobre proveedores; solo los declara para la futura ejecución. Con cuatro modelos de dos esfuerzos genera 432 filas; cada modelo sin control resta 54, siempre conservando casos, brazos, agentes y tres réplicas. En cada estrato modelo × esfuerzo × agente × caso, N, S y T ocupan una vez cada posición a lo largo de las tres réplicas. Los bloques completos se mezclan con una semilla registrada, y cada bloque conserva sus tres brazos en el orden asignado. El calendario completo, que incluye hashes de referencias selladas, es material del custodio y **no se entrega íntegro a los ejecutores**.

## Comprobación de bytes y paquete de una corrida

[`scripts/preflight_assets.py`](../scripts/preflight_assets.py) añade un paso **offline de desarrollo** entre el calendario y cualquier ejecución. Lo usa quien custodia los archivos, no el ejecutor. Su mapa JSON de esquema 1 liga `schedule_sha256` e `input_sha256` con rutas absolutas de los tres paquetes visibles, tres referencias ocultas, contrato, prompt común, prompts N/S/T, rúbrica, política de herramientas, guía SDD y toolkit. Comprueba la identidad completa del calendario y lee los **15 archivos** para comparar sus SHA-256 reales con los digests registrados. El mapa de rutas y los archivos ocultos se mantienen fuera del paquete entregado.

```sh
uv run python scripts/preflight_assets.py calendario-candidato.json mapa-custodio.json --check
uv run python scripts/preflight_assets.py calendario-candidato.json mapa-custodio.json --run-id conf-ID --output-dir /ruta-privada/entrega-nueva
```

`--check` no crea un destino y devuelve `development_asset_preflight_unsealed`. La segunda forma crea un directorio nuevo, con permisos restrictivos, para **un solo** `run_id`. Copia paquete visible del caso, contrato y prompt comunes, prompt de ese brazo y política de herramientas; S recibe además la guía SDD y T recibe el toolkit. N no recibe ninguno de esos dos. Las referencias ocultas, la rúbrica con respuestas, prompts de otros brazos y el calendario íntegro no se copian. El manifiesto final liga archivos verificados, límites e identidad de esa corrida, y conserva `development_release_unsealed`. Si falla una copia, el directorio parcial queda sin manifiesto válido para inspección; no se borra ni se sobrescribe un destino anterior.

El padre del destino debe pertenecer al usuario que ejecuta el script y no permitir escritura al grupo ni a otros. Eso reduce sustituciones por otros usuarios, pero **un proceso hostil con el mismo UID aún puede cambiar rutas o archivos**. La comprobación de hashes tampoco detecta una respuesta oculta incrustada como fragmento o paráfrasis en un archivo visible. Antes de una reserva real hacen falta una revisión humana independiente de los materiales visibles, una cuenta y almacenamiento de custodia separados de los ejecutores, el registro previo inmutable y una entrega con acceso controlado. El resultado local no afirma ninguna de esas garantías.

## Firma offline del diseño candidato

[`scripts/check_study_signature.py`](../scripts/check_study_signature.py) vuelve a verificar los 15 archivos, exige el SHA-256 original de `GOAL.md` y que los bytes del protocolo coincidan con el digest del calendario. `challenge` produce los bytes canónicos en base64 para una firma Ed25519 externa; el mensaje liga propósito, GOAL, protocolo, calendario y roles/digests de activos. No incluye rutas ni contenido de los casos. La herramienta no genera ni lee claves privadas.

```sh
uv run python scripts/check_study_signature.py challenge calendario-candidato.json mapa-custodio.json --goal GOAL.md --protocol docs/protocolo_experimental.md
uv run python scripts/check_study_signature.py verify calendario-candidato.json mapa-custodio.json --goal GOAL.md --protocol docs/protocolo_experimental.md --attestation constancia-firmada.json --trust /ruta-externa/claves-publicas.json
```

La constancia de esquema 1 tiene `key_id`, `message_sha256` y `signature_base64`; el archivo de confianza separado contiene las claves públicas autorizadas por el operador. `verify` comprueba la firma y publica el SHA-256 de la clave y del **contenido JSON canonizado** de la confianza (este último no equivale necesariamente al hash de bytes del archivo). Ambas salidas dicen `development_*_unsealed`: la verificación criptográfica acredita control de la clave suministrada, **no** identidad o autoridad del firmante, fecha anterior a las ejecuciones, custodia independiente ni autorización de presupuesto. La firma real, el origen de la clave, la aprobación normativa y un registro temporal independiente siguen pendientes.

## Auditoría de recibos declarados

[`scripts/audit_run_receipts.py`](../scripts/audit_run_receipts.py) recibe el calendario y un JSON con intentos declarados por `run_id`. Comprueba IDs y versiones previstos, sesiones y solicitudes únicas, secuencia de reintentos solo tras caída externa, tiempos UTC, límites **por invocación** y los diez cupos adicionales del estudio. Dentro de cada bloque verifica que un brazo no empiece antes de que el anterior termine o trunque, incluidos sus reintentos. Para contar tokens suma entrada y salida de cada llamada y trata entrada de caché y razonamiento como subconjuntos, sin contarlos dos veces. Informa las corridas sin recibo, truncamientos, excesos y el pico de corridas simultáneas declaradas frente al límite de cuatro. Conserva los intentos fallidos y el gasto total aunque un reintento válido tenga su propio límite.

```sh
uv run python scripts/audit_run_receipts.py calendario-candidato.json intentos-de-desarrollo.json > /ruta/de/desarrollo/auditoria-recibos.json
```

El reporte liga el digest canónico de los recibos, pero **no coteja los bytes** de trazas o artefactos ni autentica la telemetría del proveedor, la identidad del modelo, el aislamiento real de sesiones, precios o costes. Tampoco sustituye los eventos de liberación y cierre custodiados exigidos por el protocolo; los tiempos declarados pueden fingirse. `matrix_receipts_complete` solo describe cobertura y ausencia de violaciones en el JSON suministrado: no acredita puntuaciones Q completas. La salida permanece `development_receipt_audit_unsealed` y `criterion_4.status: not_assessed`. Un ejecutor real deberá registrar y proteger trazas originales, normalizar telemetría por proveedor y verificar facturación; el auditor no lo sustituye.

## Análisis de calidad pareada

[`scripts/analyze_confirmatory.py`](../scripts/analyze_confirmatory.py) recibe ese calendario y un JSON con un registro por **cada** ID previsto: `q` entre 0 y 100, o estado explícito `missing`/`truncated`. Una ejecución truncada con artefactos puntuables conserva su `q`; una sin puntuación deja su terna incompleta. El script rechaza IDs omitidos, duplicados o ajenos, puntuaciones inválidas y digests que no coinciden **dentro de los archivos aportados**; todavía no coteja un registro bajo custodia externa.

```sh
uv run python scripts/analyze_confirmatory.py calendario-candidato.json puntuaciones-sinteticas.json > /ruta/de/desarrollo/analisis.json
```

Solo las ternas N/S/T completas entran en las diferencias `Q(T)−Q(S)` y `Q(T)−Q(N)`. Cuando todas las ternas están completas, el efecto medio promedia réplicas por estrato, casos y configuraciones con igual peso, esfuerzos dentro de cada modelo y por último los cuatro modelos con un cuarto cada uno. El IC percentil del 95 % remuestrea **ternas** dentro de cada estrato 10 000 veces con semilla registrada. Si falta una puntuación, publica pares disponibles como descriptivos y omite el estimador principal; nunca sustituye ni imputa. La salida siempre dice `development_analysis_unsealed` y `criterion_4.status: not_assessed`: Q sola no demuestra el aporte sin puntuación ciega doble, errores, trazabilidad, recuperación, intervención humana, tiempo, tokens, coste, ablaciones y custodia externa.

El planificador, comprobador de firma, auditor de recibos y analizador son de lectura sobre los archivos de estudio; el preparador escribe solo al recibir `--run-id` y un directorio nuevo. Las suites `tests/test_plan_confirmatory.py`, `tests/test_analyze_confirmatory.py`, `tests/test_preflight_assets.py`, `tests/test_check_study_signature.py` y `tests/test_audit_run_receipts.py` usan **modelos, hashes, archivos, firmas efímeras, recibos y puntuaciones inventados para desarrollo**. Prueban cobertura, contrabalanceo y orden reproducible, manipulación de bytes y firma, selección de archivos por brazo, reintentos, límites y aritmética pareada. Ninguna abre la reserva ni aporta observaciones confirmatorias. Siguen faltando registro previo bajo custodia independiente, ejecutor aislado con límites reales y telemetría contrastada, recibos de proveedor, doble evaluación ciega, costes y análisis completo de todos los umbrales.
