from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts import run_bread_continuation as continuation


SCRIPT = """import json, sys
from pathlib import Path
packet = Path(sys.argv[1])
assert json.loads((packet / 'prototype_case.json').read_text())['case_id'] == 'D-F-BREAD-NORWAY'
assert (packet / 'source_lca.txt').is_file()
print(json.dumps({'baseline': {'value': 1, 'unit': 'kg', 'base': 'synthetic test'}}))
"""


def _proposal(script: str = SCRIPT) -> dict:
    return {"analysis_py": script, "sources_json": '  {"sources": []}\n',
            "report_md": "  Draft; normative decisions remain pending.\n"}


def _events(behavior: str) -> list[dict]:
    item_type = {"tool": "command_execution", "unknown_item": "unknown"}.get(behavior, "agent_message")
    usage = {"input_tokens": 0 if behavior == "zero" else 10,
             "cached_input_tokens": 11 if behavior == "incoherent" else 0,
             "cache_write_input_tokens": 0, "output_tokens": 10, "reasoning_output_tokens": 0}
    events = [{"type": "thread.started", "thread_id": "test-only"},
              {"type": "item.completed", "item": {"id": "message", "type": item_type, "text": "draft"}}]
    if behavior == "error":
        events.append({"type": "error", "message": "synthetic failure"})
    events.append({"type": "turn.completed", "usage": usage})
    return events


@pytest.fixture
def admission(tmp_path, monkeypatch):
    monkeypatch.setenv(continuation.ADMISSION_ENV, str(tmp_path / "admission"))


def _fake_cli(tmp_path: Path, monkeypatch, *, behavior="valid", proposal=None) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    proposal = _proposal() if proposal is None else proposal
    cli = bindir / "codex"
    cli.write_text("#!" + sys.executable + "\n" + f'''
import json, os, sys, time
from pathlib import Path
args = sys.argv[1:]
if args == ["login", "status"]:
    print("Logged in using {"API key" if behavior == "api_key" else "ChatGPT"}")
    sys.exit(0)
counter = Path(__file__).with_name("calls.txt")
with counter.open("a") as stream:
    stream.write("generate\\n")
Path(__file__).with_name("api_env_present.txt").write_text(str("OPENAI_API_KEY" in os.environ))
if {behavior!r} == "timeout":
    print(json.dumps({{"type":"thread.started","thread_id":"test-only"}}), flush=True)
    time.sleep(300)
if {behavior!r} == "large":
    print("x" * (32 * 1024 * 1024 + 1), flush=True)
    sys.exit(1)
Path(args[args.index("-o") + 1]).write_text(json.dumps({proposal!r}))
for event in {_events(behavior)!r}:
    print(json.dumps(event), flush=True)
sys.exit({1 if behavior == "exit" else 0})
''', encoding="utf-8")
    cli.chmod(0o700)
    host = bindir / "codex-code-mode-host"
    host.write_text("#!" + sys.executable + "\nprint('synthetic local host help')\n", encoding="utf-8")
    host.chmod(0o700)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    return bindir


def _prepare(tmp_path: Path, *, name="run", repo=None) -> Path:
    directory = tmp_path / name
    result = continuation.prepare(continuation.ROOT if repo is None else repo, directory)
    assert result["state"] == "prepared"
    return directory


def _copy_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    protocol, _ = continuation._authority()
    for pin in [*protocol["source_files"].values(), protocol["parent_checkpoint"]["receipt"]]:
        relative = pin["path"]
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(continuation.ROOT / relative, target)
    relative = protocol["parent_checkpoint"]["directory"]
    shutil.copytree(continuation.ROOT / relative, repo / relative)
    return repo


