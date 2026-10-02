# Reproducción local del análisis escolar

Desarrollo local con autores y mandato declarados.

Revisión del expediente: 68. Fases aceptadas: 9/9.

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

Necesitamos comprobar que un agente puede reproducir el análisis del XLSX escolar disponible sin cambiar la fuente, el plan o los resultados históricos\.

Autor: agent:mvp\-builder.

### a1 · actor · v1

El dueño fija el propósito; un agente implementa y otro revisa los resultados locales\.

Autor: agent:mvp\-builder.

Depende de: p1 v1.

### b1 · boundary · v1

Workspace de desarrollo y archivos disponibles\. Sin API adicional ni acciones de campo\.

Autor: agent:mvp\-builder.

Depende de: p1 v1.

### c1 · concept · v1

Autonomía es ejecutar dentro del encargo; reproducibilidad es poder repetir y cotejar resultados\.

Autor: agent:mvp\-builder.

Depende de: p1 v1.

### s1 · assumption · v1

Las herramientas y archivos locales permiten comprobar este proyecto en el entorno actual\.

Autor: agent:mvp\-builder.

Depende de: p1 v1.

### f1 · frame\_option · v1

Encuadrar el problema como falta de garantías externas en cada transición\.

Autor: agent:mvp\-builder.

Depende de: p1 v1.

### f2 · frame\_option · v1

Encuadrar el problema como una experiencia local usable con confianza declarada y evidencia verificable\.

Autor: agent:mvp\-builder.

Depende de: p1 v1.

### n1 · norm · v1

Aplicar el mandato del dueño al MVP: usar recursos presentes, preservar historia, delegar decisiones técnicas reversibles y mantener explícitos los límites de las conclusiones\.

Autor: agent:mvp\-builder.

Depende de: a1 v1, p1 v1.

Aprobación vigente: sí.

```json
{
  "authorization_scope": "MVP local de filosofia, ciencia e ingenieria; recursos presentes; decisiones tecnicas reversibles delegadas; preservar originales y declarar limites.",
  "identity_authenticated": false,
  "origin": "existing_owner_mandate"
}
```

### q1 · question · v1

¿Podemos producir y revisar una entrega local reproducible con los recursos presentes?

Autor: agent:mvp\-builder.

Depende de: p1 v1.

### h1 · hypothesis · v2

El analizador existente reproduce exactamente el JSON de referencia al conservar fuente y plan fijados\.

Autor: agent:mvp\-builder.

Depende de: q1 v1.

### pr1 · protocol · v2

Registrar criterios, ejecutar comandos reales, conservar streams y cotejar resultados antes de evaluar\.

Autor: agent:mvp\-builder.

Depende de: h1 v2, q1 v1.

```json
{
  "comparison": "JSON histórico del análisis escolar",
  "method": "Ejecución local, hashes de originales, cotejo objetivo y revisión nativa separada",
  "population": "Este proyecto de desarrollo expuesto, en el entorno actual",
  "uncertainty": "Un entorno y un proyecto; sin causalidad de campo ni comparación confirmatoria"
}
```

### e0 · evidence · v2

La salida reproducida coincide exactamente con el JSON histórico; sus hashes y el cotejo de bytes están conservados\.

Autor: agent:mvp\-builder.

Depende de: pr1 v2.

```json
{
  "date": "2026-10-01",
  "locator": "byte_equal and historical_sha256/reproduced_sha256",
  "method": "Compare retained actual output bytes with historical JSON; verify both SHA256 digests",
  "metric_key": "exact_reproduction",
  "origin": "observed",
  "scope": "current exact reproduction",
  "source": "/workspace/SpecOrganon/experiments/development/mvp_local_2026-10-01/run01/school/source_checks.json",
  "unit": "match",
  "value": 1
}
```

### i1 · indicator · v2

Coincidencia exacta de la reproducción con el resultado histórico\.

Autor: agent:mvp\-builder.

Depende de: e0 v2, n1 v1, p1 v1.

```json
{
  "metric": "exact_reproduction",
  "unit": "match"
}
```

### inf1 · inference · v2

El cotejo actual muestra reproducibilidad técnica exacta; no identifica un efecto causal sobre los residuos escolares\.

Autor: agent:mvp\-builder.

Depende de: e0 v2, h1 v2.

### syn1 · synthesis · v2

El analizador reproduce el resultado descriptivo histórico y conserva exclusiones y límites causales; la comparación técnica fue exacta\.

Autor: agent:mvp\-builder.

Depende de: e0 v2, inf1 v2.

### u1 · uncertainty · v2

La ejecución local no autentica custodios, personas ni mejoras causales fuera del software observado\.

Autor: agent:mvp\-builder.

Depende de: syn1 v2.

### o1 · option · v2

Recalcular manualmente en una hoja nueva conservando las reglas del plan y comprobar transcripción y redondeo\.

Autor: agent:mvp\-builder.

Depende de: n1 v1, syn1 v2.

### o2 · option · v2

Reutilizar el analizador con hashes fijados y cotejar los bytes de salida contra la referencia\.

Autor: agent:mvp\-builder.

Depende de: n1 v1, syn1 v2.

### cmp1 · comparison · v2

