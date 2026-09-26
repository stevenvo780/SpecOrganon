# Metodología operativa de SpecOrganon

**Estado:** versión de trabajo sometida a las pruebas de [GOAL.md](../GOAL.md). La comparación de prototipos solo respalda provisionalmente el grafo de dependencias; no demuestra todavía superioridad frente a SDD o trabajo libre. Este texto describe cómo operar el método y dónde debe detenerse.

## Unidad de trabajo y reglas de conocimiento

Un caso es una intervención posible en un sistema real delimitado. Su unidad no es un documento de software: incluye actores, procesos materiales, entradas, salidas, efectos y decisiones de valor. Un artefacto del caso tiene `id`, tipo, texto, versión, autor, datos estructurados y referencias a **versiones concretas** de otros artefactos. Cada cambio añade un evento al ledger. Una referencia a una versión antigua marca al descendiente como obsoleto hasta que se revise; también reabre las compuertas que dependían de él.

Al registrar una afirmación se indica si es problema formulado, compromiso normativo, hipótesis, dato publicado, observación propia, cálculo derivado, simulación o inferencia. Para evidencia se exige fuente, fecha y localizador; para observación propia también método. El sistema verifica esos campos y cálculos de producto declarados, pero **no verifica que una fuente diga lo afirmado**, que una medición sea representativa o que el actor declarado sea quien dice ser. Eso requiere revisión independiente y, cuando importe, autenticación externa.

El trabajo puede avanzar por ramas: un agente puede investigar una pregunta o esbozar opciones mientras se revisa otra. Los artefactos pueden añadirse fuera del orden de fases. La aceptación de una fase necesita sus propias condiciones y la aceptación vigente de la anterior; esto impide publicar como justificado un resultado cuya base sigue abierta. La exploración anticipada no confiere autorización para desplegar ni convierte un borrador en evidencia.

En un caso real, `approval_policy="signed"` es la política inicial y el ledger recibe un `case_id` UUID. El operador registra fuera del ledger el UUID, la ruta canónica, el digest de los metadatos del caso y la clave pública de `human:<nombre>` en `ORGANON_APPROVERS_FILE`. Una norma o decisión se aprueba mediante el desafío canónico `approval-challenge`: la persona examina el contenido y firma offline los bytes decodificados de `message_base64` con su clave Ed25519; `approve --signature` verifica la firma contra ese registro externo. El mensaje firmado vincula caso y ruta, metadatos, cabeza previa del ledger, ítem, versión, hash de contenido, actor y motivo. Si el archivo de confianza falta, se retira la clave, cambia el caso o se copia su ledger a otra ruta, una aprobación previa queda no verificada al releer el ledger y no satisface la compuerta. La firma acredita control de una clave configurada; identificar a su custodio, validar su competencia y conservar la decisión humana son tareas externas. Ninguna clave privada entra en el repositorio, comandos o logs. La política `fixture` se solicita explícitamente solo para pruebas sintéticas en rutas no registradas, con `ORGANON_ALLOW_FIXTURES=1`; admite únicamente `human:fixture`, sin autorización real. Sin esa variable, la fixture se puede leer pero no pasar compuertas mediante sus aprobaciones.

La cadena de hashes del ledger no es una garantía append-only ante escritura directa: se pueden eliminar eventos posteriores a una aprobación válida o añadir revisiones y avances falsos y recalcular la cadena. La firma protege la aprobación y el prefijo anterior, pero no autentica revisores: sus etiquetas de actor son autodeclaradas. El verificador opcional `ORGANON_LEDGER_ANCHORS_FILE` exige que UUID, ruta, metadatos, secuencia y cabeza coincidan con un registro externo en cada lectura; una alteración local coherente queda bloqueada mientras el ancla permanezca íntegra y vigente. Tras cada evento legítimo, el expediente queda temporalmente por delante del ancla y las lecturas siguientes se detienen hasta que un custodio independiente compruebe la transición y publique una cabeza nueva. No se debe actualizar el ancla automáticamente con el ledger: eso bendeciría una falsificación. Producción requiere esa custodia y comprobación por transición, o almacenamiento append-only independiente. Ni el ancla ni la firma autentican por sí solas a los revisores o demuestran autoridad humana.

## Ciclo por frentes y fase final

