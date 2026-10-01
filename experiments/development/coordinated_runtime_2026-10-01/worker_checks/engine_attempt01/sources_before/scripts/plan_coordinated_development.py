"""Pure prospective R1 metadata for equally coordinated A/B/C development.

This schema has new identities. The legacy DEV2 manifest only normalizes the
common declarations; its solo schedule is never executed or relabelled here.
Matching runtime metadata establishes a local binding, not runtime capability,
provider identity, measured activity, custody, quality or authorization.
"""

from __future__ import annotations

import json
import re
from typing import Any

import plan_development_round as original


MANIFEST_SCHEMA = "specorganon.coordinated_development_manifest.v1"
SCHEDULE_SCHEMA = "specorganon.coordinated_development_schedule.v1"
CLASSIFICATION = "development_coordinated_round_preparation_unsealed"
RUNTIME_PROFILE = "coordinated_development_parent_v1"
COORDINATION = {
    "profile": "leader_two_workers_reviewer_v1",
    "roles": ["leader", "worker-1", "worker-2", "reviewer"],
    "workers": 2,
    "max_concurrent_worker_requests": 2,
    "reviewer": {"serial": True, "tools": False},
    "sharing": "public_artifacts_only",
    "bootstrap": {"work": "empty", "init": "leader"},
    "budget": "single_parent",
}
MANIFEST_KEYS = {"schema", "base", "coordination", "shared_contract", "runtime_policy",
                 "provider_route", "source_freeze_sha256"}
SCHEDULE_KEYS = {
    "schema", "classification", "manifest", "seed", "protocol_sha256", "input_sha256",
    "models", "cases", "inputs", "per_run_limits", "max_model_requests", "cost_limit_micro_usd",
    "coordination", "coordination_sha256", "shared_contract", "runtime_policy", "provider_route",
    "source_freeze_sha256", "run_count", "block_count", "runs", "schedule_sha256",
}
RUNTIME_DESCRIPTOR_KEYS = {
    "schema", "execution_profile", "schedule_sha256", "run_id", "run_sha256", "coordinates",
    "model", "provider_route", "per_run_limits", "max_model_requests", "cost_limit_micro_usd",
    "inputs", "shared_contract", "runtime_policy", "source_freeze_sha256", "coordination",
}
DevelopmentPlanError = original.DevelopmentPlanError
CoordinatedDevelopmentError = DevelopmentPlanError
canonical_bytes = original.canonical_bytes
digest = original.digest
_COORDINATION_BYTES = canonical_bytes(COORDINATION)
_ROUTE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


def _strict_json(value: Any) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise DevelopmentPlanError("metadata object keys must be strings")
            _strict_json(item)
    elif type(value) is list:
        for item in value:
            _strict_json(item)
    elif value is not None and type(value) not in (str, int, bool):
        raise DevelopmentPlanError("metadata contains a non-JSON or noninteger field")


def _checked_json(value: Any) -> None:
    try:
        _strict_json(value)
    except RecursionError as exc:
        raise DevelopmentPlanError("metadata nesting is invalid") from exc


def validate_provider_route(raw: Any) -> dict[str, str]:
    """Validate bounded route identifiers, without URL, header or auth fields."""
    route = original._object(raw, "provider_route", {"provider", "api", "version", "service_tier"})
    provider = original._text(route["provider"], "provider_route.provider", max_bytes=16)
    if provider not in {"openai", "google", "minimax", "fixture"}:
        raise DevelopmentPlanError("provider_route provider is unsupported")
    result = {"provider": provider}
    for key in ("api", "version", "service_tier"):
        text = original._text(route[key], f"provider_route.{key}", max_bytes=128)
        if _ROUTE_ID.fullmatch(text) is None:
            raise DevelopmentPlanError("provider_route values must be bounded identifiers, not URLs or auth")
        result[key] = text
    return result


def validate_manifest(raw: Any) -> dict[str, Any]:
    """Normalize DEV2 declarations and require the fixed four-role contract."""
    source = original._object(raw, "coordinated manifest", MANIFEST_KEYS)
    _checked_json(source)
    if type(source["schema"]) is not str or source["schema"] != MANIFEST_SCHEMA:
        raise DevelopmentPlanError("invalid coordinated manifest schema")
    if type(source["base"]) is not dict or source["base"].get("schema") != original.MANIFEST_SCHEMA_V2:
        raise DevelopmentPlanError("coordinated base must use the original DEV2 manifest schema")
    base = original.validate_manifest(source["base"])
    if canonical_bytes(source["coordination"]) != _COORDINATION_BYTES:
        raise DevelopmentPlanError("coordination differs from the common four-role contract")
    shared = original._object(source["shared_contract"], "shared_contract",
                              {"delivery", "rubric", "coordination_prompt"})
    return {
        "schema": MANIFEST_SCHEMA, "base": base,
        "coordination": json.loads(_COORDINATION_BYTES),
        "shared_contract": {key: original._reference(shared[key], f"shared_contract.{key}")
                            for key in ("delivery", "rubric", "coordination_prompt")},
        "runtime_policy": original._reference(source["runtime_policy"], "runtime_policy"),
        "provider_route": validate_provider_route(source["provider_route"]),
        "source_freeze_sha256": original._sha256(source["source_freeze_sha256"], "source_freeze_sha256"),
    }


