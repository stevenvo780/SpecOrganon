"""Bound D118 preparation to a persistent original-mode development runtime.

The local CLI uses an explicit loopback fixture, never paid provider credentials.
Runtime mechanisms, public byte binding and delivery structure remain separate
from authenticated provider activity, substantive quality and final acceptance.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import development_delivery_contract as delivery  # noqa: E402
import local_run_admission as admission  # noqa: E402
import plan_coordinated_development as planner  # noqa: E402
import prepare_coordinated_development as preparation  # noqa: E402
from run_managed_response import OpenAIResponsesHTTP  # noqa: E402

SPEC = ROOT / "experiments/development/coordinated_contract_2026-10-01"
SPEC_SHA256 = "6724df13d881e46b08c17213e440a5e231eca16c5541abc283f06ae101f4a044"
PROFILE = "coordinated_prototype_runtime_v1"
ROLES = ["leader", "worker-1", "worker-2", "reviewer"]
INPUT_NAMES = ["task_contract", "common_prompt", "tool_policy", "delivery_contract.json", "rubric.json",
               "coordination_prompt.md", "runtime_policy.json"]
CONFIG_KEYS = {"schema", "role_config", "max_epochs", "tool_wall_seconds"}


class CoordinatedRuntimeError(ValueError):
    """An unbound input or unsafe development operation cannot proceed."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(path: Path, maximum: int = 4 * 1024 * 1024):
    return delivery.parse_json(preparation._read(path, maximum))


def _integer(value, lower: int, upper: int, label: str) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise CoordinatedRuntimeError(f"{label} must be an integer in [{lower},{upper}]")
    return value


def validate_configuration(raw: dict, descriptor: dict) -> dict:
    if type(raw) is not dict or set(raw) != CONFIG_KEYS or type(raw["schema"]) is not int or raw["schema"] != 1:
        raise CoordinatedRuntimeError("configuration must have exactly the schema-1 runtime fields")
    values = raw["role_config"]
    if type(values) is not dict or set(values) != set(ROLES):
        raise CoordinatedRuntimeError("role_config must contain exactly the four coordinated roles")
    roles = {}
    for name in ROLES:
        row = values[name]
        if type(row) is not dict or set(row) != {"max_output_tokens", "max_model_turns"}:
            raise CoordinatedRuntimeError("role_config fields are invalid")
        roles[name] = {
            "max_output_tokens": _integer(row["max_output_tokens"], 1,
                    min(8192, descriptor["per_run_limits"]["measured_tokens"]), "output allowance"),
            "max_model_turns": _integer(row["max_model_turns"], 1,
                    1 if name == "reviewer" else descriptor["max_model_requests"], "global role turn allowance")}
    return {"schema": 1, "role_config": roles,
            "max_epochs": _integer(raw["max_epochs"], 1, descriptor["max_model_requests"], "max epochs"),
            "tool_wall_seconds": _integer(raw["tool_wall_seconds"], 1,
                                          min(300, descriptor["per_run_limits"]["active_seconds"]), "tool wall seconds")}


def _publication() -> dict:
    raw = preparation._read(SPEC / "source_freeze.json")
    if _sha(raw) != SPEC_SHA256:
        raise CoordinatedRuntimeError("published D118 source freeze is absent or changed")
    freeze = delivery.parse_json(raw)
    for row in freeze["records"]:
        source = preparation._read(ROOT / row["path"])
        if len(source) != row["bytes"] or _sha(source) != row["sha256"]:
            raise CoordinatedRuntimeError("published contract/compiler sources changed")
    for row in freeze["external_tools"]:
        source = preparation._read(Path(row["path"]))
        if len(source) != row["bytes"] or _sha(source) != row["sha256"]:
            raise CoordinatedRuntimeError("published extraction tool changed")
    return freeze


def _runtime_sources() -> dict:
    pending, seen, rows = [Path(__file__).stem, "managed_coordinated_prototype",
                           "coordinated_prototype_broker", "coordinated_prototype_kernel"], set(), {}
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        path = SCRIPTS / (name + ".py")
        raw = preparation._read(path)
        seen.add(name)
        rows[path.relative_to(ROOT).as_posix()] = _sha(raw)
        for node in ast.walk(ast.parse(raw)):
            names = ([entry.name.split(".")[0] for entry in node.names] if isinstance(node, ast.Import)
                     else [node.module.split(".")[0]] if isinstance(node, ast.ImportFrom) and node.module else [])
            pending.extend(value for value in names if (SCRIPTS / (value + ".py")).is_file())
    rows["prototypes/core.py"] = _sha(preparation._read(ROOT / "prototypes/core.py"))
    for name, digest in rows.items():
        if _sha(preparation._read(ROOT / name)) != digest:
            raise CoordinatedRuntimeError("runtime source closure changed during capture")
    return dict(sorted(rows.items()))


def _content_tree(path: Path) -> list[dict]:
    preparation._chain(path, directory=True)
    records = []
    for child in sorted(path.iterdir()):
        raw = preparation._read(child)
        records.append({"path": child.name, "bytes": len(raw), "sha256": _sha(raw)})
    return records


