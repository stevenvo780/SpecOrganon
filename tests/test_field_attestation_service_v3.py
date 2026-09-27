"""Synthetic attestation controls for the declared service denominator ceiling."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from specorganon import field_attestation
from specorganon.field_guardrails import canonical_sha256
from test_field_attestation import _write_json
from test_field_attestation_service_v2 import _read, _refresh_declarations, _schema2_bundle


def _schema3_bundle(tmp_path: Path) -> tuple[dict, dict]:
    project, report = _schema2_bundle(tmp_path)
    manifest = _read(tmp_path / "manifest.json")
    plan = _read(tmp_path / "plan.json")
    field = _read(tmp_path / "field.json")
    registry = _read(tmp_path / "registry.json")
    measurements = _read(tmp_path / "measurements.json")
    service = field["service"]
    service["schema"] = 3
    rules = [
        {"id": "raw", "material_id": "synthetic-food", "classification": "eligible",
         "basis": "Synthetic declared ceiling, not physical feasibility",
         "max_service_per_kg": 0.9},
        {"id": "ingredient", "material_id": "synthetic-inedible",
         "classification": "unsuitable", "basis": "Synthetic exclusion",
         "max_service_per_kg": 0},
        {"id": "water", "material_id": "synthetic-water",
         "classification": "water", "basis": "Added water is excluded",
         "max_service_per_kg": 0},
    ]
    service["equivalence"]["denominator_rules"] = rules
    approval_path = tmp_path / "synthetic_approval_record.json"
    approval = _read(approval_path)
    approval["records"][0]["denominator_rules"] = rules
    approval_raw = _write_json(approval_path, approval)
    approval_digest = hashlib.sha256(approval_raw).hexdigest()
    service["equivalence"]["record_sha256"] = approval_digest
    next(item for item in manifest["sources"] if item["role"] == "approval_record")[
        "sha256"] = approval_digest

    flows = {flow["id"]: flow for flow in field["flows"]}
    source_path = tmp_path / "synthetic_source_record.json"
    source = _read(source_path)
    records = {(item["group_id"], item["period"]): item for item in source["records"]
               if item["kind"] == "service_row"}
    for row in service["rows"]:
        prefix = f"{row['group_id']}-{row['period']}"
        row["feasible_max_service"]["uncertainty"] = 0.09
        record = records[(row["group_id"], row["period"])]
        record["feasible_max_service"]["uncertainty"] = 0.09
        row["denominator_inputs"] = []
        record["denominator_inputs"] = []
        for suffix, rule_id, material_id in (
            ("raw", "raw", "synthetic-food"),
            ("ingredient", "ingredient", "synthetic-inedible"),
            ("water", "water", "synthetic-water"),
        ):
            flow = flows[f"{prefix}-{suffix}"]
            flow["material_id"] = material_id
            row["denominator_inputs"].append({"input_flow_id": flow["id"],
                                               "rule_id": rule_id})
            record["denominator_inputs"].append({
                "input_flow_id": flow["id"], "material_id": material_id,
                "rule_id": rule_id, "mass": flow["mass"],
            })
    source_raw = _write_json(source_path, source)
    source_digest = hashlib.sha256(source_raw).hexdigest()
    next(item for item in manifest["sources"] if item["role"] == "source_record")[
        "sha256"] = source_digest
    plan["allocation_record_sha256"] = source_digest
    registry["plan_sha256"] = canonical_sha256(plan)
    measurements["registry_sha256"] = canonical_sha256(registry)
    for row in measurements["rows"]:
        row["source"]["record_sha256"] = source_digest
    for row in service["rows"]:
        row["source"]["record_sha256"] = source_digest
    for role, value in (("plan", plan), ("field", field), ("registry", registry),
                        ("measurements", measurements)):
        _write_json(tmp_path / f"{role}.json", value)
    _refresh_declarations(tmp_path, manifest, report)
    return project, report


def test_schema3_denominator_bytes_are_in_signed_attestation_message(tmp_path: Path) -> None:
    project, _ = _schema3_bundle(tmp_path)
    materials = field_attestation.inspect_materials(
        project, "ass1", 1, "cumplido", str(tmp_path / "manifest.json"),
        str(tmp_path / "report.json"),
    )
    assert materials["service_denominator_rule_approval_byte_bound"] is True
    assert materials["service_denominator_input_byte_bound"] is True
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    binding = {"assessment_id": "ass1", "assessment_version": 1, "verdict": "cumplido",
               "items": [{"id": "ass1", "version": 1, "sha256": "a" * 64}]}
    actor = "assessor:synthetic"
    reason = "Synthetic denominator binding only"
    head = "b" * 64
    challenge = field_attestation.challenge(project, tmp_path, binding, materials,
                                            actor, reason, head)
    signed_payload = json.loads(base64.b64decode(challenge["message_base64"]))
    assert signed_payload["materials"]["service_denominator_input_byte_bound"] is True
    signature = base64.b64encode(key.sign(base64.b64decode(challenge["message_base64"]))).decode()
    assert field_attestation.verify(project, tmp_path, binding, materials, actor, reason,
                                    head, signature, hashlib.sha256(public).hexdigest(),
                                    {actor: public})
    changed_materials = {**materials, "service_denominator_input_byte_bound": False}
    assert not field_attestation.verify(project, tmp_path, binding, changed_materials,
                                        actor, reason, head, signature,
                                        hashlib.sha256(public).hexdigest(), {actor: public})


def test_rehashed_field_rule_basis_without_opened_approval_bytes_fails_closed(
    tmp_path: Path,
) -> None:
    project, report = _schema3_bundle(tmp_path)
    field = _read(tmp_path / "field.json")
    field["service"]["equivalence"]["denominator_rules"][0]["basis"] = "changed"
    _write_json(tmp_path / "field.json", field)
    _refresh_declarations(tmp_path, _read(tmp_path / "manifest.json"), report)
    with pytest.raises(field_attestation.FieldAttestationError,
                       match="primary source content differs from declarations"):
        field_attestation.inspect_materials(
            project, "ass1", 1, "cumplido", str(tmp_path / "manifest.json"),
            str(tmp_path / "report.json"),
        )


def test_coordinated_denominator_and_coefficient_inflation_needs_new_approval_bytes(
    tmp_path: Path,
) -> None:
    project, report = _schema3_bundle(tmp_path)
    field = _read(tmp_path / "field.json")
    field["service"]["equivalence"]["denominator_rules"][0][
        "max_service_per_kg"] = 9000
    for row in field["service"]["rows"]:
        row["feasible_max_service"]["value"] = 900000
        row["feasible_max_service"]["uncertainty"] = 900
    _write_json(tmp_path / "field.json", field)
    _refresh_declarations(tmp_path, _read(tmp_path / "manifest.json"), report)
    with pytest.raises(field_attestation.FieldAttestationError,
                       match="primary source content differs from declarations"):
        field_attestation.inspect_materials(
            project, "ass1", 1, "cumplido", str(tmp_path / "manifest.json"),
            str(tmp_path / "report.json"),
        )
