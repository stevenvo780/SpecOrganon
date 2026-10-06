# Controlador de desarrollo Libre/SDD — candidato mutable dev6

Alcance: `neutral_controller.NeutralController` ejecuta una máquina de estados N/S
con paquetes `files-v1`, transporte Docker privado y revisión D/G/H ligada a bytes.
Es infraestructura de desarrollo público. No calcula F independiente, paquete
comparativo completo ni superioridad; todavía falta integrar T al indicador común,
congelar una versión completa y registrar/calificar las cohortes requeridas.
Los registros dev4/dev5 y las nueve fases del engine T se conservan sin cambios.

## Tabla de transiciones y recursos

| Etapa | N | S | Rol/resultado permitido | Límite acumulado |
|---|---|---|---|---|
| plan | Notas y criterios con estructura elegida por el autor | SPEC/DESIGN/TASKS solicitados con alternativas y enlaces | Autor; documentos, sin programa ni ejecución | 2 autores de esta etapa |
| plan-review | No aplica | Revisión de sustancia previa al programa | Revisor separado; accept/reject/inconclusive | 2 revisiones de esta etapa |
| program | Programa y README | Programa y README basados en plan | Autor; bytes completos, sin batería propia todavía | 2 autores de etapa y 3 build totales |
| tests | Añadir batería y fixtures, sin modificar programa/README | Igual | Autor; archivos nuevos; argv elegido por host | 2 autores de etapa y 3 build totales |
| measure | Ejecutar entrega vigente | Igual | Docker offline real; salida/cierre medidos | 2 ejecuciones totales del intento, sin reinicio por ID |
| audit | D/G comunes; H no aplica | D/G comunes y H separado | Revisor separado de todos los autores; snapshot exacto | 2 auditorías de esta etapa |
| repair | Tras fallo de ejecución o rechazo D/G, si queda la cadena completa de recursos | Igual | Autor cambia programa/docs, nunca batería original | 2 autores de etapa dentro de los 3 build totales |

Cada rol consume el techo de 40. Los autores de programa/tests/repair comparten
3, incluidos paquetes rechazados por admisión. Los rechazos cerrados conservan el consumo, y las incertidumbres no autorizan
una llamada de reemplazo. Un body nativo inadmisible se distingue de un
transporte incierto: en plan/plan-review S con criterios anteriores se conserva
H=false y se continúa D/G; nunca se admite ese body como rol aceptado. Un paquete admitido por
sintaxis/tamaño puede ser semánticamente incorrecto: sólo una revisión substantiva
y F externo pueden resolverlo. No se transforma una etiqueta en prueba.

Un rechazo/inconclusión de diseño S permite una reparación de plan y otra revisión
con los mismos contadores. Si persiste, se conserva el fallo H y se puede construir
un paquete D/G: un rechazo exclusivamente metodológico no vuelve falso el indicador
común. La auditoría final sólo dispara repair cuando rechaza D/G; cambiar H o
verdict raíz conserva readiness y consumo. N usa notas propias, sin nombres SDD.
La etapa de notas previa al programa es explícita en este candidato de desarrollo;
no equivale a una comparación contra trabajo libre irrestricto ni está registrada
como control reservado. La competencia de los controles y la definición final de
N se revisan antes de cualquier registro comparativo.

La primera batería completa, sus fixtures/configuración añadidos y su argv quedan
sellados. Una reparación no puede reemplazarlos; cada medida posterior ejecuta la
misma batería contra la entrega actual. Se conservan también los criterios y todas
las generaciones anteriores. La reparación sólo cambia archivos ya existentes del programa/documentos, sin
añadir archivos, reemplazar tests ni introducir un shim de su framework. El argv
único es Python de la imagen, `-I -B /input/delivery/<test_file>`; los tests usan
la biblioteca estándar y cargan el programa por ruta absoluta, sin depender del
path de imports de la entrega. Ni una batería propia aprobada ni un juicio
favorable de revisión producen F.

## Custodia, recuperación y reloj

Una reserva durable antecede al dispatch, con ID de trabajo, request exacto, etapa,
hash del estado previo y contadores consumidos. El transporte debe ser DockerRoles
con fuentes registradas; un resultado sin recibo cerrado conserva incertidumbre.
Recuperar el mismo trabajo puede observar su recibo existente; nunca se le asigna
otro ID ni se reinician cuotas. Un cierre terminal impide nuevos trabajos.

