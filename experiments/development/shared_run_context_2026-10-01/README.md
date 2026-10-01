# D-111 — presupuesto común y relevos locales

Estado: implementación y verificación en curso. El plan prospectivo es
`7ea1cd5`; la revisión preventiva y enmienda es `d9e89e2`. Base técnica
`053894a8b725224dfa6b603e85dbc7784c07f41f` (D-110).

## Contrato y alcance

Un runner de desarrollo optativo con plan schema:2 comparte un único ledger
de tokens, solicitudes y costo declarado, una única sesión de herramientas y
un único claim local. Ejecuta segmentos secuenciales; pausa explícita y relevo
por checkpoint. Cada rol mantiene su historial; comparte únicamente los
entregables textuales seleccionados por el plan. Las etiquetas líder,
especialista y revisor no prueban identidades o independencia de personas.

El tiempo activo se acumula; cambiar de proceso o rol no repone presupuesto.
La espera pausada se registra aparte y no se llama automáticamente espera
humana. Un segmento activo sin cierre conciliado no puede reanudarse. El
checkpoint rechaza alteraciones, incorporaciones y pérdidas de journals.
El guard del segmento revocado bloquea procesos anteriores; se comprueba el
deadline antes y después de operaciones y al cerrar el segmento.

El conteo HTTP de entrada puede ocurrir antes de conocer que tokens/costo no
permiten una reserva. El límite de solicitudes Responses se comprueba antes
de ese conteo. Sigue sin existir un techo autenticado de facturación remota,
cancelación remota o custodia independiente. El control es cooperativo del
mismo UID, con directorios privados y locks locales.

## Evidencia prevista

- Nuevos módulos y pruebas focales, fuentes guardadas antes de cada intento.
- Capturas de stdout/stderr, códigos, duraciones, comandos y hashes.
- Relevos entre procesos y negativos de checkpoint, presupuesto, plazo,
  incertidumbre e aislamiento de razonamiento, usando proveedores falsos.
- Herramienta local sellada de fixture pública; compatibilidad schema:1.
- Revisión independiente de fuentes estables y de capturas finales.

Los resultados y limitaciones se incorporarán después de cerrar los gates.
`baseline_pins.json` fija 36 entradas: GOAL, protocolo, nueve dependencias del
runner/controles, wheel D-107 y 24 módulos de producción. `quota_routing.json`
es metadata pública de la sonda; no acredita acceso, gasto o generación.

## Aceptación pendiente

**1/5 en el alcance técnico de C1 D-107; C2–C5 No demostrados.** Este cambio
no ejecuta las 24 celdas A/B/C × D-F/D-E × dos rondas × dos repeticiones,
la matriz confirmatoria, ablaciones o Q. No abre material reservado real,
credenciales o historias de otros runtimes; no autoriza gasto, normas,
evaluadores, sitio de campo o publicación externa.

Después del contrato común siguen pendientes la configuración operativa y
telemetría de proveedores de las 24 celdas, dos rondas y selección congelada,
custodia independiente y liberación de reserva nueva, jueces y recursos
humanos autorizados, y baseline e intervención alimentaria reales.
