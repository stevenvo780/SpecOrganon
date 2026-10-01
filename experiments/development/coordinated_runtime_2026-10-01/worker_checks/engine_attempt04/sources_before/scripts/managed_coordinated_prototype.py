"""Persistent, locally guarded A/B/C conversations under one parent budget.

The runtime lifecycle is independent of the original method's phase acceptance.
Sources and local prices are declarations, never paid-provider authorization.
"""

from __future__ import annotations

import ast
import importlib
import json
import math
import re
import threading
from pathlib import Path
from typing import Any, Callable

import local_run_admission as admission
import managed_parallel_tools as tools
import managed_parallel_wave as wave
import plan_coordinated_development as planner
from development_delivery_contract import check_delivery, parse_json, validate_delivery_contract
from managed_run_context import RunContext
from managed_token_ledger import BudgetError, _canonical as price_bytes, _price_profile
from managed_wave_ledger import WaveLedger
from run_managed_conversation import (
    _canonical, _new_private_file, _private_dir, _read_json, _run_lock, _write_state,
)
from run_managed_response import MAX_JSON_BYTES, _json_bytes, _validate_function_tool, _validated_request
from staged_tool_session import _work_inventory
from tool_policy import _read_bounded_file


PROFILE = "coordinated_development_parent_v1"
CLASSIFICATION = "development_coordinated_prototype_runtime_unsealed"
ROLES = ("leader", "worker-1", "worker-2", "reviewer")
JOURNALS = (*wave.JOURNALS, "histories", "control")
PLAN_KEYS = {
    "schema", "execution_profile", "run_id", "schedule", "descriptor", "case_dir", "inputs_dir",
    "model", "effort", "price_profile", "functions", "role_config", "max_epochs", "limits",
    "context", "journal_roots", "runtime_source_digests",
}
LIMIT_KEYS = {"limit_tokens", "max_model_requests", "cost_limit_micro_usd", "active_limit_seconds",
              "max_tool_calls", "tool_wall_seconds"}
STATE_KEYS = {
    "schema", "classification", "state", "runtime_stage", "plan_sha256", "run_id",
    "admission_descriptor", "claim_sha256", "source_digests", "broker_binding", "side_binding",
    "reason", "completed_requests", "tool_calls_completed", "cursor", "epoch", "assignments",
    "roles", "timeline", "delegations", "merges", "initialized", "delivery", "reviewer_done",
}
STAGES = {"leader", "workers", "reviewer", "finished", "stopped"}
ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[0-9a-f]{64}\Z")
_AST_NAMES: dict[str, list[str]] = {}
_AST_LOCK = threading.Lock()
LEADER_INSTRUCTION = (
    'Start from empty work and perform actual method init before delegating. '
    'Use original mode semantics, keep norms pending, and integrate public worker artifacts. '
    'Terminal text must be exactly one JSON object with only action and public_text: '
    '{"action":"delegate"|"deliver","public_text":"nonempty public text"}. '
    'Delegate selects one or two currently eligible nodes through the host adapter. '
    'Deliver requires successful current readonly host analysis of the integrated work and all '
    'public delivery artifacts. Do not disclose private reasoning.'
)


class CoordinatedPrototypeError(ValueError):
    """A source, resource, lifecycle, or journal binding no longer holds."""


def _broker(run_dir: Path, binding: dict):
    return importlib.import_module("coordinated_prototype_broker").CoordinatedPrototypeBroker(run_dir, binding)


def _kernel():
    return importlib.import_module("coordinated_prototype_kernel")


def _sources() -> dict[str, str]:
    """Capture actual transitive local code, including dynamically chosen modules."""
    pending = [Path(__file__).stem, "coordinated_prototype_broker", "coordinated_prototype_kernel"]
    captured: dict[str, str] = {}
    while pending:
        name = pending.pop()
        relative = "scripts/" + name + ".py"
        if relative in captured:
            continue
        path = ROOT / relative
        raw = _read_bounded_file(path, "runtime source", 20_000_000)
        digest = wave._sha(raw)
        captured[relative] = digest
        with _AST_LOCK:
            names = _AST_NAMES.get(digest)
            if names is None:
                names = []
                for node in ast.walk(ast.parse(raw)):
                    names.extend([item.name.split(".")[0] for item in node.names] if isinstance(node, ast.Import)
                                 else [node.module.split(".")[0]] if isinstance(node, ast.ImportFrom) and node.module else [])
                _AST_NAMES[digest] = names
        pending.extend(item for item in names if (ROOT / "scripts" / (item + ".py")).is_file())
    captured["prototypes/core.py"] = wave._sha(_read_bounded_file(ROOT / "prototypes/core.py", "core", 20_000_000))
    _verify_sources(captured)
    return dict(sorted(captured.items()))


def _verify_sources(pins: Any) -> None:
    if type(pins) is not dict or not pins:
        raise CoordinatedPrototypeError("missing runtime source closure")
    for relative, digest in pins.items():
        if (type(relative) is not str or Path(relative).is_absolute() or ".." in Path(relative).parts
                or not relative.endswith(".py") or type(digest) is not str or SHA.fullmatch(digest) is None
                or wave._sha(_read_bounded_file(ROOT / relative, "runtime source", 20_000_000)) != digest):
            raise CoordinatedPrototypeError("runtime source pin changed")


