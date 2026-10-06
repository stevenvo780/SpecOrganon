# Piloto autónomo de backups

Estado: las 18 corridas, 36 etapas y 36 evaluaciones reservadas terminaron.
La auditoría de integridad pasó; las 36 comprobaciones exploratorias en Python
limpio reprodujeron los mismos checks. El producto seleccionado, sin modificar,
pasó V1/V2/V3 (22/22 cada una), 32 pruebas propias y su ejemplo aislado.
Consulte [RESULTADOS.md](RESULTADOS.md), [producto](product/README.md) y
`planning/checkpoint.json`. Los controles de desarrollo no son resultados del piloto.
Este experimento evalúa un producto de software pequeño y el paquete SpecOrganon
frente a esta guía SDD y trabajo libre. No demuestra eficacia de campo ni cumple
por sí solo el GOAL.md original.

El contrato y los presupuestos están en `planning/contract.md` y `planning/protocol.md`.
`schedule.py` genera seis bloques pareados y las seis permutaciones del orden N/S/T.
`run_pilot.py` congela hashes e imágenes, ejecuta cada etapa en una sesión efímera,
conserva artefactos y revisiones separadas y evalúa después de cerrar todas las entregas.
Nunca monta el evaluador, semillas reservadas, fuentes del host ni controles al autor.

Desde la raíz del repositorio:

```bash
docker compose build codex
docker compose run --rm codex codex login --device-auth
docker build -f experiments/backup_pilot/Dockerfile.control -t specorganon-backup-control:dev .
docker build -f experiments/backup_pilot/Dockerfile.evaluator -t specorganon-backup-evaluator:dev .
PYTHONPATH=src python -m pytest -q experiments/backup_pilot/tests experiments/backup_pilot/development/tests
python experiments/backup_pilot/run_pilot.py freeze --seed 17863
python experiments/backup_pilot/run_pilot.py run
```

El login sólo es necesario si este volumen aún no tiene sesión. No copie auth.json,
no intercambie perfiles ni cambie cuenta/modelo por errores de cuota. El ejecutor
utiliza exclusivamente el volumen `specorganon-lab_codex-home` ya autenticado.
N/S usan una imagen sin toolkit. T añade el MCP local real y la skill del método.
La excepción de AppArmor y el perfil seccomp del modelo se describen en el protocolo;
Codex mantiene su sandbox y el evaluador usa el aislamiento Docker habitual.

Cada etapa conserva `author.prompt.txt`, `author.jsonl`, recibos con duración,
exit_code, timeout, hashes y tokens informados; T añade sesión de auditoría del
método. La revisión funcional recibe sólo contrato, código y README, con la
asignación oculta aunque su estilo pueda permitir inferirla. No devuelve cambios
para mejorar esa misma entrega. La etapa dos comparte el cambio --max-bytes,
sin resultados de pruebas reservadas. `artifact` congela cada entrega antes de
la etapa siguiente; `evaluation.json` y `evaluation-streams` conservan resultados
y streams limitados con tamaño/hash completo y señal explícita de truncamiento.

`frozen/manifest.json` se crea una sola vez. No lo regenere para legitimar cambios
posteriores. El runner valida los hashes antes de cada etapa. Los recibos ya
cerrados se leen sin repetir llamadas. Un marcador `.started.json` sin recibo
final indica interrupción y bloquea la repetición automática: inspeccione el
proceso/contenedor y documente la disposición explícita antes de reanudar.
`.lock` impide dos escritores; no elimine un lock de un proceso vivo.
Para otra reproducción independiente use un checkout separado, imágenes verificadas
y un árbol nuevo de resultados. No sobreescriba ni reutilice soluciones previas.

`development/reference` es un control del evaluador, nunca una corrida ni el producto
seleccionado. Los controles defectuosos y fallos de infraestructura también quedan
guardados. El análisis posterior debe usar seis unidades independientes por brazo,
no cada check como réplica. Presentará fallos críticos, calidad por etapa, diferencias
pareadas, costes y límites, incluso si no aparece ventaja del método.

Al existir `runs/complete.json`, compruebe primero la consistencia de la evidencia:

```bash
python experiments/backup_pilot/audit.py --output experiments/backup_pilot/analysis/provenance-audit.json
python experiments/backup_pilot/method_report.py
python experiments/backup_pilot/clean_runtime.py
python experiments/backup_pilot/analyze.py --output analysis
```

Para inspección posterior y verificación del producto conservado:

