# Dev12: custodia y entrada instalada T

Este corte es ingeniería parcial prospectiva. Conserva cinco defectos reproducidos
y corregidos, los rechazos originales, el timeout de revisión y las comprobaciones
del código final. **Cero nuevas generaciones de proyectos, sin admisión nativa T,
calificación, versión completa congelada ni superioridad.** F externo y completitud
común reservada permanecen `null`; la meta sigue activa.

## Código y correcciones

La fuente inicial es `5484566e39ff70df43bd3aaf0e6ae318e2e7b86a`; el runtime final
es `2a0153a20fa1a519733671356eb2404270c1c5bd`, versión `0.2.0rc3.dev12`.
El [recibo](engineering-receipt.json) y los [48 pins](final-2-installed-source-pins.json)
identifican los bytes verificados, aunque la integración en main tenga otro SHA.

- F9: revalida al auditor común original antes del primer cierre terminal.
- F10: exige contenedor `exited` con Running/Dead/Restarting exactamente `false`,
  identidad e imagen correctas y custodia durable. Un ciclo incierto mantiene bloqueo.
- F11: el checker público consume metadata y buffers de la misma lectura verificada.
- CT-01: la siguiente solicitud T conserva los buffers verificados. Los campos
  compartidos del recibo apuntan al estado completo y reconstruyen toda la metadata;
  nunca se releen streams sin cotejo ni se recorta contenido para caber.
- TEX-01: N conserva íntegros los requisitos funcionales y documentos, con precedencia
  procedural v2 explícita solo para N, tanto en generación como en auditoría.

No cambian las nueve fases, H separada de D/G, criterios/batería sellados, cuotas
originales, CLOCK_BOOTTIME ni campañas cerradas. La política lifecycle nueva rechaza
journals antiguos: no hay migración ni reanudación silenciosa.

## Verificación final

| Comprobación | Resultado | Recibo |
|---|---:|---|
| Pruebas seleccionadas del host | 593 aprobadas | [final-2-targeted](final-2-targeted.receipt.json) |
| Controles con Docker real y contenido/roles simulados | 17 aprobados | [final-2-actual-docker](final-2-actual-docker.receipt.json) |
| Guardas desde wheel instalada | 70 aprobadas | [final-2-installed-guards](final-2-installed-guards.receipt.json) |
| Módulos instalados en release y Codex | 48 idénticos | [release](final-2-installed-release-receipt.json), [Codex](final-2-codex-modules.receipt.json) |
| CLI, MCP stdio y Codex | help, 24 herramientas, 0.160.0 | [release](final-2-installed-release.receipt.json), [versión](final-2-codex-version.receipt.json) |
| Bootstrap T desde imagen y wheel del host | 10 posiciones sin iniciar; exit2 esperado | [imagen](cut2-installed-T-report.receipt.json), [host](cut2-host-installed-T-report.receipt.json) |
| Instalación editable | rechazada correctamente | [recibo](cut2-editable-refusal.receipt.json) |

Las cuentas se solapan; no se suman como sujetos ni entregas. Las comprobaciones
instaladas usan red desactivada, filesystem de solo lectura y ningún montaje de
credenciales. Las imágenes y wheel dev12 son locales; la última wheel pública
sigue siendo dev5. Wheel final del host: SHA256
`ac776bc9404cfdfbfde893b978710faae20eae521e184454869dc2ffd1c9fa41`.

Los planes son **previews**, con rutas/imágenes originales. Sus diez posiciones
RangeAudit4/LedgerFold3/TopoPlan3 nunca se despacharon. La entrada exige una wheel
instalada, registro fresco y fuentes exactas. Clonar main no permite reabrir un
registro histórico ni convertir una preview en resultado nativo.

## Revisión independiente y evidencia adversa

[Originales](original-partition-verdicts.json): dos particiones Codex rechazadas
por CT-01 alto y TEX-01 medio; una partición Gemini aceptada dentro de sus 16
módulos. El intento de revisión completa terminó [timeout600 sin texto](full-review-original-timeout.json).
Las reproducciones mecánicas conservaron ocho fallos iniciales de F9/F10/F11 y
dos del primer corte dev12. No son generaciones nativas.

Las [dos revisiones delta](independent-review-aggregate.json) aceptaron las
correcciones estáticas dentro de sus cruces. La cobertura distribuida comprende
48 módulos, con 46 byte iguales al corte previo y dos modificados. Esta composición
no se presenta como aceptación independiente de una versión completa; esa puerta
sigue pendiente. El README de uso cambió después del snapshot revisado y no amplía
su aceptación. Se corrige explícitamente la referencia errónea del reviewer a
`docker/codex/compose.yaml`: el archivo real de raíz se leyó en la delta.

Se conserva el output Gemini completo: un job produjo dos bloques JSON idénticos
y mencionó artefactos internos del cliente fuera del snapshot. Los 299 pins del
snapshot permanecieron intactos; esto no afirma ausencia de escrituras internas
del proveedor. Se conservan también fallos intermedios de recursos y un error del
helper que intentó interpretar stdout cuando el rechazo editable venía en stderr.
El corte final pasa las comprobaciones declaradas.

Ocho jobs de ingeniería consumieron modelos: una planificación, una implementación
y seis revisiones, incluido el timeout. No se cuentan dos veces los bloques JSON
duplicados. Duraciones, cuentas y máquina constan en el recibo; tokens y coste
monetario son desconocidos. No se cambió de cuenta ni se reactivó el sondeo local
de cuota Codex. El login observado del volumen original no acredita identidad
o cuota y no admite ejecución nativa.

## Reproducción y pendientes

Desde la raíz de un clon nuevo de main:

```sh
uv sync --frozen --extra dev
uv run --extra dev python -m pytest -q tests/test_dev12_terminal_custody.py tests/test_dev12_partition_regressions.py tests/test_t_native_entry.py tests/test_t_native_pilot.py
docker build -f docker/release/Dockerfile -t specorganon-release:0.2.0rc3.dev12 .
docker compose build codex
docker compose run --rm codex codex --version
```

Los scripts de evidencia conservan los argv y rutas utilizados en esta ejecución.
`validation_cut2.py` es un registro reproducible de aquel workspace; para otro clon
hay que adaptar la raíz y usar otra carpeta de resultados, preservando estos originales.
Verifica este paquete con `sha256sum -c SHA256SUMS` dentro de esta carpeta.

La [auditoría de los ocho criterios](completion-audit.json) mantiene visibles lo
que falta: aceptación independiente completa, diez intentos nativos originales
con al menos nueve completos, controles N/S competentes, comparación reservada,
intervalos simultáneos por generación, funcionalidad no inferior, tiempo comparable
y réplica independiente. Publicar este corte no satisface esas condiciones.

La publicación se acredita mediante un recibo separado en
`goals/publication-main-20261006/`, sin reescribir este snapshot de ingeniería.
