# Ejecutor instalado de pilotos públicos N/S — desarrollo mutable

Este ejecutor no congela una versión completa, no califica T, no establece
competencia ni calcula superioridad. Sigue pendiente resolver/revisar la definición
operativa de N: el controlador actual exige notas antes del código y no ofrece
revisión previa de notas, mientras S dispone de revisión previa y reparación de
SPEC/DESIGN/TASKS. La revisión independiente de diseño identifica F01–F07. No se
admiten generaciones nativas de este plan hasta resolver los hallazgos y revisar
la implementación. Preparar un plan o verificarlo no autoriza una afirmación de
eficacia. Se conservan los seis lugares incluso si el proceso se interrumpe.

`scripts/register_neutral_pilot.py` prepara una política SHA para las posiciones
RangeAudit-N, RangeAudit-S, LedgerFold-N, LedgerFold-S, TopoPlan-N, TopoPlan-S.
No llama a Docker ni modelos; usa fuentes, perfiles y rutas originales explícitos.
No copia credenciales, no sustituye cuentas ni reemplaza un lugar fallido. Un plan
nuevo después de cambiar código es otro desarrollo; no reetiqueta el plan anterior.

La consola instalada `organon-controls run PLAN --plan-sha256 SHA` admite el
desarrollo a través de `NeutralController` y `DockerRoles`. `report` solo lee los
lugares y cierres existentes: no crea carpetas/locks/controladores, inspecciona
Docker, reconcilia ni llama a modelos. Una carpeta pendiente conserva su lugar;
no desaparece del denominador ni equivale a una entrega fallida o exitosa.

## Bytes y frontera confiable

Intérprete, initializer, entrypoint instalado, dependencias y host/daemon son la
frontera confiable. El bootstrap liga sus archivos a fuentes y comprueba inventario
exacto, pero estos dos módulos mínimos ya se ejecutaron al invocar la consola;
no afirma verificarlos antes de ejecutar ni atestiguar un host malicioso. Compila
los demás módulos desde los mismos bytes instalados capturados, sin usar pyc.
Rechaza módulos adicionales ya importados. Cada import declara su SHA comprobado;
el driver exige esa procedencia y las rutas instaladas. Contratos/checker se leen
por acceso nofollow a archivos regulares con un solo enlace y se usan los mismos
bytes cuyo SHA se compara. DockerRoles liga fuentes/inputs antes de preparar cada
operación. El registro explícito del ejecutable Gemini se conserva.

Los contratos N/S separan el contrato funcional común de los requisitos de T;
las copias históricas de tres contratos y las nueve fases del engine no cambian.
No se evalúa cumplimiento N/S por exigencias del engine T.

## Ejecución, evaluación y recuperación

Un inicio externo con boot/host/CLOCK_BOOTTIME antecede a la construcción del
controlador y las inspecciones Docker. El controlador tiene su propio clock
durable y techo de 6000s de admisión; admite hasta 40 roles y tres autores build,
dos tests propios. Ese techo no es deadline de fin ni incluye el checker público
posterior. El checker tiene otra operación Docker offline de hasta120s, registrada
por separado e incluida en el tiempo externo. Usa Python `-I -S -B`, sin imports
desde la entrega ni site-packages. Los módulos
del autor llamados `subprocess.py`, `json.py` u otros no pueden sustituir las
bibliotecas del evaluator. El proceso del programa generado sigue evaluándose
por sus outputs reales bajo las invocaciones fijadas por el checker público.
Preparación compartida y agregación confirmatoria siguen sin medir;
`comparative_time_ratio` permanece desconocido.
Cambiar de boot conserva duración desconocida. Una reanudación no crea un inicio
nuevo. Los costes monetarios y tokens comparables siguen desconocidos.

Reserva del controller y create-intent/nonce Docker son durables antes del
dispatch. Un crash anterior a recibir CID se reconcilia por la identidad propia
ya registrada; no hace restart. Un error de inspección/cleanup no equivale a
ausencia: conserva el mismo lugar y detiene el plan sin sellar tiempo conocido.
El checker público agrega su propia intención durable, con entrega/checker/argv,
imagen y lugar exactos antes de construir su transporte. Su cierre exige recibo
medido, streams y parsing estricto. No se acepta una declaración del autor como
ejecución. Un resultado sin recibo conserva incertidumbre y nunca da otra llamada.

Se evalúa públicamente todo lugar que tenga programa Python, incluso con D/G
rechazado. Ausencias, fallos y resultados desconocidos se conservan sin imputar
scores. La evaluación pública no se manda al autor ni habilita reparación. El
JSON del checker exige schema implícito exacto, denominador fijo, passed entero,
lista de fallos consistente, stdout completo y código de salida correspondiente.
Sus hashes vinculan intento, entrega y checker a recibos Docker reales. Estos son
controles públicos de desarrollo, no F reservado independiente ni blinded.

Un outcome fija su propio inventario completo SHA de los journals antes de su
publicación atómica; el cierre exige el mismo inventario, nunca captura otro
después de una interrupción. Un índice público liga cada nombre de caso a su
input SHA y a la identidad/argumentos/denominador del checker registrado. El
parser exige esa identidad y fallos distintos con schema correcto/passed=false.
`index_neutral_public_cases.py` reproduce el índice sin ejecutar entregas: solo
compila los checkers públicos confiables e invoca sus generadores deterministas.
El SHA global de observaciones es declarado por el checker ejecutado; no se
reconstruyen los resultados individuales exitosos a partir de ese SHA.
Un crash tras outcome puede finalizar el sello únicamente reconstruyendo los
datos terminales ya cerrados, sin dispatch. Inventario o reconstrucción divergente
rechazan el cierre. `report` comprueba la copia y el sello; eso es auditoría de
consistencia del archivo, no una reejecución ni atestación del host/daemon.
`external_F`, `common_complete`, competencia y superioridad nunca se infieren.

## Pendientes para ejecutar y confirmar

Resolver la autonomía/opciones de N y la asimetría de revisión; verificar el
driver instalado y revisar código/controles de recuperación antes de pilotos
nativos. Después integrar T a D/G, evaluar F común por oráculo externo, verificar
imagen completa instalada, congelar versión, calificar sus diez T (≥9/10), y
registrar tamaños/análisis/primario reservado/réplica. Estos seis pilotos no
satisfacen ninguna de esas cohortes ni cambian los resultados históricos dev4.
