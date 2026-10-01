"""Prospective identities, equal coordination and declared metadata binding."""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import plan_coordinated_development as planner  # noqa: E402
import plan_development_round as legacy  # noqa: E402


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def json_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def manifest():
    base = {
        "schema": legacy.MANIFEST_SCHEMA_V2, "round": 1, "seed": 118,
        "protocol_sha256": sha("public protocol"),
        "cases": [{"case_id": case, "package_sha256": sha("public " + case)} for case in ("D-F", "D-E")],
        "inputs": {**{key: {"sha256": sha(key)} for key in legacy.INPUTS},
                   "arm_prompts": {arm: {"sha256": sha("public prompt " + arm)} for arm in legacy.ARMS}},
        "alternatives": [{"alternative": arm, "mode": mode, "core_sha256": sha("original core")}
                         for arm, mode in legacy.MODES.items()],
        "model": {"model_id": "offline-fixture-model", "version": "fixture-v1", "family": "fixture",
                  "tier": "fixture", "effort": "default", "effort_provider_value": None,
                  "price_profile_sha256": sha("declared fixture prices")},
        "per_run_limits": {"measured_tokens": 80000, "active_seconds": 5400, "tool_calls": 64},
        "max_model_requests": 128, "cost_limit_micro_usd": 0,
    }
    return {"schema": planner.MANIFEST_SCHEMA, "base": base, "coordination": copy.deepcopy(planner.COORDINATION),
            "shared_contract": {key: {"sha256": sha(key)} for key in ("delivery", "rubric", "coordination_prompt")},
            "runtime_policy": {"sha256": sha("public runtime policy")},
            "provider_route": {"provider": "fixture", "api": "responses", "version": "fixture-v1", "service_tier": "default"},
            "source_freeze_sha256": sha("prospective source freeze")}


def assign(value, path, replacement):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = replacement


def test_exact_new_twelve_cells_and_independent_hashes():
    raw = manifest()
    before = copy.deepcopy(raw)
    schedule = planner.compile_schedule(raw)
    assert raw == before
    assert schedule["schema"] == planner.SCHEDULE_SCHEMA
    assert schedule["run_count"] == len(schedule["runs"]) == 12
    assert schedule["block_count"] == 4
    assert schedule["input_sha256"] == json_sha(raw)
    assert schedule["coordination_sha256"] == json_sha(raw["coordination"])
    assert schedule["schedule_sha256"] == json_sha({key: value for key, value in schedule.items()
                                                   if key != "schedule_sha256"})
    assert {(run["arm"], run["case_id"], run["replica"]) for run in schedule["runs"]} == set(
        itertools.product(legacy.ARMS, legacy.CASE_IDS, (1, 2)))
    for run in schedule["runs"]:
        body = {key: value for key, value in run.items() if key not in {"run_id", "run_sha256"}}
        assert run["run_sha256"] == json_sha(body)
        assert run["run_id"] == "dev-coord-" + json_sha(body)[:24]
        assert run["agents"] == planner.COORDINATION["profile"] and run["agent_count"] == 4
        assert run["mode"] == legacy.MODES[run["arm"]]
        assert run["case_reference_sha256"] is None
    old = legacy.compile_schedule(raw["base"])
    assert not {run["run_id"] for run in schedule["runs"]} & {run["run_id"] for run in old["runs"]}
    assert all(run["agents"] == "solo" for run in old["runs"])
    assert planner.validate_schedule(json.loads(json.dumps(schedule))) == schedule
    with pytest.raises(planner.DevelopmentPlanError):
        planner.validate_schedule(old)
    with pytest.raises(legacy.DevelopmentPlanError):
        legacy.validate_schedule(schedule)


def test_seeded_blocks_normalize_base_order_without_relabelling_solo():
    raw = manifest()
    expected = planner.compile_schedule(raw)
    raw["base"]["cases"].reverse()
    raw["base"]["alternatives"].reverse()
    assert planner.compile_schedule(raw) == expected
    for offset in range(0, 12, 3):
        block = expected["runs"][offset:offset + 3]
        assert len({run["block_id"] for run in block}) == 1
        assert [run["order_position"] for run in block] == [1, 2, 3]
        assert len({(run["case_id"], run["replica"]) for run in block}) == 1
        assert {run["arm"] for run in block} == set(legacy.ARMS)
    for case in legacy.CASE_IDS:
        orders = [[run["arm"] for run in expected["runs"] if run["case_id"] == case and run["replica"] == replica]
                  for replica in (1, 2)]
        assert orders[1] == orders[0][1:] + orders[0][:1]