def test_prepare_and_generation_exact_outputs_without_automatic_execution(tmp_path, monkeypatch, admission):
    directory = _prepare(tmp_path)
    bindir = _fake_cli(tmp_path, monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-not-a-credential")
    before = continuation._artifact_record(continuation.ROOT /
        "experiments/development/prototype_checkpoint_compatibility_2026-09-30/attempt/state.json")
    result = continuation.generate(directory)
    assert result["state"] == "awaiting_review"
    assert result["generation_verified"] and not result["baseline_verified"]
    assert result["replay_allowed"] and not result["generation_allowed"]
    assert not (directory / "baseline.stdout.json").exists()
    assert not (directory / "launch.py").exists()
    for key, name in continuation.OUTPUTS.items():
        assert (directory / name).read_bytes() == _proposal()[key].encode("utf-8")
    assert (bindir / "api_env_present.txt").read_text() == "False"
    assert result["run"]["authentication"]["raw_output_retained"] is False
    assert result["approved_normative_decisions"] == result["completed_phases"] == 0
    argv = result["run"]["argv"]
    assert "--ignore-user-config" in argv and "read-only" in argv
    assert argv[argv.index("--enable") + 1] == "code_mode_host"
    assert "code_mode_host" not in [argv[i + 1] for i, part in enumerate(argv) if part == "--disable"]
    assert continuation._artifact_record(continuation.ROOT /
        "experiments/development/prototype_checkpoint_compatibility_2026-09-30/attempt/state.json") == before
    process = subprocess.run([sys.executable, str(continuation.ROOT / "scripts/run_bread_continuation.py"),
                              "status", str(directory)], capture_output=True, text=True, check=True)
    assert json.loads(process.stdout)["state"] == "awaiting_review"
    with pytest.raises(continuation.ContinuationError, match="relaunch forbidden"):
        continuation.generate(directory)
    assert (bindir / "calls.txt").read_text() == "generate\n"


def test_real_reviewed_sealed_baseline_and_no_repetition(tmp_path, monkeypatch, admission):
    from scripts.local_replay_sandbox import probe_sandbox
    if not probe_sandbox().available:
        pytest.skip("required sandbox unavailable")
    directory = _prepare(tmp_path)
    bindir = _fake_cli(tmp_path, monkeypatch)
    continuation.generate(directory)
    script = (directory / "analysis.py").read_bytes()
    script_sha = hashlib.sha256(script).hexdigest()
    with pytest.raises(continuation.ContinuationError, match="reviewed script SHA"):
        continuation.replay(directory, reviewed_script_sha="0" * 64)
    assert continuation.status(directory)["state"] == "awaiting_review"
    result = continuation.replay(directory, reviewed_script_sha=script_sha)
    assert result["state"] == "replayed", result["run"].get("error")
    assert result["baseline_verified"] and not result["replay_allowed"]
    assert (directory / "analysis.py").read_bytes() == script
    assert (directory / "metrics.json").read_bytes() == (directory / "baseline.stdout.json").read_bytes()
    payload_sha = hashlib.sha256(continuation.PACKAGING_PREFIX + script).hexdigest()
    assert result["run"]["payload_sha256"] == result["run"]["replay"]["sealed_executable_sha256"] == payload_sha
    assert result["run"]["packaging_prefix"] == "#!/usr/bin/python3.12 -I\n"
    for call in (lambda: continuation.replay(directory, reviewed_script_sha=script_sha),
                 lambda: continuation.generate(directory)):
        with pytest.raises(continuation.ContinuationError):
            call()
    assert (bindir / "calls.txt").read_text() == "generate\n"


def test_real_sandbox_replay_cannot_create_files_network_or_descendants(tmp_path, monkeypatch, admission):
    from scripts.local_replay_sandbox import probe_sandbox
    if not probe_sandbox().available:
        pytest.skip("required sandbox unavailable")
    script = """import json, os, socket, sys
from pathlib import Path
blocked = 0
for operation in (lambda: Path(sys.argv[1], 'unexpected.txt').write_text('bad'),
                  lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM), lambda: os.fork()):
    try:
        operation()
    except OSError:
        blocked += 1
    else:
        raise AssertionError('restriction failed')
print(json.dumps({'blocked': blocked}))
"""
    directory = _prepare(tmp_path)
    _fake_cli(tmp_path, monkeypatch, proposal=_proposal(script))
    continuation.generate(directory)
    result = continuation.replay(directory, reviewed_script_sha=hashlib.sha256(script.encode()).hexdigest())
    assert result["state"] == "replayed", result["run"].get("error")
    assert json.loads((directory / "metrics.json").read_text()) == {"blocked": 3}
    assert not (directory / "input/unexpected.txt").exists()


@pytest.mark.parametrize("behavior", ["tool", "unknown_item", "error", "zero", "incoherent", "exit", "api_key"])
def test_failed_generation_retains_raw_trace_and_forbids_retry(tmp_path, monkeypatch, admission, behavior):
    directory = _prepare(tmp_path)
    bindir = _fake_cli(tmp_path, monkeypatch, behavior=behavior)
    result = continuation.generate(directory)
    assert result["state"] == "failed" and not result["generation_verified"]
    assert not (directory / "analysis.py").exists()
    with pytest.raises(continuation.ContinuationError, match="relaunch forbidden"):
        continuation.generate(directory)
    if behavior == "api_key":
        assert not (bindir / "calls.txt").exists()
    else:
        assert result["run"]["artifacts"]["model.stdout.jsonl"]["bytes"] > 0
        assert (bindir / "calls.txt").read_text() == "generate\n"
    assert continuation.status(directory)["state"] == "failed"


def test_real_model_capture_timeout_preserves_partial(tmp_path, monkeypatch, admission):
    directory = _prepare(tmp_path)
    bindir = _fake_cli(tmp_path, monkeypatch, behavior="timeout")
    original = continuation._capture

    def short_capture(*args, **kwargs):
        if kwargs.get("stage") == "model":
            kwargs.update(timeout_seconds=0.2, active_deadline=time.monotonic() + 0.2)
        return original(*args, **kwargs)
    monkeypatch.setattr(continuation, "_capture", short_capture)
    result = continuation.generate(directory)
    assert result["state"] == "failed" and result["run"]["model"]["timed_out"]
    assert b"thread.started" in (directory / "model.stdout.jsonl").read_bytes()
    assert result["run"]["artifacts"]["model.stdout.jsonl"]["bytes"] > 0
    assert (bindir / "calls.txt").read_text() == "generate\n"
    assert continuation.status(directory)["state"] == "failed"


def test_large_failed_stream_is_hashed_with_no_relaunch(tmp_path, monkeypatch, admission):
    directory = _prepare(tmp_path)
    _fake_cli(tmp_path, monkeypatch, behavior="large")
    result = continuation.generate(directory)
    assert result["state"] == "failed"
    pin = result["run"]["artifacts"]["model.stdout.jsonl"]
    assert pin["bytes"] > 32 * 1024 * 1024
    assert pin == continuation._artifact_record(directory / "model.stdout.jsonl")
    assert continuation.status(directory)["state"] == "failed"


@pytest.mark.parametrize("defect", ["extra", "type", "sources_array", "sources_duplicate", "sources_nonfinite",
                                  "script_large", "sources_large", "report_large"])
def test_bad_proposal_not_repaired_or_published(tmp_path, monkeypatch, admission, defect):
    proposal = _proposal()
    if defect == "extra":
        proposal["extra"] = "unexpected"
    elif defect == "type":
        proposal["analysis_py"] = []
    elif defect == "sources_array":
        proposal["sources_json"] = "[]"
    elif defect == "sources_duplicate":
        proposal["sources_json"] = '{"x":1,"x":2}'
    elif defect == "sources_nonfinite":
        proposal["sources_json"] = '{"x":1e400}'
    elif defect == "script_large":
        proposal["analysis_py"] = "#" * (32 * 1024 + 1)
    elif defect == "sources_large":
        proposal["sources_json"] = json.dumps({"text": "x" * (32 * 1024)})
    else:
        proposal["report_md"] = "word " * 1201
    directory = _prepare(tmp_path)
    _fake_cli(tmp_path, monkeypatch, proposal=proposal)
    result = continuation.generate(directory)
    assert result["state"] == "failed"
    assert not (directory / "analysis.py").exists()
    assert json.loads((directory / "proposal.json").read_text()) == proposal
    assert result["run"]["artifacts"]["proposal.json"] == continuation._artifact_record(directory / "proposal.json")


def test_shared_protocol_admission_blocks_second_destination(tmp_path, monkeypatch, admission):
    first = _prepare(tmp_path, name="first")
    second = _prepare(tmp_path, name="second")
    bindir = _fake_cli(tmp_path, monkeypatch)
    assert continuation.generate(first)["state"] == "awaiting_review"
    result = continuation.generate(second)
    assert result["state"] == "failed" and "already claimed" in result["run"]["error"]
    assert (bindir / "calls.txt").read_text() == "generate\n"


@pytest.mark.parametrize("target", ["input/source_lca.txt", "input/prototype_case.json", "prompt.txt", "schema.json",
                                  "analysis.py", "sources.json", "report.md", "model.stdout.jsonl"])
def test_mutated_input_or_output_pin_is_rejected(tmp_path, monkeypatch, admission, target):
    directory = _prepare(tmp_path)
    _fake_cli(tmp_path, monkeypatch)
    continuation.generate(directory)
    with (directory / target).open("ab") as stream:
        stream.write(b"\n")
    with pytest.raises(continuation.ContinuationError, match="changed"):
        continuation.status(directory)
    with pytest.raises(continuation.ContinuationError, match="changed"):
        continuation.replay(directory, reviewed_script_sha="0" * 64)


def test_changed_source_rejected_before_new_directory(tmp_path, admission):
    repo = _copy_repo(tmp_path)
    protocol, _ = continuation._authority()
    changed = repo / protocol["source_files"]["source_lca.txt"]["path"]
    with changed.open("ab") as stream:
        stream.write(b"\n")
    destination = tmp_path / "invalid"
    with pytest.raises(continuation.ContinuationError, match="registered bytes changed"):
        continuation.prepare(repo, destination)
    assert not destination.exists()


def test_parent_changes_rejected_without_touching_original(tmp_path, admission):
    repo = _copy_repo(tmp_path)
    directory = _prepare(tmp_path, repo=repo)
    protocol, _ = continuation._authority()
    parent = repo / protocol["parent_checkpoint"]["state"]["path"]
    with parent.open("ab") as stream:
        stream.write(b"\n")
    with pytest.raises(continuation.CheckpointError, match="artifact changed"):
        continuation.status(directory)


@pytest.mark.parametrize("target", ["repo", "parent_work", "source", "symlink_parent"])
def test_prepare_cannot_add_a_stage_to_protected_tree(tmp_path, admission, target):
    repo = _copy_repo(tmp_path)
    protocol, _ = continuation._authority()
    parent_work = repo / protocol["parent_checkpoint"]["directory"] / "work"
    parent_work.mkdir(exist_ok=True)
    if target == "repo":
        destination = repo / "new-stage"
    elif target == "parent_work":
        destination = parent_work / "new-stage"
    elif target == "source":
        destination = (repo / protocol["source_files"]["source_lca.txt"]["path"]).parent / "new-stage"
    else:
        link = tmp_path / "external-spelling"
        link.symlink_to(parent_work, target_is_directory=True)
        destination = link / "new-stage"

    def snapshot():
        entries = {}
        for path in repo.rglob("*"):
            entries[str(path.relative_to(repo))] = (
                continuation._artifact_record(path) if path.is_file() else "directory")
        return entries

    before = snapshot()
    with pytest.raises(continuation.ContinuationError, match="outside.*protected"):
        continuation.prepare(repo, destination)
    assert not destination.exists()
    assert snapshot() == before


@pytest.mark.parametrize("mutation", ["override", "config", "remove_input_pin"])
def test_coherent_runtime_plan_mutation_cannot_authorize_change(tmp_path, admission, mutation):
    directory = _prepare(tmp_path)
    plan = json.loads((directory / "plan.json").read_text())
    if mutation == "override":
        duplicate = tmp_path / "alternative.json"
        duplicate.write_bytes(continuation.PLAN.read_bytes())
        plan["protocol_path"] = str(duplicate)
    elif mutation == "config":
        plan["model"] = "gpt-6-astra"
    else:
        plan["fixed_files"].pop("input/source_lca.txt")
    continuation._atomic(directory / "plan.json", plan)
    state = json.loads((directory / "run.json").read_text())
    state["plan"] = continuation._record((directory / "plan.json").read_bytes())
    continuation._atomic(directory / "run.json", state)
    with pytest.raises(continuation.ContinuationError, match="fixed"):
        continuation.status(directory)


def test_caller_cannot_override_authority_or_omit_review_declaration(tmp_path):
    script = str(continuation.ROOT / "scripts/run_bread_continuation.py")
    for args in (["prepare", str(continuation.ROOT), str(tmp_path / "run"),
                  "--plan", str(continuation.PLAN), "--plan-sha", continuation.PLAN_SHA],
                 ["replay", str(tmp_path / "run")]):
        process = subprocess.run([sys.executable, script, *args], capture_output=True, text=True)
        assert process.returncode == 2
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("baseline", ['{"x":NaN}', '{"x":1e400}', '{"x":1,"x":2}', '[]'])
def test_invalid_baseline_is_terminal_and_raw_preserved(tmp_path, monkeypatch, admission, baseline):
    from scripts.local_replay_sandbox import probe_sandbox
    if not probe_sandbox().available:
        pytest.skip("required sandbox unavailable")
    script = f"print({baseline!r})\n"
    directory = _prepare(tmp_path)
    _fake_cli(tmp_path, monkeypatch, proposal=_proposal(script))
    continuation.generate(directory)
    sha = hashlib.sha256(script.encode()).hexdigest()
    result = continuation.replay(directory, reviewed_script_sha=sha)
    assert result["state"] == "failed"
    assert (directory / "baseline.stdout.json").read_text() == baseline + "\n"
    assert result["run"]["artifacts"]["baseline.stdout.json"]["bytes"] > 0
    assert not (directory / "metrics.json").exists()
    with pytest.raises(continuation.ContinuationError, match="repeat forbidden"):
        continuation.replay(directory, reviewed_script_sha=sha)


def test_replaying_marker_prevents_restart_after_interruption(tmp_path, monkeypatch, admission):
    directory = _prepare(tmp_path)
    _fake_cli(tmp_path, monkeypatch)
    continuation.generate(directory)
    state = json.loads((directory / "run.json").read_text())
    state.update(state="replaying", stage="replay")
    continuation._atomic(directory / "run.json", state)
    with pytest.raises(continuation.ContinuationError, match="repeat forbidden"):
        continuation.replay(directory, reviewed_script_sha=hashlib.sha256(SCRIPT.encode()).hexdigest())
    assert continuation.status(directory)["state"] == "replaying"
