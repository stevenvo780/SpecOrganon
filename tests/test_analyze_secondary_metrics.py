"""Declared secondary arithmetic keeps missing data and model weights visible."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "analyze_secondary_metrics.py"
sys.path.insert(0, str(SCRIPTS))
from analyze_secondary_metrics import SecondaryError, analyze_secondary_metrics  # noqa: E402
from plan_confirmatory import compile_schedule  # noqa: E402


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()


def _ref(label: str) -> dict[str, str]:
    return {"ref": f"synthetic/{label}", "sha256": _hash(label)}


def _schedule() -> dict[str, Any]:
    models = []
    for family in ("family-a", "family-b"):
        for tier in ("lower", "higher"):
            single = family == "family-a" and tier == "lower"
            models.append({
                "family": family, "tier": tier,
                "model_id": f"{family}/{tier}", "version": "synthetic-v1",
                "effort_control": not single,
                "efforts": ([{"label": "default"}] if single else [
                    {"label": "low", "provider_value": "low"},
                    {"label": "high", "provider_value": "high"},
                ]),
            })
    return compile_schedule({
        "schema": 1, "seed": 29, "protocol_sha256": _hash("protocol"),
        "tool_call_cap": 100, "models": models,
        "cases": [
            {"case_id": case_id, "package_sha256": _hash(case_id),
             "reference_sha256": _hash(f"reference-{case_id}")}
            for case_id in ("R-F", "R-M", "R-S")
        ],
        "inputs": {
            "task_contract": _ref("task"), "common_prompt": _ref("common"),
            "arm_prompts": {arm: _ref(f"prompt-{arm}") for arm in ("N", "S", "T")},
            "rubric": _ref("rubric"), "tool_policy": _ref("policy"),
            "sdd_guide": _ref("sdd"), "toolkit": _ref("toolkit"),
        },
    })


def _utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _attempt(run: dict[str, Any]) -> dict[str, Any]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
        seconds=run["release_block_order"] * 100 + run["order_position"] * 20
    )
    return {
        "run_id": run["run_id"], "run_sha256": run["run_sha256"],
        "attempt_number": 1, "session_id": f"session-{run['run_id']}",
        "status": "completed", "model_id": run["model_id"],
        "model_version": run["model_version"], "effort": run["effort"],
        "effort_provider_value": run["effort_provider_value"],
        "agents": run["agents"], "case_id": run["case_id"],
        "replica": run["replica"], "arm": run["arm"],
        "started_at_utc": _utc(start), "ended_at_utc": _utc(start + timedelta(seconds=10)),
        "human_wait_seconds": 2, "active_seconds": 8,
        "trace_sha256": _hash("trace-" + run["run_id"]),
        "artifact_sha256": _hash("artifact-" + run["run_id"]),
        "agent_usage": [
            {"agent_id": f"agent-{n}", "tool_calls": 1, "provider_calls": [{
                "request_id": f"request-{run['run_id']}-{n}",
                "input_total": 100, "cached_input": 20,
                "output_total": 50, "reasoning_output": 10,
            }]}
            for n in range(1 if run["agents"] == "solo" else 3)
        ],
    }


def _detail(run: dict[str, Any], attempt: dict[str, Any], e: int) -> dict[str, Any]:
    incidents = {_hash("incident-" + run["run_id"])[:32]: "false_test"} if e else {}
    return {
        "run_id": run["run_id"], "opaque_id": _hash("opaque-" + run["run_id"])[:32],
        "terminal_artifact_sha256": attempt["artifact_sha256"],
        "terminal_trace_sha256": attempt["trace_sha256"],
        "blind_package_sha256": attempt["artifact_sha256"],
        "blind_trace_sha256": attempt["trace_sha256"],
        "preparation_record_sha256": None,
        "raw_q": {"primary": [
            {"evaluator_id": evaluator,
             "q_components": {name: 10 for name in (
                 "formulation", "evidence", "alternatives", "technical", "validation"
             )}, "q_total": 50}
            for evaluator in ("external-a", "external-b")
        ], "adjudicator": None},
        "raw_critical_incidents": {"primary": [
            {"evaluator_id": evaluator, "incidents": incidents}
            for evaluator in ("external-a", "external-b")
        ], "adjudicator": None},
        "adjudication": {"basis": "primary_arithmetic_mean", "triggers": []},
        "sensitivity": {"primary_mean_q": 50, "selected_q": 50,
                        "selected_minus_primary_mean_q": 0},
        "critical_incidents": incidents, "E": e,
    }


def _bundle() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    schedule = _schedule()
    attempts = [_attempt(run) for run in schedule["runs"]]
    receipts = {"schema": 1, "schedule_sha256": schedule["schedule_sha256"],
                "attempts": attempts}
    target_model = schedule["models"][0]["model_id"]
    e_values = [int(run["model_id"] == target_model and run["arm"] == "T")
                for run in schedule["runs"]]
    details = [_detail(run, attempt, e) for run, attempt, e in
               zip(schedule["runs"], attempts, e_values, strict=True)]
    evaluations = {"schema": 1, "schedule_sha256": schedule["schedule_sha256"],
                   "runs": [
                       {"run_id": run["run_id"], "status": "scored", "q": 50,
                        "artifact_sha256": attempt["artifact_sha256"]}
                       for run, attempt in zip(schedule["runs"], attempts, strict=True)
                   ]}
    assembly = {
        "schema": 1, "classification": "development_rated_q_assembly_unsealed",
        "notice": "Synthetic declared Q assembly; no raw judge authentication.",
        "mapping_schema": 1, "schedule_sha256": schedule["schedule_sha256"],
        "receipts_sha256": _digest(receipts),
        "manifest_sha256": _hash("manifest"), "ratings_sha256": _hash("ratings"),
        "mapping_sha256": _hash("mapping"),
        "duplicate_terminal_pairs_requiring_external_preparation_verification": [],
        "evaluations": evaluations, "details": details,
        "counts": {"scheduled_runs": len(details), "mapped_runs": len(details),
                   "scored_runs": len(details), "truncated_runs": 0,
                   "truncated_scored_runs": 0, "missing_runs": 0,
                   "adjudicated_runs": 0, "critical_incident_runs": sum(e_values)},
        "criterion_4": {"status": "not_assessed", "reason": "synthetic only"},
    }
    wall_by_model = {
        model["model_id"]: amount
        for model, amount in zip(schedule["models"], (10, 20, 100, 200), strict=True)
    }
    cost_by_model = {
        model["model_id"]: amount
        for model, amount in zip(schedule["models"], (1, 2, 100, 200), strict=True)
    }
    secondary_runs = []
    for run, attempt in zip(schedule["runs"], attempts, strict=True):
        model = run["model_id"]
        wall_seconds = wall_by_model[model]
        cost = cost_by_model[model]
        if run["arm"] == "T" and model in tuple(wall_by_model)[:2]:
            wall_seconds *= 2
            cost *= 2
        selected = int(run["arm"] == "T" and model == target_model)
        start = datetime.fromisoformat(attempt["started_at_utc"].replace("Z", "+00:00"))
        secondary_runs.append({
            "run_id": run["run_id"], "status": "measured",
            "reference_sha256": run["case_reference_sha256"],
            "audit_sha256": _hash("audit-" + run["run_id"]),
            "compliance": {"met": 8, "required": 10, "critical_omissions": 0},
            "traceability": {"tp": selected, "fp": 0, "fn": 1 - selected,
                             "complete_requirements": 4, "required_requirements": 5,
                             "complete_indicators": 2, "required_indicators": 3},
            "recovery": {"injection_sha256": _hash("injection-" + run["run_id"]),
                         "recovered": bool(selected), "resume_seconds": 3,
                         "repeated_decisions": 0},
            "human": {"active_seconds": 2, "wait_seconds": 2,
                      "active_seconds_by_type": {
                          "approvals": 0.5, "external_reviews": 1,
                          "blocks": 0, "corrections": 0.5, "unblocks": 0,
                      },
                      "events_sha256": _hash("human-" + run["run_id"]),
                      "event_counts": {
                          "approvals": 1, "external_reviews": 2, "blocks": 0,
                          "corrections": 1, "unblocks": 0,
                      }},
            "wall": {"released_at_utc": attempt["started_at_utc"],
                     "delivered_at_utc": _utc(start + timedelta(seconds=wall_seconds)),
                     "event_sha256": _hash("wall-" + run["run_id"])},
            "cost": {"model_usd": str(cost), "tools_usd": "0", "human_usd": "0",
                     "total_usd": str(cost),
                     "invoice_sha256": _hash("invoice-" + run["run_id"])},
        })
    secondary = {
        "schema": 1, "schedule_sha256": schedule["schedule_sha256"],
        "receipts_sha256": _digest(receipts),
        "assembly_sha256": _digest(assembly), "rate_card_sha256": _hash("rate-card"),
        "runs": secondary_runs,
    }
    return schedule, receipts, assembly, secondary


@pytest.fixture(scope="module")
def bundle() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    return _bundle()


def test_full_weighted_secondary_math_and_model_medians(bundle: tuple[dict[str, Any], ...]) -> None:
    result = analyze_secondary_metrics(*bundle)

    assert result["classification"] == "development_secondary_analysis_unsealed"
    assert result["criterion_4"]["status"] == "not_assessed"
    assert result["counts"] == {
        "scheduled_runs": 378, "secondary_measured_runs": 378,
        "secondary_missing_runs": 0, "assembly_E_available_runs": 378,
    }
    for metric in ("E", "T", "R"):
        assert result["aggregate"][metric]["by_arm"]["T"] == pytest.approx(0.25)
        assert result["aggregate"][metric]["T_minus_S_pp"] == pytest.approx(25)
    assert result["aggregate"]["E"]["incident_counts"]["by_type_available"] == {
        "false_test": 18
    }
    assert result["aggregate"]["E"]["incident_counts"]["by_arm_available"]["T"] == {
        "available_runs": 126, "total_unique_available": 18,
        "by_type_available": {"false_test": 18},
    }
    assert sum(row["E"] for row in result["runs"] if row["arm"] == "T") / 126 == pytest.approx(1 / 7)
    assert result["aggregate"]["W"]["by_arm"] == {"N": 60, "S": 60, "T": 70}
    assert result["aggregate"]["W"]["T_over_S"] == pytest.approx(7 / 6)
    assert result["aggregate"]["P"]["by_arm"] == {"N": "51", "S": "51", "T": "52"}
    assert Decimal(result["aggregate"]["P"]["T_over_S"]) == pytest.approx(Decimal(52) / 51)
    agent_count = 1 if bundle[0]["runs"][0]["agents"] == "solo" else 3
    assert result["runs"][0]["K"] == {
        "input_uncached": 80 * agent_count,
        "input_cached": 20 * agent_count,
        "output_nonreasoning": 40 * agent_count,
        "output_reasoning": 10 * agent_count,
        "total": 150 * agent_count,
        "provider_calls": agent_count,
    }
    assert result["runs"][0]["H"]["event_counts"]["approvals"] == 1
    assert result["aggregate"]["H"]["total_event_counts"]["external_reviews"] == 756
    assert result["runs"][0]["H"]["active_seconds_by_type"]["approvals"] == 0.5
    assert result["aggregate"]["H"]["total_active_seconds_by_type"]["approvals"] == 189
    assert result["aggregate"]["H"]["by_arm_available_totals"]["T"]["active_seconds_by_type"]["external_reviews"] == 126


def test_missing_data_and_zero_s_cost_do_not_create_favorable_claims(
    bundle: tuple[dict[str, Any], ...],
) -> None:
    schedule, receipts, assembly, secondary = copy.deepcopy(bundle)
    secondary["runs"][0] = {"run_id": schedule["runs"][0]["run_id"],
                            "status": "missing", "reason": "audit absent"}
    result = analyze_secondary_metrics(schedule, receipts, assembly, secondary)
    assert result["aggregate"]["E"]["missing_count"] == 0
    for metric in ("T", "R", "W", "P"):
        assert result["aggregate"][metric]["missing_count"] == 1
        assert result["aggregate"][metric]["by_arm"]["T"] is None
    assert result["aggregate"]["P"]["T_over_S"] is None
    assert result["criterion_4"]["status"] == "not_assessed"

    secondary = copy.deepcopy(bundle[3])
    for run, row in zip(schedule["runs"], secondary["runs"], strict=True):
        if run["arm"] == "S":
            row["cost"].update({"model_usd": "0", "total_usd": "0"})
    result = analyze_secondary_metrics(schedule, receipts, assembly, secondary)
    assert result["aggregate"]["P"]["by_arm"]["S"] == "0"
    assert result["aggregate"]["P"]["T_over_S"] is None


def test_failed_recovery_can_have_no_resume_time(
    bundle: tuple[dict[str, Any], ...],
) -> None:
    schedule, receipts, assembly, secondary = copy.deepcopy(bundle)
    index = next(i for i, row in enumerate(secondary["runs"])
                 if row["recovery"]["recovered"] is False)
    secondary["runs"][index]["recovery"]["resume_seconds"] = None
    result = analyze_secondary_metrics(schedule, receipts, assembly, secondary)
    assert result["runs"][index]["R"] == {
        "recovered": 0, "resume_seconds": None, "repeated_decisions": 0,
    }

    secondary["runs"][index]["recovery"]["recovered"] = True
    with pytest.raises(SecondaryError, match="must be numeric when recovered"):
        analyze_secondary_metrics(schedule, receipts, assembly, secondary)


def test_recovery_only_missing_keeps_other_measured_metrics(
    bundle: tuple[dict[str, Any], ...],
) -> None:
    schedule, receipts, assembly, secondary = copy.deepcopy(bundle)
    secondary["runs"][0]["recovery"] = {
        "status": "missing", "reason": "injection event not verifiable"
    }

    result = analyze_secondary_metrics(schedule, receipts, assembly, secondary)
    row = result["runs"][0]
    assert row["status"] == "measured"
    assert row["R"] is None
    assert row["R_missing_reason"] == "injection event not verifiable"
    assert all(row[metric] is not None for metric in ("C", "T", "H", "W", "K", "P", "E"))
    assert result["aggregate"]["R"]["missing_count"] == 1
    assert result["aggregate"]["R"]["by_arm"]["T"] is None
    for metric in ("E", "T", "W", "P"):
        assert result["aggregate"][metric]["missing_count"] == 0


def test_unrated_assembly_run_has_missing_e_not_zero(bundle: tuple[dict[str, Any], ...]) -> None:
    schedule, receipts, assembly, secondary = copy.deepcopy(bundle)
    run_id = schedule["runs"][0]["run_id"]
    assembly["evaluations"]["runs"][0] = {
        "run_id": run_id, "status": "missing", "reason": "no rating"
    }
    removed = assembly["details"].pop(0)
    assembly["counts"]["mapped_runs"] -= 1
    assembly["counts"]["scored_runs"] -= 1
    assembly["counts"]["missing_runs"] += 1
    assembly["counts"]["critical_incident_runs"] -= removed["E"]
    secondary["assembly_sha256"] = _digest(assembly)
    result = analyze_secondary_metrics(schedule, receipts, assembly, secondary)
    assert result["runs"][0]["E"] is None
    assert result["aggregate"]["E"]["missing_count"] == 1
    assert result["aggregate"]["E"]["T_minus_S_pp"] is None


def test_declared_adjudication_q_is_recomputed(bundle: tuple[dict[str, Any], ...]) -> None:
    schedule, receipts, assembly, secondary = copy.deepcopy(bundle)
    index = next(i for i, detail in enumerate(assembly["details"]) if detail["E"] == 1)
    detail = assembly["details"][index]
    second = detail["raw_q"]["primary"][1]
    second["q_components"] = {name: 14 for name in second["q_components"]}
    second["q_total"] = 70
    third = copy.deepcopy(second)
    third["evaluator_id"] = "external-c"
    third["q_components"] = {name: 12 for name in third["q_components"]}
    third["q_total"] = 60
    detail["raw_q"]["adjudicator"] = third
    detail["raw_critical_incidents"]["adjudicator"] = {
        "evaluator_id": "external-c", "incidents": detail["critical_incidents"]
    }
    detail["adjudication"] = {
        "basis": "third_locked_rating", "triggers": ["q_total_difference_gt_10"],
        "q_resolution": {"basis": "third_locked_rating", "rationale": "synthetic third rating"},
        "critical_failure_resolutions": [],
    }
    detail["sensitivity"] = {
        "primary_mean_q": 60, "selected_q": 60,
        "selected_minus_primary_mean_q": 0,
    }
    assembly["evaluations"]["runs"][index]["q"] = 60
    assembly["counts"]["adjudicated_runs"] = 1
    secondary["assembly_sha256"] = _digest(assembly)

    result = analyze_secondary_metrics(schedule, receipts, assembly, secondary)
    assert result["runs"][index]["E"] == 1
    assert result["runs"][index]["E_incidents"] == {
        "total_unique": 1, "by_type": {"false_test": 1}
    }
    assert result["aggregate"]["E"]["incident_counts"]["by_type_available"] == {
        "false_test": 18
    }
    assert result["criterion_4"]["status"] == "not_assessed"


def test_same_incident_id_in_two_runs_counts_two_observations(
    bundle: tuple[dict[str, Any], ...],
) -> None:
    schedule, receipts, assembly, secondary = copy.deepcopy(bundle)
    first, second = [detail for detail in assembly["details"] if detail["E"] == 1][:2]
    second["critical_incidents"] = copy.deepcopy(first["critical_incidents"])
    for primary in second["raw_critical_incidents"]["primary"]:
        primary["incidents"] = copy.deepcopy(first["critical_incidents"])
    secondary["assembly_sha256"] = _digest(assembly)

    result = analyze_secondary_metrics(schedule, receipts, assembly, secondary)
    assert result["aggregate"]["E"]["incident_counts"]["by_type_available"] == {
        "false_test": 18
    }
    assert next(row for row in result["runs"] if row["run_id"] == second["run_id"])["E_incidents"] == {
        "total_unique": 1, "by_type": {"false_test": 1}
    }


def test_retry_tokens_and_wall_gaps(bundle: tuple[dict[str, Any], ...]) -> None:
    schedule, receipts, assembly, secondary = copy.deepcopy(bundle)
    run = schedule["runs"][0]
    terminal = receipts["attempts"][0]
    first = copy.deepcopy(terminal)
    start = datetime.fromisoformat(terminal["started_at_utc"].replace("Z", "+00:00"))
    first.update({
        "attempt_number": 1, "session_id": "retry-session", "status": "external_failure",
        "started_at_utc": _utc(start - timedelta(seconds=30)),
        "ended_at_utc": _utc(start - timedelta(seconds=20)),
        "incident_sha256": _hash("retry-incident"),
    })
    first.pop("artifact_sha256")
    first["agent_usage"][0]["provider_calls"][0]["request_id"] = "retry-request"
    terminal["attempt_number"] = 2
    receipts["attempts"].insert(0, first)
    assembly["receipts_sha256"] = _digest(receipts)
    secondary["receipts_sha256"] = _digest(receipts)
    secondary["assembly_sha256"] = _digest(assembly)
    secondary["runs"][0]["wall"].update({
        "released_at_utc": first["started_at_utc"],
        "delivered_at_utc": _utc(start + timedelta(seconds=12)),
    })
    secondary["runs"][0]["human"]["wait_seconds"] = 5
    result = analyze_secondary_metrics(schedule, receipts, assembly, secondary)
    assert result["runs"][0]["W"]["seconds"] == 42
    assert result["runs"][0]["K"]["provider_calls"] == 2
    assert result["runs"][0]["K"]["total"] == 300
    assert result["runs"][0]["K"]["input_cached"] == 40
    assert result["runs"][0]["H"]["wait_seconds"] == 5
    assert result["aggregate"]["K"]["by_arm_available_totals"][run["arm"]]["provider_calls"] == \
        sum(row["K"]["provider_calls"] for row in result["runs"] if row["arm"] == run["arm"])


@pytest.mark.parametrize("change,match", [
    ("forged_e", "E differs"),
    ("forged_incidents", "critical_incidents differs"),
    ("forged_q", "selected Q differs"),
    ("missing_detail", "details must cover"),
    ("wrong_reference", "reference_sha256 differs"),
    ("empty_reference", "nonempty reference link set"),
    ("bool_count", "must be an integer"),
    ("wrong_cost", "exact component sum"),
    ("short_wall", "include all receipt attempts"),
    ("long_resume", "resume_seconds exceeds wall duration"),
    ("underreported_wait", "below receipt human_wait_seconds"),
    ("bad_human_type", "event_counts.blocks must be an integer"),
    ("bad_human_keys", "human.event_counts has missing keys"),
    ("bad_human_active_sum", "active_seconds differs from active_seconds_by_type"),
    ("bad_human_active_keys", "active_seconds_by_type has missing keys"),
    ("malformed_recovery", "recovery has missing keys"),
    ("huge_seconds", "finite number from 0"),
    ("huge_money", "at most 256 characters"),
])
def test_tamper_and_invalid_values_rejected(
    bundle: tuple[dict[str, Any], ...], change: str, match: str,
) -> None:
    schedule, receipts, assembly, secondary = copy.deepcopy(bundle)
    if change == "forged_e":
        assembly["details"][0]["E"] = 1 - assembly["details"][0]["E"]
    elif change == "forged_incidents":
        assembly["details"][0]["critical_incidents"] = {_hash("fake")[:32]: "false_test"}
    elif change == "forged_q":
        assembly["evaluations"]["runs"][0]["q"] = 51
    elif change == "missing_detail":
        assembly["details"].pop(0)
    elif change == "wrong_reference":
        secondary["runs"][0]["reference_sha256"] = _hash("wrong")
    elif change == "empty_reference":
        secondary["runs"][0]["traceability"].update({"tp": 0, "fn": 0})
    elif change == "bool_count":
        secondary["runs"][0]["compliance"]["met"] = True
    elif change == "wrong_cost":
        secondary["runs"][0]["cost"]["total_usd"] = "0"
    elif change == "short_wall":
        secondary["runs"][0]["wall"]["delivered_at_utc"] = \
            secondary["runs"][0]["wall"]["released_at_utc"]
    elif change == "long_resume":
        secondary["runs"][0]["recovery"]["resume_seconds"] = 1000
    elif change == "underreported_wait":
        secondary["runs"][0]["human"]["wait_seconds"] = 0
    elif change == "bad_human_type":
        secondary["runs"][0]["human"]["event_counts"]["blocks"] = True
    elif change == "bad_human_keys":
        secondary["runs"][0]["human"]["event_counts"].pop("blocks")
    elif change == "bad_human_active_sum":
        secondary["runs"][0]["human"]["active_seconds_by_type"]["approvals"] = 0
    elif change == "bad_human_active_keys":
        secondary["runs"][0]["human"]["active_seconds_by_type"].pop("blocks")
    elif change == "malformed_recovery":
        secondary["runs"][0]["recovery"] = {"status": "missing"}
    elif change == "huge_seconds":
        secondary["runs"][0]["human"]["active_seconds"] = 10**400
    elif change == "huge_money":
        secondary["runs"][0]["cost"]["model_usd"] = "1" * 300
    secondary["assembly_sha256"] = _digest(assembly)
    with pytest.raises(SecondaryError, match=match):
        analyze_secondary_metrics(schedule, receipts, assembly, secondary)


def test_long_decimal_component_sum_is_exact(bundle: tuple[dict[str, Any], ...]) -> None:
    schedule, receipts, assembly, secondary = copy.deepcopy(bundle)
    cost = secondary["runs"][0]["cost"]
    cost.update({
        "model_usd": "0.00000000000000000000000000001",
        "tools_usd": "0.00000000000000000000000000002",
        "human_usd": "0", "total_usd": "0.00000000000000000000000000003",
    })
    analyze_secondary_metrics(schedule, receipts, assembly, secondary)
    cost["total_usd"] = "0.00000000000000000000000000004"
    with pytest.raises(SecondaryError, match="exact component sum"):
        analyze_secondary_metrics(schedule, receipts, assembly, secondary)


def test_cli_one_stdin_and_structured_error(
    bundle: tuple[dict[str, Any], ...], tmp_path: Path,
) -> None:
    paths = []
    for name, value in zip(("schedule", "receipts", "assembly", "secondary"), bundle, strict=True):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths.append(str(path))
    command = [sys.executable, str(SCRIPT), paths[0], paths[1], paths[2], "-"]
    result = subprocess.run(command, input=json.dumps(bundle[3]), text=True,
                            capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["criterion_4"]["status"] == "not_assessed"
    command[-2] = "-"
    result = subprocess.run(command, input="{}", text=True, capture_output=True, check=False)
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"] == {
        "code": "invalid_input", "message": "only one input may use stdin"
    }
    assert json.loads(result.stdout)["criterion_4"]["status"] == "not_assessed"