def _path(value: Any, label: str) -> Path:
    if type(value) is not str or not Path(value).is_absolute() or ".." in Path(value).parts:
        raise CoordinatedPrototypeError("invalid absolute " + label)
    return Path(value)


def _validate_plan(raw: Any) -> dict:
    if (type(raw) is not dict or set(raw) != PLAN_KEYS or type(raw["schema"]) is not int
            or raw["schema"] != 1 or raw["execution_profile"] != PROFILE):
        raise CoordinatedPrototypeError("invalid closed coordinated plan")
    planner.validate_runtime_binding(raw["schedule"], raw["run_id"], raw["descriptor"])
    descriptor = raw["descriptor"]
    if (raw["model"] != descriptor["model"]["model_id"]
            or raw["effort"] != (descriptor["model"]["effort_provider_value"] or "default")):
        raise CoordinatedPrototypeError("runtime model/effort differ from declared descriptor")
    wave._text(raw["model"], "model", 256)
    wave._text(raw["effort"], "effort", 256)
    profile = _price_profile(raw["price_profile"])
    if (profile["model"] != raw["model"]
            or wave._sha(price_bytes(profile)) != descriptor["model"]["price_profile_sha256"]):
        raise CoordinatedPrototypeError("price profile binding changed")
    limits = raw["limits"]
    expected = {
        "limit_tokens": descriptor["per_run_limits"]["measured_tokens"],
        "active_limit_seconds": descriptor["per_run_limits"]["active_seconds"],
        "max_tool_calls": descriptor["per_run_limits"]["tool_calls"],
        "max_model_requests": descriptor["max_model_requests"],
        "cost_limit_micro_usd": descriptor["cost_limit_micro_usd"],
    }
    if (type(limits) is not dict or set(limits) != LIMIT_KEYS
            or any(type(limits[key]) is not int or limits[key] != value for key, value in expected.items())):
        raise CoordinatedPrototypeError("limits differ from common descriptor")
    wall = limits["tool_wall_seconds"]
    if type(wall) not in (int, float) or not math.isfinite(wall) or not 0 < wall <= min(300, limits["active_limit_seconds"]):
        raise CoordinatedPrototypeError("invalid tool wall cap")
    config = raw["role_config"]
    if type(config) is not dict or set(config) != set(ROLES):
        raise CoordinatedPrototypeError("four persistent roles required")
    for role, caps in config.items():
        if type(caps) is not dict or set(caps) != {"max_output_tokens", "max_model_turns"}:
            raise CoordinatedPrototypeError("invalid role caps")
        wave._integer(caps["max_output_tokens"], 1, min(8192, limits["limit_tokens"]), "role output cap")
        wave._integer(caps["max_model_turns"], 1, limits["max_model_requests"], "global role turn cap")
        if role == "reviewer" and caps["max_model_turns"] != 1:
            raise CoordinatedPrototypeError("reviewer is one serial textual request")
    wave._integer(raw["max_epochs"], 1, limits["max_model_requests"], "epoch cap")
    wave._text(raw["context"], "public context")
    for key in ("case_dir", "inputs_dir"):
        _path(raw[key], key)
    functions = raw["functions"]
    if type(functions) is not list or len(functions) != 2:
        raise CoordinatedPrototypeError("exact method/analysis functions required")
    names = set()
    for function in functions:
        if type(function) is not dict or set(function) != {"type", "name", "description", "parameters", "strict"}:
            raise CoordinatedPrototypeError("functions contain only provider fields")
        _validate_function_tool(function)
        names.add(function["name"])
    if names != {"development_method", "development_analysis"}:
        raise CoordinatedPrototypeError("unsupported functions")
    roots = raw["journal_roots"]
    if type(roots) is not list or not roots or len(roots) > 32 or len(set(roots)) != len(roots):
        raise CoordinatedPrototypeError("invalid fixed journal roots")
    for value in roots:
        _path(value, "journal root")
    _verify_sources(raw["runtime_source_digests"])
    if not _sources().items() <= raw["runtime_source_digests"].items():
        raise CoordinatedPrototypeError("plan omits actual runtime code closure")
    if len(_canonical(raw)) > MAX_JSON_BYTES:
        raise CoordinatedPrototypeError("plan exceeds byte cap")
    return json.loads(_canonical(raw))


def _input_pins(plan: dict) -> None:
    descriptor, directory = plan["descriptor"], Path(plan["inputs_dir"])
    case = parse_json(_read_bounded_file(Path(plan["case_dir"]) / "case.json", "public case", 1_000_000))
    if type(case) is not dict or case.get("case_id") != descriptor["coordinates"]["case_id"]:
        raise CoordinatedPrototypeError("actual public case identity differs from descriptor")
    references = {name: descriptor["inputs"][name]["sha256"] for name in ("task_contract", "common_prompt", "tool_policy")}
    references["arm_prompt"] = descriptor["inputs"]["arm_prompts"][descriptor["coordinates"]["arm"]]["sha256"]
    references.update({name: descriptor["shared_contract"][key]["sha256"] for key, name in (
        ("delivery", "delivery_contract.json"), ("rubric", "rubric.json"), ("coordination_prompt", "coordination_prompt.md"))})
    references["runtime_policy.json"] = descriptor["runtime_policy"]["sha256"]
    for name, digest in references.items():
        raw = _read_bounded_file(directory / name, "public input", 1_000_000)
        if wave._sha(raw) != digest:
            raise CoordinatedPrototypeError("public common/arm/contract input changed: " + name)
    validate_delivery_contract(parse_json(_read_bounded_file(directory / "delivery_contract.json", "delivery contract", 131072)))


