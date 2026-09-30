"""One-use D097 development continuation: generate, locally review, baseline replay."""
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_prototype_checkpoint as checkpoint  # noqa: E402
from local_replay_sandbox import (  # noqa: E402
    SandboxError, SandboxUnavailable, default_python_runtime_roots, run_sandboxed,
)
from run_development_arm import RunError, _capture, _parse_usage  # noqa: E402
from run_prototype_checkpoint import (  # noqa: E402
    CheckpointError, LIMITS, _artifact_record, _atomic, _auth, _claim,
    _disabled_features, _environment, _host_preflight, _json, _now, _read, _record,
)

PLAN = ROOT / "experiments/development/bread_continuation_2026-09-30/plan.json"
PLAN_SHA = "fca4a7dc7587782541402710a83d07f81724432fa0f4a6eec631ff529906b0a2"
ADMISSION_ENV = "SPECORGANON_CHECKPOINT_ADMISSION_ROOT"
PACKAGING_PREFIX = b"#!/usr/bin/python3.12 -I\n"
PACKAGING_INTERPRETER = Path("/usr/bin/python3.12")
PROPOSAL_MAX = 96 * 1024
COMPONENT_MAX = 32 * 1024
SANDBOX_LIMITS = {"timeout_seconds": 30, "cpu_seconds": 10,
                  "address_space_bytes": 512 * 1024 * 1024,
                  "file_bytes_per_file": 2 * 1024 * 1024}
OUTPUTS = {"analysis_py": "analysis.py", "sources_json": "sources.json", "report_md": "report.md"}
GENERATED_ARTIFACTS = ("host.stdout.txt", "host.stderr.txt", "model.stdout.jsonl",
                       "model.stderr.txt", "proposal.json", *OUTPUTS.values())
REPLAY_ARTIFACTS = ("baseline.stdout.json", "baseline.stderr.txt", "metrics.json")
ARTIFACTS = (*GENERATED_ARTIFACTS, *REPLAY_ARTIFACTS)
STATES = {"prepared", "started", "awaiting_review", "replaying", "replayed", "failed"}


class ContinuationError(ValueError):
    pass


def _strict_json(raw: bytes) -> dict:
    value = _json(raw)

    def finite(item):
        if type(item) is float and not math.isfinite(item):
            raise ContinuationError("nonfinite JSON number")
        if type(item) is dict:
            for child in item.values():
                finite(child)
        elif type(item) is list:
            for child in item:
                finite(child)
    finite(value)
    return value


def _relative(value: str) -> Path:
    if type(value) is not str or not value:
        raise ContinuationError("invalid registered relative path")
    path = Path(value)
    if path.is_absolute() or any(part in {".", ".."} for part in value.split("/")):
        raise ContinuationError("invalid registered relative path")
    return path


def _pin(raw: bytes, pin: dict, label: str) -> None:
    if type(pin) is not dict or _record(raw) != {key: pin.get(key) for key in ("sha256", "bytes")}:
        raise ContinuationError(f"registered bytes changed: {label}")


def _authority() -> tuple[dict, bytes]:
    raw = _read(PLAN)
    if _record(raw)["sha256"] != PLAN_SHA:
        raise ContinuationError("fixed prospective D097 plan changed")
    plan = _strict_json(raw)
    if (plan.get("attempts") != 1 or plan.get("provider_cli") != "codex"
            or (plan.get("requested_model"), plan.get("requested_effort"), plan.get("active_seconds"))
            != ("gpt-6-luna", "medium", 240)
            or plan.get("generation_schema_fields") != list(OUTPUTS)
            or plan.get("payload_prefix") != PACKAGING_PREFIX.decode("ascii")
            or plan.get("replay") != {
                "wall_seconds": SANDBOX_LIMITS["timeout_seconds"],
                "cpu_seconds": SANDBOX_LIMITS["cpu_seconds"],
                "address_space_bytes": SANDBOX_LIMITS["address_space_bytes"],
                "file_bytes_per_file": SANDBOX_LIMITS["file_bytes_per_file"],
                "write_roots": [], "requires_exact_reviewed_script_sha": True,
                "model_generated_code_automatically_executed": False}):
        raise ContinuationError("invalid fixed D097 configuration")
    return plan, raw


