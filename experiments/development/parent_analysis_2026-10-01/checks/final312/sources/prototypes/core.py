"""Small, dependency-free workflow kernel shared by the two comparison prototypes.

Fixture claims are inputs to a workflow experiment, not verified field evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


PHASES = ("philosophy", "science", "engineering", "validation")
KINDS = {"problem", "assumption", "normative", "evidence", "requirement", "test_result"}
STATUSES = {"supported", "pending", "contradicted"}


class WorkflowError(Exception):
    pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkflowError(f"cannot read JSON at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkflowError("JSON root must be an object")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def validate_case(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(case.get("case_id"), str) or not case["case_id"]:
        raise WorkflowError("case_id must be a nonempty string")
    items = case.get("nodes")
    if not isinstance(items, list) or not items:
        raise WorkflowError("nodes must be a nonempty list")
    nodes: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise WorkflowError("each node must be an object")
        node_id = item.get("id")
        if not isinstance(node_id, str) or not node_id or node_id in nodes:
            raise WorkflowError(f"node id must be unique and nonempty: {node_id!r}")
        if item.get("kind") not in KINDS or item.get("phase") not in PHASES:
            raise WorkflowError(f"invalid kind or phase for {node_id}")
        if item.get("status") not in STATUSES:
            raise WorkflowError(f"invalid status for {node_id}")
        if item["kind"] == "normative" and item["status"] != "pending":
            raise WorkflowError(f"normative node {node_id} must start pending approval")
        if not isinstance(item.get("claim"), str) or not item["claim"].strip():
            raise WorkflowError(f"claim missing for {node_id}")
        deps = item.get("depends_on")
        if not isinstance(deps, list) or any(not isinstance(dep, str) for dep in deps):
            raise WorkflowError(f"depends_on must be a list of ids for {node_id}")
        risk = item.get("risk", {"impact": 3, "uncertainty": 3, "effort": 3})
        if not isinstance(risk, dict) or any(
            not isinstance(risk.get(key), int) or isinstance(risk.get(key), bool)
            or not 1 <= risk[key] <= 5 for key in ("impact", "uncertainty", "effort")
        ):
            raise WorkflowError(f"risk requires impact, uncertainty and effort integers 1-5 for {node_id}")
        nodes[node_id] = {
            "id": node_id,
            "kind": item["kind"],
            "phase": item["phase"],
            "status": item["status"],
            "claim": item["claim"],
            "depends_on": deps,
            "risk": risk,
            "version": 1,
            "stale": False,
        }
    for node_id, node in nodes.items():
        for dep in node["depends_on"]:
            if dep not in nodes:
                raise WorkflowError(f"unknown dependency {dep} in {node_id}")
            if dep == node_id:
                raise WorkflowError(f"self dependency in {node_id}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise WorkflowError(f"dependency cycle at {node_id}")
        if node_id in visited:
            return
        visiting.add(node_id)
        for dep in nodes[node_id]["depends_on"]:
            visit(dep)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in nodes:
        visit(node_id)
    for phase in PHASES:
        if not any(node["phase"] == phase for node in nodes.values()):
            raise WorkflowError(f"phase {phase} has no node")
    return nodes


def ready(node: dict[str, Any]) -> bool:
    expected = "approved" if node["kind"] == "normative" else "supported"
    return node["status"] == expected and not node["stale"]


def closure_ready(nodes: dict[str, dict[str, Any]], node_id: str) -> bool:
    node = nodes[node_id]
    return ready(node) and all(closure_ready(nodes, dep) for dep in node["depends_on"])


def closure_versions(nodes: dict[str, dict[str, Any]], node_ids: list[str]) -> dict[str, int]:
    versions: dict[str, int] = {}

    def collect(node_id: str) -> None:
        node = nodes[node_id]
        versions[node_id] = node["version"]
        for dep in node["depends_on"]:
            if dep not in versions:
                collect(dep)

    for node_id in node_ids:
        collect(node_id)
    return versions


def descendants(nodes: dict[str, dict[str, Any]], source: str) -> set[str]:
    seen: set[str] = set()
    frontier = [source]
    while frontier:
        current = frontier.pop()
        for node_id, node in nodes.items():
            if current in node["depends_on"] and node_id not in seen:
                seen.add(node_id)
                frontier.append(node_id)
    return seen


def risk_plan(nodes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Prioritize open work; waves indicate possible independence, not agent runs."""
    open_ids = {node_id for node_id, node in nodes.items() if not ready(node)}

    def entry(node_id: str) -> dict[str, Any]:
        node = nodes[node_id]
        risk = node["risk"]
        if node["kind"] == "normative":
            action = "approve"
        elif node["status"] != "supported":
            action = "revise"
        else:
            action = "review"
        return {
            "id": node_id,
            "action": action,
            "score": round(risk["impact"] * risk["uncertainty"] / risk["effort"], 2),
            "blocked_by": sorted(dep for dep in node["depends_on"] if not closure_ready(nodes, dep)),
        }

    entries = {node_id: entry(node_id) for node_id in open_ids}
    queue = sorted(entries.values(), key=lambda row: (-row["score"], row["id"]))
    remaining = set(open_ids)
    waves: list[list[str]] = []
    while remaining:
        wave = sorted(
            (node_id for node_id in remaining
             if not any(dep in remaining for dep in nodes[node_id]["depends_on"])),
            key=lambda node_id: (-entries[node_id]["score"], node_id),
        )
        if not wave:
            raise WorkflowError("open-work dependency cycle")
        waves.append(wave)
        remaining.difference_update(wave)
    return {"work_queue": queue, "potential_waves": waves}


