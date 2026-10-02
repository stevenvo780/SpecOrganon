# Plan del MVP local · antes del piloto

## Encargo y alcance

Entregar una entrada de uso de SpecOrganon que pueda conducir un proyecto
local con agentes nativos y recursos presentes. El dueño autorizó continuar
con ese hito después de su aclaración de alcance. Su mandato incluye elegir
una implementación reversible en este repositorio; no concede gasto
adicional, despliegue ni intervención de campo.

La norma del caso y la decisión técnica se registrarán como aplicación de
ese mandato existente. El modo local declara ese origen, sin autenticar la
identidad del dueño ni convertir un agente en una persona firmante.

## Hipótesis y alternativas

Una política local explícita, más una entrada para agentes y un informe de
caso, permite completar un proyecto de desarrollo conservando trazas y
revisión técnica sin preparar el estudio confirmatorio.

Alternativas de arquitectura:

1. Mantener exclusivamente el modo firmado y configurar claves externas
   para todas las revisiones técnicas. Conserva la garantía actual, con
   configuración y custodia necesarias antes del primer recorrido.
2. Usar fixtures para todo el desarrollo. Es simple, pero sus aprobaciones
   inventadas no representan el encargo real ni una entrega operativa.
3. Añadir un modo local explícito para trabajo de confianza, conservando
   compuertas, versiones, contradicciones y separación de autores; declarar
   sus límites. Mantener firmado como valor inicial para los demás casos.

Se implementará la tercera. Los registros anteriores no se reinterpretan ni
se convierten a modo local. La comparación siguiente prueba una capacidad
operativa en esta configuración; no mide superioridad del método.

## Procedimiento y criterios previos

- Control: caso nuevo firmado sin registro externo, con los tres artefactos
  de encuadre. Medir fases aceptadas y la tarea siguiente; conservar el
  bloqueo original. No generar claves ni decisiones humanas sintéticas.
- Proyecto local: filosofía del encargo, protocolo de observación de la
  entrada existente, contraste de alternativas, especificación de política
  y reporte, implementación y pruebas reales. Completar las nueve fases
  tras revisión de un subagente distinto del ejecutor.
- Métrica técnica: número de fases del proyecto aceptadas, unidad `phase`.
  Umbral 9; rechazo de cierre si falta cualquiera, hay contradicción abierta
  o una prueba fallida. Es una medida de completitud del expediente local.
- Criterios adicionales: reporte usable, CLI/MCP coherentes, firmas y
  fixtures existentes conservadas, resultado `technical`, revisión de todos
  los autores históricos, y bloqueo de declaraciones decisivas de campo.
- Interrumpir el controlador al detenerse ante revisión; reanudar en otro
  proceso y comprobar ausencia de duplicados. No afirmar recuperación ante
  un corte abrupto si no se ha ejecutado ese control.
- Revisar una premisa en una copia local del expediente terminado y medir
  obsolescencia y reapertura. No borrar la historia para restaurar éxito.
- Segundo proyecto: reproducir con el mismo núcleo el análisis local del
  XLSX escolar disponible y verificar el resultado contra el JSON existente.
  El resultado es técnico/descriptivo; no causal ni una prueba de reserva.

## Presupuesto y parada

Dos rondas como máximo del recorrido del piloto; una primera implementación
y una corrección respaldada por hallazgos, si se necesita. Herramientas y
agentes nativos presentes, sin API adicional. Cada ronda conserva resultados
negativos. Los arreglos necesarios de integridad o regresiones se completan
antes de entregar, sin usarlos para declarar una victoria experimental.

El hito se declara listo para uso local si los criterios pasan; de lo
contrario se informa el fallo o pendiente concreto. Los criterios finales
C2–C5 de GOAL conservan su veredicto independiente.
