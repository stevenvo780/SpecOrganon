# Registered fractionmix software cell

Desarrollo local con autores y mandato declarados.

Revisión del expediente: 52. Fases aceptadas: 9/9.

## Siguiente trabajo

Todas las fases tienen avance vigente\.

## Recorrido

| Frente | Fase | Estado |
| --- | --- | --- |
| philosophy | frame | aceptada |
| philosophy | critique | aceptada |
| science | study | aceptada |
| science | observe | aceptada |
| science | explain | aceptada |
| engineering | compare | aceptada |
| engineering | specify | aceptada |
| engineering | build | aceptada |
| validation | validate | aceptada |

## Artefactos y trazabilidad

### p1 · problem · v1

El encargo requiere una utilidad FractionMix reproducible que sume racionales exactamente y devuelva una fracción canónica bajo una interfaz estricta\. La necesidad técnica es preservar exactitud y distinguir entradas válidas de errores contractuales, incluidos resultados mayores que el límite decimal predeterminado de CPython\. contract\.md define esa necesidad; no aporta mediciones de fallos existentes ni evidencia de daño en personas\. Una formulación rival sería resolver sumas puntuales manualmente: puede cubrir ejemplos aislados, pero no entrega la interfaz automatizada exigida\. Otra sería estudiar superioridad general de métodos; excede la evidencia y el alcance de esta celda\.

Autor: agent:codex\-isolated\-author.

```json
{
  "sources": [
    "contract.md: Propósito y entrega; Entrada y validación; Cálculo y resultado",
    "existing-mandate.md"
  ]
}
```

### a1 · actor · v1

El actor afectado identificado es el operador que encargó proyectos pequeños autónomos y reproducibles: necesita una entrega cuya corrección y límites puedan examinarse\. El mandato existente delega las decisiones técnicas locales dentro del contrato y exige conservar fallos y artefactos parciales\. La etiqueta human:owner registra ese mandato local, sin autenticar identidad o custodia\. Los autores y evaluadores cumplen funciones técnicas de construcción y comprobación; no se presupone una población de usuarios de campo ni preferencias personales del operador sobre soluciones aún no propuestas\.

Autor: agent:codex\-isolated\-author.

Depende de: p1 v1.

```json
{
  "sources": [
    "existing-mandate.md",
    "state.json: project.created_by; approval_identity_authenticated",
    "contract.md: Documentación, pruebas y alcance"
  ]
}
```

### b1 · boundary · v1

La frontera es una utilidad técnica Python 3\.12 con biblioteca estándar, entrada exclusivamente por stdin y salida contractual, sobre entradas sintéticas finitas\. Incluye validación JSON estricta, máximo 65536 bytes y 1000 términos, límites de enteros de entrada, suma exacta, reducción, cero canónico y conteo sin deduplicación; los resultados no heredan los límites individuales de entrada\. La observación futura se limita a comportamiento ejecutable, documentación y pruebas aisladas bajo los recursos del contrato: 3 segundos, 2 CPU, 1 GiB, 128 procesos y streams de hasta 2 MiB\. Las 84 recetas son una matriz candidata documentada, no mediciones disponibles ni cobertura universal\. Se excluyen utilidad en personas, superioridad general, cambios de cuentas, credenciales, servicios o límites, y reparaciones basadas en feedback reservado\. El contrato y la matriz siguen siendo candidatos; no hay implementación ni registros de pruebas suministrados\.

Autor: agent:codex\-isolated\-author.

Depende de: a1 v1, p1 v1.

```json
{
  "sources": [
    "contract.md",
    "existing-mandate.md",
    "delivery-files.json",
    "measured-test-records.json"
  ]
}
```

### c1 · concept · v1

Corrección contractual significa validar toda la entrada y producir la suma racional exacta en forma canónica, o el error especificado\. Incluye interfaz, límites y recursos; acertar los dos ejemplos no basta\. Es distinta de cobertura experimental: una matriz finita puede detectar defectos, pero no demostrar corrección universal\. Tampoco equivale a utilidad para personas\. Esta distinción evita definir éxito como aquello que una implementación concreta consiga ejecutar\.

Autor: agent:codex\-isolated\-author.

Depende de: b1 v1, p1 v1.

```json
{
  "sources": [
    "contract.md"
  ]
}
```

