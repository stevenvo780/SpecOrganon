"""Compile twelve public A/B/C preparations for development round 1.

The manifest binds declared assets, model settings, price profile and limits.
Compilation does not read assets, execute a provider, reserve cases or seal an
experiment. Round 2 requires a separately frozen adaptation to round 1 evidence.
Usage: ``python scripts/plan_development_round.py [manifest.json|-]``.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


SCHEDULE_SCHEMA = "specorganon.development_round_schedule.v1"
MANIFEST_SCHEMA = "specorganon.development_round_manifest.v1"
CLASSIFICATION = "development_round_preparation_unsealed"
CASE_IDS = ("D-F", "D-E")
ARMS = ("A", "B", "C")
MODES = {"A": "sequential", "B": "graph", "C": "risk"}
INPUTS = ("task_contract", "common_prompt", "tool_policy")
ARM_PERMUTATIONS = tuple(itertools.permutations(ARMS))
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MANIFEST_KEYS = {
    "schema", "round", "seed", "protocol_sha256", "cases", "inputs",
    "alternatives", "model", "per_run_limits", "max_model_requests",
    "cost_limit_micro_usd",
}
SCHEDULE_KEYS = {
    "schema", "classification", "manifest", "seed", "protocol_sha256",
    "input_sha256", "models", "cases", "inputs", "per_run_limits",
    "max_model_requests", "cost_limit_micro_usd", "run_count", "block_count",
    "runs", "schedule_sha256",
}


class DevelopmentPlanError(ValueError):
    """A development manifest, schedule or asset binding is invalid."""


def canonical_bytes(value: Any) -> bytes:
    """Canonical UTF-8 JSON for every identity; non-JSON numbers are forbidden."""
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise DevelopmentPlanError("value cannot be encoded as canonical JSON") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _object(value: Any, name: str, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise DevelopmentPlanError(f"{name} must have exactly {sorted(keys)}")
    return value


def _list(value: Any, name: str, length: int) -> list[Any]:
    if type(value) is not list or len(value) != length:
        raise DevelopmentPlanError(f"{name} must contain exactly {length} entries")
    return value


def _integer(value: Any, name: str, minimum: int, maximum: int | None = None) -> int:
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        upper = "" if maximum is None else f" through {maximum}"
        raise DevelopmentPlanError(f"{name} must be an integer from {minimum}{upper}")
    return value


def _text(value: Any, name: str, *, max_bytes: int = 512) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise DevelopmentPlanError(f"{name} must be a nonempty trimmed string")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise DevelopmentPlanError(f"{name} must be valid UTF-8") from exc
    if len(encoded) > max_bytes or any(
        unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in value
    ):
        raise DevelopmentPlanError(f"{name} exceeds {max_bytes} UTF-8 bytes or contains controls")
    return value


def _sha256(value: Any, name: str) -> str:
    if type(value) is not str or HEX_SHA256.fullmatch(value) is None:
        raise DevelopmentPlanError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _reference(value: Any, name: str) -> dict[str, str]:
    source = _object(value, name, {"sha256"})
    return {"sha256": _sha256(source["sha256"], f"{name}.sha256")}


def validate_manifest(raw: Any) -> dict[str, Any]:
    """Validate and normalize the complete public round 1 manifest."""
    source = _object(raw, "manifest", MANIFEST_KEYS)
    if type(source["schema"]) is not str or source["schema"] != MANIFEST_SCHEMA:
        raise DevelopmentPlanError("invalid development manifest schema")
    if type(source["round"]) is not int or source["round"] != 1:
        raise DevelopmentPlanError("only round 1 is supported; round 2 needs frozen round 1 evidence")
    seed = _integer(source["seed"], "seed", 0, 2**64 - 1)
    cases = []
    for index, value in enumerate(_list(source["cases"], "cases", 2)):
        item = _object(value, f"cases[{index}]", {"case_id", "package_sha256"})
        if type(item["case_id"]) is not str or item["case_id"] not in CASE_IDS:
            raise DevelopmentPlanError("cases must be public D-F and D-E only")
        cases.append({
            "case_id": item["case_id"],
            "package_sha256": _sha256(item["package_sha256"], f"cases[{index}].package_sha256"),
        })
    if {item["case_id"] for item in cases} != set(CASE_IDS):
        raise DevelopmentPlanError("cases must contain D-F and D-E exactly once")
    cases.sort(key=lambda item: CASE_IDS.index(item["case_id"]))

    inputs = _object(source["inputs"], "inputs", set(INPUTS) | {"arm_prompts"})
    prompts = _object(inputs["arm_prompts"], "inputs.arm_prompts", set(ARMS))
    validated_inputs = {key: _reference(inputs[key], f"inputs.{key}") for key in INPUTS}
    validated_inputs["arm_prompts"] = {
        arm: _reference(prompts[arm], f"inputs.arm_prompts.{arm}") for arm in ARMS
    }

    alternatives = []
    for index, value in enumerate(_list(source["alternatives"], "alternatives", 3)):
        item = _object(value, f"alternatives[{index}]", {"alternative", "mode", "core_sha256"})
        arm = item["alternative"]
        if type(arm) is not str or arm not in ARMS or type(item["mode"]) is not str or item["mode"] != MODES[arm]:
            raise DevelopmentPlanError("alternatives must be A=sequential, B=graph, C=risk")
        alternatives.append({
            "alternative": arm, "mode": item["mode"],
            "core_sha256": _sha256(item["core_sha256"], f"alternatives[{index}].core_sha256"),
        })
    if {item["alternative"] for item in alternatives} != set(ARMS):
        raise DevelopmentPlanError("alternatives must contain A, B and C exactly once")
    if len({item["core_sha256"] for item in alternatives}) != 1:
        raise DevelopmentPlanError("all alternatives must share the same core digest")
    alternatives.sort(key=lambda item: ARMS.index(item["alternative"]))

    model_source = _object(source["model"], "model", {
        "model_id", "version", "family", "tier", "effort",
        "effort_provider_value", "price_profile_sha256",
    })
    model = {
        key: _text(model_source[key], f"model.{key}")
        for key in ("model_id", "version", "family", "tier", "effort")
    }
    provider_value = model_source["effort_provider_value"]
    model["effort_provider_value"] = (
        None if provider_value is None else _text(provider_value, "model.effort_provider_value")
    )
    model["price_profile_sha256"] = _sha256(model_source["price_profile_sha256"], "model.price_profile_sha256")
    limits = _object(source["per_run_limits"], "per_run_limits", {"measured_tokens", "active_seconds", "tool_calls"})
    return {
        "schema": MANIFEST_SCHEMA, "round": 1, "seed": seed,
        "protocol_sha256": _sha256(source["protocol_sha256"], "protocol_sha256"),
        "cases": cases, "inputs": validated_inputs, "alternatives": alternatives,
        "model": model,
        "per_run_limits": {
            "measured_tokens": _integer(limits["measured_tokens"], "measured_tokens", 1, 80_000),
            "active_seconds": _integer(limits["active_seconds"], "active_seconds", 1, 5_400),
            "tool_calls": _integer(limits["tool_calls"], "tool_calls", 1, 16),
        },
        "max_model_requests": _integer(source["max_model_requests"], "max_model_requests", 2, 32),
        "cost_limit_micro_usd": _integer(source["cost_limit_micro_usd"], "cost_limit_micro_usd", 0),
    }


def compile_schedule(raw: Any) -> dict[str, Any]:
    """Compile twelve solo preparations; no filesystem or provider effects."""
    manifest = validate_manifest(raw)
    input_sha256 = digest(manifest)
    model = manifest["model"]
    blocks = []
    for case in manifest["cases"]:
        stratum = {
            "model_id": model["model_id"], "effort": model["effort"],
            "agents": "solo", "case_id": case["case_id"], "round": 1,
        }
        stratum_id = "dev-stratum-" + digest({"input_sha256": input_sha256, **stratum})[:24]
        order_seed = digest({"seed": manifest["seed"], "stratum": stratum})
        base_order = list(ARM_PERMUTATIONS[int(order_seed, 16) % len(ARM_PERMUTATIONS)])
        for replica in (1, 2):
            # Two cyclic orders reduce repeated positions; they do not provide
            # the complete positional balance of a three-replica experiment.
            order = base_order[replica - 1:] + base_order[:replica - 1]
            block_id = "dev-block-" + digest({"stratum_id": stratum_id, "replica": replica})[:24]
            block = []
            for position, arm in enumerate(order, start=1):
                block.append({
                    "stratum_id": stratum_id, "block_id": block_id,
                    "family": model["family"], "tier": model["tier"],
                    "model_id": model["model_id"], "model_version": model["version"],
                    "effort": model["effort"], "effort_provider_value": model["effort_provider_value"],
                    "agents": "solo", "case_id": case["case_id"], "replica": replica,
                    "order_position": position, "arm": arm,
                    "input_sha256": input_sha256, "case_package_sha256": case["package_sha256"],
                    "case_reference_sha256": None, "round": 1,
                })
            blocks.append(block)
    blocks.sort(key=lambda block: digest({"seed": manifest["seed"], "block_id": block[0]["block_id"]}))
    runs = []
    for release_order, block in enumerate(blocks, start=1):
        for run in block:
            run["release_block_order"] = release_order
            run_sha256 = digest(run)
            runs.append({**run, "run_id": "dev-" + run_sha256[:24], "run_sha256": run_sha256})
    schedule = {
        "schema": SCHEDULE_SCHEMA, "classification": CLASSIFICATION,
        "manifest": manifest, "seed": manifest["seed"],
        "protocol_sha256": manifest["protocol_sha256"], "input_sha256": input_sha256,
        "models": [model], "cases": manifest["cases"], "inputs": manifest["inputs"],
        "per_run_limits": manifest["per_run_limits"],
        "max_model_requests": manifest["max_model_requests"],
        "cost_limit_micro_usd": manifest["cost_limit_micro_usd"],
        "run_count": len(runs), "block_count": len(blocks), "runs": runs,
    }
    schedule["schedule_sha256"] = digest(schedule)
    return schedule


def _strict_json(value: Any) -> None:
    """Avoid Python equality/JSON coercions accepting bools, tuples or floats."""
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise DevelopmentPlanError("schedule object keys must be strings")
            _strict_json(item)
    elif type(value) is list:
        for item in value:
            _strict_json(item)
    elif value is not None and type(value) not in (str, int):
        raise DevelopmentPlanError("schedule contains an invalid field type")


def validate_schedule(raw: Any) -> dict[str, Any]:
    """Require exact recompilation, including coordinates, identities and order."""
    source = _object(raw, "schedule", SCHEDULE_KEYS)
    try:
        _strict_json(source)
    except RecursionError as exc:
        raise DevelopmentPlanError("schedule nesting is invalid") from exc
    expected = compile_schedule(source["manifest"])
    if canonical_bytes(source) != canonical_bytes(expected):
        raise DevelopmentPlanError("schedule differs from exact manifest recompilation")
    return expected


def validate_runtime_budget(
    schedule: Any, *, max_model_requests: int, cost_limit_micro_usd: int,
    price_profile: dict[str, Any],
) -> None:
    """Bind a runner's budget to DEV declarations before creating any run state.

    Price bytes use the ledger's ASCII JSON plus newline protocol, rather than
    the schedule's UTF-8 JSON protocol. Rates remain caller declarations.
    """
    verified = validate_schedule(schedule)
    _integer(max_model_requests, "runtime max_model_requests", 2, verified["max_model_requests"])
    _integer(cost_limit_micro_usd, "runtime cost_limit_micro_usd", 0, verified["cost_limit_micro_usd"])
    from managed_token_ledger import BudgetError, _canonical, _price_profile

    try:
        profile = _price_profile(price_profile)
        profile_sha256 = hashlib.sha256(_canonical(profile)).hexdigest()
    except BudgetError as exc:
        raise DevelopmentPlanError("invalid runtime price profile") from exc
    model = verified["manifest"]["model"]
    if profile["model"] != model["model_id"]:
        raise DevelopmentPlanError("runtime price profile model differs from declared model")
    if profile_sha256 != model["price_profile_sha256"]:
        raise DevelopmentPlanError("runtime price profile digest differs from declared price profile")


def _absolute_file_path(raw: Any, label: str) -> Path:
    text = _text(raw, label, max_bytes=4_096)
    path = Path(text)
    if not path.is_absolute():
        raise DevelopmentPlanError(f"{label} must be an absolute file path")
    return path


def asset_paths(schedule: Any, raw: Any) -> tuple[dict[str, Path], dict[str, str]]:
    """Bind eight public asset paths; reading or hashing bytes is preflight's job."""
    verified = validate_schedule(schedule)
    source = _object(raw, "asset map", {"schema", "schedule_sha256", "input_sha256", "cases", "inputs"})
    if type(source["schema"]) is not int or source["schema"] != 1:
        raise DevelopmentPlanError("asset map schema must be integer 1")
    for key in ("schedule_sha256", "input_sha256"):
        if _sha256(source[key], f"asset map.{key}") != verified[key]:
            raise DevelopmentPlanError("asset map digest binding differs from schedule")
    cases = _object(source["cases"], "asset map cases", set(CASE_IDS))
    inputs = _object(source["inputs"], "asset map inputs", set(INPUTS) | {"arm_prompts"})
    prompts = _object(inputs["arm_prompts"], "asset map arm_prompts", set(ARMS))
    paths, digests = {}, {}
    for case in verified["cases"]:
        label = f"case:{case['case_id']}:package"
        paths[label] = _absolute_file_path(cases[case["case_id"]], label)
        digests[label] = case["package_sha256"]
    for key in INPUTS:
        label = f"input:{key}"
        paths[label] = _absolute_file_path(inputs[key], label)
        digests[label] = verified["inputs"][key]["sha256"]
    for arm in ARMS:
        label = f"prompt:{arm}"
        paths[label] = _absolute_file_path(prompts[arm], label)
        digests[label] = verified["inputs"]["arm_prompts"][arm]["sha256"]
    return paths, digests


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DevelopmentPlanError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise DevelopmentPlanError(f"non-JSON numeric constant: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", nargs="?", default="-")
    args = parser.parse_args(argv)
    try:
        text = sys.stdin.read() if args.manifest == "-" else Path(args.manifest).read_text(encoding="utf-8")
        raw = json.loads(text, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant)
        output = canonical_bytes(compile_schedule(raw)).decode("utf-8")
    except (DevelopmentPlanError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Invalid development manifest: {exc}", file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
