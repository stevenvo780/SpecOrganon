"""Read-only development analysis of a candidate N/S/T schedule.

Usage: ``python scripts/analyze_confirmatory.py schedule.json evaluations.json``.
Either input may be ``-`` for stdin, but not both. Successful and invalid-input
responses are JSON on stdout; the command never writes files or calls providers.

Evaluation schema 1 supplies one record for *every* scheduled run::

    {"schema": 1, "schedule_sha256": "<schedule digest>", "runs": [
      {"run_id": "conf-...", "q": 72},
      {"run_id": "conf-...", "status": "missing", "reason": "no rating"},
      {"run_id": "conf-...", "status": "truncated", "q": 43}
    ]}

``status: scored`` is an optional explicit form for a usable Q. A truncated
run can carry a Q from available artifacts and remains usable, or omit Q and
make its triplet incomplete. Missing runs cannot carry Q. Scores are numeric
values from 0 through 100; no missing value is imputed or replaced.

The output is *always* development_analysis_unsealed. Q alone cannot establish
criterion 4: independent dual ratings, E/T/R/K/P, ablations, and an external
seal are absent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__:
    from .plan_confirmatory import ManifestError, compile_schedule
else:
    from plan_confirmatory import ManifestError, compile_schedule


ARMS = ("N", "S", "T")
CASES = ("R-F", "R-M", "R-S")
AGENTS = ("solo", "trio")
REPLICAS = (1, 2, 3)
DEFAULT_RESAMPLES = 10_000
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
CLASSIFICATION = "development_analysis_unsealed"
RUN_FIELDS = frozenset({
    "run_id", "run_sha256", "input_sha256", "stratum_id", "block_id",
    "family", "tier", "model_id", "model_version", "effort",
    "effort_provider_value", "agents", "case_id", "case_package_sha256",
    "case_reference_sha256", "replica", "order_position", "arm",
    "release_block_order",
})
CRITERION_4_LIMITATION = (
    "Q-only development analysis; independent dual ratings, E/T/R/K/P, "
    "ablations, and an external seal are absent. Criterion 4 is not assessed."
)


class AnalysisError(ValueError):
    """The schedule or evaluation input is incomplete or ambiguous."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise AnalysisError(f"{label} must be an object")
    return value


