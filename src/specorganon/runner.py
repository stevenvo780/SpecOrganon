"""Bounded work instructions and resumable execution of declared case steps.

The ledger is the checkpoint. A manifest supplies content, but cannot supply
human approval or an independent phase review. Those decisions are recorded
through the engine and the same manifest can then be resumed in another process.
"""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import engine
from .ledger import ConflictError, _open_regular_file
from .workflow import KIND_TO_PHASE, KINDS, PHASES, PHASE_BY_ID


ROLE_LABELS = {
    "analyst": "analista",
    "specialist": "especialista",
    "reviewer": "revisor",
    "human": "aprobador humano",
    "executor": "ejecutor externo",
    "observer": "observador externo",
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
MANIFEST_FIELDS = frozenset({'schema', 'name', 'description', 'steps'})
PUT_REQUIRED_FIELDS = frozenset({'op', 'id', 'kind', 'text', 'refs', 'data'})
PUT_OPTIONAL_FIELDS = frozenset({'expected_version', 'expected_deps'})


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


def _retired_indicator(item: dict[str, Any]) -> bool:
    return item["kind"] == "indicator" and item.get("retired", False) is True


def _validate_roles(roles: dict[str, str] | None) -> dict[str, str]:
    if roles is None:
        return {}
    if not isinstance(roles, dict) or any(
        key not in ROLE_LABELS or not isinstance(value, str) or not value.strip()
        for key, value in roles.items()
    ):
        raise ManifestError(
            "roles must map analyst, specialist, reviewer, human, executor or observer to nonempty actor names"
        )
    return {key: value.strip() for key, value in roles.items()}


def next_task(path: str | Path, roles: dict[str, str] | None = None) -> dict[str, Any]:
    """Read one public case snapshot and describe its first unaccepted phase."""
    actors = _validate_roles(roles)
    return describe_task(engine.get_state(path), actors)


def describe_task(state: dict[str, Any], roles: dict[str, str] | None = None) -> dict[str, Any]:
    """Describe the first unaccepted phase without dumping the whole case.

    Derive the task entirely from one public ``engine.get_state`` snapshot;
    do not reread a ledger, registry, trust anchor or source archive.
    Every input and artifact includes its current version. Context is capped;
    callers can use ``engine.trace`` for full text and dependency details.
    Suggested actors are caller supplied, never inferred as authenticated people.
    """
    actors = _validate_roles(roles)
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
        (item for item in items.values()
         if KIND_TO_PHASE[item["kind"]] == phase.id and not _retired_indicator(item)),
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
        and not _retired_indicator(item)
    ]
    prior.sort(key=lambda item: (
        0 if item["id"] in priority_refs else 1,
        input_kinds.index(item["kind"]) if item["kind"] in input_kinds else len(input_kinds),
        -item["seq"],
    ))
    approvals = [item for item in current if item["kind"] in {"norm", "decision"} and not item["approved"]]
    troubled = [item for item in current if item["stale"] or item["contested"] or item["issues"]]
    execution_issues = {
        "signed test needs a current successful signed execution receipt",
        "latest signed test execution failed or timed out",
        "local test needs an exact structured execution receipt",
        "local test needs passed=true",
        "local test execution failed or timed out",
    }
    observation_issues = {
        "signed test needs a current successful observed repeat receipt",
        "latest signed observed repeat failed or its bundle is unavailable",
    }
    execution_targets = [
        item for item in troubled
        if item["kind"] == "test" and not item["stale"] and not item["contested"]
        and any(issue in execution_issues for issue in item["issues"])
        and set(item["issues"]) <= execution_issues | observation_issues
    ]
    observation_targets = [
        item for item in troubled
        if state["project"].get("test_gate_policy", "signed_report") == "signed_observed"
        and item["kind"] == "test" and not item["stale"] and not item["contested"]
        and item.get("test_execution_status") == "signed_passed"
        and item.get("test_observation_status") != "observed_passed"
        and bool(item["issues"]) and set(item["issues"]) <= observation_issues
    ]
    only_execution_pending = bool(execution_targets) and len(execution_targets) == len(troubled) and all(
        entry["kind"] == "test" for entry in missing
    )
    only_observation_pending = (
        bool(observation_targets) and len(observation_targets) == len(troubled)
        and all(entry["kind"] == "test" for entry in missing)
    )
    challenges = state["open_challenges"]
    base_role = "analyst" if phase.front == "philosophy" else "specialist"
    if any(item["contested"] for item in troubled):
        action, role, task = "resolve_contradiction", "reviewer", "Investigar contradicciones; registrar síntesis y revisión independiente antes de continuar."
    elif only_execution_pending:
        action, role = "execute_test", "executor"
        if state["project"]["approval_policy"] == "local":
            task = ("Ejecutar externamente el argv declarado; registrar una nueva versión del test "
                    "con passed, exit_code, timed_out y hashes de streams y resultado en receipt. "
                    "La procedencia es local_declared y no autentica al ejecutor.")
        else:
            task = "Ejecutar externamente el argv declarado; registrar el reporte y la firma Ed25519 del ejecutor."
    elif only_observation_pending:
        action, role, task = (
            "observe_test", "observer",
            "Repetir externamente la ejecución firmada con los insumos fijados; "
            "registrar el recibo de observación y la firma Ed25519 del observador."
        )
    elif troubled:
        action, role, task = "repair_artifacts", base_role, "Corregir artefactos inválidos o referencias a versiones anteriores."
    elif approvals:
        action, role, task = "human_approval", "human", "Decidir explícitamente los compromisos normativos o decisiones pendientes."
    elif not status["ready"] and any(not blocker.startswith("needs ") for blocker in status["blockers"]):
        action, role, task = "repair_artifacts", base_role, "Corregir los vínculos o condiciones metodológicas señaladas por la compuerta."
    elif missing:
        action, role, task = "create_artifacts", base_role, "Producir los artefactos faltantes con contenido y fuentes verificables."
    elif not status["reviewed"]:
        action, role = "review_phase", "reviewer"
        if state["project"]["approval_policy"] == "signed":
            if state["phase_review_trust"] == "configured":
                task = ("Confirmar que el actor revisor elegido tiene clave pública registrada y es distinto "
                        "de los autores; revisar el snapshot vigente, pedir phase-review-challenge "
                        "y registrar la firma Ed25519 externa con review-phase.")
            else:
                task = ("Registrar fuera del caso la clave pública de un revisor competente y distinto "
                        "de los autores; después pedir phase-review-challenge y registrar su firma.")
        else:
            task = "Revisar independientemente el snapshot vigente y registrar veredicto motivado."
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
        "phase_review_trust": state["phase_review_trust"],
        "test_execution_trust": state["test_execution_trust"],
        "test_observation_trust": state.get("test_observation_trust"),
        "inputs_description": phase.inputs,
        "inputs": _limited(prior),
        "artifacts": _limited(current),
        "missing": missing,
        "approval_targets": [{"id": item["id"], "version": item["version"]} for item in approvals[:CONTEXT_LIMIT]],
        "omitted_approval_targets": max(0, len(approvals) - CONTEXT_LIMIT),
        "test_execution_targets": [
            {"id": item["id"], "version": item["version"], "argv": item["data"]["argv"],
             "command": item["data"]["command"]}
            for item in execution_targets[:CONTEXT_LIMIT]
        ],
        "omitted_test_execution_targets": max(0, len(execution_targets) - CONTEXT_LIMIT),
        "test_observation_targets": [
            {"id": item["id"], "version": item["version"],
             "report_provenance": item.get("test_execution_provenance"),
             "observation_status": item.get("test_observation_status")}
            for item in observation_targets[:CONTEXT_LIMIT]
        ],
        "omitted_test_observation_targets": max(0, len(observation_targets) - CONTEXT_LIMIT),
        "criteria": {"exit": phase.exit_rule, "review": phase.review, "stop": phase.stop_rule},
        "gate": {key: status[key] for key in (
            "ready", "reviewed", "independent_review", "review_signature_verified",
            "review_provenance", "accepted", "snapshot",
        )},
        "blockers": [_short(blocker, TEXT_LIMIT) for blocker in status["blockers"][:BLOCKER_LIMIT]],
        "omitted_blockers": max(0, len(status["blockers"]) - BLOCKER_LIMIT),
        "open_challenges": [
            {**challenge, "reason": _short(challenge["reason"], TEXT_LIMIT)}
            for challenge in challenges[:CONTEXT_LIMIT]
        ],
        "omitted_challenges": max(0, len(challenges) - CONTEXT_LIMIT),
    }


