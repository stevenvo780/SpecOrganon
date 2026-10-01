"""Opt-in textual development waves: one host writes, daemon workers do I/O.

No tools, core mutations, normative approval, retry, or provider authorization.
Callbacks may outlive the deadline; their late results cannot mutate journals.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import queue
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

import local_run_admission as admission
from managed_run_context import RunContext
from managed_token_ledger import BudgetError, _price_profile
from managed_wave_ledger import WaveLedger
from run_managed_conversation import (
    _canonical, _new_private_file, _private_dir, _read_json, _run_lock, _write_state,
)
from run_managed_response import MAX_JSON_BYTES, OpenAIResponsesHTTP, _json_bytes, _validated_request


CLASSIFICATION = "development_parallel_wave_proposals_unsealed"
PROFILE = "parallel_wave_v1"
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")
PLAN_KEYS = {"schema", "execution_profile", "run_id", "model", "effort", "price_profile",
             "limit_tokens", "max_model_requests", "cost_limit_micro_usd",
             "active_limit_seconds", "context", "tasks", "reviewer"}
STATE_KEYS = {"schema", "classification", "state", "plan_sha256", "run_id",
              "admission_descriptor", "claim_sha256", "source_digests", "reason",
              "completed_requests", "artifact_count"}
JOURNALS = ("requests", "responses", "receipts", "artifacts",
            "tool_reservations", "tool_receipts")


class ParallelWaveError(ValueError):
    """An opt-in textual wave cannot proceed or certify completion."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _integer(value: Any, minimum: int, maximum: int, label: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ParallelWaveError(f"invalid {label}")
    return value


def _text(value: Any, label: str, maximum: int = 262144) -> str:
    if (type(value) is not str or not value.strip() or len(value.encode("utf-8")) > maximum
            or any(ord(char) < 32 and char not in "\n\t\r" for char in value)):
        raise ParallelWaveError(f"invalid {label}")
    return value


def _identifier(value: Any, label: str) -> str:
    if type(value) is not str or ID.fullmatch(value) is None:
        raise ParallelWaveError(f"invalid {label}")
    return value


def _validate_plan(plan: Any) -> dict:
    if (type(plan) is not dict or set(plan) != PLAN_KEYS
            or type(plan["schema"]) is not int or plan["schema"] != 1
            or plan["execution_profile"] != PROFILE):
        raise ParallelWaveError("invalid strict parallel wave plan")
    _identifier(plan["run_id"], "run_id")
    if not plan["run_id"].startswith("wave-"):
        raise ParallelWaveError("wave requires a new wave- identity, never a DEV solo run")
    for field in ("model", "effort"):
        _text(plan[field], field, 256)
    _text(plan["context"], "common factual context")
    try:
        profile = _price_profile(plan["price_profile"])
    except BudgetError as exc:
        raise ParallelWaveError("invalid declared price profile") from exc
    if profile["model"] != plan["model"]:
        raise ParallelWaveError("price profile model differs")
    limit = _integer(plan["limit_tokens"], 1, 80000, "token cap")
    _integer(plan["cost_limit_micro_usd"], 0, 10**15, "cost cap")
    active = plan["active_limit_seconds"]
    if type(active) not in (int, float) or not math.isfinite(active) or not 0 < active <= 5400:
        raise ParallelWaveError("invalid active deadline")
    tasks = plan["tasks"]
    if type(tasks) is not list or not 2 <= len(tasks) <= 4:
        raise ParallelWaveError("wave requires two through four tasks")
    ids, roles, nodes = set(), set(), set()
    for task in tasks:
        if type(task) is not dict or set(task) != {"task_id", "role", "user", "max_output_tokens", "owned_node_ids"}:
            raise ParallelWaveError("invalid task fields")
        task_id = _identifier(task["task_id"], "task_id")
        role = _identifier(task["role"], "role")
        if task_id in ids or task_id == "reviewer" or role in roles or role in {"reviewer", "coordinator"}:
            raise ParallelWaveError("task IDs and roles must be unique and disjoint from reviewer")
        ids.add(task_id)
        roles.add(role)
        _text(task["user"], "task user")
        _integer(task["max_output_tokens"], 1, limit, "task output cap")
        owned = task["owned_node_ids"]
        if type(owned) is not list or not 1 <= len(owned) <= 128:
            raise ParallelWaveError("task ownership must be a nonempty list")
        for node in owned:
            _identifier(node, "owned node")
            if node in nodes:
                raise ParallelWaveError("task ownership overlaps")
            nodes.add(node)
    reviewer = plan["reviewer"]
    if type(reviewer) is not dict or set(reviewer) != {"user", "max_output_tokens"}:
        raise ParallelWaveError("invalid reviewer fields")
    _text(reviewer["user"], "reviewer user")
    _integer(reviewer["max_output_tokens"], 1, limit, "reviewer output cap")
    _integer(plan["max_model_requests"], len(tasks) + 1, 128, "request cap")
    if len(_canonical(plan)) > MAX_JSON_BYTES:
        raise ParallelWaveError("plan exceeds byte bound")
    return json.loads(_canonical(plan))