@pytest.mark.parametrize("path,replacement", [
    (("schema",), legacy.MANIFEST_SCHEMA_V2), (("base", "schema"), legacy.MANIFEST_SCHEMA),
    (("base", "round"), 2), (("base", "round"), True),
    (("base", "cases", 0, "case_id"), "R-F"), (("base", "cases", 1, "case_id"), "D-F"),
    (("base", "alternatives", 0, "mode"), "risk"),
    (("base", "inputs", "common_prompt", "sha256"), "bad"),
    (("base", "per_run_limits", "measured_tokens"), 80001),
    (("base", "per_run_limits", "active_seconds"), 5401),
    (("base", "per_run_limits", "tool_calls"), 65),
    (("base", "max_model_requests"), 129), (("base", "max_model_requests"), False),
    (("base", "model", "version"), ""), (("base", "seed"), 1.0),
    (("coordination", "profile"), "solo"), (("coordination", "workers"), 1),
    (("coordination", "workers"), 2.0), (("coordination", "max_concurrent_worker_requests"), True),
    (("coordination", "roles"), ["leader"]), (("coordination", "reviewer", "serial"), 1),
    (("coordination", "reviewer", "tools"), True), (("coordination", "sharing"), "private_histories"),
    (("coordination", "bootstrap", "work"), "preseeded"),
    (("coordination", "bootstrap", "init"), "caller"), (("coordination", "budget"), "per_worker"),
    (("shared_contract", "rubric"), {"sha256": sha("rubric"), "answers": []}),
    (("shared_contract", "delivery", "sha256"), "A" * 64),
    (("source_freeze_sha256",), None), (("runtime_policy",), {"path": "/caller/policy"}),
])
def test_invalid_coordination_limits_cases_or_refs_fail_closed(path, replacement):
    raw = manifest()
    assign(raw, path, replacement)
    with pytest.raises(planner.DevelopmentPlanError):
        planner.compile_schedule(raw)


@pytest.mark.parametrize("provider", ["openai", "google", "minimax", "fixture"])
def test_routes_are_bounded_declarations(provider):
    raw = manifest()["provider_route"]
    raw["provider"] = provider
    assert planner.validate_provider_route(raw) == raw


@pytest.mark.parametrize("key,value", [
    ("provider", "unregistered"), ("provider", "openai "), ("api", "https://example.invalid"),
    ("api", "Authorization: Bearer fixture"), ("version", "x" * 129),
    ("version", "v1\n"), ("service_tier", ""), ("service_tier", None),
])
def test_routes_reject_url_headers_invalid_values(key, value):
    route = manifest()["provider_route"]
    route[key] = value
    with pytest.raises(planner.DevelopmentPlanError):
        planner.validate_provider_route(route)


@pytest.mark.parametrize("path,replacement", [
    (("base", "seed"), 119), (("base", "protocol_sha256"), sha("other protocol")),
    (("base", "cases", 0, "package_sha256"), sha("other package")),
    (("base", "inputs", "common_prompt", "sha256"), sha("other common")),
    (("base", "inputs", "arm_prompts", "C", "sha256"), sha("other C prompt")),
    (("base", "model", "version"), "fixture-v2"), (("base", "model", "effort"), "high"),
    (("base", "model", "price_profile_sha256"), sha("other price")),
    (("base", "per_run_limits", "tool_calls"), 63), (("base", "max_model_requests"), 127),
    (("shared_contract", "delivery", "sha256"), sha("other delivery")),
    (("shared_contract", "rubric", "sha256"), sha("other rubric")),
    (("shared_contract", "coordination_prompt", "sha256"), sha("other coordination prompt")),
    (("runtime_policy", "sha256"), sha("other policy")),
    (("provider_route", "version"), "fixture-v2"), (("source_freeze_sha256",), sha("other freeze")),
])
def test_full_contract_changes_rebind_every_identity(path, replacement):
    raw = manifest()
    before = planner.compile_schedule(raw)
    assign(raw, path, replacement)
    after = planner.compile_schedule(raw)
    assert before["schedule_sha256"] != after["schedule_sha256"]
    assert not {run["run_id"] for run in before["runs"]} & {run["run_id"] for run in after["runs"]}


