"""Opt-in private tool conversations sharing one wave ledger and active clock.

Daemon workers only perform model I/O. The host reconciles all effects and
publishes artifacts only after review, merge, and the final context checkpoint.
"""

from __future__ import annotations

import ast
import json
import math
import re
from pathlib import Path
from typing import Any, Callable

import local_run_admission as admission
import managed_parallel_wave as wave
from managed_run_context import RunContext
from managed_token_ledger import BudgetError
from managed_wave_ledger import WaveLedger
from parallel_tool_broker import ParallelToolBroker
from run_managed_conversation import (
    _canonical, _new_private_file, _private_dir, _read_json, _run_lock, _write_state,
)
from run_managed_response import (
    MAX_JSON_BYTES, _json_bytes, _validate_function_tool, _validated_request,
)
from run_managed_tool_conversation import _response_kind


PROFILE = "parallel_tool_wave_v2"
CLASSIFICATION = "development_parallel_tool_wave_unsealed"
PLAN_KEYS = wave.PLAN_KEYS | {"functions", "branch_manifest", "max_tool_calls", "tool_wall_seconds"}
STATE_KEYS = wave.STATE_KEYS | {"cursor", "workers", "reviewer_done", "tool_calls_completed", "merge_result"}
JOURNALS = (*wave.JOURNALS, "histories", "broker", "merge")


class ParallelToolsError(ValueError):
    """A private conversation cannot proceed or publish its result."""


def _validate_plan(raw: Any) -> dict:
    if (type(raw) is not dict or set(raw) != PLAN_KEYS or type(raw["schema"]) is not int
            or raw["schema"] != 2 or raw["execution_profile"] != PROFILE):
        raise ParallelToolsError("invalid strict parallel tool plan")
    if type(raw["run_id"]) is not str or not raw["run_id"].startswith("tool-wave-"):
        raise ParallelToolsError("tool wave requires a new tool-wave- identity")
    tasks = raw["tasks"]
    if type(tasks) is not list:
        raise ParallelToolsError("invalid tasks")
    base = {key: value for key, value in raw.items() if key in wave.PLAN_KEYS}
    base.update(schema=1, execution_profile=wave.PROFILE, run_id="wave-" + raw["run_id"][10:])
    base["tasks"] = []
    for task in tasks:
        if type(task) is not dict or set(task) != {
            "task_id", "role", "user", "max_output_tokens", "owned_node_ids", "max_model_turns"
        }:
            raise ParallelToolsError("invalid tool task fields")
        wave._integer(task["max_model_turns"], 1, 32, "worker model turns")
        base["tasks"].append({key: value for key, value in task.items() if key != "max_model_turns"})
    wave._validate_plan(base)
    wave._identifier(raw["run_id"], "run_id")
    wave._integer(raw["max_tool_calls"], 1, 64, "tool cap")
    wall = raw["tool_wall_seconds"]
    if type(wall) not in (int, float) or not math.isfinite(wall) or not 0 < wall <= 300:
        raise ParallelToolsError("invalid tool wall limit")
    functions = raw["functions"]
    if type(functions) is not list or not 1 <= len(functions) <= 8:
        raise ParallelToolsError("invalid provider functions")
    names = set()
    for function in functions:
        if type(function) is not dict or set(function) != {"type", "name", "description", "parameters", "strict"}:
            raise ParallelToolsError("functions contain only the five provider fields")
        _validate_function_tool(function)
        if function["name"] in names:
            raise ParallelToolsError("duplicate function")
        names.add(function["name"])
    binding = raw["branch_manifest"]
    if (type(binding) is not dict or set(binding) != {"path", "sha256"}
            or type(binding["path"]) is not str or not Path(binding["path"]).is_absolute()
            or type(binding["sha256"]) is not str or re.fullmatch("[0-9a-f]{64}", binding["sha256"]) is None):
        raise ParallelToolsError("invalid branch manifest binding")
    if len(_canonical(raw)) > MAX_JSON_BYTES:
        raise ParallelToolsError("tool plan exceeds byte bound")
    return json.loads(_canonical(raw))


