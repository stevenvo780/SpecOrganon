"""D113 analysis broker adapter over the unchanged D115 execution engine.

Preparation and status explicitly select the new broker. No module globals are
replaced, and every callback still consumes the original parent ledger/lease.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import local_run_admission as admission
import managed_parallel_tools as engine
import managed_parallel_wave as wave
from managed_run_context import RunContext
from managed_wave_ledger import WaveLedger
from parallel_analysis_broker import AnalysisParallelToolBroker
from run_managed_conversation import (
    _canonical, _new_private_file, _private_dir, _read_json, _run_lock,
)


PROFILE = "parallel_analysis_wave_v1"
CLASSIFICATION = "development_parallel_analysis_wave_unsealed"


class ParallelAnalysisError(ValueError):
    """The explicitly bound analysis adapter cannot proceed."""


def _source_digests() -> dict:
    root = Path(__file__).resolve().parent
    paths = [root / name for name in (
        "managed_parallel_analysis.py", "c_parallel_analysis.py", "parallel_analysis_broker.py")]
    return {str(path): wave._sha(path.read_bytes()) for path in paths}


def bind_analysis_plan(plan: dict) -> dict:
    plan = engine._validate_plan(plan)
    try:
        common = json.loads(plan["context"])
    except ValueError:
        common = {"public_context": plan["context"]}
    if type(common) is not dict:
        raise ParallelAnalysisError("analysis context must be text or a JSON object")
    binding = {"schema": 1, "profile": PROFILE, "source_digests": _source_digests()}
    if "analysis_binding" in common and common["analysis_binding"] != binding:
        raise ParallelAnalysisError("analysis adapter binding differs from current sources")
    common["analysis_binding"] = binding
    plan["context"] = _canonical(common).decode()
    return engine._validate_plan(plan)


def require_analysis_binding(plan: dict) -> None:
    common = json.loads(plan["context"])
    expected = {"schema": 1, "profile": PROFILE, "source_digests": _source_digests()}
    if type(common) is not dict or common.get("analysis_binding") != expected:
        raise ParallelAnalysisError("analysis adapter profile or source closure changed")


def _validate_broker(plan: dict, broker) -> None:
    engine._bind_broker(plan, broker)
    for task in plan["tasks"]:
        functions = broker.branch(task["task_id"])["functions"]
        if len(functions) != 2 or {f["profile"] for f in functions} != {"workspace", "analysis_readonly"}:
            raise ParallelAnalysisError("analysis branches require workspace and D113 readonly functions")


def prepare_analysis_wave(run_dir: Path, plan: dict, *, admission_root: Path | None = None) -> dict:
    plan = bind_analysis_plan(plan)
    require_analysis_binding(plan)
    run_dir = Path(run_dir)
    if not run_dir.is_absolute() or any(part in (".", "..") for part in run_dir.parts):
        raise ParallelAnalysisError("run directory must be absolute")
    _private_dir(run_dir.parent)
    if run_dir.exists() or run_dir.is_symlink():
        raise FileExistsError("analysis wave already exists")
    state = {"schema": 2, "classification": engine.CLASSIFICATION, "state": "prepared",
             "plan_sha256": wave._sha(_canonical(plan)), "run_id": plan["run_id"],
             "admission_descriptor": admission.descriptor(admission_root), "claim_sha256": "",
             "source_digests": engine._sources(), "reason": None, "completed_requests": 0,
             "artifact_count": 0, "cursor": 0, "reviewer_done": False,
             "tool_calls_completed": 0, "merge_result": None, "workers": {}}
    state["claim_sha256"] = admission.claim_digest(**wave._claim_args(run_dir, state))
    run_dir.mkdir(mode=0o700)
    _new_private_file(run_dir / ".lock", b"")
    for name in engine.JOURNALS:
        (run_dir / name).mkdir(mode=0o700)
    _new_private_file(run_dir / "plan.json", _canonical(plan))
    for task in plan["tasks"]:
        directory = run_dir / "histories" / task["task_id"]
        directory.mkdir(mode=0o700)
        history = {"history": engine._initial_history(plan, task)}
        _new_private_file(directory / "run.json", _canonical(history))
        state["workers"][task["task_id"]] = {
            "turns": 0, "finished": False, "history_sha256": wave._sha(_canonical(history))}
    _new_private_file(run_dir / "run.json", _canonical(state))
    broker = AnalysisParallelToolBroker(run_dir, plan["branch_manifest"])
    _validate_broker(plan, broker)
    require_analysis_binding(plan)
    WaveLedger.create(run_dir / "ledger", plan["limit_tokens"], plan["max_model_requests"],
                      cost_limit_micro_usd=plan["cost_limit_micro_usd"],
                      price_profile=plan["price_profile"], effort=plan["effort"])
    bindings = {"ledger_kind": "wave_v1", "ledger_schema": 3, "plan_sha256": state["plan_sha256"],
                "run_id": plan["run_id"], "claim_sha256": state["claim_sha256"],
                "source_digests": state["source_digests"], "branch_manifest": plan["branch_manifest"],
                "analysis_binding": json.loads(plan["context"])["analysis_binding"]}
    RunContext.create(run_dir / "context", run_dir / "ledger", bindings,
                      active_limit_seconds=plan["active_limit_seconds"], max_tool_calls=plan["max_tool_calls"],
                      roles=["coordinator"], ledger_kind="wave_v1",
                      journal_roots=[run_dir / name for name in engine.JOURNALS] +
                      [run_dir / "plan.json", run_dir / "run.json", run_dir / "ledger"] + broker.journal_roots())
    return read_analysis_wave_status(run_dir)


def _status(result: dict) -> dict:
    return {**result, "base_execution_profile": result["execution_profile"],
            "execution_profile": PROFILE, "classification": CLASSIFICATION,
            "caller_graph_required": True, "comparable_development_cell": False}


def read_analysis_wave_status(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    with _run_lock(run_dir):
        plan = engine._validate_plan(_read_json(run_dir / "plan.json"))
        require_analysis_binding(plan)
        broker = AnalysisParallelToolBroker(run_dir, plan["branch_manifest"])
        loaded = engine._load(run_dir, broker)
        plan, state, ledger, context, broker = loaded
        if state["state"] in {"prepared", "paused", "completed"}:
            engine._audit(run_dir, plan, state, ledger, broker)
        require_analysis_binding(plan)
        result = engine._view(run_dir, *loaded)
        require_analysis_binding(plan)
        return _status(result)


def execute_analysis_wave_step(run_dir: Path, transports_by_task: dict, *, expected_checkpoint: str,
                               broker=None, guard: Callable | None = None, merge: Callable | None = None) -> dict:
    run_dir = Path(run_dir)
    plan = engine._validate_plan(_read_json(run_dir / "plan.json"))
    require_analysis_binding(plan)
    broker = broker or AnalysisParallelToolBroker(run_dir, plan["branch_manifest"])
    if not isinstance(broker, AnalysisParallelToolBroker):
        raise ParallelAnalysisError("analysis execution requires its bound broker")

    def checked_guard():
        require_analysis_binding(plan)
        if guard is not None:
            guard()
        require_analysis_binding(plan)

    result = engine.execute_tool_wave_step(
        run_dir, transports_by_task, expected_checkpoint=expected_checkpoint,
        broker=broker, guard=checked_guard, merge=merge)
    require_analysis_binding(plan)
    return _status(result)