def _functions() -> list[dict]:
    return [{"type": "function", "name": "development_method", "strict": True,
             "description": "Fixed original-mode method. Leader initializes once then integrates and applies native gates. Workers revise/review owned nodes and write only owned files. Norms stay pending; no approval. Read/status/plan where the selected mode supports it; write/replace CAS.",
             "parameters": {"type": "object", "additionalProperties": False,
                            "properties": {"request": {"type": "string"}}, "required": ["request"]}},
            {"type": "function", "name": "development_analysis", "strict": True,
             "description": "Run fixed analysis.py readonly with the original case and current script SHA. Host validates finite JSON and publishes or retires metrics; failed calls consume budget. Final metrics must match final work. No normative approval or Q.",
             "parameters": {"type": "object", "additionalProperties": False,
                            "properties": {"script_sha256": {"type": "string"}}, "required": ["script_sha256"]}}]


def _binding(plan: dict) -> dict:
    context = delivery.parse_json(plan["context"].encode())
    binding = context.get("wrapper_binding")
    if type(binding) is not dict or binding.get("profile") != PROFILE:
        raise CoordinatedRuntimeError("runtime wrapper binding is absent or changed")
    return binding


def guard_coordinated_runtime(plan: dict, state: dict, broker) -> None:
    del state, broker
    binding = _binding(plan)
    _publication()
    bundle = Path(binding["bundle"])
    receipt = _json(bundle / "bundle.json")
    if (_sha(preparation._read(bundle / "bundle.json")) != binding["bundle_receipt_sha256"]
            or receipt["inventory"] != preparation._inventory(bundle)
            or receipt["source_records"] != preparation._source_records(SPEC / "public_contract")
            or receipt["contract_dir"] != str(SPEC / "public_contract")):
        raise CoordinatedRuntimeError("prepared bundle or original sources changed")
    if (_sha(preparation._canonical(_content_tree(Path(plan["case_dir"])))) != binding["case_inventory_sha256"]
            or _sha(preparation._canonical(_content_tree(Path(plan["inputs_dir"])))) != binding["inputs_inventory_sha256"]):
        raise CoordinatedRuntimeError("runtime public case or inputs changed")
    schedule = planner.validate_schedule(_json(bundle / "schedule.json"))
    if schedule != plan["schedule"] or schedule["source_freeze_sha256"] != SPEC_SHA256:
        raise CoordinatedRuntimeError("runtime calendar differs from the published preparation")
    planner.validate_runtime_binding(schedule, plan["run_id"], plan["descriptor"])
    if plan["runtime_source_digests"] != _runtime_sources():
        raise CoordinatedRuntimeError("runtime implementation closure changed")