### s1 · assumption · v1

Se adopta como supuesto de trabajo que el contrato candidato permite orientar una construcción técnica reproducible\. Su interfaz está descrita, pero las 84 recetas no se suministran aquí y no hay implementación ni mediciones\. Por ello no se supone cobertura suficiente, viabilidad bajo los recursos ni ausencia de defectos\. Si aparecen contradicciones contractuales, deberán explicitarse antes de convertirlas en criterios; no reducir el dominio para acomodar una solución\.

Autor: agent:codex\-isolated\-author.

Depende de: b1 v1, c1 v1, p1 v1.

```json
{
  "sources": [
    "contract.md",
    "delivery-files.json",
    "measured-test-records.json"
  ]
}
```

### f1 · frame\_option · v1

Encuadrar el encargo como construcción de una utilidad automatizada de suma exacta con validación estricta\. La exactitud y el rechazo completo de entradas inválidas tienen prioridad sobre tolerancia o comodidad, conforme al contrato\. Esta alternativa permite entregar la interfaz requerida, pero exige justificar aritmética, serialización de enteros grandes y manejo de errores; su coste y comportamiento bajo límites aún no están medidos\. La posible utilidad se restringe al objetivo técnico delegado\.

Autor: agent:codex\-isolated\-author.

Depende de: a1 v1, b1 v1, c1 v1, p1 v1, s1 v1.

```json
{
  "sources": [
    "contract.md",
    "existing-mandate.md"
  ]
}
```

### f2 · frame\_option · v1

Alternativa sin software nuevo: resolver sumas puntuales mediante cálculo racional manual y documentar reducción y conteo\. Puede explicar los ejemplos públicos y evita construir un ejecutable, aunque sigue expuesta a errores humanos\. Cambia el fin hacia demostración documental: no proporciona la interfaz stdin ni validación automatizada del dominio completo y, por tanto, no satisface la entrega solicitada\. Es una alternativa sustantiva para ejemplos aislados, no un sustituto equivalente del encargo\.

Autor: agent:codex\-isolated\-author.

Depende de: a1 v1, b1 v1, c1 v1, p1 v1, s1 v1.

```json
{
  "sources": [
    "contract.md: Propósito y entrega; Dos ejemplos públicos",
    "existing-mandate.md"
  ]
}
```

### n1 · norm · v1

Dentro del mandato técnico delegado, orientar FractionMix hacia f1: preservar exactitud, trazabilidad y documentación útil, tratando cada entrada inválida como error completo\. La razón normativa es cumplir la interfaz reproducible solicitada; f2 sirve a otro fin y no la entrega\. La tensión entre tolerancia y rigor se resuelve por la validación estricta del contrato, no por una preferencia personal atribuida al operador\. Esta orientación no acredita viabilidad ni beneficios de campo\. Conservar fallos, no usar feedback reservado para reparar y detenerse ante un nuevo conflicto de valor fuera del mandato\.

Autor: agent:codex\-isolated\-author.

Depende de: a1 v1, b1 v1, c1 v1, f1 v1, f2 v1, p1 v1, s1 v1.

Aprobación vigente: sí.

```json
{
  "sources": [
    "existing-mandate.md",
    "contract.md"
  ]
}
```

### q1 · question · v1

¿En qué casos de una matriz sintética fijada antes de generar FractionMix coincide su comportamiento con el contrato, incluidos validación completa, suma exacta, serialización y recursos? La pregunta distingue conformidad en casos finitos de corrección universal y utilidad humana\.

Autor: agent:codex\-isolated\-author.

Depende de: c1 v1, n1 v1, p1 v1, s1 v1.

```json
{
  "sources": [
    "contract.md"
  ]
}
```

### h1 · hypothesis · v1

Hipótesis prospectiva: la entrega producirá el comportamiento contractual en cada caso de la matriz fijada\. Un caso discordante refuta esta hipótesis para esa matriz\. La falta de recetas, entrega o registros deja la hipótesis sin demostrar; los dos ejemplos no establecen cobertura suficiente\.

Autor: agent:codex\-isolated\-author.

Depende de: c1 v1, p1 v1, q1 v1, s1 v1.

```json
{
  "sources": [
    "contract.md"
  ]
}
```

### pr1 · protocol · v1

