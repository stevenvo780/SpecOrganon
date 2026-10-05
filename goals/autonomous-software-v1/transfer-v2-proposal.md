# Propuesta pendiente de revisión: segunda transferencia de ingeniería

Esta propuesta no autoriza generación ni sustituye la especificación original.
Se revisará y registrará como una versión nueva de la decisión y del criterio
antes de ejecutar. El mandato técnico del dueño permite proponerla; no implica
que él haya elegido personalmente la tarea o aprobado sus resultados.

## Resultado anterior e hipótesis de reparación

LogLens v1 permanece detenido: dos llamadas reales, tres borradores de frame,
cero fases aceptadas, ningún programa. Gemini devolvió un ACCEPT textual con
hallazgos de tipo string; el adaptador lo rechazó correctamente. No se convertirá
esa respuesta en aceptación ni se reiniciará su caso o presupuesto.

El controlador cambió materialmente: explicita el formato de hallazgos, mantiene
el rechazo del formato inválido, aísla staging de archivos, reanuda puts parciales,
impide repetir pruebas tras cambios de README y distingue recibos históricos de
la aceptación de bytes actuales. Schema4 incluye el vínculo assessment->risk.
Hay revisión técnica nativa de integración aceptada, controles C5–C8 y una
instalación CLI/MCP limpia. Esto no cumple C1–C4 ni la entrega del método.

Se propone una sola transferencia nueva de tipo distinto, **IntervalDesk**,
para comprobar aplicación de la versión corregida sin volver a generar LogLens.
Ambos intentos aparecerán en el informe de ingeniería. El intento nuevo no es
réplica confirmatoria, comparación N/S/T, prueba de superioridad ni sustitución
del resultado inconcluso anterior. Si falla o queda inconcluso, se detiene; esta
propuesta no permite una cadena de casos nuevos hasta obtener una victoria.

## Contrato público propuesto de IntervalDesk

Entregar `cover.py`, pruebas pertinentes y README, usando Python 3.12 y su
biblioteca estándar. La CLI `python cover.py INPUT` lee un archivo UTF-8 JSON
con exactamente la clave `intervals`, cuyo valor es una lista de hasta 1000
pares `[start,end]`. Ambos extremos son enteros exactos, excluyendo booleanos,
y cumplen `0 <= start < end <= 1440`. Representan intervalos semiabiertos de
un día abstracto. No se infiere eficiencia de reuniones, impacto social ni
una población de usuarios real a partir de esta representación.

La salida JSON contiene exactamente `merged`, `covered_minutes` e `input_count`.
`merged` contiene la unión en pares ordenados por inicio, sin solapamientos ni
adyacencias: `[0,5]` y `[5,10]` se unen. `covered_minutes` suma sus longitudes;
`input_count` cuenta todos los pares originales, incluidos duplicados. Una lista
vacía produce `merged=[]`, duración 0 e input_count 0. El orden inicial no cambia la unión.

Ejemplo público: `{"intervals":[[5,10],[0,7],[10,12],[20,25]]}` produce
`{"merged":[[0,12],[20,25]],"covered_minutes":17,"input_count":4}`.
Otro ejemplo: dos copias de `[1,3]` producen duración 2 e input_count 2.

Una entrada inválida, archivo inexistente/ilegible, BOM, UTF-8 inválido, clave
duplicada/desconocida o archivo mayor que 65536 bytes falla con exit 2, un error
no vacío en stderr y ninguna salida en stdout. No se admiten números flotantes,
NaN/Infinity, extremos invertidos ni listas de longitud distinta de 2. No se
modifica el archivo de entrada y no se realizan solicitudes de red. `--help`
explica el uso y devuelve exit 0. Se pueden aceptar espacios JSON ordinarios.

El autor debe estudiar alternativas reales, por ejemplo ordenar/fusionar frente
a una representación discreta de 1440 minutos o cálculo manual para pocas filas;
derivar requisitos y criterios antes de medir; investigar supuestos/límites;
producir las nueve fases, pruebas, recibos y documentación. Este texto fija el
contrato; no preescribe sus argumentos ni su decisión técnica.

## Presupuesto y aceptación propuestos

- Un caso nuevo; máximo 40 llamadas, dos autorías y dos juicios (incluyendo
  conformidad del mandato) por fase; 180 s por rol y 6000 s globales. Se conservan
  errores de cliente, rechazos, respuestas inválidas y límites alcanzados.
- Codex gpt-6.1-sol autor y Gemini gemini-3.1-pro-high revisor, con sus perfiles
  primarios originales y snapshots RO separados. Cuotas/catalogados deben
  comprobarse nuevamente antes de ejecutar. No cambiar cuenta/modelo por fallo.
- Máximo dos ejecuciones por prueba, 120 s, sólo después de criterios registrados;
  repetir requiere un cambio material de código ejecutable. Imagen limpia fija,
  sin red/perfiles, 1 GiB, 2 CPU, 128 procesos. Uso/coste faltante queda desconocido.
- Misma exigencia de nueve fases, trazas, tests reales de éxito/errores/unión,
  README y ejemplo limpio. C1–C4 se puntuarán para este NUEVO caso/versionado;
  sus resultados no alteran los C1–C4 de LogLens. Los controles C5–C8 conservan
  criterio y evidencias técnicas anteriores, vinculadas al mismo código revisado.
- Antes de generar, revisión separada de esta propuesta y puts guardados de
  decisión/requisito/criterio en el caso de ingeniería; su fase specify quedará
  reabierta hasta aprobar la revisión actual. No transferir la aceptación antigua.

Las tareas reservadas N/S/T, sus repeticiones justificadas, dos familias y
ablación siguen pendientes de otro protocolo. Ninguna de estas dos tareas de
ingeniería se reutilizará como tarea reservada de ese estudio.
