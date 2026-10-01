# Solicitud de activación de las primeras doce R1

Estado observado el 2026-10-01 UTC sobre D124 `b47671b`.
El turno anterior fue progreso: ingreso de evaluaciones implementado,
probado y sellado. Este registro precisa la decisión pendiente; no ejecuta
R1, asigna Q ni modifica los requisitos o los dossiers anteriores.

## Qué está preparado

- [D122](real_route_proposal_2026-10-01/README.md): dos opciones concretas
  para doce coordenadas R1 A/B/C, configuración, materiales, calendario y
  recursos originales. No se suman las dos opciones.
- [D123](authorized_route_entry_2026-10-01/README.md): entrada Responses
  con guards, declaración ligada a run/fuentes/recursos y observación local;
  lector de respuestas incompletas conservando reservas. Resuelve la falta
  de implementación de transporte/lector descrita en el corte histórico D122.
  Sus controles no acreditan acceso o consumo real.
- [D124](external_rating_ingress_2026-10-01/README.md): lector de una nota
  DEV externa con originales/hash e incidentes separados. No crea juicio
  humano ni autentica identidad, independencia, custodia o cegamiento.

El intake nativo acotado contrastó estos tres cortes y confirmó que la
siguiente acción requiere decisión del dueño; no propuso más controles
sintéticos. Cuota observada 22:13:37 UTC: Codex sin ventanas verificadas;
Gemini 97% de cinco horas y 95% semanal. No es permiso ni acceso Responses.

## Opciones revisadas

Se cotejaron de nuevo las tarifas oficiales Standard de texto/contexto corto.
Coinciden con el forecast D122: Astra input/cache-read/cache-write/output
10/1/12,50/50 USD por millón; Luna 0,10/0,01/0,125/0,50 USD por millón.
[Astra](https://developers.openai.com/api/docs/models/gpt-6-astra),
[Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) y
[tarifas](https://developers.openai.com/api/docs/pricing).

| Una opción para 12 R1 | Cota condicional sólo de tokens del modelo | Saldo local propuesto |
| --- | ---: | ---: |
| Astra `high` | USD 48,001536 | USD 60, máximo USD 5 por celda |
| Luna `high` | USD 0,481536 | USD 0,60, máximo USD 0,05 por celda |

La cota es inferencia aritmética: doce veces 80.000 tokens medidos a la
tarifa máxima y margen de redondeo por hasta 128 solicitudes por celda.
El presupuesto es compartido por los cuatro roles; no se multiplica por rol.
La configuración común incluye 64 tools y 5.400 segundos activos por celda,
8.192 tokens de salida por request y los límites publicados de turnos/épocas.
Se propone Python 3.11.15, el intérprete ya validado, para una única ruta.

No es coste total ni tope remoto de factura. No incluye impuestos, conteo
remoto, herramientas, revisión humana o primas regionales. Esas fuentes y
condiciones deben fijarse; ausencia no significa coste cero. Si no aplican
las tarifas propuestas o faltan telemetría/recursos, no se libera R1.

Astra está descrito oficialmente para trabajo exigente y Luna para tareas
acotadas y de gran volumen; eso no prueba equivalencia de calidad ni la
suficiencia del límite de salida para estas tareas. Las páginas consultadas
listan aliases; no acreditan un snapshot servido o acceso de esta cuenta.
No se selecciona Luna por haberlo usado en intakes internos.

## Decisión necesaria y límites de autorización

El dueño debe elegir una opción y autorizar explícitamente su saldo local
para tokens del modelo. Los acuerdos suministrados, AGENTS §7, exigen permiso
directo antes de gastar. Continuar el desarrollo o disponer de cuota no lo
autoriza. No se autorizaron llamadas API experimentales durante este turno.

El dueño indicó un revisor y custodio disponibles. Está pendiente la pregunta
ya enviada sobre si son personas distintas. No se repite ni se presupone
la respuesta. Antes de liberar se deben fijar sus condiciones de revisión,
competencia/independencia, correspondencia de IDs, custodia y cronología,
además de la medición de tiempo humano y costes. Un revisor puede aportar
una nota DEV; la confirmación final mantiene dos evaluadores y un tercero
ante las discrepancias previstas. No se reduce ni traslada esa regla a DEV.

La autorización solicitada no abre reserva, R2 o campo y no convierte las
puertas restantes en cumplidas. Elegida la ruta, se cierra acceso/modelo/
esfuerzo/telemetría y evaluación antes del freeze real y la liberación.
Un resultado incompleto se conserva y detiene; no se reejecuta para sustituirlo
por uno favorable. Luego12 R1 → adaptación/freeze →12 R2/selección →
confirmación N/SDD/T con modelos/esfuerzos/agentes/ablaciones → campo y
transferencia real.

**C1 técnico D107; C2–C5 No demostrado; 0/24 formales.** No se inició ni
se confirmó un proceso R1 propio: el siguiente paso está pendiente de autorización/input
humano y estado externo. El objetivo continúa activo e incompleto.
