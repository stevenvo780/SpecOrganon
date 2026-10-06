# Libre y SDD competentes: diseño pendiente de implementación

Este documento prepara la siguiente fase de la meta. No registra una comparación,
no ejecuta autores ni abre oráculos reservados. Dev4 está congelado en su checkout
original mientras termina la cohorte02. Cualquier cambio de ese candidato exige
otra versión y otro registro; este checkout separado permite trabajar en controles.

## Problema comprobado en los controles anteriores

El flujo N de v3 conserva programa, tests, medición y revisión final. S añade
especificación, diseño, tareas y verificación. El paquete común exige documentación
útil y trazas/criterios registrados antes de tests, pero N no recibe un recorrido
competente para aportarlos y la revisión final no permite corregir. La guía SDD
conserva requisitos y alternativas, pero sus rechazos no tienen un ciclo útil de
corrección antes del cierre. Además, la gramática nativa dev4 de manifest-v1 exige
pasos no vacíos, mientras N/S antiguos solicitan steps vacíos: ese harness histórico
no debe usarse con el adaptador nuevo para declarar una comparación válida.

## Infraestructura común propuesta

Los tres métodos reciben el mismo contrato, mandato técnico acotado, criterios
comunes F/D/G y presupuestos máximos. Las nueve fases H solo aplican a SpecOrganon.
El revisor de fuentes usa otro proceso/proveedor; el ejecutor real es común y no
recibe perfiles. La evaluación funcional reservada permanece separada y ciega al
método, después del cierre de generaciones. No se aportan sus resultados al autor.

La sintaxis de N/S debe ser una entrega neutral (archivos/documentos/razón), sin
pasos del motor ni artefactos ficticios. Requiere una ruta explícita independiente
y probada; no convertir paquetes inválidos antiguos en respuestas válidas. Las
reglas de respuesta cruda de un turno, identidad/configuración, archivos/insumos
por hash y recibos deben ser equivalentes a las de T. Declarar las diferencias de
formato y registrar su coste. No extender los presupuestos solo a un método.

El programa y README se sellan antes de redactar tests. Criterios, requisitos y
justificación que se afirmen previos deben existir en paquetes fechados anteriores
a la medición; las notas posteriores se distinguen. Cada cambio conserva el
paquete previo, motivo, archivos y límites. Revisión adversa o tests fallidos
habilitan una corrección únicamente dentro de las cuotas comunes disponibles.
Una llamada incierta nunca se repite. No se puede terminar favorablemente una
celda incompleta ni descartar fallos técnicos del denominador registrado.

## Trabajo libre

El autor elige organización, algoritmo y documentos de trabajo. Conoce los
requisitos del paquete común y puede escribir notas/criterios en prosa útil, sin
una secuencia SDD ni fases impuestas. Obtiene feedback independiente antes de
sellar y feedback de tests reales. Una revisión final crítica puede consumir una
corrección restante; cada revisión y test cuentan. La ausencia de nueve fases no
falla H, que no aplica. No exigirle más trazabilidad que la definición común ni
rebajar esa definición para SpecOrganon.

## SDD

El flujo registra SPEC (requisitos y criterios), DESIGN (alternativas y decisión)
y TASKS antes del programa. Una revisión de diseño tiene posibilidad de corrección
acotada antes de construir. Tests y VERIFY contrastan criterios originales y
recibos reales; no se reescriben criterios para esconder defectos. Las revisiones
se cobran a las mismas cuotas y el presupuesto no se renueva entre etapas.

## Admisión posterior

Antes de cualquier comparación reservada: implementar controles adversarios,
probar N y S en desarrollo público y comprobar paquetes completos con F/D/G. Un
fallo de los baselines se corrige en desarrollo y se conserva, sin declararlo prueba
de superioridad. T debe superar primero el criterio de fiabilidad fijado: al menos
9/10 entregas en su cohorte completa y dos tipos con nueve fases. No escoger solo
las generaciones favorables ni cambiar criterios al ver una ventaja.

Después se fijan versión completa, tareas nuevas, dos familias de autores disponibles,
presupuestos, orden de ejecución, oráculos independientes y plan estadístico. El
análisis usa unidades de generación apareadas, límites simultáneos95% frente a ambas
alternativas, ventaja de paquetes>=10pp y margen funcional5pp, razón de tiempo
medio total<=2. El tamaño debe justificarse antes de admitirse. Un tamaño insuficiente
es inconcluso, aunque haya miles de comprobaciones por programa. Se congelan tareas
nuevas y una réplica independiente con exactamente la misma versión y criterios.

No se conocen todavía tamaños, potencia, costes comparables ni un ganador. Se
registrará tiempo total que incluya preparación, análisis, correcciones, tests y
revisión; job_seconds_sum por sí solo omite parte de la preparación Docker. Los
contadores heterogéneos de tokens y el coste monetario siguen desconocidos.
