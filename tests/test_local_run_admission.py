"""Host-local admission shared by staged sessions and one-shot tools."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_replay_sandbox as sandbox  # noqa: E402
import local_run_admission as admission  # noqa: E402
import run_staged_local_tool as oneshot  # noqa: E402
import stage_released_run  # noqa: E402
import staged_tool_session as staged  # noqa: E402
import test_staged_tool_session as fixture  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_admission_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(admission.ROOT_ENV, str(tmp_path / "admissions"))


@pytest.fixture
def available_sandbox() -> None:
    capability = sandbox.probe_sandbox()
    if not capability.available:
        pytest.skip(capability.reason or "sandbox unavailable")


def _copies(tmp_path: Path, *, cap: int = 1) -> tuple[dict, str, Path, Path, Path]:
    schedule, _, run_id, first_stage, first_tool, _, _ = fixture._stage(tmp_path, cap=cap)
    second_stage = tmp_path / "second-stage"
    stage_released_run.stage_released_run(
        schedule, tmp_path / "release", second_stage,
        development_unsequenced=True,
    )
    return schedule, run_id, first_stage, second_stage, first_tool


def _claim_path(root: Path, schedule: dict, run_id: str) -> Path:
    return root / f"{admission._key(schedule['schedule_sha256'], run_id)}.json"


def test_private_claim_race_and_distinct_run_ids(tmp_path: Path) -> None:
    root = tmp_path / "admissions"
    registry = admission.descriptor()
    sha = "a" * 64
    first = admission.owner("staged", tmp_path / "stage-a", tmp_path / "session-a")
    second = admission.owner("oneshot", tmp_path / "stage-b", tmp_path / "receipt-b")
    barrier = threading.Barrier(2)
    outcomes: list[tuple[dict, str | BaseException]] = []

    def publish(selected: dict) -> None:
        barrier.wait(timeout=10)
        try:
            result: str | BaseException = admission.publish_claim(sha, "run-one", selected, registry)
        except BaseException as exc:
            result = exc
        outcomes.append((selected, result))

    threads = [threading.Thread(target=publish, args=(selected,)) for selected in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)
    winners = [(selected, value) for selected, value in outcomes if isinstance(value, str)]
    losers = [(selected, value) for selected, value in outcomes if isinstance(value, BaseException)]
    assert len(winners) == len(losers) == 1
    assert isinstance(losers[0][1], admission.AdmissionError)
    assert "already has" in str(losers[0][1])
    assert admission.require_claim(sha, "run-one", winners[0][0], registry) == winners[0][1]
    with pytest.raises(admission.AdmissionError, match="another local owner"):
        admission.require_claim(sha, "run-one", losers[0][0], registry)
    assert (root.stat().st_mode & 0o777) == 0o700
    first_claim = root / f"{admission._key(sha, 'run-one')}.json"
    assert (first_claim.stat().st_mode & 0o777) == 0o600
    assert json.loads(first_claim.read_text())["attempt_number"] == 1
    # The key includes run_id: another run in the same schedule is admitted.
    other_digest = admission.publish_claim(sha, "run-two", losers[0][0], registry)
    assert admission.require_claim(sha, "run-two", losers[0][0], registry) == other_digest


def test_root_is_fixed_from_passwd_and_rejects_symlink(tmp_path: Path,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(admission.ROOT_ENV)
    monkeypatch.setenv("HOME", str(tmp_path / "false-home"))
    monkeypatch.setenv("TMPDIR", str(tmp_path / "false-temp"))
    assert admission.configured_root() == (
        Path(admission.pwd.getpwuid(os.geteuid()).pw_dir) / ".specorganon-local-admissions-v1"
    )
    private = tmp_path / "actual"
    private.mkdir(mode=0o700)
    (tmp_path / "symlink").symlink_to(private, target_is_directory=True)
    with pytest.raises(OSError):
        admission.descriptor(tmp_path / "symlink", create=False)


def test_two_prepared_stage_copies_only_one_launches(
    tmp_path: Path, available_sandbox: None,
) -> None:
    original_goal = hashlib.sha256((ROOT / "GOAL.md").read_bytes()).hexdigest()
    schedule, run_id, first_stage, second_stage, tool = _copies(tmp_path)
    protocol = schedule["protocol_sha256"]
    first_session, second_session = tmp_path / "first-session", tmp_path / "second-session"
    first_ready = staged.create_session(schedule, run_id, first_stage, first_session)
    second_ready = staged.create_session(schedule, run_id, second_stage, second_session)
    assert first_ready["status"] == second_ready["status"] == "ready"
    assert first_ready["local_run_claim_status"] == "unclaimed"
    receipt = staged.call_tool(schedule, run_id, first_stage, first_session,
                               "first", tool, wall_seconds=3)
    assert receipt["status"] == "success"
    assert receipt["attempt_number"] == 1
    assert receipt["global_run_limits_enforced"] is False
    assert staged.resume_session(schedule, run_id, first_stage, first_session)["status"] == "exhausted"
    loser = staged.resume_session(schedule, run_id, second_stage, second_session)
    assert loser["status"] == "blocked" and loser["local_run_claim_status"] == "blocked"
    assert "another local owner" in loser["blocked_reason"]
    with pytest.raises(staged.SessionError, match="another local owner"):
        staged.call_tool(schedule, run_id, second_stage, second_session,
                         "first", tool, wall_seconds=3)
    assert not (second_session / "calls" / "000001").exists()
    assert list((second_stage / "work").iterdir()) == []
    manifest = json.loads((first_session / "session.json").read_text())
    reservation = json.loads((first_session / "calls" / "000001" / "reservation.json").read_text())
    anchor = json.loads(staged._anchor_path(first_stage, run_id).read_text())
    for record in (manifest, reservation, anchor, receipt):
        assert record["local_run_admission_root"] == str(tmp_path / "admissions")
        assert record["local_run_admission_root_identity"] == receipt["local_run_admission_root_identity"]
        assert record["local_run_claim_sha256"] == receipt["local_run_claim_sha256"]
        assert record["attempt_number"] == 1
    assert schedule["protocol_sha256"] == protocol
    assert hashlib.sha256((ROOT / "GOAL.md").read_bytes()).hexdigest() == original_goal


@pytest.mark.parametrize("stage_first", [True, False])
def test_stage_and_oneshot_exclude_each_other_in_both_orders(
    tmp_path: Path, available_sandbox: None, stage_first: bool,
) -> None:
    schedule, run_id, stage_a, stage_b, tool = _copies(tmp_path)
    session = tmp_path / "session"
    staged.create_session(schedule, run_id, stage_a, session)
    receipt_dir = tmp_path / "oneshot-receipt"
    if stage_first:
        winner = staged.call_tool(schedule, run_id, stage_a, session, "first", tool,
                                  wall_seconds=3)
        assert winner["status"] == "success"
        with pytest.raises(admission.AdmissionError, match="already has"):
            oneshot.run_staged_local_tool(schedule, run_id, stage_b, "first", tool, receipt_dir)
        assert not (receipt_dir / "reservation.json").exists()
        assert list((stage_b / "work").iterdir()) == []
    else:
        winner = oneshot.run_staged_local_tool(
            schedule, run_id, stage_b, "first", tool, receipt_dir, wall_seconds=3
        )
        assert winner["status"] == "deliverables_missing"
        assert winner["attempt_number"] == 1
        assert winner["global_run_limits_enforced"] is False
        assert json.loads((receipt_dir / "reservation.json").read_text())[
            "local_run_claim_sha256"
        ] == winner["local_run_claim_sha256"]
        assert staged.resume_session(schedule, run_id, stage_a, session)["status"] == "blocked"
        with pytest.raises(staged.SessionError, match="another local owner"):
            staged.call_tool(schedule, run_id, stage_a, session, "first", tool,
                             wall_seconds=3)
        assert not (session / "calls" / "000001").exists()


def test_concurrent_first_calls_publish_one_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, run_id, stage_a, stage_b, tool = _copies(tmp_path)
    session_a, session_b = tmp_path / "session-a", tmp_path / "session-b"
    staged.create_session(schedule, run_id, stage_a, session_a)
    staged.create_session(schedule, run_id, stage_b, session_b)
    barrier = threading.Barrier(2)
    original = admission.acquire_staged_claim
    launched: list[Path] = []
    results: list[BaseException] = []

    def synchronized_claim(*args: object, **kwargs: object) -> str:
        barrier.wait(timeout=10)
        return original(*args, **kwargs)

    def crash_after_reservation(**kwargs: object) -> None:
        launched.append(Path(kwargs["write_roots"][0]))
        raise KeyboardInterrupt("simulated child crash")

    monkeypatch.setattr(admission, "acquire_staged_claim", synchronized_claim)
    monkeypatch.setattr(staged, "run_sandboxed", crash_after_reservation)

    def invoke(stage: Path, session: Path) -> None:
        try:
            staged.call_tool(schedule, run_id, stage, session, "first", tool,
                             wall_seconds=3)
        except BaseException as exc:
            results.append(exc)

    threads = [threading.Thread(target=invoke, args=(stage, session)) for stage, session in (
        (stage_a, session_a), (stage_b, session_b)
    )]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)
    assert len(launched) == 1
    assert len(results) == 2
    assert sum(isinstance(item, KeyboardInterrupt) for item in results) == 1
    assert sum(isinstance(item, admission.AdmissionError) for item in results) == 1
    statuses = [staged.resume_session(schedule, run_id, stage, session)["status"]
                for stage, session in ((stage_a, session_a), (stage_b, session_b))]
    assert sorted(statuses) == ["blocked", "indeterminate"]


def test_separate_cli_processes_race_one_claim_without_loser_reservation(
    tmp_path: Path, available_sandbox: None,
) -> None:
    schedule, run_id, stage_a, stage_b, tool = _copies(tmp_path)
    session_a, session_b = tmp_path / "session-a", tmp_path / "session-b"
    staged.create_session(schedule, run_id, stage_a, session_a)
    staged.create_session(schedule, run_id, stage_b, session_b)
    launcher = """
