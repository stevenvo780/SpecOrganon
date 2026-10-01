# D118 — contrato común de desarrollo coordinado A/B/C

[Plan prospectivo](plan.md), [freeze fuente](source_freeze.json),
[contrato de entrega](public_contract/delivery_contract.json),
[rúbrica pública](public_contract/rubric.json) y
[coordinación](public_contract/coordination_prompt.md).

## Capacidades

El compilador crea doce identidades NUEVAS R1: A/B/C × D-F/D-E × dos
repeticiones, en cuatro bloques. Cada alternativa declara los mismos cuatro
roles —líder, dos workers y reviewer—, acceso, modelo, esfuerzo y saldo padre.
Los modos originales siguen siendo sequential, graph y risk; las cuatro
fases del prototipo conservan sus reglas. El solo del calendario anterior no
se relabela, ni se aplica aquí el solo/trío de N/S/T confirmatorio.

El preparador crea paquetes reales de las seis fuentes D-F y tres D-E;
añade los mismos 38 derivados de las 35 páginas PDF, herramientas originales,
prompts, contrato y rúbrica sin cifras resueltas. Verifica el inventario
completo, ZIP, fuente/imports, extractor, políticas y hashes del calendario.
Requiere las fuentes originales, el extractor y el directorio público con
los mismos bytes; no es una imagen portátil de un runtime.

El checker comprueba entregables, sintaxis sin ejecutar, JSON finito,
unidades/bases, valores nulos motivados, citas por archivo/SHA/localizador y
DAG de claims, e informe de hasta 1200 palabras. Puede aceptar una entrega
estructuralmente válida con todos los cálculos pendientes. No autentica la
generación de métricas, ni verifica pasajes, ni juzga completitud semántica/Q.

## Uso local

La [configuración de fixture](fixture_configuration.json) declara un modelo
inexistente, ruta fixture y tarifas sintéticas. Sólo sirve para preparar y
verificar; no ejecuta participantes ni autoriza proveedores.

Desde el checkout, con el extractor original disponible:

```sh
python3 -I -B scripts/development_delivery_contract.py validate \
  experiments/development/coordinated_contract_2026-10-01/public_contract/delivery_contract.json \
  --rubric experiments/development/coordinated_contract_2026-10-01/public_contract/rubric.json
```

El build usa rutas absolutas y un destino NUEVO, bajo un padre privado y
propio; rechaza solapes con el checkout o los contratos. Ejemplo con un padre
previamente creado con modo 0700:

```sh
python3 -I -B /workspace/SpecOrganon/scripts/prepare_coordinated_development.py build \
  --destination /tmp/specorganon-D118-manual-unique/round \
  --configuration /workspace/SpecOrganon/experiments/development/coordinated_contract_2026-10-01/fixture_configuration.json \
  --contract-dir /workspace/SpecOrganon/experiments/development/coordinated_contract_2026-10-01/public_contract \
  --source-freeze-sha256 6724df13d881e46b08c17213e440a5e231eca16c5541abc283f06ae101f4a044
python3 -I -B /workspace/SpecOrganon/scripts/prepare_coordinated_development.py verify \
  --bundle /tmp/specorganon-D118-manual-unique/round
```

Para una entrega, `development_delivery_contract.py check CONTRACT CASE WORK`
devuelve estructura válida con exit0, problemas de artefactos con exit1 o
contrato/caso inseguro con exit2. CASE conserva su inventario original; WORK
es disjunto y contiene los entregables. No se ejecuta `analysis.py`.

## Alcance y dependencia siguiente

El digest del freeze y el texto de coordinación son entradas declaradas:
el calendario liga sus bytes, pero la concordancia de un descriptor no
autentica un runtime ni autoriza ejecutarlo. Una admisión futura debe exigir
el freeze/contrato publicado específico, adaptadores completos, rutas
autorizadas y telemetría auténtica de tokens/coste y suma de actividad.

Faltan los runtimes coordinados A/B, la continuidad y el binding nuevo de C.
R2 sigue bloqueada hasta resultados R1 y adaptación congelada prospectivamente.
Este perfil DEV de cuatro roles no demuestra revisión humana competente,
calidad, impacto, reserva ni transferencia. **C1 técnico D107 preservado;
C2–C5 No demostrado; 0/24 ejecuciones formales.**

Los resultados finales y negativos se documentan en [evidence.md](evidence.md)
y la revisión independiente en [review.md](review.md). Los archivos de
custodia retienen bytes y metadata; no restauran autorización.