def validate_plan(raw: Any, *, check_inputs: bool = False) -> dict:
    """Validate closed declarations before creating participant inputs or run files."""
    checked = _validate_plan(raw)
    if check_inputs:
        _input_pins(checked)
    return checked


def _claim_args(run_dir: Path, plan: dict, state: dict) -> dict:
    return {"schedule_sha256": plan["descriptor"]["schedule_sha256"], "run_id": plan["run_id"],
            "selected_owner": admission.owner("oneshot", run_dir, run_dir),
            "root_descriptor": state["admission_descriptor"], "attempt_number": 1}


def _side_binding(run_dir: Path, plan: dict, state: dict) -> dict:
    return {"schema": 1, "schedule_sha256": plan["descriptor"]["schedule_sha256"],
            "run_id": plan["run_id"], "owner": admission.owner("oneshot", run_dir, run_dir),
            "plan_sha256": state["plan_sha256"], "descriptor_sha256": planner.digest(plan["descriptor"]),
            "limits": plan["limits"], "role_config": plan["role_config"],
            "runtime_source_digests": plan["runtime_source_digests"]}


def _claim(run_dir: Path, plan: dict, state: dict, *, acquire: bool) -> None:
    root = Path(state["admission_descriptor"]["local_run_admission_root"])
    args = _claim_args(run_dir, plan, state)
    expected = _side_binding(run_dir, plan, state)
    path = root / (admission._key(args["schedule_sha256"], args["run_id"], 1) + ".coordinated-binding")
    if state["side_binding"] != {"path": str(path), "sha256": wave._sha(_canonical(expected))}:
        raise CoordinatedPrototypeError("immutable first-plan binding changed")
    if acquire:
        actual = admission.acquire_staged_claim(**args, override=root)
        try:
            _new_private_file(path, _canonical(expected))
        except FileExistsError:
            pass
    else:
        actual = admission.require_claim(**args, override=root)
    if actual != state["claim_sha256"] or _read_json(path) != expected:
        raise CoordinatedPrototypeError("original schedule claim or first-plan binding changed")


def _task(plan: dict, role: str) -> dict:
    return {"task_id": role, "role": role, **plan["role_config"][role]}


def _initial_history(plan: dict, role: str) -> list:
    instruction = (LEADER_INSTRUCTION if role == "leader" else
                   "Review only public artifacts and structural delivery evidence; return public text without tools or approval."
                   if role == "reviewer" else
                   "Work only on your active assigned nodes and files, using revise/review, never init/approve/advance. Return public text.")
    return [{"role": "user", "content": _json_bytes({"common_context": plan["context"],
             "task_id": role, "role": role, "instruction": instruction}).decode()}]


def _request(plan: dict, role: str, history: list) -> dict:
    value = {"model": plan["model"], "reasoning": {"effort": plan["effort"]},
             "service_tier": "default", "max_output_tokens": plan["role_config"][role]["max_output_tokens"],
             "input": history}
    if role != "reviewer":
        value.update(tools=plan["functions"], parallel_tool_calls=False)
    return _validated_request(value)


def _roots(run_dir: Path, plan: dict) -> list[Path]:
    return sorted(set([run_dir / name for name in JOURNALS] +
                      [run_dir / "plan.json", run_dir / "run.json", run_dir / "ledger", run_dir / "broker_stages", run_dir / "broker_tools"] +
                      list(map(Path, plan["journal_roots"]))), key=str)


def _bindings(plan: dict, state: dict) -> dict:
    return {"profile": PROFILE, "ledger_kind": "wave_v1", "ledger_schema": 3,
            "plan_sha256": state["plan_sha256"], "schedule_sha256": plan["descriptor"]["schedule_sha256"],
            "descriptor_sha256": planner.digest(plan["descriptor"]), "run_id": plan["run_id"],
            "claim_sha256": state["claim_sha256"], "side_binding": state["side_binding"],
            "broker_binding": state["broker_binding"], "source_digests": state["source_digests"]}


def _check_context(run_dir: Path, plan: dict, state: dict) -> None:
    actual = _read_json(run_dir / "context/run.json")
    if (actual["bindings"] != _bindings(plan, state) or actual["roles"] != ["coordinator"]
            or actual["journal_roots"] != list(map(str, _roots(run_dir, plan)))
            or actual["ledger_dir"] != str(run_dir / "ledger")
            or actual["active_limit_seconds"] != plan["limits"]["active_limit_seconds"]
            or actual["max_tool_calls"] != plan["limits"]["max_tool_calls"]):
        raise CoordinatedPrototypeError("effective context policy changed")


