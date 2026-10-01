"""Opt-in risk-directed exploration; proposals do not mutate the method graph.

This development runner has a new identity, not a DEV solo/trio schedule cell.
It can use an explicitly selected transport, and never treats text as approval,
empirical support, or a completed evaluation of the methodology.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path
from urllib.parse import urlsplit

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from managed_parallel_wave import (  # noqa: E402
    execute_wave, prepare_wave, read_wave_status,
)
from managed_run_context import _path  # noqa: E402
from run_managed_conversation import _canonical, _read_json  # noqa: E402
from run_managed_response import OpenAIResponsesHTTP  # noqa: E402

CORE_PATH = SCRIPTS.parent / "prototypes" / "core.py"
spec = importlib.util.spec_from_file_location("specorganon_parallel_core", CORE_PATH)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
MAX_INPUT_BYTES = 16 * 1024 * 1024
CONFIG_KEYS = {
    "run_id", "model", "effort", "price_profile", "limit_tokens",
    "max_model_requests", "cost_limit_micro_usd", "active_limit_seconds",
    "workers", "max_output_tokens", "reviewer_max_output_tokens",
}
STATE_KEYS = {
    "schema", "case_id", "mode", "nodes", "phase_status", "accepted_versions", "history",
}
NODE_KEYS = {
    "id", "kind", "phase", "status", "claim", "depends_on", "risk", "version", "stale",
}


class CParallelError(ValueError):
    """No safe independent exploration can be launched from this snapshot."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _bytes(path: Path) -> bytes:
    path = _path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_INPUT_BYTES:
            raise CParallelError("bound input must be a regular file within its byte limit")
        parts, remaining = [], MAX_INPUT_BYTES + 1
        while remaining:
            part = os.read(fd, min(remaining, 65536))
            if not part:
                break
            parts.append(part)
            remaining -= len(part)
        raw = b"".join(parts)
        after = os.fstat(fd)
        if len(raw) > MAX_INPUT_BYTES or (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise CParallelError("bound input changed while reading")
        return raw
    finally:
        os.close(fd)


def _input_json(raw: bytes) -> dict:
    from run_managed_response import _reject_constant, _unique_pairs

    value = json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    if type(value) is not dict:
        raise CParallelError("input JSON must be an object")
    return value


def _state(raw: bytes) -> dict:
    value = _input_json(raw)
    if (type(value) is not dict or set(value) != STATE_KEYS
            or type(value["schema"]) is not int or value["schema"] != 1
            or value["mode"] != "risk" or type(value["nodes"]) is not dict
            or not 4 <= len(value["nodes"]) <= 64):
        raise CParallelError("C requires a bounded risk-mode prototype state")
    nodes = value["nodes"]
    initial = []
    for node_id, node in nodes.items():
        if (type(node) is not dict or set(node) != NODE_KEYS or node_id != node["id"]
                or type(node["version"]) is not int or node["version"] < 1
                or type(node["stale"]) is not bool
                or type(node["depends_on"]) is not list
                or len(set(node["depends_on"])) != len(node["depends_on"])
                or node["status"] not in core.STATUSES | {"approved"}
                or node["status"] == "approved"
                or node["kind"] == "normative" and node["status"] != "pending"):
            raise CParallelError("C node shape, version, dependencies or status is invalid")
        initial.append({**node, "status": "pending" if node["kind"] == "normative"
                        else node["status"]})
    core.validate_case({"case_id": value["case_id"], "nodes": initial})
    if (type(value["phase_status"]) is not dict
            or set(value["phase_status"]) != set(core.PHASES)
            or any(status not in {"not_started", "accepted", "needs_review"}
                   for status in value["phase_status"].values())
            or type(value["accepted_versions"]) is not dict
            or type(value["history"]) is not list):
        raise CParallelError("C phase or history shape is invalid")
    if core.audit(value)["unsafe_accepted_phases"]:
        raise CParallelError("C snapshot contains an unsafe accepted phase")
    return value


def select_independent_work(state: dict, workers: int) -> list[dict]:
    if type(workers) is not int or not 2 <= workers <= 4:
        raise CParallelError("C requires two to four independent workers")
    selected = [entry for entry in core.risk_plan(state["nodes"])["work_queue"]
                if not entry["blocked_by"] and entry["action"] != "approve"][:workers]
    if len(selected) != workers:
        raise CParallelError("insufficient eligible nonnormative work for a parallel wave")
    ids = {entry["id"] for entry in selected}
    if any(set(state["nodes"][entry["id"]]["depends_on"]) & ids for entry in selected):
        raise CParallelError("wave contains an internal dependency")
    return selected


def prepare_c_wave(run_dir: Path, state_path: Path, facts_path: Path, config: dict, *,
                   admission_root: Path | None = None) -> dict:
    if type(config) is not dict or set(config) != CONFIG_KEYS:
        raise CParallelError("C parallel config has missing or unsupported fields")
    state_raw, facts_raw = _bytes(state_path), _bytes(facts_path)
    state = _state(state_raw)
    selected = select_independent_work(state, config["workers"])
    facts = facts_raw.decode("utf-8")
    if not facts.strip() or "\x00" in facts:
        raise CParallelError("common factual input must be nonempty UTF-8 text")
    binding = {
        "profile": "c_risk_proposals_v1", "base_state_path": str(state_path),
        "base_state_sha256": _sha(state_raw), "facts_path": str(facts_path),
        "facts_sha256": _sha(facts_raw), "core_sha256": _sha(_bytes(CORE_PATH)),
        "wrapper_sha256": _sha(_bytes(Path(__file__))),
    }
    context = _canonical({"binding": binding, "prototype_state": state,
                          "common_facts": facts,
                          "facts_status": "caller_supplied_not_independently_verified"}).decode()
    tasks = [{
        "task_id": f"c-task-{i}", "role": f"c-worker-{i}",
        "owned_node_ids": [entry["id"]], "max_output_tokens": config["max_output_tokens"],
        "user": (
            f"Explore the {entry['action']} task for node {entry['id']} independently. "
            "Use the common facts, explain evidence, alternatives and uncertainty, and propose "
            "a revision or review artifact. You have no tools or write access. A proposal is "
            "not verified support, normative approval, or permission to advance a phase."
        ),
    } for i, entry in enumerate(selected, 1)]
    plan = {key: config[key] for key in CONFIG_KEYS - {
        "workers", "max_output_tokens", "reviewer_max_output_tokens",
    }}
    plan.update(schema=1, execution_profile="parallel_wave_v1", context=context, tasks=tasks,
                reviewer={"user": "Review only the proposed artifacts against the common facts. "
                          "Identify contradictions, missing evidence, risks and necessary corrections. "
                          "Do not approve norms or advance the method state.",
                          "max_output_tokens": config["reviewer_max_output_tokens"]})
    # Check the inputs again immediately before preparing; execution guards them
    # from the plan's pinned common context, without an unbound second manifest.
    _guard(plan)
    return prepare_wave(run_dir, plan, admission_root=admission_root)


def _guard(plan: dict) -> None:
    context = json.loads(plan["context"])
    binding = context["binding"]
    if binding["profile"] != "c_risk_proposals_v1":
        raise CParallelError("C context profile changed")
    current_raw = _bytes(Path(binding["base_state_path"]))
    current = _state(current_raw)
    pairs = ((current_raw, "base_state_sha256"),
             (_bytes(Path(binding["facts_path"])), "facts_sha256"),
             (_bytes(CORE_PATH), "core_sha256"),
             (_bytes(Path(__file__)), "wrapper_sha256"))
    if any(_sha(raw) != binding[key] for raw, key in pairs):
        raise CParallelError("C base, common facts, core or wrapper changed")
    if current != context["prototype_state"]:
        raise CParallelError("C common snapshot differs from its pinned base")
    selected = select_independent_work(current, len(plan["tasks"]))
    if [task["owned_node_ids"] for task in plan["tasks"]] != [[entry["id"]] for entry in selected]:
        raise CParallelError("C task eligibility or ownership changed")


def execute_c_wave(run_dir: Path, transports_by_task: dict, *,
                   expected_checkpoint: str) -> dict:
    plan = _read_json(run_dir / "plan.json")
    return execute_wave(run_dir, transports_by_task, expected_checkpoint=expected_checkpoint,
                        guard=lambda: _guard(plan))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--state", type=Path, required=True)
    prepare.add_argument("--facts", type=Path, required=True)
    prepare.add_argument("--config", type=Path, required=True)
    prepare.add_argument("--admission-root", type=Path)
    for name in ("prepare", "status", "execute"):
        command = prepare if name == "prepare" else sub.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
    execute = sub.choices["execute"]
    execute.add_argument("--expected-checkpoint", required=True)
    transport = execute.add_mutually_exclusive_group(required=True)
    transport.add_argument("--provider", choices=["openai"])
    transport.add_argument("--local-http-fixture", help="Explicit synthetic fixture at 127.0.0.1")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_c_wave(args.run_dir, args.state, args.facts,
                                    _input_json(_bytes(args.config)), admission_root=args.admission_root)
        elif args.command == "status":
            result = read_wave_status(args.run_dir)
        else:
            plan = _read_json(args.run_dir / "plan.json")
            if args.local_http_fixture:
                url = urlsplit(args.local_http_fixture)
                if (url.scheme != "http" or url.hostname != "127.0.0.1"
                        or url.username is not None or url.password is not None
                        or url.port is None or url.query or url.fragment
                        or url.path not in {"", "/v1"}):
                    raise CParallelError("fixture endpoint must be HTTP at 127.0.0.1 with an explicit port")
                # A public placeholder is not operator authentication. Never
                # read OPENAI_API_KEY for the explicitly synthetic transport.
                def make_transport():
                    return OpenAIResponsesHTTP("public-synthetic-no-credential",
                                               base_url=args.local_http_fixture)
            else:
                key = os.environ.get("OPENAI_API_KEY")
                if not key:
                    raise CParallelError("OPENAI_API_KEY is required for explicit provider execution")

                def make_transport():
                    return OpenAIResponsesHTTP(key)

            transports = {task["task_id"]: make_transport() for task in plan["tasks"]}
            transports["reviewer"] = make_transport()
            result = execute_c_wave(args.run_dir, transports,
                                    expected_checkpoint=args.expected_checkpoint)
            result["local_http_fixture"] = bool(args.local_http_fixture)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0 if result.get("state") != "indeterminate" else 2
    except (ValueError, OSError, KeyError, TypeError) as exc:
        # Report an error class, never provider credentials or response bodies.
        print(json.dumps({"classification": "development_c_parallel_unsealed",
                          "error": type(exc).__name__, "state": "rejected"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
