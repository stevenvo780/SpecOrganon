"""Deterministic races for guarded item writes."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from specorganon import approval, engine, ledger


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("ORGANON_LEDGER_ANCHORS_FILE", raising=False)
    path = tmp_path / "case"
    engine.create_case(path, "Concurrent writes", "fixture", "agent:operator")
    return path


def _competing_put(path: Path, item_id: str, version: int, *, expected_seq: int, deps: dict[str, int] | None = None) -> None:
    ledger.append_event(path, "item_put", {
        "id": item_id, "kind": "problem", "version": version, "text": "Competing write",
        "deps": {} if deps is None else deps, "data": {},
    }, "agent:competitor", expected_seq=expected_seq)


def test_guarded_put_retries_unrelated_append_once(case: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine.put_item(case, "p1", "problem", "Reference", [], {}, "agent:seed")
    original = engine.append_event
    attempts: list[int] = []

    def racing_append(path, kind, payload, actor, *, expected_seq):
        attempts.append(expected_seq)
        if len(attempts) == 1:
            _competing_put(path, "q1", 1, expected_seq=expected_seq)
        return original(path, kind, payload, actor, expected_seq=expected_seq)

    monkeypatch.setattr(engine, "append_event", racing_append)
    result = engine.put_item(case, "a1", "actor", "Needs p1", ["p1"], {}, "agent:writer",
                             expected_version=0, expected_deps={"p1": 1})
    events = ledger.read_project(case)["events"]
    assert attempts == [1, 2]
    assert [(event["kind"], event["payload"]["id"]) for event in events] == [
        ("item_put", "p1"), ("item_put", "q1"), ("item_put", "a1"),
    ]
    assert result["seq"] == 3 and result["version"] == 1 and result["deps"] == {"p1": 1}


def test_two_processes_resolve_one_forced_global_conflict_without_caller_retry(case: Path, tmp_path: Path) -> None:
    engine.put_item(case, "p1", "problem", "Shared reference", [], {}, "agent:seed")
    code = """
import json
import sys
import time
from pathlib import Path
from specorganon import engine

case, item_id, own_ready, other_ready = sys.argv[1:]
original = engine.append_event
attempts = []

def synchronized_append(path, kind, payload, actor, *, expected_seq):
    attempts.append(expected_seq)
    if len(attempts) == 1:
        Path(own_ready).write_text("ready", encoding="utf-8")
        deadline = time.monotonic() + 5
        while not Path(other_ready).exists():
            if time.monotonic() > deadline:
                raise TimeoutError("other writer did not reach the first append")
            time.sleep(0.001)
    return original(path, kind, payload, actor, expected_seq=expected_seq)

engine.append_event = synchronized_append
result = engine.put_item(case, item_id, "actor", item_id, ["p1"], {}, f"agent:{item_id}",
                         expected_version=0, expected_deps={"p1": 1})
