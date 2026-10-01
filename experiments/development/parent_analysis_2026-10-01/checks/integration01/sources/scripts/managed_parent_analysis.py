"""Opt-in leader bootstrap and private analysis under one durable budget.

This development parent never prepares a nested run. Its local active clock,
declared prices and synthetic transports do not authenticate provider activity.
"""

from __future__ import annotations

import ast
import json
import math
import re
from pathlib import Path
from typing import Any, Callable

import local_run_admission as admission
import managed_parallel_tools as tools
import managed_parallel_wave as wave
from managed_parallel_analysis import require_analysis_binding
from managed_run_context import RunContext
from managed_token_ledger import BudgetError, _price_profile
from managed_wave_ledger import WaveLedger
from parent_analysis_broker import ParentAnalysisBroker
from run_managed_conversation import (
    _canonical, _new_private_file, _private_dir, _read_json, _run_lock, _write_state,
)
from run_managed_response import MAX_JSON_BYTES, _json_bytes, _validate_function_tool
from tool_policy import _read_bounded_file


PROFILE = "parent_analysis_wave_v1"
CLASSIFICATION = "development_parent_analysis_unsealed"
JOURNALS = (*tools.JOURNALS, "seed", "transitions")
PLAN_KEYS = {
    "schema", "execution_profile", "run_id", "context", "model", "effort",
    "price_profile", "limit_tokens", "max_model_requests", "cost_limit_micro_usd",
    "active_limit_seconds", "max_tool_calls", "tool_wall_seconds", "functions",
    "bootstrap_manifest", "leader", "workers", "reviewer", "journal_roots",
}
STATE_KEYS = {
    "schema", "classification", "state", "phase", "plan_sha256", "run_id",
    "admission_descriptor", "claim_sha256", "source_digests", "reason",
    "completed_requests", "artifact_count", "cursor", "tool_calls_completed",
    "leader", "workers", "transition", "reviewer_done", "merge_result",
}
SCALARS = {
    "model", "effort", "price_profile", "limit_tokens", "max_model_requests",
    "cost_limit_micro_usd", "active_limit_seconds", "max_tool_calls", "tool_wall_seconds",
}
_SOURCE_CACHE: tuple[dict[str, str], set[str]] | None = None


class ParentAnalysisError(ValueError):
    """The parent cannot authorize another local effect or publication."""


def _sources() -> dict[str, str]:
    global _SOURCE_CACHE
    root = Path(__file__).resolve().parent
    if _SOURCE_CACHE is not None:
        digests, candidates = _SOURCE_CACHE
        existing = {name for name in candidates if (root / (name + ".py")).is_file()}
        if existing == {Path(path).stem for path in digests}:
            current = {path: wave._sha((root / Path(path).name).read_bytes()) for path in digests}
            if current == digests:
                return current
    pending = [Path(__file__).stem, "parent_analysis_broker", "c_parent_analysis"]
    seen, captured, candidates = set(), {}, set(pending)
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        path = root / (name + ".py")
        raw = path.read_bytes()
        seen.add(name)
        captured["scripts/" + name + ".py"] = wave._sha(raw)
        for node in ast.walk(ast.parse(raw)):
            names = ([item.name.split(".")[0] for item in node.names]
                     if isinstance(node, ast.Import) else
                     [node.module.split(".")[0]]
                     if isinstance(node, ast.ImportFrom) and node.module else [])
            candidates.update(names)
            pending.extend(name for name in names if (root / (name + ".py")).is_file())
    if any(wave._sha((root / Path(path).name).read_bytes()) != digest
           for path, digest in captured.items()):
        raise ParentAnalysisError("source closure changed during capture")
    captured = dict(sorted(captured.items()))
    _SOURCE_CACHE = (captured, candidates)
    return captured.copy()


def _binding(value: Any) -> dict:
    if (type(value) is not dict or set(value) != {"path", "sha256"}
            or type(value["path"]) is not str or not Path(value["path"]).is_absolute()
            or ".." in Path(value["path"]).parts
            or type(value["sha256"]) is not str
            or re.fullmatch("[0-9a-f]{64}", value["sha256"]) is None):
        raise ParentAnalysisError("invalid manifest binding")
    return value


