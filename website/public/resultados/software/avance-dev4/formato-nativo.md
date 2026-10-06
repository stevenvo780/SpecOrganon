# Dev4: formato nativo e integridad del adaptador

Diagnóstico prospectivo público de sintaxis. Tres registros con tres identidades
fijas cada uno, antes de sus llamadas. No son generaciones de software ni revisiones
que acepten fases. Ningún intento fallido se reemplaza.

- Registro 01: tres fallos HTTP400 del esquema de AGY.
- Registro 02: tres salidas nativas con exit0 rechazadas por el adaptador: turnos
  adicionales o ejecución interna de `finish`. No se adoptó `structured_output`.
- Registro 03: guía sintáctica en el prompt, sin flag AGY. Tres respuestas válidas,
  un solo turno y sin herramientas: rechazo por recibo ausente, rechazo por exceder
  el mandato y contenido de autor válido. No son aprobaciones reales.

Se conservan registros, fuentes congeladas y recibos/streams originales de las
nueve llamadas. Las fuentes actuales evolucionaron después del registro03:
parser estricto sin recortar whitespace inválido y transporte schema4 con hashes
vinculados y copia de los mismos bytes. El wheel final instalado pasó 296 controles, el smoke real CLI/MCP24 y una
revalidación offline de los tres transcripts con el parser final. No se presentan
los tres éxitos anteriores como nuevas llamadas de la versión final. La revisión estática04 acepta el snapshot; tests_executed=false. Los rechazos
anteriores y el fallo de preparación sin llamada están preservados.

La suite final pasa 296 controles en el host y otros296 contra el wheel final
instalado en Docker, incluidos los controles del driver versionado. La suite completa no está aprobada.
La mejora de fiabilidad de proyectos requiere otro registro de diez intentos;
la superioridad frente a libre y SDD aún requiere comparación reservada y réplica.

La cohorte01 dev2 terminó: 3/10 entregas, siete fallos, dos tipos de proyecto
y cero reemplazos. RangeAudit pasó 115/115 en dos intentos y LedgerFold 104/104
en uno. Intervalo descriptivo Wilson95: [10.8%,60.3%]. No cumple90% ni
demuestra superioridad. `cohort-terminal-01/` conserva copias de ledgers,
acciones, cierres, entregas y recibos de host con sus hashes. Los paths absolutos
históricos permanecen y no se afirman trasladados. La verificación física se hizo
con el driver congelado y sus43 bindings antes de copiar.
