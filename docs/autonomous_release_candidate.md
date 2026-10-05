# Candidato autónomo 0.2.0rc2

Esta preparación parte del commit congelado 3748028166ad1d4ac722f62f4ebf90701d397622.
El cambio de versión ocurre en un checkout separado; no cambia las fuentes de
la campaña activa, sus presupuestos ni sus modelos. Las dependencias de uv.lock
conservan exactamente sus entradas anteriores.

El wheel contiene SpecOrganon y los entrypoints organon y organon-mcp. Los
ejecutores de campañas son módulos del paquete fuente, bajo experiments; no se
instalan como entrypoints del wheel. Su registro vincula el checkout original
y no se puede trasladar a este checkout para seguir una campaña ya iniciada.

La instalación CLI/MCP se verifica con contenido sintético de control y
transporte stdio real. Ese control no cuenta como caso autónomo ni como resultado
comparativo. La entrega real FractionMix de nueve fases se conserva por separado;
la campaña completa y su evaluación reservada siguen pendientes.

Este candidato no acredita eficacia de campo ni la tesis general. La publicación
final requiere cerrar y comunicar todos los resultados del protocolo registrado,
incluidos fallos y mediciones desconocidas.
