"""Bounded D099 two-turn subscription experiment with one reviewed offline replay.

Local admission and hashes protect cooperating callers. They do not authenticate
the provider, attest remote request counts, or resist the same UID rewriting state.
The operator applies the registered S/T/N order; this arm broker does not enforce it.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from local_replay_sandbox import (  # noqa: E402
    SandboxError,
    SandboxUnavailable,
    default_python_runtime_roots,
    run_sandboxed,
)
from run_development_arm import RunError, _capture, _parse_usage  # noqa: E402
from run_prototype_checkpoint import (  # noqa: E402
    LIMITS,
    CheckpointError,
    _artifact_record,
    _atomic,
    _auth,
    _disabled_features,
    _environment,
    _host_preflight,
    _json,
    _now,
    _read,
    _record,
)

PLAN = ROOT / "experiments/development/subscription_method_trial_2026-09-30/plan.json"
PLAN_SHA = "ec9c7d1a6359e91a8543e07872226c4d2009296e78b8c151843cc283dab24ed1"
ADMISSION_ENV = "SPECORGANON_SUBSCRIPTION_METHOD_ADMISSION_ROOT"
PACKAGING_PREFIX = b"#!/usr/bin/python3.12 -I\n"
PACKAGING_INTERPRETER = Path("/usr/bin/python3.12")
PROPOSAL_MAX = 96 * 1024
COMPONENT_MAX = 32 * 1024
SANDBOX_LIMITS = {"wall_seconds": 30, "cpu_seconds": 10,
                  "address_space_bytes": 536870912, "file_bytes_per_file": 2097152}
KINDS = ("problem", "actor", "boundary", "assumption", "evidence", "norm", "decision", "requirement")
OUTPUTS = {"analysis_py": "first.analysis.py", "draft_report_md": "first.report.md",
           "items_json": "first.items.json"}
ACTOR = "agent:d099_executor"
TITLE = "D099 exposed building energy method trial"
DOMAIN = "building_energy"
STATES = {"prepared", "generating", "awaiting_review", "feedback_started",
          "feedback_ready", "finalizing", "completed", "failed"}
CLAIMS = {**LIMITS, "approved_normative_decisions": 0, "completed_phases": 0,
          "global_acceptance": "0/5", "Q": None, "human_quality_score": None,
          "method_winner_selected": False, "field_intervention_authorized": False,
          "model_calls_independently_attested": False,
          "ordered_execution_preventively_enforced": False,
          "arm_order_control": "operator applies fixed S/T/N terminal-before-next"}


class TrialError(ValueError):
    pass


def _strict(raw: bytes, *, array: bool = False):
    # Wrap arrays to reuse duplicate-key and constant rejection from D097.
    value = _json(b'{"value":' + raw + b'}')["value"] if array else _json(raw)
    def finite(item):
        if type(item) is float and not math.isfinite(item):
            raise TrialError("nonfinite JSON number")
        if type(item) is dict:
            for child in item.values():
                finite(child)
        elif type(item) is list:
            for child in item:
                finite(child)
    finite(value)
    if array and type(value) is not list:
        raise TrialError("items must be a JSON array")
    return value


def _relative(value: str) -> Path:
    if (type(value) is not str or not value or Path(value).is_absolute()
            or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise TrialError("invalid registered relative path")
    return Path(value)


def _pin(raw: bytes, pin: dict, label: str) -> None:
    if type(pin) is not dict or _record(raw) != {k: pin.get(k) for k in ("sha256", "bytes")}:
        raise TrialError(f"registered bytes changed: {label}")


def _authority() -> tuple[dict, bytes]:
    raw = _read(PLAN)
    if _record(raw)["sha256"] != PLAN_SHA:
        raise TrialError("fixed prospective D099 plan changed")
    plan = _strict(raw)
    required = {"schema": 1, "study_id": "D099", "requested_model": "gpt-6-luna",
                "requested_effort": "medium", "arm_order": ["S", "T", "N"],
                "active_seconds_per_arm": 360, "attempts_per_arm": 1,
                "max_model_calls_per_arm": 2, "max_generic_replays_per_arm": 1,
                "max_toolkit_puts": 8, "sandbox": SANDBOX_LIMITS,
                "allowed_item_kinds": list(KINDS), "first_schema_fields": list(OUTPUTS),
                "second_schema_fields": ["report_md"],
                "item_fields": ["id", "kind", "text", "refs", "data"]}
    if any(plan.get(key) != value for key, value in required.items()):
        raise TrialError("invalid fixed D099 configuration")
    if (set(plan.get("sources", {})) != {"task.md", "source_manifest.json", "sample_first_complete_week.csv"}
            or set(plan.get("prompts", {})) != {"common", "N", "S", "T"}):
        raise TrialError("invalid registered public packet")
    return plan, raw


def _schema(fields: tuple[str, ...]) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(fields),
            "properties": {name: {"type": "string"} for name in fields}}


def _items(raw: bytes) -> list[dict]:
    if len(raw) > COMPONENT_MAX:
        raise TrialError("items exceeds 32 KiB")
    items = _strict(raw, array=True)
    if len(items) > 8:
        raise TrialError("at most eight toolkit items")
    declared = set()
    reserved = {"approved", "approval", "approvals", "signature", "signatures", "signed",
                "trust", "trusted", "review", "reviews", "reviewed", "advance", "advanced",
                "command", "commands", "argv", "execute", "execution", "test_result",
                "test_results", "test_passed", "passed", "accepted", "verified"}
    def safe_data(value):
        if type(value) is dict:
            for key, child in value.items():
                normalized = key.casefold().replace("-", "_")
                if (normalized in reserved or normalized.startswith(("approval_", "signature_",
                        "trust_", "review_", "advance_", "command_", "execution_"))):
                    raise TrialError("privileged item data key forbidden")
                safe_data(child)
        elif type(value) is list:
            for child in value:
                safe_data(child)
    for item in items:
        if type(item) is not dict or set(item) != {"id", "kind", "text", "refs", "data"}:
            raise TrialError("invalid exact item fields")
        identifier = item["id"]
        if (type(identifier) is not str or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{1,63}", identifier)
                or identifier in declared or item["kind"] not in KINDS):
            raise TrialError("invalid unique item id or kind")
        if (type(item["text"]) is not str or not item["text"].strip()
                or len(item["text"].encode()) > 8192 or "\0" in item["text"]):
            raise TrialError("invalid bounded item text")
        refs = item["refs"]
        if (type(refs) is not list or any(type(r) is not str or r not in declared for r in refs)
                or len(refs) != len(set(refs)) or type(item["data"]) is not dict):
            raise TrialError("item refs must name earlier distinct ids and data must be an object")
        safe_data(item["data"])
        declared.add(identifier)
    return items


def _proposal(raw: bytes, *, final: bool = False) -> dict:
    if len(raw) > PROPOSAL_MAX:
        raise TrialError("proposal exceeds 96 KiB")
    result = _strict(raw)
    expected = {"report_md"} if final else set(OUTPUTS)
    if set(result) != expected or any(type(value) is not str for value in result.values()):
        raise TrialError("proposal requires exact string fields")
    if any(len(value.encode()) > COMPONENT_MAX for value in result.values()):
        raise TrialError("component exceeds 32 KiB")
    report = result["report_md" if final else "draft_report_md"]
    if not report.strip():
        raise TrialError("report is empty")
    if len(report.split()) > 1200:
        raise TrialError("report exceeds 1200 words")
    if not final:
        # Item interpretation waits for reviewed feedback, but JSON syntax is fixed now.
        _strict(result["items_json"].encode(), array=True)
    return result


def _blobs(repo: Path, protocol: dict, raw: bytes, arm: str) -> dict[str, bytes]:
    blobs = {"protocol.json": raw}
    for category, prefix in (("sources", "input"), ("prompts", "prompts")):
        for name, pin in protocol[category].items():
            source = repo / _relative(pin["path"])
            data = _read(source)
            _pin(data, pin, name)
            blobs[f"{prefix}/{name}"] = data
    toolkit = protocol["toolkit"]
    cli = Path(toolkit["cli_path"])
    if not cli.is_absolute():
        raise TrialError("toolkit CLI must be absolute")
    _pin(_read(cli), toolkit["cli_pin"], "toolkit CLI")
    files = toolkit["source_files"]
    if type(files) is not dict or not files:
        raise TrialError("toolkit sources missing")
    for relative, pin in files.items():
        path = _relative(relative)
        if path.parts[:2] != ("src", "specorganon") or path.suffix != ".py":
            raise TrialError("toolkit pin is not a source module")
        _pin(_read(repo / path), pin, relative)
    prompt = (
        "Return ONLY one JSON object with exactly three strings: analysis_py, draft_report_md, items_json. "
        "No tools, shell, filesystem inspection, subprocess, network, approvals, reviews or phase advance. "
        "Each string <=32 KiB; draft report <=1200 words. analysis_py is standard-library Python: "
        "one argument INPUT_DIRECTORY; read public inputs and sample_first_complete_week.csv; "
        "emit exactly one finite JSON object to stdout and write no files. "
        "The supervisor will inspect this exact proposal before one sealed offline replay. "
        "items_json is a JSON array; each item has exactly id,kind,text,refs,data; "
        "safe unique ids, refs only earlier ids, finite object data, at most eight items. "
        "Kinds: " + ",".join(KINDS) + ". No privileged data keys or commands. "
        "N/S can leave the array empty. Preserve all normative decisions as pending.\n"
    )
    for label, content in (("COMMON", blobs["prompts/common"]),
                           ("ASSIGNED ARM", blobs[f"prompts/{arm}"]),
                           ("PUBLIC task.md", blobs["input/task.md"]),
                           ("PUBLIC source_manifest.json", blobs["input/source_manifest.json"])):
        prompt += f"\n{label}\n" + content.decode("utf-8")
    blobs["first.prompt.txt"] = prompt.encode()
    for prefix, fields in (("first", tuple(OUTPUTS)), ("second", ("report_md",))):
        blobs[f"{prefix}.schema.json"] = (json.dumps(_schema(fields), sort_keys=True) + "\n").encode()
    return blobs


def _runtime(repo: Path, blobs: dict, arm: str, admission_root: str) -> dict:
    return {"schema": 1, "study_id": "D099", "arm": arm, "source_repo": str(repo),
            "protocol_path": str(PLAN.resolve(strict=True)), "protocol_sha256": PLAN_SHA,
            "model": "gpt-6-luna", "effort": "medium", "active_seconds": 360,
            "admission_root": admission_root,
            "fixed_files": {name: _record(raw) for name, raw in blobs.items()}, **CLAIMS}


def prepare(repo: Path, destination: Path, *, arm: str) -> dict:
    if arm not in {"N", "S", "T"}:
        raise TrialError("unknown arm")
    protocol, raw = _authority()
    repo = repo.resolve(strict=True)
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise TrialError("destination must be new")
    destination = destination.parent.resolve(strict=True) / destination.name
    protected = {repo, ROOT.resolve(strict=True), PLAN.parent.resolve(strict=True)}
    for category in ("sources", "prompts"):
        protected.update((repo / _relative(pin["path"])).parent.resolve(strict=True)
                         for pin in protocol[category].values())
    if any(destination == p or destination.is_relative_to(p) for p in protected):
        raise TrialError("destination must stay outside repository and frozen source trees")
    blobs = _blobs(repo, protocol, raw, arm)
    admission_root = str(Path(os.environ.get(ADMISSION_ENV,
        str(Path.home() / ".local/state/specorganon/subscription_method_admissions"))).absolute())
    destination.mkdir(mode=0o700)
    for name, content in blobs.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(content)
    for name in ("work", "first.preflight/work", "second.preflight/work"):
        (destination / name).mkdir(parents=True, mode=0o700)
    (destination / "run.lock").touch(mode=0o600)
    _atomic(destination / "plan.json", _runtime(repo, blobs, arm, admission_root))
    _atomic(destination / "run.json", {"schema": 1, "state": "prepared",
        "plan": _record(_read(destination / "plan.json")), "prepared_at_utc": _now(),
        "active_seconds_used": 0.0, "model_cli_invocations": 0, "generic_replays": 0,
        "artifacts": {}, "stages": {}, "error": None, "analysis_successful": False})
    return status(destination)


def _load(directory: Path) -> tuple[dict, dict]:
    for name in ("input", "work", "prompts", "first.preflight", "second.preflight"):
        if not stat.S_ISDIR((directory / name).lstat().st_mode):
            raise TrialError("prepared directory changed")
    state = _strict(_read(directory / "run.json"))
    raw = _read(directory / "plan.json")
    if state.get("plan") != _record(raw):
        raise TrialError("runtime plan changed")
    plan = _strict(raw)
    protocol, authority_raw = _authority()
    repo = Path(plan["source_repo"])
    if not repo.is_absolute() or repo.resolve(strict=True) != repo:
        raise TrialError("invalid source repository")
    arm = plan["arm"]
    if arm not in {"N", "S", "T"}:
        raise TrialError("invalid runtime arm")
    blobs = _blobs(repo, protocol, authority_raw, arm)
    if plan != _runtime(repo, blobs, arm, plan["admission_root"]):
        raise TrialError("runtime differs from fixed D099 authority")
    if state.get("state") not in STATES or type(state.get("artifacts")) is not dict:
        raise TrialError("invalid execution state")
    used = state.get("active_seconds_used")
    if (type(used) not in {int, float} or not math.isfinite(used) or used < 0
            or type(state.get("model_cli_invocations")) is not int
            or not 0 <= state["model_cli_invocations"] <= 2
            or type(state.get("generic_replays")) is not int
            or not 0 <= state["generic_replays"] <= 1):
        raise TrialError("invalid cumulative execution accounting")
    stages = state.get("stages")
    if type(stages) is not dict or not set(stages) <= {"generate", "feedback", "finalize"}:
        raise TrialError("invalid stage accounting")
    stage_sum = 0.0
    for name in ("generate", "feedback", "finalize"):
        if name not in stages:
            continue
        record = stages[name]
        if type(record) is not dict or record.get("active_seconds_before") != stage_sum:
            raise TrialError("incoherent stage budget history")
        if "ended_at_utc" in record:
            duration = record.get("active_seconds")
            if type(duration) not in {int, float} or not math.isfinite(duration) or duration < 0:
                raise TrialError("invalid stage elapsed duration")
            stage_sum += duration
    if not math.isclose(stage_sum, used, rel_tol=0, abs_tol=1e-9):
        raise TrialError("cumulative active budget differs from retained stage durations")
    for name in ("generate", "feedback", "finalize"):
        record = stages.get(name, {})
        if "ended_at_utc" not in record:
            continue
        captures = []
        if name in {"generate", "finalize"}:
            turn = state.get("first" if name == "generate" else "second", {})
            captures = [turn.get(key, {}) for key in ("authentication", "host", "model")]
        elif name == "feedback":
            captures = [state.get("replay", {})] + [item.get("capture", {})
                for item in state.get("toolkit_commands", [])]
        # Shared capture rounds milliseconds. Subtract one ms per capture before
        # comparing lower bounds to unrounded supervisor stage duration.
        lower_bound = 0.0
        for capture in captures:
            elapsed = capture.get("wall_seconds")
            if elapsed is None:
                continue
            if type(elapsed) not in {int, float} or not math.isfinite(elapsed) or elapsed < 0:
                raise TrialError("invalid captured elapsed duration")
            lower_bound += max(0.0, elapsed - 0.001)
        if record["active_seconds"] + 1e-9 < lower_bound:
            raise TrialError("stage duration is shorter than retained process durations")
    for name, content in blobs.items():
        if _record(_read(directory / name)) != _record(content):
            raise TrialError(f"fixed input changed: {name}")
    for name, pin in state["artifacts"].items():
        if name not in _artifact_names():
            raise TrialError("unknown retained artifact")
        if _artifact_record(directory / name) != pin:
            raise TrialError(f"retained artifact changed: {name}")
    return state, plan


def _artifact_names() -> tuple[str, ...]:
    names = [*OUTPUTS.values(), "second.report.md", "generic.stdout.json", "generic.stderr.txt",
             "metrics.json", "feedback.json", "second.prompt.txt", "case/organon.json"]
    for turn in ("first", "second"):
        names.extend(f"{turn}.{suffix}" for suffix in
                     ("proposal.json", "model.stdout.jsonl", "model.stderr.txt"))
        names.extend(f"{turn}.preflight/{name}" for name in ("host.stdout.txt", "host.stderr.txt"))
    names.extend(f"toolkit.{i:02d}.{suffix}" for i in range(12)
                 for suffix in ("stdout.json", "stderr.txt"))
    names.extend(f"case/{name}" for name in
                 ("task.md", "source_manifest.json", "sample_first_complete_week.csv"))
    return tuple(names)


def _trace(directory: Path, turn: str, model: str) -> dict:
    path = directory / f"{turn}.model.stdout.jsonl"
    allowed = {"thread.started", "turn.started", "item.started", "item.updated", "item.completed", "turn.completed"}
    for line in _read(path, 32 * 1024 * 1024).splitlines():
        event = _strict(line)
        kind = event.get("type")
        if type(kind) is not str or kind not in allowed or "error" in event:
            raise TrialError("observed error or unknown CLI event")
        if kind.startswith("item."):
            item = event.get("item")
            if (type(item) is not dict or type(item.get("type")) is not str
                    or item.get("type") not in {"reasoning", "agent_message"}):
                raise TrialError("observed tool or unknown CLI item")
            if "error" in item or item.get("status") in ("error", "failed"):
                raise TrialError("observed CLI item failure")
    usage = _parse_usage("codex", path, model)
    if (not usage["terminal_success"] or not usage["complete"]
            or usage["final_usage"]["input_tokens"] <= 0
            or usage["final_usage"]["output_tokens"] <= 0):
        raise TrialError("incomplete, incoherent or nonpositive local CLI usage")
    return usage


def _check_turn(directory: Path, state: dict, plan: dict, turn: str) -> None:
    required = {f"{turn}.{suffix}" for suffix in
                ("proposal.json", "model.stdout.jsonl", "model.stderr.txt")}
    required.update(f"{turn}.preflight/{name}" for name in ("host.stdout.txt", "host.stderr.txt"))
    required.update(OUTPUTS.values() if turn == "first" else ("second.report.md",))
    if not required <= set(state["artifacts"]):
        raise TrialError("turn lacks required retained artifacts")
    proposal = _proposal(_read(directory / f"{turn}.proposal.json", PROPOSAL_MAX), final=turn == "second")
    mapping = OUTPUTS if turn == "first" else {"report_md": "second.report.md"}
    for key, name in mapping.items():
        if _read(directory / name, COMPONENT_MAX) != proposal[key].encode():
            raise TrialError("retained proposal strings changed")
    records = state.get(turn, {})
    if records.get("usage") != _trace(directory, turn, plan["model"]):
        raise TrialError("stored usage differs from native CLI trace")
    for name in ("model", "host"):
        record = records.get(name, {})
        if record.get("exit_code") != 0 or record.get("timed_out") is not False or record.get("launch_error"):
            raise TrialError("turn lacks successful host/model capture")
        for stream, relative in (("stdout", f"{turn}.model.stdout.jsonl" if name == "model"
                                  else f"{turn}.preflight/host.stdout.txt"),
                                 ("stderr", f"{turn}.model.stderr.txt" if name == "model"
                                  else f"{turn}.preflight/host.stderr.txt")):
            capture_pin = record.get(stream, {})
            if {key: capture_pin.get(key) for key in ("sha256", "bytes")} != state["artifacts"][relative]:
                raise TrialError("capture stream pin differs from retained artifact")
    auth = records.get("authentication", {})
    if (auth.get("exit_code") != 0 or auth.get("chatgpt_login_reported") is not True
            or auth.get("api_key_login_reported") is not False or auth.get("raw_output_retained") is not False):
        raise TrialError("turn lacks subscription authentication classification")


def _feedback_document(directory: Path, state: dict, plan: dict) -> dict:
    commands = state.get("toolkit_commands", [])
    captures = [record.get("capture", {}) for record in commands]
    launched = [capture for capture in captures
                if capture and capture.get("launch_error") is None]
    successful = [capture for capture in launched
                  if capture.get("exit_code") == 0 and capture.get("timed_out") is False]
    document = {"schema": 1, "arm": plan["arm"], "reviewed_proposal_sha256":
                state["reviewed_proposal_sha256"], "review_scope": "entire raw proposal safety only",
                "generic": {**state["replay"], "analysis_successful": state["analysis_successful"],
                    "stdout": _read(directory / "generic.stdout.json", SANDBOX_LIMITS["file_bytes_per_file"]).decode("utf-8", errors="replace"),
                    "stderr": _read(directory / "generic.stderr.txt", SANDBOX_LIMITS["file_bytes_per_file"]).decode("utf-8", errors="replace")},
                "toolkit": {"attempted": bool(commands), "executed": bool(launched),
                    "successful_commands": len(successful),
                    "trace_created": (directory / "case/organon.json").is_file(), "commands": []}, **CLAIMS}
    for record in commands:
        document["toolkit"]["commands"].append({**record,
            "stdout": _read(directory / record["stdout_path"], SANDBOX_LIMITS["file_bytes_per_file"]).decode("utf-8", errors="replace"),
            "stderr": _read(directory / record["stderr_path"], SANDBOX_LIMITS["file_bytes_per_file"]).decode("utf-8", errors="replace")})
    if "toolkit_error" in state:
        document["toolkit"]["error"] = state["toolkit_error"]
    return document


def _second_prompt(directory: Path) -> bytes:
    return ("Return ONLY one JSON object with exactly one string report_md, <=32 KiB and <=1200 words. "
            "Produce the final report from the exact first prompt/proposal and unmodified supervisor feedback below. "
            "No new analysis, code, tools, repair or third call. Explain measured outputs and failures honestly. "
            "Normative approvals and completed phases remain zero. No field impact, global acceptance or method winner.\n"
            + "\nEXACT FIRST PROMPT\n" + _read(directory / "first.prompt.txt").decode()
            + "\nEXACT FIRST PROPOSAL\n" + _read(directory / "first.proposal.json", PROPOSAL_MAX).decode()
            + "\nUNMODIFIED SUPERVISOR FEEDBACK\n" + _read(directory / "feedback.json", 32 * 1024 * 1024).decode()).encode()


def _check_feedback(directory: Path, state: dict, plan: dict) -> None:
    required = {"generic.stdout.json", "generic.stderr.txt", "feedback.json", "second.prompt.txt"}
    if not required <= set(state["artifacts"]):
        raise TrialError("feedback lacks required artifact pins")
    if state.get("reviewed_proposal_sha256") != _record(_read(directory / "first.proposal.json", PROPOSAL_MAX))["sha256"]:
        raise TrialError("reviewed proposal SHA differs")
    script = _read(directory / "first.analysis.py", COMPONENT_MAX)
    payload_sha = _record(PACKAGING_PREFIX + script)["sha256"]
    replay = state.get("replay", {})
    if state.get("payload_sha256") != payload_sha or state.get("packaging_prefix") != PACKAGING_PREFIX.decode():
        raise TrialError("recorded sealed payload differs")
    if replay.get("executed") and replay.get("sealed_executable_sha256") not in {None, payload_sha}:
        raise TrialError("sealed executable SHA differs")
    if replay.get("executed") and (
            replay.get("read_roots") != [str(Path(state["admission"]["directory"]) / "input")]
            or replay.get("write_roots") != []
            or replay.get("backend") != "linux_landlock_seccomp_rlimit_sealed_memfd"):
        raise TrialError("replay record differs from fixed sandbox policy")
    if state["analysis_successful"]:
        if ("metrics.json" not in state["artifacts"] or replay.get("exit_code") != 0
                or replay.get("timed_out") is not False or replay.get("launch_error")
                or replay.get("sealed_executable_sha256") != payload_sha):
            raise TrialError("false successful analysis")
        raw = _read(directory / "generic.stdout.json", SANDBOX_LIMITS["file_bytes_per_file"])
        _strict(raw)
        if _read(directory / "metrics.json", SANDBOX_LIMITS["file_bytes_per_file"]) != raw:
            raise TrialError("metrics differs from exact replay stdout")
    if _strict(_read(directory / "feedback.json", 32 * 1024 * 1024)) != _feedback_document(directory, state, plan):
        raise TrialError("feedback differs from retained raw streams")
    if _read(directory / "second.prompt.txt", 32 * 1024 * 1024) != _second_prompt(directory):
        raise TrialError("second prompt differs from exact first turn and feedback")
    if plan["arm"] == "T":
        _check_toolkit(directory, state, plan)
    elif state.get("toolkit_commands") or (directory / "case").exists():
        raise TrialError("N/S must never execute toolkit")


def _check_toolkit(directory: Path, state: dict, plan: dict) -> None:
    items = _items(_read(directory / "first.items.json", COMPONENT_MAX))
    commands = state.get("toolkit_commands", [])
    if type(commands) is not list or not 1 <= len(commands) <= 12:
        raise TrialError("toolkit feedback lacks bounded command records")
    successful = []
    init_successful = False
    prior_order = -1
    recipe = _toolkit_recipe(Path(state["admission"]["directory"]), items)
    ordering = list(recipe)
    if commands[0].get("stage") != "init":
        raise TrialError("toolkit command sequence must start with init")
    for index, record in enumerate(commands):
        label = record.get("stage")
        if label not in recipe or ordering.index(label) <= prior_order or record.get("argv") != recipe[label]:
            raise TrialError("toolkit command differs from fixed ordered recipe")
        prior_order = ordering.index(label)
        if (record.get("stdout_path") != f"toolkit.{index:02d}.stdout.json"
                or record.get("stderr_path") != f"toolkit.{index:02d}.stderr.txt"
                or not {record["stdout_path"], record["stderr_path"]} <= set(state["artifacts"])
                or type(record.get("capture")) is not dict):
            raise TrialError("toolkit command lacks pinned streams/capture")
        capture = record["capture"]
        for stream in ("stdout", "stderr"):
            capture_pin = capture.get(stream, {})
            if {key: capture_pin.get(key) for key in ("sha256", "bytes")} != state["artifacts"][record[f"{stream}_path"]]:
                raise TrialError("toolkit capture pin differs from retained stream")
        if capture.get("exit_code") == 0 and not capture.get("timed_out") and not capture.get("launch_error"):
            response = _strict(_read(directory / record["stdout_path"], SANDBOX_LIMITS["file_bytes_per_file"]))
            if label == "init":
                init_successful = True
            if label.startswith("put:"):
                successful.append(label.removeprefix("put:"))
            if label == "status" and (response.get("project", {}).get("approval_policy") != "signed"
                        or response.get("approval_trust") != "unavailable"
                        or any(item.get("approved") for item in response.get("items", {}).values())
                        or any(phase.get("accepted") for phase in response.get("phases", {}).values())):
                raise TrialError("toolkit status claims approval or accepted phases")
    if not state.get("toolkit_error") and [record["stage"] for record in commands] != ordering:
        raise TrialError("successful toolkit feedback lacks complete fixed recipe")
    ledger = directory / "case/organon.json"
    if init_successful and (not ledger.exists() or "case/organon.json" not in state["artifacts"]):
        raise TrialError("successful toolkit init lacks retained actual ledger")
    if ledger.exists() and "case/organon.json" not in state["artifacts"]:
        raise TrialError("toolkit ledger lacks retained pin")
    if ledger.exists():
        data = _strict(_read(ledger))
        project = data.get("project", {})
        if (data.get("schema") != 1 or project.get("approval_policy") != "signed"
                or project.get("created_by") != ACTOR or project.get("title") != TITLE
                or project.get("domain") != DOMAIN or type(data.get("events")) is not list
                or len(data["events"]) != len(successful)):
            raise TrialError("toolkit ledger is not the signed initial item trace")
        prior = "0" * 64
        proposed = {item["id"]: item for item in items}
        for index, event in enumerate(data["events"], 1):
            item = proposed[successful[index - 1]]
            expected_payload = {"id": item["id"], "kind": item["kind"], "version": 1,
                "text": item["text"].strip(), "deps": {ref: 1 for ref in item["refs"]}, "data": item["data"]}
            canonical = json.dumps({k: v for k, v in event.items() if k != "hash"},
                ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            if (event.get("seq") != index or event.get("prev_hash") != prior
                    or event.get("actor") != ACTOR or event.get("kind") != "item_put"
                    or event.get("payload") != expected_payload
                    or event.get("hash") != hashlib.sha256(canonical).hexdigest()):
                raise TrialError("toolkit event differs from exact proposed pending item")
            prior = event["hash"]
        for name in ("task.md", "source_manifest.json", "sample_first_complete_week.csv"):
            if f"case/{name}" not in state["artifacts"] or _read(directory / f"case/{name}") != _read(directory / f"input/{name}"):
                raise TrialError("toolkit copied public input changed")


def status(directory: Path) -> dict:
    directory = directory.resolve(strict=True)
    state, plan = _load(directory)
    if state["state"] in {"awaiting_review", "feedback_started", "feedback_ready", "finalizing", "completed"}:
        _check_turn(directory, state, plan, "first")
    if state["state"] in {"feedback_ready", "finalizing", "completed"}:
        _check_feedback(directory, state, plan)
    if state["state"] == "completed":
        _check_turn(directory, state, plan, "second")
        if (state["model_cli_invocations"] != 2 or state["generic_replays"] != 1 or state["active_seconds_used"] >= 360
                or set(state["stages"]) != {"generate", "feedback", "finalize"}
                or any("ended_at_utc" not in entry for entry in state["stages"].values())):
            raise TrialError("completed state lacks bounded two-turn accounting")
    return {"state": state["state"], "completed": state["state"] == "completed",
            "analysis_successful": state["analysis_successful"], "run": state, "plan": plan,
            "generation_allowed": state["state"] == "prepared",
            "feedback_allowed": state["state"] == "awaiting_review",
            "finalize_allowed": state["state"] == "feedback_ready",
            "review_scope": "caller local safety declaration for entire proposal; no normative approval",
            "runtime_custody": "interpreter/runtime and same-UID state are unsealed caller authority",
            **CLAIMS}


@contextmanager
def _locked(directory: Path):
    fd = os.open(directory / "run.lock", os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise TrialError("invalid run lock")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _claim_target(plan: dict) -> Path:
    root = Path(plan["admission_root"])
    if not root.is_absolute():
        raise TrialError("invalid admission root")
    return root / f'{PLAN_SHA}-{plan["arm"]}.json'


def _claim(directory: Path, plan: dict) -> dict:
    target = _claim_target(plan)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    claim = {"protocol_sha256": PLAN_SHA, "arm": plan["arm"], "directory": str(directory),
             "claimed_at_utc": _now(), "scope": "cooperating callers sharing one local admission root"}
    try:
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise TrialError("protocol arm already claimed; no second destination") from None
    with os.fdopen(fd, "w") as stream:
        json.dump(claim, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return claim


def _bound_admission(directory: Path, state: dict, plan: dict) -> None:
    claim = _strict(_read(_claim_target(plan), 8192))
    if (claim != state.get("admission") or claim.get("directory") != str(directory)
            or claim.get("arm") != plan["arm"] or claim.get("protocol_sha256") != PLAN_SHA):
        raise TrialError("mutation requires canonical admitted directory; copied attempt forbidden")


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TrialError("cumulative active deadline exhausted")
    return remaining


@contextmanager
def _stage(directory: Path, state: dict, plan: dict, stage: str, executing_state: str):
    if stage in state["stages"]:
        raise TrialError("stage already started; repeat forbidden")
    started = time.monotonic()
    deadline = started + max(0.0, 360 - state["active_seconds_used"])
    state.update(state=executing_state, current_stage=stage)
    state["stages"][stage] = {"started_at_utc": _now(), "active_seconds_before": state["active_seconds_used"]}
    _atomic(directory / "run.json", state)
    try:
        _remaining(deadline)
        yield deadline
    except (TrialError, CheckpointError, RunError, SandboxError, SandboxUnavailable, OSError, ValueError,
            RecursionError, subprocess.SubprocessError) as exc:
        state.update(state="failed", error=f"{type(exc).__name__}: {exc}")
    finally:
        for name in _artifact_names():
            path = directory / name
            if path.exists() or path.is_symlink():
                try:
                    if not stat.S_ISREG(path.lstat().st_mode):
                        raise TrialError("artifact is not regular")
                    with path.open("rb") as stream:
                        os.fsync(stream.fileno())
                    pin = _artifact_record(path)
                    if name in state["artifacts"] and state["artifacts"][name] != pin:
                        raise TrialError("retained artifact changed during stage")
                    state["artifacts"][name] = pin
                except (CheckpointError, TrialError, OSError) as exc:
                    state.update(state="failed", error=f"artifact persistence failed: {type(exc).__name__}")
        elapsed = time.monotonic() - started
        state["active_seconds_used"] += elapsed
        state["stages"][stage].update(ended_at_utc=_now(), active_seconds=elapsed)
        if time.monotonic() >= deadline:
            state.update(state="failed", truncated=True, error="cumulative active deadline exhausted")
        _atomic(directory / "run.json", state)


def _model(directory: Path, state: dict, plan: dict, turn: str, deadline: float) -> dict:
    _remaining(deadline)
    if state["model_cli_invocations"] >= 2:
        raise TrialError("two CLI invocations exhausted")
    env = _environment()
    cli = shutil.which("codex", path=env.get("PATH"))
    if not cli:
        raise TrialError("codex CLI unavailable")
    record = state.setdefault(turn, {})
    auth_started = time.monotonic()
    record["authentication"] = _auth(cli, env, deadline)
    record["authentication"]["wall_seconds"] = time.monotonic() - auth_started
    record["host"] = _host_preflight(cli, directory / f"{turn}.preflight", env, deadline)
    argv = [cli, "exec", "--json", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check",
            "-C", str(directory / "work"), "-s", "read-only", "-m", plan["model"],
            "-c", f'model_reasoning_effort="{plan["effort"]}"', "-c", 'web_search="disabled"',
            "--enable", "code_mode_host"]
    for feature in _disabled_features("D096"):
        argv += ["--disable", feature]
    argv += ["--output-schema", str(directory / f"{turn}.schema.json"), "-o",
             str(directory / f"{turn}.proposal.json"), "-"]
    record["argv"] = argv
    state["model_cli_invocations"] += 1
    _atomic(directory / "run.json", state)
    record["model"] = _capture(argv, cwd=directory / "work", env=env,
        timeout_seconds=_remaining(deadline), active_deadline=deadline,
        stdin_text=_read(directory / f"{turn}.prompt.txt", 32 * 1024 * 1024).decode(),
        stdout_path=directory / f"{turn}.model.stdout.jsonl",
        stderr_path=directory / f"{turn}.model.stderr.txt", stage=turn)
    if record["model"]["exit_code"] != 0 or record["model"]["timed_out"] or record["model"]["launch_error"]:
        raise TrialError("CLI failed or exceeded cumulative active deadline")
    record["usage"] = _trace(directory, turn, plan["model"])
    proposal = _proposal(_read(directory / f"{turn}.proposal.json", PROPOSAL_MAX), final=turn == "second")
    for key, name in (OUTPUTS if turn == "first" else {"report_md": "second.report.md"}).items():
        (directory / name).write_bytes(proposal[key].encode())
    _remaining(deadline)
    return proposal


def generate(directory: Path) -> dict:
    directory = directory.resolve(strict=True)
    with _locked(directory):
        state, plan = _load(directory)
        if state["state"] != "prepared":
            raise TrialError("generation already started; repeat forbidden")
        with _stage(directory, state, plan, "generate", "generating") as deadline:
            state["admission"] = _claim(directory, plan)
            _atomic(directory / "run.json", state)
            _model(directory, state, plan, "first", deadline)
            state["state"] = "awaiting_review"
    return status(directory)


def feedback(directory: Path, *, reviewed_proposal_sha: str) -> dict:
    directory = directory.resolve(strict=True)
    with _locked(directory):
        verified = status(directory)
        state, plan = verified["run"], verified["plan"]
        if state["state"] != "awaiting_review":
            raise TrialError("feedback already started or unavailable; repeat forbidden")
        _bound_admission(directory, state, plan)
        sha = _record(_read(directory / "first.proposal.json", PROPOSAL_MAX))["sha256"]
        if type(reviewed_proposal_sha) is not str or not re.fullmatch(r"[0-9a-f]{64}", reviewed_proposal_sha) or sha != reviewed_proposal_sha:
            raise TrialError("reviewed proposal SHA differs from entire raw first proposal")
        with _stage(directory, state, plan, "feedback", "feedback_started") as deadline:
            state["reviewed_proposal_sha256"] = sha
            items = _items(_read(directory / "first.items.json", COMPONENT_MAX))
            _replay(directory, state, deadline)
            if plan["arm"] == "T":
                _toolkit(directory, state, plan, items, deadline)
            _remaining(deadline)
            _atomic(directory / "feedback.json", _feedback_document(directory, state, plan))
            (directory / "second.prompt.txt").write_bytes(_second_prompt(directory))
            state["state"] = "feedback_ready"
    return status(directory)


def finalize(directory: Path) -> dict:
    directory = directory.resolve(strict=True)
    with _locked(directory):
        verified = status(directory)
        state, plan = verified["run"], verified["plan"]
        if state["state"] != "feedback_ready":
            raise TrialError("finalization already started or unavailable; repeat forbidden")
        _bound_admission(directory, state, plan)
        with _stage(directory, state, plan, "finalize", "finalizing") as deadline:
            _model(directory, state, plan, "second", deadline)
            state["state"] = "completed"
    return status(directory)


def _replay(directory: Path, state: dict, deadline: float) -> None:
    if state["generic_replays"] != 0:
        raise TrialError("generic replay already reserved; no repair/replay")
    script = _read(directory / "first.analysis.py", COMPONENT_MAX)
    payload = PACKAGING_PREFIX + script
    payload_sha = _record(payload)["sha256"]
    interpreter = PACKAGING_INTERPRETER.resolve(strict=True)
    runtime_roots = tuple(dict.fromkeys((*default_python_runtime_roots(), interpreter)))
    state.update(payload_sha256=payload_sha, packaging_prefix=PACKAGING_PREFIX.decode(),
        generic_replays=1, runtime_interpreter={"path": str(interpreter),
            **_artifact_record(interpreter), "sealed": False}, runtime_roots=list(map(str, runtime_roots)))
    _atomic(directory / "run.json", state)
    stdout = directory / "generic.stdout.json"
    stderr = directory / "generic.stderr.txt"
    timeout = min(SANDBOX_LIMITS["wall_seconds"], _remaining(deadline))
    try:
        result = run_sandboxed(argv=[str(directory / "launch.py"), str(directory / "input")],
            cwd=directory / "work", read_roots=[directory / "input"], write_roots=[],
            runtime_roots=runtime_roots, stdout_path=stdout, stderr_path=stderr,
            timeout_seconds=timeout, cpu_seconds=SANDBOX_LIMITS["cpu_seconds"],
            address_space_bytes=SANDBOX_LIMITS["address_space_bytes"],
            file_bytes_per_file=SANDBOX_LIMITS["file_bytes_per_file"],
            sealed_executable_bytes=payload, sealed_executable_sha256=payload_sha)
    except (SandboxError, SandboxUnavailable, OSError, ValueError) as exc:
        state["replay"] = {"executed": False, "exit_code": None, "timed_out": False,
            "launch_error": f"{type(exc).__name__}: {exc}", "timeout_seconds": timeout,
            "sealed_executable_sha256": None}
        for path in (stdout, stderr):
            if not path.exists():
                path.write_bytes(b"")
        return
    state["replay"] = {**asdict(result), "executed": True, "timeout_seconds": timeout,
                       "read_roots": [str(directory / "input")], "write_roots": [],
                       "backend": "linux_landlock_seccomp_rlimit_sealed_memfd"}
    if result.sealed_executable_sha256 not in {None, payload_sha}:
        raise TrialError("sealed replay SHA differs from exact reviewed payload")
    if result.exit_code == 0 and not result.timed_out and not result.launch_error:
        try:
            raw = _read(stdout, SANDBOX_LIMITS["file_bytes_per_file"])
            _strict(raw)
        except (CheckpointError, TrialError, ValueError, RecursionError) as exc:
            state["replay"]["output_error"] = f"{type(exc).__name__}: {exc}"
        else:
            if result.sealed_executable_sha256 != payload_sha:
                raise TrialError("successful replay lacks sealed executable digest")
            (directory / "metrics.json").write_bytes(raw)
            state["analysis_successful"] = True


def _toolkit_recipe(directory: Path, items: list[dict]) -> dict[str, list[str]]:
    cli = _authority()[0]["toolkit"]["cli_path"]
    case = str(directory / "case")
    recipe = {"init": [cli, "init", case, "--title", TITLE, "--domain", DOMAIN,
                        "--actor", ACTOR, "--approval-policy", "signed"]}
    for item in items:
        argv = [cli, "put", case, item["id"], "--kind", item["kind"], f'--text={item["text"]}',
                "--actor", ACTOR, "--data", json.dumps(item["data"], ensure_ascii=False, sort_keys=True, allow_nan=False),
                "--expected-version", "0"]
        for ref in item["refs"]:
            argv += ["--ref", ref]
        argv += ["--expected-deps", json.dumps({ref: 1 for ref in item["refs"]}, sort_keys=True)]
        recipe[f'put:{item["id"]}'] = argv
    recipe.update(status=[cli, "status", case], **{
        "gate:frame": [cli, "gate", case, "frame"], "gate:critique": [cli, "gate", case, "critique"]})
    return recipe


def _toolkit(directory: Path, state: dict, plan: dict, items: list[dict], deadline: float) -> None:
    if plan["arm"] != "T":
        raise TrialError("only T may execute toolkit")
    case = directory / "case"
    if case.exists() or case.is_symlink():
        raise TrialError("toolkit case must be new")
    # Discard caller ORGANON_*, API credentials, Python injection and private HOME.
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
           "HOME": str(directory / "work"), "TMPDIR": str(directory / "work"),
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}
    state["toolkit_commands"] = []
    failed_put = False
    for label, argv in _toolkit_recipe(directory, items).items():
        if failed_put and label.startswith("put:"):
            continue
        _remaining(deadline)
        index = len(state["toolkit_commands"])
        entry = {"stage": label, "argv": argv, "started_at_utc": _now(),
                 "stdout_path": f"toolkit.{index:02d}.stdout.json",
                 "stderr_path": f"toolkit.{index:02d}.stderr.txt"}
        state["toolkit_commands"].append(entry)
        _atomic(directory / "run.json", state)
        entry["capture"] = _capture(argv, cwd=directory / "work", env=env,
            timeout_seconds=min(30.0, _remaining(deadline)), active_deadline=deadline,
            stdout_path=directory / entry["stdout_path"], stderr_path=directory / entry["stderr_path"],
            stage=f"toolkit:{label}")
        capture = entry["capture"]
        _atomic(directory / "run.json", state)
        if capture["exit_code"] != 0 or capture["timed_out"] or capture["launch_error"]:
            state["toolkit_error"] = f"actual toolkit command failed: {label}"
            if label == "init":
                return
            if label.startswith("put:"):
                failed_put = True
        elif label == "init":
            for name in ("task.md", "source_manifest.json", "sample_first_complete_week.csv"):
                (case / name).write_bytes(_read(directory / f"input/{name}"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("repo", type=Path)
    p.add_argument("directory", type=Path)
    p.add_argument("--arm", choices=("N", "S", "T"), required=True)
    for name in ("generate", "finalize", "status"):
        commands.add_parser(name).add_argument("directory", type=Path)
    p = commands.add_parser("feedback")
    p.add_argument("directory", type=Path)
    p.add_argument("--reviewed-proposal-sha", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.repo, args.directory, arm=args.arm)
        elif args.command == "feedback":
            result = feedback(args.directory, reviewed_proposal_sha=args.reviewed_proposal_sha)
        else:
            result = globals()[args.command](args.directory)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1 if result["state"] == "failed" else 0
    except (TrialError, CheckpointError, OSError, ValueError, RecursionError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
