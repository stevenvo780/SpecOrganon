"""Synthetic custody tests for the read-only development observation CLI."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "observe_development_run.py"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).parent))
from run_development_arm import (  # noqa: E402
    _assembled_prompt,
    _parse_usage,
    _toolkit_fingerprint,
    run_development_arm,
)
import run_development_arm as runner  # noqa: E402
from test_run_development_arm import FAKE_CLI, fake_t_setup  # noqa: E402


def _record(path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}


def _write_summary(run_dir: Path, summary: dict[str, Any]) -> None:
    (run_dir / "run.json").write_text(
        json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8"
    )


def _pilot(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    run_dir = tmp_path / "pilot"
    work = run_dir / "work"
    work.mkdir(parents=True)
    for name, content in (
        ("task.md", "task input\n"),
        ("source_manifest.json", '{"selection": "synthetic"}\n'),
        ("sample_first_complete_week.csv", "t,kWh\n0,1\n"),
        ("common.md", "common prompt\n"),
        ("arm.md", "assigned arm\n"),
        ("analysis.py", "raise AssertionError('generated code must never execute')\n"),
        ("report.md", "private report body should not appear in observation\n"),
    ):
        (work / name).write_text(content, encoding="utf-8")
    (run_dir / "prompt.txt").write_text(
        _assembled_prompt("N", (work / "common.md").read_bytes(),
                          (work / "arm.md").read_bytes()),
        encoding="utf-8",
    )
    (run_dir / "cli.stdout.jsonl").write_text(
        '{"type":"thread.started","thread_id":"private-thread-id"}\n'
        '{"type":"turn.completed","usage":{"input_tokens":20,'
        '"cached_input_tokens":2,"cache_write_input_tokens":0,'
        '"output_tokens":8,"reasoning_output_tokens":1}}\n',
        encoding="utf-8",
    )
    (run_dir / "cli.stderr").write_text("private stderr\n", encoding="utf-8")
    packet = {
        name: _record(work / name)
        for name in (
            "task.md",
            "source_manifest.json",
            "sample_first_complete_week.csv",
        )
    }
    summary: dict[str, Any] = {
        "schema": 1,
        "classification": "exposed_development_unsealed",
        "arm": "N",
        "provider_cli": "codex",
        "requested_model": "synthetic-model",
        "requested_effort": "medium",
        "tool_policy": "default",
        "execution_status": "artifacts_ready_for_inspection",
        "packet": packet,
        "packet_after": packet.copy(),
        "packet_unchanged": True,
        "prompt": {
            "assembled_sha256": _record(run_dir / "prompt.txt")["sha256"],
            "common_sha256": _record(work / "common.md")["sha256"],
            "arm_sha256": _record(work / "arm.md")["sha256"],
        },
        "artifacts": {
            name: _record(work / name) for name in ("analysis.py", "report.md")
        },
        "cli": {
            "stdout": _record(run_dir / "cli.stdout.jsonl"),
            "stderr": _record(run_dir / "cli.stderr"),
            "timed_out": False,
            "exit_code": 0,
        },
        "cli_usage": _parse_usage(
            "codex", run_dir / "cli.stdout.jsonl", "synthetic-model"
        ),
        "analysis_replay": None,
        "toolkit": None,
        "t_ledger": None,
        "provider_request_id": None,
        "price": None,
        "cost": None,
        "controlled_comparison_eligible": False,
    }
    _write_summary(run_dir, summary)
    return run_dir, summary


def _invoke(run_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(run_dir)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_complete_observation_checks_bytes_and_keeps_claims_local(
    tmp_path: Path,
) -> None:
    run_dir, summary = _pilot(tmp_path)
    result = _invoke(run_dir)
    assert result.returncode == 0, result.stderr
    observation = json.loads(result.stdout)
    assert observation["classification"] == "development_observation_unsealed"
    assert observation["run_json_sha256"] == _record(run_dir / "run.json")["sha256"]
    assert observation["execution_status"] == "artifacts_ready_for_inspection"
    assert (
        observation["cli_usage"]["origin"]
        == "local_cli_jsonl_not_authenticated_provider_receipt"
    )
    assert (
        observation["cli_usage"]["final_usage"] == summary["cli_usage"]["final_usage"]
    )
    assert observation["cli_usage"]["final_usage"]["input_tokens"] == 20
    assert (
        observation["verified_inputs"]["work/task.md"] == summary["packet"]["task.md"]
    )
    assert (
        observation["verified_artifacts"]["work/analysis.py"]
        == summary["artifacts"]["analysis.py"]
    )
    assert (
        observation["verified_streams"]["cli.stdout.jsonl"] == summary["cli"]["stdout"]
    )
    assert observation["provider_request_ids"] is None
    assert observation["authenticated_model_id"] is None
    assert observation["authenticated_model_version"] is None
    assert observation["authenticated_cost_usd"] is None
    assert observation["authenticated_agent_attribution"] is None
    assert observation["cap_status"] == "unknown"
    assert observation["controlled_comparison_eligible"] is False
    assert observation["criterion_4"] == "not_assessed"
    assert "attempts" not in observation
    assert "private-thread-id" not in result.stdout
    assert "private report body" not in result.stdout
    assert not (run_dir / "work" / "generated_code_was_run").exists()


@pytest.mark.parametrize("provider", ["agy", "codex"])
def test_observes_directory_emitted_by_real_runner_with_existing_fake_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    executable = fake_bin / provider
    executable.write_text(FAKE_CLI, encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ["PATH"])
    run_dir, summary = run_development_arm(
        arm="N",
        provider=provider,
        model="test-model",
        effort="medium",
        output_root=tmp_path / "runner-output",
        timeout_seconds=10,
    )
    assert summary["execution_status"] == "artifacts_ready_for_inspection"
    assert "no_command_tool_trace" not in summary["cli_usage"]
    assert not (run_dir / "analysis_replay.stdout").exists()
    result = _invoke(run_dir)
    assert result.returncode == 0, result.stderr
    observation = json.loads(result.stdout)
    assert observation["execution_status"] == summary["execution_status"]
    assert (
        observation["cli_usage"]["final_usage"] == summary["cli_usage"]["final_usage"]
    )
    assert (
        observation["verified_artifacts"]["work/analysis.py"]
        == summary["artifacts"]["analysis.py"]
    )
    assert observation["verified_streams"]["cli.stderr"] == summary["cli"]["stderr"]
    assert not (run_dir / "analysis_replay.stdout").exists()


@pytest.mark.parametrize("arm", ["N", "S", "T"])
def test_observer_verifies_opencode_local_receipt_for_each_arm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arm: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    executable = fake_bin / "opencode"
    executable.write_text(FAKE_CLI, encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ["PATH"])
    wheel = None
    if arm == "T":
        wheel = tmp_path / "specorganon-0.1.0-py3-none-any.whl"
        wheel.write_bytes(b"synthetic wheel fixture, not installed\n")
        monkeypatch.setattr(runner, "_setup_toolkit", fake_t_setup)
    run_dir, summary = run_development_arm(
        arm=arm, provider="opencode", model="minimax/MiniMax-M3",
        effort="uncontrolled", output_root=tmp_path / "runs", timeout_seconds=10,
        toolkit_wheel=wheel,
    )
    expected_status = (
        "t_tool_execution_unverified" if arm == "T"
        else "artifacts_ready_for_inspection"
    )
    assert summary["execution_status"] == expected_status
    result = _invoke(run_dir)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["execution_status"] == expected_status
    assert observed["provider_cli"] == "opencode"
    assert observed["requested_model"] == "minimax/MiniMax-M3"
    assert observed["requested_effort"] == "uncontrolled"
    assert observed["cli_usage"]["complete"] is True
    assert observed["cli_usage"]["final_usage"] == summary["cli_usage"]["final_usage"]
    assert observed["verified_streams"]["cli.stdout.jsonl"] == summary["cli"]["stdout"]
    assert observed["provider_request_ids"] is None
    assert observed["authenticated_model_id"] is None
    assert observed["authenticated_cost_usd"] is None
    assert observed["controlled_comparison_eligible"] is False
    assert observed["criterion_4"] == "not_assessed"
    assert "private-local-session-id" not in result.stdout
    if arm == "T":
        assert observed["verified_artifacts"]["work/case/organon.json"] is not None
        assert observed["t_process_trace"]["tool_ledger_publish_count"] == 0
        assert observed["t_process_trace"]["other_ledger_write_count"] >= 1
        summary["t_process_trace"]["tool_ledger_publish_count"] = 2
        summary["execution_status"] = "artifacts_ready_for_inspection"
        _write_summary(run_dir, summary)
        forged = _invoke(run_dir)
        assert forged.returncode == 2
        assert "T process trace counts differ" in forged.stderr


def test_observer_preserves_opencode_absent_optional_total(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    executable = fake_bin / "opencode"
    executable.write_text(FAKE_CLI, encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_SCENARIO", "opencode_missing_usage")
    run_dir, summary = run_development_arm(
        arm="N", provider="opencode", model="minimax/MiniMax-M3",
        effort="uncontrolled", output_root=tmp_path / "runs", timeout_seconds=10,
    )
    assert summary["execution_status"] == "artifacts_ready_for_inspection"
    result = _invoke(run_dir)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["cli_usage"]["terminal_success"] is True
    assert observed["cli_usage"]["complete"] is False
    assert observed["cli_usage"]["final_usage"]["total_tokens"] is None
    assert observed["cli_usage"]["final_usage"]["input_tokens"] == 30
    assert observed["controlled_comparison_eligible"] is False


@pytest.mark.parametrize("scenario", [
    "opencode_open_step", "opencode_tool_calls_no_tool", "opencode_overlapping_steps",
])
def test_observer_rejects_forged_opencode_green_and_model_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    executable = fake_bin / "opencode"
    executable.write_text(FAKE_CLI, encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_SCENARIO", scenario)
    run_dir, summary = run_development_arm(
        arm="N", provider="opencode", model="minimax/MiniMax-M3",
        effort="uncontrolled", output_root=tmp_path / "runs", timeout_seconds=10,
    )
    assert summary["execution_status"] == "cli_internal_failure"
    honest = _invoke(run_dir)
    assert honest.returncode == 0, honest.stderr
    assert json.loads(honest.stdout)["cli_usage"]["terminal_success"] is False

    summary["execution_status"] = "artifacts_ready_for_inspection"
    summary["cli_usage"].update(
        terminal_success=True, complete=True, terminal_errors=[], errors=[],
    )
    _write_summary(run_dir, summary)
    forged = _invoke(run_dir)
    assert forged.returncode == 2
    assert "cli_usage differs from the verified local CLI stream" in forged.stderr

    summary["execution_status"] = "cli_internal_failure"
    summary["cli_usage"] = _parse_usage(
        "opencode", run_dir / "cli.stdout.jsonl", "minimax/MiniMax-M3"
    )
    summary["cli_usage"]["observed_model"] = "minimax/MiniMax-M3"
    _write_summary(run_dir, summary)
    forged_model = _invoke(run_dir)
    assert forged_model.returncode == 2
    assert "cli_usage differs from the verified local CLI stream" in forged_model.stderr


def test_observer_rejects_old_green_claim_for_open_codex_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    executable = fake_bin / "codex"
    executable.write_text(FAKE_CLI, encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_SCENARIO", "codex_open_item")
    run_dir, summary = run_development_arm(
        arm="N", provider="codex", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
    )
    assert summary["execution_status"] == "cli_internal_failure"
    observed = _invoke(run_dir)
    assert observed.returncode == 0, observed.stderr
    observation = json.loads(observed.stdout)
    assert observation["execution_status"] == "cli_internal_failure"
    assert observation["cli_usage"]["terminal_success"] is False
    assert observation["cli_usage"]["complete"] is False

    # Reproduce the old parser's false green while preserving the stream byte record.
    summary["execution_status"] = "artifacts_ready_for_inspection"
    summary["cli_usage"].update(
        terminal_success=True, complete=True, terminal_errors=[], errors=[]
    )
    _write_summary(run_dir, summary)
    rejected = _invoke(run_dir)
    assert rejected.returncode == 2
    assert "cli_usage differs from the verified local CLI stream" in rejected.stderr


@pytest.mark.parametrize("scenario,violating,uninspectable", [
    ("agy_command_tool", 1, 0),
    ("agy_tool_name_missing", 1, 0),
    ("agy_tool_name_array", 1, 0),
    ("agy_unknown_command_step", 0, 1),
])
def test_observer_rejects_old_no_command_false_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: str,
    violating: int, uninspectable: int,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    executable = fake_bin / "agy"
    executable.write_text(FAKE_CLI, encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_SCENARIO", scenario)
    run_dir, summary = run_development_arm(
        arm="N", provider="agy", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
        agy_no_command_tool=True,
    )
    assert summary["execution_status"] == "cli_internal_failure"
    observed = json.loads(_invoke(run_dir).stdout)
    assert observed["execution_status"] == "cli_internal_failure"
    assert observed["cli_usage"]["no_command_tool_trace"]["violating_tool_steps"] == violating
    assert observed["cli_usage"]["no_command_tool_trace"]["uninspectable_step_events"] == uninspectable

    summary["execution_status"] = "artifacts_ready_for_inspection"
    summary["cli_usage"] = _parse_usage("agy", run_dir / "cli.stdout.jsonl", "test-model")
    _write_summary(run_dir, summary)
    tampered = _invoke(run_dir)
    assert tampered.returncode == 2
    assert "cli_usage differs" in tampered.stderr

    summary["tool_policy"] = "default"
    _write_summary(run_dir, summary)
    downgraded = _invoke(run_dir)
    assert downgraded.returncode == 2
    assert "tool policy differs from the verified prompt bytes" in downgraded.stderr


def test_observer_accepts_reported_write_only_no_command_pilot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    executable = fake_bin / "agy"
    executable.write_text(FAKE_CLI, encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ["PATH"])
    run_dir, summary = run_development_arm(
        arm="S", provider="agy", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
        agy_no_command_tool=True,
    )
    assert summary["execution_status"] == "artifacts_ready_for_inspection"
    observation = json.loads(_invoke(run_dir).stdout)
    assert observation["execution_status"] == "artifacts_ready_for_inspection"
    assert observation["cli_usage"]["no_command_tool_trace"]["allowed_tool_steps"] == 1
    assert observation["cli_usage"]["no_command_tool_trace"]["violating_tool_steps"] == 0
    summary["cli_usage"].pop("no_command_tool_trace")
    _write_summary(run_dir, summary)
    legacy_observation = json.loads(_invoke(run_dir).stdout)
    assert legacy_observation["execution_status"] == "artifacts_ready_for_inspection"
    assert legacy_observation["cli_usage"]["no_command_tool_trace"]["allowed_tool_steps"] == 1


@pytest.mark.parametrize("status", ["preparing", "preflight_failure"])
def test_incomplete_preflight_reports_absent_copies_without_claiming_usage(
    tmp_path: Path,
    status: str,
) -> None:
    run_dir, summary = _pilot(tmp_path)
    (run_dir / "work" / "arm.md").unlink()
    for name in ("cli.stdout.jsonl", "cli.stderr"):
        (run_dir / name).unlink()
    for name in ("analysis.py", "report.md"):
        (run_dir / "work" / name).unlink()
    summary.update(
        {
            "execution_status": status,
            "cli": None,
            "cli_usage": None,
            "packet_after": None,
            "packet_unchanged": None,
            "artifacts": {},
        }
    )
    if status == "preflight_failure":
        summary["preflight_error"] = "assigned prompt files could not be copied"
    _write_summary(run_dir, summary)
    result = _invoke(run_dir)
    assert result.returncode == 0, result.stderr
    observation = json.loads(result.stdout)
    assert observation["observation_state"] == "partial"
    assert observation["cli_usage"] is None
    assert "work/arm.md" in observation["unavailable_materials"]
    assert "cli.stdout.jsonl" in observation["unavailable_materials"]
    assert "work/arm.md" not in observation["verified_inputs"]
    assert observation["verified_artifacts"] == {}


@pytest.mark.parametrize(
    "relative",
    [
        "cli.stdout.jsonl",
        "cli.stderr",
        "work/analysis.py",
        "work/report.md",
        "work/task.md",
        "prompt.txt",
        "work/common.md",
    ],
)
def test_tampered_recorded_bytes_are_rejected(tmp_path: Path, relative: str) -> None:
    run_dir, _ = _pilot(tmp_path)
    path = run_dir / relative
    content = path.read_bytes()
    path.write_bytes((b"X" if content[:1] != b"X" else b"Y") + content[1:])
    result = _invoke(run_dir)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "differs from" in result.stderr


@pytest.mark.parametrize(
    "relative",
    [
        "cli.stdout.jsonl",
        "cli.stderr",
        "work/analysis.py",
        "work/task.md",
        "prompt.txt",
    ],
)
def test_missing_recorded_bytes_are_rejected(tmp_path: Path, relative: str) -> None:
    run_dir, _ = _pilot(tmp_path)
    (run_dir / relative).unlink()
    result = _invoke(run_dir)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "absent or unsafe" in result.stderr


@pytest.mark.parametrize(
    "relative", ["run.json", "cli.stdout.jsonl", "work/analysis.py"]
)
def test_recorded_symlink_is_rejected(tmp_path: Path, relative: str) -> None:
    run_dir, _ = _pilot(tmp_path)
    original = run_dir / relative
    moved = original.with_name(original.name + ".real")
    original.rename(moved)
    original.symlink_to(moved)
    result = _invoke(run_dir)
    assert result.returncode == 2
    assert result.stdout == ""


def test_run_directory_symlink_and_relative_path_are_rejected(tmp_path: Path) -> None:
    run_dir, _ = _pilot(tmp_path)
    linked = tmp_path / "pilot-link"
    linked.symlink_to(run_dir, target_is_directory=True)
    assert _invoke(linked).returncode == 2
    assert _invoke(Path("relative-pilot")).returncode == 2


@pytest.mark.parametrize(
    "injection",
    [
        '"schema":1,"schema":1',
        '"schema":1,"nonfinite":NaN',
        '"schema":1,"nonfinite":1e999',
    ],
)
def test_forged_duplicate_or_nonfinite_json_is_rejected(
    tmp_path: Path, injection: str
) -> None:
    run_dir, _ = _pilot(tmp_path)
    summary_file = run_dir / "run.json"
    raw = summary_file.read_text(encoding="utf-8")
    summary_file.write_text("{" + injection + "," + raw.lstrip()[1:], encoding="utf-8")
    result = _invoke(run_dir)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "run.json" in result.stderr


def test_partial_record_with_cli_claim_is_rejected(tmp_path: Path) -> None:
    run_dir, summary = _pilot(tmp_path)
    summary["execution_status"] = "preflight_failure"
    summary["preflight_error"] = "synthetic failure"
    _write_summary(run_dir, summary)
    result = _invoke(run_dir)
    assert result.returncode == 2
    assert "partial run has inconsistent" in result.stderr


def test_preparing_run_does_not_present_unrecorded_bytes_as_absent_or_verified(
    tmp_path: Path,
) -> None:
    run_dir, summary = _pilot(tmp_path)
    summary.update(
        {
            "execution_status": "preparing",
            "cli": None,
            "cli_usage": None,
            "packet_after": None,
            "packet_unchanged": None,
            "artifacts": {},
        }
    )
    _write_summary(run_dir, summary)
    result = _invoke(run_dir)
    assert result.returncode == 0, result.stderr
    observation = json.loads(result.stdout)
    assert "cli.stdout.jsonl" in observation["unrecorded_materials"]
    assert "work/analysis.py" in observation["unrecorded_materials"]
    assert "cli.stdout.jsonl" not in observation["unavailable_materials"]
    assert observation["verified_streams"] == {}
    assert observation["verified_artifacts"] == {}


def test_forged_usage_cannot_override_verified_stream(tmp_path: Path) -> None:
    run_dir, summary = _pilot(tmp_path)
    summary["cli_usage"]["final_usage"]["input_tokens"] += 1000
    _write_summary(run_dir, summary)
    result = _invoke(run_dir)
    assert result.returncode == 2
    assert "cli_usage differs" in result.stderr


def test_successful_cli_cannot_claim_launch_failure(tmp_path: Path) -> None:
    run_dir, summary = _pilot(tmp_path)
    summary["cli"]["launch_error"] = "OSError: executable could not start"
    _write_summary(run_dir, summary)
    result = _invoke(run_dir)
    assert result.returncode == 2
    assert "inconsistent launch failure" in result.stderr


def test_missing_artifact_is_explicit_on_failed_cli_run(tmp_path: Path) -> None:
    run_dir, summary = _pilot(tmp_path)
    (run_dir / "work" / "report.md").unlink()
    summary["artifacts"]["report.md"] = None
    summary["execution_status"] = "required_artifact_missing"
    _write_summary(run_dir, summary)
    result = _invoke(run_dir)
    assert result.returncode == 0, result.stderr
    observation = json.loads(result.stdout)
    assert observation["observation_state"] == "partial"
    assert "work/report.md" in observation["unavailable_materials"]
    assert "work/report.md" not in observation["verified_artifacts"]


def test_existing_replay_streams_are_verified_without_executing_generated_code(
    tmp_path: Path,
) -> None:
    run_dir, summary = _pilot(tmp_path)
    (run_dir / "analysis_replay.stdout").write_text(
        "preexisting replay output\n", encoding="utf-8"
    )
    (run_dir / "analysis_replay.stderr").write_text("", encoding="utf-8")
    summary.update(
        {
            "execution_status": "output_replayed",
            "reviewed_analysis_sha256": summary["artifacts"]["analysis.py"]["sha256"],
            "replay_material_mismatches": [],
            "analysis_replay": {
                "stdout": _record(run_dir / "analysis_replay.stdout"),
                "stderr": _record(run_dir / "analysis_replay.stderr"),
                "timed_out": False,
                "exit_code": 0,
            },
        }
    )
    _write_summary(run_dir, summary)
    result = _invoke(run_dir)
    assert result.returncode == 0, result.stderr
    observation = json.loads(result.stdout)
    assert (
        observation["verified_streams"]["analysis_replay.stdout"]
        == summary["analysis_replay"]["stdout"]
    )
    assert observation["execution_status"] == "output_replayed"
    summary["analysis_replay"]["launch_error"] = "OSError: replay could not start"
    _write_summary(run_dir, summary)
    forged = _invoke(run_dir)
    assert forged.returncode == 2
    assert "inconsistent launch failure" in forged.stderr


def test_sandbox_setup_timeout_is_observed_as_launch_failure(
    tmp_path: Path,
) -> None:
    run_dir, summary = _pilot(tmp_path)
    for suffix in ("stdout", "stderr"):
        (run_dir / f"analysis_replay.{suffix}").write_bytes(b"")
    summary.update({
        "execution_status": "analysis_replay_launch_failure",
        "reviewed_analysis_sha256": summary["artifacts"]["analysis.py"]["sha256"],
        "replay_material_mismatches": [],
        "analysis_replay": {
            "stdout": _record(run_dir / "analysis_replay.stdout"),
            "stderr": _record(run_dir / "analysis_replay.stderr"),
            "timed_out": True, "exit_code": None,
            "launch_error": "sandbox setup timed out",
            "sandbox": {
                "backend": "linux_landlock_seccomp_rlimit_single_process",
                "enforced": False,
            },
        },
    })
    _write_summary(run_dir, summary)
    observed = _invoke(run_dir)
    assert observed.returncode == 0, observed.stderr
    assert json.loads(observed.stdout)["execution_status"] == "analysis_replay_launch_failure"

    summary["analysis_replay"]["sandbox"]["enforced"] = True
    _write_summary(run_dir, summary)
    forged = _invoke(run_dir)
    assert forged.returncode == 2
    assert "sandbox claim is inconsistent" in forged.stderr


def test_replay_mutation_status_is_explicitly_unobservable(tmp_path: Path) -> None:
    run_dir, summary = _pilot(tmp_path)
    summary["execution_status"] = "replay_artifacts_mutated"
    _write_summary(run_dir, summary)
    result = _invoke(run_dir)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "replay_artifacts_mutated cannot be observed" in result.stderr


def test_changed_packet_before_and_after_cannot_be_presented_as_verified_input(
    tmp_path: Path,
) -> None:
    run_dir, summary = _pilot(tmp_path)
    path = run_dir / "work" / "task.md"
    path.write_text("different input\n", encoding="utf-8")
    summary["packet_after"]["task.md"] = _record(path)
    summary["packet_unchanged"] = False
    summary["execution_status"] = "public_packet_mutated"
    _write_summary(run_dir, summary)
    result = _invoke(run_dir)
    assert result.returncode == 2
    assert result.stdout == ""


def test_t_observation_verifies_setup_streams_wheel_sources_and_ledger(
    tmp_path: Path,
) -> None:
    run_dir, summary = _pilot(tmp_path)
    work = run_dir / "work"
    package = work / ".venv" / "lib" / "python3.11" / "site-packages" / "specorganon"
    package.mkdir(parents=True)
    (work / ".venv" / "bin").mkdir()
    (work / ".venv" / "bin" / "organon").write_text(
        "#!/usr/bin/env python3\n", encoding="utf-8"
    )
    (package / "__init__.py").write_text("VERSION = 1\n", encoding="utf-8")
    wheel = work / "specorganon-0.1-py3-none-any.whl"
    wheel.write_bytes(b"synthetic wheel bytes")
    steps: dict[str, dict[str, Any]] = {}
    for name in ("toolkit_venv", "toolkit_install", "toolkit_init", "toolkit_status"):
        for suffix in ("stdout", "stderr"):
            content = (
                '{"project":{"approval_policy":"signed"}}\n'
                if name == "toolkit_status" and suffix == "stdout"
                else f"{name} {suffix}\n"
            )
            (run_dir / f"{name}.{suffix}").write_text(content, encoding="utf-8")
        steps[name] = {
            "stdout": _record(run_dir / f"{name}.stdout"),
            "stderr": _record(run_dir / f"{name}.stderr"),
            "exit_code": 0,
            "timed_out": False,
        }
    case = work / "case"
    case.mkdir()
    ledger = case / "organon.json"
    ledger.write_text(
        '{"project":{"approval_policy":"signed"},"events":[{}]}\n', encoding="utf-8"
    )
    for suffix in ("stdout", "stderr"):
        content = (
            '{"project":{"approval_policy":"signed"}}\n'
            if suffix == "stdout"
            else "checked\n"
        )
        (run_dir / f"toolkit_after_status.{suffix}").write_text(
            content, encoding="utf-8"
        )
    summary["arm"] = "T"
    summary["toolkit"] = {
        "wheel": _record(wheel),
        "steps": steps,
        "toolkit_files_fingerprint_sha256": _toolkit_fingerprint(work),
        "signed_policy_verified_in_local_probe": True,
    }
    summary["t_ledger"] = {
        "present": True,
        "signed_policy": True,
        "event_count": 1,
        "sha256": _record(ledger)["sha256"],
        "toolkit_files_unchanged": True,
        "model_cli_invocations_proven": False,
        "independent_cli_status": {
            "stdout": _record(run_dir / "toolkit_after_status.stdout"),
            "stderr": _record(run_dir / "toolkit_after_status.stderr"),
            "exit_code": 0,
            "timed_out": False,
        },
    }
    summary["execution_status"] = "t_tool_execution_unverified"
    (run_dir / "prompt.txt").write_text(
        _assembled_prompt("T", (work / "common.md").read_bytes(),
                          (work / "arm.md").read_bytes()),
        encoding="utf-8",
    )
    summary["prompt"]["assembled_sha256"] = _record(run_dir / "prompt.txt")["sha256"]
    _write_summary(run_dir, summary)
    result = _invoke(run_dir)
    assert result.returncode == 0, result.stderr
    observation = json.loads(result.stdout)
    assert observation["execution_status"] == "t_tool_execution_unverified"
    assert observation["verified_inputs"][f"work/{wheel.name}"] == _record(wheel)
    assert (
        observation["verified_artifacts"]["work/case/organon.json"]["sha256"]
        == summary["t_ledger"]["sha256"]
    )
    assert (
        observation["verified_streams"]["toolkit_install.stderr"]
        == steps["toolkit_install"]["stderr"]
    )
    assert (
        observation["verified_streams"]["toolkit_after_status.stdout"]
        == summary["t_ledger"]["independent_cli_status"]["stdout"]
    )
    summary["execution_status"] = "artifacts_ready_for_inspection"
    _write_summary(run_dir, summary)
    old_green = _invoke(run_dir)
    assert old_green.returncode == 2
    assert "execution status contradicts" in old_green.stderr
    summary["execution_status"] = "t_tool_execution_unverified"
    partial = json.loads(json.dumps(summary))
    partial.update(
        {
            "execution_status": "preparing",
            "cli": None,
            "cli_usage": None,
            "packet_after": None,
            "packet_unchanged": None,
            "artifacts": {},
            "t_ledger": None,
        }
    )
    _write_summary(run_dir, partial)
    partial_result = _invoke(run_dir)
    assert partial_result.returncode == 0, partial_result.stderr
    partial_observation = json.loads(partial_result.stdout)
    assert partial_observation["observation_state"] == "partial"
    assert (
        partial_observation["verified_streams"]["toolkit_install.stderr"]
        == steps["toolkit_install"]["stderr"]
    )
    assert "cli.stdout.jsonl" in partial_observation["unrecorded_materials"]
    _write_summary(run_dir, summary)
    summary["toolkit"]["steps"]["toolkit_install"]["exit_code"] = 1
    _write_summary(run_dir, summary)
    failed_setup = _invoke(run_dir)
    assert failed_setup.returncode == 2
    assert "failed or invalid setup capture" in failed_setup.stderr
    summary["toolkit"]["steps"]["toolkit_install"]["exit_code"] = 0
    original_ledger = ledger.read_bytes()
    original_ledger_sha = summary["t_ledger"]["sha256"]
    ledger.write_text(
        '{"project":{"approval_policy":"fixture"},"events":[]}\n', encoding="utf-8"
    )
    summary["t_ledger"]["sha256"] = _record(ledger)["sha256"]
    _write_summary(run_dir, summary)
    forged_ledger = _invoke(run_dir)
    assert forged_ledger.returncode == 2
    assert "T ledger event count differs" in forged_ledger.stderr
    ledger.write_bytes(original_ledger)
    summary["t_ledger"]["sha256"] = original_ledger_sha
    _write_summary(run_dir, summary)
    (package / "__init__.py").write_text("VERSION = 2\n", encoding="utf-8")
    changed = _invoke(run_dir)
    assert changed.returncode == 2
    assert "toolkit source fingerprint differs" in changed.stderr
