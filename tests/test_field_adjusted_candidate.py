"""Synthetic adjusted ITT G candidate checks; none represents site evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from specorganon.field_adjusted_candidate import (
    INTERVAL,
    MANIFEST_CLASSIFICATION,
    MODEL,
    REPORT_CLASSIFICATION,
    RESAMPLING,
    RNG,
    SPEC_CLASSIFICATION,
    FieldAdjustedCandidateError,
    analyze_field_adjusted_candidate,
)
from specorganon.field_guardrails import canonical_sha256
from test_audit_field_trial_design import _plan, _twelve_group_field


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "analyze_field_adjusted_candidate.py"


def _case(*, draws: int = 400) -> tuple[dict, dict, dict, dict]:
    field = _twelve_group_field()
    for group in field["groups"]:
        if int(group["id"][1:]) > 3:
            group["stratum"] = "S2"
    plan = _plan(field)
    volumes = {f"c{i}": 80 + 10 * i for i in range(1, 7)}
    volumes.update({f"i{i}": 160 + 10 * i for i in range(1, 7)})
    log_center = sum(math.log(volume) for volume in volumes.values()) / len(volumes)
    groups = {group["id"]: group for group in field["groups"]}
    for row in field["service"]["rows"]:
        group = groups[row["group_id"]]
        row["feasible_max_service"]["value"] = 90
        if row["period"] == "pre":
            row["consumed_service"]["value"] = 45
        else:
            delta = (0.05 + 0.10 * (group["arm"] == "intervention")
                     + 0.02 * (group["stratum"] == "S2")
                     + 0.05 * (math.log(volumes[group["id"]]) - log_center))
            row["consumed_service"]["value"] = 90 * (0.5 + delta)
    definition = "Sum of eligible input mass received during the complete pre window, per assigned operational group."
    unit = "kg_eligible_input"
    definition_sha256 = canonical_sha256({"unit": unit, "definition": definition})
    spec = {
        "schema": 1, "classification": SPEC_CLASSIFICATION,
        "study_id": plan["study_id"], "plan_sha256": canonical_sha256(plan),
        "registered_at_utc": plan["registered_at_utc"],
        "service": {
            "unit": field["service"]["equivalence"]["service_unit"],
            "equivalence_record_sha256": field["service"]["equivalence"]["record_sha256"],
        },
        "baseline_input_volume": {
            "unit": unit, "definition": definition, "definition_sha256": definition_sha256,
        },
        "estimator": {
            "outcome": "post_minus_pre_v", "model": MODEL, "group_weight": "equal",
            "denominator": "one_minus_intervention_pre_mean_v",
        },
        "bootstrap": {
            "resampling": RESAMPLING, "rng": RNG, "seed": 1776, "draws": draws,
            "interval": INTERVAL, "confidence_level": 0.95,
        },
    }
    pre = next(period for period in plan["periods"] if period["id"] == "pre")
    rows = []
    for group_id, volume in volumes.items():
        locator = f"synthetic-volume/{group_id}"
        rows.append({
            "group_id": group_id, "period": "pre", "value": volume, "unit": unit,
            "window_start_utc": pre["start_utc"], "window_end_utc": pre["end_utc"],
            "source": {
                "record_sha256": hashlib.sha256(locator.encode()).hexdigest(),
                "locator": locator, "observed_at_utc": "2026-01-31T12:00:00Z",
                "method": "synthetic complete pre-window aggregation",
            },
        })
    manifest = {
        "schema": 1, "classification": MANIFEST_CLASSIFICATION,
        "study_id": plan["study_id"], "plan_sha256": canonical_sha256(plan),
        "candidate_spec_sha256": canonical_sha256(spec),
        "unit": unit, "definition_sha256": definition_sha256, "rows": rows,
    }
    return plan, field, spec, manifest


def _rebind(case: tuple[dict, dict, dict, dict]) -> None:
    plan, _field, spec, manifest = case
    spec["plan_sha256"] = canonical_sha256(plan)
    manifest["plan_sha256"] = canonical_sha256(plan)
    manifest["candidate_spec_sha256"] = canonical_sha256(spec)


def test_known_effect_with_volume_imbalance_and_reproducible_bootstrap() -> None:
    case = _case()
    report = analyze_field_adjusted_candidate(*case)
    repeated = analyze_field_adjusted_candidate(*case)
    assert report == repeated
    assert report["classification"] == REPORT_CLASSIFICATION
    assert abs(float(report["candidate_point"]["tau_adjusted_change"]) - 0.10) < 1e-12
    assert abs(float(report["candidate_point"]["g_adjusted"]) - 0.20) < 1e-12
    assert report["candidate_point"]["one_minus_intervention_pre_mean_v_fraction"] == "1/2"
    bounds = report["candidate_interval"]["bounds"]
    assert bounds is not None and len(bounds) == 2
    assert float(bounds[0]) <= float(bounds[1])
    assert report["candidate_interval"]["nominal_only"]
    assert not report["candidate_interval"]["calibrated_for_design"]
    assert report["diagnostics"]["residual_degrees_of_freedom"] == 8
    assert report["diagnostics"]["bootstrap"]["draws_requested"] == 400
    assert report["diagnostics"]["bootstrap"]["valid_draws"] > 0
    assert report["criterion_3"]["status"] == "not_assessed"
    assert report["decision_ready"] is False
    for key in (
        "registration_authenticated", "randomization_verified", "source_records_authenticated",
        "input_volume_source_authenticated", "complete_measurement_coverage_verified",
        "service_calibration_verified", "confidence_interval_calibrated",
    ):
        assert report[key] is False
    # The raw arm contrast is biased upward by the deliberately imbalanced volume.
    field = case[1]
    post = {row["group_id"]: row["consumed_service"]["value"] / 90 - 0.5
            for row in field["service"]["rows"] if row["period"] == "post"}
    raw_contrast = (sum(post[f"i{i}"] for i in range(1, 7))
                    - sum(post[f"c{i}"] for i in range(1, 7))) / 6
    assert raw_contrast > float(report["candidate_point"]["tau_adjusted_change"]) + 0.01


def test_bootstrap_and_point_are_invariant_to_all_input_row_orders() -> None:
    case = _case()
    baseline = analyze_field_adjusted_candidate(*case)
    reordered = copy.deepcopy(case)
    reordered[0]["groups"].reverse()
    reordered[0]["periods"].reverse()
    for name in ("groups", "lots", "flows", "burdens"):
        reordered[1][name].reverse()
    reordered[1]["service"]["rows"].reverse()
    reordered[3]["rows"].reverse()
    _rebind(reordered)
    result = analyze_field_adjusted_candidate(*reordered)
    assert result["candidate_point"] == baseline["candidate_point"]
    assert result["candidate_interval"] == baseline["candidate_interval"]
    assert result["diagnostics"] == baseline["diagnostics"]


@pytest.mark.parametrize("mutation,pattern", [
    ("missing", "exactly one"),
    ("duplicate", "duplicated"),
    ("zero", "positive"),
    ("late_source", "pre-window-complete and preassignment"),
    ("early_source", "pre-window-complete and preassignment"),
    ("wrong_window", "exactly the declared pre window"),
    ("wrong_unit", "unit differs"),
    ("wrong_spec_digest", "candidate_spec_sha256 differs"),
    ("extra_row_key", "unexpected keys"),
])
def test_volume_manifest_fails_closed(mutation: str, pattern: str) -> None:
    case = _case(draws=20)
    manifest = case[3]
    row = manifest["rows"][0]
    if mutation == "missing":
        manifest["rows"].pop()
    elif mutation == "duplicate":
        manifest["rows"].append(copy.deepcopy(row))
    elif mutation == "zero":
        row["value"] = 0
    elif mutation == "late_source":
        row["source"]["observed_at_utc"] = "2026-02-01T00:00:00Z"
    elif mutation == "early_source":
        row["source"]["observed_at_utc"] = "2026-01-30T12:00:00Z"
    elif mutation == "wrong_window":
        row["window_end_utc"] = "2026-01-30T00:00:00Z"
    elif mutation == "wrong_unit":
        row["unit"] = "different-unit"
    elif mutation == "wrong_spec_digest":
        manifest["candidate_spec_sha256"] = "f" * 64
    else:
        row["unknown"] = True
    with pytest.raises(FieldAdjustedCandidateError, match=pattern):
        analyze_field_adjusted_candidate(*case)


def test_spec_registration_and_definition_digest_fail_closed() -> None:
    case = _case(draws=20)
    case[2]["registered_at_utc"] = "2026-02-01T00:00:00Z"
    _rebind(case)
    with pytest.raises(FieldAdjustedCandidateError, match="registration must .* predate the pre window"):
        analyze_field_adjusted_candidate(*case)
    case = _case(draws=20)
    case[2]["registered_at_utc"] = "2026-01-31T10:00:00Z"
    _rebind(case)
    with pytest.raises(FieldAdjustedCandidateError, match="registration must .* predate the pre window"):
        analyze_field_adjusted_candidate(*case)
    case = _case(draws=20)
    case[2]["baseline_input_volume"]["definition"] = "different definition"
    _rebind(case)
    with pytest.raises(FieldAdjustedCandidateError, match="definition digest differs"):
        analyze_field_adjusted_candidate(*case)


def test_original_fit_and_zero_denominator_fail_closed() -> None:
    case = _case(draws=20)
    for row in case[3]["rows"]:
        row["value"] = 100
    with pytest.raises(FieldAdjustedCandidateError, match="nonidentifiable or numerically singular"):
        analyze_field_adjusted_candidate(*case)
    case = _case(draws=20)
    for row in case[1]["service"]["rows"]:
        if row["period"] == "pre" and row["group_id"].startswith("i"):
            row["consumed_service"]["value"] = 90
    with pytest.raises(FieldAdjustedCandidateError, match="G denominator is zero"):
        analyze_field_adjusted_candidate(*case)


def test_invalid_bootstrap_draws_are_counted_without_erasure() -> None:
    case = _case(draws=100)
    for row in case[3]["rows"]:
        row["value"] = 120 if row["group_id"] == "c1" else 100
    report = analyze_field_adjusted_candidate(*case)
    boot = report["diagnostics"]["bootstrap"]
    assert boot["singular_fit_draws"] > 0
    assert boot["valid_draws"] > 0
    assert boot["valid_draws"] + boot["invalid_draws"] == boot["draws_requested"]
    assert len(boot["invalid_draw_indices_zero_based"]) == boot["invalid_draws"]
    assert report["candidate_interval"]["valid_draws_only"]


def test_too_few_valid_bootstrap_draws_do_not_define_a_percentile_interval() -> None:
    report = analyze_field_adjusted_candidate(*_case(draws=1))
    assert report["candidate_interval"]["bounds"] is None
    assert report["candidate_interval"]["defined"] is False
    assert report["candidate_interval"]["minimum_valid_draws"] == 200
    assert report["candidate_interval"]["undefined_reason"]

    case = _case(draws=100)
    for row in case[1]["service"]["rows"]:
        if row["period"] == "pre" and row["group_id"].startswith("i") and row["group_id"] != "i1":
            row["consumed_service"]["value"] = 90
    report = analyze_field_adjusted_candidate(*case)
    boot = report["diagnostics"]["bootstrap"]
    assert boot["zero_denominator_draws"] > 0
    assert boot["valid_draws"] + boot["invalid_draws"] == boot["draws_requested"]


def test_degenerate_interval_is_descriptive_but_singleton_cell_is_rejected() -> None:
    case = _case(draws=400)
    for row in case[1]["service"]["rows"]:
        row["consumed_service"]["value"] = 45
    report = analyze_field_adjusted_candidate(*case)
    assert report["candidate_interval"]["bounds"] == ["0", "0"]
    assert report["candidate_interval"]["defined"]
    assert report["decision_ready"] is False

    case = _case(draws=40)
    for group in case[1]["groups"]:
        group["stratum"] = f"S{group['id'][1:]}"
    case[0]["groups"] = _plan(case[1])["groups"]
    _rebind(case)
    with pytest.raises(FieldAdjustedCandidateError, match="singleton arm-stratum cell"):
        analyze_field_adjusted_candidate(*case)


def test_cli_accepts_strict_json_and_rejects_duplicate_keys(tmp_path: Path) -> None:
    case = _case(draws=20)
    paths = []
    for name, value in zip(("plan", "field", "spec", "volume"), case, strict=True):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        paths.append(str(path))
    completed = subprocess.run([sys.executable, str(SCRIPT), *paths],
                               text=True, capture_output=True, check=True)
    assert json.loads(completed.stdout) == analyze_field_adjusted_candidate(*case)
    assert completed.stderr == ""
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema":1,"schema":1}', encoding="utf-8")
    completed = subprocess.run([sys.executable, str(SCRIPT), *paths[:3], str(bad)],
                               text=True, capture_output=True)
    assert completed.returncode == 2
    assert "duplicate" in completed.stderr.lower()
    bad.write_text('{"schema":NaN}', encoding="utf-8")
    completed = subprocess.run([sys.executable, str(SCRIPT), *paths[:3], str(bad)],
                               text=True, capture_output=True)
    assert completed.returncode == 2
    assert "non-finite" in completed.stderr.lower()
