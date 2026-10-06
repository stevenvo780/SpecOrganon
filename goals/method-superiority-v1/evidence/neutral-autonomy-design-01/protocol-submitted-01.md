# N con autonomía de estrategia — propuesta de desarrollo v2

Estado: propuesta pendiente de revisión independiente y de implementación.
Este documento no autoriza generaciones nativas, no sustituye planes anteriores,
no congela la versión instalada y no demuestra competencia ni superioridad.
Su propósito es resolver el hallazgo de diseño F06 antes del próximo piloto.

## Alcance y comparación

N será trabajo libre respecto al proceso de solución: puede empezar por código,
planificar primero, combinar código, documentación y pruebas, pedir retroalimentación
o medir su batería. No se le exige una fase de notas, notas anteriores al código,
nombres SPEC/DESIGN/TASKS, diseño por alternativas ni artefactos del engine T.
El contrato funcional, el paquete común D/G y el presupuesto experimental sí
son comunes. "Libre" no significa recursos ilimitados: ambos brazos usan roles
de generación de texto sin herramientas internas, archivos stdlib y ejecución
offline por el host. La inferencia futura se limitará a esa modalidad registrada;
no se generaliza a agentes interactivos con herramientas irrestrictas.

S conserva especificación, alternativas/diseño y tareas anteriores al código,
revisión previa y reparación del plan, construcción, batería propia, medición,
revisión D/G/H y reparación. Sus requisitos H permanecen separados del paquete
común. T conserva sus nueve fases y requisitos; no se altera en este desarrollo.
Los contratos públicos N/S anteriores y las campañas cerradas permanecen iguales.
Una implementación nueva usará identidad y registro nuevos, sin reabrir un intento.

## Recursos y oportunidades

Para el siguiente piloto N/S se fijarán prospectivamente, en ambos brazos:

| Recurso | N | S |
|---|---|---|
| Invocaciones de autor | hasta 5 actualizaciones libres | hasta 2 de plan y 3 acumuladas de construcción/pruebas/reparación |
| Invocaciones de revisor | hasta 4, incluida la auditoría D/G final | hasta 2 de plan y 2 de auditoría final |
| Mediciones de batería propia | hasta 2 | hasta 2 |
| Presupuesto general de roles | hasta 40, conservando el techo histórico como límite adicional | igual |
| Archivos/documentos/streams/request/prompt | 20000/54000/4000/110000/128000 bytes JSON | igual |
| Admisión temporal del controlador | 6000 s desde inicio durable previo a preparación | igual |
| Evaluación pública posterior | operación offline independiente, hasta 120 s | igual |

Una invocación de autor cuenta incluso si solo pide revisión/medición, devuelve
contenido inválido o no cambia nada. Cada revisión también consume su recurso;
no hay director gratuito, reparación gratis ni reenviados ocultos. N puede gastar
sus cinco actualizaciones en el orden que elija; S asigna esos mismos cinco cupos
a su estructura. Esta diferencia de asignación es el tratamiento deliberado.
N no conserva el antiguo límite de tres autores build, pues cinco actualizaciones
autónomas y un límite build de tres volverían a imponer una clasificación de fases.
La disponibilidad de slots no es competencia empírica: esta se observará después.
No se suman estas nueve oportunidades a cuarenta nuevas: cada una cuenta también
contra el techo general. Los intentos fallidos consumen el recurso reservado.

## Interfaz autónoma y estado

La respuesta del autor conserva `schema:1, files, documents, reason`; un documento
operativo reservado `controller-next.json` contiene exactamente `{"action": A}`,
con A igual a `continue`, `review`, `measure` o `audit`. Se extrae y valida con
JSON estricto, sin duplicados, no finitos ni claves sobrantes, antes de admitir
contenido. Ese documento no entra en la entrega, notas, criterios ni auditoría
semántica. Es protocolo de transporte, no un artefacto metodológico. Debe estar
presente incluso si no hay cambios; una respuesta solo operativa es admisible.
Se conservarán bytes íntegros y decisión en reserva, resultado y generación.

N empieza con una actualización libre, sin documentos previos obligatorios.
`files` y `documents` son parches sobre el último mapa capturado: no hay borrado
implícito ni sustitución de intento. Una actualización puede incluir programa,
README y batería juntos. `continue` concede otra actualización si queda cupo.
`review` solicita feedback independiente del paquete actual, aunque solo haya
ideas, código sin criterios o documentación incompleta; no exige aceptación.
El feedback inspecciona la estrategia elegida y defectos reales, nunca impone SDD.
El mismo contrato y todos los resultados anteriores llegan al autor siguiente.

`measure` requiere programa Python, README y el archivo de batería del argv fijo,
y una declaración sustantiva de criterios anterior a esa ejecución. Los criterios
pueden aparecer en README o documentos arbitrarios, incluso después del código.
No se acepta una cadena no vacía como prueba de sustancia: se captura el mapa
íntegro anterior a la medición y el auditor D/G juzga G1/G2/G3. El contrato original
del host es inmutable y limita los criterios posteriores. La batería completa y
sus dependencias de prueba se sellan en la primera medida; futuras reparaciones
solo pueden modificar programa/documentación, nunca añadir archivos ni debilitar
la batería. Es la misma regla conservadora de S, explícita al autor desde inicio.
Se prohíbe modificar README/archivos por esa vía si forman parte de la batería
sellada; la separación entre código bajo prueba y paquete de pruebas deberá ser
declarada, validada y capturada antes de medir, sin depender de extensiones.

