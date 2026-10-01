"""Build and verify public coordinated DEV R1 preparations, without running cells."""

from __future__ import annotations

import argparse
import ast
import base64
import copy
import io
import json
import os
import re
import stat
import sys
import zipfile
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import development_analysis_inputs as text_inputs  # noqa: E402
import development_analysis_tool as analyzer  # noqa: E402
import development_method_tool as method  # noqa: E402
import plan_coordinated_development as planner  # noqa: E402
import prepare_development_round as original  # noqa: E402
from case_package import _parse_json, inspect_package  # noqa: E402
from managed_token_ledger import _canonical as price_bytes, _price_profile  # noqa: E402
from plan_development_round import MANIFEST_SCHEMA_V2  # noqa: E402

ROOT = SCRIPTS.parent
CLASSIFICATION = "coordinated_development_bundle_preparation_unsealed"
CONFIG_KEYS = {"schema", "seed", "model", "price_profile", "per_run_limits",
               "max_model_requests", "cost_limit_micro_usd", "provider_route"}
CONTRACT_NAMES = ("delivery_contract.json", "rubric.json", "coordination_prompt.md")
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_BUNDLE_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 512


class CoordinatedPreparationError(ValueError):
    """The preparation's public bytes, contracts or paths cannot be verified."""


def _sha(raw: bytes) -> str:
    import hashlib
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return original._bytes(value)


def _chain(path: Path, *, directory: bool = False, new: bool = False) -> Path:
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise CoordinatedPreparationError("paths must be absolute without parent traversal")
    current = Path(path.anchor)
    parts = path.parts[1:] if directory and not new else path.parent.parts[1:]
    for part in parts:
        current /= part
        if not stat.S_ISDIR(current.lstat().st_mode):
            raise CoordinatedPreparationError("path chain must contain real directories, without symlinks")
    if new:
        try:
            path.lstat()
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("bundle destination must be new")
    return path


def _read(path: Path, cap: int = MAX_FILE_BYTES) -> bytes:
    path = _chain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or not 0 <= before.st_size <= cap):
            raise CoordinatedPreparationError("bounded single-link regular file required")
        pieces, size = [], 0
        while piece := os.read(fd, min(65536, cap + 1 - size)):
            size += len(piece)
            if size > cap:
                raise CoordinatedPreparationError("file exceeds byte limit")
            pieces.append(piece)
        after, named = os.fstat(fd), path.lstat()
        def identity(item):
            return (item.st_dev, item.st_ino, item.st_mode, item.st_nlink,
                    item.st_size, item.st_mtime_ns, item.st_ctime_ns)
        if identity(before) != identity(after) or identity(after) != identity(named):
            raise CoordinatedPreparationError("file changed during read")
        return b"".join(pieces)
    finally:
        os.close(fd)


def _json(path: Path) -> Any:
    return _parse_json(_read(path, 1024 * 1024))


def _contracts(contract_dir: Path) -> dict[str, bytes]:
    from development_delivery_contract import validate_delivery_contract, validate_rubric

    contract_dir = _chain(contract_dir, directory=True)
    if {entry.name for entry in contract_dir.iterdir()} != set(CONTRACT_NAMES):
        raise CoordinatedPreparationError("contract directory must contain exactly the three public contracts")
    files = {name: _read(contract_dir / name, 1024 * 1024) for name in CONTRACT_NAMES}
    validate_delivery_contract(_parse_json(files["delivery_contract.json"]))
    validate_rubric(_parse_json(files["rubric.json"]))
    prompt = files["coordination_prompt.md"].decode("utf-8")
    if not prompt.strip() or len(files["coordination_prompt.md"]) > 64 * 1024 or "\x00" in prompt:
        raise CoordinatedPreparationError("coordination prompt must be bounded nonempty UTF-8 text")
    return files


