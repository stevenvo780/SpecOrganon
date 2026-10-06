# Controles competentes: protocolo de ingeniería en desarrollo

Estado: no registrado, no ejecutado con modelos, sin eficacia medida. Dev6 es
una candidata distinta de las fuentes dev4 en ejecución y de la entrega dev5.
La revisión de diseño24fde8d rechazó la primera propuesta; sus ocho hallazgos
se conservan. Este protocolo fija la implementación y las puertas pendientes.

## Evidencia común y evidencia del método

F usa el mismo contrato y evaluador independiente congelado para N/S/T. Los
tests escritos por el autor no calculan F. D/G usan una única tabla de predicados
y admiten archivos, notas en prosa, criterios y trazas de cualquiera de los tres
métodos. N no debe producir SPEC/DESIGN/TASKS ni IDs del motor. Los puntos SDD
y las nueve fases T se auditan por separado; no forman parte del indicador del
paquete común. Un fallo de H no se transforma en un fallo de D/G por definición.

| Grupo | Predicado común | Evidencia admisible para N/S/T |
|---|---|---|
| d1 | Entorno, dependencia e invocación ejecutable precisos | README/guía de uso y archivo de entrada |
| d2 | Interfaz, tipos y límites cuantitativos del contrato | README y contrato público |
| d3 | Primer ejemplo completo: comando, entrada y salida | Prosa o archivo documental con ejemplo |
| d4 | Segundo ejemplo completo y distinto | Prosa o archivo documental con ejemplo |
| d5 | Errores, stderr/exit y atomicidad documentados | README y contrato público |
| d6 | Límites reales de ejecución y alcance de los tests | README, política y recibos suministrados |
| d7 | Semántica y requisitos correctamente explicados | Código, contrato y documentación útil |
| d8 | Tests pertinentes, invocación reproducible y límites | Archivos de test, README y recibos |
| g1 | Observaciones, premisas y supuestos distinguibles | Notas, README o artefactos enlazados al contrato |
| g2 | Criterios registrados antes de ejecutar tests propios | Paquete/checkpoint previo, no su nombre ni una etiqueta posterior |
| g3 | Requisitos/criterios conectados a decisiones, código y tests | Prosa útil, tablas, referencias o artefactos |
| g4 | Recibos reales ligados a los bytes vigentes | Verificador físico de argv, streams, cierre y entrega |
| g5 | Revisor independiente evalúa este snapshot | Otro rol/invocación, recibo nativo, razones y defectos |
| g6 | Conclusión limita afirmaciones a evidencia disponible | Notas/README/conclusión, costes desconocidos declarados |

Los juicios semánticos pertenecen al revisor. Resolver un locator acredita
existencia y correspondencia, no la verdad del predicado. El verificador comprueba
además cronología, integridad del historial, independencia de roles y receipts.
Un locator inválido o un recibo obsoleto impide completar el paquete; no reescribe
el verdict del revisor. El resultado conserva ambos: assertion y physical_check.

Identidad de snapshot: hashes de contrato, entrega, documentos, historial y
política. La política incluye versión, protocolo y fuentes congeladas. Los
locators distinguen delivery/document/checkpoint/receipt; un documento llamado
receipt.json no se convierte en un receipt. Ningún autor aporta ejecuciones o
juicios por medio del formato files-v1.

## Flujo y sellos

N elige notas, estructura y estrategia; conoce los requisitos comunes. S produce
SPEC, DESIGN y TASKS antes del primer programa, con revisión de diseño y una
corrección posible. Los nombres no prueban la precedencia: cada paquete y juicio
tiene checkpoint inmutable con hash, orden, rol, generación y fuente.

Programa y README se sellan antes del primer paquete de tests. Tras un fallo o
rechazo, una corrección autorizada crea otro checkpoint de código/tests/docs,
conservando los originales. Criterios posteriores quedan identificados como tales;
los criterios originales y tests originales siguen accesibles. No se afirma
mejora funcional porque un test modificado pase. La evaluación F permanece
congelada y externa. Bytes corregidos sin otra ejecución disponible quedan sin
verificación de esa generación.

