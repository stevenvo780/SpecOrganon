"""Integration checks for the March seed's resumable CLI/MCP workflow."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_citibike_march_workflow as probe  # noqa: E402


SCRIPT = ROOT / "scripts/verify_citibike_march_workflow.py"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_installed_cli_mcp_resume_and_replay_leave_real_ledgers_intact(tmp_path: Path) -> None:
    before = {path: path.read_bytes() for path in probe.REAL_LEDGERS}
    receipt_path = tmp_path / "receipt.json"
    process = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(receipt_path)],
        cwd=ROOT, text=True, capture_output=True, check=True, timeout=90,
    )
    receipt = json.loads(process.stdout)
    assert receipt == json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["sha256"]["seed"] == _digest(probe.SEED)
    assert receipt["sha256"]["published_result"] == _digest(probe.PUBLISHED_RESULT)
    assert receipt["sha256"]["analysis_script"] == _digest(probe.ANALYSIS_SCRIPT)
    assert receipt["sha256"]["manifest"] == (
        "27bc567d7435b5a0accbe9e3653f817323e7925c160f7a88d223f40dc6f04244"
    )
    assert receipt["steps"] == {"put": 22, "advance": 1, "total": 23}

    assert receipt["first"] == {
        "status": "waiting", "cursor": 22, "applied": 22, "skipped": 0,
        "reason": "independent_review_required",
    }
    assert receipt["review"] == {
        "seq": 23, "actor": probe.REVIEWER, "independent": True,
        "signature_verified": True,
        "scope": "synthetic_reviewer_identity_and_actor_separation_only",
    }
    assert {"run", "status", "trace", "gate"} <= set(receipt["mcp"]["discovered_tools"])
    assert receipt["mcp"]["resume"] == {
        "status": "waiting", "cursor": 23, "applied": 1, "skipped": 22,
        "reason": "human_approval_required",
    }
    assert receipt["mcp"]["status_equal_to_cli"] is True
    assert receipt["retry"] == {
        "status": "waiting", "cursor": 23, "applied": 0, "skipped": 23,
        "reason": "human_approval_required",
    }
    assert receipt["final"]["event_kinds"] == {
        "item_put": 22, "phase_advance": 1, "phase_review": 1,
    }
    assert receipt["final"]["revision"] == 24
    assert receipt["final"]["frame_accepted"] is True
    assert receipt["final"]["critique"] == {
        "ready": False,
        "accepted": False,
        "blockers": ["n_scope requires a verified human approval"],
    }
    assert receipt["final"]["norm_approved"] is False
    for item_id in probe.EVIDENCE_IDS:
        assert {"p_access", "pr_reanalysis"} <= set(
            receipt["final"]["evidence_ancestors"][item_id]
        )
    assert receipt["criterion_5"] == "not_assessed"
    assert receipt["real_ledgers_unchanged"] is True
    assert {path: path.read_bytes() for path in before} == before


def test_manifest_pins_seed_dependencies_and_rejects_changed_result() -> None:
    seed = json.loads(probe.SEED.read_text(encoding="utf-8"))
    manifest = probe.build_manifest(seed)
    assert [step["id"] for step in manifest["steps"][:-1]] == [
        item["id"] for item in seed["items"]
    ]
    assert all(step["expected_version"] == 0 for step in manifest["steps"][:-1])
    assert all(
        step["expected_deps"] == {ref: 1 for ref in step["refs"]}
        for step in manifest["steps"][:-1]
    )
    assert manifest["steps"][-1] == {"op": "advance", "phase": "frame"}

    published = json.loads(probe.PUBLISHED_RESULT.read_text(encoding="utf-8"))
    changed = deepcopy(seed)
    next(item for item in changed["items"] if item["id"] == "e_rental")["data"]["value"] += 1
    with pytest.raises(AssertionError, match="published numeric locator differs"):
        probe._source_checks(changed, published)