def _source_records(contract_dir: Path) -> list[dict]:
    # Fixed original identities and archived derivations are checked before any mkdir.
    paths = set()
    for name in original.SOURCE_PINS:
        original._pinned_source(name)
        paths.add(ROOT / name)
    _, _, _, text_pins = text_inputs._sources()
    paths.update(Path(name) if Path(name).is_absolute() else ROOT / name for name in text_pins)
    pending = ["prepare_coordinated_development", "plan_coordinated_development",
               "development_delivery_contract"]
    seen = set()
    captured = {}
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        path = SCRIPTS / f"{name}.py"
        raw = _read(path)
        captured[path] = raw
        seen.add(name)
        paths.add(path)
        for node in ast.walk(ast.parse(raw)):
            names = ([item.name.split(".")[0] for item in node.names]
                     if isinstance(node, ast.Import) else
                     [node.module.split(".")[0]]
                     if isinstance(node, ast.ImportFrom) and node.module else [])
            pending.extend(item for item in names if (SCRIPTS / f"{item}.py").is_file())
    paths.update(contract_dir / name for name in CONTRACT_NAMES)
    rows = []
    for path in sorted(paths):
        raw = _read(path)
        if path in captured and raw != captured[path]:
            raise CoordinatedPreparationError("Python source changed during closure capture")
        rows.append({"path": str(path), "bytes": len(raw), "sha256": _sha(raw)})
    return rows


def _manifest(configuration: dict, contracts: dict[str, bytes], freeze: str,
              *, cases: list[dict] | None = None, refs: dict | None = None,
              runtime_sha: str = "0" * 64) -> dict:
    if (type(configuration) is not dict or set(configuration) != CONFIG_KEYS
            or type(configuration["schema"]) is not int or configuration["schema"] != 1):
        raise CoordinatedPreparationError("configuration must have the exact coordinated schema-1 fields")
    if type(freeze) is not str or re.fullmatch(r"[0-9a-f]{64}", freeze) is None:
        raise CoordinatedPreparationError("source freeze reference must be lowercase SHA-256")
    model = configuration["model"]
    if type(model) is not dict or set(model) != {
        "model_id", "version", "family", "tier", "effort", "effort_provider_value"
    }:
        raise CoordinatedPreparationError("model must contain the six declared model fields, without a price digest")
    price = _price_profile(configuration["price_profile"])
    if price["model"] != model["model_id"]:
        raise CoordinatedPreparationError("model and price profile differ")
    base = {"schema": MANIFEST_SCHEMA_V2, "round": 1, "seed": configuration["seed"],
            "protocol_sha256": original.SOURCE_PINS["docs/protocolo_experimental.md"],
            "cases": cases or [{"case_id": key, "package_sha256": "0" * 64} for key in original.CASE_INPUTS],
            "inputs": refs or {**{key: {"sha256": "0" * 64} for key in ("task_contract", "common_prompt", "tool_policy")},
                                "arm_prompts": {arm: {"sha256": "0" * 64} for arm in original.MODES}},
            "alternatives": [{"alternative": arm, "mode": mode,
                              "core_sha256": original.SOURCE_PINS["prototypes/core.py"]}
                             for arm, mode in original.MODES.items()],
            "model": {**model, "price_profile_sha256": _sha(price_bytes(price))},
            **{key: configuration[key] for key in ("per_run_limits", "max_model_requests", "cost_limit_micro_usd")}}
    return planner.validate_manifest({
        "schema": planner.MANIFEST_SCHEMA, "base": base, "coordination": copy.deepcopy(planner.COORDINATION),
        "shared_contract": {key: {"sha256": _sha(contracts[name])} for key, name in zip(
            ("delivery", "rubric", "coordination_prompt"), CONTRACT_NAMES, strict=True)},
        "runtime_policy": {"sha256": runtime_sha}, "provider_route": configuration["provider_route"],
        "source_freeze_sha256": freeze})