Diseño prospectivo, sin ejecución\. Antes de generar, fijar contrato, recetas, identificadores y salidas esperadas; después del cierre, conservar entrega y todos los registros\. Las recetas no están suministradas: su ausencia impide aplicar este protocolo\. No repetir fallos hasta obtener éxito ni reparar con feedback reservado\. Evaluar interfaz, entradas inválidas y válidas, aritmética, enteros grandes y recursos; registrar omisiones como ausencia de evidencia\. No intervienen personas ni se infieren beneficios de campo\.

Autor: agent:codex\-isolated\-author.

Depende de: h1 v1, n1 v1, p1 v1, q1 v1, s1 v1.

```json
{
  "comparison": "Comparar cada registro con un oráculo independiente de aritmética entera y validación contractual. Para inválidos: exit 2, stdout vacío y stderr exacto. Para válidos: suma reducida, conteo, formato, exit 0 y stderr vacío. El cálculo manual explica ejemplos, pero no sustituye la interfaz ni aporta un comparador medido.",
  "method": "Futuro ensayo aislado por caso con Python 3.12: capturar entrada, salida, stderr, exit y fallos de ejecución; 3 s, 2 CPU, 1 GiB, 128 procesos, streams de 2 MiB, entrega readonly y sin red. Conservar registros y versiones; separar error contractual de timeout, OOM o crash.",
  "population": "Los 84 casos candidatos descritos en contract.md, incluidos dos ejemplos públicos y 82 entradas reservadas; recetas pendientes de examen y fijación.",
  "uncertainty": "Una matriz finita no demuestra corrección universal. Duplicación de ejemplos, selección de casos y errores compartidos con el oráculo pueden sesgar la evaluación; examinar recetas y contrastar expectativas con derivaciones independientes. Informar discordancias y casos sin registro por separado; no imputar valores ni intervalos poblacionales."
}
```

### e1 · evidence · v1

Evidencia documental: el contrato suministrado exige coincidencia exacta con reglas de entrada, resultado, error y recursos, y describe una matriz candidata de 84 recetas\. Fundamenta qué contar, sin proporcionar recetas ni observaciones\. La fecha identifica la copia suministrada en este contexto, no una publicación fechada\. No contiene medición de conformidad\.

Autor: agent:codex\-isolated\-author.

Depende de: n1 v1, p1 v1, pr1 v1.

```json
{
  "date": "2026-10-05",
  "locator": "contract.md: Entrada y validación; Cálculo y resultado; Documentación, pruebas y alcance",
  "origin": "published",
  "source": "contract.md, documento candidato suministrado"
}
```

### i1 · indicator · v1

Indicador prospectivo: casos con conformidad integral divididos por casos de la matriz fijada\. Un caso sólo contribuye al numerador con registro completo y coincidencia en todas las condiciones aplicables; conservar separadamente discordancias y casos sin evidencia\. Informar numerador, denominador e identificadores, sin asignar ahora ningún valor\. El indicador responde a exactitud y trazabilidad de n1; e1 fundamenta su definición contractual, no una medición\. Si cambia la matriz candidata, reconsiderar el protocolo y esta definición antes de medir\.

Autor: agent:codex\-isolated\-author.

Depende de: e1 v1, n1 v1, p1 v1, pr1 v1.

```json
{
  "metric": "proporcion_casos_conformes",
  "scope": "Sólo la matriz sintética fijada y la versión de entrega examinada; sin extrapolación a usuarios ni a todas las entradas posibles.",
  "sources": [
    "contract.md"
  ],
  "unit": "proporción"
}
```

### inf1 · inference · v1

De e1 se infiere que la conformidad debe abarcar validación, suma exacta, formato, error y recursos: los ejemplos aislados no bastan para responder q1\. Esta conclusión es documental, no una observación del comportamiento de FractionMix\. El protocolo pr1 requiere recetas fijadas, entrega y registros por caso; las recetas no están suministradas y delivery\-files\.json y measured\-test\-records\.json contienen mapas vacíos\. Por tanto, con estas fuentes no se puede calcular i1 ni confirmar o refutar h1\. La ausencia de registros tampoco demuestra incumplimiento\. La alternativa de cálculo manual f2 puede explicar ejemplos, pero no aporta evidencia sobre la interfaz ejecutable\. Se detiene aquí la inferencia empírica por datos insuficientes; quedan sin demostrar cobertura, comportamiento bajo recursos y corrección de una implementación\. No se identifican contradicciones entre las reglas documentales y el diseño prospectivo, pero faltan recetas para examinar su correspondencia con el contrato\.