def test_mixed_solo_quartet_cannot_be_hidden_by_rehashed_rows():
    schedule = planner.compile_schedule(manifest())
    for run in schedule["runs"]:
        if run["arm"] in {"A", "B"}:
            run["agents"], run["agent_count"] = "solo", 1
            run["run_sha256"] = json_sha({key: value for key, value in run.items() if key not in {"run_id", "run_sha256"}})
            run["run_id"] = "dev-coord-" + run["run_sha256"][:24]
    schedule["schedule_sha256"] = json_sha({key: value for key, value in schedule.items() if key != "schedule_sha256"})
    with pytest.raises(planner.DevelopmentPlanError, match="recompilation"):
        planner.validate_schedule(schedule)


@pytest.mark.parametrize("path,replacement", [
    (("execution_profile",), "parent_analysis_wave_v1"), (("schema",), True),
    (("coordinates", "agents"), "solo"), (("coordinates", "case_id"), "D-S"),
    (("coordinates", "mode"), "wrong"), (("coordinates", "agent_count"), 1),
    (("model", "model_id"), "other"), (("model", "version"), "other-v2"),
    (("model", "effort_provider_value"), "high"), (("provider_route", "provider"), "google"),
    (("per_run_limits", "measured_tokens"), 79999), (("per_run_limits", "active_seconds"), 5399),
    (("per_run_limits", "tool_calls"), 63), (("max_model_requests",), 127),
    (("cost_limit_micro_usd",), 1), (("inputs", "tool_policy", "sha256"), sha("other")),
    (("shared_contract", "rubric", "sha256"), sha("other")),
    (("runtime_policy", "sha256"), sha("other")), (("source_freeze_sha256",), sha("other")),
    (("coordination", "bootstrap", "work"), "preseeded"),
    (("coordination", "budget"), "reset_after_init"),
    (("coordination", "reviewer", "tools"), True), (("run_id",), "dev-legacy-id"),
])
def test_runtime_binding_rejects_altered_declared_metadata(path, replacement):
    schedule = planner.compile_schedule(manifest())
    run_id = schedule["runs"][0]["run_id"]
    descriptor = planner.runtime_descriptor(schedule, run_id)
    assign(descriptor, path, replacement)
    with pytest.raises(planner.DevelopmentPlanError, match="binding"):
        planner.validate_runtime_binding(schedule, run_id, descriptor)


def test_all_cell_bindings_are_local_only_and_accept_no_authentication_flags():
    schedule = planner.compile_schedule(manifest())
    for run in schedule["runs"]:
        descriptor = planner.runtime_descriptor(schedule, run["run_id"])
        assert set(descriptor) == planner.RUNTIME_DESCRIPTOR_KEYS
        report = planner.validate_runtime_binding(schedule, run["run_id"], descriptor)
        assert report["binding_matches"] is True
        assert report["runtime_authenticated"] is False
        assert report["execution_authorized"] is False
        assert report["descriptor_sha256"] == json_sha(descriptor)
    descriptor["runtime_available"] = True
    with pytest.raises(planner.DevelopmentPlanError):
        planner.validate_runtime_binding(schedule, run["run_id"], descriptor)
    for field in ("execution_authorized", "results", "agents"):
        raw = manifest()
        raw[field] = True
        with pytest.raises(planner.DevelopmentPlanError):
            planner.validate_manifest(raw)
    with pytest.raises(planner.DevelopmentPlanError, match="absent"):
        planner.runtime_descriptor(schedule, "dev-legacy-id")


def test_compiler_has_no_filesystem_subprocess_or_claim_effects(monkeypatch):
    raw = manifest()

    def forbidden(*args, **kwargs):
        raise AssertionError("pure scheduler attempted an external effect")

    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr(os, "open", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    schedule = planner.compile_schedule(raw)
    run_id = schedule["runs"][0]["run_id"]
    planner.validate_runtime_binding(schedule, run_id, planner.runtime_descriptor(schedule, run_id))


def test_exported_coordination_mapping_cannot_redefine_the_fixed_contract(monkeypatch):
    raw = manifest()
    poisoned = copy.deepcopy(planner.COORDINATION)
    poisoned["workers"] = 1
    monkeypatch.setattr(planner, "COORDINATION", poisoned)
    assert planner.validate_manifest(raw)["coordination"]["workers"] == 2
    raw["coordination"] = poisoned
    with pytest.raises(planner.DevelopmentPlanError):
        planner.validate_manifest(raw)
