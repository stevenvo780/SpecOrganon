"""Compile a read-only, unsealed candidate for the confirmatory N/S/T matrix.

Usage: ``python scripts/plan_confirmatory.py [manifest.json|-]``. With no
argument, read JSON from stdin. Print one JSON object to stdout; never write
files, invoke providers, reserve cases, or register an experiment.

Schema-1 input example (every digest is a lowercase SHA-256 of the named asset)::

    {
      "schema": 1,
      "seed": 123,
      "protocol_sha256": "<64 hex digits>",
      "tool_call_cap": 100,
      "models": [
        {"family": "family-a", "tier": "lower", "model_id": "a-small",
         "version": "2026-01", "effort_control": true,
         "efforts": [{"label": "low", "provider_value": "low"},
                     {"label": "high", "provider_value": "high"}]}
      ],
      "cases": [{"case_id": "R-F", "package_sha256": "<64 hex digits>",
                 "reference_sha256": "<64 hex digits>"}],
      "inputs": {
        "task_contract": {"ref": "...", "sha256": "<64 hex digits>"},
        "common_prompt": {"ref": "...", "sha256": "<64 hex digits>"},
        "arm_prompts": {"N": {"ref": "...", "sha256": "<64 hex digits>"},
                        "S": {"ref": "...", "sha256": "<64 hex digits>"},
                        "T": {"ref": "...", "sha256": "<64 hex digits>"}},
        "rubric": {"ref": "...", "sha256": "<64 hex digits>"},
        "tool_policy": {"ref": "...", "sha256": "<64 hex digits>"},
        "sdd_guide": {"ref": "...", "sha256": "<64 hex digits>"},
        "toolkit": {"ref": "...", "sha256": "<64 hex digits>"}
      }
    }

The example abbreviates the required four models and three reserved cases.
``package_sha256`` identifies executor-visible case material;
``reference_sha256`` identifies its separately custodied sealed solution. The
compiler checks digest syntax and bindings, never reads reserved bytes.
For a model without an effort control, use ``effort_control: false`` and
``efforts: [{"label": "default"}]``. At least one model per family must be
configurable, as required to interpret the protocol's effort comparison.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import sys
from pathlib import Path
from typing import Any


ARMS = ("N", "S", "T")
ARM_PERMUTATIONS = tuple(itertools.permutations(ARMS))
AGENT_CONFIGURATIONS = ("solo", "trio")
CASE_IDS = ("R-F", "R-M", "R-S")
TIERS = ("lower", "higher")
REPLICAS = 3
MAX_CONFIRMATORY_RUNS = 432
TOKENS_PER_RUN = 80_000
ACTIVE_SECONDS_PER_RUN = 90 * 60
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
FAMILY_SLUG = re.compile(r"[a-z][a-z0-9._-]{0,63}\Z")


class ManifestError(ValueError):
    """The prospective manifest does not satisfy input schema 1."""


def canonical_bytes(value: Any) -> bytes:
    """UTF-8 canonical JSON used for all identifiers and SHA-256 digests."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _object(value: Any, name: str, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise ManifestError(f"{name} must be an object")
    missing, extra = keys - value.keys(), value.keys() - keys
    if missing or extra:
        raise ManifestError(f"{name} has missing keys {sorted(missing)} or unexpected keys {sorted(extra)}")
    return value


def _list(value: Any, name: str, length: int) -> list[Any]:
    if type(value) is not list or len(value) != length:
        raise ManifestError(f"{name} must contain exactly {length} entries")
    return value