Autor: agent:codex\-isolated\-author.

Depende de: e1 v1, f2 v1, h1 v1, i1 v1, p1 v1, pr1 v1, q1 v1.

```json
{
  "scope": "Conclusión documental sobre la evidencia suministrada; sin mediciones ni extrapolación.",
  "sources": [
    "contract.md",
    "delivery-files.json",
    "measured-test-records.json"
  ]
}
```

### syn1 · synthesis · v1

```text
Hallazgos documentales: e1 describe las reglas de validación, suma exacta, salida, error y recursos de FractionMix y una matriz candidata de 84 recetas; no contiene mediciones. delivery-files.json y measured-test-records.json son mapas vacíos, y las recetas no se suministran. Como establece inf1, no es posible calcular i1 ni confirmar o refutar h1 con estas fuentes. La ausencia de registros no demuestra incumplimiento.
Supuesto de trabajo: s1 permite orientar una construcción por el contrato candidato, sin dar por demostradas su viabilidad ni la cobertura de la matriz. pr1 describe un ensayo futuro, no una ejecución.
Alternativas: f1 responde a la interfaz automatizada solicitada; f2 permite explicar sumas aisladas mediante cálculo manual, pero no proporciona esa interfaz ni evidencia sobre su comportamiento. Los ejemplos correctos del documento son especificaciones, no resultados de una implementación. La falta de datos es compatible tanto con una futura entrega conforme como con una defectuosa; no discrimina entre ellas.
Límite: la conclusión es documental. No establece corrección ejecutable, rendimiento, superioridad entre métodos ni utilidad humana. La selección de casos, los ejemplos repetidos y posibles errores compartidos del oráculo deben examinarse antes de interpretar mediciones.
```

Autor: agent:codex\-isolated\-author.

Depende de: e1 v1, f1 v1, f2 v1, h1 v1, i1 v1, inf1 v1, p1 v1, pr1 v1, s1 v1.

```json
{
  "scope": "Síntesis documental de las fuentes suministradas; sin resultados experimentales.",
  "sources": [
    "contract.md",
    "delivery-files.json",
    "measured-test-records.json"
  ]
}
```

### u1 · uncertainty · v1

```text
La síntesis syn1 queda limitada por tres ausencias: recetas examinables, entrega ejecutable y registros por caso. No hay base para asignar valores a i1, estimar efectos o intervalos, ni juzgar h1 como confirmada o refutada. Se conserva la conclusión de falta de demostración, sin convertir ausencia de evidencia en fallo.
Incluso con registros futuros, una matriz sintética finita sólo sustentaría conclusiones sobre sus casos y la versión examinada. Selección de entradas y repetición de los ejemplos pueden ocultar defectos; coincidencia entre implementación y oráculo puede reflejar errores compartidos. pr1 propone contrastar expectativas con derivaciones independientes y separar discordancias, registros ausentes y fallos de ejecución. Aquí no se ha aplicado ese procedimiento.
Para reducir estas incertidumbres harían falta contrato y recetas fijados, expectativas contrastadas y registros íntegros vinculados a una entrega concreta bajo los recursos establecidos. Esas necesidades no acreditan que existan ni garantizan cobertura universal. Se detiene la inferencia empírica en el alcance documental de syn1; no se extrapola a usuarios, otras tareas o familias de modelos.
```

Autor: agent:codex\-isolated\-author.

Depende de: e1 v1, h1 v1, i1 v1, inf1 v1, pr1 v1, syn1 v1.

```json
{
  "scope": "Límites de soporte y posibles sesgos; sin cuantificación inventada.",
  "sources": [
    "contract.md",
    "delivery-files.json",
    "measured-test-records.json"
  ]
}
```

### o1 · option · v1

