from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import run_prototype_checkpoint as checkpoint


def _case() -> dict:
    def node(identifier, kind, phase, dependencies):
        return {"id": identifier, "kind": kind, "phase": phase, "status": "pending",
                "claim": "Candidate work requiring verification or approval.", "depends_on": dependencies}
    return {"case_id": "D-F-BREAD-NORWAY", "nodes": [
        node("p", "problem", "philosophy", []),
        node("n", "normative", "philosophy", ["p"]),
        node("e", "evidence", "science", ["p"]),
        node("r", "requirement", "engineering", ["e", "n"]),
        node("t", "test_result", "validation", ["r"])]}


def _events(tokens: int = 10, *, tool: bool = False) -> list[dict]:
    return [{"type": "thread.started", "thread_id": "test-only"},
            {"type": "item.completed", "item": {"id": "message", "type":
                "command_execution" if tool else "agent_message", "text": "pending proposal"}},
            {"type": "turn.completed", "usage": {"input_tokens": tokens,
                "cached_input_tokens": 0, "cache_write_input_tokens": 0,
                "output_tokens": tokens, "reasoning_output_tokens": 0}}]


@pytest.fixture
def admission(tmp_path, monkeypatch):
    monkeypatch.setenv(checkpoint.ADMISSION_ENV, str(tmp_path / "admission"))


def _prepare(tmp_path, *, active_seconds=120, name="run", monkeypatch=None, study_id="D095") -> Path:
    if active_seconds != 120:
        assert monkeypatch is not None
        protocol = json.loads(checkpoint.PROTOCOL.read_text())
        protocol["active_seconds"] = active_seconds
        protocol_path = tmp_path / f"protocol-{active_seconds}.json"
        protocol_path.write_text(json.dumps(protocol))
        monkeypatch.setattr(checkpoint, "PROTOCOL", protocol_path)
        monkeypatch.setattr(checkpoint, "PROTOCOL_SHA", hashlib.sha256(protocol_path.read_bytes()).hexdigest())
    directory = tmp_path / name
    checkpoint.prepare(checkpoint.ROOT, directory, mode="graph", model="gpt-6-luna",
                       effort="medium", active_seconds=active_seconds, study_id=study_id)
    return directory


def _fake_cli(tmp_path, monkeypatch, *, behavior="valid", case=None):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    cli = bindir / "codex"
    case = _case() if case is None else case
    cli.write_text("#!" + sys.executable + "\n" + f'''
import json, os, sys, time
from pathlib import Path
args = sys.argv[1:]
if args == ["login", "status"]:
    print("Logged in using {"API key" if behavior == "api_key" else "ChatGPT"}")
    sys.exit(0)
counter = Path(__file__).parent / "calls.txt"
with counter.open("a") as stream:
    stream.write("execute\\n")
Path(__file__).with_name("api_env_present.txt").write_text(str("OPENAI_API_KEY" in os.environ))
if {behavior!r} == "timeout":
    print(json.dumps({{"type":"thread.started","thread_id":"test-only"}}), flush=True)
    time.sleep(30)
if {behavior!r} == "large":
    print("x" * (32 * 1024 * 1024 + 1), flush=True)
    sys.exit(1)
proposal = {case!r}
Path(args[args.index("-o") + 1]).write_text(json.dumps(proposal))
events = {_events(0 if behavior == "zero" else 10, tool=behavior == "tool")!r}
for event in events:
    print(json.dumps(event), flush=True)
''')
    cli.chmod(0o700)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    return bindir