def _validate_plan(raw: Any) -> dict:
    if (type(raw) is not dict or set(raw) != PLAN_KEYS or type(raw["schema"]) is not int
            or raw["schema"] != 1 or raw["execution_profile"] != PROFILE):
        raise ParentAnalysisError("invalid strict parent plan")
    wave._identifier(raw["run_id"], "parent run_id")
    if not raw["run_id"].startswith("parent-wave-"):
        raise ParentAnalysisError("parent requires a new parent-wave- identity")
    for field in ("model", "effort"):
        wave._text(raw[field], field, 256)
    wave._text(raw["context"], "public context")
    profile = _price_profile(raw["price_profile"])
    if profile["model"] != raw["model"]:
        raise ParentAnalysisError("declared price profile model differs")
    limit = wave._integer(raw["limit_tokens"], 1, 80000, "parent token cap")
    wave._integer(raw["max_model_requests"], 1, 128, "parent request cap")
    wave._integer(raw["cost_limit_micro_usd"], 0, 10**15, "parent cost cap")
    wave._integer(raw["max_tool_calls"], 1, 64, "parent tool cap")
    for field, cap in (("active_limit_seconds", 5400), ("tool_wall_seconds", 300)):
        value = raw[field]
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= cap:
            raise ParentAnalysisError("invalid " + field)
    leader = raw["leader"]
    if (type(leader) is not dict or set(leader) != {
            "task_id", "role", "user", "max_output_tokens", "max_model_turns"}
            or leader["task_id"] != "leader" or leader["role"] != "leader"):
        raise ParentAnalysisError("single bootstrap leader has invalid fields")
    wave._text(leader["user"], "leader task")
    wave._integer(leader["max_output_tokens"], 1, limit, "leader output cap")
    wave._integer(leader["max_model_turns"], 2, 32, "leader turn cap")
    workers = raw["workers"]
    if type(workers) is not dict or set(workers) != {"count", "max_output_tokens", "max_model_turns"}:
        raise ParentAnalysisError("invalid deferred worker policy")
    wave._integer(workers["count"], 2, 4, "worker slots")
    wave._integer(workers["max_output_tokens"], 1, limit, "worker output cap")
    wave._integer(workers["max_model_turns"], 1, 32, "worker turn cap")
    reviewer = raw["reviewer"]
    if type(reviewer) is not dict or set(reviewer) != {"user", "max_output_tokens"}:
        raise ParentAnalysisError("invalid reviewer policy")
    wave._text(reviewer["user"], "reviewer task")
    wave._integer(reviewer["max_output_tokens"], 1, limit, "reviewer output cap")
    functions = raw["functions"]
    if type(functions) is not list or len(functions) != 2:
        raise ParentAnalysisError("parent requires its two sealed provider functions")
    names = set()
    for function in functions:
        if type(function) is not dict or set(function) != {"type", "name", "description", "parameters", "strict"}:
            raise ParentAnalysisError("functions contain only provider fields")
        _validate_function_tool(function)
        names.add(function["name"])
    if names != {"development_method", "development_analysis"}:
        raise ParentAnalysisError("unexpected parent provider functions")
    _binding(raw["bootstrap_manifest"])
    roots = raw["journal_roots"]
    if (type(roots) is not list or not roots or len(roots) > 16
            or any(type(path) is not str or not Path(path).is_absolute()
                   or ".." in Path(path).parts for path in roots)):
        raise ParentAnalysisError("invalid fixed external journal roots")
    if len(_canonical(raw)) > MAX_JSON_BYTES:
        raise ParentAnalysisError("parent plan exceeds JSON cap")
    return json.loads(_canonical(raw))


def _initial_history(plan: dict, task: dict) -> list:
    content = {"common_context": plan["context"], "task": task["user"],
               "task_id": task["task_id"], "role": task["role"]}
    if "owned_node_ids" in task:
        content["owned_node_ids"] = task["owned_node_ids"]
    return [{"role": "user", "content": _json_bytes(content).decode()}]


def _artifact(task: dict, text: str) -> dict:
    value = {"task_id": task["task_id"], "role": task["role"], "text": text}
    if "owned_node_ids" in task:
        value["owned_node_ids"] = task["owned_node_ids"]
    value["artifact_sha256"] = wave._sha(_canonical(value))
    return value


def _new_history(run_dir: Path, plan: dict, task: dict) -> dict:
    directory = run_dir / "histories" / task["task_id"]
    directory.mkdir(mode=0o700)
    value = {"history": _initial_history(plan, task)}
    _new_private_file(directory / "run.json", _canonical(value))
    return {"turns": 0, "finished": False, "history_sha256": wave._sha(_canonical(value))}


def _bindings(plan: dict, state: dict) -> dict:
    return {"ledger_kind": "wave_v1", "ledger_schema": 3, "profile": PROFILE,
            "plan_sha256": state["plan_sha256"], "run_id": plan["run_id"],
            "claim_sha256": state["claim_sha256"], "source_digests": state["source_digests"],
            "bootstrap_manifest": plan["bootstrap_manifest"], "journal_roots": plan["journal_roots"]}