def _sha256(value: Any, label: str) -> str:
    if type(value) is not str or SHA256.fullmatch(value) is None:
        raise AnalysisError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _nonempty_text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise AnalysisError(f"{label} must be a nonempty trimmed string")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise AnalysisError(f"{label} contains a control character")
    return value


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_schedule(raw: Any) -> tuple[dict[str, Any], dict[tuple[Any, ...], dict[str, dict[str, Any]]], dict[str, int]]:
    schedule = _object(raw, "schedule")
    if type(schedule.get("schema")) is not int or schedule["schema"] != 1:
        raise AnalysisError("schedule.schema must be integer 1")
    if schedule.get("classification") != "candidate_schedule_unsealed":
        raise AnalysisError("schedule must be a candidate_schedule_unsealed plan")
    scheduled_digest = _sha256(schedule.get("schedule_sha256"), "schedule.schedule_sha256")
    try:
        actual_digest = _canonical_digest({k: v for k, v in schedule.items() if k != "schedule_sha256"})
    except (TypeError, ValueError, OverflowError) as exc:
        raise AnalysisError(f"schedule cannot be canonically hashed: {exc}") from exc
    if scheduled_digest != actual_digest:
        raise AnalysisError("schedule digest mismatch")

    if type(schedule.get("seed")) is not int or not 0 <= schedule["seed"] < 2**64:
        raise AnalysisError("schedule.seed must be an unsigned 64-bit integer")
    input_sha256 = _sha256(schedule.get("input_sha256"), "schedule.input_sha256")
    _sha256(schedule.get("protocol_sha256"), "schedule.protocol_sha256")
    limits = _object(schedule.get("per_run_limits"), "schedule.per_run_limits")
    tool_calls = limits.get("tool_calls")
    if type(tool_calls) is not int or not 1 <= tool_calls <= 1_000_000:
        raise AnalysisError("schedule.per_run_limits.tool_calls must be a positive integer")
    inputs = _object(schedule.get("inputs"), "schedule.inputs")
    if schedule.get("arms") != list(ARMS) or schedule.get("agent_configurations") != list(AGENTS):
        raise AnalysisError("schedule arms or agent configurations differ from the planner")
    if type(schedule.get("replicas_per_stratum")) is not int or schedule["replicas_per_stratum"] != 3:
        raise AnalysisError("schedule must contain three replicas per stratum")

    models = schedule.get("models")
    if type(models) is not list or len(models) != 4:
        raise AnalysisError("schedule must contain exactly four models")
    model_by_id: dict[str, dict[str, Any]] = {}
    efforts_by_model: dict[str, dict[str, str | None]] = {}
    for index, value in enumerate(models):
        model = _object(value, f"schedule.models[{index}]")
        model_id = _nonempty_text(model.get("model_id"), f"schedule.models[{index}].model_id")
        if model_id in model_by_id:
            raise AnalysisError(f"duplicate schedule model_id: {model_id}")
        _nonempty_text(model.get("family"), f"schedule.models[{index}].family")
        _nonempty_text(model.get("tier"), f"schedule.models[{index}].tier")
        _nonempty_text(model.get("version"), f"schedule.models[{index}].version")
        effort_rows = model.get("efforts")
        if type(effort_rows) is not list or len(effort_rows) not in (1, 2):
            raise AnalysisError(f"schedule.models[{index}].efforts must have one or two levels")
        efforts: dict[str, str | None] = {}
        for effort_index, value in enumerate(effort_rows):
            effort = _object(value, f"schedule.models[{index}].efforts[{effort_index}]")
            label = effort.get("label")
            if type(label) is not str or label not in ("default", "low", "high") or label in efforts:
                raise AnalysisError(f"schedule.models[{index}] has invalid effort labels")
            provider_value = effort.get("provider_value")
            if label == "default":
                if provider_value is not None:
                    raise AnalysisError(f"schedule.models[{index}] default effort must lack provider value")
            else:
                _nonempty_text(provider_value, f"schedule.models[{index}].efforts[{effort_index}].provider_value")
            efforts[label] = provider_value
        if set(efforts) not in ({"default"}, {"low", "high"}):
            raise AnalysisError(f"schedule model {model_id} must use default or low/high efforts")
        model_by_id[model_id] = model
        efforts_by_model[model_id] = efforts

    cases = schedule.get("cases")
    if type(cases) is not list or len(cases) != len(CASES):
        raise AnalysisError("schedule must contain exactly three cases")
    case_by_id: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(cases):
        case = _object(value, f"schedule.cases[{index}]")
        case_id = case.get("case_id")
        if type(case_id) is not str or case_id not in CASES or case_id in case_by_id:
            raise AnalysisError(f"schedule.cases[{index}] has an invalid or duplicate case_id")
        _sha256(case.get("package_sha256"), f"schedule.cases[{index}].package_sha256")
        _sha256(case.get("reference_sha256"), f"schedule.cases[{index}].reference_sha256")
        case_by_id[case_id] = case
    if set(case_by_id) != set(CASES):
        raise AnalysisError("schedule cases must be R-F, R-M, R-S")

    manifest = {
        "schema": 1,
        "seed": schedule["seed"],
        "protocol_sha256": schedule["protocol_sha256"],
        "tool_call_cap": tool_calls,
        "models": models,
        "cases": cases,
        "inputs": inputs,
    }
    if _canonical_digest(manifest) != input_sha256:
        raise AnalysisError("schedule input digest mismatch")

    runs = schedule.get("runs")
    if type(runs) is not list:
        raise AnalysisError("schedule.runs must be an array")

    triplets: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    seen_ids: set[str] = set()
    for index, value in enumerate(runs):
        run = _object(value, f"schedule.runs[{index}]")
        if set(run) != RUN_FIELDS:
            raise AnalysisError(
                f"schedule.runs[{index}] has missing identity fields {sorted(RUN_FIELDS - run.keys())} "
                f"or unexpected fields {sorted(run.keys() - RUN_FIELDS)}"
            )
        run_id = _nonempty_text(run.get("run_id"), f"schedule.runs[{index}].run_id")
        if run_id in seen_ids:
            raise AnalysisError(f"duplicate scheduled run_id: {run_id}")
        seen_ids.add(run_id)
        run_sha256 = _sha256(run["run_sha256"], f"schedule.runs[{index}].run_sha256")
        run_body = {key: value for key, value in run.items() if key not in ("run_id", "run_sha256")}
        if _canonical_digest(run_body) != run_sha256:
            raise AnalysisError(f"schedule.runs[{index}] run_sha256 mismatch")
        if run_id != "conf-" + run_sha256[:24]:
            raise AnalysisError(f"schedule.runs[{index}] run_id does not match run_sha256")
        model_id = _nonempty_text(run.get("model_id"), f"schedule.runs[{index}].model_id")
        effort = run.get("effort")
        agents = run.get("agents")
        case_id = run.get("case_id")
        replica = run.get("replica")
        arm = run.get("arm")
        order = run.get("order_position")
        if (
            model_id not in model_by_id
            or type(effort) is not str or effort not in efforts_by_model[model_id]
            or type(agents) is not str or agents not in AGENTS
            or type(case_id) is not str or case_id not in CASES
            or type(replica) is not int or replica not in REPLICAS
            or type(arm) is not str or arm not in ARMS
            or type(order) is not int or order not in REPLICAS
        ):
            raise AnalysisError(f"schedule.runs[{index}] has an invalid panel coordinate")
        model = model_by_id[model_id]
        case = case_by_id[case_id]
        if (
            run["input_sha256"] != input_sha256
            or run["family"] != model["family"]
            or run["tier"] != model["tier"]
            or run["model_version"] != model["version"]
            or run["effort_provider_value"] != efforts_by_model[model_id][effort]
            or run["case_package_sha256"] != case["package_sha256"]
            or run["case_reference_sha256"] != case["reference_sha256"]
        ):
            raise AnalysisError(f"schedule.runs[{index}] work identity differs from model, effort, or case metadata")
        stratum = {"model_id": model_id, "effort": effort, "agents": agents, "case_id": case_id}
        expected_stratum_id = "stratum-" + _canonical_digest({"input_sha256": input_sha256, **stratum})[:24]
        expected_block_id = "block-" + _canonical_digest({"stratum_id": expected_stratum_id, "replica": replica})[:24]
        if run["stratum_id"] != expected_stratum_id or run["block_id"] != expected_block_id:
            raise AnalysisError(f"schedule.runs[{index}] stratum_id or block_id mismatch")
        release_order = run["release_block_order"]
        if type(release_order) is not int or release_order < 1:
            raise AnalysisError(f"schedule.runs[{index}].release_block_order must be positive")
        key = (model_id, effort, agents, case_id, replica)
        if arm in triplets[key]:
            raise AnalysisError(f"duplicate scheduled coordinate: {key}, {arm}")
        triplets[key][arm] = run

    expected_count = sum(len(efforts) for efforts in efforts_by_model.values()) * len(AGENTS) * len(CASES) * len(REPLICAS) * len(ARMS)
    if len(runs) != expected_count:
        raise AnalysisError(f"schedule.runs must contain exactly {expected_count} entries")
    if type(schedule.get("run_count")) is not int or schedule["run_count"] != expected_count:
        raise AnalysisError("schedule.run_count does not match the full panel")
    expected_keys = {
        (model_id, effort, agents, case_id, replica)
        for model_id, efforts in efforts_by_model.items()
        for effort in efforts
        for agents in AGENTS
        for case_id in CASES
        for replica in REPLICAS
    }
    if set(triplets) != expected_keys:
        raise AnalysisError("schedule omits or adds triplet coordinates")
    seen_blocks: set[str] = set()
    arm_positions: dict[tuple[str, str, str, str], dict[str, set[int]]] = defaultdict(
        lambda: {arm: set() for arm in ARMS}
    )
    release_by_block: dict[str, int] = {}
    for key, arms in triplets.items():
        if set(arms) != set(ARMS):
            raise AnalysisError(f"schedule triplet lacks N/S/T: {key}")
        blocks = {run["block_id"] for run in arms.values()}
        orders = {run["order_position"] for run in arms.values()}
        if len(blocks) != 1 or orders != set(REPLICAS):
            raise AnalysisError(f"schedule triplet has inconsistent block or order: {key}")
        block = next(iter(blocks))
        if block in seen_blocks:
            raise AnalysisError(f"schedule reuses block_id: {block}")
        seen_blocks.add(block)
        releases = {run["release_block_order"] for run in arms.values()}
        if len(releases) != 1:
            raise AnalysisError(f"schedule triplet has inconsistent release order: {key}")
        release_by_block[block] = next(iter(releases))
        stratum_key = key[:4]
        for arm, run in arms.items():
            arm_positions[stratum_key][arm].add(run["order_position"])
    for key, by_arm in arm_positions.items():
        if any(positions != set(REPLICAS) for positions in by_arm.values()):
            raise AnalysisError(f"schedule arm positions are not counterbalanced in stratum: {key}")
    ordered_blocks = sorted(seen_blocks, key=lambda block: _canonical_digest({"seed": schedule["seed"], "block_id": block}))
    if any(release_by_block[block] != position for position, block in enumerate(ordered_blocks, start=1)):
        raise AnalysisError("schedule release_block_order differs from planner order")
    if type(schedule.get("block_count")) is not int or schedule["block_count"] != len(triplets):
        raise AnalysisError("schedule.block_count does not match the full panel")
    # Exact reproduction checks the seed-derived arm order and all planner
    # metadata beyond the detailed invariants above.
    try:
        reproduced = compile_schedule(manifest)
    except ManifestError as exc:
        raise AnalysisError(f"schedule manifest cannot be reproduced: {exc}") from exc
    if reproduced != schedule or reproduced["schedule_sha256"] != scheduled_digest:
        raise AnalysisError("schedule differs from deterministic planner output")
    return schedule, triplets, {model_id: len(efforts) for model_id, efforts in efforts_by_model.items()}


