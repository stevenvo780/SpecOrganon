# Revisión de la orientación prospectiva schema8

Cambio en checkout separado, commit `d143444b`, rama
`codex/artifact-repair-contract`. CSVShape permanece cerrado:2/9,rev22,
ocho llamadas. No se generó otro caso ni se reabrió una campaña.

La revisión inicial de diseño Gemini3.8Flash aceptó el alcance orientativo y
pidió ausencia de valores ilustrativos y resumen explícitamente truncado.
Fue anterior a añadir el guard de fuentes; no se atribuye a ese guard su juicio.

Muse Code, configuración Meta original `muse-spark-1.3`, effort medium,
un paso y herramientas shell/write/web desactivadas, emitió primero `revise`
en46.1s y después `accept` en48.5s. No ejecutó pruebas. Su cuota e identidad de
cuenta permanecen desconocidas. Los streams completos están en el journal
privado; los recibos conservan hashes, input y juicio sin exponer perfiles.

## Triage del primer juicio

- Se restringieron los paquetes sin `__file__` a namespaces de scripts/experiments
  con todas las rutas dentro del checkout registrado y archivos descendientes
  vinculados. Se verifica nuevamente tras importar la matriz.
- Fases desconocidas y estado malformado producen errores ValueError controlados.
- El hint usa el mismo serializador canónico que el documento transmitido. Antes
  ambos serializadores eran equivalentes; se unificó la autoridad para evitar
  divergencia futura. No se afirmó un exceso4096bytes observado.
- La política vincula el digest del archivo de orientación además del contrato;
  modificar la ayuda exige otro run versionado. Se eliminó la constante obsoleta.

## Triage del juicio final

Dos observaciones menores afirmaron que `_read(path, limit)` digestaba sólo un
prefijo. La implementación existente rechaza `st_size > limit`, lee completo y
contrasta tamaño/inodo/mtime/ctime antes y después. Un control real de archivo4B
con límite3B produjo `JobError: job record must be bounded, singly linked regular
data`. Ambas observaciones quedan preservadas y descartadas con esa evidencia;
no se cambiaron lectores ya correctos.

La limitación restante es real: se vinculan rutas y bytes actuales, no bytecode
ya cargado. Las verificaciones de registro preceden inicialización, cada paso y
admisión CellBudget, pero no eliminan toda carrera entre lectura y uso. Está
explicado en `docs/prospective_artifact_guidance.md`; no se instaló un import hook
ni se cambió configuración de proveedores.

## Resultado y alcance

84 controles pasaron en host y84 en Docker, fuentes montadas en sólo lectura,
red none e imagen fijada. Son controles sintéticos/componentes, no nuevas fases
aceptadas ni wheel instalado nuevo. Se conservan también los fallos anteriores:
contexto excedido, IDs de prueba demasiado cortos y duplicación legítima de rutas
namespace inicialmente rechazada; no se reetiquetan como PASS.

La consulta del CSV cerrado identificó exactamente
`evidence-doc-csv -> protocol-verification [1 vs2]`, evidencia/indicador
transitivamente obsoletos y `evidence-parser-probes` inválida. Su ledger quedó
byteidéntico.179fuentes CSV,48fuentes comparación,30inputs backup y GOAL.md
permanecen intactos. Faltan la nueva entrega real de nueve fases, evaluación
comparativa completa, release integrada/versionada instalada y cierre publicado
para completar la goal. Esta corrección es progreso de ingeniería.
