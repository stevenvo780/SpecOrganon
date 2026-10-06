# Autonomía del control libre N — diseño y política pura

Avance parcial de ingeniería, sin nuevas generaciones experimentales.
F06 se resolvió **a nivel de diseño** con revisión independiente de Gemini:
código antes de notas, elección de estrategia y de momentos de feedback/medición,
cinco autores, cuatro revisores compartidos y dos medidas, igual al máximo S.
No se imponen SPEC/DESIGN/TASKS ni las nueve fases a N. El máximo efectivo de
roles N/S es nueve; el techo nominal común cuarenta no concede slots adicionales.

El módulo `free_control_policy.py` implementa parser operativo, contabilidad y
viabilidad de decisiones; **no es el controlador ejecutable**. El documento de
partición de batería está formalizado, pero su sellado/custodia queda por implementar.
El driver instalado publicado sigue staged v1. No hay admisión nativa, instalación
actualizada ni competencia empírica, F reservado, paquete común completo o superioridad.

## Evidencia y resultados adversos

- `design-review-01.json`: Gemini, job `0bb689edf7894b3eb5d1505051240869`, lectura
  independiente de diseño, aceptación con cinco precisiones exigidas antes de ejecutar.
- `code-review-01.json`: Gemini, job `be6f4c5e58e249fab7b642ab2ef11d04`, **rechazo**:
  capacidad de roles restantes sobreestimada al confundir techo nominal y cupos efectivos.
  `code-submitted-01.py`, `tests-submitted-01.py` y `protocol-submitted-01.md`
  preservan los bytes de esa iteración; no se reescriben como aceptados.
- `code-and-design-review-02.json`: Gemini, job `9f774ee907ad454187aba7daa418f855`,
  aceptación limitada del contrato corregido y parser/contabilidad/decisiones puros.
  `source-review-02.json` vincula sus tres fuentes y las copias exactas remitidas.
- `tests-01.*`: **69 passed**, primer snapshot. `tests-02.*`: **73 passed**, snapshot
  corregido. Las selecciones se superponen; no se suman ni son suite completa.
  Comandos, código de salida y streams completos están registrados.
- `resource-audit-01.json` deriva de las fuentes reales los máximos S 5/4 usados
  en el contrato inicial. No ejecuta controlador ni mide una comparación.

Las tres revisiones son invocaciones reales de ingeniería, **no tres sujetos de la
comparación**. El puente informa proveedor/modelo/máquina/cwd/job/duración, sin una
identidad exacta de cuenta Gemini; se conserva su ruta/configuración existente.
No se copió perfil ni se cambió cuenta. Duraciones observadas de esas revisiones:
361.9 s, 151.9 s y 48.2 s. Tokens y coste monetario de Gemini no fueron informados.
La consulta de cuota de la app Codex indicó luego uso ordinario no habilitado;
no se envió una nueva revisión Codex ni se dedujo cuota del volumen Docker original.

## Reproducción y límite

```sh
uv run --frozen --extra dev python -m pytest \
  tests/test_free_control_policy.py tests/test_neutral_controller.py \
  tests/test_neutral_pilot.py -q
```

Estas pruebas no llaman a modelos ni Docker. El contrato y el estado de implementación
están en `../../development/neutral-autonomy-v2/`. El ejecutor durable v2 requiere
reservas previas reales, partición y batería selladas, D/G con cronología, recuperación,
integración instalada/CLI/MCP/Docker y revisión de implementación antes de los seis
pilotos públicos fijos. Siguen pendientes la calificación T propia ≥9/10 de una
versión completa congelada, el primario reservado y la réplica de la misma versión.
La meta queda ACTIVE, sin superioridad demostrada.
