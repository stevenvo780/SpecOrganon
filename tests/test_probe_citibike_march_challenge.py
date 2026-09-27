"""Public CLI challenge regression on the pinned historical March case."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from specorganon.ledger import read_project


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import probe_citibike_march_challenge as probe  # noqa: E402


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def test_real_cli_challenge_resolution_reopens_without_source_edits(tmp_path: Path) -> None:
    before = {path: path.read_bytes() for path in probe.PROTECTED}
    published = json.loads(before[probe.PUBLISHED_RESULT])
    source = json.loads(before[probe.SOURCE_LEDGER])
    derived = tmp_path / "derived"
    output = derived / "receipt.json"
    process = subprocess.run(
        [sys.executable, str(ROOT / "scripts/probe_citibike_march_challenge.py"),
         "--derived-case", str(derived), "--output", str(output)],
        cwd=ROOT, text=True, capture_output=True, check=True, timeout=90,
    )
    receipt = json.loads(process.stdout)
    assert output.read_bytes() == process.stdout.encode("utf-8")
    assert receipt["classification"] == "public_development_adversarial_challenge_probe"
    assert receipt["transport"] == "installed_organon_cli"
    assert receipt["adversarial_claim"]["classification"] == (
        "synthetic_on_authentic_published_counts"
    )
    counts = receipt["denominator_source_check"]
    assert counts["raw_rows"] == published["rows"] == 1_812_548
    assert counts["excluded_rows"] == published["quality"]["excluded_rows"] == 3_512
    assert counts["eligible_rows"] == published["quality"]["conservative_dock_rows"] == 1_809_036
    assert counts["published_denominator"] == published["snapshot_row_service"]["denominator"]
    assert counts["raw_rows"] - counts["excluded_rows"] == counts["eligible_rows"]
    assert counts["detection"] == "manual_challenge_after_pinned_source_assertion"

    challenge = receipt["challenged"]
    challenge_seq = challenge["challenge_seq"]
    assert challenge["open_challenge_seqs"] == [challenge_seq]
    assert challenge["items"]["e_eligible"]["contested"] is True
    for item_id in probe.DESCENDANTS:
        assert challenge["items"][item_id]["contested"] is True
        assert challenge["items"][item_id]["stale"] is False
        assert challenge["items"][item_id]["denominator"] == counts["raw_rows"]
    for phase, item_id in (
        ("study", probe.INDICATOR), ("observe", probe.INFERENCE),
        ("specify", probe.REQUIREMENT),
    ):
        assert f"{item_id} has an unresolved contradiction" in challenge["phase_blockers"][phase]

    failures = receipt["rejected_operations"]
    assert "later synthesis" in failures["premature_synthesis"]["error"]
    assert "independent accepted item review" in failures["unreviewed_synthesis"]["error"]
    assert "reviewer must differ" in failures["self_review"]["error"]
    assert all(failure["ledger_unchanged"] for failure in failures.values())
    invalid = receipt["corrected_inference_invalidated"]
    assert invalid["items"][probe.INFERENCE]["version"] == 2
    assert invalid["items"][probe.INFERENCE]["denominator"] == counts["eligible_rows"]
    assert invalid["items"][probe.INDICATOR]["stale"] is True
    assert invalid["items"][probe.REQUIREMENT]["stale"] is True

    synthesis = receipt["reviewed_synthesis"]
    assert {probe.INFERENCE, "e_eligible", "e_excluded"} <= set(synthesis["ancestors"])
    assert synthesis["selected_denominator"] == counts["eligible_rows"]
    assert synthesis["rejected_raw_denominator"] == counts["raw_rows"]
    assert synthesis["review_actor"] != probe.AUTHOR
    assert synthesis["review_scope"] == "actor_separation_only_no_external_human_review"
    pre_resolution = receipt["before_resolution"]
    assert pre_resolution["open_challenge_seqs"] == [challenge_seq]
    for item_id in (*probe.DESCENDANTS, probe.SYNTHESIS):
        assert pre_resolution["items"][item_id]["denominator"] == counts["eligible_rows"]
        assert pre_resolution["items"][item_id]["contested"] is True
        assert pre_resolution["items"][item_id]["stale"] is False

    resolved = receipt["resolved"]
    assert resolved["open_challenge_seqs"] == []
    assert resolved["norm_approved"] is False
    assert "n_scope requires a verified human approval" in resolved["critique_blockers"]
    assert "req_raw_fraction lacks a path to problem, norm, evidence or decision" in (
        resolved["specify_blockers"]
    )
    for item_id in (*probe.DESCENDANTS, probe.SYNTHESIS):
        assert resolved["items"][item_id]["denominator"] == counts["eligible_rows"]
        assert resolved["items"][item_id]["contested"] is False
        assert resolved["items"][item_id]["stale"] is False
    assert resolved["items"][probe.INDICATOR]["version"] == 2
    assert resolved["items"][probe.REQUIREMENT]["version"] == 2
    assert probe.SYNTHESIS in resolved["items"][probe.INDICATOR]["deps"]
    assert probe.SYNTHESIS in resolved["items"][probe.REQUIREMENT]["deps"]

    reopened = receipt["reopened"]
    assert reopened["open_challenge_seqs"] == [challenge_seq]
    assert reopened["items"]["e_eligible"]["version"] == 2
    assert reopened["items"]["e_eligible"]["stale"] is False
    for item_id in (*probe.DESCENDANTS, probe.SYNTHESIS):
        assert reopened["items"][item_id]["stale"] is True
        assert reopened["items"][item_id]["contested"] is True
        assert reopened["items"][item_id]["denominator"] == counts["eligible_rows"]
    assert "i_raw_fraction depends on an older revision" in reopened["phase_blockers"]["study"]
    assert "req_raw_fraction has an unresolved contradiction" in reopened["phase_blockers"]["specify"]

    derived_bytes = (derived / "organon.json").read_bytes()
    derived_ledger = read_project(derived)
    manifest = json.loads((derived / "manifest.json").read_bytes())
    assert derived_ledger["project"] == source["project"]
    assert derived_ledger["events"][:24] == source["events"]
    assert derived_ledger["events"][challenge_seq - 1]["kind"] == "challenge"
    assert derived_ledger["events"][resolved["resolution_seq"] - 1]["kind"] == "challenge_resolved"
    assert derived_ledger["events"][synthesis["review_seq"] - 1]["kind"] == "item_review"
    assert all(
        event["kind"] not in {"approval", "phase_advance", "phase_review"}
        for event in derived_ledger["events"][24:]
    )
    assert manifest["source_sha256"] == _sha256(before[probe.SOURCE_LEDGER])
    assert manifest["seed_sha256"] == _sha256(before[probe.SEED])
    assert manifest["derived_sha256"] == _sha256(derived_bytes)
    assert manifest["historical_prefix_head_hash"] == source["events"][23]["hash"]
    assert (derived / "seed.json").read_bytes() == before[probe.SEED]
    assert receipt["derived_ledger"]["event_count"] == len(derived_ledger["events"]) == 35
    assert receipt["derived_ledger"]["historical_prefix_preserved"] is True
    assert receipt["human_approval"] == manifest["human_approval"] == "absent"
    assert receipt["criterion_5"] == manifest["criterion_5"] == "not_assessed"
    assert receipt["field_impact"] == "not_assessed"
    assert receipt["protected_sources_unchanged"] is True
    assert {path: path.read_bytes() for path in probe.PROTECTED} == before


def test_seed_alignment_rejects_modified_candidate_source() -> None:
    seed = json.loads(probe.SEED.read_bytes())
    ledger = json.loads(probe.SOURCE_LEDGER.read_bytes())
    changed = deepcopy(seed)
    next(item for item in changed["items"] if item["id"] == "e_eligible")["data"]["value"] += 1
    with pytest.raises(AssertionError, match="seed item e_eligible differs"):
        probe._seed_matches_ledger(changed, ledger)


def test_destinations_cannot_replace_historical_sources(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="historical case sources"):
        probe._validate_destinations(probe.SOURCE_LEDGER, None)
    with pytest.raises(ValueError, match="historical case sources"):
        probe._validate_destinations(None, ROOT / "cases/new_development_derivative")
    with pytest.raises(ValueError, match="collides"):
        probe._validate_destinations(tmp_path / "derived/organon.json", tmp_path / "derived")