def compile_schedule(raw: Any) -> dict[str, Any]:
    """Compile 12 fresh R1 cells; no filesystem, provider or claim effects."""
    manifest = validate_manifest(raw)
    base, model = manifest["base"], manifest["base"]["model"]
    input_sha = digest(manifest)
    coordination_sha = digest(manifest["coordination"])
    blocks = []
    for case in base["cases"]:
        stratum = {"model_id": model["model_id"], "model_version": model["version"],
                   "effort": model["effort"], "agents": manifest["coordination"]["profile"],
                   "coordination_sha256": coordination_sha, "case_id": case["case_id"], "round": 1}
        stratum_id = "dev-coord-stratum-" + digest({"input_sha256": input_sha, **stratum})[:24]
        order_seed = digest({"seed": base["seed"], "stratum": stratum})
        order = list(original.ARM_PERMUTATIONS[int(order_seed, 16) % len(original.ARM_PERMUTATIONS)])
        for replica in (1, 2):
            rotated = order[replica - 1:] + order[:replica - 1]
            block_id = "dev-coord-block-" + digest({"stratum_id": stratum_id, "replica": replica})[:24]
            blocks.append([{
                "stratum_id": stratum_id, "block_id": block_id,
                "family": model["family"], "tier": model["tier"], "model_id": model["model_id"],
                "model_version": model["version"], "effort": model["effort"],
                "effort_provider_value": model["effort_provider_value"],
                "agents": manifest["coordination"]["profile"], "agent_count": 4,
                "coordination_sha256": coordination_sha,
                "case_id": case["case_id"], "case_package_sha256": case["package_sha256"],
                "case_reference_sha256": None, "replica": replica, "order_position": position,
                "arm": arm, "mode": original.MODES[arm], "input_sha256": input_sha, "round": 1,
            } for position, arm in enumerate(rotated, 1)])
    blocks.sort(key=lambda block: digest({"seed": base["seed"], "block_id": block[0]["block_id"]}))
    runs = []
    for release_order, block in enumerate(blocks, 1):
        for run in block:
            body = {**run, "release_block_order": release_order}
            run_sha = digest(body)
            runs.append({**body, "run_id": "dev-coord-" + run_sha[:24], "run_sha256": run_sha})
    schedule = {
        "schema": SCHEDULE_SCHEMA, "classification": CLASSIFICATION, "manifest": manifest,
        "seed": base["seed"], "protocol_sha256": base["protocol_sha256"], "input_sha256": input_sha,
        "models": [model], "cases": base["cases"], "inputs": base["inputs"],
        "per_run_limits": base["per_run_limits"], "max_model_requests": base["max_model_requests"],
        "cost_limit_micro_usd": base["cost_limit_micro_usd"],
        **{key: manifest[key] for key in ("coordination", "shared_contract", "runtime_policy",
                                       "provider_route", "source_freeze_sha256")},
        "coordination_sha256": coordination_sha, "run_count": 12, "block_count": 4, "runs": runs,
    }
    schedule["schedule_sha256"] = digest(schedule)
    return json.loads(canonical_bytes(schedule))


def validate_schedule(raw: Any) -> dict[str, Any]:
    """Require all rows, metadata, order and identities to recompile exactly."""
    source = original._object(raw, "coordinated schedule", SCHEDULE_KEYS)
    _checked_json(source)
    expected = compile_schedule(source["manifest"])
    if canonical_bytes(source) != canonical_bytes(expected):
        raise DevelopmentPlanError("coordinated schedule differs from exact manifest recompilation")
    return expected


def runtime_descriptor(schedule: Any, run_id: str) -> dict[str, Any]:
    """Return the declared descriptor for a cell, without claiming it exists."""
    checked = validate_schedule(schedule)
    if type(run_id) is not str:
        raise DevelopmentPlanError("runtime run_id must be a string")
    selected = next((run for run in checked["runs"] if run["run_id"] == run_id), None)
    if selected is None:
        raise DevelopmentPlanError("runtime run_id is absent from coordinated schedule")
    descriptor = {
        "schema": 1, "execution_profile": RUNTIME_PROFILE,
        "schedule_sha256": checked["schedule_sha256"], "run_id": run_id,
        "run_sha256": selected["run_sha256"],
        "coordinates": {key: value for key, value in selected.items() if key not in {"run_id", "run_sha256"}},
        "model": checked["models"][0],
        **{key: checked[key] for key in ("provider_route", "per_run_limits", "max_model_requests",
            "cost_limit_micro_usd", "inputs", "shared_contract", "runtime_policy",
            "source_freeze_sha256", "coordination")},
    }
    return json.loads(canonical_bytes(descriptor))


def validate_runtime_binding(schedule: Any, run_id: str, descriptor: Any) -> dict[str, Any]:
    """Check exact local declarations; never authorize or authenticate flags."""
    provided = original._object(descriptor, "runtime descriptor", RUNTIME_DESCRIPTOR_KEYS)
    _checked_json(provided)
    expected = runtime_descriptor(schedule, run_id)
    if canonical_bytes(provided) != canonical_bytes(expected):
        raise DevelopmentPlanError("runtime descriptor differs from coordinated cell binding")
    return {"schema": 1, "classification": "development_coordinated_runtime_binding_unsealed",
            "schedule_sha256": expected["schedule_sha256"], "run_id": run_id,
            "run_sha256": expected["run_sha256"], "descriptor_sha256": digest(expected),
            "binding_matches": True, "runtime_authenticated": False, "execution_authorized": False}
