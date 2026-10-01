# D-109 — activación de la evaluación pendiente

**Apertura: 2026-09-30 UTC; revisión: 2026-10-01 UTC, después de D-108.** Auditoría y
preparación documental revisables. [Plan](plan.md), [24 celdas](planned_development_cells.json)
y [metadatos públicos de proveedores](provider_readiness.json).

**Resultado: NO-GO para iniciar las corridas.** El inventario está preparado,
pero no es un calendario ejecutable o sellado. Hay **24 celdas planificadas y
cero ejecutadas**: A/B/C × D-F/D-E × dos rondas × dos repeticiones. A/B/C son las
[alternativas de prototipo](../../../docs/alternativas.md), diferentes de los
brazos confirmatorios N/SDD/toolkit. Los pilotos anteriores, incluidos los seis
intentos CLI que solicitaron Luna en D-099, siguen siendo exploración expuesta;
no se les atribuye calidad `Q` ni pertenencia a estas 24 celdas.

La [puerta de activación actualizada](../../../docs/activacion_validacion.md)
corrige el resumen antiguo de 0/5 y 21 operaciones. **Aceptación: 1/5 en el
alcance técnico D-107 de C1; C2–C5 no demostrados.** D-109 no añade pruebas de
funcionamiento, solicitudes experimentales, firmas humanas o campo.

## Qué se verificó en esta auditoría

- GOAL y protocolo conservan sus bytes. El wheel D-107, sus recibos y los
  resultados D-108 se usan como evidencia histórica identificada; no se
  reconstruyen o ejecutan de nuevo.
- La herramienta de cuotas dio un snapshot de Gemini vía Antigravity con 98 %
  disponible en sus dos ventanas. La sonda Codex no tenía datos fiables. Eso no
  demuestra agotamiento ni inutilidad de los subagentes nativos actuales.
- El inventario público de rutas anuncia CLI presentes para Codex, Gemini y
  MiniMax. `agy models` terminó con código 0 y enumeró Flash 3.8 bajo/medio/alto
  y Pro 3.1 bajo/alto, entre otros Gemini. No enumeró Flash-Lite 3.5. Los alias
  locales no autentican ID API, versión, esfuerzo efectivo, uso o factura.
