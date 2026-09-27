"""Integrated, durable staged local tool session checks."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_replay_sandbox as sandbox  # noqa: E402
import local_run_admission as admission  # noqa: E402
import plan_confirmatory  # noqa: E402
import preflight_assets  # noqa: E402
import stage_released_run  # noqa: E402
import staged_tool_session as session_runner  # noqa: E402
import test_inspect_released_payload as fixture  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_admission_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(admission.ROOT_ENV, str(tmp_path / "admissions"))


FIRST = """
import sys
from pathlib import Path
case, inputs, work = map(Path, sys.argv[1:])
assert (case / 'task.md').read_text() == 'Visible task for R-F.\\n'
assert (inputs / 'tool_policy').is_file()
(work / 'intermediate.txt').write_text('sealed first output\\n')
print('first tool')
"""
SECOND = """
import sys
from pathlib import Path
case, inputs, work = map(Path, sys.argv[1:])
assert (case / 'task.md').is_file()
assert (inputs / 'common_prompt').is_file()
assert (work / 'intermediate.txt').read_text() == 'sealed first output\\n'
(work / 'report.md').write_text('derived from sealed first output\\n')
print('second tool')
"""
MANY_OUTPUTS = """
import sys
from pathlib import Path
work = Path(sys.argv[3])
for index in range(260):
    (work / f'f-{index:03d}').write_text('x')