def _validate_evaluations(raw: Any, scheduled_digest: str, scheduled_ids: set[str]) -> dict[str, dict[str, Any]]:
    evaluations = _object(raw, "evaluations")
    if set(evaluations) != {"schema", "schedule_sha256", "runs"}:
        raise AnalysisError("evaluations must contain exactly schema, schedule_sha256, and runs")
    if type(evaluations["schema"]) is not int or evaluations["schema"] != 1:
        raise AnalysisError("evaluations.schema must be integer 1")
    if _sha256(evaluations["schedule_sha256"], "evaluations.schedule_sha256") != scheduled_digest:
        raise AnalysisError("evaluation schedule digest mismatch")
    rows = evaluations["runs"]
    if type(rows) is not list:
        raise AnalysisError("evaluations.runs must be an array")
    by_run: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(rows):
        row = _object(value, f"evaluations.runs[{index}]")
        if not {"run_id"} <= set(row) or set(row) - {"run_id", "status", "q", "reason"}:
            raise AnalysisError(f"evaluations.runs[{index}] has missing or unexpected keys")
        run_id = _nonempty_text(row["run_id"], f"evaluations.runs[{index}].run_id")
        if run_id in by_run:
            raise AnalysisError(f"duplicate evaluated run_id: {run_id}")
        if run_id not in scheduled_ids:
            raise AnalysisError(f"unscheduled evaluated run_id: {run_id}")
        status = row.get("status", "scored")
        if type(status) is not str or status not in ("scored", "missing", "truncated"):
            raise AnalysisError(f"evaluations.runs[{index}].status must be scored, missing, or truncated")
        if status == "scored" and "q" not in row:
            raise AnalysisError(f"scored run {run_id} requires q")
        if status == "missing" and "q" in row:
            raise AnalysisError(f"missing run {run_id} cannot carry q")
        if "q" in row:
            q = row["q"]
            if type(q) not in (int, float) or not 0 <= q <= 100 or (type(q) is float and not math.isfinite(q)):
                raise AnalysisError(f"run {run_id} q must be a finite number from 0 through 100")
        if "reason" in row:
            if status == "scored":
                raise AnalysisError(f"scored run {run_id} cannot carry a missing/truncated reason")
            _nonempty_text(row["reason"], f"run {run_id} reason")
        by_run[run_id] = {"run_id": run_id, "status": status}
        if "q" in row:
            by_run[run_id]["q"] = row["q"]
        if "reason" in row:
            by_run[run_id]["reason"] = row["reason"]
    omitted = scheduled_ids - by_run.keys()
    if omitted:
        raise AnalysisError(f"evaluations omit {len(omitted)} scheduled run_id values; first: {sorted(omitted)[0]}")
    return by_run


