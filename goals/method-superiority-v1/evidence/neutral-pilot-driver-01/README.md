# Driver instalado público N/S: ingeniería parcial

Resultado actual: `engineering-receipt.json`, fuentes revisadas en
`source-review-03.json`. **143 pruebas seleccionadas**, **4 controles Docker**
separados y cinco controles de consola instalada con **38 módulos iguales a sus
fuentes**. Las selecciones se superponen con pruebas anteriores: no se suman como
una suite nueva completa. No hay generaciones nativas dev6, competencia N/SDD
establecida, versión completa congelada, calificación T ni superioridad.

La revisión final Codex principal en Kratos, job
`10860bdc95e942cb962624f78dd407b2`, acepta exclusivamente la corrección R04 de
aislamiento del evaluator y sus vecinos de integridad. La revisión no ejecutó
tests ni auditó los recibos runtime: leyó fuentes y stdout previos. Cuatro
invocaciones independientes de ingeniería (diseño y tres revisiones de código)
consumieron cuota; no se presentan como sujetos experimentales.

## Qué cambió

La nueva consola `organon-controls` prepara lectura/ejecución reproducible de
seis posiciones públicas N/S usando un plan ligado a SHA y un bootstrap instalado
que compila las fuentes comprobadas sin consumir pyc. `report` conserva todos
los lugares y no crea un runtime ni hace inspecciones/dispatch Docker. El
registro se prepara con `scripts/register_neutral_pilot.py`; los contratos N/S
no imponen las nueve fases T. Los contratos T y fuentes históricas se conservan.

Un resultado terminal fija su inventario antes del sello. Recuperar tras un crash
no admite archivos añadidos o modificados, ni otra ejecución para sustituir una
medida cerrada. El parser exige identidad de tarea/contrato/checker/argumentos y
denominador; cada fallo corresponde a un caso único con input SHA registrado.
El índice público se reproduce mediante `scripts/index_neutral_public_cases.py`,
sin ejecutar productos. El evaluator usa `-I -S -B`: un `subprocess.py` escrito por
el autor no puede emitir un resumen falso durante las importaciones del checker.

Los controles Docker usan productos deliberadamente incorrectos y estados de
autor sintéticos. Miden procesos offline reales con imágenes existentes dev4;
no llaman a proveedores, no montan perfiles ni prueban una imagen instalada
dev6. RangeAudit roto da 0/115; LedgerFold roto con sombra maliciosa da 0/104.
Esos son controles mecánicos, no resultados de N/SDD ni eficacia del método.

La wheel local final aparece por SHA en `installed-receipt-03.json`; no se publica
una release. La consola instalada mantiene seis lugares no iniciados, ignora un
pyc adulterado y rechaza fuentes modificadas/módulos extra. Exit2 del informe
significa incompleto con cero lugares cerrados. Los planes de esta comprobación
ligan los bytes del working tree mutable: su `source_commit` es procedencia de
base, no un freeze Git completo. No se admite una cohorte a partir de ese probe.

## Revisión, fallos y custodia

- `design-review-01.json`: rechazo de vacíos del diseño; F06 sigue pendiente.
- `code-review-01.json`: R01 inventario posterior al outcome, R02 identidad del
  checker y R03 schema de fallos; corregidos y cubiertos por regresiones.
- `code-review-02.json`: R04 imports adulterables; corregido con aislamiento.
- `code-review-03.json`: aceptación limitada; no aprueba admisión nativa.
- `docker-04.stdout`: tres aprobadas y una fallida. El aislamiento ya bloqueó el
  resumen falso, pero el parser rechazó la forma real JSONDecodeError. Se conserva
  el error como fallo funcional observado tras corregir esa lista de excepciones.
  La retención de pytest borró ese raw intermedio antes de archivarlo: se declara
  en `r04-failed-raw-limitation.json`, sin recrear ni imputar el recibo perdido.
- El primer test de policy detectó `reviewer` donde schema5 exige `review`: 21
  aprobadas/una fallida, descritas como resumen del transcript en `commands-01.json`.
- `archive-verification-02.stderr`: fallo del verificador al buscar el archivo
  intermedio perdido. La versión corregida conserva solo los archivos disponibles;
  `archive-verification-03.stdout` verifica **126 archivos/618064 bytes** y las
  trece fuentes actuales. Eso comprueba copias, no reejecución o attestation.

Comprobaciones reproducibles desde la raíz del checkout:

```sh
uv run --frozen --extra dev python -m pytest tests/test_neutral_pilot.py tests/test_neutral_controller.py tests/test_closed_native_role.py tests/test_native_invocation_consistency.py tests/test_neutral_snapshot_guards.py tests/test_staged_review_regressions.py -q
SPECORGANON_NEUTRAL_PILOT_DOCKER=1 uv run --frozen --extra dev python -m pytest tests/test_neutral_pilot_docker.py -q
python goals/method-superiority-v1/evidence/neutral-pilot-driver-01/verify_evidence.py --check-source
```

La fuente y resultados actuales tienen SHA en `SHA256SUMS`; las wheels/venvs
locales permanecen ignoradas. Presupuestos, fuentes, origen de cuenta y máquinas
se conservan. La cuota del volumen Codex original sigue UNKNOWN; la lectura de
la app principal no se atribuye a ese volumen. Tokens comparables, coste monetario,
F reservado, paquete común completo y ratio comparativo permanecen desconocidos.

Siguiente: resolver/revisar F06, autonomía de N y asimetría de planificación/
revisión frente a S, antes de los pilotos nativos públicos. Después integrar T
al indicador común y F externo, verificar instalación Docker completa, congelar
la versión, calificar sus diez T con ≥9/10, y registrar evaluación reservada y
réplica independiente. La meta permanece activa; dev4 sigue en 5/10.
