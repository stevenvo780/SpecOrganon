"""Historical March ledger lineage regression with real CLI and stdio MCP."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from specorganon import engine
from specorganon.ledger import read_project


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
    derivative = tmp_path / "derivative"
    receipt_path = derivative / "receipt.json"
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
    assert _digest(receipt_path.read_bytes()) == _digest(
        completed.stdout.encode("utf-8")
    )
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


@pytest.mark.parametrize("artifact", probe.DERIVED_ARTIFACT_NAMES)
def test_output_collision_rejected_before_new_derived_case(
    tmp_path: Path, artifact: str
) -> None:
    versioned = ROOT / "cases/citibike_march2024_lineage"
    protected = tuple(versioned / name for name in probe.DERIVED_ARTIFACT_NAMES)
    before = {path: path.read_bytes() for path in protected}
    derived = tmp_path / "derived"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/probe_citibike_march_indicator_lineage.py"),
            "--derived-case",
            str(derived),
            "--output",
            str(derived / artifact),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert completed.returncode == 2
    assert "--output collides with a derived-case artifact" in completed.stderr
    assert not derived.exists()
    assert {path: path.read_bytes() for path in protected} == before


@pytest.mark.parametrize("alias_kind", ("parent", "output"))
def test_output_collision_resolves_symlink_aliases(
    tmp_path: Path, alias_kind: str
) -> None:
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    derived = real_parent / "derived"
    if alias_kind == "parent":
        alias = tmp_path / "alias"
        alias.symlink_to(real_parent, target_is_directory=True)
        output = alias / "derived" / "organon.json"
    else:
        output = tmp_path / "receipt-link.json"
        output.symlink_to(derived / "organon.json")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/probe_citibike_march_indicator_lineage.py"),
            "--derived-case",
            str(derived),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert completed.returncode == 2
    assert "--output collides with a derived-case artifact" in completed.stderr
    assert not derived.exists()


def test_existing_versioned_derivative_survives_colliding_output() -> None:
    derived = ROOT / "cases/citibike_march2024_lineage"
    protected = tuple(derived / name for name in probe.DERIVED_ARTIFACT_NAMES)
    before = {path: path.read_bytes() for path in protected}
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/probe_citibike_march_indicator_lineage.py"),
            "--derived-case",
            str(derived),
            "--output",
            str(derived / "organon.json"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert completed.returncode == 2
    assert "--output collides with a derived-case artifact" in completed.stderr
    assert {path: path.read_bytes() for path in protected} == before


def test_atomic_receipt_keeps_existing_bytes_if_publish_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "receipt.json"
    output.write_bytes(b"existing receipt\n")

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("simulated publication failure")

    monkeypatch.setattr(probe.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated publication failure"):
        probe._write_receipt_atomic(output, '{"new":true}\n')
    assert output.read_bytes() == b"existing receipt\n"
    assert list(tmp_path.iterdir()) == [output]


def test_atomic_receipt_verifies_published_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "receipt.json"
    original_read_bytes = Path.read_bytes

    def read_corrupted(path: Path) -> bytes:
        if path == output:
            return b"corrupted after publication"
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read_corrupted)
    with pytest.raises(AssertionError, match="receipt hash differs"):
        probe._write_receipt_atomic(output, '{"new":true}\n')
    assert original_read_bytes(output) == b'{"new":true}\n'


def test_versioned_lineage_artifacts_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    derived = ROOT / "cases/citibike_march2024_lineage"
    ledger_path = derived / "organon.json"
    manifest_path = derived / "manifest.json"
    receipt_path = (
        ROOT
        / "experiments/development/citibike_march_indicator_lineage_2026-09-27.json"
    )
    delivered = (ledger_path, manifest_path, receipt_path)
    before = {path: path.read_bytes() for path in delivered}
    ledger = read_project(derived, verify_external_anchor=False)
    source = read_project(probe.SOURCE_CASE, verify_external_anchor=False)
    manifest = json.loads(before[manifest_path])
    receipt = json.loads(before[receipt_path])

    assert len(source["events"]) == manifest["source_event_count"] == 24
    assert len(ledger["events"]) == manifest["derived_event_count"] == 42
    assert ledger["project"] == source["project"]
    assert ledger["events"][:24] == source["events"]
    assert manifest["inherited_case_id"] == source["project"]["case_id"]
    assert (
        manifest["source_sha256"]
        == receipt["sha256"]["source_ledger"]
        == _digest(probe.SOURCE_LEDGER.read_bytes())
    )
    assert (
        manifest["derived_sha256"]
        == receipt["sha256"]["derived_ledger"]
        == _digest(before[ledger_path])
    )
    prefix_hash = _digest(probe._encode(source["events"]).encode("utf-8"))
    assert (
        manifest["source_event_prefix_sha256"]
        == receipt["sha256"]["historical_event_prefix"]
        == prefix_hash
    )
    assert (
        manifest["historical_prefix_head_hash"]
        == receipt["sha256"]["historical_prefix_head"]
        == ledger["events"][23]["hash"]
    )
    assert [
        ledger["events"][index - 1]["payload"]["id"] for index in (25, 30, 31, 42)
    ] == ["i_rows", "req_row_report", "e_eligible", "req_row_report"]
    assert all(event["kind"] == "item_put" for event in ledger["events"][24:])

    for revision, label in (
        (30, "before_source_revision"),
        (31, "invalidated"),
        (42, "repaired"),
    ):
        prefix = {**ledger, "events": ledger["events"][:revision]}
        with monkeypatch.context() as patch:
            patch.setattr(engine, "read_project", lambda _path: prefix)
            state = engine.get_state(derived)
            study = engine.gate(derived, "study")
            specify = engine.gate(derived, "specify")
        expected = receipt["linked"][label]
        assert state["revision"] == expected["revision"] == revision
        assert probe._record(state, *expected["items"]) == expected["items"]
        assert study["blockers"] == expected["study_blockers"]
        assert specify["blockers"] == expected["specify_blockers"]
        if revision == 30:
            assert state["items"]["i_rows"]["version"] == 2
            assert state["items"]["req_row_report"]["stale"] is False
        elif revision == 31:
            assert state["items"]["i_rows"]["stale"] is True
            assert state["items"]["req_row_report"]["stale"] is True
        else:
            assert state["items"]["i_rows"]["version"] == 3
            assert state["items"]["req_row_report"]["version"] == 2
            assert state["items"]["i_rows"]["stale"] is False
            assert state["items"]["req_row_report"]["stale"] is False
            assert (
                "d_reporting requires a verified human approval" in specify["blockers"]
            )

    assert not any(event["kind"] == "approval" for event in ledger["events"])
    assert manifest["human_approval"] == "absent"
    assert manifest["criterion_5"] == receipt["criterion_5"] == "not_assessed"
    assert receipt["field_impact"] == "not_assessed"
    assert receipt["numeric_source_check"] == {
        "raw_rows": 1_812_548,
        "excluded_rows": 3_512,
        "eligible_denominator": 1_809_036,
        "false_raw_row_denominator_rejected": True,
    }
    assert {path: path.read_bytes() for path in delivered} == before
