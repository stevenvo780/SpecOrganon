# Contrato explícito de artefactos y mantenimiento de referencias

Propuesta prospectiva, posterior al CSVShape v1 cerrado. No habilita reanudarlo,
crear una entrega sustituta ni modificar sus179fuentes. Implementación en otro
checkout desde `codex/prospective-software-repairs`, no en el checkout congelado.

## Defectos observados

La guía del rol decía “observed includes collection method”, sin nombrar la clave
`data.method` que valida el motor. El autor emitió `collection_method`. Al editar
el protocolo, mantuvo una evidencia ligada a la versión anterior, de modo que el
indicador corregido seguía obsoleto por dependencia transitiva. Las puertas
detectaron ambos problemas; no fue un falso PASS del motor.

## Cambio propuesto

- Publicar en cada request un contrato JSON orientativo de claves, condiciones
  y localizadores de validadores reales, sin argumentos, datos o consentimientos
  preescritos. Nombrar `method` y los campos de una medición que fundamenta un
  indicador (`metric_key`, `scope`, `unit`, `value`). Explicitar requisitos de un
  assessment decisivo: un criterio/baseline/result, test real ligado directamente,
  threshold/effect con métrica/unidad y valores sustentados.
- Mantener el mapa de dependencias completo en `state.json`; añadir orientación
  compacta con versiones directas obsoletas,
  propagación transitiva, lista en orden de dependencia y descendientes que se
  deben reconsiderar si cambia un artefacto. El diagnóstico tiene techo4096bytes;
  si se excede, declara modo resumen/conteos y localizadores del estado completo,
  sin listas parciales presentadas como completas. La orientación informa; no rebasa
  revisiones, reescribe refs, cambia texto, añade evidencia o acepta fases.
- Versionar el controlador a schema8 por cambio del contrato de request. Conservar
  todas las cotas schema7 (dos autores, tres build, dos revisores/dos conformidades,
  cuarenta llamadas y límites de contexto/archivos). Rechazar reanudación schema7
  antes de crear árboles de entrega. Registrar diagnóstico orientativo en el
  request y aclarar que no acredita una corrección semántica.
- Impedir en el runner registrado CSVShape importar un driver/toolkit de otro
  checkout o wheel mientras verifica hashes de una carpeta distinta. Contrastar
  rutas y bytes de los módulos cargados con el registro antes de tocar el caso.
  No ejecutar esta versión sobre el caso cerrado: su rechazo sirve como control
  de diagnóstico, sin modificar el antiguo runner o aceptar sus fases.

## Verificación anterior a uso real

Controles claramente sintéticos de claves exactas frente a `_item_issues`, cadena
protocolo/evidencia/indicador obsoleta, reparación explícita en orden correcto,
inmutabilidad del estado al consultar, casos con dependencias densas y nuevos
requests bajo presupuestos existentes. Reproducir el estado fallido CSVShape en
una copia de diagnóstico sólo para verificar localizadores y flags, sin escribir
su ledger ni asignar aceptación. Revisión nativa independiente del diff final y
verificación Docker de fuentes montados. Ningún control cuenta como nueve fases.

La corrección no cambia registros ni resultados históricos, no introduce aliases
que oculten campos incorrectos y no añade otro intento a CSVShape. Antes de otra
decisión experimental se necesita un protocolo nuevo que no seleccione tareas o
repeticiones buscando una victoria. Toda la goal permanece sin cumplir.