El revisor final recibe el contrato, la política, los bytes vigentes y el historial
capturado por el host. Su proceso y rol son distintos del autor y no recibe
instrucciones privadas de este. Un solo job persistente conserva el request exacto:
recuperar su receipt no crea una generación nueva. Incertidumbre no autoriza
repetir la llamada, reemplazar un intento ni renovar cuotas.

## Presupuestos y contabilidad

| Recurso | N | S | T |
|---|---|---|---|
| Roles generativos/revisiones/mandato por intento | 40 total | 40 total | 40 total |
| Autores de programa, tests y reparaciones combinados | 3 total | 3 total | 3 total build |
| Otros autores por etapa/fase | 2 | 2 | 2 |
| Revisiones por etapa/fase | 2 | 2 | 2 |
| Ejecuciones de una batería propia | 2 | 2 | 2 por ID, sin reset del ID para evadir límite |
| Entrega codificada | 20000 | 20000 | 20000 |
| Documentos/artefactos de proceso actuales | 54000 total | 54000 total | 9 mapas de hasta6000 cada uno |
| Streams propios conservados por request | 4000 cada uno | 4000 cada uno | 4000 cada uno |
| Request canónico / prompt nativo | 110000 /128000 | 110000 /128000 | 110000 /128000 |
| Role / test / control Docker | 180s /120s /15s | igual | igual |
| Diario host | 80jobs/admisión6000s | igual | igual |

El límite documental acumulado de N/S permite su organización propia y contabiliza
el mapa almacenado completo con metadata y doble codificación JSON, como T. No
se impone a N una fase de6000 bytes. La distribución del límite T por nueve fases
es una restricción del método; esta diferencia y el uso real se informan. No se
confunden iguales techos totales con idénticos recorridos o costes efectivos.

Cada corrección y paquete cerrado rechazado consume autor/rol. Cada revisión
consume revisión/rol. Cada ejecución propia consume un test; una recuperación
del mismo receipt no vuelve a consumir ni a ejecutar. Un transporte incierto
termina sin nueva oportunidad. La ejecución independiente para F no retroalimenta
al autor; se contabiliza por separado y usa la misma política en los tres métodos.

JobStore aplica6000s transcurridos a la admisión de payloads, contando preparación
anterior. No reserva preparación Docker ni es un deadline estricto del intento.
No se afirma tiempo comparativo a partir de sumas de receipts.

## Tiempo total y análisis pendiente

Inicio de un intento: registro antes de construir transporte, inspeccionar imágenes
o preparar inputs. Fin: cierre terminal sellado, incluidos rechazo, error y timeout.
El tiempo monotónico del mismo boot incluye revisiones, correcciones, controles,
ejecuciones, agregación y recuperación dentro del intento. Una interrupción no
reinicia el reloj. Reboot o reloj inválido produce tiempo no verificable y no se
imputa cero ni una ventaja de eficiencia. Todos los intentos fijos tienen una fila.

Construcción de imágenes y registro común se informan como preparación compartida:
su duración se reparte por igual entre todos los intentos previstos, incluidos
fallidos. Se informa además tiempo directo por intento y ratio con preparación.
El desarrollo previo del método no se presenta como coste de generación.

Antes de la comparación reservada se deben implementar y revisar: indicador
común, emparejamiento por instancia/tipo/familia y generación, dependencia por
instancia, familia exacta de intervalos simultáneos95% (ambos contrastes de entrega,
F y tiempo), tamaño/potencia, regla de parada y réplica independiente. F7 sigue
pendiente; este documento no sustituye aquel registro ni concede un ganador.

Antes de cualquier cohorte contabilizada se congelan versión completa, adaptadores,
prompts, políticas, formatos, fuentes/verificador e imágenes/configuración. Dev6
necesita su propia cohorte T fija de10, distribución4RangeAudit/3LedgerFold/3TopoPlan,
sin reemplazos,≥9 completos y dos tipos con nueve fases. Los controles N/S deben
demostrar competencia en desarrollo público. Pilotos y fixtures no son esa cohorte.
La evaluación reservada y réplica mantendrán exactamente la misma versión completa.
