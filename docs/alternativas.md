# Alternativas y prototipos de workflow

## Alcance de este experimento

Este corte compara **mecánicas de avance, revisión, priorización y reanudación** de un toolkit reutilizable. El caso alimentario es una *fixture sintética*: sus estados `supported` y `test_result` son entradas suministradas al motor, no mediciones, bibliografía verificada ni evidencia de impacto. La aprobación `N` en estas ejecuciones es un comando de prueba, no una autorización humana para una decisión normativa real.

La comparación usa el mismo esquema de caso, la misma perturbación y procesos CLI nuevos en cada paso. Los tres prototipos son programas Python sin dependencias externas; usan JSON persistente, escritura atómica por reemplazo y un historial de operaciones. Ninguno es todavía el toolkit completo ni un servidor MCP.

## Tres alternativas de método y arquitectura

| Alternativa | Metodología y workflow | Arquitectura posible | Hipótesis y ventaja esperada | Riesgo y señal de rechazo |
|---|---|---|---|---|
| **A. Etapas con compuertas locales** | Filosofía → ciencia → ingeniería SDD → validación. Cada etapa acepta sus artefactos y exige que las anteriores estén aceptadas. Una revisión vuelve a abrir solo su etapa. | Documentos y estado versionados por etapa; CLI de `advance`, `revise` y `status`; un responsable por etapa. | Es simple de enseñar y auditar; reduce carga de seguimiento y puede bastar en problemas con supuestos estables. | Una evidencia tardía puede dejar decisiones posteriores aceptadas sin reabrirlas. Rechazar si conserva un requisito o validación aceptados cuya justificación ya falla. |
| **B. Grafo revisable de afirmaciones** | Las fases siguen orientando el trabajo, pero problema, supuesto, evidencia, compromiso normativo, requisito y prueba son nodos con dependencias explícitas. Al revisar un nodo se invalidan descendientes y sus compuertas; la revisión ocurre antes de reavanzar. | Almacén de nodos y aristas, historial versionado, propagador de invalidación, CLI y después adaptador MCP con la misma lógica. | Mejora la trazabilidad y evita avances basados en premisas caídas; permite exploración paralela de ramas independientes. | Mantener aristas y revisiones cuesta trabajo; aristas incompletas producen falsa seguridad. Rechazar si añade pasos sin reducir errores o si no detecta cambios de premisa. |
| **C. Portafolio dirigido por riesgos** | Filosofía define valores y restricciones; ciencia puede explorar preguntas independientes antes de cerrar toda la fase anterior. Una cola prioriza incertidumbres y trabajos de revisión bajo un presupuesto. A futuro, ramas independientes de intervenciones podrían explorarse en paralelo y una mesa humana decidiría continuar, pivotar o detener. | Libro de hipótesis y efectos por actor, nodos de dependencia, puntajes de impacto/incertidumbre/esfuerzo y planificador de tandas potenciales. El prototipo ofrece `plan --budget`; no ejecuta agentes. | Evita fijar una solución temprano y dirige atención a las incertidumbres de mayor consecuencia, manteniendo la invalidación de B. | El puntaje puede esconder valores arbitrarios, y el plan puede añadir coste sin mejorar resultados. Rechazar si prioriza mal, salta compromisos normativos, desplaza perjuicios entre actores o no mejora calidad bajo presupuesto equivalente. |

Estas son hipótesis de diseño, no un orden de mérito. A, B y C tienen prototipos en `prototypes/`. El de C **solo modela prioridad y tandas posibles**; no demuestra exploración paralela ni decisiones de portafolio con agentes reales. Una selección final requiere los ensayos amplios de `GOAL.md`, incluidos agentes reales, modelos, casos retenidos y observación en campo.

## Contrato común de los prototipos

