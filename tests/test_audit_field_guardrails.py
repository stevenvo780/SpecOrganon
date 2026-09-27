"""Synthetic-only structural controls for prospective field-harm guardrails."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/audit_field_guardrails.py"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from audit_field_guardrails import (  # noqa: E402
    MEASUREMENTS_CLASSIFICATION,
    METRICS,
    REGISTRY_CLASSIFICATION,
    FieldGuardrailError,
    audit_field_guardrails,
    canonical_sha256,
)
from test_audit_field_trial_design import _plan, _twelve_group_field  # noqa: E402


PARTICIPATION = (
    ("farmer", "harvest"),
    ("processor", "process"),
    ("processor", "logistics-a"),
    ("processor", "logistics-b"),
    ("processor", "finish"),
)


def _synthetic_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    field = _twelve_group_field()
    plan = _plan(field)
    registry: dict[str, Any] = {
        "schema": 1,
        "classification": REGISTRY_CLASSIFICATION,
        "study_id": plan["study_id"],
        "plan_sha256": canonical_sha256(plan),
        "registered_at_utc": "2025-12-20T00:00:00Z",
        "approved_by": "synthetic-declared-reviewer",
        "participation": [{"actor_id": actor, "stage": stage}
                          for actor, stage in PARTICIPATION],
        "planned_group_actors": [
            {"group_id": group_id, "actor_id": actor_id}
            for group_id, actor_id in sorted({
                (group["id"], actor_id)
                for group in field["groups"] for actor_id in group["actor_ids"]
            })
        ],
        "planned_stages": [
            {"group_id": group_id, "period": period, "stage": stage}
            for group_id, period, stage in sorted({
                (lot["group_id"], lot["period"], lot["stage"])
                for lot in field["lots"]
            })
        ],
        "cells": [],
    }
    for actor, stage in PARTICIPATION:
        for metric in sorted(METRICS):
            cell: dict[str, Any] = {
                "id": f"{actor}:{stage}:{metric}",
                "actor_id": actor,
                "stage": stage,
                "metric": metric,
                "status": "measured",
                "unit": "synthetic-unit",
                "denominator": "one declared service unit",
                "comparator": {
                    "reference_arm": "control",
                    "target_arm": "intervention",
                    "method": "synthetic paired-arm comparison",
                },
                "window": {"periods": ["pre", "post"], "aggregation": "weekly"},
                "source_id": f"synthetic-source:{actor}:{stage}:{metric}",
                "missing_rule": "synthetic missingness rule",
            }
            if metric == "safety":
                cell["stop_condition"] = "synthetic stop if the declared safety event occurs"
            else:
                cell["margin"] = {"direction": "synthetic upper bound", "value": 0.25}
            registry["cells"].append(cell)
    measurements: dict[str, Any] = {
        "schema": 1,
        "classification": MEASUREMENTS_CLASSIFICATION,
        "study_id": plan["study_id"],
        "registry_sha256": canonical_sha256(registry),
        "rows": [],
    }
    for group in field["groups"]:
        for period in ("pre", "post"):
            stages = {lot["stage"] for lot in field["lots"]
                      if lot["group_id"] == group["id"] and lot["period"] == period}
            for cell in registry["cells"]:
                if cell["actor_id"] not in group["actor_ids"] or cell["stage"] not in stages:
                    continue
                key = f"{group['id']}/{period}/{cell['id']}"
                measurements["rows"].append({
                    "group_id": group["id"],
                    "period": period,
                    "cell_id": cell["id"],
                    "value": 1.0,
                    "source": {
                        "record_sha256": hashlib.sha256(key.encode()).hexdigest(),
                        "locator": f"synthetic/{key}",
                        "observed_at_utc": (
                            "2026-01-15T12:00:00Z" if period == "pre"
                            else "2026-03-15T12:00:00Z"
                        ),
                        "method": "synthetic fixture only",
                    },
                })
    return plan, field, registry, measurements


def _audit(plan: dict, field: dict, registry: dict, measurements: dict) -> dict:
    return audit_field_guardrails(
        plan, field, registry, measurements,
        plan_sha256=canonical_sha256(plan),
        registry_sha256=canonical_sha256(registry),
    )


def test_synthetic_complete_matrix_remains_unapproved_and_unready() -> None:
    plan, field, registry, measurements = _synthetic_inputs()
    report = _audit(plan, field, registry, measurements)
    assert report["structural_match_at_read"] is True
    assert report["declared_participation_pairs"] == 5
    assert report["planned_group_actors"] == 12 * 2
    assert report["planned_group_period_stages"] == 12 * 2 * 5
    assert report["metric_cells"] == 30
    assert report["measured_cells"] == 30
    assert report["group_period_cell_rows"] == 12 * 2 * 30
    assert report["measurement_source_references_unique"] is True
    assert report["approval_authenticated"] is False
    assert report["registration_authenticated"] is False
    assert report["actor_stage_participation_authenticated"] is False
    assert report["execution_ready"] is False
    assert report["criterion_3"]["status"] == "not_assessed"


def test_declared_exclusion_needs_approval_fields_and_has_no_measurement() -> None:
    plan, field, registry, measurements = _synthetic_inputs()
    cell = registry["cells"][0]
    excluded_id = cell["id"]
    registry["cells"][0] = {
        **{key: cell[key] for key in ("id", "actor_id", "stage", "metric")},
        "status": "excluded",
        "reason": "synthetic example of a separately justified exclusion",
        "approved_by": "synthetic-declared-approver",
        "approved_at_utc": "2025-12-21T00:00:00Z",
        "approval_record_sha256": "b" * 64,
    }
    measurements["rows"] = [row for row in measurements["rows"]
                            if row["cell_id"] != excluded_id]
    measurements["registry_sha256"] = canonical_sha256(registry)
    report = _audit(plan, field, registry, measurements)
    assert report["excluded_cells"] == 1
    assert report["group_period_cell_rows"] == 12 * 2 * 29
    assert report["approval_authenticated"] is False
    assert report["execution_ready"] is False

    registry["cells"][0].pop("approved_by")
    with pytest.raises(FieldGuardrailError, match="missing keys"):
        _audit(plan, field, registry, measurements)


@pytest.mark.parametrize(("change", "error"), [
    ("missing_metric", "lacks metric cells"),
    ("missing_participation", "unregistered pair or metric"),
    ("omitted_stage", "misses declared stages"),
    ("duplicate_participation", "duplicate actor-stage participation"),
    ("duplicate_cell", "duplicate guardrail cell ID"),
    ("duplicate_metric", "duplicate guardrail metric"),
    ("wrong_plan_hash", "plan_sha256 differs from exact plan hash"),
    ("late_registration", "registration must predate first assignment"),
    ("registration_after_pre_start", "registration must predate start of pre window"),
    ("missing_margin", "exactly one margin or stop_condition"),
    ("missing_measurement", "measurements missing 1"),
    ("duplicate_measurement", "duplicate group-period-cell measurement"),
    ("reused_source", "measurement source reference reused"),
    ("wrong_registry_hash", "measurements.registry_sha256 differs"),
])
def test_structural_omissions_and_mismatches_fail_closed(change: str, error: str) -> None:
    plan, field, registry, measurements = _synthetic_inputs()
    if change == "missing_metric":
        registry["cells"].pop()
    elif change == "missing_participation":
        registry["participation"].pop()
    elif change == "omitted_stage":
        registry["participation"] = [pair for pair in registry["participation"]
                                     if pair["stage"] != "finish"]
        registry["cells"] = [cell for cell in registry["cells"]
                             if cell["stage"] != "finish"]
    elif change == "duplicate_participation":
        registry["participation"].append(copy.deepcopy(registry["participation"][0]))
    elif change == "duplicate_cell":
        registry["cells"].append(copy.deepcopy(registry["cells"][0]))
    elif change == "duplicate_metric":
        extra = copy.deepcopy(registry["cells"][0])
        extra["id"] += ":again"
        registry["cells"].append(extra)
    elif change == "wrong_plan_hash":
        registry["plan_sha256"] = "f" * 64
    elif change == "late_registration":
        registry["registered_at_utc"] = "2026-02-02T00:00:00Z"
    elif change == "registration_after_pre_start":
        registry["registered_at_utc"] = "2026-01-30T00:00:00Z"
    elif change == "missing_margin":
        registry["cells"][0].pop("margin")
    elif change == "missing_measurement":
        measurements["rows"].pop()
    elif change == "duplicate_measurement":
        measurements["rows"].append(copy.deepcopy(measurements["rows"][0]))
    elif change == "reused_source":
        measurements["rows"][1]["source"] = copy.deepcopy(measurements["rows"][0]["source"])
    elif change == "wrong_registry_hash":
        measurements["registry_sha256"] = "f" * 64
    if change in {
        "missing_metric", "missing_participation", "omitted_stage",
        "duplicate_participation", "duplicate_cell", "duplicate_metric",
        "wrong_plan_hash", "late_registration", "registration_after_pre_start",
        "missing_margin",
    }:
        measurements["registry_sha256"] = canonical_sha256(registry)
    with pytest.raises(FieldGuardrailError, match=error):
        _audit(plan, field, registry, measurements)


def test_api_rejects_spoofed_hash_arguments() -> None:
    plan, field, registry, measurements = _synthetic_inputs()
    with pytest.raises(FieldGuardrailError, match="exact canonical plan JSON"):
        audit_field_guardrails(
            plan, field, registry, measurements,
            plan_sha256="0" * 64, registry_sha256=canonical_sha256(registry),
        )
    with pytest.raises(FieldGuardrailError, match="exact canonical registry JSON"):
        audit_field_guardrails(
            plan, field, registry, measurements,
            plan_sha256=canonical_sha256(plan), registry_sha256="0" * 64,
        )


def test_declared_stage_drift_cannot_shrink_measurement_matrix() -> None:
    plan, field, registry, measurements = _synthetic_inputs()
    for lot in field["lots"]:
        if lot["group_id"] == "c1" and lot["stage"] == "logistics-a":
            lot["stage"] = "logistics-b"
    measurements["rows"] = [
        row for row in measurements["rows"]
        if not (row["group_id"] == "c1" and ":logistics-a:" in row["cell_id"])
    ]
    assert len(measurements["rows"]) == 708
    with pytest.raises(FieldGuardrailError, match="field stages differ from registry planned_stages"):
        _audit(plan, field, registry, measurements)


def test_actor_removal_cannot_shrink_matrix_with_another_harvest_actor() -> None:
    plan, field, registry, measurements = _synthetic_inputs()
    registry["participation"].append({"actor_id": "processor", "stage": "harvest"})
    harvest_cells = [cell for cell in registry["cells"]
                     if cell["actor_id"] == "farmer" and cell["stage"] == "harvest"]
    for cell in harvest_cells:
        duplicate = copy.deepcopy(cell)
        duplicate["id"] = cell["id"].replace("farmer:", "processor:", 1)
        duplicate["actor_id"] = "processor"
        duplicate["source_id"] = cell["source_id"].replace("farmer:", "processor:", 1)
        registry["cells"].append(duplicate)
    new_rows = []
    for row in measurements["rows"]:
        if row["cell_id"] not in {cell["id"] for cell in harvest_cells}:
            continue
        duplicate = copy.deepcopy(row)
        duplicate["cell_id"] = row["cell_id"].replace("farmer:", "processor:", 1)
        key = f"{row['group_id']}/{row['period']}/{duplicate['cell_id']}"
        duplicate["source"]["record_sha256"] = hashlib.sha256(key.encode()).hexdigest()
        duplicate["source"]["locator"] = f"synthetic/{key}"
        new_rows.append(duplicate)
    measurements["rows"].extend(new_rows)
    measurements["registry_sha256"] = canonical_sha256(registry)
    assert len(measurements["rows"]) == 864
    assert _audit(plan, field, registry, measurements)["group_period_cell_rows"] == 864

    for group in field["groups"]:
        if group["id"] == "c1":
            group["actor_ids"].remove("farmer")
    field["burdens"] = [burden for burden in field["burdens"]
                        if not (burden["group_id"] == "c1" and burden["actor_id"] == "farmer")]
    measurements["rows"] = [row for row in measurements["rows"]
                            if not (row["group_id"] == "c1"
                                    and row["cell_id"].startswith("farmer:harvest:"))]
    assert len(measurements["rows"]) == 852
    with pytest.raises(FieldGuardrailError, match="field group actors differ from registry planned_group_actors"):
        _audit(plan, field, registry, measurements)


def test_decimal_canonical_hash_equivalence_and_numeric_bounds() -> None:
    from_float = {"a": 0.25, "b": [1.0, -0.0, 1e-18]}
    from_decimal = {"a": Decimal("0.2500"),
                    "b": [Decimal("1.000"), Decimal("-0.00"), Decimal("1E-18")]}
    assert canonical_sha256(from_float) == canonical_sha256(from_decimal)
    for value in (Decimal("1e-19"), Decimal("1e19"), Decimal("9" * 81),
                  float("nan"), float("inf")):
        with pytest.raises(FieldGuardrailError, match="number"):
            canonical_sha256({"value": value})


def _write_cli_inputs(tmp_path: Path) -> list[Path]:
    paths = [tmp_path / f"{name}.json" for name in (
        "plan", "field", "registry", "measurements"
    )]
    for path, value in zip(paths, _synthetic_inputs(), strict=True):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return paths


def test_cli_reads_four_synthetic_json_files_without_mutation(tmp_path: Path) -> None:
    paths = _write_cli_inputs(tmp_path)
    before = [path.read_bytes() for path in paths]
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *(str(path) for path in paths)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["group_period_cell_rows"] == 720
    assert report["approval_authenticated"] is False
    assert report["execution_ready"] is False
    assert report["criterion_3"]["status"] == "not_assessed"
    assert [path.read_bytes() for path in paths] == before


@pytest.mark.parametrize(("change", "error"), [
    ("duplicate_key", "duplicate JSON object key"),
    ("nonfinite", "non-finite JSON numeric constant"),
    ("subunderflow", "magnitude is outside supported numeric range"),
])
def test_cli_rejects_invalid_json_without_mutation(tmp_path: Path,
                                                   change: str, error: str) -> None:
    paths = _write_cli_inputs(tmp_path)
    if change == "duplicate_key":
        path = paths[0]
        original = path.read_text(encoding="utf-8")
        path.write_text(original.replace('"schema": 1,', '"schema": 1, "schema": 1,', 1),
                        encoding="utf-8")
    else:
        path = paths[3]
        original = path.read_text(encoding="utf-8")
        replacement = "NaN" if change == "nonfinite" else "1e-10000"
        assert '"value": 1.0' in original
        path.write_text(original.replace('"value": 1.0', f'"value": {replacement}', 1),
                        encoding="utf-8")
    before = [path.read_bytes() for path in paths]
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *(str(path) for path in paths)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert error in result.stderr
    assert result.stdout == ""
    assert [path.read_bytes() for path in paths] == before