def _journal_roots(run_dir: Path, plan: dict, broker) -> list[Path]:
    roots = [run_dir / folder for folder in JOURNALS]
    roots.extend([run_dir / "plan.json", run_dir / "run.json", run_dir / "ledger"])
    for path in [*map(Path, plan["journal_roots"]), *broker.journal_roots()]:
        if path not in roots:
            roots.append(path)
    return roots


def _check_context(run_dir: Path, plan: dict, state: dict, broker) -> None:
    captured = _read_json(run_dir / "context/run.json")
    if (captured["bindings"] != _bindings(plan, state) or captured["roles"] != ["coordinator"]
            or captured["ledger_dir"] != str(run_dir / "ledger")
            or captured["active_limit_seconds"] != plan["active_limit_seconds"]
            or captured["max_tool_calls"] != plan["max_tool_calls"]
            or captured["journal_roots"] != sorted(map(str, _journal_roots(run_dir, plan, broker)))):
        raise ParentAnalysisError("immutable parent context differs from its original policy")


def prepare_parent_analysis(run_dir: Path, plan: dict, *, admission_root: Path | None = None) -> dict:
    plan = _validate_plan(plan)
    run_dir = Path(run_dir)
    if not run_dir.is_absolute() or ".." in run_dir.parts:
        raise ParentAnalysisError("parent run directory must be absolute")
    _private_dir(run_dir.parent)
    if run_dir.exists() or run_dir.is_symlink():
        raise FileExistsError("parent run already exists")
    state = {"schema": 1, "classification": CLASSIFICATION, "state": "prepared", "phase": "bootstrap",
             "plan_sha256": wave._sha(_canonical(plan)), "run_id": plan["run_id"],
             "admission_descriptor": admission.descriptor(admission_root), "claim_sha256": "",
             "source_digests": _sources(), "reason": None, "completed_requests": 0,
             "artifact_count": 0, "cursor": 0, "tool_calls_completed": 0,
             "leader": None, "workers": {}, "transition": None, "reviewer_done": False, "merge_result": None}
    state["claim_sha256"] = admission.claim_digest(**wave._claim_args(run_dir, state))
    run_dir.mkdir(mode=0o700)
    _new_private_file(run_dir / ".lock", b"")
    for folder in JOURNALS:
        (run_dir / folder).mkdir(mode=0o700)
    _new_private_file(run_dir / "plan.json", _canonical(plan))
    state["leader"] = _new_history(run_dir, plan, plan["leader"])
    _new_private_file(run_dir / "run.json", _canonical(state))
    broker = ParentAnalysisBroker(run_dir, plan["bootstrap_manifest"])
    verified = broker.verify()
    if verified["blocked"] or verified["pending"] or broker.operations():
        raise ParentAnalysisError("new bootstrap broker is not empty and reconciled")
    WaveLedger.create(run_dir / "ledger", plan["limit_tokens"], plan["max_model_requests"],
                      cost_limit_micro_usd=plan["cost_limit_micro_usd"],
                      price_profile=plan["price_profile"], effort=plan["effort"])
    RunContext.create(run_dir / "context", run_dir / "ledger", _bindings(plan, state),
                      active_limit_seconds=plan["active_limit_seconds"], max_tool_calls=plan["max_tool_calls"],
                      roles=["coordinator"], ledger_kind="wave_v1", journal_roots=_journal_roots(run_dir, plan, broker))
    return read_parent_analysis_status(run_dir)


def _wave_plan(plan: dict, state: dict) -> dict:
    transition = state["transition"]
    if type(transition) is not dict or not {"wave_plan", "branch_manifest", "transition_path", "transition_sha256", "seed"} <= set(transition):
        raise ParentAnalysisError("missing authenticated bootstrap transition")
    path = Path(transition["transition_path"])
    if (not path.is_absolute() or ".." in path.parts or path.is_symlink()
            or wave._sha(path.read_bytes()) != transition["transition_sha256"]):
        raise ParentAnalysisError("bootstrap transition changed")
    result = tools._validate_plan(transition["wave_plan"])
    require_analysis_binding(result)
    if (any(result[key] != plan[key] for key in SCALARS)
            or result["functions"] != plan["functions"] or result["reviewer"] != plan["reviewer"]
            or result["branch_manifest"] != transition["branch_manifest"]
            or len(result["tasks"]) != plan["workers"]["count"]):
        raise ParentAnalysisError("transition changes the parent resource or provider policy")
    for task in result["tasks"]:
        if (task["task_id"] in {"leader", "reviewer"} or task["role"] == "leader"
                or task["max_output_tokens"] != plan["workers"]["max_output_tokens"]
                or task["max_model_turns"] != plan["workers"]["max_model_turns"]):
            raise ParentAnalysisError("worker identity or caps differ from fixed parent policy")
    return result


