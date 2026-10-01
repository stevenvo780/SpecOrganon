"""Development-only serial role handoffs over one claimed, budgeted staged run.

The schema-2 runner keeps one schedule attempt, token ledger, sealed tool
session, and checkpoint context across processes. It never opens a reserved
case, authenticates a provider invoice, or turns its local receipts into C4.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

import local_run_admission as admission
from managed_run_context import RunContext
from managed_token_ledger import BudgetError, CostBudgetExhausted, TokenBudgetExhausted, TokenLedger
from run_managed_conversation import (
    _canonical, _deadline, _new_private_file, _private_dir, _read_json, _run_lock,
    _write_state,
)
from run_managed_response import (
    MAX_JSON_BYTES, DispatchError, OpenAIResponsesHTTP, ResponseTransport,
    _json_bytes, _parse_function_arguments, dispatch_response,
)
from run_managed_tool_conversation import (
    ToolConversationError, _file_bytes, _invoke_tool, _request, _response_kind,
    _schedule_at, _tool_binding, _tool_stream, _validate_plan as _validate_bridge_plan,
)
from staged_tool_session import create_session, resume_session


CLASSIFICATION = "development_managed_team_unsealed"
ROLES = ("leader", "specialist", "reviewer")
MAX_SEGMENTS = 32
SOURCE_ROOT = Path(__file__).resolve().parent
STATE_KEYS = {
    "schema", "classification", "plan_sha256", "schedule_path",
    "schedule_bytes_sha256", "run_id", "model", "stage_dir", "session_dir",
    "session_manifest_sha256", "tool_binding", "limit_tokens",
    "active_limit_seconds", "cost_limit_micro_usd", "price_profile_sha256",
    "max_model_requests", "max_tool_calls", "model_requests_completed",
    "tool_calls_completed", "segments_completed", "claim_sha256", "source_sha256",
    "terminal_reason",
}


class TeamError(ValueError):
    """The prepared local team run cannot safely proceed."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _absolute(path: Path, label: str) -> Path:
    if not path.is_absolute() or any(part in (".", "..") for part in path.parts):
        raise TeamError(f"{label} must be absolute without dot components")
    return path


def _source_closure() -> dict[str, str]:
    """Pin the local Python import closure, including the runner itself."""
    pending = ["run_managed_team", "managed_run_context"]
    seen: set[str] = set()
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        path = SOURCE_ROOT / f"{module}.py"
        if not path.is_file():
            raise TeamError(f"local source is missing: {module}")
        seen.add(module)
        tree = ast.parse(path.read_bytes(), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".", 1)[0]]
            pending.extend(name for name in names if (SOURCE_ROOT / f"{name}.py").is_file())
    return {f"scripts/{name}.py": _sha((SOURCE_ROOT / f"{name}.py").read_bytes())
            for name in sorted(seen)}


def _validate_plan(raw: Any, schedule: dict[str, Any]) -> dict[str, Any]:
    required = {"schema", "run_id", "model", "service_tier", "segments", "functions",
                "max_model_requests", "max_tool_calls", "tool_wall_seconds"}
    optional = {"instructions", "reasoning"}
    if (type(raw) is not dict or set(raw) - required - optional or not required <= set(raw)
            or type(raw["schema"]) is not int or raw["schema"] != 2):
        raise TeamError("team plan schema or fields are invalid")
    segments = raw["segments"]
    if type(segments) is not list or not 2 <= len(segments) <= MAX_SEGMENTS:
        raise TeamError("team plan requires 2 to 32 segments")
    if (schedule.get("schema") == "specorganon.development_round_schedule.v1"
            and any(type(segment) is dict and segment.get("role") != "leader"
                    for segment in segments)):
        raise TeamError("development round schedule declares a solo leader")
    for number, segment in enumerate(segments, 1):
        if (type(segment) is not dict
                or set(segment) != {"role", "user", "max_output_tokens", "share_from"}
                or segment["role"] not in ROLES or type(segment["user"]) is not str
                or not segment["user"] or type(segment["max_output_tokens"]) is not int
                or not 1 <= segment["max_output_tokens"] <= schedule["per_run_limits"]["measured_tokens"]
                or type(segment["share_from"]) is not list
                or any(type(index) is not int or index < 1 or index >= number
                       for index in segment["share_from"])
                or segment["share_from"] != sorted(set(segment["share_from"]))):
            raise TeamError(f"segment {number} is invalid or references a future artifact")
    if (type(raw["max_model_requests"]) is not int
            or raw["max_model_requests"] < len(segments)):
        raise TeamError("model request cap is lower than the number of segments")
    projected = {key: raw[key] for key in required - {"schema", "segments"}}
    projected["schema"] = 1
    projected.update({key: raw[key] for key in optional if key in raw})
    for number, segment in enumerate(segments, 1):
        # The schema-1 bridge checks only its first projected request. Project
        # every schema-2 segment before any directory or claim is created.
        projected["turns"] = [
            {"user": segment["user"], "max_output_tokens": segment["max_output_tokens"]}
        ] * 2
        _validate_bridge_plan(projected, schedule)
        placeholders = {index: {"role": segments[index - 1]["role"],
                                "artifact_sha256": "0" * 64, "text": ""}
                        for index in range(1, number)}
        _request(_request_plan(raw, segment),
                 [{"role": "user", "content": _prompt(segment, placeholders)}], 1)
    if len(_canonical(raw)) > MAX_JSON_BYTES:
        raise TeamError("team plan exceeds the byte limit")
    return json.loads(_json_bytes(raw))


