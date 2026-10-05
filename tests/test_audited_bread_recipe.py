"""D101 publishes a pending signed recipe only after reauditing its public inputs."""

from __future__ import annotations

import asyncio
import copy
import errno
import fcntl
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from scripts import run_audited_bread_recipe as recipe
from specorganon import engine
from specorganon.ledger import read_project

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "cases/bread_development/source_claims.json"
TABLE = ROOT / "cases/bread_norway/survey_table1.json"
CLI = Path(sys.executable).parent / "organon"


def _load(path: Path) -> dict:
    return json.loads(path.read_bytes())


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def _pin(path: Path) -> dict:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _rehash_packet(directory: Path, report: dict) -> None:
    """Make the editable packet internally coherent without changing trusted code."""
    case = directory / "case"
    _write(case / "audit_report.json", report)
    binding = _load(directory / "binding.json")
    binding["files"] = {name: _pin(case / name) for name in binding["files"]}
    manifest = recipe.build_manifest(report, binding["files"])
    _write(directory / "manifest.json", manifest)
    binding["manifest"] = _pin(directory / "manifest.json")
    _write(directory / "binding.json", binding)


def _claim(document: dict, key: str) -> dict:
    return next(item for item in document["claims"] if item["key"] == key)


def _ledger_files(directory: Path) -> list[Path]:
    return list(directory.rglob("organon.json")) if directory.exists() else []


@pytest.fixture
def prepared(tmp_path):
    directory = tmp_path / "trial"
    result = recipe.prepare(ROOT, directory)
    return directory, result


@pytest.mark.parametrize("field,value", [
    ("value", 737), ("value", True), ("unit", "kg/piece"),
    ("base", "Per household per day"), ("provenance", "field_observation"),
])
def test_invalid_claim_rejected_before_ledger_publication(tmp_path, field, value):
    claims = _load(CLAIMS)
    _claim(claims, "piece_mass")[field] = value
    claims_path = tmp_path / "claims.json"
    _write(claims_path, claims)
    directory = tmp_path / "trial"
    with pytest.raises(recipe.RecipeError):
        recipe.prepare(ROOT, directory, claims_path=claims_path)
    assert not _ledger_files(directory)


@pytest.mark.parametrize("document,defect", [
    ("claims", "duplicate_key"), ("claims", "duplicate_claim"), ("claims", "false_root"),
    ("table", "duplicate_key"), ("table", "false_root"),
])
def test_invalid_json_and_duplicate_claims_reject_before_publication(tmp_path, document, defect):
    claims = _load(CLAIMS)
    path = tmp_path / "claims.json"
    if defect == "duplicate_key":
        path.write_text('{"schema":1,"schema":1}', encoding="utf-8")
    elif defect == "duplicate_claim":
        claims["claims"].append(copy.deepcopy(claims["claims"][0]))
        _write(path, claims)
    else:
        path.write_text("false", encoding="utf-8")
    directory = tmp_path / "trial"
    with pytest.raises(recipe.RecipeError):
        recipe.prepare(ROOT, directory, **{f"{document}_path": path})
    assert not _ledger_files(directory)


