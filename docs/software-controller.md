# Controlador externo de software: schema6

Este controlador conduce casos locales mediante el motor SpecOrganon. Los
autores y revisores trabajan en procesos Docker separados; los tests se ejecutan
en otro contenedor sin red ni perfiles de proveedores. El motor conserva sus
compuertas y versiones. Una aprobación local documenta un mandato existente y
no autentica identidad, consentimiento personal ni custodia externa.

La versión de ingeniería schema6 admite solamente runs nuevos. Los runs schema5
de LogLens e IntervalDesk permanecen terminales e inconclusos; cambiar el código
no permite migrar su presupuesto o sustituir una llamada fallida.

## Preparación y ejecución

Desde la raíz del checkout:

```bash
cd /datos/workspaces/personal/SpecOrganon
uv sync --locked --extra dev
uv run python scripts/autonomous_software_controller.py --help
```

Antes de generar, guarda el contrato público, el mandato existente y los límites
del experimento. Crea el caso con política local explícita; selecciona las cuentas
autorizadas y verifica sus cuotas/rutas actuales. Conserva hashes de las imágenes,
catálogo público y fuente. El directorio del run debe ser privado, persistente y
estar fuera de los mounts de los proveedores. Los perfiles originales se montan
en su rol correspondiente: no copies tokens o auth.json.

La CLI requiere `--case`, `--run-root`, `--contract`, `--mandate`, `--native-image`,
`--test-image` y `--public-catalog`. Elige explícitamente autor/revisor de familias
distintas mediante `--author-provider`, `--author-model`, `--reviewer-provider` y
`--reviewer-model`. `--steps 1` admite un único paso; nunca crea de nuevo el caso.
Una segunda invocación sobre el mismo run recupera su checkpoint, sujeto al
presupuesto original. Los errores terminan con código2 y un motivo estructurado.
Un proceso incierto o timeout nativo conserva el fallo: la recuperación no lo
transforma en otra generación. La comparación reservada exige además su propio
prerregistro y no se ha iniciado.

## Construcción y medición

Build mantiene una fase metodológica, con dos autorías iniciales:

1. Programa y README de al menos200 caracteres: exactamente un put nuevo de
   implementación, sin tests. El controlador sella los hashes de esos archivos
   y la versión del ID de implementación.
2. Tests pertinentes: sólo nuevos archivos `test_*.py`, un draft de test y una
   nueva versión del mismo ID de implementación. Programa y README permanecen
   idénticos. El test enlaza criterio e implementación actual y declara un argv
   absoluto; command se deriva mecánicamente de ese vector.
3. El executor mide el test sobre un snapshot readonly. Su resultado, streams y
   hashes se registran antes de solicitar revisión semántica independiente.
4. Sólo un fallo real cerrado o un rechazo semántico vigente permite una tercera
   autoría de reparación. Actualiza los mismos IDs. Toda segunda medición exige
   cambio en archivos Python o argv, incluso si la primera pasó. Un segundo fallo,
   segundo rechazo o rol inconcluso detiene el caso.

No se admiten `passed`, recibos o avances declarados por el autor. Un passed real
es una condición mecánica: el revisor debe juzgar código, pertinencia de pruebas,
documentación, premisas, alternativas y trazabilidad. Las nueve fases conservan
sus contratos y snapshots; dos etapas de build no son dos fases nuevas.

## Presupuesto y admisión

El techo del controlador es40 llamadas, con dos autorías por fase salvo las tres
permitidas de build, y dos revisiones/aprobaciones por fase. El transporte mantiene
180s por rol y6000s globales desde la primera admisión. El executor conserva
120s,1GiB,2CPU,128pids y dos mediciones por ID. Recuperar no reinicia esos límites.

Cada mapa completo de items actuales de una fase admite hasta seis items y6000
bytes de contribución JSON codificada. Los archivos combinados admiten20000 bytes.
Se mide la contribución al request, incluyendo ID, deps y metadatos; no sólo texto
o bytes de disco. El request completo conserva el guard adicional110000 bytes,
y la entrada nativa128000. El estado se conserva completo. Contratos largos,
historiales y razones nativas todavía pueden exceder el guard global: el caso
entonces se detiene. La fixture de carga prueba un escenario explícito, no una
garantía para cualquier entrada.

Cada stream completo de test admite4000 bytes de contribución codificada para
revisión; el raw puede conservar hasta2MiB. Exceder el cap de revisión bloquea
admisión sin registrar passed=true. No se sustituye la salida por un prefijo.

El manifiesto completo se aplica primero sobre una copia privada del ledger
actual para verificar conflictos y tamaños. Sólo tras esa admisión se escriben
archivos y puts reales. SIGKILL en puts/rename/checkpoints recupera el mismo packet
cerrado de forma idempotente. Un checkpoint o archivo divergente bloquea replay.

## Comprobación y alcance

```bash
uv run python -m pytest -q tests/test_software_controller_resources.py \
  tests/test_software_controller.py tests/test_controller_recovery.py
```

Las fixtures son inventadas y están marcadas como sintéticas. Se verificaron
además tests instalados en una imagen limpia, CLI/MCP real, perturbaciones de
evidencia/rechazo/contradicción/premisa y SIGKILL real. Los recibos de ingeniería
están en `goals/autonomous-software-v1/evidence/`; sus fallos intermedios se
conservan. La revisión independiente del código no ejecutó tests ni aprobó una
entrega de nueve fases.

`package_gate` exige las nueve fases actuales aceptadas, trazas completas,
artefactos válidos, ambos checkpoints, los IDs de implementación/test originales,
tests externos verificados sobre bytes actuales, README útil y revisiones de
build/validate sobre el árbol vigente. Estos controles todavía requieren una
entrega nueva real y la evaluación comparativa prevista. La goal sigue activa;
esta versión de ingeniería no es la release final ni validación de la tesis.
