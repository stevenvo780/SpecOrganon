# D112 — preparación ejecutable del desarrollo A/B/C

Base: `98a1403ea972f328a86a114f207716978fd98a98`; rama
`work/toolkit-foundation`. Objetivo y protocolo completos leídos. El D111
anterior constituye progreso: sus 166 pins coinciden con HEAD. Este corte
conecta casos públicos y prototipos al ejecutor común; no declara ejecutadas
las 24 celdas ni modifica GOAL/protocolo.

## Contrato anterior a los gates

1. Nuevo esquema explícito de desarrollo, validado por reproducción exacta:
   ronda 1, A/B/C × D-F/D-E × dos repeticiones = 12 preparaciones. Modelo,
   esfuerzo, precio declarado, código, prompts, casos, orden y límites quedan
   ligados por digest. Ronda 2 rechazada hasta implementar y congelar su
   adaptación a resultados reales de ronda 1. El inventario completo sigue
   siendo 24 celdas; estas preparaciones no son ejecuciones formales.
2. Mantener validadores confirmatorios R-F/R-M/R-S y N/S/T sin flexibilizar.
   Routing sólo por el esquema nuevo. Desarrollo usa ocho assets públicos,
   ningún archivo de referencia oculto ni caso reservado. Reutiliza release,
   stage, sandbox, claim, ledger y context de D111.
3. Paquetes originales D-F: tarea, claims, manifest, dos PDF y tabla pública;
   D-E: tarea, manifest y CSV original. Las copias originales no cambian. El
   builder añade sólo case.json con identidad, hashes y entregables. No
   sustituye casos por variaciones escalares ni agrega resultados anteriores.
4. Herramienta ejecutable autónoma con core del prototipo embebido byte por
   byte. Modo fijado por arm_prompt A=sequential/B=graph/C=risk. Ejecuta
   init/status/revise/review/advance/plan reales en el proceso sellado. La
   operación approve de fixtures no se expone. Rechazo metodológico esperado
   se devuelve como dato con estado/digest y sin error de infraestructura.
5. Lectura de inputs enumerados y escritura de entregables en chunks, offset
   exacto; estado del método y fuentes no pueden escribirse con esas ops.
   analysis.py se ejecuta in-process bajo sandbox externo, sin habilitar fork
   ni red. Su stdout debe ser JSON estricto. No se modifica el código del
   participante ni se repara desde el evaluador.
6. Topes de esta versión: 80k tokens, 5400 segundos, hasta 32 solicitudes y
   16 herramientas; modelo/esfuerzo iguales para todos los roles. Los límites
   son prospectivos para esta preparación; no se amplía silenciosamente D111.
   C sólo calcula cola y tandas posibles: paralelismo real sigue pendiente.
   Leer pasajes PDF exige un mecanismo común futuro de extracción congelada;
   este corte no pretende completar el análisis de D-F con hashes únicamente.
7. Pruebas mecánicas offline con proveedor falso y herramientas reales:
   cobertura de los dos casos y tres modos, límites/admisión compartidos,
   estado normativo pendiente, invalidación y chunks. No generación real,
   factura, identidad autenticada, normas humanas, Q, reserva o campo.

## Ownership y gates

Root: plan, builder de paquetes/preparación, routing en preflight, integración,
documentación y captura. Worker1: plan_development_round.py y su test.
Worker2: development_method_tool.py y su test. Revisor independiente read-only
después de estabilizar fuentes. Máximo root + dos workers + un revisor;
preservar trabajo ajeno, sin push ni main.

Fase → agentes nativos existentes → contratos y herramientas locales; cuota
consultada 2026-10-01T01:52:31.947Z: Codex sin sonda fiable, Gemini 97%/98%.
No se elige proveedor pagado ni se interpreta esa sonda como autorización.

Antes de gates finales: freeze de fuentes y hashes. Capturar cada intento,
comando, duración, código de salida, stdout/stderr y copias de fuente; no
borrar negativos. Pytest proporcional 3.11, subset/integración 3.12, Ruff y
compilación. Regresión confirmatoria y del ejecutor por el routing nuevo.
No rebuild de wheel ni suite global sin riesgo concreto. Revisión independiente
de bindings, fuentes, resultados y límites. Criterio C1 técnico D107 sigue
1/5; C2–C5 no demostrado hasta satisfacer todo GOAL.