def prepare_coordinated_prototype(run_dir: Path, plan: dict, *, admission_root: Path | None = None) -> dict:
    plan = _validate_plan(plan)
    _input_pins(plan)
    run_dir = _path(str(run_dir), "run directory")
    _private_dir(run_dir.parent)
    if run_dir.exists() or run_dir.is_symlink():
        raise FileExistsError("coordinated run already exists")
    registry = admission.configured_root(admission_root)
    for source in (Path(plan["case_dir"]), Path(plan["inputs_dir"]), registry):
        if run_dir == source or run_dir in source.parents or source in run_dir.parents:
            raise CoordinatedPrototypeError("run, sources, and admission registry must be disjoint")
    state = {"schema": 1, "classification": CLASSIFICATION, "state": "prepared", "runtime_stage": "leader",
             "plan_sha256": wave._sha(_canonical(plan)), "run_id": plan["run_id"],
             "admission_descriptor": admission.descriptor(registry), "claim_sha256": "", "side_binding": None,
             "source_digests": plan["runtime_source_digests"], "broker_binding": None, "reason": None,
             "completed_requests": 0, "tool_calls_completed": 0, "cursor": 0, "epoch": 0,
             "assignments": [], "roles": {}, "timeline": [], "delegations": [], "merges": [],
             "initialized": False, "delivery": None, "reviewer_done": False}
    state["claim_sha256"] = admission.claim_digest(**_claim_args(run_dir, plan, state))
    binding_path = registry / (admission._key(plan["descriptor"]["schedule_sha256"], plan["run_id"]) + ".coordinated-binding")
    state["side_binding"] = {"path": str(binding_path), "sha256": wave._sha(_canonical(_side_binding(run_dir, plan, state)))}
    run_dir.mkdir(mode=0o700)
    _new_private_file(run_dir / ".lock", b"")
    for folder in JOURNALS:
        (run_dir / folder).mkdir(mode=0o700)
    _new_private_file(run_dir / "plan.json", _canonical(plan))
    for role in ROLES:
        directory = run_dir / "histories" / role
        directory.mkdir(mode=0o700)
        value = {"history": _initial_history(plan, role)}
        _new_private_file(directory / "run.json", _canonical(value))
        state["roles"][role] = {"turns": 0, "finished": False, "history_sha256": wave._sha(_canonical(value))}
    # Broad immutable journal roots are selected before context creation.
    state["broker_binding"] = importlib.import_module("coordinated_prototype_broker").prepare_broker(
        run_dir, Path(plan["case_dir"]), Path(plan["inputs_dir"]), mode=plan["descriptor"]["coordinates"]["mode"])
    _new_private_file(run_dir / "run.json", _canonical(state))
    limits = plan["limits"]
    WaveLedger.create(run_dir / "ledger", limits["limit_tokens"], limits["max_model_requests"],
                      cost_limit_micro_usd=limits["cost_limit_micro_usd"], price_profile=plan["price_profile"], effort=plan["effort"])
    RunContext.create(run_dir / "context", run_dir / "ledger", _bindings(plan, state),
                      active_limit_seconds=limits["active_limit_seconds"], max_tool_calls=limits["max_tool_calls"],
                      roles=["coordinator"], ledger_kind="wave_v1", journal_roots=_roots(run_dir, plan))
    return read_coordinated_prototype_status(run_dir)


def _load(run_dir: Path):
    _private_dir(run_dir)
    plan = _validate_plan(_read_json(run_dir / "plan.json"))
    _input_pins(plan)
    state = _read_json(run_dir / "run.json")
    if (type(state) is not dict or set(state) != STATE_KEYS or state["schema"] != 1
            or state["classification"] != CLASSIFICATION
            or state["state"] not in {"prepared", "paused", "started", "completed", "indeterminate"}
            or state["runtime_stage"] not in STAGES or state["run_id"] != plan["run_id"]
            or state["plan_sha256"] != wave._sha(_canonical(plan))
            or state["source_digests"] != plan["runtime_source_digests"]
            or state["claim_sha256"] != admission.claim_digest(**_claim_args(run_dir, plan, state))):
        raise CoordinatedPrototypeError("plan, source, lifecycle or schedule claim changed")
    for key in ("completed_requests", "tool_calls_completed", "cursor", "epoch"):
        wave._integer(state[key], 0, 10000, key)
    if type(state["roles"]) is not dict or set(state["roles"]) != set(ROLES):
        raise CoordinatedPrototypeError("persistent role set changed")
    for role, cursor in state["roles"].items():
        if (type(cursor) is not dict or set(cursor) != {"turns", "finished", "history_sha256"}
                or type(cursor["finished"]) is not bool or type(cursor["history_sha256"]) is not str
                or SHA.fullmatch(cursor["history_sha256"]) is None):
            raise CoordinatedPrototypeError("invalid role cursor")
        wave._integer(cursor["turns"], 0, plan["role_config"][role]["max_model_turns"], "global role counter")
    ledger, context = WaveLedger(run_dir / "ledger"), RunContext(run_dir / "context")
    wave._check_budget({**plan, **plan["limits"]}, ledger.status())
    _check_context(run_dir, plan, state)
    if state["cursor"] or state["state"] not in {"prepared"}:
        _claim(run_dir, plan, state, acquire=False)
    return plan, state, ledger, context, _broker(run_dir, state["broker_binding"])


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
        raise CoordinatedPrototypeError("actual RAW/request/receipt/ledger replay changed")
    return response


def _envelope(text: str) -> dict:
    try:
        value = parse_json(text.encode())
    except ValueError as exc:
        raise CoordinatedPrototypeError("leader terminal envelope is invalid") from exc
    if (type(value) is not dict or set(value) != {"action", "public_text"}
            or value["action"] not in {"delegate", "deliver"}):
        raise CoordinatedPrototypeError("leader terminal envelope has unexpected fields/action")
    wave._text(value["public_text"], "leader public text")
    return value


