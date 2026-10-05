# Laboratorio SpecOrganon

Usa el MCP `specorganon` para crear y consultar los casos en `/workspace/cases`.
Lee `.agents/skills/specorganon/SKILL.md` para aplicar el método.
El paquete está instalado en `/opt/specorganon/venv`: `organon` y `organon-mcp`
están en PATH. En este contenedor usa `organon` directamente, sin `uv run`.
Los contratos se encuentran en `/workspace/docs`.

Cada prueba debe crear un caso nuevo, conservar su ledger y guardar resultados
bajo `/workspace/results`. Usa `approval_policy="local"` y `actor="human:owner"`
cuando el encargo autorice un caso local; es una etiqueta declarativa del dueño.
Conserva el mandato real y los bloqueos pendientes. No inventes revisiones,
consentimiento, resultados de tests ni evidencia de campo. La variable
`ORGANON_ALLOW_FIXTURES` permanece desactivada para las sesiones de Codex.
Una prueba técnica de transporte no demuestra eficacia del método.
