# LotLedger: decisión experimental prospectiva, borrador

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
