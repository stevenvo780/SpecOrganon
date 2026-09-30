"""Real source preparation and pending prospectus lineage; no field intervention."""

from __future__ import annotations

import hashlib
import json
import shutil
from fractions import Fraction
from pathlib import Path

import pytest

from scripts import build_bread_prospectus as prospectus
from specorganon import engine
from specorganon.ledger import read_project
from specorganon.lot_journal import audit_lot_journal
from specorganon.runner import run_manifest

ROOT = Path(__file__).resolve().parents[1]


def _json(path):
    return json.loads(path.read_bytes())


def _pins(directory):
    return {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob("*") if path.is_file()}


@pytest.fixture
def prepared(tmp_path):
    directory = tmp_path / "prospectus"
    result = prospectus.prepare(directory)
    return directory, result


def test_real_d100_sources_prepare_closed_new_pending_prospectus(prepared):
    directory, result = prepared
    assert result["state"] == "prepared" and result["manifest_steps"] == 64
    assert result["ledger_created"] is False and result["execution_ready"] is False
    assert result["example_classification"] == "synthetic_arithmetic_not_observed_lot"
    assert not list(directory.rglob("organon.json"))
    audit = _json(directory / "case/audit_report.json")
    assert audit["passed"] is True and audit["verified_claims"] == 17 and audit["verified_survey_rows"] == 7
    manifest = _json(directory / "manifest.json")
    assert len(manifest["steps"]) == 64
    assert all(step["op"] == "put" for step in manifest["steps"])
    assert len({step["id"] for step in manifest["steps"]}) == 64
    plan = _json(directory / "prospectus.json")
    assert plan["classification"] == "food_intervention_prospectus_unapproved"
    assert plan["source_coverage"] == {"published_numeric_claims": 17, "archived_survey_rows": 7}
    assert plan["norms_approved"] is False and plan["field_intervention"] is False
    assert plan["execution_ready"] is False and plan["effect_estimate"] is None
    assert plan["Q"] is None and plan["global_acceptance"] == "0/5"
    assert plan["historical_waste_rates_are_sequential_lot_measurements"] is False
    assert plan["slices_to_kg_conversion"] is None
    protocol = plan["measurement_protocol"]
    for field in ("sample_size", "primary_value_metric", "success_threshold", "rejection_threshold",
                  "human_approved_equivalences", "human_approved_harm_margins"):
        assert protocol[field] is None
    assert all(option["selection"] == "unselected" and option["efficacy_estimate"] is None
               and option["cost_estimate"] is None for option in plan["options"])
    assert all(row["competent_approval"] is None and row["equivalence_or_margin"] is None
               for row in plan["value_matrix"])


def test_documentary_normalization_keeps_units_and_does_not_become_an_observed_lot(prepared):
    directory, _ = prepared
    audit = _json(directory / "case/audit_report.json")
    quantities = _json(directory / "prospectus.json")["derived_documentary_quantities"]
    assert quantities["normalization_input_kg"] == 1000
    assert quantities["normalization_is_observed_lot"] is False
    mass_outputs = quantities["wheat_outputs_per_normalized_tonne_kg"]
    assert sum(Fraction(value) for value in mass_outputs.values()) == 1000
    for key, value in mass_outputs.items():
        assert Fraction(value) == Fraction(audit["claims"][key]["value"]) * 10
    energy = quantities["bakery_total_energy_per_kg"]
    assert energy["unit"] == "kWh/kg bread"
    assert energy["classification"] == "derived_from_published_piece_values"
    published_energy = sum(Fraction(audit["claims"][key]["value"])
                           for key in ("bakery_electricity", "bakery_natural_gas"))
    assert Fraction(energy["numerator"], energy["denominator"]) == published_energy / (
        Fraction(audit["claims"]["piece_mass"]["value"]) / 1000)


def test_example_arithmetic_is_incremental_balanced_and_dry_pending(prepared):
    directory, _ = prepared
    example = _json(directory / "example_journal.json")
    recorded = _json(directory / "example_audit.json")
    assert recorded == audit_lot_journal(example)
    assert all(row["wet"]["residual_kg"] == "0" for row in recorded["balances"])
    assert recorded["pending"]["dry_balance_event_ids"] == ["milling", "baking"]
    assert recorded["pending"]["capture_completeness"] == "not_established"
    assert recorded["observations_authenticated"] is False
    assert recorded["field_scope_complete"] is False and recorded["execution_ready"] is False
    assert recorded["criterion_3"]["status"] == "not_assessed"
    assert all("Synthetic" in event["source"]["method"] for event in example["events"])


