"""A local fake CLI checks D-E run custody without calling paid models."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import run_development_arm as runner  # noqa: E402
from observe_development_run import observe_run_dir  # noqa: E402
from run_development_arm import (  # noqa: E402
    RunError, prepare_development_arm, replay_run_dir, run_development_arm,
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
if provider in {"codex", "opencode"}:
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
    elif scenario == "codex_open_item":
        print(json.dumps({"type": "item.started", "item": {
            "id": "item-1", "type": "command_execution"}}))
    else:
        print(json.dumps({"type": "item.completed", "item": {"type": "command_execution"}}))
    usage = None if scenario == "missing_usage" else {
        "input_tokens": 20, "cached_input_tokens": 2,
        "cache_write_input_tokens": 0, "output_tokens": 8,
        "reasoning_output_tokens": 1}
    print(json.dumps({"type": "turn.completed", "usage": usage}))
elif provider == "opencode":
    session_id = "private-local-session-id"
    def emit(kind, part=None):
        event = {"type": kind, "sessionID": session_id}
        if part is not None:
            event["part"] = part
        print(json.dumps(event))
    def part(part_id, message_id, kind, **extra):
        return {"id": part_id, "messageID": message_id, "sessionID": session_id,
                "type": kind, **extra}
    if Path(".venv/bin/organon").exists():
        case = Path("case")
        case.mkdir()
        (case / "organon.json").write_text(
            '{"project":{"approval_policy":"signed"},"events":[{}]}\n',
            encoding="utf-8")
    emit("step_start", part("part-start-1", "message-1", "step-start"))
    first_tokens = {"input": 10, "output": 4, "reasoning": 1,
                    "cache": {"read": 2, "write": 0}, "total": 17}
    if scenario == "opencode_nonadditive_total":
        first_tokens["total"] = 99
    elif scenario == "opencode_bad_usage":
        first_tokens["total"] = -1
    elif scenario == "opencode_null_total":
        first_tokens["total"] = None
    elif scenario == "opencode_missing_usage":
        del first_tokens["total"]
    elif scenario == "opencode_bool_usage":
        first_tokens["input"] = True
    elif scenario == "opencode_float_usage":
        first_tokens["output"] = 4.0
    if scenario == "opencode_overlapping_steps":
        emit("step_start", part("part-start-2", "message-2", "step-start"))
    if scenario not in {"opencode_open_step", "opencode_wrong_message"}:
        emit("step_finish", part("part-finish-1", "message-1", "step-finish",
                                 reason="tool-calls", tokens=first_tokens, cost=0))
    elif scenario == "opencode_wrong_message":
        emit("step_finish", part("part-finish-1", "message-2", "step-finish",
                                 reason="tool-calls", tokens=first_tokens, cost=0))
    if scenario == "opencode_open_step":
        sys.exit(0)
    tool = part("part-tool-1",
                "unattached-message" if scenario == "opencode_unattached_tool" else
                "message-2" if scenario == "opencode_tool_wrong_step" else "message-1",
                "tool", state={"status": "error" if scenario == "opencode_tool_error"
                               else "completed"})
    if scenario != "opencode_missing_tool_name":
        tool["tool"] = "task" if scenario == "opencode_child_task" else "write"
    if scenario not in {"opencode_tool_calls_no_tool", "opencode_tool_wrong_step"}:
        emit("tool_use", tool)
    if scenario == "opencode_duplicate_tool":
        emit("tool_use", tool)
    if scenario == "opencode_session_changed":
        session_id = "another-private-session-id"
    if scenario != "opencode_overlapping_steps":
        emit("step_start", part("part-tool-1" if scenario == "opencode_part_id_reused"
                                else "part-start-2", "message-2", "step-start"))
    if scenario == "opencode_tool_wrong_step":
        emit("tool_use", tool)
    emit("text", part("part-text-2", "message-2", "text", text="private model answer"))
    second_tokens = {"input": 20, "output": 5, "reasoning": 2,
                     "cache": {"read": 1, "write": 1}, "total": 29}
    emit("step_finish", part("part-finish-2", "message-2", "step-finish",
                             reason="tool-calls" if scenario in {"opencode_no_stop",
                                                                  "opencode_multiple_tool_steps"}
                             else "stop",
                             tokens=second_tokens, cost=0))
    if scenario == "opencode_multiple_tool_steps":
        emit("tool_use", part("part-tool-2", "message-2", "tool", tool="write",
                              state={"status": "completed"}))
        emit("step_start", part("part-start-3", "message-3", "step-start"))
        emit("text", part("part-text-3", "message-3", "text", text="private final answer"))
        emit("step_finish", part("part-finish-3", "message-3", "step-finish",
                                 reason="stop", tokens={"input": 7, "output": 3,
                                                        "reasoning": 0,
                                                        "cache": {"read": 0, "write": 0},
                                                        "total": 10}, cost=0))
    if scenario == "opencode_duplicate_finish":
        emit("step_finish", part("part-finish-2", "message-2", "step-finish",
                                 reason="stop", tokens=second_tokens, cost=0))
    if scenario == "opencode_error":
        emit("error", {"name": "LocalError"})
    if scenario == "opencode_invalid_utf8":
        sys.stdout.flush()
        sys.stdout.buffer.write(b"\xff\n")
else:
    model = sys.argv[sys.argv.index("--model") + 1]
    init_event = {"event": "init", "init": {"model": model, "cwd": str(Path.cwd())}}
    if scenario not in {"agy_ids_absent", "agy_result_id_only"}:
        init_event["conversation_id"] = (
            42 if scenario == "agy_init_id_malformed" else "local-conversation-id")
    print(json.dumps(init_event))
    if scenario in {
        "agy_unknown_event_same_id", "agy_unknown_event_mismatch",
        "agy_unknown_event_malformed", "agy_unknown_event_no_id",
        "agy_invalid_event_kind_with_id",
    }:
        unknown_event = {"event": 7 if scenario == "agy_invalid_event_kind_with_id"
                         else "message"}
        if scenario != "agy_unknown_event_no_id":
            unknown_event["conversation_id"] = (
                "local-conversation-id" if scenario == "agy_unknown_event_same_id"
                else 42 if scenario == "agy_unknown_event_malformed"
                else "another-private-conversation-id")
        print(json.dumps(unknown_event))
    for state in (() if scenario == "agy_no_tool_step" else ("ACTIVE", "DONE")):
        tool_index = "2" if scenario == "agy_tool_index_string" and state == "DONE" else 2
        tool_state = 123 if scenario == "agy_tool_state_malformed" and state == "DONE" else state
        tool_update = {"step_index": tool_index, "step_type": "tool",
                       "state": tool_state,
                       "tool_info": {"parameters": {"TargetFile": "private-name"}}}
        if scenario != "agy_tool_name_missing":
            tool_update["tool_name"] = (
                ["write_to_file"] if scenario == "agy_tool_name_array"
                else "RunCommand" if scenario == "agy_command_tool"
                else "write_to_file"
            )
        tool_event = {"event": "step_update", "step_update": tool_update}
        if state == "ACTIVE":
            if scenario == "agy_step_ids_match":
                tool_event["conversation_id"] = "local-conversation-id"
                tool_update["conversation_id"] = "local-conversation-id"
            elif scenario == "agy_step_outer_id_mismatch":
                tool_event["conversation_id"] = "another-private-conversation-id"
            elif scenario == "agy_step_nested_id_mismatch":
                tool_update["conversation_id"] = "another-private-conversation-id"
            elif scenario == "agy_step_id_malformed":
                tool_update["conversation_id"] = []
        print(json.dumps(tool_event))
    if scenario == "agy_unknown_command_step":
        print(json.dumps({"event": "step_update", "step_update": {
            "step_index": 9, "step_type": "tool_call", "tool_name": "RunCommand",
            "state": "DONE"}}))
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
    final_result = {
        "status": "FAILURE" if scenario == "agy_final_failure" else "SUCCESS",
        "usage": usage,
        "denied_actions": [{"action": "command", "secret_parameter": "do-not-copy"}]
                          if scenario == "agy_denied_actions" else []}
    if scenario not in {"agy_ids_absent", "agy_init_id_only"}:
        final_result["conversation_id"] = (
            "another-private-conversation-id" if scenario == "agy_result_id_mismatch"
            else " " if scenario == "agy_result_id_blank"
            else {"private": "id"} if scenario == "agy_result_id_malformed"
            else "local-conversation-id")
    print(json.dumps({"event": "result", "result": final_result}))
'''


@pytest.fixture
def fake_clis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("codex", "agy", "opencode"):
        executable = bin_dir / name
        executable.write_text(FAKE_CLI, encoding="utf-8")
        executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    return bin_dir


def _write_activation_dossier(path: Path, data: dict[str, object]) -> str:
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_pilot_triplet_plan(
    path: Path, dossier_sha256: str, *, schema: int = 2,
    active_budget_seconds: object = 5400,
) -> str:
    plan = {
        "schema": schema,
        "classification": "offline_exploratory_triplet_plan_unsealed",
        "status": "configuration_declared_not_authorization",
        "activation_dossier_sha256": dossier_sha256,
        "family_slots": {
            "A": {"provider_cli": "codex", "requested_model": "test-model",
                  "requested_effort": "medium", "model_version": "declared-test-version",
                  "other_model_parameters": {}},
            "B": {"provider_cli": "agy", "requested_model": "test-model-b",
                  "requested_effort": "high", "model_version": "declared-test-version-b",
                  "other_model_parameters": {}},
        },
        "planned_cells": [
            {"family_slot": slot, "arm": arm}
            for slot in ("A", "B") for arm in ("N", "S", "T")
        ],
        "limitations": ["Synthetic requested configuration only; no provider authorization."],
    }
    if schema == 2:
        plan["active_budget_seconds"] = active_budget_seconds
    return _write_activation_dossier(path, plan)


@pytest.fixture
def activation_dossier_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, dict[str, object]]:
    original_root = runner.ROOT
    root = tmp_path / "asset-root"
    for relative in runner.DOSSIER_ASSET_PATHS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        content = (b"local fixture wheel\n" if relative.startswith("dist/")
                   else (original_root / relative).read_bytes())
        target.write_bytes(content)
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setattr(runner, "PACKET", root / "cases/building_energy")
    monkeypatch.setattr(runner, "PROMPTS", root / "experiments/development/energy_pilot")
    dossier = json.loads((original_root / "experiments/development/energy_pilot"
                          / "activation_dossier_2026-09-27.json").read_text(encoding="utf-8"))
    dossier["fixed_local_assets_sha256"] = {
        relative: runner._sha256(root / relative) for relative in runner.DOSSIER_ASSET_PATHS
    }
    path = tmp_path / "activation.json"
    _write_activation_dossier(path, dossier)
    return root, path, dossier


def fake_t_setup(
    work: Path, run_dir: Path, wheel: Path | None, _timeout_seconds: int,
    _env: dict[str, str], *, expected_wheel_sha256: str | None = None,
    active_deadline: float | None = None,
) -> dict[str, object]:
    """Provide verifiable local T fixture files, without installing a wheel."""
    assert wheel is not None
    copied = work / wheel.name
    copied.write_bytes(wheel.read_bytes())
    if expected_wheel_sha256 is not None:
        assert runner._sha256(copied) == expected_wheel_sha256
    executable = work / ".venv" / "bin" / "organon"
    executable.parent.mkdir(parents=True)
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "print(json.dumps({'project': {'approval_policy': 'signed'}}))\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    package = work / ".venv" / "lib" / "python3.11" / "site-packages" / "specorganon"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("VERSION = 1\n", encoding="utf-8")
    steps: dict[str, dict[str, object]] = {}
    for name in ("toolkit_venv", "toolkit_install", "toolkit_init", "toolkit_status"):
        remaining = (max(0.0, active_deadline - time.monotonic())
                     if active_deadline is not None else None)
        for suffix in ("stdout", "stderr"):
            content = ('{"project":{"approval_policy":"signed"}}\n'
                       if name == "toolkit_status" and suffix == "stdout"
                       else f"{name} {suffix}\n")
            (run_dir / f"{name}.{suffix}").write_text(content, encoding="utf-8")
        steps[name] = {
            "stdout": runner._file_record(run_dir / f"{name}.stdout"),
            "stderr": runner._file_record(run_dir / f"{name}.stderr"),
            "exit_code": 0,
            "timed_out": False,
            "wall_seconds": 0.0,
            "timeout_seconds": (min(_timeout_seconds, remaining)
                                if remaining is not None else _timeout_seconds),
            "timeout_cap": ("run_budget" if remaining is not None
                            and remaining <= _timeout_seconds else "stage"),
        }
    return {
        "wheel": runner._file_record(copied),
        "steps": steps,
        "toolkit_files_fingerprint_sha256": runner._toolkit_fingerprint(work),
        "signed_policy_verified_in_local_probe": True,
    }


@pytest.mark.parametrize("arm,provider,model,effort,no_command", [
    ("N", "codex", "test-model", "medium", False),
    ("S", "agy", "test-model", "high", True),
    ("T", "opencode", "minimax/MiniMax-M3", "uncontrolled", False),
])
def test_prepare_only_pins_inputs_and_never_launches(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
    arm: str, provider: str, model: str, effort: str, no_command: bool,
) -> None:
    wheel = None
    if arm == "T":
        wheel = tmp_path / "specorganon-0.1.0-py3-none-any.whl"
        wheel.write_bytes(b"offline fixture wheel\n")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("prepare-only launched a command or toolkit setup")

    monkeypatch.setattr(runner, "_capture", forbidden)
    monkeypatch.setattr(runner, "_setup_toolkit", forbidden)
    monkeypatch.setattr(runner, "_system_strace", forbidden)
    monkeypatch.setenv("PRIVATE_ENV_SENTINEL", "never-write-this-environment-value")
    run_dir, prepared = prepare_development_arm(
        arm=arm, provider=provider, model=model, effort=effort,
        output_root=tmp_path / "runs", timeout_seconds=11,
        toolkit_wheel=wheel, agy_no_command_tool=no_command,
    )

    saved = (run_dir / "prepared.json").read_text(encoding="utf-8")
    assert json.loads(saved) == prepared
    assert "never-write-this-environment-value" not in saved
    assert prepared["classification"] == "development_prompt_preparation_unsealed"
    assert prepared["status"] == "no_go_for_provider_calls"
    assert prepared["execution_status"] == "prepared_without_execution"
    assert prepared["provider_calls"] == 0
    for flag in ("execution_ready", "launch_ready", "tool_parity_verified",
                 "human_review_verified", "controlled_comparison_eligible"):
        assert prepared[flag] is False
    assert prepared["cap_status"] == "unknown"
    assert prepared["provider_command"] == str(fake_clis / provider)
    assert prepared["provider_argv"][0] == prepared["provider_command"]
    assert prepared["provider_command_resolved_on_path"] is True
    assert prepared["packet"] == {
        name: runner._file_record(run_dir / "work" / name) for name in runner.PUBLIC_FILES
    }
    assert prepared["prompt"]["common_sha256"] == runner._sha256(run_dir / "work/common.md")
    assert prepared["prompt"]["arm_sha256"] == runner._sha256(run_dir / "work/arm.md")
    prompt = (run_dir / "prompt.txt").read_text(encoding="utf-8")
    assert prepared["prompt_file"] == runner._file_record(run_dir / "prompt.txt")
    assert prepared["prompt"]["assembled_sha256"] == hashlib.sha256(prompt.encode()).hexdigest()
    if provider == "agy":
        assert prepared["prompt_transport"] == "argv"
        assert prepared["provider_argv"][prepared["provider_argv"].index("--print") + 1] == prompt
        assert prepared["stdin"] == {"mode": "devnull", "sha256": None, "bytes": 0}
        assert "do not call run_command, RunCommand" in prompt
    else:
        assert prepared["prompt_transport"] == "stdin"
        assert prepared["stdin"] == {
            "mode": "pipe", "sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "bytes": len(prompt.encode()),
        }
    if wheel is not None:
        assert prepared["wheel"] == runner._file_record(wheel)
        assert not (run_dir / "work" / wheel.name).exists()
    else:
        assert prepared["wheel"] is None
    assert set(path.name for path in (run_dir / "work").iterdir()) == {
        *runner.PUBLIC_FILES, "common.md", "arm.md",
    }
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((run_dir / "prepared.json").stat().st_mode) == 0o600
    assert not (run_dir / "run.json").exists()
    assert not (run_dir / "cli.stdout.jsonl").exists()
    assert not (run_dir / "cli.stderr").exists()
    assert not (run_dir / "work/fake_argv.json").exists()
    with pytest.raises(RunError, match="run directory, summary or work directory"):
        replay_run_dir(run_dir, "0" * 64)


def test_prepare_only_works_without_provider_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty_path = tmp_path / "empty-bin"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))
    run_dir, prepared = prepare_development_arm(
        arm="N", provider="codex", model="test-model", effort="low",
        output_root=tmp_path / "runs",
    )
    assert prepared["provider_command"] == "codex"
    assert prepared["provider_command_resolved_on_path"] is False
    assert prepared["execution_ready"] is False
    assert (run_dir / "prepared.json").exists()


@pytest.mark.parametrize("provider,model,effort", [
    ("codex", "test-model", "medium"),
    ("agy", "test-model", "medium"),
    ("opencode", "minimax/MiniMax-M3", "uncontrolled"),
])
def test_prepare_only_argv_matches_real_runner_builder(
    tmp_path: Path, fake_clis: Path, provider: str, model: str, effort: str,
) -> None:
    prepared_dir, prepared = prepare_development_arm(
        arm="N", provider=provider, model=model, effort=effort,
        output_root=tmp_path / "prepared", timeout_seconds=10,
    )
    run_dir, _ = run_development_arm(
        arm="N", provider=provider, model=model, effort=effort,
        output_root=tmp_path / "executed", timeout_seconds=10,
    )
    observed_argv = json.loads((run_dir / "work/fake_argv.json").read_text(encoding="utf-8"))
    planned_argv = [
        argument.replace(str(prepared_dir / "work"), str(run_dir / "work"))
        for argument in prepared["provider_argv"][1:]
    ]
    assert planned_argv == observed_argv
    assert (prepared_dir / "prompt.txt").read_bytes() == (run_dir / "prompt.txt").read_bytes()
    assert not (prepared_dir / "work/fake_argv.json").exists()


@pytest.mark.parametrize("source_name", [
    "sample_first_complete_week.csv", "common.md", "arm_n.md",
])
def test_prepare_only_rejects_tampered_copies_before_positive_report(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
    source_name: str,
) -> None:
    original_copy = runner.shutil.copyfile

    def tamper_copy(source: Path, destination: Path) -> str:
        result = original_copy(source, destination)
        if Path(source).name == source_name:
            target = Path(destination)
            target.write_bytes(target.read_bytes() + b"\nchanged during copy\n")
        return result

    monkeypatch.setattr(runner.shutil, "copyfile", tamper_copy)
    with pytest.raises(RunError, match="(public packet changed|assigned prompt copies differ)"):
        prepare_development_arm(
            arm="N", provider="codex", model="test-model", effort="low",
            output_root=tmp_path / "runs",
        )
    assert not list((tmp_path / "runs").glob("*/prepared.json"))
    assert not list((tmp_path / "runs").glob("*/work/fake_argv.json"))


def test_prepare_only_rejects_wheel_mutation_before_positive_report(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel = tmp_path / "specorganon-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"original wheel bytes\n")
    original_which = runner.shutil.which

    def mutate_wheel(command: str) -> str | None:
        wheel.write_bytes(b"changed wheel bytes\n")
        return original_which(command)

    monkeypatch.setattr(runner.shutil, "which", mutate_wheel)
    with pytest.raises(RunError, match="prepared inputs changed"):
        prepare_development_arm(
            arm="T", provider="codex", model="test-model", effort="medium",
            output_root=tmp_path / "runs", toolkit_wheel=wheel,
        )
    assert not list((tmp_path / "runs").glob("*/prepared.json"))
    assert not list((tmp_path / "runs").glob("*/work/fake_argv.json"))


def test_prepare_only_rejects_source_mutation_before_positive_report(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts = tmp_path / "public-prompts"
    prompts.mkdir()
    for name in ("common.md", "arm_n.md"):
        (prompts / name).write_bytes((runner.PROMPTS / name).read_bytes())
    monkeypatch.setattr(runner, "PROMPTS", prompts)
    original_builder = runner._provider_invocation

    def mutate_source(*args: object, **kwargs: object) -> object:
        common = prompts / "common.md"
        common.write_bytes(common.read_bytes() + b"\nchanged after copy\n")
        return original_builder(*args, **kwargs)

    monkeypatch.setattr(runner, "_provider_invocation", mutate_source)
    with pytest.raises(RunError, match="prepared inputs changed"):
        prepare_development_arm(
            arm="N", provider="codex", model="test-model", effort="low",
            output_root=tmp_path / "runs",
        )
    assert not list((tmp_path / "runs").glob("*/prepared.json"))
    assert not list((tmp_path / "runs").glob("*/work/fake_argv.json"))


@pytest.mark.parametrize("overrides,error", [
    ({"arm": "X"}, "arm must be N/S/T"),
    ({"model": ""}, "model and effort"),
    ({"effort": "uncontrolled"}, "effort must be"),
    ({"timeout_seconds": 0}, "timeout values"),
    ({"agy_no_command_tool": True}, "requires Agy N/S"),
    ({"arm": "T"}, "requires --toolkit-wheel"),
])
def test_prepare_only_invalid_request_never_creates_positive_report(
    tmp_path: Path, overrides: dict[str, object], error: str,
) -> None:
    options: dict[str, object] = {
        "arm": "N", "provider": "codex", "model": "test-model", "effort": "low",
        "output_root": tmp_path / "runs",
    }
    options.update(overrides)
    with pytest.raises(RunError, match=error):
        prepare_development_arm(**options)
    assert not (tmp_path / "runs").exists()


def test_prepare_only_cli_reports_private_location_and_no_go(
    tmp_path: Path, fake_clis: Path,
) -> None:
    script = SCRIPTS / "run_development_arm.py"
    help_result = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True, text=True, check=True,
    )
    assert "--prepare-only" in help_result.stdout
    assert "prepared.json" in help_result.stdout
    result = subprocess.run([
        sys.executable, str(script), "--prepare-only", "--arm", "S",
        "--provider", "agy", "--model", "test-model", "--effort", "medium",
        "--output-root", str(tmp_path / "runs"), "--agy-no-command-tool",
    ], capture_output=True, text=True, check=True)
    output = json.loads(result.stdout)
    run_dir = Path(output["run_dir"])
    assert output == {
        "run_dir": str(run_dir), "prepared_record": str(run_dir / "prepared.json"),
        "status": "no_go_for_provider_calls", "provider_calls": 0,
        "execution_ready": False,
    }
    assert (run_dir / "prepared.json").exists()
    assert not (run_dir / "work/fake_argv.json").exists()
    assert "Development-only D-E execution" not in result.stdout


@pytest.mark.parametrize("arm,family_slot", [
    ("N", "A"), ("S", "A"), ("T", "A"),
    ("N", "B"), ("S", "B"), ("T", "B"),
])
def test_strict_dossier_prepares_planned_cell_without_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    arm: str, family_slot: str,
) -> None:
    root, dossier_path, _ = activation_dossier_fixture
    wheel = root / "dist/specorganon-0.1.0-py3-none-any.whl" if arm == "T" else None

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("strict offline preparation launched a command")

    monkeypatch.setattr(runner, "_capture", forbidden)
    monkeypatch.setattr(runner, "_setup_toolkit", forbidden)
    monkeypatch.setattr(runner, "_system_strace", forbidden)
    expected_sha = hashlib.sha256(dossier_path.read_bytes()).hexdigest()
    run_dir, prepared = prepare_development_arm(
        arm=arm, provider="codex", model="test-model", effort="low",
        output_root=tmp_path / "runs", toolkit_wheel=wheel,
        activation_dossier=dossier_path, activation_dossier_sha256=expected_sha,
        family_slot=family_slot,
    )
    assert prepared["activation_dossier_sha256"] == expected_sha
    assert prepared["family_slot"] == family_slot
    assert prepared["dossier_assets_match"] is True
    assert prepared["status"] == "no_go_for_provider_calls"
    assert prepared["provider_calls"] == 0
    assert prepared["launch_ready"] is False
    assert prepared["execution_ready"] is False
    assert prepared["cap_status"] == "unknown"
    assert prepared["tool_parity_verified"] is False
    assert prepared["human_review_verified"] is False
    assert prepared["controlled_comparison_eligible"] is False
    assert json.loads((run_dir / "prepared.json").read_text(encoding="utf-8")) == prepared
    assert not (run_dir / "run.json").exists()
    assert not (run_dir / "work/.venv").exists()


@pytest.mark.parametrize("relative,arm", [
    ("cases/building_energy/task.md", "N"),
    ("experiments/development/energy_pilot/common.md", "S"),
    ("dist/specorganon-0.1.0-py3-none-any.whl", "T"),
    ("experiments/development/energy_pilot/rubric.md", "N"),
])
def test_strict_dossier_rejects_tampered_fixed_asset_before_preparation(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    relative: str, arm: str,
) -> None:
    root, dossier_path, _ = activation_dossier_fixture
    asset = root / relative
    asset.write_bytes(asset.read_bytes() + b"\ntampered\n")
    wheel = root / "dist/specorganon-0.1.0-py3-none-any.whl" if arm == "T" else None
    with pytest.raises(RunError, match="activation dossier asset hash differs"):
        prepare_development_arm(
            arm=arm, provider="codex", model="test-model", effort="low",
            output_root=tmp_path / "runs", toolkit_wheel=wheel,
            activation_dossier=dossier_path,
            activation_dossier_sha256=hashlib.sha256(dossier_path.read_bytes()).hexdigest(),
            family_slot="A",
        )
    assert not (tmp_path / "runs").exists()


def test_strict_dossier_rejects_dossier_byte_change_before_preparation(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
) -> None:
    _, dossier_path, _ = activation_dossier_fixture
    expected_sha = hashlib.sha256(dossier_path.read_bytes()).hexdigest()
    dossier_path.write_bytes(dossier_path.read_bytes() + b"\n")
    with pytest.raises(RunError, match="dossier SHA-256 differs"):
        prepare_development_arm(
            arm="N", provider="codex", model="test-model", effort="low",
            output_root=tmp_path / "runs", activation_dossier=dossier_path,
            activation_dossier_sha256=expected_sha, family_slot="A",
        )
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("change,error", [
    ("schema", "unexpected schema"),
    ("duplicate_cell", "duplicate planned cells"),
    ("missing_cell", "missing or unexpected planned cells"),
    ("unsafe_path", "unsafe or unexpected asset path"),
    ("invalid_asset_hash", "invalid asset SHA-256"),
    ("non_null_caps", "unexpected proposed scope"),
    ("non_null_model", "unverified family configurations"),
])
def test_strict_dossier_rejects_invalid_canonical_content(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    change: str, error: str,
) -> None:
    _, dossier_path, dossier = activation_dossier_fixture
    if change == "schema":
        dossier["schema"] = 2
    elif change == "duplicate_cell":
        dossier["planned_cells"][1] = dict(dossier["planned_cells"][0])
    elif change == "missing_cell":
        dossier["planned_cells"].pop()
    elif change == "unsafe_path":
        dossier["fixed_local_assets_sha256"]["../outside.md"] = "0" * 64
    elif change == "invalid_asset_hash":
        dossier["fixed_local_assets_sha256"]["cases/building_energy/task.md"] = "not-a-hash"
    elif change == "non_null_caps":
        dossier["proposed_scope"]["maximum_provider_requests"] = 1
    else:
        dossier["family_configs_shared_by_all_three_arms"]["A"]["model_id"] = "test-model"
    expected_sha = _write_activation_dossier(dossier_path, dossier)
    with pytest.raises(RunError, match=error):
        prepare_development_arm(
            arm="N", provider="codex", model="test-model", effort="low",
            output_root=tmp_path / "runs", activation_dossier=dossier_path,
            activation_dossier_sha256=expected_sha, family_slot="A",
        )
    assert not (tmp_path / "runs").exists()


def test_strict_dossier_rejects_duplicate_json_asset_key(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
) -> None:
    _, dossier_path, _ = activation_dossier_fixture
    raw = dossier_path.read_text(encoding="utf-8")
    asset_key = '"cases/building_energy/task.md"'
    raw = raw.replace(asset_key, f'{asset_key}: "{"0" * 64}", {asset_key}', 1)
    dossier_path.write_text(raw, encoding="utf-8")
    with pytest.raises(RunError, match="duplicate JSON key"):
        prepare_development_arm(
            arm="N", provider="codex", model="test-model", effort="low",
            output_root=tmp_path / "runs", activation_dossier=dossier_path,
            activation_dossier_sha256=hashlib.sha256(dossier_path.read_bytes()).hexdigest(),
            family_slot="A",
        )
    assert not (tmp_path / "runs").exists()


def test_strict_dossier_cli_creates_only_offline_record(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    _, dossier_path, _ = activation_dossier_fixture

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("CLI strict preparation launched a command")

    monkeypatch.setattr(runner, "_capture", forbidden)
    monkeypatch.setattr(runner, "_setup_toolkit", forbidden)
    expected_sha = hashlib.sha256(dossier_path.read_bytes()).hexdigest()
    assert runner.main([
        "--prepare-only", "--arm", "S", "--provider", "codex",
        "--model", "test-model", "--effort", "low", "--output-root", str(tmp_path / "runs"),
        "--activation-dossier", str(dossier_path), "--activation-dossier-sha256", expected_sha,
        "--family-slot", "B",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    run_dir = Path(result["run_dir"])
    prepared = json.loads((run_dir / "prepared.json").read_text(encoding="utf-8"))
    assert result["status"] == "no_go_for_provider_calls"
    assert result["provider_calls"] == 0
    assert result["execution_ready"] is False
    assert prepared["family_slot"] == "B"
    assert prepared["activation_dossier_sha256"] == expected_sha
    assert not (run_dir / "run.json").exists()


def test_strict_dossier_rechecks_unassigned_asset_after_copy(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, dossier_path, _ = activation_dossier_fixture
    rubric = root / "experiments/development/energy_pilot/rubric.md"
    original_builder = runner._provider_invocation

    def mutate_rubric(*args: object, **kwargs: object) -> object:
        rubric.write_bytes(rubric.read_bytes() + b"\nchanged during copy\n")
        return original_builder(*args, **kwargs)

    monkeypatch.setattr(runner, "_provider_invocation", mutate_rubric)
    with pytest.raises(RunError, match="activation dossier asset hash differs"):
        prepare_development_arm(
            arm="N", provider="codex", model="test-model", effort="low",
            output_root=tmp_path / "runs", activation_dossier=dossier_path,
            activation_dossier_sha256=hashlib.sha256(dossier_path.read_bytes()).hexdigest(),
            family_slot="A",
        )
    assert not list((tmp_path / "runs").glob("*/prepared.json"))


def test_strict_dossier_rechecks_dossier_after_copy(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, dossier_path, _ = activation_dossier_fixture
    expected_sha = hashlib.sha256(dossier_path.read_bytes()).hexdigest()
    original_builder = runner._provider_invocation

    def mutate_dossier(*args: object, **kwargs: object) -> object:
        dossier_path.write_bytes(dossier_path.read_bytes() + b"\n")
        return original_builder(*args, **kwargs)

    monkeypatch.setattr(runner, "_provider_invocation", mutate_dossier)
    with pytest.raises(RunError, match="activation dossier changed during preparation"):
        prepare_development_arm(
            arm="N", provider="codex", model="test-model", effort="low",
            output_root=tmp_path / "runs", activation_dossier=dossier_path,
            activation_dossier_sha256=expected_sha, family_slot="A",
        )
    assert not list((tmp_path / "runs").glob("*/prepared.json"))


@pytest.mark.parametrize("provided", [
    {"activation_dossier_sha256": "0" * 64, "family_slot": "A"},
    {"activation_dossier": Path("missing.json"), "family_slot": "A"},
    {"activation_dossier": Path("missing.json"), "activation_dossier_sha256": "0" * 64},
])
def test_strict_dossier_requires_all_three_options(
    tmp_path: Path, provided: dict[str, object],
) -> None:
    with pytest.raises(RunError, match="require each other"):
        prepare_development_arm(
            arm="N", provider="codex", model="test-model", effort="low",
            output_root=tmp_path / "runs", **provided,
        )
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("argument", [
    "--activation-dossier", "--activation-dossier-sha256", "--family-slot",
])
def test_strict_dossier_cli_options_require_prepare_only(
    tmp_path: Path, argument: str,
) -> None:
    value = "A" if argument == "--family-slot" else "0" * 64
    script = SCRIPTS / "run_development_arm.py"
    result = subprocess.run([
        sys.executable, str(script), "--arm", "N", "--provider", "codex",
        "--model", "test-model", "--effort", "low", "--output-root",
        str(tmp_path / "runs"), argument, value,
    ], capture_output=True, text=True)
    assert result.returncode == 2
    assert "activation dossier options require --prepare-only" in result.stderr
    assert not (tmp_path / "runs").exists()


def test_unbound_pilot_template_is_no_go_before_run_directory(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    fake_clis: Path,
) -> None:
    _, dossier_path, _ = activation_dossier_fixture
    template = SCRIPTS.parent / "experiments/development/energy_pilot/pilot_triplet_plan_template_v2.json"
    assert json.loads(template.read_text(encoding="utf-8"))["active_budget_seconds"] is None
    with pytest.raises(RunError, match="NO-GO template"):
        run_development_arm(
            arm="N", provider="codex", model="test-model", effort="medium",
            output_root=tmp_path / "runs", pilot_triplet_plan=template,
            pilot_triplet_plan_sha256=runner._sha256(template),
            activation_dossier=dossier_path,
            activation_dossier_sha256=runner._sha256(dossier_path), family_slot="A",
        )
    assert not (tmp_path / "runs").exists()


def test_configured_v1_pilot_cannot_launch_or_lookup_provider(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, dossier_path, _ = activation_dossier_fixture
    dossier_sha = runner._sha256(dossier_path)
    plan_path = tmp_path / "legacy-plan.json"
    plan_sha = _write_pilot_triplet_plan(plan_path, dossier_sha, schema=1)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("legacy pilot reached provider lookup")

    monkeypatch.setattr(runner.shutil, "which", forbidden)
    with pytest.raises(RunError, match="schema 1 is legacy"):
        run_development_arm(
            arm="N", provider="codex", model="test-model", effort="medium",
            output_root=tmp_path / "runs", pilot_triplet_plan=plan_path,
            pilot_triplet_plan_sha256=plan_sha, activation_dossier=dossier_path,
            activation_dossier_sha256=dossier_sha, family_slot="A",
        )
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("budget", [None, True, False, 0, 5401, 1.5, "37"])
def test_pilot_plan_requires_one_strict_shared_budget_before_provider_lookup(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch, budget: object,
) -> None:
    _, dossier_path, _ = activation_dossier_fixture
    dossier_sha = runner._sha256(dossier_path)
    plan_path = tmp_path / "triplet-plan-v2.json"
    _write_pilot_triplet_plan(plan_path, dossier_sha, active_budget_seconds=budget)
    if budget is None:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        del plan["active_budget_seconds"]
        _write_activation_dossier(plan_path, plan)
    plan_sha = runner._sha256(plan_path)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid budget reached provider lookup")

    monkeypatch.setattr(runner.shutil, "which", forbidden)
    with pytest.raises(RunError, match="active_budget_seconds must be an integer from 1 to 5400"):
        run_development_arm(
            arm="N", provider="codex", model="test-model", effort="medium",
            output_root=tmp_path / "runs", pilot_triplet_plan=plan_path,
            pilot_triplet_plan_sha256=plan_sha, activation_dossier=dossier_path,
            activation_dossier_sha256=dossier_sha, family_slot="A",
        )
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("requested_budget", [None, 38])
def test_pilot_budget_mismatch_rejected_before_provider_lookup(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch, requested_budget: int | None,
) -> None:
    _, dossier_path, _ = activation_dossier_fixture
    dossier_sha = runner._sha256(dossier_path)
    plan_path = tmp_path / "triplet-plan-v2.json"
    plan_sha = _write_pilot_triplet_plan(plan_path, dossier_sha, active_budget_seconds=37)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("mismatched budget reached provider lookup")

    monkeypatch.setattr(runner.shutil, "which", forbidden)
    budget_kwarg = ({} if requested_budget is None
                    else {"active_budget_seconds": requested_budget})
    with pytest.raises(RunError, match="active_budget_seconds differs from requested run budget"):
        run_development_arm(
            arm="N", provider="codex", model="test-model", effort="medium",
            output_root=tmp_path / "runs", pilot_triplet_plan=plan_path,
            pilot_triplet_plan_sha256=plan_sha, activation_dossier=dossier_path,
            activation_dossier_sha256=dossier_sha, family_slot="A",
            **budget_kwarg,
        )
    assert not (tmp_path / "runs").exists()


def test_pilot_rejects_duplicate_root_budget_before_provider_lookup(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, dossier_path, _ = activation_dossier_fixture
    dossier_sha = runner._sha256(dossier_path)
    plan_path = tmp_path / "triplet-plan-v2.json"
    _write_pilot_triplet_plan(plan_path, dossier_sha)
    plan_text = plan_path.read_text(encoding="utf-8")
    assert '"active_budget_seconds": 5400' in plan_text
    plan_path.write_text(plan_text.replace(
        '"active_budget_seconds": 5400',
        '"active_budget_seconds": 5400, "active_budget_seconds": 5400', 1,
    ), encoding="utf-8")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("duplicate budget reached provider lookup")

    monkeypatch.setattr(runner.shutil, "which", forbidden)
    with pytest.raises(RunError, match="duplicate JSON key: active_budget_seconds"):
        run_development_arm(
            arm="N", provider="codex", model="test-model", effort="medium",
            output_root=tmp_path / "runs", pilot_triplet_plan=plan_path,
            pilot_triplet_plan_sha256=runner._sha256(plan_path),
            activation_dossier=dossier_path, activation_dossier_sha256=dossier_sha,
            family_slot="A",
        )
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("arm", ["N", "S"])
def test_pilot_triplet_a_inherits_exact_requested_tuple_and_copies_plan(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    fake_clis: Path, arm: str,
) -> None:
    _, dossier_path, _ = activation_dossier_fixture
    dossier_sha = runner._sha256(dossier_path)
    plan_path = tmp_path / "triplet-plan-v1.json"
    plan_sha = _write_pilot_triplet_plan(plan_path, dossier_sha)
    run_dir, summary = run_development_arm(
        arm=arm, provider="codex", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
        pilot_triplet_plan=plan_path, pilot_triplet_plan_sha256=plan_sha,
        activation_dossier=dossier_path, activation_dossier_sha256=dossier_sha,
        family_slot="A",
    )
    assert summary["execution_status"] == "artifacts_ready_for_inspection"
    assert summary["controlled_comparison_eligible"] is False
    assert summary["classification"] == "exposed_development_unsealed"
    binding = summary["pilot_triplet_binding"]
    assert binding["plan_sha256"] == plan_sha
    assert binding["activation_dossier_sha256"] == dossier_sha
    assert binding["cell"] == {"family_slot": "A", "arm": arm}
    assert binding["declared_model_version"] == "declared-test-version"
    assert binding["schema"] == 2
    assert binding["active_budget_seconds"] == 5400
    assert summary["active_budget_seconds"] == 5400
    assert summary["run_time_budget"]["active_budget_seconds"] == 5400
    assert (run_dir / "pilot_triplet_plan.json").read_bytes() == plan_path.read_bytes()
    assert (run_dir / "activation_dossier.json").read_bytes() == dossier_path.read_bytes()
    assert (run_dir / "work/fake_argv.json").exists()


def test_one_pilot_plan_digest_binds_all_six_fake_cli_cells(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, dossier_path, _ = activation_dossier_fixture
    dossier_sha = runner._sha256(dossier_path)
    plan_path = tmp_path / "triplet-plan-v1.json"
    plan_sha = _write_pilot_triplet_plan(plan_path, dossier_sha, active_budget_seconds=37)
    monkeypatch.setattr(runner, "_setup_toolkit", fake_t_setup)
    matrix = {
        "A": ("codex", "test-model", "medium"),
        "B": ("agy", "test-model-b", "high"),
    }
    seen: set[tuple[str, str]] = set()
    for slot, (provider, model, effort) in matrix.items():
        for arm in ("N", "S", "T"):
            run_dir, summary = run_development_arm(
                arm=arm, provider=provider, model=model, effort=effort,
                output_root=tmp_path / "runs", timeout_seconds=10,
                active_budget_seconds=37,
                toolkit_wheel=(root / "dist/specorganon-0.1.0-py3-none-any.whl"
                               if arm == "T" else None),
                pilot_triplet_plan=plan_path, pilot_triplet_plan_sha256=plan_sha,
                activation_dossier=dossier_path, activation_dossier_sha256=dossier_sha,
                family_slot=slot,
            )
            seen.add((slot, arm))
            assert summary["execution_status"] != "preflight_failure"
            assert summary["pilot_triplet_binding"]["plan_sha256"] == plan_sha
            assert summary["pilot_triplet_binding"]["active_budget_seconds"] == 37
            assert summary["active_budget_seconds"] == 37
            assert summary["run_time_budget"]["active_budget_seconds"] == 37
            assert summary["pilot_triplet_binding"]["cell"] == {
                "family_slot": slot, "arm": arm,
            }
            assert (summary["provider_cli"], summary["requested_model"],
                    summary["requested_effort"]) == matrix[slot]
            argv = json.loads((run_dir / "work/fake_argv.json").read_text(encoding="utf-8"))
            if provider == "codex":
                assert argv[argv.index("-m") + 1] == model
                assert f'model_reasoning_effort="{effort}"' in argv
            else:
                assert argv[argv.index("--model") + 1] == model
                assert argv[argv.index("--effort") + 1] == effort
            assert summary["controlled_comparison_eligible"] is False
    assert seen == runner.PILOT_CELLS


def test_explicit_pilot_cli_parses_plan_and_keeps_run_unsealed(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    fake_clis: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    _, dossier_path, _ = activation_dossier_fixture
    dossier_sha = runner._sha256(dossier_path)
    plan_path = tmp_path / "triplet-plan-v1.json"
    plan_sha = _write_pilot_triplet_plan(plan_path, dossier_sha)
    assert runner.main([
        "--arm", "N", "--provider", "codex", "--model", "test-model",
        "--effort", "medium", "--output-root", str(tmp_path / "runs"),
        "--pilot-triplet-plan", str(plan_path),
        "--pilot-triplet-plan-sha256", plan_sha,
        "--activation-dossier", str(dossier_path),
        "--activation-dossier-sha256", dossier_sha,
        "--family-slot", "A", "--timeout-seconds", "10",
    ]) == 0
    response = json.loads(capsys.readouterr().out)
    summary = json.loads((Path(response["run_dir"]) / "run.json").read_text(encoding="utf-8"))
    assert summary["pilot_triplet_binding"]["plan_sha256"] == plan_sha
    assert summary["controlled_comparison_eligible"] is False


@pytest.mark.parametrize("changed", [
    {"model": "different-model", "effort": "medium"},
    {"model": "test-model", "effort": "high"},
])
def test_pilot_triplet_a_s_rejects_model_or_effort_change_before_cli(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    fake_clis: Path, changed: dict[str, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, dossier_path, _ = activation_dossier_fixture
    dossier_sha = runner._sha256(dossier_path)
    plan_path = tmp_path / "triplet-plan-v1.json"
    plan_sha = _write_pilot_triplet_plan(plan_path, dossier_sha)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a mismatched pilot started a CLI or toolkit subprocess")

    monkeypatch.setattr(runner, "_capture", forbidden)
    monkeypatch.setattr(runner, "_setup_toolkit", forbidden)
    with pytest.raises(RunError, match="cell differs from requested CLI/model/effort"):
        run_development_arm(
            arm="S", provider="codex", model=changed["model"], effort=changed["effort"],
            output_root=tmp_path / "runs", timeout_seconds=10,
            pilot_triplet_plan=plan_path, pilot_triplet_plan_sha256=plan_sha,
            activation_dossier=dossier_path, activation_dossier_sha256=dossier_sha,
            family_slot="A",
        )
    assert not (tmp_path / "runs").exists()


def test_pilot_triplet_rejects_dossier_asset_mutation_before_run_directory(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    fake_clis: Path,
) -> None:
    root, dossier_path, _ = activation_dossier_fixture
    dossier_sha = runner._sha256(dossier_path)
    plan_path = tmp_path / "triplet-plan-v1.json"
    plan_sha = _write_pilot_triplet_plan(plan_path, dossier_sha)
    rubric = root / "experiments/development/energy_pilot/rubric.md"
    rubric.write_bytes(rubric.read_bytes() + b"\nchanged\n")
    with pytest.raises(RunError, match="activation dossier asset hash differs"):
        run_development_arm(
            arm="N", provider="codex", model="test-model", effort="medium",
            output_root=tmp_path / "runs", pilot_triplet_plan=plan_path,
            pilot_triplet_plan_sha256=plan_sha, activation_dossier=dossier_path,
            activation_dossier_sha256=dossier_sha, family_slot="A",
        )
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("change", ["digest", "downgrade"])
def test_pilot_replay_rejects_changed_binding_before_generated_code_runs(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    fake_clis: Path, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    _, dossier_path, _ = activation_dossier_fixture
    dossier_sha = runner._sha256(dossier_path)
    plan_path = tmp_path / "triplet-plan-v1.json"
    plan_sha = _write_pilot_triplet_plan(plan_path, dossier_sha)
    run_dir, summary = run_development_arm(
        arm="N", provider="codex", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
        pilot_triplet_plan=plan_path, pilot_triplet_plan_sha256=plan_sha,
        activation_dossier=dossier_path, activation_dossier_sha256=dossier_sha,
        family_slot="A",
    )
    assert summary["execution_status"] == "artifacts_ready_for_inspection"
    if change == "digest":
        summary["pilot_triplet_binding"]["plan_sha256"] = "0" * 64
    else:
        summary["pilot_triplet_binding"]["schema"] = 1
        del summary["pilot_triplet_binding"]["active_budget_seconds"]
    runner._write_json(run_dir / "run.json", summary)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("replay executed generated code after pilot binding changed")

    monkeypatch.setattr(runner, "_capture", forbidden)
    with pytest.raises(RunError, match="pilot_triplet_binding changed after the model run"):
        replay_run_dir(run_dir, summary["artifacts"]["analysis.py"]["sha256"])
    assert not (run_dir / "analysis_replay.stdout").exists()


@pytest.mark.parametrize("has_d080_budget_metadata", [True, False])
def test_pilot_replay_reads_v1_legacy_without_shared_budget_claim(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    fake_clis: Path, has_d080_budget_metadata: bool,
) -> None:
    _, dossier_path, _ = activation_dossier_fixture
    dossier_sha = runner._sha256(dossier_path)
    plan_path = tmp_path / "triplet-plan-v2.json"
    plan_sha = _write_pilot_triplet_plan(plan_path, dossier_sha)
    run_dir, summary = run_development_arm(
        arm="N", provider="codex", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
        pilot_triplet_plan=plan_path, pilot_triplet_plan_sha256=plan_sha,
        activation_dossier=dossier_path, activation_dossier_sha256=dossier_sha,
        family_slot="A",
    )
    assert summary["execution_status"] == "artifacts_ready_for_inspection"
    legacy_path = tmp_path / "triplet-plan-v1.json"
    legacy_sha = _write_pilot_triplet_plan(legacy_path, dossier_sha, schema=1)
    copied_plan = run_dir / "pilot_triplet_plan.json"
    copied_plan.write_bytes(legacy_path.read_bytes())
    binding = summary["pilot_triplet_binding"]
    binding["schema"] = 1
    binding["plan_sha256"] = legacy_sha
    binding["plan_record"] = runner._file_record(copied_plan)
    del binding["active_budget_seconds"]
    if has_d080_budget_metadata:
        del summary["run_time_budget"]["active_budget_seconds"]
    else:
        del summary["active_budget_seconds"]
        del summary["run_time_budget"]
    runner._write_json(run_dir / "run.json", summary)

    assert runner._material_mismatches(run_dir, summary) == []
    replayed = replay_run_dir(run_dir, summary["artifacts"]["analysis.py"]["sha256"])
    assert replayed["execution_status"] == "output_replayed"
    assert replayed["analysis_replay"]["exit_code"] == 0
    assert replayed["controlled_comparison_eligible"] is False
    assert replayed["pilot_triplet_binding"]["schema"] == 1
    assert "active_budget_seconds" not in replayed["pilot_triplet_binding"]
    assert runner._material_mismatches(run_dir, replayed) == []
    observed = observe_run_dir(run_dir)
    assert observed["pilot_triplet_binding"]["plan_schema"] == 1
    assert "active_budget_seconds" not in observed["pilot_triplet_binding"]
    assert observed["cap_status"] == "unknown"
    assert observed["controlled_comparison_eligible"] is False
    if has_d080_budget_metadata:
        forged = json.loads(json.dumps(replayed))
        forged["run_time_budget"]["active_budget_seconds"] = 5400
        assert "pilot_triplet_binding" in runner._material_mismatches(run_dir, forged)


def test_pilot_t_rejects_wheel_swapped_during_copy_before_any_subprocess(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, dossier_path, _ = activation_dossier_fixture
    wheel = root / "dist/specorganon-0.1.0-py3-none-any.whl"
    dossier_sha = runner._sha256(dossier_path)
    plan_path = tmp_path / "triplet-plan-v1.json"
    plan_sha = _write_pilot_triplet_plan(plan_path, dossier_sha)
    original_copy = runner.shutil.copyfile
    swapped = False

    def swap_at_wheel_copy(src: object, dst: object, *args: object, **kwargs: object) -> object:
        nonlocal swapped
        if Path(src) == wheel and Path(dst).parent.name == "work":
            wheel.write_bytes(b"substituted wheel bytes\n")
            swapped = True
        return original_copy(src, dst, *args, **kwargs)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a toolkit or provider subprocess was invoked after wheel substitution")

    monkeypatch.setattr(runner.shutil, "copyfile", swap_at_wheel_copy)
    monkeypatch.setattr(runner, "_capture", forbidden)
    run_dir, summary = run_development_arm(
        arm="T", provider="codex", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
        toolkit_wheel=wheel, pilot_triplet_plan=plan_path,
        pilot_triplet_plan_sha256=plan_sha, activation_dossier=dossier_path,
        activation_dossier_sha256=dossier_sha, family_slot="A",
    )
    assert swapped is True
    assert summary["execution_status"] == "preflight_failure"
    assert "T copied wheel differs from the activation dossier" in summary["preflight_error"]
    assert not (run_dir / "work/fake_argv.json").exists()
    assert not (run_dir / "toolkit_venv.stdout").exists()
    assert not (run_dir / "cli.stdout.jsonl").exists()


def test_pilot_t_rechecks_copied_wheel_after_setup_before_provider_cli(
    tmp_path: Path, activation_dossier_fixture: tuple[Path, Path, dict[str, object]],
    fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, dossier_path, _ = activation_dossier_fixture
    wheel = root / "dist/specorganon-0.1.0-py3-none-any.whl"
    dossier_sha = runner._sha256(dossier_path)
    plan_path = tmp_path / "triplet-plan-v1.json"
    plan_sha = _write_pilot_triplet_plan(plan_path, dossier_sha)

    def mutate_after_fake_setup(
        work: Path, run_dir: Path, source: Path | None, timeout_seconds: int,
        env: dict[str, str], *, expected_wheel_sha256: str | None = None,
        active_deadline: float | None = None,
    ) -> dict[str, object]:
        result = fake_t_setup(
            work, run_dir, source, timeout_seconds, env,
            expected_wheel_sha256=expected_wheel_sha256,
            active_deadline=active_deadline,
        )
        (work / wheel.name).write_bytes(b"changed after setup\n")
        return result

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("provider CLI was invoked after T wheel changed")

    monkeypatch.setattr(runner, "_setup_toolkit", mutate_after_fake_setup)
    monkeypatch.setattr(runner, "_capture", forbidden)
    run_dir, summary = run_development_arm(
        arm="T", provider="codex", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
        toolkit_wheel=wheel, pilot_triplet_plan=plan_path,
        pilot_triplet_plan_sha256=plan_sha, activation_dossier=dossier_path,
        activation_dossier_sha256=dossier_sha, family_slot="A",
    )
    assert summary["execution_status"] == "preflight_failure"
    assert "T copied wheel changed after toolkit setup" in summary["preflight_error"]
    assert not (run_dir / "work/fake_argv.json").exists()
    assert not (run_dir / "cli.stdout.jsonl").exists()


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


def _codex_item_trace(path: Path, item_events: list[dict[str, object]]) -> dict[str, object]:
    usage = {
        "input_tokens": 20,
        "cached_input_tokens": 2,
        "cache_write_input_tokens": 0,
        "output_tokens": 8,
        "reasoning_output_tokens": 1,
    }
    events = [*item_events, {"type": "turn.completed", "usage": usage}]
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    return usage


def test_codex_complete_item_pair_and_legacy_unpaired_completion(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "codex.jsonl"
    usage = _codex_item_trace(trace, [
        {"type": "item.started", "item": {"id": "item-1", "type": "command_execution"}},
        {"type": "item.completed", "item": {"id": "item-1", "type": "command_execution"}},
    ])
    parsed = runner._parse_usage("codex", trace, "test-model")
    assert parsed["terminal_success"] is True
    assert parsed["complete"] is True
    assert parsed["final_usage"] == usage

    for item in ({"id": "legacy-1", "type": "command_execution"},
                 {"type": "command_execution"}):
        _codex_item_trace(trace, [{"type": "item.completed", "item": item}])
        legacy = runner._parse_usage("codex", trace, "test-model")
        assert legacy["terminal_success"] is True
        assert legacy["complete"] is True


@pytest.mark.parametrize("item_type", ["agent_message", "reasoning"])
@pytest.mark.parametrize("kind", ["item.completed", "item.updated", "item.future_suffix"])
def test_codex_message_and_reasoning_items_keep_terminal_success(
    tmp_path: Path, item_type: str, kind: str,
) -> None:
    trace = tmp_path / "codex.jsonl"
    usage = _codex_item_trace(trace, [{
        "type": kind,
        "item": {"id": "message-1", "type": item_type, "text": "done"},
    }])
    parsed = runner._parse_usage("codex", trace, "test-model")
    assert parsed["terminal_success"] is True
    assert parsed["complete"] is True
    assert parsed["final_usage"] == usage


@pytest.mark.parametrize("kind", [
    "item.started", "item.completed", "item.failed", "item.updated", "item.future_suffix", "error",
])
@pytest.mark.parametrize("details", [
    {"message": "startup failure", "status": "error", "id": "error-1"},
    {}, {"message": None}, {"message": 42, "id": []},
])
@pytest.mark.parametrize("position", ["startup", "before_final", "after_final"])
def test_codex_explicit_errors_fail_closed_and_preserve_usage(
    tmp_path: Path, kind: str, details: dict[str, object], position: str,
) -> None:
    trace = tmp_path / "codex.jsonl"
    usage = _codex_item_trace(trace, [])
    final_event = json.loads(trace.read_text(encoding="utf-8"))
    error_event = ({"type": kind, **details} if kind == "error" else {
        "type": kind, "item": {"type": "error", **details},
    })
    events = [{"type": "turn.started"}, final_event]
    error_index = {"startup": 0, "before_final": 1, "after_final": 2}[position]
    events.insert(error_index, error_event)
    raw = "".join(json.dumps(event) + "\n" for event in events)
    trace.write_text(raw, encoding="utf-8")

    parsed = runner._parse_usage("codex", trace, "test-model")

    assert parsed["terminal_success"] is False
    assert parsed["complete"] is False
    assert parsed["observed_failed_codex_items_partial"] == 1
    assert any("failed item/turn events" in error for error in parsed["terminal_errors"])
    assert parsed["final_usage"] == usage
    assert trace.read_text(encoding="utf-8") == raw


def test_codex_d095_archived_startup_error_rejects_terminal_success() -> None:
    trace = (SCRIPTS.parent / "experiments/development/prototype_checkpoint_2026-09-30"
             / "attempt/model.stdout.jsonl")
    raw = trace.read_bytes()
    events = [json.loads(line) for line in raw.splitlines()]
    assert events[1]["type"] == "item.completed"
    assert events[1]["item"]["type"] == "error"
    assert events[-1]["type"] == "turn.completed"

    parsed = runner._parse_usage("codex", trace, "archived-model")

    assert parsed["terminal_success"] is False
    assert parsed["complete"] is False
    assert parsed["observed_failed_codex_items_partial"] == 1
    assert parsed["final_usage"] == events[-1]["usage"] == {
        "input_tokens": 17576, "cached_input_tokens": 0, "cache_write_input_tokens": 0,
        "output_tokens": 956, "reasoning_output_tokens": 0,
    }
    assert any("failed item/turn events" in error for error in parsed["terminal_errors"])
    assert trace.read_bytes() == raw


@pytest.mark.parametrize("item_events,error_fragment", [
    ([{"type": "item.started", "item": {"id": "item-1", "type": "command_execution"}}],
     "started items without completion/failure"),
    ([{"type": "item.started", "item": {"type": "command_execution"}},
      {"type": "item.completed", "item": {"type": "command_execution"}}],
     "malformed item events"),
    ([{"type": "item.started", "item": {"id": "item-1", "type": "command_execution"}},
      {"type": "item.completed", "item": {"id": "item-2", "type": "command_execution"}}],
     "started items without completion/failure"),
    ([{"type": "item.started", "item": {"id": "item-1", "type": "command_execution"}},
      {"type": "item.completed", "item": {"type": "command_execution"}}],
     "started items without completion/failure"),
    ([{"type": "item.started", "item": {"id": "item-1", "type": "command_execution"}},
      {"type": "item.completed", "item": {"id": "item-1", "type": "file_change"}}],
     "contradictory item ID/type transitions"),
    ([{"type": "item.started", "item": {"id": "item-1", "type": "command_execution"}},
      {"type": "item.started", "item": {"id": "item-1", "type": "file_change"}},
      {"type": "item.completed", "item": {"id": "item-1", "type": "command_execution"}}],
     "contradictory item ID/type transitions"),
    ([{"type": "item.started", "item": {"id": "item-1", "type": "command_execution"}},
      {"type": "item.failed", "item": {"id": "item-1", "type": "command_execution"}}],
     "failed item/turn events"),
    ([{"type": "item.completed", "item": {"id": "item-1", "type": "command_execution"}},
      {"type": "item.completed", "item": {"id": "item-1", "type": "command_execution"}}],
     "contradictory item ID/type transitions"),
])
def test_codex_item_trace_rejects_open_failed_or_contradictory_items(
    tmp_path: Path, item_events: list[dict[str, object]], error_fragment: str,
) -> None:
    trace = tmp_path / "codex.jsonl"
    usage = _codex_item_trace(trace, item_events)
    parsed = runner._parse_usage("codex", trace, "test-model")
    assert parsed["final_usage"] == usage
    assert parsed["terminal_success"] is False
    assert parsed["complete"] is False
    assert any(error_fragment in error for error in parsed["terminal_errors"])


@pytest.mark.parametrize("exit_code", ["1", 1.0, True, None])
def test_codex_command_rejects_noninteger_exit_code(
    tmp_path: Path, exit_code: object,
) -> None:
    trace = tmp_path / "codex.jsonl"
    _codex_item_trace(trace, [
        {"type": "item.started", "item": {"id": "item-1", "type": "command_execution"}},
        {"type": "item.completed", "item": {
            "id": "item-1", "type": "command_execution", "status": "completed",
            "exit_code": exit_code,
        }},
    ])
    parsed = runner._parse_usage("codex", trace, "test-model")
    assert parsed["terminal_success"] is False
    assert parsed["complete"] is False
    assert any("malformed item events" in error for error in parsed["terminal_errors"])


def test_codex_command_accepts_integer_zero_exit_code(tmp_path: Path) -> None:
    trace = tmp_path / "codex.jsonl"
    _codex_item_trace(trace, [
        {"type": "item.started", "item": {"id": "item-1", "type": "command_execution"}},
        {"type": "item.completed", "item": {
            "id": "item-1", "type": "command_execution", "status": "completed",
            "exit_code": 0,
        }},
    ])
    parsed = runner._parse_usage("codex", trace, "test-model")
    assert parsed["terminal_success"] is True
    assert parsed["complete"] is True


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


@pytest.mark.parametrize("provider", ["codex", "agy"])
@pytest.mark.parametrize("replacement,error_fragment", [
    ('"input_tokens": 90000, "input_tokens": {value}', "duplicate JSON key"),
    ('"input_tokens": NaN', "nonfinite JSON number"),
    ('"input_tokens": Infinity', "nonfinite JSON number"),
    ('"input_tokens": -Infinity', "nonfinite JSON number"),
    ('"input_tokens": 1e999', "nonfinite JSON number"),
])
def test_codex_and_agy_reject_ambiguous_or_nonfinite_usage_jsonl(
    tmp_path: Path, provider: str, replacement: str, error_fragment: str,
) -> None:
    usage = {"input_tokens": 20, "output_tokens": 8}
    if provider == "codex":
        usage.update(cached_input_tokens=2, cache_write_input_tokens=0,
                     reasoning_output_tokens=1)
    else:
        usage = {"input_tokens": 30, "output_tokens": 9, "thinking_tokens": 3,
                 "cache_read_tokens": 1, "total_tokens": 39}
    trace = tmp_path / "cli.stdout.jsonl"
    valid = _usage_trace(trace, provider, usage, usage if provider == "agy" else None)
    accepted = runner._parse_usage(provider, trace, "test-model")
    assert accepted["terminal_success"] is True
    assert accepted["complete"] is True
    assert accepted["final_usage"] == usage

    original = f'"input_tokens": {usage["input_tokens"]}'
    prefix, suffix = valid.rsplit(original, 1)
    corrupted = prefix + replacement.format(value=usage["input_tokens"]) + suffix
    assert corrupted != valid
    trace.write_text(corrupted, encoding="utf-8")
    parsed = runner._parse_usage(provider, trace, "test-model")

    line = 1 if provider == "codex" else 3
    assert parsed["terminal_success"] is False
    assert parsed["complete"] is False
    assert any(f"line {line}: invalid or ambiguous JSON ({error_fragment})" == error
               for error in parsed["terminal_errors"])
    assert trace.read_text(encoding="utf-8") == corrupted


@pytest.mark.parametrize("provider", ["codex", "agy"])
def test_codex_and_agy_reject_invalid_utf8_without_replacing_it(
    tmp_path: Path, provider: str,
) -> None:
    usage = {"input_tokens": 20, "output_tokens": 8}
    if provider == "codex":
        usage.update(cached_input_tokens=2, cache_write_input_tokens=0,
                     reasoning_output_tokens=1)
    else:
        usage = {"input_tokens": 30, "output_tokens": 9, "thinking_tokens": 3,
                 "cache_read_tokens": 1, "total_tokens": 39}
    trace = tmp_path / "cli.stdout.jsonl"
    valid = _usage_trace(trace, provider, usage, usage if provider == "agy" else None)
    raw = b"\xff\n" + valid.encode("utf-8")
    trace.write_bytes(raw)

    parsed = runner._parse_usage(provider, trace, "test-model")

    assert parsed["terminal_success"] is False
    assert parsed["complete"] is False
    assert "line 1: invalid or ambiguous JSON (invalid UTF-8)" in parsed["terminal_errors"]
    assert trace.read_bytes() == raw


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
    if provider == "agy":
        assert parsed["conversation_identity"] == "local_identity_unverified"
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
        assert summary["cli_usage"]["conversation_identity"] == "local_ids_consistent"
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


def test_agy_matching_ids_in_step_update_remain_local_evidence(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", "agy_step_ids_match")
    run_dir, summary = run_development_arm(
        arm="N", provider="agy", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
    )
    assert summary["execution_status"] == "artifacts_ready_for_inspection"
    assert summary["cli_usage"]["terminal_success"] is True
    assert summary["cli_usage"]["complete"] is True
    assert summary["cli_usage"]["conversation_identity"] == "local_ids_consistent"
    assert summary["provider_request_id"] is None
    assert summary["controlled_comparison_eligible"] is False
    assert "local-conversation-id" not in (run_dir / "run.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("scenario", [
    "agy_ids_absent", "agy_init_id_only", "agy_result_id_only",
])
def test_agy_missing_ids_preserve_legacy_valid_stream_as_unverified(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch, scenario: str,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", scenario)
    run_dir, summary = run_development_arm(
        arm="N", provider="agy", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
    )
    assert summary["execution_status"] == "artifacts_ready_for_inspection"
    assert summary["cli_usage"]["terminal_success"] is True
    assert summary["cli_usage"]["complete"] is True
    assert summary["cli_usage"]["conversation_identity"] == "local_identity_unverified"
    assert "local-conversation-id" not in (run_dir / "run.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("scenario,line,fragment", [
    ("agy_result_id_mismatch", 6, "agy result conversation_id changed"),
    ("agy_step_outer_id_mismatch", 2, "agy step_update conversation_id changed"),
    ("agy_step_nested_id_mismatch", 2, "agy step_update conversation_id changed"),
    ("agy_init_id_malformed", 1, "agy init conversation_id is malformed"),
    ("agy_result_id_malformed", 6, "agy result conversation_id is malformed"),
    ("agy_result_id_blank", 6, "agy result conversation_id is malformed"),
    ("agy_step_id_malformed", 2, "agy step_update conversation_id is malformed"),
])
def test_agy_conversation_identity_error_rejects_zero_exit_with_artifacts(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
    scenario: str, line: int, fragment: str,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", scenario)
    run_dir, summary = run_development_arm(
        arm="N", provider="agy", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
    )
    usage = summary["cli_usage"]
    assert summary["cli"]["exit_code"] == 0
    assert all(summary["artifacts"].values())
    assert summary["execution_status"] == "cli_internal_failure"
    assert usage["terminal_success"] is False
    assert usage["complete"] is False
    assert usage["conversation_identity"] == "local_ids_invalid"
    assert f"line {line}: {fragment}" in usage["terminal_errors"]
    public_summary = (run_dir / "run.json").read_text(encoding="utf-8")
    assert "local-conversation-id" not in public_summary
    assert "another-private-conversation-id" not in public_summary


@pytest.mark.parametrize("scenario,identity,kind_error,id_error", [
    ("agy_unknown_event_same_id", "local_ids_consistent",
     "unknown agy event type", None),
    ("agy_unknown_event_no_id", "local_ids_consistent",
     "unknown agy event type", None),
    ("agy_unknown_event_mismatch", "local_ids_invalid",
     "unknown agy event type", "agy event conversation_id changed"),
    ("agy_unknown_event_malformed", "local_ids_invalid",
     "unknown agy event type", "agy event conversation_id is malformed"),
    ("agy_invalid_event_kind_with_id", "local_ids_invalid",
     "event/event missing", "agy event conversation_id changed"),
])
def test_agy_unknown_event_fails_closed_and_checks_envelope_id(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
    scenario: str, identity: str, kind_error: str, id_error: str | None,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", scenario)
    run_dir, summary = run_development_arm(
        arm="N", provider="agy", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
    )
    usage = summary["cli_usage"]
    assert summary["cli"]["exit_code"] == 0
    assert all(summary["artifacts"].values())
    assert summary["execution_status"] == "cli_internal_failure"
    assert usage["terminal_success"] is False
    assert usage["complete"] is False
    assert usage["conversation_identity"] == identity
    assert f"line 2: {kind_error}" in usage["terminal_errors"]
    if id_error is not None:
        assert f"line 2: {id_error}" in usage["terminal_errors"]
    assert "local-conversation-id" not in (run_dir / "run.json").read_text(encoding="utf-8")
    assert "another-private-conversation-id" not in (
        run_dir / "run.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("arm", ["N", "S", "T"])
def test_opencode_fake_cli_produces_local_arm_receipt(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch, arm: str,
) -> None:
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
    assert summary["execution_status"] == (
        "t_tool_execution_unverified" if arm == "T"
        else "artifacts_ready_for_inspection"
    )
    assert summary["controlled_comparison_eligible"] is False
    assert summary["provider_request_id"] is None
    assert summary["cost"] is None
    assert summary["price"] is None
    assert summary["cli_usage"]["observed_model"] is None
    assert summary["cli_usage"]["terminal_success"] is True
    assert summary["cli_usage"]["complete"] is True
    assert summary["cli_usage"]["final_usage"] == {
        "input_tokens": 30, "output_tokens": 9, "reasoning_tokens": 3,
        "cache_read_tokens": 3, "cache_write_tokens": 1, "total_tokens": 46,
    }
    assert summary["cli_usage"]["preterminal_step_usage"]["completed_steps"] == 2
    assert summary["cli_usage"]["observed_completed_tool_steps"] == 1
    assert summary["cli_mode"] == {
        "opencode_format": "json", "opencode_pure": True, "opencode_agent": "build",
    }
    assert "private-local-session-id" not in (run_dir / "run.json").read_text(encoding="utf-8")
    argv = json.loads((run_dir / "work" / "fake_argv.json").read_text(encoding="utf-8"))
    assert argv == [
        "--pure", "run", "--format", "json", "--model", "minimax/MiniMax-M3",
        "--agent", "build", "--dir", str(run_dir / "work"),
    ]
    assert (run_dir / "work" / "fake_prompt.txt").read_text(encoding="utf-8") == (
        run_dir / "prompt.txt").read_text(encoding="utf-8")
    if arm == "T":
        assert summary["t_ledger"]["signed_policy"] is True
        assert summary["t_ledger"]["event_count"] == 1
        assert summary["t_process_trace"]["tool_ledger_publish_count"] == 0
        assert summary["t_process_trace"]["other_ledger_write_count"] >= 1
    else:
        assert summary["t_ledger"] is None


def test_opencode_retains_separately_reported_numeric_total(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", "opencode_nonadditive_total")
    _, summary = run_development_arm(
        arm="N", provider="opencode", model="minimax/MiniMax-M3",
        effort="uncontrolled", output_root=tmp_path / "runs", timeout_seconds=10,
    )
    assert summary["execution_status"] == "artifacts_ready_for_inspection"
    assert summary["cli_usage"]["origin"] == "local_cli_jsonl_not_authenticated_provider_receipt"
    assert summary["cli_usage"]["final_usage"]["total_tokens"] == 128
    assert summary["cli_usage"]["final_usage"]["input_tokens"] == 30
    assert summary["cost"] is None


def test_opencode_multiple_model_steps_pair_with_their_tools(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", "opencode_multiple_tool_steps")
    _, summary = run_development_arm(
        arm="N", provider="opencode", model="minimax/MiniMax-M3",
        effort="uncontrolled", output_root=tmp_path / "runs", timeout_seconds=10,
    )
    assert summary["execution_status"] == "artifacts_ready_for_inspection"
    assert summary["cli_usage"]["terminal_success"] is True
    assert summary["cli_usage"]["complete"] is True
    assert summary["cli_usage"]["preterminal_step_usage"]["completed_steps"] == 3
    assert summary["cli_usage"]["observed_completed_tool_steps"] == 2
    assert summary["cli_usage"]["final_usage"] == {
        "input_tokens": 37, "output_tokens": 12, "reasoning_tokens": 3,
        "cache_read_tokens": 3, "cache_write_tokens": 1, "total_tokens": 56,
    }


def test_opencode_absent_optional_total_preserves_valid_terminal_stop(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", "opencode_missing_usage")
    _, summary = run_development_arm(
        arm="N", provider="opencode", model="minimax/MiniMax-M3",
        effort="uncontrolled", output_root=tmp_path / "runs", timeout_seconds=10,
    )
    assert summary["execution_status"] == "artifacts_ready_for_inspection"
    assert summary["controlled_comparison_eligible"] is False
    usage = summary["cli_usage"]
    assert usage["terminal_success"] is True
    assert usage["complete"] is False
    assert usage["final_usage"]["total_tokens"] is None
    assert usage["final_usage"]["input_tokens"] == 30
    assert usage["preterminal_step_usage"]["steps_with_valid_usage"] == 1
    assert usage["errors"] == []


@pytest.mark.parametrize("scenario,error_fragment", [
    ("opencode_open_step", "unfinished model steps"),
    ("opencode_wrong_message", "unmatched OpenCode step_finish messageID"),
    ("opencode_session_changed", "sessionID changed"),
    ("opencode_bad_usage", "step usage missing or invalid"),
    ("opencode_null_total", "step usage missing or invalid"),
    ("opencode_bool_usage", "step usage missing or invalid"),
    ("opencode_float_usage", "step usage missing or invalid"),
    ("opencode_tool_calls_no_tool", "tool-calls step has no completed tool_use"),
    ("opencode_tool_wrong_step", "tool-calls step has no completed tool_use"),
    ("opencode_overlapping_steps", "overlapping OpenCode model steps"),
    ("opencode_tool_error", "OpenCode tool failed"),
    ("opencode_missing_tool_name", "OpenCode tool name missing"),
    ("opencode_duplicate_tool", "duplicate OpenCode tool part ID"),
    ("opencode_unattached_tool", "parts without a model step messageID"),
    ("opencode_part_id_reused", "part ID changed type or messageID"),
    ("opencode_child_task", "task child usage is absent"),
    ("opencode_no_stop", "no terminal stop"),
    ("opencode_duplicate_finish", "event after terminal stop"),
    ("opencode_error", "OpenCode reported an error"),
    ("opencode_invalid_utf8", "invalid or ambiguous JSON"),
])
def test_opencode_fake_cli_rejects_incomplete_or_contradictory_jsonl(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
    scenario: str, error_fragment: str,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", scenario)
    _, summary = run_development_arm(
        arm="N", provider="opencode", model="minimax/MiniMax-M3",
        effort="uncontrolled", output_root=tmp_path / "runs", timeout_seconds=10,
    )
    assert summary["cli"]["exit_code"] == 0
    assert all(summary["artifacts"].values())
    assert summary["execution_status"] == "cli_internal_failure"
    assert summary["cli_usage"]["terminal_success"] is False
    assert summary["cli_usage"]["complete"] is False
    assert any(error_fragment in error for error in summary["cli_usage"]["errors"])


@pytest.mark.parametrize("model,effort", [
    ("minimax/MiniMax-M3", "low"),
    ("minimax/MiniMax-M3", "high"),
    ("other/model", "uncontrolled"),
])
def test_opencode_rejects_unproven_effort_or_non_minimax_route_before_capture(
    tmp_path: Path, fake_clis: Path, model: str, effort: str,
) -> None:
    with pytest.raises(RunError):
        run_development_arm(
            arm="N", provider="opencode", model=model, effort=effort,
            output_root=tmp_path / "runs", timeout_seconds=10,
        )
    assert not (tmp_path / "runs").exists()


def test_explicit_sandboxed_replay_records_local_enforcement(
    tmp_path: Path, fake_clis: Path,
) -> None:
    from local_replay_sandbox import probe_sandbox

    capability = probe_sandbox()
    if not capability.available:
        pytest.skip(f"Linux local sandbox unavailable: {capability.reason}")
    run_dir, summary = run_development_arm(
        arm="N", provider="codex", model="test-model", effort="low",
        output_root=tmp_path / "runs", timeout_seconds=10,
    )
    assert summary["execution_status"] == "artifacts_ready_for_inspection"

    command = subprocess.run(
        [sys.executable, str(SCRIPTS / "run_development_arm.py"),
         "--replay-run-dir", str(run_dir), "--expected-analysis-sha256",
         summary["artifacts"]["analysis.py"]["sha256"], "--sandboxed-replay"],
        capture_output=True, text=True, check=False, timeout=15,
    )
    assert command.returncode == 0, command.stderr
    replayed = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert replayed["execution_status"] == "output_replayed"
    assert replayed["analysis_replay"]["sandbox"]["enforced"] is True
    assert replayed["analysis_replay"]["sandbox"]["landlock_abi"] >= 3
    assert replayed["analysis_replay"]["sandbox"]["path_opened_writes_allowed"] is False
    assert "118280" in (run_dir / "analysis_replay.stdout").read_text(encoding="utf-8")
    assert not (run_dir / "replay_tmp").exists()
    assert not (run_dir / "replay_home").exists()
    assert (run_dir / "run.json").exists()
    observed = subprocess.run(
        [sys.executable, str(SCRIPTS / "observe_development_run.py"), str(run_dir)],
        capture_output=True, text=True, check=False, timeout=15,
    )
    assert observed.returncode == 0, observed.stderr
    assert json.loads(observed.stdout)["execution_status"] == "output_replayed"


def test_sandbox_setup_timeout_never_claims_enforcement(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import local_replay_sandbox as sandbox

    run_dir, summary = run_development_arm(
        arm="N", provider="codex", model="test-model", effort="low",
        output_root=tmp_path / "runs", timeout_seconds=10,
    )
    monkeypatch.setattr(sandbox, "run_sandboxed", lambda **_kwargs: sandbox.SandboxResult(
        exit_code=None, timed_out=True, launch_error="sandbox setup timed out",
        landlock_abi=9, duration_seconds=10.0,
    ))

    replayed = replay_run_dir(
        run_dir, summary["artifacts"]["analysis.py"]["sha256"], sandboxed=True,
    )

    assert replayed["execution_status"] == "analysis_replay_launch_failure"
    assert replayed["analysis_replay"]["sandbox"]["enforced"] is False


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


def test_codex_open_item_with_valid_final_usage_is_internal_failure(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", "codex_open_item")
    run_dir, summary = run_development_arm(
        arm="N", provider="codex", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
    )
    assert summary["cli"]["exit_code"] == 0
    assert all(summary["artifacts"].values())
    assert summary["cli_usage"]["final_usage"]["input_tokens"] == 20
    assert summary["cli_usage"]["terminal_success"] is False
    assert summary["cli_usage"]["complete"] is False
    assert summary["execution_status"] == "cli_internal_failure"
    assert "item.started" in (run_dir / "cli.stdout.jsonl").read_text(encoding="utf-8")


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


@pytest.mark.parametrize("scenario", [
    "agy_command_tool", "agy_tool_name_missing", "agy_tool_name_array",
])
def test_no_command_pilot_rejects_observed_unapproved_tool(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch, scenario: str,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", scenario)
    run_dir, summary = run_development_arm(
        arm="N", provider="agy", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
        agy_no_command_tool=True,
    )
    assert summary["cli"]["exit_code"] == 0
    assert summary["cli_usage"]["final_status"] == "SUCCESS"
    assert summary["execution_status"] == "cli_internal_failure"
    assert summary["cli_usage"]["terminal_success"] is False
    assert summary["cli_usage"]["no_command_tool_trace"]["violating_tool_steps"] == 1
    with pytest.raises(RunError, match="not in artifacts_ready"):
        replay_run_dir(run_dir, summary["artifacts"]["analysis.py"]["sha256"])
    assert (run_dir / "cli.stdout.jsonl").exists()


def test_no_command_pilot_needs_observable_file_write_step(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", "agy_no_tool_step")
    _, summary = run_development_arm(
        arm="N", provider="agy", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
        agy_no_command_tool=True,
    )
    assert summary["execution_status"] == "cli_internal_failure"
    assert summary["cli_usage"]["terminal_success"] is False
    assert any("no observable file-writing tool step" in error
               for error in summary["cli_usage"]["terminal_errors"])


def test_no_command_pilot_rejects_unrecognized_command_bearing_step(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", "agy_unknown_command_step")
    run_dir, summary = run_development_arm(
        arm="N", provider="agy", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
        agy_no_command_tool=True,
    )
    assert summary["execution_status"] == "cli_internal_failure"
    assert summary["cli_usage"]["no_command_tool_trace"] == {
        "origin": "local_cli_jsonl_observed_steps_only_not_enforced",
        "allowed_tool_steps": 1,
        "violating_tool_steps": 0,
        "uninspectable_step_events": 1,
    }
    with pytest.raises(RunError, match="not in artifacts_ready"):
        replay_run_dir(run_dir, summary["artifacts"]["analysis.py"]["sha256"])

    default_usage = runner._parse_usage("agy", run_dir / "cli.stdout.jsonl", "test-model")
    assert default_usage["terminal_success"] is True


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
    assert summary["cli"]["timeout_cap"] == "stage"
    assert (run_dir / "cli.stdout.jsonl").exists()
    assert summary["controlled_comparison_eligible"] is False


@pytest.mark.parametrize("invalid", [0, 5401, True])
def test_active_budget_rejects_values_outside_one_local_invocation(
    tmp_path: Path, invalid: int,
) -> None:
    with pytest.raises(RunError, match="active_budget_seconds"):
        run_development_arm(
            arm="N", provider="codex", model="test-model", effort="medium",
            output_root=tmp_path / "runs", active_budget_seconds=invalid,
        )
    assert not (tmp_path / "runs").exists()


def test_cli_rejects_active_budget_above_5400_before_provider_lookup(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "run_development_arm.py"),
         "--arm", "N", "--provider", "codex", "--model", "test-model",
         "--effort", "medium", "--output-root", str(tmp_path / "runs"),
         "--active-budget-seconds", "5401"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "active_budget_seconds must be an integer from 1 to 5400" in result.stderr
    assert not (tmp_path / "runs").exists()


def test_active_budget_exhausts_during_t_setup_and_retains_partial_streams(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel = tmp_path / "fake-0.1-py3-none-any.whl"
    wheel.write_bytes(b"offline fake wheel\n")
    real_capture = runner._capture
    launched: list[str] = []

    def setup_capture(argv: list[str], **kwargs: object) -> dict[str, object]:
        stage = kwargs["stage"]
        assert isinstance(stage, str) and stage in runner.T_SETUP_STEPS
        launched.append(stage)
        code = ("print('setup partial', flush=True); import time; "
                + ("time.sleep(3)" if stage == "toolkit_install"
                   else "time.sleep(0.05)"))
        return real_capture([sys.executable, "-u", "-c", code], **kwargs)

    monkeypatch.setattr(runner, "_capture", setup_capture)
    run_dir, summary = run_development_arm(
        arm="T", provider="opencode", model="minimax/MiniMax-M3",
        effort="uncontrolled", output_root=tmp_path / "runs",
        toolkit_wheel=wheel, timeout_seconds=10, setup_timeout_seconds=10,
        active_budget_seconds=1,
    )
    assert launched == ["toolkit_venv", "toolkit_install"]
    assert summary["execution_status"] == "run_time_budget_exhausted"
    assert summary["run_time_budget"]["exhausted_stage"] == "toolkit_install"
    assert summary["toolkit"]["steps"]["toolkit_install"]["timed_out"] is True
    assert summary["toolkit"]["steps"]["toolkit_install"]["timeout_cap"] == "run_budget"
    assert summary["toolkit"]["steps"]["toolkit_install"]["stdout"] == runner._file_record(
        run_dir / "toolkit_install.stdout")
    assert "setup partial" in (run_dir / "toolkit_install.stdout").read_text()
    assert summary["cli"] is None
    assert not (run_dir / "toolkit_init.stdout").exists()
    assert not (run_dir / "cli.stdout.jsonl").exists()
    assert summary["controlled_comparison_eligible"] is False
    observer = SCRIPTS / "observe_development_run.py"
    observed = subprocess.run([sys.executable, str(observer), str(run_dir)],
                              capture_output=True, text=True, check=False)
    assert observed.returncode == 0, observed.stderr
    observed_json = json.loads(observed.stdout)
    assert observed_json["observation_state"] == "partial"
    assert observed_json["verified_streams"]["toolkit_install.stdout"] == (
        summary["toolkit"]["steps"]["toolkit_install"]["stdout"])
    assert observed_json["cap_status"] == "unknown"
    forged_elapsed = json.loads(json.dumps(summary))
    forged_elapsed["run_time_budget"]["elapsed_seconds"] = (
        summary["toolkit"]["steps"]["toolkit_install"]["wall_seconds"] + 0.01)
    runner._write_json(run_dir / "run.json", forged_elapsed)
    too_short = subprocess.run([sys.executable, str(observer), str(run_dir)],
                               capture_output=True, text=True, check=False)
    assert too_short.returncode == 2
    assert "shorter than verified capture wall time" in too_short.stderr
    runner._write_json(run_dir / "run.json", summary)
    (run_dir / "toolkit_install.stdout").write_text("changed setup stream\n")
    changed = subprocess.run([sys.executable, str(observer), str(run_dir)],
                             capture_output=True, text=True, check=False)
    assert changed.returncode == 2
    assert "differs from its recorded bytes" in changed.stderr


def test_active_budget_exhausts_in_provider_cli_before_stage_timeout(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_SCENARIO", "sleep")
    run_dir, summary = run_development_arm(
        arm="N", provider="agy", model="test-model", effort="low",
        output_root=tmp_path / "runs", timeout_seconds=10,
        active_budget_seconds=1,
    )
    assert summary["execution_status"] == "run_time_budget_exhausted"
    assert summary["run_time_budget"]["exhausted_stage"] == "cli"
    assert summary["cli"]["timed_out"] is True
    assert summary["cli"]["timeout_cap"] == "run_budget"
    assert summary["cli"]["timeout_seconds"] <= 1
    assert summary["cli"]["stdout"] == runner._file_record(run_dir / "cli.stdout.jsonl")
    assert summary["controlled_comparison_eligible"] is False


def test_active_budget_after_fourth_t_setup_capture_is_observable(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel = tmp_path / "fake-0.1-py3-none-any.whl"
    wheel.write_bytes(b"offline fake wheel\n")
    real_capture = runner._capture

    def finish_setup_at_deadline(argv: list[str], **kwargs: object) -> dict[str, object]:
        stage = kwargs["stage"]
        assert isinstance(stage, str) and stage in runner.T_SETUP_STEPS
        code = ("print('{\"project\":{\"approval_policy\":\"signed\"}}')"
                if stage == "toolkit_status" else "print('setup step')")
        result = real_capture([sys.executable, "-u", "-c", code], **kwargs)
        if stage == "toolkit_install":
            # The runner's work directory is the capture cwd.
            work = kwargs["cwd"]
            assert isinstance(work, Path)
            executable = work / ".venv/bin/organon"
            executable.parent.mkdir(parents=True, exist_ok=True)
            executable.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            executable.chmod(0o755)
        if stage == "toolkit_status":
            time.sleep(1.1)
        return result

    monkeypatch.setattr(runner, "_capture", finish_setup_at_deadline)
    run_dir, summary = run_development_arm(
        arm="T", provider="opencode", model="minimax/MiniMax-M3",
        effort="uncontrolled", output_root=tmp_path / "runs",
        toolkit_wheel=wheel, timeout_seconds=10, setup_timeout_seconds=10,
        active_budget_seconds=1,
    )
    assert summary["execution_status"] == "run_time_budget_exhausted"
    assert summary["run_time_budget"]["exhausted_stage"] == "toolkit_status"
    assert set(summary["toolkit"]["steps"]) == set(runner.T_SETUP_STEPS)
    assert "signed_policy_verified_in_local_probe" not in summary["toolkit"]
    observer = SCRIPTS / "observe_development_run.py"
    observed = subprocess.run([sys.executable, str(observer), str(run_dir)],
                              capture_output=True, text=True, check=False)
    assert observed.returncode == 0, observed.stderr
    assert json.loads(observed.stdout)["observation_state"] == "partial"


def test_active_budget_exhausts_before_t_status_without_launching_it(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel = tmp_path / "fake-0.1-py3-none-any.whl"
    wheel.write_bytes(b"offline fake wheel\n")
    monkeypatch.setattr(runner, "_setup_toolkit", fake_t_setup)
    real_capture = runner._capture

    def consume_after_cli(argv: list[str], **kwargs: object) -> dict[str, object]:
        result = real_capture(argv, **kwargs)
        if kwargs.get("stage") == "cli":
            time.sleep(1.1)
        return result

    def forbidden_status(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("T status launched after active budget was exhausted")

    monkeypatch.setattr(runner, "_capture", consume_after_cli)
    monkeypatch.setattr(runner, "_inspect_t_ledger", forbidden_status)
    run_dir, summary = run_development_arm(
        arm="T", provider="opencode", model="minimax/MiniMax-M3",
        effort="uncontrolled", output_root=tmp_path / "runs",
        toolkit_wheel=wheel, timeout_seconds=10, active_budget_seconds=1,
    )
    assert summary["execution_status"] == "run_time_budget_exhausted"
    assert summary["run_time_budget"]["exhausted_stage"] == "post_cli"
    assert summary["cli"]["exit_code"] == 0
    assert summary["t_ledger"] is None
    assert not (run_dir / "toolkit_after_status.stdout").exists()
    observer = SCRIPTS / "observe_development_run.py"
    observed = subprocess.run([sys.executable, str(observer), str(run_dir)],
                              capture_output=True, text=True, check=False)
    assert observed.returncode == 0, observed.stderr
    assert json.loads(observed.stdout)["execution_status"] == "run_time_budget_exhausted"
    summary["execution_status"] = "artifacts_ready_for_inspection"
    summary["run_time_budget"]["exhausted_stage"] = None
    summary["run_time_budget"]["elapsed_seconds"] = 0.1
    runner._write_json(run_dir / "run.json", summary)
    forged = subprocess.run([sys.executable, str(observer), str(run_dir)],
                            capture_output=True, text=True, check=False)
    assert forged.returncode == 2


def test_active_budget_is_shared_with_t_status_capture(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel = tmp_path / "fake-0.1-py3-none-any.whl"
    wheel.write_bytes(b"offline fake wheel\n")
    monkeypatch.setattr(runner, "_setup_toolkit", fake_t_setup)
    real_capture = runner._capture
    launched: list[str] = []

    def slow_status(argv: list[str], **kwargs: object) -> dict[str, object]:
        stage = kwargs.get("stage")
        if stage == "toolkit_after_status":
            launched.append(stage)
            argv = [sys.executable, "-u", "-c",
                    "print('partial status', flush=True); import time; time.sleep(3)"]
        return real_capture(argv, **kwargs)

    monkeypatch.setattr(runner, "_capture", slow_status)
    run_dir, summary = run_development_arm(
        arm="T", provider="opencode", model="minimax/MiniMax-M3",
        effort="uncontrolled", output_root=tmp_path / "runs",
        toolkit_wheel=wheel, timeout_seconds=10, setup_timeout_seconds=10,
        active_budget_seconds=1,
    )
    assert launched == ["toolkit_after_status"]
    assert summary["execution_status"] == "run_time_budget_exhausted"
    assert summary["run_time_budget"]["exhausted_stage"] == "toolkit_after_status"
    capture = summary["t_ledger"]["independent_cli_status"]
    assert capture["timed_out"] is True
    assert capture["timeout_cap"] == "run_budget"
    assert capture["stdout"] == runner._file_record(run_dir / "toolkit_after_status.stdout")
    observer = SCRIPTS / "observe_development_run.py"
    observed = subprocess.run([sys.executable, str(observer), str(run_dir)],
                              capture_output=True, text=True, check=False)
    assert observed.returncode == 0, observed.stderr
    assert json.loads(observed.stdout)["verified_streams"]["toolkit_after_status.stdout"] == (
        capture["stdout"])
    forged_elapsed = json.loads(json.dumps(summary))
    forged_elapsed["run_time_budget"]["elapsed_seconds"] = (
        capture["wall_seconds"] + 0.01)
    runner._write_json(run_dir / "run.json", forged_elapsed)
    too_short = subprocess.run([sys.executable, str(observer), str(run_dir)],
                               capture_output=True, text=True, check=False)
    assert too_short.returncode == 2
    assert "shorter than verified capture wall time" in too_short.stderr


def test_active_budget_expires_before_run_directory_without_provider_launch(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_which = runner.shutil.which

    def delayed_which(name: str) -> str | None:
        if name == "codex":
            time.sleep(1.1)
        return real_which(name)

    monkeypatch.setattr(runner.shutil, "which", delayed_which)
    with pytest.raises(RunError, match="active run time budget exhausted at prelaunch"):
        run_development_arm(
            arm="N", provider="codex", model="test-model", effort="medium",
            output_root=tmp_path / "runs", active_budget_seconds=1,
        )
    assert not (tmp_path / "runs").exists()


def test_active_budget_sigkill_grace_does_not_add_three_seconds(
    tmp_path: Path,
) -> None:
    result = runner._capture(
        [sys.executable, "-u", "-c",
         "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
         "print('partial', flush=True); time.sleep(5)"],
        cwd=tmp_path, timeout_seconds=10,
        stdout_path=tmp_path / "stdout", stderr_path=tmp_path / "stderr",
        active_deadline=time.monotonic() + 1, stage="cli",
    )
    assert result["timed_out"] is True
    assert result["timeout_cap"] == "run_budget"
    assert result["wall_seconds"] < 2
    assert (tmp_path / "stdout").read_text().strip() == "partial"


def test_timeout_signals_descendants_before_reaping_group_leader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_code = (
        "import subprocess,sys,time\n"
        "from pathlib import Path\n"
        "child = subprocess.Popen([sys.executable, '-u', '-c', "
        "\"import signal,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "Path('child_ready').write_text('ready'); time.sleep(30)\"])\n"
        "while not Path('child_ready').exists(): time.sleep(0.01)\n"
        "Path('child.pid').write_text(str(child.pid))\n"
        "print('parent ready', flush=True)\n"
        "time.sleep(30)\n"
    )
    real_killpg = runner.os.killpg
    signals: list[int] = []

    def checked_killpg(group_id: int, sent_signal: int) -> None:
        if sent_signal == runner.signal.SIGKILL:
            try:
                # WNOWAIT leaves the leader reserved. ECHILD would mean that
                # the final group signal targets a reusable process-group ID.
                os.waitid(os.P_PID, group_id,
                          os.WEXITED | os.WNOHANG | os.WNOWAIT)
            except ChildProcessError as exc:
                raise AssertionError("SIGKILL was sent after leader reap") from exc
        signals.append(sent_signal)
        real_killpg(group_id, sent_signal)

    monkeypatch.setattr(runner.os, "killpg", checked_killpg)
    result = runner._capture(
        [sys.executable, "-u", "-c", parent_code], cwd=tmp_path,
        timeout_seconds=0.5, stdout_path=tmp_path / "stdout",
        stderr_path=tmp_path / "stderr",
    )
    assert result["timed_out"] is True
    assert signals == [runner.signal.SIGTERM, runner.signal.SIGKILL]
    assert (tmp_path / "stdout").read_text().strip() == "parent ready"
    child_pid = int((tmp_path / "child.pid").read_text())

    def child_running() -> bool:
        stat_file = Path(f"/proc/{child_pid}/stat")
        return stat_file.exists() and stat_file.read_text().split()[2] not in {"Z", "X"}

    stopped_by = time.monotonic() + 1
    while child_running() and time.monotonic() < stopped_by:
        time.sleep(0.01)
    assert not child_running(), "SIGTERM-resistant descendant survived group SIGKILL"


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


def test_t_requires_local_tracer_before_model_call(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel = tmp_path / "specorganon-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"synthetic wheel fixture\n")
    monkeypatch.setattr(runner, "_system_strace", lambda: None)
    with pytest.raises(RunError, match="requires an available strace"):
        run_development_arm(
            arm="T", provider="codex", model="test-model", effort="medium",
            output_root=tmp_path / "runs", toolkit_wheel=wheel,
        )
    assert not (tmp_path / "runs").exists()


def test_t_process_trace_requires_installed_case_publications(tmp_path: Path) -> None:
    work = tmp_path / "work"
    case = work / "case"
    cli = work / ".venv/bin/organon"
    mcp = work / ".venv/bin/organon-mcp"
    ledger = case / "organon.json"
    def quoted(path: Path) -> str:
        return json.dumps(str(path))
    positive = "\n".join([
        f"100 execve({quoted(cli)}, [\"organon\", \"init\"], 0x0) = 0",
        f"100 rename({quoted(case / '.organon-init')}, {quoted(ledger)}) = 0",
        f"101 execve({quoted(mcp)}, [\"organon-mcp\"], 0x0) = 0",
        f"101 rename({quoted(case / '.organon-put')}, {quoted(ledger)}) = 0",
    ]).encode()
    observed = runner._parse_t_process_trace_bytes(positive, work)
    assert observed == {
        "organon_cli_execs": 1, "organon_mcp_execs": 1,
        "tool_ledger_publish_count": 2, "other_ledger_write_count": 0,
        "inspectable": True,
    }

    help_then_copy = "\n".join([
        f"100 execve({quoted(cli)}, [\"organon\", \"--help\"], 0x0) = 0",
        f"99 openat(AT_FDCWD, {quoted(ledger)}, O_WRONLY|O_CREAT|O_TRUNC, 0666) = 3",
        f"100 rename({quoted(case / '.organon-unused')}, {quoted(ledger)}) = -1 ENOENT",
    ]).encode()
    observed = runner._parse_t_process_trace_bytes(help_then_copy, work)
    assert observed["organon_cli_execs"] == 1
    assert observed["tool_ledger_publish_count"] == 0
    assert observed["other_ledger_write_count"] == 1

    replaced_after_real_put = positive + (
        f"\n99 rename({quoted(case / 'copied-ledger')}, {quoted(ledger)}) = 0\n"
    ).encode()
    observed = runner._parse_t_process_trace_bytes(replaced_after_real_put, work)
    assert observed["tool_ledger_publish_count"] == 2
    assert observed["other_ledger_write_count"] == 1

    swapped_case = positive + (
        f"\n99 rename({quoted(case)}, {quoted(work / 'original_case')}) = 0\n"
        f"99 rename({quoted(work / 'copied_case')}, {quoted(case)}) = 0\n"
    ).encode()
    observed = runner._parse_t_process_trace_bytes(swapped_case, work)
    assert observed["tool_ledger_publish_count"] == 2
    assert observed["other_ledger_write_count"] == 2

    linked_old_ledger = positive + (
        f"\n99 unlink({quoted(ledger)}) = 0\n"
        f"99 link({quoted(work / 'old_ledger.json')}, {quoted(ledger)}) = 0\n"
    ).encode()
    observed = runner._parse_t_process_trace_bytes(linked_old_ledger, work)
    assert observed["tool_ledger_publish_count"] == 2
    assert observed["other_ledger_write_count"] == 2

    fd_relative_replace = positive + (
        f"\n99 renameat(3<{work}>, \"old_ledger.json\", "
        f"4<{case}>, \"organon.json\") = 0\n"
    ).encode()
    observed = runner._parse_t_process_trace_bytes(fd_relative_replace, work)
    assert observed["tool_ledger_publish_count"] == 2
    assert observed["other_ledger_write_count"] == 1

    pinned_mcp = "\n".join([
        f"101 execve({quoted(mcp)}, [\"organon-mcp\"], 0x0) = 0",
        f"101 openat(AT_FDCWD, {quoted(case)}, O_PATH|O_DIRECTORY) = 11<{case}>",
        "101 rename(\"/proc/self/fd/11/.organon-put\", "
        "\"/proc/self/fd/11/organon.json\") = 0",
        f"101 close(11<{case}>)  = 0",
        "101 rename(\"/proc/self/fd/11/.organon-after-close\", "
        "\"/proc/self/fd/11/organon.json\") = 0",
    ]).encode()
    observed = runner._parse_t_process_trace_bytes(pinned_mcp, work)
    assert observed["organon_mcp_execs"] == 1
    assert observed["tool_ledger_publish_count"] == 1
    assert observed["other_ledger_write_count"] == 1

    traced_thread = "\n".join([
        f"101 execve({quoted(mcp)}, [{quoted(mcp)}], 0x0 <unfinished ...>",
        "101 <... execve resumed>) = 0",
        f"101 execve({quoted(work / '.venv/bin/python')}, "
        f"[{quoted(work / '.venv/bin/python')}, {quoted(mcp)}], 0x0) = 0",
        "101 clone(child_stack=NULL, flags=CLONE_THREAD) = 102",
        f"102 openat(AT_FDCWD, {quoted(case)}, O_PATH|O_DIRECTORY) = 11<{case}>",
        "102 rename(\"/proc/self/fd/11/.organon-put\", "
        "\"/proc/self/fd/11/organon.json\") = 0",
    ]).encode()
    observed = runner._parse_t_process_trace_bytes(traced_thread, work)
    assert observed["organon_mcp_execs"] == 1
    assert observed["tool_ledger_publish_count"] == 1
    assert observed["other_ledger_write_count"] == 0


def test_t_replay_rejects_forged_green_without_tool_publications(
    tmp_path: Path, fake_clis: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel = tmp_path / "specorganon-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"synthetic wheel fixture\n")
    monkeypatch.setattr(runner, "_setup_toolkit", fake_t_setup)
    run_dir, summary = run_development_arm(
        arm="T", provider="opencode", model="minimax/MiniMax-M3",
        effort="uncontrolled", output_root=tmp_path / "runs", timeout_seconds=10,
        toolkit_wheel=wheel,
    )
    assert summary["execution_status"] == "t_tool_execution_unverified"
    summary["execution_status"] = "artifacts_ready_for_inspection"
    runner._write_json(run_dir / "run.json", summary)
    with pytest.raises(RunError, match="T local tool execution cannot support replay"):
        replay_run_dir(run_dir, summary["artifacts"]["analysis.py"]["sha256"])
    assert not (run_dir / "analysis_replay.stdout").exists()
