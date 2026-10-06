# Cohorte dev4 02 cerrada: cinco entregas completas de diez

Registro prospectivo schema2, diez intentos fijos, versión 0.2.0rc3.dev4 y 45
fuentes congeladas. El proceso original session60853 terminó con exit0. Una
nueva lectura mediante su bootstrap/driver original `report`, sin llamadas ni
ejecuciones nuevas, terminó con exit0 y verificó físicamente cierres, fases,
entregas, recibos y controles públicos. Fecha del informe: 2026-10-06 04:23:28 UTC.

| Intento | Tarea | Resultado del paquete | Comprobaciones públicas |
|---|---|---|---|
| 01 | RangeAudit | Fallido: deadline control Docker, sin arranque del rol pendiente | No ejecutadas |
| 02 | LedgerFold | Fallido: dos autores de compare agotados tras rechazar 6436/6150 bytes frente a 6000 | No ejecutadas |
| 03 | TopoPlan | Fallido: deadline control Docker, sin arranque del rol pendiente | No ejecutadas |
| 04 | RangeAudit | Fallido: deadline control Docker del primer autor | No ejecutadas |
| 05 | LedgerFold | Completo, nueve fases | 104/104 |
| 06 | TopoPlan | Completo, nueve fases | 105/105 |
| 07 | RangeAudit | Completo, nueve fases | 115/115 |
| 08 | LedgerFold | Completo, nueve fases | 104/104 |
| 09 | TopoPlan | Fallido: JSON nativo inválido en autor validate, outerexit2 | No ejecutadas |
| 10 | RangeAudit | Completo, nueve fases | 115/115 |

El noveno intento pasó su test propio, pero no completó el paquete; no se
promueve por ese resultado. El fallo02 no agotó los 40 roles globales: agotó
la cuota de autores de esa fase, con 13 jobs cerrados. No se reemplazó ninguno.

Resultado: **50% (5/10)**. Intervalo Wilson descriptivo95%: **23.66–76.34%**.
Tres tipos consiguieron entregas de nueve fases; no se alcanza el umbral de
9/10. No es una comparación con libre o SDD, no hay sujetos reservados y no
acredita superioridad ni fiabilidad de dev5/dev6. La meta sigue activa.

## Contabilidad y custodia

Los recibos cerrados del informe registran 85 roles de autor, 64 revisiones,
15 comprobaciones del mandato, seis tests propios y cinco verificaciones públicas
independientes. Los roles que no arrancaron por el control Docker no se imputan
como nuevas generaciones del servidor. La suma de wall_seconds originales por
intento es 4275.604s; usa reloj epoch y no incluye toda la agregación entre
intentos ni preparación compartida. Es descriptiva y no sustituye la futura
medida monotónica total para comparar eficiencia. Coste monetario desconocido;
contadores heterogéneos de tokens no se equiparan.

`registration.json` conserva el hash original
`923d5f1d6dac9b9271d1f311c5c714c848782e0bd40afe6f49ef87ba87552055`.
`source-verification.json` y `source/` conservan los 45 inputs registrados, con
sus bytes verificados. El driver original está en el tag
`dev4-source-20261006`; el registro, en `dev4-native-cohort02-registration-20261006`.
`report.json`, `summary.json`, los outcomes/cierres, checkpoints, entregas,
diarios y salidas nativas seleccionadas permiten inspeccionar el resultado.
`manifest.sha256.json` fija los 3854 archivos seleccionados (19,638,256 bytes).

Se excluyen credenciales/perfiles, mounts, caches del proveedor y copias grandes
repetidas de fuentes/catálogos por rol. `archive.py` conserva el filtro y la
verificación. Las rutas absolutas de los recibos originales siguen refiriendo al
runtime privado conservado: este archivo es evidencia inspeccionable, no un run
reubicado ni una autorización para reejecutar llamadas o migrarlo a dev6.
