"""Write two pending items through an installed CLI, after a named FIFO barrier.

One real native agent invokes this helper per disjoint role. Keys, approvals,
reviews and field facts are absent. Process overlap is induced by the barrier
and is not a measurement of model speed, quality or independent key custody.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import sysconfig
import time
import zipfile


D102_WHEEL_SHA = "e155d010a17a1235f071da6b0d89c1773b5dc92295a85251873f1880c448390b"


def pin(raw: bytes) -> dict:
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def installed(wheel: Path) -> dict:
    if sys.prefix == sys.base_prefix:
        raise ValueError("use a wheel installed in a virtual environment")
    raw = wheel.read_bytes()
    if pin(raw)["sha256"] != D102_WHEEL_SHA:
        raise ValueError("wheel differs from frozen D102 bytes")
    purelib = Path(sysconfig.get_path("purelib")).resolve(strict=True)
    modules = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name in archive.namelist():
            if not name.startswith("specorganon/") or not name.endswith(".py"):
                continue
            path = purelib / name
            expected = archive.read(name)
            if (not stat.S_ISREG(path.lstat().st_mode)
                    or not path.resolve(strict=True).is_relative_to(purelib)
                    or path.read_bytes() != expected):
                raise ValueError("installed module differs from wheel: " + name)
            module_name = name[:-3].replace("/", ".").removesuffix(".__init__")
            module = importlib.import_module(module_name)
            if Path(module.__file__).resolve(strict=True) != path.resolve(strict=True):
                raise ValueError("module imported outside installed wheel: " + module_name)
            modules[module_name] = {"path": str(path), **pin(expected)}
    if len(modules) != 24:
        raise ValueError("expected all 24 D102 package modules")
    cli = Path(sys.executable).parent / "organon"
    if not cli.is_file() or not os.access(cli, os.X_OK):
        raise ValueError("installed CLI is missing")
    return {"python": sys.version, "executable": sys.executable, "wheel": pin(raw),
            "modules": modules, "cli": {"path": str(cli), **pin(cli.read_bytes())}}


def run(case: Path, barrier: Path, output: Path, role: str, wheel: Path,
        expected_case_id: str, expected_project_sha256: str) -> None:
    if output.exists() or output.is_symlink():
        raise ValueError("writer destination must be new")
    output.mkdir(parents=True, mode=0o700)
    before_installed = installed(wheel)
    cli = Path(sys.executable).parent / "organon"
    # Preserve the caller's HOME; do not copy configuration or inherited tokens.
    env = {"PATH": os.pathsep.join((str(cli.parent), "/usr/bin", "/bin")),
           "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    if "HOME" in os.environ:
        env["HOME"] = os.environ["HOME"]
    started = time.monotonic_ns()
    checks = []

    def status() -> dict:
        result = subprocess.run([str(cli), "status", str(case)], env=env,
                                capture_output=True, text=True, timeout=30, check=True)
        checks.append({"argv": result.args, "stdout": result.stdout, "stderr": result.stderr,
                       "exit": result.returncode})
        (output / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")
        value = json.loads(result.stdout)
        if (value["project"]["case_id"] != expected_case_id
                or value["project"]["approval_policy"] != "signed"
                or value["project_sha256"] != expected_project_sha256):
            raise ValueError("case identity, signed policy or project differs from supervisor pin")
        if (any(phase["accepted"] for phase in value["phases"].values())
                or value["phase_review_history"] or value["field_attestations"]
                or value["test_execution_history"] or value["test_observation_history"]):
            raise ValueError("native case must remain without accepted phases or signed records")
        return value

    initial = status()
    if initial["revision"] != 1 or set(initial["items"]) != {"p_native"}:
        raise ValueError("native case must begin with only the registered problem")
    barrier_stat = barrier.lstat()
    if not stat.S_ISFIFO(barrier_stat.st_mode):
        raise ValueError("barrier must be a named FIFO, not a symlink or regular file")
    ready = {"pid": os.getpid(), "role": role, "started_monotonic_ns": started,
             "package_origin": before_installed["modules"]["specorganon"]["path"],
             "waiting_on": str(barrier), "barrier_is_fifo": True,
             "barrier_device": barrier_stat.st_dev, "barrier_inode": barrier_stat.st_ino,
             "ready_is_not_proof_of_waiting": True, "project_sha256": expected_project_sha256,
             "case_id": expected_case_id, "installed": before_installed}
    (output / "ready.json").write_text(json.dumps(ready, indent=2) + "\n")
    fd = os.open(barrier, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb", buffering=0) as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISFIFO(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
                barrier_stat.st_dev, barrier_stat.st_ino):
            raise ValueError("FIFO changed while opening")
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
        item = json.loads(result.stdout)
        if (item["kind"] != kind or item["id"] != id or item["author"] != actor
                or item["version"] != 1 or item["deps"] != deps):
            raise ValueError("installed CLI returned an unexpected item")
    final = status()
    for id in ids:
        if final["items"][id]["version"] != 1 or final["items"][id]["author"] != actor:
            raise ValueError("own writes were not durable")
    ledger = json.loads((case / "organon.json").read_bytes())
    if any(event["kind"] != "item_put" for event in ledger["events"]):
        raise ValueError("native writers must not approve, review or advance")
    after_installed = installed(wheel)
    if before_installed != after_installed:
        raise ValueError("installed wheel changed during writer execution")
    receipt = {**ready, "released_monotonic_ns": released, "finished_monotonic_ns": time.monotonic_ns(),
               "ids": list(ids), "actor": actor, "calls": len(calls), "human_approvals": 0,
               "cli_sha256": hashlib.sha256(cli.read_bytes()).hexdigest(),
               "helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "installed_verified_before_and_after": True,
               "final_revision_at_own_check": final["revision"],
               "field_scope": False, "model_or_effort_authenticated": False}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"state": "passed", "role": role, "items": len(ids)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("barrier", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("role", choices=("A", "B"))
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--expected-case-id", required=True)
    parser.add_argument("--expected-project-sha256", required=True)
    args = parser.parse_args()
    run(args.case.absolute(), args.barrier.absolute(), args.output.absolute(), args.role,
        args.wheel.resolve(strict=True), args.expected_case_id, args.expected_project_sha256)