def _request_plan(plan: dict[str, Any], segment: dict[str, Any]) -> dict[str, Any]:
    selected = {key: plan[key] for key in ("model", "service_tier", "functions")}
    selected["turns"] = [{"user": segment["user"],
                          "max_output_tokens": segment["max_output_tokens"]}]
    selected.update({key: plan[key] for key in ("instructions", "reasoning") if key in plan})
    return selected


def _prompt(segment: dict[str, Any], artifacts: dict[int, dict[str, Any]]) -> str:
    shared = [{"segment": index, "role": artifacts[index]["role"],
               "artifact_sha256": artifacts[index]["artifact_sha256"],
               "text": artifacts[index]["text"]}
              for index in segment["share_from"]]
    return json.dumps({"role": segment["role"], "task": segment["user"],
                       "shared_text_artifacts": shared},
                      ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _text_artifact(segment_index: int, role: str, request_index: int,
                   response: dict[str, Any], response_sha: str) -> dict[str, Any]:
    text = "\n".join(
        part["text"] for item in response["output"] if item.get("type") == "message"
        for part in item["content"] if part["text"]
    )
    if not text:
        raise TeamError("text segment has no shareable artifact")
    value = {"schema": 2, "segment_index": segment_index, "role": role,
             "request_index": request_index, "response_sha256": response_sha,
             "text": text}
    value["artifact_sha256"] = _sha(_canonical(value))
    return value


def _claim_args(schedule: dict[str, Any], state: dict[str, Any],
                session_status: dict[str, Any]) -> dict[str, Any]:
    return {
        "schedule_sha256": schedule["schedule_sha256"], "run_id": state["run_id"],
        "selected_owner": admission.owner("staged", state["stage_dir"], state["session_dir"]),
        "root_descriptor": {key: session_status[key] for key in (
            "local_run_admission_root", "local_run_admission_root_identity",
            "local_run_admission_scope")},
        "attempt_number": session_status["attempt_number"],
    }


def _require_claim(schedule: dict[str, Any], state: dict[str, Any],
                   session_status: dict[str, Any]) -> None:
    if admission.require_claim(**_claim_args(schedule, state, session_status)) != state["claim_sha256"]:
        raise TeamError("local admission claim differs from prepared team run")


def _journal_roots(run_dir: Path, stage: Path, schedule_path: Path) -> list[Path]:
    roots = [run_dir / name for name in (
        "requests", "responses", "receipts", "tool_reservations", "tool_receipts",
        "histories", "artifacts", "ledger", "tool_session")]
    roots.extend((stage / "work", stage / "case", stage / "inputs",
                  run_dir / "plan.json", run_dir / "run.json", schedule_path))
    return roots


def prepare_team(
    run_dir: Path, schedule_path: Path, stage_dir: Path, plan: dict[str, Any], *,
    limit_tokens: int, active_limit_seconds: int,
    cost_limit_micro_usd: int, price_profile: dict[str, Any],
) -> dict[str, Any]:
    """Prepare one local attempt; its first active segment claims before count."""
    run_dir = _absolute(Path(run_dir), "run directory")
    schedule_path = _absolute(Path(schedule_path), "schedule path")
    stage = _absolute(Path(stage_dir), "stage directory")
    schedule, schedule_bytes_sha = _schedule_at(schedule_path)
    validated = _validate_plan(plan, schedule)
    if (type(limit_tokens) is not int or not 1 <= limit_tokens <= 80_000
            or limit_tokens > schedule["per_run_limits"]["measured_tokens"]
            or any(item["max_output_tokens"] > limit_tokens
                   for item in validated["segments"])
            or type(active_limit_seconds) is not int or not 1 <= active_limit_seconds <= 5_400
            or active_limit_seconds > schedule["per_run_limits"]["active_seconds"]
            or type(cost_limit_micro_usd) is not int or cost_limit_micro_usd < 0
            or type(price_profile) is not dict or price_profile.get("model") != validated["model"]):
        raise TeamError("team token, active time, or cost ceiling is invalid")
    if schedule.get("schema") == "specorganon.development_round_schedule.v1":
        from plan_development_round import validate_runtime_budget
        validate_runtime_budget(
            schedule, max_model_requests=validated["max_model_requests"],
            cost_limit_micro_usd=cost_limit_micro_usd, price_profile=price_profile)
    binding = _tool_binding(stage, schedule, validated["functions"][0])
    sources = _source_closure()
    if run_dir.exists():
        raise FileExistsError("team run directory already exists")
    run_dir.mkdir(mode=0o700)
    for name in ("requests", "responses", "receipts", "tool_reservations",
                 "tool_receipts", "histories", "artifacts"):
        (run_dir / name).mkdir(mode=0o700)
    ledger = TokenLedger.create(
        run_dir / "ledger", limit_tokens, validated["max_model_requests"],
        cost_limit_micro_usd=cost_limit_micro_usd, price_profile=price_profile,
    )
    session = run_dir / "tool_session"
    session_status = create_session(schedule, validated["run_id"], stage, session)
    if session_status["status"] != "ready" or session_status["reserved_tool_calls"] != 0:
        raise TeamError("new staged tool session is not empty and ready")
    expected_claim = session_status["local_run_claim_sha256"]
    raw_plan = _canonical(validated)
    _new_private_file(run_dir / "plan.json", raw_plan)
    _new_private_file(run_dir / ".lock", b"")
    state = {
        "schema": 2, "classification": CLASSIFICATION,
        "plan_sha256": _sha(raw_plan), "schedule_path": str(schedule_path),
        "schedule_bytes_sha256": schedule_bytes_sha,
        "run_id": validated["run_id"], "model": validated["model"],
        "stage_dir": str(stage), "session_dir": str(session),
        "session_manifest_sha256": _sha((session / "session.json").read_bytes()),
        "tool_binding": binding, "limit_tokens": limit_tokens,
        "active_limit_seconds": active_limit_seconds,
        "cost_limit_micro_usd": cost_limit_micro_usd,
        "price_profile_sha256": ledger.status()["price_profile_sha256"],
        "max_model_requests": validated["max_model_requests"],
        "max_tool_calls": validated["max_tool_calls"],
        "model_requests_completed": 0, "tool_calls_completed": 0,
        "segments_completed": 0, "claim_sha256": expected_claim,
        "source_sha256": sources, "terminal_reason": None,
    }
    _new_private_file(run_dir / "run.json", _canonical(state))
    bindings = {"schedule_sha256": schedule["schedule_sha256"],
                "schedule_bytes_sha256": schedule_bytes_sha, "run_id": validated["run_id"],
                "attempt_number": session_status["attempt_number"],
                "stage_dir": str(stage), "session_dir": str(session),
                "session_manifest_sha256": state["session_manifest_sha256"],
                "claim_sha256": expected_claim, "plan_sha256": state["plan_sha256"],
                "model": validated["model"], "price_profile_sha256": state["price_profile_sha256"],
                "source_digests": sources}
    RunContext.create(run_dir / "context", run_dir / "ledger", bindings,
                      active_limit_seconds=active_limit_seconds,
                      max_tool_calls=validated["max_tool_calls"],
                      roles=sorted({item["role"] for item in validated["segments"]}),
                      journal_roots=_journal_roots(run_dir, stage, schedule_path))
    return read_team_status(run_dir)


def _load(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any],
                                  dict[str, Any], TokenLedger, RunContext, dict[str, Any]]:
    _private_dir(run_dir)
    for name in ("requests", "responses", "receipts", "tool_reservations",
                 "tool_receipts", "histories", "artifacts", "ledger", "tool_session",
                 "context"):
        _private_dir(run_dir / name)
    state = _read_json(run_dir / "run.json")
    if (set(state) != STATE_KEYS or type(state["schema"]) is not int or state["schema"] != 2
            or state["classification"] != CLASSIFICATION
            or any(type(state[key]) is not int for key in (
                "limit_tokens", "active_limit_seconds", "cost_limit_micro_usd",
                "max_model_requests", "max_tool_calls", "model_requests_completed",
                "tool_calls_completed", "segments_completed"))
            or min(state["model_requests_completed"], state["tool_calls_completed"],
                   state["segments_completed"]) < 0
            or type(state["source_sha256"]) is not dict
            or state["source_sha256"] != _source_closure()):
        raise TeamError("team state or frozen source closure differs")
    schedule_path = _absolute(Path(state["schedule_path"]), "schedule path")
    schedule, schedule_bytes_sha = _schedule_at(schedule_path)
    if schedule_bytes_sha != state["schedule_bytes_sha256"]:
        raise TeamError("schedule bytes changed after team preparation")
    plan_raw = _file_bytes(run_dir / "plan.json", MAX_JSON_BYTES, "team plan")
    if _sha(plan_raw) != state["plan_sha256"]:
        raise TeamError("team plan bytes changed")
    plan = _validate_plan(_read_json(run_dir / "plan.json"), schedule)
    if (state["run_id"] != plan["run_id"] or state["model"] != plan["model"]
            or state["max_model_requests"] != plan["max_model_requests"]
            or state["max_tool_calls"] != plan["max_tool_calls"]
            or state["segments_completed"] > len(plan["segments"])
            or state["active_limit_seconds"] > schedule["per_run_limits"]["active_seconds"]
            or state["limit_tokens"] > schedule["per_run_limits"]["measured_tokens"]):
        raise TeamError("team state differs from plan or schedule")
    stage = _absolute(Path(state["stage_dir"]), "stage directory")
    session = _absolute(Path(state["session_dir"]), "session directory")
    if session != run_dir / "tool_session":
        raise TeamError("tool session is not in the team run directory")
    binding = _tool_binding(stage, schedule, plan["functions"][0])
    if binding != state["tool_binding"]:
        raise TeamError("sealed function binding changed")
    manifest = _file_bytes(session / "session.json", MAX_JSON_BYTES, "tool session manifest")
    if _sha(manifest) != state["session_manifest_sha256"]:
        raise TeamError("tool session manifest changed")
    session_status = resume_session(schedule, plan["run_id"], stage, session)
    if session_status["local_run_claim_status"] != "unclaimed":
        _require_claim(schedule, state, session_status)
    ledger = TokenLedger(run_dir / "ledger")
    budget = ledger.status()
    if (budget["limit_tokens"] != state["limit_tokens"]
            or budget["max_requests"] != plan["max_model_requests"]
            or budget["cost_limit_micro_usd"] != state["cost_limit_micro_usd"]
            or budget["price_profile_sha256"] != state["price_profile_sha256"]
            or budget["price_profile"]["model"] != plan["model"]):
        raise TeamError("team ledger, model, or cost binding changed")
    context = RunContext(run_dir / "context")
    context_status = context.status()
    if (context_status["state"] in {"paused", "completed"}
            and session_status["local_run_claim_status"] != "claimed"):
        raise TeamError("started team run lacks its durable local claim")
    if (context_status["cursor"] != state["segments_completed"]
            and context_status["state"] in {"prepared", "paused", "completed"}):
        raise TeamError("team cursor differs from durable checkpoint")
    return plan, state, schedule, session_status, ledger, context, context_status


