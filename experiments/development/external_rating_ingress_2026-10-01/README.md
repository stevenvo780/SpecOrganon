# D124 — ingreso de evaluaciones externas DEV

Plan previo `776710a`; freeze inicial `9f0b266`, corregido `4459ae2`.
El alcance es recibir y verificar la forma y los hashes de una nota externa
DEV. No evalúa una entrega, genera notas ni acredita juicio humano.

## Capacidades

- [API pura](../../../scripts/development_rating_ingress.py): JSON cerrado,
  cinco componentes enteros de 0 a 20, seis tipos de incidentes críticos,
  declaraciones booleanas o desconocidas y enlaces a bytes originales.
- [Comando de lectura](../../../scripts/read_development_rating.py): originales
  privados, acotados y de un único enlace, sin seguir aliases de directorios
  ni archivos. Coteja identidad y bytes antes/después, además de los tres
  originales públicos fijos de rúbrica, contrato y protocolo.
- La salida conserva `declared_component_total` e incidentes por separado.
  Una suma de 100 con un incidente no se presenta como aprobación. Textos
  de incidentes e identificadores se resumen con hashes; los originales
  permanecen en los archivos recibidos.
- Declarar independencia, revisión ciega o custodia no verifica esos hechos.
  Calidad, Q, aceptación y ejecución formal permanecen false. No se aplican
  al formato DEV reglas nuevas del panel confirmatorio.

## Uso de la lectura

Desde este checkout, con un directorio absoluto del usuario de modo 700 y
dos archivos regulares de modo 600 llamados exactamente `rating.json` y
`blinded-delivery.bin`:

```sh
python -I -B scripts/read_development_rating.py \
  --rating /ruta/privada/rating.json \
  --rating-sha256 SHA256_DE_LOS_BYTES_ORIGINALES \
  --blinded-delivery /ruta/privada/blinded-delivery.bin \
  --blinded-delivery-sha256 SHA256_DE_LOS_BYTES_ORIGINALES
```

Los hashes son 64 caracteres hexadecimales en minúscula. Salida JSON y
exit 0 indican forma y enlaces válidos; un rechazo produce JSON fijo y
exit 2 sin imprimir argumentos o contenido privado. No escribe una nota
normalizada sustituta. No requiere credenciales de proveedor.

El esquema 1 exacto está documentado en la API: `schema`, `classification`,
los tres hashes de entrega/rúbrica/contrato, `reviewer_reference_sha256`
(hash o null), `scores`, `critical_incidents` y `declarations`. Las dimensiones
son formulation, evidence, intervention, technical y validation. Los seis
campos de declaración son human_judgment, independent_reviewer, blinded_review,
chronology_preserved, external_custody y critical_review_complete. Deben estar
presentes; null significa desconocido. Cada incidente contiene incident_id,
type, evidence_sha256 y description. El formato no decide si la evidencia
del incidente es cierta, si equivale a otro incidente o si la entrega fue
redactada correctamente.

Los paquetes humanos futuros se conservarán fuera de este dossier público.
Todos los archivos de control registrados aquí contienen datos sintéticos.

## Evidencia y reproducción

| Gate definitivo | Python 3.11.15 | Python 3.12.3 |
| --- | --- | --- |
| Tests API + lectura | 87 pasan | 87 pasan |
| Ruff, sintaxis, diff | exit 0 | exit 0 |
| Lecturas CLI reales nuevas | 7: 3 aceptadas, 4 rechazadas | 7: 3 aceptadas, 4 rechazadas |
| Archivo de originales CLI | 21 miembros, 1.762 bytes | 21 miembros, 1.754 bytes |
| Fuentes y HEAD durante gate | 8 fuentes intactas | 8 fuentes intactas |

Capturas [3.11](checks/final02_py311/report.json) y
[3.12](checks/final02_py312/report.json): argv, streams, fuentes exactas y
snapshots de cada original antes/después. Los controles incluyen suma 100
con incidente visible, valores iguales con bytes/hash diferentes, declaraciones
null y rechazo de hash, privacidad, JSON duplicado y argumento desconocido.
Son catorce lecturas sintéticas en la captura definitiva, no evaluaciones humanas.

