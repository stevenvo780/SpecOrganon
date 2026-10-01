# D120 · Medición conciliada y faltantes explícitos

Se añade [un lector CLI separado](../../../scripts/measure_coordinated_runtime.py)
al runtime D119. Bajo un único lock original comprueba guard, replay y
publicación nativos, captura los journals y concilia corrida/brazo/rol/request,
respuesta, recibo, ledger y cada herramienta. Publica sólo identificadores,
hashes y telemetría permitida; no copia prompts, RAW textual ni argumentos.
La API pura concilia snapshots declarados; sólo el CLI añade la comprobación
del guard/replay/publicación nativos. Ninguna de las dos autentica al proveedor.

## Resultado reproducible

- [Plan prospectivo](plan.md), commit `357ac43`.
- [Freeze](source_freeze.json), commit `8576cc6`: 92 registros; 93 con el propio
  freeze en cada captura. SHA `95a36c73ecc7cd0eb32244f9ab02df534830ddc2e1722d456d92478a5e61cc1d`.
- [51 pruebas nuevas por Python 3.11](checks/final311/report.json) y
  [3.12](checks/final312/report.json); Ruff, sintaxis y diff exit 0. Fuentes y
  HEAD iguales antes/después.
- [Doce lecturas CLI reales](checks/integration02/report.json) de los
  runtimes sintéticos ya cerrados en D119, sin reejecutarlos. Por intérprete:
  seis coordenadas A/B/C × D-F/D-E de réplica 1, **113 requests, 69 tools y
  791 tokens declarados por fixtures** conciliados. Calendarios/run IDs
  distintos entre intérpretes; no son doce celdas reales R1.
- Inventario de cada runtime idéntico antes/después. Los 2283 pins de D119,
  incluido su receipt, iguales antes/después de gates y lecturas. Después se
  actualizan sólo cuatro documentos activos; sus originales siguen en Git
  `c64169c`. Dossiers/fuentes/casos/core/GOAL/protocolo/wheel intactos.
- [Evidencia agregada](evidence.json), [revisión prospectiva](review/plan_review.json),
  [probes y cierres](review/early_candidate_recheck.json) y
  [revisión final](review/final_review.json). La cobertura se sella en
  [receipt.json](receipt.json).

```bash
/tmp/specorganon-D107-deps-re8v1j45/venv-311/bin/python -B \
  scripts/measure_coordinated_runtime.py \
  --run-dir /tmp/specorganon-D119-integration311_02-ddvo36cs/A-D-F/run
```

Para 3.12 se usan su intérprete exacto y su root original. Otro intérprete,
runtime incompleto/publicación inválida o datos discordantes rechazan la
medición. Los originales temporales están preservados además en el archivo
D119; este lector no restaura admisiones ni autoridad desde ese tar.

## Qué se mide y qué falta

| Medida | Resultado y alcance |
| --- | --- |
| Uso | Input/output/total concordantes por request y rol. Caché y razonamiento son subconjuntos; datos ausentes siguen desconocidos. No se añade razonamiento otra vez al output. |
| Coste local | Perfil declarado congelado, cálculo y redondeo por solicitud, luego suma cotejada con ledger. Input sin clasificación usa la tarifa máxima declarada; no se rotula uncached autenticado. 791 microUSD calculados por intérprete son una declaración sintética, no una factura. |
| Send | Duración monotónica de cada envío y suma. Sin boot/identidad global de reloj no se calcula unión ni W. |
| Herramientas | Duraciones de sandbox y host separadas; host incluye sandbox. No se suman ambas como actividad adicional. |
| Contexto | Lease activo y pausas del host, con alcance local explícito. No son actividad remota, H ni W. |
| Faltantes | Liberación→entrega W, H humano, conteo de input, actividad remota, precios de tools/revisión/puntuación y coste total del estudio. Tampoco se autentican modelo/esfuerzo/uso/tarifa/factura ni Q. |

La [guía oficial de razonamiento](https://developers.openai.com/api/docs/guides/reasoning)
documenta que el razonamiento se factura dentro de output; la referencia y su
alcance están en [official_usage_sources.json](official_usage_sources.json).
Consultar el esquema no verifica nuestros recibos sintéticos ni una tarifa.

## Negativos y correcciones conservados

La revisión reprodujo tres huecos de la API **pura**: input reservado distinto
del uso, ordinal booleano aceptado como 1 y epoch de líder no cero. Se
corrigieron con pruebas de rechazo y digests coherentes. El broker original
fija epoch 0 al líder; los workers deben corresponder al timeline. No se
afirmó un bypass del CLI nativo. Fuente probada y streams están preservados.

[Intentos del worker](worker_checks/) conservaron 42, 45 y finalmente 51
pruebas por intérprete. El intento 01 sólo conserva hashes de fuente; sus
bytes originales no se recuperaron. Intentos 02/03 sí contienen fuentes
before/after. El bootstrap `python` ausente y un import no usado de un helper
están documentados en [attempts.md](attempts.md).

La revisión también exigió freeze/HEAD antes/después en la captura de doce
lecturas y cotejo de matriz, cantidad real, flags nativos y coordenadas en el
sealer. Se incorporaron antes del freeze/gates finales.

## Distancia a GOAL

**C1 técnico D107 preservado; C2–C5 No demostrado; 0/24 corridas formales.**
El [inventario de rutas](routing_inventory.json) observa CLI disponibles y
cuotas en una fecha; no prueba una ruta HTTP Responses autenticada, precios
o permiso de gasto. Luna aportó [inventario acotado](luna_intake.json), no una
comparación de calidad/coste entre modelos.

Siguiente: captura prospectiva de W/conteos con reloj identificable y ruta real
autorizada con telemetría/precios verificables; 12 R1 reales, adaptación/freeze
y 12 R2/selección. Siguen reserva independiente, panel/custodia/jueces,
autoridades, campo causal alimentario y transferencia reservada. Las sumas
locales actuales no justifican una ventaja de coste/tiempo ni aceptación.