def _sources() -> dict:
    root = Path(__file__).resolve().parent
    pending, seen = [Path(__file__).stem], set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        path = root / f"{name}.py"
        raw = path.read_bytes()
        seen.add(name)
        for node in ast.walk(ast.parse(raw)):
            names = ([item.name.split(".")[0] for item in node.names] if isinstance(node, ast.Import)
                     else [node.module.split(".")[0]] if isinstance(node, ast.ImportFrom) and node.module else [])
            pending.extend(item for item in names if (root / f"{item}.py").is_file())
    return {f"scripts/{name}.py": wave._sha((root / f"{name}.py").read_bytes()) for name in sorted(seen)}


def _bind_broker(plan: dict, broker: ParallelToolBroker) -> None:
    verified = broker.verify()
    if verified["blocked"]:
        raise ParallelToolsError("broker has an unresolved effect")
    names = {item["name"] for item in plan["functions"]}
    for task in plan["tasks"]:
        branch = broker.branch(task["task_id"])
        if (branch["owned_node_ids"] != task["owned_node_ids"]
                or {item["name"] for item in branch["functions"]} != names):
            raise ParallelToolsError("branch ownership or functions differ from plan")


def prepare_tool_wave(run_dir: Path, plan: dict, *, admission_root: Path | None = None) -> dict:
    plan = _validate_plan(plan)
    run_dir = Path(run_dir)
    if not run_dir.is_absolute() or any(part in (".", "..") for part in run_dir.parts):
        raise ParallelToolsError("run directory must be absolute")
    _private_dir(run_dir.parent)
    if run_dir.exists() or run_dir.is_symlink():
        raise FileExistsError("tool wave already exists")
    state = {"schema": 2, "classification": CLASSIFICATION, "state": "prepared",
             "plan_sha256": wave._sha(_canonical(plan)), "run_id": plan["run_id"],
             "admission_descriptor": admission.descriptor(admission_root), "claim_sha256": "",
             "source_digests": _sources(), "reason": None, "completed_requests": 0,
             "artifact_count": 0, "cursor": 0, "reviewer_done": False,
             "tool_calls_completed": 0, "merge_result": None, "workers": {}}
    state["claim_sha256"] = admission.claim_digest(**wave._claim_args(run_dir, state))
    run_dir.mkdir(mode=0o700)
    _new_private_file(run_dir / ".lock", b"")
    for name in JOURNALS:
        (run_dir / name).mkdir(mode=0o700)
    _new_private_file(run_dir / "plan.json", _canonical(plan))
    for task in plan["tasks"]:
        directory = run_dir / "histories" / task["task_id"]
        directory.mkdir(mode=0o700)
        history = _initial_history(plan, task)
        _new_private_file(directory / "run.json", _canonical({"history": history}))
        state["workers"][task["task_id"]] = {
            "turns": 0, "finished": False, "history_sha256": wave._sha(_canonical({"history": history}))}
    _new_private_file(run_dir / "run.json", _canonical(state))
    broker = ParallelToolBroker(run_dir, plan["branch_manifest"])
    _bind_broker(plan, broker)
    WaveLedger.create(run_dir / "ledger", plan["limit_tokens"], plan["max_model_requests"],
                      cost_limit_micro_usd=plan["cost_limit_micro_usd"],
                      price_profile=plan["price_profile"], effort=plan["effort"])
    bindings = {"ledger_kind": "wave_v1", "ledger_schema": 3, "plan_sha256": state["plan_sha256"],
                "run_id": plan["run_id"], "claim_sha256": state["claim_sha256"],
                "source_digests": state["source_digests"], "branch_manifest": plan["branch_manifest"]}
    RunContext.create(run_dir / "context", run_dir / "ledger", bindings,
                      active_limit_seconds=plan["active_limit_seconds"], max_tool_calls=plan["max_tool_calls"],
                      roles=["coordinator"], ledger_kind="wave_v1",
                      journal_roots=[run_dir / name for name in JOURNALS] +
                      [run_dir / "plan.json", run_dir / "run.json", run_dir / "ledger"] + broker.journal_roots())
    return read_tool_wave_status(run_dir)


def _initial_history(plan: dict, task: dict) -> list:
    content = {"common_context": plan["context"], "task": task["user"], "task_id": task["task_id"],
               "role": task["role"], "owned_node_ids": task["owned_node_ids"]}
    return [{"role": "user", "content": _json_bytes(content).decode()}]


