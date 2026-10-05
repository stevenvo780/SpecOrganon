# Propuesta pendiente: controlar contexto y dividir construcción

La prueba real de IntervalDesk terminó en revisión40, siete fases aceptadas,
17 llamadas intentadas y 16 paquetes cerrados. La llamada17 de construcción
agotó 180 segundos: Docker terminó137, attach-9, sin OOM ni respuesta final.
No existe programa o ejecución de tests. LogLens y este intento permanecen
inconclusos; esta propuesta no los reinicia, no reemplaza llamadas ni concede
una nueva cadena de casos de ingeniería hasta obtener éxito.

Hubo dos detenciones previas antes de despachar revisiones, por contexto de
111528 y113248 bytes frente al guard de110000. Reparaciones sin pérdida de
contenido eliminaron duplicación del resumen de tareas, conservando estado
completo, políticas, llamadas cerradas y reloj global. La última entrada fue
109201 bytes: queda poco margen para añadir código, tests o resultados.

La configuración actual, cuyo hash coincide con la captura nativa, no fija
model_reasoning_effort; el catálogo público proyectado declara default low.
Esto no prueba el esfuerzo efectivo remoto ni la causa del timeout. No se
atribuirá el fallo a una cuota, modelo o configuración sin evidencia.

## Alternativas

1. Mantener el diseño actual, una autoría de build para código/tests/README y
   estado completo en cada rol. Tiene infraestructura verificada y conserva
   todas las premisas, pero la prueba real expone saturación de entrada y una
   construcción inconclusa. No se puede declarar que completar otros casos
   con este diseño esté demostrado.
2. Fijar límites de tamaño prospectivos y dividir build en dos autorías ya
   contempladas por el techo de dos por fase: primero implementación/README,
   después tests y actualización trazable de implementación. El ejecutor mide
   sólo cuando la segunda entrega está completa; el revisor lee la entrega
   conjunta y los recibos. Conserva 180 segundos por llamada,40 llamadas y
   estado completo. Añade una llamada y riesgo de inconsistencias entre piezas.
3. Aumentar el tiempo por llamada y/o permitir leer grandes snapshots fuera
   del prompt. Puede admitir programas mayores, pero cambia recursos/superficie
   del experimento y requiere otras verificaciones de aislamiento y admisión.
   No se aplicará retroactivamente al intento terminal.

Se propone investigar la alternativa2 para la próxima versión, con revisión
separada antes de implementarla. No hay aún una decisión aprobada o un
presupuesto comparativo congelado.

## Restricciones prospectivas propuestas

- Schema6 nuevo, sin migrar runs schema5. Los casos anteriores conservan sus
  políticas/recibos/veredictos; ningún job17 fallido se vuelve a ejecutar.
- Máximo seis artefactos actuales por fase y6000 bytes combinados de texto/data
  por fase, declarados antes de autoría. Límites controlados sobre los puts
  propuestos y la fase resultante; una respuesta excedida queda como fallo,
  sin recortar argumentos, fabricar datos o reinterpretar aceptación.
- Archivos combinados de entrega hasta20000 bytes; el autor recibe el techo
  y debe mantener programa, tests pertinentes y README utilizable. Siguen
  vigentes input110000/128000,2MiB streams,180s/rol,6000s globales.
- La fase build tendrá etapa1 (implementación+README, sin test draft) y etapa2
  (test source/draft más nueva versión de implementación vinculada al árbol
  conjunto). El autor propone cada argumento y vínculo. La coordinación no
  inventa contenidos o revisiones para completar la fase.
- Ninguna ejecución antes de código y tests completos, criterios registrados
  y árbol/versiones vinculados. Dos mediciones por test como máximo, segunda
  sólo tras cambio ejecutable/argv. Un cambio documental sigue sin bastar.
- El checkpoint debe conservar etapa y autorías cerradas, admitir replay tras
  interrupción sin duplicación y rechazar una entrega conjunta incoherente.
- El esfuerzo de cada modelo se fijará explícitamente antes del prerregistro
  y será el mismo entre métodos de esa familia. No se bajará por fallo/cuota.

Estos tamaños son hipótesis de ingeniería, no una prueba matemática de que
todo request admisible cabe: versiones, refs, metadatos y streams también
consumen bytes. Antes de congelar hay que construir fixtures con la combinación
máxima de artefactos/IDs/refs/resultados y verificar el límite total exacto.
Si no cabe, se revisará la propuesta antes de generación reservada, conservando
la versión fallida. No se proyectará el contexto omitiendo premisas necesarias.

## Comparación y cierre

Las restricciones comunes de archivos, entrada, tiempo y cómputo deben ser
idénticas entre N/S/T y la ablación. El cap de artefactos depende del formato
de cada método y se publicará como parte del tratamiento, no como igualdad
de proceso. Las revisiones y etapa extra consumen el presupuesto de su celda.
Las celdas nuevas de la comparación sólo se generan tras protocolo/evaluador
congelados; ningún resultado adverso permite sustituir tareas o cuentas.

Para aceptar el cambio hacen falta pruebas pertinentes de admisión en el
límite, exceso preservado sin puts, coherencia de hashes entre dos etapas,
SIGKILL/replay, ausencia de medición prematura y compuertas tras fallo.
Después, revisión nativa separada de la implementación e instalación limpia.
Estas fixtures verifican mecanismos; no completan la exigencia de un caso
nuevo con nueve fases semánticas y una entrega real.