def _schema() -> dict:
    return {"type": "object", "additionalProperties": False,
            "required": list(OUTPUTS),
            "properties": {key: {"type": "string"} for key in OUTPUTS}}


def _proposal(raw: bytes) -> dict:
    if len(raw) > PROPOSAL_MAX:
        raise ContinuationError("proposal exceeds 96 KiB")
    proposal = _strict_json(raw)
    if set(proposal) != set(OUTPUTS) or any(type(value) is not str for value in proposal.values()):
        raise ContinuationError("proposal requires exactly three string fields")
    encoded = {key: value.encode("utf-8") for key, value in proposal.items()}
    if sum(map(len, encoded.values())) > PROPOSAL_MAX:
        raise ContinuationError("proposal components exceed 96 KiB")
    if any(len(encoded[key]) > COMPONENT_MAX for key in ("analysis_py", "sources_json")):
        raise ContinuationError("analysis or sources exceeds 32 KiB")
    if len(proposal["report_md"].split()) > 1200:
        raise ContinuationError("report exceeds 1200 words")
    _strict_json(encoded["sources_json"])
    return proposal


def _parent(repo: Path, protocol: dict) -> tuple[dict[str, bytes], dict]:
    parent = protocol["parent_checkpoint"]
    directory = repo / _relative(parent["directory"])
    verified = checkpoint.status(directory)
    if (not verified["checkpoint_verified"] or verified["state"] != "checkpoint_ready"
            or verified["plan"].get("study_id") != "D096"):
        raise ContinuationError("parent is not the intact D096 initial checkpoint")
    blobs = {}
    for kind, name in (("receipt", "parent_receipt.json"),
                       ("case", "prototype_case.json"), ("state", "parent_state.json")):
        pin = parent[kind]
        path = repo / _relative(pin["path"])
        if kind in {"case", "state"} and path.resolve(strict=True) != (
                directory / ("prototype_case.json" if kind == "case" else "state.json")).resolve(strict=True):
            raise ContinuationError("parent file differs from fixed checkpoint")
        raw = _read(path)
        _pin(raw, pin, name)
        blobs[f"input/{name}"] = raw
    return blobs, verified


def _prompt(blobs: dict[str, bytes], protocol: dict) -> bytes:
    prompt = (
        "Return ONLY one JSON object with exactly three strings: analysis_py, sources_json, report_md. "
        "Use no tools, file inspection, web access, subprocess or network. Produce a Python analysis "
        "using only the standard library. Its sole argument is the public input directory; emit one "
        "finite JSON object to stdout for the baseline, without writing files. The analysis will be "
        "reviewed locally before one restricted replay. sources_json must itself be a strict JSON object "
        "with source provenance. Preserve uncertainty and pending normative decisions; do not approve "
        "decisions or claim phases, field impact or validation were completed. analysis_py and "
        "sources_json each have a 32 KiB limit; report_md has a 1200-word limit.\n"
    )
    prompt += "\nORIGINAL PUBLIC TASK\n" + blobs["input/task.md"].decode("utf-8")
    prompt += "\nREGISTERED CONTINUATION ADDENDUM\n" + protocol["prompt_addendum"]
    for name in ("prototype_case.json", "parent_state.json", *protocol["prompt_source_order"]):
        if name == "task.md":
            continue
        prompt += f"\nPUBLIC {name}\n" + blobs[f"input/{name}"].decode("utf-8")
    return prompt.encode("utf-8")


def _blobs(repo: Path, protocol: dict, protocol_raw: bytes) -> dict[str, bytes]:
    blobs, _ = _parent(repo, protocol)
    sources = protocol["source_files"]
    if type(sources) is not dict or len(sources) != 9:
        raise ContinuationError("expected six original sources and three text packet files")
    expected = set(checkpoint.SOURCES) | {"source_lca.txt", "source_survey.txt", "text_manifest.json"}
    if set(sources) != expected:
        raise ContinuationError("registered public source names differ")
    for name, pin in sources.items():
        raw = _read(repo / _relative(pin["path"]))
        _pin(raw, pin, name)
        blobs[f"input/{name}"] = raw
    order = protocol["prompt_source_order"]
    if (type(order) is not list or len(order) != len(set(order))
            or set(order) != expected - {"source_lca.pdf", "source_survey.pdf"}
            or type(protocol.get("prompt_addendum")) is not str):
        raise ContinuationError("invalid frozen public prompt packet")
    blobs["protocol.json"] = protocol_raw
    blobs["prompt.txt"] = _prompt(blobs, protocol)
    blobs["schema.json"] = (json.dumps(_schema(), sort_keys=True, indent=2) + "\n").encode("utf-8")
    return blobs