def _sources() -> dict[str, str]:
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
    return {f"scripts/{name}.py": _sha((root / f"{name}.py").read_bytes()) for name in sorted(seen)}


def _claim_args(run_dir: Path, state: dict) -> dict:
    return {"schedule_sha256": state["plan_sha256"], "run_id": state["run_id"],
            "selected_owner": admission.owner("oneshot", run_dir, run_dir),
            "root_descriptor": state["admission_descriptor"]}


def _claim_override(state: dict) -> Path:
    return Path(state["admission_descriptor"]["local_run_admission_root"])


def _check_budget(plan: dict, snapshot: dict) -> None:
    if (snapshot["limit_tokens"] != plan["limit_tokens"]
            or snapshot["max_requests"] != plan["max_model_requests"]
            or snapshot["cost_limit_micro_usd"] != plan["cost_limit_micro_usd"]
            or snapshot["price_profile"] != plan["price_profile"]
            or snapshot["effort"] != plan["effort"]):
        raise ParallelWaveError("wave ledger caps or model/effort changed")


def prepare_wave(run_dir: Path, plan: dict, *, admission_root: Path | None = None) -> dict:
    plan = _validate_plan(plan)
    run_dir = Path(run_dir)
    if not run_dir.is_absolute() or any(part in (".", "..") for part in run_dir.parts):
        raise ParallelWaveError("run directory must be absolute")
    _private_dir(run_dir.parent)
    if run_dir.exists() or run_dir.is_symlink():
        raise FileExistsError("wave directory already exists")
    descriptor = admission.descriptor(admission_root)
    plan_raw = _canonical(plan)
    state = {"schema": 1, "classification": CLASSIFICATION, "state": "prepared",
             "plan_sha256": _sha(plan_raw), "run_id": plan["run_id"],
             "admission_descriptor": descriptor, "claim_sha256": "",
             "source_digests": _sources(), "reason": None,
             "completed_requests": 0, "artifact_count": 0}
    state["claim_sha256"] = admission.claim_digest(**_claim_args(run_dir, state))
    run_dir.mkdir(mode=0o700)
    _new_private_file(run_dir / ".lock", b"")
    for name in JOURNALS:
        (run_dir / name).mkdir(mode=0o700)
    _new_private_file(run_dir / "plan.json", plan_raw)
    _new_private_file(run_dir / "run.json", _canonical(state))
    WaveLedger.create(run_dir / "ledger", plan["limit_tokens"], plan["max_model_requests"],
                      cost_limit_micro_usd=plan["cost_limit_micro_usd"],
                      price_profile=plan["price_profile"], effort=plan["effort"])
    bindings = {"ledger_kind": "wave_v1", "ledger_schema": 3,
                "plan_sha256": state["plan_sha256"], "run_id": state["run_id"],
                "claim_sha256": state["claim_sha256"], "source_digests": state["source_digests"]}
    RunContext.create(run_dir / "context", run_dir / "ledger", bindings,
                      active_limit_seconds=plan["active_limit_seconds"], max_tool_calls=0,
                      roles=["coordinator"], ledger_kind="wave_v1",
                      journal_roots=[run_dir / name for name in JOURNALS] +
                      [run_dir / "plan.json", run_dir / "run.json", run_dir / "ledger"])
    return read_wave_status(run_dir)


def _load(run_dir: Path) -> tuple[dict, dict, WaveLedger, RunContext]:
    _private_dir(run_dir)
    for name in (*JOURNALS, "ledger", "context"):
        _private_dir(run_dir / name)
    state = _read_json(run_dir / "run.json")
    if (type(state) is not dict or set(state) != STATE_KEYS or type(state["schema"]) is not int or state["schema"] != 1
            or state["classification"] != CLASSIFICATION
            or state["state"] not in {"prepared", "started", "completed", "indeterminate"}
            or state["source_digests"] != _sources()):
        raise ParallelWaveError("wave state or source closure changed")
    for name in ("completed_requests", "artifact_count"):
        _integer(state[name], 0, 5, name)
    plan = _validate_plan(_read_json(run_dir / "plan.json"))
    if _sha((run_dir / "plan.json").read_bytes()) != state["plan_sha256"] or plan["run_id"] != state["run_id"]:
        raise ParallelWaveError("frozen wave plan changed")
    if admission.claim_digest(**_claim_args(run_dir, state)) != state["claim_sha256"]:
        raise ParallelWaveError("wave admission identity changed")
    if list((run_dir / "tool_reservations").iterdir()) or list((run_dir / "tool_receipts").iterdir()):
        raise ParallelWaveError("textual waves cannot have tool records")
    ledger, context = WaveLedger(run_dir / "ledger"), RunContext(run_dir / "context")
    snapshot = ledger.status()
    _check_budget(plan, snapshot)
    return plan, state, ledger, context