def _common_assets(configuration: dict, contracts: dict[str, bytes], interpreter: str) -> dict[str, bytes]:
    core_raw = original._pinned_source("prototypes/core.py")
    method_raw = (f"#!{interpreter}\n" + method._RUNTIME.replace(
        "__EMBEDDED_CORE_B64__", base64.b64encode(core_raw).decode("ascii")).replace(
        "__EMBEDDED_CORE_SHA256__", _sha(core_raw))).encode()
    analysis_raw = (f"#!{interpreter}\n" + analyzer._RUNTIME).encode()
    common = (
        "Use only the original public task, listed sources and common PDF passages. "
        "Keep facts, inferences, assumptions and normative proposals distinct. "
        "The leader starts with empty work and initializes 4–64 pending nodes through the fixed original core. "
        "Include an engineering requirement depending on a pending normative node. "
        "All alternatives share leader, worker-1, worker-2 and reviewer, with at most two concurrent worker requests. "
        "Workers have private contexts and disjoint ownership; share only public artifacts. "
        "The reviewer runs after workers and receives no private reasoning or tools. "
        "Use fixed method read/write/replace CAS/status/revise/review/advance/plan as supported by the selected mode, "
        "and isolated development_analysis with current analysis.py SHA. "
        "Analysis uses [analysis.py, case_dir], standard library only, no subprocess/network, and emits a finite JSON object. "
        "Participant failures consume calls; repair your own code using digest-checked replacement. "
        "Do not approve norms, fabricate signatures, causal efficacy, provider identity, invoices or final Q. "
        "Every role, bootstrap, tool and review shares one parent token/request/tool/cost/active-time budget without reset. "
        "This bundle declares prospective coordination; execution adapters remain pending. "
        "Original prototype phases and invalidation semantics remain distinct.\n")
    task = ("Follow the original case/task.md deliverables and source restrictions. "
            "The public delivery contract records the common D113 argv/JSON adaptation. "
            "Keep normative decisions pending and dependent engineering requirements explicit. "
            "Deliver report.md, analysis.py and D-F sources.json; metrics.json is host generated by isolated analysis. "
            "Preparation and structural verification do not establish quality, scientific truth or real impact.\n")
    instructions = {
        "A": "Use original sequential phase order and local gates. Preserve stage-local invalidation and the unavailable review operation.",
        "B": "Use original dependency closure, ordered phases, descendant invalidation and explicit stale-node review.",
        "C": "Use original risk priorities and dependency-ready potential waves, with original risk-mode advance semantics. Actual concurrency must be demonstrated by the future parent runtime."}
    limits = configuration["per_run_limits"]
    policy = {"schema": 2, "classification": "common_coordinated_development_tool_policy_declaration",
              "network": "disabled", "read_roots": ["/case", "/inputs", "/work"], "write_roots": ["/work"],
              "generic_tools": [{"id": "method", "version": "development-original-core-v1",
                                 "executable_sha256": _sha(method_raw), "profile": "workspace"},
                                {"id": "analysis", "version": "development-readonly-analysis-v1",
                                 "executable_sha256": _sha(analysis_raw), "profile": "analysis_readonly"}],
              "limits": limits}
    runtime = {"schema": 1, "classification": "prospective_coordinated_parent_policy_declaration",
               "profile": planner.RUNTIME_PROFILE, "coordination": copy.deepcopy(planner.COORDINATION),
               "model": configuration["model"], "provider_route": planner.validate_provider_route(configuration["provider_route"]),
               "per_run_limits": limits, "max_model_requests": configuration["max_model_requests"],
               "cost_limit_micro_usd": configuration["cost_limit_micro_usd"],
               "normative_policy": "pending_no_model_approval", "participant_analysis": "isolated_readonly",
               "pending": ["A_B_four_role_parent_adapters", "C_schedule_contract_binding", "authorized_routes_and_provider_telemetry"]}
    return {**contracts, "method_tool": method_raw, "analysis_tool": analysis_raw,
            "task_contract": task.encode(), "common_prompt": common.encode(),
            "tool_policy": _canonical(policy), "runtime_policy.json": _canonical(runtime),
            **{f"prompt_{arm}": _canonical({"alternative": arm, "mode": mode,
                                            "instructions": instructions[arm]}) for arm, mode in original.MODES.items()}}


