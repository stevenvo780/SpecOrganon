# D121 · Observación prospectiva local

Plan previo `d8bbae8`; fuente congelada `892d6a8`, **104 registros** más
extractor externo. Hash del freeze:
`93e6dbab2cb1568ad09497a0d3126d10489a2e50089e09436ad2d080103bc824`.
GOAL, protocolo, core, wheel, casos y fuentes D119/D120 conservados.

## Qué cambió

`coordinated_observation_journal.py` registra eventos privados canónicos,
cadena de SHA, reloj monotónico y hash del boot. Lock de driver no bloqueante
separado del lock de eventos; token sólo en memoria/PID. Un crash activo no
reanuda, y un callback después de cerrar el paso devuelve false sin escribir.

`observed_coordinated_runtime.py` libera sólo un run preparado intacto, dentro
del lock original. Predice IDs/requests con los turnos originales y observa
count/send mediante proxy de protocolo; no es subclase HTTP. El deadline se
fija antes de persistir, por lo que ese I/O consume el timeout. Hook por instancia
del broker recibido por guard, instalado una vez; originales se delegan una
sola vez. Sin reemplazos globales. Precheck coteja receipts de delegación,
merge y entrega y métricas finales antes del visitor.

El cierre requiere snapshot/guard/replay/publicación nativos D119 y conciliación
D120. Conteos, envíos y tools coinciden exactamente en IDs/roles/digests/usage;
los intervalos send están dentro de sus receipts nativos. Duración de tool
observada contiene los subconjuntos host/sandbox nativos. La API pura no
afirma ejecución del guard; el caller nativo sí la verifica.

## Evidencia nueva

- **88 pruebas por Python 3.11/3.12**: 65 journal y 23 wrapper. Ruff,
  compilación y diff exit 0; freeze/HEAD before/after iguales.
- Seis runs NUEVOS en total: A/B/C × D-E en cada intérprete, seed 121, 118 CLI reales,
  HTTP loopback y tools originales. **110 count, 110 send, 66 tools** y
  770 tokens de fixture declarados. Los calendarios/IDs de ambos entornos
  son distintos. A sin solapamiento de workers; B/C con solapamiento HTTP.
- Dos releases retrospectivos sobre originales completed rechazados por
  CLI, sin crear observador; inventarios intactos. Ninguna request/tool nueva
  contra los doce originales D119.
- Baseline D119/D120: 2283/2439 pins, incluidos receipts y cuatro docs
  históricos cotejados contra Git `c64169c`/`f05bb9c`. Todos los inventarios
  de los doce originales iguales antes/después. Los cuatro docs activos
  avanzan después de las capturas; sus versiones anteriores siguen en Git.
- Dos archives, cada uno con **1369 entradas** cotejadas por bytes/modos,
  membresía y raíces originales. No restauran autoridad:
  7 777 734 B, SHA `8a5f4bc67f6f78b0ddb8fe0e9288d9d83caf2a1a1f3bf5bf5ae197fcb00c3f38`;
  7 777 744 B, SHA `caf742c1ba6c9c5d81fcd9a3431f37684bfba33f281b7ae71445cd098a88904b`.

| Entorno | A · W local s | B · W local s | C · W local s |
| --- | ---: | ---: | ---: |
| Python 3.11 | 168.573035 | 158.715666 | 146.330522 |
| Python 3.12 | 186.162558 | 167.919466 | 156.224924 |

Estos valores describen estos controles sintéticos en este host y con
observación. No son una comparación de eficacia, latencia de proveedores ni
ventaja de las arquitecturas. W va de la muestra de liberación del run preparado
a la muestra de la marca de entrega verificada; incluye pausas, guard/I/O y
observación dentro de ese intervalo. No incluye preparación previa ni recepción
externa o serialización posterior del informe. Wall delta es separado; no
altera elapsed monotónico. Sumas/uniones por kind y rol evitan sumar solapamientos
como si fueran pared. W menos unión es tiempo local fuera de callbacks, no H ni CPU.

## Correcciones y límites

Todos los intentos conservan fuentes/streams: journal 55→61→65 pruebas y
wrapper 5 pass/6 fail/9 errors→20→23 pass. Error inicial count_input/count_payload,
E402/F401, negativos de reloj/privacidad y gap de precheck conservados.
El revisor reprodujo el precheck con cuatro negativos y control válido; no
afirmó bypass del cierre D120. Ver revisión y recibo en este dossier.

Cadena local, clocks y locks cooperantes no autentican custodia, proveedor,
versión, esfuerzo efectivo, usage o factura. Callers directos sin observador
se detectan por cobertura/checkpoint; no se impide un escritor hostil del mismo
UID. No hay garantía de cancelación remota. Un fallo puede dejar evidencia
parcial no reanudable; no se convierte en duración cero o entrega exitosa.

**C1 técnico preservado; C2–C5 No demostrado; 0/24 formales.** H, actividad
remota, costes completos de tools/personas/evaluación/estudio, desglose de
caché/razonamiento, ruta verificable y Q siguen faltantes. No hubo proveedor
pagado, reserva ni campo. Ver [siguiente puerta](next_activation.md).

## Reproducir el alcance local

Los helpers capturan comandos y fuentes antes/después, con los intérpretes
registrados en `capture_checks.py`. `checks/` conserva resultados y archives;
`archive_runtimes.py --archive … --inventory …` coteja el archivo sin extraerlo.
`seal_evidence.py verify --head` coteja live/index/HEAD y los pins históricos.
Para repetir ejecuciones se requiere un nombre de captura y un destino nuevos;
no se reutilizan los IDs/claims originales. Los paths temporales y la cuota
son snapshots, no garantías de disponibilidad futura.

Luna hizo inventarios read-only de interfaces y decisiones de activación;
root verificó vigencia frente a D118/D119. No se midió calidad relativa de Luna.