def _text(value: Any, name: str, *, max_length: int = 512) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > max_length:
        raise ManifestError(f"{name} must be a nonempty, trimmed string of at most {max_length} characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ManifestError(f"{name} contains a control character")
    return value


def _sha256(value: Any, name: str) -> str:
    if type(value) is not str or HEX_SHA256.fullmatch(value) is None:
        raise ManifestError(f"{name} must be a lowercase 64-character SHA-256 digest")
    return value


def _reference(value: Any, name: str) -> dict[str, str]:
    item = _object(value, name, {"ref", "sha256"})
    return {
        "ref": _text(item["ref"], f"{name}.ref"),
        "sha256": _sha256(item["sha256"], f"{name}.sha256"),
    }


def _model(value: Any, index: int) -> dict[str, Any]:
    name = f"models[{index}]"
    model = _object(value, name, {"family", "tier", "model_id", "version", "effort_control", "efforts"})
    family = _text(model["family"], f"{name}.family", max_length=64)
    if FAMILY_SLUG.fullmatch(family) is None:
        raise ManifestError(f"{name}.family must be a lowercase identifier")
    tier = model["tier"]
    if tier not in TIERS or type(tier) is not str:
        raise ManifestError(f"{name}.tier must be lower or higher")
    model_id = _text(model["model_id"], f"{name}.model_id")
    version = _text(model["version"], f"{name}.version")
    controlled = model["effort_control"]
    if type(controlled) is not bool:
        raise ManifestError(f"{name}.effort_control must be a boolean")

    efforts = _list(model["efforts"], f"{name}.efforts", 2 if controlled else 1)
    if controlled:
        validated = []
        for effort_index, effort in enumerate(efforts):
            effort_name = f"{name}.efforts[{effort_index}]"
            item = _object(effort, effort_name, {"label", "provider_value"})
            label = item["label"]
            if type(label) is not str or label not in ("low", "high"):
                raise ManifestError(f"{effort_name}.label must be low or high")
            validated.append({
                "label": label,
                "provider_value": _text(item["provider_value"], f"{effort_name}.provider_value"),
            })
        if {item["label"] for item in validated} != {"low", "high"}:
            raise ManifestError(f"{name}.efforts must contain low and high exactly once")
        if len({item["provider_value"] for item in validated}) != 2:
            raise ManifestError(f"{name}.efforts must use distinct provider values")
        validated.sort(key=lambda item: ("low", "high").index(item["label"]))
    else:
        item = _object(efforts[0], f"{name}.efforts[0]", {"label"})
        if item["label"] != "default" or type(item["label"]) is not str:
            raise ManifestError(f"{name}.efforts must contain only the default level without a provider value")
        validated = [{"label": "default"}]

    return {
        "family": family,
        "tier": tier,
        "model_id": model_id,
        "version": version,
        "effort_control": controlled,
        "efforts": validated,
    }


def validate_manifest(raw: Any) -> dict[str, Any]:
    """Reject incomplete, ambiguous, or selectively thinned matrix inputs."""
    source = _object(raw, "manifest", {
        "schema", "seed", "protocol_sha256", "tool_call_cap", "models", "cases", "inputs"
    })
    if type(source["schema"]) is not int or source["schema"] != 1:
        raise ManifestError("schema must be integer 1")
    seed = source["seed"]
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ManifestError("seed must be an unsigned 64-bit integer")
    protocol_sha256 = _sha256(source["protocol_sha256"], "protocol_sha256")
    tool_call_cap = source["tool_call_cap"]
    if type(tool_call_cap) is not int or not 1 <= tool_call_cap <= 1_000_000:
        raise ManifestError("tool_call_cap must be an integer from 1 through 1000000")

    models = [_model(item, index) for index, item in enumerate(_list(source["models"], "models", 4))]
    if len({model["model_id"] for model in models}) != 4:
        raise ManifestError("model_id values must be unique")
    families = {model["family"] for model in models}
    if len(families) != 2:
        raise ManifestError("models must identify exactly two families")
    for family in families:
        family_models = [model for model in models if model["family"] == family]
        if {model["tier"] for model in family_models} != set(TIERS) or len(family_models) != 2:
            raise ManifestError(f"family {family} must have one lower and one higher tier")
        if not any(model["effort_control"] for model in family_models):
            raise ManifestError(f"family {family} needs at least one model with low/high effort control")
    models.sort(key=lambda item: (item["family"], TIERS.index(item["tier"]), item["model_id"]))

    cases = []
    for index, value in enumerate(_list(source["cases"], "cases", 3)):
        item = _object(value, f"cases[{index}]", {"case_id", "package_sha256", "reference_sha256"})
        if type(item["case_id"]) is not str or item["case_id"] not in CASE_IDS:
            raise ManifestError(f"cases[{index}].case_id must be R-F, R-M, or R-S")
        cases.append({
            "case_id": item["case_id"],
            "package_sha256": _sha256(item["package_sha256"], f"cases[{index}].package_sha256"),
            "reference_sha256": _sha256(item["reference_sha256"], f"cases[{index}].reference_sha256"),
        })
    if {item["case_id"] for item in cases} != set(CASE_IDS):
        raise ManifestError("cases must contain R-F, R-M, and R-S exactly once")
    if len({item["package_sha256"] for item in cases}) != 3:
        raise ManifestError("case packages must have distinct SHA-256 digests")
    if len({item["reference_sha256"] for item in cases}) != 3:
        raise ManifestError("case reference solutions must have distinct SHA-256 digests")
    cases.sort(key=lambda item: CASE_IDS.index(item["case_id"]))

    inputs = _object(source["inputs"], "inputs", {
        "task_contract", "common_prompt", "arm_prompts", "rubric", "tool_policy", "sdd_guide", "toolkit"
    })
    arm_prompts = _object(inputs["arm_prompts"], "inputs.arm_prompts", set(ARMS))
    validated_inputs = {
        key: _reference(inputs[key], f"inputs.{key}")
        for key in ("task_contract", "common_prompt", "rubric", "tool_policy", "sdd_guide", "toolkit")
    }
    validated_inputs["arm_prompts"] = {
        arm: _reference(arm_prompts[arm], f"inputs.arm_prompts.{arm}") for arm in ARMS
    }
    if len({validated_inputs["arm_prompts"][arm]["sha256"] for arm in ARMS}) != 3:
        raise ManifestError("N, S, and T arm prompts must have distinct SHA-256 digests")

    return {
        "schema": 1,
        "seed": seed,
        "protocol_sha256": protocol_sha256,
        "tool_call_cap": tool_call_cap,
        "models": models,
        "cases": cases,
        "inputs": validated_inputs,
    }


def compile_schedule(raw: Any) -> dict[str, Any]:
    """Build all paired cells and balanced arm orders without side effects."""
    manifest = validate_manifest(raw)
    input_sha256 = digest(manifest)
    blocks: list[list[dict[str, Any]]] = []
    for model in manifest["models"]:
        for effort in model["efforts"]:
            for agents in AGENT_CONFIGURATIONS:
                for case in manifest["cases"]:
                    stratum = {
                        "model_id": model["model_id"],
                        "effort": effort["label"],
                        "agents": agents,
                        "case_id": case["case_id"],
                    }
                    stratum_seed = digest({"seed": manifest["seed"], "stratum": stratum})
                    base_order = list(ARM_PERMUTATIONS[int(stratum_seed, 16) % len(ARM_PERMUTATIONS)])
                    stratum_id = "stratum-" + digest({"input_sha256": input_sha256, **stratum})[:24]
                    for replica in range(1, REPLICAS + 1):
                        order = base_order[replica - 1 :] + base_order[: replica - 1]
                        block_id = "block-" + digest({"stratum_id": stratum_id, "replica": replica})[:24]
                        block = []
                        for order_position, arm in enumerate(order, start=1):
                            run = {
                                "input_sha256": input_sha256,
                                "stratum_id": stratum_id,
                                "block_id": block_id,
                                "family": model["family"],
                                "tier": model["tier"],
                                "model_id": model["model_id"],
                                "model_version": model["version"],
                                "effort": effort["label"],
                                "effort_provider_value": effort.get("provider_value"),
                                "agents": agents,
                                "case_id": case["case_id"],
                                "case_package_sha256": case["package_sha256"],
                                "case_reference_sha256": case["reference_sha256"],
                                "replica": replica,
                                "order_position": order_position,
                                "arm": arm,
                            }
                            block.append(run)
                        blocks.append(block)

    # Release whole paired blocks in a seeded, cross-model order. The arms
    # inside each block remain in their cyclic, counterbalanced order.
    blocks.sort(key=lambda block: digest({"seed": manifest["seed"], "block_id": block[0]["block_id"]}))
    runs = []
    for release_block_order, block in enumerate(blocks, start=1):
        for run in block:
            run["release_block_order"] = release_block_order
            run_sha256 = digest(run)
            runs.append({
                "run_id": "conf-" + run_sha256[:24],
                "run_sha256": run_sha256,
                **run,
            })
    if len(runs) > MAX_CONFIRMATORY_RUNS:
        raise ManifestError("confirmatory run cap exceeded")
    expected = (
        sum(len(model["efforts"]) for model in manifest["models"])
        * len(AGENT_CONFIGURATIONS) * len(CASE_IDS) * REPLICAS * len(ARMS)
    )
    if len(runs) != expected:
        raise RuntimeError("schedule cell count does not match the complete panel")
    if len({run["run_id"] for run in runs}) != len(runs):
        raise RuntimeError("schedule run identifiers are not unique")

    result = {
        "schema": 1,
        "classification": "candidate_schedule_unsealed",
        "notice": (
            "Prospective schedule only; no sealed registry, case reservation, "
            "provider execution, spending, or results."
        ),
        "input_sha256": input_sha256,
        "seed": manifest["seed"],
        "protocol_sha256": manifest["protocol_sha256"],
        "models": manifest["models"],
        "cases": manifest["cases"],
        "inputs": manifest["inputs"],
        "arms": list(ARMS),
        "agent_configurations": list(AGENT_CONFIGURATIONS),
        "replicas_per_stratum": REPLICAS,
        "per_run_limits": {
            "measured_tokens": TOKENS_PER_RUN,
            "active_seconds": ACTIVE_SECONDS_PER_RUN,
            "tool_calls": manifest["tool_call_cap"],
        },
        "study_limits": {
            "max_confirmatory_runs": MAX_CONFIRMATORY_RUNS,
            "max_simultaneous_runs": 4,
            "external_retry_slots_studywide": 10,
        },
        "block_count": len(blocks),
        "run_count": len(runs),
        "runs": runs,
    }
    result["schedule_sha256"] = digest(result)
    return result


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ManifestError(f"non-JSON numeric constant: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", nargs="?", default="-", help="schema-1 JSON manifest path, or - for stdin")
    args = parser.parse_args(argv)
    try:
        if args.manifest == "-":
            source = sys.stdin.read()
        else:
            source = Path(args.manifest).read_text(encoding="utf-8")
        raw = json.loads(source, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant)
        result = compile_schedule(raw)
    except (ManifestError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Invalid confirmatory manifest: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