def test_prepare_preserves_audited_inputs_without_creating_a_ledger(prepared):
    directory, result = prepared
    case = directory / "case"
    assert result["state"] == "prepared"
    assert result["coverage"] == {
        "published_numeric_claims": 17, "audited_archived_survey_rows": 7,
    }
    assert result["ledger_created"] is False
    assert not _ledger_files(directory)
    assert (case / "source_claims.json").read_bytes() == CLAIMS.read_bytes()
    assert (case / "survey_table1.json").read_bytes() == TABLE.read_bytes()
    audit = _load(case / "audit_report.json")
    assert audit["passed"] is True
    assert audit["verified_claims"] == 17 and audit["verified_survey_rows"] == 7
    assert audit["base_validation"] == "reviewed_contract_consistency"
    assert audit["Q"] is None and audit["field_intervention"] is False
    manifest = _load(directory / "manifest.json")
    assert result["manifest_steps"] == len(manifest["steps"])
    assert all(step["op"] == "put" for step in manifest["steps"])
    by_id = {step["id"]: step for step in manifest["steps"]}
    assert len(by_id) == len(manifest["steps"])
    for key, claim in audit["claims"].items():
        item = by_id[f"e_{key}"]
        assert item["kind"] == "evidence"
        assert item["data"]["origin"] == "published"
        assert item["data"]["unit"] == claim["unit"]
    assert {"e_bundle_claims", "e_bundle_table", "e_bundle_contract", "e_bundle_audit"} <= by_id.keys()
    binding = _load(directory / "binding.json")
    for bundle in ("claims", "table", "contract", "audit"):
        item = by_id[f"e_bundle_{bundle}"]
        archive = item["data"]["archive"]
        assert item["data"]["source_sha256"] == binding["files"][archive]["sha256"]
        assert binding["files"][archive] == _pin(case / archive)
    for key, claim in audit["claims"].items():
        item = by_id[f"e_{key}"]
        data = item["data"]
        passage = audit["passages"][claim["passage"]]
        assert data["value"] == claim["value"]
        assert data["base"] == claim["base"] and data["provenance"] == claim["provenance"]
        assert data["audited_locator"] == claim["locator"]
        assert data["source_sha256"] == audit["source_extraction"][claim["source"]]["sha256"]
        assert data["source_sha256"] == _pin(case / data["archive"])["sha256"]
        assert data["audit_report_sha256"] == _pin(case / "audit_report.json")["sha256"]
        assert data["audit_contract_sha256"] == _pin(case / "audit_contract.json")["sha256"]
        for field in ("page_sha256", "passage_sha256", "matched_sha256"):
            assert data[field] == passage[field]
        assert {"p_seed", "pr_docs", "e_bundle_audit"} <= set(item["refs"])
    assert recipe.validate(directory)["state"] == "prepared"


@pytest.mark.parametrize("name", [
    "source_claims.json", "survey_table1.json", "source_lca.pdf", "source_survey.pdf",
    "audit_contract.json", "audit_report.json",
])
def test_archived_input_tamper_is_rejected_before_execute(prepared, name):
    directory, _ = prepared
    path = directory / "case" / name
    path.write_bytes(path.read_bytes() + b"\nchanged")
    with pytest.raises(recipe.RecipeError):
        recipe.validate(directory)
    with pytest.raises(recipe.RecipeError):
        asyncio.run(recipe.execute(directory, cli=CLI))
    assert not _ledger_files(directory)


@pytest.mark.parametrize("field,value", [
    ("value", 737), ("unit", "kg/piece"),
    ("base", "Per household per day"), ("provenance", "field_observation"),
])
def test_forged_passed_report_and_coherent_hashes_cannot_bypass_fresh_audit(prepared, field, value):
    directory, _ = prepared
    case = directory / "case"
    claims = _load(case / "source_claims.json")
    _claim(claims, "piece_mass")[field] = value
    _write(case / "source_claims.json", claims)
    report = _load(case / "audit_report.json")
    report["claims"]["piece_mass"][field] = str(value) if field == "value" else value
    report["passed"] = True
    report["input_pins"]["claims"] = _pin(case / "source_claims.json")
    _rehash_packet(directory, report)
    with pytest.raises(recipe.RecipeError, match="source precondition rejected"):
        recipe.validate(directory)
    with pytest.raises(recipe.RecipeError, match="source precondition rejected"):
        asyncio.run(recipe.execute(directory, cli=CLI))
    assert not _ledger_files(directory)


def test_forged_audit_receipt_with_coherent_manifest_is_compared_to_new_extraction(prepared):
    directory, _ = prepared
    report = _load(directory / "case/audit_report.json")
    report["passages"][report["claims"]["piece_mass"]["passage"]]["matched_sha256"] = "0" * 64
    _rehash_packet(directory, report)
    with pytest.raises(recipe.RecipeError, match="persisted audit differs"):
        recipe.validate(directory)
    assert not _ledger_files(directory)