Construir FractionMix como utilidad Python 3\.12 con biblioteca estándar: validar íntegramente bytes, JSON y términos antes de sumar con aritmética racional exacta; reducir y serializar enteros grandes sin restringir el dominio contractual\. Entregar interfaz stdin, errores exactos y README reproducible\. Para el operador ofrece una entrega examinable; para el autor exige implementación y documentación, y para el evaluador exige expectativas independientes y registros por caso\. Son tareas previstas, no efectos medidos\. El coste incluye construcción, comprobación y mantenimiento, sin estimación disponible\. Riesgos: aceptación accidental de entradas inválidas, límites decimales y agotamiento de recursos\. Viabilidad y conformidad siguen sin demostrar\.

Autor: agent:codex\-isolated\-author.

Depende de: e1 v1, n1 v1, syn1 v1, u1 v1.

```json
{
  "sources": [
    "contract.md",
    "existing-mandate.md"
  ]
}
```

### o2 · option · v1

Alternativa organizativa sin software nuevo: para sumas puntuales pequeñas, registrar cada término, obtener un denominador común con aritmética entera, sumar numeradores, reducir por el máximo común divisor y contar todos los términos; otra persona puede contrastar la derivación\. Es practicable para explicar los ejemplos públicos, sin afirmar que se haya realizado\. El operador recibe una explicación documental; quien calcula y quien contrasta asumen trabajo por entrada y riesgo de transcripción\. Evita construir un ejecutable, pero tiene coste humano recurrente no cuantificado\. No entrega la interfaz stdin, el rechazo automatizado ni los límites temporales exigidos; no sustituye el encargo completo\.

Autor: agent:codex\-isolated\-author.

Depende de: f2 v1, n1 v1, syn1 v1, u1 v1.

```json
{
  "sources": [
    "contract.md: Dos ejemplos públicos",
    "existing-mandate.md"
  ]
}
```

### cmp1 · comparison · v1

o1 aborda la entrega automatizada requerida por n1; o2 aborda explicación de casos pequeños\. Para el operador, o1 requiere examinar una entrega y sus registros, mientras o2 requiere conservar derivaciones por entrada y deja pendiente la interfaz\. Para autores y evaluadores, o1 concentra trabajo en construcción, documentación y comprobación; o2 desplaza trabajo hacia cálculo y contraste manual recurrentes\. No hay importes, tiempos ni tasas de error medidos para ordenar costes\. o1 expone a defectos de validación, serialización y recursos; o2 a transcripción y omisiones humanas\. Ambas requieren comprobación independiente: automatizar no elimina ese trabajo\. Respecto de la entrega completa, o2 queda descartada por incompatibilidad de interfaz, no por inferioridad empírica; para explicar ejemplos no está dominada con la evidencia disponible\. o1 concuerda documentalmente con el mandato, pero no se infiere superioridad, viabilidad ni conformidad ejecutable\. La ausencia de recetas y registros impide una comparación experimental\.

Autor: agent:codex\-isolated\-author.

Depende de: n1 v1, o1 v1, o2 v1, syn1 v1, u1 v1.

```json
{
  "sources": [
    "contract.md",
    "delivery-files.json",
    "measured-test-records.json"
  ]
}
```

### r1 · risk · v1

En o1, validar parcialmente puede ocultar términos inválidos; conservar la validación completa aunque haya ceros o cancelaciones\. Los enteros grandes pueden afectar serialización y recursos: preservar el dominio y los límites contractuales, distinguiendo timeout/OOM/crash del error de entrada\. En o2, errores de transcripción o reducción recaen en quien calcula; conservar términos y derivaciones para contraste, sin presentarlos como evidencia del ejecutable\. En ambas, expectativas compartidas pueden ocultar errores y trasladar carga al evaluador: contrastar derivaciones independientes y conservar fallos\. No modificar cuentas, credenciales, servicios ni límites; no reparar con feedback reservado\. Si surge un conflicto de valor fuera del mandato o una contradicción contractual, detener la construcción dependiente y explicitarlo\. Sin recetas fijadas ni registros, detener las conclusiones empíricas; estos controles son propuestas, no mitigaciones verificadas\.

Autor: agent:codex\-isolated\-author.

Depende de: cmp1 v1, n1 v1, o1 v1, o2 v1, u1 v1.

```json
{
  "sources": [
    "contract.md",
    "existing-mandate.md"
  ]
}
```

### d1 · decision · v1

