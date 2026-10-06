# Estado de implementación de autonomía N v2

El contrato PROTOCOL.md y la política pura corregida recibieron aceptación limitada
de Gemini en `evidence/neutral-autonomy-design-01/code-and-design-review-02.json`.
El contrato resuelve F06 a nivel de diseño; no hay admisión para pilotos.
El módulo `src/specorganon/free_control_policy.py` implementa únicamente:

- extracción estricta de `controller-next.json` sin admitirlo como sustancia;
- rechazo de JSON ambiguo, decisiones inválidas, colisión con entrega y tamaño;
- contadores exactos con cinco autores y cuatro revisores compartidos;
- cobro separado de dos medidas, sin director gratis ni reembolso por parser;
- ruta de última actualización medida→auditoría o fallo, según cupos y outcome.
- rechazo previo al parche de continue/review en el quinto turno, y de acciones
  sin recursos para su medida/revisión final.

Las funciones son puras. No persisten reservas, hacen dispatch ni verifican medidas;
reciben el estado que el futuro controlador deberá autenticar por su journal.
`following_measure(passed=True)` expresa una transición de política, nunca verifica
una ejecución. No devuelve éxito, entrega completa, F o superioridad.

La prueba seleccionada registrada en `evidence/neutral-autonomy-design-01/tests-01.*`
incluye estos controles y los del controlador/driver existentes: 69 passed en
el primer snapshot, luego 73 passed en el corregido (`tests-02.*`). No se suman.
No se suma al total de 143 de otro snapshot ni equivale a prueba del ejecutor v2.
No hubo Docker, nuevos sujetos experimentales ni comprobación instalada en esta
prueba. Las invocaciones de revisión de ingeniería se cuentan por separado.

**Pendiente:** resolución del contrato tras revisión, controlador autónomo durable,
clasificación/custodia de batería, historia compatible con D/G, presupuesto exacto
en requests, agotamiento y todas las rutas de crash/reconciliación, integración al
driver instalado con identidad/versión nueva, CLI/MCP/Docker, revisión independiente
de implementación y luego seis pilotos nativos fijos sin reemplazos.

El driver `organon-controls` publicado sigue usando exclusivamente el controlador
staged v1 y su definición provisional; no importa este módulo para ejecutar N.
Una fuente adicional cambia el inventario de paquete: las instalaciones anteriores
de 38 módulos son recibos históricos, no evidencia de instalación de esta candidata.
No adaptar registros antiguos ni atribuir a su wheel este código nuevo.
F06 no está resuelto a nivel de ejecución ni hay competencia empírica demostrada.
La calificación T ≥9/10, evaluación reservada y réplica de la meta siguen pendientes.
