"""Write two pending items through an installed CLI, after a named FIFO barrier.

One real native agent invokes this helper per disjoint role. Keys, approvals,
reviews and field facts are absent. Process overlap is induced by the barrier
and is not a measurement of model speed, quality or independent key custody.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def run(case: Path, barrier: Path, output: Path, role: str) -> None:
    if output.exists():
        raise ValueError("writer destination must be new")
    output.mkdir(parents=True)
    cli = Path(sys.executable).parent / "organon"
    if not cli.is_file() or sys.prefix == sys.base_prefix:
        raise ValueError("use a wheel installed in a virtual environment")
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("ORGANON_") and key not in {"PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE"}}
    env["PYTHONNOUSERSITE"] = "1"
    started = time.monotonic_ns()
    origin = subprocess.run([sys.executable, "-I", "-c", "import specorganon; print(specorganon.__file__)"],
                            env=env, capture_output=True, text=True, check=True)
    if not Path(origin.stdout.strip()).resolve().is_relative_to(Path(sys.prefix).resolve()):
        raise ValueError("installed package origin is outside this virtual environment")
    ready = {"pid": os.getpid(), "role": role, "started_monotonic_ns": started,
             "package_origin": origin.stdout.strip(), "waiting_on": str(barrier)}
    (output / "ready.json").write_text(json.dumps(ready, indent=2) + "\n")
    with barrier.open("rb", buffering=0) as stream:
        if stream.read(1) != b"x":
            raise ValueError("barrier did not provide the registered release byte")
    released = time.monotonic_ns()
    actor = "agent:native-D103-" + role
    ids = ("a_" + role, "b_" + role)
    calls = []
    for id, kind, text in ((ids[0], "actor", "Synthetic native writer " + role + "; no human authority"),
                            (ids[1], "boundary", "Only installed pending-item coordination; no field intervention")):
        refs = ["p_native"]
        deps = {"p_native": 1}
        if kind == "boundary":
            refs.append(ids[0])
            deps[ids[0]] = 1
        argv = [str(cli), "put", str(case), id, "--kind", kind, "--text", text, "--actor", actor,
                "--expected-version", "0", "--expected-deps", json.dumps(deps)]
        for ref in refs:
            argv.extend(["--ref", ref])
        call_start = time.monotonic_ns()
        result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=30)
        record = {"argv": argv, "exit": result.returncode, "stdout": result.stdout, "stderr": result.stderr,
                  "start_monotonic_ns": call_start, "end_monotonic_ns": time.monotonic_ns()}
        calls.append(record)
        (output / "calls.json").write_text(json.dumps(calls, indent=2) + "\n")
        if result.returncode != 0:
            raise ValueError("guarded installed CLI call failed; original streams retained")
        event = json.loads(result.stdout)
        if event["kind"] != "item_put" or event["payload"]["id"] != id or event["actor"] != actor:
            raise ValueError("installed CLI returned an unexpected event")
    receipt = {**ready, "released_monotonic_ns": released, "finished_monotonic_ns": time.monotonic_ns(),
               "ids": list(ids), "actor": actor, "calls": len(calls), "human_approvals": 0,
               "cli_sha256": hashlib.sha256(cli.read_bytes()).hexdigest(),
               "helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "field_scope": False, "model_or_effort_authenticated": False}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"state": "passed", "role": role, "items": len(ids)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("barrier", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("role", choices=("A", "B"))
    args = parser.parse_args()
    run(args.case.absolute(), args.barrier.absolute(), args.output.absolute(), args.role)
