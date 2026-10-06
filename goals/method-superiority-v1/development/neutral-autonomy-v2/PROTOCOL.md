# N con autonomía de estrategia — propuesta de desarrollo v2

Estado: diseño inicial aceptado con cinco precisiones pendientes de implementación.
Esta revisión del texto aplica F06-01 a F06-05; no tiene revisión de código completo.
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
contra el techo general. El máximo ejecutable N/S es nueve roles (cinco autores
más cuatro revisores); cuarenta es un techo nominal adicional, no disponibilidad
efectiva. El reporte de capacidad restante de roles usa el máximo ejecutable nueve
y llega a cero cuando los dos cupos se agotan. Los intentos fallidos consumen su reserva.

## Interfaz autónoma y estado

La respuesta del autor conserva `schema:1, files, documents, reason`; un documento
operativo reservado `controller-next.json` contiene exactamente `{"action": A}`,
con A igual a `continue`, `review`, `measure` o `audit`. Se extrae y valida con
JSON estricto, sin duplicados, no finitos ni claves sobrantes, antes de admitir
contenido. Ese documento no entra en la entrega, notas, criterios ni auditoría
semántica. Su única ubicación válida es `documents`; su presencia en `files`
rechaza todo el parche y la acción, conservando el cobro del turno.
Es protocolo de transporte, no un artefacto metodológico. Debe estar
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

`measure` requiere físicamente programa Python, README y el archivo de batería del
argv fijo, y captura íntegra del mapa de programa/documentación anterior a ejecución.
Esa captura ofrece los criterios que existan; no inventa criterios ni aceptación.
Los criterios pueden aparecer en README o documentos arbitrarios, incluso después
del código. El host verifica únicamente precedencia y custodia de esa captura;
no decide sustancia por cadenas no vacías ni exige notas adicionales para medir.
El auditor independiente D/G juzga G1/G2/G3 con evidencia enlazada. Criterios ausentes,
vacíos o retrospectivos producen fail/inconclusive semántico, nunca pass inferido.
El contrato original del host es inmutable y limita los criterios posteriores.
La batería completa y
sus dependencias de prueba se sellan en la primera medida; futuras reparaciones
solo pueden modificar programa/documentación, nunca añadir archivos ni debilitar
la batería. Es la misma regla conservadora de S, explícita al autor desde inicio.
Se prohíbe modificar README/archivos por esa vía si forman parte de la batería
sellada; la separación entre código bajo prueba y paquete de pruebas deberá ser
declarada, validada y capturada antes de medir, sin depender de extensiones.
En la primera solicitud `measure`, el autor incluye además el documento reservado
`controller-test-files.json`, exclusivamente en `documents`, con JSON estricto
`{"test_files":[...],"mutable_files":[...]}`. Ambas listas son no vacías y tienen
rutas distintas, seguras, presentes en `files`; son disjuntas y su unión es exactamente
el conjunto de archivos de la entrega. `test_files` incluye obligatoriamente el script
del argv y todos los fixtures/dependencias de la batería. No se infiere por extensión.
`mutable_files` enumera código bajo prueba/documentación que puede repararse; no incluye
el script de tests. Si la batería consume README como fixture, README debe estar entre
los test_files y sus bytes no pueden cambiar. Esta declaración se extrae del mapa
documental, se preserva en el resultado/control histórico y queda sellada junto con
los bytes originales antes del dispatch de la primera medida. No sustituye un recibo.
Una declaración falsa de dependencias constituye defecto sustantivo para la auditoría,
no algo que la mera partición mecánica o una firma hagan verdadero. La frontera
conserva host/daemon confiable; no promete inferir estáticamente todos los imports
posibles de Python ni demostrar que una batería sea pertinente por nombres.
Tras sellar la partición no se pueden añadir archivos ni cambiar listas o bytes de
test_files; si el documento se reenvía debe contener la misma partición. No se exige
reenviarlo en solicitudes siguientes. Su presencia en files o en acciones distintas
de measure es inválida. Un módulo shadow adicional posterior al sello es rechazado.

Después de una medida, N recibe su recibo real y puede consumir otra actualización
si queda cupo. Puede solicitar revisión o una segunda medida. Toda modificación
de los hashes de files o documents después de una medida invalida su actualidad para
auditoría final, incluso si cambia solo README. `audit` requiere batería propia
pasada y actual, criterios anteriores a ella y cupo de revisor disponible; ejecuta
la auditoría común independiente de este snapshot, con H vacío para N. D/G rechazado
devuelve defectos sin declarar éxito; una reparación necesita otro autor y otra
medición actual. Una respuesta puramente operativa o un parche idempotente no cambia
esos hashes y conserva la vigencia del recibo. Los documentos operativos extraídos
no pertenecen a esos mapas. Al agotarse recursos se cierra como fallo con evidencia.

No se concede una nueva actualización automáticamente después de gastar la quinta.
Su acción puede medir y después solicitar auditoría final sin otro autor, o auditar
directamente si ya existe medida actual. Para que esta ruta sea inequívoca, `measure`
tras la última actualización ejecuta la medida y, si pasa, agenda auditoría D/G;
si falla, cierra fallido. Si quedan autores, el resultado vuelve a la actualización
libre. Tras reservar el quinto autor, `continue` y `review` son inválidos: consumen
esa reserva y cierran fallo sin despachar más autor ni feedback. Solo `measure`
(con cupos propios y de auditoría restantes) o `audit` (con medida pasada actual y
cupo de revisor) son admisibles. Una acción sin su cupo requerido rechaza el parche
completo y la acción, sin aplicar cambios ni enviar otra operación. La regla y sus
costes son explícitos desde inicio. Un rechazo, acción inválida
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

## Enmienda prospectiva de transporte dev8: referencias lossless

La versión nueva incorpora `lossless-package-context-v1` según
`../REQUEST_CONTENT_V1.md`. El contrato funcional, todos los resultados anteriores,
los criterios originales, capturas, metadatos, orden y recibos siguen disponibles;
solo se representa una vez cada string repetido mediante posiciones y referencias
con contenido presente en la misma solicitud. Los presupuestos 110000/128000 y
los límites de entrega no cambian. La identidad canónica tras reconstrucción se
verifica antes de enviar. La auditoría mantiene sus localizadores y bytes originales.
Esta enmienda no altera ni reabre el registro dev7 y por sí sola no admite otro
piloto, prueba competencia ni congela una versión completa.
