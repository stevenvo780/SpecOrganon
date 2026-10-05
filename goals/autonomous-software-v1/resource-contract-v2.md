# Contrato de ingeniería propuesto: controlador schema6

Se propone extender o2, controlador externo, tras los diagnósticos preservados.
Este contrato requiere nueva conformidad/revisión en el caso de ingeniería
antes de implementar o medir sus controles. No reabre ni repite los intentos
terminales de LogLens/IntervalDesk; no modifica sus presupuestos o veredictos.
La comparación reservada sigue pendiente de su propio prerregistro.

## Decisión y límites

Frente a mantener construcción en una llamada o aumentar sus recursos,
se elige provisionalmente dividir build y controlar la contribución al contexto.
La revisión separada de Gemini aceptó la orientación con correcciones de
inmutabilidad, transiciones y pruebas de carga máxima. No ejecutó tests.

Schema6 sólo admite runs nuevos. Techo total40 llamadas; dos autorías por fase
salvo build: dos autorías iniciales y una única autoría de reparación opcional.
Las revisiones/aprobaciones siguen con techo dos por fase; el rol mantiene180s,
el reloj global6000s desde primera admisión y no se reinicia en recuperación.
No hay reparación tras respuesta nativa inconclusa, timeout o proceso incierto:
esos trabajos conservan su cierre/ausencia de cierre, sin sustitución automática.

El cap de contexto continúa110000 bytes de request canónico y128000 de entrada
nativa/prompt. No se omiten textos, datos o premisas del estado para hacerlos
caber. Se fijan máximos prospectivos de seis items actuales por fase y6000 bytes
de **contribución codificada al request** de su mapa completo: JSON canónico de
items, después codificado como string JSON. Incluye ID, deps y metadatos, no sólo
la narrativa. El autor recibe límites de salida y responsabilidad de concisión;
una respuesta excedida queda cerrada y rechazada antes de puts/archivos.

Los archivos combinados de entrega tienen cap20000 bytes de contribución
codificada, no bytes de disco. Toda medición/contexto tiene el guard global
independiente: estos caps aún deben comprobarse con fixtures máximas antes de
prerregistrar la comparación. Un caso con contexto imposible queda terminal,
sin aumentar el límite ni truncar razonamientos necesarios.

Los tests conservan1GiB/2CPU/128pids/sin red o perfiles,120s y máximo dos
mediciones por ID. Para presentar los streams completos al revisor dentro del
presupuesto se propone cap4000 bytes de contribución codificada por stdout/
stderr de test; el raw2MiB se conserva. Exceder el cap semántico es fallo de
admisión de resultado, nunca passed=true o aceptación con logs ocultos.
El contrato/budget comparativo debe aplicar esos recursos de medición a N/S/T
y ablación por igual. No se emplea este cap para respuestas de modelos.

## Máquina de estados de build

1. **programa:** una autoría entrega programa y README (al menos200 caracteres),
   exactamente un put de implementación y ningún draft de test. Se cierran
   packet, puts y archivos con sus hashes; se registra el checkpoint inmutable
   de los bytes de programa/README y del ID/versión de implementación.
2. **tests:** una autoría añade archivos test_*.py, un draft de test y una nueva
   versión del mismo ID de implementación para vincular el árbol conjunto.
   Conserva idénticos los archivos cerrados en1; no puede sustituirlos, borrarlos
   ni crear otro ID de implementación. El hash de la etapa1 se verifica en
   admisión y aplicación/replay. Los nuevos archivos no se imponen por plantilla:
   el autor escribe las pruebas y explica su relación con criterio/implementación.
3. **medición y revisión:** sólo tras ambas etapas y vínculos válidos se ejecuta
   el test real. Un recibo válido puede cumplir la compuerta mecánica; el revisor
   separado debe juzgar pertinencia, documentación, código y alcance semántico.
4. **reparación opcional:** sólo un fallo real cerrado de test o un rechazo
   semántico sobre la entrega vigente permite la tercera autoría. Puede editar
   programa/test/README, actualiza los mismos IDs de implementación/test y
   preserva los snapshots/recibos anteriores. Necesita cambiar bytes ejecutables
   .py o argv para otra medición; no basta texto, README o nuevas etiquetas.
   Requiere nueva medición y revisión sobre los bytes actuales. Una segunda
   medición, tanto si la primera pasó como si falló, exige cambio ejecutable.
5. **terminal:** tercer intento de autoría ya consumido, segunda medición fallida,
   segundo rechazo o rol inconcluso detienen el caso. No hay reset, nuevo ID de
   test para eludir cupos o repetición de la llamada fallida.

Las dos etapas no son dos fases adicionales del método. Build sigue teniendo
su único criterio/snapshot/revisión/avance, y las nueve fases siguen exigidas.
La nueva autoría opcional consume el presupuesto de la celda; no es un recurso
gratis para T. Es una política nueva prospectiva, no una modificación de schema5.

## Admisión, recuperación y evidencia

El guard debe prevalidar todo el manifiesto/árbol propuesto y sus tamaños en
un estado privado equivalente antes de modificar el ledger o entrega real.
No admitir una mitad del paquete y después descubrir el exceso. Los streams
raw y packets cerrados excedidos permanecen como evidencia de fallo.

Una interrupción durante etapa1/2 o sus puts/renames recupera el mismo packet
cerrado; no lanza otra autoría o executor. Checkpoints inmutables se escriben
con validación de contenido y replay idempotente. Deben detectarse archivos o
ledger divergentes, incluido cambio de programa en la etapa2.

Se verifican R1 tamaño máximo de validate completo; R2 hash de etapa1;
R3 bloqueo de medición prematura; R4 exceso sin writes parciales;
R5 elegibilidad/cupo de reparación; R6 SIGKILL/replay;
R7 segunda medición sólo tras cambio ejecutable; R8 rechazo de runs schema5 y
paquetes sin nueve fases/recibos/docs actuales. Todos requieren prueba y recibo;
los contenidos sintéticos no cumplen C1 de una entrega nueva semántica.

## Relación con la entrega y estudio

Los controles C1–C8 originales no se debilitan. Los C1–C4 de LogLens e
IntervalDesk siguen inconclusos/no medidos. Los guardas R son condiciones
adicionales de la versión nueva; los C5–C8 deben revalidarse cuando su código
cambie. Una prueba sintética de guardas nunca cumple el recorrido real.

Para el siguiente hito de entrega C1–C4 siguen requiriendo un caso NUEVO completo,
programa, tests reales, trazas y documentación. Los casos nuevos serán los de
la comparación prospectiva ya planificada, con conjunto y orden congelados
antes de generar; se reportarán todos, no se añadirán casos hasta obtener éxito.
La goal sigue sin cerrarse si no existe ninguna entrega completa, aunque la
comparación o estas fixtures produzcan scores. Esta vinculación no convierte
un resultado de ingeniería en una nueva celda o evaluación reservada.