def _view(plan: dict, state: dict, ledger: WaveLedger, context: RunContext) -> dict:
    status = context.status()
    published = status["state"] == state["state"] == "completed"
    artifact_paths = sorted((context.directory.parent / "artifacts").iterdir())
    artifacts = ([{"path": str(path), "sha256": _sha(path.read_bytes())} for path in artifact_paths]
                 if published else [])
    return {"classification": CLASSIFICATION, "execution_profile": PROFILE,
            "state": status["state"], "stored_state": state["state"],
            "run_id": plan["run_id"], "checkpoint_sha256": status["checkpoint_sha256"],
            "cursor": status["cursor"], "active_seconds": status["active_seconds"],
            "remaining_active_seconds": status["remaining_active_seconds"],
            "completed_requests": state["completed_requests"], "artifact_count": len(artifacts),
            "artifacts": artifacts, "forensic_artifact_entry_count": 0 if published else len(artifact_paths),
            "reason": state["reason"], "budget": ledger.status(), "tools_enabled": False,
            "identity_authenticated": False, "cost_authenticated": False,
            "formal_cell_executed": False, "core_mutated": False,
            "remote_cancellation_guaranteed": False}


def read_wave_status(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    with _run_lock(run_dir):
        return _view(*_load(run_dir))


class _RemainingTransport:
    """Reuse an HTTP adapter in this runtime without mutating its timeout."""

    def __init__(self, original: Any, deadline: float):
        self.original, self.deadline = original, deadline

    @property
    def _timeout(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ParallelWaveError("wave deadline expired")
        return remaining

    def __getattr__(self, name: str) -> Any:
        if name in {"_api_key", "_base_url", "_opener"}:
            return getattr(self.original, name)
        raise AttributeError(name)

    def _post(self, endpoint: str, payload: dict) -> dict:
        return OpenAIResponsesHTTP._post(self, endpoint, payload)

    def operation(self, kind: str, payload: dict) -> Any:
        if isinstance(self.original, OpenAIResponsesHTTP):
            return getattr(OpenAIResponsesHTTP, kind)(self, payload)
        return getattr(self.original, kind)(payload, timeout_seconds=self._timeout)


def _request(plan: dict, task: dict, artifacts: list[dict] | None = None) -> dict:
    content = {"common_context": plan["context"], "task": task["user"]}
    if artifacts is None:
        content.update(task_id=task["task_id"], role=task["role"], owned_node_ids=task["owned_node_ids"])
    else:
        content["worker_artifacts"] = artifacts
    return _validated_request({"model": plan["model"], "reasoning": {"effort": plan["effort"]},
                               "service_tier": "default", "max_output_tokens": task["max_output_tokens"],
                               "input": [{"role": "user", "content": _json_bytes(content).decode()}]})


def _response_text(response: Any, model: str) -> str:
    if (type(response) is not dict or type(response.get("id")) is not str or not response["id"]
            or response.get("model") != model or response.get("status") != "completed"
            or response.get("service_tier") != "default"
            or type(response.get("output")) is not list or not response["output"]):
        raise ParallelWaveError("invalid, cross-model or incomplete wave response")
    texts = []
    for item in response["output"]:
        if type(item) is not dict:
            raise ParallelWaveError("response item is invalid")
        if item.get("type") == "reasoning":
            continue
        if (item.get("type") != "message" or item.get("role") != "assistant"
                or item.get("status", "completed") != "completed"
                or type(item.get("content")) is not list or not item["content"]):
            raise ParallelWaveError("textual wave rejects tools and unsupported output")
        for part in item["content"]:
            if type(part) is not dict or part.get("type") != "output_text":
                raise ParallelWaveError("textual wave rejects non-text content")
            texts.append(_text(part.get("text"), "proposal text", 1048576))
    text = "\n".join(texts)
    _text(text, "final proposal text", 1048576)
    return text


def _batch(
    run_dir: Path, plan: dict, tasks: list[dict], requests: list[dict], transports: dict,
    wave_id: str, ledger: WaveLedger, context: RunContext, guard: Callable[[], None],
    state: dict, *, request_ids: dict[str, str] | None = None,
    decoder: Callable[[dict, str], dict] | None = None,
) -> list[dict]:
    assert context.deadline is not None
    deadline = context.deadline
    results: queue.Queue = queue.Queue()
    stop = threading.Event()
    gate = threading.Event()
    digests = {task["task_id"]: _sha(_json_bytes(request)) for task, request in zip(tasks, requests, strict=True)}
    by_id = {task["task_id"]: task for task in tasks}
    request_ids = ({key: key for key in by_id} if request_ids is None else request_ids.copy())
    if (set(request_ids) != set(by_id) or len(set(request_ids.values())) != len(by_id)
            or any(type(value) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value) is None
                   for value in request_ids.values())):
        raise ParallelWaveError("invalid batch request identities")
    sending = False

    def worker(task: dict, request: dict, operation: str) -> None:
        task_id = task["task_id"]
        result = started = ended = None
        try:
            if operation == "send":
                gate.wait()
            if stop.is_set():
                return
            guard()
            original = _json_bytes(request)
            payload = json.loads(original)
            if operation == "count_input":
                payload.pop("max_output_tokens")
                payload.pop("service_tier")
            else:
                payload.update(store=False, stream=False)
            payload_bytes = _json_bytes(payload)
            started = time.monotonic_ns()
            result = _RemainingTransport(transports[task_id], deadline).operation(operation, payload)
            ended = time.monotonic_ns()
            guard()
            if _json_bytes(payload) != payload_bytes or _json_bytes(request) != original:
                raise ParallelWaveError("transport mutated request while counting or sending")
            if not stop.is_set():
                results.put((task_id, result, None, started, ended))
        except BaseException as exc:
            if not stop.is_set():
                results.put((task_id, result, type(exc).__name__, started, ended))

    def preserve_response(task_id: str, response: Any, ended: int | None) -> str | None:
        # Forensic preservation is a host effect, never a successful publication.
        # Keep responses observed by the deadline even when a post-I/O guard fails.
        if ended is None or ended / 1_000_000_000 >= deadline:
            return None
        raw = _json_bytes(response) + b"\n"
        if len(raw) > MAX_JSON_BYTES:
            raise ParallelWaveError("response exceeds byte bound")
        path = run_dir / "responses" / f"{request_ids[task_id]}.json"
        if not path.exists():
            _new_private_file(path, raw)
        return _sha(raw)

    def accept_response(task_id: str, response: dict, started: int, ended: int, response_sha: str) -> dict:
        guard()
        task = by_id[task_id]
        decoded = ({"text": _response_text(response, plan["model"])} if decoder is None
                   else decoder(response, plan["model"]))
        request_id = request_ids[task_id]
        usage = response.get("usage")
        measured = ({key: usage.get(key) for key in ("input_tokens", "output_tokens", "total_tokens")}
                    if type(usage) is dict else usage)
        details = ({key: usage[key] for key in ("input_tokens_details", "output_tokens_details") if key in usage}
                   if type(usage) is dict else None)
        guard()
        settled = ledger.settle(request_id, response_sha, measured, usage_details=details)
        _new_private_file(run_dir / "receipts" / f"{request_id}.json", _canonical({
            "request_id": request_id, "role": task["role"], "payload_sha256": digests[task_id],
            "response_sha256": response_sha, "send_started_ns": started, "send_ended_ns": ended,
            "classification": state["classification"], "settled": settled}))
        state["completed_requests"] += 1
        _write_state(run_dir, state)
        guard()
        artifact = {"task_id": task_id, "role": task["role"], **decoded}
        if decoder is not None:
            artifact["request_id"] = request_id
        if "owned_node_ids" in task:
            artifact["owned_node_ids"] = task["owned_node_ids"]
        artifact["artifact_sha256"] = _sha(_canonical(artifact))
        return artifact

    def collect(number: int, *, preserve: bool = False) -> dict:
        collected = {}
        for _ in range(number):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ParallelWaveError("wave deadline expired")
            try:
                task_id, result, error, started, ended = results.get(timeout=remaining)
            except queue.Empty as exc:
                raise ParallelWaveError("wave deadline expired") from exc
            response_sha = preserve_response(task_id, result, ended) if preserve and task_id in by_id else None
            guard()
            if error is not None:
                raise ParallelWaveError(f"worker transport failed: {error}")
            if task_id in collected:
                raise ParallelWaveError("duplicate worker result")
            collected[task_id] = (accept_response(task_id, result, started, ended, response_sha)
                                  if preserve else (result, started, ended))
        return collected

    try:
        guard()
        budget = ledger.status()
        if budget["blocked"] or budget["request_count"] + len(tasks) > plan["max_model_requests"]:
            raise ParallelWaveError("wave request cap or unresolved reservation blocks count")
        for task, request in zip(tasks, requests, strict=True):
            threading.Thread(target=worker, args=(task, request, "count_input"), daemon=True).start()
        counted = collect(len(tasks))
        items = []
        for task in tasks:
            count = counted[task["task_id"]][0]
            _integer(count, 1, 10**9, "input count")
            items.append({"request_id": request_ids[task["task_id"]], "role": task["role"],
                          "payload_sha256": digests[task["task_id"]], "input_tokens": count,
                          "max_output_tokens": task["max_output_tokens"], "model": plan["model"], "effort": plan["effort"]})
        guard()
        permit = ledger.reserve_wave(wave_id, items)
        for task, request in zip(tasks, requests, strict=True):
            guard()
            task_id = task["task_id"]
            _new_private_file(run_dir / "requests" / f"{request_ids[task_id]}.json", _canonical(request))
            permit.begin_send(request_ids[task_id], digests[task_id])
            threading.Thread(target=worker, args=(task, request, "send"), daemon=True).start()
        guard()
        gate.set()
        sending = True
        received = collect(len(tasks), preserve=True)
        guard()
        return [received[task["task_id"]] for task in tasks]
    finally:
        stop.set()
        gate.set()
        if sending:
            # Preserve only responses already available to this host. No joining,
            # waiting for further responses, settlement, or late callback writes.
            while True:
                try:
                    task_id, result, _, _, ended = results.get_nowait()
                except queue.Empty:
                    break
                if task_id in by_id:
                    preserve_response(task_id, result, ended)


def execute_wave(run_dir: Path, transports_by_task: dict, *, expected_checkpoint: str,
                 guard: Callable[[], None] | None = None) -> dict:
    run_dir = Path(run_dir)
    with _run_lock(run_dir):
        plan, state, ledger, context = _load(run_dir)
        if state["state"] != "prepared" or context.status()["state"] != "prepared":
            raise ParallelWaveError("started or terminal wave never reexecutes")
        expected_transports = {task["task_id"] for task in plan["tasks"]} | {"reviewer"}
        if type(transports_by_task) is not dict or set(transports_by_task) != expected_transports:
            raise ParallelWaveError("transport keys must match tasks and reviewer")
        if guard is not None and not callable(guard):
            raise ParallelWaveError("base guard must be callable")
        context.begin(expected_checkpoint, "coordinator")
        state["state"] = "started"
        try:
            _write_state(run_dir, state)
            if admission.acquire_staged_claim(**_claim_args(run_dir, state),
                                              override=_claim_override(state)) != state["claim_sha256"]:
                raise ParallelWaveError("wave did not acquire expected claim")

            def active_guard() -> None:
                context.require_active()
                if _sources() != state["source_digests"]:
                    raise ParallelWaveError("wave source closure changed")
                if _sha((run_dir / "plan.json").read_bytes()) != state["plan_sha256"]:
                    raise ParallelWaveError("frozen wave plan changed")
                if admission.require_claim(**_claim_args(run_dir, state),
                                           override=_claim_override(state)) != state["claim_sha256"]:
                    raise ParallelWaveError("wave claim changed")
                if guard is not None:
                    guard()
                _check_budget(plan, ledger.status())
                context.require_active()

            active_guard()
            artifacts = _batch(run_dir, plan, plan["tasks"], [_request(plan, task) for task in plan["tasks"]],
                               transports_by_task, "workers", ledger, context, active_guard, state)
            reviewer = {**plan["reviewer"], "task_id": "reviewer", "role": "reviewer"}
            reviewed = _batch(run_dir, plan, [reviewer], [_request(plan, reviewer, artifacts)],
                              transports_by_task, "review", ledger, context, active_guard, state)
            active_guard()
            for artifact in artifacts + reviewed:
                active_guard()
                _new_private_file(run_dir / "artifacts" / f"{artifact['task_id']}.json", _canonical(artifact))
            state.update(state="completed", artifact_count=len(artifacts) + len(reviewed))
            _write_state(run_dir, state)
            active_guard()
            context.finish(1)
        except BaseException as exc:
            state.update(state="indeterminate", reason=type(exc).__name__)
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
        return _view(plan, state, ledger, context)
