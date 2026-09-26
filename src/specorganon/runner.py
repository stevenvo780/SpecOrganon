"""Bounded work instructions and resumable execution of declared case steps.

The ledger is the checkpoint. A manifest supplies content, but cannot supply
human approval or an independent phase review. Those decisions are recorded
through the engine and the same manifest can then be resumed in another process.
"""

from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import engine
from .workflow import KIND_TO_PHASE, KINDS, PHASES, PHASE_BY_ID


ROLE_LABELS = {
    "analyst": "analista",
    "specialist": "especialista",
    "reviewer": "revisor",
    "human": "aprobador humano",
}
PHASE_INPUT_KINDS = {
    "frame": (),
    "critique": ("problem", "actor", "boundary"),
    "study": ("problem", "norm", "concept", "assumption"),
    "observe": ("protocol", "indicator", "hypothesis", "question"),
    "explain": ("evidence", "inference", "hypothesis", "protocol"),
    "compare": ("synthesis", "uncertainty", "norm", "evidence"),
    "specify": ("comparison", "option", "risk", "norm", "evidence", "problem"),
    "build": ("requirement", "criterion", "decision"),
    "validate": ("criterion", "risk", "implementation", "test", "indicator"),
}
CONTEXT_LIMIT = 24
TEXT_LIMIT = 280
DATA_LIMIT = 560
BLOCKER_LIMIT = 24
REF_LIMIT = 12
PHASE_INDEX = {phase.id: index for index, phase in enumerate(PHASES)}


class ManifestError(engine.MethodError):
    """The declarative case plan is malformed or diverges from its checkpoint."""


