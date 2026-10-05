# Orientación prospectiva de artefactos, schema8

El controlador añade `artifact-data-contract.json` con claves y condiciones
orientativas de los validadores y `reference-maintenance.json` con diagnósticos
de versiones. `state.json` conserva completos texto, datos, dependencias,
versiones, flags e incidencias; sigue siendo la fuente autoritativa. Las
indicaciones de formato se limitan a la fase actual para respetar los mismos
límites de contexto. No se incluyen argumentos, mediciones o aprobaciones
preescritas.

Para evidencia observada, `data.method` describe la recogida real;
`collection_method` no sustituye esa clave. Cambiar un protocolo puede dejar
obsoletos evidencia e indicadores transitivamente: reconsiderar y editar primero
los ancestros y luego los descendientes, con nuevas revisiones cuando proceda.
El diagnóstico no reescribe dependencias ni acredita esa reconsideración.

La orientación de referencias tiene techo4096bytes de JSON canónico. Si no
cabe, declara `summary_only`, `details_omitted` y `truncated`, muestra conteos y
remite al estado completo. Dependencias ausentes o ciclos impiden presentar un
orden completo. Estados malformados y fases desconocidas producen `ValueError`.
La política fija el digest del contrato y del archivo de orientación; un cambio
impide reusar un run ya inicializado. Los runs schema7 se rechazan antes de
recrear el árbol de entrega. Se conservan dos autores por fase, tres en build,
dos revisores y dos conformidades, cuarenta llamadas y los límites de contexto,
archivos y resultados de pruebas.

El runner CSVShape registrado contrasta su propia ruta y las rutas/bytes
actuales de módulos SpecOrganon/scripts/experiments con el registro. Los paquetes
namespace sin archivo sólo se permiten cuando todos sus directorios de búsqueda
pertenecen a la fuente registrada y contienen archivos vinculados. Verifica
antes de inicializar, antes de cada paso y en la admisión de CellBudget; también
tras importar la matriz reservada. Es vinculación de rutas y archivos actuales,
no una atestación del bytecode en memoria ni eliminación de toda carrera entre
lectura y uso. Sólo se aplica al runner de fuentes registradas, no exige un
checkout fuente para la CLI/MCP general instalada.

CSVShape v1 permanece cerrado con dos fases aceptadas. Este cambio se desarrolla
en otro checkout y no se ejecuta sobre su ledger para generar artefactos. Los
controles de reparación son sintéticos; no cuentan como fases aceptadas ni como
entrega autónoma. El rechazo de un registro de otro checkout y su diagnóstico
son consultas de sólo lectura. Esta corrección tampoco acredita superioridad
metodológica, eficacia de campo o una versión instalada limpia.