Los archivos se cotejan por nombres, tipos, modos, tamaños y SHA contra
inventarios y raíces temporales conservadas. SHA finales:

- 3.11: `6ecb74d9bf53ec189b9591ae8c710f4079f98bf6a8c477f85ddc96e477ab8c03`.
- 3.12: `86a13ca2b732f14223192d1874fa93fb034563756dc07a445e84a1f777a558ab`.

[Procedencia](provenance/staging_scope.json): 19 archivos regulares del borrador
original, 70.888 bytes, preservados sin rescribirlos; archivo de 22 miembros.
Se excluyen caches y árboles temporales de fixtures pytest. El módulo API es
idéntico al borrador; el test sólo adapta sus rutas/import para este checkout.
[Root](root_reopen_report.json) reabrió streams, fuentes, archivos y originales.

La captura definitiva usa `source_freeze.json` SHA
`d2103281db40e959451d018984d9e9786caba78f7edb0a91e1a7d98963c30113`.
Para reproducir el gate local se emplea un output absoluto nuevo:

```sh
python -I -B experiments/development/external_rating_ingress_2026-10-01/capture_checks.py \
  --output /ruta/nueva/captura
```

El wrapper de archivo reutiliza el helper D123 fijado por SHA, sin extraer o
ejecutar código archivado. El sello exige `PASS_local_scope` independiente,
bindings live/índice/HEAD y preservación previa; revisar `review/` y `receipt.json`.
Las copias no restauran autoridad de un runtime ni autentican custodia.

## Hallazgo y corrección conservados

La revisión independiente detectó P2 en el wrapper: `Path.absolute()` retenía
`..`; un destino léxico podía resolver dentro del árbol original y escribir
antes del fallo posterior. [Probe y fuente](review/helper_review.json) se
conservan; el probe independiente fue puro, sin crear TAR ni tocar originales.
El fix rechaza `..` en todos los argumentos antes de inspección/helper/escritura.
Siete variantes y seis controles previos pasan en ambos Python; el revisor
cerró el hallazgo en [containment_closure.json](review/containment_closure.json).

Freeze01 y sus capturas completas permanecen intactos. Usaron destinos
canónicos y pasaron sus aserciones, pero no constituyen el cierre definitivo
del helper vulnerable. En ellas los snapshots before/after sólo fueron
aserciones en memoria. Freeze02 añade su persistencia y repite los gates.

## Preservación y límites de aceptación

Se preservan 725 registros D123 distintos de los cuatro docs activos y el
recibo original. Los cuatro docs D123 se cotejan con Git `7d5a776` antes de
avanzar este corte. El cierre heredado mantiene 5.875 pins D121, 121 registros
D122 y ocho fuentes D123. No se describen los cuatro docs históricos como
725+4 registros live sin cambios.

Los controles son locales y cooperativos bajo el mismo UID; dos lecturas no
aportan una captura atómica global frente a escritores de confianza ni prueba
externa de identidad, competencia, independencia, cegamiento o cronología.
No hubo API experimental, credenciales, notas humanas ni nuevas celdas formales.
GOAL, protocolo, casos, producción y dossiers sellados permanecen intactos.

**C1 técnico D107; C2–C5 No demostrado; 0/24 formales.** La
[siguiente activación](next_activation.md) necesita personas, elección/acceso
y autorización de gasto, mediciones reales y después confirmación, campo y
transferencia. El dueño indica un revisor y custodio disponibles; queda por
aclarar si son la misma persona y verificar separación/competencia/custodia.
No hay notas humanas recibidas; el panel confirmatorio de dos evaluadores
y arbitraje sigue pendiente. [Ruteo](routing_inventory.json): Luna ayudó con un intake
acotado cotejado contra fuentes; no se midió equivalencia de calidad.