La fixture `cold_chain.json` representa seis nodos: problema `P`, supuesto `A`, compromiso normativo `N`, evidencia `E`, requisito `R` y resultado simulado `V`. Sus dependencias son `P → A → E → R → V` y `P → N → R`. Las fases son filosofía, ciencia, ingeniería y validación. Cada fase exige nodos locales `supported` y el compromiso `N` aprobado; B y C exigen además que toda la cadena de dependencias esté vigente. A y B exigen orden de fases; C permite avanzar una fase antes de otra si sus dependencias están listas. En los tres motores, `approve N` es explícito; una `revise` exige motivo y queda en el historial.

C agrega a cada nodo tres enteros ordinales suministrados por la fixture (`impact`, `uncertainty`, `effort`, de 1 a 5) y calcula `impact × uncertainty ÷ effort`. `status` lista trabajo abierto, bloqueos y tandas posibles según aristas; `plan --budget N` selecciona hasta `N` tareas que ya pueden ejecutarse. El puntaje no es una valoración empírica de daño ni una decisión normativa. Las tandas son una **predicción estructural de independencia**, no ejecuciones paralelas observadas.

El criterio de seguridad observable es **cero fases aceptadas cuya cadena de justificación actual contiene un nodo pendiente, contradicho, obsoleto o de versión distinta a la que se aceptó**. `unsafe_accepted_phases` es una auditoría común aplicada a los tres estados; evita que la implementación A pueda ocultar una decisión aceptada al no propagar cambios. Este criterio no decide por sí solo el método: también se observarán esfuerzo de reparación, claridad del estado y coste operativo.

Los primeros ocho escenarios se fijaron antes de la primera ejecución comparativa. Tras revisar esa ronda, se añadió `problem_reframed` para comprobar una dependencia normativa que faltaba cubrir. Una revisión posterior detectó que una evidencia puede cambiar de versión sin pasar a `contradicted`; se añadió `evidence_reestimated` y una comparación de versiones aceptadas. Al incorporar C, se mantuvieron los diez escenarios y se añadió `early_science_exploration` para observar la diferencia de orden. Se conservan los registros de cada ronda.

| Escenario | Perturbación compartida | Resultado exigido por el criterio |
|---|---|---|
| `nominal` | Aprobar `N` y pasar las cuatro fases. | Cuatro fases aceptadas; ninguna insegura. |
| `missing_approval` | Intentar pasar filosofía sin aprobar `N`. | Avance rechazado. |
| `early_science_exploration` (ronda 5) | Intentar ciencia y luego ingeniería sin aprobar `N` ni cerrar filosofía. | A/B rechazan ciencia por orden; C puede aceptar ciencia con `P/A/E` vigentes, pero debe rechazar ingeniería por `N`. |
| `insufficient_evidence` | Poner `E` en `pending` antes de ciencia. | Ciencia rechazada. |
| `late_contradiction` | Tras las cuatro fases, contradecir `E`. | Ingeniería y validación no deben permanecer aceptadas con justificación rota. |
| `evidence_reestimated` (ronda 3) | Tras las cuatro fases, actualizar `E` a una nueva versión que sigue `supported`. | Ingeniería y validación deben reabrirse por cambio de versión. |
| `assumption_shift` | Tras las cuatro fases, contradecir `A`. | Ciencia, ingeniería y validación no deben permanecer aceptadas con justificación rota. |
| `problem_reframed` (ronda 2) | Tras las cuatro fases, contradecir `P`. | Reabrir todas las fases dependientes; `N` requiere nueva aprobación explícita. |
| `resume_after_process_exit` | Consultar estado tras ciencia y continuar en nuevos procesos. | Cuatro fases aceptadas al final. Esto cubre reinicio entre comandos, no corte a mitad de escritura. |
| `recovery_after_correction` | Igual contradicción tardía; luego restaurar `E` y reavanzar. | Cuatro fases aceptadas sin nodos obsoletos. Las acciones de reparación varían según arquitectura y se cuentan. |
| `invalid_dependency` | Inicializar una fixture con arista a un ID ausente. | `init` rechaza el caso sin crear estado. |

