"""Synthetic field-flow preflight controls; none is an observed field result."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_field_flows.py"
sys.path.insert(0, str(SCRIPT.parent))
from audit_field_flows import FieldFlowError, audit_field_flows  # noqa: E402


def _evidence(label: str) -> dict[str, str]:
    observed_at = ("2026-03-15T12:00:00Z" if "-post-" in label else
                   "2026-02-01T00:00:00Z" if "assignment" in label else
                   "2026-01-15T12:00:00Z")
    return {
        "source_id": f"synthetic-{label}", "locator": f"record/{label}",
        "observed_at_utc": observed_at, "method": "synthetic measurement",
    }


def _mass(value: float, unit: str = "kg", uncertainty: float = 0.1) -> dict[str, Any]:
    return {"value": value, "unit": unit, "uncertainty": uncertainty}


def _flow(prefix: str, name: str, source: str | None, target: str | None,
          kind: str, value: float, destination: str | None = None,
          *, unit: str = "kg", load_id: str | None = None) -> dict[str, Any]:
    flow_id = f"{prefix}-{name}"
    outcome = None
    dest = None
    if destination is not None:
        dest = {"kind": destination, "source": _evidence(flow_id + "-destination")}
        consumed = destination == "human_consumption"
        outcome = {
            "status": "observed_consumed" if consumed else "observed_other",
            "mass": _mass(value, unit), "source": _evidence(flow_id + "-outcome"),
            "safety": {"status": "safe" if consumed else "not_assessed",
                       "source": _evidence(flow_id + "-safety")},
            "nutrition": ({"status": "useful", "source": _evidence(flow_id + "-nutrition")}
                          if consumed else None),
        }
    return {
        "id": flow_id, "load_id": load_id or f"load-{flow_id}",
        "group_id": prefix.split("-")[0], "period": prefix.split("-")[1],
        "from_lot_id": source, "to_lot_id": target, "kind": kind,
        "mass": _mass(value, unit), "source": _evidence(flow_id),
        "destination": dest, "outcome": outcome,
    }


def _lot(prefix: str, name: str, inputs: list[dict[str, Any]],
         outputs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": f"{prefix}-{name}", "group_id": prefix.split("-")[0],
        "period": prefix.split("-")[1], "stage": name,
        "source": _evidence(prefix + "-" + name),
        "input_flow_ids": [flow["id"] for flow in inputs],
        "output_flow_ids": [flow["id"] for flow in outputs],
        "observed_input_load_ids": [flow["load_id"] for flow in inputs],
        "observed_output_load_ids": [flow["load_id"] for flow in outputs],
    }


def field_data(*, with_service: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": 1, "study_id": "synthetic-study", "balance_tolerance_kg": 0.05,
        "tolerance_source": _evidence("scale-tolerance"), "currency": "INR",
        "actors": [{"id": "farmer", "role": "producer"},
                   {"id": "processor", "role": "processor"}],
        "groups": [
            {"id": "control", "arm": "control", "stratum": "S1",
             "assigned_at_utc": "2026-02-01T00:00:00Z", "actor_ids": ["farmer", "processor"],
             "source": _evidence("control-assignment")},
            {"id": "intervention", "arm": "intervention", "stratum": "S1",
             "assigned_at_utc": "2026-02-01T00:00:00Z", "actor_ids": ["farmer", "processor"],
             "source": _evidence("intervention-assignment")},
        ],
        "periods": [
            {"id": "pre", "start_utc": "2026-01-01T00:00:00Z",
             "end_utc": "2026-01-31T00:00:00Z", "source": _evidence("pre-window")},
            {"id": "post", "start_utc": "2026-02-02T00:00:00Z",
             "end_utc": "2026-04-01T00:00:00Z", "source": _evidence("post-window")},
        ],
        "lots": [], "flows": [], "burdens": [],
    }
    service_rows: list[dict[str, Any]] = []
    for group in ("control", "intervention"):
        for period in ("pre", "post"):
            prefix = f"{group}-{period}"
            wash = prefix + "-wash"
            process = prefix + "-process"
            raw = _flow(prefix, "raw", None, wash, "feed", 100)
            water = _flow(prefix, "water", None, wash, "water_addition", 10)
            transfer = _flow(prefix, "transfer", wash, process, "product", 95)
            reject = _flow(prefix, "reject", wash, None, "residue", 5, "compost")
            wash_moisture = _flow(prefix, "wash-moisture", wash, None, "moisture", 10, "evaporation")
            ingredient = _flow(prefix, "ingredient", None, process, "ingredient", 5)
            consumed = _flow(prefix, "consumed", process, None, "product", 70, "human_consumption")
            coproduct = _flow(prefix, "coproduct", process, None, "coproduct", 25, "animal_feed")
            process_moisture = _flow(prefix, "process-moisture", process, None, "moisture", 5, "wastewater")
            flows = [raw, water, transfer, reject, wash_moisture,
                     ingredient, consumed, coproduct, process_moisture]
            result["flows"].extend(flows)
            result["lots"].extend([
                _lot(prefix, "wash", [raw, water], [transfer, reject, wash_moisture]),
                _lot(prefix, "process", [transfer, ingredient], [consumed, coproduct, process_moisture]),
            ])
            for actor in ("farmer", "processor"):
                result["burdens"].append({
                    "group_id": group, "period": period, "actor_id": actor,
                    "source": _evidence(f"{prefix}-{actor}-burden"),
                    "net_income": 20 if actor == "farmer" else -3,
                    "cost": 8, "work_hours": 2, "energy_kwh": 1,
                    "water_l": 10, "emissions_kg_co2e": 0.5,
                })
            service_rows.append({
                "group_id": group, "period": period,
                "consumption_flow_ids": [consumed["id"]],
                "consumed_service": {"value": 70, "unit": "approved-servings", "uncertainty": 1},
                "feasible_max_service": {"value": 90, "unit": "approved-servings", "uncertainty": 2},
                "source": _evidence(prefix + "-service"),
            })
    if with_service:
        result["service"] = {
            "equivalence": {
                "id": "synthetic-equivalence", "service_unit": "approved-servings",
                "approved_at_utc": "2025-12-01T00:00:00Z",
                "approved_by_actor_ids": ["farmer", "processor"],
                "verified_by": "separate-custodian",
                "record_sha256": "a" * 64, "source": _evidence("equivalence-record"),
            },
            "rows": service_rows,
        }
    return result


def _by_id(rows: list[dict[str, Any]], item_id: str) -> dict[str, Any]:
    return next(row for row in rows if row["id"] == item_id)


def test_complete_synthetic_graph_with_additions_moisture_and_coproducts() -> None:
    report = audit_field_flows(field_data())
    assert report["valid"] is True
    assert report["classification"] == "field_flow_preflight_declared_only"
    assert report["counts"] == {
        "groups": 2, "lots": 8, "flows": 36, "terminal_flows": 20,
        "consumed_flows": 4, "burden_rows": 8,
    }
    assert all(balance["residual_kg"] == "0" for balance in report["balances"])
    assert report["service_status"] == "declared_service_inputs_bounded_approval_unverified"
    assert report["criterion_3"]["status"] == "not_assessed"
    assert report["scope_status"] == "declared_graph_only_full_chain_not_checked"
    assert "V" not in report and "G" not in report


def test_complete_graph_without_approved_equivalence_does_not_compute_service() -> None:
    report = audit_field_flows(field_data(with_service=False))
    assert report["valid"] is True
    assert report["service_status"] == "not_assessed_no_declared_equivalence"
    assert "V" not in report and "G" not in report


@pytest.mark.parametrize("change,match", [
    ("missing_link", "linkage is incomplete"),
    ("duplicate_flow_reference", "duplicate IDs"),
    ("duplicate_physical_load", "duplicate ID"),
    ("wrong_group_period", "crosses group"),
    ("missing_moisture", "mass balance residual"),
    ("missing_addition", "mass balance residual"),
    ("wrong_terminal_mass", "terminal mass differs"),
    ("sale_is_not_consumption", "destination.kind must be one of"),
    ("unknown_consumption", "outcome.status must be one of"),
    ("unsafe_consumption", "requires observed ingestion and safe evidence"),
    ("unproven_nutrition", "requires useful nutrition evidence"),
    ("duplicate_burden", "duplicate burden row"),
    ("missing_actor_burden", "missing actor-specific burden rows"),
    ("invalid_denominator", "feasible_max_service.value must be positive"),
    ("v_over_one", "V > 1"),
    ("omitted_consumption_flow", "exactly cover observed consumed flows"),
    ("self_verified_approval", "verifier must be distinct"),
    ("late_approval", "approval must predate"),
])
def test_preflight_rejects_false_completeness_or_unjustified_service(change: str, match: str) -> None:
    data = field_data()
    wash = _by_id(data["lots"], "control-pre-wash")
    process = _by_id(data["lots"], "control-pre-process")
    consumed = _by_id(data["flows"], "control-pre-consumed")
    if change == "missing_link":
        wash["output_flow_ids"].remove("control-pre-transfer")
    elif change == "duplicate_flow_reference":
        wash["output_flow_ids"].append("control-pre-transfer")
    elif change == "duplicate_physical_load":
        consumed["load_id"] = "load-control-pre-coproduct"
    elif change == "wrong_group_period":
        _by_id(data["flows"], "control-pre-transfer")["period"] = "post"
    elif change == "missing_moisture":
        wash["output_flow_ids"].remove("control-pre-wash-moisture")
        wash["observed_output_load_ids"].remove("load-control-pre-wash-moisture")
        data["flows"] = [f for f in data["flows"] if f["id"] != "control-pre-wash-moisture"]
    elif change == "missing_addition":
        process["input_flow_ids"].remove("control-pre-ingredient")
        process["observed_input_load_ids"].remove("load-control-pre-ingredient")
        data["flows"] = [f for f in data["flows"] if f["id"] != "control-pre-ingredient"]
    elif change == "wrong_terminal_mass":
        consumed["outcome"]["mass"]["value"] = 60
    elif change == "sale_is_not_consumption":
        consumed["destination"]["kind"] = "retail_sale"
    elif change == "unknown_consumption":
        consumed["outcome"]["status"] = "unknown"
    elif change == "unsafe_consumption":
        consumed["outcome"]["safety"]["status"] = "unsafe"
    elif change == "unproven_nutrition":
        consumed["outcome"]["nutrition"]["status"] = "unknown"
    elif change == "duplicate_burden":
        data["burdens"].append(copy.deepcopy(data["burdens"][0]))
    elif change == "missing_actor_burden":
        data["burdens"].pop()
    elif change == "invalid_denominator":
        data["service"]["rows"][0]["feasible_max_service"]["value"] = 0
    elif change == "v_over_one":
        data["service"]["rows"][0]["consumed_service"]["value"] = 91
    elif change == "omitted_consumption_flow":
        data["service"]["rows"][0]["consumption_flow_ids"] = []
    elif change == "self_verified_approval":
        data["service"]["equivalence"]["verified_by"] = "farmer"
    elif change == "late_approval":
        data["service"]["equivalence"]["approved_at_utc"] = "2026-03-01T00:00:00Z"
    with pytest.raises(FieldFlowError, match=match):
        audit_field_flows(data)


def test_distinct_fao_loads_cannot_be_spliced_into_one_chain() -> None:
    data = field_data(with_service=False)
    raw = _by_id(data["flows"], "control-pre-raw")
    transfer = _by_id(data["flows"], "control-pre-transfer")
    reject = _by_id(data["flows"], "control-pre-reject")
    ingredient = _by_id(data["flows"], "control-pre-ingredient")
    consumed = _by_id(data["flows"], "control-pre-consumed")
    coproduct = _by_id(data["flows"], "control-pre-coproduct")
    process_moisture = _by_id(data["flows"], "control-pre-process-moisture")
    wash = _by_id(data["lots"], "control-pre-wash")
    process = _by_id(data["lots"], "control-pre-process")
    # FAO table 15 tracked 5.0 -> 4.4 t for sorting and a *different*
    # 4,200 -> 4,180 kg load for transport. The second lot's observed input
    # identity cannot be silently replaced by the first load's output edge.
    raw["mass"] = _mass(5, "t", 0.0001)
    transfer["mass"] = _mass(4.4, "t", 0.0001)
    reject["mass"] = _mass(600)
    reject["outcome"]["mass"] = _mass(600)
    transfer["load_id"] = "fao-sorting-4400kg"
    wash["observed_output_load_ids"][0] = "fao-sorting-4400kg"
    process["input_flow_ids"].remove(ingredient["id"])
    process["observed_input_load_ids"].remove(ingredient["load_id"])
    process["output_flow_ids"].remove(process_moisture["id"])
    process["observed_output_load_ids"].remove(process_moisture["load_id"])
    data["flows"] = [flow for flow in data["flows"] if flow["id"] not in {ingredient["id"], process_moisture["id"]}]
    consumed["mass"] = _mass(4180)
    consumed["outcome"]["mass"] = _mass(4180)
    coproduct["kind"] = "residue"
    coproduct["destination"]["kind"] = "compost"
    coproduct["mass"] = _mass(20)
    coproduct["outcome"]["mass"] = _mass(20)
    process["observed_input_load_ids"][0] = "fao-transport-4200kg"
    with pytest.raises(FieldFlowError, match="observed physical load IDs do not match linked flows"):
        audit_field_flows(data)
    process["observed_input_load_ids"][0] = "fao-sorting-4400kg"
    with pytest.raises(FieldFlowError, match="mass balance residual 200 kg exceeds allowance"):
        audit_field_flows(data)


def test_mixed_mass_units_reconcile_after_conversion() -> None:
    data = field_data()
    raw = _by_id(data["flows"], "control-pre-raw")
    raw["mass"] = _mass(0.1, "t", 0.0001)
    transfer = _by_id(data["flows"], "control-pre-transfer")
    transfer["mass"] = _mass(95_000, "g", 100)
    report = audit_field_flows(data)
    balance = next(item for item in report["balances"] if item["lot_id"] == "control-pre-wash")
    assert float(balance["residual_kg"]) == 0


@pytest.mark.parametrize("evidence_path", ["lot", "flow", "destination", "outcome", "safety",
                                           "nutrition", "burden", "service"])
def test_historical_evidence_cannot_be_mislabeled_as_post(evidence_path: str) -> None:
    data = field_data()
    flow = _by_id(data["flows"], "control-post-consumed")
    sources = {
        "lot": _by_id(data["lots"], "control-post-process")["source"],
        "flow": flow["source"],
        "destination": flow["destination"]["source"],
        "outcome": flow["outcome"]["source"],
        "safety": flow["outcome"]["safety"]["source"],
        "nutrition": flow["outcome"]["nutrition"]["source"],
        "burden": next(row for row in data["burdens"]
                       if row["group_id"] == "control" and row["period"] == "post")["source"],
        "service": next(row for row in data["service"]["rows"]
                        if row["group_id"] == "control" and row["period"] == "post")["source"],
    }
    sources[evidence_path]["observed_at_utc"] = "2016-06-01T12:00:00Z"
    with pytest.raises(FieldFlowError, match="falls outside declared period"):
        audit_field_flows(data)


def test_assignment_cannot_follow_post_measurement() -> None:
    data = field_data()
    data["groups"][0]["assigned_at_utc"] = "2026-03-01T00:00:00Z"
    with pytest.raises(FieldFlowError, match="assignment must fall after pre and before post"):
        audit_field_flows(data)


def test_assignment_source_cannot_be_historical() -> None:
    data = field_data()
    data["groups"][0]["source"]["observed_at_utc"] = "2016-06-01T12:00:00Z"
    with pytest.raises(FieldFlowError, match="assignment source falls outside assignment interval"):
        audit_field_flows(data)


@pytest.mark.parametrize("source_name", ["tolerance_source", "service.equivalence.source"])
@pytest.mark.parametrize("observed_at", ["2026-02-01T00:00:00Z", "2026-02-01T06:00:00Z"])
def test_prospective_sources_must_precede_first_assignment(source_name: str, observed_at: str) -> None:
    data = field_data(with_service=source_name != "tolerance_source")
    data["groups"][1]["assigned_at_utc"] = "2026-02-01T12:00:00Z"
    source = (data["tolerance_source"] if source_name == "tolerance_source"
              else data["service"]["equivalence"]["source"])
    source["observed_at_utc"] = observed_at
    with pytest.raises(FieldFlowError, match="must predate first group assignment") as error:
        audit_field_flows(data)
    assert source_name in str(error.value)


def test_equivalence_record_cannot_predate_declared_approval() -> None:
    data = field_data()
    data["service"]["equivalence"]["source"]["observed_at_utc"] = "2025-11-30T23:59:59Z"
    with pytest.raises(FieldFlowError, match="service.equivalence.source predates its declared approval"):
        audit_field_flows(data)


def test_equivalence_record_may_be_observed_at_declared_approval() -> None:
    data = field_data()
    equivalence = data["service"]["equivalence"]
    equivalence["source"]["observed_at_utc"] = equivalence["approved_at_utc"]
    report = audit_field_flows(data)
    assert report["service_status"] == "declared_service_inputs_bounded_approval_unverified"
    assert report["criterion_3"]["status"] == "not_assessed"


def test_service_observation_must_follow_covered_consumption() -> None:
    data = field_data()
    row = next(item for item in data["service"]["rows"]
               if item["group_id"] == "control" and item["period"] == "post")
    row["source"]["observed_at_utc"] = "2026-03-01T12:00:00Z"
    with pytest.raises(FieldFlowError, match="service observation predates a covered consumption outcome"):
        audit_field_flows(data)


@pytest.mark.parametrize("change,match", [
    ("output_before_lot", "precedes its source lot operation"),
    ("internal_flow_after_child", "arrives after its target lot operation"),
    ("destination_before_output", "terminal chronology"),
    ("outcome_before_destination", "terminal chronology"),
])
def test_within_period_chronology_is_checked(change: str, match: str) -> None:
    data = field_data()
    consumed = _by_id(data["flows"], "control-post-consumed")
    if change == "output_before_lot":
        _by_id(data["lots"], "control-post-process")["source"]["observed_at_utc"] = "2026-03-20T12:00:00Z"
    elif change == "internal_flow_after_child":
        _by_id(data["flows"], "control-post-transfer")["source"]["observed_at_utc"] = "2026-03-20T12:00:00Z"
    elif change == "destination_before_output":
        consumed["source"]["observed_at_utc"] = "2026-03-20T12:00:00Z"
    elif change == "outcome_before_destination":
        consumed["outcome"]["source"]["observed_at_utc"] = "2026-03-01T12:00:00Z"
    with pytest.raises(FieldFlowError, match=match):
        audit_field_flows(data)


def test_exact_mass_arithmetic_does_not_erase_tiny_addition() -> None:
    data = field_data(with_service=False)
    data["balance_tolerance_kg"] = 0
    data["lots"] = []
    data["flows"] = []
    for group in ("control", "intervention"):
        for period in ("pre", "post"):
            prefix = f"{group}-{period}"
            lot_id = f"{prefix}-single-stage"
            mass = Decimal("1000000000000000000") if prefix == "control-pre" else Decimal(10)
            raw = _flow(prefix, "single-raw", None, lot_id, "feed", mass)
            eaten = _flow(prefix, "single-eaten", lot_id, None, "product", mass, "human_consumption")
            inputs = [raw]
            outputs = [eaten]
            if prefix == "control-pre":
                tiny = _flow(prefix, "tiny-ingredient", None, lot_id, "ingredient", Decimal("1e-18"))
                inputs.append(tiny)
            for flow in inputs + outputs:
                flow["mass"]["uncertainty"] = 0
                if flow["outcome"] is not None:
                    flow["outcome"]["mass"]["uncertainty"] = 0
            data["flows"].extend(inputs + outputs)
            data["lots"].append(_lot(prefix, "single-stage", inputs, outputs))
    with pytest.raises(FieldFlowError, match="residual 0.000000000000000001 kg exceeds allowance 0 kg"):
        audit_field_flows(data)


def test_short_declared_graph_does_not_claim_full_chain_coverage() -> None:
    data = field_data(with_service=False)
    data["lots"] = []
    data["flows"] = []
    for group in ("control", "intervention"):
        for period in ("pre", "post"):
            prefix = f"{group}-{period}"
            lot_id = f"{prefix}-single-stage"
            raw = _flow(prefix, "single-raw", None, lot_id, "feed", 10)
            eaten = _flow(prefix, "single-eaten", lot_id, None, "product", 10, "human_consumption")
            data["flows"].extend([raw, eaten])
            data["lots"].append(_lot(prefix, "single-stage", [raw], [eaten]))
    report = audit_field_flows(data)
    assert report["valid"] is True
    assert report["scope_status"] == "declared_graph_only_full_chain_not_checked"
    assert report["criterion_3"]["status"] == "not_assessed"


def test_cli_reads_without_modifying_input_and_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "field.json"
    original = json.dumps(field_data(), ensure_ascii=False).encode("utf-8")
    path.write_bytes(original)
    valid = subprocess.run([sys.executable, str(SCRIPT), str(path)], text=True,
                           capture_output=True, check=False)
    assert valid.returncode == 0
    assert json.loads(valid.stdout)["criterion_3"]["status"] == "not_assessed"
    assert path.read_bytes() == original
    invalid = subprocess.run([sys.executable, str(SCRIPT), "-"], input='{"schema":1,"schema":1}',
                             text=True, capture_output=True, check=False)
    assert invalid.returncode == 2
    assert "duplicate JSON object key" in json.loads(invalid.stdout)["error"]


@pytest.mark.parametrize("source", [
    '{"schema":' + "9" * 5000 + "}",
    "[" * 1200 + "0" + "]" * 1200,
])
def test_cli_returns_structured_error_for_extreme_json(source: str) -> None:
    result = subprocess.run([sys.executable, str(SCRIPT), "-"], input=source,
                            text=True, capture_output=True, check=False)
    assert result.returncode == 2
    output = json.loads(result.stdout)
    assert output["valid"] is False
    assert output["classification"] == "field_flow_preflight_declared_only"
    assert output["error"]


def test_cli_catches_extreme_decimal_exponent_without_traceback() -> None:
    source = json.dumps(field_data()).replace('"balance_tolerance_kg": 0.05',
                                              '"balance_tolerance_kg": 1e999999999')
    assert '"balance_tolerance_kg": 1e999999999' in source
    result = subprocess.run([sys.executable, str(SCRIPT), "-"], input=source,
                            text=True, capture_output=True, check=False)
    assert result.returncode == 2
    output = json.loads(result.stdout)
    assert output["valid"] is False
    assert "magnitude is outside supported numeric range" in output["error"]
    assert not result.stderr