def _percentile(sorted_values: list[float], proportion: float) -> float:
    position = (len(sorted_values) - 1) * proportion
    low = math.floor(position)
    high = math.ceil(position)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def _primary_effects(
    complete: dict[tuple[Any, ...], tuple[float, float]],
    effort_counts: dict[str, int],
    resamples: int,
    seed: int,
) -> dict[str, Any]:
    strata: dict[tuple[str, str, str, str], list[tuple[float, float]]] = defaultdict(list)
    for (model, effort, agents, case_id, replica), pair in sorted(complete.items()):
        strata[(model, effort, agents, case_id)].append(pair)
    weighted: list[tuple[str, float, list[tuple[float, float]]]] = []
    for (model, _effort, _agents, _case_id), pairs in sorted(strata.items()):
        if len(pairs) != 3:
            raise AnalysisError("primary effects require all three complete paired replicas per stratum")
        weight = 1 / (4 * effort_counts[model] * len(AGENTS) * len(CASES))
        weighted.append((model, weight, pairs))
    if not math.isclose(math.fsum(item[1] for item in weighted), 1.0, abs_tol=1e-12):
        raise AnalysisError("primary weights do not sum to one")

    observed = [
        math.fsum(weight * math.fsum(pair[k] for pair in pairs) / 3 for _model, weight, pairs in weighted)
        for k in (0, 1)
    ]
    by_model = {
        model: [
            math.fsum(4 * weight * math.fsum(pair[k] for pair in pairs) / 3
                      for row_model, weight, pairs in weighted if row_model == model)
            for k in (0, 1)
        ]
        for model in sorted(effort_counts)
    }
    rng = random.Random(seed)
    bootstrap: tuple[list[float], list[float]] = ([], [])
    for _ in range(resamples):
        contributions: tuple[list[float], list[float]] = ([], [])
        for _model, weight, pairs in weighted:
            drawn = [pairs[rng.randrange(3)] for _ in REPLICAS]
            contributions[0].append(weight * math.fsum(pair[0] for pair in drawn) / 3)
            contributions[1].append(weight * math.fsum(pair[1] for pair in drawn) / 3)
        bootstrap[0].append(math.fsum(contributions[0]))
        bootstrap[1].append(math.fsum(contributions[1]))
    for values in bootstrap:
        values.sort()
    return {
        label: {
            "mean": observed[k],
            "ci95_percentile": [_percentile(bootstrap[k], 0.025), _percentile(bootstrap[k], 0.975)],
            "by_model": {model: values[k] for model, values in by_model.items()},
        }
        for k, label in enumerate(("T_minus_S", "T_minus_N"))
    }


