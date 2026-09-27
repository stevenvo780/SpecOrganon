"""Synthetic trial-design controls, without field measurements or custody."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_field_trial_design.py"
sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(Path(__file__).parent))
from audit_field_trial_design import (  # noqa: E402
    PLAN_CLASSIFICATION,
    FieldTrialDesignError,
    audit_field_trial_design,
)
from test_audit_field_flows import field_data_with_schema3_allocations  # noqa: E402


def _rename(value: Any, old: str, new: str, key: str = "") -> Any:
    if isinstance(value, dict):
        return {field: _rename(item, old, new, field) for field, item in value.items()}
    if isinstance(value, list):
        return [_rename(item, old, new, key) for item in value]
    if isinstance(value, str):
        if key in {"id", "group_id"} and value == old:
            return new
        return value.replace(f"{old}-", f"{new}-")
    return value


def _twelve_group_field() -> dict[str, Any]:
    base = field_data_with_schema3_allocations()
    field = copy.deepcopy(base)
    for key in ("groups", "lots", "flows", "burdens"):
        field[key] = []
    field["service"]["rows"] = []
    for arm, prefix in (("control", "c"), ("intervention", "i")):
        for number in range(1, 7):
            new_group = f"{prefix}{number}"
            for key in ("groups", "lots", "flows", "burdens"):
                for row in base[key]:
                    owner = row["id"] if key == "groups" else row["group_id"]
                    if owner == arm:
                        field[key].append(_rename(row, arm, new_group))
            for row in base["service"]["rows"]:
                if row["group_id"] == arm:
                    field["service"]["rows"].append(_rename(row, arm, new_group))
    return field


def _plan(field: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": 1,
        "classification": PLAN_CLASSIFICATION,
        "study_id": field["study_id"],
        "registered_at_utc": "2025-12-15T00:00:00Z",
        "allocation_method": "stratified_random",
        "allocation_record_sha256": "a" * 64,
        "groups": [{key: group[key] for key in ("id", "arm", "stratum")}
                   for group in field["groups"]],
        "periods": [{key: period[key] for key in ("id", "start_utc", "end_utc")}
                    for period in field["periods"]],
    }


def test_twelve_group_schema3_candidate_matches_without_claiming_impact() -> None:
    field = _twelve_group_field()
    report = audit_field_trial_design(_plan(field), field)
    assert report["structural_match_at_read"]
    assert report["groups"] == {"total": 12, "control": 6, "intervention": 6}
    assert report["strata"] == {"S1": {"control": 6, "intervention": 6}}
    assert report["window_days"]["pre"] >= 28
    assert report["window_days"]["post"] >= 56
    assert not report["randomization_verified"]
    assert not report["registration_authenticated"]
    assert not report["weekly_measurement_coverage_verified"]
    assert not report["execution_ready"]
    assert report["criterion_3"]["status"] == "not_assessed"


def test_two_group_field_fixture_cannot_be_mistaken_for_trial_design() -> None:
    field = field_data_with_schema3_allocations()
    with pytest.raises(FieldTrialDesignError, match="at least 12 groups"):
        audit_field_trial_design(_plan(field), field)


@pytest.mark.parametrize("change,expected", [
    ("arm", "group IDs, arms or strata differ"),
    ("group", "group IDs, arms or strata differ"),
    ("window", "period windows differ"),
    ("registration", "registration must predate"),
    ("late_baseline_registration", "needs a declared baseline release"),
    ("post_duration", "post window is shorter than eight weeks"),
    ("service", "schema 3 with service rows"),
])
def test_plan_field_mismatches_and_missing_design_inputs_fail(change: str, expected: str) -> None:
    field = _twelve_group_field()
    plan = _plan(field)
    if change == "arm":
        plan["groups"][0]["arm"] = "intervention"
    elif change == "group":
        plan["groups"].pop()
    elif change == "window":
        plan["periods"][0]["start_utc"] = "2026-01-02T00:00:00Z"
    elif change == "registration":
        plan["registered_at_utc"] = "2026-02-01T00:00:00Z"
        plan["baseline_release"] = {
            "first_access_at_utc": "2026-02-01T12:00:00Z",
            "record_sha256": "b" * 64,
            "custodian_id": "synthetic-custodian",
        }
    elif change == "late_baseline_registration":
        plan["registered_at_utc"] = "2026-01-30T00:00:00Z"
    elif change == "post_duration":
        field["periods"][1]["end_utc"] = "2026-03-20T00:00:00Z"
        plan = _plan(field)
    else:
        field.pop("service")
    with pytest.raises(FieldTrialDesignError, match=expected):
        audit_field_trial_design(plan, field)


def test_both_arms_must_exist_within_each_declared_stratum() -> None:
    field = _twelve_group_field()
    for group in field["groups"]:
        if group["arm"] == "control":
            group["stratum"] = "S2"
    with pytest.raises(FieldTrialDesignError, match="each declared stratum needs both arms"):
        audit_field_trial_design(_plan(field), field)


def test_baseline_observed_before_registration_needs_later_declared_access() -> None:
    field = _twelve_group_field()
    plan = _plan(field)
    plan["registered_at_utc"] = "2026-01-30T00:00:00Z"
    plan["baseline_release"] = {
        "first_access_at_utc": "2026-01-30T12:00:00Z",
        "record_sha256": "b" * 64,
        "custodian_id": "synthetic-custodian",
    }
    report = audit_field_trial_design(plan, field)
    assert report["baseline_release_declared"]
    assert not report["baseline_release_authenticated"]
    assert report["criterion_3"]["status"] == "not_assessed"

    plan["baseline_release"]["first_access_at_utc"] = "2026-01-29T12:00:00Z"
    with pytest.raises(FieldTrialDesignError, match="first access must follow registration"):
        audit_field_trial_design(plan, field)


def test_declared_assignment_source_must_follow_registration() -> None:
    field = _twelve_group_field()
    for group in field["groups"]:
        group["source"]["observed_at_utc"] = "2026-01-31T06:00:00Z"
    plan = _plan(field)
    plan["registered_at_utc"] = "2026-01-31T12:00:00Z"
    plan["baseline_release"] = {
        "first_access_at_utc": "2026-01-31T18:00:00Z",
        "record_sha256": "b" * 64,
        "custodian_id": "synthetic-custodian",
    }
    with pytest.raises(FieldTrialDesignError, match="assignment source predates registration"):
        audit_field_trial_design(plan, field)


def test_cli_reads_exact_input_bytes_and_leaves_them_unchanged(tmp_path: Path) -> None:
    field = _twelve_group_field()
    plan_path = tmp_path / "plan.json"
    field_path = tmp_path / "field.json"
    plan_path.write_text(json.dumps(_plan(field)), encoding="utf-8")
    field_path.write_text(json.dumps(field), encoding="utf-8")
    before = {"plan": plan_path.read_bytes(), "field": field_path.read_bytes()}
    result = subprocess.run([sys.executable, str(SCRIPT), str(plan_path), str(field_path)],
                            capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report["input_sha256"] == {
        key: hashlib.sha256(raw).hexdigest() for key, raw in before.items()
    }
    assert report["criterion_3"]["status"] == "not_assessed"
    assert before == {"plan": plan_path.read_bytes(), "field": field_path.read_bytes()}


def test_cli_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    field_path = tmp_path / "field.json"
    plan_path.write_text('{"schema":1,"schema":1}', encoding="utf-8")
    field_path.write_text("{}", encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), str(plan_path), str(field_path)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert not result.stdout
    assert "duplicate JSON object key" in result.stderr
