# Trabajo posterior a la campaña 02

La campaña registrada terminó por la regla de parada ante un fallo nativo real.
No se abre otra celda, no se reenvía la reparación de TreeMap y no se sustituyen
los seis resultados inconclusos del evaluador. Las 28 filas conservan seis fallos,
una interrupción de infraestructura y 21 celdas no iniciadas. Los dos programas
parciales evaluados no constituyen entregas completas ni comparación concluyente.

## Problemas observados y reparación prospectiva

1. El evaluador usa IDs de recetas como IDs opacos de ejecución. Seis recetas
   tienen puntos o caracteres fuera del conjunto permitido y se rechazaron
   antes de ejecutar. Una futura versión debe derivar un ID ASCII seguro de la
   identidad completa de la receta, conservando el ID original y hashes en el
   recibo. Verificar colisiones, estabilidad, Unicode y los seis formatos
   afectados con controles nuevos; no reemplazar ni recalcular observaciones
   cerradas de esta campaña.
2. El controlador cuenta aprobación normativa y revisión de fase dentro del
   mismo límite de dos intervenciones. En TreeMap T la aprobación y el rechazo
   consumieron el límite: la corrección redactada quedó sin revisar. Una futura
   especificación debe separar los límites por función y mantener un techo
   global explícito. Comprobar que una corrección sustantiva recibe revisión y
   que aprobaciones repetidas/rechazos persistentes no forman un bucle. Es un
   cambio de protocolo; no se aplica retrospectivamente a las celdas congeladas.
3. Los techos de documentos y archivos produjeron fallos reales en N/S/T/A.
   Conservar esos fallos. Revisar instrucciones de concisión y admisión antes
   de otra generación; no aumentar presupuestos de celdas ya observadas.
4. La reparación nativa Gemini agotó 180 segundos, sin stdout/stderr ni respuesta
   válida; el contenedor terminó 137 y no fue OOM. No se conoce la causa remota
   o de cuota. Cualquier cambio de timeout o ruta requiere una especificación
   nueva anterior a ejecución, con la misma atribución de cuentas originales.

## Orden del siguiente hito

- Conservar el snapshot de 48 fuentes y el registro por separado; todos sus
  bytes deben seguir verificables aun cuando se desarrolle otra versión.
- Formular y revisar independientemente las correcciones y sus límites antes
  de modificar el mecanismo. Usar controles técnicos nuevos, no los programas
  o resultados reservados cerrados como feedback de reparación.
- Definir prospectivamente una entrega nueva de nueve fases dentro del mandato
  original, con una sola identidad, criterios, presupuesto y regla de parada.
  No reabrir LogLens, IntervalDesk, RoutePlan o TreeMap para buscar una victoria,
  ni sustituir las 21 celdas no iniciadas en la comparación histórica.
- Completar esa entrega con alternativas sustantivas, revisiones separadas,
  pruebas reales y README reproducible. Un archivo, una fase aceptada o una
  puntuación funcional no cumplen este requisito.
- Preparar la versión CLI/MCP instalada en limpio y el veredicto final por
  criterio. Publicar resultados adversos y límites junto a los positivos.

La publicación intermedia de la campaña 02 está verificada por HTTP y hashes;
no acredita layout mediante navegador ni cierre de la goal. El objetivo de
campo del GOAL.md original y la tesis general siguen sin evidencia suficiente.
