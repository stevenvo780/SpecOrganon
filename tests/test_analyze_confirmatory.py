"""Q-only paired analysis stays complete, balanced, deterministic, and read-only."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "analyze_confirmatory.py"
sys.path.insert(0, str(SCRIPTS))
from analyze_confirmatory import AnalysisError, analyze  # noqa: E402
from plan_confirmatory import compile_schedule  # noqa: E402


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _ref(label: str) -> dict[str, str]:
    return {"ref": f"synthetic/{label}", "sha256": _hash(label)}


def _manifest(*, one_single_effort: bool = False) -> dict[str, Any]:
    models = []
    for family in ("family-a", "family-b"):
        for tier in ("lower", "higher"):
            single = one_single_effort and family == "family-a" and tier == "lower"
            models.append({
                "family": family,
                "tier": tier,
                "model_id": f"{family}/{tier}",
                "version": "synthetic-v1",
                "effort_control": not single,
                "efforts": ([{"label": "default"}] if single else [
                    {"label": "low", "provider_value": "low"},
                    {"label": "high", "provider_value": "high"},
                ]),
            })
    return {
        "schema": 1,
        "seed": 73,
        "protocol_sha256": _hash("synthetic protocol"),
        "tool_call_cap": 100,
        "models": models,
        "cases": [
            {"case_id": case_id, "package_sha256": _hash(case_id),
             "reference_sha256": _hash(f"sealed-reference-{case_id}")}
            for case_id in ("R-F", "R-M", "R-S")
        ],
        "inputs": {
            "task_contract": _ref("task"),
            "common_prompt": _ref("common"),
            "arm_prompts": {arm: _ref(f"{arm}-prompt") for arm in ("N", "S", "T")},
            "rubric": _ref("rubric"),
            "tool_policy": _ref("tool-policy"),
            "sdd_guide": _ref("guide"),
            "toolkit": _ref("toolkit"),
        },
    }


def _schedule(*, one_single_effort: bool = False) -> dict[str, Any]:
    return compile_schedule(_manifest(one_single_effort=one_single_effort))


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reseal_schedule(schedule: dict[str, Any], *, runs: bool) -> None:
    if runs:
        for run in schedule["runs"]:
            body = {key: value for key, value in run.items() if key not in ("run_id", "run_sha256")}
            run["run_sha256"] = _digest(body)
            run["run_id"] = "conf-" + run["run_sha256"][:24]
    schedule["schedule_sha256"] = _digest({key: value for key, value in schedule.items() if key != "schedule_sha256"})


def _evaluations(schedule: dict[str, Any], score: Any = None) -> dict[str, Any]:
    rows = []
    for run in schedule["runs"]:
        q = score(run) if score is not None else 50
        rows.append({"run_id": run["run_id"], "q": q})
    return {"schema": 1, "schedule_sha256": schedule["schedule_sha256"], "runs": rows}


def test_equal_model_weight_when_one_model_lacks_effort() -> None:
    schedule = _schedule(one_single_effort=True)
    evaluations = _evaluations(schedule, lambda run: 100 if run["model_id"] == "family-a/lower" and run["arm"] == "T" else 0)

    result = analyze(schedule, evaluations, development_resamples=120)

    assert result["classification"] == "development_analysis_unsealed"
    assert result["matrix_complete"] is True
    assert result["counts"]["scheduled_runs"] == 378
    assert result["counts"]["complete_triplets"] == 126
    assert result["counts"]["incomplete_triplets"] == 0
    for label in ("T_minus_S", "T_minus_N"):
        effect = result["primary_effects"][label]
        assert effect["mean"] == pytest.approx(25)
        assert effect["ci95_percentile"] == pytest.approx([25, 25])
        assert effect["by_model"] == {
            "family-a/higher": 0,
            "family-a/lower": 100,
            "family-b/higher": 0,
            "family-b/lower": 0,
        }
    assert result["criterion_4"]["status"] == "not_assessed"
    assert result["bootstrap"]["resamples"] == 120
    assert result["bootstrap"]["default_resamples"] == 10_000


def test_aggregate_advantage_does_not_hide_a_case_deterioration() -> None:
    schedule = _schedule(one_single_effort=True)
    evaluations = _evaluations(schedule, lambda run: (
        20 if run["arm"] == "N" else
        50 if run["arm"] == "S" else
        30 if run["case_id"] == "R-F" else 100
    ))

    result = analyze(schedule, evaluations, development_resamples=30)
    effect = result["primary_effects"]["T_minus_S"]
    assert effect["mean"] == pytest.approx(80 / 3)
    assert effect["ci95_percentile"] == pytest.approx([80 / 3, 80 / 3])
    assert effect["by_case"] == pytest.approx({"R-F": -20, "R-M": 50, "R-S": 50})
    assert effect["by_agents"] == pytest.approx({"solo": 80 / 3, "trio": 80 / 3})
    assert effect["by_family"] == pytest.approx({"family-a": 80 / 3, "family-b": 80 / 3})
    assert effect["by_model_effort"]["family-a/lower"]["default"] == pytest.approx(80 / 3)
    assert all(row["mean"] == -20 for row in effect["by_stratum"] if row["case_id"] == "R-F")
    cell = next(row for row in result["q_cells"] if row["model_id"] == "family-a/lower"
                and row["effort"] == "default" and row["agents"] == "solo" and row["case_id"] == "R-F")
    assert cell["arms"]["T"]["q_by_replica"] == [30, 30, 30]
    assert cell["arms"]["T"]["median"] == 30
    assert cell["arms"]["T"]["range"] == [30, 30]
    assert cell["paired_effects"]["T_minus_S"]["by_replica"] == [-20, -20, -20]
    assert cell["critical_failures"] is None
    assert result["criterion_4"]["status"] == "not_assessed"


def test_effort_effect_is_reported_within_each_model() -> None:
    schedule = _schedule()
    evaluations = _evaluations(schedule, lambda run: (
        20 if run["arm"] == "N" else
        50 if run["arm"] == "S" else
        40 if run["effort"] == "low" else 70
    ))
    result = analyze(schedule, evaluations, development_resamples=20)
    effect = result["primary_effects"]["T_minus_S"]
    assert effect["mean"] == pytest.approx(5)
    assert effect["by_model_effort"] == {
        model["model_id"]: {"high": pytest.approx(20), "low": pytest.approx(-10)}
        for model in schedule["models"]
    }


def test_reduced_run_without_work_identity_is_rejected() -> None:
    schedule = _schedule(one_single_effort=True)
    fields = ("run_id", "model_id", "effort", "agents", "case_id", "replica",
              "arm", "block_id", "order_position")
    schedule["runs"] = [{field: run[field] for field in fields} for run in schedule["runs"]]
    _reseal_schedule(schedule, runs=False)
    evaluations = _evaluations(schedule)

    with pytest.raises(AnalysisError, match="missing identity fields"):
        analyze(schedule, evaluations, development_resamples=20)


def test_paired_bootstrap_is_reproducible_and_evaluation_order_independent() -> None:
    schedule = _schedule()
    variation = {1: -8, 2: 0, 3: 13}
    evaluations = _evaluations(schedule, lambda run: (
        40 + run["replica"] * 2 if run["arm"] == "N" else
        48 + run["replica"] * 2 if run["arm"] == "S" else
        60 + run["replica"] * 2 + variation[run["replica"]]
    ))
    first = analyze(schedule, evaluations, development_resamples=300, seed=17)
    evaluations["runs"].reverse()
    second = analyze(schedule, evaluations, development_resamples=300, seed=17)

    assert first == second
    assert first["bootstrap"] == {"seed": 17, "resamples": 300, "default_resamples": 10_000}
    assert first["primary_effects"]["T_minus_S"]["mean"] == pytest.approx(12 + 5 / 3)
    assert first["primary_effects"]["T_minus_N"]["mean"] == pytest.approx(20 + 5 / 3)
    for effect in first["primary_effects"].values():
        low, high = effect["ci95_percentile"]
        assert low < effect["mean"] < high
    ci_s = first["primary_effects"]["T_minus_S"]["ci95_percentile"]
    ci_n = first["primary_effects"]["T_minus_N"]["ci95_percentile"]
    assert [n - s for n, s in zip(ci_n, ci_s)] == pytest.approx([8, 8])
    assert first["counts"]["complete_triplets"] == 144


def test_truncation_with_q_is_kept_and_negative_result_remains_visible() -> None:
    schedule = _schedule()
    evaluations = _evaluations(schedule, lambda run: 30 if run["arm"] == "S" else 20)
    target = next(run for run in schedule["runs"] if run["arm"] == "T")
    row = next(row for row in evaluations["runs"] if row["run_id"] == target["run_id"])
    row.update({"status": "truncated", "q": 0, "reason": "time limit"})

    result = analyze(schedule, evaluations, development_resamples=40)

    assert result["matrix_complete"] is True
    assert result["counts"]["truncated_runs"] == 1
    assert result["counts"]["truncated_scored_runs"] == 1
    triplet = next(item for item in result["triplets"] if item["block_id"] == target["block_id"])
    assert triplet["T_minus_S"] == -30
    assert triplet["arms"]["T"] == {
        "run_id": target["run_id"], "status": "truncated", "q": 0, "reason": "time limit"
    }
    assert result["descriptive_available_pairs"]["T_minus_S"]["minimum"] == -30


def test_incomplete_triplet_retains_available_pair_but_has_no_primary_effect() -> None:
    schedule = _schedule()
    evaluations = _evaluations(schedule, lambda run: {"N": 20, "S": 40, "T": 60}[run["arm"]])
    target = next(run for run in schedule["runs"] if run["arm"] == "N")
    row = next(row for row in evaluations["runs"] if row["run_id"] == target["run_id"])
    row.pop("q")
    row.update({"status": "truncated", "reason": "no usable artifacts"})

    result = analyze(schedule, evaluations, development_resamples=20)

    assert result["matrix_complete"] is False
    assert result["primary_effects"] is None
    assert result["bootstrap"]["resamples"] == 0
    assert result["counts"]["complete_triplets"] == 143
    assert result["counts"]["incomplete_triplets"] == 1
    assert result["descriptive_available_pairs"]["T_minus_S"] == {
        "count": 144, "mean": 20, "minimum": 20, "maximum": 20,
    }
    assert result["descriptive_available_pairs"]["T_minus_N"]["count"] == 143
    assert result["incomplete_triplets"][0]["arms"]["N"]["status"] == "truncated"
    assert result["incomplete_triplets"][0]["T_minus_S"] == 20
    cell = next(item for item in result["q_cells"] if all(item[key] == target[key]
                for key in ("model_id", "effort", "agents", "case_id")))
    assert cell["arms"]["N"]["q_by_replica"][target["replica"] - 1] is None
    assert cell["arms"]["N"]["unscored"] == 1
    assert cell["arms"]["N"]["truncated"] == 1
    assert cell["paired_effects"]["T_minus_N"]["complete_pairs"] == 2
    assert result["criterion_4"]["status"] == "not_assessed"
    assert "matrix is also incomplete" in result["criterion_4"]["reason"]


@pytest.mark.parametrize("change,match", [
    ("omitted", "omit"),
    ("duplicate", "duplicate evaluated run_id"),
    ("unscheduled", "unscheduled evaluated run_id"),
    ("schedule_mismatch", "evaluation schedule digest mismatch"),
    ("missing_with_q", "cannot carry q"),
    ("scored_without_q", "requires q"),
    ("bad_status", "status must"),
])
def test_invalid_evaluation_identity_or_status_rejected(change: str, match: str) -> None:
    schedule = _schedule()
    evaluations = _evaluations(schedule)
    if change == "omitted":
        evaluations["runs"].pop()
    elif change == "duplicate":
        evaluations["runs"][1]["run_id"] = evaluations["runs"][0]["run_id"]
    elif change == "unscheduled":
        evaluations["runs"][0]["run_id"] = "conf-unscheduled"
    elif change == "schedule_mismatch":
        evaluations["schedule_sha256"] = "0" * 64
    elif change == "missing_with_q":
        evaluations["runs"][0]["status"] = "missing"
    elif change == "scored_without_q":
        evaluations["runs"][0].pop("q")
    elif change == "bad_status":
        evaluations["runs"][0]["status"] = "replaced"
    with pytest.raises(AnalysisError, match=match):
        analyze(schedule, evaluations, development_resamples=10)


@pytest.mark.parametrize("bad_q", [-0.01, 100.01, True, None, "42", float("nan"), float("inf"), 10**500])
def test_malformed_q_rejected(bad_q: Any) -> None:
    schedule = _schedule()
    evaluations = _evaluations(schedule)
    evaluations["runs"][0]["q"] = bad_q
    with pytest.raises(AnalysisError, match="q must be a finite number"):
        analyze(schedule, evaluations, development_resamples=10)


def test_optional_scored_artifact_digest_is_validated_and_preserved() -> None:
    schedule = _schedule()
    evaluations = _evaluations(schedule)
    row = evaluations["runs"][0]
    row["artifact_sha256"] = _hash("synthetic scored artifact")
    result = analyze(schedule, evaluations, development_resamples=10)
    assert any(
        arm.get("artifact_sha256") == row["artifact_sha256"]
        for triplet in result["triplets"] for arm in triplet["arms"].values()
    )

    row["artifact_sha256"] = "invalid"
    with pytest.raises(AnalysisError, match="artifact_sha256"):
        analyze(schedule, evaluations, development_resamples=10)
    row["artifact_sha256"] = _hash("synthetic scored artifact")
    row.pop("q")
    row["status"] = "truncated"
    with pytest.raises(AnalysisError, match="artifact_sha256 requires q"):
        analyze(schedule, evaluations, development_resamples=10)


def test_tampered_schedule_digest_rejected() -> None:
    schedule = _schedule()
    evaluations = _evaluations(schedule)
    schedule = copy.deepcopy(schedule)
    schedule["runs"][0]["order_position"] = 99
    with pytest.raises(AnalysisError, match="schedule digest mismatch"):
        analyze(schedule, evaluations, development_resamples=10)


@pytest.mark.parametrize("field,value", [
    ("input_sha256", _hash("foreign input")),
    ("family", "foreign-family"),
    ("tier", "foreign-tier"),
    ("model_version", "foreign-version"),
    ("effort_provider_value", "foreign-effort"),
    ("case_package_sha256", _hash("foreign package")),
    ("case_reference_sha256", _hash("foreign reference")),
])
def test_rehashed_run_with_foreign_work_identity_is_rejected(field: str, value: str) -> None:
    schedule = _schedule()
    target = schedule["runs"][0]
    target[field] = value
    _reseal_schedule(schedule, runs=True)

    with pytest.raises(AnalysisError, match="work identity differs"):
        analyze(schedule, _evaluations(schedule), development_resamples=10)


def test_run_hash_and_run_id_are_checked_independently_of_schedule_digest() -> None:
    schedule = _schedule()
    schedule["runs"][0]["case_package_sha256"] = _hash("foreign package")
    _reseal_schedule(schedule, runs=False)
    with pytest.raises(AnalysisError, match="run_sha256 mismatch"):
        analyze(schedule, _evaluations(schedule), development_resamples=10)

    schedule = _schedule()
    schedule["runs"][0]["run_id"] = "conf-" + "0" * 24
    _reseal_schedule(schedule, runs=False)
    with pytest.raises(AnalysisError, match="run_id does not match run_sha256"):
        analyze(schedule, _evaluations(schedule), development_resamples=10)


def test_input_digest_is_bound_to_schedule_metadata() -> None:
    schedule = _schedule()
    schedule["cases"][0]["package_sha256"] = _hash("different package")
    _reseal_schedule(schedule, runs=False)

    with pytest.raises(AnalysisError, match="schedule input digest mismatch"):
        analyze(schedule, _evaluations(schedule), development_resamples=10)


def test_each_arm_must_use_each_position_once_across_replicas() -> None:
    schedule = _schedule()
    first = schedule["runs"][0]
    stratum = (first["model_id"], first["effort"], first["agents"], first["case_id"])
    siblings = [
        run for run in schedule["runs"]
        if (run["model_id"], run["effort"], run["agents"], run["case_id"]) == stratum
    ]
    first_positions = {run["arm"]: run["order_position"] for run in siblings if run["replica"] == 1}
    for run in siblings:
        if run["replica"] == 2:
            run["order_position"] = first_positions[run["arm"]]
    assert {run["order_position"] for run in siblings if run["replica"] == 2} == {1, 2, 3}
    _reseal_schedule(schedule, runs=True)

    with pytest.raises(AnalysisError, match="not counterbalanced"):
        analyze(schedule, _evaluations(schedule), development_resamples=10)


def test_balanced_but_wrong_seeded_arm_order_is_rejected() -> None:
    schedule = _schedule()
    first = schedule["runs"][0]
    stratum = (first["model_id"], first["effort"], first["agents"], first["case_id"])
    siblings = [
        run for run in schedule["runs"]
        if (run["model_id"], run["effort"], run["agents"], run["case_id"]) == stratum
    ]
    for replica in (1, 2, 3):
        block = {run["arm"]: run for run in siblings if run["replica"] == replica}
        block["N"]["order_position"], block["S"]["order_position"] = (
            block["S"]["order_position"], block["N"]["order_position"]
        )
        assert {run["order_position"] for run in block.values()} == {1, 2, 3}
    assert {
        arm: {run["order_position"] for run in siblings if run["arm"] == arm}
        for arm in ("N", "S", "T")
    } == {arm: {1, 2, 3} for arm in ("N", "S", "T")}
    _reseal_schedule(schedule, runs=True)

    with pytest.raises(AnalysisError, match="differs from deterministic planner output"):
        analyze(schedule, _evaluations(schedule), development_resamples=10)


def test_rehashed_planner_limit_change_is_rejected() -> None:
    schedule = _schedule()
    schedule["per_run_limits"]["measured_tokens"] += 1
    _reseal_schedule(schedule, runs=False)

    with pytest.raises(AnalysisError, match="differs from deterministic planner output"):
        analyze(schedule, _evaluations(schedule), development_resamples=10)


def test_cli_outputs_json_and_does_not_write_files(tmp_path: Path) -> None:
    schedule = _schedule()
    evaluations = _evaluations(schedule)
    evaluations["runs"][0] = {"run_id": evaluations["runs"][0]["run_id"], "status": "missing"}
    schedule_file = tmp_path / "schedule.json"
    scores_file = tmp_path / "evaluations.json"
    schedule_file.write_text(json.dumps(schedule), encoding="utf-8")
    scores_file.write_text(json.dumps(evaluations), encoding="utf-8")
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    completed = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(schedule_file), str(scores_file)],
        cwd=tmp_path, text=True, capture_output=True, check=False,
    )

    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert after == before
    output = json.loads(completed.stdout)
    assert output["classification"] == "development_analysis_unsealed"
    assert output["primary_effects"] is None
    assert output["counts"]["incomplete_triplets"] == 1


def test_cli_rejects_duplicate_json_keys_as_json_without_writes(tmp_path: Path) -> None:
    schedule = _schedule()
    schedule_file = tmp_path / "schedule.json"
    scores_file = tmp_path / "evaluations.json"
    schedule_file.write_text(json.dumps(schedule), encoding="utf-8")
    scores_file.write_text('{"schema":1,"schema":1}', encoding="utf-8")
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}

    completed = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(schedule_file), str(scores_file)],
        cwd=tmp_path, text=True, capture_output=True, check=False,
    )

    assert completed.returncode == 2
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before
    output = json.loads(completed.stdout)
    assert output["classification"] == "development_analysis_unsealed"
    assert "duplicate JSON object key" in output["error"]