- La documentación de [Luna](https://developers.openai.com/api/docs/models/gpt-6-luna),
  [Sol](https://developers.openai.com/api/docs/models/gpt-6-sol) y
  [Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) contempla
  esfuerzo bajo/alto. Sirve para investigar candidatos; no prueba el acceso de
  esta cuenta ni calidad equivalente entre modelos.
- La [guía Gemini](https://ai.google.dev/gemini-api/docs/thinking) documenta
  bajo/alto para Flash 3.8 y Flash-Lite 3.5. La
  [API MiniMax](https://platform.minimax.io/docs/api-reference/responses-create)
  distingue M3.1 Flash Preview, que ajusta profundidad, de M3/M2.x. La nueva
  versión está restringida actualmente a **M Plan y MiniMax Code**; no se acredita
  acceso por API ordinaria de pago por uso. La ruta M3.1 no fue anunciada por la
  herramienta local; no se selecciona un panel.

Solo se conservan campos públicos o sanitizados en `provider_readiness.json`.
No se abrieron credenciales, configuraciones, sesiones ni paquetes reservados.

## Puertas y entregables que faltan

| Fase | Estado | Entregable necesario y responsable |
| --- | --- | --- |
| Desarrollo de 24 celdas | **NO-GO técnico** | Ejecutor: fijar las instancias públicas D-F/D-E, las versiones A/B/C, instrucciones, modelo/esfuerzo, orden y contrato común de entrega antes de la ronda 1; implementar y verificar límites preventivos compartidos y registro de recursos. Las instancias/modelos y hashes siguen nulos en el inventario. |
| Desarrollo con proveedores o decisiones reales | **NO-GO de recursos/autoridad** | Dueño: aprobar el alcance y techo concreto de gasto, si procede, una vez presupuestada la ruta viable. Operador: demostrar acceso/telemetría. Personas competentes: decisiones normativas y revisiones sustantivas requeridas, con identidad y autoridad comprobables. Una aprobación de gasto no arregla los límites técnicos. |
| Selección y congelación | **Pendiente de resultados** | Ejecutor y revisor: preservar los 24 resultados, negativos y faltantes; justificar cambios antes de la ronda 2; documentar selección y fijar candidato después de ambas rondas. Sin añadir rondas para hacer pasar el resultado. |
| Reserva, C2/C4/C5 | **NO-GO externo y técnico** | Custodio ajeno al desarrollo: casos R-F/R-M/R-S nuevos, banco de 21 inyecciones, referencias y rúbrica fuera de los ejecutores, registro y anclajes independientes. Ejecutor: cuatro modelos de dos familias, capacidades y esfuerzos efectivos, topes globales y telemetría autenticada, matriz solo/trío, réplicas y ablaciones. |
| Evaluación final | **NO-GO externo** | Dos personas ajenas a las ejecuciones: `Q` ciega bloqueada antes de abrir trazas; tercer evaluador para arbitraje según el protocolo. Los revisores de fase y autores no son esos jueces. Custodio: correspondencias opacas y verificación independiente de fuentes/pruebas. |
| Campo, C3 | **NO-GO externo** | Operador alimentario y actores: sitio elegible, permisos, línea base real, seguimiento hasta consumo y valores/perjuicios aprobados. Responsable estadístico: resolver dimensionamiento, potencia y cobertura antes de asignar. Custodio: originales y asignación. |

El panel de cuatro modelos es un requisito del ensayo confirmatorio. Este
inventario de prototipos **no añade ese factor a sus 24 celdas**: debe fijar su
configuración propia y comparabilidad antes de ejecutarlas. Tampoco convierte
el piloto histórico de seis brazos en una etapa obligatoria adicional.

## Presupuesto: tarifas públicas y límites de la estimación

Las [tarifas API OpenAI](https://developers.openai.com/api/docs/pricing) y
[Gemini](https://ai.google.dev/gemini-api/docs/pricing) consultadas se registran
como observaciones públicas, separadas de la cuota de suscripción y de cualquier
factura. El modelo y la ruta de ejecución no están elegidos.

Solo como cota aritmética condicionada: 24 × 80 000 = **1,92 millones de tokens**.
Si cada celda cumpliera realmente ese tope agregado, todos esos tokens se
cobraran como texto Standard de contexto corto y ninguna otra partida aplicara,
las cotas homogéneas serían USD **0,96 con Luna**, **19,20 con Sol**, **96 con
Astra** o **7,20 con Flash 3.8** a la tarifa vigente. Se usa la tarifa de token
más alta de cada modelo; no se afirma que todas las celdas deban usarlo.
**No es una proyección del estudio completo, autorización ni garantía de cobro.**
Faltan herramientas, almacenamiento de caché, evaluación, horas humanas, campo,
impuestos, primas y facturación efectiva. Gemini publica un cambio de tarifas
para 2027; una ejecución posterior requiere refrescarlas.

Los sobres del [protocolo, sección 8](../../../docs/protocolo_experimental.md#8-presupuesto-parada-y-publicación)
siguen siendo propuestas: USD 2 500 modelos/herramientas, USD 40 000/800 h
humanas y USD 30 000/400 h de campo; total USD 72 500/1 200 h. No se pide aprobar
ese total como presupuesto efectivo: primero hacen falta ruta viable y
proyección completa con precios y capacidad actuales.

## Siguiente trabajo concreto

Concentrar la implementación en **admisión y presupuesto por corrida compartidos
por agentes, solicitudes y herramientas**, y preparar la configuración propia
de las 24 celdas. Esa integración sigue siendo trabajo técnico autorizado y
puede desarrollarse con proveedores falsos sin generar respuestas facturables.
La revisión independiente comprobará su alcance antes de activar proveedores.
La autorización externa corresponde a los recursos, decisiones y custodia
identificados arriba, según AGENTS §7 y el protocolo; no autoriza avances falsos.

Al terminar las dos rondas, seleccionar y congelar; después, custodia y reserva.
Nuevas variantes documentales no sustituyen ese orden ni los resultados reales.
