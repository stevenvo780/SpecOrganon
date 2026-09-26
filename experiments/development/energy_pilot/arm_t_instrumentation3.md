# Corrección de instrumentación T3 · piloto de desarrollo

T1 no encontró el CLI y el entorno local de T2, instalado sin dependencias, respondió a `--help` pero falló al cargar el motor por falta de `cryptography`. T3 es otra repetición exploratoria posterior a esos resultados; ninguno de los intentos anteriores se reemplaza ni se interpreta como réplica ciega.

El wheel de SpecOrganon y todas sus dependencias ya están instalados en `.venv`. Se comprobó que `.venv/bin/organon init` y `status` funcionan en un caso temporal separado antes de este intento. Usa **`.venv/bin/organon`** para todas las operaciones del caso y crea el expediente bajo `case/` en tu directorio de trabajo. Ese comando registra invocaciones y respuestas en `cli_invocations.jsonl`; conserva también el caso y su ledger. Si un comando falla, registra el error real y no lo sustituyas por una afirmación de éxito. Usa `signed` y detente en la aprobación normativa que no puedes otorgar.