Los umbrales anteriores son para la mecánica del workflow. La métrica `wall_ms` incluye arranque de Python por comando y es descriptiva en una sola ejecución; no se usará para concluir que un método es más rápido. `state_bytes` cuantifica solo tamaño del archivo de estado. El presupuesto de C limita **cantidad de tareas sugeridas**, no tiempo, tokens ni dinero; no se implementó todavía una condición de parada del portafolio. Ninguna métrica de tokens, coste de modelos ni impacto alimentario está disponible en estos prototipos.

## Comandos reproducibles

Desde la raíz del repositorio:

```bash
python3 prototypes/compare.py --output prototypes/results/compare.json
python3 prototypes/check_results.py prototypes/results/compare.json
organon_run_dir=$(mktemp -d)
python3 prototypes/sequential.py init --case prototypes/cases/cold_chain.json --state "$organon_run_dir/sequential.json"
python3 prototypes/sequential.py approve --state "$organon_run_dir/sequential.json" --id N
python3 prototypes/sequential.py advance --state "$organon_run_dir/sequential.json" --phase philosophy
python3 prototypes/sequential.py status --state "$organon_run_dir/sequential.json"
python3 prototypes/risk.py init --case prototypes/cases/cold_chain.json --state "$organon_run_dir/risk.json"
python3 prototypes/risk.py approve --state "$organon_run_dir/risk.json" --id N
for phase in philosophy science engineering validation; do
  python3 prototypes/risk.py advance --state "$organon_run_dir/risk.json" --phase "$phase"
done
python3 prototypes/risk.py revise --state "$organon_run_dir/risk.json" --id E --status contradicted --reason "New observation"
python3 prototypes/risk.py plan --state "$organon_run_dir/risk.json" --budget 2
```

Para usar otro motor, cambie `sequential.py` por `graph.py` o `risk.py` y use otro archivo de estado. `init` rechaza una ruta existente para evitar sobrescribir un experimento previo. `compare.py` crea estados limpios temporales para cada par escenario/motor, ejecuta cada acción mediante un proceso nuevo y guarda comandos, códigos de salida, respuestas, tiempo y tamaño de estado en `prototypes/results/compare.json`.

## Resultados observados

Se ejecutaron cinco rondas locales el 2026-09-26, de desarrollo incremental, **no cinco repeticiones independientes**. La primera incluyó ocho escenarios para A/B (`prototypes/results/round1.json`). La segunda añadió `problem_reframed` y nueva aprobación normativa en B (`round2.json`). La tercera añadió `evidence_reestimated` y versiones de dependencias al aceptar (`round3.json`). La cuarta incorporó C con los diez escenarios (`round4.json`). La quinta añadió `early_science_exploration`. Su registro íntegro, incluidos comandos, respuestas, errores, tiempos y SHA-256 de los archivos de entrada, está en `prototypes/results/compare.json`. La última ronda produjo **33 ejecuciones escenario/motor**; `check_results.py` devolvió `PASS: 33 scenario/mode runs; safety checks and negative controls match`. Cada comando de un escenario fue un proceso Python separado. Las rondas históricas anteriores no conservan hashes de su código fuente, por lo que su reconstrucción exacta queda limitada.

