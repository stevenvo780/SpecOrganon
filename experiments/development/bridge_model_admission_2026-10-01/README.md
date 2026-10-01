# D-110 — excluir copias antes de las solicitudes de modelo

Plan prospectivo en `ecd7ca51fa002c39e4a3e9bcc6c02d023f375892`, después de
[D-109](../activation_readiness_2026-09-30/README.md). Se corrige un defecto del
bridge de desarrollo; el motor y el wheel D-107 no cambian.

## Defecto conservado y corrección

El código original adquiría la exclusión del intento al ejecutar una herramienta.
Dos copias del mismo intento que solo produjeran texto podían llegar al proveedor
con presupuestos separados. El negativo previo al arreglo usó `FakeTransport`:
**cada copia completó dos conteos y dos envíos**; la segunda modificó su ledger.
Su pytest salió con código 1 esperado, sin HTTP ni modelo real.

Ahora el bridge adquiere el claim canónico de calendario/run/attempt y owner de
sesión **antes del primer conteo**, dentro del plazo activo y después del marcador
durable de inicio. Comprueba el mismo claim antes de **cada conteo y envío**.
Reutiliza el registro existente, sin cambiar el esquema. La preparación histórica
sin claim sigue siendo válida; los errores e interrupciones posteriores al inicio
no habilitan un reintento automático.

En el control corregido, la primera copia completa dos conteos/dos envíos; la
segunda se rechaza con **cero conteos, cero envíos y ledger intacto**. También se
comprueban exclusión entre procesos, claim ajeno o alterado, alteración entre
conteo/envío y entre respuestas, interrupción tras adquirir el claim y el positivo
con herramienta sellada. Los proveedores son falsos y los casos son fixtures;
sus etiquetas R-F/R-M/R-S no son los paquetes reservados del estudio.

## Gates y revisión

| Gate | Resultado conservado |
| --- | --- |
| Python 3.11, bridge + admisión local | 46 passed, exit 0, 16,63 s |
| Python 3.12, controles nuevos + positivo con herramienta | 8 passed, 20 deselected, exit 0, 4,58 s |
| Ruff, compilación en memoria 3.11/3.12 y diff-check de código | Aprobados |
| Revisión nativa independiente de fuente y capturas | Sin P1/P2 en el defecto acotado |

[Capturas y parámetros](unit_checks/), [revisión](review.json) y
[recibo de conservación](receipt.json). No se repitió la suite global ni se
atribuyen estos resultados a una ejecución contra un proveedor real.

Bridge final SHA-256 `9dc2bc466f2484730a5efbbe4f49f9615b0578981e8bbf3b7a7f05dcdbbcf5f4`.
Test final SHA-256 `51671b7cdc688ab7b293e66a04a297bb0f8b212fdda7f0bed25eef495c7ba3cc`.

## Negativos y conservación

- Los dos archivos originales se conservaron byte exacto contra `0e31be0`.
  El primer registro de metadatos quedó parcial por `FileExistsError`; se
  conserva y se añade `source_pins_complete.json`, sin sobrescribirlo.
- Se conservan los espacios finales de la captura del focal fallido. El
  diff-check estricto de todo el índice los señala; código, documentación y
  metadatos pasan el chequeo separado. No se normalizan las salidas originales.
- El primer focal dio 44 aprobadas y 2 fallidas por expectativas nuevas de
  `status`: el contrato existente rechaza un caso preparado con claim ajeno o
  alterado. Se corrigieron esas dos expectativas sin modificar el bridge.
  **Se conservaron hash y logs del test intermedio, pero no sus bytes completos**;
  no se reconstruye ni se afirma reproducibilidad exacta de ese intento.
- Un launcher `python` ausente salió con 127 antes de ejecutar pytest; el
  registro se conserva. Los gates finales usaron los Python absolutos disponibles.
- [Archivo del negativo original](baseline_negative.tar.gz) e
  [inventario](baseline_archive.json): 77 miembros regulares cotejados por bytes
  y hash; no es una imagen del entorno ni conserva directorios vacíos.
  Los workspaces completos del primer focal quedan locales, ignorados por Git;
  los finales permanecen en las rutas `/tmp` registradas. El recibo incluye
  fuentes y capturas esenciales, no miles de fixtures regenerables.

## Límite y siguiente paso

La exclusión es **local y cooperativa, bajo el mismo UID y registro**. No autentica
identidad/esfuerzo del modelo, factura o cancelación remota. Tampoco proporciona
relevo, pausa humana o límites globales de una matriz con varios agentes y
proveedores; los adapters simples y la CLI opaca no reciben esta corrección.

**Aceptación: 1/5 en el alcance técnico D-107; C2–C5 no demostrados.** Cero
solicitudes reales a proveedores, campo, aprobaciones humanas o celdas de las
24 previstas. El siguiente trabajo integra el contexto común de presupuesto y
admisión del ensayo; las puertas externas de D-109 siguen pendientes.
