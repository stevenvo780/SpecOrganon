"""One-shot, offline-development bridge between Responses and sealed staged tools.

Prepare binds an independent schedule, a staged run, one strict primitive
function, executable bytes, and a declared price profile. Execute sends a
two-turn conversation once with a shared token/cost ledger and process deadline.
The local journal is same-UID evidence, not external custody or a provider bill.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import sys
import time
from pathlib import Path
from typing import Any, Callable

import local_run_admission as admission
from managed_token_ledger import (
    BudgetError, CostBudgetExhausted, TokenBudgetExhausted, TokenLedger,
)
from run_managed_conversation import (
    _DeadlineTransport, _canonical, _deadline, _new_private_file, _private_dir,
    _private_file, _read_json, _run_lock, _unique_pairs, _write_state,
)
from run_managed_response import (
    MAX_JSON_BYTES, DispatchError, OpenAIResponsesHTTP, ResponseTransport,
    _json_bytes, _parse_function_arguments, _read_json_file, _validated_request,
    dispatch_response,
)
from run_staged_local_tool import MAX_EXECUTABLE_BYTES
from staged_tool_session import (
    MAX_TOOL_ARGS_BYTES, SessionError, call_tool, create_session, resume_session,
)
from tool_policy import MAX_POLICY_BYTES, _read_bounded_file
from verify_released_run import _read_schedule


CLASSIFICATION = "development_managed_tool_conversation_unsealed"
MAX_OUTPUT_BYTES = 64 * 1024
MAX_REQUESTS = 32
MAX_TOOL_CALLS = 16
MAX_ACTIVE_SECONDS = 5_400
MAX_TOKENS = 80_000
STATE_KEYS = {
    "schema", "state", "reason", "plan_sha256", "schedule_path",
    "schedule_bytes_sha256", "run_id", "model", "stage_dir", "session_dir",
    "session_manifest_sha256", "tool_binding", "limit_tokens",
    "active_limit_seconds", "cost_limit_micro_usd", "price_profile_sha256",
    "max_model_requests", "max_tool_calls", "model_requests_completed",
    "tool_calls_completed", "turns_completed", "active_seconds",
}


class ToolConversationError(ValueError):
    """The prepared tool conversation cannot proceed safely."""


class _ClaimedTransport(_DeadlineTransport):
    """Recheck the staged attempt owner before each provider operation."""

    def __init__(self, transport: ResponseTransport, deadline: float,
                 claim_args: dict[str, Any], expected_claim: str) -> None:
        super().__init__(transport, deadline)
        self.claim_args = claim_args
        self.expected_claim = expected_claim

    def _require_claim(self) -> None:
        self.check()
        if admission.require_claim(**self.claim_args) != self.expected_claim:
            raise ToolConversationError("local admission claim differs from prepared tool session")

    def count_input(self, payload: dict[str, Any]) -> int:
        self._require_claim()
        return super().count_input(payload)

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_claim()
        return super().send(payload)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_bytes(path: Path, limit: int, label: str) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ToolConversationError(f"{label} must be a regular file, not a symlink")
    if info.st_size > limit:
        raise ToolConversationError(f"{label} exceeds the byte limit")
    data = path.read_bytes()
    if len(data) != info.st_size or len(data) > limit:
        raise ToolConversationError(f"{label} changed while being read")
    return data


def _absolute(path: Path, label: str) -> Path:
    if not path.is_absolute() or any(part in (".", "..") for part in path.parts):
        raise ToolConversationError(f"{label} must be absolute without dot components")
    return path


def _schedule_at(path: Path) -> tuple[dict[str, Any], str]:
    _absolute(path, "schedule path")
    data = _file_bytes(path, MAX_JSON_BYTES, "schedule")
    schedule = _read_schedule(str(path))
    if type(schedule) is not dict or data != _file_bytes(path, MAX_JSON_BYTES, "schedule"):
        raise ToolConversationError("schedule changed during validation")
    return schedule, _sha(data)


def _provider_tool(function: dict[str, Any]) -> dict[str, Any]:
    return {key: function[key] for key in
            ("type", "name", "description", "parameters", "strict")}


def _validate_plan(raw: Any, schedule: dict[str, Any]) -> dict[str, Any]:
    required = {"schema", "run_id", "model", "service_tier", "turns", "functions",
                "max_model_requests", "max_tool_calls", "tool_wall_seconds"}
    optional = {"instructions", "reasoning"}
    if type(raw) is not dict or not required <= set(raw) or set(raw) - required - optional:
        raise ToolConversationError("tool conversation plan fields are invalid")
    if raw["schema"] != 1 or type(raw["schema"]) is not int:
        raise ToolConversationError("unsupported tool conversation plan schema")
    run = next((item for item in schedule["runs"] if item["run_id"] == raw["run_id"]), None)
    if run is None or raw["model"] != run["model_id"]:
        raise ToolConversationError("plan run_id or model differs from schedule")
    effort = run.get("effort_provider_value")
    if ((effort is None and "reasoning" in raw)
            or (effort is not None and raw.get("reasoning") != {"effort": effort})):
        raise ToolConversationError("plan reasoning differs from scheduled effort")
    if raw["service_tier"] != "default":
        raise ToolConversationError("priced plan requires explicit default service tier")
    turns = raw["turns"]
    if (type(turns) is not list or len(turns) != 2
            or any(type(item) is not dict or set(item) != {"user", "max_output_tokens"}
                   or type(item["user"]) is not str or not item["user"]
                   or type(item["max_output_tokens"]) is not int
                   or item["max_output_tokens"] < 1 for item in turns)):
        raise ToolConversationError("plan needs exactly two bounded text user turns")
    if (type(raw["max_model_requests"]) is not int
            or not 2 <= raw["max_model_requests"] <= MAX_REQUESTS
            or type(raw["max_tool_calls"]) is not int
            or not 0 <= raw["max_tool_calls"] <= MAX_TOOL_CALLS
            or raw["max_tool_calls"] > schedule["per_run_limits"]["tool_calls"]
            or type(raw["tool_wall_seconds"]) not in (int, float)
            or not 0 < raw["tool_wall_seconds"] <= 300):
        raise ToolConversationError("model, tool, or tool wall cap is invalid")
    if (schedule.get("schema") == "specorganon.development_round_schedule.v1"
            and raw["max_model_requests"] > schedule["max_model_requests"]):
        raise ToolConversationError("model request cap exceeds development schedule")
    functions = raw["functions"]
    if type(functions) is not list or len(functions) != 1 or type(functions[0]) is not dict:
        raise ToolConversationError("this bridge supports exactly one sealed function")
    function = functions[0]
    if set(function) != {"type", "name", "description", "parameters", "strict",
                         "tool_id", "executable"}:
        raise ToolConversationError("function declaration or local binding is invalid")
    _absolute(Path(function["executable"]), "tool executable")
    request = {
        "model": raw["model"], "service_tier": "default",
        "input": [{"role": "user", "content": turns[0]["user"]}],
        "max_output_tokens": turns[0]["max_output_tokens"],
        "tools": [_provider_tool(function)], "parallel_tool_calls": False,
    }
    for key in optional:
        if key in raw:
            request[key] = raw[key]
    _validated_request(request)
    if len(_canonical(raw)) > MAX_JSON_BYTES:
        raise ToolConversationError("plan exceeds the byte limit")
    return json.loads(_json_bytes(raw))


def _tool_binding(stage: Path, schedule: dict[str, Any], function: dict[str, Any]) -> dict[str, str]:
    policy_bytes = _read_bounded_file(stage / "inputs" / "tool_policy",
                                      "staged tool policy", MAX_POLICY_BYTES)
    if _sha(policy_bytes) != schedule["inputs"]["tool_policy"]["sha256"]:
        raise ToolConversationError("staged policy differs from independent schedule")
    policy = json.loads(policy_bytes, object_pairs_hook=_unique_pairs)
    entry = next((item for item in policy["generic_tools"]
                  if item["id"] == function["tool_id"]), None)
    if entry is None:
        raise ToolConversationError("function tool_id is absent from staged policy")
    executable = _absolute(Path(function["executable"]), "tool executable")
    raw = _read_bounded_file(executable, "tool executable", MAX_EXECUTABLE_BYTES)
    digest = _sha(raw)
    if digest != entry["executable_sha256"] or not os.access(executable, os.X_OK):
        raise ToolConversationError("function executable differs from sealed policy")
    return {"name": function["name"], "tool_id": function["tool_id"],
            "executable": str(executable), "executable_sha256": digest}


def _check_cost(state: dict[str, Any], ledger: TokenLedger, plan: dict[str, Any]) -> dict[str, Any]:
    budget = ledger.status()
    if (budget["cost_limit_micro_usd"] is None
            or budget["cost_limit_micro_usd"] != state["cost_limit_micro_usd"]
            or budget["price_profile_sha256"] != state["price_profile_sha256"]
            or budget["price_profile"]["model"] != plan["model"]
            or budget["max_requests"] != plan["max_model_requests"]
            or budget["limit_tokens"] != state["limit_tokens"]):
        raise ToolConversationError("cost, model, or ledger binding differs from preparation")
    return budget


def _validate_state(state: dict[str, Any]) -> None:
    if (set(state) != STATE_KEYS or type(state["schema"]) is not int
            or state["schema"] != 1
            or type(state["state"]) is not str
            or state["state"] not in {"prepared", "started", "completed",
                                     "truncated", "indeterminate"}
            or state["reason"] is not None and type(state["reason"]) is not str
            or state["state"] in {"prepared", "completed"} and state["reason"] is not None
            or state["state"] in {"truncated", "indeterminate"} and not state["reason"]
            or type(state["run_id"]) is not str
            or type(state["model"]) is not str
            or type(state["tool_binding"]) is not dict
            or any(type(state[key]) is not str for key in
                   ("plan_sha256", "schedule_path", "schedule_bytes_sha256",
                    "stage_dir", "session_dir", "session_manifest_sha256",
                    "price_profile_sha256"))
            or any(type(state[key]) is not int for key in
                   ("limit_tokens", "active_limit_seconds", "cost_limit_micro_usd",
                    "max_model_requests", "max_tool_calls", "model_requests_completed",
                    "tool_calls_completed", "turns_completed"))
            or not 1 <= state["active_limit_seconds"] <= MAX_ACTIVE_SECONDS
            or not 0 <= state["model_requests_completed"] <= state["max_model_requests"]
            or not 0 <= state["tool_calls_completed"] <= state["max_tool_calls"]
            or not 0 <= state["turns_completed"] <= 2
            or state["state"] == "completed" and state["turns_completed"] != 2
            or state["state"] == "prepared" and any(state[key] for key in
                ("model_requests_completed", "tool_calls_completed", "turns_completed"))
            or type(state["active_seconds"]) not in (int, float)
            or not math.isfinite(state["active_seconds"])
            or state["active_seconds"] < 0):
        raise ToolConversationError("run state is inconsistent")


def _load(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], TokenLedger]:
    _private_dir(run_dir)
    for name in ("requests", "responses", "receipts", "tool_reservations",
                 "tool_receipts", "ledger"):
        _private_dir(run_dir / name)
    for name in (".lock", "plan.json", "run.json"):
        _private_file(run_dir / name)
    state = _read_json(run_dir / "run.json")
    _validate_state(state)
    schedule_path = _absolute(Path(state["schedule_path"]), "schedule path")
    schedule, schedule_sha = _schedule_at(schedule_path)
    if schedule_sha != state["schedule_bytes_sha256"]:
        raise ToolConversationError("schedule bytes changed after preparation")
    if state["active_limit_seconds"] > schedule["per_run_limits"]["active_seconds"]:
        raise ToolConversationError("active time ceiling exceeds the schedule")
    plan_bytes = (run_dir / "plan.json").read_bytes()
    if _sha(plan_bytes) != state["plan_sha256"]:
        raise ToolConversationError("plan bytes changed after preparation")
    plan = _validate_plan(_read_json(run_dir / "plan.json"), schedule)
    if (state["run_id"] != plan["run_id"]
            or state["model"] != plan["model"]
            or state["max_model_requests"] != plan["max_model_requests"]
            or state["max_tool_calls"] != plan["max_tool_calls"]):
        raise ToolConversationError("run metadata differs from the prepared plan")
    stage = _absolute(Path(state["stage_dir"]), "stage path")
    session = _absolute(Path(state["session_dir"]), "session path")
    if session != run_dir / "tool_session":
        raise ToolConversationError("tool session path differs from run directory")
    binding = _tool_binding(stage, schedule, plan["functions"][0])
    if binding != state["tool_binding"]:
        raise ToolConversationError("sealed executable binding changed")
    manifest = _file_bytes(session / "session.json", MAX_JSON_BYTES, "session manifest")
    if _sha(manifest) != state["session_manifest_sha256"]:
        raise ToolConversationError("tool session manifest changed")
    tool_status = resume_session(schedule, plan["run_id"], stage, session)
    if tool_status["run_id"] != plan["run_id"]:
        raise ToolConversationError("tool session run_id differs from plan")
    ledger = TokenLedger(run_dir / "ledger")
    budget = _check_cost(state, ledger, plan)
    uncertain = state["state"] in {"started", "indeterminate"}
    if (not uncertain
            and tool_status["reserved_tool_calls"] != state["tool_calls_completed"]
            or uncertain
            and not state["tool_calls_completed"] <= tool_status["reserved_tool_calls"]
            <= state["tool_calls_completed"] + 1
            or not uncertain
            and budget["request_count"] != state["model_requests_completed"]
            or uncertain
            and not state["model_requests_completed"] <= budget["request_count"]
            <= state["model_requests_completed"] + 1):
        raise ToolConversationError("local reservations differ from run state")
    return plan, state, tool_status, ledger


def prepare_tool_conversation(
    run_dir: Path, schedule_path: Path, stage_dir: Path, plan: dict[str, Any], *,
    limit_tokens: int, active_limit_seconds: int,
    cost_limit_micro_usd: int, price_profile: dict[str, Any],
) -> dict[str, Any]:
    """Prepare private journals and an empty sealed tool session without sending."""
    run_dir = _absolute(Path(run_dir), "run directory")
    stage = _absolute(Path(stage_dir), "stage directory")
    schedule_path = _absolute(Path(schedule_path), "schedule path")
    schedule, schedule_sha = _schedule_at(schedule_path)
    validated = _validate_plan(plan, schedule)
    if (type(limit_tokens) is not int or not 1 <= limit_tokens <= MAX_TOKENS
            or limit_tokens > schedule["per_run_limits"]["measured_tokens"]
            or type(active_limit_seconds) is not int
            or not 1 <= active_limit_seconds <= MAX_ACTIVE_SECONDS
            or active_limit_seconds > schedule["per_run_limits"]["active_seconds"]
            or type(cost_limit_micro_usd) is not int or cost_limit_micro_usd < 0
            or type(price_profile) is not dict or price_profile.get("model") != validated["model"]):
        raise ToolConversationError("token, time, or declared cost ceiling is invalid")
    if schedule.get("schema") == "specorganon.development_round_schedule.v1":
        from plan_development_round import validate_runtime_budget
        validate_runtime_budget(
            schedule, max_model_requests=validated["max_model_requests"],
            cost_limit_micro_usd=cost_limit_micro_usd, price_profile=price_profile)
    binding = _tool_binding(stage, schedule, validated["functions"][0])
    if run_dir.exists():
        raise FileExistsError("run directory already exists")
    run_dir.mkdir(mode=0o700)
    run_dir.chmod(0o700)
    for name in ("requests", "responses", "receipts", "tool_reservations", "tool_receipts"):
        (run_dir / name).mkdir(mode=0o700)
    ledger = TokenLedger.create(
        run_dir / "ledger", limit_tokens, validated["max_model_requests"],
        cost_limit_micro_usd=cost_limit_micro_usd, price_profile=price_profile,
    )
    budget = ledger.status()
    session = run_dir / "tool_session"
    session_status = create_session(schedule, validated["run_id"], stage, session)
    if session_status["status"] != "ready" or session_status["reserved_tool_calls"] != 0:
        raise ToolConversationError("new staged tool session is not empty and ready")
    raw_plan = _canonical(validated)
    _new_private_file(run_dir / "plan.json", raw_plan)
    _new_private_file(run_dir / ".lock", b"")
    state = {
        "schema": 1, "state": "prepared", "reason": None,
        "plan_sha256": _sha(raw_plan), "schedule_path": str(schedule_path),
        "schedule_bytes_sha256": schedule_sha, "run_id": validated["run_id"],
        "model": validated["model"], "stage_dir": str(stage),
        "session_dir": str(session),
        "session_manifest_sha256": _sha((session / "session.json").read_bytes()),
        "tool_binding": binding,
        "limit_tokens": limit_tokens,
        "active_limit_seconds": active_limit_seconds,
        "cost_limit_micro_usd": cost_limit_micro_usd,
        "price_profile_sha256": budget["price_profile_sha256"],
        "max_model_requests": validated["max_model_requests"],
        "max_tool_calls": validated["max_tool_calls"],
        "model_requests_completed": 0, "tool_calls_completed": 0,
        "turns_completed": 0, "active_seconds": 0.0,
    }
    _new_private_file(run_dir / "run.json", _canonical(state))
    return read_tool_conversation_status(run_dir)


def _request(plan: dict[str, Any], history: list[dict[str, Any]], turn: int) -> dict[str, Any]:
    request = {
        "model": plan["model"], "service_tier": "default",
        "input": history.copy(),
        "max_output_tokens": plan["turns"][turn - 1]["max_output_tokens"],
        "tools": [_provider_tool(plan["functions"][0])],
        "parallel_tool_calls": False,
    }
    for key in ("instructions", "reasoning"):
        if key in plan:
            request[key] = plan[key]
    return _validated_request(request)


def _response_kind(response: dict[str, Any], function: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    output = response.get("output")
    if type(output) is not list or not output:
        return "unsupported", None
    calls = [item for item in output if type(item) is dict
             and item.get("type") == "function_call"]
    if len(calls) > 1:
        return "unsupported", None
    if calls:
        call = calls[0]
        if (output[-1] is not call or call.get("name") != function["name"]
                or type(call.get("call_id")) is not str or not call["call_id"]
                or call.get("status", "completed") != "completed"):
            return "unsupported", None
        for preceding in output[:-1]:
            if (type(preceding) is not dict
                    or preceding.get("type") != "reasoning"
                    or type(preceding.get("encrypted_content")) is not str
                    or not preceding["encrypted_content"]):
                return "unsupported", None
        try:
            parsed = _parse_function_arguments(_provider_tool(function), call.get("arguments"))
        except DispatchError:
            return "unsupported", None
        if len(_json_bytes(parsed)) > MAX_TOOL_ARGS_BYTES:
            return "unsupported", None
        return "function", call
    text = []
    for item in output:
        if type(item) is not dict:
            return "unsupported", None
        if item.get("type") == "reasoning":
            if type(item.get("encrypted_content")) is not str or not item["encrypted_content"]:
                return "unsupported", None
        elif item.get("type") == "message" and item.get("role") == "assistant":
            parts = item.get("content")
            if type(parts) is not list or not parts:
                return "unsupported", None
            for part in parts:
                if (type(part) is not dict or part.get("type") != "output_text"
                        or type(part.get("text")) is not str):
                    return "unsupported", None
                text.append(part["text"])
        else:
            return "unsupported", None
    return ("text" if any(text) else "unsupported"), None


def _tool_stream(path: Path, expected: Path) -> tuple[str, str]:
    if path != expected:
        raise ToolConversationError("tool stream path differs from numbered session call")
    raw = _file_bytes(expected, MAX_OUTPUT_BYTES, "tool stream")
    if stat.S_IMODE(expected.stat().st_mode) != 0o600:
        raise ToolConversationError("tool stream is not private")
    try:
        decoded = raw.decode("utf-8")
    except UnicodeError as exc:
        raise ToolConversationError("tool stream is not UTF-8") from exc
    return decoded, _sha(raw)


def _invoke_tool(
    run_dir: Path, plan: dict[str, Any], state: dict[str, Any],
    schedule: dict[str, Any], request_index: int, turn: int,
    call: dict[str, Any], response_sha: str, request_sha: str,
    deadline: float, *, guard: Callable[[], None] | None = None,
) -> dict[str, Any]:
    next_number = state["tool_calls_completed"] + 1
    if next_number > plan["max_tool_calls"]:
        raise TokenBudgetExhausted("tool call cap exhausted before launch")
    session = Path(state["session_dir"])
    stage = Path(state["stage_dir"])
    status = resume_session(schedule, plan["run_id"], stage, session)
    if status["status"] != "ready" or status["reserved_tool_calls"] != next_number - 1:
        raise ToolConversationError("staged tool session cannot reserve the next call")
    remaining = deadline - time.monotonic()
    wall_seconds = min(float(plan["tool_wall_seconds"]), remaining - 1.0)
    if wall_seconds <= 0:
        raise TokenBudgetExhausted("active deadline exhausted before tool launch")
    function = plan["functions"][0]
    arguments = _parse_function_arguments(_provider_tool(function), call["arguments"])
    arguments_sha = _sha(_json_bytes(arguments))
    reservation = {
        "schema": 1, "run_id": plan["run_id"], "tool_call_number": next_number,
        "request_index": request_index, "turn": turn,
        "call_id": call["call_id"], "name": function["name"],
        "tool_id": function["tool_id"], "arguments_sha256": arguments_sha,
        "request_sha256": request_sha, "response_sha256": response_sha,
        "session_call_number": next_number,
    }
    name = f"{next_number:04d}.json"
    reservation_path = run_dir / "tool_reservations" / name
    _new_private_file(reservation_path, _canonical(reservation))
    if guard is not None:
        guard()
    terminal = call_tool(
        schedule, plan["run_id"], stage, session, function["tool_id"],
        function["executable"], tool_args=arguments, wall_seconds=wall_seconds,
    )
    if guard is not None:
        guard()
    terminal_path = session / "calls" / f"{next_number:06d}" / "terminal.json"
    terminal_raw = _file_bytes(terminal_path, MAX_JSON_BYTES, "tool terminal")
    if _sha(terminal_raw) != _sha(_canonical(terminal)):
        raise ToolConversationError("tool terminal return differs from durable receipt")
    if (terminal.get("run_id") != plan["run_id"]
            or terminal.get("call_number") != next_number
            or terminal.get("tool_id") != function["tool_id"]
            or terminal.get("tool_args_sha256") != arguments_sha):
        raise ToolConversationError("tool terminal identity or arguments differ")
    terminal_sha = _sha(terminal_raw)
    receipt: dict[str, Any] = {
        **reservation, "reservation_sha256": _sha(reservation_path.read_bytes()),
        "terminal_sha256": terminal_sha, "terminal_status": terminal["status"],
        "stdout_sha256": None, "stderr_sha256": None,
        "output": None, "output_sha256": None,
    }
    try:
        streams: dict[str, str] = {}
        for stream in ("stdout", "stderr"):
            reported = terminal.get(stream)
            if reported is None:
                streams[stream] = ""
            else:
                value, digest = _tool_stream(
                    Path(reported), session / "calls" / f"{next_number:06d}" / stream
                )
                streams[stream] = value
                receipt[f"{stream}_sha256"] = digest
        if terminal["status"] == "success":
            output = json.dumps({
                "run_id": plan["run_id"], "call_id": call["call_id"],
                "terminal_sha256": terminal_sha, "terminal": terminal,
                **streams,
            }, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            if len(output.encode("utf-8")) > MAX_JSON_BYTES:
                raise ToolConversationError("function output exceeds request byte limit")
            receipt["output"] = output
            receipt["output_sha256"] = _sha(output.encode("utf-8"))
    except ToolConversationError as exc:
        receipt["output_error"] = str(exc)
    _new_private_file(run_dir / "tool_receipts" / name, _canonical(receipt))
    state["tool_calls_completed"] = next_number
    _write_state(run_dir, state)
    return receipt


def _finish(run_dir: Path, state: dict[str, Any], outcome: str,
            reason: str | None, started_at: float) -> None:
    state["state"] = outcome
    state["reason"] = reason
    state["active_seconds"] = time.monotonic() - started_at
    _write_state(run_dir, state)


def execute_tool_conversation(
    run_dir: Path, transport: ResponseTransport,
) -> dict[str, Any]:
    """Execute the prepared two-turn run once; no retry after its start marker."""
    run_dir = Path(run_dir)
    with _run_lock(run_dir):
        plan, state, tool_status, ledger = _load(run_dir)
        if state["state"] != "prepared":
            raise ToolConversationError("run already started or ended; no retry")
        if (tool_status["status"] != "ready" or tool_status["reserved_tool_calls"] != 0
                or ledger.status()["request_count"] != 0
                or any(any((run_dir / name).iterdir()) for name in
                       ("requests", "responses", "receipts", "tool_reservations",
                        "tool_receipts"))):
            raise ToolConversationError("prepared run is no longer empty and ready")
        state["state"] = "started"
        _write_state(run_dir, state)
        started_at = time.monotonic()
        deadline = started_at + state["active_limit_seconds"]
        history: list[dict[str, Any]] = []
        try:
            with _deadline(state["active_limit_seconds"]):
                schedule, digest = _schedule_at(Path(state["schedule_path"]))
                if digest != state["schedule_bytes_sha256"]:
                    raise ToolConversationError("schedule changed before model admission")
                claim_args = {
                    "schedule_sha256": schedule["schedule_sha256"], "run_id": plan["run_id"],
                    "selected_owner": admission.owner("staged", Path(state["stage_dir"]),
                                                       Path(state["session_dir"])),
                    "root_descriptor": {key: tool_status[key] for key in (
                        "local_run_admission_root", "local_run_admission_root_identity",
                        "local_run_admission_scope",
                    )},
                    "attempt_number": tool_status["attempt_number"],
                }
                expected_claim = tool_status["local_run_claim_sha256"]
                if admission.acquire_staged_claim(**claim_args) != expected_claim:
                    raise ToolConversationError("local admission claim differs from prepared tool session")
                bounded = _ClaimedTransport(transport, deadline, claim_args, expected_claim)
                for turn, item in enumerate(plan["turns"], 1):
                    history.append({"role": "user", "content": item["user"]})
                    while True:
                        bounded.check()
                        next_index = state["model_requests_completed"] + 1
                        if next_index > plan["max_model_requests"]:
                            _finish(run_dir, state, "truncated", "model_request_cap", started_at)
                            return _snapshot(run_dir, plan, state, ledger)
                        request = _request(plan, history, turn)
                        name = f"{next_index:04d}.json"
                        request_sha = _sha(_json_bytes(request))
                        _new_private_file(run_dir / "requests" / name, _canonical({
                            "run_id": plan["run_id"], "request_index": next_index,
                            "turn": turn, "request_sha256": request_sha,
                            "request": request,
                        }))
                        try:
                            result = dispatch_response(
                                ledger, request_id=f"model-{next_index:04d}",
                                role="agent", request=request,
                                response_path=run_dir / "responses" / name,
                                transport=bounded,
                            )
                        except (CostBudgetExhausted, TokenBudgetExhausted) as exc:
                            _finish(run_dir, state, "truncated", type(exc).__name__, started_at)
                            return _snapshot(run_dir, plan, state, ledger)
                        response_raw = _file_bytes(run_dir / "responses" / name,
                                                   MAX_JSON_BYTES, "provider response")
                        response_sha = _sha(response_raw)
                        if response_sha != result["response_sha256"]:
                            raise ToolConversationError("provider response digest differs from dispatch")
                        response = _read_json(run_dir / "responses" / name)
                        _new_private_file(run_dir / "receipts" / name, _canonical({
                            "run_id": plan["run_id"], "request_index": next_index,
                            "turn": turn, "request_sha256": request_sha,
                            **result,
                        }))
                        state["model_requests_completed"] = next_index
                        _write_state(run_dir, state)
                        if result["provider_status"] != "completed":
                            _finish(run_dir, state, "truncated", "provider_incomplete", started_at)
                            return _snapshot(run_dir, plan, state, ledger)
                        kind, call = _response_kind(response, plan["functions"][0])
                        if kind == "unsupported":
                            _finish(run_dir, state, "truncated", "unsupported_response", started_at)
                            return _snapshot(run_dir, plan, state, ledger)
                        history.extend(response["output"])
                        if kind == "text":
                            state["turns_completed"] = turn
                            _write_state(run_dir, state)
                            break
                        assert call is not None
                        # Validate the *entire* replay before any local effect.
                        # This also catches duplicate call_id values and output
                        # fields the next Responses request would reject.
                        try:
                            _request(plan, [*history, {
                                "type": "function_call_output",
                                "call_id": call["call_id"], "output": "preflight",
                            }], turn)
                        except DispatchError:
                            _finish(run_dir, state, "truncated", "unsupported_response", started_at)
                            return _snapshot(run_dir, plan, state, ledger)
                        if state["tool_calls_completed"] >= plan["max_tool_calls"]:
                            _finish(run_dir, state, "truncated", "tool_call_cap", started_at)
                            return _snapshot(run_dir, plan, state, ledger)
                        schedule, digest = _schedule_at(Path(state["schedule_path"]))
                        if digest != state["schedule_bytes_sha256"]:
                            raise ToolConversationError("schedule changed before tool launch")
                        receipt = _invoke_tool(run_dir, plan, state, schedule, next_index,
                                               turn, call, response_sha, request_sha,
                                               deadline)
                        if receipt["terminal_status"] != "success" or receipt["output"] is None:
                            _finish(run_dir, state, "truncated",
                                    receipt.get("output_error") or "tool_failure", started_at)
                            return _snapshot(run_dir, plan, state, ledger)
                        history.append({"type": "function_call_output",
                                        "call_id": call["call_id"],
                                        "output": receipt["output"]})
                bounded.check()
                _finish(run_dir, state, "completed", None, started_at)
                return _snapshot(run_dir, plan, state, ledger)
        except Exception as exc:
            try:
                _finish(run_dir, state, "indeterminate", type(exc).__name__, started_at)
            except (OSError, ValueError):
                pass
            raise ToolConversationError("run outcome indeterminate; no automatic retry") from exc


def _snapshot(run_dir: Path, plan: dict[str, Any], state: dict[str, Any],
              ledger: TokenLedger) -> dict[str, Any]:
    budget = _check_cost(state, ledger, plan)
    model_names = {f"{number:04d}.json" for number in
                   range(1, state["model_requests_completed"] + 1)}
    tool_names = {f"{number:04d}.json" for number in
                  range(1, state["tool_calls_completed"] + 1)}
    pending_names: dict[str, list[str]] = {}
    for folder, expected, pending_name in (
        ("requests", model_names, f"{state['model_requests_completed'] + 1:04d}.json"),
        ("responses", model_names, f"{state['model_requests_completed'] + 1:04d}.json"),
        ("receipts", model_names, f"{state['model_requests_completed'] + 1:04d}.json"),
        ("tool_reservations", tool_names, f"{state['tool_calls_completed'] + 1:04d}.json"),
        ("tool_receipts", tool_names, f"{state['tool_calls_completed'] + 1:04d}.json"),
    ):
        present = {path.name for path in (run_dir / folder).iterdir()}
        extra = present - expected
        allowed = ({pending_name} if state["state"] in {"started", "indeterminate"}
                   or folder == "requests" and state["state"] == "truncated"
                   and state["reason"] in {"CostBudgetExhausted", "TokenBudgetExhausted"}
                   else set())
        if not expected <= present or not extra <= allowed:
            raise ToolConversationError(f"{folder} numbering differs from run state")
        pending_names[folder] = sorted(extra)
        for name in present:
            _private_file(run_dir / folder / name)
    response_by_index: dict[int, dict[str, Any]] = {}
    request_by_index: dict[int, dict[str, Any]] = {}
    for index in range(1, state["model_requests_completed"] + 1):
        name = f"{index:04d}.json"
        request = _read_json(run_dir / "requests" / name)
        response = _read_json(run_dir / "responses" / name)
        receipt = _read_json(run_dir / "receipts" / name)
        payload = request.get("request")
        request_sha = _sha(_json_bytes(payload))
        response_sha = _sha((run_dir / "responses" / name).read_bytes())
        record = budget["requests"].get(f"model-{index:04d}")
        if (request.get("run_id") != plan["run_id"]
                or receipt.get("run_id") != plan["run_id"]
                or request.get("request_index") != index
                or receipt.get("request_index") != index
                or request.get("turn") != receipt.get("turn")
                or request.get("request_sha256") != request_sha
                or receipt.get("request_sha256") != request_sha
                or receipt.get("response_sha256") != response_sha
                or record is None or record["state"] != "settled"
                or record["payload_sha256"] != request_sha
                or response.get("model") != plan["model"]
                or receipt.get("model_reported") != response.get("model")
                or receipt.get("provider_status") != response.get("status")
                or receipt.get("provider_response_id") != response.get("id")
                or receipt.get("usage") != response.get("usage")
                or receipt.get("budget") != record
                or receipt.get("cost_basis") != "declared_price_ceiling_not_invoice"):
            raise ToolConversationError("model request, response, receipt, or ledger differs")
        response_by_index[index] = response
        request_by_index[index] = payload
    for name in pending_names["requests"]:
        pending_request = _read_json(run_dir / "requests" / name)
        payload = pending_request.get("request")
        if (pending_request.get("run_id") != plan["run_id"]
                or pending_request.get("request_index")
                != state["model_requests_completed"] + 1
                or pending_request.get("request_sha256") != _sha(_json_bytes(payload))):
            raise ToolConversationError("pending model request differs from run")
    session = Path(state["session_dir"])
    tool_by_request: dict[int, dict[str, Any]] = {}
    for number in range(1, state["tool_calls_completed"] + 1):
        name = f"{number:04d}.json"
        reservation = _read_json(run_dir / "tool_reservations" / name)
        receipt = _read_json(run_dir / "tool_receipts" / name)
        terminal_path = session / "calls" / f"{number:06d}" / "terminal.json"
        terminal_raw = _file_bytes(terminal_path, MAX_JSON_BYTES, "tool terminal")
        terminal = json.loads(terminal_raw)
        index = reservation.get("request_index")
        response = response_by_index.get(index)
        calls = ([item for item in response["output"]
                  if type(item) is dict and item.get("type") == "function_call"]
                 if response is not None else [])
        if len(calls) != 1:
            raise ToolConversationError("tool reservation lacks one originating function call")
        call = calls[0]
        parsed = _parse_function_arguments(_provider_tool(plan["functions"][0]),
                                           call["arguments"])
        args_sha = _sha(_json_bytes(parsed))
        if (reservation.get("run_id") != plan["run_id"]
                or receipt.get("run_id") != plan["run_id"]
                or terminal.get("run_id") != plan["run_id"]
                or reservation.get("tool_call_number") != number
                or receipt.get("tool_call_number") != number
                or terminal.get("call_number") != number
                or reservation.get("call_id") != call.get("call_id")
                or receipt.get("call_id") != call.get("call_id")
                or reservation.get("arguments_sha256") != args_sha
                or terminal.get("tool_args_sha256") != args_sha
                or terminal.get("tool_id") != reservation.get("tool_id")
                or terminal.get("executable_sha256")
                != state["tool_binding"]["executable_sha256"]
                or receipt.get("terminal_sha256") != _sha(terminal_raw)
                or receipt.get("reservation_sha256")
                != _sha((run_dir / "tool_reservations" / name).read_bytes())
                or receipt.get("terminal_status") != terminal.get("status")
                or any(receipt.get(key) != value for key, value in reservation.items())):
            raise ToolConversationError("tool reservation, arguments, or terminal differs")
        streams: dict[str, str] = {}
        for stream in ("stdout", "stderr"):
            expected_sha = receipt.get(f"{stream}_sha256")
            if expected_sha is not None:
                expected = session / "calls" / f"{number:06d}" / stream
                value, digest = _tool_stream(Path(terminal[stream]), expected)
                if digest != expected_sha:
                    raise ToolConversationError("tool stream digest changed")
                streams[stream] = value
            elif terminal.get(stream) is None:
                streams[stream] = ""
            elif receipt.get("output") is not None:
                raise ToolConversationError("function output omits a tool stream digest")
        output = receipt.get("output")
        if output is not None and receipt.get("output_sha256") != _sha(output.encode("utf-8")):
            raise ToolConversationError("function output digest changed")
        if output is not None:
            expected_output = json.dumps({
                "run_id": plan["run_id"], "call_id": call["call_id"],
                "terminal_sha256": _sha(terminal_raw), "terminal": terminal,
                **streams,
            }, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            if output != expected_output:
                raise ToolConversationError("function output differs from sealed terminal and streams")
        if output is not None and index < state["model_requests_completed"]:
            next_request = _read_json(run_dir / "requests" / f"{index + 1:04d}.json")
            expected_item = {"type": "function_call_output", "call_id": call["call_id"],
                             "output": output}
            if expected_item not in next_request["request"]["input"]:
                raise ToolConversationError("next model request omits the bound tool output")
        tool_by_request[index] = receipt
    for name in pending_names["tool_reservations"]:
        pending = _read_json(run_dir / "tool_reservations" / name)
        index = pending.get("request_index")
        source = response_by_index.get(index)
        calls = ([item for item in source["output"]
                  if type(item) is dict and item.get("type") == "function_call"]
                 if source is not None else [])
        if len(calls) != 1:
            raise ToolConversationError("pending tool reservation lacks a model call")
        parsed = _parse_function_arguments(_provider_tool(plan["functions"][0]),
                                           calls[0]["arguments"])
        if (pending.get("run_id") != plan["run_id"]
                or pending.get("tool_call_number") != state["tool_calls_completed"] + 1
                or pending.get("call_id") != calls[0].get("call_id")
                or pending.get("arguments_sha256") != _sha(_json_bytes(parsed))
                or pending.get("request_sha256")
                != _sha(_json_bytes(request_by_index[index]))
                or pending.get("response_sha256")
                != _sha((run_dir / "responses" / f"{index:04d}.json").read_bytes())):
            raise ToolConversationError("pending tool reservation identity differs")
    history: list[dict[str, Any]] = []
    turn = 1
    need_user = True
    for index in range(1, state["model_requests_completed"] + 1):
        if need_user:
            if turn > 2:
                raise ToolConversationError("model request exceeds the two planned turns")
            history.append({"role": "user", "content": plan["turns"][turn - 1]["user"]})
        if request_by_index[index].get("input") != history:
            raise ToolConversationError("model request omits or changes prior complete output")
        expected = _request(plan, history, turn)
        if request_by_index[index] != expected:
            raise ToolConversationError("model request omits or changes prior complete output")
        response = response_by_index[index]
        if response["status"] != "completed":
            break
        kind, call = _response_kind(response, plan["functions"][0])
        if kind == "unsupported":
            break
        history.extend(response["output"])
        if kind == "text":
            turn += 1
            need_user = True
            continue
        receipt = tool_by_request.get(index)
        if receipt is None or receipt.get("output") is None:
            break
        assert call is not None
        history.append({"type": "function_call_output",
                        "call_id": call["call_id"], "output": receipt["output"]})
        need_user = False
    if state["state"] == "completed" and (turn != 3 or state["turns_completed"] != 2):
        raise ToolConversationError("completed run lacks two finished user turns")
    if state["state"] in {"prepared", "completed", "truncated"}:
        if state["turns_completed"] != min(turn - 1, 2):
            raise ToolConversationError("finished-turn count differs from response history")
    for name in pending_names["requests"]:
        pending_request = _read_json(run_dir / "requests" / name)
        pending_history = history.copy()
        if need_user:
            if turn > 2:
                raise ToolConversationError("pending model request exceeds planned turns")
            pending_history.append({"role": "user",
                                    "content": plan["turns"][turn - 1]["user"]})
        if pending_request["request"].get("input") != pending_history:
            raise ToolConversationError("pending request omits complete history")
        if pending_request["request"] != _request(plan, pending_history, turn):
            raise ToolConversationError("pending model request differs from complete history")
    pending = {name: entries for name, entries in pending_names.items() if entries}
    return {
        "classification": CLASSIFICATION,
        "state": "indeterminate" if state["state"] == "started" else state["state"],
        "stored_state": state["state"], "reason": state["reason"],
        "run_id": plan["run_id"], "model": plan["model"],
        "schedule_bytes_sha256": state["schedule_bytes_sha256"],
        "plan_sha256": state["plan_sha256"],
        "model_requests_completed": state["model_requests_completed"],
        "max_model_requests": plan["max_model_requests"],
        "tool_calls_completed": state["tool_calls_completed"],
        "max_tool_calls": plan["max_tool_calls"],
        "turns_completed": state["turns_completed"], "turns_total": 2,
        "active_seconds": state["active_seconds"],
        "active_limit_seconds": state["active_limit_seconds"],
        "budget": budget,
        "cost_basis": "declared_price_ceiling_not_invoice",
        "completed_artifacts_verified": state["state"] not in {"started", "indeterminate"},
        "pending_artifacts": pending,
        "global_run_limits_enforced": False,
        "criterion_4": "not_assessed",
    }


def read_tool_conversation_status(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    with _run_lock(run_dir):
        plan, state, tool_status, ledger = _load(run_dir)
        if state["state"] == "prepared" and (
            tool_status["status"] != "ready" or tool_status["reserved_tool_calls"] != 0
        ):
            raise ToolConversationError("prepared tool session is no longer empty and ready")
        if tool_status["reserved_tool_calls"] < state["tool_calls_completed"]:
            raise ToolConversationError("tool session lost a reserved call")
        return _snapshot(run_dir, plan, state, ledger)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="prepare private run and sealed session offline")
    prepare.add_argument("schedule", type=Path)
    prepare.add_argument("stage", type=Path)
    prepare.add_argument("plan_file", type=Path)
    prepare.add_argument("run_dir", type=Path)
    prepare.add_argument("--limit-tokens", type=int, required=True)
    prepare.add_argument("--active-limit-seconds", type=int, required=True)
    prepare.add_argument("--cost-limit-micro-usd", type=int, required=True)
    prepare.add_argument("--price-profile", type=Path, required=True)
    execute = sub.add_parser("execute", help="execute one prepared run")
    execute.add_argument("run_dir", type=Path)
    execute.add_argument("--allow-paid-requests", action="store_true")
    status = sub.add_parser("status", help="inspect without sending or launching")
    status.add_argument("run_dir", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            plan = _read_json_file(args.plan_file)
            profile = _read_json_file(args.price_profile)
            result = prepare_tool_conversation(
                args.run_dir, args.schedule, args.stage, plan,
                limit_tokens=args.limit_tokens,
                active_limit_seconds=args.active_limit_seconds,
                cost_limit_micro_usd=args.cost_limit_micro_usd,
                price_profile=profile,
            )
        elif args.command == "status":
            result = read_tool_conversation_status(args.run_dir)
        else:
            if not args.allow_paid_requests:
                raise ToolConversationError("execute requires --allow-paid-requests")
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ToolConversationError("OPENAI_API_KEY is unavailable")
            prepared = read_tool_conversation_status(args.run_dir)
            if prepared["budget"]["cost_limit_micro_usd"] is None:
                raise ToolConversationError("execute requires a prepared cost ceiling")
            result = execute_tool_conversation(args.run_dir, OpenAIResponsesHTTP(api_key))
    except (OSError, ValueError, BudgetError, DispatchError, SessionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
