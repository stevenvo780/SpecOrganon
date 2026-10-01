# Panel de modelos: investigación previa, sin congelar

**Consulta documental:** 2026-09-26 UTC. Este archivo no registra modelos para la reserva, no verifica acceso o cuotas en este entorno y no autoriza llamadas ni gasto. Los IDs, versiones, límites, telemetría y precios deberán comprobarse de nuevo con los proveedores y el ejecutor elegido **antes** del registro inmutable.

| Familia autorizada o candidata | Dos niveles de capacidad documentados | Control bajo/alto dentro de un mismo modelo | Consecuencia para el protocolo |
| --- | --- | --- | --- |
| Gemini | [`gemini-3.8-flash`](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) y [`gemini-3.5-flash-lite`](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) son IDs publicados para perfiles distintos. | La [guía oficial de pensamiento](https://ai.google.dev/gemini-api/docs/thinking) enumera `low` y `high` para ambos. | Candidato documental para una familia con esfuerzo configurable; falta probar acceso y telemetría efectiva. |
| MiniMax | [`MiniMax-M3` y `MiniMax-M2.7`](https://platform.minimax.io/docs/guides/text-generation) aparecen en la documentación del proveedor. | La [API Responses](https://platform.minimax.io/docs/api-reference/responses-create) acepta valores `low`/`high` para M3, pero declara que **no ajustan la profundidad** de razonamiento; M2.x no permite desactivar razonamiento. | La etiqueta de parámetro no basta para afirmar dos esfuerzos efectivos. MiniMax no satisface por ahora la condición de un modelo bajo/alto dentro de esta familia. |
| Codex / OpenAI API, sujeto a acceso separado | El [catálogo oficial](https://developers.openai.com/api/docs/models) publica `gpt-6-astra` y `gpt-6-sol` como opciones de distinta capacidad. | La [guía de razonamiento](https://developers.openai.com/api/docs/guides/reasoning) documenta `reasoning.effort` bajo y alto. | Candidato documental para la segunda familia; el catálogo API no prueba que esos IDs, versiones, cuotas y telemetría estén disponibles mediante la licencia o el runtime Codex de este proyecto. |

Por ello **Gemini + MiniMax no se congela** como panel para la matriz que exige un modelo bajo/alto por familia. Gemini + Codex/OpenAI API es una hipótesis condicionada a autorización, acceso real, dos niveles de capacidad, versiones estables y medición comparable. El [protocolo](protocolo_experimental.md) exige fijar los cuatro modelos y parámetros antes de abrir los casos reservados; no permite cambiar un modelo por su resultado.

## Actualización pública D-109: 2026-09-30 UTC

El [dossier de activación](../experiments/development/activation_readiness_2026-09-30/README.md)
separa catálogo API, rutas ofrecidas y capacidades efectivamente verificadas.
No ejecuta modelos ni registra un panel.

- La documentación oficial de [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna)
  y [GPT-6 Sol](https://developers.openai.com/api/docs/models/gpt-6-sol) documenta
  `reasoning.effort` bajo y alto. Luna es una opción adicional para tareas acotadas;
  su precio o presencia en la herramienta de delegación no demuestran calidad
  equivalente, versión efectiva o recursos comparables en este estudio.
- El catálogo local `agy models` ofrece Gemini 3.8 Flash bajo/medio/alto y Gemini
  3.1 Pro bajo/alto; no enumeró Flash-Lite. La [guía oficial de pensamiento](https://ai.google.dev/gemini-api/docs/thinking)
  sigue documentando bajo/alto para Flash 3.8 y Flash-Lite 3.5. La lista local no
  autentica que una generación use ese modelo y esfuerzo, y sus nombres no se
  equiparan automáticamente a los IDs de la API.
- La [API Responses de MiniMax](https://platform.minimax.io/docs/api-reference/responses-create)
  ahora documenta que **`MiniMax-M3.1-Flash-Preview` sí ajusta la profundidad** con
  `effort` bajo/alto. M3 y M2.x conservan la limitación descrita en la tabla
  histórica. La fuente restringe actualmente M3.1 Preview a **M Plan y MiniMax
  Code**; no establece disponibilidad mediante API ordinaria de pago por uso.
  La herramienta local solo anunció rutas M3/M2.7, sin M3.1; no se
  verificó acceso, versión estable, telemetría ni dos niveles de capacidad para
  esa nueva combinación. El rechazo anterior corresponde al panel concreto
  M3/M2.7, no a todos los modelos futuros de MiniMax.

Las cuotas consultadas son un snapshot operativo y no acreditan acceso API o
facturación. El contraste confirmatorio continúa pendiente de un panel viable,
límites globales, custodia, evaluadores y autorización; no se cambia el protocolo.

Para hacer cumplir 80 000 tokens por ejecución habrá que medir todas las llamadas y agentes, incluido razonamiento y caché sin contar dos veces los desgloses. Las guías oficiales describen campos de uso para [Gemini](https://ai.google.dev/gemini-api/docs/tokens), [MiniMax Responses](https://platform.minimax.io/docs/api-reference/responses-create) y [OpenAI Responses](https://developers.openai.com/api/docs/guides/reasoning). Una [ruta ejecutable de desarrollo](presupuesto_solicitudes_modelo.md) reserva tokens y coste estimado para solicitudes OpenAI que comparten ledger; encadena turnos de texto y, en un puente separado, una función con herramienta local sellada bajo un plazo de proceso. Todavía **no aplica el límite global de la matriz** a agentes, herramientas y proveedores, ni autentica el gasto. El perfil local lo aporta el operador y no cubre por sí mismo Gemini, MiniMax, herramientas u horas humanas. El cálculo confirmatorio requiere tarifas actuales por tipo de token y herramienta, mezcla prevista de uso, facturación y horas humanas; las páginas de [Google](https://ai.google.dev/gemini-api/docs/pricing), [MiniMax](https://platform.minimax.io/docs/guides/pricing-paygo) y [OpenAI](https://developers.openai.com/api/docs/pricing) son fuentes para un nuevo corte, no precios congelados aquí. Si falla acceso, telemetría o presupuesto, la comparación queda `no demostrado` en vez de reemplazar el panel después de ver resultados.