def _inventory(bundle: Path) -> dict:
    _chain(bundle, directory=True)
    if stat.S_IMODE(bundle.lstat().st_mode) != 0o700:
        raise CoordinatedPreparationError("bundle root must be private mode 0700")
    files, directories, size = [], [], 0
    pending = [bundle]
    while pending:
        directory = pending.pop()
        for path in sorted(directory.iterdir()):
            relative = path.relative_to(bundle).as_posix()
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                if stat.S_IMODE(info.st_mode) != 0o700:
                    raise CoordinatedPreparationError("bundle directory must be private mode 0700")
                directories.append(relative)
                pending.append(path)
            elif stat.S_ISREG(info.st_mode):
                raw = _read(path)
                if relative == "bundle.json":
                    continue
                size += len(raw)
                files.append({"path": relative, "bytes": len(raw), "sha256": _sha(raw),
                              "mode": stat.S_IMODE(info.st_mode)})
            else:
                raise CoordinatedPreparationError("bundle contains a symlink or nonregular entry")
            if len(files) + len(directories) > MAX_ENTRIES or size > MAX_BUNDLE_BYTES:
                raise CoordinatedPreparationError("bundle inventory exceeds resource bounds")
    return {"directories": sorted(directories), "files": sorted(files, key=lambda row: row["path"])}


def _capsule_expected() -> tuple[dict[str, dict[str, bytes]], dict[str, bytes]]:
    _, texts, _, _ = text_inputs._sources()
    extraction = text_inputs.expected_bundle(texts)
    capsules = {}
    for case_id, source_names in original.CASE_INPUTS.items():
        files = {Path(name).name: original._pinned_source(name) for name in source_names}
        if case_id == "D-F":
            files.update(extraction)
        deliverables = ["analysis.py", "report.md"]
        if case_id == "D-F":
            deliverables.insert(1, "sources.json")
        manifest = {"schema": 1, "classification": "executor_visible_case_package", "case_id": case_id,
                    "task_file": "task.md", "files": [{"path": name, "bytes": len(raw), "sha256": _sha(raw)}
                                                         for name, raw in files.items()], "deliverables": deliverables}
        capsules[case_id] = {**files, "case.json": _canonical(manifest)}
    return capsules, extraction


