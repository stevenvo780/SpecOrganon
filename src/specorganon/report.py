"""Read-only case dossier for a person or a native agent resuming work."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import engine
from .runner import describe_task
from .workflow import PHASES


def _text(value: Any) -> str:
    return re.sub(r"([\\`*_{}\[\]()<>#+.!|~-])", r"\\\1", str(value))


def _json_block(value: Any) -> str:
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    runs = re.findall(r"`+", content)
    fence = "`" * max(3, 1 + max((len(run) for run in runs), default=0))
    return f"{fence}json\n{content}\n{fence}"


def _retirement_lines(item: dict[str, Any]) -> list[str]:
    """Display the engine's evaluated lifecycle and exact historical guards."""
    if not item["retirement_history"]:
        return []
    status = item["retirement_status"]
    labels = {"effective": "efectiva", "invalidated": "invalidada", "superseded": "superada"}
    lines = [
        f"Retirada: {labels[status]} ({status}). Retirado actualmente: {'sí' if item['retired'] else 'no'}.",
        "",
        "La retirada conserva el historial; no acredita aprobación ni validez empírica.",
        "",
    ]
    for record in item["retirement_history"]:
        replacements = ", ".join(
            f"{_text(ref)} v{version}" for ref, version in sorted(record["replacements"].items())
        )
        lines.extend([
            f"Declaración de retirada #{record['seq']}: {_text(record['id'])} v{record['version']}; "
            f"vigente: {'sí' if record['effective'] else 'no'}.",
            "",
            f"Autor de la retirada: {_text(record['actor'])}.",
            "",
            f"Revisión negativa vinculada: #{record['review_seq']}.",
            "",
            f"Reemplazos declarados: {replacements}.",
            "",
            f"Motivo: {_text(record['reason'])}",
            "",
        ])
        if record["issues"]:
            lines.extend(["Problemas de esta retirada:", ""])
            lines.extend(f"- {_text(issue)}" for issue in record["issues"])
            lines.append("")
    return lines


def case_report(path: str | Path) -> dict[str, Any]:
    """Render current artifacts, gates and pending work without writing a case.

    The task and dossier derive from one evaluated state. External trust or
    archived evidence may change later; this read never mixes two snapshots.
    """
    state = engine.get_state(path)
    task = describe_task(state)
    project = state["project"]
    policy = project["approval_policy"]
    limitations = [
        "El informe resume el expediente; no verifica por sí solo la verdad de sus fuentes.",
        "Aceptar fases no demuestra superioridad metodológica ni impacto de campo.",
    ]
    if policy == "local":
        scope = "Desarrollo local con autores y mandato declarados."
        limitations.append(
            "El modo local no autentica identidades ni custodia externa; "
            "sus revisiones y recibos son declaraciones del entorno de trabajo."
        )
    elif policy == "fixture":
        scope = "Fixture sintética para probar la mecánica."
        limitations.append("Las aprobaciones de fixture no representan consentimiento humano real.")
    else:
        scope = "Caso firmado; consultar la confianza vigente de cada compuerta."
        limitations.append("Una firma válida acredita control de una clave; no prueba competencia personal.")

    phases = state["phases"]
    accepted = sum(bool(phases[phase.id]["accepted"]) for phase in PHASES)
    lines = [
        f"# {_text(project['title'])}",
        "",
        scope,
        "",
        f"Revisión del expediente: {state['revision']}. Fases aceptadas: {accepted}/{len(PHASES)}.",
        "",
        "## Siguiente trabajo",
        "",
        _text(task["task"]),
        "",
    ]
    if task["phase"] is not None:
        lines.extend([f"Fase: {_text(task['phase'])}. Acción: {_text(task['action'])}.", ""])
    if task["blockers"]:
        lines.extend(["Bloqueos:", ""])
        lines.extend(f"- {_text(blocker)}" for blocker in task["blockers"])
        lines.append("")
    lines.extend([
        "## Recorrido",
        "",
        "| Frente | Fase | Estado |",
        "| --- | --- | --- |",
    ])
    for phase in PHASES:
        gate = phases[phase.id]
        status = "aceptada" if gate["accepted"] else "lista para revisión" if gate["ready"] else "pendiente"
        lines.append(f"| {_text(phase.front)} | {_text(phase.id)} | {status} |")
    lines.extend(["", "## Artefactos y trazabilidad", ""])
    for item in sorted(state["items"].values(), key=lambda item: item["seq"]):
        lines.extend([
            f"### {_text(item['id'])} · {_text(item['kind'])} · v{item['version']}",
            "",
            _text(item["text"]),
            "",
            f"Autor: {_text(item['author'])}.",
            "",
        ])
        if item["deps"]:
            refs = ", ".join(f"{_text(ref)} v{version}" for ref, version in sorted(item["deps"].items()))
            lines.extend([f"Depende de: {refs}.", ""])
        if item["kind"] in {"norm", "decision"}:
            lines.extend([f"Aprobación vigente: {'sí' if item['approved'] else 'pendiente'}.", ""])
        if item["stale"]:
            lines.extend(["Sus dependencias cambiaron; requiere revisión.", ""])
        if item["contested"]:
            lines.extend(["Tiene una contradicción pendiente.", ""])
        if item["issues"]:
            lines.extend(f"- {_text(issue)}" for issue in item["issues"])
            lines.append("")
        if item["kind"] == "indicator":
            lines.extend(_retirement_lines(item))
        if item["data"]:
            lines.extend([_json_block(item["data"]), ""])
    if not state["items"]:
        lines.extend(["El caso todavía no contiene artefactos.", ""])
    lines.extend(["## Alcance del informe", ""])
    lines.extend(f"- {_text(limit)}" for limit in limitations)
    return {
        "schema": 1,
        "title": project["title"],
        "case_id": project.get("case_id"),
        "approval_policy": policy,
        "revision": state["revision"],
        "accepted_phases": accepted,
        "artifact_count": len(state["items"]),
        "next": task,
        "limitations": limitations,
        "markdown": "\n".join(lines) + "\n",
    }