```bash
python experiments/backup_pilot/inspect_deliveries.py
python experiments/backup_pilot/verify_product.py
```

El inventario no ejecuta las soluciones en el host ni decide automáticamente
cumplimiento semántico. La revisión manual queda en `analysis/manual-review`.
El verificador de producto exige el mismo hash y una revisión de fuente coincidente;
las observaciones de ingeniería están separadas de las 18 corridas. Reutiliza y
comprueba recibos terminados; no elimina marcas de interrupción para repetir tareas.

Los cuatro comandos rechazan una campaña incompleta antes de abrir sus resultados.
`audit.py` verifica los archivos congelados, comandos, prompts, recibos, inventarios,
hashes de logs/artefactos/streams, separación de IDs de sesión y orden temporal.
Comprueba que la revisión funcional recibió sólo el contrato y la solución, y
señala errores de proveedor incluso si coinciden con un timeout. Registra aparte
la inicialización del caso T y los tokens no informados como desconocidos.
Un exit code 1 requiere explicar las incidencias; no convierte un fallo de
infraestructura en un cero de calidad. El analizador comprueba el diseño factorial,
denominadores y puntuaciones, pero su exportación por sí sola no certifica la auditoría.
El analizador también rechaza errores de proveedor, flags de infraestructura y
fallos de proceso fuera de un timeout en cualquiera de las tres funciones de modelo.
Un timeout de presupuesto sin esos errores conserva su resultado funcional; un
error de API coincidente deja calidad desconocida e impide exportar la comparación.

El auditor y el analizador se desarrollaron después de congelar el protocolo,
con fixtures sintéticos y sin inspección de resultados antes del cierre de todas
las generaciones. No cambian las pruebas reservadas ni los presupuestos.
Los hashes acreditan consistencia local; no prueban identidad autenticada ni
custodia independiente. Para streams truncados se conserva y comprueba el prefijo;
el hash completo declarado no puede verificarse sin los bytes que faltan.
Las llamadas MCP registradas no prueban por sí solas cumplimiento semántico de
todas las fases. La selección del analizador debe verificarse en un Python limpio
antes de entregar el producto, conservando origen y hash del candidato.

`method_report.py` añade `analysis/method/method-report.json` con las doce
observaciones del brazo T. Lee cada ledger mediante el motor de la imagen congelada,
montando la entrega en solo lectura, sin red ni autenticación. Distingue revisiones
históricas, fases actualmente aceptadas, bloqueos y confianza local declarada.
Conserva el hash del motor/ledger y recibos del observador. Un ledger ausente,
alterado o ilegible deja una observación desconocida; no produce un cero de
calidad ni un supuesto cero de fases aceptadas. Los recibos cacheados deben
coincidir con los logs originales. Su coste es diagnóstico posterior, separado
del presupuesto de autor y revisor, y no implica una revisión semántica independiente.

La comprobación de entrega usa `Dockerfile.delivery` y `delivery_entry.py`.
El evaluador del piloto congelado ejecuta Python desde el entorno virtual del
toolkit; sus puntuaciones funcionales se conservan con ese entorno común para
todos los brazos. La comprobación adicional de entrega usa el Python genérico
de la imagen control, con `-E -s -S -B`, y omite paquetes instalados y PYTHONPATH.
Permite módulos propios de la solución y conserva PID y grupo del proceso con
`exec`, para mantener efectiva la interrupción real. Su evaluación es posterior
y no sustituye las puntuaciones congeladas del piloto.

Para construirla, etiquete el ID de `images.control` del manifiesto como
`specorganon-backup-control:delivery-base` y compruebe con `docker image inspect`
que el tag sigue apuntando a ese ID. Después:

```bash
docker build --build-arg BASE_IMAGE=specorganon-backup-control:delivery-base -f experiments/backup_pilot/Dockerfile.delivery -t specorganon-backup-delivery:dev .
```

Monte la carpeta de solución seleccionada en `/candidate` en solo lectura, sin
volumen de autenticación ni red. Use el mismo UID1000 del candidato, límites,
caps del controlador y tmpfs del evaluador. El argumento del evaluador debe ser
`--candidate /entry/backup.py`: ese launcher ejecuta `/candidate/backup.py` sin
paquetes del entorno. Compruebe V1/V2/V3, etapa dos, y conserve el SHA256 de la
fuente real, del launcher, del evaluador y de la imagen; el launcher no es la
implementación del producto. Los recibos `development/delivery-build.json` y
`development/delivery-clean-controls.json` documentan los comandos y controles
verificados. Los tres controles pasaron 22/22 con UID1000. Un control que importa
un paquete instalado fue rechazado en ese runtime, preservando su error y recibos.
Estos controles de desarrollo no son corridas del piloto ni el producto elegido.