| Escenario final | Etapas A | Grafo B | Riesgo C |
|---|---|---|---|
| `nominal` | 4 fases aceptadas, 0 inseguras | Igual | Igual |
| `missing_approval` | Filosofía rechazada | Igual | Igual |
| `early_science_exploration` | Ciencia e ingeniería rechazadas por orden | Igual | Ciencia aceptada sin filosofía cerrada; ingeniería rechazada por `N` pendiente |
| `insufficient_evidence` | Ciencia rechazada | Igual; `R/V` obsoletos | Igual que B |
| `late_contradiction` | **Ingeniería y validación siguen aceptadas e inseguras** | Ambas se reabren; 0 inseguras | Igual que B; plan: `E → R → V` |
| `evidence_reestimated` | **Ingeniería y validación siguen aceptadas con versión vieja de `E`** | Ambas se reabren; 0 inseguras | Igual que B |
| `assumption_shift` | **Ciencia, ingeniería y validación siguen aceptadas e inseguras** | Las cuatro fases se reabren; 0 inseguras | Igual que B |
| `problem_reframed` | **Tres fases posteriores siguen aceptadas e inseguras**; `N` sigue aprobado | Todo se reabre; `N` vuelve a `pending` | Igual que B; tandas posibles: `P → (N, A) → E → R → V` |
| `resume_after_process_exit` | 4 fases aceptadas | Igual | Igual |
| `recovery_after_correction` | 4 fases aceptadas tras **4** comandos de reparación | 4 fases tras **6** | 4 fases tras **6** |
| `invalid_dependency` | `init` rechaza `MISSING`; 0 bytes de estado | Igual | Igual |

Los errores de `missing_approval`, `insufficient_evidence` e `invalid_dependency` son **rechazos esperados**, no fallos del runner. El negativo sustantivo es la aceptación obsoleta de A. El negativo de coste para B/C es la revisión adicional: en recuperación necesitaron **6 comandos frente a 4** de A. El estado final ocupó 4802 bytes en B, 4801 en C y 4567 en A. Los tiempos acumulados de la última ejecución fueron 260, 248 y 217 ms respectivamente; incluyen arranque de procesos y no sustentan una conclusión de rendimiento. Las rondas posteriores mantienen los negativos de la primera; no se repitió hasta obtener un resultado favorable.

El plan de C se invocó también por CLI tras contradecir `E`: con presupuesto 2 seleccionó solo `E` (`score: 6.67`), informó dos tareas diferidas y las tandas potenciales `[[E], [R], [V]]`. El registro de `problem_reframed` muestra `[[P], [N, A], [E], [R], [V]]`. Son propuestas de orden y posible independencia, **no ejecución simultánea**. Los seis puntajes proceden de la fixture y no se sometieron a expertos, mediciones ni comparación de calidad. El valor adicional de esta prioridad queda no demostrado.

Una prueba manual adicional restauró `P` tras `problem_reframed`: `review N` falló con `normative node requires explicit approval`; después `approve N` funcionó, pero filosofía siguió bloqueada hasta revisar `A`. Esto verifica que una aprobación nueva no limpia automáticamente otras dependencias obsoletas.

**Veredicto limitado:** B y C satisfacen el umbral mecánico de invalidación en estas fixtures y A no; A requiere menos acciones de reparación en el caso ensayado. C permite una investigación científica anticipada con dependencias vigentes, pero no se ha medido si eso mejora calidad o tiempo. No se elige método final entre A, B y C con este conjunto sintético. Falta medir la carga de declarar aristas y puntajes, omisiones de dependencias, trabajo de agentes, calidad de decisiones e impacto de intervenciones reales.

## Exclusiones al cerrar la comparación de prototipos

**Esta lista es una fotografía del cierre de los tres prototipos, no del estado actual del repositorio.** En ese punto no se había investigado la cadena alimentaria ni demostrado una intervención; tampoco había cliente MCP, coordinación de agentes reales, control de identidad para aprobación humana, integración SDD con implementación, bibliografía, trazabilidad de fuentes externas, ensayos de concurrencia, interrupción a mitad de escritura, modelos o evaluación independiente. La fixture solo comprobaba estados y dependencias predefinidos; una arista omitida podía hacer pasar una conclusión injustificada. La iteración posterior incorporó parte de esos controles; el [estado actual](estado.md) y la [auditoría por criterio](validacion_actual.md) distinguen lo ya verificado de lo que sigue pendiente.