def test_real_init_and_new_process_status_with_fake_model(tmp_path, monkeypatch, admission):
    directory = _prepare(tmp_path)
    bindir = _fake_cli(tmp_path, monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-not-a-credential")
    result = checkpoint.execute(directory)
    assert result["state"] == "checkpoint_ready"
    assert result["checkpoint_verified"] and not result["relaunch_allowed"]
    assert result["run"]["init"]["exit_code"] == 0
    assert result["run"]["authentication"]["raw_output_retained"] is False
    assert (bindir / "api_env_present.txt").read_text() == "False"
    assert result["plan"]["global_run_limits_enforced"] is False
    assert "--ignore-user-config" in result["run"]["argv"]
    assert "read-only" in result["run"]["argv"]
    process = subprocess.run([sys.executable, str(checkpoint.ROOT / "scripts/run_prototype_checkpoint.py"),
                              "status", str(directory)], capture_output=True, text=True, check=True)
    assert json.loads(process.stdout)["checkpoint_verified"]
    with pytest.raises(checkpoint.CheckpointError, match="relaunch forbidden"):
        checkpoint.execute(directory)
    assert (bindir / "calls.txt").read_text() == "execute\n"
    with (directory / "state.json").open("a") as stream:
        stream.write("\n")
    with pytest.raises(checkpoint.CheckpointError, match="artifact changed"):
        checkpoint.status(directory)


def test_real_process_deadline_preserves_partial_and_never_relaunches(tmp_path, monkeypatch, admission):
    directory = _prepare(tmp_path, active_seconds=1, monkeypatch=monkeypatch)
    bindir = _fake_cli(tmp_path, monkeypatch, behavior="timeout")
    result = checkpoint.execute(directory)
    assert result["state"] == "failed"
    assert result["run"]["model"]["timed_out"]
    assert result["run"]["observed_wall_seconds"] < 4
    assert b"thread.started" in (directory / "model.stdout.jsonl").read_bytes()
    assert not (directory / "state.json").exists()
    with pytest.raises(checkpoint.CheckpointError, match="relaunch forbidden"):
        checkpoint.execute(directory)
    assert (bindir / "calls.txt").read_text() == "execute\n"
    assert checkpoint.status(directory)["run"]["artifacts"]["model.stdout.jsonl"]["bytes"] > 0


@pytest.mark.parametrize("behavior", ["tool", "zero", "api_key"])
def test_observed_tool_zero_usage_and_api_auth_reject(tmp_path, monkeypatch, admission, behavior):
    directory = _prepare(tmp_path)
    bindir = _fake_cli(tmp_path, monkeypatch, behavior=behavior)
    result = checkpoint.execute(directory)
    assert result["state"] == "failed" and not result["checkpoint_verified"]
    assert not (directory / "state.json").exists()
    if behavior == "api_key":
        assert not (bindir / "calls.txt").exists()


@pytest.mark.parametrize("defect", ["supported", "missing_norm", "unlinked", "cycle", "unknown"])
def test_invalid_pending_proposal_never_initializes(tmp_path, monkeypatch, admission, defect):
    case = _case()
    if defect == "supported":
        case["nodes"][0]["status"] = "supported"
    elif defect == "missing_norm":
        case["nodes"][1]["kind"] = "assumption"
    elif defect == "unlinked":
        case["nodes"][3]["depends_on"] = ["e"]
    elif defect == "cycle":
        case["nodes"][0]["depends_on"] = ["t"]
    else:
        case["nodes"][3]["depends_on"] = ["absent"]
    directory = _prepare(tmp_path)
    _fake_cli(tmp_path, monkeypatch, case=case)
    assert checkpoint.execute(directory)["state"] == "failed"
    assert not (directory / "state.json").exists()


def test_large_partial_stream_still_publishes_terminal_failure(tmp_path, monkeypatch, admission):
    directory = _prepare(tmp_path)
    _fake_cli(tmp_path, monkeypatch, behavior="large")
    result = checkpoint.execute(directory)
    assert result["state"] == "failed"
    pin = result["run"]["artifacts"]["model.stdout.jsonl"]
    assert pin["bytes"] > 32 * 1024 * 1024
    assert pin["sha256"] == hashlib.sha256((directory / "model.stdout.jsonl").read_bytes()).hexdigest()
    assert checkpoint.status(directory)["state"] == "failed"


def test_one_protocol_cannot_execute_a_second_destination(tmp_path, monkeypatch, admission):
    first = _prepare(tmp_path, name="first")
    second = _prepare(tmp_path, name="second")
    bindir = _fake_cli(tmp_path, monkeypatch)
    assert checkpoint.execute(first)["checkpoint_verified"]
    result = checkpoint.execute(second)
    assert result["state"] == "failed" and "already claimed" in result["run"]["error"]
    assert (bindir / "calls.txt").read_text() == "execute\n"


def test_default_protocol_rejects_other_config_before_destination(tmp_path, admission):
    destination = tmp_path / "invalid"
    with pytest.raises(checkpoint.CheckpointError, match="pinned prospective protocol"):
        checkpoint.prepare(checkpoint.ROOT, destination, mode="risk", model="gpt-6-astra",
                           effort="high", active_seconds=300)
    assert not destination.exists()


def test_changed_source_rejects_before_destination_without_touching_repo(tmp_path, admission):
    copy = tmp_path / "repo-copy"
    for name in [checkpoint.STAGING, *checkpoint.SOURCES.values(),
                 *[f"prototypes/{n}.py" for n in ("core", "graph", "risk", "sequential")]]:
        path = copy / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(checkpoint.ROOT / name, path)
    (copy / "cases/bread_development/task.md").write_text("changed source")
    # Git object reads still use the real immutable object store; no checkout writes.
    (copy / ".git").write_text(f"gitdir: {checkpoint.ROOT / '.git'}\n")
    with pytest.raises(checkpoint.CheckpointError, match="source bytes changed"):
        checkpoint.prepare(copy, tmp_path / "invalid", mode="graph", model="gpt-6-luna",
                           effort="medium", active_seconds=120)
    assert not (tmp_path / "invalid").exists()


def test_coherent_runtime_config_edit_still_rejects_protocol(tmp_path, admission):
    directory = _prepare(tmp_path)
    plan_path = directory / "plan.json"
    plan = json.loads(plan_path.read_text())
    plan["model"] = "gpt-6-astra"
    checkpoint._atomic(plan_path, plan)
    state = json.loads((directory / "run.json").read_text())
    state["plan"] = checkpoint._record(plan_path.read_bytes())
    checkpoint._atomic(directory / "run.json", state)
    with pytest.raises(checkpoint.CheckpointError, match="differs from the prospective"):
        checkpoint.status(directory)
    with pytest.raises(checkpoint.CheckpointError, match="differs from the prospective"):
        checkpoint.execute(directory)


def test_cli_rejects_protocol_override_without_creating_destination(tmp_path):
    destination = tmp_path / "invalid"
    process = subprocess.run([sys.executable, str(checkpoint.ROOT / "scripts/run_prototype_checkpoint.py"),
        "prepare", str(checkpoint.ROOT), str(destination), "--mode", "graph", "--model", "gpt-6-luna",
        "--effort", "medium", "--active-seconds", "120", "--protocol", str(checkpoint.PROTOCOL),
        "--protocol-sha256", checkpoint.PROTOCOL_SHA], capture_output=True, text=True)
    assert process.returncode == 2 and not destination.exists()
    assert "unrecognized arguments" in process.stderr


def test_coherent_protocol_override_is_rejected_on_reload(tmp_path, admission):
    directory = _prepare(tmp_path)
    override = tmp_path / "alternate.json"
    override.write_bytes(checkpoint.PROTOCOL.read_bytes())
    plan_path = directory / "plan.json"
    plan = json.loads(plan_path.read_text())
    plan["protocol_path"] = str(override)
    checkpoint._atomic(plan_path, plan)
    state = json.loads((directory / "run.json").read_text())
    state["plan"] = checkpoint._record(plan_path.read_bytes())
    checkpoint._atomic(directory / "run.json", state)
    with pytest.raises(checkpoint.CheckpointError, match="fixed study authority"):
        checkpoint.execute(directory)


def _fake_host(bindir: Path, *, success=True) -> None:
    host = bindir / "codex-code-mode-host"
    host.write_text("#!" + sys.executable + "\n" +
                    f"import sys\nprint('synthetic help, no provider')\nsys.exit({0 if success else 1})\n")
    host.chmod(0o700)


def test_registered_compatibility_round_initializes_without_changing_d095(tmp_path, monkeypatch, admission):
    archive = checkpoint.ROOT / "experiments/development/prototype_checkpoint_2026-09-30/attempt"
    before = (archive / "run.json").read_bytes()
    directory = _prepare(tmp_path, study_id="D096")
    bindir = _fake_cli(tmp_path, monkeypatch)
    _fake_host(bindir)
    result = checkpoint.execute(directory)
    assert result["checkpoint_verified"]
    assert result["run"]["host"]["exit_code"] == 0
    assert result["run"]["host"]["model_call"] is False
    argv = result["run"]["argv"]
    assert argv[argv.index("--enable") + 1] == "code_mode_host"
    pairs = [(argv[i], argv[i + 1]) for i in range(len(argv) - 1)]
    assert ("--disable", "code_mode_host") not in pairs
    assert ("--disable", "shell_tool") in pairs
    assert ("--disable", "multi_agent") in pairs
    assert checkpoint.status(archive)["state"] == "failed"
    assert (archive / "run.json").read_bytes() == before
    process = subprocess.run([sys.executable, str(checkpoint.ROOT / "scripts/run_prototype_checkpoint.py"),
                             "status", str(directory)], capture_output=True, text=True, check=True)
    assert json.loads(process.stdout)["checkpoint_verified"]


@pytest.mark.parametrize("host_state", ["missing", "failed"])
def test_host_preflight_stops_before_model_invocation(tmp_path, monkeypatch, admission, host_state):
    directory = _prepare(tmp_path, study_id="D096")
    bindir = _fake_cli(tmp_path, monkeypatch)
    if host_state == "failed":
        _fake_host(bindir, success=False)
    result = checkpoint.execute(directory)
    assert result["state"] == "failed" and not result["checkpoint_verified"]
    assert not (bindir / "calls.txt").exists()
    assert not (directory / "model.stdout.jsonl").exists()
    assert not (directory / "state.json").exists()


def test_second_compatibility_destination_never_invokes_model(tmp_path, monkeypatch, admission):
    first = _prepare(tmp_path, study_id="D096", name="first")
    second = _prepare(tmp_path, study_id="D096", name="second")
    bindir = _fake_cli(tmp_path, monkeypatch)
    _fake_host(bindir)
    assert checkpoint.execute(first)["checkpoint_verified"]
    result = checkpoint.execute(second)
    assert result["state"] == "failed" and "already claimed" in result["run"]["error"]
    assert (bindir / "calls.txt").read_text() == "execute\n"


def test_unregistered_study_rejected_before_destination(tmp_path, admission):
    with pytest.raises(checkpoint.CheckpointError, match="unknown registered study"):
        checkpoint.prepare(checkpoint.ROOT, tmp_path / "invalid", mode="graph", model="gpt-6-luna",
                           effort="medium", active_seconds=120, study_id="unregistered")
    assert not (tmp_path / "invalid").exists()
