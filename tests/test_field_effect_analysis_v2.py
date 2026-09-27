"""Recomputed adjusted field candidate stays nondecisive in the five-file auditor."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from specorganon.field_adjusted_candidate import (
    INTERVAL,
    MANIFEST_CLASSIFICATION,
    MODEL,
    RESAMPLING,
    RNG,
    SPEC_CLASSIFICATION,
)
from specorganon.field_effect_analysis import (
    RECOMPUTED_CLASSIFICATION,
    FieldEffectAnalysisError,
    audit_field_effect_analysis,
)
from specorganon.field_guardrails import canonical_sha256
from test_field_effect_analysis import _case


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_field_effect_analysis.py"


def _recomputed_case() -> tuple[dict, dict, dict, dict, dict]:
    plan, field, registry, measurements, analysis = _case()
    definition = "All eligible input received by the assigned group during the complete pre window."
    volume_unit = "kg_eligible_input"
    definition_sha256 = canonical_sha256({"unit": volume_unit, "definition": definition})
    spec = {
        "schema": 1,
        "classification": SPEC_CLASSIFICATION,
        "study_id": plan["study_id"],
        "plan_sha256": canonical_sha256(plan),
        "registered_at_utc": plan["registered_at_utc"],
        "service": {
            "unit": field["service"]["equivalence"]["service_unit"],
            "equivalence_record_sha256": field["service"]["equivalence"]["record_sha256"],
        },
        "baseline_input_volume": {
            "unit": volume_unit,
            "definition": definition,
            "definition_sha256": definition_sha256,
        },
        "estimator": {
            "outcome": "post_minus_pre_v",
            "model": MODEL,
            "group_weight": "equal",
            "denominator": "one_minus_intervention_pre_mean_v",
        },
        "bootstrap": {
            "resampling": RESAMPLING,
            "rng": RNG,
            "seed": 17,
            "draws": 40,
            "interval": INTERVAL,
            "confidence_level": 0.95,
        },
    }
    pre = next(period for period in plan["periods"] if period["id"] == "pre")
    rows = []
    for group in field["groups"]:
        group_id = group["id"]
        locator = f"synthetic-volume/{group_id}"
        rows.append({
            "group_id": group_id,
            "period": "pre",
            "value": 100 + 10 * int(group_id[1:]) + (group_id.startswith("i") * 50),
            "unit": volume_unit,
            "window_start_utc": pre["start_utc"],
            "window_end_utc": pre["end_utc"],
            "source": {
                "record_sha256": hashlib.sha256(locator.encode()).hexdigest(),
                "locator": locator,
                "observed_at_utc": "2026-01-31T12:00:00Z",
                "method": "synthetic aggregate",
            },
        })
    volume_manifest = {
        "schema": 1,
        "classification": MANIFEST_CLASSIFICATION,
        "study_id": plan["study_id"],
        "plan_sha256": canonical_sha256(plan),
        "candidate_spec_sha256": canonical_sha256(spec),
        "unit": volume_unit,
        "definition_sha256": definition_sha256,
        "rows": rows,
    }
    analysis["schema"] = 2
    analysis["classification"] = RECOMPUTED_CLASSIFICATION
    del analysis["adjusted_effect"]
    analysis["candidate_spec"] = spec
    analysis["baseline_input_volume_manifest"] = volume_manifest
    return plan, field, registry, measurements, analysis


def test_v2_recomputes_adjusted_g_without_opening_field_decision() -> None:
    result = audit_field_effect_analysis(*_recomputed_case())
    assert result["schema"] == 2
    assert result["classification"] == "field_effect_arithmetic_adjusted_candidate_development"
    assert result["unadjusted_g_fraction"] == "1/2"
    computed = result["adjusted_effect_computed_candidate"]
    assert abs(float(computed["candidate_point"]["g_adjusted"]) - 0.5) < 1e-12
    assert computed["candidate_interval"]["bounds"] is None
    assert computed["candidate_interval"]["undefined_reason"]
    assert computed["diagnostics"]["bootstrap"]["draws_requested"] == 40
    assert computed["input_volume_source_authenticated"] is False
    assert result["decision_ready"] is False
    assert result["criterion_3"]["status"] == "not_assessed"


def test_v2_rejects_missing_volume_and_legacy_adjusted_claim() -> None:
    case = _recomputed_case()
    case[4]["baseline_input_volume_manifest"]["rows"].pop()
    with pytest.raises(FieldEffectAnalysisError, match="exactly one preassignment aggregate"):
        audit_field_effect_analysis(*case)

    case = _recomputed_case()
    case[4]["adjusted_effect"] = {"estimate": 999}
    with pytest.raises(FieldEffectAnalysisError, match="must have exactly"):
        audit_field_effect_analysis(*case)


def test_v2_five_file_cli_recomputes_the_same_candidate(tmp_path: Path) -> None:
    case = _recomputed_case()
    paths = []
    for name, value in zip(("plan", "field", "registry", "measurements", "analysis"), case,
                           strict=True):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        paths.append(str(path))
    result = subprocess.run([sys.executable, str(SCRIPT), *paths],
                            text=True, capture_output=True, check=True)
    assert json.loads(result.stdout) == audit_field_effect_analysis(*case)
    assert result.stderr == ""
