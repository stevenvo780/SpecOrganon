# Comparación prospectiva de software pequeño

Este directorio conserva una campaña local de 28 celdas: RoutePlan/TreeMap,
Codex/Gemini, dos réplicas operativas N/S/T y cuatro ablaciones A. No acredita
superioridad general ni beneficios de campo. La goal exige además una entrega
nueva T con nueve fases completas, pruebas reales y documentación.

## Fuentes y versiones

- frozen/registration.json registra el primer arranque. Terminó antes de iniciar
  el proveedor por confundir un registro de rutas MCP con metadata pública de
  modelos Codex. Se conserva una fila infra_inconclusive y 27 no iniciadas.
- frozen/registration-02.json registra la corrección técnica antes de la primera
  generación real: misma población, IDs, orden, cuentas, imágenes y presupuestos.
  SHA:231dbf966a2155c283e671c6de0c3340793b1eaccd19ba30112bcfbb7df30be7.
- Los archivos con nombre draft están congelados por su hash en el registro;
  su nombre original se conserva. No editar sus bytes durante la campaña.
- Las revisiones conjuntas son aceptación técnica prospectiva de texto. No
  ejecutaron tests ni aceptaron entregas nuevas de nueve fases.

La primera versión conserva un snapshot externo de sus46 fuentes en
/datos/workspaces/personal/specorganon-validation/autonomous-software-v1/software-comparison-v1-frozen-source.
Sus 28 filas y archivo raw con índice están en goals/autonomous-software-v1/evidence.
La segunda versión ejecuta en un root privado distinto, con 48 fuentes vinculadas.

## Entorno original y ejecución

Los registros fijan imágenes Docker por digest y los perfiles originales del
operador. No contienen autenticación. No copiar auth.json, sesiones o SQLite,
intercambiar cuentas, forzar resets, comprar créditos o usar otra máquina como
cuota adicional. Las cuentas necesitan autorización previa; esta campaña ya
usa el mandato existente. La consulta de quota no garantiza capacidad remota.

Desde /datos/workspaces/personal/SpecOrganon, una celda pendiente se observa o
continúa con la misma identidad y fuentes:

```bash
PYTHONPATH=src:. python scripts/software_study_harness.py \
  --registration experiments/software_comparison_v1/frozen/registration-02.json \
  --cell ID_EXACTO_DE_LA_SIGUIENTE_CELDA \
  --quota-snapshot RUTA_A_OBSERVACION_ACTUAL_ORIGINAL.json \
  --steps 1
```

La observación contiene schema1, captured_at UTC, aliases de cuentas originales
y porcentajes/source/observed_at por proveedor. Datos no observables quedan
status=unknown con lista vacía y motivo; nunca se convierten a capacidad confirmada.
La CLI rechaza observaciones de más de 600s, agotadas o con metadata adicional.
Los snapshots conservados en evidence son históricos: no reutilizarlos después
de su ventana. El coordinador consulta las herramientas de cuota autorizadas
y conserva la lectura nueva antes de admitir otro envío.

El root de campaña viene del registro y no se puede dividir para renovar límites.
Sólo se admite la próxima celda del orden fijo. Un fallo de generación cierra
esa celda y conserva exportación parcial; no permite mejorar el resultado con
una nueva llamada. Un fallo nativo desconocido detiene nuevos envíos de toda
la campaña. Una pausa de cuota anterior al dispatch no consume una llamada.
Una interrupción permite observar/reconciliar el mismo handle; no sustituirlo.
La discontinuidad entre boots pausa y no renueva el presupuesto; no se afirma
recuperación del reloj entre reinicios. Se conserva el tiempo global de 6000s.

El controlador T cuenta revisiones y aprobaciones conjuntamente dentro del
límite de dos intervenciones por fase. En TreeMap/Gemini/r1, la aprobación de
la norma y la revisión que rechazó critique consumieron ambas intervenciones.
Aunque el autor redactó una corrección, ésta quedó sin una revisión nueva al
cerrarse la celda. El registro vincula ese comportamiento por el hash del
controlador; el límite no se modifica durante generación. No interpretar ese
cierre como un juicio técnico de la corrección ni como completar nueve fases.

## Evaluación posterior

Hasta que toda generación esté cerrada o haya parada terminal real de
infraestructura, el driver bloquea feedback reservado:

```bash
PYTHONPATH=src:. python -m experiments.software_comparison_v1.reserved.campaign_evaluation \
  --registration experiments/software_comparison_v1/frozen/registration-02.json
```

El sujeto funcional recibe entrega opaca y entrada actual, sin perfiles/red,
método, ledger, oráculos o expected. RoutePlan tiene 61 invocaciones; TreeMap 52
y un probe independiente de acceso a contenido/destino de enlaces. Los archivos
raw y recibos quedan en el root privado. Una invocación incierta se conserva
con su ID, sin sustituirla. El probe no demuestra todos los accesos posibles.

README/comunes/adherencia se presentan por separado. La revisión final es una
sola llamada de la familia opuesta, sin reparación posterior; ve ambos intentos
públicos cuando existan. Un recibo viejo no prueba el programa reparado. Los
ejemplos públicos se ejecutan mediante recetas fijas después del sellado; el
revisor juzga la correspondencia del README. No se ejecuta shell arbitrario
del documento. Faltantes quedan inconclusos y no se suman dimensiones para
inventar un ganador o un veredicto causal.

## Lectura honesta del estado

El checkpoint actualizado está en goals/autonomous-software-v1/checkpoint.json.
Un archivo exportado o un autor cerrado no significa que la celda haya completado
sus tests/revisión o que T tenga nueve fases aceptadas. Una contribución rechazada
queda en los raw, sin promoverla a artefacto vigente del motor. No evaluar el
funcionamiento reservado durante generación ni ajustar fuentes, criterios,
prompts, límites o población según resultados observados. Mantener intactos
el GOAL.md original y los 30 inputs/ledgers/resultados históricos del piloto backup.