def _artifact(role: str, request_id: str, epoch: int, text: str) -> dict:
    value = {"task_id": role, "role": role, "request_id": request_id, "epoch": epoch, "text": text}
    value["artifact_sha256"] = wave._sha(_canonical(value))
    return value


def _save_history(run_dir: Path, state: dict, role: str, history: list) -> None:
    value = {"history": history}
    _write_state(run_dir / "histories" / role, value)
    state["roles"][role]["history_sha256"] = wave._sha(_canonical(value))
    _write_state(run_dir, state)


def _host_message(run_dir: Path, plan: dict, state: dict, role: str, public: dict) -> None:
    message = {"role": "user", "content": _json_bytes(public).decode()}
    state["timeline"].append({"kind": "host", "role": role, "epoch": state["epoch"], "message": message})
    history = _read_json(run_dir / "histories" / role / "run.json")["history"] + [message]
    _request(plan, role, history)
    _save_history(run_dir, state, role, history)


def _audit(run_dir: Path, plan: dict, state: dict, ledger: WaveLedger, broker) -> None:
    verified = broker.verify()
    if verified["blocked"] or verified["pending"] or ledger.status()["blocked"]:
        raise CoordinatedPrototypeError("uncertain model/tool/host journals block checkpoint")
    operations = broker.operations()
    if len(operations) != state["tool_calls_completed"]:
        raise CoordinatedPrototypeError("global tool counter differs from broker")
    indexed, call_ids = {}, set()
    for ordinal, operation in enumerate(operations, 1):
        key = (operation["task_id"], operation["request_id"])
        if key in indexed or operation["call_id"] in call_ids or operation["global_ordinal"] != ordinal:
            raise CoordinatedPrototypeError("tool identities or global ordinals changed")
        indexed[key] = operation
        call_ids.add(operation["call_id"])
    histories = {role: _initial_history(plan, role) for role in ROLES}
    turns = dict.fromkeys(ROLES, 0)
    requests, consumed, artifacts = set(), set(), set()
    for event in state["timeline"]:
        role = event["role"]
        if role not in ROLES:
            raise CoordinatedPrototypeError("timeline has unknown role")
        if event["kind"] == "host":
            if (set(event) != {"kind", "role", "epoch", "message"}
                    or set(event["message"]) != {"role", "content"} or event["message"]["role"] != "user"):
                raise CoordinatedPrototypeError("invalid public host feedback")
            histories[role].append(event["message"])
            continue
        if event["kind"] != "model" or set(event) != {"kind", "role", "epoch", "turn", "request_id", "artifact"}:
            raise CoordinatedPrototypeError("invalid model timeline")
        turns[role] += 1
        request_id = tools._id(role, turns[role])
        if event["turn"] != turns[role] or event["request_id"] != request_id or request_id in requests:
            raise CoordinatedPrototypeError("global role counter/ID replay changed")
        requests.add(request_id)
        response = _response(run_dir, state, request_id, _request(plan, role, histories[role]), role, ledger)
        decoded = ({"kind": "text", "text": wave._response_text(response, plan["model"])} if role == "reviewer"
                   else tools._decode(plan, response, plan["model"]))
        histories[role].extend(response["output"])
        if decoded["kind"] == "function":
            operation, call = indexed.get((role, request_id)), decoded["call"]
            if (event["artifact"] is not None or operation is None or operation["call_id"] != call["call_id"]
                    or operation["function_name"] != call["name"]
                    or operation["outer_arguments"] != json.loads(call["arguments"])):
                raise CoordinatedPrototypeError("tool operation differs from actual model request")
            result = operation["result"]
            if (type(result) is not dict or set(result) != {"type", "call_id", "output"}
                    or result["type"] != "function_call_output" or result["call_id"] != call["call_id"]
                    or type(result["output"]) is not str):
                raise CoordinatedPrototypeError("invalid tool result feedback")
            histories[role].append(result)
            consumed.add((role, request_id))
        else:
            text = _envelope(decoded["text"])["public_text"] if role == "leader" else decoded["text"]
            name = request_id + ".json"
            if event["artifact"] != name or _read_json(run_dir / "artifacts" / name) != _artifact(role, request_id, event["epoch"], text):
                raise CoordinatedPrototypeError("public artifact differs from actual response")
            artifacts.add(name)
        _request(plan, role, histories[role])
    for role in ROLES:
        value = {"history": histories[role]}
        if (state["roles"][role]["turns"] != turns[role]
                or _read_json(run_dir / "histories" / role / "run.json") != value
                or state["roles"][role]["history_sha256"] != wave._sha(_canonical(value))):
            raise CoordinatedPrototypeError("private history or global counter changed")
    if (consumed != set(indexed) or set(ledger.status()["requests"]) != requests
            or len(requests) != state["completed_requests"]):
        raise CoordinatedPrototypeError("unbound tool/model effects or request counters")
    for directory in ("requests", "responses", "receipts"):
        if {path.name for path in (run_dir / directory).iterdir()} != {key + ".json" for key in requests}:
            raise CoordinatedPrototypeError("flat model journal inventory changed")
    if {path.name for path in (run_dir / "artifacts").iterdir()} != artifacts:
        raise CoordinatedPrototypeError("public artifact inventory changed")


def _public_artifacts(run_dir: Path) -> list[dict]:
    return [_read_json(path) for path in sorted((run_dir / "artifacts").iterdir())]


