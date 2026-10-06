# Controladores por etapas — ingeniería parcial, dev6 mutable

`neutral_controller.NeutralController` implementa recorridos N/S con reservas,
contadores, generaciones atómicas, batería original inmutable y auditoría D/G/H
sobre snapshots completos. La documentación de transiciones está en
`../../development/STAGED_CONTROLS_V1.md`. Este hito no congela una versión
completa, certifica controles competentes ni acredita eficacia de SpecOrganon.

## Verificación final del padre

- `targeted-tests-09-command.json` y sus stdout/stderr: **627 passed, 16 skipped**.
  Incluye bibliotecas comunes, transporte/contratos nativos, recuperación,
  controlador T, interfaces CLI/MCP, runner y nuevos controles N/S. No es la suite
  histórica global. Tres componentes Docker antiguos y trece nuevos requieren
  opt-in; los trece nuevos tienen ejecución separada y no se cuentan dos veces.
- `docker-controls-11.stdout`: **13 passed**, Docker real, test image dev4 existente.
  Dos recorridos N/S con autores/revisores sintéticos; crash tras medida cerrada;
  un test realmente fallido que rechaza `passed=true` adulterado; SIGKILL antes y
  después de 6000s, sin restart; medida cerrada recuperada sin resumen después del
  corte; puente nativo real con ejecutable Gemini **simulado**, perfil vacío y
  body vacío que cierra exit2 sin aceptar el rol. Cero llamadas experimentales a
  modelos. La simulación está declarada, no es una prueba de proveedor real.
- `installed-receipt-05.json`: wheel local SHA
  `42c4c5f02fe30102121fa106b4336da56468630a6bf67580a6a3379bc1b34faf`;
  **36 módulos** byte iguales a las fuentes, imports correctos, CLI help exit0,
  MCP stdio real del host con **24 herramientas** y caso sintético controlado.
  Sus errores esperados de versión/ruta prueban rechazo, no éxito externo.
  La wheel queda en `local-wheel/` ignorada: no es una release publicada ni
  acredita el paquete dev6 instalado dentro de una nueva imagen Docker.
- `native02-custody-01.stdout`: el archivo histórico dev4 mantiene 3854 hashes,
  45 fuentes registradas, diez cierres y 175 recibos host enlazados. Cero nuevas
  ejecuciones o llamadas. Su resultado terminal original sigue siendo **5/10**,
  sin reemplazos; no satisface el 90%. La GOAL.md alimentaria no cambia.

## Rechazos, fallos y revisión independiente

La revisión arquitectónica textual `c7c9cd6e19c243428b87ea6170d8edf3`
(`design-review-01.json`) rechazó F01–F10. Las revisiones estáticas de código
`dd9f8456fc374ce79d2555a5e2d1b189` y `a85e417d36d048378cf63cb0925d005c`
rechazaron R1–R7 y R8–R12; los resultados completos se conservan. Se corrigieron
pins de ejecutable, argv/metadata/transcripts medidos, preflight Codex, resultado
adulterado de tests, batería/repair, presupuesto/reanudación y fallo H aislado.
La revisión `dfc733cd507f474eb9d646e282a98dbe` fue cancelada por el **agente padre**
cuando las pruebas reales requirieron cambiar sus fuentes; no emitió veredicto.
Se añadió un tercer control de timeout de inspect durante reanudación y dos
SIGKILL reales durante escritura atómica de resultado/generación. Los temporales
no publicados se ignoran sin interpretar sus bytes; nombres extraños, symlinks,
hardlinks y directorios se rechazan. La reparación también rechaza documentos
nuevos. La construcción de transporte fallida ante un create-intent propio y
una limpieza no confirmada conservan reserva sin coste terminal conocido.
El texto genérico del MCP «solicitud del usuario» no describe esa decisión humana.
La revisión `7f66fc24ff824055b865bb71c2c3c12e` rechazó R14/R15/R16
(`code-review-04.json`); se corrigieron con los controles anteriores. La revisión
`430fd590ecab483fadb3b2ad094bf107` rechazó R17 por falta de launch con intent
conservado (`code-review-05.json`). El transporte y controlador ahora retienen
reserva en ese caso y exigen limpieza confirmada. Dos controles Docker nuevos
retiran launch con un contenedor real en marcha, antes/después del corte.
La revisión final `623d84b55e6240d18afd330dec8e4912` aceptó el cierre R17 y las
rutas vecinas R14–R16 sin hallazgos (`code-review-06.json`), verificando los trece
SHA al inicio/final. Es una aceptación de ingeniería acotada; no certifica
eficacia, competencia de los métodos ni nuevas ejecuciones de proveedores. Los reviewers usan Codex GPT-6.1 Sol, cuenta principal, Kratos,
access=read/text, sin ejecutar pruebas, Docker ni delegar. La aceptación de
helpers anterior no cubre estos nuevos controladores. Las pruebas las ejecutó
el padre; los fixtures de journals Codex no autentican un operador malicioso.

