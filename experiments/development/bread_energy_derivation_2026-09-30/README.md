# D108 · Energía documental del pan

Desarrollo del30de septiembre2026. **Aceptación global1/5; C2–C5 No demostrados**.
GOAL/matriz, núcleo24módulos y wheel D107 permanecen iguales. No se reconstruye
el método para esta variante alimentaria: usa put/run/status/gate/trace/next
existentes por CLI/MCP instalados.

## Registro previo y derivación

Plan `880ccbd`, instrumentos y controles `b7a1df6`, freeze `64aa0a8`:
**89archivos públicos** comprobados contra bytes vivos y blobs Git antes del
lanzamiento. Preparador/ejecutor verifican expresamente todos los inputs
conservados, incluido el wheel; no dependen de archivos omitidos del commit.

Se reutiliza el caso documental signed de64eventos del borrador D102 y sus
tres evidencias v1: masa736g/pieza, electricidad0,297kWh/pieza y
gas0,115kWh/pieza. Nuevo protocolo de esta derivación fija también las tres
fuentes; inferencia, evidencia e indicador son sus descendientes.

`(0.297 + 0.115)/(736/1000) = 103/184 kWh/kg produced bread`.
HALF_EVEN24 da0,559782608695652173913043; error racional
11/23000000000000000000000000≤5e-25. Es precisión de representación,
sin cuantificar incertidumbre física o crear umbral de eficacia. Población:
producto comercial estudiado; publicación2018-12-21, registros empresariales
de fecha desconocida. Fecha de la derivación UTC real separada de publicación.

No se estima energía útil, emisiones, coste, baseline actual, lote observado,
causalidad ni equivalencia de valor. Tampoco se recrea el ACV de los autores.
La suma por kg producido no equivale a la unidad funcional completa consumida.

## Pruebas y ejecuciones reales

Ruff y compilación pasan. **Cuatro pruebas puras de contrato en cada Python**
verifican aritmética, grafo/guards, siete negativos y JSON inválido. Cero
ejecuciones experimentales durante esos checks. Fuentes y streams en
[unit_checks](unit_checks/receipt.json). Suite global2674 es D107; no se repite
la global porque no cambian los24módulos de producción.

Un único intento por entorno, sin retry, rebuild o instalación nueva. Se
reutilizan wheel137581B SHA256
`63c58a91c3f174d41b8ca8b6ce21122f9aeb8f156005ad59767db4960c9f88e3`
y entornos externos3.11.15/3.12.3;24módulos y1555archivos públicos por entorno
verificados antes/después. Sourcefreeze e instrumentos compilados desde bytes
fijados; env mínimo sin copiar HOME, credenciales ni sesiones.

| Resultado | Python3.11 | Python3.12 |
| --- | ---: | ---: |
| Exit / timeout / error | 0 / no / no | 0 / no / no |
| Duración del proceso completo | 33,28s | 37,74s |
| Puts CLI / MCP | 4 / 4 | 4 / 4 |
| Prefijo / eventos finales, por caso | 64 / 68 | 64 / 68 |
| Replay aplicado / omitido | 0 / 4 | 0 / 4 |
| Comparaciones CLI/MCP | 58 | 58 |
| Controles de revisión de fuentes | 3 | 3 |
| Controles de archivo | 2 | 2 |
| Negativos de preparación en memoria | 7 | 7 |
| Fases aceptadas | 0 | 0 |

Cada calls.jsonl conserva243registros:63CLI,61MCP (incluye discovery23tools),
un builder,60registros de tiempo MCP y58comparaciones. Los tiempos añadidos
son una adaptación explícita del capturador D105, sin afirmar framing raw;
se conservan stdout/stderr y modelos SDK originales. Verificador instalado
D107 se compila desde bytes verificados y sólo se usa verify_installed.
La vista temporal de _pending se adapta al pan, con comprobación adicional
de todas las normas/decisiones reales y cuatro criterios threshold-null.

Cuatro positivos mantienen proyecto/UUID y64eventos originales. Nueve gates,
cuatro trazas nuevas, status y next coinciden por ambos transportes. La
comparación entre positivos excluye sólo timestamps/hashes de nuevos eventos;
sus payloads coinciden. `frame` sigue listo para revisión independiente,
sin revisión, avance o aprobación nueva.

En copias, revisar cada fuente con datos idénticos crea un evento69 y deja
stale los cuatro nodos nuevos. Cambiar/eliminar derivation.json afecta la
evidencia y el indicador sin añadir eventos de consulta; lecturas/trazas
siguen disponibles. Restaurar bytes exactos recupera el estado anterior:
no se atribuye memoria de daño transitorio sin evento durable. Los siete
rechazos son del constructor en memoria, no del put genérico; ningún writer
del ledger se invoca en ellos. Los positivos permanecen intactos.

## Conservación y publicación

Dos tar con216regulares cada uno, sin symlinks; todos los miembros reabiertos
y cotejados. Recibos y streams terminales se copian byte exacto:
[3.11](archive_311.json) · [3.12](archive_312.json).
[Pan68 publicado](../../../cases/bread_documentary_energy/README.md): diez
copias originales del MCP positivo3.12 y preparación, sin locks.
El recibo de preparación declara0puts porque precede su ejecución.

Revisión preventiva cerró tres P2: fecha de derivación confundida con
publicación, éxito sin reporte y falso verde del archivo tras error final.
Fuentes iniciales de wrappers se conservan sin ejecución. La primera fuente
del builder revisado no se archivó separadamente; su SHA y limitación quedan
declarados, sin reconstruirla. Fallos de rutas locales Ruff preservados;
corrección al binario público disponible, sin instalar.
[Gate previo](prelaunch_review.json).

[Revisión posterior independiente](postrun_review.json) recalcula89pines,
432miembros, diez copias, cadenas/controles,58pares y128streams por Python;
confirma instalación sin cambios y alcance temporal/aritmético. Sin P1/P2
abierto en ese alcance; no se reejecutan sondas/tests para revisar.
[Recibo consolidado](receipt.json) · [Conservación de anteriores](preservation_after.json).

Para otra repetición usar los inputs e instrumentos del freeze64aa0a8,
preparar entornos/destinos nuevos y registrar/comprometer nuevos pines antes
de ejecutar. Los markers impiden repetir estos intentos. Paths e inventarios
de entornos actuales son locales a esta máquina, no un paquete portable.

## Límites y próximo trabajo

La derivación específica coteja valores, unidades, bases, versiones,
localizadores, hash PDF y alcance. El motor genérico no valida semánticamente
esta división ni autentica verdad física/custodia externas. No sustenta los
cuatro indicadores de intervención, que siguen sin evidencia competente o
umbrales aprobados. El resultado añade trazabilidad documental de una medida;
no convierte C2–C5 en PASS.

Sin Q, generación experimental de modelos, Luna nuevo, norma humana, campo
o corrida de las24. Pendientes: evidencia técnica tipada de captura/bases,
evaluación final independiente, autoridad y métricas normativas competentes,
baseline enlazado/observación de efectos y comparación de modelos/agentes.