Elegir o1 dentro del mandato técnico delegado y de n1: construir una utilidad Python 3\.12 de biblioteca estándar con validación completa y suma racional exacta\. cmp1 descarta o2 para la entrega porque no proporciona la interfaz automatizada; sigue siendo una alternativa para explicar ejemplos aislados\. No hay mediciones que permitan ordenar costes o afirmar superioridad\. Usar aritmética entera y reducción por máximo común divisor, sin redondeo; validar todos los términos antes de calcular y permitir serialización de resultados mayores de 4300 dígitos\. Estas decisiones responden al contrato documentado en e1 y a los riesgos r1\. La construcción no demuestra conformidad\. pr1 sigue condicionado a fijar y examinar las recetas ausentes antes de generar; no se sustituirán por los dos ejemplos ni se reparará usando feedback reservado\.

Autor: agent:codex\-isolated\-author.

Depende de: cmp1 v1, e1 v1, n1 v1, o1 v1, o2 v1, p1 v1, pr1 v1, r1 v1.

Aprobación vigente: sí.

```json
{
  "selected_option": "o1",
  "sources": [
    "contract.md",
    "existing-mandate.md"
  ]
}
```

### req1 · requirement · v1

Entregar fractionmix\.py y README conforme a contract\.md\. Invocación sin argumentos mediante /opt/specorganon/venv/bin/python \-E \-s \-B /input/delivery/fractionmix\.py; cualquier argumento causa error antes de leer stdin\. Leer exclusivamente stdin, hasta 65536 bytes inclusive\. Exigir UTF\-8 estricto sin BOM inicial ni NUL y un único JSON, sin claves duplicadas ni constantes no JSON\. Objeto superior con sólo terms: lista de 0 a 1000 objetos con sólo numerator y denominator; enteros exactos, excluidos bool y float, numerador entre \-1000000000 y 1000000000 y denominador entre 1 y 1000000000\. Validar incluso ceros y cancelaciones\. Sumar exactamente, reducir, mantener denominador positivo, cero 0/1 y contar todos los términos sin deduplicar; admitir resultados mayores de 4300 dígitos\. Éxito: exit 0, stderr vacío y único objeto JSON con enteros numerator, denominator y term\_count, stdout empieza con \{ y termina con \} y LF, sin whitespace exterior\. Error contractual: exit 2, stdout vacío y stderr exactamente \{"error":"invalid\_input"\} seguido de LF\. Conservar timeout/OOM/crash como fallos de ejecución\. Respetar 3 s, 2 CPU, 1 GiB, 128 procesos y streams de 2 MiB; sin red, credenciales, archivos auxiliares ni consulta del entorno; entrega readonly\. README documentará instalación, invocación, ambos ejemplos con comandos y resultados especificados, errores, límites, aritmética, pruebas reproducibles y alcance sintético\. Las pruebas propias futuras cubrirán éxito, error y bordes; no hay ejecución suministrada\.

Autor: agent:codex\-isolated\-author.

Depende de: d1 v1, e1 v1, n1 v1, p1 v1, pr1 v1, r1 v1.

```json
{
  "sources": [
    "contract.md",
    "existing-mandate.md"
  ]
}
```

### cr1 · criterion · v1

Antes de cualquier resultado, fijar para req1 el criterio de conformidad en la matriz de pr1: proporcion\_casos\_conformes = 1, según i1\. Sólo contará como conforme un caso con registro completo de entrada, versión, exit, stdout, stderr y estado de ejecución que coincida con todas las reglas aplicables de req1 y con expectativas contrastadas independientemente\. Un caso discordante basta para rechazar la conformidad integral de esa versión en esa matriz; conservar su identificador y discrepancia, incluidos timeout/OOM/crash\. Registros ausentes, recetas sin fijar o expectativas sin contrastar impiden demostrar el criterio; no se imputarán como éxitos ni como mediciones de fallo\. Examinar cobertura de validación, aritmética, enteros grandes, formato y recursos, además del README y pruebas propias exigidos por req1\. El indicador mide casos, no sustituye la comprobación documental\. No calcular ahora valores ni intervalos: e1 es evidencia documental y los mapas de entrega y registros están vacíos\. Una futura coincidencia total sólo sustentará el alcance de la matriz y versión examinadas, sin demostrar corrección universal ni utilidad humana\.

