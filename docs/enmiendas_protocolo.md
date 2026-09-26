# Bitácora de enmiendas del protocolo

El registro inmutable de un estudio confirmatorio todavía no existe y ningún paquete reservado, resultado o puntuación se ha abierto. Estas aclaraciones preceden al ensayo. Cuando exista un registro, cada cambio posterior deberá conservar su versión, fecha, motivo, autor y efecto sobre el análisis; un cambio tras abrir resultados será exploratorio y no moverá umbrales confirmatorios.

## 2026-09-26 · Aclaración de diseño previa a la reserva

- **Versión anterior:** SHA-256 de `docs/protocolo_experimental.md` `894f82b64f63cffec409dcca653042d77d16a94ebbc0e69818f4d744069f8cc0`.
- **Versión aclarada:** SHA-256 `f516286da9002311daa043388376336a905f6d012304088ed7754ae2855e5e23`.
- **Motivo:** auditoría independiente de consistencia del diseño antes de generar el calendario o ver casos reservados. Encontró que 540 era un máximo condicionado por controles de esfuerzo, que un promedio por celda sobreponderaría modelos con dos esfuerzos y que faltaban reglas para ternas incompletas, reserva de entradas y preselección de ablaciones.
- **Cambios:** 432 ejecuciones confirmatorias como máximo, con 54 menos por modelo sin esfuerzo configurable; un modelo bajo/alto por familia; orden N/S/T equilibrado por estrato; peso final igual por modelo; remuestreo de ternas y regla explícita para ausencia de puntuaciones; separación de todas las entradas y soluciones reservadas respecto del desarrollo y de los ejecutores; R-S distinto de D-S; modelos de ablación preseleccionados antes de resultados. El máximo de 540 programadas y 550 invocaciones incluye los casos de dos esfuerzos; el total efectivo se fija al registrar el panel.
- **Sin cambios:** objetivos de GOAL.md, cinco criterios, umbrales de aceptación, número de casos y réplicas, siete ablaciones, límites por ejecución y sobres presupuestarios propuestos. No hay autorización de gasto, custodia de reserva, medición de campo ni comparación N/SDD/toolkit ejecutada.

## 2026-09-26 · Regla de agregación para generalización

- **Versión anterior:** SHA-256 `f516286da9002311daa043388376336a905f6d012304088ed7754ae2855e5e23`.
- **Versión aclarada:** SHA-256 `3637ea6fde78933f5c6582238e83f6981fce627410bfdf1adb37b3711021c9e2`.
- **Motivo:** una revisión separada del planificador observó que `Q ≥ 70` en R-M y R-S podía interpretarse como media, mediana o mínimo y dar veredictos distintos con los mismos datos. No existe todavía ninguna puntuación reservada.
- **Cambio:** `Q` de cada caso se calcula solo con T, promediando réplicas, configuraciones de agentes, esfuerzos dentro de modelo y, al final, cuatro modelos con peso igual. Una puntuación requerida ausente impide afirmar cumplimiento; todos los fallos individuales siguen visibles y un error crítico no se compensa con la media.
- **Sin cambios:** umbral `Q ≥ 70`, cinco criterios, brazos, casos, número de réplicas, límites y presupuesto. El registro confirmatorio sigue pendiente de custodia y aprobación humana.

## 2026-09-26 · Secuencia de brazos y reintentos dentro de bloque

- **Versión anterior:** SHA-256 `3637ea6fde78933f5c6582238e83f6981fce627410bfdf1adb37b3711021c9e2`.
- **Versión aclarada:** SHA-256 `9922e3a322e277403435038cce4c423e522f5682f19ad2d44118303bd7a7ad30`.
- **Motivo:** la auditoría adversarial del contrato de recibos, antes de cualquier ejecución reservada, mostró que comprobar solo el primer inicio de cada brazo permitiría empezar el siguiente antes de terminar un reintento externo del anterior. Los timestamps autodeclarados tampoco demuestran por sí solos el orden de liberación del custodio.
- **Cambio:** los brazos de cada bloque se liberan en secuencia tras resultado terminal utilizable o truncamiento; un reintento externo elegible termina antes de avanzar. Una caída sin reintento detiene el bloque y deja faltantes visibles. El custodio registra fuera del ejecutor un evento por intento con secuencia, hora, bloque, `run_id`, intento, posición y hash del calendario, más el evento terminal ligado a traza y estado. Se permiten hasta cuatro bloques simultáneos.
- **Sin cambios:** casos, panel, brazos, réplicas, umbrales, límites por invocación, cupos de reintento y presupuesto. No existe aún registro confirmado ni dato reservado observado.

## 2026-09-26 · Cegamiento, incidentes y consolidación de Q

