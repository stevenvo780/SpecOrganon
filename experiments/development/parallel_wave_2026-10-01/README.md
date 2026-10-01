# D114 — propuestas C en paralelo

**Estado:** mecanismo exploratorio implementado y revisado. C1 técnico D107
se conserva; C2–C5 no demostrados. **Cero corridas formales de las 24**.

El plan `bce12de` precede la implementación; las fuentes están congeladas en
`4e9de575c301d499a6e60230e4704d9e1bdcf0a6`. Los [24 pines](source_freeze.json)
y los [38 activos protegidos](baseline_pins.json) coinciden con sus bytes.
Producción, GOAL, protocolo, core A/B/C, casos originales y wheel no cambian.

## Qué funciona

- WaveLedger schema 3 admite atómicamente el lote completo antes de enviar.
  Tokens, solicitudes y coste declarado se suman bajo un único techo. Un
  permiso original marca `inflight` antes del efecto; abrir el archivo después
  no autoriza reenvío. La conciliación puede llegar fuera de orden.
- Contexto schema 2 optativo selecciona ese ledger y fija la elección en sus
  bindings/checkpoint. Schema 1 mantiene TokenLedger; no hay ledger espejo.
- El coordinador lanza 2–4 propuestas con contextos privados y luego un
  reviewer serial del mismo modelo/esfuerzo. El reviewer recibe hechos comunes
  y artefactos textuales, sin copiar los items privados de razonamiento.
- C selecciona tareas risk elegibles y disjuntas; fija base, hechos y fuentes.
  Este perfil exige normas pendientes y rechaza una aprobación no verificada.
  No tiene tools, no modifica el grafo y no avanza fases.
- Una lease/plazo cubre counts, sends y reviewer. Workers daemon sólo entregan
  resultados al host. Vencer el plazo retorna sin esperar callbacks; reservas
  inciertas conservan su allowance. Las respuestas oportunas ya observadas se
  preservan antes de guards/validación. No se garantiza cancelar trabajo remoto.
- Sólo un contexto y estado ambos `completed` exponen artefactos publicados.
  Un fallo de cierre conserva archivos forenses sin publicarlos como propuestas.

## Evidencia reproducible

| Gate posterior al freeze | Resultado |
| --- | --- |
| Python 3.11.15, diez archivos afectados/legacy | 231 passed, 117.05 s |
| Python 3.12.3, mismos diez archivos | 231 passed, 110.06 s |
| Ruff, compilación y diff-check, cada intérprete | exit 0 |
| Fuentes por captura | 21/21 idénticas antes/después |
| Trazas C por HTTP local | D-F/D-E sintéticos y CLI D-F por intérprete: seis rutas distintas |
| Archivo reabierto por root y revisor | 7.875/7.875 regulares de nueve raíces, cero diferencias |

[Capturas finales](checks/), [trazas verificadas](verified_traces.json),
[manifest de runtime](archives/runtime_manifest.json) y [revisión](review.md).
Cada traza C conserva tres requests, tres artefactos y 39 tokens **reportados
por fixtures**, sin normas aprobadas ni fases aceptadas. Los intervalos de
envío y la barrera prueban concurrencia real local; esos tokens no miden uso
de un modelo. El motor también verifica ancho cuatro, crash, holds, caps,
respuesta tardía, input/fuente/claim cambiados, tools inválidas y cierre fallido.

El tar [runtimes.tar.gz](archives/runtimes.tar.gz) tiene 2.862.493 bytes y SHA
`357d510c3ad3d11ddd50479fcc753419a8bb9500dc1484fa53c9cfa0e61ebae0`.
Directorios y 376 symlinks sólo tienen metadata, sin seguir targets. No es una
imagen restaurable de sesiones. Los pytest roots por defecto de unitarios
tempranos de ledger/contexto no están archivados; sus fuentes y streams sí.

Para repetir los gates desde el checkout fuente:

```sh
python3 -m pytest -q tests/test_managed_wave_ledger.py tests/test_managed_wave_context.py tests/test_managed_parallel_wave.py tests/test_c_parallel_work.py
```

La CLI de desarrollo es `scripts/c_parallel_work.py prepare|status|execute`.
`prepare` recibe rutas absolutas de estado risk, hechos UTF-8, config JSON y
directorio nuevo; `execute` exige el checkpoint devuelto. La prueba CLI usa
`--local-http-fixture http://127.0.0.1:PORT/v1`, sin leer auth del operador.
La ruta `--provider openai` es explícita y no se ejecutó en este corte.

## Negativos y correcciones

[Evidencia y límites](evidence.md) distingue los primeros gates fallidos,
correcciones de producto y errores de fixtures. Tres P2 de revisión quedaron
cerrados antes del freeze: autoridad normativa de entrada, pérdida de raw
tras guard post-send y exposición de artefactos al fallar el checkpoint.
El primer enumerador de trazas incluyó alias pytest `current`; el guard de
identidad rechazó esa ruta. El verificador y revisor los excluyen del conteo.

## Qué sigue

Esta wave tiene identidad nueva `parallel_wave_v1`, separada de calendarios
DEV solo y de los tríos confirmatorios. C necesita tools en branches privadas,
su integración/publicación bajo presupuesto global y un registro prospectivo
comparable antes de R1. No se reclasifican fixtures como celdas ni se cambia
una corrida ya abierta.

Siguen pendientes contrato/rúbrica común sin respuestas, ruta/modelos/versiones/
effort/telemetría y autorización; 12 R1 reales, adaptación/freeze R2, 12 R2 y
selección; reserva, custodia, panel, jueces y autoridades competentes, C2
completo, campo causal alimentario y transferencia completa. No hay Q,
comparación entre modelos, factura, norma humana ni impacto observado aquí.
