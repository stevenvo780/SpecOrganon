"""The prospective schedule is complete, balanced, reproducible, and read-only."""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plan_confirmatory.py"


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def json_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def reference(name: str) -> dict[str, str]:
    return {"ref": f"refs/{name}.json", "sha256": sha256(name)}


def model(family: str, tier: str, configurable: bool = True) -> dict[str, Any]:
    return {
        "family": family,
        "tier": tier,
        "model_id": f"{family}/{tier}-model",
        "version": "2026-09-example",
        "effort_control": configurable,
        "efforts": (
            [{"label": "low", "provider_value": "low-setting"},
             {"label": "high", "provider_value": "high-setting"}]
            if configurable else [{"label": "default"}]
        ),
    }


def manifest() -> dict[str, Any]:
    return {
        "schema": 1,
        "seed": 73,
        "protocol_sha256": sha256("synthetic protocol for schedule tests"),
        "tool_call_cap": 120,
        "models": [
            model("family-a", "lower"),
            model("family-a", "higher"),
            model("family-b", "lower"),
            model("family-b", "higher"),
        ],
        "cases": [
            {
                "case_id": case_id,
                "package_sha256": sha256(f"synthetic {case_id} executor package"),
                "reference_sha256": sha256(f"synthetic {case_id} custodied solution"),
            }
            for case_id in ("R-F", "R-M", "R-S")
        ],
        "inputs": {
            "task_contract": reference("task-contract"),
            "common_prompt": reference("common-prompt"),
            "arm_prompts": {arm: reference(f"{arm}-prompt") for arm in ("N", "S", "T")},
            "rubric": reference("rubric"),
            "tool_policy": reference("tool-policy"),
            "sdd_guide": reference("sdd-guide"),
            "toolkit": reference("toolkit"),
        },
    }