(work / 'report.md').write_text('done')
"""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tool(path: Path, body: str) -> None:
    path.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
    path.chmod(0o700)


def _stage(
    tmp_path: Path, *, first_body: str = FIRST, cap: int = 2,
) -> tuple[dict, Path, str, Path, Path, Path, tuple[bytes, ...]]:
    first = tmp_path / "first_tool"
    second = tmp_path / "second_tool"
    _tool(first, first_body)
    _tool(second, SECOND)
    schedule, assets, schedule_path, hidden = fixture._fixture(tmp_path)
    policy_path = Path(assets["inputs"]["tool_policy"])
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["generic_tools"] = [
        {"id": "first", "version": "1", "executable_sha256": _sha(first.read_bytes())},
        {"id": "second", "version": "1", "executable_sha256": _sha(second.read_bytes())},
    ]
    policy["limits"]["tool_calls"] = cap
    policy_bytes = json.dumps(policy, sort_keys=True).encode("utf-8")
    policy_path.write_bytes(policy_bytes)
    manifest = dict(schedule["inputs"])
    manifest["tool_policy"] = {**manifest["tool_policy"], "sha256": _sha(policy_bytes)}
    raw = {
        "schema": 1, "seed": schedule["seed"],
        "protocol_sha256": schedule["protocol_sha256"],
        "tool_call_cap": cap, "models": schedule["models"],
        "cases": schedule["cases"], "inputs": manifest,
    }
    schedule = plan_confirmatory.compile_schedule(raw)
    schedule_path.write_text(json.dumps(schedule), encoding="utf-8")
    assets["schedule_sha256"] = schedule["schedule_sha256"]
    assets["input_sha256"] = schedule["input_sha256"]
    run = next(item for item in schedule["runs"] if item["arm"] == "N" and item["case_id"] == "R-F")
    release = tmp_path / "release"
    preflight_assets.preflight(
        schedule, assets, run_id=run["run_id"], output_dir=release,
        development_unsequenced=True,
    )
    stage = tmp_path / "stage"
    stage_released_run.stage_released_run(
        schedule, release, stage, development_unsequenced=True
    )
    return schedule, schedule_path, run["run_id"], stage, first, second, hidden


@pytest.fixture
def available_sandbox() -> None:
    capability = sandbox.probe_sandbox()
    if not capability.available:
        pytest.skip(capability.reason or "sandbox unavailable")


def _cli(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / "staged_tool_session.py"),
         *(str(arg) for arg in args)],
        capture_output=True, text=True, check=False, timeout=20,
    )


def test_two_real_sealed_tools_resume_and_cap(
    tmp_path: Path, available_sandbox: None,
) -> None:
    schedule, schedule_path, run_id, stage, first, second, hidden = _stage(tmp_path)
    session = tmp_path / "session"
    init = _cli("init", schedule_path, run_id, stage, session)
    assert init.returncode == 0, init.stderr
    assert json.loads(init.stdout)["status"] == "ready"
    assert (session.stat().st_mode & 0o777) == 0o700
    assert (stage / "work").is_dir() and list((stage / "work").iterdir()) == []
    first_call = _cli("call", schedule_path, run_id, stage, session, "first", first,
                      "--wall-seconds", "3")
    assert first_call.returncode == 0, first_call.stderr
    first_receipt = json.loads(first_call.stdout)
    assert first_receipt["status"] == "success"
    assert first_receipt["execution_bytes_sealed"] is True
    assert first_receipt["deliverables_present"] is False
    assert first_receipt["reserved_tool_calls"] == 1
    assert first_receipt["provider_calls"] == 0
    assert first_receipt["measured_tokens"] is None
    assert first_receipt["criterion_4"] == "not_assessed"
    assert first_receipt["budget_scope"] == "stage_instance_local"
    assert first_receipt["global_run_limits_enforced"] is False
    assert first_receipt == json.loads((session / "calls" / "000001" / "terminal.json").read_text())
    resumed = _cli("status", schedule_path, run_id, stage, session)
    assert resumed.returncode == 0, resumed.stderr
    assert json.loads(resumed.stdout)["reserved_tool_calls"] == 1
    assert json.loads(resumed.stdout)["status"] == "ready"
    assert json.loads(resumed.stdout)["budget_scope"] == "stage_instance_local"
    assert json.loads(resumed.stdout)["global_run_limits_enforced"] is False
    second_call = _cli("call", schedule_path, run_id, stage, session, "second", second,
                       "--wall-seconds", "3")
    assert second_call.returncode == 0, second_call.stderr
    second_receipt = json.loads(second_call.stdout)
    assert second_receipt["status"] == "success"
    assert second_receipt["execution_bytes_sealed"] is True
    assert second_receipt["deliverables_present"] is True
    assert {item["path"] for item in second_receipt["outputs"]} == {"intermediate.txt", "report.md"}
    assert (stage / "work" / "report.md").read_text() == "derived from sealed first output\n"
    status = session_runner.resume_session(schedule, run_id, stage, session)
    assert status["status"] == "exhausted"
    assert status["remaining_tool_calls"] == 0
    assert "tool_calls cap" in status["blocked_reason"]
    rejected = _cli("call", schedule_path, run_id, stage, session, "first", first)
    assert rejected.returncode == 2
    assert "tool_calls cap" in rejected.stderr
    assert sorted(path.name for path in (session / "calls").iterdir()) == ["000001", "000002"]
    assert set(path.name for path in stage.iterdir()) == {"case", "inputs", "work", "stage.json"}
    for secret in hidden:
        for receipt in (session / "calls").glob("*/terminal.json"):
            assert secret not in receipt.read_bytes()


def test_pending_reservation_survives_crash_and_blocks_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, _, run_id, stage, first, second, _ = _stage(tmp_path)
    session = tmp_path / "session"
    session_runner.create_session(schedule, run_id, stage, session)

    def crash_after_reservation(**kwargs: object) -> None:
        assert (session / "calls" / "000001" / "reservation.json").is_file()
        (stage / "work" / "effect.txt").write_text("possible effect")
        raise KeyboardInterrupt("simulated crash")

    monkeypatch.setattr(session_runner, "run_sandboxed", crash_after_reservation)
    with pytest.raises(KeyboardInterrupt, match="simulated crash"):
        session_runner.call_tool(schedule, run_id, stage, session, "first", first,
                                 wall_seconds=3)
    status = session_runner.resume_session(schedule, run_id, stage, session)
    assert status["status"] == "indeterminate"
    assert status["pending_call"] == 1
    assert status["reserved_tool_calls"] == 1
    assert status["remaining_tool_calls"] == 1
    assert (stage / "work" / "effect.txt").read_text() == "possible effect"
    with pytest.raises(session_runner.SessionError, match="indeterminate"):
        session_runner.call_tool(schedule, run_id, stage, session, "second", second)
    assert not (session / "calls" / "000002").exists()
    assert not (session / "calls" / "000001" / "terminal.json").exists()


def test_mutated_stage_input_blocks_resume_and_next_call(
    tmp_path: Path, available_sandbox: None,
) -> None:
    schedule, _, run_id, stage, first, second, _ = _stage(tmp_path)
    session = tmp_path / "session"
    session_runner.create_session(schedule, run_id, stage, session)
    session_runner.call_tool(schedule, run_id, stage, session, "first", first, wall_seconds=3)
    (stage / "inputs" / "arm_prompt").write_text("tampered", encoding="utf-8")
    status = session_runner.resume_session(schedule, run_id, stage, session)
    assert status["status"] == "blocked"
    assert "stage case, inputs" in status["blocked_reason"]
    with pytest.raises(session_runner.SessionError, match="stage case, inputs"):
        session_runner.call_tool(schedule, run_id, stage, session, "second", second)
    assert not (session / "calls" / "000002").exists()


def test_mutated_work_between_calls_blocks_resume_and_next_call(
    tmp_path: Path, available_sandbox: None,
) -> None:
    schedule, _, run_id, stage, first, second, _ = _stage(tmp_path)
    session = tmp_path / "session"
    session_runner.create_session(schedule, run_id, stage, session)
    session_runner.call_tool(schedule, run_id, stage, session, "first", first, wall_seconds=3)
    (stage / "work" / "intermediate.txt").write_text("changed outside session")
    status = session_runner.resume_session(schedule, run_id, stage, session)
    assert status["status"] == "blocked"
    assert "work tree differs" in status["blocked_reason"]
    with pytest.raises(session_runner.SessionError, match="work tree differs"):
        session_runner.call_tool(schedule, run_id, stage, session, "second", second)
    assert not (session / "calls" / "000002").exists()


def test_corrupt_terminal_is_indeterminate_and_never_retried(
    tmp_path: Path, available_sandbox: None,
) -> None:
    schedule, _, run_id, stage, first, second, _ = _stage(tmp_path)
    session = tmp_path / "session"
    session_runner.create_session(schedule, run_id, stage, session)
    session_runner.call_tool(schedule, run_id, stage, session, "first", first, wall_seconds=3)
    terminal = session / "calls" / "000001" / "terminal.json"
    terminal.write_text('{"truncated":', encoding="utf-8")
    status = session_runner.resume_session(schedule, run_id, stage, session)
    assert status["status"] == "indeterminate"
    assert status["pending_call"] == 1
    assert status["reserved_tool_calls"] == 1
    assert "incomplete or unreadable" in status["pending_reason"]
    with pytest.raises(session_runner.SessionError, match="indeterminate"):
        session_runner.call_tool(schedule, run_id, stage, session, "second", second)
    assert not (session / "calls" / "000002").exists()
    assert terminal.read_text() == '{"truncated":'


def test_forged_success_without_deliverable_is_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, _, run_id, stage, first, second, _ = _stage(tmp_path)
    session = tmp_path / "session"
    session_runner.create_session(schedule, run_id, stage, session)

    def crash_after_reservation(**kwargs: object) -> None:
        raise KeyboardInterrupt("simulated crash")

    monkeypatch.setattr(session_runner, "run_sandboxed", crash_after_reservation)
    with pytest.raises(KeyboardInterrupt):
        session_runner.call_tool(schedule, run_id, stage, session, "first", first,
                                 wall_seconds=3)
    call_dir = session / "calls" / "000001"
    reservation_data = (call_dir / "reservation.json").read_bytes()
    reservation = json.loads(reservation_data)
    for name in ("stdout", "stderr"):
        stream = call_dir / name
        stream.write_bytes(b"")
        stream.chmod(0o600)
    forged = {
        "schema": 1, "classification": session_runner.CLASSIFICATION,
        "notice": session_runner.NOTICE, "call_number": 1,
        "budget_scope": "stage_instance_local", "global_run_limits_enforced": False,
        "reservation_sha256": _sha(reservation_data),
        "run_id": run_id,
        "run_sha256": next(item["run_sha256"] for item in schedule["runs"] if item["run_id"] == run_id),
        "schedule_sha256": schedule["schedule_sha256"],
        "tool_id": reservation["tool_id"], "tool_version": reservation["tool_version"],
        "executable_sha256": reservation["executable_sha256"],
        "sealed_executable_sha256": reservation["executable_sha256"],
        "execution_bytes_sealed": True, "executable_unchanged_after_run": True,
        "policy_sha256": reservation["policy_sha256"],
        "runtime_image_sha256_declared": "a" * 64,
        "runtime_image_verified": False, "status": "success", "exit_code": 0,
        "timed_out": False, "launch_error": None,
        "sandbox_duration_seconds": 0.01, "local_elapsed_seconds": 0.01,
        "active_seconds_charged": 1.01, "active_budget_overrun": False,
        "stage_unchanged_after_run": True, "output_inventory_complete": True,
        "output_inventory_reason": None,
        "work_before_sha256": reservation["work_before_sha256"],
        "work_after_sha256": reservation["work_before_sha256"],
        "outputs": [], "deliverables": ["report.md"], "deliverables_present": True,
        "stdout": str(call_dir / "stdout"), "stderr": str(call_dir / "stderr"),
        "reserved_tool_calls": 1, "provider_calls": 0,
        "measured_tokens": None, "criterion_4": "not_assessed", "provider_receipt": False,
    }
    (call_dir / "terminal.json").write_bytes(session_runner._canonical_bytes(forged, newline=True))
    status = session_runner.resume_session(schedule, run_id, stage, session)
    assert status["status"] == "indeterminate"
    assert status["pending_reason"] == "latest terminal receipt is invalid"
    with pytest.raises(session_runner.SessionError, match="indeterminate"):
        session_runner.call_tool(schedule, run_id, stage, session, "second", second)
    assert not (call_dir.parent / "000002").exists()


def test_forged_output_list_cannot_make_missing_deliverable_ready(
    tmp_path: Path, available_sandbox: None,
) -> None:
    schedule, _, run_id, stage, first, second, _ = _stage(tmp_path)
    session = tmp_path / "session"
    session_runner.create_session(schedule, run_id, stage, session)
    session_runner.call_tool(schedule, run_id, stage, session, "first", first,
                             wall_seconds=3)
    terminal = session / "calls" / "000001" / "terminal.json"
    forged = json.loads(terminal.read_text())
    forged["outputs"].append({"path": "report.md", "bytes": 4, "sha256": _sha(b"fake")})
    forged["deliverables_present"] = True
    terminal.write_bytes(session_runner._canonical_bytes(forged, newline=True))
    status = session_runner.resume_session(schedule, run_id, stage, session)
    assert status["status"] == "blocked"
    assert "terminal output list differs" in status["blocked_reason"]
    with pytest.raises(session_runner.SessionError, match="terminal output list differs"):
        session_runner.call_tool(schedule, run_id, stage, session, "second", second)
    assert not (session / "calls" / "000002").exists()


def test_deeply_nested_terminal_is_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, _, run_id, stage, first, second, _ = _stage(tmp_path)
    session = tmp_path / "session"
    session_runner.create_session(schedule, run_id, stage, session)
    monkeypatch.setattr(
        session_runner, "run_sandboxed",
        lambda **kwargs: (_ for _ in ()).throw(KeyboardInterrupt("simulated crash")),
    )
    with pytest.raises(KeyboardInterrupt):
        session_runner.call_tool(schedule, run_id, stage, session, "first", first,
                                 wall_seconds=3)
    terminal = session / "calls" / "000001" / "terminal.json"
    terminal.write_text("[" * 1500 + "0" + "]" * 1500, encoding="utf-8")
    status = session_runner.resume_session(schedule, run_id, stage, session)
    assert status["status"] == "indeterminate"
    assert status["pending_call"] == 1
    with pytest.raises(session_runner.SessionError, match="indeterminate"):
        session_runner.call_tool(schedule, run_id, stage, session, "second", second)
    assert not (session / "calls" / "000002").exists()


def test_output_inventory_incomplete_blocks_continuation(
    tmp_path: Path, available_sandbox: None,
) -> None:
    schedule, _, run_id, stage, first, second, _ = _stage(tmp_path, first_body=MANY_OUTPUTS)
    session = tmp_path / "session"
    session_runner.create_session(schedule, run_id, stage, session)
    receipt = session_runner.call_tool(schedule, run_id, stage, session, "first", first,
                                       wall_seconds=3)
    assert receipt["status"] == "output_inventory_incomplete"
    assert receipt["output_inventory_complete"] is False
    assert receipt["deliverables_present"] is None
    assert len(receipt["outputs"]) <= session_runner.MAX_WORK_FILES
    status = session_runner.resume_session(schedule, run_id, stage, session)
    assert status["status"] == "blocked"
    with pytest.raises(session_runner.SessionError, match="blocked"):
        session_runner.call_tool(schedule, run_id, stage, session, "second", second)
    assert not (session / "calls" / "000002").exists()


def test_init_rejects_existing_session_and_nonempty_work(tmp_path: Path) -> None:
    schedule, _, run_id, stage, _, _, _ = _stage(tmp_path)
    session = tmp_path / "session"
    session_runner.create_session(schedule, run_id, stage, session)
    original = (session / "session.json").read_bytes()
    with pytest.raises(FileExistsError):
        session_runner.create_session(schedule, run_id, stage, session)
    assert (session / "session.json").read_bytes() == original
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    second_schedule, _, second_run_id, second_stage, _, _, _ = _stage(fresh)
    (second_stage / "work" / "old.txt").write_text("old")
    with pytest.raises(session_runner.StageVerificationError, match="work directory is not empty"):
        session_runner.create_session(
            second_schedule, second_run_id, second_stage, tmp_path / "new-session"
        )
    assert not (tmp_path / "new-session").exists()


def test_stage_run_anchor_rejects_second_session_and_budget_reset(
    tmp_path: Path, available_sandbox: None,
) -> None:
    schedule, _, run_id, stage, first, _, _ = _stage(tmp_path, cap=1)
    session = tmp_path / "session"
    session_runner.create_session(schedule, run_id, stage, session,
                                  active_budget_seconds=5)
    with pytest.raises(session_runner.SessionError, match="already has a durable local session anchor"):
        session_runner.create_session(schedule, run_id, stage, tmp_path / "second-session")
    assert not (tmp_path / "second-session").exists()
    receipt = session_runner.call_tool(schedule, run_id, stage, session, "first", first,
                                       wall_seconds=2)
    assert receipt["status"] == "success"
    assert session_runner.resume_session(schedule, run_id, stage, session)["status"] == "exhausted"
    with pytest.raises(session_runner.SessionError, match="already has a durable local session anchor"):
        session_runner.create_session(schedule, run_id, stage, tmp_path / "third-session",
                                      active_budget_seconds=5)
    assert not (tmp_path / "third-session").exists()
    assert sorted(path.name for path in (session / "calls").iterdir()) == ["000001"]


def test_same_release_run_second_stage_cannot_spend_local_cap(
    tmp_path: Path, available_sandbox: None,
) -> None:
    schedule, _, run_id, first_stage, first, _, _ = _stage(tmp_path, cap=1)
    second_stage = tmp_path / "second-stage"
    stage_released_run.stage_released_run(
        schedule, tmp_path / "release", second_stage,
        development_unsequenced=True,
    )
    assert first_stage != second_stage
    first_session = tmp_path / "first-session"
    second_session = tmp_path / "second-session"
    first_summary = session_runner.create_session(schedule, run_id, first_stage, first_session)
    second_summary = session_runner.create_session(schedule, run_id, second_stage, second_session)
    assert first_summary["run_id"] == second_summary["run_id"] == run_id
    assert first_summary["schedule_sha256"] == second_summary["schedule_sha256"]
    assert first_summary["local_run_claim_status"] == "unclaimed"
    assert second_summary["local_run_claim_status"] == "unclaimed"
    receipt = session_runner.call_tool(schedule, run_id, first_stage, first_session,
                                       "first", first, wall_seconds=3)
    assert receipt["status"] == "success"
    assert receipt["reserved_tool_calls"] == 1
    assert receipt["global_run_limits_enforced"] is False
    assert (first_stage / "work" / "intermediate.txt").read_text() == "sealed first output\n"
    first_status = session_runner.resume_session(schedule, run_id, first_stage, first_session)
    assert first_status["status"] == "exhausted"
    assert first_status["remaining_tool_calls"] == 0
    second_status = session_runner.resume_session(schedule, run_id, second_stage, second_session)
    assert second_status["status"] == "blocked"
    assert "another local owner" in second_status["blocked_reason"]
    with pytest.raises(session_runner.SessionError, match="another local owner"):
        session_runner.call_tool(schedule, run_id, second_stage, second_session,
                                 "first", first, wall_seconds=3)
    assert list((second_stage / "work").iterdir()) == []
    assert session_runner._anchor_path(first_stage, run_id) != session_runner._anchor_path(second_stage, run_id)


def test_manifest_write_eio_does_not_publish_anchor_or_block_new_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, _, run_id, stage, _, _, _ = _stage(tmp_path)
    first_session = tmp_path / "first-session"
    original = session_runner._write_json

    def fail_manifest(path: Path, value: dict) -> str:
        if path.name == "session.json":
            raise OSError(errno.EIO, "injected manifest write failure")
        return original(path, value)

    monkeypatch.setattr(session_runner, "_write_json", fail_manifest)
    with pytest.raises(OSError, match="injected manifest write failure"):
        session_runner.create_session(schedule, run_id, stage, first_session)
    assert first_session.is_dir()
    assert not (first_session / "session.json").exists()
    assert not session_runner._anchor_path(stage, run_id).exists()
    monkeypatch.setattr(session_runner, "_write_json", original)
    second_session = tmp_path / "second-session"
    assert session_runner.create_session(schedule, run_id, stage, second_session)["status"] == "ready"
    assert session_runner._anchor_path(stage, run_id).is_file()
    with pytest.raises((session_runner.SessionError, session_runner.ToolPolicyError)):
        session_runner.resume_session(schedule, run_id, stage, first_session)


def test_manifest_without_anchor_is_unusable_and_new_init_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, _, run_id, stage, _, _, _ = _stage(tmp_path)
    first_session = tmp_path / "first-session"
    original = session_runner._write_anchor

    def fail_anchor(stage_path: Path, selected_run_id: str, value: dict) -> str:
        raise OSError(errno.EIO, "injected anchor publication failure")

    monkeypatch.setattr(session_runner, "_write_anchor", fail_anchor)
    with pytest.raises(OSError, match="injected anchor publication failure"):
        session_runner.create_session(schedule, run_id, stage, first_session)
    assert (first_session / "session.json").is_file()
    assert not session_runner._anchor_path(stage, run_id).exists()
    with pytest.raises(session_runner.SessionError, match="anchor cannot be read"):
        session_runner.resume_session(schedule, run_id, stage, first_session)
    monkeypatch.setattr(session_runner, "_write_anchor", original)
    second_session = tmp_path / "second-session"
    assert session_runner.create_session(schedule, run_id, stage, second_session)["status"] == "ready"
    with pytest.raises(session_runner.SessionError, match="anchor differs"):
        session_runner.resume_session(schedule, run_id, stage, first_session)


def test_real_crash_during_anchor_temp_write_does_not_block_new_init(
    tmp_path: Path,
) -> None:
    schedule, schedule_path, run_id, stage, _, _, _ = _stage(tmp_path)
    first_session = tmp_path / "crashed-session"
    script = """
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import staged_tool_session as session
original_write = os.write
def crash_during_anchor_write(fd, data):
    path = os.readlink(f'/proc/self/fd/{fd}')
    if '.staged-local-session-' in path and path.endswith('.tmp'):
        original_write(fd, b'{')
        os.fsync(fd)
        os._exit(73)
    return original_write(fd, data)