def _numbered(root: Path, count: int) -> None:
    expected = {f"{number:04d}.json" for number in range(1, count + 1)}
    if {path.name for path in root.iterdir()} != expected:
        raise TeamError(f"numbered journal differs: {root.name}")


def _verify_tool_receipt(
    run_dir: Path, state: dict[str, Any], plan: dict[str, Any], number: int,
    request_index: int, call: dict[str, Any], request_sha: str, response_sha: str,
) -> str:
    name = f"{number:04d}.json"
    reservation = _read_json(run_dir / "tool_reservations" / name)
    receipt = _read_json(run_dir / "tool_receipts" / name)
    terminal_path = Path(state["session_dir"]) / "calls" / f"{number:06d}" / "terminal.json"
    terminal_raw = _file_bytes(terminal_path, MAX_JSON_BYTES, "tool terminal")
    terminal = json.loads(terminal_raw)
    parsed = _parse_function_arguments(
        {key: plan["functions"][0][key] for key in
         ("type", "name", "description", "parameters", "strict")}, call["arguments"])
    args_sha = _sha(_json_bytes(parsed))
    if (reservation.get("run_id") != plan["run_id"]
            or reservation.get("tool_call_number") != number
            or reservation.get("request_index") != request_index
            or reservation.get("call_id") != call["call_id"]
            or reservation.get("arguments_sha256") != args_sha
            or reservation.get("request_sha256") != request_sha
            or reservation.get("response_sha256") != response_sha
            or any(receipt.get(key) != value for key, value in reservation.items())
            or receipt.get("reservation_sha256") != _sha((run_dir / "tool_reservations" / name).read_bytes())
            or receipt.get("terminal_sha256") != _sha(terminal_raw)
            or receipt.get("terminal_status") != terminal.get("status")
            or terminal.get("run_id") != plan["run_id"]
            or terminal.get("call_number") != number
            or terminal.get("tool_args_sha256") != args_sha
            or terminal.get("executable_sha256") != state["tool_binding"]["executable_sha256"]):
        raise TeamError("tool reservation, provider call, and sealed terminal differ")
    streams: dict[str, str] = {}
    for stream in ("stdout", "stderr"):
        reported = terminal.get(stream)
        if reported is None:
            streams[stream] = ""
            if receipt.get(f"{stream}_sha256") is not None:
                raise TeamError("tool stream receipt is inconsistent")
        else:
            expected = Path(state["session_dir"]) / "calls" / f"{number:06d}" / stream
            value, digest = _tool_stream(Path(reported), expected)
            if receipt.get(f"{stream}_sha256") != digest:
                raise TeamError("tool stream digest differs")
            streams[stream] = value
    output = json.dumps({"run_id": plan["run_id"], "call_id": call["call_id"],
                         "terminal_sha256": _sha(terminal_raw), "terminal": terminal,
                         **streams}, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    if (terminal.get("status") != "success" or receipt.get("output") != output
            or receipt.get("output_sha256") != _sha(output.encode("utf-8"))):
        raise TeamError("tool output is not a complete sealed success")
    return output


def _audit_completed(
    run_dir: Path, plan: dict[str, Any], state: dict[str, Any],
    session_status: dict[str, Any], ledger: TokenLedger, context_status: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], dict[int, dict[str, Any]]]:
    if context_status["state"] not in {"prepared", "paused", "completed"}:
        raise TeamError("active or uncertain run cannot be resumed or certified")
    budget = ledger.status()
    if (budget["blocked"] or budget["request_count"] != state["model_requests_completed"]
            or session_status["reserved_tool_calls"] != state["tool_calls_completed"]
            or session_status["completed_tool_calls"] != state["tool_calls_completed"]
            or state["segments_completed"] != context_status["cursor"]):
        raise TeamError("team journal or budget has an unresolved operation")
    for folder, count in (("requests", state["model_requests_completed"]),
                          ("responses", state["model_requests_completed"]),
                          ("receipts", state["model_requests_completed"]),
                          ("tool_reservations", state["tool_calls_completed"]),
                          ("tool_receipts", state["tool_calls_completed"]),
                          ("histories", state["segments_completed"]),
                          ("artifacts", state["segments_completed"])):
        _numbered(run_dir / folder, count)
    role_histories: dict[str, list[dict[str, Any]]] = {}
    artifacts: dict[int, dict[str, Any]] = {}
    request_index = tool_number = 0
    for segment_index in range(1, state["segments_completed"] + 1):
        segment = plan["segments"][segment_index - 1]
        role = segment["role"]
        history = list(role_histories.get(role, []))
        history.append({"role": "user", "content": _prompt(segment, artifacts)})
        request_plan = _request_plan(plan, segment)
        while True:
            request_index += 1
            if request_index > state["model_requests_completed"]:
                raise TeamError("segment lacks a complete model response")
            name = f"{request_index:04d}.json"
            request_record = _read_json(run_dir / "requests" / name)
            response_raw = _file_bytes(run_dir / "responses" / name, MAX_JSON_BYTES,
                                       "provider response")
            response = _read_json(run_dir / "responses" / name)
            receipt = _read_json(run_dir / "receipts" / name)
            expected = _request(request_plan, history, 1)
            request_sha = _sha(_json_bytes(expected))
            response_sha = _sha(response_raw)
            budget_record = budget["requests"].get(f"model-{request_index:04d}")
            if (request_record.get("run_id") != plan["run_id"]
                    or request_record.get("segment_index") != segment_index
                    or request_record.get("role") != role
                    or request_record.get("request_index") != request_index
                    or request_record.get("request") != expected
                    or request_record.get("request_sha256") != request_sha
                    or receipt.get("run_id") != plan["run_id"]
                    or receipt.get("segment_index") != segment_index
                    or receipt.get("role") != role
                    or receipt.get("request_index") != request_index
                    or receipt.get("request_sha256") != request_sha
                    or receipt.get("response_sha256") != response_sha
                    or receipt.get("provider_status") != response.get("status")
                    or receipt.get("provider_response_id") != response.get("id")
                    or receipt.get("model_reported") != response.get("model")
                    or receipt.get("usage") != response.get("usage")
                    or response.get("model") != plan["model"]
                    or budget_record is None or budget_record["state"] != "settled"
                    or budget_record["role"] != role
                    or budget_record["payload_sha256"] != request_sha
                    or receipt.get("budget") != budget_record
                    or receipt.get("cost_basis") != "declared_price_ceiling_not_invoice"):
                raise TeamError("model request, response, receipt, or ledger differs")
            if response["status"] != "completed":
                raise TeamError("completed segment has an incomplete provider response")
            kind, call = _response_kind(response, plan["functions"][0])
            if kind == "unsupported":
                raise TeamError("completed segment has unsupported provider output")
            history.extend(response["output"])
            if kind == "text":
                artifact = _text_artifact(segment_index, role, request_index,
                                          response, response_sha)
                if _read_json(run_dir / "artifacts" / f"{segment_index:04d}.json") != artifact:
                    raise TeamError("shared text artifact differs from source response")
                artifacts[segment_index] = artifact
                break
            assert call is not None
            tool_number += 1
            if tool_number > state["tool_calls_completed"]:
                raise TeamError("function call lacks a sealed local tool terminal")
            output = _verify_tool_receipt(run_dir, state, plan, tool_number,
                                          request_index, call, request_sha, response_sha)
            history.append({"type": "function_call_output", "call_id": call["call_id"],
                            "output": output})
        stored_history = {"schema": 2, "segment_index": segment_index, "role": role,
                          "items": history, "items_sha256": _sha(_canonical(history))}
        if _read_json(run_dir / "histories" / f"{segment_index:04d}.json") != stored_history:
            raise TeamError("role history omits or changes complete prior output")
        role_histories[role] = history
    if (request_index != state["model_requests_completed"]
            or tool_number != state["tool_calls_completed"]):
        raise TeamError("extra model or tool operation is outside completed segments")
    return role_histories, artifacts


