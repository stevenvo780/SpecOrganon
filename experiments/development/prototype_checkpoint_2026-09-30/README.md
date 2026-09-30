# D-095 · Checkpoint inicial con un proceso supervisado

El [plan](plan.json) fija una tentativa de desarrollo sobre el paquete público
del pan: Codex CLI, modelo solicitado `gpt-6-luna`, esfuerzo `medium`, modo
`graph` y 120 segundos activos locales compartidos por preflight, generación e
inicialización. El commit previo al lanzamiento deberá fijar supervisor,
pruebas y plan. No se busca puntuar calidad, seleccionar arquitectura ni
resolver el caso alimentario en este paso.

El checkpoint debe contener un grafo inicial válido, todas sus decisiones
pendientes y un requisito de ingeniería dependiente de una norma pendiente.
El supervisor valida la propuesta y llama al `init` real del prototipo;
conserva estado y hashes para una inspección en otro proceso. Una ejecución
iniciada no se vuelve a lanzar. Fallos, streams parciales y salidas ausentes
son parte del resultado.

## Corrección del calendario

El puente managed permitía solicitar un plazo local superior al fijado en
el calendario. Ahora `prepare` rechaza antes de crear archivos; `status` y
`execute` repiten la comprobación antes de iniciar una llamada. El
[recibo](managed_validation.json) registra 172 pruebas combinadas y cinco
regresiones nuevas repetidas por un revisor nativo independiente. No hubo
proveedor real en esas pruebas.

## Alcance de la futura observación CLI

Se reutiliza la autenticación ChatGPT existente sin copiar credenciales;
una clasificación incierta o con API key se rechaza. Se solicita sandbox de
solo lectura y se ignora la configuración del usuario. Las opciones de
ejecución no constituyen aislamiento completo frente a procesos del mismo
UID. El rechazo de herramientas observadas ocurre después de recibir su
traza; no acredita una prohibición preventiva global.

La [documentación oficial del modo no interactivo](https://learn.chatgpt.com/docs/non-interactive-mode)
describe JSONL y salida con esquema; los flags empleados se cotejan además
con la CLI instalada. La telemetría de uso local no autentica al proveedor,
su versión de modelo ni el coste. El corte del proceso local no demuestra
cancelación remota. Faltan límites comunes de tokens, herramientas y coste,
repeticiones, familias/esfuerzos, casos reservados y evaluación ciega. Este
intento no cuenta entre las 24 corridas y no cambia el veredicto **0/5**.

El resultado real, sus comandos y la revisión posterior se registrarán tras
la congelación; esta sección prospectiva no declara que el checkpoint exista.
