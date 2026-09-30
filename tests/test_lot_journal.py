"""Synthetic declaration controls; none of these quantities is a field observation."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from specorganon.lot_journal import MAX_INPUT_BYTES, LotJournalError, audit_lot_journal, read_journal

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/audit_lot_journal.py"


def _load(id, kind, value, *, unit="kg", fraction=0.8, material="synthetic-grain"):
    return {"load_id": id, "material_id": material, "kind": kind,
            "mass": {"value": value, "unit": unit, "uncertainty": 0},
            "basis": "wet", "dry_fraction": fraction}


def _event(id, hour, inputs, outputs):
    at = f"2026-09-30T{hour:02}:00:00Z"
    return {"id": id, "stage": "Synthetic operation", "stage_role": "transformation",
            "actor": "agent:synthetic_recorder", "at_utc": at,
            "inputs": inputs, "outputs": outputs, "balance_tolerance_kg": 0,
            "source": {"source_id": "synthetic-only-record", "locator": f"row/{id}",
                       "observed_at_utc": at, "method": "invented mechanics fixture",
                       "record_sha256": "a" * 64}}


@pytest.fixture
def journal():
    flour = _load("flour1", "product", 9)
    first = _event("mill", 10, [
        _load("feed1", "feed", 10), _load("ingredient1", "ingredient", 1000, unit="g"),
        _load("water1", "water_addition", 0.002, unit="t", fraction=0, material="water"),
    ], [flour, _load("bran1", "coproduct", 2),
        _load("vapour1", "evaporation", 2000, unit="g", fraction=0, material="water")])
    second = _event("bake", 11, [
        copy.deepcopy(flour), _load("ingredient2", "ingredient", 1),
        _load("water2", "water_addition", 1, fraction=0, material="water"),
    ], [_load("bread1", "product", 7.5), _load("bran2", "coproduct", 2.5),
        _load("vapour2", "moisture", 1, fraction=0, material="water")])
    return {"schema": 1, "classification": "lot_journal_declared_only",
            "journal_id": "synthetic-journal", "events": [first, second]}


def test_mixed_units_water_coproducts_and_transfer_have_exact_declared_balances(journal):
    original = copy.deepcopy(journal)
    report = audit_lot_journal(journal)
    assert journal == original
    assert report["valid"] is True
    assert report["counts"] == {"events": 2, "loads": 11, "external_inputs": 5, "transfers": 1}
    assert report["balances"][0] == {
        "event_id": "mill",
        "wet": {"status": "balanced", "input_kg": "13", "output_kg": "13", "residual_kg": "0", "allowance_kg": "0"},
        "dry": {"status": "balanced", "input_kg": "8.8", "output_kg": "8.8", "residual_kg": "0", "allowance_kg": "0"},
    }
    assert report["balances"][1]["wet"]["input_kg"] == "11"
    assert report["balances"][1]["dry"]["output_kg"] == "8"
    assert report["unconsumed_output_load_ids"] == ["bran1", "bran2", "bread1", "vapour1", "vapour2"]
    assert report["terminal_output_load_ids"] == ["vapour1"]
    assert report["pending"] == {"capture_completeness": "not_established", "dry_balance_event_ids": []}
    assert report["observations_authenticated"] is False
    assert report["field_scope_complete"] is False and report["execution_ready"] is False
    assert report["criterion_3"]["status"] == "not_assessed"
    assert not {"V", "G", "control", "approved"} & report.keys()


def test_incremental_prefix_needs_no_experiment_or_terminal_observation(journal):
    journal["events"] = journal["events"][:1]
    report = audit_lot_journal(journal)
    assert report["counts"]["events"] == 1
    assert report["capture_status"] == "incremental_declared_events_only"
    assert report["pending"]["capture_completeness"] == "not_established"
    assert report["execution_ready"] is False


def test_missing_dry_fraction_keeps_wet_balance_and_explicit_pending_status(journal):
    for event in journal["events"]:
        for load in event["inputs"] + event["outputs"]:
            if load["kind"] not in {"water_addition", "evaporation", "moisture"}:
                load["dry_fraction"] = None
    report = audit_lot_journal(journal)
    assert report["pending"]["dry_balance_event_ids"] == ["mill", "bake"]
    assert all(row["wet"]["status"] == "balanced" for row in report["balances"])
    assert all(row["dry"] == {"status": "pending_missing_dry_fraction"} for row in report["balances"])


@pytest.mark.parametrize("defect", ["event", "input", "output", "consumed", "preexisting_output", "input_as_output"])
def test_duplicate_and_reused_physical_ids_reject(journal, defect):
    first, second = journal["events"]
    if defect == "event":
        second["id"] = first["id"]
    elif defect == "input":
        first["inputs"].append(copy.deepcopy(first["inputs"][0]))
    elif defect == "output":
        first["outputs"].append(copy.deepcopy(first["outputs"][0]))
    elif defect == "consumed":
        second["inputs"].append(copy.deepcopy(first["inputs"][0]))
    elif defect == "preexisting_output":
        second["outputs"][0]["load_id"] = first["outputs"][1]["load_id"]
    else:
        first["outputs"][0]["load_id"] = first["inputs"][0]["load_id"]
    with pytest.raises(LotJournalError):
        audit_lot_journal(journal)


@pytest.mark.parametrize("field,value", [
    ("material_id", "different-material"), ("kind", "ingredient"),
    ("dry_fraction", None), ("dry_fraction", 0.7), ("basis", "dry"),
])
def test_transferred_load_definition_cannot_change(journal, field, value):
    journal["events"][1]["inputs"][0][field] = value
    with pytest.raises(LotJournalError):
        audit_lot_journal(journal)


def test_transferred_mass_cannot_change(journal):
    journal["events"][1]["inputs"][0]["mass"]["value"] = 9.1
    with pytest.raises(LotJournalError, match="definition differs"):
        audit_lot_journal(journal)


def test_transfer_accepts_exact_equivalent_units_without_redefining_physical_quantity(journal):
    load = journal["events"][1]["inputs"][0]
    load["mass"] = {"value": 9000, "unit": "g", "uncertainty": 0}
    report = audit_lot_journal(journal)
    assert report["counts"]["transfers"] == 1
    assert report["balances"][1]["wet"]["input_kg"] == "11"


@pytest.mark.parametrize("input_kind", ["evaporation", "moisture", "product"])
def test_terminal_evaporation_cannot_reenter_as_transfer_or_relabeled_load(input_kind):
    lost = _load("vapour", "evaporation", 1, fraction=0, material="water")
    first = _event("release", 10, [
        _load("water", "water_addition", 1, fraction=0, material="water"),
    ], [lost])
    reused = copy.deepcopy(lost)
    reused["kind"] = input_kind
    second = _event("reuse", 11, [reused], [
        _load("reused-water", "product", 1, fraction=0, material="water"),
    ])
    data = {"schema": 1, "classification": "lot_journal_declared_only",
            "journal_id": "synthetic-evaporation", "events": [first, second]}
    with pytest.raises(LotJournalError, match="terminal evaporation load cannot be consumed"):
        audit_lot_journal(data)


def test_explicitly_captured_water_product_can_transfer_without_claiming_field_coverage():
    captured = _load("captured-water", "product", 1, fraction=0, material="water")
    first = _event("capture", 10, [
        _load("water", "water_addition", 1, fraction=0, material="water"),
    ], [captured])
    second = _event("reuse", 11, [copy.deepcopy(captured)], [
        _load("reused-water", "product", 1, fraction=0, material="water"),
    ])
    data = {"schema": 1, "classification": "lot_journal_declared_only",
            "journal_id": "synthetic-water-recovery", "events": [first, second]}
    report = audit_lot_journal(data)
    assert report["counts"]["transfers"] == 1
    assert report["terminal_output_load_ids"] == []
    assert report["unconsumed_output_load_ids"] == ["reused-water"]
    assert all(row["dry"]["input_kg"] == row["dry"]["output_kg"] == "0" for row in report["balances"])
    assert report["field_scope_complete"] is False and report["execution_ready"] is False


@pytest.mark.parametrize("field,value", [
    ("value", True), ("value", 0), ("value", -1), ("value", float("nan")),
    ("value", float("inf")), ("uncertainty", -1), ("uncertainty", False),
    ("value", "10"),
    ("unit", "lb"), ("unit", "KG"), ("unit", "kg_dry"),
])
def test_invalid_mass_type_number_and_unit_reject(journal, field, value):
    journal["events"][0]["inputs"][0]["mass"][field] = value
    with pytest.raises(LotJournalError):
        audit_lot_journal(journal)


@pytest.mark.parametrize("fraction", [True, -0.1, 1.1, "0.8", float("nan"), float("inf")])
def test_invalid_dry_fraction_reject(journal, fraction):
    journal["events"][0]["inputs"][0]["dry_fraction"] = fraction
    with pytest.raises(LotJournalError):
        audit_lot_journal(journal)


@pytest.mark.parametrize("fraction", [None, 0.1])
@pytest.mark.parametrize("side,index", [("inputs", 2), ("outputs", 2)])
def test_water_or_evaporation_requires_known_zero_dry_fraction(journal, fraction, side, index):
    journal["events"][0][side][index]["dry_fraction"] = fraction
    with pytest.raises(LotJournalError, match="dry_fraction zero"):
        audit_lot_journal(journal)


def test_wet_imbalance_rejects_before_dry_reporting(journal):
    journal["events"][0]["outputs"][0]["mass"]["value"] = 8
    with pytest.raises(LotJournalError, match="wet mass balance"):
        audit_lot_journal(journal)


def test_known_dry_imbalance_rejects_even_when_wet_mass_conserves(journal):
    journal["events"][0]["inputs"][0]["dry_fraction"] = 0.9
    with pytest.raises(LotJournalError, match="dry mass balance"):
        audit_lot_journal(journal)


def test_balance_uses_sum_of_uncertainties_plus_declared_tolerance(journal):
    journal["events"] = journal["events"][:1]
    event = journal["events"][0]
    event["inputs"][0]["mass"]["uncertainty"] = 0.2
    event["outputs"][0]["mass"]["value"] = 9.1
    event["balance_tolerance_kg"] = 0.05
    balance = audit_lot_journal(journal)["balances"][0]
    assert balance["wet"]["residual_kg"] == "-0.1" and balance["wet"]["allowance_kg"] == "0.25"
    assert balance["dry"]["residual_kg"] == "-0.08" and balance["dry"]["allowance_kg"] == "0.21"


def test_dry_balance_accepts_exact_boundary_and_rejects_a_larger_residual(journal):
    journal["events"] = journal["events"][:1]
    event = journal["events"][0]
    event["inputs"][0]["dry_fraction"] = 0.8001
    event["balance_tolerance_kg"] = 0.001
    dry = audit_lot_journal(journal)["balances"][0]["dry"]
    assert dry["residual_kg"] == dry["allowance_kg"] == "0.001"
    event["inputs"][0]["dry_fraction"] = 0.80010001
    with pytest.raises(LotJournalError, match="dry mass balance"):
        audit_lot_journal(journal)


def test_decimal_arithmetic_does_not_round_a_real_mass_discrepancy(journal):
    event = journal["events"][0]
    event["inputs"] = [_load("small1", "feed", 0.1), _load("small2", "ingredient", 0.2)]
    event["outputs"] = [_load("small3", "product", 0.3)]
    journal["events"] = [event]
    wet = audit_lot_journal(journal)["balances"][0]["wet"]
    assert wet["input_kg"] == wet["output_kg"] == "0.3"
    event["outputs"][0]["mass"]["value"] = 0.30000000000000004
    with pytest.raises(LotJournalError, match="wet mass balance"):
        audit_lot_journal(journal)


@pytest.mark.parametrize("value", ["2026-09-30T09:00:00Z", "2026-09-30T11:00:00+00:00", "2026-02-30T11:00:00Z"])
def test_decreasing_or_invalid_event_times_reject(journal, value):
    journal["events"][1]["at_utc"] = value
    with pytest.raises(LotJournalError):
        audit_lot_journal(journal)


@pytest.mark.parametrize("field,value", [
    ("source_id", ""), ("locator", ""), ("method", False),
    ("observed_at_utc", "yesterday"), ("record_sha256", "A" * 64),
    ("record_sha256", "a" * 63), ("record_sha256", None),
])
def test_source_metadata_must_be_explicit_but_is_never_authenticated(journal, field, value):
    journal["events"][0]["source"][field] = value
    with pytest.raises(LotJournalError):
        audit_lot_journal(journal)


@pytest.mark.parametrize("defect", [
    "unknown_top", "wrong_schema", "boolean_schema", "wrong_classification", "no_events",
    "no_inputs", "no_outputs", "extra_event", "extra_load", "extra_mass", "extra_source",
    "missing_source_digest", "wrong_actor", "wrong_stage_role", "negative_tolerance",
    "boolean_tolerance", "nan_tolerance", "unknown_external_product", "output_feed",
])
def test_closed_shapes_and_invalid_event_declarations_reject(journal, defect):
    event = journal["events"][0]
    if defect == "unknown_top":
        journal["control"] = True
    elif defect == "wrong_schema":
        journal["schema"] = 2
    elif defect == "boolean_schema":
        journal["schema"] = True
    elif defect == "wrong_classification":
        journal["classification"] = "observed_field_journal"
    elif defect == "no_events":
        journal["events"] = []
    elif defect == "no_inputs":
        event["inputs"] = []
    elif defect == "no_outputs":
        event["outputs"] = []
    elif defect == "extra_event":
        event["approved"] = True
    elif defect == "extra_load":
        event["inputs"][0]["physical_alias"] = "different-load"
    elif defect == "extra_mass":
        event["inputs"][0]["mass"]["dry_value"] = 8
    elif defect == "extra_source":
        event["source"]["authenticated"] = True
    elif defect == "missing_source_digest":
        event["source"].pop("record_sha256")
    elif defect == "wrong_actor":
        event["actor"] = False
    elif defect == "wrong_stage_role":
        event["stage_role"] = "unknown"
    elif defect == "negative_tolerance":
        event["balance_tolerance_kg"] = -1
    elif defect == "boolean_tolerance":
        event["balance_tolerance_kg"] = True
    elif defect == "nan_tolerance":
        event["balance_tolerance_kg"] = float("nan")
    elif defect == "unknown_external_product":
        event["inputs"][0]["kind"] = "product"
    else:
        event["outputs"][0]["kind"] = "feed"
    with pytest.raises(LotJournalError):
        audit_lot_journal(journal)


def test_source_digest_pointer_does_not_open_records_or_authenticate_observations(journal, monkeypatch):
    def no_source_reads(*args, **kwargs):
        pytest.fail("a declared source pointer must not cause file reads")

    monkeypatch.setattr(Path, "read_bytes", no_source_reads)
    for event in journal["events"]:
        event["source"]["locator"] = "/nonexistent/not-authorized/source.json"
        event["source"]["record_sha256"] = "0" * 64
    report = audit_lot_journal(journal)
    assert report["valid"] is True and report["observations_authenticated"] is False


def test_strict_cli_file_and_stdin_preserve_input_and_report_declared_scope(journal, tmp_path):
    raw = json.dumps(journal).encode()
    path = tmp_path / "journal.json"
    path.write_bytes(raw)
    for args, stdin in (([str(path)], None), (["-"], raw)):
        result = subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin,
                                capture_output=True, timeout=10, check=False)
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        assert report["valid"] is True and report["execution_ready"] is False
        assert report == audit_lot_journal(journal)
    assert path.read_bytes() == raw
    assert set(tmp_path.iterdir()) == {path}


@pytest.mark.parametrize("raw", [
    b'{"schema":1,"schema":1}', b'{"schema":NaN}', b'{"schema":Infinity}', b'false',
])
def test_cli_rejects_duplicate_keys_nonfinite_and_wrong_root(raw):
    result = subprocess.run([sys.executable, str(SCRIPT), "-"], input=raw,
                            capture_output=True, timeout=10, check=False)
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["valid"] is False and report["execution_ready"] is False


def test_cli_rejects_nested_duplicate_mass_key_in_otherwise_valid_journal(journal):
    raw = json.dumps(journal).replace('"value": 10', '"value": 10, "value": 10', 1).encode()
    result = subprocess.run([sys.executable, str(SCRIPT), "-"], input=raw,
                            capture_output=True, timeout=10, check=False)
    assert result.returncode == 2
    assert "duplicate key in JSON object" in json.loads(result.stdout)["error"]


@pytest.mark.parametrize("path_type", [str, Path])
def test_read_journal_exposes_the_common_strict_reader_without_schema_admission(tmp_path, path_type):
    path = tmp_path / "not-yet-a-journal.json"
    raw = b'{"unregistered":0.8}'
    path.write_bytes(raw)
    assert read_journal(path_type(path)) == {"unregistered": 0.8}
    assert path.read_bytes() == raw


@pytest.mark.parametrize("mode", ["file", "stdin"])
def test_cli_rejects_decimal_precision_loss_before_auditing_flows(journal, tmp_path, mode):
    raw = json.dumps(journal).replace('"value": 10', '"value": 1.0000000000000000001', 1).encode()
    path = tmp_path / "precision-loss.json"
    path.write_bytes(raw)
    result = subprocess.run([sys.executable, str(SCRIPT), "-" if mode == "stdin" else str(path)],
                            input=raw if mode == "stdin" else None,
                            capture_output=True, timeout=10, check=False)
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["valid"] is False and report["execution_ready"] is False
    assert "loses decimal precision" in report["error"]


@pytest.mark.parametrize("path_type", [str, Path])
def test_read_journal_rejects_nonrepresentable_decimal_json(tmp_path, path_type):
    path = tmp_path / "precision-loss.json"
    path.write_text('{"value":1.0000000000000000001}', encoding="utf-8")
    with pytest.raises(LotJournalError, match="loses decimal precision"):
        read_journal(path_type(path))


def test_pure_python_auditor_preserves_explicit_decimal_quantities(journal):
    event = journal["events"][0]
    amount = Decimal("1.0000000000000000001")
    event["inputs"] = [_load("decimal1", "feed", amount)]
    event["outputs"] = [_load("decimal2", "product", amount)]
    journal["events"] = [event]
    wet = audit_lot_journal(journal)["balances"][0]["wet"]
    assert wet["input_kg"] == wet["output_kg"] == str(amount)
    assert wet["residual_kg"] == "0"


@pytest.mark.parametrize("mode", ["stdin", "file"])
def test_cli_input_byte_limit_precedes_json_parsing(tmp_path, mode):
    raw = b" " * (MAX_INPUT_BYTES + 1)
    path = tmp_path / "oversized.json"
    path.write_bytes(raw)
    result = subprocess.run([sys.executable, str(SCRIPT), "-" if mode == "stdin" else str(path)],
                            input=raw if mode == "stdin" else None,
                            capture_output=True, timeout=10, check=False)
    assert result.returncode == 2
    assert "byte limit" in json.loads(result.stdout)["error"]


@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_cli_rejects_nonregular_or_symlink_file_without_blocking(journal, tmp_path, kind):
    path = tmp_path / "journal.json"
    if kind == "symlink":
        target = tmp_path / "target.json"
        target.write_text(json.dumps(journal), encoding="utf-8")
        path.symlink_to(target)
    else:
        os.mkfifo(path)
    result = subprocess.run([sys.executable, str(SCRIPT), str(path)],
                            capture_output=True, timeout=10, check=False)
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["valid"] is False
    assert "symlink" in report["error"] or "regular file" in report["error"]