def _runtime_plan(repo: Path, blobs: dict[str, bytes], admission_root: str) -> dict:
    return {"schema": 1, "study_id": "D097", "source_repo": str(repo),
            "protocol_path": str(PLAN.resolve(strict=True)), "protocol_sha256": PLAN_SHA,
            "model": "gpt-6-luna", "effort": "medium", "active_seconds": 240,
            "admission_root": admission_root,
            "fixed_files": {name: _record(raw) for name, raw in blobs.items()},
            "sandbox_limits": SANDBOX_LIMITS, "packaging_prefix": PACKAGING_PREFIX.decode("ascii"),
            **LIMITS}


def _destination(repo: Path, protocol: dict, destination: Path) -> Path:
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ContinuationError("destination must be new")
    # Resolve the real existing parent before creating anything. An external
    # spelling through a symlink must not introduce a stage into a frozen tree.
    destination = destination.parent.resolve(strict=True) / destination.name
    protected = {repo, ROOT.resolve(strict=True), PLAN.parent.resolve(strict=True),
                 (repo / _relative(protocol["parent_checkpoint"]["directory"])).resolve(strict=True)}
    protected.update((repo / _relative(pin["path"])).parent.resolve(strict=True)
                     for pin in protocol["source_files"].values())
    protected.update((repo / _relative(protocol["parent_checkpoint"][kind]["path"])).parent.resolve(strict=True)
                     for kind in ("receipt", "case", "state"))
    if any(destination == root or destination.is_relative_to(root) for root in protected):
        raise ContinuationError("destination must stay outside the repository and protected source/checkpoint trees")
    return destination


def prepare(repo: Path, destination: Path) -> dict:
    protocol, protocol_raw = _authority()
    repo = repo.resolve(strict=True)
    destination = _destination(repo, protocol, destination)
    blobs = _blobs(repo, protocol, protocol_raw)
    admission_root = str(Path(os.environ.get(ADMISSION_ENV,
        str(Path.home() / ".local/state/specorganon/prototype_checkpoint_admissions"))).absolute())
    destination.mkdir(mode=0o700)
    for name, raw in blobs.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(raw)
    (destination / "work").mkdir(mode=0o700)
    (destination / "run.lock").touch(mode=0o600)
    _atomic(destination / "plan.json", _runtime_plan(repo, blobs, admission_root))
    _atomic(destination / "run.json", {
        "schema": 1, "state": "prepared", "prepared_at_utc": _now(),
        "plan": _record(_read(destination / "plan.json")), "artifacts": {}, "error": None})
    return status(destination)


def _trace(directory: Path, model: str) -> dict:
    raw = _read(directory / "model.stdout.jsonl", 32 * 1024 * 1024)
    for line in raw.splitlines():
        event = _strict_json(line)
        kind = event.get("type")
        if type(kind) is not str:
            raise ContinuationError("missing CLI event type")
        if kind.startswith("item."):
            item = event.get("item")
            if type(item) is not dict or item.get("type") not in {"reasoning", "agent_message"}:
                raise ContinuationError("observed tool or unknown item")
    usage = _parse_usage("codex", directory / "model.stdout.jsonl", model)
    if not usage["terminal_success"] or not usage["complete"]:
        raise ContinuationError("incomplete or incoherent local CLI turn/usage")
    if usage["final_usage"]["input_tokens"] <= 0 or usage["final_usage"]["output_tokens"] <= 0:
        raise ContinuationError("generation requires positive input/output token usage")
    return usage


