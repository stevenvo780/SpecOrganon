"""Published PDF numbers must independently constrain the bread case transcript."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from specorganon.ledger import read_project

CASE = Path(__file__).resolve().parents[1] / "cases" / "bread_norway"
sys.path.insert(0, str(CASE.parents[1] / "scripts"))
import verify_bread_frame as bread_probe  # noqa: E402
from verify_bread_frame import SourceCheckError, verify_source_transcription  # noqa: E402


def _documents() -> tuple[dict, dict]:
    manifest = json.loads((CASE / "frame_manifest.json").read_text(encoding="utf-8"))
    ledger = json.loads((CASE / "organon.json").read_text(encoding="utf-8"))
    return manifest, ledger


def test_nine_original_transcriptions_match_archived_pdf_passages() -> None:
    manifest, ledger = _documents()
    published = verify_source_transcription(manifest, ledger, CASE)
    assert len(published) == 9
    assert published["e_retail_waste"] == Decimal("11.4")
    assert published["e_household_est"] == Decimal("8.2")
    assert published["e_survey_size"] == Decimal("1000")


def test_cli_mcp_probe_requires_verified_review_and_preserves_source_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> None:
    source_case = shutil.copytree(CASE, tmp_path / "source" / "bread_norway")
    # Removing copied locks makes accidental runner writes to the source
    # visible even if the ledger itself would remain idempotent.
    for name in (".organon.lock", ".organon.runner.lock"):
        (source_case / name).unlink(missing_ok=True)
    before = bread_probe.case_file_hashes(source_case)
    monkeypatch.setattr(bread_probe, "CASE", source_case)

    bread_probe.main()

    report = json.loads(capsys.readouterr().out)
    assert report["probe_case"] == "temporary_copy"
    assert report["original_case_preserved"] is True
    assert report["original_case_sha256_before"] == report["original_case_sha256_after"] == before
    assert bread_probe.case_file_hashes(source_case) == before
    assert not (source_case / ".organon.runner.lock").exists()
    assert report["ledger_revision"] == 21
    assert report["events"] == {"item_put": 19, "phase_review": 1, "phase_advance": 1}
    assert len(report["source_content_check"]["values"]) == 9
    assert report["source_sha256"] == {
        archive: pinned[1] for archive, pinned in bread_probe.SOURCE_PDFS.items()
    }
    assert report["historical_review_verdict"] == "accept"
    assert report["historical_independence_claim_unverified"] is True
    assert report["frame_ready"] is True and report["frame_blockers"] == []
    assert report["frame_accepted"] is False and report["frame_reviewed"] is False
    assert report["independent_review"] is False
    assert report["review_provenance"] == "legacy_unverified"
    assert report["review_signature_verified"] is False
    assert report["next_phase"] == "frame" and report["next_action"] == "review_phase"
    assert report["cli_replay_skipped"] == report["mcp"]["replay_skipped"] == 19
    assert report["cli_replay_reason"] == report["mcp"]["replay_reason"] == "independent_review_required"
    assert report["mcp"]["parity_checks"] == [
        "status", "gate_frame", "gate_critique", "trace", "next_task",
        "idempotent_run", "invalid_run_no_mutation",
    ]
    assert report["critique_blockers"] == [
        "n_bread_harm requires a verified human approval",
        "previous phase is not currently accepted",
    ]
    assert report["criterion_3"] == "not_assessed"


def _rehash_events(ledger: dict) -> None:
    prior = "0" * 64
    for event in ledger["events"]:
        event["prev_hash"] = prior
        body = {key: value for key, value in event.items() if key != "hash"}
        prior = hashlib.sha256(
            json.dumps(
                body,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        event["hash"] = prior


def test_coherent_manifest_and_ledger_false_retail_value_is_rejected(
    tmp_path: Path,
) -> None:
    manifest, ledger = map(copy.deepcopy, _documents())
    manifest_item = next(
        step for step in manifest["steps"] if step.get("id") == "e_retail_waste"
    )
    ledger_item = next(
        event["payload"]
        for event in ledger["events"]
        if event["kind"] == "item_put" and event["payload"]["id"] == "e_retail_waste"
    )
    for item in (manifest_item, ledger_item):
        item["data"]["value"] = 99
        item["text"] = item["text"].replace("11,4", "99")
    _rehash_events(ledger)
    assert manifest_item["data"] == ledger_item["data"]
    assert manifest_item["text"] == ledger_item["text"]
    (tmp_path / "organon.json").write_text(json.dumps(ledger), encoding="utf-8")
    assert read_project(tmp_path, verify_external_anchor=False) == ledger

    with pytest.raises(
        SourceCheckError, match="published PDF value differs.*e_retail_waste"
    ):
        verify_source_transcription(manifest, ledger, CASE)


def test_coherent_false_visible_retail_claim_is_rejected(tmp_path: Path) -> None:
    manifest, ledger = map(copy.deepcopy, _documents())
    manifest_item = next(
        step for step in manifest["steps"] if step.get("id") == "e_retail_waste"
    )
    ledger_item = next(
        event["payload"]
        for event in ledger["events"]
        if event["kind"] == "item_put" and event["payload"]["id"] == "e_retail_waste"
    )
    for item in (manifest_item, ledger_item):
        item["text"] = item["text"].replace("11,4 %", "99 %")
    _rehash_events(ledger)
    assert manifest_item["data"] == ledger_item["data"]
    assert manifest_item["data"]["value"] == 11.4
    assert manifest_item["text"] == ledger_item["text"]
    (tmp_path / "organon.json").write_text(json.dumps(ledger), encoding="utf-8")
    assert read_project(tmp_path, verify_external_anchor=False) == ledger

    with pytest.raises(
        SourceCheckError,
        match="published PDF value differs from visible text: e_retail_waste",
    ):
        verify_source_transcription(manifest, ledger, CASE)


def test_coherent_false_household_provenance_is_rejected(tmp_path: Path) -> None:
    manifest, ledger = map(copy.deepcopy, _documents())
    manifest_item = next(
        step for step in manifest["steps"] if step.get("id") == "e_household_est"
    )
    ledger_item = next(
        event["payload"]
        for event in ledger["events"]
        if event["kind"] == "item_put" and event["payload"]["id"] == "e_household_est"
    )
    for item in (manifest_item, ledger_item):
        item["data"]["origin"] = "observed"
        item["data"]["scope"] = "medicion_directa_hogares_del_producto"
        item["text"] = (
            "El 8,2 % de desperdicio doméstico se midió directamente en hogares del producto."
        )
    _rehash_events(ledger)
    assert manifest_item["data"] == ledger_item["data"]
    assert manifest_item["text"] == ledger_item["text"]
    (tmp_path / "organon.json").write_text(json.dumps(ledger), encoding="utf-8")
    assert read_project(tmp_path, verify_external_anchor=False) == ledger

    with pytest.raises(
        SourceCheckError, match="development-case provenance differs: e_household_est"
    ):
        verify_source_transcription(manifest, ledger, CASE)


def test_false_household_interpretation_in_text_is_rejected() -> None:
    manifest, ledger = map(copy.deepcopy, _documents())
    manifest_item = next(
        step for step in manifest["steps"] if step.get("id") == "e_household_est"
    )
    ledger_item = next(
        event["payload"]
        for event in ledger["events"]
        if event["kind"] == "item_put" and event["payload"]["id"] == "e_household_est"
    )
    false_text = "El 8,2 % de desperdicio doméstico en la tabla 7 se midió directamente en hogares de este producto."
    manifest_item["text"] = ledger_item["text"] = false_text
    assert manifest_item["data"] == ledger_item["data"]
    with pytest.raises(
        SourceCheckError,
        match="development-case visible text differs from reviewed fixture: e_household_est",
    ):
        verify_source_transcription(manifest, ledger, CASE)


def test_extra_household_data_claim_is_rejected_with_valid_ledger_chain(
    tmp_path: Path,
) -> None:
    manifest, ledger = map(copy.deepcopy, _documents())
    manifest_item = next(
        step for step in manifest["steps"] if step.get("id") == "e_household_est"
    )
    ledger_item = next(
        event["payload"]
        for event in ledger["events"]
        if event["kind"] == "item_put" and event["payload"]["id"] == "e_household_est"
    )
    manifest_item["data"]["field_observed_and_lot_linked"] = True
    ledger_item["data"]["field_observed_and_lot_linked"] = True
    _rehash_events(ledger)
    assert manifest_item["data"] == ledger_item["data"]
    (tmp_path / "organon.json").write_text(json.dumps(ledger), encoding="utf-8")
    assert read_project(tmp_path, verify_external_anchor=False) == ledger
    with pytest.raises(
        SourceCheckError,
        match="development-case evidence data fields differ: e_household_est",
    ):
        verify_source_transcription(manifest, ledger, CASE)


def test_extra_top_level_household_claim_is_rejected() -> None:
    manifest, ledger = map(copy.deepcopy, _documents())
    manifest_item = next(
        step for step in manifest["steps"] if step.get("id") == "e_household_est"
    )
    ledger_item = next(
        event["payload"]
        for event in ledger["events"]
        if event["kind"] == "item_put" and event["payload"]["id"] == "e_household_est"
    )
    manifest_item["field_observed_and_lot_linked"] = True
    ledger_item["field_observed_and_lot_linked"] = True
    with pytest.raises(
        SourceCheckError,
        match="development-case evidence item shape differs: e_household_est",
    ):
        verify_source_transcription(manifest, ledger, CASE)


def test_added_evidence_dependency_is_rejected() -> None:
    manifest, ledger = map(copy.deepcopy, _documents())
    manifest_item = next(
        step for step in manifest["steps"] if step.get("id") == "e_household_est"
    )
    ledger_item = next(
        event["payload"]
        for event in ledger["events"]
        if event["kind"] == "item_put" and event["payload"]["id"] == "e_household_est"
    )
    manifest_item["refs"] = ["e_product_mass"]
    ledger_item["deps"] = {"e_product_mass": 1}
    with pytest.raises(
        SourceCheckError,
        match="development-case evidence item shape differs: e_household_est",
    ):
        verify_source_transcription(manifest, ledger, CASE)


def test_coherent_false_publication_date_is_rejected() -> None:
    manifest, ledger = map(copy.deepcopy, _documents())
    manifest_item = next(
        step for step in manifest["steps"] if step.get("id") == "e_retail_waste"
    )
    ledger_item = next(
        event["payload"]
        for event in ledger["events"]
        if event["kind"] == "item_put" and event["payload"]["id"] == "e_retail_waste"
    )
    manifest_item["data"]["date"] = ledger_item["data"]["date"] = "2026-09"
    assert manifest_item["data"] == ledger_item["data"]
    with pytest.raises(
        SourceCheckError, match="development-case provenance differs: e_retail_waste"
    ):
        verify_source_transcription(manifest, ledger, CASE)


@pytest.mark.parametrize(
    ("field", "wrong"),
    [
        ("archive", "source_survey.pdf"),
        ("locator", "tabla 8, retail waste"),
        ("metric_key", "consumer_bread_waste_estimate"),
        ("unit", "kg/pieza"),
    ],
)
def test_coherent_manifest_and_ledger_false_attribution_is_rejected(
    field: str, wrong: str
) -> None:
    manifest, ledger = map(copy.deepcopy, _documents())
    manifest_item = next(
        step for step in manifest["steps"] if step.get("id") == "e_retail_waste"
    )
    ledger_item = next(
        event["payload"]
        for event in ledger["events"]
        if event["kind"] == "item_put" and event["payload"]["id"] == "e_retail_waste"
    )
    manifest_item["data"][field] = ledger_item["data"][field] = wrong
    assert manifest_item["data"] == ledger_item["data"]

    with pytest.raises(
        SourceCheckError, match="PDF claim identity differs: e_retail_waste"
    ):
        verify_source_transcription(manifest, ledger, CASE)


def test_coherent_manifest_and_ledger_false_doi_is_rejected() -> None:
    manifest, ledger = map(copy.deepcopy, _documents())
    manifest_item = next(
        step for step in manifest["steps"] if step.get("id") == "e_retail_waste"
    )
    ledger_item = next(
        event["payload"]
        for event in ledger["events"]
        if event["kind"] == "item_put" and event["payload"]["id"] == "e_retail_waste"
    )
    manifest_item["data"]["source"] = ledger_item["data"]["source"] = (
        "https://doi.org/10.3390/su10072251"
    )
    assert manifest_item["data"] == ledger_item["data"]
    with pytest.raises(SourceCheckError, match="PDF DOI differs: e_retail_waste"):
        verify_source_transcription(manifest, ledger, CASE)


def test_archived_source_bytes_must_remain_fixed(tmp_path: Path) -> None:
    manifest, ledger = _documents()
    (tmp_path / "source_lca.pdf").write_bytes(
        (CASE / "source_lca.pdf").read_bytes() + b" "
    )
    (tmp_path / "source_survey.pdf").write_bytes(
        (CASE / "source_survey.pdf").read_bytes()
    )
    with pytest.raises(
        SourceCheckError, match="archived PDF size changed: source_lca.pdf"
    ):
        verify_source_transcription(manifest, ledger, tmp_path)
