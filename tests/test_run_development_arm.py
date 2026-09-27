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
        tool_index = "2" if scenario == "agy_tool_index_string" and state == "DONE" else 2
        tool_state = 123 if scenario == "agy_tool_state_malformed" and state == "DONE" else state
        print(json.dumps({"event": "step_update", "step_update": {
            "step_index": tool_index, "step_type": "tool", "tool_name": "write_to_file",
            "state": tool_state, "tool_info": {"parameters": {"TargetFile": "private-name"}}}}))
    step_usages = [
        {"input_tokens": 10, "output_tokens": 4, "thinking_tokens": 1,
         "cache_read_tokens": 0, "total_tokens": 14},
        {"input_tokens": 20, "output_tokens": 5, "thinking_tokens": 2,
         "cache_read_tokens": 1, "total_tokens": 25},
    ]
    if scenario == "agy_bad_both_arithmetic":
        step_usages = [{"input_tokens": 10, "output_tokens": 5,
                        "thinking_tokens": 2, "cache_read_tokens": 0, "total_tokens": 99}]
        agent_pairs = [(1, step_usages[0])]
    else:
        agent_pairs = [(1, step_usages[0]),
                       (2 if scenario == "agy_index_collision" else 3, step_usages[1])]
    for index, step_usage in agent_pairs:
        print(json.dumps({"event": "step_update", "step_update": {
            "step_index": index, "step_type": "agent_response", "state": "DONE",
            "text_delta": "private response text", "usage": step_usage}}))
    if scenario == "agy_active_agent":
        print(json.dumps({"event": "step_update", "step_update": {
            "step_index": 4, "step_type": "agent_response", "state": "ACTIVE"}}))
    if scenario in {"agy_duplicate_step", "agy_conflicting_step"}:
        duplicate = dict(step_usages[1])
        if scenario == "agy_conflicting_step":
            duplicate["output_tokens"] += 1
            duplicate["total_tokens"] += 1
        print(json.dumps({"event": "step_update", "step_update": {
            "step_index": 3, "step_type": "agent_response", "state": "DONE",
            "usage": duplicate}}))
    usage = None if scenario == "missing_usage" else {
        "input_tokens": 30, "output_tokens": 9, "thinking_tokens": 3,
        "cache_read_tokens": 1, "total_tokens": 39}
    if scenario == "agy_final_usage_mismatch":
        usage["input_tokens"] = 31
        usage["total_tokens"] = 40
    elif scenario == "agy_bad_both_arithmetic":
        usage = dict(step_usages[0])
    elif scenario == "agy_bad_final_arithmetic":
        usage["total_tokens"] = 99
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


def _usage_trace(
    path: Path,
    provider: str,
    final_usage: dict[str, int],
    step_usage: dict[str, int] | None = None,
) -> str:
    if provider == "codex":
        events = [{"type": "turn.completed", "usage": final_usage}]
    else:
        assert step_usage is not None
        events = [
            {"event": "init", "init": {"model": "test-model"}},
            {
                "event": "step_update",
                "step_update": {
                    "step_index": 1,
                    "step_type": "agent_response",
                    "state": "DONE",
                    "usage": step_usage,
                },
            },
            {
                "event": "result",
                "result": {
                    "status": "SUCCESS",
                    "usage": final_usage,
                    "denied_actions": [],
                },
            },
        ]
    raw = "".join(json.dumps(event) + "\n" for event in events)
    path.write_text(raw, encoding="utf-8")
    return raw


@pytest.mark.parametrize("provider", ["codex", "agy"])
def test_usage_subsets_accept_equality_and_keep_raw_trace(
    tmp_path: Path,
    provider: str,
) -> None:
    usage = {"input_tokens": 10, "output_tokens": 2}
    if provider == "codex":
        usage.update(
            cached_input_tokens=10,
            cache_write_input_tokens=0,
            reasoning_output_tokens=2,
        )
    else:
        usage.update(cache_read_tokens=10, thinking_tokens=2, total_tokens=12)
    trace_path = tmp_path / "cli.stdout.jsonl"
    raw = _usage_trace(
        trace_path, provider, usage, usage if provider == "agy" else None
    )

    parsed = runner._parse_usage(provider, trace_path, "test-model")

    assert parsed["terminal_success"] is True
    assert parsed["complete"] is True
    assert parsed["errors"] == []
    assert parsed["final_usage"] == usage
    assert trace_path.read_text(encoding="utf-8") == raw


@pytest.mark.parametrize(
    "provider,source,field,parent_field",
    [
        ("codex", "final", "cached_input_tokens", "input_tokens"),
        ("codex", "final", "reasoning_output_tokens", "output_tokens"),
        ("agy", "final", "cache_read_tokens", "input_tokens"),
        ("agy", "final", "thinking_tokens", "output_tokens"),
        ("agy", "step", "cache_read_tokens", "input_tokens"),
        ("agy", "step", "thinking_tokens", "output_tokens"),
    ],
)
def test_usage_subsets_exceeding_parent_invalidate_telemetry_only(
    tmp_path: Path,
    provider: str,
    source: str,
    field: str,
    parent_field: str,
) -> None:
    final_usage = {"input_tokens": 10, "output_tokens": 2}
    step_usage = None
    if provider == "codex":
        final_usage.update(
            cached_input_tokens=0, cache_write_input_tokens=0, reasoning_output_tokens=0
        )
    else:
        final_usage.update(cache_read_tokens=0, thinking_tokens=0, total_tokens=12)
        step_usage = final_usage.copy()
    target = final_usage if source == "final" else step_usage
    assert target is not None
    target[field] = target[parent_field] + 1
    trace_path = tmp_path / "cli.stdout.jsonl"
    raw = _usage_trace(trace_path, provider, final_usage, step_usage)

    parsed = runner._parse_usage(provider, trace_path, "test-model")

    assert parsed["terminal_success"] is True
    assert parsed["terminal_errors"] == []
    assert parsed["complete"] is False
    label = "final usage" if source == "final" else "agy agent_response usage"
    assert f"{label}.{field} exceeds {label}.{parent_field}" in parsed["errors"]
    if source == "step":
        assert parsed["preterminal_step_usage"]["invalid_events"] == 1
    assert trace_path.read_text(encoding="utf-8") == raw