def _cursor(value: dict, turns: int) -> None:
    if type(value) is not dict or set(value) != {"turns", "finished", "history_sha256"}:
        raise ParentAnalysisError("invalid private role cursor")
    wave._integer(value["turns"], 0, turns, "private role turns")
    if type(value["finished"]) is not bool or re.fullmatch("[0-9a-f]{64}", value["history_sha256"]) is None:
        raise ParentAnalysisError("invalid private role history binding")


def _load(run_dir: Path):
    _private_dir(run_dir)
    plan = _validate_plan(_read_json(run_dir / "plan.json"))
    state = _read_json(run_dir / "run.json")
    if (type(state) is not dict or set(state) != STATE_KEYS or type(state["schema"]) is not int
            or state["schema"] != 1 or state["classification"] != CLASSIFICATION
            or state["state"] not in {"prepared", "paused", "started", "completed", "indeterminate"}
            or state["phase"] not in {"bootstrap", "wave"}
            or state["plan_sha256"] != wave._sha(_canonical(plan)) or state["run_id"] != plan["run_id"]
            or state["source_digests"] != _sources()
            or state["claim_sha256"] != admission.claim_digest(**wave._claim_args(run_dir, state))):
        raise ParentAnalysisError("parent plan, source, lifecycle or claim changed")
    for field in ("completed_requests", "artifact_count", "cursor"):
        wave._integer(state[field], 0, 128, field)
    wave._integer(state["tool_calls_completed"], 0, plan["max_tool_calls"], "parent tool counter")
    _cursor(state["leader"], plan["leader"]["max_model_turns"])
    if type(state["workers"]) is not dict or type(state["reviewer_done"]) is not bool:
        raise ParentAnalysisError("invalid parent roles")
    if state["phase"] == "bootstrap":
        if state["transition"] is not None or state["workers"] or state["reviewer_done"]:
            raise ParentAnalysisError("bootstrap unexpectedly contains wave effects")
    else:
        derived = _wave_plan(plan, state)
        if not state["leader"]["finished"] or set(state["workers"]) != {t["task_id"] for t in derived["tasks"]}:
            raise ParentAnalysisError("wave does not follow a completed leader")
        for task in derived["tasks"]:
            _cursor(state["workers"][task["task_id"]], task["max_model_turns"])
    ledger, context = WaveLedger(run_dir / "ledger"), RunContext(run_dir / "context")
    wave._check_budget(plan, ledger.status())
    broker = ParentAnalysisBroker(run_dir, plan["bootstrap_manifest"])
    _check_context(run_dir, plan, state, broker)
    return plan, state, ledger, context, broker


def _response(run_dir: Path, state: dict, request_id: str, request: dict, role: str, ledger: WaveLedger) -> dict:
    receipt = _read_json(run_dir / "receipts" / (request_id + ".json"))
    response = _read_json(run_dir / "responses" / (request_id + ".json"))
    record = ledger.status()["requests"].get(request_id)
    if (record is None or record["state"] != "settled" or receipt["settled"] != record
            or receipt["request_id"] != request_id or receipt["role"] != role
            or receipt["classification"] != state["classification"]
            or receipt["payload_sha256"] != wave._sha(_json_bytes(request))
            or record["payload_sha256"] != receipt["payload_sha256"]
            or receipt["response_sha256"] != wave._sha(_canonical(response))
            or record["response_sha256"] != receipt["response_sha256"]
            or _read_json(run_dir / "requests" / (request_id + ".json")) != request):
        raise ParentAnalysisError("parent model request/response/ledger replay differs")
    return response


