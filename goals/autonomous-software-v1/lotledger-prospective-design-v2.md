# LotLedger: diseño prospectivo revisado, borrador v2

No registrado; no inicializa caso ni habilita generación. Propuesta posterior a
la corrección técnica schema8. El propósito sigue siendo una entrega NUEVA de
nueve fases y la comparación reservada posterior. No reabre LogLens,
IntervalDesk, CSVShape ni las campañas anteriores y no sustituye sus resultados.

## Justificación y límite contra selección favorable

LotLedger propone una CLI de conciliación de movimientos de existencias por
lote y ubicación, útil para detectar doble aplicación de eventos, saldo negativo
y conflictos de identidad antes de importar un ledger operativo. Es una nueva
familia de máquina de estados, diferente de agregación de logs, intervalos,
validación CSV, grafos de rutas y recorrido de archivos. Se eligió por la necesidad
de integridad e idempotencia de transferencias; no hay resultados de autores ni
medición piloto de su probabilidad de pasar. No es una prueba clínica/alimentaria
ni se afirma reducción de pérdidas, ahorro de trabajo o eficacia de campo.

Se propone una sola identidad `lotledger-delivery-v1`, sin variantes de dificultad
ni selección del mejor candidato. Tras congelarla, se ejecuta una vez con los
slots acotados del controlador. Si falla se publica el fallo y no se reemplaza
por otra tarea o cuenta. La aceptación de este borrador no registra el caso;
primero requiere contrato exacto, evaluador reservado y revisión independiente
antes de la congelación. Tampoco abre otra campaña N/S/T a partir de un resultado
favorable: esa comparación conserva su propio protocolo prospectivo multitype.

## Contrato funcional propuesto

Programa `lotledger.py`, Python3.12 stdlib, stdin UTF-8 estricto con eventos JSONL
hasta65536bytes inclusive y1000eventos. No BOM/NUL, líneas vacías ni objetos con
claves JSON duplicadas; LF separa eventos, terminador final opcional. Un input
vacío representa ledger vacío. No normalizar espacios, Unicode o mayúsculas.
Sin argumentos CLI; error de argv también invalida antes de leer stdin.

Tipos exactos, sin claves extra:

- receive: id,op="receive",lot,site,quantity.
- consume: id,op="consume",lot,site,quantity.
- move: id,op="move",lot,from,to,quantity; from y to distintos.

id/lot/site/from/to son strings no vacíos de hasta64bytes UTF-8, sin NUL/CR/LF.
quantity es entero JSON exacto, no booleano/float, entre1 y1000000000. Los
saldos iniciales son0. receive suma; consume resta; move resta de origen y suma
al destino. Consumo/transferencia con saldo insuficiente invalidan todo el input.
Se procesa en orden de aparición; no ordenar eventos ni permitir saldo negativo
transitorio. Una repetición de id con el mismo objeto validado no aplica otra vez
sus efectos y suma duplicate_events; mismo id con diferente objeto invalida todo.
La igualdad ignora sólo el orden de claves JSON, no tipos, valores ni strings.

Éxito: exit0, stderr vacío, stdout único JSON terminado en newline con claves
unique_events (int),duplicate_events (int),stocks (lista). Stocks positivos, sin
ceros, ordenados por (lot,site) según comparación de strings Python; cada fila
sólo lot,site,quantity (int). Error: exit2, stdout vacío, stderr exactamente
`{"error":"invalid_input"}\n`. Sin resultados parciales ni escritura de datos.
Límite3s/2CPU/1GiB, sin red, perfiles o credenciales. Entrega readonly.

El contrato completo incluirá dos ejemplos públicos ejecutables, documentación
de instalación/errores/límites y pruebas propias con argv absoluto. No se
suministrará implementación, argumentario de las nueve fases ni outcomes.

## Evidencia, alternativas y veredictos

El autor debe formular problema/actores/frontera, normas, encuadres rivales,
pregunta/hipótesis/protocolo, indicadores fundamentados, observaciones e
inferencias, síntesis/incertidumbre, alternativas sustantivas y requisitos
trazables. Una alternativa viable debe reutilizar SQLite con transacciones,
unicidad y operaciones SQL en vez de software específico; no fingir que SQLite
por sí solo implementa este formato/idempotencia contractual.