La vía manual necesita verificar transcripción y redondeo\. El analizador versionado permite cotejo exacto con los recursos actuales\. No se midió ahorro de tiempo\.

Autor: agent:mvp\-builder.

Depende de: o1 v2, o2 v2.

### risk1 · risk · v2

Una etiqueta o un recibo declarados pueden ser falsos; conservar streams y revisar las fuentes; no extrapolar el resultado local a campo o superioridad metodológica\.

Autor: agent:mvp\-builder.

Depende de: o2 v2.

### d1 · decision · v2

Reutilizar el analizador con pines y cotejo exacto dentro de la delegación técnica del dueño\.

Autor: agent:mvp\-builder.

Depende de: cmp1 v2, e0 v2, n1 v1.

Aprobación vigente: sí.

### req1 · requirement · v2

Conservar compuertas y trazabilidad, ejecutar una prueba real y producir un informe reproducible\.

Autor: agent:mvp\-builder.

Depende de: d1 v2.

### crit1 · criterion · v2

Reproducir exactamente el JSON existente sin modificar originales\.

Autor: agent:mvp\-builder.

Depende de: i1 v2, req1 v2.

```json
{
  "metric": "exact_reproduction",
  "reject": "No cerrar si el resultado es menor que 1 o hay prueba fallida",
  "reject_test": {
    "operator": "<",
    "statistic": "estimate",
    "value": 1
  },
  "threshold": {
    "operator": ">=",
    "statistic": "estimate",
    "value": 1
  },
  "unit": "match"
}
```

### impl1 · implementation · v2

Analizador escolar existente, con fuente y plan fijados por hashes\.

Autor: agent:mvp\-builder.

Depende de: req1 v2.

```json
{
  "paths": [
    "scripts/analyze_school_waste.py"
  ]
}
```

### t1 · test · v2

Ejecución real conservada en execution/; recibo local no autenticado externamente\.

Autor: agent:mvp\-builder.

Depende de: crit1 v2, impl1 v2.

```json
{
  "argv": [
    "/workspace/SpecOrganon/.venv/bin/python3",
    "scripts/analyze_school_waste.py",
    "--output",
    "/workspace/SpecOrganon/experiments/development/mvp_local_2026-10-01/run01/school/school_waste_reproduced.json"
  ],
  "command": "/workspace/SpecOrganon/.venv/bin/python3 scripts/analyze_school_waste.py --output /workspace/SpecOrganon/experiments/development/mvp_local_2026-10-01/run01/school/school_waste_reproduced.json",
  "passed": true,
  "receipt": {
    "argv": [
      "/workspace/SpecOrganon/.venv/bin/python3",
      "scripts/analyze_school_waste.py",
      "--output",
      "/workspace/SpecOrganon/experiments/development/mvp_local_2026-10-01/run01/school/school_waste_reproduced.json"
    ],
    "exit_code": 0,
    "result_sha256": "8a352fbf0915d5761a11103c7dcb8de86843002b1bf2ffbdb28e9fd1e4b12161",
    "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "stdout_sha256": "76345610f1d615f929b6ef3552e3e16e7da267c33978e4d5774bef354172673c",
    "timed_out": false
  }
}
```

### base1 · baseline · v2

Comparador histórico real conservado; la salida debe coincidir exactamente con sus bytes\.

Autor: agent:mvp\-builder.

Depende de: crit1 v2.

```json
{
  "date": "2026-10-01",
  "meaning": "Referencia fijada del cotejo exacto: objetivo coincidencia=1, sin afirmar una reproducción fallida anterior",
  "metric": "exact_reproduction",
  "origin": "technical",
  "reference_sha256": "dd2f41c01a7c082871144ee36398a8372914436be9c808ad8954ab3f8a86a878",
  "source": "/workspace/SpecOrganon/experiments/development/school_waste_2026-09-26.json",
  "unit": "match",
  "value": 1
}
```

### res1 · result · v2

La reproducción actual coincide byte por byte con el JSON histórico\.

Autor: agent:mvp\-builder.

Depende de: base1 v2, crit1 v2, t1 v2.

```json
{
  "date": "2026-10-01",
  "effect": {
    "estimate": 1,
    "interval": [
      1,
      1
    ],
    "metric": "exact_reproduction",
    "unit": "match"
  },
  "origin": "technical",
  "source": "/workspace/SpecOrganon/experiments/development/mvp_local_2026-10-01/run01/school/execution"
}
```

### ass1 · assessment · v2

Reproducción técnica exacta; las diferencias escolares siguen siendo descriptivas, sin atribución causal\.

Autor: agent:mvp\-builder.

Depende de: res1 v2, risk1 v2.

```json
{
  "adverse_effects": "Originales preservados; ninguna intervención externa",
  "claim_scope": "technical",
  "cost": "Agentes y herramientas presentes; sin API adicional. Consumo total no medido.",
  "uncertainty": "Conteo o coincidencia exactos en esta ejecución; sin intervalo estadístico poblacional",
  "verdict": "cumplido"
}
```

## Alcance del informe

- El informe resume el expediente; no verifica por sí solo la verdad de sus fuentes\.
- Aceptar fases no demuestra superioridad metodológica ni impacto de campo\.
- El modo local no autentica identidades ni custodia externa; sus revisiones y recibos son declaraciones del entorno de trabajo\.