def _load(directory: Path) -> tuple[dict, dict]:
    for name in ("input", "work"):
        if not stat.S_ISDIR((directory / name).lstat().st_mode):
            raise ContinuationError("prepared directory changed")
    state = _strict_json(_read(directory / "run.json"))
    plan_raw = _read(directory / "plan.json")
    if state.get("plan") != _record(plan_raw):
        raise ContinuationError("runtime plan changed")
    plan = _strict_json(plan_raw)
    protocol, protocol_raw = _authority()
    if (plan.get("protocol_path") != str(PLAN.resolve(strict=True))
            or plan.get("protocol_sha256") != PLAN_SHA):
        raise ContinuationError("runtime plan differs from fixed D097 authority")
    if type(plan.get("source_repo")) is not str:
        raise ContinuationError("invalid source repository")
    repo = Path(plan["source_repo"])
    if not repo.is_absolute() or str(repo.resolve(strict=True)) != str(repo):
        raise ContinuationError("invalid source repository")
    if type(plan.get("admission_root")) is not str or not Path(plan["admission_root"]).is_absolute():
        raise ContinuationError("invalid local admission root")
    blobs = _blobs(repo, protocol, protocol_raw)
    if plan != _runtime_plan(repo, blobs, plan["admission_root"]):
        raise ContinuationError("runtime configuration or input pins differ from fixed plan")
    if state.get("state") not in STATES or type(state.get("artifacts")) is not dict:
        raise ContinuationError("invalid continuation state")
    for name, expected_raw in blobs.items():
        if _record(_read(directory / name)) != _record(expected_raw):
            raise ContinuationError(f"fixed input changed: {name}")
    for name, pin in state["artifacts"].items():
        if name not in ARTIFACTS or _artifact_record(directory / name) != pin:
            raise ContinuationError(f"continuation artifact changed: {name}")
    return state, plan


def _check_generation(directory: Path, state: dict, plan: dict) -> None:
    if not all(name in state["artifacts"] for name in GENERATED_ARTIFACTS):
        raise ContinuationError("generation lacks required artifact pins")
    proposal = _proposal(_read(directory / "proposal.json", PROPOSAL_MAX))
    for key, name in OUTPUTS.items():
        if _read(directory / name, PROPOSAL_MAX) != proposal[key].encode("utf-8"):
            raise ContinuationError("model proposal strings changed")
    if state.get("usage") != _trace(directory, plan["model"]):
        raise ContinuationError("stored usage differs from CLI trace")
    for key in ("model", "host"):
        capture = state.get(key, {})
        if capture.get("exit_code") != 0 or capture.get("timed_out") is not False or capture.get("launch_error"):
            raise ContinuationError("generation lacks successful local preflight and capture")
    auth = state.get("authentication", {})
    if (auth.get("exit_code") != 0 or auth.get("chatgpt_login_reported") is not True
            or auth.get("api_key_login_reported") is not False or auth.get("raw_output_retained") is not False):
        raise ContinuationError("generation lacks subscription authentication classification")


def _check_replay(directory: Path, state: dict) -> None:
    if not all(name in state["artifacts"] for name in REPLAY_ARTIFACTS):
        raise ContinuationError("baseline lacks required artifact pins")
    script = _read(directory / "analysis.py", COMPONENT_MAX)
    payload_sha = _record(PACKAGING_PREFIX + script)["sha256"]
    replay = state.get("replay", {})
    if (state.get("reviewed_script_sha256") != _record(script)["sha256"]
            or state.get("payload_sha256") != payload_sha
            or state.get("packaging_prefix") != PACKAGING_PREFIX.decode("ascii")
            or replay.get("sealed_executable_sha256") != payload_sha
            or replay.get("exit_code") != 0 or replay.get("timed_out") is not False
            or replay.get("launch_error") is not None):
        raise ContinuationError("invalid sealed baseline replay record")
    raw = _read(directory / "baseline.stdout.json", SANDBOX_LIMITS["file_bytes_per_file"])
    _strict_json(raw)
    if _read(directory / "metrics.json", SANDBOX_LIMITS["file_bytes_per_file"]) != raw:
        raise ContinuationError("baseline metrics differ from raw stdout")