def test_coherent_forged_survey_rows_are_reextracted_before_publication(prepared):
    directory, _ = prepared
    case = directory / "case"
    table = _load(case / "survey_table1.json")
    first, second = table["categories"][:2]
    first["count"] += 1
    second["count"] -= 1
    first["reported_percent"] = "43.0"
    second["reported_percent"] = "30.0"
    assert sum(row["count"] for row in table["categories"]) == table["reported_total"]
    _write(case / "survey_table1.json", table)
    report = _load(case / "audit_report.json")
    for row, changed in zip(report["survey_rows"], table["categories"], strict=True):
        row.update(changed)
    report["input_pins"]["table"] = _pin(case / "survey_table1.json")
    _rehash_packet(directory, report)
    with pytest.raises(recipe.RecipeError, match="source precondition rejected"):
        recipe.validate(directory)
    with pytest.raises(recipe.RecipeError):
        asyncio.run(recipe.execute(directory, cli=CLI))
    assert not _ledger_files(directory)


@pytest.mark.parametrize("field,value", [
    ("coverage", {"published_numeric_claims": 999, "audited_archived_survey_rows": 99}),
    ("approval_policy", "fixture"), ("phase_advances", 1), ("human_approvals", 1),
])
def test_binding_cannot_overstate_coverage_or_change_pending_signed_contract(prepared, field, value):
    directory, _ = prepared
    binding = _load(directory / "binding.json")
    binding[field] = value
    _write(directory / "binding.json", binding)
    with pytest.raises(recipe.RecipeError):
        recipe.validate(directory)
    with pytest.raises(recipe.RecipeError):
        asyncio.run(recipe.execute(directory, cli=CLI))
    assert not _ledger_files(directory)


@pytest.mark.parametrize("relative", [
    "case/source_lca.pdf", "case/source_claims.json", "case/audit_report.json",
    "manifest.json", "binding.json",
])
def test_equal_bytes_through_symlink_are_rejected(prepared, tmp_path, relative):
    directory, _ = prepared
    path = directory / relative
    external = tmp_path / "external"
    external.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(external)
    with pytest.raises(recipe.RecipeError, match="symlink"):
        recipe.validate(directory)
    with pytest.raises(recipe.RecipeError):
        asyncio.run(recipe.execute(directory, cli=CLI))
    assert not _ledger_files(directory)


def test_symlink_input_is_rejected_before_ledger_creation(tmp_path):
    claims = tmp_path / "claims.json"
    claims.symlink_to(CLAIMS)
    directory = tmp_path / "trial"
    with pytest.raises(recipe.RecipeError, match="symlink"):
        recipe.prepare(ROOT, directory, claims_path=claims)
    assert not _ledger_files(directory)


def test_manifest_override_cannot_publish_an_unaudited_number(prepared):
    directory, _ = prepared
    manifest = _load(directory / "manifest.json")
    numeric = next(step for step in manifest["steps"] if step["id"] == "e_piece_mass")
    numeric["data"]["value"] = 737
    with pytest.raises(recipe.RecipeError):
        recipe.validate(directory, manifest)
    assert not _ledger_files(directory)


def test_real_cli_recipe_is_pending_and_restart_writes_zero_events(prepared):
    directory, _ = prepared
    first = asyncio.run(recipe.execute(directory, cli=CLI))
    assert first["result"]["status"] == "waiting"
    assert first["result"]["reason"] == "independent_review_required"
    assert first["result"]["applied"] == 37 and first["result"]["skipped"] == 0
    assert first["phase_advances_requested"] == first["human_approvals_requested"] == 0
    case = directory / "case"
    state = engine.get_state(case)
    assert state["project"]["approval_policy"] == "signed"
    assert all(item["version"] == 1 for item in state["items"].values())
    assert all(phase["accepted"] is False for phase in state["phases"].values())
    assert state["phases"]["frame"]["ready"] is True
    assert state["phase_review_history"] == []
    assert state["items"]["n_harm"]["approved"] is False
    events = read_project(case)["events"]
    assert len(events) == 37
    assert all(event["kind"] == "item_put" and event["actor"] == "agent:d101_controller" for event in events)
    before = (case / "organon.json").read_bytes()
    revision = state["revision"]
    again = asyncio.run(recipe.execute(directory, cli=CLI))
    assert again["result"]["applied"] == 0 and again["result"]["skipped"] == 37
    assert (case / "organon.json").read_bytes() == before
    assert engine.get_state(case)["revision"] == revision