def _request(plan: dict, task: dict, history: list) -> dict:
    return _validated_request({"model": plan["model"], "reasoning": {"effort": plan["effort"]},
                               "service_tier": "default", "max_output_tokens": task["max_output_tokens"],
                               "input": history, "tools": plan["functions"], "parallel_tool_calls": False})


def _decode(plan: dict, response: dict, model: str) -> dict:
    if (type(response) is not dict or type(response.get("id")) is not str or not response["id"]
            or response.get("model") != model or response.get("status") != "completed"
            or response.get("service_tier") != "default"):
        raise ParallelToolsError("invalid, cross-model or incomplete tool response")
    kind, call = _response_kind(response, plan["functions"])
    if kind == "text":
        return {"kind": "text", "text": wave._response_text(response, model)}
    if kind == "function":
        return {"kind": "function", "call": call}
    raise ParallelToolsError("unsupported tool response")


def _id(task_id: str, turn: int) -> str:
    return f"{task_id}-turn-{turn:04d}"


def _load(run_dir: Path, broker=None) -> tuple:
    _private_dir(run_dir)
    for name in (*JOURNALS, "ledger", "context"):
        _private_dir(run_dir / name)
    plan = _validate_plan(_read_json(run_dir / "plan.json"))
    state = _read_json(run_dir / "run.json")
    if (set(state) != STATE_KEYS or type(state["schema"]) is not int or state["schema"] != 2
            or state["classification"] != CLASSIFICATION
            or state["state"] not in {"prepared", "paused", "started", "completed", "indeterminate"}
            or state["plan_sha256"] != wave._sha(_canonical(plan)) or state["run_id"] != plan["run_id"]
            or state["source_digests"] != _sources()
            or admission.claim_digest(**wave._claim_args(run_dir, state)) != state["claim_sha256"]):
        raise ParallelToolsError("tool wave state, sources, plan or admission changed")
    for field in ("completed_requests", "cursor", "artifact_count"):
        wave._integer(state[field], 0, 128, field)
    wave._integer(state["tool_calls_completed"], 0, plan["max_tool_calls"], "tool count")
    if type(state["reviewer_done"]) is not bool or set(state["workers"]) != {t["task_id"] for t in plan["tasks"]}:
        raise ParallelToolsError("invalid worker cursors")
    for task in plan["tasks"]:
        worker = state["workers"][task["task_id"]]
        if type(worker) is not dict or set(worker) != {"turns", "finished", "history_sha256"}:
            raise ParallelToolsError("invalid worker state")
        wave._integer(worker["turns"], 0, task["max_model_turns"], "worker cursor")
        if type(worker["finished"]) is not bool:
            raise ParallelToolsError("invalid worker terminal flag")
    ledger, context = WaveLedger(run_dir / "ledger"), RunContext(run_dir / "context")
    wave._check_budget(plan, ledger.status())
    broker = broker or ParallelToolBroker(run_dir, plan["branch_manifest"])
    _bind_broker(plan, broker)
    return plan, state, ledger, context, broker


def _artifact(plan: dict, task: dict, text: str) -> dict:
    artifact = {"task_id": task["task_id"], "role": task["role"], "text": text,
                "owned_node_ids": task["owned_node_ids"]}
    artifact["artifact_sha256"] = wave._sha(_canonical(artifact))
    return artifact


