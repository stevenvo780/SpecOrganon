import json
import os
from decimal import Decimal

import pytest

from specorganon import ledger


def test_strict_json_preserves_common_decimal_values_and_explicit_zero():
    for literal in ("0.1", "1.00", "1e20", "0e-9999", "-0.0", "-0.000E+9999"):
        value = ledger.strict_json_loads(literal)
        assert Decimal(str(value)) == Decimal(literal)


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


@pytest.mark.parametrize("value", (float("nan"), float("inf"), -float("inf")))
def test_append_rejects_nested_nonfinite_payload_without_writing(tmp_path, value):
    project = tmp_path / "project"
    ledger.init_project(project, "Case", "domain", "human")
    path = ledger.project_file(project)
    before = path.read_bytes()

    with pytest.raises(ledger.LedgerError, match="not strict JSON"):
        ledger.append_event(project, "observation", {"nested": {"value": value}}, "agent")
    assert path.read_bytes() == before


def test_read_rejects_nonfinite_literal_before_verifying_event_hash(tmp_path):
    project = tmp_path / "project"
    ledger.init_project(project, "Case", "domain", "human")
    ledger.append_event(project, "observation", {"value": 1}, "agent")
    path = ledger.project_file(project)
    poisoned = json.loads(path.read_text(encoding="utf-8"))
    poisoned["events"][0]["payload"]["value"] = float("nan")
    path.write_text(json.dumps(poisoned), encoding="utf-8")

    with pytest.raises(ledger.LedgerError, match="non-finite JSON number NaN"):
        ledger.read_project(project)


def test_read_rejects_underflow_literal_before_verifying_event_hash(tmp_path):
    project = tmp_path / "project"
    ledger.init_project(project, "Case", "domain", "human")
    path = ledger.project_file(project)
    poisoned = json.loads(path.read_text(encoding="utf-8"))
    poisoned["underflow"] = "UNDERFLOW"
    path.write_text(json.dumps(poisoned).replace('"UNDERFLOW"', "1e-9999"), encoding="utf-8")

    with pytest.raises(ledger.LedgerError, match="JSON number underflows to zero"):
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


def test_read_rejects_fifo_ledger_without_blocking(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    os.mkfifo(ledger.project_file(project))

    with pytest.raises(ledger.LedgerError, match="not a regular file"):
        ledger.read_project(project)


def test_init_rejects_dangling_symlinked_ledger(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    target = ledger.project_file(project)
    target.symlink_to(tmp_path / "absent-external-ledger")

    with pytest.raises(ledger.LedgerError, match="project already exists"):
        ledger.init_project(project, "Case", "domain", "human")
    assert target.is_symlink()
    assert not (tmp_path / "absent-external-ledger").exists()