def _public_deliverables(plan: dict, broker) -> list[dict]:
    """Publish actual bounded participant files, with their content hashes."""
    case_id = plan["descriptor"]["coordinates"]["case_id"]
    files = ["analysis.py", "report.md"] + (["sources.json"] if case_id == "D-F" else [])
    result = []
    for name in files:
        raw = _read_bounded_file(broker.leader_stage() / "work" / name, "public deliverable", 131072)
        result.append({"path": name, "bytes": len(raw), "sha256": wave._sha(raw), "content": raw.decode("utf-8")})
    return result


def _bound_receipt(value: dict, label: str) -> None:
    if type(value) is not dict or not {"path", "sha256"} <= set(value):
        raise CoordinatedPrototypeError(label + " has no durable receipt")
    path = _path(value["path"], label)
    if wave._sha(_read_bounded_file(path, label, MAX_JSON_BYTES)) != value["sha256"]:
        raise CoordinatedPrototypeError(label + " durable receipt changed")


def _initialized(plan: dict, broker) -> None:
    operations = broker.operations()
    successful = [row for row in operations if row["task_id"] == "leader"
                  and type(row.get("request")) is dict and row["request"].get("op") == "init"
                  and type(row.get("output_json")) is dict and row["output_json"].get("ok") is True]
    if len(successful) != 1:
        raise CoordinatedPrototypeError("delegation requires exactly one actual sealed successful leader init")
    public = broker.public_state()
    state = public.get("state")
    if type(state) is not dict:
        raise CoordinatedPrototypeError("broker public state has no original method state")
    _kernel().parse_state(json.dumps(state).encode(), mode=plan["descriptor"]["coordinates"]["mode"],
                          case_id=plan["descriptor"]["coordinates"]["case_id"])


def _delegate(run_dir: Path, plan: dict, state: dict, broker, active_guard: Callable) -> None:
    _initialized(plan, broker)
    state["initialized"] = True
    if state["epoch"] >= plan["max_epochs"]:
        raise CoordinatedPrototypeError("fixed delegation epoch cap exhausted")
    public = broker.public_state()
    selected = _kernel().select_work(public["state"], limit=2)
    if not selected:
        state.update(runtime_stage="stopped", reason="no eligible work; runtime delivery remains pending")
        _write_state(run_dir, state)
        return
    epoch = state["epoch"] + 1
    assignments = [{"task_id": "worker-" + str(index), "owned_node_ids": [row["id"]],
                    "owned_files": ["analysis.py"] if index == 1 else ["report.md", "sources.json"]}
                   for index, row in enumerate(selected, 1)]
    activation = broker.activate_epoch(epoch, assignments, guard=active_guard)
    _bound_receipt(activation, "epoch activation")
    state.update(epoch=epoch, assignments=assignments, runtime_stage="workers")
    state["delegations"].append({"epoch": epoch, "selection": selected, "assignments": assignments, "activation": activation})
    _write_state(run_dir, state)
    for assignment, row in zip(assignments, selected, strict=True):
        role = assignment["task_id"]
        state["roles"][role]["finished"] = False
        _host_message(run_dir, plan, state, role, {"epoch": epoch, "assignment": assignment,
                      "selected_action": row["action"], "public_method": public,
                      "public_artifacts": _public_artifacts(run_dir)})


def _validate_delivery(run_dir: Path, plan: dict, broker) -> dict:
    current = broker.current_metrics("leader")
    if type(current) is not dict:
        raise CoordinatedPrototypeError("delivery requires current readonly host metrics from integrated leader work")
    work = broker.leader_stage() / "work"
    source = _read_bounded_file(work / "analysis.py", "analysis source", 131072)
    metrics = _read_bounded_file(work / "metrics.json", "host metrics", 131072)
    if (current.get("analysis_script_sha256") != wave._sha(source)
            or current.get("analysis_metrics_sha256") != wave._sha(metrics)
            or current.get("metrics_path") != str(work / "metrics.json")
            or current.get("metrics") != parse_json(metrics)):
        raise CoordinatedPrototypeError("final analysis source or host metrics binding changed")
    operations = broker.operations()
    row = next((row for row in operations if row["global_ordinal"] == current.get("global_ordinal")), None)
    if (row is None or row["task_id"] != "leader" or row["function_name"] != "development_analysis"
            or wave._sha(_canonical(row["terminal"])) != current.get("receipt_sha256")):
        raise CoordinatedPrototypeError("final metrics lack actual integrated readonly analysis receipt")
    contract = parse_json(_read_bounded_file(Path(plan["inputs_dir"]) / "delivery_contract.json", "public contract", 131072))
    checked = check_delivery(Path(plan["case_dir"]), work, contract)
    if not checked["structural_checks_passed"]:
        raise CoordinatedPrototypeError("public delivery structure failed: " + json.dumps(checked["issues"]))
    value = {"schema": 1, "current_metrics": current, "checker": checked,
             "work_inventory": _work_inventory(broker.leader_stage()), "public_method": broker.public_state()}
    name = run_dir / "control/delivery.json"
    _new_private_file(name, _canonical(value))
    return {"path": str(name), "sha256": wave._sha(_canonical(value)), **value}


