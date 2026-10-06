# Evidencia pública anterior a generar LotLedger

Origen observed; datos concretos en public-sqlite-observations.json y procedimiento
en public_sqlite_observations.py. Ejecutado2026-10-05 con Python3.12.3/SQLite3.45.1,
imagen sha256:98723123de528a5f0201a1c341fe044f88d885345b2e1bedd6a89574c4796d92,
sin red/perfiles y sólo el script de primitivas montado readonly. Seis assertions,
seis resultados coincidentes. Población seis entradas sintéticas SQL, unidad cases,
métrica sqlite_primitives_verified. Localizadores observations/id de ese JSON;
fuente/argv/streams y hashes conservados en los recibos originales. No medir un
programa generado ni afirmar que seis assertions prueben el contrato JSONL.

PK duplicate rechaza y conserva una fila; ABORT rechaza el statement pero conserva
la primera fila de la transacción; ROLLBACK explícito elimina el lote; CHECK rechaza
saldo negativo y mantiene7; transferencia guardada conserva total8 con A4/B4;
origen insuficiente no afecta filas y conserva A2/B1. Son observaciones de ese
entorno, no garantía de política completa ni demanda/utilidad/impacto humano.

Fuentes primarias consultadas2026-10-05:
[SQLite Transaction](https://www.sqlite.org/lang_transaction.html),
[ON CONFLICT](https://www.sqlite.org/lang_conflict.html) y
[Python3.12 JSON](https://docs.python.org/3.12/library/json.html).
La biblioteca JSON admite extensiones de números y comportamiento sobre claves
repetidas por defecto; el contrato exige rechazo explícito. SQLite permite
transacciones pero la política de evento/idempotencia debe especificarse; no
identificar ABORT con rollback completo ni IGNORE con igualdad de contenido.

No existe baseline medida de conformidad completa LotLedger, ni comparación
con usuarios, ni dinero atribuible. Estos valores quedan desconocidos.
