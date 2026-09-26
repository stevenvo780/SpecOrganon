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