def _publication(run_dir: Path, plan: dict, state: dict, status: dict) -> dict:
    return {"schema": 1, "classification": CLASSIFICATION, "profile": PROFILE,
            "schedule_sha256": plan["descriptor"]["schedule_sha256"], "run_id": plan["run_id"],
            "plan_sha256": state["plan_sha256"], "checkpoint_sha256": status["checkpoint_sha256"],
            "delivery_sha256": state["delivery"]["sha256"],
            "delegations_sha256": wave._sha(_canonical(state["delegations"])),
            "merges_sha256": wave._sha(_canonical(state["merges"])),
            "artifacts": [{"path": str(path), "sha256": wave._sha(path.read_bytes())}
                          for path in sorted((run_dir / "artifacts").iterdir())],
            "method_phases_accepted": False, "quality_assessed": False, "formal_cell_executed": False}


def _view(run_dir: Path, plan: dict, state: dict, ledger: WaveLedger, context: RunContext) -> dict:
    captured = context.status()
    terminal = state["state"] == captured["state"] == "completed"
    published = False
    if terminal:
        try:
            published = _read_json(run_dir / "publication.json") == _publication(run_dir, plan, state, captured)
        except (OSError, ValueError, KeyError):
            pass
    return {"classification": CLASSIFICATION, "execution_profile": PROFILE,
            "state": "indeterminate" if terminal and not published else captured["state"],
            "stored_state": state["state"], "runtime_stage": state["runtime_stage"], "epoch": state["epoch"],
            "run_id": plan["run_id"], "schedule_sha256": plan["descriptor"]["schedule_sha256"],
            "checkpoint_sha256": captured["checkpoint_sha256"], "cursor": captured["cursor"],
            "context": captured, "budget": ledger.status(), "roles": state["roles"],
            "assignments": state["assignments"], "delegations": state["delegations"], "merges": state["merges"],
            "completed_requests": state["completed_requests"], "tool_calls_completed": state["tool_calls_completed"],
            "reason": "publication marker missing or invalid" if terminal and not published else state["reason"],
            "artifacts": _publication(run_dir, plan, state, captured)["artifacts"] if published else [],
            "delivery": state["delivery"] if published else None, "publication_valid": published,
            "formal_cell_executed": False, "comparable_development_cell": False, "quality_assessed": False,
            "method_phases_accepted": False, "identity_authenticated": False, "cost_authenticated": False,
            "bundle_custody_authenticated": False, "engine_scope": "local_declared_bindings_external_wrapper_guard_required_for_D118_bundle",
            "active_time_scope": "shared_local_clock_not_authenticated_provider_activity",
            "remote_cancellation_guaranteed": False}


def read_coordinated_prototype_status(run_dir: Path, *, guard: Callable | None = None) -> dict:
    run_dir = Path(run_dir)
    with _run_lock(run_dir):
        plan, state, ledger, context, broker = _load(run_dir)
        if guard is not None:
            guard(plan, state, broker)
        if state["state"] in {"prepared", "paused", "completed"}:
            _audit(run_dir, plan, state, ledger, broker)
            for row in state["delegations"]:
                _bound_receipt(row["activation"], "epoch activation")
            for row in state["merges"]:
                _bound_receipt(row["receipt"], "epoch merge")
        if state["state"] == "completed":
            _bound_receipt(state["delivery"], "delivery")
            if broker.current_metrics("leader") != state["delivery"]["current_metrics"]:
                raise CoordinatedPrototypeError("published metrics are stale")
        return _view(run_dir, plan, state, ledger, context)