def test_real_engine_accepts_all_puts_as_pending_and_requirements_trace_sources(prepared):
    directory, _ = prepared
    case = directory / "case"
    manifest = _json(directory / "manifest.json")
    engine.create_case(case, prospectus.TITLE, "food", prospectus.ACTOR, approval_policy="signed")
    result = run_manifest(case, manifest, prospectus.ACTOR)
    assert result["status"] == "waiting" and result["applied"] == 64 and result["cursor"] == 64
    state = engine.get_state(case)
    assert state["revision"] == 64 and len(state["items"]) == 64
    assert state["project"]["approval_policy"] == "signed"
    assert all(phase["accepted"] is False for phase in state["phases"].values())
    for id, item in state["items"].items():
        if item["kind"] in {"norm", "decision"}:
            assert item["approved"] is False
            phase = "critique" if item["kind"] == "norm" else "specify"
            assert any(id in blocker and "approval" in blocker for blocker in state["phases"][phase]["blockers"])
        if item["kind"] == "requirement":
            kinds = {ancestor["kind"] for ancestor in engine.trace(case, id)["ancestors"]}
            assert {"problem", "norm", "evidence", "decision"} <= kinds
        if item["kind"] == "criterion":
            assert item["data"]["threshold"] is None
        if item["kind"] == "evidence":
            assert item["data"]["origin"] in {"published", "derived"}
    assert not any(item["kind"] in {"baseline", "result"} for item in state["items"].values())
    assert state["items"]["as_field_pending"]["data"]["verdict"] == "no_demostrado"
    assert all(event["kind"] == "item_put" and event["actor"] == prospectus.ACTOR for event in read_project(case)["events"])
    assert state["phase_review_history"] == []


@pytest.mark.parametrize("defect", ["false737", "false_root", "duplicate_key", "altered_pdf"])
def test_false_or_invalid_public_source_packet_rejects_before_ledger(tmp_path, monkeypatch, defect):
    repository = tmp_path / "source-copy"
    source = repository / "cases/bread_norway"
    source.mkdir(parents=True)
    claims = repository / "cases/bread_development/source_claims.json"
    claims.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "cases/bread_development/source_claims.json", claims)
    for name in ("survey_table1.json", "source_lca.pdf", "source_survey.pdf"):
        shutil.copyfile(ROOT / "cases/bread_norway" / name, source / name)
    if defect == "false737":
        document = _json(claims)
        next(claim for claim in document["claims"] if claim["key"] == "piece_mass")["value"] = 737
        claims.write_text(json.dumps(document), encoding="utf-8")
    elif defect == "false_root":
        claims.write_text("false", encoding="utf-8")
    elif defect == "duplicate_key":
        claims.write_text('{"schema":1,"schema":1}', encoding="utf-8")
    else:
        pdf = source / "source_lca.pdf"
        pdf.write_bytes(pdf.read_bytes() + b"altered archived PDF")
    monkeypatch.setattr(prospectus, "ROOT", repository)
    directory = tmp_path / "rejected-prospectus"
    with pytest.raises(prospectus.base.RecipeError):
        prospectus.prepare(directory)
    assert not list(directory.rglob("organon.json"))
    assert not (directory / "prospectus.json").exists()


def test_existing_destination_is_rejected_without_overwrite(tmp_path):
    directory = tmp_path / "existing"
    directory.mkdir()
    marker = directory / "retain.txt"
    marker.write_text("existing unrelated work", encoding="utf-8")
    before = _pins(directory)
    with pytest.raises(prospectus.base.RecipeError, match="destination must be new"):
        prospectus.prepare(directory)
    assert _pins(directory) == before


def test_changed_archived_claim_after_documentary_prepare_is_not_republished(tmp_path, monkeypatch):
    real_prepare = prospectus.base.prepare

    def prepare_then_alter(repo, directory, *args, **kwargs):
        result = real_prepare(repo, directory, *args, **kwargs)
        claims_path = directory / "case/source_claims.json"
        claims = _json(claims_path)
        next(claim for claim in claims["claims"] if claim["key"] == "piece_mass")["value"] = 737
        claims_path.write_text(json.dumps(claims), encoding="utf-8")
        return result

    monkeypatch.setattr(prospectus.base, "prepare", prepare_then_alter)
    directory = tmp_path / "changed-source-packet"
    with pytest.raises(prospectus.base.RecipeError):
        prospectus.prepare(directory)
    assert not list(directory.rglob("organon.json"))
    assert _json(directory / "binding.json")["study_id"] == "D101"
    assert not (directory / "documentary_binding.json").exists()
    assert len(_json(directory / "manifest.json")["steps"]) == 37


def test_new_prospectus_preserves_separate_original_d101_preparation(tmp_path):
    original = tmp_path / "original-d101"
    prospectus.base.prepare(ROOT, original)
    before = _pins(original)
    directory = tmp_path / "new-d102"
    prospectus.prepare(directory)
    engine.create_case(directory / "case", prospectus.TITLE, "food", prospectus.ACTOR)
    run_manifest(directory / "case", _json(directory / "manifest.json"), prospectus.ACTOR)
    assert _pins(original) == before
    assert not list(original.rglob("organon.json"))
    assert len(_json(original / "manifest.json")["steps"]) == 37
    assert len(_json(directory / "manifest.json")["steps"]) == 64
