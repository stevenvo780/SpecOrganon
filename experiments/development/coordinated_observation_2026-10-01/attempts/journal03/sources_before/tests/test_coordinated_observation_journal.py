"""Real local journal/lock tests, without models or D119 runtime execution."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import coordinated_observation_journal as module

ROOT = Path(__file__).resolve().parents[1]


def binding(tmp_path):
    return {"run_dir": str(tmp_path / "run"), "run_id": "fixture-observed-run", "plan_sha256": "1" * 64,
            "schedule_sha256": "2" * 64, "initial_checkpoint_sha256": "3" * 64,
            "observer_source_digests": {"scripts/coordinated_observation_journal.py": "4" * 64}}


def call(role="leader", turn=1):
    return {"role": role, "request_id": f"{role}-turn-{turn:04d}", "request_sha256": "5" * 64,
            "count_payload_sha256": "6" * 64, "send_payload_sha256": "7" * 64}


@pytest.fixture
def journal(tmp_path):
    return module.ObservationJournal.create(tmp_path / "journal", binding(tmp_path))


def begin(journal, calls=None):
    return journal.begin_step(journal.report()["checkpoint_sha256"], calls or [call()])


def count_and_send(journal, token, expected=None):
    expected = expected or call()
    count = journal.begin_operation(token, "count_input", expected["role"], expected["request_id"], expected["count_payload_sha256"])
    assert journal.end_operation(token, count, result_sha256="8" * 64, input_tokens=3)
    send = journal.begin_operation(token, "send", expected["role"], expected["request_id"], expected["send_payload_sha256"])
    assert journal.end_operation(token, send, result_sha256="9" * 64)
    return count, send


def inventory(journal):
    return {str(path.relative_to(journal.directory)): path.read_bytes()
            for path in journal.directory.rglob("*") if path.is_file()}


def reseal(journal, index, mutate):
    paths = sorted((journal.directory / "events").iterdir())
    values = [json.loads(path.read_bytes()) for path in paths]
    mutate(values[index])
    previous = module.ZERO_SHA
    for path, value in zip(paths, values, strict=True):
        value["prev_sha256"] = previous
        raw = module._canonical(value)
        path.write_bytes(raw)
        previous = module._sha(raw)


def test_release_and_finish_are_sanitized(journal):
    released = journal.report()
    assert released["state"] == "released" and released["W_local_elapsed_seconds"] is None
    assert released["clock_info"]["monotonic"] is True
    assert released["clock_info"]["adjustable"] is False
    assert released["events"][0]["type"] == "release"
    assert released["events"][0]["boot_sha256"] == module._boot_digest()
    token = begin(journal)
    count_and_send(journal, token)
    tool = journal.begin_operation(token, "tool", "leader", "leader-turn-0001", "a" * 64)
    assert journal.end_operation(token, tool, result_sha256="b" * 64)
    journal.end_step(token, "c" * 64, "completed")
    ready = journal.report()
    assert ready["state"] == "ready" and ready["current_step_id"] is None
    assert ready["W_local_elapsed_seconds"] is None
    delivered = journal.finish("d" * 64)
    assert delivered["state"] == "delivered" and delivered["W_local_elapsed_seconds"] >= 0
    assert delivered["metrics"]["all"]["completed_intervals"] == 3
    assert not delivered["native_guard_verified"] and not delivered["Q_demonstrated"]
    assert token not in json.dumps(delivered)
    assert token.encode() not in b"".join(inventory(journal).values())
    raw_boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    assert raw_boot not in json.dumps(delivered)
    assert module.ObservationJournal(journal.directory).report() == delivered


def test_union_and_W_include_concurrency_pauses_and_logging(tmp_path, monkeypatch):
    clock = {"monotonic_ns": 0, "wall_ns": 100_000_000_000, "boot_sha256": "e" * 64}
    monkeypatch.setattr(module, "_sample", lambda: dict(clock))
    journal = module.ObservationJournal.create(tmp_path / "journal", binding(tmp_path))
    def at(seconds):
        clock.update(monotonic_ns=seconds * 1_000_000_000, wall_ns=(100 + seconds) * 1_000_000_000)
    first, second = call("worker-1"), call("worker-2")
    at(1)
    token = begin(journal, [first, second])
    at(2)
    c1 = journal.begin_operation(token, "count_input", first["role"], first["request_id"], first["count_payload_sha256"])
    at(3)
    c2 = journal.begin_operation(token, "count_input", second["role"], second["request_id"], second["count_payload_sha256"])
    at(5)
    journal.end_operation(token, c1, result_sha256="8" * 64, input_tokens=3)
    at(7)
    journal.end_operation(token, c2, result_sha256="8" * 64, input_tokens=3)
    at(8)
    s1 = journal.begin_operation(token, "send", first["role"], first["request_id"], first["send_payload_sha256"])
    at(9)
    s2 = journal.begin_operation(token, "send", second["role"], second["request_id"], second["send_payload_sha256"])
    at(11)
    journal.end_operation(token, s1, result_sha256="9" * 64)
    at(13)
    journal.end_operation(token, s2, result_sha256="9" * 64)
    at(14)
    tool = journal.begin_operation(token, "tool", first["role"], first["request_id"], "a" * 64)
    at(15)
    journal.end_operation(token, tool, result_sha256="b" * 64)
    at(16)
    journal.end_step(token, "a" * 64, "paused")
    at(20)
    token = begin(journal)
    at(21)
    count = journal.begin_operation(token, "count_input", "leader", "leader-turn-0001", "6" * 64)
    at(22)
    journal.end_operation(token, count, result_sha256="8" * 64, input_tokens=3)
    at(23)
    send = journal.begin_operation(token, "send", "leader", "leader-turn-0001", "7" * 64)
    at(24)
    journal.end_operation(token, send, result_sha256="9" * 64)
    at(25)
    journal.end_step(token, "b" * 64, "completed")
    at(30)
    clock["wall_ns"] = 99_000_000_000  # wall adjustment is separate from monotonic elapsed
    report = journal.finish("c" * 64)
    assert report["W_local_elapsed_seconds"] == 30
    assert report["wall_delta_seconds"] == -1
    assert report["metrics"]["by_kind"]["count_input"]["sum_seconds"] == 8
    assert report["metrics"]["by_kind"]["count_input"]["union_seconds"] == 6
    assert report["metrics"]["by_kind"]["send"]["sum_seconds"] == 8
    assert report["metrics"]["by_kind"]["send"]["union_seconds"] == 6
    assert report["metrics"]["all"]["sum_seconds"] == 17
    assert report["metrics"]["all"]["union_seconds"] == 13
    assert report["metrics"]["outside_operation_union_seconds"] == 17


@pytest.mark.parametrize("mutation", ["missing", "extra", "bool_digest", "bad_path", "empty_sources", "source_path", "surrogate_path"])
def test_closed_binding_validated_before_create(tmp_path, mutation):
    value = binding(tmp_path)
    if mutation == "missing":
        value.pop("run_id")
    elif mutation == "extra":
        value["authorization"] = True
    elif mutation == "bool_digest":
        value["plan_sha256"] = True
    elif mutation == "bad_path":
        value["run_dir"] = "relative/run"
    elif mutation == "empty_sources":
        value["observer_source_digests"] = {}
    elif mutation == "surrogate_path":
        value["run_dir"] = "/private/\ud800"
    else:
        value["observer_source_digests"] = {"../secret": "4" * 64}
    with pytest.raises(module.ObservationError):
        module.ObservationJournal.create(tmp_path / "journal", value)
    assert not (tmp_path / "journal").exists()


@pytest.mark.parametrize("mutation", ["fields", "bool_sha", "bad_role", "bad_id", "first_turn", "duplicate", "empty"])
def test_expected_calls_are_closed_and_bound(journal, mutation):
    values = [call()]
    if mutation == "fields":
        values[0]["prompt"] = "PRIVATE-SENTINEL"
    elif mutation == "bool_sha":
        values[0]["request_sha256"] = True
    elif mutation == "bad_role":
        values[0]["role"] = "unknown"
    elif mutation == "bad_id":
        values[0]["request_id"] = "worker-1-turn-0001"
    elif mutation == "first_turn":
        values = [call(turn=2)]
    elif mutation == "duplicate":
        values += [call()]
    else:
        values = []
    before = inventory(journal)
    with pytest.raises(module.ObservationError):
        journal.begin_step("3" * 64, values)
    assert inventory(journal) == before


def test_ordering_duplicate_and_checkpoint_checks(journal):
    with pytest.raises(module.ObservationError):
        journal.begin_step("0" * 64, [call()])
    token = begin(journal)
    with pytest.raises(module.ObservationError):
        journal.begin_operation(token, "send", "leader", "leader-turn-0001", "7" * 64)
    count = journal.begin_operation(token, "count_input", "leader", "leader-turn-0001", "6" * 64)
    for kind in ("count_input", "send", "tool"):
        with pytest.raises(module.ObservationError):
            journal.begin_operation(token, kind, "leader", "leader-turn-0001", "6" * 64)
    with pytest.raises(module.ObservationError):
        journal.end_step(token, "a" * 64, "paused")
    journal.end_operation(token, count, result_sha256="8" * 64, input_tokens=3)
    with pytest.raises(module.ObservationError):
        journal.end_operation(token, count, result_sha256="8" * 64, input_tokens=3)
    with pytest.raises(module.ObservationError):
        journal.begin_operation(token, "tool", "leader", "leader-turn-0001", "a" * 64)
    send = journal.begin_operation(token, "send", "leader", "leader-turn-0001", "7" * 64)
    journal.end_operation(token, send, result_sha256="9" * 64)
    journal.end_step(token, "a" * 64, "paused")
    token = begin(journal, [call(turn=2)])
    count_and_send(journal, token, call(turn=2))
    journal.end_step(token, "b" * 64, "completed")
    with pytest.raises(module.ObservationError):
        begin(journal, [call(turn=3)])


@pytest.mark.parametrize("tokens", [None, 0, -1, True, 3.0])
def test_count_requires_positive_exact_integer(journal, tokens):
    token = begin(journal)
    op = journal.begin_operation(token, "count_input", "leader", "leader-turn-0001", "6" * 64)
    before = inventory(journal)
    with pytest.raises(module.ObservationError):
        journal.end_operation(token, op, result_sha256="8" * 64, input_tokens=tokens)
    assert inventory(journal) == before


@pytest.mark.parametrize("error", ["PRIVATE-EXCEPTION-SENTINEL", "", True, {"message": "PRIVATE"}])
def test_error_messages_never_accepted(journal, error):
    token = begin(journal)
    op = journal.begin_operation(token, "count_input", "leader", "leader-turn-0001", "6" * 64)
    before = inventory(journal)
    with pytest.raises(module.ObservationError):
        journal.end_operation(token, op, result_sha256=None, error=error)
    assert inventory(journal) == before


@pytest.mark.parametrize("mutation", ["missing_result", "bool_result", "tokens_on_error", "tokens_on_send", "unknown_op"])
def test_end_operation_fields_are_complete_and_closed(journal, mutation):
    token = begin(journal)
    op = journal.begin_operation(token, "count_input", "leader", "leader-turn-0001", "6" * 64)
    values = {"result_sha256": "8" * 64, "input_tokens": 3}
    if mutation == "missing_result":
        values["result_sha256"] = None
    elif mutation == "bool_result":
        values["result_sha256"] = True
    elif mutation == "tokens_on_error":
        values.update(result_sha256=None, error="transport_error")
    elif mutation == "tokens_on_send":
        journal.end_operation(token, op, **values)
        op = journal.begin_operation(token, "send", "leader", "leader-turn-0001", "7" * 64)
    else:
        op = "op-9999"
    before = inventory(journal)
    with pytest.raises(module.ObservationError):
        journal.end_operation(token, op, **values)
    assert inventory(journal) == before


def test_failure_preserves_missing_end_and_late_callback_is_read_only(journal):
    token = begin(journal)
    op = journal.begin_operation(token, "count_input", "leader", "leader-turn-0001", "6" * 64)
    assert journal.fail_step(token)
    before = inventory(journal)
    assert journal.end_operation(token, op, result_sha256=None, error="PRIVATE-SENTINEL") is False
    assert journal.fail_step(token) is False
    assert inventory(journal) == before
    report = journal.report()
    assert report["state"] == "uncertain" and report["metrics"]["incomplete_operations"] == 1
    assert report["W_local_elapsed_seconds"] is None
    with pytest.raises(module.ObservationError):
        begin(journal)
    with pytest.raises(module.ObservationError):
        journal.finish("a" * 64)


def test_failed_operation_cannot_enable_send_or_delivery(journal):
    token = begin(journal)
    op = journal.begin_operation(token, "count_input", "leader", "leader-turn-0001", "6" * 64)
    assert journal.end_operation(token, op, result_sha256=None, error="transport_error")
    with pytest.raises(module.ObservationError):
        journal.begin_operation(token, "send", "leader", "leader-turn-0001", "7" * 64)
    with pytest.raises(module.ObservationError):
        journal.end_step(token, "a" * 64, "completed")
    journal.fail_step(token)
    assert journal.report()["metrics"]["failed_operations"] == 1


def test_reopen_active_never_restores_capability(journal):
    token = begin(journal)
    op = journal.begin_operation(token, "count_input", "leader", "leader-turn-0001", "6" * 64)
    reopened = module.ObservationJournal(journal.directory)
    before = inventory(journal)
    assert reopened.report()["state"] == "active"
    with pytest.raises(module.ObservationError):
        begin(reopened)
    assert reopened.end_operation(token, op, result_sha256="8" * 64, input_tokens=3) is False
    assert reopened.fail_step(token) is False
    assert inventory(journal) == before


@pytest.mark.parametrize("mutation", ["hash", "seq_bool", "mono_bool", "wall_float", "mono_regression", "boot", "clock_missing", "clock_resolution", "clock_overflow", "clock_surrogate", "data_extra"])
def test_resealed_corruption_is_rejected(journal, mutation):
    begin(journal)
    if mutation == "hash":
        path = journal.directory / "events/000002.json"
        value = json.loads(path.read_bytes())
        value["prev_sha256"] = "f" * 64
        path.write_bytes(module._canonical(value))
    elif mutation in ("clock_missing", "clock_resolution", "clock_overflow", "clock_surrogate"):
        def mutate(event):
            if mutation == "clock_missing":
                event["data"]["clock_info"].pop("implementation")
            elif mutation == "clock_resolution":
                event["data"]["clock_info"]["resolution_seconds"] = True
            elif mutation == "clock_overflow":
                event["data"]["clock_info"]["resolution_seconds"] = 10**400
            else:
                event["data"]["clock_info"]["implementation"] = "\ud800"
        reseal(journal, 0, mutate)
    else:
        def mutate(event):
            if mutation == "seq_bool":
                event["seq"] = True
            elif mutation == "mono_bool":
                event["monotonic_ns"] = True
            elif mutation == "wall_float":
                event["wall_ns"] = float(event["wall_ns"])
            elif mutation == "mono_regression":
                event["monotonic_ns"] = 0
            elif mutation == "boot":
                event["boot_sha256"] = "f" * 64
            else:
                event["data"]["private_payload"] = "PRIVATE-SENTINEL"
        reseal(journal, 1, mutate)
    with pytest.raises(module.ObservationError):
        journal.report()


@pytest.mark.parametrize("mutation", ["duplicate_key", "nonfinite", "missing", "extra", "symlink", "permissions", "hardlink"])
def test_artifact_integrity(journal, mutation, tmp_path):
    path = journal.directory / "events/000001.json"
    if mutation == "duplicate_key":
        path.write_bytes(path.read_bytes().replace(b'"seq":1', b'"seq":1,"seq":1'))
    elif mutation == "nonfinite":
        path.write_bytes(path.read_bytes().replace(b'"monotonic_ns":', b'"monotonic_ns":NaN,"ignored":'))
    elif mutation == "missing":
        path.unlink()
    elif mutation == "extra":
        (journal.directory / "events/extra.json").write_text('{}')
    elif mutation == "symlink":
        copy = tmp_path / "copy.json"
        copy.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(copy)
    elif mutation == "permissions":
        path.chmod(0o644)
    else:
        import os
        os.link(path, tmp_path / "copy.json")
    with pytest.raises(module.ObservationError):
        journal.report()


@pytest.mark.parametrize("mutation", ["boot", "regression", "missing_boot"])
def test_current_clock_rejected_before_append(journal, monkeypatch, mutation):
    before = inventory(journal)
    original = module._sample()
    if mutation == "boot":
        original["boot_sha256"] = "f" * 64
    elif mutation == "regression":
        original["monotonic_ns"] = 0
    else:
        monkeypatch.setattr(module, "_boot_digest", lambda: (_ for _ in ()).throw(module.ObservationError("boot identity is unavailable")))
    if mutation != "missing_boot":
        monkeypatch.setattr(module, "_sample", lambda: original)
    with pytest.raises(module.ObservationError):
        begin(journal)
    assert inventory(journal) == before


def test_parallel_duplicate_begin_is_serialized(journal):
    token = begin(journal)
    barrier, results = threading.Barrier(2), []
    def invoke():
        barrier.wait(timeout=5)
        try:
            results.append(journal.begin_operation(token, "count_input", "leader", "leader-turn-0001", "6" * 64))
        except module.ObservationError:
            results.append("rejected")
    threads = [threading.Thread(target=invoke) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert sorted(results) == ["op-0001", "rejected"]
    assert [event["seq"] for event in journal.report()["events"]] == [1, 2, 3]


def test_count_and_send_callbacks_for_two_requests_can_run_concurrently(journal):
    expected = [call("worker-1"), call("worker-2")]
    token = begin(journal, expected)
    barrier, errors = threading.Barrier(2), []
    def invoke(item):
        try:
            op = journal.begin_operation(token, "count_input", item["role"], item["request_id"], item["count_payload_sha256"])
            barrier.wait(timeout=5)
            journal.end_operation(token, op, result_sha256="8" * 64, input_tokens=3)
            send = journal.begin_operation(token, "send", item["role"], item["request_id"], item["send_payload_sha256"])
            journal.end_operation(token, send, result_sha256="9" * 64)
        except Exception as exc:
            errors.append(type(exc).__name__)
    threads = [threading.Thread(target=invoke, args=(item,)) for item in expected]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert errors == []
    journal.end_step(token, "a" * 64, "completed")
    assert journal.finish("b" * 64)["metrics"]["all"]["completed_intervals"] == 4


def test_process_crash_leaves_active_observation_without_resumption(journal):
    program = '''import json,os,sys
sys.path.insert(0,sys.argv[1])
from coordinated_observation_journal import ObservationJournal
j=ObservationJournal(__import__('pathlib').Path(sys.argv[2]))
token=j.begin_step("3"*64,json.loads(sys.argv[3]))
j.begin_operation(token,"count_input","leader","leader-turn-0001","6"*64)
os._exit(0)
'''
    process = subprocess.run([sys.executable, "-B", "-c", program, str(ROOT / "scripts"), str(journal.directory), json.dumps([call()])],
                             capture_output=True, timeout=10)
    assert process.returncode == 0 and process.stdout == b""
    reopened = module.ObservationJournal(journal.directory)
    before = inventory(journal)
    assert reopened.report()["state"] == "active"
    assert reopened.report()["metrics"]["incomplete_operations"] == 1
    with pytest.raises(module.ObservationError):
        begin(reopened)
    with pytest.raises(module.ObservationError):
        reopened.finish("a" * 64)
    assert inventory(journal) == before


def test_late_thread_callback_after_fail_cannot_write(journal):
    token = begin(journal)
    op = journal.begin_operation(token, "count_input", "leader", "leader-turn-0001", "6" * 64)
    gate, results = threading.Event(), []
    def callback():
        assert gate.wait(timeout=5)
        results.append(journal.end_operation(token, op, result_sha256="8" * 64, input_tokens=3))
    thread = threading.Thread(target=callback)
    thread.start()
    journal.fail_step(token)
    before = inventory(journal)
    gate.set()
    thread.join(timeout=10)
    assert not thread.is_alive() and results == [False]
    assert inventory(journal) == before


def test_driver_lock_is_nonblocking_across_processes_and_callbacks_use_other_lock(journal):
    program = '''import sys
sys.path.insert(0,sys.argv[1])
from coordinated_observation_journal import ObservationJournal,ObservationError
j=ObservationJournal(__import__('pathlib').Path(sys.argv[2]))
try:
    with j.driver_lock():
        print("unexpected acquisition")
except ObservationError:
    print("driver blocked")
    raise SystemExit(42)
'''
    token = begin(journal)
    with journal.driver_lock():
        started = time.monotonic()
        process = subprocess.run([sys.executable, "-B", "-c", program, str(ROOT / "scripts"), str(journal.directory)],
                                 capture_output=True, timeout=10)
        assert process.returncode == 42 and process.stdout == b"driver blocked\n"
        assert time.monotonic() - started < 10
        count_and_send(journal, token)  # does not try to obtain the held driver lock
        assert journal.report()["state"] == "active"
    journal.end_step(token, "a" * 64, "completed")
    journal.finish("b" * 64)


def test_finish_requires_terminal_complete_step_and_revokes_callbacks(journal):
    with pytest.raises(module.ObservationError):
        journal.finish("a" * 64)
    token = begin(journal)
    count_and_send(journal, token)
    op = journal.begin_operation(token, "tool", "leader", "leader-turn-0001", "a" * 64)
    with pytest.raises(module.ObservationError):
        journal.end_step(token, "a" * 64, "completed")
    journal.end_operation(token, op, result_sha256="b" * 64)
    journal.end_step(token, "a" * 64, "completed")
    report = journal.finish("b" * 64)
    before = inventory(journal)
    assert not journal.end_operation(token, op, result_sha256="b" * 64)
    with pytest.raises(module.ObservationError):
        journal.finish("b" * 64)
    assert inventory(journal) == before
    assert report["events"][-1]["type"] == "delivery"


def test_resealed_post_delivery_event_rejected(journal):
    token = begin(journal)
    count_and_send(journal, token)
    journal.end_step(token, "a" * 64, "completed")
    report = journal.finish("b" * 64)
    extra = {"schema": 1, "seq": len(report["events"]) + 1, "type": "step_begin", **module._sample(),
             "prev_sha256": report["last_event_sha256"],
             "data": {"step_id": "step-0002", "expected_checkpoint": "a" * 64, "expected_calls": [call(turn=2)]}}
    path = journal.directory / "events" / f"{extra['seq']:06d}.json"
    path.write_bytes(module._canonical(extra))
    path.chmod(0o600)
    with pytest.raises(module.ObservationError, match="post-delivery"):
        journal.report()


def test_missing_journal_and_parent_symlink_do_not_create(tmp_path):
    with pytest.raises(module.ObservationError):
        module.ObservationJournal(tmp_path / "missing")
    assert not (tmp_path / "missing").exists()
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(module.ObservationError):
        module.ObservationJournal.create(link / "journal", binding(tmp_path))
    assert not (real / "journal").exists()


def test_create_filesystem_rejection_is_fixed_and_preserves_existing(journal, tmp_path):
    before = inventory(journal)
    with pytest.raises(module.ObservationError, match="^observation creation could not be completed$"):
        module.ObservationJournal.create(journal.directory, binding(tmp_path))
    assert inventory(journal) == before
    missing = tmp_path / "PRIVATE-PATH-SENTINEL" / "journal"
    with pytest.raises(module.ObservationError) as caught:
        module.ObservationJournal.create(missing, binding(tmp_path))
    assert "PRIVATE-" not in str(caught.value) and not missing.parent.exists()


def test_file_bytes_match_chain_report(journal):
    previous = module.ZERO_SHA
    for event, path in zip(journal.report()["events"], sorted((journal.directory / "events").iterdir()), strict=True):
        assert event["prev_sha256"] == previous
        assert path.read_bytes() == module._canonical(event)
        previous = hashlib.sha256(path.read_bytes()).hexdigest()
    assert journal.report()["last_event_sha256"] == previous
