# Estado de implementación de autonomía N v2

La candidata mutable `0.2.0rc3.dev7` implementa el contrato PROTOCOL.md en
`src/specorganon/neutral_autonomy.py`. El driver instalado `organon-controls`
selecciona ese controlador para N y conserva el controlador staged para S.
Los registros nuevos usan schema 2 y fijan protocolo, mandato, límites e
inventario completo de 40 módulos. Los registros antiguos no se reinterpretan.

N puede escribir código, documentación y batería juntos, decidir continuar,
pedir feedback, medir o auditar. Cada decisión consume un turno de autor; no
hay director gratuito. Se conservan cinco autores, cuatro revisores compartidos
y dos medidas propias. La primera medida sella la partición exhaustiva y los
bytes de la batería original; cambios posteriores de entrega invalidan el
resultado anterior. Journal y snapshots conservan reservas y recuperación de
trabajos cerrados. Las solicitudes N y S muestran consumo y recursos restantes.
La pertinencia semántica de la batería necesita auditoría independiente.

La evidencia de ingeniería está en
`evidence/neutral-autonomy-controller-01/engineering-receipt.json`:

- 186 pruebas seleccionadas aprobadas en ocho archivos afectados.
- Tres controles nuevos con medidas Docker reales aprobados tras corregir la
  instrumentación de un contador. Autores y revisores son sintéticos.
- Wheel local, imagen de release y laboratorio Codex con los mismos 40 módulos
  que las fuentes; CLI y MCP stdio verificados, 24 herramientas descubiertas.
- Codex CLI 0.160.0 verificado sin login ni copia de perfiles.
- Aceptación estática de ingeniería de Gemini 3.8 Flash. Después se movió solo
  el contador de un test antes de la aserción deliberadamente fallida; se
  ejecutaron de nuevo sus tres controles. Las fuentes de producción revisadas
  siguen idénticas.

Los primeros fallos de fixtures, logs y archivos originales se conservan.
No se suman snapshots ni se presenta una corrida de 20/20 inexistente.
Los controles mecánicos usaron la imagen histórica fijada en sus fixtures;
las pruebas instaladas de ambas imágenes dev7 se registran por separado.

Esta aceptación no admite una cohorte nativa ni congela la versión completa.
No se ejecutaron nuevos sujetos experimentales. Quedan seis pilotos públicos
N/S fijos con registro prospectivo y admisión, integración T con D/G comunes y
F externo, freeze completo, su propia calificación T >=9/10, comparación
reservada y réplica independiente. La meta sigue activa y no hay superioridad
demostrada. Wheel e imágenes son locales, sin publicación en un registro.
