"""Reproducible native-harness reference check, without model calls or installs.

CLI/MCP retain artifacts; this external driver executes the functional fixture.
Only the separate fixture-policy case invents approvals/reviews. The local case
remains pending real owner decisions and independent review. No actual-agent,
authenticated-custody, field-effect or general new-application claim is made.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from specorganon.engine import local_test_result_sha256


AUTHOR = "agent:reference-driver"
CLI = [sys.executable, "-m", "specorganon.cli"]


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _environment(*, fixture: bool = False) -> dict[str, str]:
    # Do not inherit operator trust settings into isolated test cases.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("ORGANON_")}
    env.update(PYTHONPATH=str(ROOT / "src"), PYTHONDONTWRITEBYTECODE="1")
    if fixture:
        env["ORGANON_ALLOW_FIXTURES"] = "1"
    return env


def _execute(argv: list[str], directory: Path, *, cwd: Path,
             env: dict[str, str], timeout: float = 30) -> dict:
    directory.mkdir()
    started = datetime.now(timezone.utc).isoformat()
    try:
        process = subprocess.run(argv, cwd=cwd, env=env, capture_output=True,
                                 timeout=timeout, check=False)
        stdout, stderr = process.stdout, process.stderr
        exit_code, timed_out = process.returncode, False
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = exc.stdout or b"", exc.stderr or b""
        exit_code, timed_out = None, True
    (directory / "stdout.bin").write_bytes(stdout)
    (directory / "stderr.bin").write_bytes(stderr)
    receipt = {
        "argv": argv, "cwd": str(cwd), "exit_code": exit_code,
        "timed_out": timed_out, "timeout_seconds": timeout,
        "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
        "stdout_sha256": _hash(stdout), "stderr_sha256": _hash(stderr),
    }
    _write(directory / "process.json", receipt)
    return receipt


class Reference:
    def __init__(self, output: Path):
        self.output = output
        self.calls = output / "cli"
        self.calls.mkdir()
        self.sequence = 0

    def cli(self, *args: str, fixture: bool = False, fails: bool = False) -> dict:
        self.sequence += 1
        directory = self.calls / f"{self.sequence:03d}-{args[0]}"
        receipt = _execute([*CLI, *map(str, args)], directory, cwd=ROOT,
                           env=_environment(fixture=fixture))
        _require(not receipt["timed_out"], f"CLI timed out: {directory}")
        if fails:
            _require(receipt["exit_code"] != 0, f"expected CLI rejection: {directory}")
            return {"receipt": receipt,
                    "stderr": (directory / "stderr.bin").read_text(encoding="utf-8")}
        _require(receipt["exit_code"] == 0, f"CLI failed: {directory}")
        return json.loads((directory / "stdout.bin").read_bytes())

    def put(self, case: Path, step: dict, *, fixture: bool = False,
            expected: int = 0, deps: dict | None = None) -> dict:
        args = ["put", str(case), step["id"], "--kind", step["kind"],
                "--text", step["text"], "--data", json.dumps(step["data"]),
                "--actor", AUTHOR, "--expected-version", str(expected)]
        for ref in step["refs"]:
            args.extend(["--ref", ref])
        if deps is not None:
            args.extend(["--expected-deps", json.dumps(deps)])
        return self.cli(*args, fixture=fixture)

    def measured_test(self, variant: str) -> dict:
        source = self.output / variant
        source.mkdir()
        originals = ROOT / "tests/fixtures/native_harness"
        for name in ("count_units.py", "test_count_units.py"):
            raw = (originals / name).read_bytes()
            if variant == "regression" and name == "count_units.py":
                _require(raw.count(b"return sum(batches)") == 1, "fixture mutation ambiguous")
                raw = raw.replace(b"return sum(batches)", b"return len(batches)")
            (source / name).write_bytes(raw)
        identity = {name: _hash((source / name).read_bytes())
                    for name in ("count_units.py", "test_count_units.py")}
        argv = [sys.executable, "-B", "-m", "unittest", "-v", "test_count_units"]
        receipt = _execute(argv, source / "execution", cwd=source,
                           env=_environment(), timeout=10)
        _require(identity == {name: _hash((source / name).read_bytes()) for name in identity},
                 "fixture source changed during execution")
        data = {
            "passed": receipt["exit_code"] == 0 and not receipt["timed_out"],
            "argv": argv, "command": shlex.join(argv),
            "receipt": {key: receipt[key] for key in (
                "argv", "exit_code", "timed_out", "stdout_sha256", "stderr_sha256")},
            "source_identity": {"directory": str(source), "sha256": identity},
            "execution_directory": str(source / "execution"),
        }
        data["receipt"]["result_sha256"] = local_test_result_sha256(data)
        _write(source / "local-test.json", data)
        return data


def _mcp_probe(reference: Reference, case: Path, expected: dict) -> dict:
    try:
        installed = importlib.metadata.version("mcp")
    except importlib.metadata.PackageNotFoundError:
        installed = None
    if installed != "2.2.0":
        return {"status": "blocked", "installed_mcp": installed,
                "required_mcp": "2.2.0", "reason": "Use the repository's already-prepared locked environment; no dependency was installed."}
    # Existing test_local_interfaces.py uses this actual stdio client contract.
    code = '''import asyncio,json,os,sys
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
async def run():
    params=StdioServerParameters(command=sys.executable,args=["-m","specorganon.server"],cwd=sys.argv[2],env=os.environ.copy())
    async with Client(params,mode="legacy") as client:
        result=await client.call_tool("status",{"path":sys.argv[1]})
        if result.is_error: raise RuntimeError(str(result.content))
        print(json.dumps(result.structured_content or json.loads(result.content[0].text),sort_keys=True))
asyncio.run(run())
'''
    for index in (1, 2):
        directory = reference.output / f"mcp-restart-{index}"
        receipt = _execute([sys.executable, "-c", code, str(case), str(reference.output)],
                           directory, cwd=ROOT, env=_environment())
        if receipt["exit_code"] != 0 or receipt["timed_out"]:
            return {"status": "blocked", "reason": "MCP stdio execution failed; inspect retained streams",
                    "execution_directory": str(directory), "installed_mcp": installed}
        observed = json.loads((directory / "stdout.bin").read_bytes())
        _require(observed == expected, "MCP/CLI state mismatch after process restart")
    return {"status": "passed", "installed_mcp": installed, "fresh_server_processes": 2}


def run_reference(output: Path) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    reference = Reference(output)
    passed = reference.measured_test("working")
    failed = reference.measured_test("regression")
    _require(passed["passed"] and not failed["passed"] and failed["receipt"]["exit_code"] == 1,
             "expected working fixture and real failing regression")
    _require(passed["source_identity"]["sha256"] != failed["source_identity"]["sha256"],
             "source variants must have distinct identities")
    manifest = json.loads((ROOT / "workflows/synthetic_full.json").read_text(encoding="utf-8"))
    manifest["name"] = "Synthetic mechanics only, with an externally executed code fixture"
    for step in manifest["steps"]:
        if step["op"] != "put":
            continue
        if step["id"] == "impl1":
            step["data"] = {"source_identity": passed["source_identity"]}
        elif step["id"] == "t1":
            step["text"] = "Measured functional fixture execution; declared local receipt, not authenticated custody."
            step["data"] = passed
    fixture_manifest = output / "fixture-workflow.json"
    _write(fixture_manifest, manifest)

    # Real CLI transport, synthetic decisions explicitly confined to fixture policy.
    fixture_case = output / "mechanics-case"
    reference.cli("init", str(fixture_case), "--title", "Synthetic acceptance mechanics",
                  "--domain", "fixture", "--actor", "human:fixture", "--approval-policy", "fixture", fixture=True)
    for _ in range(12):  # Nine synthetic phase reviews plus two synthetic decisions.
        result = reference.cli("run", str(fixture_case), "--manifest", str(fixture_manifest),
                               "--actor", AUTHOR, fixture=True)
        if result["status"] == "complete":
            break
        task = result["next"]
        if task["action"] == "human_approval":
            for target in task["approval_targets"]:
                reference.cli("approve", str(fixture_case), target["id"], "--reason",
                              "Invented test decision, not real consent", "--actor", "human:fixture", fixture=True)
        else:
            _require(task["action"] == "review_phase", f"unexpected fixture task: {task['action']}")
            reference.cli("review-phase", str(fixture_case), task["phase"], "--verdict", "accept",
                          "--reason", "Deterministic synthetic fixture review, no independent agent participated",
                          "--actor", "agent:fixture-review-label", fixture=True)
    else:
        raise RuntimeError("synthetic mechanics did not complete")
    completed = reference.cli("status", str(fixture_case), fixture=True)
    _require(all(phase["accepted"] for phase in completed["phases"].values()), "fixture phases incomplete")
    before = (fixture_case / "organon.json").read_bytes()
    replay = reference.cli("run", str(fixture_case), "--manifest", str(fixture_manifest),
                           "--actor", AUTHOR, fixture=True)
    _require(replay["applied"] == 0 and replay["skipped"] == len(manifest["steps"])
             and before == (fixture_case / "organon.json").read_bytes(), "replay changed completed ledger")
    _write(output / "mechanics-completed.json", completed)

    # Revise a premise in the accepted synthetic graph; preserve both versions.
    evidence = next(copy.deepcopy(s) for s in manifest["steps"] if s.get("id") == "e1")
    evidence["text"] = "Revised synthetic premise: the assigned count is 11, not 10."
    evidence["data"]["value"] = 11
    reference.put(fixture_case, evidence, fixture=True, expected=1,
                  deps=completed["items"]["e1"]["deps"])
    revised = reference.cli("status", str(fixture_case), fixture=True)
    _require(revised["items"]["req1"]["stale"] and revised["items"]["t1"]["stale"]
             and not revised["phases"]["validate"]["accepted"], "changed premise did not invalidate dependents")
    _require(revised["phases"]["study"]["accepted"], "unrelated earlier phase unexpectedly invalidated")
    before = (fixture_case / "organon.json").read_bytes()
    rejection = reference.cli("run", str(fixture_case), "--manifest", str(fixture_manifest),
                              "--actor", AUTHOR, fixture=True, fails=True)
    _require("version" in rejection["stderr"] and before == (fixture_case / "organon.json").read_bytes(),
             "stale manifest must fail without overwriting history")
    _write(output / "mechanics-invalidated.json", revised)

    # The local-policy case never receives fabricated approvals or phase reviews.
    local_case = output / "local-review-case"
    reference.cli("init", str(local_case), "--title", "Functional fixture, genuine review pending",
                  "--domain", "local acceptance check", "--actor", "human:acceptance-operator", "--approval-policy", "local")
    drafts = copy.deepcopy(manifest)
    drafts["steps"] = [s for s in drafts["steps"] if s["op"] == "put"]
    for step in drafts["steps"]:
        if step["kind"] == "criterion":
            step["data"]["threshold"] = {"operator": ">=", "statistic": "estimate", "value": 0}
        if step["kind"] == "assessment":
            step["data"]["claim_scope"] = "technical"
            step["text"] = "Fixture test executed; actual agent/human review and broader effectiveness remain unproved."
    draft_path = output / "local-drafts.json"
    _write(draft_path, drafts)
    first = reference.cli("run", str(local_case), "--manifest", str(draft_path), "--actor", AUTHOR)
    _require(first["status"] == "waiting" and first["next"]["action"] == "review_phase", "local case skipped review")
    initial = reference.cli("status", str(local_case))
    _require(not initial["items"]["t1"]["issues"], "real successful local receipt is invalid")
    before = (local_case / "organon.json").read_bytes()
    restarted = reference.cli("run", str(local_case), "--manifest", str(draft_path), "--actor", AUTHOR)
    _require(restarted["applied"] == 0 and restarted["skipped"] == len(drafts["steps"])
             and before == (local_case / "organon.json").read_bytes(), "local restart changed checkpoint")
    test_step = next(copy.deepcopy(s) for s in drafts["steps"] if s["id"] == "t1")
    implementation = next(copy.deepcopy(s) for s in drafts["steps"] if s["id"] == "impl1")
    implementation["data"]["source_identity"] = failed["source_identity"]
    reference.put(local_case, implementation, expected=1, deps=initial["items"]["impl1"]["deps"])
    test_step["data"] = failed
    test_deps = dict(initial["items"]["t1"]["deps"], impl1=2)
    reference.put(local_case, test_step, expected=1, deps=test_deps)
    failed_state = reference.cli("status", str(local_case))
    issues = failed_state["items"]["t1"]["issues"]
    _require("local test execution failed or timed out" in issues
             and not failed_state["phases"]["build"]["ready"], "failed execution did not block local build")
    before = (local_case / "organon.json").read_bytes()
    rejection = reference.cli("advance", str(local_case), "build", "--actor", AUTHOR, fails=True)
    _require("local test" in rejection["stderr"] and before == (local_case / "organon.json").read_bytes(),
             "failed-test advance must be rejected without a write")
    _write(output / "local-failed-test.json", failed_state)
    # Restore the measured working source; this is a revision, not a deletion.
    implementation["data"]["source_identity"] = passed["source_identity"]
    reference.put(local_case, implementation, expected=2, deps=initial["items"]["impl1"]["deps"])
    test_step["data"] = passed
    reference.put(local_case, test_step, expected=2, deps=dict(test_deps, impl1=3))
    final = reference.cli("status", str(local_case))
    _require(not final["items"]["t1"]["issues"] and final["items"]["t1"]["version"] == 3,
             "restored receipt did not create the third preserved version")
    ledger = json.loads((local_case / "organon.json").read_bytes())
    _require(not any(event["kind"] in {"approval", "phase_review", "phase_advance"}
                     for event in ledger["events"]), "local case manufactured consent or acceptance")
    test_events = [e for e in ledger["events"] if e["kind"] == "item_put" and e["payload"]["id"] == "t1"]
    _require([e["payload"]["data"]["receipt"]["exit_code"] for e in test_events] == [0, 1, 0],
             "test history did not preserve pass/fail/repair")
    _write(output / "local-final.json", final)
    _write(output / "local-report.json", reference.cli("report", str(local_case)))
    mcp = _mcp_probe(reference, local_case, final)
    next_task = reference.cli("next-task", str(local_case))
    summary = {
        "status": "passed" if mcp["status"] == "passed" else "blocked",
        "scope": "deterministic reference mechanics only",
        "cli": {"status": "passed", "processes": reference.sequence,
                "real_fixture_exit_codes": [0, 1], "preserved_test_versions": 3,
                "failed_test_rejected": True, "premise_invalidated": True,
                "restart_replay_unchanged": True},
        "mcp": mcp,
        "native_agent_and_human_review": {"status": "not_run", "local_accepted_phases": 0,
                                          "reason": "Requires real independent review and actual owner decisions; no labels synthesize that evidence."},
        "synthetic_mechanics": {"policy": "fixture", "accepted_before_revision": 9,
                                "accepted_validate_after_revision": False},
        "next": next_task,
    }
    _write(output / "summary.json", summary)
    inventory = {str(path.relative_to(output)): _hash(path.read_bytes())
                 for path in sorted(output.rglob("*")) if path.is_file()}
    _write(output / "sha256.json", inventory)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory; existing evidence is never replaced")
    args = parser.parse_args()
    try:
        summary = run_reference(args.output)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"reference check failed; preserve output for diagnosis: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
