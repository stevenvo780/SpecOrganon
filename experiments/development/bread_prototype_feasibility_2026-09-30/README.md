# D-094 · Tres intentos nativos sobre el paquete alimentario público

Se congelaron consigna, fuentes, referencias aritméticas, rúbrica, instrucciones y prototipos en el commit **`7f8a344d56b467d032e449883074feb977f5a2c7`**, antes de los tres lanzamientos nativos. El paquete visible contiene los mismos seis archivos en cada intento; referencias, rúbrica y soluciones históricas quedan fuera. Los artículos y resultados anteriores están expuestos: no es una reserva ni un estudio confirmatorio. El ensayo tiene un ejecutor por alternativa, con modelo/esfuerzo heredados solicitados y contexto `none`; no autentica la identidad efectiva ni impone aislamiento de filesystem.

## Resultados conservados

| Intento | Entregables presentes al capturar | CLI del prototipo | Repetición del cálculo | Estado de la entrega |
| --- | --- | --- | --- | --- |
| A-01 · sequential | `analysis.py`, `metrics.json` | Sin traza ni estado | JSON idéntico; 25/25 cotejos aritméticos | Interrumpido, sin entrega terminal |
| B-01 · graph | Los siete entregables requeridos | Seis comandos; tres avances rechazados | JSON idéntico; 25/25 cotejos aritméticos | Interrumpido, sin entrega terminal |
| C-01 · risk | `analysis.py`, `metrics.json` | Sin traza ni estado | JSON idéntico; 25/25 cotejos aritméticos | Interrumpido, sin entrega terminal |

Los tres seguían `running` al solicitar la interrupción. El operador declara haber superado los 15 minutos solicitados; no se capturaron horas exactas de interrupción ni duración autenticada. Se conservaron **11 archivos originales**, sin reparar resultados ni sustituir intentos. B tiene un paquete de artefactos completo, pero ninguna fase aceptada ni entrega terminal del agente. La mera ausencia de estado en A/C deja su control normativo sin observar.

En B, `N-consent` sigue pendiente y `R-engineering` depende de ella. Filosofía rechaza por `N-consent`; ingeniería responde **`prior phases not accepted: philosophy, science`**. Esto documenta el vínculo y ambos rechazos, sin aislar la norma como causa del rechazo de ingeniería. El inspector inicialmente sobreafirmó `observed_normative_control:true`; un revisor nativo separado detectó el P2 y la corrección preservada cambia ese valor a **`false`**. Ninguna aprobación figura en historial o llamadas. El informe tiene 1009 palabras por separación de espacios.

## Repetición y dependencias

Los tres programas importan solo módulos Python estándar, pero invocan el ejecutable externo **`pdftotext`** para cotejar pasajes de PDF. Esa dependencia adicional impide considerarlos ejecutables autónomos con Python estándar solamente. El replay Landlock ABI 9/seccomp se ejecutó y **falló en los tres** con `Operation not permitted`, porque el sandbox impide crear procesos descendientes. Los streams negativos se conservan.

Tras revisar los scripts, se realizó un replay adicional explícito con entorno limpio y plazo de 30 segundos, que permite `pdftotext`. Este segundo replay **no impone sandbox de archivos/red**. Los tres terminaron con código 0 y stdout idéntico en bytes a las métricas originales; fuentes y entregables permanecieron intactos. No se editó ni sustituyó código de los ejecutores para hacerlo pasar.

Desde la raíz del repositorio, con Python y `pdftotext` local disponibles:

```bash
organon_bread_replay_parent=$(mktemp -d)
python3 experiments/development/bread_prototype_feasibility_2026-09-30/replay_trials.py \
  "$PWD" "$organon_bread_replay_parent/replay" --reviewed-subprocess-replay
python3 experiments/development/bread_prototype_feasibility_2026-09-30/check_arithmetic.py "$PWD"
```

La receta exige inputs y prototipos versionados idénticos a los congelados. Crea un directorio nuevo y reproduce los outputs preservados; **no vuelve a lanzar agentes**. El flag de subproceso es deliberado: conserva el fallo del sandbox antes de la repetición adicional. Revisar el código preservado antes de ejecutar esa segunda ruta.

Los 25 cotejos por intento comparan balance, masa de pieza, energía y cotas con la referencia fijada y aritmética racional de la tabla. Los alias de nombres de métricas se escribieron después de recibir outputs y se declaran como proyección; no cambiaron referencias ni rúbrica. No son Q. A conserva cinco conteos de encuesta sin objetos `value/unit/base`, una desviación de formato aunque sus números coincidan.

## Evidencia y alcance

- [plan.json](plan.json), [staging_receipt.json](staging_receipt.json), [launch_receipt.json](launch_receipt.json): diseño, pins previos y tres handles canónicos. Un nombre con mayúscula fue rechazado antes de crear agente y se corrigió; no es un reintento de ejecución.
- [stager_validation.json](stager_validation.json), [pretrial_review.json](pretrial_review.json): fixture pública del preparador, negativos por fuente/instrucción alterada y dos defectos corregidos antes de congelar. Esa fixture no es otro ensayo nativo.
- [time_reminder.json](time_reminder.json), [stop_receipt.json](stop_receipt.json), [artifact_inspection.json](artifact_inspection.json): recordatorio común sin respuestas, interrupciones declaradas, archivos faltantes y causas de rechazo.
- [replay_receipt.json](replay_receipt.json), `replays/`, [arithmetic_receipt.json](arithmetic_receipt.json): streams de ambos tipos de repetición, hashes y cálculos.
- `runs/`: once archivos originales. El coste/tokens del agente nativo son `null`, no cero; la sonda de cuota Codex no era fiable. Los límites de herramientas/tiempo/modelo no están autenticados ni globalmente aplicados.
- [review.json](review.json), [receipt.json](receipt.json): revisión nativa separada, corrección de interpretación, verificaciones finales y pendientes.

**No se emitió Q**, no hubo doble evaluación ciega humana y el informe no elige ganador A/B/C. Una sola tentativa por alternativa, dos paquetes incompletos, cronología sin custodia y límites sin aplicar impiden una comparación causal. No hubo perturbación común, rondas/repeticiones completas, D-E ni brazos N/SDD/T en estos intentos. Estos resultados **no cuentan entre las 24 corridas** del protocolo ni satisfacen el criterio 4.

El siguiente diseño debe fijar un ejecutor con deadline/cupos observables, separar cálculo de extracción documental o declarar la dependencia de `pdftotext`, y exigir checkpoints de estado/entregables. Solo una nueva ronda registrada podrá probar esas modificaciones, conservando estos resultados negativos. Siguen pendientes panel/casos reservados, presupuesto autorizado medido y evaluación independiente; decisiones e impacto de campo requieren actores y evidencia real. `GOAL.md`, los cinco ledgers reales y el motor no cambian. Veredicto de aceptación: **0/5 criterios demostrados**.
