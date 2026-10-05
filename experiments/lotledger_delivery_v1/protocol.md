# LotLedger v1: protocolo candidato de ingeniería

No registrado; no autoriza generación. Identidad única `lotledger-delivery-v1`,
caso `cases/lotledger_v1`, posterior a la candidata técnica schema8. Se preservan
LogLens, IntervalDesk, CSVShape y todas las campañas cerradas. Si esta identidad
falla, se publica su resultado, sin reemplazo, ampliación de presupuesto o cuenta.

## Mandato, roles y separación

El operador delegó entregar software autónomo verificable. Codex escogió esta
herramienta como decisión técnica; no afirmar que el operador eligió personalmente
la arquitectura. Política local con actor `human:owner`, declarativa, sin autenticar
identidades o custodia. Autor Codex gpt-6.1-sol, esfuerzo medium, volumen ORIGINAL
`specorganon-lab_codex-home`; revisor Gemini 3.8 Flash (Medium), perfil ORIGINAL
`/home/stev/.gemini` y ejecutable `/home/stev/.local/bin/agy`. Contenedores distintos
por llamada; sólo el controlador escribe el ledger. Muse revisa el diseño por
texto y no genera ni acepta las fases de esta identidad.

El autor/revisor de fases recibe contrato, mandato, datos públicos, estado, informe,
tarea y snapshots readonly. Nunca se montan reserved.py, subjects.py, matriz,
diarios ni expectativas reservadas. La revisión de diseño del evaluador es otra
llamada independiente; no reusa esa conversación para generar o revisar fases.
Pruebas propias y sujetos reservados corren sin red/perfiles, entrega readonly.
El host conserva recetas, expectativas y recibos; el sujeto sólo recibe código,
stdin y argv. El host y daemon Docker son autoridad confiable.

## Congelación y límites

Antes de inicializar: revisión nativa aceptada de contrato/protocolo/fuentes de
admisión/evaluador, controles del evaluador ejecutados, hashes de todos esos
fuentes, observaciones públicas, tests, revisión, contexto/catálogo públicos e
imágenes inmutables. El registro debe preceder cualquier caso/primera admisión.
Cambiar fuentes después del freeze invalida y cierra la identidad; no autoriza otra.
El registro vincula todos los módulos del toolkit, los cinco scripts importados o
ejecutados por este trial, los módulos LotLedger, documentos/contexto/catálogo y
los controles pertinentes. No incluye scripts históricos ajenos a esa ejecución.
El guard de módulos cargados sigue rechazando cualquier import local no vinculado;
un control adicional comprueba el cierre de imports de los scripts registrados.
La revisión recibe completos todos los archivos vinculados, sin sustituir código
por una lista de hashes. Esto delimita custodia de fuentes, no reduce el objetivo.

Schema8: techo40 llamadas incluyendo auditoría final,180s/llamada,6000s desde
primera admisión,128000bytes de prompt renderizado/llamada,3145728 acumulados,
2MiB/stream nativo. <=2 autores/fase, excepto build<=3 (código,tests,reparación sólo
tras fallo/rechazo); <=2 revisiones y <=2 conformidades/fase, contadas por separado.
<=6 artefactos y6000bytes JSON escapados/fase; archivos<=20000bytes JSON escapados;
salida de tests<=4000bytes escapados. <=2 pruebas propias de120s, segunda sólo tras
cambio ejecutable/argv por fallo o rechazo, nunca por cambiar README o texto.
Techo común no garantiza acabar. No aumentar cotas tras observar respuestas.

Consultar catálogo/cuotas originales antes de roles reales. Captura y observación
<=600s antes de cada admisión; ausencia declarada unknown, agotamiento explícito
o datos vencidos pausan antes del envío. Refrescar cuota no renueva reloj/slots.
No reactivar sondeo Codex, comprar créditos, copiar perfiles o cambiar cuentas.
Un handle incierto se reconcilia sin relanzar. Error de proveedor, formato,
timeout, límite o rechazo persistente cierra la identidad y conserva evidencia.

## Sustancia de fases y evidencia anterior a medir