def _manifest_steps(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    # JSON numeric 1 (including 1.0) is supported; Boolean true is not a version.
    if (not isinstance(manifest, dict)
            or type(manifest.get("schema")) not in (int, float)
            or manifest["schema"] != 1
            or not isinstance(manifest.get("steps"), list)):
        raise ManifestError("manifest needs schema 1 and a steps array")
    if set(manifest) - MANIFEST_FIELDS:
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
            required = PUT_REQUIRED_FIELDS
            if required - set(step) or set(step) - required - PUT_OPTIONAL_FIELDS:
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
            if "expected_deps" in step:
                deps = step["expected_deps"]
                if (not isinstance(deps, dict) or set(deps) != set(refs)
                        or any(type(version) is not int or version < 1 for version in deps.values())):
                    raise ManifestError(f"step {index} expected_deps must map every ref to a positive version")
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


def _expected_step_deps(steps: list[dict[str, Any]]) -> list[dict[str, int] | None]:
    """Pin each put to declared or earlier manifest item versions."""
    planned_versions: dict[str, int] = {}
    expectations: list[dict[str, int] | None] = []
    for index, step in enumerate(steps):
        if step["op"] != "put":
            expectations.append(None)
            continue
        external_refs = set(step["refs"]) - planned_versions.keys()
        if external_refs and "expected_deps" not in step:
            raise ManifestError(f"step {index} needs expected_deps for external refs: {sorted(external_refs)}")
        deps = (dict(step["expected_deps"]) if "expected_deps" in step
                else {ref: planned_versions[ref] for ref in step["refs"]})
        mismatched = {ref: planned_versions[ref] for ref in step["refs"]
                      if ref in planned_versions and deps[ref] != planned_versions[ref]}
        if mismatched:
            raise ManifestError(f"step {index} expected_deps conflicts with earlier manifest versions: {mismatched}")
        expectations.append(deps)
        planned_versions[step["id"]] = step.get("expected_version", 0) + 1
    return expectations


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


def _pending_reason(task: dict[str, Any], approval_policy: str) -> str:
    if task["action"] == "execute_test" and approval_policy == "local":
        return "local_test_execution_required"
    return {
        "resolve_contradiction": "contradiction",
        "repair_artifacts": "invalid_or_stale_artifact",
        "human_approval": "human_approval_required",
        "execute_test": "signed_test_execution_required",
        "observe_test": "signed_test_observation_required",
        "review_phase": "independent_review_required",
    }.get(task["action"], "manifest_exhausted")


@contextmanager
def _run_lock(path: str | Path) -> Iterator[None]:
    """Serialize all manifest executions for a case without changing the ledger."""
    fd = _open_regular_file(Path(path) / ".organon.runner.lock", os.O_RDWR | os.O_CREAT | os.O_APPEND)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


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


def _json_equal(left: Any, right: Any) -> bool:
    pending = [(left, right)]
    while pending:
        left, right = pending.pop()
        if isinstance(left, bool) or isinstance(right, bool):
            if not isinstance(left, bool) or not isinstance(right, bool) or left != right:
                return False
        elif isinstance(left, (int, float)) or isinstance(right, (int, float)):
            if not isinstance(left, (int, float)) or not isinstance(right, (int, float)) or left != right:
                return False
        elif isinstance(left, dict) or isinstance(right, dict):
            if not isinstance(left, dict) or not isinstance(right, dict) or left.keys() != right.keys():
                return False
            pending.extend((value, right[key]) for key, value in left.items())
        elif isinstance(left, list) or isinstance(right, list):
            if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right):
                return False
            pending.extend(zip(left, right))
        elif isinstance(left, str) or isinstance(right, str):
            if not isinstance(left, str) or not isinstance(right, str) or left != right:
                return False
        elif left is not None or right is not None:
            return False
    return True