| Frente / fase ejecutable | Entrada y resultado mínimo | Compuerta, revisión y detención |
| --- | --- | --- |
| Filosofía `frame` | Encargo → problema, actor y frontera. | Revisar exclusiones y formulaciones rivales; detener si la unidad o afectados decisivos no están delimitados. |
| Filosofía `critique` | Formulación → concepto, supuesto, dos encuadres rivales y compromiso normativo. | Distinguir realidad de deseabilidad y justificar el compromiso; exigir aprobación humana registrada para la norma. Detener ante conflicto de valor sin decisión. |
| Ciencia `study` | Preguntas → pregunta, hipótesis, protocolo e indicador. | El protocolo nombra población, método, comparación e incertidumbre; el indicador enlaza problema y norma. Detener si no se puede investigar éticamente o separar dato de supuesto. |
| Ciencia `observe` | Protocolo → evidencia con procedencia e inferencia enlazada. | Contrastar datos, detectar inconsistencia cuantitativa o contradicción declarada. Detener ante fuente insuficiente o incongruencia sin resolver. |
| Ciencia `explain` | Evidencias e inferencias → síntesis y límites de incertidumbre. | Revisar hipótesis rivales y condiciones materiales. Una síntesis que excede sus datos no pasa. |
| Ingeniería `compare` | Síntesis y valores → al menos dos opciones, comparación y riesgo. | Incluir cambios de proceso, organización o infraestructura además de software cuando corresponda. Revisar costes y daños desplazados; detener si solo se desarrolló la primera idea. |
| Ingeniería SDD `specify` | Comparación → decisión, requisito y criterio de aceptación. | Cada requisito y criterio debe tener camino a problema, norma y evidencia. Una decisión que fija un intercambio de valor exige aprobación humana; el criterio precede al resultado. |
| Ingeniería SDD `build` | Requisitos → implementación y prueba ejecutada documentada. | Revisar factibilidad y seguridad material. Una prueba registrada como fallida detiene; el registro de comando requiere inspección externa del resultado y no es garantía automática. |
| Validación `validate` | Criterios previos, línea base y resultado → evaluación con incertidumbre, costes y daños. | Separar resultado técnico, simulado y observado; comparar con línea base y diseño causal. Sin campo suficiente, declarar `no_demostrado` para eficacia real. Detener ante daño crítico. |

Cada fase tiene contrato detallado en [`workflow.py`](../src/specorganon/workflow.py). `gate` muestra bloqueos sin cambiar el estado; `review-phase` fija un juicio sobre la instantánea actual; `advance` registra aceptación solo si la revisión y el gate siguen vigentes. Un cambio de evidencia o de supuesto puede invalidar el resultado de `advance`, aunque el evento histórico siga visible. La revisión puede ser propia para una exploración individual, pero `independent_review` lo distingue; las comparaciones finales requieren jueces externos.

## Retorno, contradicción y decisión

La relación básica es `problema → norma/hipótesis → evidencia → síntesis → opción → decisión → requisito → implementación → resultado`. Un nodo puede tener varias entradas y varias salidas; el grafo no presupone una cadena lineal de materiales ni que una solución sea software. `trace` devuelve antecesores y descendientes para auditar una decisión.

Ante una fuente que contradice otra, un cálculo incoherente o una premisa que cambia:

1. Registrar la contradicción con `challenge` o una nueva versión de la evidencia. Los valores incompatibles de un mismo indicador, unidad y alcance se señalan automáticamente. La fase y los descendientes afectados quedan bloqueados u obsoletos.
2. Investigar la discrepancia: unidades, denominadores, población, fecha, método, sesgo y fuentes alternativas. Una nueva síntesis no puede borrar la observación original del historial.
3. Para cerrar una contradicción declarada, crear una síntesis o evaluación posterior que enlace ambos lados y obtener revisión de un actor distinto al autor. Solo entonces `resolve-challenge` cierra la objeción; los descendientes obsoletos deben revisarse y aceptarse de nuevo.
4. Si la discrepancia cambia una preferencia o reparte perjuicios, devolver la decisión a la persona competente. El actor `human:<nombre>` por sí solo no identifica a nadie: en casos reales se exige la firma verificable de la revisión exacta y un registro externo que vincule clave, persona y autoridad. Ningún agente debe fabricar ese consentimiento.

La revisión no se repite indefinidamente: antes de cada caso se fija un presupuesto de tiempo, consultas y coste; cuando se agota, se entrega un veredicto parcial con incertidumbre y pendientes. Un hallazgo adverso se conserva, no se reejecuta hasta obtener uno favorable. La selección del método y la validación confirmatoria siguen el [protocolo predefinido](protocolo_experimental.md).

## Medición de una cadena alimentaria

Para cada lote o flujo, registrar identificador, origen, transformación, destino, período, unidad, masa de entrada, ingredientes y agua añadidos, productos principales, coproductos, merma, humedad, incertidumbre y actor que soporta cada coste. Comprobar el balance con tolerancias de medición antes de atribuir una desaparición a desperdicio. Cáscara, hueso, pulpa, agua evaporada y fruta no inocua tienen destinos y valores distintos; la reducción de masa en transformación no equivale a pérdida de servicio.

Medir separadamente servicio alimentario inocuo efectivamente consumido, calidad, nutrientes, ingresos/costes netos por actor, trabajo, seguridad, energía, agua, emisiones y residuos. Un índice agregado solo puede construirse con equivalencias y pesos aprobados por las personas afectadas antes del ensayo. Mantener el vector desagregado para detectar beneficios globales que desplazan daños. El indicador `V` y el diseño de campo propuestos están en el protocolo; sin aprobación de equivalencias, datos a consumo y comparador causal, la resolución efectiva no está demostrada.

## Qué prueba cada clase de resultado

- **Funcionamiento técnico:** instalación limpia, comandos y MCP real producen y reabren los estados esperados; no prueba verdad empírica.
- **Simulación:** muestra consecuencias bajo un modelo, parámetros y sensibilidad declarados; necesita validación retrospectiva y no prueba impacto de campo.
- **Campo:** compara grupos o un diseño causal defendible con línea base, mide también daños y costes y reporta incertidumbre. Solo esto puede sustentar una afirmación de mejora material en la población estudiada.
- **Aporte del método:** comparación pareada dentro de cada modelo frente a trabajo libre y SDD, con réplicas, ablaciones, evaluación independiente, tiempo, tokens y coste. Una sola ejecución favorable no basta.