def _audit(run_dir: Path, plan: dict, state: dict, ledger: WaveLedger, broker) -> None:
    verified = broker.verify()
    if verified["blocked"] or verified["pending"] or ledger.status()["blocked"]:
        raise ParentAnalysisError("unreconciled parent journals prevent a checkpoint")
    operations = broker.operations()
    if len(operations) != state["tool_calls_completed"]:
        raise ParentAnalysisError("tool count differs from unified broker")
    indexed, seen_calls = {}, set()
    for ordinal, operation in enumerate(operations, 1):
        key = (operation["task_id"], operation["request_id"])
        if key in indexed or operation["call_id"] in seen_calls or operation["global_ordinal"] != ordinal:
            raise ParentAnalysisError("duplicate or discontinuous parent operation")
        indexed[key] = operation
        seen_calls.add(operation["call_id"])
    expected_ids, consumed, artifacts = set(), set(), []
    roles = [(plan, plan["leader"], state["leader"])]
    if state["phase"] == "wave":
        derived = _wave_plan(plan, state)
        roles.extend((derived, task, state["workers"][task["task_id"]]) for task in derived["tasks"])
    for role_plan, task, cursor in roles:
        task_id = task["task_id"]
        history, finished = _initial_history(role_plan, task), False
        for turn in range(1, cursor["turns"] + 1):
            if finished:
                raise ParentAnalysisError("request after role completion")
            request_id = tools._id(task_id, turn)
            expected_ids.add(request_id)
            request = tools._request(role_plan, task, history)
            response = _response(run_dir, state, request_id, request, task["role"], ledger)
            decoded = tools._decode(role_plan, response, plan["model"])
            history.extend(response["output"])
            if decoded["kind"] == "function":
                operation = indexed.get((task_id, request_id))
                call = decoded["call"]
                if (operation is None or operation["call_id"] != call["call_id"]
                        or operation["function_name"] != call["name"]
                        or operation["outer_arguments"] != json.loads(call["arguments"])):
                    raise ParentAnalysisError("tool differs from the actual model request")
                result = operation["result"]
                if (type(result) is not dict or set(result) != {"type", "call_id", "output"}
                        or result["type"] != "function_call_output" or result["call_id"] != call["call_id"]
                        or type(result["output"]) is not str):
                    raise ParentAnalysisError("invalid parent tool feedback")
                consumed.add((task_id, request_id))
                history.append(result)
            else:
                finished = True
                artifact = _artifact(task, decoded["text"])
                if _read_json(run_dir / "artifacts" / (task_id + ".json")) != artifact:
                    raise ParentAnalysisError("public artifact differs from actual response")
                artifacts.append(artifact)
            tools._request(role_plan, task, history)
        retained = _read_json(run_dir / "histories" / task_id / "run.json")
        if (retained != {"history": history} or cursor["history_sha256"] != wave._sha(_canonical(retained))
                or cursor["finished"] != finished):
            raise ParentAnalysisError("private role history differs from replay")
    if consumed != set(indexed):
        raise ParentAnalysisError("unbound parent tool operation")
    if state["reviewer_done"]:
        if state["phase"] != "wave" or len(artifacts) != 1 + len(derived["tasks"]):
            raise ParentAnalysisError("review precedes all public artifacts")
        reviewer = {**derived["reviewer"], "task_id": "reviewer", "role": "reviewer"}
        request_id = tools._id("reviewer", 1)
        expected_ids.add(request_id)
        response = _response(run_dir, state, request_id, wave._request(derived, reviewer, artifacts), "reviewer", ledger)
        artifact = _artifact(reviewer, wave._response_text(response, plan["model"]))
        if _read_json(run_dir / "artifacts/reviewer.json") != artifact:
            raise ParentAnalysisError("reviewer artifact differs from its response")
        artifacts.append(artifact)
    if set(ledger.status()["requests"]) != expected_ids or len(expected_ids) != state["completed_requests"]:
        raise ParentAnalysisError("parent request cursors differ from its single ledger")
    for folder in ("requests", "responses", "receipts"):
        if {p.name for p in (run_dir / folder).iterdir()} != {key + ".json" for key in expected_ids}:
            raise ParentAnalysisError("parent model journal inventory differs")
    if {p.name for p in (run_dir / "artifacts").iterdir()} != {a["task_id"] + ".json" for a in artifacts}:
        raise ParentAnalysisError("parent artifact inventory differs")


def _publication(run_dir: Path, state: dict, status: dict) -> dict:
    return {"schema": 1, "profile": PROFILE, "plan_sha256": state["plan_sha256"],
            "checkpoint_sha256": status["checkpoint_sha256"],
            "transition_sha256": state["transition"]["transition_sha256"],
            "artifacts": [{"name": path.name, "sha256": wave._sha(_canonical(_read_json(path)))}
                          for path in sorted((run_dir / "artifacts").iterdir())],
            "merge_result_sha256": wave._sha(_canonical(state["merge_result"]))}