def _apply_manifest(path: str | Path, steps: list[dict[str, Any]], actor: str) -> dict[str, Any]:
    state = engine.get_state(path)
    approval_policy = state["project"]["approval_policy"]
    known_ids = set(state["items"])
    for index, step in enumerate(steps):
        if step["op"] == "put":
            unknown = set(step["refs"]) - known_ids
            if unknown:
                raise ManifestError(f"step {index} references unknown or later items: {sorted(unknown)}")
            if step["id"] in step["refs"]:
                raise ManifestError(f"step {index} references itself")
            known_ids.add(step["id"])
    expectations = _expected_step_deps(steps)
    applied = skipped = 0
    for index, step in enumerate(steps):
        state = engine.get_state(path)
        item = state["items"].get(step["id"]) if step["op"] == "put" else None
        if step["op"] == "put":
            expected = step.get("expected_version", 0)
            expected_deps = expectations[index]
            assert expected_deps is not None
            ref_versions = {ref: state["items"][ref]["version"] for ref in step["refs"]}
            if expected_deps != ref_versions:
                raise ManifestError(f"step {index} expected reference versions {expected_deps}, found {ref_versions}")
            if item is not None and item["version"] == expected + 1:
                if ((item["kind"], item["text"], item["deps"]) != (
                    step["kind"], step["text"].strip(), expected_deps
                ) or not _json_equal(item["data"], step["data"])):
                    raise ManifestError(f"step {index} diverges from item {step['id']} version {item['version']}")
                skipped += 1
                continue
            if item is not None and item["version"] != expected:
                raise ManifestError(f"step {index} expected item {step['id']} version {expected}, found {item['version']}")
            if item is None and expected != 0:
                raise ManifestError(f"step {index} expected missing item {step['id']} at version {expected}")
            try:
                engine.put_item(path, step["id"], step["kind"], step["text"], step["refs"], step["data"], actor,
                                expected_version=expected, expected_deps=expected_deps)
            except (engine.MethodError, ConflictError) as exc:
                raise ManifestError(f"step {index} failed: {exc}") from exc
            applied += 1
        else:
            phase_id = step["phase"]
            if state["phases"][phase_id]["accepted"]:
                skipped += 1
                continue
            status = state["phases"][phase_id]
            if not status["ready"]:
                return _response(path, "waiting", index, len(steps), applied, skipped,
                                 _pending_reason(next_task(path), approval_policy))
            if not status["reviewed"] or not status["independent_review"]:
                return _response(path, "waiting", index, len(steps), applied, skipped, "independent_review_required")
            try:
                engine.advance(path, phase_id, actor)
            except engine.MethodError as exc:
                raise ManifestError(f"step {index} failed: {exc}") from exc
            applied += 1
    next_up = next_task(path)
    status = "complete" if next_up["status"] == "done" else "waiting"
    reason = None if status == "complete" else _pending_reason(next_up, approval_policy)
    return _response(path, status, len(steps), len(steps), applied, skipped, reason)