def build_coordinated_round(destination: Path, configuration: dict, contract_dir: Path,
                            source_freeze_sha256: str) -> dict:
    destination, contract_dir = Path(destination), Path(contract_dir)
    contracts = _contracts(contract_dir)
    _manifest(configuration, contracts, source_freeze_sha256)
    destination = _chain(destination, new=True)
    original._private_parent(destination)
    physical = destination.resolve()
    for source in (ROOT.resolve(), contract_dir.resolve()):
        if physical == source or physical in source.parents or source in physical.parents:
            raise CoordinatedPreparationError("bundle must not overlap source checkout or public contracts")
    sources = _source_records(contract_dir)
    interpreter = sys.executable
    common = _common_assets(configuration, contracts, interpreter)
    if sources != _source_records(contract_dir) or contracts != _contracts(contract_dir):
        raise CoordinatedPreparationError("sources or contracts changed during preparation preflight")
    destination.mkdir(mode=0o700)
    assets = destination / "assets"
    assets.mkdir(mode=0o700)
    cases, _, _ = original._capsules(assets, analysis=True)
    method.build_tool(assets / "method_tool", core_path=ROOT / "prototypes/core.py")
    analyzer.build_analysis_tool(assets / "analysis_tool")
    for name, raw in common.items():
        if name not in {"method_tool", "analysis_tool"}:
            original._new_file(assets / name, raw)
        elif _read(assets / name) != raw:
            raise CoordinatedPreparationError("tool builder bytes differ from fixed source")
    refs = {**{name: {"sha256": _sha(common[name])} for name in ("task_contract", "common_prompt", "tool_policy")},
            "arm_prompts": {arm: {"sha256": _sha(common[f"prompt_{arm}"])} for arm in original.MODES}}
    manifest = _manifest(configuration, contracts, source_freeze_sha256, cases=cases, refs=refs,
                         runtime_sha=_sha(common["runtime_policy.json"]))
    schedule = planner.compile_schedule(manifest)
    asset_map = {"schema": 1, "schedule_sha256": schedule["schedule_sha256"],
                 "paths": {**{f"case:{key}:package": f"assets/{key}.zip" for key in original.CASE_INPUTS},
                           **{name: f"assets/{name}" for name in common}}}
    for name, raw in {"configuration.json": _canonical(configuration), "schedule.json": _canonical(schedule),
                      "assets.json": _canonical(asset_map),
                      "price_profile.json": price_bytes(_price_profile(configuration["price_profile"]))}.items():
        original._new_file(destination / name, raw)
    if sources != _source_records(contract_dir) or contracts != _contracts(contract_dir):
        raise CoordinatedPreparationError("source or contract changed after bundle creation")
    receipt = {"schema": 1, "classification": CLASSIFICATION, "contract_dir": str(contract_dir),
               "source_freeze_sha256": source_freeze_sha256, "tool_interpreter": interpreter,
               "source_records": sources, "inventory": _inventory(destination)}
    original._new_file(destination / "bundle.json", _canonical(receipt))
    return verify_coordinated_bundle(destination)


