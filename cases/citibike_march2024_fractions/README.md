# Fracciones descriptivas de Citi Bike, marzo de 2024

Checkpoint de desarrollo D-105, copiado byte a byte de la sonda instalada en
Python 3.12. Conserva el proyecto y los 42 eventos del caso
[de linaje original](../citibike_march2024_lineage/), incluidas su revisión y
su avance históricos. Añade nueve escrituras y un rechazo técnico del antiguo
indicador compuesto: **52 eventos; cero fases aceptadas por el motor vigente**.
La revisión histórica es `legacy_unverified`; el rechazo nuevo no es una
aprobación humana ni afirma que los conteos históricos sean falsos.

## Qué contiene

| Acción declarada en el feed | Numerador | Denominador elegible | Razón exacta reducida |
|---|---:|---:|---:|
| Alquiler habilitado con bicicleta disponible | 1.725.248 | 1.809.036 | 431312/452259 |
| Devolución habilitada con muelle disponible | 1.682.386 | 1.809.036 | 841193/904518 |

Cada acción tiene evidencia e indicador con la misma métrica literal y unidad
`fraction`. [derived_ratios.json](derived_ratios.json) conserva operandos,
contrato, procedencia, racional y representación decimal. Esta última usa
24 decimales, `ROUND_HALF_EVEN`, error absoluto máximo `5e-25` y tolerancia
numérica `1e-24`. Esa precisión de representación no mide incertidumbre del
muestreo ni constituye un umbral de eficacia o de valor.

Las dos evidencias dependen de la versión del denominador y de su numerador.
Los indicadores, la síntesis y las ramas actualizadas del reporte excluyen
transitivamente `i_rows`. Este permanece como historial, con su versión y tipo
intactos. [manifest.json](manifest.json) conserva los nueve puts guardados;
la revisión técnica adicional pertenece a la sonda.

## Evidencia de ejecución

[Dossier D-105](../../experiments/development/citibike_fraction_lineage_2026-09-30/):
el mismo wheel D-102, 24 módulos instalados iguales al código actual, Python
3.11.15/3.12.3. CLI aplicó nueve puts; MCP real descubrió 22 herramientas y
releyó el manifiesto con cero puts y nueve omisiones. Se cotejaron estado,
cinco trazas y nueve compuertas por transporte. Una revisión del denominador
con contenido idéntico invalidó descendientes; las evidencias de exclusiones
y huecos siguieron vigentes. Cambiar o eliminar el archivo de razones produjo
issues y rechazos sin añadir eventos; restituir sus bytes recuperó el estado.
Cuatro negativos del contrato fueron rechazados por entorno.

Los primeros dos intentos fallaron antes de publicar puts por una suposición
incorrecta del constructor sobre los eventos históricos. Sus fuentes, streams
y archivos tar permanecen en el dossier. Los resultados corregidos están en
`repaired_311.json` y `repaired_312.json`; no sustituyen los fallidos.

## Límites y siguiente paso

La unidad es una fila estación-instantánea elegible del archivo de marzo de
2024. No representa estación-minutos, intentos de viaje, acceso vivido o
efecto de una intervención. D-105 calcula desde el JSON publicado; sus flags
de verdad de fuente y cotejo de filas siguen falsos. La repetición posterior
[D-106](../../experiments/development/citibike_raw_count_audit_2026-09-30/)
verifica las filas del Parquet fijado y reproduce el reporte, sin modificar
retroactivamente este ledger ni sus flags.

`n_scope` y `d_reporting` siguen sin aprobación humana verificada. `study`
conserva también el bloqueo por `i_rows` rechazado: la revisión no lo retira
del inventario requerido por esa fase. La nueva
síntesis conserva además el bloqueo `s_rows_pair must link inference and
evidence` en `explain`; no se declara una explicación completa. Faltan
revisiones válidas, criterios, intervención, baseline y resultados de campo.
Aceptación del objetivo completo: **1/5; C2–C5 No demostrados**.
