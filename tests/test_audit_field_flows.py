"""Synthetic field-flow preflight controls; none is an observed field result."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_field_flows.py"
sys.path.insert(0, str(SCRIPT.parent))
from audit_field_flows import FieldFlowError, _lineage_bounds, audit_field_flows  # noqa: E402


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
    physical_load_id = load_id or f"load-{flow_id}"
    outcome = None
    dest = None
    if destination is not None:
        dest = {"kind": destination, "source": _evidence(flow_id + "-destination")}
        consumed = destination == "human_consumption"
        safety_source = _evidence(flow_id + "-safety")
        nutrition = None
        if consumed:
            safety_source["load_id"] = physical_load_id
            nutrition_source = _evidence(flow_id + "-nutrition")
            nutrition_source["load_id"] = physical_load_id
            nutrition = {"status": "useful", "source": nutrition_source}
        outcome = {
            "status": "observed_consumed" if consumed else "observed_other",
            "mass": _mass(value, unit), "source": _evidence(flow_id + "-outcome"),
            "safety": {"status": "safe" if consumed else "not_assessed",
                       "source": safety_source},
            "nutrition": nutrition,
        }
    return {
        "id": flow_id, "load_id": physical_load_id,
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


def _as_schema2(data: dict[str, Any]) -> dict[str, Any]:
    """Bind each declared terminal observation to its load in schema 2 fixtures."""
    data["schema"] = 2
    for flow in data["flows"]:
        if flow["to_lot_id"] is None:
            flow["destination"]["source"]["load_id"] = flow["load_id"]
            flow["outcome"]["source"]["load_id"] = flow["load_id"]
    return data


def field_data_with_stage_witnesses() -> dict[str, Any]:
    """Add a synthetic serial scope path to every schema-1 group-period."""
    data = field_data()
    for group in ("control", "intervention"):
        for period in ("pre", "post"):
            prefix = f"{group}-{period}"
            harvest = _by_id(data["lots"], f"{prefix}-wash")
            process = _by_id(data["lots"], f"{prefix}-process")
            transfer = _by_id(data["flows"], f"{prefix}-transfer")
            consumed = _by_id(data["flows"], f"{prefix}-consumed")
            harvest["stage"] = "harvest"
            harvest["stage_role"] = "production"
            process["stage_role"] = "transformation"

            storage_id = f"{prefix}-logistics-a"
            transport_id = f"{prefix}-logistics-b"
            finish_id = f"{prefix}-finish"
            transfer["to_lot_id"] = storage_id
            stored = _flow(prefix, "stored", storage_id, transport_id, "product", 95)
            transported = _flow(prefix, "transported", transport_id, process["id"], "product", 95)
            storage = _lot(prefix, "logistics-a", [transfer], [stored])
            storage["stage_role"] = "storage"
            transport = _lot(prefix, "logistics-b", [stored], [transported])
            transport["stage_role"] = "transport"
            process["input_flow_ids"].remove(transfer["id"])
            process["input_flow_ids"].append(transported["id"])
            process["observed_input_load_ids"].remove(transfer["load_id"])
            process["observed_input_load_ids"].append(transported["load_id"])

            consumed["to_lot_id"] = finish_id
            consumed["destination"] = None
            consumed["outcome"] = None
            finished = _flow(prefix, "finished", finish_id, None, "product", 70, "human_consumption")
            finish = _lot(prefix, "finish", [consumed], [finished])
            finish["stage_role"] = "transformation"
            data["lots"].extend([storage, transport, finish])
            data["flows"].extend([stored, transported, finished])
            service_row = next(row for row in data["service"]["rows"]
                               if (row["group_id"], row["period"]) == (group, period))
            service_row["consumption_flow_ids"] = [finished["id"]]
    return _as_schema2(data)


def _by_id(rows: list[dict[str, Any]], item_id: str) -> dict[str, Any]:
    return next(row for row in rows if row["id"] == item_id)


def _allocation(data: dict[str, Any], incoming: str, outgoing: str,
                amount: float, *, unit: str = "kg") -> dict[str, Any]:
    source = _evidence(f"allocation-{incoming}-{outgoing}")
    source["input_load_id"] = _by_id(data["flows"], incoming)["load_id"]
    source["output_load_id"] = _by_id(data["flows"], outgoing)["load_id"]
    return {
        "input_flow_id": incoming, "output_flow_id": outgoing,
        "mass": _mass(amount, unit, uncertainty=0), "source": source,
    }


def field_data_with_schema3_allocations() -> dict[str, Any]:
    """Exact nominal accounting for a synthetic full-stage fixture."""
    data = field_data_with_stage_witnesses()
    data["schema"] = 3
    for group in ("control", "intervention"):
        for period in ("pre", "post"):
            prefix = f"{group}-{period}"

            def a(incoming: str, outgoing: str, amount: float) -> dict[str, Any]:
                return _allocation(data, f"{prefix}-{incoming}", f"{prefix}-{outgoing}", amount)

            _by_id(data["lots"], f"{prefix}-wash")["allocations"] = [
                a("raw", "transfer", 95), a("raw", "reject", 5),
                a("water", "wash-moisture", 10),
            ]
            _by_id(data["lots"], f"{prefix}-logistics-a")["allocations"] = [
                a("transfer", "stored", 95),
            ]
            _by_id(data["lots"], f"{prefix}-logistics-b")["allocations"] = [
                a("stored", "transported", 95),
            ]
            _by_id(data["lots"], f"{prefix}-process")["allocations"] = [
                a("transported", "consumed", 70),
                a("transported", "coproduct", 25),
                a("ingredient", "process-moisture", 5),
            ]
            _by_id(data["lots"], f"{prefix}-finish")["allocations"] = [
                a("consumed", "finished", 70),
            ]
    return data


def _extend_final_mix(data: dict[str, Any], *, long_to_consumption: int) -> None:
    prefix = "control-post"
    finish = _by_id(data["lots"], f"{prefix}-finish")
    late = _flow(prefix, "late-ingredient", None, finish["id"], "ingredient", 70)
    compost = _flow(prefix, "late-compost", finish["id"], None, "residue", 70, "compost")
    data["flows"].extend([late, compost])
    finish["input_flow_ids"].append(late["id"])
    finish["observed_input_load_ids"].append(late["load_id"])
    finish["output_flow_ids"].append(compost["id"])
    finish["observed_output_load_ids"].append(compost["load_id"])
    compost["destination"]["source"]["load_id"] = compost["load_id"]
    compost["outcome"]["source"]["load_id"] = compost["load_id"]
    finished = f"{prefix}-finished"
    before = f"{prefix}-consumed"
    finish["allocations"] = [
        _allocation(data, before, finished, long_to_consumption),
        _allocation(data, before, compost["id"], 70 - long_to_consumption),
        _allocation(data, late["id"], finished, 70 - long_to_consumption),
        _allocation(data, late["id"], compost["id"], long_to_consumption),
    ] if 0 < long_to_consumption < 70 else [
        _allocation(data, before, compost["id"], 70),
        _allocation(data, late["id"], finished, 70),
    ]


def _set_flow_mass(flow: dict[str, Any], value: int) -> None:
    flow["mass"]["value"] = value
    if flow["outcome"] is not None:
        flow["outcome"]["mass"]["value"] = value


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
    assert report["stage_witnesses"] == []
    assert "V" not in report and "G" not in report


def test_complete_graph_without_approved_equivalence_does_not_compute_service() -> None:
    report = audit_field_flows(field_data(with_service=False))
    assert report["valid"] is True
    assert report["service_status"] == "not_assessed_no_declared_equivalence"
    assert "V" not in report and "G" not in report


def _as_service_schema2(data: dict[str, Any]) -> dict[str, Any]:
    data["service"]["schema"] = 2
    for row in data["service"]["rows"]:
        row["source"]["record_sha256"] = "a" * 64
    return data


def test_service_schema2_requires_digest_and_keeps_preflight_byte_claim_false() -> None:
    data = _as_service_schema2(field_data())
    report = audit_field_flows(data)
    assert report["service_status"] == "declared_service_inputs_bounded_approval_unverified"
    assert report["service_v_input_byte_bound"] is False
    assert "service_v_input_byte_bound" not in audit_field_flows(field_data())


@pytest.mark.parametrize("change, message", [
    ("missing_digest", "missing keys"),
    ("uppercase_digest", "record_sha256 must be lowercase SHA-256"),
    ("duplicate_reference", "repeats a service digest and locator reference"),
    ("unsupported_schema", "service.schema must be integer 2"),
])
def test_service_schema2_rejects_unbound_or_duplicate_sources(change: str, message: str) -> None:
    data = _as_service_schema2(field_data())
    rows = data["service"]["rows"]
    if change == "missing_digest":
        del rows[0]["source"]["record_sha256"]
    elif change == "uppercase_digest":
        rows[0]["source"]["record_sha256"] = "A" * 64
    elif change == "duplicate_reference":
        rows[1]["source"]["locator"] = rows[0]["source"]["locator"]
    else:
        data["service"]["schema"] = 1
    with pytest.raises(FieldFlowError, match=message):
        audit_field_flows(data)


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
        for evidence_kind in ("safety", "nutrition"):
            consumed["outcome"][evidence_kind]["source"]["load_id"] = consumed["load_id"]
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


@pytest.mark.parametrize("evidence_kind", ["safety", "nutrition"])
def test_consumption_evidence_cannot_predate_terminal_output(evidence_kind: str) -> None:
    data = field_data()
    consumed = _by_id(data["flows"], "control-post-consumed")
    consumed["outcome"][evidence_kind]["source"]["observed_at_utc"] = "2026-03-15T11:59:59Z"
    with pytest.raises(
        FieldFlowError,
        match=rf"outcome\.{evidence_kind}\.source\.observed_at_utc predates terminal output flow",
    ):
        audit_field_flows(data)


@pytest.mark.parametrize("observed_at", ["2026-03-15T12:00:00Z", "2026-03-16T12:00:00Z"])
def test_consumption_evidence_may_be_at_output_or_after_consumption(observed_at: str) -> None:
    data = field_data()
    consumed = _by_id(data["flows"], "control-post-consumed")
    assert consumed["source"]["observed_at_utc"] == consumed["outcome"]["source"]["observed_at_utc"]
    for evidence_kind in ("safety", "nutrition"):
        assert consumed["outcome"][evidence_kind]["source"]["load_id"] == consumed["load_id"]
        consumed["outcome"][evidence_kind]["source"]["observed_at_utc"] = observed_at
    assert audit_field_flows(data)["valid"] is True


@pytest.mark.parametrize("evidence_kind", ["safety", "nutrition"])
@pytest.mark.parametrize("change,match", [
    ("copied_other_group", r"load_id does not match terminal flow\.load_id"),
    ("missing_load_id", r"missing keys \['load_id'\]"),
])
def test_consumption_evidence_must_identify_its_own_physical_load(
    evidence_kind: str, change: str, match: str
) -> None:
    data = field_data()
    consumed = _by_id(data["flows"], "control-post-consumed")
    if change == "copied_other_group":
        other = _by_id(data["flows"], "intervention-post-consumed")
        consumed["outcome"][evidence_kind]["source"] = copy.deepcopy(other["outcome"][evidence_kind]["source"])
    else:
        consumed["outcome"][evidence_kind]["source"].pop("load_id")
    with pytest.raises(FieldFlowError, match=rf"outcome\.{evidence_kind}\.source.*{match}"):
        audit_field_flows(data)


@pytest.mark.parametrize("source_location", ["destination", "outcome"])
@pytest.mark.parametrize("target_id,other_group_id,same_group_id", [
    ("control-post-finished", "intervention-post-finished", "control-post-coproduct"),
    ("control-post-reject", "intervention-post-reject", "control-post-wash-moisture"),
])
@pytest.mark.parametrize("change", ["copied_other_group", "copied_same_group", "missing_load_id"])
def test_schema2_terminal_sources_identify_their_own_physical_load(
    source_location: str, target_id: str, other_group_id: str, same_group_id: str, change: str
) -> None:
    data = field_data_with_stage_witnesses()
    target = _by_id(data["flows"], target_id)[source_location]["source"]
    if change == "missing_load_id":
        target.pop("load_id")
        expected = r"missing keys \['load_id'\]"
    else:
        donor_id = other_group_id if change == "copied_other_group" else same_group_id
        donor = _by_id(data["flows"], donor_id)[source_location]["source"]
        target.update(copy.deepcopy(donor))
        expected = r"load_id does not match terminal flow\.load_id"
    with pytest.raises(FieldFlowError, match=rf"{source_location}\.source.*{expected}"):
        audit_field_flows(data)


def test_schema2_terminal_sources_allow_retrospective_observation_of_the_same_load() -> None:
    data = field_data_with_stage_witnesses()
    flow = _by_id(data["flows"], "control-post-finished")
    flow["destination"]["source"]["observed_at_utc"] = "2026-03-15T13:00:00Z"
    flow["outcome"]["source"]["observed_at_utc"] = "2026-03-16T12:00:00Z"
    assert flow["destination"]["source"]["load_id"] == flow["load_id"]
    assert flow["outcome"]["source"]["load_id"] == flow["load_id"]
    service_row = next(row for row in data["service"]["rows"]
                       if (row["group_id"], row["period"]) == ("control", "post"))
    service_row["source"]["observed_at_utc"] = "2026-03-17T12:00:00Z"
    assert audit_field_flows(data)["valid"] is True


def test_schema1_keeps_unbound_terminal_sources_and_limited_scope() -> None:
    data = field_data()
    target = _by_id(data["flows"], "control-post-consumed")
    donor = _by_id(data["flows"], "intervention-post-consumed")
    assert "load_id" not in target["destination"]["source"]
    target["outcome"]["source"] = copy.deepcopy(donor["outcome"]["source"])
    report = audit_field_flows(data)
    assert report["valid"] is True
    assert report["scope_status"] == "declared_graph_only_full_chain_not_checked"


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


def test_schema2_reports_a_continuous_declared_stage_witness() -> None:
    report = audit_field_flows(field_data_with_stage_witnesses())
    assert report["valid"] is True
    assert report["schema"] == 2
    assert report["scope_status"] == "declared_stage_witness_per_consumed_flow_only"
    assert len(report["stage_witnesses"]) == 4
    assert report["stage_witnesses"][0] == {
        "group_id": "control", "period": "post",
        "lot_ids": ["control-post-wash", "control-post-logistics-a",
                    "control-post-logistics-b", "control-post-process", "control-post-finish"],
        "consumption_flow_id": "control-post-finished",
    }
    assert report["criterion_3"]["status"] == "not_assessed"
    assert "physical identity" in report["notice"]


def test_schema2_rejects_short_consumed_branch_beside_a_complete_path() -> None:
    data = field_data_with_stage_witnesses()
    prefix = "control-post"
    wash = _by_id(data["lots"], f"{prefix}-wash")
    raw = _flow(prefix, "short-raw", None, wash["id"], "feed", 10)
    short = _flow(prefix, "short-eaten", wash["id"], None, "product", 10,
                  "human_consumption")
    wash["input_flow_ids"].append(raw["id"])
    wash["observed_input_load_ids"].append(raw["load_id"])
    wash["output_flow_ids"].append(short["id"])
    wash["observed_output_load_ids"].append(short["load_id"])
    data["flows"].extend([raw, short])
    service_row = next(row for row in data["service"]["rows"]
                       if (row["group_id"], row["period"]) == ("control", "post"))
    service_row["consumption_flow_ids"].append(short["id"])
    service_row["consumed_service"]["value"] = 80
    with pytest.raises(FieldFlowError, match=r"lacks a continuous declared path.*control-post-short-eaten"):
        audit_field_flows(_as_schema2(data))


def test_schema2_reports_each_consumed_flow_across_multiple_complete_branches() -> None:
    data = field_data_with_stage_witnesses()
    prefix = "control-post"
    stages = ["branch-production", "branch-storage", "branch-transport",
              "branch-first-transform", "branch-second-transform"]
    roles = ["production", "storage", "transport", "transformation", "transformation"]
    lot_ids = [f"{prefix}-{stage}" for stage in stages]
    raw = _flow(prefix, "branch-raw", None, lot_ids[0], "feed", 10)
    links = [_flow(prefix, f"branch-link-{index}", lot_ids[index], lot_ids[index + 1],
                   "product", 10) for index in range(len(stages) - 1)]
    eaten = _flow(prefix, "branch-eaten", lot_ids[-1], None, "product", 10,
                  "human_consumption")
    branch_flows = [raw, *links, eaten]
    data["flows"].extend(branch_flows)
    for index, (stage, role) in enumerate(zip(stages, roles, strict=True)):
        lot = _lot(prefix, stage, [branch_flows[index]], [branch_flows[index + 1]])
        lot["stage_role"] = role
        data["lots"].append(lot)
    service_row = next(row for row in data["service"]["rows"]
                       if (row["group_id"], row["period"]) == ("control", "post"))
    service_row["consumption_flow_ids"].append(eaten["id"])
    service_row["consumed_service"]["value"] = 80
    report = audit_field_flows(_as_schema2(data))
    assert report["valid"] is True
    assert report["counts"]["consumed_flows"] == 5
    assert len(report["stage_witnesses"]) == 5
    witnesses = {row["consumption_flow_id"]: row["lot_ids"] for row in report["stage_witnesses"]}
    assert witnesses[eaten["id"]] == lot_ids
    assert witnesses["control-post-finished"] != lot_ids


def test_schema2_accepts_transport_before_storage_on_same_path() -> None:
    data = field_data_with_stage_witnesses()
    for lot in data["lots"]:
        if lot["stage_role"] == "storage":
            lot["stage_role"] = "transport"
        elif lot["stage_role"] == "transport":
            lot["stage_role"] = "storage"
    assert audit_field_flows(data)["scope_status"] == "declared_stage_witness_per_consumed_flow_only"


def test_schema2_accepts_transformation_before_storage_and_transport() -> None:
    data = field_data(with_service=False)
    data["lots"] = []
    data["flows"] = []
    stages = ["production", "first-transform", "storage", "transport", "second-transform"]
    roles = ["production", "transformation", "storage", "transport", "transformation"]
    for group in ("control", "intervention"):
        for period in ("pre", "post"):
            prefix = f"{group}-{period}"
            lot_ids = [f"{prefix}-{stage}" for stage in stages]
            raw = _flow(prefix, "raw", None, lot_ids[0], "feed", 10)
            links = [_flow(prefix, f"link-{index}", lot_ids[index], lot_ids[index + 1], "product", 10)
                     for index in range(len(stages) - 1)]
            eaten = _flow(prefix, "eaten", lot_ids[-1], None, "product", 10, "human_consumption")
            path_flows = [raw, *links, eaten]
            data["flows"].extend(path_flows)
            for index, (stage, role) in enumerate(zip(stages, roles, strict=True)):
                lot = _lot(prefix, stage, [path_flows[index]], [path_flows[index + 1]])
                lot["stage_role"] = role
                data["lots"].append(lot)
    report = audit_field_flows(_as_schema2(data))
    assert report["valid"] is True
    assert report["stage_witnesses"][0]["lot_ids"] == [f"control-post-{stage}" for stage in stages]
    assert report["criterion_3"]["status"] == "not_assessed"


@pytest.mark.parametrize("change,match", [
    ("missing_role", "lacks a continuous declared path"),
    ("only_one_transformation", "lacks a continuous declared path"),
    ("invalid_role", "stage_role must be one of"),
    ("missing_tag", "missing keys.*stage_role"),
])
def test_schema2_rejects_missing_or_invalid_stage_coverage(change: str, match: str) -> None:
    data = field_data_with_stage_witnesses()
    target = _by_id(data["lots"], "control-pre-logistics-b" if change in {"missing_role", "invalid_role", "missing_tag"}
                    else "control-pre-finish")
    if change == "missing_role":
        target["stage_role"] = "other"
    elif change == "only_one_transformation":
        target["stage_role"] = "other"
    elif change == "invalid_role":
        target["stage_role"] = "retail"
    else:
        del target["stage_role"]
    with pytest.raises(FieldFlowError, match=match):
        audit_field_flows(data)


def test_schema2_rejects_a_short_graph_even_if_all_mass_and_outcomes_balance() -> None:
    data = field_data(with_service=False)
    for lot in data["lots"]:
        lot["stage_role"] = "production" if lot["id"].endswith("-wash") else "transformation"
    with pytest.raises(FieldFlowError, match="lacks a continuous declared path"):
        audit_field_flows(_as_schema2(data))


def test_schema2_cannot_join_stage_roles_on_disjoint_coproduct_branches() -> None:
    data = field_data(with_service=False)
    data["lots"] = []
    data["flows"] = []
    for group in ("control", "intervention"):
        for period in ("pre", "post"):
            prefix = f"{group}-{period}"
            production = f"{prefix}-production"
            storage = f"{prefix}-storage"
            transport = f"{prefix}-transport"
            a_first = f"{prefix}-a-first"
            a_second = f"{prefix}-a-second"
            b_first = f"{prefix}-b-first"
            b_second = f"{prefix}-b-second"
            raw = _flow(prefix, "raw", None, production, "feed", 100)
            to_storage = _flow(prefix, "to-storage", production, storage, "product", 60)
            to_transport = _flow(prefix, "to-transport", production, transport, "coproduct", 40)
            a1 = _flow(prefix, "a1", storage, a_first, "product", 60)
            a2 = _flow(prefix, "a2", a_first, a_second, "product", 60)
            a_eaten = _flow(prefix, "a-eaten", a_second, None, "product", 60, "human_consumption")
            b1 = _flow(prefix, "b1", transport, b_first, "product", 40)
            b2 = _flow(prefix, "b2", b_first, b_second, "product", 40)
            b_eaten = _flow(prefix, "b-eaten", b_second, None, "product", 40, "human_consumption")
            data["flows"].extend([raw, to_storage, to_transport, a1, a2, a_eaten, b1, b2, b_eaten])
            stages = [
                (_lot(prefix, "production", [raw], [to_storage, to_transport]), "production"),
                (_lot(prefix, "storage", [to_storage], [a1]), "storage"),
                (_lot(prefix, "transport", [to_transport], [b1]), "transport"),
                (_lot(prefix, "a-first", [a1], [a2]), "transformation"),
                (_lot(prefix, "a-second", [a2], [a_eaten]), "transformation"),
                (_lot(prefix, "b-first", [b1], [b2]), "transformation"),
                (_lot(prefix, "b-second", [b2], [b_eaten]), "transformation"),
            ]
            for lot, role in stages:
                lot["stage_role"] = role
                data["lots"].append(lot)
    with pytest.raises(FieldFlowError, match="lacks a continuous declared path"):
        audit_field_flows(_as_schema2(data))


def test_schema2_cannot_hide_a_consumed_branch_with_no_production_ancestor() -> None:
    data = field_data_with_stage_witnesses()
    del data["service"]
    prefix = "control-pre"
    lot_id = f"{prefix}-untraced"
    raw = _flow(prefix, "untraced-raw", None, lot_id, "feed", 10)
    eaten = _flow(prefix, "untraced-eaten", lot_id, None, "product", 10, "human_consumption")
    lot = _lot(prefix, "untraced", [raw], [eaten])
    lot["stage_role"] = "other"
    data["flows"].extend([raw, eaten])
    data["lots"].append(lot)
    with pytest.raises(FieldFlowError, match="not reachable from externally fed production"):
        audit_field_flows(_as_schema2(data))


def test_schema3_conservative_declared_mass_lineage_and_legacy_contracts() -> None:
    data = field_data_with_schema3_allocations()
    report = audit_field_flows(data)
    assert report["schema"] == 3 and report["valid"] is True
    assert report["scope_status"] == "declared_conservative_mass_lineage_per_consumed_flow"
    assert len(report["lineage_bounds"]) == report["counts"]["consumed_flows"] == 4
    assert all(Decimal(row["guaranteed_stage_mass_kg"]) > 0 for row in report["lineage_bounds"])
    assert report["criterion_3"]["status"] == "not_assessed"
    assert "V" not in report and "G" not in report

    legacy = copy.deepcopy(data)
    legacy["schema"] = 2
    for lot in legacy["lots"]:
        del lot["allocations"]
    old = audit_field_flows(legacy)
    assert old["scope_status"] == "declared_stage_witness_per_consumed_flow_only"
    assert "lineage_bounds" not in old


@pytest.mark.parametrize("long_to_consumption,passes", [(0, False), (20, True)])
def test_schema3_distinguishes_late_ingredient_from_long_path(
    long_to_consumption: int, passes: bool,
) -> None:
    data = field_data_with_schema3_allocations()
    _extend_final_mix(data, long_to_consumption=long_to_consumption)

    legacy = copy.deepcopy(data)
    legacy["schema"] = 2
    for lot in legacy["lots"]:
        del lot["allocations"]
    assert audit_field_flows(legacy)["valid"] is True

    if passes:
        report = audit_field_flows(data)
        bound = next(row for row in report["lineage_bounds"]
                     if row["consumption_flow_id"] == "control-post-finished")
        assert Decimal(bound["guaranteed_stage_mass_kg"]) > 0
    else:
        with pytest.raises(FieldFlowError, match="control-post-finished"):
            audit_field_flows(data)


@pytest.mark.parametrize("long_into_finish,passes", [(1, False), (2, True)])
def test_schema3_does_not_splice_different_material_across_serial_mixes(
    long_into_finish: int, passes: bool,
) -> None:
    data = field_data_with_schema3_allocations()
    prefix = "control-post"
    for flow in data["flows"]:
        if (flow["group_id"], flow["period"]) == ("control", "post"):
            flow["mass"]["uncertainty"] = 0
            if flow["outcome"] is not None:
                flow["outcome"]["mass"]["uncertainty"] = 0
    ingredient = _by_id(data["flows"], f"{prefix}-ingredient")
    coproduct = _by_id(data["flows"], f"{prefix}-coproduct")
    _set_flow_mass(ingredient, 70 - long_into_finish)
    _set_flow_mass(coproduct, 90 - long_into_finish)
    process = _by_id(data["lots"], f"{prefix}-process")
    process["allocations"] = [
        _allocation(data, f"{prefix}-transported", f"{prefix}-consumed", long_into_finish),
        _allocation(data, f"{prefix}-transported", f"{prefix}-coproduct", 90 - long_into_finish),
        _allocation(data, f"{prefix}-transported", f"{prefix}-process-moisture", 5),
        _allocation(data, f"{prefix}-ingredient", f"{prefix}-consumed", 70 - long_into_finish),
    ]
    finish = _by_id(data["lots"], f"{prefix}-finish")
    finished = _by_id(data["flows"], f"{prefix}-finished")
    _set_flow_mass(finished, 69)
    compost = _flow(prefix, "serial-compost", finish["id"], None, "residue", 1, "compost")
    compost["mass"]["uncertainty"] = 0
    compost["outcome"]["mass"]["uncertainty"] = 0
    compost["destination"]["source"]["load_id"] = compost["load_id"]
    compost["outcome"]["source"]["load_id"] = compost["load_id"]
    data["flows"].append(compost)
    finish["output_flow_ids"].append(compost["id"])
    finish["observed_output_load_ids"].append(compost["load_id"])
    finish["allocations"] = [
        _allocation(data, f"{prefix}-consumed", finished["id"], 69),
        _allocation(data, f"{prefix}-consumed", compost["id"], 1),
    ]
    for row in data["service"]["rows"]:
        if (row["group_id"], row["period"]) == ("control", "post"):
            row["consumed_service"]["value"] = 69

    legacy = copy.deepcopy(data)
    legacy["schema"] = 2
    for lot in legacy["lots"]:
        del lot["allocations"]
    assert audit_field_flows(legacy)["valid"] is True
    if passes:
        result = audit_field_flows(data)
        assert any(row["consumption_flow_id"] == finished["id"]
                   and Decimal(row["guaranteed_stage_mass_kg"]) > 0
                   for row in result["lineage_bounds"])
    else:
        with pytest.raises(FieldFlowError, match="control-post-finished"):
            audit_field_flows(data)


def test_schema3_rejects_duplicate_or_incomplete_nominal_allocations() -> None:
    data = field_data_with_schema3_allocations()
    storage = _by_id(data["lots"], "control-post-logistics-a")
    row = storage["allocations"][0]
    row["mass"]["value"] = 40
    duplicate = copy.deepcopy(row)
    duplicate["mass"]["value"] = 55
    storage["allocations"].append(duplicate)
    with pytest.raises(FieldFlowError, match="duplicate"):
        audit_field_flows(data)

    data = field_data_with_schema3_allocations()
    row = _by_id(data["lots"], "control-post-logistics-a")["allocations"][0]
    row["mass"]["value"] = 94
    with pytest.raises(FieldFlowError, match="allocation"):
        audit_field_flows(data)


def test_schema3_allocation_units_and_load_binding() -> None:
    data = field_data_with_schema3_allocations()
    _by_id(data["lots"], "control-post-logistics-a")["allocations"][0]["mass"] = _mass(
        95000, "g", uncertainty=0,
    )
    _by_id(data["lots"], "control-post-logistics-b")["allocations"][0]["mass"] = _mass(
        0.095, "t", uncertainty=0,
    )
    assert audit_field_flows(data)["valid"] is True
    row = _by_id(data["lots"], "control-post-logistics-a")["allocations"][0]
    row["source"]["input_load_id"] = "load-from-another-flow"
    with pytest.raises(FieldFlowError, match="input_load_id"):
        audit_field_flows(data)


def test_schema3_uses_exact_complement_to_tighten_uncertain_allocation() -> None:
    data = field_data_with_schema3_allocations()
    _extend_final_mix(data, long_to_consumption=20)
    finish = _by_id(data["lots"], "control-post-finish")
    long_to_finished = next(row for row in finish["allocations"]
                            if (row["input_flow_id"], row["output_flow_id"]) ==
                            ("control-post-consumed", "control-post-finished"))
    long_to_finished["mass"]["uncertainty"] = 20
    report = audit_field_flows(data)
    bound = next(row for row in report["lineage_bounds"]
                 if row["consumption_flow_id"] == "control-post-finished")
    assert bound["guaranteed_stage_mass_kg"] == "20"


def test_schema3_does_not_treat_ambiguous_positive_nominal_as_guaranteed() -> None:
    data = field_data_with_schema3_allocations()
    _extend_final_mix(data, long_to_consumption=20)
    finish = _by_id(data["lots"], "control-post-finish")
    for row in finish["allocations"]:
        row["mass"]["uncertainty"] = 20
    with pytest.raises(FieldFlowError, match="control-post-finished"):
        audit_field_flows(data)


def test_schema3_uses_exact_incident_allocations_to_tighten_flow_mass() -> None:
    data = field_data_with_schema3_allocations()
    _by_id(data["flows"], "control-post-raw")["mass"]["uncertainty"] = 100
    report = audit_field_flows(data)
    bound = next(row for row in report["lineage_bounds"]
                 if row["consumption_flow_id"] == "control-post-finished")
    assert Decimal(bound["guaranteed_stage_mass_kg"]) > 0


def test_schema3_preserves_union_of_branches_before_common_later_stages() -> None:
    roles = {
        "produce": "production", "early-storage": "storage",
        "early-transport": "transport", "direct": "other", "merge": "other",
        "split": "other", "late-storage": "storage", "late-transport": "transport",
        "transform-a": "transformation", "transform-b": "transformation",
    }
    lots = {lot_id: {"stage_role": role} for lot_id, role in roles.items()}
    flow_rows = [
        ("origin", None, "produce", "feed", 100),
        ("p-store", "produce", "early-storage", "product", 40),
        ("p-transport", "produce", "early-transport", "product", 40),
        ("p-direct", "produce", "direct", "product", 20),
        ("stored", "early-storage", "merge", "product", 40),
        ("transported", "early-transport", "merge", "product", 40),
        ("directed", "direct", "merge", "product", 20),
        ("mixed", "merge", "split", "product", 100),
        ("common", "split", "late-storage", "product", 60),
        ("residual", "split", None, "residue", 40),
        ("stored-again", "late-storage", "late-transport", "product", 60),
        ("transported-again", "late-transport", "transform-a", "product", 60),
        ("once", "transform-a", "transform-b", "product", 60),
        ("consumed", "transform-b", None, "product", 60),
    ]
    flows = {
        flow_id: {"from": source, "to": target, "kind": kind,
                  "mass": (Fraction(amount), Fraction(0))}
        for flow_id, source, target, kind, amount in flow_rows
    }
    allocation_rows = {
        "produce": [("origin", "p-store", 40), ("origin", "p-transport", 40),
                    ("origin", "p-direct", 20)],
        "early-storage": [("p-store", "stored", 40)],
        "early-transport": [("p-transport", "transported", 40)],
        "direct": [("p-direct", "directed", 20)],
        "merge": [("stored", "mixed", 40), ("transported", "mixed", 40),
                  ("directed", "mixed", 20)],
        "split": [("mixed", "common", 60), ("mixed", "residual", 40)],
        "late-storage": [("common", "stored-again", 60)],
        "late-transport": [("stored-again", "transported-again", 60)],
        "transform-a": [("transported-again", "once", 60)],
        "transform-b": [("once", "consumed", 60)],
    }
    allocations = {
        lot_id: [(incoming, outgoing, Fraction(amount), Fraction(0))
                 for incoming, outgoing, amount in rows]
        for lot_id, rows in allocation_rows.items()
    }
    bounds = _lineage_bounds(lots, flows, {("control", "post"): {"consumed"}},
                             list(roles), allocations)
    assert bounds[0]["guaranteed_stage_mass_kg"] == "60"


def test_schema3_cli_reports_bounds_without_modifying_input(tmp_path: Path) -> None:
    path = tmp_path / "field-schema3.json"
    original = json.dumps(field_data_with_schema3_allocations(), ensure_ascii=False).encode("utf-8")
    path.write_bytes(original)
    completed = subprocess.run([sys.executable, str(SCRIPT), str(path)], text=True,
                               capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["schema"] == 3
    assert report["scope_status"] == "declared_conservative_mass_lineage_per_consumed_flow"
    assert len(report["lineage_bounds"]) == 4
    assert report["criterion_3"]["status"] == "not_assessed"
    assert path.read_bytes() == original


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


def test_cli_accepts_schema2_and_reports_declared_witnesses(tmp_path: Path) -> None:
    path = tmp_path / "field-schema2.json"
    original = json.dumps(field_data_with_stage_witnesses(), ensure_ascii=False).encode("utf-8")
    path.write_bytes(original)
    result = subprocess.run([sys.executable, str(SCRIPT), str(path)], text=True,
                            capture_output=True, check=False)
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["schema"] == 2
    assert report["scope_status"] == "declared_stage_witness_per_consumed_flow_only"
    assert len(report["stage_witnesses"]) == 4
    assert report["criterion_3"]["status"] == "not_assessed"
    assert path.read_bytes() == original


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