Después de una medida, N recibe su recibo real y puede consumir otra actualización
si queda cupo. Puede solicitar revisión o una segunda medida. Toda modificación
de archivos o documentos después de una medida invalida su actualidad para
auditoría final, incluso si cambia solo README. `audit` requiere batería propia
pasada y actual, criterios anteriores a ella y cupo de revisor disponible; ejecuta
la auditoría común independiente de este snapshot, con H vacío para N. D/G rechazado
devuelve defectos sin declarar éxito; una reparación necesita otro autor y otra
medición actual. Al agotarse recursos se cierra como fallo conservando evidencia.

No se concede una nueva actualización automáticamente después de gastar la quinta.
Su acción puede medir y después solicitar auditoría final sin otro autor, o auditar
directamente si ya existe medida actual. Para que esta ruta sea inequívoca, `measure`
tras la última actualización ejecuta la medida y, si pasa, agenda auditoría D/G;
si falla, cierra fallido. Si quedan autores, el resultado vuelve a la actualización
libre. La regla y sus costes son explícitos desde inicio. Un rechazo, acción inválida
o paquete inadmisible consume su reserva y vuelve a actualizar si queda cupo; no
ejecuta una acción parcialmente admitida. La última respuesta inválida cierra fallo.

## Revisión y custodia

Feedback intermedio: schema1 review con verdict/reason/findings/tests_executed=false,
con invocación independiente e inputs inmutables; accept no es gate ni D/G.
Auditoría final: el formato enlazado D/G/H existente y sus verificaciones físicas,
revisión separada del autor y medida actual; ningún veredicto raíz sustituye D/G.
Rechazo de feedback nunca obliga a una fase ni esquema nuevos. Revisor y autor
reciben sus presupuestos restantes exactos. N puede omitir feedback previo, usar
dos revisiones de notas como S, o dedicarlo a código ya creado. No se le descuentan
revisiones por no haber pedido una al comienzo; no se conceden revisiones gratuitas.

Se reutilizan intención durable anterior a dispatch, snapshots de los mismos bytes,
recibos cerrados y reconciliación de la operación exacta. Una operación incierta
retiene el lugar y detiene el plan; no se reemplaza por otra. Inicio boot/host y
CLOCK_BOOTTIME sobreviven reinicios en el mismo boot; cambiar boot deja tiempo
desconocido. Contadores, decisiones, mapas y reservas se reconstruyen determinísticamente.
El JSON operativo se preserva en el resultado crudo y en el historial de control,
sin confundirse con sustancia documental. Bootstrap/host/dependencias siguen siendo
frontera confiable, sin atestación de un host malicioso.

El informe conserva seis posiciones públicas y todos los fallos/unknown/no iniciados.
Funcionalidad pública, D/G, H, consumo y tiempo se muestran separados; F externo,
common_complete, coste monetario comparable y superioridad permanecen null/false.
No se presenta la suma de tiempos cerrados como razón media confirmatoria.

## Admisión y verificación exigidas

Antes de cualquier nueva generación experimental: revisión independiente de este
contrato, implementación en versión nueva, bootstrap instalado/CLI/MCP/Docker y
controles negativos con recuperación; revisión del código y recibos reales.
Un contrato aceptado solo resuelve el diseño F06; no valida su implementación.
Los seis pilotos públicos fijos nuevos no sustituyen la calificación de diez T
propios de la versión completa (al menos nueve completos, tres tipos y nueve fases
en al menos dos tipos), ni el primario reservado y la réplica independiente.
Mantener las restricciones de fuente, oráculos, cuentas y publicación del GOAL.

Controles mínimos de implementación:

1. Código antes de notas admitido; README/criterios antes de medida capturados.
2. Actualización conjunta con código/batería; ausencia de criterios no imputa G pass.
3. Dos ciclos de feedback y revisión sin SPEC/DESIGN/TASKS obligatorios.
4. Cinco autores y cuatro revisores realmente cobrados, incluido autor solo operativo.
5. Mismos techos S y nuevas reservas N; agotamiento no concede extras ni director gratis.
6. Clasificación original de batería/dependencias sellada antes de medir; intento de
   alterar bytes/añadir shadow module/debilitar fixtures rechazado conservando consumo.
7. Código o documento cambiado después de medida impide auditoría con recibo anterior.
8. Quinta actualización→medida→auditoría pasada; fallo o rechazo sin cupos conserva fallo.
9. Crash antes/después de cierre/reconciliación, reinicio/boot distinto, parser operativo
   inválido y adulteración de historia no disparan otra operación ni reinician cupos.
10. Report instalado sin Docker/dispatch; oráculo público y recuperación con programa
    deliberadamente roto, denominadores completos y ninguna inferencia confirmatoria.
