# Coordinación común A/B/C de desarrollo

Cuatro agentes de modelo: líder, worker-1, worker-2 y reviewer. Todos reciben
el mismo caso público, acceso a fuentes/análisis, modelo, versión y esfuerzo.
Un presupuesto padre cubre bootstrap, workers, herramientas y reviewer; no
se repone al reparar o pausar. El formato de coordinación es prospectivo y
no es el solo/trío confirmatorio ni un calendario histórico reclasificado.

El líder empieza con work vacío, lee la tarea y crea mediante el driver
sellado su propio grafo pendiente. No recibe una propuesta host ni respuestas
resueltas. Mantén las diferencias del kernel original: A usa puertas locales
secuenciales; B cierre de dependencias e invalidación; C selección por riesgo
y exploración paralela de ámbitos independientes. El máximo de dos requests
de workers simultáneas está permitido por igual; orden y selección son parte
de la alternativa, no permiso para añadir agentes o información exclusiva.

Cada agente conserva su historial bruto privado. Se comparten únicamente
artefactos públicos con procedencia. El reviewer recibe esos artefactos al
terminar el trabajo de los otros roles y no tiene herramientas. Su texto no
es una aprobación competente ni una puntuación independiente de Q.

## Entrega y revisión

Lee la tarea original completa y los contratos públicos adjuntos. Conserva
las distinciones entre observación publicada, cálculo, inferencia, supuesto y
decisión normativa pendiente. Nunca inventes firma humana, eficacia causal,
factura, identidad efectiva de proveedor o resultado de una prueba no hecha.

Los tres métodos reciben los mismos campos de entrega por caso. El contrato
JSON fija nombres, unidades/bases, null motivado, métricas, fuente y límite de
1200 palabras para todo el reporte. En D-E, argv posicional y JSON son la
adaptación común D113; los nombres de campos y mapa de fuentes de D118 son
una adaptación pública adicional. Las tareas y originales no se modifican.

Una cantidad tiene `value`, `unit` y `base`; null necesita `reason`. No hay
NaN/Infinity. D-F exige las secciones y campos enumerados, un intervalo cerrado
con su propio denominador, identificación motivada de cotas superiores y
reglas de categorías/faltantes. Mantén separados masa y asignación económica.
D-E declara intervalos con count/check/issues, consumo semanal y diario en
cantidades con unidad/base, una observación adicional justificada y auditoría
de fuentes. Los campos no contienen valores esperados ni respuestas resueltas.

`sources.json` D-F usa schema1 y una lista de claims con todos los campos
enumerados. Una referencia identifica archivo visible, SHA y localizador.
Un cálculo derived declara fórmula e IDs de claims de entrada existentes;
una assumption identifica autor/propuesta; pending declara razón. Los hashes
no sustituyen el cotejo del pasaje ni la auditoría independiente del cálculo.

La rúbrica pública describe cinco dimensiones 0–20 y anclas 0/10/20, sin
soluciones de referencia. No puntúes tu propio Q. Presencia, sintaxis, JSON y
SHA son controles mecánicos; la corrección, justificación, seguridad y calidad
requieren verificación/revisión independientes. Reconoce resultados parciales,
truncamiento, incertidumbre y limitaciones sin convertirlos en éxitos.

Los adaptadores del perfil nuevo y la contabilidad auténtica aún necesitan
integración. Crear un paquete o un descriptor no autoriza API/gasto/campo ni
ejecuta una celda formal. R2 sólo se fija tras resultados reales de R1 y una
adaptación congelada. No leas ninguna entrada de reserva o solución sellada.