Frame delimita actor/problema/frontera locales, sin demanda humana inventada.
Critique explicita normas, supuesto discutible y encuadres distintos, incluyendo
integridad/idempotencia frente a reparación silenciosa; aprobación registra mandato.
Study fija pregunta falsable, hipótesis, protocolo, población/colección/comparación/
incertidumbre y unidades. Observe usa observaciones públicas reales con fuente,
fecha, localizador y método; Explain separa observación, inferencia y incertidumbre.
Compare incluye >=2 opciones viables distintas, una basada en SQLite/transacciones
y herramienta existente sin fingir que SQLite implementa todo el contrato JSONL.
Compara unicidad, duplicados con contenido, errores por statement y rollback global,
riesgos y costes desconocidos. Specify deriva decisión y requisitos trazables a
problema/norma/evidencia/protocolo. No copiar valores posteriores a criterios previos.

Datos disponibles: seis primitivas SQLite medidas en la imagen fija, con consultas,
streams y hashes en public-sqlite-observations.json. Población: seis assertions SQL
sintéticas, no usuarios ni entradas LotLedger. Son evidencia sobre la alternativa;
no son baseline de conformidad del programa. No sustituir una métrica por otra ni
inventar baseline0. La selección de indicadores debe declarar su población propia.

Criterios anteriores a build, sin compensación: F pruebas propias pertinentes
pasadas con recibo exacto y ejemplos correctos, reserva externa73/73 para conformidad
completa; D documentación8/8; M nueve fases aceptadas con argumentos sustantivos,
trazas vigentes y auditoría6/6. Pruebas propias no prueban F reservado. D/M se miden
externamente después del cierre, sin completar el ledger retrospectivamente.

Build entrega programa+README y después tests ejecutables, un implementation y un
test vigentes enlazados directamente a requisitos/criterios. El controlador ejecuta
y registra el test; el autor no declara passed. Validate registra resultados reales,
baseline si existe para la misma población y métricas, incertidumbre/efectos/coste.
Antes del reservado no hay prueba de conformidad completa ni mejora sobre una
baseline del programa: esos juicios deben quedar no_demostrado cuando falte evidencia.
Un resultado propio parcial puede describirse con su recibo; no convertirlo en
comparación causal o eficacia de campo. Un juicio decisivo, si está fundamentado,
debe cumplir íntegramente las obligaciones vigentes del motor (un criterio/baseline/
result trazados, misma métrica/unidad/población y test directamente pertinente).
No rebajar el motor ni inventar una medición para obtener un gate verde.

## Auditoría y cierre de ingeniería

Checklist D8: instalación Python3.12/stdlib; interfaz stdin/sin argv; ejemplo1 con
comando completo/salida; ejemplo2 con comando/salida; error exacto; todos los límites;
semántica orden/duplicados/Unicode; tests ejecutables y alcance honesto.
Checklist M6:9fases realmente aceptadas; trazas requisito/criterio vigentes; alternativas
sustantivas; recibos reales de test de entrega exacta; revisiones independientes físicas;
alcance sin afirmaciones reservadas/campo/causales/costes inventados. Una única llamada
final del revisor de fases después del gate y antes del reservado, dentro del techo40.
Sin reparar después de esa auditoría o de conocer resultados reservados.

Los controles C1–C8 de goals/autonomous-software-v1/controller-specification.md
conservan su texto/historia. Para esta identidad nueva se aplican explícitamente:
C1 nueve fases LotLedger vigentes con snapshots/revisores reales y entrega contractual;
C2 trazas de cada requisito/criterio a problema/norma/evidencia/protocolo/decisión;
C3 test limpio real que cubre éxito, error, duplicados/bordes con recibos registrados;
C4 README útil y dos ejemplos ejecutados desde carpeta limpia;
C5 retirada de evidencia y rechazo bloquean avance/publicación;
C6 contradicción abierta bloquea descendiente/publicación;
C7 cambio de premisa vuelve obsoletos descendientes/revisiones y no acepta recibo viejo;
C8 SIGKILL después del recibo reusa sin llamadas/eventos duplicados y antes del recibo
queda inconcluso sin relanzar. C5–C8 son controles sintéticos del mecanismo, separados
del caso y revalidados pertinentemente. Faltante/incierto no es satisfecho.

