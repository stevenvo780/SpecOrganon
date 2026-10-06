# Auditoría de cierre de la goal local

Estado: auditoría final de evidencia local, 2026-10-04. Esta lista se deriva de la
goal autorizada, del contrato y del protocolo congelados. Se preparó durante la
generación y se cerró tras inspeccionar la campaña, las observaciones adicionales,
la fuente seleccionada, sus pruebas y los paquetes de entrega. No cambia las
condiciones del piloto. El cierre corresponde al experimento local, incluso con
resultados adversos; no acepta las nueve fases del método ni el GOAL.md original.

| Requisito | Evidencia que debe inspeccionarse | Criterio de cierre |
| --- | --- | --- |
| Contrato y protocolo anteriores a las comparaciones | `frozen/manifest.json`, hashes actuales, fechas y recibos | Integridad de los 30 archivos e imágenes; límites de la congelación y revisión tardía del caso raíz declarados |
| Evaluador separado, casos reservados y controles defectuosos | Evaluador congelado, pruebas y controles de `development`, comandos/montajes reales | Pruebas adversas y controles verificables; ninguna evaluación reservada entregada a los autores |
| Docker autenticado y MCP real | Recibos y eventos de las sesiones, configuración de aislamiento y llamadas MCP | Uso real documentado; sin copiar credenciales ni intercambiar cuentas; errores MCP examinados |
| Diseño completo de 18 ejecuciones y dos etapas | Calendario del manifiesto, 36 marcadores y recibos, `runs/complete.json` | Tres variantes × tres brazos × dos repeticiones; cada etapa identificada, sin sustituciones o repeticiones favorables |
| Condiciones y presupuestos comparables | Prompts, archivos de entrada, modelo/esfuerzo, argv, imágenes, recursos y tiempos | Diferencias previstas y desviaciones reales declaradas; no afirmar igualdad de tokens a partir de límites temporales |
| Cambio de requisito común | Contratos de ambas etapas y entregas archivadas | `--max-bytes` aplicado en la segunda etapa a todos los brazos, sin retroalimentación reservada |
| Conservación y procedencia de la evidencia | `audit.py`, inventarios, hashes, JSONL, streams y recibos físicos | Incidencias resueltas o acotadas; errores de infraestructura nunca convertidos en ceros de calidad; truncamientos y custodia local declarados |
| Separación de funciones | Entradas de revisión funcional y eventos de las doce revisiones del método | Revisión funcional en solo lectura; inspección explícita de posibles cambios de código por el revisor del método, cuyo montaje permite escritura |
| Calidad, recuperación y fallos | Las 36 evaluaciones congeladas y sus streams | Denominadores 20/22, corrupción, SIGKILL, bytes exactos y fallos críticos incluidos; ausencias e inconclusos visibles |
| Variabilidad y costes disponibles | Exportación del analizador y recibos por función/etapa | Seis unidades por brazo/etapa, diferencias pareadas, media/mediana/rango; tokens desconocidos como desconocidos, sin sumar dos veces caché o razonamiento |
| Cumplimiento del entorno de entrega | Addendum y 36 observaciones de `clean_runtime.py`, revisión de fuentes | Cobertura completa y no selectiva; imports, código incorporado y comandos externos examinados; diagnóstico exploratorio separado de puntuaciones primarias |
| Uso efectivo del método | `method_report.py`, ledgers y eventos MCP | Doce observaciones; aceptación vigente distinguida de histórica; llamadas mecánicas no presentadas como validación semántica o identidad autenticada |
| Veredicto reproducible | Informe de resultados y datos citados | Ventaja, ausencia de ventaja o resultado adverso admitidos; alcance de una familia, tres variantes y dos repeticiones preservado |
| Producto utilizable | Fuente seleccionada, helpers, hashes y procedencia, validación limpia V1/V2/V3, ejemplos CLI | Todas las garantías contractuales verificadas; si hace falta reparar, entrega de ingeniería separada del piloto y sin alterar sus resultados |
| Instrucciones de uso y reproducción | README del producto y del experimento, comandos comprobados | Crear, verificar, listar, restaurar y cuota explicados; reproducción en resultados/checkouts nuevos, sin borrar locks vivos ni duplicar sesiones |
| Límites y alcance original | Diff de `GOAL.md`, estado de la suite original y reporte del caso raíz | GOAL original intacta y no declarada cumplida; límites, pruebas pendientes y revisión tardía explícitos; otras familias/dominios como siguiente etapa |

Los informes automáticos aportan evidencia de alcance limitado. Una auditoría
válida de hashes no prueba por sí sola calidad, cumplimiento semántico del método,
identidad ni independencia de custodia. Ejecutar el producto sin paquetes del
entorno tampoco prueba por sí solo la política completa de dependencias.

