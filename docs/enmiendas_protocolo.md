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
