"""Declared receipts are bounded and remain development evidence only."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "audit_run_receipts.py"
sys.path.insert(0, str(SCRIPTS))
from audit_run_receipts import ReceiptError, audit_receipts  # noqa: E402
from plan_confirmatory import compile_schedule  # noqa: E402


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _ref(label: str) -> dict[str, str]:
    return {"ref": f"synthetic/{label}", "sha256": _hash(label)}


@pytest.fixture(scope="module")
def schedule() -> dict[str, Any]:
    models = []
    for family in ("family-a", "family-b"):
        for tier in ("lower", "higher"):
            controlled = tier == "higher"
            models.append({
                "family": family, "tier": tier, "model_id": f"{family}/{tier}",
                "version": "synthetic-v1", "effort_control": controlled,
                "efforts": ([
                    {"label": "low", "provider_value": "low"},
                    {"label": "high", "provider_value": "high"},
                ] if controlled else [{"label": "default"}]),
            })
    return compile_schedule({
        "schema": 1, "seed": 3, "protocol_sha256": _hash("synthetic-protocol"),
        "tool_call_cap": 100, "models": models,
        "cases": [{"case_id": case_id, "package_sha256": _hash(case_id),
                   "reference_sha256": _hash("reference-" + case_id)}
                  for case_id in ("R-F", "R-M", "R-S")],
        "inputs": {
            "task_contract": _ref("task"), "common_prompt": _ref("common"),
            "arm_prompts": {arm: _ref("prompt-" + arm) for arm in ("N", "S", "T")},
            "rubric": _ref("rubric"), "tool_policy": _ref("policy"),
            "sdd_guide": _ref("sdd"), "toolkit": _ref("toolkit"),
        },
    })


def _attempt(run: dict[str, Any], number: int = 1, status: str = "completed") -> dict[str, Any]:
    ordinal = (run["release_block_order"] - 1) * 3 + run["order_position"] - 1
    start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=ordinal * 300 + number * 20)
    end = start + timedelta(seconds=10)
    agents = []
    for index in range(1 if run["agents"] == "solo" else 3):
        agents.append({
            "agent_id": f"agent-{index}", "tool_calls": 1,
            "provider_calls": [{
                "request_id": f"request-{run['run_id']}-{number}-{index}",
                "input_total": 100, "cached_input": 25,
                "output_total": 20, "reasoning_output": 8,
            }],
        })
    result = {
        "run_id": run["run_id"], "run_sha256": run["run_sha256"],
        "attempt_number": number,
        "session_id": f"session-{run['run_id']}-{number}",
        "status": status,
        "model_id": run["model_id"], "model_version": run["model_version"],
        "effort": run["effort"], "effort_provider_value": run["effort_provider_value"],
        "agents": run["agents"], "case_id": run["case_id"],
        "replica": run["replica"], "arm": run["arm"],
        "started_at_utc": start.isoformat().replace("+00:00", "Z"),
        "ended_at_utc": end.isoformat().replace("+00:00", "Z"),
        "human_wait_seconds": 2, "active_seconds": 8,
        "trace_sha256": _hash(f"trace-{run['run_id']}-{number}"),
        "agent_usage": agents,
    }
    if status == "external_failure":
        result["incident_sha256"] = _hash(f"incident-{run['run_id']}-{number}")
    elif status == "completed":
        result["artifact_sha256"] = _hash(f"artifact-{run['run_id']}-{number}")
    return result


def _receipts(schedule: dict[str, Any], attempts: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema": 1, "schedule_sha256": schedule["schedule_sha256"], "attempts": attempts}


def _shift_attempt(attempt: dict[str, Any], seconds: int) -> None:
    for key in ("started_at_utc", "ended_at_utc"):
        value = datetime.fromisoformat(attempt[key].replace("Z", "+00:00"))
        attempt[key] = (value + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _first_block_by_position(schedule: dict[str, Any]) -> dict[int, dict[str, Any]]:
    block_id = schedule["runs"][0]["block_id"]
    return {
        run["order_position"]: run for run in schedule["runs"]
        if run["block_id"] == block_id
    }


def test_valid_external_failure_retry_and_missing_runs_are_explicit(schedule: dict[str, Any]) -> None:
    run = schedule["runs"][0]
    result = audit_receipts(schedule, _receipts(schedule, [
        _attempt(run, 1, "external_failure"), _attempt(run, 2, "completed"),
    ]))

    assert result["classification"] == "development_receipt_audit_unsealed"
    assert result["matrix_receipts_complete"] is False
    assert result["counts"]["scheduled_runs"] == 324
    assert result["counts"]["attempted_runs"] == 1
    assert result["counts"]["completed_runs"] == 1
    assert result["counts"]["missing_runs"] == 323
    assert result["counts"]["retry_attempts"] == 1
    assert result["counts"]["external_failures"] == 1
    assert result["counts"]["violations"] == 0
    assert len(result["missing_runs"]) == 323
    assert {item["run_id"] for item in result["missing_runs"]} == {
        item["run_id"] for item in schedule["runs"][1:]
    }
    run_report = next(item for item in result["runs"] if item["run_id"] == run["run_id"])
    assert run_report["outcome"] == "completed"
    assert [item["status"] for item in run_report["attempts"]] == ["external_failure", "completed"]
    assert result["criterion_4"]["status"] == "not_assessed"
    assert "not authenticated" in result["notice"]
    assert "release_block_order requires a separately custodied release event" in result["notice"]
    assert len(result["receipts_sha256"]) == 64


def test_external_failure_without_terminal_is_missing(schedule: dict[str, Any]) -> None:
    run = schedule["runs"][0]
    result = audit_receipts(schedule, _receipts(schedule, [_attempt(run, status="external_failure")]))
    assert result["counts"]["missing_runs"] == 324
    assert {"run_id": run["run_id"], "reason": "external_failure_without_terminal_receipt"} in result["missing_runs"]


@pytest.mark.parametrize("change,match", [
    ("completed_retry", "cannot be retried"),
    ("truncated_retry", "cannot be retried"),
    ("duplicate_attempt_number", "consecutive"),
    ("attempt_gap", "consecutive"),
    ("overlapping_attempts", "overlap"),
    ("failure_with_artifact", "cannot carry an artifact"),
    ("failure_without_incident", "incident_sha256"),
])
def test_invalid_retry_sequences_rejected(schedule: dict[str, Any], change: str, match: str) -> None:
    run = schedule["runs"][0]
    first = _attempt(run, 1, "external_failure")
    second = _attempt(run, 2, "completed")
    if change == "completed_retry":
        first = _attempt(run, 1, "completed")
    elif change == "truncated_retry":
        first = _attempt(run, 1, "truncated")
    elif change == "duplicate_attempt_number":
        second["attempt_number"] = 1
    elif change == "attempt_gap":
        second["attempt_number"] = 3
    elif change == "overlapping_attempts":
        second["started_at_utc"] = first["started_at_utc"]
        second["ended_at_utc"] = first["ended_at_utc"]
    elif change == "failure_with_artifact":
        first["artifact_sha256"] = _hash("should-not-exist")
    elif change == "failure_without_incident":
        del first["incident_sha256"]

    with pytest.raises(ReceiptError, match=match):
        audit_receipts(schedule, _receipts(schedule, [first, second]))


@pytest.mark.parametrize("change,match", [
    ("duplicate_session", "duplicate session_id"),
    ("duplicate_request", "duplicate provider request_id"),
    ("wrong_version", "model_version differs"),
    ("wrong_effort", "effort differs"),
    ("wrong_run_digest", "run_sha256 mismatch"),
    ("extra_run_id", "unscheduled run_id"),
    ("wrong_schedule_digest", "receipt schedule_sha256 mismatch"),
    ("wrong_timestamp", "active_seconds.*differs"),
    ("cached_over_input", "cached_input exceeds"),
    ("reasoning_over_output", "reasoning_output exceeds"),
])
def test_invalid_identity_or_usage_rejected(schedule: dict[str, Any], change: str, match: str) -> None:
    first = _attempt(schedule["runs"][0])
    second = _attempt(schedule["runs"][1])
    receipts = _receipts(schedule, [first, second])
    if change == "duplicate_session":
        second["session_id"] = first["session_id"]
    elif change == "duplicate_request":
        second["agent_usage"][0]["provider_calls"][0]["request_id"] = first["agent_usage"][0]["provider_calls"][0]["request_id"]
    elif change == "wrong_version":
        first["model_version"] = "other-version"
    elif change == "wrong_effort":
        first["effort"] = "high"
    elif change == "wrong_run_digest":
        first["run_sha256"] = _hash("wrong")
    elif change == "extra_run_id":
        first["run_id"] = "conf-unscheduled"
    elif change == "wrong_schedule_digest":
        receipts["schedule_sha256"] = _hash("wrong")
    elif change == "wrong_timestamp":
        first["active_seconds"] = 9
    elif change == "cached_over_input":
        first["agent_usage"][0]["provider_calls"][0]["cached_input"] = 101
    elif change == "reasoning_over_output":
        first["agent_usage"][0]["provider_calls"][0]["reasoning_output"] = 21
    with pytest.raises(ReceiptError, match=match):
        audit_receipts(schedule, receipts)


def test_budget_violations_keep_all_attempt_records(schedule: dict[str, Any]) -> None:
    run = next(item for item in schedule["runs"] if item["agents"] == "trio")
    attempt = _attempt(run)
    for agent in attempt["agent_usage"]:
        agent["provider_calls"][0].update({
            "input_total": 27_000, "cached_input": 26_000,
            "output_total": 100, "reasoning_output": 90,
        })
        agent["tool_calls"] = 40
    attempt["ended_at_utc"] = (
        datetime.fromisoformat(attempt["started_at_utc"].replace("Z", "+00:00"))
        + timedelta(seconds=5_413)
    ).isoformat().replace("+00:00", "Z")
    attempt["active_seconds"] = 5_411

    result = audit_receipts(schedule, _receipts(schedule, [attempt]))

    codes = {violation["code"] for violation in result["violations"]}
    assert codes == {"measured_tokens_over_cap", "active_seconds_over_cap", "tool_calls_over_cap"}
    assert result["counts"]["measured_tokens"] == 81_300
    assert result["counts"]["tool_calls"] == 120
    assert result["matrix_receipts_complete"] is False
    record = next(item for item in result["runs"] if item["run_id"] == run["run_id"])
    assert record["attempt_count"] == 1
    assert record["attempts"][0]["status"] == "completed"
    assert record["attempts"][0]["measured_tokens"] == 81_300


def test_retry_invocations_each_within_cap_do_not_create_false_run_cap_violation(schedule: dict[str, Any]) -> None:
    run = schedule["runs"][0]
    first = _attempt(run, 1, "external_failure")
    second = _attempt(run, 2, "completed")
    for attempt in (first, second):
        call = attempt["agent_usage"][0]["provider_calls"][0]
        call.update({"input_total": 59_000, "cached_input": 5_000,
                     "output_total": 1_000, "reasoning_output": 500})
    result = audit_receipts(schedule, _receipts(schedule, [first, second]))
    record = next(item for item in result["runs"] if item["run_id"] == run["run_id"])

    assert record["measured_tokens"] == 120_000
    assert result["counts"]["measured_tokens"] == 120_000
    assert not result["violations"]


def test_five_declared_simultaneous_runs_report_violation(schedule: dict[str, Any]) -> None:
    distinct_blocks = []
    seen_blocks: set[str] = set()
    for run in schedule["runs"]:
        if run["block_id"] not in seen_blocks:
            seen_blocks.add(run["block_id"])
            distinct_blocks.append(run)
        if len(distinct_blocks) == 5:
            break
    attempts = [_attempt(run) for run in distinct_blocks]
    for attempt in attempts[1:]:
        attempt["started_at_utc"] = attempts[0]["started_at_utc"]
        attempt["ended_at_utc"] = attempts[0]["ended_at_utc"]
    result = audit_receipts(schedule, _receipts(schedule, attempts))

    assert result["counts"]["peak_simultaneous_runs"] == 5
    assert result["violations"] == [{"code": "simultaneous_runs_over_cap", "actual": 5, "limit": 4}]
    assert result["matrix_receipts_complete"] is False


@pytest.mark.parametrize("change", ["swap12", "tie12", "swap23"])
def test_full_receipt_matrix_with_wrong_first_arm_start_order_is_incomplete(
    schedule: dict[str, Any], change: str,
) -> None:
    attempts = [_attempt(run) for run in schedule["runs"]]
    block_id = schedule["runs"][0]["block_id"]
    positions = {
        run["order_position"]: index
        for index, run in enumerate(schedule["runs"])
        if run["block_id"] == block_id
    }
    first = attempts[positions[1]]
    second = attempts[positions[2]]
    third = attempts[positions[3]]
    if change == "tie12":
        for key in ("started_at_utc", "ended_at_utc"):
            first[key] = second[key]
    else:
        left, right = (first, second) if change == "swap12" else (second, third)
        for key in ("started_at_utc", "ended_at_utc"):
            left[key], right[key] = right[key], left[key]

    result = audit_receipts(schedule, _receipts(schedule, attempts))

    assert result["counts"]["missing_runs"] == 0
    assert result["counts"]["completed_runs"] == len(schedule["runs"])
    assert result["matrix_receipts_complete"] is False
    assert [item["code"] for item in result["violations"]] == [
        "arm_start_order_mismatch", "block_advanced_before_prior_terminal",
    ]
    violation = result["violations"][0]
    assert violation["block_id"] == block_id
    assert violation["run_ids_by_order_position"] == [
        schedule["runs"][positions[number]]["run_id"] for number in (1, 2, 3)
    ]


@pytest.mark.parametrize("terminal_status", ["completed", "truncated"])
def test_next_arm_waits_for_valid_external_retry_terminal(
    schedule: dict[str, Any], terminal_status: str,
) -> None:
    runs = _first_block_by_position(schedule)
    first_failure = _attempt(runs[1], 1, "external_failure")
    first_terminal = _attempt(runs[1], 2, terminal_status)
    second = _attempt(runs[2])
    third = _attempt(runs[3])
    _shift_attempt(second, -270)  # Begins exactly when retry terminates.
    _shift_attempt(third, -540)

    result = audit_receipts(schedule, _receipts(schedule, [
        first_failure, first_terminal, second, third,
    ]))

    assert result["violations"] == []
    assert result["counts"]["retry_attempts"] == 1
    assert result["counts"]["missing_runs"] == len(schedule["runs"]) - 3


def test_next_arm_starting_during_late_retry_is_reported(schedule: dict[str, Any]) -> None:
    runs = _first_block_by_position(schedule)
    attempts = [
        _attempt(runs[1], 1, "external_failure"),
        _attempt(runs[1], 2, "completed"),
        _attempt(runs[2]), _attempt(runs[3]),
    ]
    _shift_attempt(attempts[1], 280)  # Retry is still active when arm 2 starts.

    result = audit_receipts(schedule, _receipts(schedule, attempts))

    assert [item["code"] for item in result["violations"]] == ["block_advanced_before_prior_terminal"]
    violation = result["violations"][0]
    assert violation["prior_run_id"] == runs[1]["run_id"]
    assert violation["next_run_id"] == runs[2]["run_id"]
    assert violation["prior_status"] == "completed"
    assert result["matrix_receipts_complete"] is False


@pytest.mark.parametrize("prior_position,prior_status", [
    (1, "external_failure"), (1, "missing"), (2, "external_failure"),
])
def test_advance_after_unresolved_or_absent_prior_arm_is_reported(
    schedule: dict[str, Any], prior_position: int, prior_status: str,
) -> None:
    runs = _first_block_by_position(schedule)
    attempts = []
    if prior_position == 2:
        attempts.append(_attempt(runs[1]))
    if prior_status == "external_failure":
        attempts.append(_attempt(runs[prior_position], status="external_failure"))
    attempts.append(_attempt(runs[prior_position + 1]))

    result = audit_receipts(schedule, _receipts(schedule, attempts))

    assert [item["code"] for item in result["violations"]] == ["block_advanced_before_prior_terminal"]
    violation = result["violations"][0]
    assert violation["prior_run_id"] == runs[prior_position]["run_id"]
    assert violation["next_run_id"] == runs[prior_position + 1]["run_id"]
    assert violation["prior_status"] == prior_status
    assert result["matrix_receipts_complete"] is False


def test_zero_active_time_with_provider_call_prevents_false_complete(schedule: dict[str, Any]) -> None:
    attempts = [_attempt(run) for run in schedule["runs"]]
    attempt = attempts[0]
    attempt["started_at_utc"] = attempt["ended_at_utc"]
    attempt["active_seconds"] = 0
    attempt["human_wait_seconds"] = 0

    result = audit_receipts(schedule, _receipts(schedule, attempts))

    assert result["counts"]["missing_runs"] == 0
    assert result["counts"]["completed_runs"] == len(schedule["runs"])
    assert result["matrix_receipts_complete"] is False
    assert result["violations"] == [{
        "code": "zero_active_time_with_provider_call",
        "run_id": attempt["run_id"], "attempt_number": 1, "provider_calls": 1,
    }]


def test_retries_accumulate_across_attempts_and_agents_without_double_counting(schedule: dict[str, Any]) -> None:
    run = next(item for item in schedule["runs"] if item["agents"] == "trio")
    first = _attempt(run, 1, "external_failure")
    second = _attempt(run, 2, "truncated")
    result = audit_receipts(schedule, _receipts(schedule, [first, second]))
    record = next(item for item in result["runs"] if item["run_id"] == run["run_id"])

    assert record["outcome"] == "truncated"
    assert record["measured_tokens"] == 720  # 3 agents x 2 calls x (100 + 20)
    assert record["provider_calls"] == 6
    assert record["tool_calls"] == 6
    assert record["active_seconds"] == 16
    assert record["human_wait_seconds"] == 4
    assert result["counts"]["truncated_runs"] == 1


def test_ten_external_retries_allowed_eleven_reported(schedule: dict[str, Any]) -> None:
    run = schedule["runs"][0]
    ten = [_attempt(run, number, "external_failure") for number in range(1, 11)]
    ten.append(_attempt(run, 11, "completed"))
    within = audit_receipts(schedule, _receipts(schedule, ten))
    assert within["counts"]["retry_attempts"] == 10
    assert not within["violations"]

    eleven = copy.deepcopy(ten)
    eleven[-1] = _attempt(run, 11, "external_failure")
    eleven.append(_attempt(run, 12, "completed"))
    over = audit_receipts(schedule, _receipts(schedule, eleven))
    assert over["counts"]["retry_attempts"] == 11
    assert over["violations"] == [{"code": "external_retry_slots_over_cap", "actual": 11, "limit": 10}]
    assert len(next(item for item in over["runs"] if item["run_id"] == run["run_id"])["attempts"]) == 12


def test_complete_declared_matrix_still_not_confirmatory(schedule: dict[str, Any]) -> None:
    attempts = [_attempt(run) for run in schedule["runs"]]
    result = audit_receipts(schedule, _receipts(schedule, attempts))

    assert result["matrix_receipts_complete"] is True
    assert result["counts"]["missing_runs"] == 0
    assert result["counts"]["completed_runs"] == len(schedule["runs"])
    assert result["counts"]["peak_simultaneous_runs"] == 1
    assert result["classification"] == "development_receipt_audit_unsealed"
    assert result["criterion_4"]["status"] == "not_assessed"


def test_cli_reports_json_success_and_input_error(schedule: dict[str, Any], tmp_path: Path) -> None:
    schedule_path = tmp_path / "schedule.json"
    receipt_path = tmp_path / "attempts.json"
    schedule_path.write_text(json.dumps(schedule), encoding="utf-8")
    receipt_path.write_text(json.dumps(_receipts(schedule, [_attempt(schedule["runs"][0])])), encoding="utf-8")
    ok = subprocess.run(
        [sys.executable, str(SCRIPT), str(schedule_path), str(receipt_path)],
        capture_output=True, text=True, check=False,
    )
    assert ok.returncode == 0, ok.stderr
    output = json.loads(ok.stdout)
    assert output["classification"] == "development_receipt_audit_unsealed"
    assert output["counts"]["completed_runs"] == 1
    assert output["counts"]["missing_runs"] == len(schedule["runs"]) - 1

    receipt_path.write_text('{"schema":1,"schema":1}', encoding="utf-8")
    bad = subprocess.run(
        [sys.executable, str(SCRIPT), str(schedule_path), str(receipt_path)],
        capture_output=True, text=True, check=False,
    )
    assert bad.returncode == 2
    assert "duplicate JSON object key" in json.loads(bad.stdout)["error"]
