# Goal

Diseña e implementa una metodología y un toolkit reutilizable, inspirado en Spec Kit, para resolver problemas complejos: desde su formulación filosófica y estudio científico hasta la construcción y validación de una intervención.

El producto principal es la metodología operativa, con workflows, comandos y servidor MCP. La aplicación del primer caso será su prueba de funcionamiento, no el límite de su alcance.

Tienes amplia libertad creativa para definir arquitectura, fases internas, herramientas y mecanismos de coordinación. Lo siguiente establece responsabilidades, una ruta de trabajo y criterios de aceptación; no una solución predeterminada.

## Tres frentes de la metodología

1. Filosofía: examinar cómo se constituye el problema, sus conceptos, supuestos, límites, actores, fines y criterios de conocimiento y valor. Distinguir afirmaciones sobre la realidad de juicios sobre lo deseable, explicitando fundamentos, alternativas y conflictos. Las decisiones normativas relevantes requieren aprobación humana.

2. Ciencia: convertir las preguntas pertinentes en una investigación empírica; seleccionar métodos adecuados, recaudar información verificable, contrastar hipótesis y establecer las condiciones materiales del problema. Diferenciar datos, inferencias, supuestos e incertidumbres. Recopilar bibliografía no sustituye la investigación necesaria.

3. Ingeniería: comparar intervenciones posibles y desarrollar la solución justificada mediante SDD, desde especificaciones hasta implementación. Vincular requisitos y decisiones con los resultados anteriores. No asumir que el software, por sí solo, resuelve el problema.

Cada frente debe contener fases con entradas, resultados, criterios de avance, revisión y detención. Mantén trazabilidad versionada entre problema, evidencia, decisiones, requisitos e implementación. La evidencia posterior debe poder corregir el planteamiento e invalidar decisiones dependientes. Evita tanto una cascada rígida como una deliberación interminable.

Después de estos tres frentes, una fase explícita de validación determinará si la intervención realmente satisface lo planteado.

## Ruta para desarrollar el propio toolkit

Aplica esta misma metodología a su creación:

- Investiga antecedentes, enfoques existentes y limitaciones. Formula qué debería mejorar este sistema y cómo demostrarlo.
- Propón varias alternativas sustancialmente distintas de metodología, workflows y arquitectura. Explicita sus hipótesis, ventajas esperadas y riesgos; no te limites a desarrollar tu primera idea.
- Construye prototipos funcionales comparables y experimenta con ellos. Aprovecha workflows ejecutables para coordinar fases, artefactos, revisiones y agentes, con contexto suficiente, persistencia y reanudación.
- Prueba ejecución individual y coordinación entre varios agentes reales. Investiga dónde aportan revisión independiente, especialización o exploración paralela y dónde solo añaden coste o errores.
- Realiza varias rondas de evaluación y mejora. Conserva resultados negativos, contrasta alternativas y selecciona o combina las mejor respaldadas. Define un presupuesto y criterio de parada que eviten iterar indefinidamente.

La exploración debe modificar propuestas cuando la evidencia lo justifique, no repetir ejecuciones hasta obtener una favorable. Separa los casos usados para desarrollar el método de los reservados para su evaluación final.

## Caso inicial

Aborda una cadena alimentaria real y delimitada: distribuir alimentos con menores pérdidas de valor desde la producción hasta el consumo, incluyendo almacenamiento, transporte y sucesivas transformaciones o complejizaciones del producto, con múltiples entradas y salidas.

Investiga qué significa conservar o perder valor, para quién y cómo medirlo. No equipares valor con precio, transformación con pérdida ni reducción de masa con desperdicio. Considera perecibilidad, rendimientos, inocuidad y perjuicios desplazados entre actores o etapas. No lo reduzcas a optimizar rutas.

## Validación final obligatoria

Antes de evaluar, establece una matriz de aceptación derivada de los frentes anteriores: objetivo o afirmación, evidencia requerida, procedimiento, métrica, umbral y condición de rechazo. No ajustes los criterios para aprobar resultados ya conocidos.

1. Funcionamiento completo.
Desde un entorno limpio, prueba instalación, comandos reales, workflows completos y descubrimiento e invocación mediante un cliente MCP real. Verifica efectos y artefactos, no solamente respuestas exitosas. Incluye varios agentes, entradas inválidas, fallos, interrupciones, persistencia, reanudación y coherencia entre CLI y MCP. Los mocks no sustituyen estas pruebas integradas.

2. Integridad metodológica.
Introduce contradicciones, evidencia insuficiente y cambios de supuestos. Comprueba que el sistema detecte estos problemas, impida avances injustificados y revise las dependencias afectadas. Cada requisito e indicador de éxito debe poder justificarse desde el problema, sus compromisos normativos y su evidencia.

3. Resolución efectiva.
Compara la intervención con una línea base mediante métricas y umbrales definidos previamente. Evalúa resultados globales, costes, efectos adversos e incertidumbre; utiliza un diseño que permita atribuir razonablemente las mejoras. Distingue funcionamiento del software, resultados simulados e impacto observado en campo. Sin evidencia suficiente, la resolución real queda no demostrada.

4. Aporte de la metodología.
Compara, dentro de cada modelo, trabajo sin metodología estructurada, SDD solamente y la metodología propuesta. Incluye modelos de distintas capacidades y familias, distintos niveles de esfuerzo cuando sean configurables y diferentes configuraciones de agentes.

Mantén comparables tareas, información, herramientas y presupuestos. Realiza múltiples ejecuciones independientes sobre varios casos; justifica las repeticiones y reporta variabilidad. Mide calidad, cumplimiento, errores, trazabilidad, recuperación, intervención humana, tiempo, tokens y coste.

Separa los efectos del método, del modelo, del esfuerzo y de la coordinación. Incluye pruebas retirando componentes para comprobar cuáles aportan realmente. Usa evaluación verificable o independiente, no únicamente la autoevaluación del ejecutor. Una ejecución favorable, más documentación o usar un modelo superior no demuestran una mejor metodología.

5. Generalización.
Aplica el toolkit a un segundo problema real de otro dominio sin reconstruir el método. Comprueba la transferencia de sus mecanismos, no solo de sus plantillas.

## Entrega y veredicto

Entrega el toolkit funcional, documentación de uso, casos reproducibles, pruebas y registros de las alternativas investigadas, experimentos y decisiones.

Emite un veredicto por criterio: cumplido, incumplido o no demostrado. Separa funcionamiento técnico, rigor metodológico, mejora frente a alternativas e impacto real. Declara bajo qué condiciones funciona mejor y de qué capacidades depende.

No inventes datos, ejecuciones ni comparaciones. La falta de credenciales, modelos o acceso al campo deja evidencia pendiente, nunca una prueba aprobada.