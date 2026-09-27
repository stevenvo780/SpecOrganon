"""Declared Q assembly binds blind ratings to terminal receipts without result claims."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "assemble_rated_q.py"
sys.path.insert(0, str(SCRIPTS))
from assemble_rated_q import AssemblyError, assemble_rated_q  # noqa: E402
from plan_confirmatory import compile_schedule  # noqa: E402
from reconcile_matrix_evidence import reconcile  # noqa: E402


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _ref(label: str) -> dict[str, str]:
    return {"ref": f"synthetic/{label}", "sha256": _hash(label)}


@pytest.fixture(scope="module")
def schedule() -> dict[str, Any]:
    models = [
        {
            "family": family, "tier": tier, "model_id": f"{family}/{tier}",
            "version": "synthetic-v1", "effort_control": tier == "higher",
            "efforts": ([
                {"label": "low", "provider_value": "low"},
                {"label": "high", "provider_value": "high"},
            ] if tier == "higher" else [{"label": "default"}]),
        }
        for family in ("family-a", "family-b")
        for tier in ("lower", "higher")
    ]
    return compile_schedule({
        "schema": 1, "seed": 19, "protocol_sha256": _hash("protocol"),
        "tool_call_cap": 100, "models": models,
        "cases": [
            {"case_id": case_id, "package_sha256": _hash(case_id),
             "reference_sha256": _hash("reference-" + case_id)}
            for case_id in ("R-F", "R-M", "R-S")
        ],
        "inputs": {
            "task_contract": _ref("task"), "common_prompt": _ref("common"),
            "arm_prompts": {arm: _ref("prompt-" + arm) for arm in ("N", "S", "T")},
            "rubric": _ref("rubric"), "tool_policy": _ref("policy"),
            "sdd_guide": _ref("sdd"), "toolkit": _ref("toolkit"),
        },
    })


def _independent_first_runs(schedule: dict[str, Any], count: int) -> list[dict[str, Any]]:
    return [run for run in schedule["runs"] if run["order_position"] == 1][:count]


def _attempt(
    run: dict[str, Any], status: str = "completed", *, artifact: bool = True,
) -> dict[str, Any]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
        seconds=run["release_block_order"] * 100 + run["order_position"] * 10
    )
    end = start + timedelta(seconds=10)
    agent_usage = [
        {
            "agent_id": f"agent-{index}", "tool_calls": 1,
            "provider_calls": [{
                "request_id": f"request-{run['run_id']}-{index}",
                "input_total": 100, "cached_input": 10,
                "output_total": 20, "reasoning_output": 5,
            }],
        }
        for index in range(1 if run["agents"] == "solo" else 3)
    ]
    row = {
        "run_id": run["run_id"], "run_sha256": run["run_sha256"],
        "attempt_number": 1, "session_id": f"session-{run['run_id']}",
        "status": status, "model_id": run["model_id"],
        "model_version": run["model_version"], "effort": run["effort"],
        "effort_provider_value": run["effort_provider_value"],
        "agents": run["agents"], "case_id": run["case_id"],
        "replica": run["replica"], "arm": run["arm"],
        "started_at_utc": start.isoformat().replace("+00:00", "Z"),
        "ended_at_utc": end.isoformat().replace("+00:00", "Z"),
        "human_wait_seconds": 2, "active_seconds": 8,
        "trace_sha256": _hash("trace-" + run["run_id"]),
        "agent_usage": agent_usage,
    }
    if status == "external_failure":
        row["incident_sha256"] = _hash("incident-" + run["run_id"])
    elif status == "completed" or artifact:
        row["artifact_sha256"] = _hash("artifact-" + run["run_id"])
    return row


def _reach_measured_token_cap(attempt: dict[str, Any]) -> None:
    first_call = attempt["agent_usage"][0]["provider_calls"][0]
    other_tokens = sum(
        call["input_total"] + call["output_total"]
        for agent in attempt["agent_usage"]
        for call in agent["provider_calls"]
        if call is not first_call
    )
    first_call.update(
        input_total=80_000 - other_tokens,
        cached_input=0,
        output_total=0,
        reasoning_output=0,
    )


def _failure(label: str, code: str = "false_test") -> dict[str, str]:
    return {"incident_id": _hash("incident-" + label)[:32], "code": code}


def _rating(
    artifact: dict[str, str], evaluator: str, q: int, *,
    failures: list[dict[str, str]] | None = None,
    adjudicator: bool = False,
    resolutions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    base, extra = divmod(q, 5)
    components = [base + int(index < extra) for index in range(5)]
    row: dict[str, Any] = {
        **artifact,
        "evaluator_id": evaluator,
        "role": "adjudicator" if adjudicator else "primary",
        "external_to_execution": True,
        "outcome_stage": {
            "recorded_at_utc": "2026-01-03T00:02:00Z" if adjudicator else "2026-01-03T00:00:00Z",
            "q_components": dict(zip(
                ("formulation", "evidence", "alternatives", "technical", "validation"),
                components, strict=True,
            )),
            "q_total": q,
            "artifact_form_reveal": {"revealed": False, "detail": None},
        },
        "trace_stage": {
            "recorded_at_utc": "2026-01-03T00:03:00Z" if adjudicator else "2026-01-03T00:01:00Z",
            "critical_failures": failures or [],
        },
    }
    if adjudicator:
        row["adjudication"] = {
            "q_resolution": {
                "basis": "third_locked_rating",
                "rationale": "The third locked assessment uses the blinded sources and tests "
                             "before the process traces were inspected by this evaluator.",
            },
            "critical_failure_resolutions": resolutions or [],
        }
    return row


def _resolution(incident: dict[str, str], code: str | None) -> dict[str, Any]:
    return {
        "incident_id": incident["incident_id"], "resolved_code": code,
        "rationale": "The declared trace and test output support this explicit incident "
                     "decision after comparison with both primary judgments.",
    }


def _bundle(
    schedule: dict[str, Any],
    specs: list[dict[str, Any]],
    *, extra_attempts: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    attempts = list(extra_attempts or [])
    artifacts = []
    ratings_rows = []
    links = []
    for spec in specs:
        run = spec["run"]
        attempt = _attempt(run, spec.get("status", "completed"))
        attempts.append(attempt)
        artifact = {
            "opaque_id": _hash("opaque-" + run["run_id"])[:32],
            "artifact_sha256": attempt["artifact_sha256"],
            "rubric_sha256": _hash("rubric"),
            "trace_sha256": attempt["trace_sha256"],
        }
        artifacts.append(artifact)
        first_failures, second_failures = spec.get("failures", ([], []))
        ratings_rows.extend([
            _rating(artifact, "external-a", spec["qs"][0], failures=first_failures),
            _rating(artifact, "external-b", spec["qs"][1], failures=second_failures),
        ])
        if "third_q" in spec:
            ratings_rows.append(_rating(
                artifact, "external-c", spec["third_q"], adjudicator=True,
                failures=spec.get("third_failures", []),
                resolutions=spec.get("resolutions", []),
            ))
        links.append({
            "opaque_id": artifact["opaque_id"],
            "run_id": run["run_id"], "run_sha256": run["run_sha256"],
        })
    receipts = {
        "schema": 1, "schedule_sha256": schedule["schedule_sha256"],
        "attempts": attempts,
    }
    manifest = {"schema": 1, "artifacts": artifacts}
    ratings = {
        "schema": 1, "manifest_sha256": _digest(manifest),
        "ratings": ratings_rows,
    }
    mapping = {
        "schema": 1, "schedule_sha256": schedule["schedule_sha256"],
        "receipts_sha256": _digest(receipts),
        "manifest_sha256": _digest(manifest),
        "ratings_sha256": _digest(ratings),
        "links": links,
    }
    return schedule, receipts, manifest, ratings, mapping


def _schema2_bundle(
    schedule: dict[str, Any], specs: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    bundle = _bundle(schedule, specs)
    _, receipts, manifest, ratings, mapping = bundle
    attempts = {row["run_id"]: row for row in receipts["attempts"]}
    artifacts = {row["opaque_id"]: row for row in manifest["artifacts"]}
    mapping["schema"] = 2
    for link in mapping["links"]:
        run_id = link["run_id"]
        artifact = artifacts[link["opaque_id"]]
        artifact["artifact_sha256"] = _hash("blind-package-" + run_id)
        artifact["trace_sha256"] = _hash("blind-trace-" + run_id)
        attempt = attempts[run_id]
        link.update({
            "terminal_artifact_sha256": attempt["artifact_sha256"],
            "terminal_trace_sha256": attempt["trace_sha256"],
            "blind_package_sha256": artifact["artifact_sha256"],
            "blind_trace_sha256": artifact["trace_sha256"],
            "preparation_record_sha256": _hash("externally-custodied-preparation-" + run_id),
        })
    for row in ratings["ratings"]:
        artifact = artifacts[row["opaque_id"]]
        row["artifact_sha256"] = artifact["artifact_sha256"]
        row["trace_sha256"] = artifact["trace_sha256"]
    ratings["manifest_sha256"] = _digest(manifest)
    mapping["manifest_sha256"] = _digest(manifest)
    mapping["ratings_sha256"] = _digest(ratings)
    return bundle


def _schema2_duplicate_terminal_pair_bundle(
    schedule: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    first, second = _independent_first_runs(schedule, 2)
    bundle = _schema2_bundle(schedule, [
        {"run": first, "qs": (40, 40)},
        {"run": second, "qs": (80, 80)},
    ])
    receipts, mapping = bundle[1], bundle[4]
    first_terminal, second_terminal = receipts["attempts"]
    for key in ("artifact_sha256", "trace_sha256"):
        second_terminal[key] = first_terminal[key]
    second_link = mapping["links"][1]
    second_link["terminal_artifact_sha256"] = second_terminal["artifact_sha256"]
    second_link["terminal_trace_sha256"] = second_terminal["trace_sha256"]
    mapping["receipts_sha256"] = _digest(receipts)
    return bundle


def _rows(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["run_id"]: row for row in result["evaluations"]["runs"]}


def test_pair_mean_keeps_half_point_agreed_incidents_and_no_result_claim(
    schedule: dict[str, Any],
) -> None:
    run, unmapped = _independent_first_runs(schedule, 2)
    failures = [_failure("one"), _failure("two")]
    bundle = _bundle(schedule, [{"run": run, "qs": (60, 61), "failures": (failures, failures)}],
                     extra_attempts=[_attempt(unmapped)])

    result = assemble_rated_q(*bundle)

    assert _rows(result)[run["run_id"]] == {
        "run_id": run["run_id"], "status": "scored", "q": 60.5,
        "artifact_sha256": _hash("artifact-" + run["run_id"]),
    }
    assert _rows(result)[unmapped["run_id"]]["status"] == "missing"
    assert "no blind rating mapping" in _rows(result)[unmapped["run_id"]]["reason"]
    assert len(result["evaluations"]["runs"]) == len(schedule["runs"])
    detail = result["details"][0]
    assert [item["q_total"] for item in detail["raw_q"]["primary"]] == [60, 61]
    assert [sum(item["q_components"].values()) for item in detail["raw_q"]["primary"]] == [60, 61]
    assert detail["adjudication"] == {"basis": "primary_arithmetic_mean", "triggers": []}
    assert detail["sensitivity"]["primary_mean_q"] == 60.5
    assert detail["critical_incidents"] == {
        item["incident_id"]: item["code"] for item in failures
    }
    assert detail["E"] == 1
    assert "E" not in _rows(result)[run["run_id"]]
    assert result["classification"].endswith("_unsealed")
    assert result["mapping_schema"] == 1
    assert detail["terminal_artifact_sha256"] == detail["blind_package_sha256"]
    assert detail["terminal_trace_sha256"] == detail["blind_trace_sha256"]
    assert detail["preparation_record_sha256"] is None
    assert result["criterion_4"]["status"] == "not_assessed"
    assert "no real-world validity" in result["notice"]
    assert "full blinded result package" in result["notice"]
    assert "result claim" in result["notice"]


def test_schema2_separates_terminal_and_blind_digests_and_reconciles(
    schedule: dict[str, Any],
) -> None:
    run = _independent_first_runs(schedule, 1)[0]
    bundle = _schema2_bundle(schedule, [{"run": run, "qs": (60, 61)}])

    result = assemble_rated_q(*bundle)
    row = _rows(result)[run["run_id"]]
    detail = result["details"][0]
    reconciliation = reconcile(schedule, bundle[1], result["evaluations"])

    assert result["mapping_schema"] == 2
    assert row["q"] == 60.5
    assert row["artifact_sha256"] == bundle[1]["attempts"][0]["artifact_sha256"]
    assert row["artifact_sha256"] != detail["blind_package_sha256"]
    assert detail["terminal_artifact_sha256"] == row["artifact_sha256"]
    assert detail["terminal_trace_sha256"] == bundle[1]["attempts"][0]["trace_sha256"]
    assert detail["terminal_trace_sha256"] != detail["blind_trace_sha256"]
    assert detail["blind_package_sha256"] == bundle[2]["artifacts"][0]["artifact_sha256"]
    assert detail["blind_trace_sha256"] == bundle[2]["artifacts"][0]["trace_sha256"]
    assert detail["preparation_record_sha256"] == bundle[4]["links"][0]["preparation_record_sha256"]
    assert "does not open or verify that record" in result["notice"]
    assert reconciliation["issues"] == []
    assert reconciliation["counts"]["concordant_scored_runs"] == 1
    assert reconciliation["declared_joint_coverage_complete"] is False
    assert result["duplicate_terminal_pairs_requiring_external_preparation_verification"] == []


def test_schema2_duplicate_terminal_pair_uses_distinct_blind_packages_and_prep_pointers(
    schedule: dict[str, Any],
) -> None:
    bundle = _schema2_duplicate_terminal_pair_bundle(schedule)

    result = assemble_rated_q(*bundle)
    rows = _rows(result)
    details = {detail["run_id"]: detail for detail in result["details"]}
    first, second = _independent_first_runs(schedule, 2)
    warnings = result["duplicate_terminal_pairs_requiring_external_preparation_verification"]
    reconciliation = reconcile(schedule, bundle[1], result["evaluations"])

    assert rows[first["run_id"]]["q"] == 40
    assert rows[second["run_id"]]["q"] == 80
    assert rows[first["run_id"]]["artifact_sha256"] == rows[second["run_id"]]["artifact_sha256"]
    assert details[first["run_id"]]["blind_package_sha256"] != details[second["run_id"]]["blind_package_sha256"]
    assert (
        details[first["run_id"]]["preparation_record_sha256"]
        != details[second["run_id"]]["preparation_record_sha256"]
    )
    assert warnings == [{
        "terminal_artifact_sha256": rows[first["run_id"]]["artifact_sha256"],
        "terminal_trace_sha256": bundle[1]["attempts"][0]["trace_sha256"],
        "terminal_run_ids": sorted([first["run_id"], second["run_id"]]),
        "mapped_run_ids": sorted([first["run_id"], second["run_id"]]),
    }]
    assert reconciliation["issues"] == []
    assert reconciliation["counts"]["concordant_scored_runs"] == 2
    assert result["criterion_4"]["status"] == "not_assessed"


def test_schema2_rejects_reused_preparation_pointer_across_duplicate_terminal_pair(
    schedule: dict[str, Any],
) -> None:
    bundle = _schema2_duplicate_terminal_pair_bundle(schedule)
    links = bundle[4]["links"]
    links[1]["preparation_record_sha256"] = links[0]["preparation_record_sha256"]

    with pytest.raises(AssemblyError, match="duplicate preparation_record_sha256"):
        assemble_rated_q(*bundle)


@pytest.mark.parametrize("digest_key", [
    "terminal_artifact_sha256", "terminal_trace_sha256",
    "blind_package_sha256", "blind_trace_sha256",
])
def test_schema2_rejects_each_misbound_digest(
    schedule: dict[str, Any], digest_key: str,
) -> None:
    run = _independent_first_runs(schedule, 1)[0]
    bundle = _schema2_bundle(schedule, [{"run": run, "qs": (60, 60)}])
    bundle[4]["links"][0][digest_key] = _hash("wrong-" + digest_key)

    with pytest.raises(AssemblyError, match=f"{digest_key} mismatch"):
        assemble_rated_q(*bundle)


@pytest.mark.parametrize("change,match", [
    ("missing", "missing keys.*preparation_record_sha256"),
    ("malformed", "preparation_record_sha256 must be a lowercase SHA-256 digest"),
])
def test_schema2_requires_well_formed_preparation_record_pointer(
    schedule: dict[str, Any], change: str, match: str,
) -> None:
    run = _independent_first_runs(schedule, 1)[0]
    bundle = _schema2_bundle(schedule, [{"run": run, "qs": (60, 60)}])
    link = bundle[4]["links"][0]
    if change == "missing":
        del link["preparation_record_sha256"]
    else:
        link["preparation_record_sha256"] = "not-a-digest"

    with pytest.raises(AssemblyError, match=match):
        assemble_rated_q(*bundle)


def test_ten_point_boundary_uses_mean_but_eleven_points_uses_third(
    schedule: dict[str, Any],
) -> None:
    first, second = _independent_first_runs(schedule, 2)
    bundle = _bundle(schedule, [
        {"run": first, "qs": (60, 70)},
        {"run": second, "qs": (60, 71), "third_q": 55},
    ])

    result = assemble_rated_q(*bundle)

    assert _rows(result)[first["run_id"]]["q"] == 65
    assert _rows(result)[second["run_id"]]["q"] == 55
    second_detail = next(row for row in result["details"] if row["run_id"] == second["run_id"])
    assert second_detail["raw_q"]["adjudicator"]["q_total"] == 55
    assert second_detail["adjudication"]["triggers"] == ["q_total_difference_gt_10"]
    assert second_detail["sensitivity"] == {
        "primary_mean_q": 65.5, "selected_q": 55,
        "selected_minus_primary_mean_q": -10.5,
    }
    assert result["counts"]["adjudicated_runs"] == 1


def test_incident_only_adjudication_preserves_agreed_and_uses_third_decisions(
    schedule: dict[str, Any],
) -> None:
    run = _independent_first_runs(schedule, 1)[0]
    agreed = _failure("agreed", "invented_claim")
    disputed = _failure("disputed", "false_test")
    newly_found = _failure("new", "unsafe_action")
    bundle = _bundle(schedule, [{
        "run": run, "qs": (50, 50),
        "failures": ([agreed, disputed], [agreed]),
        "third_q": 42, "third_failures": [newly_found],
        "resolutions": [_resolution(disputed, None), _resolution(newly_found, "unsafe_action")],
    }])

    result = assemble_rated_q(*bundle)

    detail = result["details"][0]
    assert _rows(result)[run["run_id"]]["q"] == 42
    assert detail["adjudication"]["triggers"] == ["critical_failure_disagreement"]
    assert detail["critical_incidents"] == {
        agreed["incident_id"]: agreed["code"],
        newly_found["incident_id"]: newly_found["code"],
    }
    assert detail["raw_critical_incidents"]["adjudicator"]["incidents"] == {
        newly_found["incident_id"]: newly_found["code"],
    }
    assert disputed["incident_id"] not in detail["critical_incidents"]
    assert detail["E"] == 1


def test_missing_and_truncated_are_explicit_and_truncated_artifact_can_be_scored(
    schedule: dict[str, Any],
) -> None:
    failed, bare_truncated, rated_truncated = _independent_first_runs(schedule, 3)
    bundle = _bundle(
        schedule, [{"run": rated_truncated, "status": "truncated", "qs": (40, 40)}],
        extra_attempts=[
            _attempt(failed, "external_failure"),
            _attempt(bare_truncated, "truncated", artifact=False),
        ],
    )
    for attempt in bundle[1]["attempts"]:
        if attempt["status"] == "truncated":
            _reach_measured_token_cap(attempt)
    bundle[4]["receipts_sha256"] = _digest(bundle[1])

    result = assemble_rated_q(*bundle)
    rows = _rows(result)

    assert rows[failed["run_id"]] == {
        "run_id": failed["run_id"], "status": "missing",
        "reason": "external_failure_without_terminal_receipt",
    }
    assert rows[bare_truncated["run_id"]] == {
        "run_id": bare_truncated["run_id"], "status": "truncated",
        "reason": "terminal truncated receipt has no artifact",
    }
    assert rows[rated_truncated["run_id"]]["status"] == "truncated"
    assert rows[rated_truncated["run_id"]]["q"] == 40
    assert rows[rated_truncated["run_id"]]["artifact_sha256"] == _hash(
        "artifact-" + rated_truncated["run_id"]
    )
    assert result["counts"]["truncated_scored_runs"] == 1


@pytest.mark.parametrize("digest_key", [
    "schedule_sha256", "receipts_sha256", "manifest_sha256", "ratings_sha256",
])
def test_mapping_document_digests_must_match_exactly(
    schedule: dict[str, Any], digest_key: str,
) -> None:
    run = _independent_first_runs(schedule, 1)[0]
    bundle = list(_bundle(schedule, [{"run": run, "qs": (60, 60)}]))
    bundle[4][digest_key] = _hash("wrong-" + digest_key)

    with pytest.raises(AssemblyError, match=f"mapping.{digest_key} digest mismatch"):
        assemble_rated_q(*bundle)


def test_self_consistent_blind_rubric_substitution_is_rejected(
    schedule: dict[str, Any],
) -> None:
    first, second = _independent_first_runs(schedule, 2)
    bundle = list(_bundle(schedule, [
        {"run": first, "qs": (60, 60)},
        {"run": second, "qs": (60, 60)},
    ]))
    _, _, manifest, ratings, mapping = bundle
    changed = manifest["artifacts"][1]
    changed["rubric_sha256"] = _hash("substituted-rubric")
    for row in ratings["ratings"]:
        if row["opaque_id"] == changed["opaque_id"]:
            row["rubric_sha256"] = changed["rubric_sha256"]
    ratings["manifest_sha256"] = _digest(manifest)
    mapping["manifest_sha256"] = _digest(manifest)
    mapping["ratings_sha256"] = _digest(ratings)

    with pytest.raises(AssemblyError, match="rubric_sha256 differs from scheduled rubric"):
        assemble_rated_q(*bundle)


def test_duplicate_terminal_digest_pair_rejects_swapped_private_links(
    schedule: dict[str, Any],
) -> None:
    first, second = _independent_first_runs(schedule, 2)
    bundle = list(_bundle(schedule, [
        {"run": first, "qs": (40, 40)},
        {"run": second, "qs": (80, 80)},
    ]))
    _, receipts, manifest, ratings, mapping = bundle
    first_artifact, second_artifact = manifest["artifacts"]
    for key in ("artifact_sha256", "trace_sha256"):
        second_artifact[key] = first_artifact[key]
        receipts["attempts"][1][key] = first_artifact[key]
    for row in ratings["ratings"]:
        if row["opaque_id"] == second_artifact["opaque_id"]:
            row["artifact_sha256"] = second_artifact["artifact_sha256"]
            row["trace_sha256"] = second_artifact["trace_sha256"]
    ratings["manifest_sha256"] = _digest(manifest)
    mapping["receipts_sha256"] = _digest(receipts)
    mapping["manifest_sha256"] = _digest(manifest)
    mapping["ratings_sha256"] = _digest(ratings)
    links = mapping["links"]
    for key in ("run_id", "run_sha256"):
        links[0][key], links[1][key] = links[1][key], links[0][key]

    with pytest.raises(AssemblyError, match="ambiguous terminal artifact/trace digest pair"):
        assemble_rated_q(*bundle)


def test_unmapped_terminal_digest_collision_cannot_take_single_rated_link(
    schedule: dict[str, Any],
) -> None:
    rated_run, other_run = _independent_first_runs(schedule, 2)
    bundle = list(_bundle(
        schedule, [{"run": rated_run, "qs": (40, 40)}],
        extra_attempts=[_attempt(other_run)],
    ))
    _, receipts, manifest, _, mapping = bundle
    rated_artifact = manifest["artifacts"][0]
    other_terminal = next(
        row for row in receipts["attempts"] if row["run_id"] == other_run["run_id"]
    )
    other_terminal["artifact_sha256"] = rated_artifact["artifact_sha256"]
    other_terminal["trace_sha256"] = rated_artifact["trace_sha256"]
    mapping["receipts_sha256"] = _digest(receipts)
    mapping["links"][0]["run_id"] = other_run["run_id"]
    mapping["links"][0]["run_sha256"] = other_run["run_sha256"]

    with pytest.raises(AssemblyError, match="ambiguous terminal artifact/trace digest pair"):
        assemble_rated_q(*bundle)


def test_duplicate_pair_only_between_unmapped_runs_keeps_missing_rows(
    schedule: dict[str, Any],
) -> None:
    rated_run, first_unmapped, second_unmapped = _independent_first_runs(schedule, 3)
    bundle = list(_bundle(
        schedule, [{"run": rated_run, "qs": (40, 40)}],
        extra_attempts=[_attempt(first_unmapped), _attempt(second_unmapped)],
    ))
    receipts, mapping = bundle[1], bundle[4]
    by_run = {row["run_id"]: row for row in receipts["attempts"]}
    for key in ("artifact_sha256", "trace_sha256"):
        by_run[second_unmapped["run_id"]][key] = by_run[first_unmapped["run_id"]][key]
    mapping["receipts_sha256"] = _digest(receipts)

    rows = _rows(assemble_rated_q(*bundle))

    assert rows[rated_run["run_id"]]["q"] == 40
    for run in (first_unmapped, second_unmapped):
        assert rows[run["run_id"]] == {
            "run_id": run["run_id"], "status": "missing",
            "reason": "terminal completed receipt has no blind rating mapping",
        }


def test_declared_rating_lock_must_follow_terminal_receipt(
    schedule: dict[str, Any],
) -> None:
    run = _independent_first_runs(schedule, 1)[0]
    bundle = list(_bundle(schedule, [{"run": run, "qs": (60, 60)}]))
    receipts, mapping = bundle[1], bundle[4]
    terminal = receipts["attempts"][0]
    later_start = datetime(2026, 1, 4, tzinfo=timezone.utc)
    terminal["started_at_utc"] = later_start.isoformat().replace("+00:00", "Z")
    terminal["ended_at_utc"] = (later_start + timedelta(seconds=10)).isoformat().replace(
        "+00:00", "Z"
    )
    mapping["receipts_sha256"] = _digest(receipts)

    with pytest.raises(AssemblyError, match="outcome_stage recorded_at_utc must be after terminal receipt"):
        assemble_rated_q(*bundle)


@pytest.mark.parametrize("change,match", [
    ("wrong_run_sha", "run_sha256 mismatch"),
    ("wrong_artifact", "terminal artifact_sha256 mismatch"),
    ("wrong_trace", "terminal trace_sha256 mismatch"),
    ("unmapped_manifest", "mapping omits"),
])
def test_mapping_requires_exact_run_and_terminal_bindings(
    schedule: dict[str, Any], change: str, match: str,
) -> None:
    run = _independent_first_runs(schedule, 1)[0]
    bundle = list(_bundle(schedule, [{"run": run, "qs": (60, 60)}]))
    _, receipts, _, _, mapping = bundle
    if change == "wrong_run_sha":
        mapping["links"][0]["run_sha256"] = _hash("wrong-run")
    elif change == "wrong_artifact":
        receipts["attempts"][0]["artifact_sha256"] = _hash("different-artifact")
        mapping["receipts_sha256"] = _digest(receipts)
    elif change == "wrong_trace":
        receipts["attempts"][0]["trace_sha256"] = _hash("different-trace")
        mapping["receipts_sha256"] = _digest(receipts)
    else:
        mapping["links"] = []

    with pytest.raises(AssemblyError, match=match):
        assemble_rated_q(*bundle)


@pytest.mark.parametrize("duplicate_field", ["opaque_id", "run_id"])
def test_duplicate_mapping_is_rejected(
    schedule: dict[str, Any], duplicate_field: str,
) -> None:
    first, second = _independent_first_runs(schedule, 2)
    bundle = list(_bundle(schedule, [
        {"run": first, "qs": (50, 50)},
        {"run": second, "qs": (50, 50)},
    ]))
    links = bundle[4]["links"]
    links[1][duplicate_field] = links[0][duplicate_field]

    with pytest.raises(AssemblyError, match=f"duplicate mapping {duplicate_field}"):
        assemble_rated_q(*bundle)


def test_receipt_audit_violation_rejected_even_with_matching_mapping_digest(
    schedule: dict[str, Any],
) -> None:
    run = _independent_first_runs(schedule, 1)[0]
    bundle = list(_bundle(schedule, [{"run": run, "qs": (50, 50)}]))
    receipts, mapping = bundle[1], bundle[4]
    receipts["attempts"][0]["agent_usage"][0]["provider_calls"][0]["input_total"] = 80_001
    mapping["receipts_sha256"] = _digest(receipts)

    with pytest.raises(AssemblyError, match="receipt audit reports 1 violation.*measured_tokens_over_cap"):
        assemble_rated_q(*bundle)


def test_mapping_cannot_claim_missing_terminal_or_truncated_without_artifact(
    schedule: dict[str, Any],
) -> None:
    run = _independent_first_runs(schedule, 1)[0]
    for status, artifact, message in (
        ("external_failure", False, "lacks a terminal"),
        ("truncated", False, "has no terminal artifact"),
    ):
        bundle = list(_bundle(schedule, [{"run": run, "qs": (60, 60)}]))
        receipts, mapping = bundle[1], bundle[4]
        receipts["attempts"][0] = _attempt(run, status, artifact=artifact)
        if status == "truncated":
            _reach_measured_token_cap(receipts["attempts"][0])
        mapping["receipts_sha256"] = _digest(receipts)
        with pytest.raises(AssemblyError, match=message):
            assemble_rated_q(*bundle)


def test_cli_success_and_structured_stdin_error(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    run = _independent_first_runs(schedule, 1)[0]
    bundle = _bundle(schedule, [{"run": run, "qs": (60, 61)}])
    paths = []
    for index, value in enumerate(bundle):
        path = tmp_path / f"input-{index}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths.append(str(path))

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), *paths],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    output = json.loads(completed.stdout)
    assert _rows(output)[run["run_id"]]["q"] == 60.5
    assert output["criterion_4"]["status"] == "not_assessed"

    paths[1:3] = ["-", "-"]
    failed = subprocess.run(
        [sys.executable, str(SCRIPT), *paths],
        input="{}", capture_output=True, text=True, check=False,
    )
    assert failed.returncode == 2
    assert json.loads(failed.stdout)["error"] == {
        "code": "invalid_input", "message": "only one input may use stdin",
    }
