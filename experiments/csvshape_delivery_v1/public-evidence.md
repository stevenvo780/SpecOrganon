# Fuentes públicas disponibles antes de generación

Fecha de recopilación: 2026-10-05. Fuente primaria:
https://docs.python.org/3.12/library/csv.html, apartados csv.reader,
Dialect.strict y ejemplos. La lectura documental previa confirmó que reader
devuelve strings sin conversión por defecto, acepta dialecto/delimiter explícitos,
requiere manejo de newline apropiado y dispone de modo strict que eleva errores
de parseo. Esto permite una interpretación operacional reproducible; no demuestra
que todos los productores de CSV, usuarios o dialectos deban usar este contrato.

Fuente de alcance: contract.md y mandate.md de esta identidad, seleccionados por
Codex dentro de la autorización de pruebas reales y proyecto pequeño. Son evidencia
de obligaciones delegadas, no observación de demanda de clientes ni ensayo de campo.
Los dos ejemplos públicos del contrato son datos de prueba propuestos; sus salidas
esperadas son expectativas, todavía no mediciones de programa.

Hipótesis técnica susceptible de refutación: una entrega puede aplicar el contrato
local exactamente, con documentación reproducible, revisión independiente y recibos
reales. La observación posterior de tests propios debe conservar comandos, bytes y
retornos reales. La evaluación reservada es posterior y el autor no accede al corpus.
No existen mediciones preexistentes de CSVShape ni mejoras comparativas demostradas.

## Observación pública del parser, anterior al caso

`parser-observation.json` conserva seis probes deterministas especificados antes
de ejecutar `scripts/csvshape_parser_preflight.py` en Docker/Python3.12.3 sin red
ni perfiles. Resultado real 6/6 (100%, metric `checks_passed_percent`, unit `percent`):
coma citada, newline citado, comilla escapada, rechazo strict de cita sin cierre,
CRLF y strings sin casts. Source, argv, datos, resultados, fecha y recibo reales
constan en ese archivo. Es una medición finita del parser estándar, útil para
fundamentar un indicador del protocolo; no prueba las restricciones añadidas,
CSVShape, documentación, nueve fases, demanda ni un efecto frente a otro método.
La proporción enumerada es exacta para estos seis probes; un punto o intervalo
degenerado no representa un intervalo estadístico ni cobertura de todos los CSV.
No transportar el 100% a otra población, ni usarlo como resultado de la entrega.
