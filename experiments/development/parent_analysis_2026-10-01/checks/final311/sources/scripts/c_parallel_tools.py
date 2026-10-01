"""Opt-in C tool waves with private branches and a checked serial merge.

This development profile is separate from preregistered solo/trio cells.
Local HTTP fixtures demonstrate control flow, not model identity or quality.
The merged state is a new artifact; the original state is never overwritten.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from c_parallel_work import (  # noqa: E402
    CORE_PATH, CONFIG_KEYS, CParallelError, _bytes, _input_json, _sha, _state,
    core, select_independent_work,
)
from development_branch_tool import build_branch_tool  # noqa: E402
from managed_parallel_tools import (  # noqa: E402
    _validate_plan as _validate_tool_plan,
    execute_tool_wave_step, prepare_tool_wave, read_tool_wave_status,
)
from parallel_tool_broker import (  # noqa: E402
    ParallelToolBroker, prepare_branch_manifest,
)
from run_managed_conversation import (  # noqa: E402
    _canonical, _fsync_dir, _new_private_file, _private_dir, _read_json,
)
from run_managed_response import OpenAIResponsesHTTP  # noqa: E402
from run_staged_local_tool import (  # noqa: E402
    MAX_STAGE_BYTES, MAX_STAGE_ENTRIES, MAX_STAGE_FILES, _inventory,
)

CONFIG = CONFIG_KEYS | {"max_model_turns", "max_tool_calls", "tool_wall_seconds"}
MERGE_CLASSIFICATION = "development_c_serial_merge_not_empirical_support"


def _tree(source: Path) -> dict:
    files, directories, complete, reason = _inventory(
        source, max_files=MAX_STAGE_FILES, max_bytes=MAX_STAGE_BYTES,
        max_file_bytes=MAX_STAGE_BYTES, max_entries=MAX_STAGE_ENTRIES)
    if not complete:
        raise CParallelError(f"public source inventory is incomplete: {reason}")
    return {"files": files, "directories": directories}


def _copy_tree(source: Path, destination: Path, snapshot: dict) -> None:
    destination.mkdir(mode=0o700)
    for item in snapshot["files"]:
        relative = Path(item["path"])
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        raw = _bytes(source / relative)
        if len(raw) != item["bytes"] or _sha(raw) != item["sha256"]:
            raise CParallelError("public source changed while copying branch")
        _new_private_file(target, raw)
    _fsync_dir(destination)


def prepare_c_tool_wave(run_dir: Path, state_path: Path, case_dir: Path,
                        inputs_dir: Path, config: dict, *,
                        admission_root: Path | None = None) -> dict:
    if type(config) is not dict or set(config) != CONFIG:
        raise CParallelError("C tool-wave config has missing or unsupported fields")
    run_dir, state_path, case_dir, inputs_dir = map(
        Path, (run_dir, state_path, case_dir, inputs_dir))
    for path in (run_dir, state_path, case_dir, inputs_dir):
        if not path.is_absolute() or ".." in path.parts:
            raise CParallelError("all C tool-wave paths must be absolute")
    if run_dir.exists() or run_dir.is_symlink():
        raise FileExistsError("C tool-wave run directory already exists")
    _private_dir(run_dir.parent)
    state_raw = _bytes(state_path)
    state = _state(state_raw)
    selected = select_independent_work(state, config["workers"])
    # Validate every scalar through the runner's pure validator before creating
    # any stage. Invalid budgets must not consume the intended preparation path.
    validation = {key: config[key] for key in CONFIG - {
        "workers", "max_output_tokens", "reviewer_max_output_tokens", "max_model_turns"}}
    validation.update(schema=2, execution_profile="parallel_tool_wave_v2", context="validate config",
                      branch_manifest={"path": "/validation/no-effects/manifest.json", "sha256": "0" * 64},
                      tasks=[{"task_id": f"c-task-{index}", "role": f"c-worker-{index}",
                              "user": "validate task", "owned_node_ids": [entry["id"]],
                              "max_output_tokens": config["max_output_tokens"],
                              "max_model_turns": config["max_model_turns"]}
                             for index, entry in enumerate(selected, 1)],
                      reviewer={"user": "validate review", "max_output_tokens": config["reviewer_max_output_tokens"]},
                      functions=[{"type": "function", "name": "development_method", "description": "validate",
                                  "strict": True, "parameters": {"type": "object", "properties": {
                                      "request": {"type": "string"}}, "required": ["request"],
                                      "additionalProperties": False}}])
    _validate_tool_plan(validation)
    case_snapshot, inputs_snapshot = _tree(case_dir), _tree(inputs_dir)
    manifest = _input_json(_bytes(case_dir / "case.json"))
    prompt = _input_json(_bytes(inputs_dir / "arm_prompt"))
    if manifest.get("case_id") != state["case_id"] or prompt.get("alternative") != "C" or prompt.get("mode") != "risk":
        raise CParallelError("public case identity or alternative differs from C state")
    binding = {
        "profile": "c_private_tools_v2", "base_state_path": str(state_path),
        "base_state_sha256": _sha(state_raw), "case_dir": str(case_dir),
        "case_inventory_sha256": _sha(_canonical(case_snapshot)),
        "inputs_dir": str(inputs_dir),
        "inputs_inventory_sha256": _sha(_canonical(inputs_snapshot)),
        "source_digests": {str(path): _sha(_bytes(path)) for path in (
            CORE_PATH, Path(__file__), SCRIPTS / "development_branch_tool.py",
            SCRIPTS / "development_method_tool.py", SCRIPTS / "c_parallel_work.py")},
    }
    branch_root = run_dir.parent / (run_dir.name + "-branches")
    branch_root.mkdir(mode=0o700)
    specifications, tasks = [], []
    for index, entry in enumerate(selected, 1):
        task_id = f"c-task-{index}"
        stage = branch_root / task_id
        stage.mkdir(mode=0o700)
        _copy_tree(case_dir, stage / "case", case_snapshot)
        _copy_tree(inputs_dir, stage / "inputs", inputs_snapshot)
        (stage / "work").mkdir(mode=0o700)
        _new_private_file(stage / "work" / "method_state.json", state_raw)
        _new_private_file(stage / "stage.json", _canonical({
            "schema": "c_private_branch_stage.v1", "task_id": task_id,
            "case_id": state["case_id"], "base_state_sha256": _sha(state_raw),
            "owned_node_ids": [entry["id"]]}))
        tool = branch_root / f"{task_id}-method.py"
        build_branch_tool(tool, [entry["id"]])
        specifications.append({"task_id": task_id, "owned_node_ids": [entry["id"]],
                               "stage_dir": str(stage), "functions": [{
                                   "name": "development_method", "executable": str(tool),
                                   "profile": "workspace"}]})
        tasks.append({"task_id": task_id, "role": f"c-worker-{index}",
                      "owned_node_ids": [entry["id"]],
                      "max_output_tokens": config["max_output_tokens"],
                      "max_model_turns": config["max_model_turns"],
                      "user": f"Investigate node {entry['id']} using the public case and fixed "
                      "method tool in your private branch. Distinguish observations, inference "
                      "and uncertainty. Revise/review only your owned node. Changes are proposals, "
                      "not empirical verification or normative approval. Do not advance phases. "
                      "Return a public report of actual operations and unresolved requirements."})
    branch_manifest = prepare_branch_manifest(branch_root, specifications)
    common = {"binding": binding, "prototype_state": state,
              "public_case_manifest": manifest,
              "common_arm_prompt": prompt,
              "facts_status": "caller_supplied_not_independently_verified"}
    plan = {key: config[key] for key in CONFIG - {
        "workers", "max_output_tokens", "reviewer_max_output_tokens", "max_model_turns"}}
    plan.update(schema=2, execution_profile="parallel_tool_wave_v2", tasks=tasks,
                branch_manifest=branch_manifest, context=_canonical(common).decode(),
                functions=[{"type": "function", "name": "development_method",
                            "description": "Run the fixed development driver in your private branch. "
                            "JSON request supports read, status, plan, revise, review, write and replace. "
                            "Only owned nodes may change; init, approval and phase advance are forbidden.",
                            "parameters": {"type": "object", "properties": {"request": {"type": "string"}},
                                           "required": ["request"], "additionalProperties": False},
                            "strict": True}],
                reviewer={"user": "Review the public artifacts against the common inputs. "
                          "Report contradictions, missing evidence and unresolved norms. "
                          "You cannot approve norms or advance phases.",
                          "max_output_tokens": config["reviewer_max_output_tokens"]})
    _guard(plan)
    return prepare_tool_wave(run_dir, plan, admission_root=admission_root)


def _guard(plan: dict) -> None:
    common = _input_json(plan["context"].encode())
    binding = common["binding"]
    if binding["profile"] != "c_private_tools_v2":
        raise CParallelError("C tool-wave context profile changed")
    raw = _bytes(Path(binding["base_state_path"]))
    if _sha(raw) != binding["base_state_sha256"] or _state(raw) != common["prototype_state"]:
        raise CParallelError("C original base state changed")
    for key in ("case", "inputs"):
        current = _tree(Path(binding[f"{key}_dir"]))
        if _sha(_canonical(current)) != binding[f"{key}_inventory_sha256"]:
            raise CParallelError("C common public source changed")
    for path, digest in binding["source_digests"].items():
        if _sha(_bytes(Path(path))) != digest:
            raise CParallelError("C core, builder or wrapper source changed")
    selected = select_independent_work(common["prototype_state"], len(plan["tasks"]))
    if [task["owned_node_ids"] for task in plan["tasks"]] != [[entry["id"]] for entry in selected]:
        raise CParallelError("C task ownership or eligibility changed")


def _apply(state_path: Path, request: dict) -> None:
    op = request["op"]
    if op == "revise" and set(request) == {"op", "id", "status", "reason"}:
        arguments = [op, "--id", request["id"], "--status", request["status"], "--reason", request["reason"]]
    elif op == "review" and set(request) == {"op", "id"}:
        arguments = [op, "--id", request["id"]]
    else:
        raise CParallelError("merge contains a forbidden method operation")
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = core.run("risk", [*arguments, "--state", str(state_path)])
    result = _input_json(stdout.getvalue().encode())
    if code != 0 or result.get("ok") is not True:
        raise CParallelError("successful branch operation could not be replayed")


def merge_c_branches(plan: dict, state: dict, broker: ParallelToolBroker,
                     context, guard) -> dict:
    """Replay trusted successful operations and publish a new gathered state."""
    del state
    guard()
    context.require_active()
    _guard(plan)
    broker.verify()
    run_dir = context.directory.parent
    destination = run_dir / "merge"
    _private_dir(destination)
    if list(destination.iterdir()):
        raise CParallelError("merge already has effects; automatic replay is forbidden")
    base = _input_json(plan["context"].encode())["prototype_state"]
    base_raw = _canonical(base)
    operations = broker.operations()
    changes = []
    ownership = {task["task_id"]: task["owned_node_ids"] for task in plan["tasks"]}
    _new_private_file(destination / ".pending.json", _canonical({
        "classification": MERGE_CLASSIFICATION, "base_sha256": _sha(base_raw),
        "operations_sha256": _sha(_canonical(operations))}))
    replay_root = destination / "branch-replays"
    replay_root.mkdir(mode=0o700)
    # Each branch must equal the replay of its actual successful tool mutations.
    # Do not flatten diffs: descendants invalidated by the core can be shared.
    for task_id, owned in ownership.items():
        branch_replay = replay_root / f"{task_id}.json"
        _new_private_file(branch_replay, base_raw)
        for operation in operations:
            if operation["task_id"] != task_id or operation["profile"] != "workspace":
                continue
            request, output = operation["request"], operation["output_json"]
            if (type(request) is not dict or request.get("op") not in {"revise", "review"}
                    or operation["terminal"]["status"] != "success"
                    or type(output) is not dict or output.get("ok") is not True):
                continue
            if request.get("id") not in owned:
                raise CParallelError("branch operation escaped node ownership")
            guard()
            _apply(branch_replay, request)
            changes.append({"task_id": task_id, "global_ordinal": operation["global_ordinal"],
                            "request": request})
        actual = _state(_bytes(Path(broker.branch(task_id)["stage_dir"]) / "work" / "method_state.json"))
        if actual != _state(_bytes(branch_replay)):
            raise CParallelError("branch state differs from authenticated operation replay")
    changes.sort(key=lambda item: item["global_ordinal"])
    merged_path = destination / "method_state.json"
    _new_private_file(merged_path, base_raw)
    for change in changes:
        guard()
        _apply(merged_path, change["request"])
    merged = _state(_bytes(merged_path))
    if (any(node["status"] != "pending" for node in merged["nodes"].values() if node["kind"] == "normative")
            or merged["phase_status"] != base["phase_status"]):
        raise CParallelError("merge changed normative approval or phase acceptance")
    artifacts = []
    for task_id in ownership:
        work = Path(broker.branch(task_id)["stage_dir"]) / "work"
        for name in ("report.md", "sources.json", "analysis.py"):
            path = work / name
            if not path.exists():
                continue
            raw = _bytes(path)
            target = destination / "artifacts" / task_id / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            _new_private_file(target, raw)
            artifacts.append({"task_id": task_id, "path": str(target),
                              "sha256": _sha(raw), "bytes": len(raw)})
    guard()
    broker.verify()
    context.require_active()
    receipt = {"classification": MERGE_CLASSIFICATION, "schema": 1,
               "base_sha256": _sha(base_raw), "branch_manifest": plan["branch_manifest"],
               "operations": changes, "state_path": str(merged_path),
               "state_sha256": _sha(_bytes(merged_path)), "artifacts": artifacts,
               "normative_approvals": 0, "new_phase_acceptances": 0,
               "empirical_support_verified": False, "formal_cell_executed": False}
    receipt_path = destination / "receipt.json"
    _new_private_file(receipt_path, _canonical(receipt))
    guard()
    context.require_active()
    # Keep the prepared marker in the frozen merge journal. The engine writes
    # its separate publication marker only after RunContext.finish succeeds.
    return {"path": str(merged_path), "sha256": receipt["state_sha256"],
            "receipt_path": str(receipt_path), "receipt_sha256": _sha(_bytes(receipt_path)),
            "operations": len(changes), "artifacts": artifacts,
            "empirical_support_verified": False, "formal_cell_executed": False}


def execute_c_tool_wave_step(run_dir: Path, transports_by_task: dict, *,
                             expected_checkpoint: str) -> dict:
    plan = _read_json(Path(run_dir) / "plan.json")
    return execute_tool_wave_step(run_dir, transports_by_task,
                                  expected_checkpoint=expected_checkpoint,
                                  guard=lambda: _guard(plan), merge=merge_c_branches)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    for name in ("state", "case-dir", "inputs-dir", "config", "admission-root"):
        prepare.add_argument("--" + name, type=Path, required=name != "admission-root")
    for name in ("prepare", "status", "step"):
        command = prepare if name == "prepare" else sub.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
    step = sub.choices["step"]
    step.add_argument("--expected-checkpoint", required=True)
    transport = step.add_mutually_exclusive_group(required=True)
    transport.add_argument("--provider", choices=["openai"])
    transport.add_argument("--local-http-fixture", help="Public synthetic fixture at 127.0.0.1")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_c_tool_wave(args.run_dir, args.state, args.case_dir,
                                         args.inputs_dir, _input_json(_bytes(args.config)),
                                         admission_root=args.admission_root)
        elif args.command == "status":
            result = read_tool_wave_status(args.run_dir)
        else:
            plan = _read_json(args.run_dir / "plan.json")
            if args.local_http_fixture:
                url = urlsplit(args.local_http_fixture)
                if (url.scheme != "http" or url.hostname != "127.0.0.1" or url.port is None
                        or url.username is not None or url.password is not None
                        or url.query or url.fragment or url.path not in {"", "/v1"}):
                    raise CParallelError("fixture endpoint must be HTTP at 127.0.0.1 with an explicit port")
                def make_transport():
                    return OpenAIResponsesHTTP("public-synthetic-no-credential", base_url=args.local_http_fixture)
            else:
                key = os.environ.get("OPENAI_API_KEY")
                if not key:
                    raise CParallelError("OPENAI_API_KEY is required for explicit provider execution")

                def make_transport():
                    return OpenAIResponsesHTTP(key)
            transports = {task["task_id"]: make_transport() for task in plan["tasks"]}
            transports["reviewer"] = make_transport()
            result = execute_c_tool_wave_step(args.run_dir, transports,
                                              expected_checkpoint=args.expected_checkpoint)
        print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}", "formal_cell_executed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
