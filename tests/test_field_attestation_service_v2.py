"""Synthetic attestation checks for byte-bound schema-2 service inputs."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import pytest

from specorganon import field_attestation
from specorganon.field_effect_analysis import audit_field_effect_analysis
from specorganon.field_guardrails import audit_field_guardrails, canonical_sha256
from test_field_attestation import _bundle, _write_json
from test_field_effect_analysis_v2 import _recomputed_case


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _refresh_declarations(tmp_path: Path, manifest: dict, report: dict) -> None:
    """Rewrite all changed declared bytes, including the assessor's outer hashes."""
    plan = _read(tmp_path / "plan.json")
    field = _read(tmp_path / "field.json")
    registry = _read(tmp_path / "registry.json")
    measurements = _read(tmp_path / "measurements.json")
    for role, value in (("plan", plan), ("field", field), ("registry", registry),
                        ("measurements", measurements)):
        raw = _write_json(tmp_path / f"{role}.json", value)
        entry = next(source for source in manifest["sources"] if source["role"] == role)
        entry["sha256"] = hashlib.sha256(raw).hexdigest()
    manifest_raw = _write_json(tmp_path / "manifest.json", manifest)
    report["source_manifest_sha256"] = hashlib.sha256(manifest_raw).hexdigest()
    preflight = audit_field_guardrails(
        plan, field, registry, measurements,
        plan_sha256=canonical_sha256(plan), registry_sha256=canonical_sha256(registry),
    )
    assert preflight["structural_match_at_read"] is True
    report["preflight_sha256"] = hashlib.sha256(
        field_attestation._canonical(preflight)
    ).hexdigest()
    _write_json(tmp_path / "report.json", report)


def _schema2_bundle(tmp_path: Path) -> tuple[dict, dict]:
    project = {"case_id": str(uuid.uuid4()), "approval_policy": "signed"}
    _, _, report = _bundle(tmp_path, project)
    manifest = _read(tmp_path / "manifest.json")
    plan = _read(tmp_path / "plan.json")
    field = _read(tmp_path / "field.json")
    registry = _read(tmp_path / "registry.json")
    measurements = _read(tmp_path / "measurements.json")
    source_path = tmp_path / "synthetic_source_record.json"
    extract = _read(source_path)

    field["service"]["schema"] = 2
    for row in field["service"]["rows"]:
        extract["records"].append({
            "kind": "service_row",
            "group_id": row["group_id"],
            "period": row["period"],
            "consumption_flow_ids": row["consumption_flow_ids"],
            "consumed_service": row["consumed_service"],
            "feasible_max_service": row["feasible_max_service"],
            "equivalence_id": field["service"]["equivalence"]["id"],
            "source": row["source"].copy(),
        })
    source_raw = _write_json(source_path, extract)
    source_sha256 = hashlib.sha256(source_raw).hexdigest()
    plan["allocation_record_sha256"] = source_sha256
    registry["plan_sha256"] = canonical_sha256(plan)
    measurements["registry_sha256"] = canonical_sha256(registry)
    for row in measurements["rows"]:
        row["source"]["record_sha256"] = source_sha256
    for row in field["service"]["rows"]:
        row["source"]["record_sha256"] = source_sha256

    for role, value in (("plan", plan), ("field", field), ("registry", registry),
                        ("measurements", measurements)):
        _write_json(tmp_path / f"{role}.json", value)
    source_entry = next(source for source in manifest["sources"]
                        if source["path"] == str(source_path))
    source_entry["sha256"] = source_sha256
    _refresh_declarations(tmp_path, manifest, report)
    return project, report


def test_schema2_service_rows_are_checked_against_opened_attestation_sources(
    tmp_path: Path,
) -> None:
    project, _ = _schema2_bundle(tmp_path)
    source = _read(tmp_path / "synthetic_source_record.json")
    assert sum(record["kind"] == "service_row" for record in source["records"]) == 24
    materials = field_attestation.inspect_materials(
        project, "ass1", 1, "cumplido", str(tmp_path / "manifest.json"),
        str(tmp_path / "report.json"),
    )
    assert "source_content_sha256" in materials
    assert "analysis_preflight_sha256" in materials


def test_schema2_service_extract_and_adjusted_candidate_share_attestation_bundle(
    tmp_path: Path,
) -> None:
    project, report = _schema2_bundle(tmp_path)
    plan = _read(tmp_path / "plan.json")
    field = _read(tmp_path / "field.json")
    registry = _read(tmp_path / "registry.json")
    measurements = _read(tmp_path / "measurements.json")
    analysis = _recomputed_case()[4]
    spec = analysis["candidate_spec"]
    spec["plan_sha256"] = canonical_sha256(plan)
    spec["service"]["equivalence_record_sha256"] = field["service"]["equivalence"][
        "record_sha256"
    ]
    volume = analysis["baseline_input_volume_manifest"]
    volume["plan_sha256"] = canonical_sha256(plan)
    volume["candidate_spec_sha256"] = canonical_sha256(spec)
    computed = audit_field_effect_analysis(plan, field, registry, measurements, analysis)
    assert computed["decision_ready"] is False
    assert computed["adjusted_effect_computed_candidate"]["input_volume_source_authenticated"] is False

    analysis_raw = _write_json(tmp_path / "analysis.json", analysis)
    analysis_sha256 = hashlib.sha256(analysis_raw).hexdigest()
    manifest = _read(tmp_path / "manifest.json")
    analysis_entry = next(source for source in manifest["sources"]
                          if source["role"] == "analysis")
    analysis_entry["sha256"] = analysis_sha256
    report["analysis_sha256"] = analysis_sha256
    _refresh_declarations(tmp_path, manifest, report)
    materials = field_attestation.inspect_materials(
        project, "ass1", 1, "cumplido", str(tmp_path / "manifest.json"),
        str(tmp_path / "report.json"),
    )
    assert materials["analysis_preflight_sha256"] == hashlib.sha256(
        field_attestation._canonical(computed)
    ).hexdigest()


@pytest.mark.parametrize("metric", ["consumed_service", "feasible_max_service"])
def test_rehashing_attestation_cannot_hide_changed_schema2_service_input(
    tmp_path: Path, metric: str,
) -> None:
    project, report = _schema2_bundle(tmp_path)
    field = _read(tmp_path / "field.json")
    field["service"]["rows"][0][metric]["value"] += 1
    _write_json(tmp_path / "field.json", field)
    manifest = _read(tmp_path / "manifest.json")
    _refresh_declarations(tmp_path, manifest, report)

    with pytest.raises(field_attestation.FieldAttestationError,
                       match="primary source content differs from declarations"):
        field_attestation.inspect_materials(
            project, "ass1", 1, "cumplido", str(tmp_path / "manifest.json"),
            str(tmp_path / "report.json"),
        )