Matriz de73recetas en reserved.py: legal11, identity10, order10, types13, format10,
boundaries19;2ejemplos públicos incluidos. Las60recetas originales se conservan y
se añaden ausencia de LF final, CR/LF escapados y cinco bordes de strings id/site/
from/to antes de registro/autores. También se añaden lot/site/from/to vacíos y byte NUL crudo.
El snapshot original60-recipes.json conserva los bytes canónicos de las60
recetas del commit895d9a2fc6d528b7be223969673e65bfb1bbdc31, SHA256
be25952e519f52a32947861737ae5fd7b8a53819ba34a0f4c5cf7bbff210fe61.
Se vincula y suministra completo al revisor, y un control compara cada receta
original con la matriz actual por ID, incluidos stdin/argv/expected. No se monta
a autores ni revisores de fases. El draft comparativo posterior no pertenece al
freeze de LotLedger; modificarlo no altera esta identidad. Esto amplía el corpus
sin retirar recetas. Cobertura
determinista finita, no potencia estadística ni prueba exhaustiva de todo input. No
selección por resultados. Expectativas explícitas y metamorfismos fijados antes de
generar; nunca construir oráculo a partir del programa. Una invocación por receta,
3s/2CPU/1GiB/128pids/2MiB por stream. Ausencia de programa cuenta73fallos, no omisión.
Timeout/crash/salida truncada del sujeto es fallo; infraestructura incierta se publica
como inconclusa. El evaluador conserva códigos, tiempos, hashes y streams privados,
y sólo reusa recibos cerrados con idénticos inputs/entrega.

completed_technical requiere C1–C8, gate9,D8/8,M6/6,F73/73, README/tests/paquete real.
Otro resultado se publica delivery_failed, infra_inconclusive o not_started, con
denominadores fijos. Este hito no basta para cerrar la goal. Después se requiere
la campaña NUEVA multitype N/S/T/ablación de experiments/software_comparison_v3/
protocol-draft.md, congelada y revisada antes de sus autores, y release/publicación
finales. Ese protocolo es requisito de la comparación, no permiso para iniciarla
por aceptar LotLedger; no se eligen tareas a partir de una victoria de LotLedger.

## Red, identidad y custodia de perfiles nativos

Los sujetos y tests de entrega tienen red none y no montan credenciales. Autor y
revisor nativos necesitan red para sus proveedores y usan exclusivamente sus
perfiles originales, sin copiar credenciales ni montar casos, evaluadores o recetas.
Las imágenes verificadas declaran USER codex (nativa) y USER ubuntu (test); el
comando id ejecutado sin perfiles observó uid1000 en ambas. El recibo image-users.json
es obligatorio en el freeze y el guard exige que sus IDs/uid1000 coincidan con ambas
imágenes configuradas antes de admitir ejecución. La ausencia de --user
en el transporte nativo hereda ese usuario de imagen; no implica ejecución root.
Se conservan readonly/cap-drop ALL/no-new-privileges/2CPU/1GiB/128pids y mounts de
entrada readonly. Los perfiles permanecen escribibles para el CLI autorizado y
renovación de sesión. Esto confía en esos CLIs/perfiles para autenticación: no es
una garantía criptográfica ni bloqueo absoluto de herramientas internas de Gemini.
El programa sujeto separado sí carece de perfiles y red; los recibos de los roles
y montajes distinguen ambos ámbitos. No convertir esta diferencia en evidencia
de seguridad universal ni ocultar el uso de red/autenticación de los proveedores.

La admisión de cuotas usa original_profile_quota.py, sin importar ni ejecutar los
harnesses o archivos de datos de campañas históricas. Conserva cuentas originales,
unknown explícito, rechazo de timestamps vencidos/futuros y pausa por cuota agotada;
no consulta tokens, sustituye cuentas ni renueva presupuestos.