def audit(state: dict[str, Any]) -> dict[str, Any]:
    nodes = state["nodes"]
    accepted = [phase for phase in PHASES if state["phase_status"][phase] == "accepted"]
    unsafe = [
        phase for phase in accepted
        if (
            any(
                not closure_ready(nodes, node_id)
                for node_id, node in nodes.items() if node["phase"] == phase
            )
            or any(
                nodes[node_id]["version"] != version
                for node_id, version in state["accepted_versions"].get(phase, {}).items()
            )
        )
    ]
    result = {
        "case_id": state["case_id"],
        "mode": state["mode"],
        "phase_status": state["phase_status"],
        "accepted_phases": accepted,
        "unsafe_accepted_phases": unsafe,
        "stale_nodes": sorted(node_id for node_id, node in nodes.items() if node["stale"]),
        "pending_normative": sorted(
            node_id for node_id, node in nodes.items()
            if node["kind"] == "normative" and node["status"] != "approved"
        ),
        "history_length": len(state["history"]),
    }
    if state["mode"] == "risk":
        result.update(risk_plan(nodes))
    return result


def record(state: dict[str, Any], action: str, **details: Any) -> None:
    state["history"].append({"seq": len(state["history"]) + 1, "action": action, **details})


def run(mode: str, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{mode} workflow prototype")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--case", required=True, type=Path)
    init.add_argument("--state", required=True, type=Path)
    for command in ("approve", "advance", "revise", "review", "status", "plan"):
        sub.add_parser(command).add_argument("--state", required=True, type=Path)
    sub.choices["approve"].add_argument("--id", required=True)
    sub.choices["advance"].add_argument("--phase", required=True, choices=PHASES)
    sub.choices["revise"].add_argument("--id", required=True)
    sub.choices["revise"].add_argument("--status", required=True, choices=sorted(STATUSES))
    sub.choices["revise"].add_argument("--reason", required=True)
    sub.choices["review"].add_argument("--id", required=True)
    sub.choices["plan"].add_argument("--budget", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            if args.state.exists():
                raise WorkflowError(f"state already exists: {args.state}")
            case = read_json(args.case)
            nodes = validate_case(case)
            state = {
                "schema": 1,
                "case_id": case["case_id"],
                "mode": mode,
                "nodes": nodes,
                "phase_status": {phase: "not_started" for phase in PHASES},
                "accepted_versions": {},
                "history": [],
            }
            record(state, "init", source=str(args.case))
            write_json(args.state, state)
            result = {"ok": True, "action": "init", "case_id": case["case_id"]}
        else:
            state = read_json(args.state)
            if state.get("schema") != 1 or state.get("mode") != mode:
                raise WorkflowError("state schema or workflow mode mismatch")
            nodes = state["nodes"]
            if args.command == "status":
                result = {"ok": True, "action": "status", **audit(state)}
            elif args.command == "plan":
                if mode != "risk" or args.budget < 1:
                    raise WorkflowError("plan requires risk mode and a positive budget")
                plan = risk_plan(nodes)
                actionable = [row for row in plan["work_queue"] if not row["blocked_by"]]
                result = {"ok": True, "action": "plan", "budget": args.budget,
                          "selected": actionable[:args.budget],
                          "deferred_count": len(plan["work_queue"]) - min(args.budget, len(actionable)),
                          "potential_waves": plan["potential_waves"]}
            elif args.command == "approve":
                node = nodes.get(args.id)
                if node is None or node["kind"] != "normative":
                    raise WorkflowError(f"normative node not found: {args.id}")
                if node["status"] == "approved" and not node["stale"]:
                    raise WorkflowError(f"normative node already approved: {args.id}")
                if mode in ("graph", "risk") and not all(closure_ready(nodes, dep) for dep in node["depends_on"]):
                    raise WorkflowError(f"dependencies blocked for normative node {args.id}")
                node["status"] = "approved"
                node["stale"] = False
                node["version"] += 1
                record(state, "approve", node=args.id, version=node["version"])
                write_json(args.state, state)
                result = {"ok": True, "action": "approve", "id": args.id}
            elif args.command == "advance":
                index = PHASES.index(args.phase)
                prior = [phase for phase in PHASES[:index] if state["phase_status"][phase] != "accepted"]
                if prior and mode != "risk":
                    raise WorkflowError(f"prior phases not accepted: {', '.join(prior)}")
                phase_nodes = [(node_id, node) for node_id, node in nodes.items() if node["phase"] == args.phase]
                blocked = [
                    node_id for node_id, node in phase_nodes
                    if not (closure_ready(nodes, node_id) if mode in ("graph", "risk") else ready(node))
                ]
                if blocked:
                    raise WorkflowError(f"blocked nodes in {args.phase}: {', '.join(blocked)}")
                state["phase_status"][args.phase] = "accepted"
                state["accepted_versions"][args.phase] = closure_versions(
                    nodes, [node_id for node_id, _ in phase_nodes]
                )
                record(state, "advance", phase=args.phase)
                write_json(args.state, state)
                result = {"ok": True, "action": "advance", "phase": args.phase}
            elif args.command == "revise":
                node = nodes.get(args.id)
                if node is None or node["kind"] == "normative":
                    raise WorkflowError(f"revisable nonnormative node not found: {args.id}")
                if not args.reason.strip():
                    raise WorkflowError("revision reason must be nonempty")
                node["status"] = args.status
                node["version"] += 1
                affected = {args.id}
                if mode in ("graph", "risk"):
                    affected.update(descendants(nodes, args.id))
                    for child_id in affected - {args.id}:
                        nodes[child_id]["stale"] = True
                        if nodes[child_id]["kind"] == "normative":
                            nodes[child_id]["status"] = "pending"
                for phase in PHASES:
                    if state["phase_status"][phase] == "accepted" and any(
                        nodes[node_id]["phase"] == phase for node_id in affected
                    ):
                        state["phase_status"][phase] = "needs_review"
                record(state, "revise", node=args.id, status=args.status,
                       reason=args.reason, affected=sorted(affected))
                write_json(args.state, state)
                result = {"ok": True, "action": "revise", "id": args.id,
                          "affected": sorted(affected)}
            elif args.command == "review":
                if mode not in ("graph", "risk"):
                    raise WorkflowError("review is available only in graph or risk mode")
                node = nodes.get(args.id)
                if node is None or not node["stale"]:
                    raise WorkflowError(f"stale node not found: {args.id}")
                if node["kind"] == "normative":
                    raise WorkflowError(f"normative node requires explicit approval: {args.id}")
                if not ready({**node, "stale": False}) or not all(
                    closure_ready(nodes, dep) for dep in node["depends_on"]
                ):
                    raise WorkflowError(f"dependencies blocked for review of {args.id}")
                node["stale"] = False
                node["version"] += 1
                record(state, "review", node=args.id, version=node["version"])
                write_json(args.state, state)
                result = {"ok": True, "action": "review", "id": args.id}
            else:
                raise AssertionError(args.command)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (WorkflowError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    print("Invoke sequential.py or graph.py", file=sys.stderr)
    raise SystemExit(2)
