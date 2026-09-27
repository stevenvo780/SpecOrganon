"""Synthetic controls for an independent field statement over exact source bytes."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from specorganon import approval, field_attestation
from specorganon.field_guardrails import audit_field_guardrails, canonical_sha256
from test_field_effect_analysis import _case as _synthetic_analysis_case


def _write_json(path: Path, value: dict) -> bytes:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(raw)
    return raw


def _bundle(tmp_path: Path, project: dict, *, assessment_version: int = 1) -> tuple[str, str, dict]:
    plan, field, registry, measurements, analysis = _synthetic_analysis_case()
    sources = []
    for role, value in (("plan", plan), ("field", field), ("registry", registry),
                        ("measurements", measurements),
                        ("analysis", analysis)):
        path = tmp_path / f"{role}.json"
        raw = _write_json(path, value)
        sources.append({"role": role, "path": str(path),
                        "sha256": hashlib.sha256(raw).hexdigest()})
    manifest_path = tmp_path / "manifest.json"
    manifest_raw = _write_json(manifest_path, {
        "schema": 1, "classification": field_attestation.MANIFEST_CLASSIFICATION,
        "sources": sources,
    })
    preflight = audit_field_guardrails(
        plan, field, registry, measurements,
        plan_sha256=canonical_sha256(plan), registry_sha256=canonical_sha256(registry),
    )
    assert preflight["structural_match_at_read"] is True
    report_path = tmp_path / "report.json"
    report = {
        "schema": 1, "classification": field_attestation.REPORT_CLASSIFICATION,
        "case_id": project["case_id"], "assessment_id": "ass1",
        "assessment_version": assessment_version, "verdict": "cumplido",
        "source_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "preflight_sha256": hashlib.sha256(field_attestation._canonical(preflight)).hexdigest(),
        "analysis_sha256": sources[-1]["sha256"],
        "source_custody": "Synthetic source files were opened and compared with this manifest.",
        "causal_attribution": "This is a synthetic fixture; no causal attribution to field work.",
        "value_metric": "The fixture does not establish a real value measure.",
        "harms_by_actor_stage": "The synthetic guardrail matrix is structurally complete only.",
        "costs": "The synthetic cost measurements have no verified source.",
        "uncertainty": "The synthetic interval is not a field estimate.",
        "limitations": "No person, field record or physical outcome was authenticated.",
        "conclusion": "cumplido",
    }
    _write_json(report_path, report)
    return str(manifest_path), str(report_path), report


def test_field_attestation_binds_sources_report_and_independent_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = {"case_id": str(uuid.uuid4()), "approval_policy": "signed"}
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
    )
    actor = "assessor:independent"
    registry_path = tmp_path / "assessors.json"
    registry = {"schema": 1, "cases": {project["case_id"]: {
        "path": str(tmp_path), "project_sha256": approval.project_fingerprint(project),
        "assessors": {actor: base64.b64encode(public).decode("ascii")},
    }}}
    _write_json(registry_path, registry)
    monkeypatch.setenv("ORGANON_FIELD_ASSESSORS_FILE", str(registry_path))
    assessors, status = field_attestation.trust_context(project, tmp_path)
    assert status == "configured" and assessors == {actor: public}

    manifest_path, report_path, _ = _bundle(tmp_path, project)
    materials = field_attestation.inspect_materials(
        project, "ass1", 1, "cumplido", manifest_path, report_path,
    )
    binding = {"assessment_id": "ass1", "assessment_version": 1, "verdict": "cumplido",
               "items": [{"id": "ass1", "version": 1, "sha256": "a" * 64}]}
    head = "b" * 64
    reason = "Independent synthetic test signature; no real field approval"
    challenge = field_attestation.challenge(
        project, tmp_path, binding, materials, actor, reason, head,
    )
    signature = base64.b64encode(key.sign(base64.b64decode(challenge["message_base64"]))).decode()
    fingerprint = hashlib.sha256(public).hexdigest()
    assert field_attestation.verify(
        project, tmp_path, binding, materials, actor, reason, head,
        signature, fingerprint, assessors,
    )
    assert not field_attestation.verify(
        project, tmp_path, binding, materials, actor, reason, "c" * 64,
        signature, fingerprint, assessors,
    )

    source_path = tmp_path / "analysis.json"
    source_path.write_bytes(source_path.read_bytes() + b" ")
    with pytest.raises(field_attestation.FieldAttestationError, match="source bytes differ"):
        field_attestation.inspect_materials(
            project, "ass1", 1, "cumplido", manifest_path, report_path,
        )
    _write_json(registry_path, {"schema": 1, "cases": {}})
    with pytest.raises(field_attestation.FieldAttestationError, match="not uniquely registered"):
        field_attestation.trust_context(project, tmp_path)


def test_rehashed_empty_analysis_is_rejected_before_signature(tmp_path: Path) -> None:
    project = {"case_id": str(uuid.uuid4()), "approval_policy": "signed"}
    manifest_path, report_path, report = _bundle(tmp_path, project)
    analysis_path = tmp_path / "analysis.json"
    analysis_raw = _write_json(analysis_path, {})
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    source = next(source for source in manifest["sources"] if source["role"] == "analysis")
    source["sha256"] = hashlib.sha256(analysis_raw).hexdigest()
    manifest_raw = _write_json(Path(manifest_path), manifest)
    report["analysis_sha256"] = source["sha256"]
    report["source_manifest_sha256"] = hashlib.sha256(manifest_raw).hexdigest()
    for name in field_attestation.REPORT_REVIEWS:
        if name != "conclusion":
            report[name] = "x"
    _write_json(Path(report_path), report)
    with pytest.raises(field_attestation.FieldAttestationError,
                       match="field effect analysis preflight failed"):
        field_attestation.inspect_materials(
            project, "ass1", 1, "cumplido", manifest_path, report_path,
        )