def status(directory: Path) -> dict:
    directory = directory.resolve(strict=True)
    state, plan = _load(directory)
    generated = state["state"] in {"awaiting_review", "replaying", "replayed"} or state.get("stage") == "replay"
    if generated:
        _check_generation(directory, state, plan)
    if state["state"] == "replayed":
        _check_replay(directory, state)
    return {"state": state["state"], "generation_verified": generated,
            "baseline_verified": state["state"] == "replayed",
            "generation_allowed": state["state"] == "prepared",
            "replay_allowed": state["state"] == "awaiting_review",
            "relaunch_allowed": False, "run": state, "plan": plan,
            "approved_normative_decisions": 0, "completed_phases": 0,
            "review_scope": "caller declaration for this local baseline; no custody or normative approval",
            **LIMITS}


def _persist(directory: Path, state: dict, started: float, *, deadline: float | None = None) -> None:
    for name in ARTIFACTS:
        path = directory / name
        if path.exists() or path.is_symlink():
            try:
                if not stat.S_ISREG(path.lstat().st_mode):
                    raise ContinuationError("artifact is not regular")
                with path.open("rb") as stream:
                    os.fsync(stream.fileno())
                pin = _artifact_record(path)
                if name in state["artifacts"] and state["artifacts"][name] != pin:
                    raise ContinuationError("retained artifact changed during replay")
                state["artifacts"][name] = pin
            except (CheckpointError, ContinuationError, OSError) as exc:
                state.update(state="failed", error=f"artifact persistence failed: {type(exc).__name__}")
                state.setdefault("unavailable_artifacts", []).append(name)
    if state["state"] == "awaiting_review" and deadline is not None and time.monotonic() >= deadline:
        state.update(state="failed", error="deadline exhausted before durable publication")
    ended = _now()
    elapsed = round(time.monotonic() - started, 3)
    stage = "replay" if state.get("stage") == "replay" else "generation"
    state.update(ended_at_utc=ended, observed_wall_seconds=elapsed)
    state[f"{stage}_ended_at_utc"] = ended
    state[f"{stage}_observed_wall_seconds"] = elapsed
    _atomic(directory / "run.json", state)


