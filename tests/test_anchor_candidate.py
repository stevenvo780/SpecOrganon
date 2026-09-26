"""The operator aid proposes a head without changing anchor custody."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from specorganon import approval, ledger


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ledger_anchor_candidate.py"


def run_candidate(case: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(ROOT / "src"), env.get("PYTHONPATH"))))
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(case)],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_empty_case_candidate_has_exact_anchor_entry_and_canonical_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORGANON_LEDGER_ANCHORS_FILE", raising=False)
    case = tmp_path / "case"
    project = ledger.init_project(case, "Case", "domain", "human")
    alias = tmp_path / "case-alias"
    alias.symlink_to(case, target_is_directory=True)
    before = ledger.project_file(case).read_bytes()

    result = run_candidate(alias)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    output = json.loads(result.stdout)
    assert output == {
        "schema": 1,
        "case_id": project["project"]["case_id"],
        "entry": {
            "path": str(case.resolve()),
            "project_sha256": approval.project_fingerprint(project["project"]),
            "seq": 0,
            "head_hash": ledger.ZERO_HASH,
        },
        "notice": "Candidate for independent custody and review; no anchor written and no evidence approved.",
    }
    assert ledger.project_file(case).read_bytes() == before
    assert set(case.iterdir()) == {ledger.project_file(case), case / ".organon.lock"}


def test_candidate_reports_legitimate_append_with_stale_external_anchor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case = tmp_path / "case"
    project = ledger.init_project(case, "Case", "domain", "human")
    case_id = project["project"]["case_id"]
    old_entry = {
        "path": approval.case_path(case),
        "project_sha256": approval.project_fingerprint(project["project"]),
        "seq": 0,
        "head_hash": ledger.ZERO_HASH,
    }
    anchor_file = tmp_path / "anchors.json"
    anchor_file.write_text(json.dumps({"schema": 1, "cases": {case_id: old_entry}}), encoding="utf-8")
    anchor_before = anchor_file.read_bytes()
    monkeypatch.setenv("ORGANON_LEDGER_ANCHORS_FILE", str(anchor_file))

    appended = ledger.append_event(case, "note", {"value": "legitimate"}, "agent", expected_seq=0)
    case_before = ledger.project_file(case).read_bytes()
    with pytest.raises(ledger.LedgerError, match="ledger anchor verification failed: ledger sequence differs"):
        ledger.read_project(case)

    result = run_candidate(case)

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["case_id"] == case_id
    assert output["entry"] == {**old_entry, "seq": 1, "head_hash": appended["hash"]}
    assert anchor_file.read_bytes() == anchor_before
    assert ledger.project_file(case).read_bytes() == case_before
    with pytest.raises(ledger.LedgerError, match="ledger anchor verification failed"):
        ledger.read_project(case)


def test_candidate_rejects_broken_internal_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORGANON_LEDGER_ANCHORS_FILE", raising=False)
    case = tmp_path / "case"
    ledger.init_project(case, "Case", "domain", "human")
    ledger.append_event(case, "note", {"value": "original"}, "agent")
    path = ledger.project_file(case)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["events"][0]["payload"]["value"] = "tampered"
    path.write_text(json.dumps(raw), encoding="utf-8")
    before = path.read_bytes()

    result = run_candidate(case)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "event digest mismatch" in result.stderr
    assert path.read_bytes() == before


@pytest.mark.parametrize("case_id", [None, "not-a-uuid", "00000000-0000-0000-0000-00000000000A"])
def test_candidate_requires_canonical_case_uuid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case_id: str | None) -> None:
    monkeypatch.delenv("ORGANON_LEDGER_ANCHORS_FILE", raising=False)
    case = tmp_path / "case"
    ledger.init_project(case, "Case", "domain", "human")
    path = ledger.project_file(case)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if case_id is None:
        raw["project"].pop("case_id")
    else:
        raw["project"]["case_id"] = case_id
    path.write_text(json.dumps(raw), encoding="utf-8")

    result = run_candidate(case)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "case_id" in result.stderr
