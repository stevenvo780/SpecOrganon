"""Historical March ledger lineage regression with real CLI and stdio MCP."""

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
import probe_citibike_march_indicator_lineage as probe  # noqa: E402


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def test_false_unfiltered_denominator_is_rejected() -> None:
    published = json.loads(probe.PUBLISHED_RESULT.read_bytes())
    assert probe.check_eligible_denominator(1_809_036, published) == 1_809_036
    with pytest.raises(ValueError, match="candidate denominator 1812548 differs"):
        probe.check_eligible_denominator(1_812_548, published)
    with pytest.raises(ValueError, match="row counts must be integers"):
        probe.check_eligible_denominator(True, published)
    inconsistent = deepcopy(published)
    inconsistent["snapshot_row_service"]["denominator"] = 1_812_548
    with pytest.raises(ValueError, match="exclusion cross-check"):
        probe.check_eligible_denominator(1_809_036, inconsistent)


def test_real_cli_mcp_invalidation_and_append_only_derived_case(tmp_path: Path) -> None:
    protected = (
        probe.SOURCE_LEDGER,
        probe.JUNE_LEDGER,
        probe.SEED,
        probe.PUBLISHED_RESULT,
        probe.ANALYSIS_SCRIPT,
    )
    before = {path: path.read_bytes() for path in protected}
    original = json.loads(before[probe.SOURCE_LEDGER])
    receipt_path = tmp_path / "receipt.json"
    derivative = tmp_path / "derivative"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/probe_citibike_march_indicator_lineage.py"),
            "--output",
            str(receipt_path),
            "--derived-case",
            str(derivative),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
        timeout=90,
    )
    receipt = json.loads(completed.stdout)
    assert receipt == json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["sha256"]["source_ledger"] == _digest(before[probe.SOURCE_LEDGER])
    assert receipt["sha256"]["seed"] == _digest(before[probe.SEED])
    assert receipt["numeric_source_check"] == {
        "raw_rows": 1_812_548,
        "excluded_rows": 3_512,
        "eligible_denominator": 1_809_036,
        "false_raw_row_denominator_rejected": True,
    }

    control = receipt["control"]
    assert control["items"]["i_rows"]["version"] == 1
    assert control["items"]["i_rows"]["stale"] is False
    assert control["items"]["e_rental"]["stale"] is True
    assert control["items"]["e_return"]["stale"] is True
    assert "i_rows depends on an older revision" not in control["study_blockers"]

    linked = receipt["linked"]
    assert linked["transport"] == {
        "indicator_revision": "real_stdio_mcp",
        "other_writes": "installed_cli",
    }
    assert {"put", "status", "trace", "gate"} <= set(linked["mcp_discovered"])
    pre = linked["before_source_revision"]
    invalid = linked["invalidated"]
    repaired = linked["repaired"]
    assert pre["items"]["i_rows"]["version"] == 2
    assert set(probe.EVIDENCE_IDS) <= set(pre["items"]["i_rows"]["deps"])
    assert pre["items"]["req_row_report"]["stale"] is False
    assert invalid["items"]["i_rows"]["stale"] is True
    assert invalid["items"]["req_row_report"]["stale"] is True
    assert "i_rows depends on an older revision" in invalid["study_blockers"]
    assert "req_row_report depends on an older revision" in invalid["specify_blockers"]
    assert repaired["items"]["i_rows"]["version"] == 3
    assert repaired["items"]["req_row_report"]["version"] == 2
    assert repaired["items"]["i_rows"]["stale"] is False
    assert repaired["items"]["req_row_report"]["stale"] is False
    assert "i_rows depends on an older revision" not in repaired["study_blockers"]
    assert (
        "req_row_report depends on an older revision"
        not in repaired["specify_blockers"]
    )
    assert (
        "d_reporting requires a verified human approval" in repaired["specify_blockers"]
    )
    assert repaired["human_approvals_present"] is False
    assert receipt["criterion_5"] == "not_assessed"
    assert receipt["field_impact"] == "not_assessed"

    derived_bytes = (derivative / "organon.json").read_bytes()
    derived = json.loads(derived_bytes)
    manifest = json.loads((derivative / "manifest.json").read_text(encoding="utf-8"))
    assert derived["project"] == original["project"]
    assert derived["events"][:24] == original["events"]
    assert len(derived["events"]) == repaired["revision"] == 42
    assert all(event["kind"] == "item_put" for event in derived["events"][24:])
    assert manifest["source_sha256"] == _digest(before[probe.SOURCE_LEDGER])
    assert manifest["derived_sha256"] == _digest(derived_bytes)
    prefix_hash = _digest(probe._encode(original["events"]).encode("utf-8"))
    assert manifest["source_event_prefix_sha256"] == prefix_hash
    assert receipt["sha256"]["historical_event_prefix"] == prefix_hash
    assert manifest["historical_prefix_head_hash"] == original["events"][-1]["hash"]
    assert receipt["sha256"]["historical_prefix_head"] == original["events"][-1]["hash"]
    assert manifest["inherited_case_id"] == original["project"]["case_id"]
    assert receipt["sha256"]["derived_ledger"] == _digest(derived_bytes)
    assert manifest["criterion_5"] == "not_assessed"
    assert "development" in (derivative / "README.md").read_text(encoding="utf-8")
    assert receipt["append_only_source_event_prefix"] is True
    assert receipt["protected_sources_unchanged"] is True
    assert {path: path.read_bytes() for path in protected} == before
