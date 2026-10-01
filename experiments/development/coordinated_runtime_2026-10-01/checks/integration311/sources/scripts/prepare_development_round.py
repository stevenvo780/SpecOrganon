"""Build public A/B/C round-one preparations; never contact a model provider.

This adapter is development only. C has no parallel executor here. Config v2
opts into a separate read-only analysis tool and common PDF text derivations.
Preparing twelve attempts does not execute twelve of the required 24 cells.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

from case_package import pack_package
from development_analysis_inputs import build_text_inputs
from development_analysis_tool import build_analysis_tool
from development_method_tool import build_tool
from managed_token_ledger import _canonical as ledger_canonical
from managed_token_ledger import _price_profile
from plan_development_round import (
    MANIFEST_SCHEMA, MANIFEST_SCHEMA_V2, SCHEDULE_SCHEMA_V2,
    compile_schedule, validate_schedule,
)
from preflight_assets import preflight
from run_managed_team import prepare_team
from stage_released_run import stage_released_run
from verify_released_run import _read_schedule


ROOT = Path(__file__).resolve().parents[1]
CLASSIFICATION = "development_round_preparation_unsealed"
SOURCE_BASE = "98a1403ea972f328a86a114f207716978fd98a98"
# Public source identities from SOURCE_BASE, fixed before building any attempt.
SOURCE_PINS = {
    "GOAL.md": "e8341bea380cc357ad9e02ec4689a4ed47fe198ba06e4c98639f29264c314c36",
    "docs/protocolo_experimental.md": "3fd27c7cdb1842732f9fe37191a844e0d1e74bd1f1019331eb98ab8584eb0341",
    "prototypes/core.py": "6bf67d5542ac4fb9b9b1f9bd1e122ddb4c3b0a29e2fe26d040f1c401a2828986",
    "cases/bread_development/task.md": "ab73075db2b4ee8c5e58dfc873ef14b75276dbcc0ba7afc9685c5b72b72add51",
    "cases/bread_development/source_claims.json": "63ce5419981c0a3f7d7ba83218cac2dbb528f061b313cfdf4655400ac2e86abc",
    "cases/bread_development/source_manifest.json": "83bdf5e7bc584971ca2446cf0fe6bd83dd4b9ea624a433fc54c5e5b3f89c4f3a",
    "cases/bread_norway/source_lca.pdf": "9d64c0538b76ebaa19af86fb7ec231243cb5e1272316105ad979cfb9b6de3a32",
    "cases/bread_norway/source_survey.pdf": "61b3b63cc7b5748138335fa2eaebde2f4ab0e454750e4592582fb80a5043dcee",
    "cases/bread_norway/survey_table1.json": "50361b4803226a6a387fb39f0289c0e708679f348b5081ccb0034242155a064f",
    "cases/building_energy/task.md": "f6fed29bc6ce18631cff30710b25f30b9662e04f889f336cccda2869f0789b64",
    "cases/building_energy/source_manifest.json": "0e18340d130c495201e68c1c869bc2c6f49b35663176040aebb0d0d7d7bd1ee1",
    "cases/building_energy/sample_first_complete_week.csv": "c7f66ffaadc4e38375a7edf03091bae4fc861880510867903487eec83f05e6ba",
}
CASE_INPUTS = {
    "D-F": (
        "cases/bread_development/task.md",
        "cases/bread_development/source_claims.json",
        "cases/bread_development/source_manifest.json",
        "cases/bread_norway/source_lca.pdf",
        "cases/bread_norway/source_survey.pdf",
        "cases/bread_norway/survey_table1.json",
    ),
    "D-E": (
        "cases/building_energy/task.md",
        "cases/building_energy/source_manifest.json",
        "cases/building_energy/sample_first_complete_week.csv",
    ),
}
MODES = {"A": "sequential", "B": "graph", "C": "risk"}
ARM_TEXT = {
    "A": "Use the original sequential kernel: phase order and local gates. Preserve its actual invalidation behavior.",
    "B": "Use the original dependency graph: current dependency closure, descendant invalidation and explicit review.",
    "C": "Use the original risk portfolio: priority and potential waves. This adapter executes calls serially; do not claim actual parallel exploration.",
}
COMMON = """Use only the public task and listed sources. Original D-F/D-E data are shared by all alternatives.
Keep factual evidence, inference, assumptions and normative proposals distinct.
Never approve norms or claim a human signature, real intervention, causal benefit, provider identity, invoice or final Q.
The sealed tool receives {"request":"JSON object"}. Its operations are init(nodes), status, revise(id,status,reason), review(id), advance(phase), plan(budget), read(path,offset,length), write(path,offset,content).
State is owned by the kernel. init requires 4–64 nodes, all initially pending, with an engineering requirement depending on a normative node. Write appends UTF-8 deliverable chunks at exact byte offsets. Read only enumerated UTF-8 inputs.
PDF passage extraction and executing delivered analysis.py are pending separate isolated capabilities; state these limits.
No approve or analyze operation is available. C potential waves are not executed parallel agents.
All calls and roles share the declared tokens, active time, request, tool and cost ceilings; a handoff does not replenish them.
"""
TASK_CONTRACT = """Read case/task.md and follow its original deliverables and source constraints.
Use the fixed alternative and original core through the sealed tool. Normative nodes start pending and cannot be approved by this adapter.
This is an unsealed development preparation. It does not authorize paid calls, reserved inputs or field work and cannot count as a completed formal cell.
"""
ANALYSIS_COMMON = COMMON.replace(
    "PDF passage extraction and executing delivered analysis.py are pending separate isolated capabilities; state these limits.\n",
    "Read the shared full PDF texts and every page listed in text_extract_manifest.json. Original source manifests remain unchanged.\n"
    "Use development_analysis with the current analysis.py SHA256. It reads case/inputs/work and cannot write them. "
    "The host publishes metrics.json only after strict finite JSON object validation; validate source passages and calculations independently.\n"
    "The fixed analysis argv is [analysis.py, case_dir]. This is a NEW common D-E adaptation; its historical task did not prescribe argv or JSON. "
    "Use standard library only, no subprocess or network. Emit only a JSON object to stdout. "
    "Participant errors and invalid JSON consume one call and return feedback; revise your own code before retrying.\n",
).replace("Write appends UTF-8 deliverable chunks at exact byte offsets.",
          "Write appends UTF-8 deliverable chunks at exact byte offsets. replace(path,expected_sha256,content) replaces an allowlisted deliverable with a bounded UTF-8 chunk after a digest check; append further chunks as needed.")


class PreparationError(ValueError):
    pass


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read(path: Path, cap: int = 16 * 1024 * 1024) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > cap:
            raise PreparationError("bounded regular input required")
        pieces: list[bytes] = []
        size = 0
        while piece := os.read(fd, 65536):
            size += len(piece)
            if size > cap:
                raise PreparationError("input exceeded byte cap")
            pieces.append(piece)
        after = os.fstat(fd)
        named = os.stat(path, follow_symlinks=False)
        keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, key) != getattr(after, key)
               or getattr(after, key) != getattr(named, key) for key in keys):
            raise PreparationError("input changed during read")
        return b"".join(pieces)
    finally:
        os.close(fd)


def _private_parent(path: Path) -> None:
    if not path.is_absolute() or any(part in (".", "..") for part in path.parts):
        raise PreparationError("output must be absolute without dot components")
    current = Path(path.anchor)
    for part in path.parent.parts[1:]:
        current /= part
        info = os.stat(current, follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode):
            raise PreparationError("output parent chain must contain real directories")
    info = os.stat(path.parent, follow_symlinks=False)
    if info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise PreparationError("output parent must be owned and not group/other writable")


def _pinned_source(source: str) -> bytes:
    raw = _read(ROOT / source)
    if _sha(raw) != SOURCE_PINS[source]:
        raise PreparationError(f"public source differs from prospective pin: {source}")
    return raw


def _new_file(path: Path, raw: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _capsules(destination: Path, *, analysis: bool = False) -> tuple[list[dict], dict[str, str], list[dict]]:
    cases, paths, source_pins = [], {}, []
    extracted = build_text_inputs(destination / "text_extracts") if analysis else None
    for case_id, sources in CASE_INPUTS.items():
        capsule = destination / case_id
        capsule.mkdir(mode=0o700)
        files = []
        for source in sources:
            raw = _pinned_source(source)
            name = Path(source).name
            _new_file(capsule / name, raw)
            record = {"path": name, "sha256": _sha(raw), "bytes": len(raw)}
            files.append(record)
            source_pins.append({**record, "path": source})
        if case_id == "D-F" and extracted is not None:
            for record in extracted["files"]:
                raw = _read(destination / "text_extracts" / record["path"])
                if _sha(raw) != record["sha256"] or len(raw) != record["bytes"]:
                    raise PreparationError("common extracted input changed before packaging")
                _new_file(capsule / record["path"], raw)
                files.append(dict(record))
        deliverables = ["analysis.py", "report.md"]
        if case_id == "D-F":
            deliverables.insert(1, "sources.json")
        manifest = {"schema": 1, "classification": "executor_visible_case_package",
                    "case_id": case_id, "task_file": "task.md", "files": files,
                    "deliverables": deliverables}
        _new_file(capsule / "case.json", _bytes(manifest))
        package = destination / f"{case_id}.zip"
        pack_package(capsule, package)
        cases.append({"case_id": case_id, "package_sha256": _sha(_read(package))})
        paths[case_id] = str(package)
    return cases, paths, source_pins


def build_round(destination: Path, configuration: dict[str, Any]) -> dict[str, Any]:
    """Create public byte-bound assets and a round-one schedule, without execution."""
    required = {"schema", "seed", "model", "price_profile", "per_run_limits",
                "max_model_requests", "cost_limit_micro_usd"}
    analysis = type(configuration) is dict and configuration.get("schema") == 2
    if (type(configuration) is not dict
            or set(configuration) != required | ({"analysis_profile"} if analysis else set())
            or type(configuration["schema"]) is not int or configuration["schema"] not in {1, 2}
            or analysis and configuration["analysis_profile"] != "read_only_v1"
            or type(configuration["model"]) is not dict):
        raise PreparationError("preparation configuration fields are invalid")
    profile = _price_profile(configuration["price_profile"])
    model = dict(configuration["model"])
    if model.get("model_id") != profile["model"]:
        raise PreparationError("model and declared price profile differ")
    if "price_profile_sha256" in model:
        raise PreparationError("price digest is derived, not supplied in model configuration")
    model["price_profile_sha256"] = _sha(ledger_canonical(profile))
    for source in SOURCE_PINS:
        _pinned_source(source)
    core = _pinned_source("prototypes/core.py")
    protocol = _pinned_source("docs/protocolo_experimental.md")
    # Validate metadata before creating any output; content hashes are replaced below.
    prospective = {
        "schema": MANIFEST_SCHEMA_V2 if analysis else MANIFEST_SCHEMA, "round": 1,
        "seed": configuration["seed"], "protocol_sha256": _sha(protocol),
        "cases": [{"case_id": case_id, "package_sha256": "0" * 64}
                  for case_id in CASE_INPUTS],
        "inputs": {**{role: {"sha256": "0" * 64}
                      for role in ("task_contract", "common_prompt", "tool_policy")},
                   "arm_prompts": {arm: {"sha256": "0" * 64} for arm in MODES}},
        "alternatives": [{"alternative": arm, "mode": mode, "core_sha256": _sha(core)}
                         for arm, mode in MODES.items()],
        "model": model, "per_run_limits": configuration["per_run_limits"],
        "max_model_requests": configuration["max_model_requests"],
        "cost_limit_micro_usd": configuration["cost_limit_micro_usd"],
    }
    compile_schedule(prospective)
    destination = Path(destination)
    _private_parent(destination)
    destination.mkdir(mode=0o700)
    assets = destination / "assets"
    assets.mkdir(mode=0o700)
    prospective["cases"], case_paths, pins = _capsules(assets, analysis=analysis)
    tool = assets / "method_tool"
    build_tool(tool, core_path=ROOT / "prototypes/core.py")
    if _read(ROOT / "prototypes/core.py") != core:
        raise PreparationError("core changed while building tool")
    tool_sha = _sha(_read(tool))
    texts = {"task_contract": TASK_CONTRACT.encode(),
             "common_prompt": (ANALYSIS_COMMON if analysis else COMMON).encode()}
    input_paths: dict[str, Any] = {}
    for role, raw in texts.items():
        _new_file(assets / role, raw)
        prospective["inputs"][role] = {"sha256": _sha(raw)}
        input_paths[role] = str(assets / role)
    for arm, mode in MODES.items():
        raw = _bytes({"alternative": arm, "mode": mode, "instructions": ARM_TEXT[arm]})
        _new_file(assets / f"prompt_{arm}", raw)
        prospective["inputs"]["arm_prompts"][arm] = {"sha256": _sha(raw)}
    input_paths["arm_prompts"] = {arm: str(assets / f"prompt_{arm}") for arm in MODES}
    # The policy field is a declaration, not an authenticated runtime-image receipt.
    runtime = {"classification": "unattested_development_runtime_declaration",
               "python_version": sys.version.split()[0], "sandbox": "existing_staged_tool_session"}
    policy = {"schema": 1, "classification": "common_tool_policy_development_unenforced",
              "runtime_image_sha256": _sha(_bytes(runtime)), "network": "disabled",
              "read_roots": ["/case"], "write_roots": ["/work"],
              "generic_tools": [{"id": "method", "version": "development-original-core-v1",
                                 "executable_sha256": tool_sha}],
              "limits": configuration["per_run_limits"]}
    if analysis:
        analyzer = build_analysis_tool(assets / "analysis_tool")
        policy["schema"] = 2
        policy["generic_tools"][0]["profile"] = "workspace"
        policy["generic_tools"].append({
            "id": "analysis", "version": "development-readonly-analysis-v1",
            "executable_sha256": analyzer["sha256"], "profile": "analysis_readonly",
        })
    raw_policy = _bytes(policy)
    _new_file(assets / "tool_policy", raw_policy)
    prospective["inputs"]["tool_policy"] = {"sha256": _sha(raw_policy)}
    input_paths["tool_policy"] = str(assets / "tool_policy")
    schedule = compile_schedule(prospective)
    asset_map = {"schema": 1, "schedule_sha256": schedule["schedule_sha256"],
                 "input_sha256": schedule["input_sha256"],
                 "cases": case_paths, "inputs": input_paths}
    _new_file(destination / "schedule.json", _bytes(schedule))
    _new_file(destination / "assets.json", _bytes(asset_map))
    _new_file(destination / "price_profile.json", ledger_canonical(profile))
    metadata = {"schema": 1, "classification": CLASSIFICATION,
                "schedule_sha256": schedule["schedule_sha256"], "prepared_cell_count": 12,
                "formal_cells_executed": 0, "real_provider_requests": 0,
                "execution_authorized": False, "source_pins": pins,
                "source_base": SOURCE_BASE, "prospective_source_sha256": SOURCE_PINS,
                "tool_sha256": tool_sha, "core_sha256": _sha(core),
                "runtime_declaration": runtime,
                "pending": ["isolated_participant_analysis", "shared_pdf_passage_extraction",
                            "actual_C_parallel_executor", "real_round_one_results",
                            "round_two_adaptation_and_freeze", "provider_authorization_and_telemetry"]}
    if analysis:
        metadata.update(analysis_profile="read_only_v1", analysis_tool_sha256=analyzer["sha256"],
                        common_text_derivation=_sha(_read(assets / "text_extracts/text_extract_manifest.json")))
        metadata["pending"] = metadata["pending"][2:]
    _new_file(destination / "preparation.json", _bytes(metadata))
    preflight(schedule, asset_map)
    return metadata


def prepare_cell(bundle: Path, run_id: str, destination: Path) -> dict[str, Any]:
    """Create one staged/managed attempt with the scheduled price and global caps."""
    bundle, destination = Path(bundle), Path(destination)
    schedule = validate_schedule(_read_schedule(str(bundle / "schedule.json")))
    profile = _price_profile(_read_schedule(str(bundle / "price_profile.json")))
    model = schedule["manifest"]["model"]
    if (profile["model"] != model["model_id"]
            or _sha(ledger_canonical(profile)) != model["price_profile_sha256"]):
        raise PreparationError("price profile differs from frozen development schedule")
    run = next((item for item in schedule["runs"] if item["run_id"] == run_id), None)
    if run is None:
        raise PreparationError("run absent from development schedule")
    assets = _read_schedule(str(bundle / "assets.json"))
    # Ensure all scheduled public assets match before creating the attempt.
    preflight(schedule, assets)
    tool = bundle / "assets" / "method_tool"
    policy = _read_schedule(assets["inputs"]["tool_policy"])
    analysis = schedule["schema"] == SCHEDULE_SCHEMA_V2
    if policy.get("schema") != (2 if analysis else 1):
        raise PreparationError("tool policy schema differs from development schedule version")
    method_entry = next((entry for entry in policy["generic_tools"] if entry["id"] == "method"), None)
    if method_entry is None or _sha(_read(tool)) != method_entry["executable_sha256"]:
        raise PreparationError("method tool differs from frozen policy")
    if analysis:
        analyzer = bundle / "assets/analysis_tool"
        entry = next((entry for entry in policy["generic_tools"] if entry["id"] == "analysis"), None)
        if (policy.get("schema") != 2 or entry is None or entry.get("profile") != "analysis_readonly"
                or method_entry.get("profile") != "workspace"
                or _sha(_read(analyzer)) != entry["executable_sha256"]):
            raise PreparationError("analysis tool or profile differs from frozen policy")
    _private_parent(destination)
    destination.mkdir(mode=0o700)
    release, stage, managed = (destination / name for name in ("release", "stage", "managed"))
    preflight(schedule, assets, run_id=run_id, output_dir=release,
              development_unsequenced=True)
    stage_released_run(schedule, release, stage, development_unsequenced=True)
    instructions = "\n".join(
        _read(stage / "inputs" / role).decode("utf-8")
        for role in ("task_contract", "common_prompt", "arm_prompt"))
    limits = schedule["per_run_limits"]
    max_output = min(2048, max(1, limits["measured_tokens"] // 8))
    plan = {"schema": 2, "run_id": run_id, "model": run["model_id"],
            "service_tier": "default", "instructions": instructions,
            "segments": [
                {"role": "leader", "user": "Read task.md and listed sources; propose nodes and use the fixed kernel. Record missing capabilities honestly.",
                 "max_output_tokens": max_output, "share_from": []},
                {"role": "leader", "user": "Deliver allowlisted files in chunks if possible. Summarize actual method state, evidence and unresolved approvals/capabilities; never declare this a completed formal cell.",
                 "max_output_tokens": max_output, "share_from": [1]}],
            "functions": [{"type": "function", "name": "development_method",
                           "description": ANALYSIS_COMMON if analysis else COMMON, "parameters": {
                               "type": "object", "properties": {"request": {"type": "string"}},
                               "required": ["request"], "additionalProperties": False},
                           "strict": True, "tool_id": "method", "executable": str(tool)}],
            "max_model_requests": schedule["max_model_requests"],
            "max_tool_calls": limits["tool_calls"], "tool_wall_seconds": 4}
    if analysis:
        plan["functions"].append({
            "type": "function", "name": "development_analysis",
            "description": "Execute fixed work/analysis.py with [analysis.py,case_dir], read only; host validates JSON and publishes metrics. No normative approval.",
            "parameters": {"type": "object", "properties": {"script_sha256": {"type": "string"}},
                           "required": ["script_sha256"], "additionalProperties": False},
            "strict": True, "tool_id": "analysis", "executable": str(analyzer),
        })
    if run["effort_provider_value"] is not None:
        plan["reasoning"] = {"effort": run["effort_provider_value"]}
    result = prepare_team(
        managed, bundle / "schedule.json", stage, plan,
        limit_tokens=limits["measured_tokens"], active_limit_seconds=limits["active_seconds"],
        cost_limit_micro_usd=schedule["cost_limit_micro_usd"], price_profile=profile)
    _new_file(destination / "preparation.json", _bytes({
        "schema": 1, "classification": CLASSIFICATION, "run_id": run_id,
        "schedule_sha256": schedule["schedule_sha256"], "formal_cell_executed": False,
        "ordering": "development_unsequenced_mechanical_preparation",
        "state": result["state"], "execution_authorized": False}))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("configuration", type=Path)
    build.add_argument("destination", type=Path)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("bundle", type=Path)
    prepare.add_argument("run_id")
    prepare.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build_round(args.destination, _read_schedule(str(args.configuration)))
        else:
            result = prepare_cell(args.bundle, args.run_id, args.destination)
    except (ValueError, OSError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
