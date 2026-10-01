"""Round 1 DEV bindings remain complete, deterministic and separate from reserve."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plan_development_round.py"
SPEC = importlib.util.spec_from_file_location("plan_development_round", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def json_sha(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def manifest() -> dict[str, Any]:
    return {
        "schema": "specorganon.development_round_manifest.v1",
        "round": 1, "seed": 73, "protocol_sha256": sha("public test protocol"),
        "cases": [
            {"case_id": case, "package_sha256": sha(f"public {case} package")}
            for case in ("D-F", "D-E")
        ],
        "inputs": {
            **{key: {"sha256": sha(key)} for key in ("task_contract", "common_prompt", "tool_policy")},
            "arm_prompts": {arm: {"sha256": sha(f"prompt {arm}")} for arm in ("A", "B", "C")},
        },
        "alternatives": [
            {"alternative": arm, "mode": mode, "core_sha256": sha("same public core")}
            for arm, mode in (("A", "sequential"), ("B", "graph"), ("C", "risk"))
        ],
        "model": {
            "model_id": "synthetic/not-a-provider", "version": "fixture-v1",
            "family": "fixture-family", "tier": "fixture-tier", "effort": "medium",
            "effort_provider_value": "fixture-medium", "price_profile_sha256": sha("declared fixture price"),
        },
        "per_run_limits": {"measured_tokens": 80_000, "active_seconds": 5_400, "tool_calls": 16},
        "max_model_requests": 32, "cost_limit_micro_usd": 0,
    }


def assign(value: dict[str, Any], path: tuple[Any, ...], replacement: Any) -> None:
    for part in path[:-1]:
        value = value[part]
    value[path[-1]] = replacement


def test_exact_twelve_cells_and_independent_canonical_identities() -> None:
    source = manifest()
    before = copy.deepcopy(source)
    schedule = planner.compile_schedule(source)
    assert source == before
    assert schedule["schema"] == "specorganon.development_round_schedule.v1"
    assert schedule["classification"] == "development_round_preparation_unsealed"
    assert schedule["run_count"] == len(schedule["runs"]) == 12
    assert schedule["block_count"] == 4
    assert schedule["models"] == [source["model"]]
    assert schedule["manifest"] == source
    assert schedule["input_sha256"] == json_sha(source)
    assert schedule["schedule_sha256"] == json_sha({
        key: value for key, value in schedule.items() if key != "schedule_sha256"
    })
    assert {
        (run["arm"], run["case_id"], run["replica"])
        for run in schedule["runs"]
    } == set(itertools.product(("A", "B", "C"), ("D-F", "D-E"), (1, 2)))
    run_keys = {
        "stratum_id", "block_id", "family", "tier", "model_id", "model_version",
        "effort", "effort_provider_value", "agents", "case_id", "replica",
        "order_position", "release_block_order", "arm", "input_sha256",
        "case_package_sha256", "case_reference_sha256", "round", "run_id", "run_sha256",
    }
    packages = {case["case_id"]: case["package_sha256"] for case in source["cases"]}
    for run in schedule["runs"]:
        assert set(run) == run_keys
        assert run["agents"] == "solo" and run["round"] == 1
        assert run["model_version"] == source["model"]["version"]
        assert run["case_reference_sha256"] is None
        assert run["case_package_sha256"] == packages[run["case_id"]]
        body = {key: value for key, value in run.items() if key not in ("run_id", "run_sha256")}
        assert run["run_sha256"] == json_sha(body)
        assert run["run_id"] == "dev-" + run["run_sha256"][:24]
    assert len({run["run_id"] for run in schedule["runs"]}) == 12
    assert planner.validate_schedule(json.loads(json.dumps(schedule))) == schedule


def test_seeded_complete_blocks_and_normalized_input_order_are_reproducible() -> None:
    source = manifest()
    schedule = planner.compile_schedule(source)
    assert planner.compile_schedule(source) == schedule
    reordered = copy.deepcopy(source)
    reordered["cases"].reverse()
    reordered["alternatives"].reverse()
    assert planner.compile_schedule(reordered) == schedule
    for release, offset in enumerate(range(0, 12, 3), start=1):
        block = schedule["runs"][offset:offset + 3]
        assert len({run["block_id"] for run in block}) == 1
        assert len({(run["case_id"], run["replica"]) for run in block}) == 1
        assert {run["arm"] for run in block} == {"A", "B", "C"}
        assert [run["order_position"] for run in block] == [1, 2, 3]
        assert [run["release_block_order"] for run in block] == [release] * 3
    for case in ("D-F", "D-E"):
        orders = [[run["arm"] for run in schedule["runs"] if run["case_id"] == case and run["replica"] == rep]
                  for rep in (1, 2)]
        assert orders[1] == orders[0][1:] + orders[0][:1]
    # Different seeds must affect order, without requiring each possible seed
    # to yield a different finite permutation of four three-arm blocks.
    signatures = set()
    for seed in range(8):
        source["seed"] = seed
        rows = planner.compile_schedule(source)["runs"]
        signatures.add(tuple((run["case_id"], run["replica"], run["arm"]) for run in rows))
    assert len(signatures) > 1


@pytest.mark.parametrize("path,replacement", [
    (("seed",), 74), (("protocol_sha256",), sha("another protocol")),
    (("cases", 0, "package_sha256"), sha("another package")),
    (("inputs", "task_contract", "sha256"), sha("another contract")),
    (("inputs", "common_prompt", "sha256"), sha("another common prompt")),
    (("inputs", "tool_policy", "sha256"), sha("another policy")),
    (("inputs", "arm_prompts", "B", "sha256"), sha("another B prompt")),
    (("model", "model_id"), "another-fixture"), (("model", "version"), "fixture-v2"),
    (("model", "family"), "another-family"), (("model", "tier"), "another-tier"),
    (("model", "effort"), "another-effort"), (("model", "effort_provider_value"), None),
    (("model", "price_profile_sha256"), sha("another declared price")),
    (("per_run_limits", "measured_tokens"), 79_999),
    (("per_run_limits", "active_seconds"), 5_399), (("per_run_limits", "tool_calls"), 15),
    (("max_model_requests",), 31), (("cost_limit_micro_usd",), 1),
])
def test_every_declared_source_model_and_budget_rebinds_all_run_identities(path: tuple, replacement: Any) -> None:
    source = manifest()
    original = planner.compile_schedule(source)
    assign(source, path, replacement)
    changed = planner.compile_schedule(source)
    assert changed["input_sha256"] != original["input_sha256"]
    assert changed["schedule_sha256"] != original["schedule_sha256"]
    assert {run["run_id"] for run in changed["runs"]}.isdisjoint(
        {run["run_id"] for run in original["runs"]}
    )


def test_shared_core_change_rebinds_all_runs_and_utf8_is_preserved() -> None:
    source = manifest()
    before = planner.compile_schedule(source)
    for alternative in source["alternatives"]:
        alternative["core_sha256"] = sha("another shared core")
    source["model"]["family"] = "familia-ñ"
    after = planner.compile_schedule(source)
    assert after["input_sha256"] != before["input_sha256"]
    assert b"familia-\xc3\xb1" in planner.canonical_bytes(after)
    assert b"\\u00f1" not in planner.canonical_bytes(after)


@pytest.mark.parametrize("path,replacement", [
    (("schema",), 1), (("round",), 2), (("round",), True), (("round",), 1.0),
    (("seed",), True), (("seed",), -1), (("seed",), 2**64),
    (("per_run_limits", "measured_tokens"), True), (("per_run_limits", "measured_tokens"), 80_001),
    (("per_run_limits", "active_seconds"), 5_401), (("per_run_limits", "active_seconds"), 0),
    (("per_run_limits", "tool_calls"), 17), (("per_run_limits", "tool_calls"), 0),
    (("max_model_requests",), 1), (("max_model_requests",), 33), (("max_model_requests",), 2.0),
    (("cost_limit_micro_usd",), -1), (("cost_limit_micro_usd",), False),
    (("cases", 0, "case_id"), "R-F"), (("cases", 1, "case_id"), "D-F"),
    (("cases", 0, "reference_sha256"), sha("hidden reference")),
    (("cases",), tuple(manifest()["cases"])),
    (("inputs", "rubric"), {"sha256": sha("hidden rubric")}),
    (("inputs", "task_contract", "ref"), "old schema reference"),
    (("inputs", "arm_prompts", "N"), {"sha256": sha("reserved arm")}),
    (("alternatives", 0, "alternative"), "N"), (("alternatives", 0, "mode"), "graph"),
    (("alternatives", 1, "core_sha256"), sha("different core")),
    (("alternatives", 1, "alternative"), "A"),
    (("protocol_sha256",), "a" * 63), (("model", "price_profile_sha256"), "A" * 64),
    (("model", "model_id"), ""), (("model", "version"), " version"),
    (("model", "family"), "x\x85y"), (("model", "tier"), "x\u200by"),
    (("model", "effort"), "\ud800"), (("model", "effort_provider_value"), False),
    (("model", "model_id"), "ñ" * 257),
    (("per_run_limits", "active_seconds"), float("nan")),
    (("per_run_limits", "measured_tokens"), float("inf")),
])
def test_invalid_manifest_is_rejected(path: tuple, replacement: Any) -> None:
    source = manifest()
    assign(source, path, replacement)
    with pytest.raises(planner.DevelopmentPlanError):
        planner.compile_schedule(source)


@pytest.mark.parametrize("mutation", ["unknown", "digest", "run_id", "round_bool", "float", "tuple", "order", "omit", "coordinate", "reference", "inline"])
def test_rehashing_a_modified_schedule_does_not_replace_exact_recompilation(mutation: str) -> None:
    schedule = planner.compile_schedule(manifest())
    if mutation == "unknown":
        schedule["unexpected"] = "extra"
    elif mutation == "digest":
        schedule["runs"][0]["run_sha256"] = "0" * 64
    elif mutation == "run_id":
        schedule["runs"][0]["run_id"] = "dev-" + "0" * 24
    elif mutation == "round_bool":
        schedule["runs"][0]["round"] = True
    elif mutation == "float":
        schedule["run_count"] = 12.0
    elif mutation == "tuple":
        schedule["runs"] = tuple(schedule["runs"])
    elif mutation == "order":
        schedule["runs"].reverse()
    elif mutation == "omit":
        schedule["runs"].pop()
        schedule["run_count"] = 11
    elif mutation == "coordinate":
        schedule["runs"][0]["arm"] = "N"
    elif mutation == "reference":
        schedule["runs"][0]["case_reference_sha256"] = sha("hidden reference")
    elif mutation == "inline":
        schedule["manifest"]["model"]["price_profile_sha256"] = sha("new price")
    schedule["schedule_sha256"] = json_sha({key: value for key, value in schedule.items() if key != "schedule_sha256"})
    with pytest.raises(planner.DevelopmentPlanError):
        planner.validate_schedule(schedule)


def assets(schedule: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": 1, "schedule_sha256": schedule["schedule_sha256"], "input_sha256": schedule["input_sha256"],
        "cases": {case: f"/not-present/{case}.zip" for case in ("D-F", "D-E")},
        "inputs": {
            **{key: f"/not-present/{key}.json" for key in ("task_contract", "common_prompt", "tool_policy")},
            "arm_prompts": {arm: f"/not-present/{arm}.md" for arm in ("A", "B", "C")},
        },
    }


def test_asset_binding_exposes_only_eight_public_paths_without_filesystem_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    schedule = planner.compile_schedule(manifest())
    def fail(*args: Any, **kwargs: Any) -> None:
        pytest.fail("asset_paths must not read or inspect filesystem assets")
    for operation in ("stat", "lstat", "open", "read_bytes", "read_text", "resolve", "exists"):
        monkeypatch.setattr(Path, operation, fail)
    paths, digests = planner.asset_paths(schedule, assets(schedule))
    expected = {
        **{f"case:{case['case_id']}:package": case["package_sha256"] for case in schedule["cases"]},
        **{f"input:{key}": schedule["inputs"][key]["sha256"] for key in ("task_contract", "common_prompt", "tool_policy")},
        **{f"prompt:{arm}": schedule["inputs"]["arm_prompts"][arm]["sha256"] for arm in ("A", "B", "C")},
    }
    assert digests == expected and set(paths) == set(expected) and len(paths) == 8
    assert all(isinstance(path, Path) and path.is_absolute() for path in paths.values())


@pytest.mark.parametrize("path,replacement", [
    (("schema",), True), (("schedule_sha256",), sha("other schedule")),
    (("input_sha256",), sha("other inputs")), (("cases", "D-F"), "relative.zip"),
    (("cases", "D-E"), {"package": "/public.zip", "reference": "/hidden.zip"}),
    (("cases", "R-F"), "/reserved.zip"), (("inputs", "rubric"), "/hidden.json"),
    (("inputs", "arm_prompts", "A"), Path("/path-object.md")),
    (("inputs", "tool_policy"), "/path\x00.json"),
])
def test_asset_bindings_reject_changed_identity_hidden_material_and_malformed_paths(path: tuple, replacement: Any) -> None:
    schedule = planner.compile_schedule(manifest())
    raw = assets(schedule)
    assign(raw, path, replacement)
    with pytest.raises(planner.DevelopmentPlanError):
        planner.asset_paths(schedule, raw)


def test_cli_is_read_only_and_rejects_duplicate_keys_and_non_json_numbers(tmp_path: Path) -> None:
    source = tmp_path / "manifest.json"
    source.write_text(json.dumps(manifest(), ensure_ascii=False), encoding="utf-8")
    before = source.read_bytes()
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(source)], cwd=tmp_path,
        capture_output=True, check=False,
    )
    assert result.returncode == 0 and result.stderr == b""
    assert json.loads(result.stdout) == planner.compile_schedule(manifest())
    assert source.read_bytes() == before and list(tmp_path.iterdir()) == [source]
    for invalid in ('{"schema":1,"schema":2}', '{"cost_limit_micro_usd":NaN}'):
        rejected = subprocess.run(
            [sys.executable, "-B", str(SCRIPT)], input=invalid.encode(), cwd=tmp_path,
            capture_output=True, check=False,
        )
        assert rejected.returncode == 2 and rejected.stdout == b""
        assert b"Invalid development manifest" in rejected.stderr
    assert source.read_bytes() == before and list(tmp_path.iterdir()) == [source]
