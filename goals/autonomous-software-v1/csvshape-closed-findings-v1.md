# CSVShape v1: hallazgos del intento cerrado

Registro previo a generación: 2026-10-05T11:10:35.373390+00:00, SHA256
`3320889464b9ae6f49286e932ef9b39eaa1e2e83e1045ab90a1eda3d65bc1f4e`.
179 fuentes, contrato, 48 recetas y reglas congeladas. La aprobación estática
independiente del protocolo se conserva como tal, no como predicción acertada
de la entrega. Sonnet agotó180s sin veredicto; Flash aceptó el diseño y la delta.

## Resultado real

Gemini3.8Flash (Medium) autor, Codexgpt-6.1-sol low revisor, perfiles originales
y contenedores separados. Ocho llamadas admitidas/382457bytes de prompt, cero
pruebas de entrega, ningún archivo de programa. Frame y critique aceptadas.
Study rechazado por el revisor: faltaba fundamentación observada del indicador
y desglose F/D/M. El autor corrigió ambas cuestiones parcialmente, pero creó:

- `protocol-verification v2` mientras `evidence-doc-csv v1` conservaba una
  dependencia a `protocol-verification v1`. El indicador v2 refiere esa evidencia
  obsoleta; la obsolescencia transitiva mantiene study bloqueado.
- `evidence-parser-probes` con `data.collection_method`. El motor valida la
  colección en `data.method` y registra “observed evidence lacks collection method”.
  Texto/recibo externo no sustituye el campo estructurado que exige el motor.

El límite prospectivo de dos autores en study se agotó. No hubo segunda revisión
de fase tras esa corrección porque la puerta primero pedía reparar artefactos.
La identidad terminó `delivery_stopped`, sin aumentar límites, cambiar cuentas
o reabrir el caso. No es el antiguo fallo de contar aprobación y revisión juntas.

La evaluación cerrada conserva48/48 fallos contractuales por ausencia de programa,
con cero sujetos reservados ejecutados. Es distinto de un programa ejecutado que
falla48tests. D/M no se auditaron al no llegar a la puerta de paquete. La goal sigue
activa e incompleta; esta identidad no se reutiliza como una entrega exitosa.

## Próxima mejora prospectiva del mecanismo

Las instrucciones deben declarar claves exactas de evidencia observada y medición,
incluyendo `method` y, cuando fundamenta una métrica, `metric_key`, `scope`, `unit`,
`value`. Deben explicar que corregir un protocolo obliga a revisar todos los
descendientes que conservan su versión anterior y a producir puts en orden de
dependencia. Los cambios han de distinguir mecánica de forma de argumentos
sustantivos, sin fabricar evidencias, modificar juicios o aumentar caps por resultado.

Preparar controles acotados de claves y reparación transitiva con contenidos
claramente sintéticos antes de otra decisión de ejecución. Conservar los179fuentes
congelados y la historia de este caso; cualquier implementación posterior debe usar
otro checkout/revisión y no modificar su registro ni recibir aceptación retroactiva.
No elegir proyectos sucesivos ni reintentar esta tarea hasta obtener una victoria.

Quedan sin cumplir entrega nueva9/9, comparación multitype con dos familias,
repeticiones/ablación y versión final CLI/MCP instalada. Las comprobaciones131Docker
de fuentes montados,11de la delta y24host prueban controles técnicos, no estos hitos.
Los30inputs backup, sus ledgers/resultados y el GOAL.md original permanecen intactos.