@pytest.mark.parametrize("provider", ["codex", "agy"])
def test_reported_success_with_both_usage_subsets_invalid_is_not_complete(
    tmp_path: Path,
    provider: str,
) -> None:
    usage = {"input_tokens": 10, "output_tokens": 2}
    if provider == "codex":
        usage.update(
            cached_input_tokens=11,
            cache_write_input_tokens=0,
            reasoning_output_tokens=3,
        )
    else:
        usage.update(cache_read_tokens=11, thinking_tokens=3, total_tokens=12)
    trace_path = tmp_path / "cli.stdout.jsonl"
    raw = _usage_trace(
        trace_path, provider, usage, usage if provider == "agy" else None
    )

    parsed = runner._parse_usage(provider, trace_path, "test-model")

    assert parsed["terminal_success"] is True
    assert parsed["complete"] is False
    assert len([error for error in parsed["errors"] if "exceeds" in error]) >= 2
    assert trace_path.read_text(encoding="utf-8") == raw


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
        assert summary["cli_usage"]["preterminal_step_usage"]["unique_steps_with_valid_usage"] == 2
        assert summary["cli_usage"]["preterminal_step_usage"]["observed_unique_step_sum"] == (
            summary["cli_usage"]["final_usage"])
        assert summary["cli_usage"]["preterminal_step_usage"]["reconciles_with_final"] is True
        assert "local-conversation-id" not in (run_dir / "run.json").read_text(encoding="utf-8")
        assert "private response text" not in (run_dir / "run.json").read_text(encoding="utf-8")
    else:
        assert "workspace-write" in argv
        assert summary["cli_usage"]["preterminal_step_usage"] is None
        assert "local-thread-id" not in (run_dir / "run.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("scenario,duplicate_count,conflict_count,reconciles,complete", [
    ("agy_duplicate_step", 1, 0, True, True),
    ("agy_conflicting_step", 0, 1, None, False),
    ("agy_final_usage_mismatch", 0, 0, False, False),
])
def test_agy_preterminal_usage_deduplicates_and_reconciles(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
    scenario: str, duplicate_count: int, conflict_count: int,
    reconciles: bool | None, complete: bool,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", scenario)
    run_dir, summary = run_development_arm(
        arm="N", provider="agy", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
    )
    usage = summary["cli_usage"]
    steps = usage["preterminal_step_usage"]
    assert summary["execution_status"] == "artifacts_ready_for_inspection"
    assert summary["controlled_comparison_eligible"] is False
    assert usage["terminal_success"] is True
    assert usage["complete"] is complete
    assert steps["unique_steps_with_valid_usage"] == 2
    assert steps["duplicate_identical_events_deduplicated"] == duplicate_count
    assert steps["contradictory_duplicate_events"] == conflict_count
    assert steps["reconciles_with_final"] is reconciles
    assert steps["observed_unique_step_sum"] == {
        "input_tokens": 30, "output_tokens": 9, "thinking_tokens": 3,
        "cache_read_tokens": 1, "total_tokens": 39,
    }
    assert "step_index" not in (run_dir / "run.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("scenario,error_fragment,summary_field", [
    ("agy_active_agent", "agent_response steps without DONE", "unfinished_agent_response_steps"),
    ("agy_bad_both_arithmetic", "total_tokens differs", "final_arithmetic_valid"),
    ("agy_bad_final_arithmetic", "total_tokens differs", "final_arithmetic_valid"),
    ("agy_index_collision", "step_index collisions", "cross_type_index_collisions"),
    ("agy_tool_index_string", "malformed step_update", "malformed_step_update_events"),
    ("agy_tool_state_malformed", "malformed step_update", "malformed_step_update_events"),
])
def test_agy_step_stream_anomalies_invalidate_telemetry_only(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
    scenario: str, error_fragment: str, summary_field: str,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", scenario)
    run_dir, summary = run_development_arm(
        arm="N", provider="agy", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
    )
    usage = summary["cli_usage"]
    steps = usage["preterminal_step_usage"]
    assert summary["execution_status"] == "artifacts_ready_for_inspection"
    assert summary["controlled_comparison_eligible"] is False
    assert usage["terminal_success"] is True
    assert usage["complete"] is False
    assert steps["step_usage_complete"] is False or steps["final_arithmetic_valid"] is False
    assert steps["reconciles_with_final"] is None
    assert any(error_fragment in error for error in usage["errors"])
    if summary_field == "final_arithmetic_valid":
        assert steps[summary_field] is False
    else:
        assert steps[summary_field] >= 1
    assert "private response text" not in (run_dir / "run.json").read_text(encoding="utf-8")


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
