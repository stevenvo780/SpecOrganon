# Diario incremental de lotes declarados

`organon audit-lot-journal ARCHIVO.json` y la herramienta MCP
`audit_lot_journal(journal)` comparten el auditor de
[`lot_journal.py`](../src/specorganon/lot_journal.py). Reciben operaciones
incrementales sin exigir brazos experimentales, períodos antes/después o
resultados finales. No crean un caso, escriben un ledger ni abren las fuentes
citadas. El diario es un objeto suministrado por quien llama; el módulo no
implementa un almacén de captura inmutable.

```sh
uv run organon audit-lot-journal mi-diario.json
uv run organon audit-lot-journal - < mi-diario.json
uv run python scripts/audit_lot_journal.py mi-diario.json
```

La CLI nativa devuelve JSON en éxito y stderr/código 1 en error. El wrapper
devuelve un informe `valid:false` y código 2 en error. MCP devuelve un error
de herramienta. La lectura de archivo/stdin está limitada a 1 MiB, exige un
archivo regular sin componentes symlink y usa JSON estricto: rechaza claves
duplicadas, no finitos y literales que perderían valor decimal al convertirlos
a float. El transporte MCP aplica la misma frontera JSON del servidor; la
API Python admite también `Decimal` explícito.

## Contrato de esquema 1

Todos los campos de cada objeto son obligatorios; las claves extra se rechazan.

| Objeto | Campos |
| --- | --- |
| Diario | `schema:1`, `classification:"lot_journal_declared_only"`, `journal_id`, `events` |
| Evento | `id`, `stage`, `stage_role`, `actor`, `at_utc`, `inputs`, `outputs`, `balance_tolerance_kg`, `source` |
| Fuente | `source_id`, `locator`, `observed_at_utc`, `method`, `record_sha256` |
| Carga | `load_id`, `material_id`, `kind`, `mass`, `basis:"wet"`, `dry_fraction` |
| Masa | `value`, `unit` (`kg`, `g` o `t`), `uncertainty` |

Los tiempos son declaraciones UTC; el orden de eventos no puede retroceder.
No se impone una relación entre el tiempo de operación y el de observación de
fuente. `record_sha256` es un puntero declarado de 64 caracteres hexadecimales;
no verifica bytes, custodia o autenticidad. Se admiten hasta 2048 eventos y
128 cargas por lado/evento. Los números usan los límites de `field_flows` y
aritmética racional exacta en kg.

Una entrada externa es `feed`, `ingredient` o `water_addition`. Una salida es
`product`, `coproduct`, `residue`, `moisture` o `evaporation`. El ID físico se
declara una sola vez y se consume como máximo una vez. Una transferencia debe
conservar material, tipo, masa, incertidumbre, base y fracción seca; se permiten
unidades equivalentes. Un ID nuevo no autentica que se trate de una carga
física distinta. `evaporation` es terminal: no puede volver a consumirse. El
agua capturada para reutilizarse debe declararse como producto de material
agua y fracción seca cero.

El balance húmedo compara entradas y salidas con la suma de incertidumbres y
la tolerancia declarada. El balance seco se comprueba sólo si todas las
fracciones son conocidas; `null` conserva `pending_missing_dry_fraction`.
`water_addition`, `moisture` y `evaporation` requieren fracción seca cero.
Las fracciones se tratan como coeficientes exactos: su incertidumbre y la
calibración de instrumentos no se modelan ni autentican.

Un resultado `valid:true` sólo certifica consistencia de esas declaraciones.
Conserva `observations_authenticated:false`, `field_scope_complete:false`,
`execution_ready:false` y criterio 3 `not_assessed`. No calcula valor `V`,
ganancia `G`, eficacia causal o aceptación.

## Aplicación alimentaria D-102

[`build_bread_prospectus.py`](../scripts/build_bread_prospectus.py) prepara en
un directorio nuevo un borrador alimentario: matriz de 54 consultas por actor
y dimensión, tres alternativas sin ranking, protocolo de captura y cuatro
obligaciones de ingeniería. Repite el cotejo documental D-100, conserva sus
dos desacuerdos y deja umbrales, márgenes, permisos, baseline y resultados
pendientes. Sus 64 puts constituyen una variante nueva; no extienden el
contrato de 37 puts de D-101.

```sh
uv run python scripts/build_bread_prospectus.py /tmp/mi-prospectus-nuevo
uv run organon audit-lot-journal /tmp/mi-prospectus-nuevo/example_journal.json
```

El ejemplo normaliza fracciones publicadas a una tonelada de trigo; las
cantidades de la segunda operación son inventadas para comprobar aritmética.
No es una receta material, lote observado o piloto. El binding fija 13
archivos al preparar; no implementa admisión estricta o actualización atómica
del manifiesto de 64 puts. Los `put` genéricos conservan su semántica.

El [dossier instalado](../experiments/development/lot_journal_prospectus_2026-09-30/)
registra paridad CLI/MCP, controles negativos y compuertas bloqueadas. La
captura enlazada, consumo real, consentimiento, revisión competente y diseño
prospectivo siguen siendo requisitos para campo. [Preparación de campo](preparacion_campo.md).