print(json.dumps({"attempts": attempts, "result": result}))
"""
    markers = [tmp_path / "a.ready", tmp_path / "b.ready"]
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(case), item_id, str(markers[index]), str(markers[1 - index])],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        for index, item_id in enumerate(("a1", "b1"))
    ]
    try:
        outputs = [process.communicate(timeout=10) for process in processes]
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()
    assert all(process.returncode == 0 for process in processes), outputs
    reports = [json.loads(stdout) for stdout, _ in outputs]
    assert sorted(report["attempts"] for report in reports) == [[1], [1, 2]]
    events = ledger.read_project(case)["events"]
    assert len(events) == 3
    assert {event["payload"]["id"] for event in events} == {"p1", "a1", "b1"}
    assert {event["actor"] for event in events[1:]} == {"agent:a1", "agent:b1"}


def test_guarded_revision_keeps_positive_expected_version(case: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine.put_item(case, "p1", "problem", "First revision", [], {}, "agent:seed")
    original = engine.append_event
    attempts: list[int] = []

    def racing_append(path, kind, payload, actor, *, expected_seq):
        attempts.append(expected_seq)
        if len(attempts) == 1:
            _competing_put(path, "q1", 1, expected_seq=expected_seq)
        return original(path, kind, payload, actor, expected_seq=expected_seq)

    monkeypatch.setattr(engine, "append_event", racing_append)
    result = engine.put_item(case, "p1", "problem", "Second revision", [], {}, "agent:writer",
                             expected_version=1)
    assert attempts == [1, 2]
    assert result["version"] == 2 and result["seq"] == 3
    assert [(event["payload"]["id"], event["payload"]["version"]) for event in ledger.read_project(case)["events"]] == [
        ("p1", 1), ("q1", 1), ("p1", 2),
    ]


def test_target_change_refuses_retry(case: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = engine.append_event
    attempts = 0

    def racing_append(path, kind, payload, actor, *, expected_seq):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            _competing_put(path, "p1", 1, expected_seq=expected_seq)
        return original(path, kind, payload, actor, expected_seq=expected_seq)

    monkeypatch.setattr(engine, "append_event", racing_append)
    with pytest.raises(ledger.ConflictError, match="item changed"):
        engine.put_item(case, "p1", "problem", "Original writer", [], {}, "agent:writer", expected_version=0)
    assert attempts == 1
    assert [event["payload"]["text"] for event in ledger.read_project(case)["events"]] == ["Competing write"]


def test_direct_reference_change_refuses_retry(case: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine.put_item(case, "p1", "problem", "Reference", [], {}, "agent:seed")
    original = engine.append_event
    attempts = 0

    def racing_append(path, kind, payload, actor, *, expected_seq):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            _competing_put(path, "p1", 2, expected_seq=expected_seq)
        return original(path, kind, payload, actor, expected_seq=expected_seq)

    monkeypatch.setattr(engine, "append_event", racing_append)
    with pytest.raises(ledger.ConflictError, match="dependency changed"):
        engine.put_item(case, "a1", "actor", "Uses p1", ["p1"], {}, "agent:writer",
                        expected_version=0, expected_deps={"p1": 1})
    assert attempts == 1
    assert [event["payload"]["id"] for event in ledger.read_project(case)["events"]] == ["p1", "p1"]


@pytest.mark.parametrize("expectations", [{}, {"expected_version": 0}, {"expected_deps": {"p1": 1}}])
def test_unguarded_or_partially_guarded_put_stays_fail_fast(
    case: Path, monkeypatch: pytest.MonkeyPatch, expectations: dict,
) -> None:
    engine.put_item(case, "p1", "problem", "Reference", [], {}, "agent:seed")
    original = engine.append_event
    attempts = 0

    def racing_append(path, kind, payload, actor, *, expected_seq):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            _competing_put(path, "q1", 1, expected_seq=expected_seq)
        return original(path, kind, payload, actor, expected_seq=expected_seq)

    monkeypatch.setattr(engine, "append_event", racing_append)
    with pytest.raises(ledger.ConflictError, match="revision conflict"):
        engine.put_item(case, "a1", "actor", "Uses p1", ["p1"], {}, "agent:writer", **expectations)
    assert attempts == 1
    assert [event["payload"]["id"] for event in ledger.read_project(case)["events"]] == ["p1", "q1"]


def test_stale_explicit_expectations_fail_before_append(case: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine.put_item(case, "p1", "problem", "Reference", [], {}, "agent:seed")

    def forbidden_append(*_args, **_kwargs):
        pytest.fail("stale expectation reached append_event")

    monkeypatch.setattr(engine, "append_event", forbidden_append)
    with pytest.raises(ledger.ConflictError, match="item version conflict"):
        engine.put_item(case, "a1", "actor", "Uses p1", ["p1"], {}, "agent:writer",
                        expected_version=1, expected_deps={"p1": 1})
    with pytest.raises(ledger.ConflictError, match="item version conflict"):
        engine.put_item(case, "p1", "problem", "Stale update", [], {}, "agent:writer", expected_version=0)
    with pytest.raises(ledger.ConflictError, match="dependency version conflict"):
        engine.put_item(case, "a1", "actor", "Uses p1", ["p1"], {}, "agent:writer",
                        expected_version=0, expected_deps={"p1": 2})


@pytest.mark.parametrize("expectations", [
    {"expected_version": True}, {"expected_version": -1}, {"expected_version": "0"},
    {"expected_deps": []}, {"expected_deps": {}}, {"expected_deps": {"p1": 0}},
    {"expected_deps": {"p1": True}}, {"expected_deps": {"p1": "1"}},
])
def test_malformed_expectations_are_rejected(case: Path, expectations: dict) -> None:
    engine.put_item(case, "p1", "problem", "Reference", [], {}, "agent:seed")
    with pytest.raises(engine.MethodError):
        engine.put_item(case, "a1", "actor", "Uses p1", ["p1"], {}, "agent:writer", **expectations)
    assert len(ledger.read_project(case)["events"]) == 1


def test_retry_budget_exhausts_without_target_write(case: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = engine.append_event
    attempts = 0

    def racing_append(path, kind, payload, actor, *, expected_seq):
        nonlocal attempts
        attempts += 1
        if attempts > 10:
            pytest.fail("item put retried without a bound")
        _competing_put(path, f"q{attempts}", 1, expected_seq=expected_seq)
        return original(path, kind, payload, actor, expected_seq=expected_seq)

    monkeypatch.setattr(engine, "append_event", racing_append)
    with pytest.raises(ledger.ConflictError, match="revision conflict"):
        engine.put_item(case, "p1", "problem", "Original writer", [], {}, "agent:writer", expected_version=0)
    assert attempts == 4
    assert [event["payload"]["id"] for event in ledger.read_project(case)["events"]] == ["q1", "q2", "q3", "q4"]


def test_changed_case_id_refuses_retry(case: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = engine.append_event
    attempts = 0

    def racing_append(path, kind, payload, actor, *, expected_seq):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            _competing_put(path, "q1", 1, expected_seq=expected_seq)
            ledger_path = ledger.project_file(path)
            raw = json.loads(ledger_path.read_text(encoding="utf-8"))
            raw["project"]["case_id"] = str(uuid.uuid4())
            ledger_path.write_text(json.dumps(raw), encoding="utf-8")
        return original(path, kind, payload, actor, expected_seq=expected_seq)

    monkeypatch.setattr(engine, "append_event", racing_append)
    with pytest.raises(ledger.ConflictError, match="case changed"):
        engine.put_item(case, "p1", "problem", "Original writer", [], {}, "agent:writer", expected_version=0)
    assert attempts == 1
    assert [event["payload"]["id"] for event in ledger.read_project(case)["events"]] == ["q1"]


def test_anchor_custody_error_is_not_retried(case: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = ledger.read_project(case)
    anchor_file = tmp_path / "anchors.json"
    anchor_file.write_text(json.dumps({"schema": 1, "cases": {project["project"]["case_id"]: {
        "path": approval.case_path(case),
        "project_sha256": approval.project_fingerprint(project["project"]),
        "seq": 0,
        "head_hash": ledger.ZERO_HASH,
    }}}), encoding="utf-8")
    monkeypatch.setenv("ORGANON_LEDGER_ANCHORS_FILE", str(anchor_file))
    original = engine.append_event
    attempts = 0

    def racing_append(path, kind, payload, actor, *, expected_seq):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            _competing_put(path, "q1", 1, expected_seq=expected_seq)
        return original(path, kind, payload, actor, expected_seq=expected_seq)

    monkeypatch.setattr(engine, "append_event", racing_append)
    with pytest.raises(ledger.LedgerError, match="ledger anchor verification failed"):
        engine.put_item(case, "p1", "problem", "Original writer", [], {}, "agent:writer", expected_version=0)
    assert attempts == 1
    assert [event["payload"]["id"] for event in ledger.read_project(case, verify_external_anchor=False)["events"]] == ["q1"]
