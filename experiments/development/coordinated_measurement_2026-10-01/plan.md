# D120 · Conciliación de mediciones del runtime coordinado

## Objetivo y alcance prospectivo

Base sellada: D119, commit `c64169c15c5cbe6dd35c5fc4c25704fc042332a7`.
Se añade un lector/verificador separado para enlazar corrida/brazo/rol/solicitud,
request, respuesta, recibo y ledger, y publicar medidas locales y faltantes
explícitos. No se modifica ningún byte de los dossiers ni fuentes congelados de
D119/D118, GOAL, protocolo, casos, núcleo o wheel.

Esta unidad resuelve una preparación de medición antes de R1: hasta ahora hay
recibos individuales, pero falta un informe agregado que concilie su cobertura,
uso, precio declarado y relojes sin confundir sus alcances. No abre R1 ni
convierte los recorridos sintéticos D119 en corridas formales.

## Diseño y alternativas

1. Modificar el runtime sellado para añadir telemetría: se descarta en esta
   unidad porque cambia su cierre de fuentes y mezcla evidencia histórica.
2. Inventar W o actividad remota desde el deadline/lease: inválido. El lease,
   las duraciones de HTTP y sandbox son medidas locales distintas.
3. Lector separado con snapshot bajo el lock original, guard del wrapper,
   replay nativo y conciliación independiente: elegido. No envía solicitudes.

El lector admite únicamente runtimes terminados y con publicación válida. El
informe conserva identificadores, hashes, coordenadas, uso y medidas, sin copiar
prompts, salidas textuales, argumentos de herramientas ni secretos.

## Invariantes y medidas

- Conjuntos exactos de requests/responses/receipts/ledger y contadores; IDs,
  roles, modelo/esfuerzo, digests, liquidación y uso concordantes. Cualquier
  discrepancia rechaza la medición; nunca se sustituye un dato inválido por cero.
- Cada herramienta queda ligada al request y a reserva/recibo, con IDs y
  contadores exactos y duración de sandbox/host finita y no negativa.
- Totales de input/output/total de las respuestas, separados por rol. Cache y
  razonamiento son subconjuntos: no sumar razonamiento otra vez a output ni
  cache otra vez a input. Detalles ausentes quedan desconocidos; input sin
  clasificación no se convierte en uncached autenticado.
- Coste local recalculado por solicitud con el perfil congelado y redondeo
  original; se coteja con el ledger. Se llama coste declarado calculado, no
  factura ni tarifa autenticada. Precio de herramientas, revisión humana y
  evaluación, y coste total del estudio permanecen faltantes.
- Duración de send = fin monotónico menos inicio monotónico. Se publican suma
  de duraciones de send y suma de sandbox/host por separado. No se mezclan
  nanosegundos wall del ledger con nanosegundos monotónicos del receipt.
  Sin identificador de reloj/boot no se calcula unión global ni W.
- Lease activo/pausas se presentan como contabilidad local del contexto.
  W liberación→entrega, H humano, conteo de input, actividad remota y cobertura
  íntegra de actividad siguen faltantes. Ninguno se infiere de los anteriores.
- Calidad, esfuerzo efectivo, identidad, factura, ventaja comparativa,
  autorización, aceptación y celdas formales permanecen sin demostrar.

## Gates fijados antes de implementar

1. Tests proporcionales de conciliación positiva y rechazo de inventario,
   digests/uso/roles/precios/timestamps/herramientas corruptos; casos de cache
   y razonamiento con ausencia explícita y sin doble conteo.
2. Ruff y compilación de archivos nuevos; Python 3.11 y 3.12.
3. CLI real de lectura sobre los doce runtimes D119 existentes (seis por
   intérprete registrado), sin reejecutarlos. Mismas coordenadas; calendarios
   distintos según intérprete. Ninguna celda nueva o efecto de tratamiento.
4. Confirmación de bytes de D119 preservados antes/después y revisión
   independiente del lector, reportes y límites.

Límite de esta unidad: un lector, sus pruebas y doce informes sanitizados;
sin fan-out de modelos experimentales ni solicitudes externas facturables.
Se conserva cualquier fallo real observado. No se repite la suite global ni
las integraciones largas D119 salvo riesgo concreto nuevo.

## Reparto

- Root: plan, captura de CLI, conservación, documentación e integración.
- Worker nativo: sólo nuevo lector y sus pruebas, ownership disjunto.
- Luna: inventario read-only de interfaces ya existentes, sin veredicto de Q.
- Revisor independiente: nuevo directorio `review/`, sin editar implementación.

## Siguiente puerta

Tras esta unidad faltará capturar prospectivamente liberación/entrega y conteos
con reloj identificable, y ligar una ruta real autorizada a datos de uso/precios
verificables. La disponibilidad de un CLI/modelo o una declaración local no
autentica esa ruta. R1/R2, selección, confirmación, campo y transferencia siguen
obligatorios para GOAL.