def _audit(run_dir: Path, plan: dict, state: dict, ledger: WaveLedger, broker) -> None:
    """Reconstruct every settled request and private history from retained receipts."""
    checked = broker.verify()
    if checked["pending"] or checked["blocked"] or ledger.status()["blocked"]:
        raise ParallelToolsError("unreconciled journals prevent checkpoint replay")
    operations = broker.operations()
    if len(operations) != state["tool_calls_completed"]:
        raise ParallelToolsError("tool counter differs from broker")
    indexed, seen_calls = {}, set()
    for operation in operations:
        key = (operation["task_id"], operation["request_id"])
        if key in indexed or operation["call_id"] in seen_calls:
            raise ParallelToolsError("duplicate tool request or call")
        indexed[key] = operation
        seen_calls.add(operation["call_id"])
    records, expected_ids, consumed = ledger.status()["requests"], set(), set()
    artifacts = []

    def model_receipt(request_id: str, request: dict, role: str) -> dict:
        expected_ids.add(request_id)
        receipt = _read_json(run_dir / "receipts" / f"{request_id}.json")
        response = _read_json(run_dir / "responses" / f"{request_id}.json")
        record = records.get(request_id)
        if (record is None or record["state"] != "settled" or receipt["settled"] != record
                or receipt["request_id"] != request_id or receipt["role"] != role
                or receipt["classification"] != CLASSIFICATION
                or receipt["payload_sha256"] != wave._sha(_json_bytes(request))
                or record["payload_sha256"] != receipt["payload_sha256"]
                or receipt["response_sha256"] != wave._sha(_canonical(response))
                or _read_json(run_dir / "requests" / f"{request_id}.json") != request):
            raise ParallelToolsError("model request/response/ledger receipt replay differs")
        return response

    for task in plan["tasks"]:
        task_id = task["task_id"]
        worker = state["workers"][task_id]
        history, finished = _initial_history(plan, task), False
        for turn in range(1, worker["turns"] + 1):
            if finished:
                raise ParallelToolsError("model request after worker completion")
            request_id = _id(task_id, turn)
            response = model_receipt(request_id, _request(plan, task, history), task["role"])
            decoded = _decode(plan, response, plan["model"])
            history.extend(response["output"])
            if decoded["kind"] == "function":
                operation = indexed.get((task_id, request_id))
                call = decoded["call"]
                if (operation is None or operation["call_id"] != call["call_id"]
                        or operation["function_name"] != call["name"]
                        or operation["outer_arguments"] != json.loads(call["arguments"])):
                    raise ParallelToolsError("tool operation differs from actual model response")
                result = operation["result"]
                if (type(result) is not dict or set(result) != {"type", "call_id", "output"}
                        or result["type"] != "function_call_output" or result["call_id"] != call["call_id"]
                        or type(result["output"]) is not str):
                    raise ParallelToolsError("invalid broker function result")
                consumed.add((task_id, request_id))
                history.append(result)
            else:
                finished = True
                artifact = _artifact(plan, task, decoded["text"])
                if _read_json(run_dir / "artifacts" / f"{task_id}.json") != artifact:
                    raise ParallelToolsError("public worker artifact differs from response")
                artifacts.append(artifact)
            _request(plan, task, history)
        retained = _read_json(run_dir / "histories" / task_id / "run.json")
        if (retained != {"history": history} or worker["history_sha256"] != wave._sha(_canonical(retained))
                or worker["finished"] != finished):
            raise ParallelToolsError("private history or cursor differs from replay")
    if consumed != set(indexed):
        raise ParallelToolsError("broker contains an unbound operation")
    if state["reviewer_done"]:
        if len(artifacts) != len(plan["tasks"]):
            raise ParallelToolsError("review happened before all worker artifacts")
        reviewer = {**plan["reviewer"], "task_id": "reviewer", "role": "reviewer"}
        response = model_receipt(_id("reviewer", 1), wave._request(plan, reviewer, artifacts), "reviewer")
        text = wave._response_text(response, plan["model"])
        artifact = {"task_id": "reviewer", "role": "reviewer", "text": text}
        artifact["artifact_sha256"] = wave._sha(_canonical(artifact))
        if _read_json(run_dir / "artifacts/reviewer.json") != artifact:
            raise ParallelToolsError("reviewer artifact differs")
    if set(records) != expected_ids or len(expected_ids) != state["completed_requests"]:
        raise ParallelToolsError("request cursors differ from common ledger")
    for folder in ("requests", "responses", "receipts"):
        if {p.name for p in (run_dir / folder).iterdir()} != {f"{key}.json" for key in expected_ids}:
            raise ParallelToolsError("model journal inventory differs")
    expected_artifacts = {f"{a['task_id']}.json" for a in artifacts}
    if state["reviewer_done"]:
        expected_artifacts.add("reviewer.json")
    if {p.name for p in (run_dir / "artifacts").iterdir()} != expected_artifacts:
        raise ParallelToolsError("artifact inventory differs")


