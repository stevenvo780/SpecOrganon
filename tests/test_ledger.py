import json

import pytest

from specorganon import ledger


def test_rejects_stale_writer_and_preserves_recoverable_state(tmp_path):
    project = tmp_path / "project"
    ledger.init_project(project, "Case", "domain", "human")
    first = ledger.append_event(project, "note", {"value": 1}, "agent-a", expected_seq=0)
    with pytest.raises(ledger.ConflictError):
        ledger.append_event(project, "note", {"value": 2}, "agent-b", expected_seq=0)
    assert [event["hash"] for event in ledger.read_project(project)["events"]] == [first["hash"]]


def test_detects_changed_event_payload(tmp_path):
    project = tmp_path / "project"
    ledger.init_project(project, "Case", "domain", "human")
    ledger.append_event(project, "observation", {"value": "measured"}, "agent")
    path = ledger.project_file(project)
    raw = json.loads(path.read_text())
    raw["events"][0]["payload"]["value"] = "invented"
    path.write_text(json.dumps(raw))
    with pytest.raises(ledger.LedgerError, match="digest mismatch"):
        ledger.read_project(project)


def test_failed_atomic_replace_keeps_previous_revision(tmp_path, monkeypatch):
    project = tmp_path / "project"
    ledger.init_project(project, "Case", "domain", "human")

    def fail_replace(*_args):
        raise OSError("simulated interruption before replace")

    monkeypatch.setattr(ledger.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated interruption"):
        ledger.append_event(project, "note", {"value": 1}, "agent", expected_seq=0)
    assert ledger.read_project(project)["events"] == []