import os
import socket
import sys
sys.path.insert(0, sys.argv[1])
import local_run_admission as admission
import staged_tool_session as staged
barrier = socket.socket(fileno=int(sys.argv[2]))
original = admission.acquire_staged_claim
def wait_then_claim(*args, **kwargs):
    barrier.sendall(b'R')
    if barrier.recv(1) != b'G':
        raise RuntimeError('race barrier was not released')
    return original(*args, **kwargs)
admission.acquire_staged_claim = wait_then_claim
raise SystemExit(staged.main(sys.argv[3:]))
"""
    processes: list[tuple[subprocess.Popen[str], socket.socket, Path]] = []
    try:
        for stage, session in ((stage_a, session_a), (stage_b, session_b)):
            parent_socket, child_socket = socket.socketpair()
            process = subprocess.Popen(
                [sys.executable, "-B", "-c", launcher, str(SCRIPTS),
                 str(child_socket.fileno()), "call", str(tmp_path / "schedule.json"),
                 run_id, str(stage), str(session), "first", str(tool),
                 "--wall-seconds", "3"],
                pass_fds=(child_socket.fileno(),), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
            child_socket.close()
            parent_socket.settimeout(10)
            processes.append((process, parent_socket, session))
        for _process, barrier_socket, _session in processes:
            assert barrier_socket.recv(1) == b"R"
        for _process, barrier_socket, _session in processes:
            barrier_socket.sendall(b"G")
        outcomes = [(process.returncode, stdout, stderr, session)
                    for process, _barrier_socket, session in processes
                    for stdout, stderr in [process.communicate(timeout=30)]]
    finally:
        for process, barrier_socket, _session in processes:
            barrier_socket.close()
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
    assert sorted(result[0] for result in outcomes) == [0, 2]
    winner = next(result for result in outcomes if result[0] == 0)
    loser = next(result for result in outcomes if result[0] == 2)
    assert json.loads(winner[1])["status"] == "success"
    assert "another local owner" in loser[2] or "already has a local admission claim" in loser[2]
    assert not (loser[3] / "calls" / "000001").exists()
    assert list((loser[3] / "calls").iterdir()) == []
    assert (winner[3] / "calls" / "000001" / "reservation.json").is_file()
    statuses = [staged.resume_session(schedule, run_id, stage, session)["status"]
                for stage, session in ((stage_a, session_a), (stage_b, session_b))]
    assert sorted(statuses) == ["blocked", "exhausted"]


def test_cli_admission_root_override_is_bound_to_staged_session(
    tmp_path: Path, available_sandbox: None,
) -> None:
    schedule, run_id, stage, _, tool = _copies(tmp_path)
    session = tmp_path / "session"
    schedule_path = tmp_path / "schedule.json"
    selected_root = tmp_path / "operator-admissions"
    wrong_root = tmp_path / "other-admissions"
    admission.descriptor(wrong_root)
    command = [sys.executable, "-B", str(SCRIPTS / "staged_tool_session.py")]
    init = subprocess.run(
        [*command, "init", str(schedule_path), run_id, str(stage), str(session),
         "--admission-root", str(selected_root)],
        capture_output=True, text=True, check=False, timeout=20,
    )
    assert init.returncode == 0, init.stderr
    assert json.loads(init.stdout)["local_run_admission_root"] == str(selected_root)
    assert json.loads(init.stdout)["local_run_claim_status"] == "unclaimed"
    wrong_status = subprocess.run(
        [*command, "status", str(schedule_path), run_id, str(stage), str(session),
         "--admission-root", str(wrong_root)],
        capture_output=True, text=True, check=False, timeout=20,
    )
    assert wrong_status.returncode == 3, wrong_status.stderr
    assert json.loads(wrong_status.stdout)["status"] == "blocked"
    wrong_call = subprocess.run(
        [*command, "call", str(schedule_path), run_id, str(stage), str(session),
         "first", str(tool), "--wall-seconds", "3", "--admission-root", str(wrong_root)],
        capture_output=True, text=True, check=False, timeout=20,
    )
    assert wrong_call.returncode == 2
    assert "differs from session" in wrong_call.stderr
    assert not (session / "calls" / "000001").exists()
    assert list(wrong_root.iterdir()) == []
    valid_status = subprocess.run(
        [*command, "status", str(schedule_path), run_id, str(stage), str(session),
         "--admission-root", str(selected_root)],
        capture_output=True, text=True, check=False, timeout=20,
    )
    assert valid_status.returncode == 0, valid_status.stderr
    assert json.loads(valid_status.stdout)["status"] == "ready"
    assert schedule["schedule_sha256"] == json.loads(valid_status.stdout)["schedule_sha256"]
    valid_call = subprocess.run(
        [*command, "call", str(schedule_path), run_id, str(stage), str(session),
         "first", str(tool), "--wall-seconds", "3", "--admission-root", str(selected_root)],
        capture_output=True, text=True, check=False, timeout=20,
    )
    assert valid_call.returncode == 0, valid_call.stderr
    assert json.loads(valid_call.stdout)["local_run_admission_root"] == str(selected_root)
    assert _claim_path(selected_root, schedule, run_id).is_file()


def test_cli_admission_root_override_is_recorded_by_oneshot(
    tmp_path: Path, available_sandbox: None,
) -> None:
    _schedule, run_id, stage, _, tool = _copies(tmp_path)
    selected_root = tmp_path / "operator-admissions"
    receipt = tmp_path / "receipt"
    run = subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / "run_staged_local_tool.py"),
         str(tmp_path / "schedule.json"), run_id, str(stage), "first", str(tool),
         str(receipt), "--wall-seconds", "3", "--admission-root", str(selected_root)],
        capture_output=True, text=True, check=False, timeout=20,
    )
    assert run.returncode == 7, run.stderr  # First tool does not create report.md.
    report = json.loads(run.stdout)
    reservation = json.loads((receipt / "reservation.json").read_text())
    assert report["status"] == "deliverables_missing"
    assert report["local_run_admission_root"] == str(selected_root)
    assert reservation["local_run_admission_root_identity"] == report[
        "local_run_admission_root_identity"
    ]
    assert report["reservation_sha256"] == hashlib.sha256(
        (receipt / "reservation.json").read_bytes()
    ).hexdigest()


def test_publication_fsync_failure_never_authorizes_second_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, run_id, stage_a, stage_b, tool = _copies(tmp_path)
    session_a, session_b = tmp_path / "session-a", tmp_path / "session-b"
    staged.create_session(schedule, run_id, stage_a, session_a)
    staged.create_session(schedule, run_id, stage_b, session_b)
    root = tmp_path / "admissions"
    claim = _claim_path(root, schedule, run_id)
    actual_fsync = os.fsync
    fail_durability = True

    def fail_after_claim_rename(fd: int) -> None:
        if (fail_durability and claim.exists()
            and os.readlink(f"/proc/self/fd/{fd}") == str(root)):
            raise OSError(errno.EIO, "injected claim publication fsync failure")
        actual_fsync(fd)

    monkeypatch.setattr(admission.os, "fsync", fail_after_claim_rename)
    with pytest.raises(OSError, match="injected claim publication fsync failure"):
        staged.call_tool(schedule, run_id, stage_a, session_a, "first", tool,
                         wall_seconds=3)
    assert claim.is_file()
    assert not (session_a / "calls" / "000001").exists()
    with pytest.raises(staged.SessionError, match="blocked"):
        staged.call_tool(schedule, run_id, stage_b, session_b, "first", tool,
                         wall_seconds=3)
    assert not (session_b / "calls" / "000001").exists()
    fail_durability = False
    assert staged.resume_session(schedule, run_id, stage_b, session_b)["status"] == "blocked"
    assert staged.resume_session(schedule, run_id, stage_a, session_a)["status"] == "ready"


def test_claim_read_fsync_failure_blocks_launch_and_other_reservation(
    tmp_path: Path, available_sandbox: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, run_id, stage_a, stage_b, tool = _copies(tmp_path, cap=2)
    session_a, session_b = tmp_path / "session-a", tmp_path / "session-b"
    staged.create_session(schedule, run_id, stage_a, session_a)
    staged.create_session(schedule, run_id, stage_b, session_b)
    assert staged.call_tool(schedule, run_id, stage_a, session_a, "first", tool,
                            wall_seconds=3)["status"] == "success"
    root = tmp_path / "admissions"
    actual_fsync = os.fsync

    def fail_claim_read(fd: int) -> None:
        if os.readlink(f"/proc/self/fd/{fd}") == str(root):
            raise OSError(errno.EIO, "injected claim read fsync failure")
        actual_fsync(fd)

    monkeypatch.setattr(admission.os, "fsync", fail_claim_read)
    with pytest.raises(staged.SessionError, match="injected claim read fsync failure"):
        staged.call_tool(schedule, run_id, stage_a, session_a, "second",
                         tmp_path / "second_tool", wall_seconds=3)
    with pytest.raises(staged.SessionError, match="injected claim read fsync failure"):
        staged.call_tool(schedule, run_id, stage_b, session_b, "first", tool,
                         wall_seconds=3)
    assert not (session_a / "calls" / "000002").exists()
    assert not (session_b / "calls" / "000001").exists()
    assert list((stage_b / "work").iterdir()) == []


def test_claim_before_reservation_can_resume_same_staged_owner(
    tmp_path: Path, available_sandbox: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, run_id, stage, _, tool = _copies(tmp_path)
    session = tmp_path / "session"
    staged.create_session(schedule, run_id, stage, session)
    original = staged._write_json

    def crash_after_claim(path: Path, value: dict) -> str:
        if path.name == "reservation.json":
            raise KeyboardInterrupt("crash after claim")
        return original(path, value)

    monkeypatch.setattr(staged, "_write_json", crash_after_claim)
    with pytest.raises(KeyboardInterrupt, match="crash after claim"):
        staged.call_tool(schedule, run_id, stage, session, "first", tool, wall_seconds=3)
    assert not (session / "calls" / "000001").exists()
    assert len(list((session / "calls").glob(".prepared-*"))) == 1
    assert staged.resume_session(schedule, run_id, stage, session)["local_run_claim_status"] == "claimed"
    assert staged.resume_session(schedule, run_id, stage, session)["status"] == "ready"
    monkeypatch.setattr(staged, "_write_json", original)
    assert staged.call_tool(schedule, run_id, stage, session, "first", tool,
                            wall_seconds=3)["status"] == "success"


def test_missing_or_malformed_claim_blocks_prior_local_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, run_id, stage, _, tool = _copies(tmp_path, cap=2)
    session = tmp_path / "session"
    staged.create_session(schedule, run_id, stage, session)
    monkeypatch.setattr(staged, "run_sandboxed", lambda **kwargs: (
        _ for _ in ()
    ).throw(KeyboardInterrupt("simulated crash")))
    with pytest.raises(KeyboardInterrupt):
        staged.call_tool(schedule, run_id, stage, session, "first", tool, wall_seconds=3)
    claim = _claim_path(tmp_path / "admissions", schedule, run_id)
    claim.unlink()
    missing = staged.resume_session(schedule, run_id, stage, session)
    assert missing["status"] == "blocked"
    assert "claim is missing" in missing["blocked_reason"]
    claim.write_text("{malformed", encoding="utf-8")
    claim.chmod(0o600)
    malformed = staged.resume_session(schedule, run_id, stage, session)
    assert malformed["status"] == "blocked"
    assert "malformed" in malformed["blocked_reason"]
    with pytest.raises(staged.SessionError, match="blocked"):
        staged.call_tool(schedule, run_id, stage, session, "first", tool, wall_seconds=3)


@pytest.mark.parametrize("damage", ["missing", "malformed"])
def test_claimed_run_with_bad_reservation_fails_closed(
    tmp_path: Path, available_sandbox: None, damage: str,
) -> None:
    schedule, run_id, stage_a, stage_b, tool = _copies(tmp_path, cap=2)
    session_a, session_b = tmp_path / "session-a", tmp_path / "session-b"
    staged.create_session(schedule, run_id, stage_a, session_a)
    staged.create_session(schedule, run_id, stage_b, session_b)
    assert staged.call_tool(schedule, run_id, stage_a, session_a, "first", tool,
                            wall_seconds=3)["status"] == "success"
    reservation = session_a / "calls" / "000001" / "reservation.json"
    if damage == "missing":
        reservation.unlink()
    else:
        reservation.write_text("{malformed", encoding="utf-8")
    status = staged.resume_session(schedule, run_id, stage_a, session_a)
    assert status["status"] == "indeterminate"
    with pytest.raises(staged.SessionError, match="indeterminate"):
        staged.call_tool(schedule, run_id, stage_a, session_a, "first", tool,
                         wall_seconds=3)
    assert staged.resume_session(schedule, run_id, stage_b, session_b)["status"] == "blocked"
    assert not (session_a / "calls" / "000002").exists()


def test_oneshot_crash_after_claim_before_reservation_blocks_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, run_id, stage_a, stage_b, tool = _copies(tmp_path)
    session = tmp_path / "session"
    staged.create_session(schedule, run_id, stage_a, session)
    receipt = tmp_path / "receipt"
    original = oneshot._write_receipt

    def crash_at_reservation(path: Path, value: dict) -> None:
        if path.name == "reservation.json":
            raise KeyboardInterrupt("crash after one-shot claim")
        original(path, value)

    monkeypatch.setattr(oneshot, "_write_receipt", crash_at_reservation)
    with pytest.raises(KeyboardInterrupt, match="crash after one-shot claim"):
        oneshot.run_staged_local_tool(schedule, run_id, stage_b, "first", tool, receipt)
    assert receipt.is_dir() and not (receipt / "reservation.json").exists()
    assert staged.resume_session(schedule, run_id, stage_a, session)["status"] == "blocked"
    with pytest.raises(admission.AdmissionError, match="already has"):
        oneshot.run_staged_local_tool(schedule, run_id, stage_b, "first", tool,
                                      tmp_path / "second-receipt")
    assert list((stage_b / "work").iterdir()) == []


def test_changed_registry_configuration_cannot_reset_session(
    tmp_path: Path, available_sandbox: None,
) -> None:
    schedule, run_id, stage, _, tool = _copies(tmp_path)
    root_one, root_two = tmp_path / "admissions", tmp_path / "other-admissions"
    session = tmp_path / "session"
    staged.create_session(schedule, run_id, stage, session, admission_root=root_one)
    admission.descriptor(root_two)
    changed = staged.resume_session(schedule, run_id, stage, session, admission_root=root_two)
    assert changed["status"] == "blocked"
    assert "differs from session" in changed["blocked_reason"]
    with pytest.raises(staged.SessionError, match="differs from session"):
        staged.call_tool(schedule, run_id, stage, session, "first", tool,
                         wall_seconds=3, admission_root=root_two)
    assert list(root_two.iterdir()) == []
    restored = staged.resume_session(schedule, run_id, stage, session, admission_root=root_one)
    assert restored["status"] == "ready"
    assert staged.call_tool(schedule, run_id, stage, session, "first", tool,
                            wall_seconds=3, admission_root=root_one)["status"] == "success"