def test_cli_uses_sealed_audited_manifest_when_disk_manifest_changes_at_launch(prepared, monkeypatch):
    directory, _ = prepared
    path = directory / "manifest.json"
    audited = _load(path)
    real_cli = recipe._cli
    launched = []

    def mutate_before_run(executable, *args, pass_fds=()):
        if args[0] != "run":
            return real_cli(executable, *args, pass_fds=pass_fds)
        snapshot = args[args.index("--manifest") + 1]
        assert snapshot.startswith("/proc/self/fd/")
        fd = int(snapshot.rsplit("/", 1)[1])
        assert pass_fds == (fd,)
        assert _load(Path(snapshot)) == audited
        assert fcntl.fcntl(fd, getattr(fcntl, "F_GET_SEALS", 1034)) & 0x0F == 0x0F
        with pytest.raises(OSError) as sealed:
            os.pwrite(fd, b"0", 0)
        assert sealed.value.errno == errno.EPERM
        changed = copy.deepcopy(audited)
        item = next(step for step in changed["steps"] if step["id"] == "e_piece_mass")
        item["data"]["value"] = "737"
        _write(path, changed)
        assert _load(Path(snapshot)) == audited
        result = real_cli(executable, *args, pass_fds=pass_fds)
        launched.append(result)
        return result

    monkeypatch.setattr(recipe, "_cli", mutate_before_run)
    # Publication uses the approved snapshot; the final disk check still rejects
    # the changed local receipt, keeping the discrepancy visible to the caller.
    with pytest.raises(recipe.RecipeError, match="publication manifest differs"):
        asyncio.run(recipe.execute(directory, cli=CLI))
    assert len(launched) == 1
    assert launched[0]["status"] == "waiting" and launched[0]["applied"] == 37
    state = engine.get_state(directory / "case")
    published = state["items"]["e_piece_mass"]
    expected = next(step for step in audited["steps"] if step["id"] == "e_piece_mass")
    assert published["data"] == expected["data"]
    assert published["data"]["value"] == "736"
    assert all(phase["accepted"] is False for phase in state["phases"].values())


@pytest.mark.parametrize("verdict", ["accept", "reject"])
def test_item_review_in_partial_checkpoint_requires_explicit_recipe_revision(prepared, verdict):
    directory, _ = prepared
    case = directory / "case"
    manifest = _load(directory / "manifest.json")
    engine.create_case(case, recipe.TITLE, recipe.DOMAIN, recipe.ACTOR)
    for step in manifest["steps"][:3]:
        engine.put_item(case, step["id"], step["kind"], step["text"], step["refs"],
                        step["data"], recipe.ACTOR)
    engine.review_item(case, "b_seed", verdict, "Independent test of checkpoint admission",
                       "agent:test_reviewer")
    state = engine.get_state(case)
    assert state["revision"] == 4 < len(manifest["steps"])
    if verdict == "reject":
        assert any("rejected" in issue for issue in state["items"]["b_seed"]["issues"])
    before = (case / "organon.json").read_bytes()
    with pytest.raises(recipe.RecipeError, match="checkpoint events differ"):
        recipe.validate(directory)
    with pytest.raises(recipe.RecipeError):
        asyncio.run(recipe.execute(directory, cli=CLI))
    assert (case / "organon.json").read_bytes() == before


@pytest.mark.usefixtures("enable_fixture_policy")
@pytest.mark.parametrize("field,value", [
    ("approval_policy", "fixture"), ("title", "Different documentary case"),
    ("domain", "fixture"), ("actor", "agent:different_controller"),
    ("test_gate_policy", "signed_observed"),
])
def test_checkpoint_project_identity_must_match_signed_recipe(prepared, field, value):
    directory, _ = prepared
    case = directory / "case"
    identity = {"title": recipe.TITLE, "domain": recipe.DOMAIN, "actor": recipe.ACTOR,
                "approval_policy": "signed", "test_gate_policy": "signed_report"}
    identity[field] = value
    engine.create_case(case, **identity)
    before = (case / "organon.json").read_bytes()
    with pytest.raises(recipe.RecipeError, match="signed recipe identity"):
        recipe.validate(directory)
    with pytest.raises(recipe.RecipeError):
        asyncio.run(recipe.execute(directory, cli=CLI))
    assert (case / "organon.json").read_bytes() == before


