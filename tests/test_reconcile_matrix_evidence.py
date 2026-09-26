"""Q declarations cannot silently outrun declared executions or artifacts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
from plan_confirmatory import compile_schedule  # noqa: E402
from reconcile_matrix_evidence import reconcile  # noqa: E402


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _ref(value: str) -> dict[str, str]:
    return {"ref": f"synthetic/{value}", "sha256": _hash(value)}


@pytest.fixture(scope="module")
def schedule() -> dict[str, Any]:
    models = []
    for family in ("family-a", "family-b"):
        for tier in ("lower", "higher"):
            models.append({
                "family": family, "tier": tier, "model_id": f"{family}/{tier}",
                "version": "synthetic-v1", "effort_control": tier == "higher",
                "efforts": ([{"label": "low", "provider_value": "low"},
                             {"label": "high", "provider_value": "high"}]
                            if tier == "higher" else [{"label": "default"}]),
            })
    return compile_schedule({
        "schema": 1, "seed": 9, "protocol_sha256": _hash("synthetic protocol"),
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


def _attempt(run: dict[str, Any], *, status: str = "completed", artifact: bool = True) -> dict[str, Any]:
    ordinal = (run["release_block_order"] - 1) * 3 + run["order_position"] - 1
    start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=ordinal * 20)
    end = start + timedelta(seconds=10)
    attempt = {
        "run_id": run["run_id"], "run_sha256": run["run_sha256"],
        "attempt_number": 1, "session_id": f"synthetic-session-{run['run_id']}",
        "status": status, "model_id": run["model_id"],
        "model_version": run["model_version"], "effort": run["effort"],
        "effort_provider_value": run["effort_provider_value"],
        "agents": run["agents"], "case_id": run["case_id"],
        "replica": run["replica"], "arm": run["arm"],
        "started_at_utc": start.isoformat().replace("+00:00", "Z"),
        "ended_at_utc": end.isoformat().replace("+00:00", "Z"),
        "active_seconds": 10, "human_wait_seconds": 0,
        "trace_sha256": _hash("trace-" + run["run_id"]),
        "agent_usage": [{
            "agent_id": f"agent-{index}", "tool_calls": 1,
            "provider_calls": [{"request_id": f"synthetic-request-{run['run_id']}-{index}",
                                "input_total": 100, "cached_input": 20,
                                "output_total": 20, "reasoning_output": 5}],
        } for index in range(1 if run["agents"] == "solo" else 3)],
    }
    if artifact:
        attempt["artifact_sha256"] = _hash("artifact-" + run["run_id"])
    return attempt


def _inputs(schedule: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    attempts = [_attempt(run) for run in schedule["runs"]]
    scores = [{"run_id": item["run_id"], "q": 50,
               "artifact_sha256": item["artifact_sha256"]} for item in attempts]
    return (
        {"schema": 1, "schedule_sha256": schedule["schedule_sha256"], "attempts": attempts},
        {"schema": 1, "schedule_sha256": schedule["schedule_sha256"], "runs": scores},
    )


def test_full_synthetic_declarations_are_concordant_but_unsealed(schedule: dict[str, Any]) -> None:
    receipts, evaluations = _inputs(schedule)
    report = reconcile(schedule, receipts, evaluations)
    assert report["classification"] == "development_matrix_reconciliation_unsealed"
    assert report["declared_joint_coverage_complete"] is True
    assert report["counts"]["concordant_scored_runs"] == 324
    assert report["counts"]["receipt_violations"] == 0
    assert report["criterion_4"]["status"] == "not_assessed"


def test_scores_without_any_receipts_cannot_look_jointly_complete(schedule: dict[str, Any]) -> None:
    receipts, evaluations = _inputs(schedule)
    receipts["attempts"] = []
    report = reconcile(schedule, receipts, evaluations)
    assert report["declared_joint_coverage_complete"] is False
    assert report["counts"]["missing_terminal_runs"] == 324
    assert {issue["code"] for issue in report["issues"]} == {
        "evaluation_without_terminal_receipt", "score_without_terminal_artifact",
    }


def test_missing_one_terminal_with_score_is_reported(schedule: dict[str, Any]) -> None:
    receipts, evaluations = _inputs(schedule)
    missing_id = receipts["attempts"].pop()["run_id"]
    report = reconcile(schedule, receipts, evaluations)
    assert report["declared_joint_coverage_complete"] is False
    assert any(item["run_id"] == missing_id and item["code"] == "evaluation_without_terminal_receipt"
               for item in report["issues"])


def test_terminal_without_rating_is_visible(schedule: dict[str, Any]) -> None:
    receipts, evaluations = _inputs(schedule)
    evaluations["runs"][0] = {"run_id": evaluations["runs"][0]["run_id"], "status": "missing"}
    report = reconcile(schedule, receipts, evaluations)
    assert report["declared_joint_coverage_complete"] is False
    assert report["counts"]["unrated_terminal_runs"] == 1
    assert any(item["code"] == "completed_run_not_scored" for item in report["issues"])


@pytest.mark.parametrize("artifact", [True, False])
def test_truncated_artifacts_control_whether_q_can_be_bound(schedule: dict[str, Any], artifact: bool) -> None:
    receipts, evaluations = _inputs(schedule)
    receipts["attempts"][0] = _attempt(schedule["runs"][0], status="truncated", artifact=artifact)
    evaluations["runs"][0]["status"] = "truncated"
    report = reconcile(schedule, receipts, evaluations)
    assert report["declared_joint_coverage_complete"] is artifact
    assert ("score_without_terminal_artifact" in {item["code"] for item in report["issues"]}) is not artifact


@pytest.mark.parametrize("change,code", [
    ("completed_marked_truncated", "completed_run_not_scored"),
    ("truncated_marked_scored", "truncation_status_mismatch"),
    ("digest_mismatch", "scored_artifact_digest_mismatch"),
    ("digest_absent", "score_artifact_digest_missing"),
])
def test_status_and_artifact_mismatches_are_reported(
    schedule: dict[str, Any], change: str, code: str,
) -> None:
    receipts, evaluations = _inputs(schedule)
    if change == "completed_marked_truncated":
        evaluations["runs"][0]["status"] = "truncated"
    elif change == "truncated_marked_scored":
        receipts["attempts"][0]["status"] = "truncated"
    elif change == "digest_mismatch":
        evaluations["runs"][0]["artifact_sha256"] = _hash("different artifact")
    else:
        evaluations["runs"][0].pop("artifact_sha256")
    report = reconcile(schedule, receipts, evaluations)
    assert report["declared_joint_coverage_complete"] is False
    assert any(item["code"] == code for item in report["issues"])


def test_receipt_cap_violations_block_declared_joint_coverage(schedule: dict[str, Any]) -> None:
    receipts, evaluations = _inputs(schedule)
    receipts["attempts"][0]["agent_usage"][0]["tool_calls"] = 101
    report = reconcile(schedule, receipts, evaluations)
    assert report["declared_joint_coverage_complete"] is False
    assert report["counts"]["receipt_violations"] == 1
    assert report["receipt_violations"][0]["code"] == "tool_calls_over_cap"


def test_cli_is_read_only_and_rejects_bad_schedule_binding(schedule: dict[str, Any], tmp_path: Path) -> None:
    receipts, evaluations = _inputs(schedule)
    evaluations["schedule_sha256"] = "0" * 64
    paths = [tmp_path / name for name in ("schedule.json", "receipts.json", "evaluations.json")]
    for path, value in zip(paths, (schedule, receipts, evaluations)):
        path.write_text(json.dumps(value), encoding="utf-8")
    before = {path.name: path.read_bytes() for path in paths}
    process = subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / "reconcile_matrix_evidence.py"),
         *(str(path) for path in paths)], capture_output=True, text=True, check=False,
    )
    assert process.returncode == 2
    assert "evaluation schedule digest mismatch" in json.loads(process.stdout)["error"]
    assert {path.name: path.read_bytes() for path in paths} == before
    assert len(list(tmp_path.iterdir())) == 3


@pytest.mark.parametrize("source", ["9" * 5000, "[" * 10000 + "0" + "]" * 10000])
def test_cli_returns_json_error_for_extreme_valid_json(source: str, tmp_path: Path) -> None:
    receipts = tmp_path / "receipts.json"
    evaluations = tmp_path / "evaluations.json"
    receipts.write_text("{}", encoding="utf-8")
    evaluations.write_text("{}", encoding="utf-8")
    process = subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / "reconcile_matrix_evidence.py"),
         "-", str(receipts), str(evaluations)],
        input=source, capture_output=True, text=True, check=False,
    )
    assert process.returncode == 2
    assert process.stderr == ""
    assert "invalid JSON value" in json.loads(process.stdout)["error"]
