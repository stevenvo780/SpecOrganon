"""Real interface parity for a synthetic, read-only declared journal."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

from specorganon.cli import invoke
from specorganon.lot_journal import LotJournalError, audit_lot_journal

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / ".venv/bin/organon"


@pytest.fixture
def journal():
    def load(id, kind):
        return {"load_id": id, "material_id": "water", "kind": kind,
                "mass": {"value": 1, "unit": "kg", "uncertainty": 0},
                "basis": "wet", "dry_fraction": 0}

    return {"schema": 1, "classification": "lot_journal_declared_only", "journal_id": "interface-synthetic",
            "events": [{"id": "capture", "stage": "Synthetic water capture", "stage_role": "transformation",
                        "actor": "agent:synthetic_recorder", "at_utc": "2026-09-30T10:00:00Z",
                        "inputs": [load("input-water", "water_addition")],
                        "outputs": [load("captured-water", "product")], "balance_tolerance_kg": 0,
                        "source": {"source_id": "synthetic-only", "locator": "row/1",
                                   "observed_at_utc": "2026-09-30T10:00:00Z", "method": "invented control",
                                   "record_sha256": "a" * 64}}]}


def _files(directory):
    return {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


def _cli(directory, argument, raw=None):
    return subprocess.run([str(CLI), "audit-lot-journal", argument], input=raw,
                          capture_output=True, timeout=10, cwd=directory,
                          env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
                               "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
                          check=False)


@pytest.mark.parametrize("mode", ["file", "stdin"])
def test_actual_cli_stdout_equals_api_and_creates_no_files(journal, tmp_path, mode):
    path = tmp_path / "journal.json"
    raw = json.dumps(journal).encode()
    path.write_bytes(raw)
    before = _files(tmp_path)
    result = _cli(tmp_path, "-" if mode == "stdin" else str(path), raw if mode == "stdin" else None)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == audit_lot_journal(journal)
    assert _files(tmp_path) == before
    assert not list(tmp_path.rglob("organon.json"))


@pytest.mark.parametrize("mode", ["file", "stdin"])
@pytest.mark.parametrize("raw,error", [
    (b'{"schema":NaN}', "non-finite"), (b'{"schema":Infinity}', "non-finite"),
    (b'{"schema":1,"schema":1}', "duplicate key"),
    (b'{"schema":1.0000000000000000001}', "loses decimal precision"),
])
def test_actual_cli_invalid_json_fails_without_report_or_writes(tmp_path, mode, raw, error):
    path = tmp_path / "journal.json"
    path.write_bytes(raw)
    before = _files(tmp_path)
    result = _cli(tmp_path, "-" if mode == "stdin" else str(path), raw if mode == "stdin" else None)
    assert result.returncode != 0 and result.stdout == b""
    assert error in result.stderr.decode()
    assert _files(tmp_path) == before
    assert not list(tmp_path.rglob("organon.json"))


def test_shared_invoke_requires_no_case_and_preserves_declared_scope(journal, tmp_path, monkeypatch):
    monkeypatch.setenv("ORGANON_ROOT", str(tmp_path))
    before = _files(tmp_path)
    result = invoke("audit_lot_journal", journal=journal)
    assert result == audit_lot_journal(journal)
    assert result["observations_authenticated"] is False
    assert result["field_scope_complete"] is False and result["execution_ready"] is False
    assert _files(tmp_path) == before == {}


def test_shared_invoke_rejects_invalid_journal_without_case_writes(journal, tmp_path):
    journal["events"][0]["outputs"][0]["mass"]["value"] = 2
    with pytest.raises(LotJournalError, match="wet mass balance"):
        invoke("audit_lot_journal", journal=journal)
    assert _files(tmp_path) == {}


def test_direct_mcp_tool_bound_root_needs_no_case_and_preserves_payload(journal, tmp_path, monkeypatch):
    pytest.importorskip("mcp", reason="MCP dependency is available in the project venv")
    from specorganon import server

    monkeypatch.setenv("ORGANON_ROOT", str(tmp_path))
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(tmp_path / "absent-public-registry.json"))
    original = copy.deepcopy(journal)
    assert server.audit_lot_journal(journal) == audit_lot_journal(journal)
    assert journal == original
    assert _files(tmp_path) == {}


def test_direct_mcp_invalid_journal_returns_tool_error_without_files(journal, tmp_path, monkeypatch):
    pytest.importorskip("mcp", reason="MCP dependency is available in the project venv")
    from mcp.server.mcpserver.exceptions import ToolError
    from specorganon import server

    monkeypatch.setenv("ORGANON_ROOT", str(tmp_path))
    journal["events"][0]["outputs"][0]["mass"]["value"] = 2
    with pytest.raises(ToolError, match="wet mass balance"):
        server.audit_lot_journal(journal)
    assert _files(tmp_path) == {}