def _validate_merge(run_dir: Path, state: dict, result: dict) -> None:
    """A callback return alone is never a completed parent merge."""
    required = {"path", "sha256", "receipt_path", "receipt_sha256",
                "analysis_receipt_path", "analysis_receipt_sha256", "parent_receipt_path",
                "parent_receipt_sha256", "analysis_artifacts", "missing_or_stale_tasks",
                "caller_graph_required", "seed_origin", "empirical_support_verified",
                "formal_cell_executed", "comparable_development_cell"}
    if type(result) is not dict or not required <= set(result):
        raise ParentAnalysisError("parent merge lacks its actual state and receipts")
    if (result["caller_graph_required"] is not False or result["seed_origin"] != "sealed_bootstrap_init"
            or any(result[field] is not False for field in (
                "empirical_support_verified", "formal_cell_executed", "comparable_development_cell"))):
        raise ParentAnalysisError("parent merge exceeds its declared scope")
    records = {}
    for key, filename in (("", "method_state.json"), ("receipt_", "receipt.json"),
                          ("analysis_receipt_", "analysis_receipt.json"), ("parent_receipt_", "parent_receipt.json")):
        expected = run_dir / "merge" / filename
        if result[key + "path"] != str(expected) or expected.resolve() != expected:
            raise ParentAnalysisError("parent merge path is outside its fixed journal")
        raw = _read_bounded_file(expected, "parent merge journal", MAX_JSON_BYTES)
        if wave._sha(raw) != result[key + "sha256"]:
            raise ParentAnalysisError("parent merge receipt or state changed")
        records[filename] = _read_json(expected)
    seed = state["transition"]["seed"]
    parent = records["parent_receipt.json"]
    base = records["receipt.json"]
    analysis = records["analysis_receipt.json"]
    graph = records["method_state.json"]
    initial = _read_json(Path(seed["state_path"]))
    if (parent.get("schema") != 1
            or parent.get("classification") != "development_c_parent_analysis_merge_unsealed"
            or parent.get("seed") != seed or parent.get("seed_origin") != "sealed_bootstrap_init"
            or parent.get("caller_graph_required") is not False
            or parent.get("analysis_receipt_sha256") != result["analysis_receipt_sha256"]
            or parent.get("empirical_support_verified") is not False
            or parent.get("comparable_development_cell") is not False
            or base.get("branch_manifest") != state["transition"]["branch_manifest"]
            or base.get("state_path") != result["path"] or base.get("state_sha256") != result["sha256"]
            or base.get("normative_approvals") != 0 or base.get("new_phase_acceptances") != 0
            or base.get("empirical_support_verified") is not False
            or base.get("formal_cell_executed") is not False
            or analysis.get("base_receipt_sha256") != result["receipt_sha256"]
            or analysis.get("analysis_artifacts") != result["analysis_artifacts"]
            or analysis.get("missing_or_stale_tasks") != result["missing_or_stale_tasks"]
            or graph.get("case_id") != initial.get("case_id")
            or graph.get("phase_status") != initial.get("phase_status")
            or any(node.get("status") != "pending" for node in graph["nodes"].values()
                   if node.get("kind") == "normative")):
        raise ParentAnalysisError("parent merge does not preserve its real bootstrap lineage")


def _view(run_dir: Path, plan: dict, state: dict, ledger: WaveLedger, context: RunContext) -> dict:
    status = context.status()
    terminal = state["state"] == status["state"] == "completed"
    published = False
    if terminal:
        try:
            published = _read_json(run_dir / "publication.json") == _publication(run_dir, state, status)
        except (OSError, ValueError, KeyError):
            pass
    paths = sorted((run_dir / "artifacts").iterdir())
    return {"classification": CLASSIFICATION, "execution_profile": PROFILE,
            "state": "indeterminate" if terminal and not published else status["state"],
            "stored_state": state["state"], "phase": state["phase"], "run_id": plan["run_id"],
            "checkpoint_sha256": status["checkpoint_sha256"], "cursor": status["cursor"],
            "context": status, "budget": ledger.status(), "leader": state["leader"], "workers": state["workers"],
            "completed_requests": state["completed_requests"], "tool_calls_completed": state["tool_calls_completed"],
            "artifact_count": len(paths) if published else 0,
            "artifacts": [{"path": str(path), "sha256": wave._sha(path.read_bytes())} for path in paths] if published else [],
            "forensic_artifact_entry_count": 0 if published else len(paths),
            "merge_result": state["merge_result"] if published else None,
            "reason": "publication marker missing or invalid" if terminal and not published else state["reason"],
            "empty_work_bootstrap": True, "caller_graph_required": False, "tools_enabled": True,
            "comparable_development_cell": False, "formal_cell_executed": False,
            "identity_authenticated": False, "cost_authenticated": False,
            "active_time_scope": "shared_local_clock_not_authenticated_provider_activity",
            "remote_cancellation_guaranteed": False}


def read_parent_analysis_status(run_dir: Path, *, guard: Callable | None = None) -> dict:
    run_dir = Path(run_dir)
    with _run_lock(run_dir):
        plan, state, ledger, context, broker = _load(run_dir)
        if guard is not None:
            guard(plan, state, broker)
        if state["state"] in {"prepared", "paused", "completed"}:
            _audit(run_dir, plan, state, ledger, broker)
        if state["state"] == "completed":
            _validate_merge(run_dir, state, state["merge_result"])
        return _view(run_dir, plan, state, ledger, context)