Los registros conservan fallos intermedios:

- `docker-controls-01.stdout`: hook de crash interrumpió replay anterior a medida;
  se corrigió la inyección. `docker-controls-02` cerró cuatro controles.
- `targeted-tests-04.stderr`: ruta de test inexistente, pytest exit4; ninguna prueba
  se atribuye como aprobada a esa invocación.
- `targeted-tests-05.stdout`: 603 passed, 11 skipped y un test histórico fallido
  por exigir schema9 cuando el controlador vigente registra12. Se actualizó
  sólo la comprobación del esquema actual, manteniendo todos sus guards.
- `docker-controls-06.stdout`: ocho fallos tras reconocer únicamente la grafía
  antigua del stderr de objeto ausente. Se añadió el literal exacto minúsculo de
  este Docker y seis controles de target/error. Error del daemon y mensaje de otro
  CID siguen sin promoverse a ausencia ni autorizar recreación.
- `recovery-regressions-04.stdout`: un guard rechazó el hardlink del fixture
  antes de la aserción prevista porque también enlazaba `initial.json`. Se
  corrigió el fixture para enlazar un archivo independiente; el guard productivo
  permaneció intacto. `recovery-regressions-05.stdout` da 95 passed.
- `recovery-regressions-06.stdout`: un marker started de fixture se tomó como
  dispatch físico. Ahora fixture_mode distingue ese registro sintético; un
  launch/intent real sigue exigiendo confirmación. `recovery-regressions-07`:
  99 passed.
- `docker-controls-10.stdout`: 12 passed y un fallo en la ruta de launch ausente
  previa al corte. Se clasifica como pendiente ya en `_prepare`. El contenedor
  del fixture fallido se retiró sólo tras comprobar CID, imagen, nombre, etiqueta
  y nonce exactos (`pending-cleanup-01.json`); no se reinició. La versión final
  da los 13 controles indicados arriba.
- Los logs intermedios `targeted-tests-01/02/03/06/07/08`, `docker-controls-03/04/05/07/08/09` y
  `installed-receipt-01/02/03/04.json` son snapshots previos, no pruebas de los bytes
  finales. No se suman sus conteos como muestras independientes.

## Archivo reproducible y límites

`docker-controls-02/03/07/09/11-archive.json` ligan 207, 243, 372, 535 y 605
archivos seleccionados, respectivamente: **1962 archivos, 4321166 bytes**. El último contiene journals,
respuestas sintéticas, fuentes del puente y el simulador declarado; no copia
credenciales ni perfiles reales. `verify_archive.py --check-source` verifica
hashes/inventario y fuentes actuales sin ejecutar Docker o modelos. Las copias
consistentes no constituyen una nueva ejecución portable ni attestación física.

Reproducir la mecánica exige las imágenes locales exactas indicadas en
`engineering-receipt.json` y Docker disponible. El comando opt-in es:

```sh
SPECORGANON_NEUTRAL_DOCKER_CONTROLS=1 uv run --frozen --extra dev python -m pytest tests/test_neutral_docker_controls.py
python goals/method-superiority-v1/evidence/staged-controls-01/verify_archive.py --check-source
```

Los trece controles no montan sesiones reales de autores/revisores. La cuota del
volumen Codex original sigue desconocida; el saldo de la app principal no se
atribuye a ese volumen. Las siete invocaciones de ingeniería consumen cuota y se
registran separadas de generaciones experimentales. Coste monetario y ratio de
tiempo comparativo desconocidos.

Pendiente: driver prospectivo instalable N/S, revisión de competencia/definición
de libre, integración T al contrato común, F independiente, preregistro
estadístico principal/réplica y tamaño/parada, imagen dev6 instalada, congelación
de versión completa y su cohorte fija ≥10 con ≥9 completas. Después deben
satisfacerse la comparación reservada y la réplica de esa misma versión.
**Cero generaciones nativas dev6, cero reservados, F y common_complete
desconocidos; la meta sigue ACTIVE y no se declara superioridad.**
