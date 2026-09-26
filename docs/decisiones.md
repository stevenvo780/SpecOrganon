# Registro de decisiones

Las decisiones son revisables: una fuente nueva o un experimento adverso debe indicar qué supuesto invalida y qué artefactos dependen de él. Los resultados de los prototipos se documentarán antes de escoger el motor de workflow.

## D-001 · Distribución local en Python y MCP oficial (provisional)

- **Fecha:** 2026-09-26 UTC.
- **Problema:** ofrecer un CLI instalable y un servidor MCP descubierto e invocado por un cliente real, con lógica compartida.
- **Opciones consideradas:** Python con SDK MCP oficial; TypeScript con SDK MCP oficial; protocolo JSON-RPC escrito a mano.
- **Razón de selección provisional:** el entorno tiene Python 3.11/3.12 y `uv`; la instalación aislada resolvió y ejecutó `mcp==2.2.0`. La API oficial expone `MCPServer`, `Client` y transporte stdio, por lo que un test puede lanzar el servidor como subproceso sin falsificar el protocolo. Escribir JSON-RPC propio introduciría riesgo de compatibilidad innecesario. La elección de lenguaje no decide aún la metodología.
- **Evidencia:** `uv sync --extra dev` resolvió 37 paquetes e instaló `mcp==2.2.0`; una inspección local confirmó `MCPServer.run(transport='stdio')`, `Client.list_tools` y `Client.call_tool`. [Documentación oficial del SDK](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/get-started/first-steps.md).
- **Riesgo y revisión:** la serie 2.x es reciente; fijar el lockfile y verificar instalación limpia y cliente real. Si el SDK bloquea el transporte o complica despliegue, reabrir esta decisión con prueba comparativa.

## D-002 · Grafo revisable como núcleo de la siguiente iteración

- **Fecha:** 2026-09-26 UTC. **Estado:** elección de implementación provisional; ventaja global de la metodología no demostrada.
- **Problema:** una contradicción o cambio de supuesto posterior debe reabrir decisiones y requisitos dependientes sin convertir las fases en cascada rígida.
- **Opciones:** A, etapas con compuertas locales; B, grafo de evidencias y dependencias; C, grafo con cola de riesgos y posible exploración paralela. Los tres tienen prototipos ejecutables y el [comparador](../prototypes/compare.py) ejecutó los mismos once escenarios por motor.
- **Evidencia:** `python3 prototypes/compare.py --output prototypes/results/compare.json` y `python3 prototypes/check_results.py prototypes/results/compare.json` dieron `PASS: 33 scenario/mode runs`. En contradicción tardía, cambio de versión de evidencia y cambio de supuesto, A mantuvo fases dependientes aceptadas; B y C las reabrieron. En recuperación A necesitó 4 comandos y B/C 6, un coste real de la trazabilidad. C pudo adelantar ciencia bajo dependencias vigentes, pero su puntaje de riesgo no fue validado ni ejecutó agentes en paralelo.
- **Decisión:** construir el motor compartido sobre B, con fases y revisión, referencias versionadas e invalidación automática. Mantener la exploración anticipada y prioridad de C como hipótesis para una ronda futura, sin activar su puntaje arbitrario como criterio decisorio. Rechazar A como núcleo para problemas con premisas mutables por su falso avance observado.
- **Límite:** las once fixtures son sintéticas, las rondas son desarrollo incremental y no repeticiones independientes. No prueban calidad de intervención, reducción de tiempo, coordinación real ni impacto alimentario. Reabrir la selección si las comparaciones reservadas muestran que el coste o aristas omitidas anulan la ventaja, o si C demuestra mejor desempeño bajo presupuesto equivalente.
