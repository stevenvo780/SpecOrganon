# Segunda aplicación: disponibilidad de Citi Bike

**Corte de fuentes:** 2026-09-26 y 2026-09-27. **Periodos de datos cuantitativos:** informe de junio de 2026 y muestra histórica separada de marzo de 2024. **Estado:** expediente documental de junio y expediente hermano retrospectivo de marzo, ejecutados con el mismo motor. La muestra histórica no se añadió al ledger de junio. No se capturó una serie GBFS propia, no hubo intervención ni trabajo de campo, y no se midió ningún viaje frustrado.

## Fuentes y unidad de observación

La fuente cuantitativa es el [informe mensual oficial de junio de 2026](https://mot-marketing-whitelabel-prod.s3.us-east-1.amazonaws.com/nyc/June-2026-Citi-Bike-Monthly-Report.pdf), entregado por el operador a NYC DOT. El PDF de ocho páginas descargado el 2026-09-26 dio SHA-256 `9c09c95c44cf8311c4003e4c1e5eb100e2135164c5a6c1de48a2782538a6ad2e`. Sus agregados describen la **red durante ese mes**. No localizan el problema en una estación ni identifican personas que intentaron iniciar o devolver un viaje sin éxito.

| Hecho publicado | Magnitud | Uso permitido en este caso |
| --- | ---: | --- |
| Viajes completados, p. 3 | 5.494.600 | Tamaño de la operación, no demanda frustrada ni efecto de redistribución. |
| Estaciones activas al fin de mes, pp. 3–4 | 2.400 | Tamaño de la red al cierre, no número de estaciones con bicicleta o anclaje en cada minuto. |
| Bicicletas redistribuidas según el operador, p. 3 | 101.757 | Actividad operacional reportada. El mismo total aparece en la introducción como acciones de bicicleta/anclaje; no se desagrega aquí ni se interpreta como bicicletas únicas o impacto. |
| Uptime de estaciones, p. 4 | 99,79 % | Operatividad reportada, sin serie de capacidad disponible por estación en el informe. |
| SLA 9, p. 7 | 108,97 % del nivel de flota requerido | Promedio mensual de una medición diaria entre 11:00 y 15:00. Es una **razón frente a un objetivo de flota**, no la probabilidad de encontrar bicicleta ni un porcentaje de estaciones accesibles. |

La [página oficial de datos](https://citibikenyc.com/system-data) enlaza el feed GBFS actual y explica que los historiales de viajes excluyen viajes de personal, de estaciones de prueba y menores de 60 segundos. Un registro de viajes completados tampoco registra la demanda que nunca produjo un viaje. La [especificación GBFS v2.3](https://github.com/MobilityData/gbfs/blob/v2.3/gbfs.md) define `station_status.json` para disponibilidad y estados de alquiler/devolución; está diseñada para estado presente y no para historia. Por eso el feed consultado ahora no recupera junio de 2026. No se ha encontrado ni incorporado un archivo de estados por estación correspondiente a ese mes. La [política oficial de uso](https://citibikenyc.com/data-sharing-policy) rige los datos; este repositorio contiene referencias y agregados del informe, no una copia de un feed o historial bruto.

### Muestra histórica de estados, separada del caso de junio

El [repositorio de la oficina del contralor de Nueva York](https://github.com/NYCComptroller/citi-bike-gbfs/tree/4c36513cf3842efe9a2940a78974bf45cb13fc0b) ofrece en su rama `sample-data` una muestra de estados de marzo de 2024 y código para construir indicadores. Se fijó ese commit y el SHA-256 `661221e1f6fc01ba6475cee61597e432fc0858689195b6c12255a6c005b52fc4` del archivo `dataset.parquet` (10.853.196 bytes); el archivo bruto se mantuvo fuera del repositorio. El [script de análisis](../cases/citibike/analyze_sample_status.py) y su [salida](../experiments/development/citibike_sample_status_2026-09-27.json) permiten reproducir el cálculo sobre una copia local de esos bytes:

```sh
uv run --no-project --with 'pyarrow==21.0.0' --with 'tzdata==2026.4' python cases/citibike/analyze_sample_status.py /ruta/local/dataset.parquet
```

La muestra contiene **1.812.548 filas estación-instantánea**, 820 instantes y 2.212 IDs de estación entre el 12 y el 23 de marzo de 2024. No hay pares estación-instante repetidos. La separación de capturas es irregular: 37 intervalos superan 30 minutos y el mayor dura 3.719 segundos. Los indicadores archivados `is_renting` e `is_returning` son enteros 0/1; esa observación del Parquet procesado no establece que el feed GBFS vivo cumpla la especificación. Un control conservador excluyó 3.512 filas donde la suma de bicicletas y anclajes disponibles excedía la capacidad declarada; 606 de ellas también tenían más bicicletas que capacidad. Entre las **1.809.036 filas restantes**, 1.725.248 (fracción 0,953684) declaraban alquiler habilitado y alguna bicicleta, y 1.682.386 (0,929990) devolución habilitada y algún anclaje. Se trata de **fracciones de filas observadas**, sin ponderación por tiempo ni inferencia a estación-minutos.

Esta muestra es de 2024 y no se combina con los agregados de junio de 2026. No contiene `last_reported` por estación ni intentos de viaje fallidos; las capturas irregulares impiden afirmar cobertura continua y ninguna cifra mide el efecto de una intervención. El análisis aporta una comprobación empírica de la separación alquiler/devolución en el segundo dominio, pero no repara el protocolo `pr_panel` obsoleto ni cambia el veredicto de generalización. Solo se conservan agregados y referencias, de acuerdo con la [política de datos del operador](https://citibikenyc.com/data-sharing-policy).

La muestra tiene ahora su [propio expediente ejecutado](../cases/citibike_march2024/README.md), separado del de junio. Sus 22 ítems enlazan los conteos derivados a la fuente y al protocolo **retrospectivo**, y el [registro de desarrollo](../experiments/development/citibike_march_ledger_2026-09-27.json) fija hashes, trazas y compuertas. Una revisión de agente aceptó solo `frame` (eventos 23–24); `critique` sigue bloqueada por la norma sin aprobación humana. El expediente no convierte la muestra en una reserva ciega ni en prueba de acceso efectivo o generalización completa.

Un [sondeo puntual de calidad](../experiments/development/citibike_gbfs_probe_2026-09-26.json) del 26-09-2026 entre 15:11:06 y 15:11:08 UTC leyó el índice oficial y los archivos de información y estado sin credenciales. Declaraban GBFS 2.3 y 2.520 estaciones cada uno, sin IDs repetidos ni faltantes entre ambos. Sin embargo, los 2.520 valores de **cada** campo `is_installed`, `is_renting` e `is_returning` fallaron la comprobación de booleano JSON exigida por [GBFS 2.3](https://github.com/MobilityData/gbfs/blob/v2.3/gbfs.md); no se conservó el tipo exacto de esos valores. Una comprobación cruda marcó 91 `last_reported` con más de cinco minutos, incluidos posibles sentinelas. Se descartaron los conteos de disponibilidad: ninguna conversión de esos indicadores estaba predefinida. Las tres respuestas se identifican por SHA-256 en el registro, pero no se retuvieron sus bytes y el feed cambia; este sondeo no es reproducible byte por byte ni una serie temporal. La [política de datos](https://citibikenyc.com/data-sharing-policy) limita la extracción automatizada y la redistribución independiente; el sondeo no autoriza un programa de captura recurrente.

## Problema, alternativas y diseño pendiente

La pregunta material es cómo reducir minutos en que una estación no permite iniciar o devolver un viaje. El servicio para iniciar requiere alquiler habilitado y al menos una bicicleta utilizable; el servicio para devolver requiere devolución habilitada y un anclaje apto. Esas dos medidas deben registrarse por separado, con cobertura y frescura del feed. Incluso una estación sin bicicleta en una instantánea **no prueba** que alguien haya querido alquilar en ese momento.

El expediente distingue a usuarios, operador, personal, gobierno local, peatones y vecinos. El compromiso propuesto de no desplazar indisponibilidad o riesgos entre zonas y grupos (`n_fair_access`) es una decisión normativa **sin aprobación humana**. Compara como opciones de estudio la redistribución focalizada y la información de alternativas cercanas. Ambas podrían desplazar cargas; el informe mensual no permite preferir una por efecto causal, coste o equidad. La decisión `d_candidate` y el requisito `req_archive` son **borradores no vinculantes**, y actualmente obsoletos tras la revisión descrita abajo.

Para un estudio prospectivo harían falta estaciones y franjas fijadas antes de observar el resultado; capturas GBFS con `last_updated`, `last_reported`, identidad de estación, estados de alquiler/devolución, bicicletas y anclajes; reglas de faltantes; costes y desplazamiento entre estaciones; y un comparador apropiado. Además haría falta medir intentos frustrados con un mecanismo distinto del conteo de viajes completados. El protocolo `pr_panel` es una propuesta, no un estudio ejecutado. No hay línea base de estación-minutos de junio, umbral de éxito aprobado ni resultado de intervención.

## Ejecución del toolkit y control de revisión

[`cases/citibike/seed.json`](../cases/citibike/seed.json) carga 30 artefactos en [`cases/citibike/organon.json`](../cases/citibike/organon.json), usando `scripts/seed_case.py` y las mismas clases de ítem, referencias, compuertas, trazas y ledger que el caso alimentario. Son artefactos de encuadre y candidatos hasta `specify`; no hay artefactos `build` ni `validate`. Ninguna norma o decisión recibió aprobación. El registro tiene 33 eventos: 30 cargas iniciales, una revisión de supuesto y la revisión histórica y avance de `frame` en los eventos 32 y 33, por `agent:case_reviewer`.

El supuesto `s_proxy` versión 1 dejaba **por comprobar** si el SLA agregado de flota podía servir como aproximación del acceso por estación. Tras confrontarlo con la definición de SLA 9 y GBFS, la versión 2 registra que no puede hacerlo. La edición en el evento 31 dejó 12 descendientes obsoletos, incluidos el protocolo `pr_panel`, la decisión candidata `d_candidate` y el requisito candidato `req_archive`; la [salida generada de verificación](../cases/citibike/revision_check.json) enumera los IDs y compuertas **tal como estaban inmediatamente después del evento 31**, antes de la revisión de `frame`. No se revalidaron esos borradores contra el supuesto corregido. Así queda observable la propagación hasta un requisito sin fingir que se aceptó la fase `specify`.

Una [regresión ejecutable sin red](../experiments/development/citibike_transfer_replay_2026-09-26.json) siembra los 30 ítems en un directorio temporal, reproduce por la CLI instalada el `item_put` exacto del evento 31 y comprueba que `req_archive` traza hasta `s_proxy` v2. Verifica los 12 obsoletos, la revisión y avance de `frame`, el bloqueo de `critique` y `specify`, y el rechazo sin mutación de una aprobación carente de firma bajo política `signed`. Su versión vigente usa una firma de revisor con clave efímera en esa copia temporal; el recibo enlazado corresponde al corte anterior sin firma de fase. La prueba conserva los bytes del ledger fuente. `revision_check.json` es una fotografía histórica: las frases de sus bloqueadores de aprobación difieren de las del motor actual y las comprobaciones actuales añaden bloqueadores de traza. La regresión compara IDs, obsolescencia y estados de compuertas, no esas frases literales.

Comprobaciones ejecutadas con la CLI:

```sh
python3 -m json.tool cases/citibike/seed.json >/dev/null
uv run organon gate cases/citibike frame
uv run organon gate cases/citibike critique
uv run organon gate cases/citibike specify
uv run organon trace cases/citibike req_archive
```

El resultado actual conserva `frame.ready=true`, la revisión histórica en el evento 32 y el avance en el 33. La revisión no tiene firma: `review_provenance=legacy_unverified` y `frame.accepted=false` bajo la compuerta vigente. El `true` que se informó antes dependía de etiquetas de autor y revisor distintas; no acredita identidad o evaluación independiente. `critique.ready=false` por falta de aprobación humana de `n_fair_access`. `specify.ready=false` muestra `d_candidate` y `req_archive` dependientes de una versión antigua, falta de criterio, falta de aprobación de decisión y la cadena anterior sin aceptar. Se verificaron 30 ítems, 33 eventos, 12 ítems obsoletos, 0 aprobaciones de normas o decisiones y 1 revisión histórica de fase. Esas cifras son del ledger local, no una medición del servicio Citi Bike.

Para reproducir la carga inicial en un directorio nuevo:

```sh
case_dir=$(mktemp -d)
uv run python scripts/seed_case.py cases/citibike/seed.json "$case_dir"
uv run organon gate "$case_dir" frame
```

El ledger incluido conserva también la revisión posterior de `s_proxy` para inspeccionar el efecto con `trace` y `gate`. La afirmación comprobada es limitada: el motor reutiliza tipos, compuertas y propagación de versiones en un dominio de movilidad. La disponibilidad real por estación, la comparación causal de opciones y la resolución efectiva del problema quedan **no demostradas**.