def _short(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _item_context(item: dict[str, Any]) -> dict[str, Any]:
    refs = list(item["deps"].items())
    return {
        "id": item["id"],
        "kind": item["kind"],
        "version": item["version"],
        "text": _short(item["text"], TEXT_LIMIT),
        "data": _short(json.dumps(item["data"], ensure_ascii=False, sort_keys=True), DATA_LIMIT),
        "refs": dict(refs[:REF_LIMIT]),
        "omitted_refs": max(0, len(refs) - REF_LIMIT),
        "stale": item["stale"],
        "contested": item["contested"],
        "issues": [_short(issue, TEXT_LIMIT) for issue in item["issues"][:4]],
        "omitted_issues": max(0, len(item["issues"]) - 4),
        "approved": item["approved"] if item["kind"] in {"norm", "decision"} else None,
    }


def _limited(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "items": [_item_context(item) for item in items[:CONTEXT_LIMIT]],
        "omitted": max(0, len(items) - CONTEXT_LIMIT),
    }


def _validate_roles(roles: dict[str, str] | None) -> dict[str, str]:
    if roles is None:
        return {}
    if not isinstance(roles, dict) or any(
        key not in ROLE_LABELS or not isinstance(value, str) or not value.strip()
        for key, value in roles.items()
    ):
        raise ManifestError("roles must map analyst, specialist, reviewer or human to nonempty actor names")
    return {key: value.strip() for key, value in roles.items()}


def next_task(path: str | Path, roles: dict[str, str] | None = None) -> dict[str, Any]:
    """Describe the first unaccepted phase without dumping the whole case.

    Every input and artifact includes its current version. Context is capped;
    callers can use ``engine.trace`` for full text and dependency details.
    Suggested actors are caller supplied, never inferred as authenticated people.
    """
    actors = _validate_roles(roles)
    state = engine.get_state(path)
    phase = next((phase for phase in PHASES if not state["phases"][phase.id]["accepted"]), None)
    if phase is None:
        return {
            "status": "done", "revision": state["revision"], "phase": None,
            "role": None, "actor": None, "action": "complete", "task": "Todas las fases tienen avance vigente.",
            "inputs": {"items": [], "omitted": 0}, "artifacts": {"items": [], "omitted": 0},
            "missing": [], "criteria": None, "blockers": [], "open_challenges": [],
        }

    status = state["phases"][phase.id]
    items = state["items"]
    current = sorted(
        (item for item in items.values() if KIND_TO_PHASE[item["kind"]] == phase.id),
        key=lambda item: item["seq"], reverse=True,
    )
    valid_counts = {
        kind: sum(
            item["kind"] == kind and not item["stale"] and not item["contested"] and not item["issues"]
            for item in current
        )
        for kind, _ in phase.required
    }
    missing = [
        {"kind": kind, "required": minimum, "valid": valid_counts[kind], "remaining": minimum - valid_counts[kind]}
        for kind, minimum in phase.required if valid_counts[kind] < minimum
    ]
    priority_refs = {ref for item in current for ref in item["deps"] if ref in items}
    input_kinds = PHASE_INPUT_KINDS[phase.id]
    prior = [
        item for item in items.values()
        if PHASE_INDEX[KIND_TO_PHASE[item["kind"]]] < PHASE_INDEX[phase.id]
        and (item["id"] in priority_refs or item["kind"] in input_kinds)
    ]
    prior.sort(key=lambda item: (
        0 if item["id"] in priority_refs else 1,
        input_kinds.index(item["kind"]) if item["kind"] in input_kinds else len(input_kinds),
        -item["seq"],
    ))
    approvals = [item for item in current if item["kind"] in {"norm", "decision"} and not item["approved"]]
    troubled = [item for item in current if item["stale"] or item["contested"] or item["issues"]]
    challenges = state["open_challenges"]
    base_role = "analyst" if phase.front == "philosophy" else "specialist"
    if any(item["contested"] for item in troubled):
        action, role, task = "resolve_contradiction", "reviewer", "Investigar contradicciones; registrar síntesis y revisión independiente antes de continuar."
    elif troubled:
        action, role, task = "repair_artifacts", base_role, "Corregir artefactos inválidos o referencias a versiones anteriores."
    elif approvals:
        action, role, task = "human_approval", "human", "Decidir explícitamente los compromisos normativos o decisiones pendientes."
    elif not status["ready"] and any(not blocker.startswith("needs ") for blocker in status["blockers"]):
        action, role, task = "repair_artifacts", base_role, "Corregir los vínculos o condiciones metodológicas señaladas por la compuerta."
    elif missing:
        action, role, task = "create_artifacts", base_role, "Producir los artefactos faltantes con contenido y fuentes verificables."
    elif not status["reviewed"]:
        action, role, task = "review_phase", "reviewer", "Revisar independientemente el snapshot vigente y registrar veredicto motivado."
    elif not status["independent_review"]:
        action, role, task = "review_phase", "reviewer", "Obtener una revisión aceptada por un actor distinto de los autores de la fase."
    else:
        action, role, task = "advance_phase", "analyst", "Registrar avance de la fase tras su revisión vigente."

    return {
        "status": "pending",
        "revision": state["revision"],
        "phase": phase.id,
        "front": phase.front,
        "purpose": phase.purpose,
        "role": role,
        "role_label": ROLE_LABELS[role],
        "actor": actors.get(role),
        "action": action,
        "task": task,
        "inputs_description": phase.inputs,
        "inputs": _limited(prior),
        "artifacts": _limited(current),
        "missing": missing,
        "approval_targets": [{"id": item["id"], "version": item["version"]} for item in approvals[:CONTEXT_LIMIT]],
        "omitted_approval_targets": max(0, len(approvals) - CONTEXT_LIMIT),
        "criteria": {"exit": phase.exit_rule, "review": phase.review, "stop": phase.stop_rule},
        "gate": {key: status[key] for key in ("ready", "reviewed", "independent_review", "accepted", "snapshot")},
        "blockers": [_short(blocker, TEXT_LIMIT) for blocker in status["blockers"][:BLOCKER_LIMIT]],
        "omitted_blockers": max(0, len(status["blockers"]) - BLOCKER_LIMIT),
        "open_challenges": [
            {**challenge, "reason": _short(challenge["reason"], TEXT_LIMIT)}
            for challenge in challenges[:CONTEXT_LIMIT]
        ],
        "omitted_challenges": max(0, len(challenges) - CONTEXT_LIMIT),
    }


def _manifest_steps(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict) or manifest.get("schema") != 1 or not isinstance(manifest.get("steps"), list):
        raise ManifestError("manifest needs schema 1 and a steps array")
    if set(manifest) - {"schema", "name", "description", "steps"}:
        raise ManifestError("unknown manifest fields")
    if "name" in manifest and (not isinstance(manifest["name"], str) or not manifest["name"].strip()):
        raise ManifestError("manifest name must be a nonempty string")
    seen_ids: set[str] = set()
    seen_advances: set[str] = set()
    for index, step in enumerate(manifest["steps"]):
        if not isinstance(step, dict):
            raise ManifestError(f"step {index} must be an object")
        op = step.get("op")
        if op == "put":
            required = {"op", "id", "kind", "text", "refs", "data"}
            if required - set(step) or set(step) - required - {"expected_version"}:
                raise ManifestError(f"step {index} has missing or unknown put fields")
            if not isinstance(step["id"], str) or not engine.ITEM_ID.fullmatch(step["id"]):
                raise ManifestError(f"step {index} has invalid item id")
            if step["id"] in seen_ids:
                raise ManifestError(f"step {index} repeats item id {step['id']}")
            seen_ids.add(step["id"])
            if not isinstance(step["kind"], str) or step["kind"] not in KINDS or not isinstance(step["text"], str) or not step["text"].strip():
                raise ManifestError(f"step {index} needs valid kind and nonempty text")
            refs = step["refs"]
            if not isinstance(refs, list) or any(not isinstance(ref, str) or not engine.ITEM_ID.fullmatch(ref) for ref in refs) or len(refs) != len(set(refs)):
                raise ManifestError(f"step {index} needs distinct item ids in refs")
            if not isinstance(step["data"], dict):
                raise ManifestError(f"step {index} data must be an object")
            expected = step.get("expected_version", 0)
            if type(expected) is not int or expected < 0:
                raise ManifestError(f"step {index} expected_version must be a nonnegative integer")
        elif op == "advance":
            if set(step) != {"op", "phase"} or not isinstance(step["phase"], str) or step["phase"] not in PHASE_BY_ID:
                raise ManifestError(f"step {index} needs a known phase")
            if step["phase"] in seen_advances:
                raise ManifestError(f"step {index} repeats phase advance {step['phase']}")
            seen_advances.add(step["phase"])
        else:
            raise ManifestError(f"step {index} has unsupported op: {op}")
    try:
        json.dumps(manifest, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ManifestError("manifest must contain finite JSON values") from exc
    return manifest["steps"]


def _response(path: str | Path, status: str, cursor: int, total: int, applied: int, skipped: int, reason: str | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "cursor": cursor,
        "total_steps": total,
        "applied": applied,
        "skipped": skipped,
        "reason": reason,
        "next": next_task(path),
    }


def _pending_reason(task: dict[str, Any]) -> str:
    return {
        "resolve_contradiction": "contradiction",
        "repair_artifacts": "invalid_or_stale_artifact",
        "human_approval": "human_approval_required",
        "review_phase": "independent_review_required",
    }.get(task["action"], "manifest_exhausted")


@contextmanager
def _run_lock(path: str | Path) -> Iterator[None]:
    """Serialize manifest replays across processes without changing the ledger."""
    with (Path(path) / ".organon.runner.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def run_manifest(path: str | Path, manifest: dict[str, Any], actor: str) -> dict[str, Any]:
    """Apply declared ``put`` and ``advance`` steps, pausing at real decisions.

    Structural errors fail before mutation. Semantic conflicts raise a
    ``ManifestError`` at the affected step; preceding events remain valid
    checkpoints. Replaying completed steps makes no new events. The caller
    must record approvals and independent phase reviews through the engine.
    """
    steps = _manifest_steps(manifest)
    if not isinstance(actor, str) or not actor.strip():
        raise ManifestError("runner actor must be a nonempty executor name")
    # Fail before the first write when no project exists or its chain is broken.
    engine.get_state(path)
    with _run_lock(path):
        return _apply_manifest(path, steps, actor)


def _apply_manifest(path: str | Path, steps: list[dict[str, Any]], actor: str) -> dict[str, Any]:
    state = engine.get_state(path)
    known_ids = set(state["items"])
    for index, step in enumerate(steps):
        if step["op"] == "put":
            unknown = set(step["refs"]) - known_ids
            if unknown:
                raise ManifestError(f"step {index} references unknown or later items: {sorted(unknown)}")
            if step["id"] in step["refs"]:
                raise ManifestError(f"step {index} references itself")
            known_ids.add(step["id"])
    applied = skipped = 0
    for index, step in enumerate(steps):
        state = engine.get_state(path)
        item = state["items"].get(step["id"]) if step["op"] == "put" else None
        if step["op"] == "put":
            expected = step.get("expected_version", 0)
            ref_versions = {ref: state["items"][ref]["version"] for ref in step["refs"]}
            if item is not None and item["version"] == expected + 1:
                if (item["kind"], item["text"], item["deps"], item["data"]) != (
                    step["kind"], step["text"].strip(), ref_versions, step["data"]
                ):
                    raise ManifestError(f"step {index} diverges from item {step['id']} version {item['version']}")
                skipped += 1
                continue
            if item is not None and item["version"] != expected:
                raise ManifestError(f"step {index} expected item {step['id']} version {expected}, found {item['version']}")
            if item is None and expected != 0:
                raise ManifestError(f"step {index} expected missing item {step['id']} at version {expected}")
            try:
                engine.put_item(path, step["id"], step["kind"], step["text"], step["refs"], step["data"], actor)
            except engine.MethodError as exc:
                raise ManifestError(f"step {index} failed: {exc}") from exc
            applied += 1
        else:
            phase_id = step["phase"]
            if state["phases"][phase_id]["accepted"]:
                skipped += 1
                continue
            status = state["phases"][phase_id]
            if not status["ready"]:
                return _response(path, "waiting", index, len(steps), applied, skipped, _pending_reason(next_task(path)))
            if not status["reviewed"] or not status["independent_review"]:
                return _response(path, "waiting", index, len(steps), applied, skipped, "independent_review_required")
            try:
                engine.advance(path, phase_id, actor)
            except engine.MethodError as exc:
                raise ManifestError(f"step {index} failed: {exc}") from exc
            applied += 1
    next_up = next_task(path)
    status = "complete" if next_up["status"] == "done" else "waiting"
    reason = None if status == "complete" else _pending_reason(next_up)
    return _response(path, status, len(steps), len(steps), applied, skipped, reason)