El contexto Docker incluye únicamente los dos archivos necesarios del experimento
(evaluador y launcher); mantiene excluidos `runs`, fuentes del control y resultados.
La configuración anterior de `.dockerignore` se respaldó de forma privada antes
de ampliar esta lista permitida.

`planning/clean-runtime-addendum.json` registra esta comprobación después de la
congelación, con 14 etapas cerradas y sin inspección de resultados del piloto.
Se aplicará a las 36 entregas con sus variantes, etapas y semillas originales;
las puntuaciones principales y sus tiempos permanecerán intactos. Se conservarán
ausencias de producto, fallos de infraestructura y resultados inconclusos, con
la procedencia de cada fuente real y del observador. Es una comprobación exploratoria
adicional, no una nueva prerregistración del piloto. Deshabilitar paquetes instalados
no prueba por sí solo toda la política de dependencias: antes de entregar el producto
se revisarán imports, código incorporado y comandos externos.

`clean_runtime.py` comprueba el addendum y los hashes de la imagen, launcher y
evaluador antes de observar las 36 entregas. `analysis/clean-runtime` conserva
recibos, fuentes reales, exportaciones y streams. Una entrega ausente queda
marcada como tal, sin inventar una evaluación; los errores de infraestructura
dejan calidad desconocida. Las estadísticas muestran seis observaciones esperadas
por brazo/etapa y el denominador de las puntuaciones conocidas. Los resultados
cacheados deben corresponder a los logs, fuente y asignación originales; un
marcador interrumpido exige disposición explícita y no provoca una repetición
automática favorable. El coste de este observador permanece separado del piloto.

## Entrega y reproducción nueva

`delivery/backup-product.tar.gz` contiene el producto operativo y su documentación,
procedencia, pruebas y ejemplos. La implementación solo requiere `backup.py` y
Python 3.12 en Linux/Unix; puede utilizarse sin Codex ni el MCP.

`delivery/specorganon-backup-reproduction.tar.gz` conserva las fuentes del toolkit,
entradas de construcción Docker, harness y los insumos congelados de desarrollo.
`delivery/reproduction-manifest.json` registra hashes y la comprobación de extracción
y `docker compose config --quiet`. El paquete no incluye credenciales, perfiles de
cuenta, sesiones, resultados de participantes ni un freeze activo. El registro
original se guarda como `original-freeze-record.json`, con sus rutas absolutas e
imágenes históricas; sirve como evidencia, no como manifiesto de una campaña nueva.

Para una repetición independiente, extrae el paquete **en un directorio nuevo**
y entra en `SpecOrganon-reproduction`. Conserva el árbol original. No copies
`runs` ni `analysis` anteriores al nuevo experimento y no arranques dos campañas
con la misma carpeta de resultados. Esta preparación no crea cuenta o cuota:
la autenticación del volumen autorizado debe existir, o el dueño debe configurar
una sesión mediante el login oficial. No copies `auth.json` entre máquinas/perfiles.

Construye las imágenes y ejecuta controles, freeze, runner y análisis con los
comandos iniciales. La nueva congelación registrará las rutas e imágenes efectivas
de esa copia; nunca regeneres el freeze del resultado histórico. Puede reproducirse
la estructura experimental, pero no garantizar pesos del proveedor ni resultados
idénticos de autores estocásticos. No se ejecutó un segundo piloto para verificar
el paquete: se comprobaron sus fuentes extraídas y configuración Docker.

Los diagnósticos adicionales requieren sus recibos de construcción y registro de
runtime. En el host actual existen las imágenes verificadas por ID. Si construyes
otras imágenes en la copia nueva, registra su build y un addendum de cobertura
36 antes de abrir resultados, con los hashes de evaluador/launcher y la identidad
real; no presentes el addendum histórico como evidencia de esa construcción.
Los comandos rechazan un ID o hash distinto y no cambian las puntuaciones principales.
El producto conservado corresponde a esta campaña; una nueva selección debe tener
su propia procedencia, revisión de fuente y verificación de ingeniería.

El veredicto es acotado: señal funcional favorable al paquete T en esta serie,
documentación ausente y método incompleto. El GOAL.md original y el problema global
de `SourceAuditError`/digest de `pdftotext` permanecen fuera de este cierre local.
