"""A local fake CLI checks D-E run custody without calling paid models."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import run_development_arm as runner  # noqa: E402
from run_development_arm import (  # noqa: E402
    RunError, replay_run_dir, run_development_arm,
)


FAKE_CLI = r'''#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

scenario = os.environ.get("FAKE_SCENARIO", "ok")
provider = Path(sys.argv[0]).name
Path("fake_argv.json").write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
if provider == "codex":
    prompt = sys.stdin.read()
else:
    prompt = sys.argv[sys.argv.index("--print") + 1]
Path("fake_prompt.txt").write_text(prompt, encoding="utf-8")
if scenario == "sleep":
    time.sleep(3)
if scenario != "no_artifact":
    if scenario == "replay_mutate":
        Path("analysis.py").write_text(
            "from pathlib import Path\n"
            "Path('report.md').write_text('mutated\\n')\n"
            "p = Path('sample_first_complete_week.csv')\n"
            "p.write_bytes(p.read_bytes() + b'\\n')\n"
            "print('done')\n", encoding="utf-8")
    else:
        Path("analysis.py").write_text(
            "import csv\nfrom pathlib import Path\n"
            "rows = list(csv.DictReader(Path('sample_first_complete_week.csv').open()))\n"
            "assert len(rows) == 1008\n"
            "print(sum(int(row['Appliances']) for row in rows))\n",
            encoding="utf-8")
    Path("report.md").write_text("Observed data only. No intervention was run.\n", encoding="utf-8")
if scenario == "mutate_packet":
    Path("sample_first_complete_week.csv").write_bytes(
        Path("sample_first_complete_week.csv").read_bytes() + b"\n")
if provider == "codex":
    print(json.dumps({"type": "thread.started", "thread_id": "local-thread-id"}))
    if scenario == "codex_internal_failure":
        for item in (
            {"type": "command_execution", "status": "failed", "exit_code": 1},
            {"type": "file_change", "status": "failed"},
            {"type": "file_change", "status": "failed"},
        ):
            print(json.dumps({"type": "item.completed", "item": item}))
    else:
        print(json.dumps({"type": "item.completed", "item": {"type": "command_execution"}}))
    usage = None if scenario == "missing_usage" else {
        "input_tokens": 20, "cached_input_tokens": 2,
        "cache_write_input_tokens": 0, "output_tokens": 8,
        "reasoning_output_tokens": 1}
    print(json.dumps({"type": "turn.completed", "usage": usage}))
else:
    model = sys.argv[sys.argv.index("--model") + 1]
    print(json.dumps({"event": "init", "conversation_id": "local-conversation-id",
                      "init": {"model": model, "cwd": str(Path.cwd())}}))
    for state in ("ACTIVE", "DONE"):
        print(json.dumps({"event": "step_update", "step_update": {
            "step_index": 2, "step_type": "tool", "tool_name": "write_to_file",
            "state": state, "tool_info": {"parameters": {"TargetFile": "private-name"}}}}))
    usage = None if scenario == "missing_usage" else {
        "input_tokens": 30, "output_tokens": 9, "thinking_tokens": 3,
        "cache_read_tokens": 1, "total_tokens": 39}
    print(json.dumps({"event": "result", "result": {
        "status": "FAILURE" if scenario == "agy_final_failure" else "SUCCESS",
        "usage": usage, "conversation_id": "local-conversation-id",
        "denied_actions": [{"action": "command", "secret_parameter": "do-not-copy"}]
                          if scenario == "agy_denied_actions" else []}}))
'''


@pytest.fixture
def fake_clis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("codex", "agy"):
        executable = bin_dir / name
        executable.write_text(FAKE_CLI, encoding="utf-8")
        executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    return bin_dir


@pytest.mark.parametrize("provider", ["codex", "agy"])
def test_run_copies_only_assigned_packet_preserves_streams_and_replays(
    tmp_path: Path, fake_clis: Path, provider: str,
) -> None:
    run_dir, summary = run_development_arm(
        arm="S", provider=provider, model="test-model", effort="medium",
        output_root=tmp_path / "private-runs", timeout_seconds=10,
    )

    assert summary["classification"] == "exposed_development_unsealed"
    assert summary["execution_status"] == "artifacts_ready_for_inspection"
    assert summary["controlled_comparison_eligible"] is False
    assert summary["provider_request_id"] is None
    assert summary["cost"] is None
    assert summary["cli_usage"]["complete"] is True
    assert summary["analysis_replay"] is None
    assert not (run_dir / "analysis_replay.stdout").exists()
    summary = replay_run_dir(run_dir, summary["artifacts"]["analysis.py"]["sha256"])
    assert summary["execution_status"] == "output_replayed"
    assert summary["analysis_replay"]["exit_code"] == 0
    assert "118280" in (run_dir / "analysis_replay.stdout").read_text(encoding="utf-8")
    assert summary["artifacts"]["analysis.py"]["bytes"] > 0
    assert set(path.name for path in (run_dir / "work").iterdir()) == {
        "task.md", "source_manifest.json", "sample_first_complete_week.csv", "common.md",
        "arm.md", "analysis.py", "report.md", "fake_argv.json", "fake_prompt.txt",
    }
    assert "Brazo S" in (run_dir / "work/arm.md").read_text(encoding="utf-8")
    assert "Brazo T" not in (run_dir / "work/fake_prompt.txt").read_text(encoding="utf-8")
    assert "guía Q" not in (run_dir / "work/fake_prompt.txt").read_text(encoding="utf-8")
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((run_dir / "cli.stdout.jsonl").stat().st_mode) == 0o600
    assert (run_dir / "cli.stderr").exists()
    assert (run_dir / "run.json").exists()
    argv = json.loads((run_dir / "work/fake_argv.json").read_text(encoding="utf-8"))
    assert "test-model" in argv and "medium" in " ".join(argv)
    if provider == "agy":
        assert summary["cli_usage"]["observed_completed_tool_steps"] == 1
        assert summary["cli_usage"]["observed_unfinished_tool_steps"] == 0
        assert "local-conversation-id" not in (run_dir / "run.json").read_text(encoding="utf-8")
    else:
        assert "workspace-write" in argv
        assert "local-thread-id" not in (run_dir / "run.json").read_text(encoding="utf-8")


def test_missing_usage_remains_missing_and_never_becomes_controlled(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", "missing_usage")
    run_dir, summary = run_development_arm(
        arm="N", provider="agy", model="test-model", effort="high",
        output_root=tmp_path / "runs", timeout_seconds=10,
    )
    assert summary["execution_status"] == "artifacts_ready_for_inspection"
    assert summary["cli_usage"]["complete"] is False
    assert summary["cli_usage"]["terminal_success"] is True
    assert all(value is None for value in summary["cli_usage"]["final_usage"].values())
    assert summary["controlled_comparison_eligible"] is False
    assert "final local CLI usage is missing or malformed" in summary["limitations"]
    assert (run_dir / "cli.stdout.jsonl").exists()


def test_replay_rejects_unreviewed_or_changed_script(
    tmp_path: Path, fake_clis: Path,
) -> None:
    run_dir, summary = run_development_arm(
        arm="N", provider="agy", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
    )
    with pytest.raises(RunError, match="reviewed analysis digest differs"):
        replay_run_dir(run_dir, "0" * 64)
    assert not (run_dir / "analysis_replay.stdout").exists()
    (run_dir / "work/analysis.py").write_text("print('changed')\n", encoding="utf-8")
    with pytest.raises(RunError, match="analysis.py changed"):
        replay_run_dir(run_dir, summary["artifacts"]["analysis.py"]["sha256"])
    assert not (run_dir / "analysis_replay.stdout").exists()


def test_replay_exit_zero_cannot_hide_mutated_materials(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", "replay_mutate")
    run_dir, summary = run_development_arm(
        arm="N", provider="agy", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
    )
    assert summary["execution_status"] == "artifacts_ready_for_inspection"
    summary = replay_run_dir(run_dir, summary["artifacts"]["analysis.py"]["sha256"])
    assert summary["analysis_replay"]["exit_code"] == 0
    assert summary["execution_status"] == "replay_artifacts_mutated"
    assert {"report.md", "sample_first_complete_week.csv"}.issubset(
        summary["replay_material_mismatches"])


def test_zero_exit_without_outputs_is_failure_and_raw_events_survive(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", "no_artifact")
    run_dir, summary = run_development_arm(
        arm="N", provider="codex", model="test-model", effort="low",
        output_root=tmp_path / "runs", timeout_seconds=10,
    )
    assert summary["cli"]["exit_code"] == 0
    assert summary["execution_status"] == "required_artifact_missing"
    assert summary["artifacts"] == {"analysis.py": None, "report.md": None}
    assert summary["analysis_replay"] is None
    assert "turn.completed" in (run_dir / "cli.stdout.jsonl").read_text(encoding="utf-8")


@pytest.mark.parametrize("provider,scenario", [
    ("codex", "codex_internal_failure"), ("agy", "agy_final_failure"),
])
def test_zero_exit_with_artifacts_but_internal_failure_is_not_ready(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
    provider: str, scenario: str,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", scenario)
    run_dir, summary = run_development_arm(
        arm="N", provider=provider, model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
    )
    assert summary["cli"]["exit_code"] == 0
    assert all(summary["artifacts"].values())
    assert summary["cli_usage"]["terminal_success"] is False
    assert summary["execution_status"] == "cli_internal_failure"
    if provider == "codex":
        assert summary["cli_usage"]["observed_failed_codex_items_partial"] == 3
    else:
        assert summary["cli_usage"]["final_status"] == "FAILURE"
    with pytest.raises(RunError, match="not in artifacts_ready"):
        replay_run_dir(run_dir, summary["artifacts"]["analysis.py"]["sha256"])


def test_agy_denied_actions_rejects_success_with_artifacts_without_leaking_details(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", "agy_denied_actions")
    run_dir, summary = run_development_arm(
        arm="N", provider="agy", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
        agy_no_command_tool=True,
    )
    assert summary["cli"]["exit_code"] == 0
    assert summary["cli_usage"]["final_status"] == "SUCCESS"
    assert summary["cli_usage"]["denied_action_count"] == 1
    assert summary["execution_status"] == "cli_internal_failure"
    assert summary["tool_policy"] == "no_command_tool"
    assert "do-not-copy" not in (run_dir / "run.json").read_text(encoding="utf-8")


def test_no_command_tool_policy_changes_prompt_and_rejects_t_or_codex(
    tmp_path: Path, fake_clis: Path,
) -> None:
    run_dir, summary = run_development_arm(
        arm="S", provider="agy", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
        agy_no_command_tool=True,
    )
    prompt = (run_dir / "prompt.txt").read_text(encoding="utf-8")
    assert summary["execution_status"] == "artifacts_ready_for_inspection"
    assert summary["tool_policy"] == "no_command_tool"
    assert "do not call run_command, RunCommand" in prompt
    assert "do not guess" in prompt
    assert "--new-project" in (run_dir / "work/fake_argv.json").read_text(encoding="utf-8")
    assert "--project" not in (run_dir / "work/fake_argv.json").read_text(encoding="utf-8")
    for arm, provider in (("T", "agy"), ("N", "codex")):
        with pytest.raises(RunError, match="requires Agy N/S"):
            run_development_arm(
                arm=arm, provider=provider, model="test-model", effort="medium",
                output_root=tmp_path / f"rejected-{arm}-{provider}", timeout_seconds=10,
                agy_no_command_tool=True,
            )


def test_wall_timeout_terminates_cli_and_retains_partial_trace(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", "sleep")
    run_dir, summary = run_development_arm(
        arm="N", provider="agy", model="test-model", effort="low",
        output_root=tmp_path / "runs", timeout_seconds=1,
    )
    assert summary["execution_status"] == "cli_timeout"
    assert summary["cli"]["timed_out"] is True
    assert (run_dir / "cli.stdout.jsonl").exists()
    assert summary["controlled_comparison_eligible"] is False


def test_mutated_public_packet_is_rejected_even_with_outputs(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", "mutate_packet")
    run_dir, summary = run_development_arm(
        arm="S", provider="agy", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
    )
    assert summary["execution_status"] == "public_packet_mutated"
    assert summary["packet_unchanged"] is False
    assert (run_dir / "cli.stdout.jsonl").exists()


def test_copy_race_rejects_destination_bytes_before_model_call(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_copy = runner.shutil.copyfile

    def substitute_after_copy(source: Path, destination: Path) -> str:
        copied = original_copy(source, destination)
        if Path(source).name == "sample_first_complete_week.csv":
            target = Path(destination)
            target.write_bytes(target.read_bytes() + b"\n")
        return copied

    monkeypatch.setattr(runner.shutil, "copyfile", substitute_after_copy)
    with pytest.raises(RunError, match="public packet changed during copy"):
        run_development_arm(
            arm="N", provider="agy", model="test-model", effort="medium",
            output_root=tmp_path / "runs", timeout_seconds=10,
        )
    assert not list((tmp_path / "runs").glob("*/work/fake_argv.json"))


@pytest.mark.parametrize("source_name", ["common.md", "arm_n.md"])
def test_prompt_copy_race_fails_preflight_before_model_call(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
    source_name: str,
) -> None:
    original_copy = runner.shutil.copyfile

    def substitute_prompt_copy(source: Path, destination: Path) -> str:
        copied = original_copy(source, destination)
        if Path(source).name == source_name:
            target = Path(destination)
            target.write_bytes(target.read_bytes() + b"\nchanged after prompt assembly\n")
        return copied

    monkeypatch.setattr(runner.shutil, "copyfile", substitute_prompt_copy)
    run_dir, summary = run_development_arm(
        arm="N", provider="agy", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
    )
    assert summary["execution_status"] == "preflight_failure"
    assert "copies differ" in summary["preflight_error"]
    assert summary["cli"] is None
    assert not (run_dir / "cli.stdout.jsonl").exists()
    assert not (run_dir / "work/fake_argv.json").exists()


def test_cli_two_step_replay_uses_exact_reviewed_digest(
    tmp_path: Path, fake_clis: Path,
) -> None:
    script = SCRIPTS / "run_development_arm.py"
    started = subprocess.run([
        sys.executable, str(script), "--arm", "N", "--provider", "agy",
        "--model", "test-model", "--effort", "medium", "--output-root", str(tmp_path / "runs"),
        "--timeout-seconds", "10", "--agy-no-command-tool",
    ], capture_output=True, text=True, check=True)
    initial = json.loads(started.stdout)
    assert initial["status"] == "artifacts_ready_for_inspection"
    run_dir = Path(initial["run_dir"])
    summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert summary["tool_policy"] == "no_command_tool"
    digest = summary["artifacts"]["analysis.py"]["sha256"]
    replayed = subprocess.run([
        sys.executable, str(script), "--replay-run-dir", str(run_dir),
        "--expected-analysis-sha256", digest,
    ], capture_output=True, text=True, check=True)
    assert json.loads(replayed.stdout)["status"] == "output_replayed"
    assert (run_dir / "analysis_replay.stdout").exists()


def test_t_rejects_missing_wheel_before_any_model_call(
    tmp_path: Path, fake_clis: Path,
) -> None:
    with pytest.raises(RunError, match="requires a real toolkit wheel"):
        run_development_arm(
            arm="T", provider="agy", model="test-model", effort="medium",
            output_root=tmp_path / "runs", toolkit_wheel=None,
        )
    assert not (tmp_path / "runs").exists()
