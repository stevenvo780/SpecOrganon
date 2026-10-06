# Dev11: recuperación de fallos cerrados y presupuesto original completo

Este hito es ingeniería prospectiva parcial. No admite una campaña T, no congela una versión completa y no establece competencia, completion común, F reservado ni superioridad. No repite ni sustituye las seis posiciones originales de dev7 o dev8. Las dos GOAL mantienen sus bytes y criterios.

El transporte guarda una prueba negativa derivada del recibo original de ejecución y del contenedor terminal: salida no cero, timeout, truncamiento u OOM. Su recuperación verifica la identidad, entrada, fuentes, argv y streams originales sin preparar, arrancar ni reconciliar otra llamada. No convierte esa prueba en respuesta aceptada, invocación nativa acreditada, usage o tokens. N/S/T conservan la misma reserva y los mismos contadores; T también conserva por separado el fallo de su auditor común.

Los intentos nativos prospectivos requieren transporte schema6 y un binding del reloj original anterior a la preparación. El presupuesto sigue siendo 6000 segundos de CLOCK_BOOTTIME, con 60 segundos reservados para limpieza, preparación mínima de 90 segundos y controles individuales de 15 segundos. La suspensión consume tanto el presupuesto global como el timeout individual. Una reanudación conserva el binding original y no compra otros 6000 segundos. Un reloj de host/boot distinto impide despacho y readiness. La limpieza de seguridad sigue permitida de forma acotada después del vencimiento; una ausencia incierta, proceso dueño muerto o bloqueo del SO/daemon conserva incertidumbre y no habilita cierre exitoso.

La observación funcional pública del driver tiene su propia intención y reloj anteriores a su fábrica real, conservados al releer. Su timeout registrado continúa siendo como máximo 120 segundos y su tiempo integra el total del driver. Esa observación independiente de desarrollo no renueva el reloj de generación, no habilita readiness y no representa F reservado.

La revisión independiente de Codex (`recovery-review-original.json`, 59 archivos/46 módulos en su corte) **rechazó el primer corte con ocho hallazgos**. Sus pins están en `recovery-review-source-pins.json`. Propuso reproducciones estáticas: no ejecutó pytest, Docker ni proveedores. Las correcciones y regresiones del corte posterior se documentan en `engineering-receipt.json`. La segunda revisión (`correction-review-original.json`, 66 archivos/46 módulos) reconoce estáticamente las correcciones F1–F8 pero **rechaza el corte por tres nuevos hallazgos pendientes F9–F11**: recibo del auditor común en el primer cierre, ciclo de vida Docker en el cierre normal y bytes consumidos para el score público. Sus reproducciones propuestas no fueron ejecutadas. No hay aceptación independiente del corte ni autorización de admisión. Gemini analizó por separado el presupuesto (`deadline-review-original.json`) y trabajó únicamente sobre el contexto y verificación negativa del controlador libre. El writer Gemini alcanzó timeout de 900 segundos tras dejar cambios; ROOT corrigió un supuesto de su fixture y verificó los cambios con sus propias pruebas. El fallo se conserva en `autonomy-writer-original.json`; no se acredita éxito al writer. Ninguna delegación de ingeniería cuenta como sujeto experimental.

Los recibos `targeted.*`, `actual-docker.*`, `build-*`, `final-*` e `installed-release-receipt.json` pertenecen a cortes anteriores a las ocho correcciones. Se conservan como historial. Los recibos `review-corrected-*` tienen pins del corte corregido, comando, salida, código de retorno y comprobación de fuentes sin cambios. Los conteos se solapan y no se suman como intentos nativos.

Reproducción de controles mecánicos desde este código:

```sh
uv sync --extra dev --frozen
uv run python -m pytest -q tests/test_attempt_deadline.py tests/test_closed_execution_failure.py tests/test_dev11_review_regressions.py tests/test_neutral_autonomy.py tests/test_neutral_pilot.py
# Docker real con autores/proveedores simulados, perfil temporal vacío y sin credenciales existentes:
SPECORGANON_NEUTRAL_DOCKER_CONTROLS=1 uv run python -m pytest -q tests/test_neutral_docker_controls.py
# Imágenes locales instaladas; las sondas no invocan un modelo:
docker build -f docker/release/Dockerfile -t specorganon-release:0.2.0rc3.dev11 .
docker build -f docker/codex/Dockerfile -t specorganon-codex:0.2.0rc3.dev11 .
uv run python goals/method-superiority-v1/evidence/whole-attempt-recovery-dev11-01/probe_installed_review_corrected.py
```

Los fixtures de autores, auditores, mandatos, journals y relojes son sintéticos. Los procesos locales y Docker se ejecutan realmente. El probe instalado coteja los 46 módulos del wheel, CLI y descubrimiento MCP stdio de 24 herramientas con red deshabilitada, filesystem de imagen en lectura y sin montajes de credenciales. La imagen Codex verifica versión y módulos instalados sin login ni llamadas. Las imágenes permanecen locales, sin publicación en un registry.

Queda pendiente revisión independiente de la fuente final completa, integración y registro de entrada T nativa, diez intentos originales con al menos nueve completos en tres tipos, fases sustantivas en dos tipos, comparación reservada pareada y réplica independiente de la misma versión. La meta sigue ACTIVE.