Autor: agent:codex\-isolated\-author.

Depende de: d1 v1, e1 v1, i1 v1, n1 v1, p1 v1, pr1 v1, req1 v1.

```json
{
  "metric": "proporcion_casos_conformes",
  "reject": "Al menos un caso con discordancia contractual documentada en la matriz fijada y la versión examinada.",
  "reject_test": {
    "metric": "numero_casos_discordantes",
    "operator": ">=",
    "statistic": "estimate",
    "unit": "casos",
    "value": 1
  },
  "scope": "Matriz fijada de pr1 y versión concreta de entrega; evidencia incompleta implica no_demostrado.",
  "sources": [
    "contract.md",
    "delivery-files.json",
    "measured-test-records.json"
  ],
  "threshold": {
    "operator": ">=",
    "statistic": "estimate",
    "value": 1
  },
  "unit": "proporción"
}
```

### impl1 · implementation · v2

Entrega de req1 v1 ampliada con test\_fractionmix\.py en la etapa tests\. fractionmix\.py y README\.md permanecen sellados, sin modificación respecto del checkpoint program\. Las pruebas propias propuestas contrastan validación, aritmética, formato y bordes con expectativas independientes; no constituyen ejecución ni sustituyen las recetas ausentes de pr1\.

Autor: agent:codex\-isolated\-author.

Depende de: d1 v1, req1 v1.

```json
{
  "delivery_tree_sha256": "6aa79fc78a4448eea825fbfc0ac74dbfce555edf207d3de9217a136a9139efa9",
  "entrypoint": "/input/delivery/fractionmix.py",
  "files": [
    "fractionmix.py",
    "README.md",
    "test_fractionmix.py"
  ],
  "sources": [
    "contract.md",
    "build-stage.json",
    "delivery-files.json"
  ]
}
```

### t1 · test · v2

Borrador ejecutable de pruebas propias para cr1 v1, req1 v1 e impl1 v2\. Comprueba ambos ejemplos, suma mediante Fraction como oráculo separado, reducción, cero, conteo, permutaciones, límites inclusivos, resultados mayores de 4300 dígitos, errores JSON/UTF\-8/tipos y rechazo de argumentos antes de recibir stdin\. Verifica exit, stderr y formato de stdout\. Cada proceso tiene timeout de 3 segundos; los demás controles de aislamiento y recursos corresponden al ejecutor externo\. No hay ejecución suministrada; estas pruebas no fijan ni reemplazan la matriz reservada de pr1\.

Autor: executor:isolated\-software\-controller.

Depende de: cr1 v1, impl1 v2, req1 v1.

```json
{
  "argv": [
    "/opt/specorganon/venv/bin/python",
    "-E",
    "-s",
    "-B",
    "/input/delivery/test_fractionmix.py"
  ],
  "command": "/opt/specorganon/venv/bin/python -E -s -B /input/delivery/test_fractionmix.py",
  "delivery_tree_sha256": "6aa79fc78a4448eea825fbfc0ac74dbfce555edf207d3de9217a136a9139efa9",
  "passed": true,
  "receipt": {
    "argv": [
      "/opt/specorganon/venv/bin/python",
      "-E",
      "-s",
      "-B",
      "/input/delivery/test_fractionmix.py"
    ],
    "exit_code": 0,
    "result_sha256": "e9f5fff967bdb20a0f247a6f94f2ca4b32ea667adef053948cc157ff29ab2bb6",
    "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "stdout_sha256": "8571ae26c0018d537b5e34d44f04fe70c112d9f2d4e997c7acdedbc48578da95",
    "timed_out": false
  },
  "scope": "Pruebas propias sobre entradas sintéticas; sin resultados ni cobertura universal.",
  "sources": [
    "contract.md",
    "build-stage.json",
    "delivery-files.json"
  ],
  "test_job_ref": "/datos/workspaces/personal/specorganon-validation/autonomous-software-v1/software-comparison-v3/cells/cell-01/transport/host-journal/test-df790ab0934e8d44a455f6fb/receipt.json"
}
```

### bl1 · baseline · v1

No se suministra una línea base medida para proporcion\_casos\_conformes en la matriz de pr1 v1\. El valor 1 de cr1 v1 es un umbral normativo, no una medición basal\. Los ejemplos públicos especifican expectativas y no constituyen observaciones previas\. No se imputa cero ni se usa el cálculo manual como comparador medido\.