def verify_coordinated_bundle(bundle: Path) -> dict:
    bundle = _chain(Path(bundle), directory=True)
    receipt = _json(bundle / "bundle.json")
    if (type(receipt) is not dict or set(receipt) != {"schema", "classification", "contract_dir",
            "source_freeze_sha256", "tool_interpreter", "source_records", "inventory"}
            or type(receipt["schema"]) is not int or receipt["schema"] != 1
            or receipt["classification"] != CLASSIFICATION
            or type(receipt["tool_interpreter"]) is not str
            or not Path(receipt["tool_interpreter"]).is_absolute()
            or any(ord(char) < 32 for char in receipt["tool_interpreter"])):
        raise CoordinatedPreparationError("bundle receipt has invalid or unsupported fields")
    contracts = _contracts(Path(receipt["contract_dir"]))
    if receipt["source_records"] != _source_records(Path(receipt["contract_dir"])):
        raise CoordinatedPreparationError("original sources or Python closure differ from captured bytes")
    inventory = _inventory(bundle)
    if _canonical(inventory) != _canonical(receipt["inventory"]):
        raise CoordinatedPreparationError("bundle inventory differs: missing, extra or altered entry")
    configuration = _json(bundle / "configuration.json")
    _manifest(configuration, contracts, receipt["source_freeze_sha256"])
    common = _common_assets(configuration, contracts, receipt["tool_interpreter"])
    capsules, extraction = _capsule_expected()
    expected_files = {f"assets/{name}": raw for name, raw in common.items()}
    expected_files.update({f"assets/text_extracts/{name}": raw for name, raw in extraction.items()})
    for case_id, files in capsules.items():
        expected_files.update({f"assets/{case_id}/{name}": raw for name, raw in files.items()})
        archive = _read(bundle / "assets" / f"{case_id}.zip")
        inspected = inspect_package(bundle / "assets" / f"{case_id}.zip", expected_case_id=case_id)
        if inspected["case_id"] != case_id:
            raise CoordinatedPreparationError("ZIP case identity differs")
        with zipfile.ZipFile(io.BytesIO(archive)) as packed:
            if set(packed.namelist()) != set(files) or any(packed.read(name) != raw for name, raw in files.items()):
                raise CoordinatedPreparationError("ZIP contents differ from complete original capsule")
    refs = {**{name: {"sha256": _sha(common[name])} for name in ("task_contract", "common_prompt", "tool_policy")},
            "arm_prompts": {arm: {"sha256": _sha(common[f"prompt_{arm}"])} for arm in original.MODES}}
    cases = [{"case_id": key, "package_sha256": _sha(_read(bundle / "assets" / f"{key}.zip"))}
             for key in original.CASE_INPUTS]
    manifest = _manifest(configuration, contracts, receipt["source_freeze_sha256"], cases=cases, refs=refs,
                         runtime_sha=_sha(common["runtime_policy.json"]))
    schedule = planner.validate_schedule(_json(bundle / "schedule.json"))
    if _canonical(schedule) != _canonical(planner.compile_schedule(manifest)):
        raise CoordinatedPreparationError("schedule differs from actual contracts, sources, model or caps")
    asset_map = {"schema": 1, "schedule_sha256": schedule["schedule_sha256"],
                 "paths": {**{f"case:{key}:package": f"assets/{key}.zip" for key in original.CASE_INPUTS},
                           **{name: f"assets/{name}" for name in common}}}
    expected_files.update({"configuration.json": _canonical(configuration), "schedule.json": _canonical(schedule),
                          "assets.json": _canonical(asset_map),
                          "price_profile.json": price_bytes(_price_profile(configuration["price_profile"]))})
    names = set(expected_files) | {f"assets/{key}.zip" for key in original.CASE_INPUTS}
    expected_dirs = {"assets", "assets/D-F", "assets/D-E", "assets/text_extracts"}
    if ({row["path"] for row in inventory["files"]} != names
            or set(inventory["directories"]) != expected_dirs):
        raise CoordinatedPreparationError("inventory names differ from the closed bundle layout")
    for name, raw in expected_files.items():
        if _read(bundle / name) != raw:
            raise CoordinatedPreparationError(f"bundle content differs from its source contract: {name}")
    if any(row["mode"] != (0o500 if row["path"] in {"assets/method_tool", "assets/analysis_tool"} else 0o600)
           for row in inventory["files"]):
        raise CoordinatedPreparationError("bundle file mode differs from private fixed layout")
    if _read(bundle / "bundle.json") != _canonical(receipt):
        raise CoordinatedPreparationError("bundle receipt bytes are not canonical")
    if stat.S_IMODE((bundle / "bundle.json").lstat().st_mode) != 0o600:
        raise CoordinatedPreparationError("bundle receipt must be private mode 0600")
    if (inventory != _inventory(bundle)
            or receipt["source_records"] != _source_records(Path(receipt["contract_dir"]))):
        raise CoordinatedPreparationError("bundle or original sources changed during verification")
    return {"classification": CLASSIFICATION, "scope": "preparation_and_byte_verification_only",
            "bundle": str(bundle), "bundle_sha256": _sha(_read(bundle / "bundle.json")),
            "schedule_sha256": schedule["schedule_sha256"], "prepared_cell_count": 12,
            "verified_files": len(inventory["files"]) + 1, "formal_cells_executed": 0,
            "pending": ["coordinated_A_B_C_runtime_binding", "actual_round_one_runs", "provider_and_evaluation_evidence"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    for name in ("destination", "configuration", "contract-dir"):
        build.add_argument("--" + name, type=Path, required=True)
    build.add_argument("--source-freeze-sha256", required=True)
    sub.add_parser("verify").add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = (build_coordinated_round(args.destination, _json(args.configuration), args.contract_dir,
                                          args.source_freeze_sha256) if args.command == "build"
                  else verify_coordinated_bundle(args.bundle))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, zipfile.BadZipFile) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}", "scope": "preparation_only"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
