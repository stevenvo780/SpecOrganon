"""One-use local subscription CLI checkpoint; no quality or global budget claim."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from prototypes.core import PHASES, WorkflowError, descendants, validate_case  # noqa: E402
from run_development_arm import RunError, _capture, _parse_usage  # noqa: E402

STAGING = "experiments/development/bread_prototype_feasibility_2026-09-30/staging_receipt.json"
STAGING_SHA = "edc8a5c6de6e8af0813a0032091d60900d7460b849c18a09efdb1309a95e825a"
FREEZE = "7f8a344d56b467d032e449883074feb977f5a2c7"
PROTOCOL = ROOT / "experiments/development/prototype_checkpoint_2026-09-30/plan.json"
PROTOCOL_SHA = "a738b51f649ba1d64a2f8c929d6a41925ed97f1935c20f52c887d613c3713969"
ADMISSION_ENV = "SPECORGANON_CHECKPOINT_ADMISSION_ROOT"
SOURCES = {
    "task.md": "cases/bread_development/task.md",
    "source_claims.json": "cases/bread_development/source_claims.json",
    "source_manifest.json": "cases/bread_development/source_manifest.json",
    "source_lca.pdf": "cases/bread_norway/source_lca.pdf",
    "source_survey.pdf": "cases/bread_norway/source_survey.pdf",
    "survey_table1.json": "cases/bread_norway/survey_table1.json",
}
FEATURES_OFF = (
    "shell_tool", "unified_exec", "multi_agent", "apps", "plugins", "browser_use",
    "computer_use", "image_generation", "view_image", "code_mode_host", "memories",
    "hooks", "skill_search", "workspace_dependencies", "remote_plugin", "goals",
    "sleep_tool", "in_app_browser", "browser_use_external", "browser_use_full_cdp_access",
)
LIMITS = {"global_run_limits_enforced": False, "token_limit_enforced": False,
          "cost_limit_enforced": False, "tool_limit_preventively_enforced": False,
          "remote_cancellation_verified": False, "provider_identity_authenticated": False,
          "cost": None, "criterion_4": "not_assessed", "counts_toward_required_24_runs": False}


class CheckpointError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record(raw: bytes) -> dict:
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _read(path: Path, maximum: int = 4 * 1024 * 1024) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
        raise CheckpointError(f"not a bounded regular file: {path.name}")
    return path.read_bytes()


def _artifact_record(path: Path) -> dict:
    """Hash retained streams with bounded memory, including oversized negatives."""
    if not stat.S_ISREG(path.lstat().st_mode):
        raise CheckpointError("artifact is not regular")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"sha256": digest.hexdigest(), "bytes": size}


def _json(raw: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise CheckpointError("duplicate JSON key")
            result[key] = value
        return result
    result = json.loads(raw, object_pairs_hook=pairs,
                        parse_constant=lambda _: (_ for _ in ()).throw(CheckpointError("nonfinite JSON")))
    if type(result) is not dict:
        raise CheckpointError("JSON root must be object")
    return result


def _atomic(path: Path, value: dict) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".checkpoint-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _schema() -> dict:
    properties = {"id": {"type": "string"}, "kind": {"type": "string", "enum": [
        "problem", "assumption", "normative", "evidence", "requirement", "test_result"]},
        "phase": {"type": "string", "enum": list(PHASES)},
        "status": {"type": "string", "enum": ["pending"]}, "claim": {"type": "string"},
        "depends_on": {"type": "array", "items": {"type": "string"}}}
    return {"type": "object", "additionalProperties": False,
            "required": ["case_id", "nodes"], "properties": {
                "case_id": {"type": "string", "enum": ["D-F-BREAD-NORWAY"]},
                "nodes": {"type": "array", "items": {"type": "object",
                          "additionalProperties": False, "required": list(properties),
                          "properties": properties}}}}


def _proposal(raw: bytes) -> dict:
    if len(raw) > 65536:
        raise CheckpointError("proposal exceeds 64 KiB")
    case = _json(raw)
    keys = set(_schema()["properties"]["nodes"]["items"]["properties"])
    if set(case) != {"case_id", "nodes"} or case["case_id"] != "D-F-BREAD-NORWAY":
        raise CheckpointError("proposal root fields or case id invalid")
    if type(case["nodes"]) is not list or not 4 <= len(case["nodes"]) <= 64:
        raise CheckpointError("proposal needs 4 to 64 nodes")
    if any(type(n) is not dict or set(n) != keys or n["status"] != "pending"
           for n in case["nodes"]):
        raise CheckpointError("all exact node fields must be pending")
    nodes = validate_case(case)
    normative = [n for n in nodes if nodes[n]["kind"] == "normative"]
    if not any(nodes[d]["phase"] == "engineering" and nodes[d]["kind"] == "requirement"
               for n in normative for d in descendants(nodes, n)):
        raise CheckpointError("engineering requirement lacks pending normative dependency")
    return case


def prepare(repo: Path, destination: Path, *, mode: str, model: str,
            effort: str, active_seconds: int) -> dict:
    if mode not in {"graph", "risk", "sequential"} or effort not in {"low", "medium", "high"}:
        raise CheckpointError("invalid mode or effort")
    if not re.fullmatch(r"gpt-[a-zA-Z0-9.-]+", model) or type(active_seconds) is not int or not 1 <= active_seconds <= 300:
        raise CheckpointError("invalid requested model or time limit")
    protocol_path = PROTOCOL.resolve(strict=True)
    protocol_sha256 = PROTOCOL_SHA
    protocol_raw = _read(protocol_path)
    if _record(protocol_raw)["sha256"] != protocol_sha256:
        raise CheckpointError("prospective protocol bytes changed")
    protocol = _json(protocol_raw)
    if (protocol.get("attempts") != 1 or protocol.get("provider_cli") != "codex"
            or (mode, model, effort, active_seconds) != (
                protocol.get("prototype_mode"), protocol.get("requested_model"),
                protocol.get("requested_effort"), protocol.get("active_seconds"))
            or protocol.get("source_freeze_commit") != FREEZE
            or set(protocol.get("common_source_paths", [])) != set(SOURCES.values())
            or set(protocol.get("prototype_paths", [])) != {
                f"prototypes/{name}.py" for name in ("core", "graph", "risk", "sequential")}):
        raise CheckpointError("configuration does not match the pinned prospective protocol")
    repo = repo.resolve(strict=True)
    receipt_raw = _read(repo / STAGING)
    if _record(receipt_raw)["sha256"] != STAGING_SHA:
        raise CheckpointError("original staging receipt changed")
    receipt = _json(receipt_raw)
    mapping = {f"input/{name}": path for name, path in SOURCES.items()}
    mapping.update({f"harness/{name}.py": f"prototypes/{name}.py"
                    for name in ("core", "graph", "risk", "sequential")})
    blobs = {}
    for target, source in mapping.items():
        raw = _read(repo / source)
        frozen = subprocess.run(["git", "show", f"{FREEZE}:{source}"], cwd=repo,
                                capture_output=True, timeout=10, check=True).stdout
        if raw != frozen or _record(raw) != receipt["frozen_git_files"][source]:
            raise CheckpointError(f"source bytes changed: {source}")
        blobs[target] = raw
    prompt = (
        "Produce ONLY the initial prototype case JSON. Do not use tools, inspect files, "
        "approve decisions, perform scientific verification or complete the task. "
        "case_id=D-F-BREAD-NORWAY. 4 to 64 nodes, exact fields: id,kind,phase,status,claim,depends_on. "
        "Every status must be pending. Include philosophy/science/engineering/validation; "
        "at least one normative decision needing human approval and an engineering requirement "
        "depending on that norm. Unknown dependencies and cycles are forbidden. "
        "Use the public packet below as context. Propose work, never claim it was performed.\n"
    )
    for name in ("task.md", "source_claims.json", "source_manifest.json"):
        prompt += f"\nPUBLIC {name}\n" + blobs[f"input/{name}"].decode("utf-8")
    blobs["prompt.txt"] = prompt.encode("utf-8")
    blobs["schema.json"] = (json.dumps(_schema(), sort_keys=True, indent=2) + "\n").encode()
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise CheckpointError("destination must be new")
    destination.mkdir(mode=0o700)
    for name, raw in blobs.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(raw)
    (destination / "work").mkdir(mode=0o700)
    (destination / "run.lock").touch(mode=0o600)
    plan = {"schema": 1, "mode": mode, "model": model, "effort": effort,
            "active_seconds": active_seconds, "source_commit": FREEZE,
            "protocol_path": str(protocol_path), "protocol_sha256": protocol_sha256,
            "admission_root": str(Path(os.environ.get(ADMISSION_ENV,
                str(Path.home() / ".local/state/specorganon/prototype_checkpoint_admissions"))).absolute()),
            "staging_receipt_sha256": STAGING_SHA, "origins": mapping,
            "fixed_files": {name: _record(raw) for name, raw in blobs.items()}, **LIMITS}
    _atomic(destination / "plan.json", plan)
    state = {"schema": 1, "state": "prepared", "prepared_at_utc": _now(),
             "plan": _record(_read(destination / "plan.json")), "artifacts": {}, "error": None}
    _atomic(destination / "run.json", state)
    return status(destination)


def _load(directory: Path) -> tuple[dict, dict]:
    state = _json(_read(directory / "run.json"))
    plan_raw = _read(directory / "plan.json")
    if state.get("plan") != _record(plan_raw):
        raise CheckpointError("plan changed")
    plan = _json(plan_raw)
    if (plan["protocol_path"] != str(PROTOCOL.resolve(strict=True))
            or plan["protocol_sha256"] != PROTOCOL_SHA):
        raise CheckpointError("runtime protocol differs from the fixed study authority")
    protocol_raw = _read(Path(plan["protocol_path"]))
    if _record(protocol_raw)["sha256"] != plan["protocol_sha256"]:
        raise CheckpointError("prospective protocol changed after preparation")
    protocol = _json(protocol_raw)
    if (plan["mode"], plan["model"], plan["effort"], plan["active_seconds"]) != (
            protocol["prototype_mode"], protocol["requested_model"],
            protocol["requested_effort"], protocol["active_seconds"]):
        raise CheckpointError("runtime configuration differs from the prospective protocol")
    if state.get("state") not in {"prepared", "started", "failed", "checkpoint_ready"}:
        raise CheckpointError("invalid execution state")
    if type(plan.get("active_seconds")) is not int or not 1 <= plan["active_seconds"] <= 300:
        raise CheckpointError("invalid active limit")
    for name, pin in plan["fixed_files"].items():
        if _record(_read(directory / name)) != pin:
            raise CheckpointError(f"fixed input changed: {name}")
    for name, pin in state["artifacts"].items():
        if _artifact_record(directory / name) != pin:
            raise CheckpointError(f"checkpoint artifact changed: {name}")
    return state, plan


def _check_init(directory: Path, plan: dict) -> dict:
    case = _proposal(_read(directory / "prototype_case.json", 65536))
    initial = _json(_read(directory / "state.json"))
    expected_nodes = validate_case(case)
    if (initial.get("mode") != plan["mode"] or initial.get("case_id") != case["case_id"]
            or initial.get("nodes") != expected_nodes
            or initial.get("phase_status") != {p: "not_started" for p in PHASES}
            or initial.get("accepted_versions") != {}
            or len(initial.get("history", [])) != 1
            or initial["history"][0].get("action") != "init"):
        raise CheckpointError("prototype state is not the initial pending checkpoint")
    return initial


def _trace(directory: Path, model: str) -> dict:
    raw = _read(directory / "model.stdout.jsonl", 32 * 1024 * 1024)
    for line in raw.splitlines():
        event = _json(line)
        if event.get("type", "").startswith("item."):
            item = event.get("item")
            if type(item) is not dict or item.get("type") not in {"reasoning", "agent_message"}:
                raise CheckpointError("observed tool or unknown item")
    usage = _parse_usage("codex", directory / "model.stdout.jsonl", model)
    if not usage["terminal_success"] or not usage["complete"]:
        raise CheckpointError("incomplete or incoherent local CLI turn/usage")
    if usage["final_usage"]["input_tokens"] <= 0 or usage["final_usage"]["output_tokens"] <= 0:
        raise CheckpointError("nonempty generation requires positive input/output token usage")
    return usage


def status(directory: Path) -> dict:
    directory = directory.resolve(strict=True)
    state, plan = _load(directory)
    if state["state"] == "checkpoint_ready":
        if not all(name in state["artifacts"] for name in (
                "prototype_case.json", "state.json", "model.stdout.jsonl", "model.stderr.txt",
                "proposal.json", "init.stdout.json", "init.stderr.txt")):
            raise CheckpointError("checkpoint lacks required artifact pins")
        _trace(directory, plan["model"])
        _check_init(directory, plan)
    return {"state": state["state"], "checkpoint_verified": state["state"] == "checkpoint_ready",
            "relaunch_allowed": state["state"] == "prepared", "run": state, "plan": plan,
            "next_action": "inspect pending decisions and plan a separately registered continuation",
            **LIMITS}


def _environment() -> dict[str, str]:
    return {key: os.environ[key] for key in (
        "HOME", "CODEX_HOME", "PATH", "LANG", "LC_ALL", "TZ", "TMPDIR",
        "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME") if key in os.environ}


def _auth(cli: str, env: dict[str, str], deadline: float) -> dict:
    remaining = min(10.0, deadline - time.monotonic())
    if remaining <= 0:
        raise CheckpointError("deadline exhausted before authentication preflight")
    process = subprocess.Popen([cli, "login", "status"], env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    try:
        out, err = process.communicate(timeout=remaining)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=1)
        raise CheckpointError("authentication preflight timeout") from None
    report = (out + err).decode("utf-8", errors="replace").lower()
    classification = {"exit_code": process.returncode,
                      "chatgpt_login_reported": "logged in using chatgpt" in report,
                      "api_key_login_reported": "api key" in report or "api_key" in report,
                      "raw_output_retained": False}
    if process.returncode or not classification["chatgpt_login_reported"] or classification["api_key_login_reported"]:
        raise CheckpointError("existing ChatGPT login not confirmed; no API fallback")
    return classification


def _claim(directory: Path, plan: dict) -> dict:
    """One local cooperative admission for a protocol, shared by copied destinations."""
    root = Path(plan["admission_root"])
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = root / (plan["protocol_sha256"] + ".json")
    claim = {"protocol_sha256": plan["protocol_sha256"], "directory": str(directory),
             "claimed_at_utc": _now(), "scope": "cooperating processes sharing this local root"}
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise CheckpointError("prospective protocol attempt already claimed; no second destination") from None
    with os.fdopen(fd, "w") as stream:
        json.dump(claim, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return claim


def execute(directory: Path) -> dict:
    directory = directory.resolve(strict=True)
    with (directory / "run.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state, plan = _load(directory)
        if state["state"] != "prepared":
            raise CheckpointError("attempt already started; relaunch forbidden")
        started = time.monotonic()
        deadline = started + plan["active_seconds"]
        state.update(state="started", started_at_utc=_now())
        _atomic(directory / "run.json", state)
        try:
            state["admission"] = _claim(directory, plan)
            env = _environment()
            cli = shutil.which("codex", path=env.get("PATH"))
            if not cli:
                raise CheckpointError("codex CLI unavailable")
            state["authentication"] = _auth(cli, env, deadline)
            argv = [cli, "exec", "--json", "--ephemeral", "--ignore-user-config",
                    "--skip-git-repo-check", "-C", str(directory / "work"), "-s", "read-only",
                    "-m", plan["model"], "-c", f'model_reasoning_effort="{plan["effort"]}"',
                    "-c", 'web_search="disabled"']
            for feature in FEATURES_OFF:
                argv += ["--disable", feature]
            argv += ["--output-schema", str(directory / "schema.json"), "-o",
                     str(directory / "proposal.json"), "-"]
            state["argv"] = argv
            state["model"] = _capture(
                argv, cwd=directory / "work", timeout_seconds=plan["active_seconds"],
                active_deadline=deadline, stdin_text=_read(directory / "prompt.txt").decode(),
                stdout_path=directory / "model.stdout.jsonl", stderr_path=directory / "model.stderr.txt",
                env=env, stage="model")
            if state["model"]["exit_code"] != 0 or state["model"]["timed_out"]:
                raise CheckpointError("CLI failed or exceeded local active deadline")
            state["usage"] = _trace(directory, plan["model"])
            case = _proposal(_read(directory / "proposal.json", 65536))
            if time.monotonic() >= deadline:
                raise CheckpointError("deadline exhausted before init")
            _atomic(directory / "prototype_case.json", case)
            state["init"] = _capture(
                [sys.executable, str(directory / f'harness/{plan["mode"]}.py'), "init",
                 "--case", str(directory / "prototype_case.json"), "--state", str(directory / "state.json")],
                cwd=directory / "work", timeout_seconds=plan["active_seconds"], active_deadline=deadline,
                stdout_path=directory / "init.stdout.json", stderr_path=directory / "init.stderr.txt",
                env=env, stage="init")
            if state["init"]["exit_code"] != 0 or state["init"]["timed_out"]:
                raise CheckpointError("prototype init failed or timed out")
            _check_init(directory, plan)
            if time.monotonic() >= deadline:
                raise CheckpointError("deadline exhausted before checkpoint publication")
            state["state"] = "checkpoint_ready"
        except (CheckpointError, WorkflowError, RunError, OSError, ValueError, subprocess.SubprocessError) as exc:
            state.update(state="failed", error=f"{type(exc).__name__}: {exc}")
        finally:
            for name in ("model.stdout.jsonl", "model.stderr.txt", "proposal.json", "prototype_case.json",
                         "state.json", "init.stdout.json", "init.stderr.txt"):
                path = directory / name
                if path.exists():
                    try:
                        with path.open("rb") as stream:
                            os.fsync(stream.fileno())
                        state["artifacts"][name] = _artifact_record(path)
                    except (CheckpointError, OSError) as exc:
                        state.update(state="failed", error=f"artifact persistence failed: {type(exc).__name__}")
                        state.setdefault("unavailable_artifacts", []).append(name)
            if state["state"] == "checkpoint_ready" and time.monotonic() >= deadline:
                state.update(state="failed", error="deadline exhausted before durable publication")
            state.update(ended_at_utc=_now(), observed_wall_seconds=round(time.monotonic() - started, 3))
            _atomic(directory / "run.json", state)
        return status(directory)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("repo", type=Path)
    p.add_argument("directory", type=Path)
    p.add_argument("--mode", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--effort", required=True)
    p.add_argument("--active-seconds", required=True, type=int)
    for name in ("execute", "status"):
        commands.add_parser(name).add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.repo, args.directory, mode=args.mode, model=args.model,
                             effort=args.effort, active_seconds=args.active_seconds)
        else:
            result = execute(args.directory) if args.command == "execute" else status(args.directory)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1 if result["state"] == "failed" else 0
    except (CheckpointError, WorkflowError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