Autor: agent:codex\-isolated\-author.

Depende de: cr1 v1, i1 v1, pr1 v1.

```json
{
  "date": "2026-10-05",
  "metric": "proporcion_casos_conformes",
  "origin": "technical",
  "scope": "Matriz candidata de 84 casos de pr1 v1; recetas y medición basal no suministradas.",
  "source": "contract.md; state.json/items/cr1; state.json/items/pr1",
  "uncertainty": "Línea base empírica desconocida; fecha de la copia documental suministrada.",
  "unit": "proporción",
  "value": null
}
```

### res1 · result · v2

El registro suministrado de t1 v2 corresponde a impl1 v2: exit 0, stderr vacío y mensaje de finalización de las pruebas propias\. Informa 1\.6332622909976635 segundos para el trabajo agregado, sin timeout ni truncamiento\. No contiene las recetas fijadas ni registros individuales de la matriz de pr1 v1; no permite calcular i1 ni demostrar cr1 v1\. bl1 v1 no aporta una medición basal, por lo que tampoco permite estimar una diferencia comparativa\.

Autor: agent:codex\-isolated\-author.

Depende de: bl1 v1, cr1 v1, i1 v1, impl1 v2, pr1 v1, t1 v2.

```json
{
  "date": "2026-10-05",
  "metric": "proporcion_casos_conformes",
  "observations": {
    "duration_seconds": 1.6332622909976635,
    "exit_code": 0,
    "stderr_bytes": 0,
    "stdout_bytes": 40,
    "timed_out": false,
    "truncated_streams": []
  },
  "origin": "technical",
  "scope": "Pruebas propias de impl1 v2 vinculadas a t1 v2; no la matriz de pr1 v1.",
  "source": "measured-test-records.json: t1; state.json/items/t1",
  "uncertainty": "Registro agregado con confianza local declarada, sin identidad autenticada ni firma verificada. No aporta numerador ni denominador del indicador; la duración no mide rendimiento por caso.",
  "unit": "proporción",
  "value": null
}
```

### as1 · assessment · v2

Veredicto no\_demostrado para cr1 v1\. El res1 actualizado conserva el soporte técnico limitado de t1 v2 sobre impl1 v2 y enlaza bl1 v1\. La finalización de las pruebas propias no demuestra conformidad integral en la matriz de pr1 v1 ni documenta una discordancia de esa matriz para aplicar el rechazo prerregistrado\. Sin línea base medida, recetas fijadas y registros por caso, no hay efecto ni intervalo estimables\. No se suministran resultados de simulación ni observaciones de campo\. El cálculo manual sigue siendo una alternativa documental para ejemplos, sin comparación medida y sin entregar la interfaz requerida\. Conforme a r1 v1, se detiene la inferencia de eficacia por soporte insuficiente\.

Autor: agent:codex\-isolated\-author.

Depende de: bl1 v1, cr1 v1, r1 v1, res1 v2.

```json
{
  "adverse_effects": "Desconocidos fuera del registro técnico suministrado. La ausencia registrada de timeout y truncamiento no demuestra ausencia general de daños, OOM o defectos.",
  "claim_scope": "technical",
  "cost": "Costes monetarios, humanos y consumo de recursos desconocidos. La duración agregada suministrada de 1.6332622909976635 segundos no representa coste total ni rendimiento por caso.",
  "effect": {
    "estimate": null,
    "interval": null,
    "metric": "proporcion_casos_conformes",
    "unit": "proporción"
  },
  "scope": "cr1 v1 y entrega impl1 v2; evidencia limitada a las pruebas propias suministradas.",
  "uncertainty": "Faltan recetas fijadas, registros por caso y línea base medida. El agregado no permite atribución causal ni extrapolación; persisten selección de casos y posibles errores compartidos con el oráculo.",
  "verdict": "no_demostrado"
}
```

## Alcance del informe

- El informe resume el expediente; no verifica por sí solo la verdad de sus fuentes\.
- Aceptar fases no demuestra superioridad metodológica ni impacto de campo\.
- El modo local no autentica identidades ni custodia externa; sus revisiones y recibos son declaraciones del entorno de trabajo\.