def _guard_operation(
    context: RunContext, run_dir: Path, plan: dict[str, Any], state: dict[str, Any],
    schedule: dict[str, Any], session_status: dict[str, Any], ledger: TokenLedger,
) -> None:
    """Check the active lease and frozen bindings around every provider effect."""
    context.require_active()
    if _source_closure() != state["source_sha256"]:
        raise TeamError("frozen runner or helper source changed during segment")
    checked_schedule, digest = _schedule_at(Path(state["schedule_path"]))
    if (digest != state["schedule_bytes_sha256"]
            or checked_schedule["schedule_sha256"] != schedule["schedule_sha256"]
            or _sha(_file_bytes(run_dir / "plan.json", MAX_JSON_BYTES, "team plan"))
            != state["plan_sha256"]):
        raise TeamError("frozen schedule or plan changed during segment")
    if (_tool_binding(Path(state["stage_dir"]), schedule, plan["functions"][0])
            != state["tool_binding"]
            or _sha(_file_bytes(Path(state["session_dir"]) / "session.json",
                               MAX_JSON_BYTES, "tool session manifest"))
            != state["session_manifest_sha256"]):
        raise TeamError("sealed tool binding changed during segment")
    _require_claim(schedule, state, session_status)
    budget = ledger.status()
    if (budget["limit_tokens"] != state["limit_tokens"]
            or budget["max_requests"] != state["max_model_requests"]
            or budget["cost_limit_micro_usd"] != state["cost_limit_micro_usd"]
            or budget["price_profile_sha256"] != state["price_profile_sha256"]
            or budget["price_profile"]["model"] != plan["model"]):
        raise TeamError("ledger price or cap changed during segment")
    context.require_active()


