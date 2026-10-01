"""Mechanical C waves with the D113 readonly analyzer and fresh metric export.

Caller-provided graphs remain an explicit limit. This does not prepare or
execute a comparable development cell. The CLI only accepts local HTTP data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import c_parallel_tools as original  # noqa: E402
from c_parallel_work import (  # noqa: E402
    CORE_PATH, CParallelError, _bytes, _input_json, _sha, _state, select_independent_work,
)
from development_analysis_tool import build_analysis_tool  # noqa: E402
from development_branch_tool import build_branch_tool  # noqa: E402
from managed_parallel_analysis import (  # noqa: E402
    bind_analysis_plan, execute_analysis_wave_step, prepare_analysis_wave,
    read_analysis_wave_status, require_analysis_binding,
)
from managed_parallel_tools import _validate_plan  # noqa: E402
from parallel_analysis_broker import prepare_analysis_branch_manifest  # noqa: E402
from run_managed_conversation import (  # noqa: E402
    _canonical, _new_private_file, _private_dir, _read_json,
)
from run_managed_response import OpenAIResponsesHTTP  # noqa: E402
from tool_policy import _parse_json  # noqa: E402


CONFIG = original.CONFIG
METRICS_CLASSIFICATION = "development_branch_analysis_metrics_unsealed"


def _functions() -> list:
    return [
        {"type": "function", "name": "development_method", "strict": True,
         "description": "Private branch read/status/plan/revise/review/write/replace CAS. Only owned nodes change. No init, approve, or phase advance.",
         "parameters": {"type": "object", "additionalProperties": False,
                        "properties": {"request": {"type": "string"}}, "required": ["request"]}},
        {"type": "function", "name": "development_analysis", "strict": True,
         "description": "Execute fixed work/analysis.py with [analysis.py,case_dir] read only. Current script SHA required. Host validates finite JSON and publishes metrics; errors consume a call. Repair your script through replace CAS before retry. No normative approval.",
         "parameters": {"type": "object", "additionalProperties": False,
                        "properties": {"script_sha256": {"type": "string"}}, "required": ["script_sha256"]}},
    ]


def prepare_c_analysis_wave(run_dir: Path, state_path: Path, case_dir: Path,
                            inputs_dir: Path, config: dict, *, admission_root: Path | None = None) -> dict:
    if type(config) is not dict or set(config) != CONFIG:
        raise CParallelError("C analysis config has missing or unsupported fields")
    run_dir, state_path, case_dir, inputs_dir = map(Path, (run_dir, state_path, case_dir, inputs_dir))
    if any(not path.is_absolute() or ".." in path.parts for path in (run_dir, state_path, case_dir, inputs_dir)):
        raise CParallelError("all C analysis paths must be absolute")
    if run_dir.exists() or run_dir.is_symlink():
        raise FileExistsError("C analysis run already exists")
    _private_dir(run_dir.parent)
    state_raw = _bytes(state_path)
    state = _state(state_raw)
    selected = select_independent_work(state, config["workers"])
    scalars = {key: config[key] for key in CONFIG - {
        "workers", "max_output_tokens", "reviewer_max_output_tokens", "max_model_turns"}}
    validation = {**scalars, "schema": 2, "execution_profile": "parallel_tool_wave_v2",
                  "context": "validate analysis config", "functions": _functions(),
                  "branch_manifest": {"path": "/validation/no-effects/manifest.json", "sha256": "0" * 64},
                  "tasks": [{"task_id": f"c-task-{i}", "role": f"c-worker-{i}",
                             "user": "validate", "owned_node_ids": [entry["id"]],
                             "max_output_tokens": config["max_output_tokens"],
                             "max_model_turns": config["max_model_turns"]}
                            for i, entry in enumerate(selected, 1)],
                  "reviewer": {"user": "validate", "max_output_tokens": config["reviewer_max_output_tokens"]}}
    _validate_plan(validation)
    try:
        policy_raw = _bytes(inputs_dir / "tool_policy")
    except OSError as exc:
        raise CParallelError("C analysis requires a regular inputs/tool_policy with schema 2 for CAS repair") from exc
    if len(policy_raw) > 128 * 1024:
        raise CParallelError("C analysis tool_policy exceeds the CAS policy byte limit")
    policy = _parse_json(policy_raw, "C analysis tool_policy")
    if type(policy) is not dict or type(policy.get("schema")) is not int or policy["schema"] != 2:
        raise CParallelError("C analysis requires inputs/tool_policy schema 2 for CAS repair")
    case_snapshot, inputs_snapshot = original._tree(case_dir), original._tree(inputs_dir)
    manifest = _input_json(_bytes(case_dir / "case.json"))
    prompt = _input_json(_bytes(inputs_dir / "arm_prompt"))
    if manifest.get("case_id") != state["case_id"] or prompt.get("alternative") != "C" or prompt.get("mode") != "risk":
        raise CParallelError("public case identity or alternative differs from C state")
    binding = {"profile": "c_private_tools_v2", "base_state_path": str(state_path),
               "base_state_sha256": _sha(state_raw), "case_dir": str(case_dir),
               "case_inventory_sha256": _sha(_canonical(case_snapshot)), "inputs_dir": str(inputs_dir),
               "inputs_inventory_sha256": _sha(_canonical(inputs_snapshot)),
               "source_digests": {str(path): _sha(_bytes(path)) for path in (
                   CORE_PATH, Path(original.__file__), Path(__file__),
                   SCRIPTS / "development_branch_tool.py", SCRIPTS / "development_method_tool.py",
                   SCRIPTS / "c_parallel_work.py", SCRIPTS / "development_analysis_tool.py")}}
    branch_root = run_dir.parent / (run_dir.name + "-branches")
    branch_root.mkdir(mode=0o700)
    analysis_tool = branch_root / "analysis-tool.py"
    build_analysis_tool(analysis_tool)
    specs, tasks = [], []
    for i, entry in enumerate(selected, 1):
        task_id = f"c-task-{i}"
        stage = branch_root / task_id
        stage.mkdir(mode=0o700)
        original._copy_tree(case_dir, stage / "case", case_snapshot)
        original._copy_tree(inputs_dir, stage / "inputs", inputs_snapshot)
        (stage / "work").mkdir(mode=0o700)
        _new_private_file(stage / "work/method_state.json", state_raw)
        _new_private_file(stage / "stage.json", _canonical({
            "schema": "c_private_analysis_stage.v1", "task_id": task_id,
            "case_id": state["case_id"], "base_state_sha256": _sha(state_raw), "owned_node_ids": [entry["id"]]}))
        tool = branch_root / f"{task_id}-method.py"
        build_branch_tool(tool, [entry["id"]])
        specs.append({"task_id": task_id, "owned_node_ids": [entry["id"]], "stage_dir": str(stage),
                      "functions": [{"name": "development_method", "executable": str(tool), "profile": "workspace"},
                                    {"name": "development_analysis", "executable": str(analysis_tool), "profile": "analysis_readonly"}]})
        tasks.append({"task_id": task_id, "role": f"c-worker-{i}", "owned_node_ids": [entry["id"]],
                      "max_output_tokens": config["max_output_tokens"], "max_model_turns": config["max_model_turns"],
                      "user": f"Investigate owned node {entry['id']} with common public case sources. Write allowlisted analysis.py; use readonly analysis with its current SHA. Repair your own source through replace CAS after ordinary errors. Distinguish calculations from empirical verification and leave norms pending. Do not initialize or advance phases. Return a public artifact; never expose private reasoning."})
    branch_manifest = prepare_analysis_branch_manifest(branch_root, specs)
    common = {"binding": binding, "prototype_state": state, "public_case_manifest": manifest,
              "common_arm_prompt": prompt, "facts_status": "caller_supplied_not_independently_verified"}
    plan = {**scalars, "schema": 2, "execution_profile": "parallel_tool_wave_v2", "tasks": tasks,
            "branch_manifest": branch_manifest, "context": _canonical(common).decode(), "functions": _functions(),
            "reviewer": {"user": "Review only public artifacts and common sources. Identify unsupported claims, errors, and unresolved norms. No tools, approval, or phase advancement.",
                         "max_output_tokens": config["reviewer_max_output_tokens"]}}
    plan = bind_analysis_plan(plan)
    _guard(plan)
    return prepare_analysis_wave(run_dir, plan, admission_root=admission_root)


def _guard(plan: dict) -> None:
    require_analysis_binding(plan)
    original._guard(plan)
    require_analysis_binding(plan)


def merge_c_analysis_branches(plan: dict, state: dict, broker, context, guard) -> dict:
    _guard(plan)
    guard()
    base = original.merge_c_branches(plan, state, broker, context, guard)
    entries, missing = [], []
    for task in plan["tasks"]:
        guard()
        _guard(plan)
        current = broker.current_metrics(task["task_id"])
        if current is None:
            missing.append(task["task_id"])
            continue
        raw = _bytes(Path(current["metrics_path"]))
        if _sha(raw) != current["analysis_metrics_sha256"] or len(raw) != current["metrics_bytes"]:
            raise CParallelError("fresh metrics changed before merge export")
        directory = context.directory.parent / "merge/analysis" / task["task_id"]
        directory.mkdir(parents=True, mode=0o700)
        target, provenance = directory / "metrics.json", directory / "provenance.json"
        _new_private_file(target, raw)
        record = {"schema": 1, "classification": METRICS_CLASSIFICATION,
                  "branch_manifest": plan["branch_manifest"], "task_id": task["task_id"],
                  "analysis_script_sha256": current["analysis_script_sha256"],
                  "global_ordinal": current["global_ordinal"], "local_ordinal": current["local_ordinal"],
                  "broker_receipt_sha256": current["receipt_sha256"],
                  "metrics_sha256": _sha(raw), "metrics_bytes": len(raw),
                  "empirical_support_verified": False, "formal_cell_executed": False}
        _new_private_file(provenance, _canonical(record))
        entries.append({"task_id": task["task_id"], "metrics_path": str(target), "metrics_sha256": _sha(raw),
                        "provenance_path": str(provenance), "provenance_sha256": _sha(_bytes(provenance)),
                        "analysis_script_sha256": current["analysis_script_sha256"],
                        "global_ordinal": current["global_ordinal"], "local_ordinal": current["local_ordinal"],
                        "broker_receipt_sha256": current["receipt_sha256"]})
        guard()
        _guard(plan)
    receipt = context.directory.parent / "merge/analysis_receipt.json"
    _new_private_file(receipt, _canonical({"schema": 1, "classification": METRICS_CLASSIFICATION,
                      "base_receipt_sha256": base["receipt_sha256"], "analysis_artifacts": entries,
                      "missing_or_stale_tasks": missing, "empirical_support_verified": False,
                      "formal_cell_executed": False, "caller_graph_required": True}))
    guard()
    _guard(plan)
    return {**base, "analysis_artifacts": entries, "missing_or_stale_tasks": missing,
            "analysis_receipt_path": str(receipt), "analysis_receipt_sha256": _sha(_bytes(receipt)),
            "caller_graph_required": True, "comparable_development_cell": False}


def execute_c_analysis_wave_step(run_dir: Path, transports_by_task: dict, *, expected_checkpoint: str) -> dict:
    plan = _read_json(Path(run_dir) / "plan.json")
    _guard(plan)
    return execute_analysis_wave_step(run_dir, transports_by_task, expected_checkpoint=expected_checkpoint,
                                      guard=lambda: _guard(plan), merge=merge_c_analysis_branches)


def read_c_analysis_wave_status(run_dir: Path) -> dict:
    plan = _read_json(Path(run_dir) / "plan.json")
    _guard(plan)
    result = read_analysis_wave_status(run_dir)
    _guard(plan)
    return result


def main(argv=None) -> int:
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
    step.add_argument("--local-http-fixture", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_c_analysis_wave(args.run_dir, args.state, args.case_dir, args.inputs_dir,
                                             _input_json(_bytes(args.config)), admission_root=args.admission_root)
        elif args.command == "status":
            result = read_c_analysis_wave_status(args.run_dir)
        else:
            endpoint = urlsplit(args.local_http_fixture)
            if (endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1" or endpoint.port is None
                    or endpoint.username is not None or endpoint.password is not None
                    or endpoint.query or endpoint.fragment or endpoint.path not in {"", "/v1"}):
                raise CParallelError("fixture must be HTTP at 127.0.0.1 with explicit port")
            plan = _read_json(args.run_dir / "plan.json")
            transports = {task["task_id"]: OpenAIResponsesHTTP("public-synthetic-no-credential", base_url=args.local_http_fixture)
                          for task in plan["tasks"]}
            transports["reviewer"] = OpenAIResponsesHTTP("public-synthetic-no-credential", base_url=args.local_http_fixture)
            result = execute_c_analysis_wave_step(args.run_dir, transports, expected_checkpoint=args.expected_checkpoint)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}", "formal_cell_executed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
