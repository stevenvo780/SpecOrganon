# Segundo caso de desarrollo: disponibilidad de Citi Bike

**Estado:** la aplicación documental de junio de 2026 en [caso_citibike_ejecucion.md](caso_citibike_ejecucion.md) ya abrió este candidato. Por tanto, este periodo y paquete no sirven como reserva ciega para la comparación confirmatoria. Se usan como demostración de desarrollo y transferencia parcial en otro dominio; una reserva futura debe seleccionarse y sellarse antes de consultarla. Un sondeo puntual del feed actual encontró indicadores de estado con tipos incompatibles con GBFS 2.3 y dejó la disponibilidad de ese feed sin calcular. Una [muestra publicada de marzo de 2024](../experiments/development/citibike_sample_status_2026-09-27.json) permitió un análisis separado de filas estación-instantánea con capturas irregulares; no representa junio de 2026 ni estación-minutos continuos. No se usó el resultado de este caso para seleccionar los tres prototipos del núcleo.

## Problema propuesto

Delimitar un conjunto de estaciones de Citi Bike en Nueva York y un periodo fijo para estudiar cuándo una persona no puede iniciar o terminar un trayecto por falta de bicicletas o de anclajes. La intervención posible podría combinar redistribución, incentivos a usuarios e información, después de comparar costes y efectos desplazados. Esa elección aún no está justificada.

Actores: personas usuarias, operador, personal de redistribución, vecinos y gobierno local. Valores potenciales: accesibilidad, equidad territorial, seguridad laboral, emisiones y coste. La ponderación entre ellos es normativa y queda pendiente de aprobación humana.

## Datos y límites

La [fuente oficial de Citi Bike](https://citibikenyc.com/system-data) publica viajes históricos (incluidos horarios y estaciones de inicio y fin), estado en tiempo real mediante GBFS e informes operativos mensuales. La misma página indica que los viajes breves, de personal y de estaciones de prueba se han excluido de los ficheros históricos. Esa selección impide interpretar los viajes publicados como toda la demanda latente; tampoco una estación vacía prueba por sí sola un viaje frustrado. La [licencia de datos](https://citibikenyc.com/data-sharing-policy) permite análisis bajo condiciones y no autoriza redistribuir el conjunto de datos como dataset independiente.

Para una prueba reproducible: fijar geografía, fechas, versiones de fuentes y plan de muestreo antes de descargar; conservar hashes y agregados, no un volcado público de datos brutos; cuantificar faltantes y cobertura del feed. Medir minutos estación vacía/llena, distribución entre estaciones, viajes completados, distancia de redistribución y costes. Una comparación observacional o simulada puede probar funcionamiento y plausibilidad, pero no atribuir impacto real sin intervención y control adecuados.

## Gate de transferencia

Usar exactamente los mismos comandos, tipos de artefacto, revisión, trazabilidad, invalidación y reanudación que el caso alimentario. Un cambio de vocabulario en una plantilla no basta. La evidencia de transferencia será un registro ejecutado con datos citables, compuertas activadas y al menos una revisión de supuesto que propague efectos a requisitos. La resolución efectiva seguirá `no demostrado` mientras no haya evaluación de campo.