def analyze(
    raw_schedule: Any,
    raw_evaluations: Any,
    *,
    development_resamples: int | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Validate all scheduled records and compute paired Q summaries only."""
    schedule, triplets, effort_counts = _validate_schedule(raw_schedule)
    scheduled_ids = {run["run_id"] for runs in triplets.values() for run in runs.values()}
    scores = _validate_evaluations(raw_evaluations, schedule["schedule_sha256"], scheduled_ids)
    if development_resamples is None:
        resamples = DEFAULT_RESAMPLES
    elif type(development_resamples) is int and 1 <= development_resamples <= DEFAULT_RESAMPLES:
        resamples = development_resamples
    else:
        raise AnalysisError("development_resamples must be an integer from 1 through 10000")
    if seed is None:
        bootstrap_seed = schedule["seed"]
    elif type(seed) is int and 0 <= seed < 2**64:
        bootstrap_seed = seed
    else:
        raise AnalysisError("seed must be an unsigned 64-bit integer")

    records = []
    incomplete = []
    paired: dict[tuple[Any, ...], tuple[float, float]] = {}
    available: dict[str, list[float]] = {"T_minus_S": [], "T_minus_N": []}
    for key, runs in sorted(triplets.items()):
        arm_scores = {arm: scores[runs[arm]["run_id"]] for arm in ARMS}
        q = {arm: arm_scores[arm].get("q") for arm in ARMS}
        differences = {
            "T_minus_S": q["T"] - q["S"] if q["T"] is not None and q["S"] is not None else None,
            "T_minus_N": q["T"] - q["N"] if q["T"] is not None and q["N"] is not None else None,
        }
        for label, value in differences.items():
            if value is not None:
                available[label].append(value)
        is_complete = all(value is not None for value in q.values())
        if is_complete:
            paired[key] = (differences["T_minus_S"], differences["T_minus_N"])
        record = {
            "model_id": key[0], "effort": key[1], "agents": key[2],
            "case_id": key[3], "replica": key[4],
            "block_id": runs["N"]["block_id"],
            "complete": is_complete,
            "arms": arm_scores,
            **differences,
        }
        records.append(record)
        if not is_complete:
            incomplete.append(record)

    matrix_complete = not incomplete
    counts = {
        "scheduled_runs": len(scheduled_ids),
        "scored_runs": sum("q" in item for item in scores.values()),
        "missing_runs": sum(item["status"] == "missing" for item in scores.values()),
        "truncated_runs": sum(item["status"] == "truncated" for item in scores.values()),
        "truncated_scored_runs": sum(item["status"] == "truncated" and "q" in item for item in scores.values()),
        "scheduled_triplets": len(triplets),
        "complete_triplets": len(paired),
        "incomplete_triplets": len(incomplete),
    }
    descriptive = {
        label: {
            "count": len(values),
            "mean": math.fsum(values) / len(values) if values else None,
            "minimum": min(values) if values else None,
            "maximum": max(values) if values else None,
        }
        for label, values in available.items()
    }
    return {
        "schema": 1,
        "classification": CLASSIFICATION,
        "schedule_sha256": schedule["schedule_sha256"],
        "matrix_complete": matrix_complete,
        "counts": counts,
        "bootstrap": {"seed": bootstrap_seed, "resamples": resamples if matrix_complete else 0,
                      "default_resamples": DEFAULT_RESAMPLES},
        "primary_effects": _primary_effects(paired, effort_counts, resamples, bootstrap_seed)
        if matrix_complete else None,
        "descriptive_available_pairs": descriptive,
        "triplets": records,
        "incomplete_triplets": incomplete,
        "criterion_4": {
            "status": "not_assessed",
            "reason": CRITERION_4_LIMITATION + (
                " The scheduled N/S/T matrix is also incomplete." if not matrix_complete else ""
            ),
        },
    }


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise AnalysisError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise AnalysisError(f"non-JSON numeric constant: {value}")


def _read_json(path: str) -> Any:
    source = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(source, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("schedule", help="candidate schedule JSON path, or - for stdin")
    parser.add_argument("evaluations", help="schema-1 evaluations JSON path, or - for stdin")
    parser.add_argument("--seed", type=int, help="bootstrap seed (default: schedule seed)")
    parser.add_argument("--development-resamples", type=int,
                        help="explicit development-only bootstrap count, 1..10000 (default: 10000)")
    args = parser.parse_args(argv)
    try:
        if args.schedule == args.evaluations == "-":
            raise AnalysisError("only one input may use stdin")
        schedule = _read_json(args.schedule)
        evaluations = _read_json(args.evaluations)
        output = analyze(schedule, evaluations,
                         development_resamples=args.development_resamples, seed=args.seed)
    except (AnalysisError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        output = {"schema": 1, "classification": CLASSIFICATION, "error": str(exc)}
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