def execute_coordinated_prototype_step(run_dir: Path, transports: dict, *, expected_checkpoint: str,
                                      guard: Callable | None = None) -> dict:
    run_dir = Path(run_dir)
    with _run_lock(run_dir):
        plan, state, ledger, context, broker = _load(run_dir)
        if (state["state"] not in {"prepared", "paused"} or context.status()["state"] != state["state"]
                or state["runtime_stage"] in {"stopped", "finished"}):
            raise CoordinatedPrototypeError("started, uncertain, stopped or terminal runs never reexecute")
        if guard is not None and not callable(guard):
            raise CoordinatedPrototypeError("external guard must be callable")
        if state["runtime_stage"] == "workers":
            roles = [item["task_id"] for item in state["assignments"] if not state["roles"][item["task_id"]]["finished"]]
        else:
            roles = [state["runtime_stage"]]
        if type(transports) is not dict or set(transports) not in (set(roles), set(ROLES)):
            raise CoordinatedPrototypeError("transport keys differ from current persistent roles")
        if guard is not None:
            guard(plan, state, broker)
        _audit(run_dir, plan, state, ledger, broker)
        context.begin(expected_checkpoint, "coordinator")
        state["state"] = "started"
        finished_context = False
        try:
            _write_state(run_dir, state)
            _claim(run_dir, plan, state, acquire=True)

            def active_guard() -> None:
                context.require_active()
                _verify_sources(state["source_digests"])
                if (not _sources().items() <= state["source_digests"].items()
                        or wave._sha((run_dir / "plan.json").read_bytes()) != state["plan_sha256"]):
                    raise CoordinatedPrototypeError("active plan/source closure changed")
                _input_pins(plan)
                _check_context(run_dir, plan, state)
                _claim(run_dir, plan, state, acquire=False)
                for role, cursor in state["roles"].items():
                    if wave._sha(_canonical(_read_json(run_dir / "histories" / role / "run.json"))) != cursor["history_sha256"]:
                        raise CoordinatedPrototypeError("active private role history changed")
                wave._check_budget({**plan, **plan["limits"]}, ledger.status())
                if broker.verify()["blocked"]:
                    raise CoordinatedPrototypeError("broker has an uncertain effect")
                if guard is not None:
                    guard(plan, state, broker)
                context.require_active()

            active_guard()
            tasks, requests, request_ids = [], [], {}
            histories = {}
            for role in roles:
                cursor = state["roles"][role]
                if cursor["turns"] >= plan["role_config"][role]["max_model_turns"] or cursor["finished"]:
                    raise CoordinatedPrototypeError("global role turn cap exhausted")
                task = _task(plan, role)
                tasks.append(task)
                histories[role] = _read_json(run_dir / "histories" / role / "run.json")["history"]
                requests.append(_request(plan, role, histories[role]))
                request_ids[role] = tools._id(role, cursor["turns"] + 1)
            reviewer = roles == ["reviewer"]
            decoded = wave._batch(run_dir, {**plan, **plan["limits"]}, tasks, requests, transports,
                                  "coordinated-step-" + str(state["cursor"] + 1), ledger, context, active_guard, state,
                                  request_ids=request_ids, decoder=(None if reviewer else
                                      lambda response, model: tools._decode(plan, response, model)))
            calls = [entry for entry in decoded if entry.get("kind") == "function"]
            if state["tool_calls_completed"] + len(calls) > plan["limits"]["max_tool_calls"]:
                raise CoordinatedPrototypeError("single parent tool cap exhausted")
            seen_calls = {operation["call_id"] for operation in broker.operations()}
            for role, entry in zip(roles, decoded, strict=True):
                if entry.get("kind") == "function":
                    if (entry["call"]["call_id"] in seen_calls
                            or state["roles"][role]["turns"] + 1 >= plan["role_config"][role]["max_model_turns"]):
                        raise CoordinatedPrototypeError("replayed tool identity or no terminal turn remaining")
                    seen_calls.add(entry["call"]["call_id"])
                elif role == "leader":
                    _envelope(entry["text"])
            for role, entry, request in zip(roles, decoded, requests, strict=True):
                active_guard()
                request_id = request_ids[role]
                response = _response(run_dir, state, request_id, request, role, ledger)
                history = histories[role] + response["output"]
                artifact = None
                if entry.get("kind") == "function":
                    result = broker.invoke(role, request_id, {key: entry["call"][key] for key in ("name", "call_id", "arguments")},
                                           context, active_guard)
                    history.append(result)
                    state["tool_calls_completed"] += 1
                else:
                    text = _envelope(entry["text"])["public_text"] if role == "leader" else entry["text"]
                    artifact = request_id + ".json"
                    _new_private_file(run_dir / "artifacts" / artifact, _canonical(_artifact(role, request_id, state["epoch"], text)))
                    if role != "leader":
                        state["roles"][role]["finished"] = True
                _request(plan, role, history)
                state["roles"][role]["turns"] += 1
                state["timeline"].append({"kind": "model", "role": role, "epoch": state["epoch"],
                                          "turn": state["roles"][role]["turns"], "request_id": request_id, "artifact": artifact})
                _save_history(run_dir, state, role, history)
                active_guard()
            if state["runtime_stage"] == "leader" and decoded[0].get("kind") != "function":
                envelope = _envelope(decoded[0]["text"])
                if envelope["action"] == "delegate":
                    _delegate(run_dir, plan, state, broker, active_guard)
                else:
                    _initialized(plan, broker)
                    state["initialized"] = True
                    state["delivery"] = _validate_delivery(run_dir, plan, broker)
                    state["roles"]["leader"]["finished"] = True
                    state["runtime_stage"] = "reviewer"
                    _write_state(run_dir, state)
                    _host_message(run_dir, plan, state, "reviewer", {
                        "public_artifacts": _public_artifacts(run_dir),
                        "public_deliverables": _public_deliverables(plan, broker),
                        "delivery": {key: state["delivery"][key] for key in ("checker", "public_method")},
                        "final_host_metrics": state["delivery"]["current_metrics"]})
            elif state["runtime_stage"] == "workers" and all(state["roles"][item["task_id"]]["finished"] for item in state["assignments"]):
                merged = broker.merge_epoch(state["epoch"], guard=active_guard)
                _bound_receipt(merged, "epoch merge")
                state["merges"].append({"epoch": state["epoch"], "receipt": merged})
                state["runtime_stage"] = "leader"
                _write_state(run_dir, state)
                _host_message(run_dir, plan, state, "leader", {"epoch": state["epoch"], "merge_receipt": merged,
                    "public_method": broker.public_state(), "public_artifacts": _public_artifacts(run_dir),
                    "current_host_metrics": broker.current_metrics("leader")})
            elif reviewer:
                state.update(reviewer_done=True, runtime_stage="finished")
            _audit(run_dir, plan, state, ledger, broker)
            state["cursor"] += 1
            if state["runtime_stage"] == "finished":
                if broker.current_metrics("leader") != state["delivery"]["current_metrics"]:
                    raise CoordinatedPrototypeError("delivery metrics became stale before finish")
                state["state"] = "completed"
                _write_state(run_dir, state)
                active_guard()
                context.finish(state["cursor"])
                finished_context = True
                _new_private_file(run_dir / "publication.json", _canonical(_publication(run_dir, plan, state, context.status())))
            else:
                state["state"] = "paused"
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


# Short programmatic aliases carry the same strict contract.
read_status = read_coordinated_prototype_status
execute_step = execute_coordinated_prototype_step