def generate(directory: Path) -> dict:
    directory = directory.resolve(strict=True)
    with (directory / "run.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state, plan = _load(directory)
        if state["state"] != "prepared":
            raise ContinuationError("generation already started; relaunch forbidden")
        started = time.monotonic()
        deadline = started + plan["active_seconds"]
        state.update(state="started", stage="generate", started_at_utc=_now())
        _atomic(directory / "run.json", state)
        try:
            state["admission"] = _claim(directory, plan)
            env = _environment()
            cli = shutil.which("codex", path=env.get("PATH"))
            if not cli:
                raise ContinuationError("codex CLI unavailable")
            state["authentication"] = _auth(cli, env, deadline)
            state["host"] = _host_preflight(cli, directory, env, deadline)
            argv = [cli, "exec", "--json", "--ephemeral", "--ignore-user-config",
                    "--skip-git-repo-check", "-C", str(directory / "work"), "-s", "read-only",
                    "-m", plan["model"], "-c", f'model_reasoning_effort="{plan["effort"]}"',
                    "-c", 'web_search="disabled"', "--enable", "code_mode_host"]
            for feature in _disabled_features("D096"):
                argv += ["--disable", feature]
            argv += ["--output-schema", str(directory / "schema.json"), "-o",
                     str(directory / "proposal.json"), "-"]
            state["argv"] = argv
            state["model"] = _capture(
                argv, cwd=directory / "work", timeout_seconds=plan["active_seconds"],
                active_deadline=deadline, stdin_text=_read(directory / "prompt.txt").decode("utf-8"),
                stdout_path=directory / "model.stdout.jsonl", stderr_path=directory / "model.stderr.txt",
                env=env, stage="model")
            if state["model"]["exit_code"] != 0 or state["model"]["timed_out"]:
                raise ContinuationError("CLI failed or exceeded local active deadline")
            state["usage"] = _trace(directory, plan["model"])
            proposal = _proposal(_read(directory / "proposal.json", PROPOSAL_MAX))
            if time.monotonic() >= deadline:
                raise ContinuationError("deadline exhausted before proposal publication")
            for key, name in OUTPUTS.items():
                (directory / name).write_bytes(proposal[key].encode("utf-8"))
            state["state"] = "awaiting_review"
        except (CheckpointError, ContinuationError, RunError, OSError, ValueError,
                RecursionError, subprocess.SubprocessError) as exc:
            state.update(state="failed", error=f"{type(exc).__name__}: {exc}")
        finally:
            if state["state"] == "awaiting_review" and time.monotonic() >= deadline:
                state.update(state="failed", error="deadline exhausted before durable publication")
            _persist(directory, state, started, deadline=deadline)
        return status(directory)


def replay(directory: Path, *, reviewed_script_sha: str) -> dict:
    directory = directory.resolve(strict=True)
    with (directory / "run.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        verified = status(directory)
        state = verified["run"]
        if state["state"] != "awaiting_review":
            raise ContinuationError("baseline replay already started or unavailable; repeat forbidden")
        script = _read(directory / "analysis.py", COMPONENT_MAX)
        script_sha = _record(script)["sha256"]
        if not re.fullmatch(r"[0-9a-f]{64}", reviewed_script_sha) or reviewed_script_sha != script_sha:
            raise ContinuationError("reviewed script SHA differs from exact analysis.py")
        started = time.monotonic()
        payload = PACKAGING_PREFIX + script
        payload_sha = _record(payload)["sha256"]
        state.update(state="replaying", stage="replay", replay_started_at_utc=_now(),
                     reviewed_script_sha256=script_sha, payload_sha256=payload_sha,
                     packaging_prefix=PACKAGING_PREFIX.decode("ascii"),
                     review_scope="caller local declaration; no custody or normative approval")
        _atomic(directory / "run.json", state)
        try:
            interpreter = PACKAGING_INTERPRETER.resolve(strict=True)
            runtime_roots = tuple(dict.fromkeys((*default_python_runtime_roots(), interpreter)))
            state["runtime_interpreter"] = {
                "path": str(interpreter), **_artifact_record(interpreter), "sealed": False}
            state["runtime_roots"] = list(map(str, runtime_roots))
            result = run_sandboxed(
                argv=[str(directory / "launch.py"), str(directory / "input")],
                cwd=directory / "work", read_roots=[directory / "input"], write_roots=[],
                runtime_roots=runtime_roots,
                stdout_path=directory / "baseline.stdout.json", stderr_path=directory / "baseline.stderr.txt",
                sealed_executable_bytes=payload, sealed_executable_sha256=payload_sha,
                **SANDBOX_LIMITS)
            state["replay"] = asdict(result)
            if result.exit_code != 0 or result.timed_out or result.launch_error:
                raise ContinuationError("baseline sandbox failed or timed out")
            if result.sealed_executable_sha256 != payload_sha:
                raise ContinuationError("sealed baseline payload differs")
            raw = _read(directory / "baseline.stdout.json", SANDBOX_LIMITS["file_bytes_per_file"])
            _strict_json(raw)
            (directory / "metrics.json").write_bytes(raw)
            state["state"] = "replayed"
        except (CheckpointError, ContinuationError, SandboxError, SandboxUnavailable, OSError,
                ValueError, RecursionError, subprocess.SubprocessError) as exc:
            state.update(state="failed", error=f"{type(exc).__name__}: {exc}")
        finally:
            _persist(directory, state, started)
        return status(directory)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("repo", type=Path)
    p.add_argument("directory", type=Path)
    for name in ("generate", "status"):
        commands.add_parser(name).add_argument("directory", type=Path)
    p = commands.add_parser("replay")
    p.add_argument("directory", type=Path)
    p.add_argument("--reviewed-script-sha", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.repo, args.directory)
        elif args.command == "generate":
            result = generate(args.directory)
        elif args.command == "replay":
            result = replay(args.directory, reviewed_script_sha=args.reviewed_script_sha)
        else:
            result = status(args.directory)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1 if result["state"] == "failed" else 0
    except (CheckpointError, ContinuationError, RunError, OSError, ValueError,
            RecursionError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