class _TeamTransport:
    """Keep an old role's transport from acting after pause or handoff."""

    def __init__(self, transport: ResponseTransport, guard: Any) -> None:
        self.transport = transport
        self.guard = guard

    def count_input(self, payload: dict[str, Any]) -> int:
        self.guard()
        result = self.transport.count_input(payload)
        self.guard()
        return result

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.guard()
        result = self.transport.send(payload)
        self.guard()
        return result


def _status_unlocked(
    run_dir: Path, plan: dict[str, Any], state: dict[str, Any],
    session_status: dict[str, Any], ledger: TokenLedger, context_status: dict[str, Any],
) -> dict[str, Any]:
    verified = context_status["state"] in {"prepared", "paused", "completed"}
    if verified:
        _audit_completed(run_dir, plan, state, session_status, ledger, context_status)
    exposed = context_status["state"]
    if exposed == "indeterminate" and state["terminal_reason"] and state["terminal_reason"].startswith("truncated:"):
        exposed = "truncated"
    return {
        "classification": CLASSIFICATION, "state": exposed,
        "context_state": context_status["state"],
        "checkpoint_sha256": context_status["checkpoint_sha256"],
        "cursor": context_status["cursor"], "revision": context_status["revision"],
        "role_next": (plan["segments"][context_status["cursor"]]["role"]
                      if context_status["cursor"] < len(plan["segments"]) else None),
        "segments_total": len(plan["segments"]),
        "model_requests_completed": state["model_requests_completed"],
        "tool_calls_completed": state["tool_calls_completed"],
        "active_seconds": context_status["active_seconds"],
        "paused_seconds": context_status["paused_seconds"],
        "remaining_active_seconds": context_status["remaining_active_seconds"],
        "terminal_reason": state["terminal_reason"],
        "budget": ledger.status(),
        "claim_sha256": state["claim_sha256"],
        "completed_artifacts_verified": verified,
        "global_study_limits_enforced": False,
        "provider_receipts_authenticated": False,
        "criterion_4": "not_assessed",
    }