@pytest.mark.parametrize("reported", [
    {},
    {"status": "waiting", "reason": "independent_review_required", "cursor": 37,
     "applied": 37, "skipped": 0},
])
def test_transport_response_without_actual_ledger_cannot_claim_publication(prepared, tmp_path, reported):
    directory, _ = prepared
    fake_cli = tmp_path / "fake-organon"
    fake_cli.write_text(f"#!{CLI.parent / 'python'}\nprint({json.dumps(reported)!r})\n",
                        encoding="utf-8")
    fake_cli.chmod(0o700)
    with pytest.raises(recipe.RecipeError, match="complete pending recipe checkpoint"):
        asyncio.run(recipe.execute(directory, cli=fake_cli))
    assert not _ledger_files(directory)
    assert recipe.validate(directory)["state"] == "prepared"


def test_archive_changed_at_run_leaves_retained_negative_checkpoint(prepared, monkeypatch):
    directory, _ = prepared
    case = directory / "case"
    real_cli = recipe._cli
    launched = []

    def alter_archive_before_run(executable, *args, pass_fds=()):
        if args[0] == "run":
            path = case / "source_lca.pdf"
            path.write_bytes(path.read_bytes() + b"concurrent local archive change")
            result = real_cli(executable, *args, pass_fds=pass_fds)
            launched.append(result)
            return result
        return real_cli(executable, *args, pass_fds=pass_fds)

    monkeypatch.setattr(recipe, "_cli", alter_archive_before_run)
    with pytest.raises(recipe.RecipeError, match="recipe archived bytes differ"):
        asyncio.run(recipe.execute(directory, cli=CLI))
    assert len(launched) == 1 and launched[0]["applied"] == 37
    state = engine.get_state(case)
    assert state["revision"] == 37
    assert state["items"]["e_piece_mass"]["data"]["value"] == "736"
    assert any("local archive" in issue for issue in state["items"]["e_piece_mass"]["issues"])
    assert any("local archive" in issue for issue in state["items"]["p_refined"]["issues"])
    assert state["phases"]["frame"]["ready"] is False
    assert all(phase["accepted"] is False for phase in state["phases"].values())
    assert state["phase_review_history"] == []
    assert all(event["kind"] == "item_put" for event in read_project(case)["events"])
    with pytest.raises(recipe.RecipeError):
        recipe.validate(directory)


@pytest.mark.parametrize("archive", ["source_lca.pdf", "source_survey.pdf", "survey_table1.json"])
def test_engine_source_invalidity_reaches_actual_dependents(prepared, archive):
    directory, _ = prepared
    asyncio.run(recipe.execute(directory, cli=CLI))
    case = directory / "case"
    before = engine.get_state(case)
    path = case / archive
    path.write_bytes(path.read_bytes() + b"altered public source")
    after = engine.get_state(case)
    direct = {
        id for id, item in before["items"].items()
        if item["kind"] == "evidence" and item["data"].get("archive") == archive
    }
    assert direct
    affected = set(direct)
    for _ in range(len(before["items"])):
        affected |= {
            id for id, item in before["items"].items()
            if set(item["deps"]) & affected
        }
    for id in affected:
        issues = after["items"][id]["issues"]
        assert any("local archive" in issue for issue in issues), (id, issues)
    for id in before["items"].keys() - affected:
        assert after["items"][id]["issues"] == before["items"][id]["issues"], id
    assert after["revision"] == before["revision"]
    assert after["phases"]["frame"]["accepted"] is False
    with pytest.raises(recipe.RecipeError):
        recipe.validate(directory)


def test_revised_checkpoint_is_rejected_without_overwrite(prepared):
    directory, _ = prepared
    asyncio.run(recipe.execute(directory, cli=CLI))
    case = directory / "case"
    item = engine.get_state(case)["items"]["s_historical"]
    engine.put_item(case, item["id"], item["kind"], "Explicit divergent historical assumption",
                    list(item["deps"]), item["data"], "agent:test_researcher")
    before = (case / "organon.json").read_bytes()
    with pytest.raises(recipe.RecipeError):
        recipe.validate(directory)
    with pytest.raises(recipe.RecipeError):
        asyncio.run(recipe.execute(directory, cli=CLI))
    assert (case / "organon.json").read_bytes() == before