def execute_parent_analysis_step(run_dir: Path, transports_by_task: dict, *, expected_checkpoint: str,
                                 bootstrap_to_wave: Callable, merge: Callable,
                                 guard: Callable | None = None) -> dict:
    run_dir = Path(run_dir)
    with _run_lock(run_dir):
        plan, state, ledger, context, broker = _load(run_dir)
        if state["state"] not in {"prepared", "paused"} or context.status()["state"] != state["state"]:
            raise ParentAnalysisError("started or terminal parent never reexecutes")
        if not callable(bootstrap_to_wave) or not callable(merge) or guard is not None and not callable(guard):
            raise ParentAnalysisError("parent callbacks must be callable")
        expected = ({"leader"} if state["phase"] == "bootstrap" else
                    {task["task_id"] for task in _wave_plan(plan, state)["tasks"]} | {"reviewer"})
        if type(transports_by_task) is not dict or set(transports_by_task) != expected:
            raise ParentAnalysisError("transport keys differ from the current parent phase")
        if guard is not None:
            guard(plan, state, broker)
        _audit(run_dir, plan, state, ledger, broker)
        context.begin(expected_checkpoint, "coordinator")
        state["state"] = "started"
        finished_context = False
        try:
            _write_state(run_dir, state)
            if admission.acquire_staged_claim(**wave._claim_args(run_dir, state),
                                              override=wave._claim_override(state)) != state["claim_sha256"]:
                raise ParentAnalysisError("parent failed to acquire its original claim")

            def common_guard() -> None:
                context.require_active()
                if (state["source_digests"] != _sources()
                        or wave._sha((run_dir / "plan.json").read_bytes()) != state["plan_sha256"]):
                    raise ParentAnalysisError("active parent plan/source/context binding changed")
                _check_context(run_dir, plan, state, broker)
                if admission.require_claim(**wave._claim_args(run_dir, state),
                                           override=wave._claim_override(state)) != state["claim_sha256"]:
                    raise ParentAnalysisError("active parent claim changed")
                for task_id, cursor in {"leader": state["leader"], **state["workers"]}.items():
                    history = _read_json(run_dir / "histories" / task_id / "run.json")
                    if wave._sha(_canonical(history)) != cursor["history_sha256"]:
                        raise ParentAnalysisError("active private history changed")
                wave._check_budget(plan, ledger.status())
                context.require_active()

            def active_guard() -> None:
                common_guard()
                if broker.verify()["blocked"]:
                    raise ParentAnalysisError("parent broker has an uncertain effect")
                if guard is not None:
                    guard(plan, state, broker)
                context.require_active()

            active_guard()
            if state["phase"] == "bootstrap":
                role_plan, tasks, cursors = plan, [plan["leader"]], {"leader": state["leader"]}
            else:
                role_plan = _wave_plan(plan, state)
                cursors = state["workers"]
                tasks = [task for task in role_plan["tasks"] if not cursors[task["task_id"]]["finished"]]
            histories, request_ids = {}, {}
            for task in tasks:
                cursor = cursors[task["task_id"]]
                if cursor["turns"] >= task["max_model_turns"] or cursor["finished"]:
                    raise ParentAnalysisError("private role turn cap exhausted")
                request_ids[task["task_id"]] = tools._id(task["task_id"], cursor["turns"] + 1)
                histories[task["task_id"]] = _read_json(run_dir / "histories" / task["task_id"] / "run.json")["history"]
            decoded = wave._batch(
                run_dir, role_plan, tasks, [tools._request(role_plan, task, histories[task["task_id"]]) for task in tasks],
                transports_by_task, "parent-step-" + str(state["cursor"] + 1), ledger, context, active_guard, state,
                request_ids=request_ids, decoder=lambda response, model: tools._decode(role_plan, response, model))
            calls = [item for item in decoded if item["kind"] == "function"]
            if state["tool_calls_completed"] + len(calls) > plan["max_tool_calls"]:
                raise ParentAnalysisError("common parent tool cap exhausted")
            seen_calls = {operation["call_id"] for operation in broker.operations()}
            for task, entry in zip(tasks, decoded, strict=True):
                response = _response(run_dir, state, request_ids[task["task_id"]],
                                     tools._request(role_plan, task, histories[task["task_id"]]), task["role"], ledger)
                decoded_again = tools._decode(role_plan, response, plan["model"])
                if decoded_again != {key: entry[key] for key in decoded_again}:
                    raise ParentAnalysisError("decoded response changed before dispatch")
                history = histories[task["task_id"]] + response["output"]
                if entry["kind"] == "function":
                    call = entry["call"]
                    if call["call_id"] in seen_calls or cursors[task["task_id"]]["turns"] + 1 >= task["max_model_turns"]:
                        raise ParentAnalysisError("replayed tool call or no remaining role turn")
                    seen_calls.add(call["call_id"])
                    history.append({"type": "function_call_output", "call_id": call["call_id"], "output": "pending"})
                tools._request(role_plan, task, history)
            for task, entry in zip(tasks, decoded, strict=True):
                active_guard()
                task_id = task["task_id"]
                response = _response(run_dir, state, request_ids[task_id],
                                     tools._request(role_plan, task, histories[task_id]), task["role"], ledger)
                history = histories[task_id] + response["output"]
                if entry["kind"] == "function":
                    result = broker.invoke(task_id, request_ids[task_id],
                                           {key: entry["call"][key] for key in ("name", "call_id", "arguments")},
                                           context, active_guard)
                    active_guard()
                    history.append(result)
                    tools._request(role_plan, task, history)
                    state["tool_calls_completed"] += 1
                else:
                    _new_private_file(run_dir / "artifacts" / (task_id + ".json"),
                                      _canonical(_artifact(task, entry["text"])))
                    cursors[task_id]["finished"] = True
                value = {"history": history}
                _write_state(run_dir / "histories" / task_id, value)
                cursors[task_id].update(turns=cursors[task_id]["turns"] + 1,
                                       history_sha256=wave._sha(_canonical(value)))
                _write_state(run_dir, state)
                active_guard()
            if state["phase"] == "bootstrap" and state["leader"]["finished"]:
                _audit(run_dir, plan, state, ledger, broker)
                # Only this active stack may construct transition metadata before
                # its activation receipt. No pause or fresh-process recovery here.
                transition = bootstrap_to_wave(plan, state, broker, context, common_guard)
                if type(transition) is not dict or len(_canonical(transition)) > MAX_JSON_BYTES:
                    raise ParentAnalysisError("bootstrap must produce a bounded authenticated transition")
                next_state = {**state, "transition": transition, "phase": "wave"}
                derived = _wave_plan(plan, next_state)
                activation = broker.activate(transition["branch_manifest"], context, common_guard)
                if activation is not None:
                    transition["activation"] = activation
                state.update(phase="wave", transition=transition)
                for task in derived["tasks"]:
                    state["workers"][task["task_id"]] = _new_history(run_dir, derived, task)
                _write_state(run_dir, state)
                active_guard()
            elif state["phase"] == "wave" and all(cursor["finished"] for cursor in state["workers"].values()):
                derived = _wave_plan(plan, state)
                artifacts = [_read_json(run_dir / "artifacts/leader.json")]
                artifacts.extend(_read_json(run_dir / "artifacts" / (task["task_id"] + ".json")) for task in derived["tasks"])
                reviewer = {**derived["reviewer"], "task_id": "reviewer", "role": "reviewer"}
                reviewed = wave._batch(run_dir, derived, [reviewer], [wave._request(derived, reviewer, artifacts)],
                                       transports_by_task, "parent-review", ledger, context, active_guard, state,
                                       request_ids={"reviewer": tools._id("reviewer", 1)})
                active_guard()
                _new_private_file(run_dir / "artifacts/reviewer.json", _canonical(_artifact(reviewer, reviewed[0]["text"])))
                state["reviewer_done"] = True
                _write_state(run_dir, state)
                _audit(run_dir, plan, state, ledger, broker)
                result = merge(derived, state, broker, context, active_guard)
                active_guard()
                if type(result) is not dict or len(_canonical(result)) > MAX_JSON_BYTES:
                    raise ParentAnalysisError("parent merge result must be bounded JSON")
                _validate_merge(run_dir, state, result)
                state.update(state="completed", cursor=state["cursor"] + 1,
                             merge_result=result, artifact_count=len(artifacts) + 1)
                _write_state(run_dir, state)
                active_guard()
                context.finish(state["cursor"])
                finished_context = True
                _new_private_file(run_dir / "publication.json", _canonical(_publication(run_dir, state, context.status())))
            if not finished_context:
                _audit(run_dir, plan, state, ledger, broker)
                state.update(state="paused", cursor=state["cursor"] + 1)
                _write_state(run_dir, state)
                active_guard()
                context.pause(state["cursor"])
        except BaseException as exc:
            if finished_context:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                return _view(run_dir, plan, state, ledger, context)
            state.update(state="indeterminate", reason=(type(exc).__name__ + ": " + str(exc))[:2048])
            for request_id, record in ledger.status()["requests"].items():
                if record["state"] != "settled":
                    try:
                        ledger.mark_indeterminate(request_id, type(exc).__name__)
                    except BudgetError:
                        pass
            try:
                _write_state(run_dir, state)
            finally:
                try:
                    context.abort(type(exc).__name__)
                except Exception:
                    pass
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
        return _view(run_dir, plan, state, ledger, context)