La entrega completa vive dentro de una generación JSON publicada atómicamente,
no en un directorio mutable de archivos aplicados uno a uno. Primero se conserva
el packet cerrado; después una transición determinista produce la generación.
El replay comprueba reserva, resultado, generaciones, fuentes, request y recibos.
Reconoce sólo temporales no publicados del escritor atómico por nombre exacto,
tipo regular, único enlace y UID propio. Los ignora sin parsear/admitir sus bytes;
los registros publicados mantienen secuencia y hashes estrictos.
Un crash entre packet y generación vuelve a aplicar únicamente esa transición
pura. Una medida con recibo y terminal cerrados se reconstruye sin necesidad de
su resumen `measured-test.json`, incluso después del corte de admisión. La
limpieza de una ejecución pendiente también se permite después del corte:
inspecciona CID, nonce, etiqueta e imagen, sin restart. Un error del daemon
no equivale a contenedor ausente. Si no se confirma la limpieza, se conserva
la reserva pendiente y no se sella resultado ni tiempo terminal como conocidos. Lo mismo se exige si
falla la preparación del transporte ante registros existentes o desaparece un
launch ligado a intent/dispatch. El retorno false de reconciliación significa
ausencia de una creación pendiente; con registros existentes sólo true permite
cerrar un error. Un marker started puramente sintético en fixture_mode no se
convierte en prueba de dispatch físico.

El reloj CLOCK_BOOTTIME se registra antes de construir transporte/inspeccionar
imágenes; incluye suspensión, recuperación y preparación dentro del intento.
La identidad de boot/host se conserva. Un cambio de boot o reloj inválido cierra
sin aceptación y con tiempo desconocido, nunca cero. El cierre temporal se sella
tras la generación terminal. Los 6000s son admisión transcurrida, no un deadline
estricto de fin: un trabajo admitido aún puede consumir su timeout. El coste de
construcción compartida de imágenes y futuras evaluaciones externas se registrará
por separado; todavía no existe ratio de tiempo comparativo.

## Snapshot y formato nativo

El snapshot schema2 conserva contrato, política, entrega/documentos actuales,
checkpoint chain, mapas completos históricos direccionados por SHA, packets de
roles, recibos de tests y ambos streams reales. Cada checkpoint debe resolver a
un mapa histórico accesible; los bytes JSON escritos por el autor se conservan
exactos. Los locators distinguen captura/documento/entrega/recibo/stream; no convierten
un archivo del autor en ejecución. Las copias consistentes no atestiguan a un
operador malicioso que controle el host y el daemon.

`DockerRoles.verify_role` compara la respuesta con stdout cerrado, request admitido,
argv real del host, metadata, creación/reconciliación, entrada, fuentes y terminal.
Además reconstruye body, uso declarado y reconexiones desde el transcript
interior con los mismos parsers del puente y aplica su contrato ligado. El
preflight Codex reconstruye las features medidas y vincula entorno, comando,
metadata, timeout y ausencia de stdin con la llamada. El ejecutable Gemini debe
coincidir con su SHA inicial al preparar, arrancar y dentro del puente. Estas
comprobaciones acreditan coherencia de los registros observables; la configuración
efectiva restante y la resistencia a un operador host malicioso siguen fuera del
alcance. No arranca ni reconcilia un rol. La verificación de tests exige la entrega actual.
Toda auditoría nueva cambia el snapshot si cambian código, README, documentos o
historia, y requiere una medición vigente. H/verdict no son gates físicos D/G.

Se cuentan bytes de los mapas completos con doble codificación, request canónico
y prompt nativo renderizado. La biblioteca y el puente comparten el renderizador
para detectar el límite exacto de 128000 antes de dispatch. Los streams conservados
son completos y tienen límite de 4000 codificados cada uno; no se recortan como
prueba suficiente. Un exceso obligatorio cierra fallo con consumo ya conservado.
El límite de entrega es 20000 y documental actual 54000; el request 110000.

## Evidencia y límites actuales

La carpeta `evidence/staged-controls-01` distingue fixtures, controles reales
Docker con autores sintéticos, revisión estática y resultados históricos. El
candidato no tiene generaciones nativas dev6 ni piloto competente N/S, versión
completa congelada, release/imágenes dev6 verificadas, nuevo registro reservado,
cohorte fija ≥9/10 ni réplica. `native_ready` nunca puede ser verdadero en fixture
mode; `common_complete` y `external_F` permanecen desconocidos. La meta sigue activa.
