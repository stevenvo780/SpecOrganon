# Contrato común D-099 · dos turnos sobre D-E expuesto

Resuelve íntegramente la tarea D-E adjunta como un único agente. Los tres
brazos reciben la misma tarea, manifiesto y CSV, sin respuestas o resultados
de otros ejecutores. No uses herramientas de modelo, web, subprocess o red.
El CSV estará disponible al código en el directorio de entrada; no está
insertado entero en el prompt. Una sola ejecución genérica de tu análisis
permitirá observarlo antes del segundo turno. No infieras efectos causales
ni simules decisiones de los habitantes o una intervención.

En el primer turno devuelve un objeto JSON con exactamente tres strings:
`analysis_py`, `draft_report_md`, `items_json`. El código usa biblioteca
estándar, recibe un único argumento INPUT_DIRECTORY y lee
`sample_first_complete_week.csv`, `task.md` o `source_manifest.json` allí.
Sólo escribe un objeto JSON finito a stdout; no escribe archivos. Verifica
integridad, filas y continuidad y calcula las magnitudes solicitadas.
Código y items tienen un límite individual de 32 KiB; propuesta total
96 KiB e informe de hasta 1200 palabras. El supervisor conservará los bytes
originales y un revisor inspeccionará el código antes de su único replay.

Para permitir el cotejo numérico común, usa estos campos en stdout:

- `rows`: número entero de observaciones.
- `first_timestamp` y `last_timestamp`: marcas originales en formato
  `YYYY-MM-DD HH:MM:SS`.
- `interval_minutes`: separación esperada entre registros.
- `continuous`: booleano que refleje el cotejo de todos los intervalos.
- `appliances_total_kwh`: energía acumulada de Appliances, Wh/1000.
- `daily_appliances_kwh`: objeto fecha `YYYY-MM-DD` → total diario en kWh.
- `lights_total_kwh`: energía acumulada de lights, como observación adicional.
- `units`: objeto con los tres campos de energía anteriores y valor `kWh`.

Puedes añadir otras observaciones justificadas. No conviertas energía de
intervalo en potencia sin declarar la operación y su base. La corrección
mecánica no sustituye la justificación de recomendaciones, incertidumbre,
seguridad, confort, trabajo o costes.

`items_json` es un array JSON, posiblemente vacío para N/S, con hasta ocho
objetos de claves exactas `id`, `kind`, `text`, `refs`, `data`. `kind` puede
ser problem, assumption, evidence, norm, decision o requirement. Los IDs
son simples, únicos; cada ref sólo nombra un ítem anterior; data es un
objeto JSON finito. Las decisiones de valor propuestas permanecen pendientes.
No incluyas aprobaciones, claves, firmas, confianza, revisiones o avances.
T usa esos ítems como acciones limitadas del tratamiento; N/S no ejecutan
el toolkit y pueden organizarse por iniciativa propia.

El supervisor devolverá en el segundo turno los streams originales del
único replay y, para T, las respuestas reales del toolkit. Entrega entonces
únicamente el informe final como JSON `{"report_md":"..."}`, hasta 1200
palabras. Justifica la recomendación o su suspensión conforme a la tarea,
explicando cualquier fallo. El código del primer turno no se reemplaza;
no hay tercer turno, reparación o nueva tentativa de esa celda.

Se comparten dos solicitudes y 360 segundos de actividad local por brazo,
con la revisión humana fuera del reloj. No hay límite preventivo verificado
de tokens o gasto; su uso y coste se declaran sin inventar equivalencia.
Esto es exploración expuesta de un puente y un tratamiento inicial, no
una comparación confirmatoria, aceptación de GOAL o actuación en campo.
