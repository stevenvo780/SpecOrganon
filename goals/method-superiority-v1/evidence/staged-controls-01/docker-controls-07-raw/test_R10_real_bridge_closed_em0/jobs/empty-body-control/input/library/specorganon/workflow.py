"""Phase contract for a revisable philosophy → science → engineering workflow."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Phase:
    id: str
    front: str
    purpose: str
    inputs: str
    required: tuple[tuple[str, int], ...]
    exit_rule: str
    review: str
    stop_rule: str


PHASES = (
    Phase("frame", "philosophy", "Delimitar el problema, actores y frontera.", "Encargo y contexto del caso.", (("problem", 1), ("actor", 1), ("boundary", 1)), "La formulación nombra el daño o necesidad, los afectados y el límite de observación.", "Revisar exclusiones y formulaciones rivales.", "Detener si el problema no puede delimitarse o falta un actor afectado decisivo."),
    Phase("critique", "philosophy", "Examinar conceptos, supuestos, alternativas y fines.", "Formulación y testimonios de actores.", (("concept", 1), ("assumption", 1), ("frame_option", 2), ("norm", 1)), "Los juicios sobre lo deseable están separados de las afirmaciones fácticas y la opción normativa está aprobada por una persona.", "Revisar conflictos de valor y fundamentos de cada alternativa.", "Detener ante conflicto normativo sin decisión humana o definición circular."),
    Phase("study", "science", "Diseñar investigación verificable.", "Preguntas derivadas del encuadre.", (("question", 1), ("hypothesis", 1), ("protocol", 1), ("indicator", 1)), "Protocolo, hipótesis e indicador fijan unidad, fuente, comparación e incertidumbre antes del resultado.", "Revisar sesgos, factibilidad y ética de medición.", "Detener si no se puede distinguir dato, inferencia y supuesto."),
    Phase("observe", "science", "Recaudar y clasificar evidencia.", "Protocolo registrado y fuentes accesibles.", (("evidence", 1), ("inference", 1)), "Cada evidencia conserva fuente, fecha, alcance y origen; cada inferencia enlaza datos.", "Revisar calidad de fuente, cobertura y contradicciones.", "Detener ante dato insuficiente o contradicción sin resolver."),
    Phase("explain", "science", "Contrastar hipótesis y condiciones materiales.", "Evidencias e inferencias vigentes.", (("synthesis", 1), ("uncertainty", 1)), "La síntesis distingue hallazgos, supuestos y límites; la incertidumbre queda explícita.", "Revisar alternativas explicativas y sesgos.", "Detener si la conclusión excede sus datos."),
    Phase("compare", "engineering", "Comparar intervenciones materiales y organizativas.", "Síntesis y compromisos normativos vigentes.", (("option", 2), ("comparison", 1), ("risk", 1)), "La comparación incluye efectos por actor, coste, riesgo y alternativa sin software cuando proceda.", "Revisar opciones dominadas y perjuicios desplazados.", "Detener si solo se evaluó la primera idea o falta una restricción de seguridad."),
    Phase("specify", "engineering", "Justificar decisiones y escribir SDD verificable.", "Comparación, evidencia y aprobación humana.", (("decision", 1), ("requirement", 1), ("criterion", 1)), "Cada requisito y criterio traza a problema, norma aprobada y evidencia; el criterio precede al resultado.", "Revisar consistencia entre spec, decisión y prueba.", "Detener ante requisito huérfano o criterio ajustado tras ver el resultado."),
    Phase("build", "engineering", "Implementar y probar la intervención.", "Requisitos y criterios versionados.", (("implementation", 1), ("test", 1)), "La implementación enlaza requisitos y las pruebas ejecutadas enlazan criterio e implementación.", "Revisar riesgos técnicos y efectos materiales.", "Detener ante prueba fallida o control de seguridad ausente."),
    Phase("validate", "validation", "Medir eficacia y daños contra línea base.", "Criterios prerregistrados e intervención ejecutada.", (("baseline", 1), ("result", 1), ("assessment", 1)), "El veredicto distingue técnico, simulado y observado y evalúa costes, daños e incertidumbre.", "Revisión independiente del diseño causal y de los resultados.", "Detener sin atribución razonable o ante daño crítico; declarar no demostrado cuando falte campo."),
)

PHASE_BY_ID = {phase.id: phase for phase in PHASES}
KIND_TO_PHASE = {kind: phase.id for phase in PHASES for kind, _ in phase.required}
KINDS = frozenset(KIND_TO_PHASE)
