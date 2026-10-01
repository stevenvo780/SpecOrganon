# D123 — entrada controlada y costos de respuestas rechazadas

Plan previo `080acba`; controlador previo a gates `e94a7d8`, corregido en
`d452b8f` para respetar `released`/`paused` del journal original. El freeze
`7246936` sólo ajusta el harness tras sus dos timeouts de600 segundos:
preflightCLI externo una vez por brazo, manteniendo el interno por step,
timeout de captura1200 y conservación de exit124/streams parciales. Los intentos
anteriores quedan conservados. Esta unidad no ejecuta una celda formal,
autentica un proveedor, puntúa Q ni autoriza gasto.

## Capacidades

- `scripts/authorized_coordinated_runtime.py`: preflight de lectura, step real
  limitado al origen oficial fijo, step fixture loopback y outcomes de lectura.
  Conserva los guards, ledger, claim, contratos y observación originales.
- Step real requiere flag explícito y una declaración privada exacta ligada a
  run, rutas, plan, schedule, observación, modelo/esfuerzo, recursos y fuentes.
  La clave se lee desde `OPENAI_API_KEY` después de esos gates. La declaración
  local es una política cooperativa; no acredita identidad o autorización del
  dueño en esta sesión. No se genera una declaración aprobada automáticamente.
- La declaración es JSON cerrado, sin claves duplicadas, archivo regular de
  único enlace con uid actual y modo600, límite de bytes y vigencia acotada.
  Se coteja antes del transporte, dentro del hilo antes del I/O y después.
- Un proxy de protocolo conserva el payload. El límite local por operación
  es ≤90 segundos y el deadline nativo; descarta resultados tardíos. El hilo
  daemon y la operación remota pueden continuar: no acredita cancelación
  remota ni límite de vida del socket. No hay retry automático.
- `scripts/provider_outcome_accounting.py`: lectura bajo un lock original y
  guard nativo, conciliación pura de usage/cache/razonamiento/precio declarado.
  Costos reportados y reservas originales son columnas alternativas. Una
  respuesta incompleta puede tener costo conocido sin entrega exitosa.
  Estado indeterminate mantiene reservas y no se reejecuta; guard verificado
  no significa replay completo. Datos faltantes quedan nulos, no cero.

## Uso de lectura

Usar el intérprete exacto del bundle y las rutas originales. El checkpoint
vigente se obtiene del status original, no se inventa a partir de un archivo.

```text
python scripts/authorized_coordinated_runtime.py preflight \
  --run-dir /ruta/run --observation-dir /ruta/observation \
  --expected-checkpoint CHECKPOINT_VIGENTE

python scripts/authorized_coordinated_runtime.py outcomes --run-dir /ruta/run
```

`preflight` devuelve una plantilla `not_approved`. El comando `step` exige
`--operator-declaration` y `--allow-paid-request`; su uso real requiere antes
la decisión y autorización concreta del dueño. El comando `step-fixture`
exige provider fixture declarado y `--local-http-fixture` en 127.0.0.1 con
puerto explícito; desactiva proxies y usa sólo un token público sintético.
No acepta una ruta OpenAI como fixture.

## Evidencia y límites

Las capturas finales, sus streams, fuentes originales y archivos de runtimes
están en `checks/final_attempt03_py311` y `checks/final_attempt03_py312`.
El resumen de resultados definitivo es `evidence.json`; la revisión
independiente se conserva en `review/`. `source_freeze.json` fija ocho fuentes
antes de los gates. `seal_evidence.py` coteja recibos anteriores, las cuatro
versiones Git de docs activos, archivos nuevos, índice y HEAD.

Los primeros lint/unit, el fallo de lifecycle y los dos timeouts se conservan, con sus fuentes
y streams. `capture_notes.json` distingue las invocaciones diagnósticas
que sólo tienen evidencia en la sesión, y la copia que expandió aliases
symlink de pytest: no se afirma fidelidad de inventario para esa copia.
Los archivos nuevos de integración sí se cotejan por bytes/modos/membresía;
no confieren autoridad para restaurar o reejecutar un run.

No se repite la suite histórica ni se modifica GOAL, protocolo, matriz,
producción, casos o fuentes congeladas D118–D122. Sólo los cuatro docs activos
avanzan tras las capturas; sus originales permanecen en Git D122.

**C1 técnico D107; C2–C5 No demostrado; 0/24 formales.** Faltan elección y
autorización del dueño, acceso real, identidad/snapshot y esfuerzo efectivos,
conteo/usage/factura reales, suficiencia de `high`/8192, Q y revisión competente,
H/costos completos. Luego freeze real → doce R1 → adaptación/freeze → doce
R2/selección → confirmación N/SDD/T con factores y ablaciones → intervención
causal y transferencia real. GPT Luna ayudó a explorar interfaces; no hay
comparación de calidad que permita afirmar equivalencia con Astra.