def invoke(raw: dict[str, Any] | str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "manifest.json"
    path.write_text(raw if isinstance(raw, str) else json.dumps(raw), encoding="utf-8")
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    after = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before
    assert not (tmp_path / "experiments" / "registro").exists()
    return result


def compiled(raw: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    result = invoke(raw, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    return json.loads(result.stdout)


def test_full_panel_has_exact_cells_and_bound_hashes(tmp_path: Path) -> None:
    source = manifest()
    plan = compiled(source, tmp_path)

    assert plan["schema"] == 1
    assert plan["classification"] == "candidate_schedule_unsealed"
    assert plan["protocol_sha256"] == source["protocol_sha256"]
    assert plan["arms"] == ["N", "S", "T"]
    assert plan["agent_configurations"] == ["solo", "trio"]
    assert plan["replicas_per_stratum"] == 3
    assert plan["per_run_limits"] == {
        "measured_tokens": 80_000,
        "active_seconds": 5_400,
        "tool_calls": 120,
    }
    assert plan["study_limits"]["max_confirmatory_runs"] == 432
    assert plan["block_count"] == 144
    assert plan["run_count"] == len(plan["runs"]) == 432

    expected = set(itertools.product(
        (item["model_id"] for item in source["models"]),
        ("low", "high"),
        ("solo", "trio"),
        ("R-F", "R-M", "R-S"),
        (1, 2, 3),
        ("N", "S", "T"),
    ))
    actual = {
        (run["model_id"], run["effort"], run["agents"], run["case_id"], run["replica"], run["arm"])
        for run in plan["runs"]
    }
    assert actual == expected
    assert len({run["run_id"] for run in plan["runs"]}) == 432
    assert len({run["block_id"] for run in plan["runs"]}) == 144

    normalized_input = {
        "schema": 1,
        "seed": plan["seed"],
        "protocol_sha256": plan["protocol_sha256"],
        "tool_call_cap": plan["per_run_limits"]["tool_calls"],
        "models": plan["models"],
        "cases": plan["cases"],
        "inputs": plan["inputs"],
    }
    assert plan["input_sha256"] == json_sha256(normalized_input)
    assert plan["schedule_sha256"] == json_sha256({k: v for k, v in plan.items() if k != "schedule_sha256"})
    for run in plan["runs"]:
        body = {key: value for key, value in run.items() if key not in ("run_id", "run_sha256")}
        assert run["run_sha256"] == json_sha256(body)
        assert run["run_id"] == "conf-" + run["run_sha256"][:24]
        assert run["input_sha256"] == plan["input_sha256"]


def test_each_reserved_case_keeps_its_package_and_custodied_reference_mapping(tmp_path: Path) -> None:
    source = manifest()
    source["cases"].reverse()
    plan = compiled(source, tmp_path)
    expected = {
        case["case_id"]: (case["package_sha256"], case["reference_sha256"])
        for case in source["cases"]
    }
    assert [case["case_id"] for case in plan["cases"]] == ["R-F", "R-M", "R-S"]
    assert {
        case["case_id"]: (case["package_sha256"], case["reference_sha256"])
        for case in plan["cases"]
    } == expected
    for run in plan["runs"]:
        assert (run["case_package_sha256"], run["case_reference_sha256"]) == expected[run["case_id"]]


def test_changing_only_custodied_reference_rebinds_plan_and_run_ids(tmp_path: Path) -> None:
    source = manifest()
    first = compiled(source, tmp_path)
    changed_source = copy.deepcopy(source)
    changed_source["cases"][1]["reference_sha256"] = sha256("replacement synthetic R-M solution")
    changed = compiled(changed_source, tmp_path)

    assert changed["cases"][1]["package_sha256"] == first["cases"][1]["package_sha256"]
    assert changed["cases"][1]["reference_sha256"] != first["cases"][1]["reference_sha256"]
    assert changed["input_sha256"] != first["input_sha256"]
    assert changed["schedule_sha256"] != first["schedule_sha256"]
    assert {run["run_id"] for run in changed["runs"]}.isdisjoint(
        {run["run_id"] for run in first["runs"]}
    )
    assert {run["run_sha256"] for run in changed["runs"]}.isdisjoint(
        {run["run_sha256"] for run in first["runs"]}
    )


def test_each_stratum_uses_all_arms_once_in_each_position(tmp_path: Path) -> None:
    plan = compiled(manifest(), tmp_path)
    strata: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for run in plan["runs"]:
        strata[(run["model_id"], run["effort"], run["agents"], run["case_id"])].append(run)

    assert len(strata) == 48
    for rows in strata.values():
        assert len(rows) == 9
        assert len({row["stratum_id"] for row in rows}) == 1
        for replica in (1, 2, 3):
            block = [row for row in rows if row["replica"] == replica]
            assert len(block) == 3
            assert {row["arm"] for row in block} == {"N", "S", "T"}
            assert {row["order_position"] for row in block} == {1, 2, 3}
            assert len({row["block_id"] for row in block}) == 1
        for arm in ("N", "S", "T"):
            assert {row["order_position"] for row in rows if row["arm"] == arm} == {1, 2, 3}
        first = [row["arm"] for row in sorted(
            (row for row in rows if row["replica"] == 1), key=lambda row: row["order_position"]
        )]
        for replica in (2, 3):
            observed = [row["arm"] for row in sorted(
                (row for row in rows if row["replica"] == replica), key=lambda row: row["order_position"]
            )]
            assert observed == first[replica - 1 :] + first[: replica - 1]


def test_complete_blocks_are_released_in_seeded_cross_model_order(tmp_path: Path) -> None:
    plan = compiled(manifest(), tmp_path)
    blocks = [plan["runs"][index : index + 3] for index in range(0, plan["run_count"], 3)]
    assert len(blocks) == plan["block_count"] == 144
    assert len({block[0]["block_id"] for block in blocks}) == 144
    for release_order, block in enumerate(blocks, start=1):
        assert len(block) == 3
        assert {row["block_id"] for row in block} == {block[0]["block_id"]}
        assert [row["release_block_order"] for row in block] == [release_order] * 3
        assert [row["order_position"] for row in block] == [1, 2, 3]

    model_sequence = [block[0]["model_id"] for block in blocks]
    for model_id in set(model_sequence):
        positions = [index for index, value in enumerate(model_sequence) if value == model_id]
        assert positions[-1] - positions[0] + 1 > len(positions)


def test_reordered_manifest_is_identical_and_new_seed_changes_arm_order(tmp_path: Path) -> None:
    source = manifest()
    first = compiled(source, tmp_path)
    assert compiled(source, tmp_path) == first

    reordered = copy.deepcopy(source)
    reordered["models"].reverse()
    reordered["cases"].reverse()
    for item in reordered["models"]:
        item["efforts"].reverse()
    assert compiled(reordered, tmp_path) == first

    changed_seed = copy.deepcopy(source)
    changed_seed["seed"] += 1
    changed = compiled(changed_seed, tmp_path)
    assert changed["input_sha256"] != first["input_sha256"]
    assert changed["schedule_sha256"] != first["schedule_sha256"]
    def ordered_cells(plan: dict[str, Any]) -> list[tuple[Any, ...]]:
        return [
            (
                run["model_id"], run["effort"], run["agents"], run["case_id"],
                run["replica"], run["order_position"], run["arm"],
            )
            for run in plan["runs"]
        ]

    first_orders = ordered_cells(first)
    changed_orders = ordered_cells(changed)
    assert changed_orders != first_orders
    first_blocks = [
        (run["model_id"], run["effort"], run["agents"], run["case_id"], run["replica"])
        for run in first["runs"][::3]
    ]
    changed_blocks = [
        (run["model_id"], run["effort"], run["agents"], run["case_id"], run["replica"])
        for run in changed["runs"][::3]
    ]
    assert changed_blocks != first_blocks


@pytest.mark.parametrize("single_effort_models,expected", [(1, 378), (2, 324)])
def test_single_effort_models_use_default_without_selective_cells(
    single_effort_models: int, expected: int, tmp_path: Path
) -> None:
    source = manifest()
    source["models"][0] = model("family-a", "lower", configurable=False)
    if single_effort_models == 2:
        source["models"][2] = model("family-b", "lower", configurable=False)
    plan = compiled(source, tmp_path)
    assert plan["run_count"] == expected <= 432
    single_ids = {source["models"][0]["model_id"]}
    if single_effort_models == 2:
        single_ids.add(source["models"][2]["model_id"])
    for run in plan["runs"]:
        if run["model_id"] in single_ids:
            assert run["effort"] == "default"
            assert run["effort_provider_value"] is None
    assert all(run["effort"] != "high" for run in plan["runs"] if run["model_id"] in single_ids)


@pytest.mark.parametrize("variant", [
    "wrong_schema", "missing_protocol_hash", "upper_protocol_hash", "boolean_seed", "negative_seed",
    "zero_tool_cap", "extra_resource_override", "three_models", "duplicate_model_id",
    "duplicate_family_tier", "family_without_configurable_effort", "wrong_effort_flag",
    "duplicate_effort_label", "duplicate_effort_provider_value", "uncontrolled_with_provider_value",
    "controlled_with_default", "two_cases", "duplicate_case_id", "duplicate_case_package",
    "missing_case_digest", "missing_case_reference_digest", "bad_case_reference_digest",
    "duplicate_case_reference_digest", "missing_reference_digest", "bad_reference_digest",
    "duplicate_arm_prompt",
])
def test_invalid_manifests_are_rejected_without_writes(variant: str, tmp_path: Path) -> None:
    source = manifest()
    if variant == "wrong_schema":
        source["schema"] = 2
    elif variant == "missing_protocol_hash":
        del source["protocol_sha256"]
    elif variant == "upper_protocol_hash":
        source["protocol_sha256"] = "A" * 64
    elif variant == "boolean_seed":
        source["seed"] = True
    elif variant == "negative_seed":
        source["seed"] = -1
    elif variant == "zero_tool_cap":
        source["tool_call_cap"] = 0
    elif variant == "extra_resource_override":
        source["tokens_per_run"] = 1_000_000
    elif variant == "three_models":
        source["models"].pop()
    elif variant == "duplicate_model_id":
        source["models"][1]["model_id"] = source["models"][0]["model_id"]
    elif variant == "duplicate_family_tier":
        source["models"][1]["tier"] = "lower"
    elif variant == "family_without_configurable_effort":
        source["models"][0] = model("family-a", "lower", configurable=False)
        source["models"][1] = model("family-a", "higher", configurable=False)
    elif variant == "wrong_effort_flag":
        source["models"][0]["effort_control"] = False
    elif variant == "duplicate_effort_label":
        source["models"][0]["efforts"][1]["label"] = "low"
    elif variant == "duplicate_effort_provider_value":
        source["models"][0]["efforts"][1]["provider_value"] = "low-setting"
    elif variant == "uncontrolled_with_provider_value":
        source["models"][0] = model("family-a", "lower", configurable=False)
        source["models"][0]["efforts"][0]["provider_value"] = "invented"
    elif variant == "controlled_with_default":
        source["models"][0]["efforts"][0]["label"] = "default"
    elif variant == "two_cases":
        source["cases"].pop()
    elif variant == "duplicate_case_id":
        source["cases"][1]["case_id"] = "R-F"
    elif variant == "duplicate_case_package":
        source["cases"][1]["package_sha256"] = source["cases"][0]["package_sha256"]
    elif variant == "missing_case_digest":
        del source["cases"][0]["package_sha256"]
    elif variant == "missing_case_reference_digest":
        del source["cases"][0]["reference_sha256"]
    elif variant == "bad_case_reference_digest":
        source["cases"][0]["reference_sha256"] = "A" * 64
    elif variant == "duplicate_case_reference_digest":
        source["cases"][1]["reference_sha256"] = source["cases"][0]["reference_sha256"]
    elif variant == "missing_reference_digest":
        del source["inputs"]["rubric"]["sha256"]
    elif variant == "bad_reference_digest":
        source["inputs"]["rubric"]["sha256"] = "not-a-digest"
    elif variant == "duplicate_arm_prompt":
        source["inputs"]["arm_prompts"]["S"]["sha256"] = source["inputs"]["arm_prompts"]["N"]["sha256"]

    result = invoke(source, tmp_path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("Invalid confirmatory manifest:")


def test_duplicate_json_keys_and_non_json_constants_are_rejected(tmp_path: Path) -> None:
    for raw in ('{"schema":1,"schema":1}', '{"schema":NaN}'):
        result = invoke(raw, tmp_path)
        assert result.returncode == 2
        assert result.stdout == ""
        assert "Invalid confirmatory manifest:" in result.stderr
