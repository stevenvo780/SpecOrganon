"""Run identical disturbances against both CLIs in fresh, isolated states.

Every action is a separate OS process. The optional repair step is intentionally
mode-specific because the two architectures require different recovery actions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
MODES = ("sequential", "graph", "risk")
REPAIR = {
    "sequential": [
        {"op": "revise", "id": "E", "status": "supported", "reason": "Fixture claim corrected for recovery test"},
        {"op": "advance", "phase": "science"},
        {"op": "advance", "phase": "engineering"},
        {"op": "advance", "phase": "validation"},
    ],
    "graph": [
        {"op": "revise", "id": "E", "status": "supported", "reason": "Fixture claim corrected for recovery test"},
        {"op": "advance", "phase": "science"},
        {"op": "review", "id": "R"},
        {"op": "advance", "phase": "engineering"},
        {"op": "review", "id": "V"},
        {"op": "advance", "phase": "validation"},
    ],
    "risk": [
        {"op": "revise", "id": "E", "status": "supported", "reason": "Fixture claim corrected for recovery test"},
        {"op": "advance", "phase": "science"},
        {"op": "review", "id": "R"},
        {"op": "advance", "phase": "engineering"},
        {"op": "review", "id": "V"},
        {"op": "advance", "phase": "validation"},
    ],
}


def arguments(action: dict[str, Any], state: Path) -> list[str]:
    op = action["op"]
    cmd = [op, "--state", str(state)]
    if op in ("approve", "revise", "review"):
        cmd += ["--id", action["id"]]
    if op == "advance":
        cmd += ["--phase", action["phase"]]
    if op == "revise":
        cmd += ["--status", action["status"], "--reason", action["reason"]]
    return cmd


def invoke(mode: str, argv: list[str]) -> dict[str, Any]:
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(HERE / f"{mode}.py"), *argv],
        cwd=HERE,
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        payload = {"parse_error": proc.stdout, "stderr": proc.stderr}
    return {"command": argv[0], "exit_code": proc.returncode,
            "elapsed_ms": elapsed_ms, "response": payload}


def one(scenario: dict[str, Any], mode: str, scratch: Path) -> dict[str, Any]:
    state = scratch / f"{scenario['id']}.{mode}.json"
    case = HERE / "cases" / scenario["case"]
    events = [invoke(mode, ["init", "--case", str(case), "--state", str(state)])]
    if events[0]["exit_code"] == 0:
        for action in scenario["actions"]:
            events.append(invoke(mode, arguments(action, state)))
        if scenario.get("repair"):
            for action in REPAIR[mode]:
                events.append(invoke(mode, arguments(action, state)))
        events.append(invoke(mode, ["status", "--state", str(state)]))
    status = events[-1]["response"] if events[-1]["command"] == "status" else None
    failed = [
        {"command": event["command"], "error": event["response"].get("error", event["response"])}
        for event in events if event["exit_code"] != 0
    ]
    return {
        "scenario": scenario["id"],
        "mode": mode,
        "commands": len(events),
        "repair_commands": len(REPAIR[mode]) if scenario.get("repair") else 0,
        "failed_commands": failed,
        "wall_ms": round(sum(event["elapsed_ms"] for event in events), 3),
        "state_bytes": state.stat().st_size if state.exists() else 0,
        "status": status,
        "events": events,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="optional JSON record path")
    args = parser.parse_args()
    scenarios = json.loads((HERE / "scenarios.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="workflow-prototypes-") as temp:
        results = [one(scenario, mode, Path(temp))
                   for scenario in scenarios for mode in MODES]
    payload = {
        "comparison_scope": "synthetic workflow mechanics only",
        "python": sys.version.split()[0],
        "scenarios": len(scenarios),
        "inputs_sha256": {
            str(path.relative_to(HERE)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                HERE / "core.py",
                HERE / "sequential.py",
                HERE / "graph.py",
                HERE / "risk.py",
                HERE / "compare.py",
                HERE / "scenarios.json",
                HERE / "cases" / "cold_chain.json",
                HERE / "cases" / "invalid_dependency.json",
            )
        },
        "results": results,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = [
        {
            "scenario": result["scenario"], "mode": result["mode"],
            "failed": len(result["failed_commands"]),
            "accepted": len(result["status"]["accepted_phases"]) if result["status"] else None,
            "unsafe_accepted": result["status"]["unsafe_accepted_phases"] if result["status"] else None,
            "stale": result["status"]["stale_nodes"] if result["status"] else None,
            "repair_commands": result["repair_commands"],
            "wall_ms": result["wall_ms"],
        }
        for result in results
    ]
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