- **Versión anterior:** SHA-256 `9922e3a322e277403435038cce4c423e522f5682f19ad2d44118303bd7a7ad30`.
- **Versión aclarada:** SHA-256 `8af3eb7406d804379abbe1431cd504c06b29476e8f91bef5859297a762a86697`.
- **Motivo:** antes de datos reservados, la auditoría del contrato de puntuaciones detectó que el protocolo exigía dos jueces y arbitraje pero no decía cómo formar una `Q` por corrida, qué evidencia verificable veían en la etapa ciega ni cómo preservar multiplicidad de errores graves. Una segunda lectura encontró que la tasa `E` agrupada o ponderada por modelo podía cambiar el veredicto con idénticos datos.
- **Cambio:** un paquete de resultado verificable y cegado precede a las trazas; cada juez fija cinco componentes de `Q` antes de auditar incidentes individualizados. El custodio armoniza IDs provisionales con anclajes de evidencia sin ver el brazo; no convierte contradicciones menores en errores críticos. Con diferencia de `Q` ≤ 10 y acuerdo de incidentes se usa la media de dos; de otro modo, el tercero fija su `Q` cegada y resuelve los incidentes disputados o nuevos. La tasa de `E` usa una bandera por corrida y pesos iguales por modelo; `T` y `R` usan esos pesos, y coste/tiempo usan medianas por modelo y después entre modelos. Se conservan notas crudas, fallos concordantes, tasas de arbitraje y una sensibilidad descriptiva. La correspondencia con corridas se revela después de cerrar las notas.
- **Sin cambios:** los cinco criterios, casos, panel, brazos, réplicas, rúbrica de cinco componentes, umbrales de aceptación, recursos, presupuesto y falta de autorización de la matriz. Ninguna puntuación reservada fue observada antes de esta aclaración.

## 2026-09-26 · Precisión de los cinco componentes de Q

- **Versión anterior:** SHA-256 `8af3eb7406d804379abbe1431cd504c06b29476e8f91bef5859297a762a86697`.
- **Versión aclarada:** SHA-256 `8159fae6b182d787f90a102c4ed1e1e1e917a37f6dba23b8255a2ca09c76237b`.
- **Motivo:** la revisión adversarial reprodujo que un decimal JSON mayor que el límite de un componente podía redondearse por `float` a 20 y que una diferencia real de `Q` apenas mayor de 10 podía redondearse a 10, evitando el tercer juez. No existe aún ninguna nota de la reserva.
- **Cambio:** cada juez asigna puntos **enteros** de 0–20 a cada uno de los cinco componentes; el total individual es su suma exacta. La media de dos jueces cuando procede puede ser fraccionaria y se conserva sin redondear para el análisis.
- **Sin cambios:** rúbrica de cinco componentes, umbral de arbitraje mayor de 10, criterios y umbrales de aceptación, casos, panel, brazos, réplicas, recursos y presupuesto. Sigue pendiente el registro bajo custodia y la autorización del ensayo.

## 2026-09-26 · Procedencia entre resultado terminal y paquete cegado

- **Versión anterior:** SHA-256 `8159fae6b182d787f90a102c4ed1e1e1e917a37f6dba23b8255a2ca09c76237b`.
- **Versión aclarada:** SHA-256 `ab0e6fc86017ce1c7a9d270c29f81f31d8bc742c0493e5728e1c8b7a110b7510`.
- **Motivo:** antes de casos reservados, la revisión de la unión entre recibos y juicios encontró que el artefacto/traza terminal y el paquete/traza cegados pueden tener bytes distintos después de seleccionar evidencia y retirar información sensible. Exigir igualdad de sus digests podía rechazar una evaluación válida; no exigir ninguna cadena de preparación permitiría atribuir un juicio a otra corrida.
- **Cambio:** se distinguen los cuatro digests. Antes de la evaluación, el custodio conserva bajo control externo un acta por ID opaco con la corrida e intento terminales, manifiesto de fuentes/pruebas y receta de preparación/redacción; su parte identificadora queda privada hasta cerrar juicios. El mapa de apertura referencia el digest del acta y los bytes originales y cegados se cotejan después. Un hash declarado sin acta custodiada no prueba procedencia.
- **Sin cambios:** regla de consolidación de `Q`, incidentes y `E`, cegamiento por etapas, cinco criterios y umbrales, casos, panel, brazos, réplicas, recursos y presupuesto. Ningún resultado reservado se ha observado ni se ha autorizado el ensayo.

## 2026-09-26 · Denominadores y faltantes de métricas secundarias

- **Versión anterior:** SHA-256 `ab0e6fc86017ce1c7a9d270c29f81f31d8bc742c0493e5728e1c8b7a110b7510`.
- **Versión aclarada:** SHA-256 `90ca6e1aa22956f4379f3f104b6540587bcaf66b9845f46207477a1e0b44d6a1`.
- **Motivo:** una auditoría previa a la reserva encontró que una referencia causal vacía, interrupción no entregada, nota `E` ausente o mediana S igual a cero podían producir divisiones indefinidas o verdes artificiales según la implementación. No existe resultado confirmatorio observado.
- **Cambio:** se exige una referencia no vacía de criterios y enlaces por caso antes de ejecutar; sin enlaces predichos frente a referencia no vacía se fija precisión/exhaustividad/`F1` en cero. Una interrupción no verificada y un `E` no evaluado son faltantes; una métrica faltante impide su agregado confirmatorio sin redistribuir pesos. Para trazabilidad y recuperación, «sin regresión frente a S» exige diferencia puntual ponderada T−S no negativa además del umbral absoluto. Si la mediana S de tiempo o coste es cero, el cociente y el umbral quedan no demostrados.
- **Sin cambios:** definiciones y umbrales de calidad, errores, trazabilidad, recuperación, tiempo y coste; cuatro modelos, tres casos, tres réplicas, panel, brazos, recursos y presupuesto propuestos. Siguen pendientes la reserva, las fuentes verificadas y la autorización humana del ensayo.
