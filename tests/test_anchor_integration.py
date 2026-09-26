"""The public engine refuses a locally valid history that diverges from its external head."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from specorganon import approval, engine, ledger


def _write_anchor(path: Path, case: Path, data: dict) -> None:
    project = data["project"]
    events = data["events"]
    entry = {
        "path": approval.case_path(case),
        "project_sha256": approval.project_fingerprint(project),
        "seq": len(events),
        "head_hash": events[-1]["hash"] if events else ledger.ZERO_HASH,
    }
    path.write_text(json.dumps({"schema": 1, "cases": {project["case_id"]: entry}}), encoding="utf-8")


def test_external_anchor_blocks_stale_and_replaced_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORGANON_LEDGER_ANCHORS_FILE", raising=False)
    case = tmp_path / "case"
    engine.create_case(case, "Anchor integration", "fixture", "agent:operator")
    anchor_file = tmp_path / "anchors.json"
    initial = ledger.read_project(case)
    _write_anchor(anchor_file, case, initial)
    monkeypatch.setenv("ORGANON_LEDGER_ANCHORS_FILE", str(anchor_file))
    assert engine.get_state(case)["revision"] == 0

    engine.put_item(case, "p1", "problem", "Synthetic problem", [], {}, "agent:writer")
    with pytest.raises(ledger.LedgerError, match="ledger anchor verification failed: ledger sequence"):
        engine.get_state(case)
    current = ledger.read_project(case, verify_external_anchor=False)
    assert len(current["events"]) == 1
    _write_anchor(anchor_file, case, current)
    assert engine.get_state(case)["revision"] == 1

    target = case / ledger.FILE_NAME
    target.write_text(json.dumps({**current, "events": []}), encoding="utf-8")
    assert ledger.read_project(case, verify_external_anchor=False)["events"] == []
    with pytest.raises(ledger.LedgerError, match="ledger sequence"):
        engine.get_state(case)
    with pytest.raises(ledger.LedgerError, match="ledger sequence"):
        engine.put_item(case, "a1", "actor", "Cannot append to truncated history", ["p1"], {}, "agent:writer")

    forged = json.loads(json.dumps(current))
    event = {
        "seq": 2,
        "at": "2026-09-26T00:00:00+00:00",
        "actor": "agent:forged",
        "kind": "item_put",
        "payload": {"id": "a1", "kind": "actor", "version": 1, "text": "Forged", "deps": {"p1": 1}, "data": {}},
        "prev_hash": current["events"][-1]["hash"],
    }
    event["hash"] = ledger._digest(event)
    forged["events"].append(event)
    target.write_text(json.dumps(forged), encoding="utf-8")
    assert len(ledger.read_project(case, verify_external_anchor=False)["events"]) == 2
    with pytest.raises(ledger.LedgerError, match="ledger sequence"):
        engine.get_state(case)

    forked = json.loads(json.dumps(current))
    forked["events"][0]["payload"]["text"] = "Forged replacement"
    forked["events"][0]["hash"] = ledger._digest({key: value for key, value in forked["events"][0].items() if key != "hash"})
    target.write_text(json.dumps(forked), encoding="utf-8")
    assert len(ledger.read_project(case, verify_external_anchor=False)["events"]) == 1
    with pytest.raises(ledger.LedgerError, match="ledger head differs"):
        engine.get_state(case)


@pytest.mark.parametrize("policy", ["signed", "fixture"])
def test_initialization_with_anchor_fails_without_side_effects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, policy: str) -> None:
    anchor_file = tmp_path / "anchors.json"
    anchor_file.write_text('{"schema":1,"cases":{}}', encoding="utf-8")
    monkeypatch.setenv("ORGANON_LEDGER_ANCHORS_FILE", str(anchor_file))
    case = tmp_path / "not-created"
    with pytest.raises(engine.MethodError, match="initialize a case before enabling"):
        engine.create_case(case, "Case", "domain", "agent:operator", approval_policy=policy)
    assert not case.exists()
    cli_case = tmp_path / "cli-not-created"
    result = subprocess.run(
        [str(Path(sys.executable).parent / "organon"), "init", str(cli_case), "--title", "Case",
         "--domain", "domain", "--actor", "agent:operator", "--approval-policy", policy],
        text=True, capture_output=True, env=os.environ.copy(), check=False,
    )
    assert result.returncode == 1 and "initialize a case before enabling" in result.stderr
    assert not cli_case.exists()


def test_stale_anchor_rejected_by_cli_and_real_mcp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORGANON_LEDGER_ANCHORS_FILE", raising=False)
    case = tmp_path / "case"
    engine.create_case(case, "Transport parity", "fixture", "agent:operator")
    anchor_file = tmp_path / "anchors.json"
    _write_anchor(anchor_file, case, ledger.read_project(case))
    monkeypatch.setenv("ORGANON_LEDGER_ANCHORS_FILE", str(anchor_file))
    engine.put_item(case, "p1", "problem", "Synthetic problem", [], {}, "agent:writer")
    before = ledger.project_file(case).read_bytes()
    bin_dir = Path(sys.executable).parent
    cli = subprocess.run([str(bin_dir / "organon"), "status", str(case)],
                         text=True, capture_output=True, env=os.environ.copy(), check=False)
    assert cli.returncode == 1 and cli.stdout == ""
    assert "ledger anchor verification failed: ledger sequence differs" in cli.stderr

    async def call_mcp() -> None:
        params = StdioServerParameters(command=str(bin_dir / "organon-mcp"), cwd=str(tmp_path), env=os.environ.copy())
        async with Client(params, mode="legacy") as client:
            result = await client.call_tool("status", {"path": str(case)})
            assert result.is_error
            assert "ledger anchor verification failed: ledger sequence differs" in str(result.content)

    asyncio.run(call_mcp())
    assert ledger.project_file(case).read_bytes() == before


def test_joint_rollback_of_ledger_and_anchor_is_external_custody_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORGANON_LEDGER_ANCHORS_FILE", raising=False)
    case = tmp_path / "case"
    engine.create_case(case, "Rollback limit", "fixture", "agent:operator")
    old_ledger = ledger.project_file(case).read_bytes()
    anchor_file = tmp_path / "anchors.json"
    _write_anchor(anchor_file, case, ledger.read_project(case))
    old_anchor = anchor_file.read_bytes()
    monkeypatch.setenv("ORGANON_LEDGER_ANCHORS_FILE", str(anchor_file))
    engine.put_item(case, "p1", "problem", "Synthetic problem", [], {}, "agent:writer")
    _write_anchor(anchor_file, case, ledger.read_project(case, verify_external_anchor=False))
    assert engine.get_state(case)["revision"] == 1

    ledger.project_file(case).write_bytes(old_ledger)
    anchor_file.write_bytes(old_anchor)
    assert engine.get_state(case)["revision"] == 0