def read_team_status(run_dir: Path) -> dict[str, Any]:
    """Read and replay all committed segments before calling them complete."""
    run_dir = Path(run_dir)
    with _run_lock(run_dir):
        plan, state, _schedule, session_status, ledger, _context, context_status = _load(run_dir)
        return _status_unlocked(run_dir, plan, state, session_status, ledger, context_status)


def execute_team_segment(
    run_dir: Path, transport: ResponseTransport, expected_checkpoint: str,
) -> dict[str, Any]:
    """Execute exactly one planned segment, then pause or finish durably."""
    run_dir = Path(run_dir)
    with _run_lock(run_dir):
        plan, state, schedule, session_status, ledger, context, context_status = _load(run_dir)
        if context_status["state"] not in {"prepared", "paused"}:
            raise TeamError("team run is active or terminal; no segment may start")
        role_histories, artifacts = _audit_completed(
            run_dir, plan, state, session_status, ledger, context_status)
        segment_index = context_status["cursor"] + 1
        if segment_index > len(plan["segments"]):
            raise TeamError("team has no remaining segment")
        segment = plan["segments"][segment_index - 1]
        context.begin(expected_checkpoint, segment["role"])
        def guard() -> None:
            _guard_operation(context, run_dir, plan, state, schedule,
                             session_status, ledger)
        bounded = _TeamTransport(transport, guard)
        history = list(role_histories.get(segment["role"], []))
        history.append({"role": "user", "content": _prompt(segment, artifacts)})
        request_plan = _request_plan(plan, segment)
        deadline_scope = None
        deadline_entered = False
        checkpoint_closed = False
        try:
            if admission.acquire_staged_claim(**_claim_args(schedule, state, session_status)) != state["claim_sha256"]:
                raise TeamError("first segment did not acquire its expected durable claim")
            remaining = context.deadline - time.monotonic()
            if remaining <= 0:
                raise TeamError("shared active deadline expired before provider operation")
            deadline_scope = _deadline(max(1, math.ceil(remaining)))
            deadline_scope.__enter__()
            deadline_entered = True
            while True:
                guard()
                budget = ledger.status()
                next_index = state["model_requests_completed"] + 1
                if budget["blocked"]:
                    raise TeamError("unresolved provider request blocks the team")
                if (budget["request_count"] >= plan["max_model_requests"]
                        or next_index > plan["max_model_requests"]):
                    raise TokenBudgetExhausted("model_request_cap")
                request = _request(request_plan, history, 1)
                name = f"{next_index:04d}.json"
                request_sha = _sha(_json_bytes(request))
                _new_private_file(run_dir / "requests" / name, _canonical({
                    "schema": 2, "run_id": plan["run_id"],
                    "segment_index": segment_index, "role": segment["role"],
                    "request_index": next_index, "request_sha256": request_sha,
                    "request": request,
                }))
                # count_input and send each check the live context and exact
                # claim both before and after transport I/O. The ledger reserves
                # before send and retains an uncertain reservation.
                result = dispatch_response(
                    ledger, request_id=f"model-{next_index:04d}", role=segment["role"],
                    request=request, response_path=run_dir / "responses" / name,
                    transport=bounded,
                )
                guard()
                response_raw = _file_bytes(run_dir / "responses" / name,
                                           MAX_JSON_BYTES, "provider response")
                response_sha = _sha(response_raw)
                if response_sha != result["response_sha256"]:
                    raise TeamError("provider response digest differs from dispatch")
                response = _read_json(run_dir / "responses" / name)
                _new_private_file(run_dir / "receipts" / name, _canonical({
                    "schema": 2, "run_id": plan["run_id"],
                    "segment_index": segment_index, "role": segment["role"],
                    "request_index": next_index, "request_sha256": request_sha,
                    **result,
                }))
                state["model_requests_completed"] = next_index
                _write_state(run_dir, state)
                if result["provider_status"] != "completed":
                    raise TeamError("provider returned an incomplete response")
                kind, call = _response_kind(response, plan["functions"][0])
                if kind == "unsupported":
                    raise TeamError("provider returned unsupported team output")
                history.extend(response["output"])
                if kind == "text":
                    artifact = _text_artifact(segment_index, segment["role"], next_index,
                                              response, response_sha)
                    _new_private_file(run_dir / "artifacts" / f"{segment_index:04d}.json",
                                      _canonical(artifact))
                    _new_private_file(run_dir / "histories" / f"{segment_index:04d}.json",
                                      _canonical({
                                          "schema": 2, "segment_index": segment_index,
                                          "role": segment["role"], "items": history,
                                          "items_sha256": _sha(_canonical(history)),
                                      }))
                    state["segments_completed"] = segment_index
                    _write_state(run_dir, state)
                    guard()
                    if segment_index == len(plan["segments"]):
                        context.finish(segment_index)
                    else:
                        context.pause(segment_index)
                    checkpoint_closed = True
                    assert deadline_scope is not None
                    deadline_scope.__exit__(None, None, None)
                    deadline_entered = False
                    return read_team_status_unlocked(run_dir, plan, state, schedule,
                                                     ledger, context)
                assert call is not None
                # Check the entire follow-up request before any local tool effect.
                _request(request_plan, [*history, {
                    "type": "function_call_output", "call_id": call["call_id"],
                    "output": "preflight",
                }], 1)
                if state["tool_calls_completed"] >= plan["max_tool_calls"]:
                    raise TokenBudgetExhausted("tool_call_cap")
                guard()
                receipt = _invoke_tool(run_dir, plan, state, schedule, next_index,
                                       segment_index, call, response_sha, request_sha,
                                       context.deadline, guard=guard)
                guard()
                if receipt["terminal_status"] != "success" or receipt["output"] is None:
                    raise TeamError(receipt.get("output_error") or "sealed_tool_failure")
                history.append({"type": "function_call_output", "call_id": call["call_id"],
                                "output": receipt["output"]})
        except Exception as exc:
            if checkpoint_closed:
                raise TeamError("completed checkpoint failed post-write verification") from exc
            reason = (f"truncated:{type(exc).__name__}" if isinstance(
                exc, (TokenBudgetExhausted, CostBudgetExhausted))
                else f"indeterminate:{type(exc).__name__}")
            state["terminal_reason"] = reason
            try:
                _write_state(run_dir, state)
                context.abort(reason)
            except Exception:
                pass  # A stale instance must not change a newer lease.
            raise TeamError("team segment outcome indeterminate; no automatic retry") from exc
        finally:
            if deadline_entered:
                assert deadline_scope is not None
                deadline_scope.__exit__(None, None, None)


