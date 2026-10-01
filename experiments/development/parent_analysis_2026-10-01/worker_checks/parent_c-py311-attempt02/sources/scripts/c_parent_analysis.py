"""Opt-in C bootstrap from empty work under one parent analysis runtime.

The leader creates the graph through the fixed method tool. Branch preparation
is a host transition bound to that real initialization and its public artifact.
This is mechanical development infrastructure, not a comparable formal cell.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import c_parallel_analysis as analysis  # noqa: E402
import c_parallel_tools as original  # noqa: E402
from c_parallel_work import CORE_PATH, CParallelError, _bytes, _input_json, _sha, _state, core, select_independent_work  # noqa: E402
from development_analysis_tool import build_analysis_tool  # noqa: E402
from development_branch_tool import build_branch_tool  # noqa: E402
from development_method_tool import build_tool  # noqa: E402
from managed_parallel_analysis import bind_analysis_plan, require_analysis_binding  # noqa: E402
from managed_parallel_wave import _integer  # noqa: E402
from parent_analysis_broker import prepare_parent_broker_manifest  # noqa: E402
from parallel_analysis_broker import prepare_analysis_branch_manifest  # noqa: E402
from run_managed_conversation import _canonical, _new_private_file, _private_dir, _read_json  # noqa: E402
from run_managed_response import OpenAIResponsesHTTP  # noqa: E402
from tool_policy import _parse_json  # noqa: E402


PROFILE = "c_parent_analysis_v1"
CONFIG = analysis.CONFIG | {"leader_max_model_turns", "leader_max_output_tokens"}
_SOURCE_LOCK = threading.RLock()
_SOURCE_CACHE: dict[str, str] | None = None


def _sources() -> dict:
    global _SOURCE_CACHE
    with _SOURCE_LOCK:
        if _SOURCE_CACHE is not None:
            current = {name: _sha(_bytes(Path(name))) for name in _SOURCE_CACHE}
            if current == _SOURCE_CACHE:
                return current
        current = _discover_sources()
        _SOURCE_CACHE = current
        return dict(current)


def _discover_sources() -> dict:
    pending = ["c_parent_analysis", "managed_parent_analysis", "parent_analysis_broker"]
    seen = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        path = SCRIPTS / f"{name}.py"
        raw = _bytes(path)
        seen.add(name)
        for node in ast.walk(ast.parse(raw)):
            names = ([item.name.split(".")[0] for item in node.names]
                     if isinstance(node, ast.Import) else
                     [node.module.split(".")[0]]
                     if isinstance(node, ast.ImportFrom) and node.module else [])
            pending.extend(item for item in names if (SCRIPTS / f"{item}.py").is_file())
    paths = [SCRIPTS / f"{name}.py" for name in sorted(seen)] + [CORE_PATH]
    return {str(path): _sha(_bytes(path)) for path in paths}


def _functions() -> list:
    functions = analysis._functions()
    functions[0]["description"] = (
        "Fixed method tool. Bootstrap leader may init pending nodes, status/read/write/replace CAS/plan. "
        "Bootstrap cannot revise/review/approve/advance. Private workers may revise/review only owned nodes; "
        "workers cannot init/approve/advance. Decisions and norms remain pending.")
    return functions


def _binding(plan: dict) -> dict:
    common = _input_json(plan["context"].encode())
    binding = common.get("parent_binding")
    if type(binding) is not dict or binding.get("profile") != PROFILE:
        raise CParallelError("C parent context binding changed")
    return binding


def prepare_c_parent_analysis(run_dir: Path, case_dir: Path, inputs_dir: Path,
                              config: dict, *, admission_root: Path | None = None) -> dict:
    import managed_parent_analysis as engine

    if type(config) is not dict or set(config) != CONFIG:
        raise CParallelError("C parent config has missing or unsupported fields")
    run_dir, case_dir, inputs_dir = map(Path, (run_dir, case_dir, inputs_dir))
    if any(not path.is_absolute() or ".." in path.parts for path in (run_dir, case_dir, inputs_dir)):
        raise CParallelError("C parent paths must be absolute without parent traversal")
    stages = run_dir.parent / (run_dir.name + "-stages")
    try:
        outputs = [path.resolve() for path in (run_dir, stages)]
        sources = [path.resolve() for path in (case_dir, inputs_dir)]
    except (OSError, RuntimeError) as exc:
        raise CParallelError("C parent paths cannot be resolved safely") from exc
    if any(output == source or output in source.parents or source in output.parents
           for output in outputs for source in sources):
        raise CParallelError("C parent run and stages must not overlap public case or inputs")
    if run_dir.exists() or run_dir.is_symlink():
        raise FileExistsError("C parent run already exists")
    _private_dir(run_dir.parent)
    count = _integer(config["workers"], 2, 4, "C parent worker slots")
    policy_raw = _bytes(inputs_dir / "tool_policy")
    if len(policy_raw) > 128 * 1024:
        raise CParallelError("C parent tool_policy exceeds the CAS byte limit")
    policy = _parse_json(policy_raw, "C parent tool_policy")
    if (type(policy) is not dict
            or type(policy.get("schema")) is not int or policy["schema"] != 2):
        raise CParallelError("C parent requires bounded inputs/tool_policy schema 2 for CAS repair")
    case_snapshot, input_snapshot = original._tree(case_dir), original._tree(inputs_dir)
    manifest = _input_json(_bytes(case_dir / "case.json"))
    prompt = _input_json(_bytes(inputs_dir / "arm_prompt"))
    if prompt.get("alternative") != "C" or prompt.get("mode") != "risk":
        raise CParallelError("C parent requires the common C/risk prompt")
    leader_stage = stages / "leader"
    slots = [{"task_id": f"c-task-{i}", "stage_dir": str(stages / "slots" / f"c-task-{i}")}
             for i in range(1, count + 1)]
    binding = {"profile": PROFILE, "case_dir": str(case_dir), "inputs_dir": str(inputs_dir),
               "case_inventory_sha256": _sha(_canonical(case_snapshot)),
               "inputs_inventory_sha256": _sha(_canonical(input_snapshot)),
               "stages_root": str(stages), "leader_stage": str(leader_stage), "slots": slots,
               "source_digests": _sources()}
    scalar_keys = CONFIG - {"workers", "max_output_tokens", "reviewer_max_output_tokens",
                           "max_model_turns", "leader_max_model_turns", "leader_max_output_tokens"}
    plan = {**{key: config[key] for key in scalar_keys}, "schema": 1,
            "execution_profile": "parent_analysis_wave_v1", "functions": _functions(),
            "context": _canonical({"parent_binding": binding, "public_case_manifest": manifest,
                                     "common_arm_prompt": prompt,
                                     "facts_status": "common_public_sources_not_independently_verified"}).decode(),
            "bootstrap_manifest": {"path": str(stages / "metadata/bootstrap_manifest.json"), "sha256": "0" * 64},
            "leader": {"task_id": "leader", "role": "leader", "max_output_tokens": config["leader_max_output_tokens"],
                       "max_model_turns": config["leader_max_model_turns"],
                       "user": "Start with empty work. Read the common case sources and initialize the pending graph through the fixed method tool. Use no caller graph. Keep norms and all phases pending. Return a public artifact; never disclose private reasoning."},
            "workers": {"count": config["workers"], "max_output_tokens": config["max_output_tokens"],
                        "max_model_turns": config["max_model_turns"]},
            "reviewer": {"user": "Review only public worker artifacts and common case sources. Identify unsupported claims and unresolved norms; no tools, approval or phase advancement.",
                         "max_output_tokens": config["reviewer_max_output_tokens"]},
            "journal_roots": [str(stages)]}
    engine._validate_plan(plan)
    if stages.exists() or stages.is_symlink():
        raise FileExistsError("C parent stages already exist")
    stages.mkdir(mode=0o700)
    metadata = stages / "metadata"
    metadata.mkdir(mode=0o700)
    leader_stage.mkdir(mode=0o700)
    original._copy_tree(case_dir, leader_stage / "case", case_snapshot)
    original._copy_tree(inputs_dir, leader_stage / "inputs", input_snapshot)
    (leader_stage / "work").mkdir(mode=0o700)
    _new_private_file(leader_stage / "stage.json", _canonical({
        "schema": "c_parent_bootstrap_stage.v1", "task_id": "leader", "case_id": manifest["case_id"]}))
    (stages / "slots").mkdir(mode=0o700)
    for slot in slots:
        stage = Path(slot["stage_dir"])
        stage.mkdir(mode=0o700)
        (stage / "work").mkdir(mode=0o700)
    method_tool, analysis_tool = metadata / "leader-method.py", metadata / "analysis-tool.py"
    build_tool(method_tool)
    build_analysis_tool(analysis_tool)
    spec = {"task_id": "leader", "stage_dir": str(leader_stage), "functions": [
        {"name": "development_method", "executable": str(method_tool), "profile": "workspace"},
        {"name": "development_analysis", "executable": str(analysis_tool), "profile": "analysis_readonly"}]}
    plan["bootstrap_manifest"] = prepare_parent_broker_manifest(stages, spec, slots)
    guard_c_parent(plan, {"phase": "bootstrap", "transition": None}, None)
    return engine.prepare_parent_analysis(run_dir, plan, admission_root=admission_root)


def guard_c_parent(plan: dict, state: dict, broker) -> None:
    del broker
    binding = _binding(plan)
    if binding["source_digests"] != _sources():
        raise CParallelError("C parent source closure changed")
    for label in ("case", "inputs"):
        if _sha(_canonical(original._tree(Path(binding[f"{label}_dir"])))) != binding[f"{label}_inventory_sha256"]:
            raise CParallelError("C parent common source changed")
    transition = state.get("transition")
    if state.get("phase") == "wave" and transition is None:
        raise CParallelError("C parent wave lacks its frozen bootstrap transition")
    if transition is not None:
        raw = _bytes(Path(transition["transition_path"]))
        if _sha(raw) != transition["transition_sha256"]:
            raise CParallelError("C parent transition changed")
        record = _input_json(raw)
        if record.get("seed") != transition["seed"] or record.get("wave_plan") != transition["wave_plan"]:
            raise CParallelError("C parent transition descriptor differs from its retained bytes")
        seed = transition["seed"]
        for name in ("proposal", "state", "leader_artifact"):
            if _sha(_bytes(Path(seed[f"{name}_path"]))) != seed[f"{name}_sha256"]:
                raise CParallelError("C parent frozen seed changed")
        _validate_seed(plan, seed)
        require_analysis_binding(transition["wave_plan"])
        original._guard(transition["wave_plan"])


def _validate_seed(plan: dict, seed: dict) -> dict:
    binding = _binding(plan)
    proposal = _input_json(_bytes(Path(seed["proposal_path"])))
    case_id = _input_json(_bytes(Path(binding["case_dir"]) / "case.json"))["case_id"]
    if proposal.get("case_id") != case_id:
        raise CParallelError("C parent seed case identity changed")
    nodes = core.validate_case(proposal)
    if any(node["status"] != "pending" for node in nodes.values()):
        raise CParallelError("C parent bootstrap nodes must all remain pending")
    norm_ids = [key for key, node in nodes.items() if node["kind"] == "normative"]
    if not any(node["kind"] == "requirement" and node["phase"] == "engineering"
               and set(norm_ids) & set(core.closure_versions(nodes, [key])) for key, node in nodes.items()):
        raise CParallelError("C parent bootstrap lacks a pending normative engineering dependency")
    expected = {"schema": 1, "case_id": case_id, "mode": "risk", "nodes": nodes,
                "phase_status": {phase: "not_started" for phase in core.PHASES}, "accepted_versions": {},
                "history": [{"seq": 1, "action": "init", "source": str(Path(binding["leader_stage"]) / "work/proposal.json")}]}
    actual = _state(_bytes(Path(seed["state_path"])))
    if actual != expected:
        raise CParallelError("C parent seed differs from the actual pending initialization")
    return actual


def bootstrap_to_wave(plan: dict, state: dict, broker, context, guard) -> dict:
    guard()
    snapshot = broker.bootstrap_snapshot()
    binding = _binding(plan)
    work = Path(binding["leader_stage"]) / "work"
    init_ops = [op for op in snapshot["operations"] if op.get("profile") == "workspace"
                and type(op.get("request")) is dict and op["request"].get("op") == "init"]
    if len(init_ops) != 1:
        raise CParallelError("C parent requires exactly one real bootstrap init operation")
    operation = init_ops[0]
    output = operation.get("output_json")
    state_raw, proposal_raw = _bytes(work / "method_state.json"), _bytes(work / "proposal.json")
    if (operation["terminal"]["status"] != "success" or type(output) is not dict or output.get("ok") is not True
            or output.get("method_state_sha256") != _sha(state_raw)
            or output.get("proposal_sha256") != _sha(proposal_raw)
            or _input_json(proposal_raw) != {"case_id": _input_json(_bytes(Path(binding["case_dir"]) / "case.json"))["case_id"],
                                           "nodes": operation["request"].get("nodes")}):
        raise CParallelError("C parent seed is not bound to the successful init tool receipt")
    run_dir = context.directory.parent
    leader_path = run_dir / "artifacts/leader.json"
    leader_raw, leader_artifact = _bytes(leader_path), _read_json(leader_path)
    if (set(leader_artifact) != {"task_id", "role", "text", "artifact_sha256"}
            or leader_artifact["task_id"] != "leader" or leader_artifact["role"] != "leader"
            or type(leader_artifact["text"]) is not str or not leader_artifact["text"].strip()
            or leader_artifact["artifact_sha256"] != _sha(_canonical({k: v for k, v in leader_artifact.items() if k != "artifact_sha256"}))):
        raise CParallelError("C parent leader has no valid final public artifact")
    seed = {"proposal_path": str(run_dir / "seed/proposal.json"), "proposal_sha256": _sha(proposal_raw),
            "state_path": str(run_dir / "seed/method_state.json"), "state_sha256": _sha(state_raw),
            "leader_artifact_path": str(run_dir / "seed/leader_artifact.json"), "leader_artifact_sha256": _sha(leader_raw),
            "init_request_id": operation["request_id"], "init_tool_ordinal": operation["global_ordinal"],
            "init_receipt_sha256": _sha(_canonical(operation["terminal"])), "origin": "sealed_bootstrap_init"}
    init_model_receipt = _read_json(run_dir / "receipts" / f"{operation['request_id']}.json")
    seed["init_payload_sha256"] = init_model_receipt["payload_sha256"]
    seed["init_response_sha256"] = init_model_receipt["response_sha256"]
    # Validate retained live bytes before materializing any branch or frozen seed.
    live_seed = {**seed, "proposal_path": str(work / "proposal.json"), "state_path": str(work / "method_state.json")}
    graph = _validate_seed(plan, live_seed)
    selected = select_independent_work(graph, plan["workers"]["count"])
    for path, raw in ((Path(seed["proposal_path"]), proposal_raw), (Path(seed["state_path"]), state_raw),
                      (Path(seed["leader_artifact_path"]), leader_raw)):
        guard()
        _new_private_file(path, raw)
    leader_files = []
    archive = run_dir / "seed/leader-work"
    guard()
    archive.mkdir(mode=0o700)
    for item in snapshot["work"]["files"]:
        guard()
        raw = _bytes(work / item["path"])
        if _sha(raw) != item["sha256"] or len(raw) != item["bytes"]:
            raise CParallelError("C parent bootstrap workspace changed during freeze")
        target = archive / item["path"]
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _new_private_file(target, raw)
        leader_files.append({"path": str(target), "sha256": _sha(raw), "bytes": len(raw)})
    seed["leader_work_files"] = leader_files
    specs, tasks = [], []
    case_snapshot = original._tree(Path(binding["case_dir"]))
    inputs_snapshot = original._tree(Path(binding["inputs_dir"]))
    stages = Path(binding["stages_root"])
    for slot, entry in zip(binding["slots"], selected, strict=True):
        guard()
        stage, task_id = Path(slot["stage_dir"]), slot["task_id"]
        if list((stage / "work").iterdir()):
            raise CParallelError("C parent future branch work is not empty")
        original._copy_tree(Path(binding["case_dir"]), stage / "case", case_snapshot)
        guard()
        original._copy_tree(Path(binding["inputs_dir"]), stage / "inputs", inputs_snapshot)
        guard()
        _new_private_file(stage / "work/method_state.json", state_raw)
        _new_private_file(stage / "stage.json", _canonical({"schema": "c_parent_analysis_branch.v1", "task_id": task_id,
            "case_id": graph["case_id"], "base_state_sha256": _sha(state_raw), "owned_node_ids": [entry["id"]]}))
        method = stages / "metadata" / f"{task_id}-method.py"
        guard()
        build_branch_tool(method, [entry["id"]])
        specs.append({"task_id": task_id, "stage_dir": str(stage), "owned_node_ids": [entry["id"]], "functions": [
            {"name": "development_method", "executable": str(method), "profile": "workspace"},
            {"name": "development_analysis", "executable": str(stages / "metadata/analysis-tool.py"), "profile": "analysis_readonly"}]})
        tasks.append({"task_id": task_id, "role": "c-worker-" + task_id.removeprefix("c-task-"),
                      "owned_node_ids": [entry["id"]], "max_output_tokens": plan["workers"]["max_output_tokens"],
                      "max_model_turns": plan["workers"]["max_model_turns"],
                      "user": f"Investigate owned node {entry['id']} using the common public sources and leader public artifact. Work privately; write/repair your own analysis.py and invoke readonly analysis. Keep norms pending. No init or phase advancement. Return a public artifact."})
    guard()
    branches = prepare_analysis_branch_manifest(stages, specs)
    c_binding = {"profile": "c_private_tools_v2", "base_state_path": seed["state_path"], "base_state_sha256": seed["state_sha256"],
                 "case_dir": binding["case_dir"], "inputs_dir": binding["inputs_dir"],
                 "case_inventory_sha256": binding["case_inventory_sha256"], "inputs_inventory_sha256": binding["inputs_inventory_sha256"],
                 "source_digests": binding["source_digests"]}
    common = {"binding": c_binding, "prototype_state": graph, "leader_artifact": leader_artifact, "bootstrap_seed": seed,
              "public_case_manifest": _input_json(_bytes(Path(binding["case_dir"]) / "case.json")),
              "common_arm_prompt": _input_json(_bytes(Path(binding["inputs_dir"]) / "arm_prompt")),
              "facts_status": "model_generated_graph_pending_not_independently_verified"}
    wave_plan = {key: plan[key] for key in ("model", "effort", "price_profile", "limit_tokens", "max_model_requests",
                                           "cost_limit_micro_usd", "active_limit_seconds", "max_tool_calls", "tool_wall_seconds")}
    wave_plan.update(schema=2, execution_profile="parallel_tool_wave_v2", run_id="tool-wave-" + plan["run_id"].removeprefix("parent-wave-"),
                     context=_canonical(common).decode(), tasks=tasks, functions=plan["functions"], reviewer=plan["reviewer"], branch_manifest=branches)
    wave_plan = bind_analysis_plan(wave_plan)
    guard()
    transition_path = stages / "metadata/transition.json"
    transition = {"schema": 1, "classification": "development_c_parent_bootstrap_transition_unsealed",
                  "bootstrap_manifest": plan["bootstrap_manifest"], "branch_manifest": branches,
                  "first_worker_ordinal": len(snapshot["operations"]) + 1,
                  "leader_work_sha256": _sha(_canonical(snapshot["work"])), "leader_state_sha256": _sha(state_raw),
                  "parent_plan_sha256": state["plan_sha256"], "seed": seed, "wave_plan": wave_plan}
    _new_private_file(transition_path, _canonical(transition))
    # The parent immediately activates this descriptor under its handoff guard.
    return {"wave_plan": wave_plan, "branch_manifest": branches, "transition_path": str(transition_path),
            "transition_sha256": _sha(_bytes(transition_path)), "seed": seed}


def merge_c_parent(wave_plan: dict, state: dict, broker, context, guard) -> dict:
    result = analysis.merge_c_analysis_branches(wave_plan, state, broker.wave_view(), context, guard)
    guard()
    seed = _input_json(wave_plan["context"].encode())["bootstrap_seed"]
    receipt = context.directory.parent / "merge/parent_receipt.json"
    _new_private_file(receipt, _canonical({
        "schema": 1, "classification": "development_c_parent_analysis_merge_unsealed",
        "seed": seed, "seed_origin": "sealed_bootstrap_init", "caller_graph_required": False,
        "private_wave_receipt_scope": "D116 branch API consumed the parent frozen bootstrap seed",
        "analysis_receipt_sha256": result["analysis_receipt_sha256"],
        "empirical_support_verified": False, "comparable_development_cell": False}))
    guard()
    return {**result, "caller_graph_required": False, "seed_origin": "sealed_bootstrap_init",
            "comparable_development_cell": False, "parent_receipt_path": str(receipt),
            "parent_receipt_sha256": _sha(_bytes(receipt))}


def execute_c_parent_analysis_step(run_dir: Path, transports_by_task: dict, *, expected_checkpoint: str) -> dict:
    import managed_parent_analysis as engine
    return engine.execute_parent_analysis_step(
        Path(run_dir), transports_by_task, expected_checkpoint=expected_checkpoint,
        guard=guard_c_parent, bootstrap_to_wave=bootstrap_to_wave, merge=merge_c_parent)


def read_c_parent_analysis_status(run_dir: Path) -> dict:
    import managed_parent_analysis as engine
    return engine.read_parent_analysis_status(Path(run_dir), guard=guard_c_parent)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    for name in ("case-dir", "inputs-dir", "config", "admission-root"):
        prepare.add_argument("--" + name, type=Path, required=name != "admission-root")
    for name in ("prepare", "status", "step"):
        command = prepare if name == "prepare" else sub.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
    step = sub.choices["step"]
    step.add_argument("--expected-checkpoint", required=True)
    step.add_argument("--local-http-fixture", "--transports", dest="local_http_fixture", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_c_parent_analysis(args.run_dir, args.case_dir, args.inputs_dir,
                                               _input_json(_bytes(args.config)), admission_root=args.admission_root)
        elif args.command == "status":
            result = read_c_parent_analysis_status(args.run_dir)
        else:
            address = urlsplit(args.local_http_fixture)
            if (address.scheme != "http" or address.hostname != "127.0.0.1" or address.port is None
                    or address.username is not None or address.password is not None
                    or address.query or address.fragment or address.path not in {"", "/v1"}):
                raise CParallelError("fixture must use HTTP at 127.0.0.1 with an explicit port")
            plan = _read_json(args.run_dir / "plan.json")
            phase = read_c_parent_analysis_status(args.run_dir)["phase"]
            ids = ["leader"] if phase == "bootstrap" else ["reviewer"] + [
                f"c-task-{i}" for i in range(1, plan["workers"]["count"] + 1)]
            transports = {key: OpenAIResponsesHTTP("public-synthetic-no-credential", base_url=args.local_http_fixture) for key in ids}
            result = execute_c_parent_analysis_step(args.run_dir, transports, expected_checkpoint=args.expected_checkpoint)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}", "formal_cell_executed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