os.write = crash_during_anchor_write
schedule = json.loads(Path(sys.argv[2]).read_text())
session.create_session(schedule, sys.argv[3], Path(sys.argv[4]), Path(sys.argv[5]))
"""
    process = subprocess.run(
        [sys.executable, "-B", "-c", script, str(SCRIPTS), str(schedule_path),
         run_id, str(stage), str(first_session)],
        capture_output=True, text=True, check=False, timeout=20,
    )
    assert process.returncode == 73, process.stderr
    assert (first_session / "session.json").is_file()
    anchor = session_runner._anchor_path(stage, run_id)
    assert not anchor.exists()
    temporaries = list(stage.parent.glob(f"{anchor.name}.*.tmp"))
    assert len(temporaries) == 1
    assert temporaries[0].read_bytes() == b"{"
    with pytest.raises(session_runner.SessionError, match="anchor cannot be read"):
        session_runner.resume_session(schedule, run_id, stage, first_session)
    second_session = tmp_path / "recovered-session"
    assert session_runner.create_session(schedule, run_id, stage, second_session)["status"] == "ready"
    assert anchor.is_file()
    assert temporaries[0].read_bytes() == b"{"
    with pytest.raises(session_runner.SessionError, match="anchor differs"):
        session_runner.resume_session(schedule, run_id, stage, first_session)


def test_call_waits_for_anchor_parent_fsync_commit(
    tmp_path: Path, available_sandbox: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, _, run_id, stage, first, _, _ = _stage(tmp_path)
    session = tmp_path / "session"
    anchor = session_runner._anchor_path(stage, run_id)
    entered = threading.Event()
    release = threading.Event()
    committed = threading.Event()
    launched = threading.Event()
    original_fsync = os.fsync
    original_sandbox = session_runner.run_sandboxed
    init_results: list[dict | BaseException] = []
    call_results: list[dict | BaseException] = []
    paused = False

    def pause_commit(fd: int) -> None:
        nonlocal paused
        if (not paused and os.readlink(f"/proc/self/fd/{fd}") == str(stage.parent)
            and anchor.exists()):
            paused = True
            entered.set()
            assert release.wait(10)
            original_fsync(fd)
            committed.set()
            return
        original_fsync(fd)

    def mark_launch(**kwargs: object) -> sandbox.SandboxResult:
        launched.set()
        assert committed.is_set(), "sandbox launched before anchor parent fsync"
        return original_sandbox(**kwargs)

    def initialize() -> None:
        try:
            init_results.append(session_runner.create_session(schedule, run_id, stage, session))
        except BaseException as exc:
            init_results.append(exc)

    def invoke() -> None:
        try:
            call_results.append(session_runner.call_tool(
                schedule, run_id, stage, session, "first", first, wall_seconds=3
            ))
        except BaseException as exc:
            call_results.append(exc)

    monkeypatch.setattr(session_runner.os, "fsync", pause_commit)
    monkeypatch.setattr(session_runner, "run_sandboxed", mark_launch)
    init_thread = threading.Thread(target=initialize)
    init_thread.start()
    assert entered.wait(10)
    assert anchor.is_file()
    assert (session / "session.json").is_file()
    call_thread = threading.Thread(target=invoke)
    call_thread.start()
    try:
        assert not launched.wait(0.25)
        assert not (stage / "work" / "intermediate.txt").exists()
    finally:
        release.set()
        init_thread.join(timeout=15)
        call_thread.join(timeout=15)
    assert not init_thread.is_alive() and not call_thread.is_alive()
    assert committed.is_set() and launched.is_set()
    assert len(call_results) == 1 and isinstance(call_results[0], dict)
    assert call_results[0]["status"] == "success"
    assert len(init_results) == 1
    assert isinstance(init_results[0], dict) or (
        isinstance(init_results[0], session_runner.SessionError)
        and "busy" in str(init_results[0])
    )


def test_failed_anchor_parent_fsync_cannot_authorize_call_until_reconfirmed(
    tmp_path: Path, available_sandbox: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, _, run_id, stage, first, _, _ = _stage(tmp_path)
    session = tmp_path / "session"
    anchor = session_runner._anchor_path(stage, run_id)
    original_fsync = os.fsync
    fail_durability = True

    def fail_parent_fsync(fd: int) -> None:
        if (fail_durability and os.readlink(f"/proc/self/fd/{fd}") == str(stage.parent)
            and anchor.exists()):
            raise OSError(errno.EIO, "injected anchor parent fsync failure")
        original_fsync(fd)

    monkeypatch.setattr(session_runner.os, "fsync", fail_parent_fsync)
    with pytest.raises(OSError, match="injected anchor parent fsync failure"):
        session_runner.create_session(schedule, run_id, stage, session)
    assert anchor.is_file()
    assert (session / "session.json").is_file()
    with pytest.raises(session_runner.SessionError, match="durability could not be confirmed"):
        session_runner.resume_session(schedule, run_id, stage, session)
    with pytest.raises(session_runner.SessionError, match="durability could not be confirmed"):
        session_runner.call_tool(schedule, run_id, stage, session, "first", first,
                                 wall_seconds=3)
    assert list((session / "calls").iterdir()) == []
    assert not (stage / "work" / "intermediate.txt").exists()
    fail_durability = False
    assert session_runner.resume_session(schedule, run_id, stage, session)["status"] == "ready"
    receipt = session_runner.call_tool(schedule, run_id, stage, session, "first", first,
                                       wall_seconds=3)
    assert receipt["status"] == "success"


def test_concurrent_init_publishes_one_anchor_after_both_manifests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, _, run_id, stage, _, _, _ = _stage(tmp_path)
    barrier = threading.Barrier(2)
    original = session_runner._write_anchor
    results: list[tuple[Path, dict | BaseException]] = []

    def synchronize_publication(stage_path: Path, selected_run_id: str, value: dict) -> str:
        barrier.wait(timeout=10)
        return original(stage_path, selected_run_id, value)

    monkeypatch.setattr(session_runner, "_write_anchor", synchronize_publication)

    def initialize(path: Path) -> None:
        try:
            result: dict | BaseException = session_runner.create_session(
                schedule, run_id, stage, path
            )
        except BaseException as exc:
            result = exc
        results.append((path, result))

    paths = [tmp_path / "session-a", tmp_path / "session-b"]
    threads = [threading.Thread(target=initialize, args=(path,)) for path in paths]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == 2
    winners = [(path, result) for path, result in results if isinstance(result, dict)]
    losers = [(path, result) for path, result in results if isinstance(result, BaseException)]
    assert len(winners) == 1
    assert len(losers) == 1
    assert winners[0][1]["status"] == "ready"
    assert isinstance(losers[0][1], session_runner.SessionError)
    assert "already has a durable local session anchor" in str(losers[0][1])
    assert (losers[0][0] / "session.json").is_file()
    assert not (losers[0][0] / "calls" / "000001").exists()
    with pytest.raises(session_runner.SessionError, match="anchor differs"):
        session_runner.resume_session(schedule, run_id, stage, losers[0][0])
    assert session_runner.resume_session(schedule, run_id, stage, winners[0][0])["status"] == "ready"
    anchor_path = session_runner._anchor_path(stage, run_id)
    anchor_bytes = anchor_path.read_bytes()
    assert json.loads(anchor_bytes)["session_dir"] == str(winners[0][0])
    with pytest.raises(session_runner.SessionError, match="already has a durable local session anchor"):
        session_runner.create_session(schedule, run_id, stage, tmp_path / "third-session")
    assert anchor_path.read_bytes() == anchor_bytes


def test_wall_deadline_rechecked_after_durable_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, _, run_id, stage, first, _, _ = _stage(tmp_path)
    session = tmp_path / "session"
    session_runner.create_session(schedule, run_id, stage, session,
                                  wall_budget_seconds=4)
    original_write = session_runner._write_json

    def delayed_reservation(path: Path, value: dict) -> str:
        digest = original_write(path, value)
        if path.name == "reservation.json":
            time.sleep(2.2)
        return digest

    monkeypatch.setattr(session_runner, "_write_json", delayed_reservation)
    receipt = session_runner.call_tool(schedule, run_id, stage, session, "first", first,
                                       wall_seconds=1)
    assert receipt["status"] == "launch_failure"
    assert "wall budget expired after reservation" in receipt["launch_error"]
    assert receipt["execution_bytes_sealed"] is False
    assert not (stage / "work" / "intermediate.txt").exists()
    assert (session / "calls" / "000001" / "terminal.json").is_file()
    assert session_runner.resume_session(schedule, run_id, stage, session)["reserved_tool_calls"] == 1


def test_idle_time_uses_wall_budget_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    schedule, _, run_id, stage, first, _, _ = _stage(tmp_path)
    session = tmp_path / "session"
    session_runner.create_session(schedule, run_id, stage, session,
                                  active_budget_seconds=10, wall_budget_seconds=20)
    created_ns = json.loads((session / "session.json").read_text())["created_ns"]
    monkeypatch.setattr(session_runner.time, "time_ns", lambda: created_ns + 10_000_000_000)
    status = session_runner.resume_session(schedule, run_id, stage, session)
    assert status["status"] == "ready"
    assert status["wall_elapsed_seconds"] == 10
    assert status["local_elapsed_seconds"] == 0
    assert status["active_seconds_charged"] == 0
    monkeypatch.setattr(session_runner.time, "time_ns", lambda: created_ns + 20_000_000_000)
    status = session_runner.resume_session(schedule, run_id, stage, session)
    assert status["status"] == "exhausted"
    assert "wall budget" in status["blocked_reason"]
    with pytest.raises(session_runner.SessionError, match="wall budget"):
        session_runner.call_tool(schedule, run_id, stage, session, "first", first,
                                 wall_seconds=1)
    assert list((session / "calls").iterdir()) == []


def test_active_reservation_and_concurrent_call_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, _, run_id, stage, first, _, _ = _stage(tmp_path)
    session = tmp_path / "session"
    session_runner.create_session(schedule, run_id, stage, session,
                                  active_budget_seconds=3)
    with pytest.raises(session_runner.SessionError, match="active budget"):
        session_runner.call_tool(schedule, run_id, stage, session, "first", first,
                                 wall_seconds=2.5)
    assert list((session / "calls").iterdir()) == []
    entered = threading.Event()
    release = threading.Event()
    original = session_runner.run_sandboxed
    errors: list[BaseException] = []

    def hold_before_launch(**kwargs: object) -> sandbox.SandboxResult:
        entered.set()
        assert release.wait(5)
        return original(**kwargs)

    def first_call() -> None:
        try:
            session_runner.call_tool(schedule, run_id, stage, session, "first", first,
                                     wall_seconds=1)
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.setattr(session_runner, "run_sandboxed", hold_before_launch)
    thread = threading.Thread(target=first_call)
    thread.start()
    try:
        assert entered.wait(5)
        assert (session / "calls" / "000001" / "reservation.json").is_file()
        with pytest.raises(session_runner.SessionError, match="busy"):
            session_runner.call_tool(schedule, run_id, stage, session, "first", first,
                                     wall_seconds=1)
    finally:
        release.set()
        thread.join(timeout=10)
    assert not errors
    assert not thread.is_alive()
    assert sorted(path.name for path in (session / "calls").iterdir()) == ["000001"]