def read_team_status_unlocked(
    run_dir: Path, plan: dict[str, Any], state: dict[str, Any],
    schedule: dict[str, Any], ledger: TokenLedger, context: RunContext,
) -> dict[str, Any]:
    session_status = resume_session(schedule, state["run_id"], state["stage_dir"],
                                    state["session_dir"])
    return _status_unlocked(run_dir, plan, state, session_status, ledger, context.status())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="prepare and claim one offline development team run")
    for field in ("schedule", "stage", "plan_file", "price_profile", "run_dir"):
        prepare.add_argument(field, type=Path)
    prepare.add_argument("--limit-tokens", type=int, required=True)
    prepare.add_argument("--active-limit-seconds", type=int, required=True)
    prepare.add_argument("--cost-limit-micro-usd", type=int, required=True)
    status = sub.add_parser("status", help="verify and report a team run")
    status.add_argument("run_dir", type=Path)
    execute = sub.add_parser("execute", help="execute exactly one planned team segment")
    execute.add_argument("run_dir", type=Path)
    execute.add_argument("--expected-checkpoint", required=True)
    execute.add_argument("--allow-paid-requests", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_team(
                args.run_dir, args.schedule, args.stage, _read_json(args.plan_file),
                limit_tokens=args.limit_tokens,
                active_limit_seconds=args.active_limit_seconds,
                cost_limit_micro_usd=args.cost_limit_micro_usd,
                price_profile=_read_json(args.price_profile),
            )
        elif args.command == "status":
            result = read_team_status(args.run_dir)
        else:
            if not args.allow_paid_requests:
                raise TeamError("execute requires --allow-paid-requests")
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise TeamError("OPENAI_API_KEY is unavailable")
            result = execute_team_segment(
                args.run_dir, OpenAIResponsesHTTP(api_key), args.expected_checkpoint)
    except (TeamError, ToolConversationError, BudgetError, DispatchError,
            OSError, ValueError) as exc:
        print(f"Team run failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