Referencias primarias consultadas2026-10-05:
[SQLite transacciones](https://www.sqlite.org/lang_transaction.html) y
[SQLite resolución de conflictos](https://www.sqlite.org/lang_conflict.html).
No se equipara ABORT con rollback del lote completo ni IGNORE con comprobar
contenido de un evento repetido. La alternativa requiere una política explícita.

Antes de generar, la evidencia pública debe contener observaciones reproducibles
sobre primitivas SQLite en la imagen fijada, población/procedimiento/ubicación y
valores efectivamente medidos; no un baseline0 inventado ni mediciones posteriores
copiadas a criterios previos. Un resultado técnico del programa se evalúa sobre
las pruebas prespecificadas. No hay medición de utilidad humana o superioridad
metodológica: deben quedar no_demostrado/unknown cuando no haya soporte. Las
mediciones públicas de primitivas no cuentan como cumplimiento del contrato
completo ni entran en recetas reservadas.

La evaluación reservada tendrá60recetas fijadas antes de generar: movimientos
legales/stock conservado, duplicados/conflictos, orden/agotamiento, tipos/UTF-8,
claves/formato, límites/Unicode y metamorfismos. Cada resultado conserva
invocación/streams/timeout/código; no se muestran respuestas reservadas al autor.
Los controles del evaluador incluyen centinelas erróneos, entrega ausente y casos
con proceso timeout, separados de programas generados.

## Roles, presupuesto y parada

Propuesta: autor Codex gpt-6.1-sol effort medium, volumen ORIGINAL
specorganon-lab_codex-home; revisor Gemini3.8Flash (Medium), perfil ORIGINAL
/home/stev/.gemini. Cada rol en contenedor separado; conformidad con el mandato
es juicio delegado independiente, no consentimiento personal inventado. Cuenta
sin cuota observable se declara desconocida; no se cambian perfiles por fallos.
Muse sólo revisa este diseño por texto y no genera el caso en esta propuesta.

Controller schema8: máximo40llamadas,2autores/fase (3build),2revisiones y
2conformidades contadas separadas. Límite180s/llamada,6000s total desde primera
admisión,128000bytes de prompt por llamada,3145728acumulados. Se conservan
6artefactos y6000bytes JSON escapados/fase,20000archivos,4000salida de tests.
Dos tests propios como máximo,120s/test; segundo sólo tras cambio ejecutable
justificado por fallo/rechazo. No ampliar presupuestos tras observar respuestas.
Cuotas actuales con antigüedad<=600s antes de cada nueva admisión; agotamiento
explícito/vencimiento pausa sin renovar presupuesto. Timeout, respuesta inválida
o slots agotados cierran fallo sin sustitución. Los replays sólo reutilizan
recibos verificados de la misma identidad y no generan trabajo incierto de nuevo.

C1–C4 requieren nueve fases aceptadas realmente, tests medidos, vínculos vigentes,
README usable y auditoría separada de sustancia/adherencia. C5–C8 son controles
sintéticos ya identificados y requieren revalidación pertinente en el candidato;
no se cuentan como entrega ni como éxito de modelos. Reservados y costes/uso
declarado se publican incluso si falla. La goal sólo se cierra cuando, además,
se complete la comparación y la release exigidas, no al aceptar este diseño.

## Precisiones tras el rechazo de diseño Muse01

Se conserva v1 y su juicio `revise_draft`. V2 no está registrado. Los requisitos
pendientes —observaciones reales, recetas/evaluador, control de aislamiento y
revisión del conjunto final— siguen impidiendo admisión.

- Input: contar todos los bytes de stdin, incluido LF final.65536 es válido,
 65537 produce invalid_input contractual; si el evaluador corta un proceso que
 no termina, registra timeout en vez de imputar ese error. Cada línea separada
 por LF es un evento; se permite un solo LF final. Vacío tiene cero eventos;
 LF solo, una línea de espacios o dos LF finales son inválidos. Whitespace JSON
 antes/después de un objeto en una línea es permitido; un CR antes de LF queda
 como whitespace JSON. Escapes que produzcan strings no codificables en UTF-8
 estricto son inválidos.1000eventos inclusive cuenta también duplicados.
- Primero validar forma/tipos de cada objeto. Después, si id ya apareció:
 igualdad de todas las claves/tipos/valores implica duplicado sin comprobación
 nueva de stock ni efecto; diferencia implica error. En un id nuevo se comprueba
 disponibilidad y se aplica su operación. Así una repetición de un consumo
 original válido tras agotar stock sigue siendo idempotente. unique_events
 cuenta distintos ids; duplicate_events todas sus ocurrencias posteriores
 idénticas. Un objeto estructuralmente inválido jamás se omite como duplicado.
- El estado se indexa por el par exacto (lot,site). Move conserva lot y quantity,
 cambia sólo ubicación, resta y suma atómicamente; no admite origen=destino.
 El resultado sólo contiene cantidades positivas. Orden de filas por Unicode
 codepoints de strings Python3.12, independiente de locale.
- Salida: claves superiores exactamente unique_events,duplicate_events,stocks;
 filas exactamente lot,site,quantity. Contadores/cantidades son int JSON, no
 bool ni float. Orden de claves del objeto y whitespace interno JSON no son
 significativos; stdout debe terminar en un único LF, sin sufijo o prefijo
 no-JSON, ni otro valor JSON. Todos los errores contractuales, incluido argv,
 usan exit2/stdout vacío/stderr error exacto; no resultados parciales.

### Distribución propuesta de60recetas

| Grupo | Cantidad | Propósito |
|---|---:|---|
| Operaciones legales y conservación |10| Receive/consume/move, estados compuestos y vacíos |
| Identidad de evento |10| Repetición idéntica, claves reordenadas, conflicto y consumo repetido |
| Orden y agotamiento |10| Fondos insuficientes, falta de origen, prefijos y ceros omitidos |
| Tipos y codificación |10| Bool/float, límites numéricos, UTF-8, escapes y Unicode |
| Objetos y formato |10| Claves extra/duplicadas/ausentes, líneas y argv |
| Bordes y metamorfismos |10| Límites bytes/eventos/strings y transformaciones especificadas |

Sesenta es una cobertura determinista acotada de seis dimensiones contractuales
con igual peso, no un tamaño muestral con potencia estadística demostrada. Cada
receta pertenece a un único grupo; límites exactos y metamorfismos aportan
pares borde/contraborde. Relaciones metamórficas: añadir eventos idénticos ya
aplicados conserva stocks y unique_events; renombrar lot/site mediante biyección
sin colisiones conserva cantidades y relaciones, reordenando sólo filas de
salida según el contrato. Se fijarán instancias/hash antes de generar. No se
añaden recetas adversas ni favorables tras ver entregas.

### Condiciones pendientes para registrar

Registro escrito con hashes del contrato, todos los fuentes/recetas/evaluador,
observaciones públicas y revisión nativa del conjunto, imágenes y modelos; debe
preceder inicialización y primera admisión. Cambio de fuentes tras freeze cierra
la identidad como inválida; no autoriza una tarea/cuenta sustituta. Evaluador
reservado aislado, recibos completos y controles centinela/ausencia/timeout
antes de congelar; logging de cuota<=600s por admisión sin renovar presupuestos.

C1–C8 se conservan en controller-specification.md como criterios del mecanismo;
para esta entrega C1–C4 se aplican al programa LotLedger y C5–C8 son controles
sintéticos separados. El borrador comparison-proposal-v1.md y los protocolos
congelados de campañas previas son antecedentes cerrados, no autorización de
una campaña nueva. Falta un protocolo NUEVO multitype N/S/T, dos familias,
repeticiones/ablación, evaluador ciego y cotas comunes antes de esa comparación.

Los valores de las primitivas SQLite deben medirse en la imagen fijada y
publicarse con fuente/procedimiento/población/ubicación antes de generar. Sólo
acreditan la semántica observada, no implementación del contrato JSONL completo,
utilidad humana ni superioridad del método. No se copian mediciones del programa
a criterios anteriores ni se inventa una línea base.
