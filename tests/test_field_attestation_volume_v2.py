"""Synthetic attestation controls for opened baseline input-volume extracts."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from specorganon import engine, field_attestation
from specorganon.field_guardrails import canonical_sha256
from specorganon.field_source_content_audit import audit_field_source_content
from specorganon.field_source_digest_audit import audit_field_source_digest_coverage
from specorganon.ledger import append_event, read_project
from test_approval_security import _sign, _signed_field_case
from test_field_attestation import _bundle, _write_json
from test_field_attestation_service_v2 import _read, _refresh_declarations, _schema2_bundle
from test_field_effect_analysis_v2 import _recomputed_case


def _refresh_analysis(tmp_path: Path, manifest: dict, report: dict) -> None:
    raw = _write_json(tmp_path / "analysis.json", _read(tmp_path / "analysis.json"))
    digest = hashlib.sha256(raw).hexdigest()
    next(source for source in manifest["sources"] if source["role"] == "analysis")[
        "sha256"
    ] = digest
    report["analysis_sha256"] = digest
    _refresh_declarations(tmp_path, manifest, report)


def _bound_bundle(
    tmp_path: Path, *, service_schema2: bool = False, project: dict | None = None,
) -> tuple[dict, dict]:
    if service_schema2:
        generated_project, report = _schema2_bundle(tmp_path)
        project = generated_project if project is None else project
        report["case_id"] = project["case_id"]
    else:
        if project is None:
            project = {"case_id": str(uuid.uuid4()), "approval_policy": "signed"}
        _, _, report = _bundle(tmp_path, project)
    plan = _read(tmp_path / "plan.json")
    field = _read(tmp_path / "field.json")
    analysis = _recomputed_case()[4]
    spec = analysis["candidate_spec"]
    spec["plan_sha256"] = canonical_sha256(plan)
    spec["service"]["equivalence_record_sha256"] = field["service"]["equivalence"][
        "record_sha256"
    ]
    volume = analysis["baseline_input_volume_manifest"]
    volume["plan_sha256"] = canonical_sha256(plan)
    volume["candidate_spec_sha256"] = canonical_sha256(spec)
    records = []
    for row in volume["rows"]:
        records.append({
            "kind": "volume_row",
            "study_id": volume["study_id"],
            "definition_sha256": volume["definition_sha256"],
            "group_id": row["group_id"],
            "period": row["period"],
            "value": row["value"],
            "unit": row["unit"],
            "window_start_utc": row["window_start_utc"],
            "window_end_utc": row["window_end_utc"],
            "source": {key: row["source"][key]
                       for key in ("locator", "observed_at_utc", "method")},
        })
    volume_path = tmp_path / "synthetic_volume_source_record.json"
    raw = _write_json(volume_path, {
        "schema": 1,
        "classification": "field_primary_source_content_extract",
        "records": records,
    })
    volume_digest = hashlib.sha256(raw).hexdigest()
    for row in volume["rows"]:
        row["source"]["record_sha256"] = volume_digest
    volume["candidate_spec_sha256"] = canonical_sha256(spec)
    _write_json(tmp_path / "analysis.json", analysis)
    manifest = _read(tmp_path / "manifest.json")
    manifest["sources"].append({
        "role": "source_record", "path": str(volume_path), "sha256": volume_digest,
    })
    _refresh_analysis(tmp_path, manifest, report)
    return project, report


def _inspect(tmp_path: Path, project: dict) -> dict:
    return field_attestation.inspect_materials(
        project, "ass1", 1, "cumplido", str(tmp_path / "manifest.json"),
        str(tmp_path / "report.json"),
    )


def _signed_volume_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Ed25519PrivateKey, str, str, dict]:
    owner_key = Ed25519PrivateKey.generate()
    approval_registry = tmp_path / "trusted-approvers.json"
    _write_json(approval_registry, {"schema": 2, "cases": {}})
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(approval_registry))
    case, _ = _signed_field_case(tmp_path, (owner_key, approval_registry))
    state = engine.get_state(case)

    assessor = "assessor:independent"
    assessor_key = Ed25519PrivateKey.generate()
    public = assessor_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    assessor_registry = tmp_path / "independent-assessors.json"
    _write_json(assessor_registry, {"schema": 1, "cases": {
        state["project"]["case_id"]: {
            "path": str(case.resolve(strict=True)),
            "project_sha256": state["project_sha256"],
            "assessors": {assessor: base64.b64encode(public).decode("ascii")},
        },
    }})
    monkeypatch.setenv("ORGANON_FIELD_ASSESSORS_FILE", str(assessor_registry))

    bundle_dir = tmp_path / "bound-volume-bundle"
    bundle_dir.mkdir()
    project, _ = _bound_bundle(bundle_dir, project=state["project"])
    assert project["case_id"] == engine.get_state(case)["project"]["case_id"]
    field_args = {
        "path": str(case), "id": "ass1",
        "reason": "Synthetic volume-binding regression; no real field effect established",
        "actor": assessor,
        "source_manifest_path": str(bundle_dir / "manifest.json"),
        "report_path": str(bundle_dir / "report.json"),
    }
    return case, assessor_key, assessor, hashlib.sha256(public).hexdigest(), field_args


@pytest.mark.parametrize("service_schema2", [False, True])
def test_attestation_binds_volume_extract_with_either_service_schema(
    tmp_path: Path, service_schema2: bool,
) -> None:
    project, _ = _bound_bundle(tmp_path, service_schema2=service_schema2)
    result = _inspect(tmp_path, project)
    assert "source_coverage_sha256" in result
    assert "source_content_sha256" in result
    assert result["baseline_volume_input_byte_bound"] is True
    assert "analysis_preflight_sha256" in result


def test_rehashing_analysis_cannot_hide_changed_volume_value(tmp_path: Path) -> None:
    project, report = _bound_bundle(tmp_path)
    analysis = _read(tmp_path / "analysis.json")
    analysis["baseline_input_volume_manifest"]["rows"][0]["value"] += 1
    _write_json(tmp_path / "analysis.json", analysis)
    manifest = _read(tmp_path / "manifest.json")
    _refresh_analysis(tmp_path, manifest, report)
    with pytest.raises(field_attestation.FieldAttestationError,
                       match="primary source content differs from declarations"):
        _inspect(tmp_path, project)


def test_rehashing_source_and_all_outer_links_cannot_hide_volume_mismatch(
    tmp_path: Path,
) -> None:
    project, report = _bound_bundle(tmp_path)
    volume_path = tmp_path / "synthetic_volume_source_record.json"
    extract = _read(volume_path)
    extract["records"][0]["value"] += 1
    new_digest = hashlib.sha256(_write_json(volume_path, extract)).hexdigest()
    analysis = _read(tmp_path / "analysis.json")
    for row in analysis["baseline_input_volume_manifest"]["rows"]:
        row["source"]["record_sha256"] = new_digest
    _write_json(tmp_path / "analysis.json", analysis)
    manifest = _read(tmp_path / "manifest.json")
    next(source for source in manifest["sources"]
         if source["path"] == str(volume_path))["sha256"] = new_digest
    _refresh_analysis(tmp_path, manifest, report)
    with pytest.raises(field_attestation.FieldAttestationError,
                       match="primary source content differs from declarations"):
        _inspect(tmp_path, project)


@pytest.mark.parametrize("change", ["missing", "wrong_role", "extra", "duplicate"])
def test_volume_digest_coverage_rejects_rehashed_manifest_tampering(
    tmp_path: Path, change: str,
) -> None:
    project, report = _bound_bundle(tmp_path)
    manifest = _read(tmp_path / "manifest.json")
    source = next(item for item in manifest["sources"]
                  if item["path"] == str(tmp_path / "synthetic_volume_source_record.json"))
    if change == "missing":
        manifest["sources"].remove(source)
    elif change == "wrong_role":
        source["role"] = "approval_record"
    elif change == "extra":
        extra_path = tmp_path / "extra_primary_source_record.json"
        raw = _write_json(extra_path, {
            "schema": 1, "classification": "field_primary_source_content_extract",
            "records": [{"kind": "volume_row", "unexpected": "extra"}],
        })
        manifest["sources"].append({
            "role": "source_record", "path": str(extra_path),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    else:
        duplicate_path = tmp_path / "duplicate_volume_source_record.json"
        raw = (tmp_path / "synthetic_volume_source_record.json").read_bytes()
        duplicate_path.write_bytes(raw)
        manifest["sources"].append({
            "role": "source_record", "path": str(duplicate_path),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    _refresh_analysis(tmp_path, manifest, report)
    with pytest.raises(field_attestation.FieldAttestationError,
                       match="primary source digests lack exact manifest coverage"):
        _inspect(tmp_path, project)


def test_signed_engine_attestation_exposes_byte_bound_volume_but_keeps_field_gate_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, assessor_key, _, _, field_args = _signed_volume_case(tmp_path, monkeypatch)
    assert engine.get_state(case)["field_attestations"] == []

    challenge = engine.field_attestation_challenge(**field_args)
    signed_message = json.loads(base64.b64decode(challenge["message_base64"], validate=True))
    assert signed_message["case_id"] == engine.get_state(case)["project"]["case_id"]
    assert signed_message["materials"]["baseline_volume_input_byte_bound"] is True
    event = engine.attest_field(**field_args, signature=_sign(assessor_key, challenge))
    assert event["kind"] == "field_attestation"
    assert event["payload"]["materials"]["baseline_volume_input_byte_bound"] is True

    status = engine.get_state(case)
    assert status["field_attestations"] == [{
        "seq": event["seq"], "actor": field_args["actor"],
        "signature_verified": True, "baseline_volume_input_byte_bound": True,
        "binding_current": True, "assessment_id": "ass1",
    }]
    gate = engine.gate(case, "validate")
    assert gate["blockers"] == [
        "ass1 decisive field verdict needs verified field effect analysis and source custody"
    ]
    assert gate["ready"] is False and gate["accepted"] is False


def test_legacy_signed_field_event_verifies_without_claiming_volume_byte_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, assessor_key, assessor, key_sha256, field_args = _signed_volume_case(
        tmp_path, monkeypatch,
    )
    challenge = engine.field_attestation_challenge(**field_args)
    signed_message = json.loads(base64.b64decode(challenge["message_base64"], validate=True))
    bundle_dir = Path(field_args["source_manifest_path"]).parent
    manifest = _read(bundle_dir / "manifest.json")
    volume_path = bundle_dir / "synthetic_volume_source_record.json"
    manifest["sources"] = [source for source in manifest["sources"]
                           if source["path"] != str(volume_path)]
    volume_path.unlink()
    report = _read(bundle_dir / "report.json")
    _refresh_declarations(bundle_dir, manifest, report)

    # Before volume byte binding, schema-2 analysis still carried its declared
    # volume manifest, but the source audits did not receive that analysis.
    plan, field, registry, measurements = (
        _read(bundle_dir / f"{role}.json")
        for role in ("plan", "field", "registry", "measurements")
    )
    legacy_coverage = audit_field_source_digest_coverage(
        plan, field, registry, measurements,
        [{"role": source["role"], "sha256": source["sha256"]}
         for source in manifest["sources"]],
    )
    legacy_content = audit_field_source_content(
        plan, field, registry, measurements,
        [{"role": source["role"], "sha256": source["sha256"],
          "raw": Path(source["path"]).read_bytes()}
         for source in manifest["sources"]
         if source["role"] in {"source_record", "approval_record"}],
    )
    assert legacy_coverage["exact_primary_source_coverage"] is True
    assert legacy_content["exact_declared_content_match"] is True
    assert "baseline_volume_input_byte_bound" not in legacy_coverage
    assert "baseline_volume_input_byte_bound" not in legacy_content
    materials = dict(signed_message["materials"])
    assert materials.pop("baseline_volume_input_byte_bound") is True
    materials.update({
        "source_manifest_sha256": hashlib.sha256(
            (bundle_dir / "manifest.json").read_bytes()
        ).hexdigest(),
        "report_sha256": hashlib.sha256(
            (bundle_dir / "report.json").read_bytes()
        ).hexdigest(),
        "source_coverage_sha256": hashlib.sha256(
            field_attestation._canonical(legacy_coverage)
        ).hexdigest(),
        "source_content_sha256": hashlib.sha256(
            field_attestation._canonical(legacy_content)
        ).hexdigest(),
    })
    assert materials["source_coverage_sha256"] != signed_message["materials"]["source_coverage_sha256"]
    assert materials["source_content_sha256"] != signed_message["materials"]["source_content_sha256"]
    prior_state = engine.get_state(case)
    legacy_challenge = field_attestation.challenge(
        prior_state["project"], case, signed_message["binding"], materials,
        assessor, field_args["reason"], challenge["ledger_head_sha256"],
    )
    event = append_event(
        case, "field_attestation", {
            "binding": signed_message["binding"], "materials": materials,
            "reason": field_args["reason"],
            "signature": _sign(assessor_key, legacy_challenge),
            "key_sha256": key_sha256,
        }, assessor, expected_seq=prior_state["revision"],
    )
    assert read_project(case)["events"][-1] == event
    assert "baseline_volume_input_byte_bound" not in event["payload"]["materials"]

    status = engine.get_state(case)
    assert status["field_attestations"] == [{
        "seq": event["seq"], "actor": assessor,
        "signature_verified": True, "baseline_volume_input_byte_bound": False,
        "binding_current": True, "assessment_id": "ass1",
    }]
    gate = engine.gate(case, "validate")
    assert gate["blockers"] == [
        "ass1 decisive field verdict needs verified field effect analysis and source custody"
    ]
    assert gate["ready"] is False and gate["accepted"] is False