def _view(run_dir: Path, plan: dict, state: dict, ledger: WaveLedger, context: RunContext, broker) -> dict:
    status = context.status()
    terminal = status["state"] == state["state"] == "completed"
    paths = sorted((run_dir / "artifacts").iterdir())
    published = False
    if terminal:
        try:
            published = _read_json(run_dir / "publication.json") == _publication(run_dir, state, status)
        except (OSError, ValueError):
            pass
    artifacts = [{"path": str(p), "sha256": wave._sha(p.read_bytes())} for p in paths] if published else []
    return {"classification": CLASSIFICATION, "execution_profile": PROFILE,
            "state": "indeterminate" if terminal and not published else status["state"],
            "stored_state": state["state"], "run_id": plan["run_id"],
            "checkpoint_sha256": status["checkpoint_sha256"], "cursor": status["cursor"],
            "context": status, "budget": ledger.status(), "workers": state["workers"],
            "completed_requests": state["completed_requests"], "tool_calls_completed": state["tool_calls_completed"],
            "artifact_count": len(artifacts), "artifacts": artifacts,
            "forensic_artifact_entry_count": 0 if published else len(paths),
            "merge_result": state["merge_result"] if published else None,
            "reason": "publication marker missing or invalid" if terminal and not published else state["reason"],
            "tools_enabled": True, "identity_authenticated": False, "cost_authenticated": False,
            "formal_cell_executed": False, "remote_cancellation_guaranteed": False}


def _publication(run_dir: Path, state: dict, status: dict) -> dict:
    # Outside frozen journal roots; this marker never changes the checkpoint.
    artifacts = []
    for path in sorted((run_dir / "artifacts").iterdir()):
        value = _read_json(path)
        artifacts.append({"name": path.name, "sha256": wave._sha(_canonical(value))})
    return {"schema": 1, "plan_sha256": state["plan_sha256"],
            "checkpoint_sha256": status["checkpoint_sha256"], "artifacts": artifacts,
            "merge_result_sha256": wave._sha(_canonical(state["merge_result"]))}