## Evidencia inspeccionada y disposición

| Requisito | Resultado verificado |
| --- | --- |
| Fijación antes de comparar | Freeze de 30 archivos a 22:37:45.556870Z, primera generación a 22:37:45.606484Z; hashes intactos. Revisión tardía del frame raíz declarada en RESULTADOS.md. |
| Evaluador y controles | Suite congelada 21/21; controles aislados V1/V2/V3 22/22 con UID1000 y controles defectuosos conservados. La referencia nunca fue seleccionada como producto. |
| Docker/MCP auténticos | 84 sesiones CLI y llamadas SpecOrganon en las doce entregas T, con sesiones de autor y revisor separadas; imágenes y argv comprobados por audit.py. No acceso del evaluador a autenticación o socket Docker. |
| Diseño y cierre | Marcador final 18 corridas/36 etapas; 36 recibos de evaluación; factorial y denominadores validados por analyze.py. No reemplazos favorables. |
| Igualdad operativa y límites | Configuración de modelo/esfuerzo, datos esenciales, recursos y presupuestos verificados; extras de T y errores locales de herramientas declarados. No paridad exacta de tokens o pesos afirmada. |
| Cambio común | Las 18 etapas dos recibieron --max-bytes, sin feedback reservado; comparación de veinte checks comunes y dos nuevos separada. |
| Integridad y procedencia | provenance-audit.json válido, cero incidencias de consistencia, 84 IDs distintos, cero streams truncados. Identidad/custodia externas no acreditadas. |
| Separación de funciones | Revisión funcional en solo lectura y entradas coincidentes. Revisión manual de 124 comandos del método sin escritura de código observada; montaje RW y ausencia de captura previa declarados como límites. |
| Calidad y recuperación | 36 resultados completos con checks 20/22, críticos, inconclusos, corrupción y SIGKILL reales. Fallos básicos conservados con denominador fijo y causa de permisos descrita; no tratados como defectos independientes. |
| Variabilidad y costes | Medias, medianas, rangos, seis diferencias pareadas y adaptación en report.md/results.json. 46/84 sesiones sin tokens informados; caché no duplicada, dinero desconocido, bootstrap separado. |
| Runtime de entrega | Addendum registrado antes de abrir resultados; 36 observaciones adicionales evaluadas, mismos resultados individuales de checks que los originales. Fuente seleccionada leída completa y stdlib verificada; inventario de las otras 35 acotado a AST. |
| Aplicación del método | Doce ledgers observados; aceptación vigente distinta de histórica, cero test_execution_records y ninguna aplicación completa. Incumplimiento reportado como resultado adverso, no ocultado ni aprobado retrospectivamente. |
| Veredicto | RESULTADOS.md: señal funcional descriptiva para paquete T, fallos documentales/adherencia, tesis fuerte no demostrada, una familia y n=6 por brazo. Datos completos y límites explícitos. |
| Producto | V1-r1-N etapa dos sin modificar, hash eaac5ef5622e77d5584474318baba62f906ff1030d6cdcad8fcf7275886e6e0a; 22/22 V1/V2/V3, 32 pruebas propias OK y ejemplo aislado PASS. Recibos en analysis/product-verification. |
| Uso y reproducción | README del producto/experimento, archivos tar.gz y manifiesto; fuentes extraídas con hashes coincidentes, compose config válido y 83 pruebas del piloto en extracción nueva. No se simuló una segunda campaña de modelos como ya ejecutada. |
| Fallos y reanudación | resumption-proof.json: recibo cerrado no repite callback, marcador iniciado sin recibo rechaza callback; CLI real de producto reutiliza cinco recibos con hashes intactos, cero llamadas de modelo. Campaña original no se reinició. |
| Alcance original | Diff de GOAL.md frente a HEAD vacío. Control actual tests/test_audit_bread_sources.py: 3 fallos/49 éxitos por digest del extractor; fuera del cierre local y sin reparaciones encubiertas. Caso raíz conserva 1/9 fases y bloqueos declarados. |

Los cierres de code-mode en V3-r1-N/autor etapa uno y V1-r1-T/revisor del método
etapa uno son desviaciones locales de herramientas. Se preservan en findings.json;
no son rechazos de API/cuota, no generaron una repetición favorable y limitan la
atribución causal. Los fallos funcionales siguen siendo comportamiento observado
de las entregas. Los incumplimientos de README y fases son resultados, no trabajo
que deba alterarse retrospectivamente para mejorar la comparación.

La verificación posterior del producto reutiliza familias/semillas conocidas y
es evidencia de ingeniería, no un nuevo holdout confirmatorio. La suite fresca de
83 pruebas cubre el harness del piloto, no toda la plataforma. Una ampliación
confirmatoria a otras familias/dominios queda expresamente como siguiente etapa.
