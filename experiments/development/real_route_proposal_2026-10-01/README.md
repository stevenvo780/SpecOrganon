# D122 — opciones concretas para una ruta R1

[Plan previo](plan.md), [clarificación previa](planning_clarification.md),
[fuentes oficiales y snapshot de inventario](sources.json),
[forecast](forecast.json) y [puertas de ejecución](readiness.md).

## Resultado local

Dos configuraciones alternativas explícitas de OpenAI Responses `high`:
[Astra](candidates/astra/configuration.json) y
[Luna](candidates/luna/configuration.json). Runtime propuesto idéntico:
cuatro roles, máximo 8.192 tokens de salida por solicitud, 32 turnos de
líder/workers y uno del reviewer, ocho épocas y tools de hasta 30 segundos.
Cada celda comparte 80.000 tokens medidos, 128 solicitudes, 64 tools y
5.400 segundos activos; no se multiplica el saldo por los cuatro roles.

**Cuatro builds y cuatro verifies originales pasaron**, dos opciones ×
Python 3.11.15/3.12.3. Cada bundle tiene doce celdas y cuatro bloques.
Además, el validador original aceptó los perfiles de roles de las doce
celdas de cada bundle. No creó runtimes, claims ni liberaciones; no se
invocó `step`, conteo remoto o envíos al proveedor. Los calendarios son
preparaciones sin sello/autorización real y no resultados R1.

Se guardan argv, exits, stdout/stderr, inventarios y calendarios reales en
[captura 311](checks/build311_attempt01/report.json) y
[captura 312](checks/build312_attempt01/report.json). Los bytes de los
candidatos no cambiaron. Los bundles completos quedan en las rutas
temporales registradas; este dossier retiene sus recibos/inventarios y
calendarios, no copias completas de los assets. Pueden reconstruirse con
el preparador y las fuentes originales preservadas. No son paquetes de
ejecución portátiles ni una restauración de autoridad.

El mismo seed fija la política de orden, pero el algoritmo publicado usa
modelo e inputs en hashes derivados. Los órdenes originales se conservan;
se cotejan coordenadas, materiales y recursos. Sólo una opción y un
intérprete podrían seleccionarse para doce R1. No se proponen 24 ejecuciones
ni una comparación intermodelo a partir de esta preparación.

## Cifras revisables

| Opción | Techo condicional de tokens de modelo, 12 R1 | Saldo local propuesto |
| --- | ---: | ---: |
| Astra `high` | USD 48,001536 | USD 60, máximo USD 5/celda |
| Luna `high` | USD 0,481536 | USD 0,60, máximo USD 0,05/celda |

Se aplican tarifas Standard actuales de texto/contexto corto, sin premium;
la cota incluye margen por redondeo de cada solicitud. Cache-read/write son
particiones de input; razonamiento está en output. La fórmula, unidades y
condiciones se conservan en `forecast.json`. Las tarifas son datos de las
páginas oficiales; las cotas son inferencias aritméticas, no previsiones de
consumo esperado, facturas ni autorización. [Astra](https://developers.openai.com/api/docs/models/gpt-6-astra),
[Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) y
[caché](https://developers.openai.com/api/docs/guides/prompt-caching).

Costes de tools, conteo remoto, H, evaluación, impuestos, regionalización y
estudio completo quedan nulos con motivo, nunca cero. Tampoco se acredita
acceso, proveedor servido, snapshot o esfuerzo efectivo. Alias en `version`
no fija una versión servida. El saldo local no controla facturación remota.

## Límites y siguiente acción

La CLI actual `step` sólo admite fixture. La API Python permite transportes,
pero falta un entrypoint real conservando los guards y observación originales.
El coordinado exige `completed`/modelo exacto antes de liquidar; `incomplete`
o un ID servido diferente podrían dejar una reserva sin conciliar aunque haya
coste. La revisión encontró estos límites en código; no reprodujo una llamada
remota. Cerrarlos precede a R1, junto con conteo/uso y evaluación independiente.

El máximo 8.192 incluye razonamiento y formato; su suficiencia para `high`
no está probada. La recomendación inicial oficial de 25.000 es orientación,
no un mínimo obligatorio ni evidencia de que el perfil vaya a fallar.
[Guía de razonamiento](https://developers.openai.com/api/docs/guides/reasoning).

Luna ayudó con inventario acotado; root cotejó sus hallazgos y el revisor
independiente cerró **PASS_local_scope**, sin hallazgos materiales abiertos.
[Veredicto](review/final_review.json), [resumen](review/short_review.md) y
[aporte de Luna](luna_findings.md). No se midió calidad relativa de modelos.
Elegir modelo/ruta, acceso del operador, presupuesto y evaluación requiere
decisiones concretas del dueño; AGENTS §7 exige su autorización para gasto.
La aprobación no sustituye las demás puertas y no habilita R2/reserva/campo.

**C1 técnico D107 preservado; C2–C5 No demostrado; 0/24 formales.**
Orden pendiente: 12 R1 → adaptación/freeze → 12 R2/selección → confirmación
independiente → campo causal y transferencia. No hay porcentaje global ni
fecha de cierre defendible. El objetivo permanece incompleto.

Los 5.879 pins y receipt D121 se verificaron antes y después del build,
antes de avanzar docs activos. Cortes históricos y sus fuentes permanecen
intactos; los cuatro docs activos anteriores se conservan en Git `9f90b79`.
Se registra el primer lanzamiento fallido del sealer por import aislado y
su límite de captura en [nota](checks/first_launch_note.json); la invocación
corregida conserva streams. El primer check puro 312 del worker falló por
ruta relativa; esa lectura no alteró configuración ni fuentes y no fue un
fallo del esquema. Su error sólo se conservó en salida de herramienta.
El revisor conservó su primera lectura fallida de modos Git/fs en
`review/audit311_attempt01`; no fue un fallo del producto y no alcanzó verify.

`seal_evidence.py build` crea una sola vez el receipt de este dossier y los
cuatro docs activos, preservando todos los demás pins D121 y los cuatro
blobs históricos. `verify --head` coteja live/índice/HEAD y el baseline; no
acredita custodia externa, proveedores ni autorización experimental.