def read_tool_wave_status(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    with _run_lock(run_dir):
        loaded = _load(run_dir)
        plan, state, ledger, context, broker = loaded
        if state["state"] in {"prepared", "paused", "completed"}:
            _audit(run_dir, plan, state, ledger, broker)
        return _view(run_dir, *loaded)


def execute_tool_wave_step(run_dir: Path, transports_by_task: dict, *, expected_checkpoint: str,
                           broker=None, guard: Callable[[], None] | None = None,
                           merge: Callable | None = None) -> dict:
    run_dir = Path(run_dir)
    with _run_lock(run_dir):
        plan, state, ledger, context, broker = _load(run_dir, broker)
        if state["state"] not in {"prepared", "paused"} or context.status()["state"] != state["state"]:
            raise ParallelToolsError("started or terminal tool wave never reexecutes")
        expected = {task["task_id"] for task in plan["tasks"]} | {"reviewer"}
        if type(transports_by_task) is not dict or set(transports_by_task) != expected:
            raise ParallelToolsError("transport keys differ from tasks and reviewer")
        if any(callback is not None and not callable(callback) for callback in (guard, merge)):
            raise ParallelToolsError("guards and merge must be callable")
        _audit(run_dir, plan, state, ledger, broker)
        context.begin(expected_checkpoint, "coordinator")
        state["state"] = "started"
        finished_context = False
        try:
            _write_state(run_dir, state)
            if admission.acquire_staged_claim(**wave._claim_args(run_dir, state),
                                              override=wave._claim_override(state)) != state["claim_sha256"]:
                raise ParallelToolsError("tool wave did not acquire expected claim")

            def active_guard() -> None:
                context.require_active()
                if (_sources() != state["source_digests"]
                        or wave._sha((run_dir / "plan.json").read_bytes()) != state["plan_sha256"]):
                    raise ParallelToolsError("frozen source or plan changed")
                if admission.require_claim(**wave._claim_args(run_dir, state),
                                           override=wave._claim_override(state)) != state["claim_sha256"]:
                    raise ParallelToolsError("tool wave claim changed")
                _bind_broker(plan, broker)
                wave._check_budget(plan, ledger.status())
                if guard is not None:
                    guard()
                context.require_active()

            active_guard()
            tasks = [task for task in plan["tasks"] if not state["workers"][task["task_id"]]["finished"]]
            ids, histories = {}, {}
            for task in tasks:
                worker = state["workers"][task["task_id"]]
                if worker["turns"] >= task["max_model_turns"]:
                    raise ParallelToolsError("worker model turn cap exhausted")
                ids[task["task_id"]] = _id(task["task_id"], worker["turns"] + 1)
                histories[task["task_id"]] = _read_json(run_dir / "histories" / task["task_id"] / "run.json")["history"]
            decoded = wave._batch(
                run_dir, plan, tasks, [_request(plan, task, histories[task["task_id"]]) for task in tasks],
                transports_by_task, f"step-{state['cursor'] + 1}", ledger, context, active_guard, state,
                request_ids=ids, decoder=lambda response, model: _decode(plan, response, model))
            calls = [entry for entry in decoded if entry["kind"] == "function"]
            if state["tool_calls_completed"] + len(calls) > plan["max_tool_calls"]:
                raise ParallelToolsError("common tool cap exhausted")
            seen = {op["call_id"] for op in broker.operations()}
            for task, entry in zip(tasks, decoded, strict=True):
                task_id = task["task_id"]
                response = _read_json(run_dir / "responses" / f"{ids[task_id]}.json")
                history = histories[task_id] + response["output"]
                if entry["kind"] == "function":
                    call = entry["call"]
                    if call["call_id"] in seen or state["workers"][task_id]["turns"] + 1 >= task["max_model_turns"]:
                        raise ParallelToolsError("replayed call or no remaining worker turn")
                    seen.add(call["call_id"])
                    _request(plan, task, history + [{"type": "function_call_output", "call_id": call["call_id"], "output": "pending"}])
                else:
                    _request(plan, task, history)
            for task, entry in zip(tasks, decoded, strict=True):
                active_guard()
                task_id = task["task_id"]
                history = histories[task_id] + _read_json(run_dir / "responses" / f"{ids[task_id]}.json")["output"]
                if entry["kind"] == "function":
                    result = broker.invoke(task_id, ids[task_id],
                                           {key: entry["call"][key] for key in ("name", "call_id", "arguments")},
                                           context, active_guard)
                    active_guard()
                    _request(plan, task, history + [result])
                    history.append(result)
                    state["tool_calls_completed"] += 1
                else:
                    _new_private_file(run_dir / "artifacts" / f"{task_id}.json", _canonical(_artifact(plan, task, entry["text"])))
                    state["workers"][task_id]["finished"] = True
                active_guard()
                directory = run_dir / "histories" / task_id
                _write_state(directory, {"history": history})
                worker = state["workers"][task_id]
                worker.update(turns=worker["turns"] + 1, history_sha256=wave._sha(_canonical({"history": history})))
                _write_state(run_dir, state)
            active_guard()
            if all(worker["finished"] for worker in state["workers"].values()):
                artifacts = [_read_json(run_dir / "artifacts" / f"{task['task_id']}.json") for task in plan["tasks"]]
                reviewer = {**plan["reviewer"], "task_id": "reviewer", "role": "reviewer"}
                reviewed = wave._batch(run_dir, plan, [reviewer], [wave._request(plan, reviewer, artifacts)],
                                       transports_by_task, "review", ledger, context, active_guard, state,
                                       request_ids={"reviewer": _id("reviewer", 1)})
                active_guard()
                _new_private_file(run_dir / "artifacts/reviewer.json", _canonical(reviewed[0]))
                state["reviewer_done"] = True
                _write_state(run_dir, state)
                _audit(run_dir, plan, state, ledger, broker)
                active_guard()
                if merge is not None:
                    result = merge(plan, state, broker, context, active_guard)
                    active_guard()
                    if type(result) is not dict or len(_canonical(result)) > MAX_JSON_BYTES:
                        raise ParallelToolsError("merge result must be bounded JSON object")
                    state["merge_result"] = result
                state.update(state="completed", cursor=state["cursor"] + 1, artifact_count=len(artifacts) + 1)
                _write_state(run_dir, state)
                active_guard()
                context.finish(state["cursor"])
                finished_context = True
                _new_private_file(run_dir / "publication.json", _canonical(_publication(run_dir, state, context.status())))
            else:
                _audit(run_dir, plan, state, ledger, broker)
                state.update(state="paused", cursor=state["cursor"] + 1)
                _write_state(run_dir, state)
                active_guard()
                context.pause(state["cursor"])
        except BaseException as exc:
            if finished_context:
                # Frozen journals remain unchanged after finish; absent/invalid
                # publication leaves a durable indeterminate public outcome.
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                return _view(run_dir, plan, state, ledger, context, broker)
            state.update(state="indeterminate", reason=f"{type(exc).__name__}: {exc}"[:2048])
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
        return _view(run_dir, plan, state, ledger, context, broker)