def prepare_coordinated_runtime(run_dir: Path, bundle: Path, run_id: str, configuration: dict,
                                *, admission_root: Path | None = None) -> dict:
    import managed_coordinated_prototype as engine

    run_dir, bundle = map(Path, (run_dir, bundle))
    run_dir = preparation._chain(run_dir, new=True)
    preparation.original._private_parent(run_dir)
    preparation._chain(bundle, directory=True)
    _publication()
    preparation.verify_coordinated_bundle(bundle)
    receipt = _json(bundle / "bundle.json")
    schedule = planner.validate_schedule(_json(bundle / "schedule.json"))
    if (receipt["contract_dir"] != str(SPEC / "public_contract")
            or schedule["source_freeze_sha256"] != SPEC_SHA256):
        raise CoordinatedRuntimeError("runtime needs the published D118 contract and source freeze")
    descriptor = planner.runtime_descriptor(schedule, run_id)
    config = validate_configuration(configuration, descriptor)
    arm, case_id = descriptor["coordinates"]["arm"], descriptor["coordinates"]["case_id"]
    inputs = run_dir.parent / (run_dir.name + "-inputs")
    preparation._chain(inputs, new=True)
    selected_admission = admission.configured_root(admission_root)
    outputs = [run_dir.resolve(), inputs.resolve()]
    sources = [bundle.resolve(), ROOT.resolve()]
    if any(output == source or output in source.parents or source in output.parents
           for output in outputs for source in sources):
        raise CoordinatedRuntimeError("runtime outputs must be disjoint from bundle and checkout")
    admission_path = selected_admission.resolve()
    if any(admission_path == path or admission_path in path.parents or path in admission_path.parents
           for path in [*outputs, *sources]):
        raise CoordinatedRuntimeError("admission root must be disjoint from runtime and public sources")
    case = bundle / "assets" / case_id
    common = {name: preparation._read(bundle / "assets" / name) for name in INPUT_NAMES}
    common["arm_prompt"] = preparation._read(bundle / "assets" / f"prompt_{arm}")
    inputs_inventory = [{"path": name, "bytes": len(raw), "sha256": _sha(raw)}
                        for name, raw in sorted(common.items())]
    binding = {"profile": PROFILE, "bundle": str(bundle),
               "bundle_receipt_sha256": _sha(preparation._read(bundle / "bundle.json")),
               "published_source_freeze_sha256": SPEC_SHA256,
               "case_inventory_sha256": _sha(preparation._canonical(_content_tree(case))),
               "inputs_inventory_sha256": _sha(preparation._canonical(inputs_inventory))}
    context = {"wrapper_binding": binding, "public_case_manifest": _json(case / "case.json"),
               "common_task_contract": common["task_contract"].decode(),
               "common_prompt": common["common_prompt"].decode(), "arm_prompt": delivery.parse_json(common["arm_prompt"]),
               "delivery_contract": delivery.parse_json(common["delivery_contract.json"]),
               "public_rubric": delivery.parse_json(common["rubric.json"]),
               "coordination_prompt": common["coordination_prompt.md"].decode(),
               "normative_status": "pending_no_authorized_human_approval",
               "classification": "development_public_context_not_verified_scientific_results"}
    limits = descriptor["per_run_limits"]
    model = descriptor["model"]
    plan = {"schema": 1, "execution_profile": planner.RUNTIME_PROFILE, "run_id": run_id,
            "schedule": schedule, "descriptor": descriptor, "case_dir": str(case), "inputs_dir": str(inputs),
            "model": model["model_id"], "effort": model["effort_provider_value"] or "default",
            "price_profile": _json(bundle / "price_profile.json"), "functions": _functions(),
            "role_config": config["role_config"], "max_epochs": config["max_epochs"],
            "limits": {"limit_tokens": limits["measured_tokens"], "max_model_requests": descriptor["max_model_requests"],
                       "cost_limit_micro_usd": descriptor["cost_limit_micro_usd"], "active_limit_seconds": limits["active_seconds"],
                       "max_tool_calls": limits["tool_calls"], "tool_wall_seconds": config["tool_wall_seconds"]},
            "context": preparation._canonical(context).decode(),
            "journal_roots": [str(run_dir / "broker_stages")], "runtime_source_digests": _runtime_sources()}
    engine.validate_plan(plan, check_inputs=False)
    # All supplied declarations and output paths have passed before creating inputs.
    inputs.mkdir(mode=0o700)
    for name, raw in common.items():
        fd = os.open(inputs / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
    return engine.prepare_coordinated_prototype(run_dir, plan, admission_root=selected_admission)


def read_coordinated_runtime_status(run_dir: Path) -> dict:
    import managed_coordinated_prototype as engine
    return engine.read_coordinated_prototype_status(Path(run_dir), guard=guard_coordinated_runtime)


def execute_coordinated_runtime_step(run_dir: Path, transports: dict, *, expected_checkpoint: str) -> dict:
    import managed_coordinated_prototype as engine
    status = engine.read_coordinated_prototype_status(Path(run_dir), guard=guard_coordinated_runtime)
    roles = ([row["task_id"] for row in status["assignments"] if not status["roles"][row["task_id"]]["finished"]]
             if status["runtime_stage"] == "workers" else [status["runtime_stage"]])
    if type(transports) is dict and set(transports) == set(ROLES):
        transports = {role: transports[role] for role in roles if role in transports}
    return engine.execute_coordinated_prototype_step(Path(run_dir), transports,
            expected_checkpoint=expected_checkpoint, guard=guard_coordinated_runtime)


def _fixture_endpoint(value: str) -> str:
    try:
        address = urlsplit(value)
        valid = (address.scheme == "http" and address.hostname == "127.0.0.1" and address.port is not None
                 and address.username is None and address.password is None and not address.query
                 and not address.fragment and address.path in {"", "/v1"})
    except ValueError as exc:
        raise CoordinatedRuntimeError("invalid fixture endpoint") from exc
    if not valid:
        raise CoordinatedRuntimeError("fixture requires HTTP 127.0.0.1, explicit port and optional /v1")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    for name in ("bundle", "configuration", "admission-root"):
        prepare.add_argument("--" + name, type=Path, required=name != "admission-root")
    prepare.add_argument("--run-id", required=True)
    for name in ("prepare", "status", "step"):
        command = prepare if name == "prepare" else sub.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
    step = sub.choices["step"]
    step.add_argument("--expected-checkpoint", required=True)
    step.add_argument("--local-http-fixture", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_coordinated_runtime(args.run_dir, args.bundle, args.run_id, _json(args.configuration),
                                                 admission_root=args.admission_root)
        elif args.command == "status":
            result = read_coordinated_runtime_status(args.run_dir)
        else:
            endpoint = _fixture_endpoint(args.local_http_fixture)
            plan = _json(args.run_dir / "plan.json")
            if plan["descriptor"]["provider_route"]["provider"] != "fixture":
                raise CoordinatedRuntimeError("local fixture CLI requires the declared fixture route")
            transports = {role: OpenAIResponsesHTTP("public-synthetic-no-credential", base_url=endpoint) for role in ROLES}
            result = execute_coordinated_runtime_step(args.run_dir, transports, expected_checkpoint=args.expected_checkpoint)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}", "formal_cell_executed": False,
                          "quality_assessed": False, "execution_authorized": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
