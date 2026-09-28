"""Exercise all nine signed phases with an installed wheel's CLI and stdio MCP.

Run with the Python interpreter of an environment containing the installed
wheel, passing the repository root. Private keys exist only in this process;
all case content and actor names are synthetic. This authenticates local
signatures and transport behavior, not a human reviewer or field impact.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import shlex
import subprocess
import sys
import sysconfig
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

import specorganon
from specorganon import test_observation


PHASES = (
    "frame", "critique", "study", "observe", "explain", "compare",
    "specify", "build", "validate",
)
APPROVALS = {"n1", "d1"}
RUNNER = "agent:synthetic-runner"
APPROVER = "human:synthetic-approver-key"
REVIEWER = "human:synthetic-reviewer-key"
EXECUTOR = "executor:synthetic"
OBSERVER = "observer:synthetic-repeat"
ZERO_HASH = "0" * 64
TEST_OUTPUT = b"synthetic count=10\n"
TEST_ARTIFACT = "t1-artifact.txt"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _public(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def _registry(
    file: Path, case: Path, project: dict[str, Any],
    project_sha256: str, approver_public: str, reviewer_public: str | None,
    executor_public: str | None, observer_public: str | None = None,
) -> None:
    entry = {
        "path": str(case.resolve(strict=True)),
        "project_sha256": project_sha256,
        "approvers": {APPROVER: approver_public},
        "phase_reviewers": {REVIEWER: reviewer_public} if reviewer_public else {},
        "test_executors": {EXECUTOR: executor_public} if executor_public else {},
        "test_observers": {OBSERVER: observer_public} if observer_public else {},
    }
    file.write_text(json.dumps({"schema": 2, "cases": {project["case_id"]: entry}}), encoding="utf-8")
    file.chmod(0o600)


def _cli(executable: Path, env: dict[str, str], work: Path, *args: str) -> dict[str, Any]:
    result = subprocess.run(
        [str(executable), *args], cwd=work, env=env, text=True,
        capture_output=True, timeout=90, check=False,
    )
    _require(result.returncode == 0, f"installed CLI {args[0]} failed: {result.stderr.strip()}")
    value = json.loads(result.stdout)
    _require(isinstance(value, dict), f"installed CLI {args[0]} did not return an object")
    return value


def _cli_rejected(executable: Path, env: dict[str, str], work: Path, *args: str) -> None:
    result = subprocess.run(
        [str(executable), *args], cwd=work, env=env, text=True,
        capture_output=True, timeout=90, check=False,
    )
    _require(result.returncode != 0 and not result.stdout and "signature" in result.stderr.lower(),
             f"installed CLI {args[0]} accepted a missing signature")


def _mcp_data(result: Any, operation: str) -> dict[str, Any]:
    _require(not result.is_error, f"MCP {operation} failed: {result.content}")
    value = result.structured_content
    if value is None:
        _require(len(result.content) == 1, f"MCP {operation} returned ambiguous content")
        value = json.loads(result.content[0].text)
    _require(isinstance(value, dict), f"MCP {operation} did not return an object")
    return value


def _ledger(case: Path) -> tuple[dict[str, Any], bytes]:
    raw = (case / "organon.json").read_bytes()
    data = json.loads(raw)
    _require(isinstance(data, dict), "case ledger is not a JSON object")
    previous = ZERO_HASH
    for number, event in enumerate(data["events"], start=1):
        _require(event["seq"] == number and event["prev_hash"] == previous,
                 f"broken event sequence {number}")
        expected = _sha256(_canonical({key: value for key, value in event.items() if key != "hash"}))
        _require(event["hash"] == expected, f"event {number} digest mismatch")
        previous = expected
    return data, raw


def _message(challenge: dict[str, Any], expected: dict[str, Any]) -> bytes:
    _require(challenge["algorithm"] == "Ed25519" and challenge["encoding"] == "base64",
             "challenge did not declare Ed25519/base64")
    raw = base64.b64decode(challenge["message_base64"], validate=True)
    _require(_sha256(raw) == challenge["message_sha256"], "challenge message hash differs")
    body = json.loads(raw)
    for key, value in expected.items():
        _require(body.get(key) == value, f"challenge did not bind {key}")
    return raw


def _execute_test(work: Path, env: dict[str, str], argv: list[str],
                  artifact_root: Path | None = None, cwd: Path | None = None) -> dict[str, Any]:
    artifact = (artifact_root or work) / TEST_ARTIFACT
    _require(not artifact.exists(), "synthetic test artifact already exists")
    result = subprocess.run(
        argv, cwd=cwd or work, env=env, capture_output=True, timeout=30, check=False,
    )
    _require(result.returncode == 0 and result.stdout == TEST_OUTPUT and result.stderr == b"",
             "local synthetic command did not produce its declared bytes and exit code")
    _require(artifact.is_file() and artifact.read_bytes() == TEST_OUTPUT,
             "local synthetic command did not produce its declared artifact bytes")
    report = {
        "schema": 1,
        "argv": argv,
        "exit_code": result.returncode,
        "timed_out": False,
        "stdout_sha256": _sha256(result.stdout),
        "stderr_sha256": _sha256(result.stderr),
        "artifacts": [{"path": TEST_ARTIFACT, "sha256": _sha256(artifact.read_bytes())}],
    }
    _require(report["stdout_sha256"] == _sha256(TEST_OUTPUT)
             and report["stderr_sha256"] == _sha256(b"")
             and report["artifacts"][0]["sha256"] == _sha256(TEST_OUTPUT),
             "synthetic test report digests do not match local bytes")
    return report


async def probe(repo: Path, *, test_gate_policy: str = "signed_report") -> dict[str, Any]:
    _require(test_gate_policy in {"signed_report", "signed_observed"},
             "unsupported test gate policy")
    observed_mode = test_gate_policy == "signed_observed"
    module_path = Path(specorganon.__file__).resolve()
    site_packages = Path(sysconfig.get_path("purelib")).resolve()
    _require(sys.prefix != sys.base_prefix
             and module_path.is_relative_to(site_packages)
             and not module_path.is_relative_to(repo / "src"),
             "specorganon must be loaded from a wheel installed in this virtual environment")
    probe_sha256 = _sha256(Path(__file__).read_bytes())
    source_manifest_path = repo / "workflows" / "synthetic_full.json"
    manifest_raw = source_manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    steps = manifest["steps"]
    item_steps = [step for step in steps if step["op"] == "put"]
    advance_steps = [step for step in steps if step["op"] == "advance"]
    _require(len(item_steps) == 29 and [step["phase"] for step in advance_steps] == list(PHASES),
             "synthetic_full.json no longer matches the nine-phase probe contract")
    _require({step["id"] for step in item_steps if step["kind"] in {"norm", "decision"}} == APPROVALS,
             "synthetic_full.json normative targets changed")
    bin_dir = Path(sys.executable).parent
    cli = bin_dir / "organon"
    mcp = bin_dir / "organon-mcp"
    _require(cli.is_file() and mcp.is_file(), "installed wheel CLI and MCP executables are required")
    with tempfile.TemporaryDirectory(prefix="organon-signed-full-") as temporary:
        work = Path(temporary)
        case = work / "case"
        path = str(case)
        registry = work / "trusted-public-keys.json"
        registry.write_text(json.dumps({"schema": 2, "cases": {}}), encoding="utf-8")
        registry.chmod(0o600)
        home = work / "home"
        scratch = work / "tmp"
        home.mkdir()
        scratch.mkdir()
        env = {
            "PATH": os.pathsep.join((str(bin_dir), "/usr/bin", "/bin")),
            "HOME": str(home),
            "TMPDIR": str(scratch),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONNOUSERSITE": "1",
            "ORGANON_APPROVERS_FILE": str(registry),
            "ORGANON_ROOT": str(work),
        }
        if observed_mode:
            test_code = (
                "from pathlib import Path; import os,sys; "
                "data=Path('payload.txt').read_bytes(); "
                f"(Path(os.environ['HOME']) / {TEST_ARTIFACT!r}).write_bytes(data); "
                "sys.stdout.buffer.write(data)"
            )
        else:
            test_code = (
                "from pathlib import Path; "
                f"Path({TEST_ARTIFACT!r}).write_bytes({TEST_OUTPUT!r}); "
                "print('synthetic count=10')"
            )
        if observed_mode:
            executable = next((candidate for candidate in (
                Path(sys.executable).resolve(strict=True),
                Path("/usr/bin/python3").resolve(strict=True),
            ) if candidate.is_file() and candidate.stat().st_size <= 16 * 1024 * 1024), None)
            _require(executable is not None,
                     "no local Python executable fits the bounded signed repeat")
        else:
            executable = Path(sys.executable)
        test_argv = [str(executable), *(["-I"] if observed_mode else []), "-c", test_code]
        repeat_dir = work / "repeat"
        if observed_mode:
            repeat_dir.mkdir(mode=0o700)
            (repeat_dir / "input").mkdir(mode=0o700)
            (repeat_dir / "input" / "payload.txt").write_bytes(TEST_OUTPUT)
        test_step = next(step for step in item_steps if step["id"] == "t1")
        test_step["data"] = {
            "passed": True,
            "argv": test_argv,
            "command": shlex.join(test_argv),
        }
        if observed_mode:
            test_step["data"].update({
                "executable_sha256": _sha256(executable.read_bytes()),
                "input_tree_sha256": test_observation.hash_input_tree(repeat_dir / "input"),
            })
        manifest_path = work / "signed-full-manifest.json"
        derived_manifest_raw = _canonical(manifest)
        manifest_path.write_bytes(derived_manifest_raw)
        init_args = ("init", path, "--title", "Synthetic signed full workflow",
                     "--domain", "synthetic mechanics only", "--actor", RUNNER,
                     "--approval-policy", "signed")
        if observed_mode:
            init_args += ("--test-gate-policy", "signed_observed")
        created = _cli(cli, env, work, *init_args)
        project = created["project"]
        _require(project["approval_policy"] == "signed", "temporary case was not signed")
        _require(project.get("test_gate_policy", "signed_report") == test_gate_policy,
                 "temporary case has the wrong test gate policy")
        approver_key = Ed25519PrivateKey.generate()
        reviewer_key = Ed25519PrivateKey.generate()
        executor_key = Ed25519PrivateKey.generate()
        observer_key = Ed25519PrivateKey.generate() if observed_mode else None
        approver_public = _public(approver_key)
        reviewer_public = _public(reviewer_key)
        executor_public = _public(executor_key)
        observer_public = _public(observer_key) if observer_key else None
        _registry(registry, case, project, created["project_sha256"],
                  approver_public, reviewer_public, executor_public, observer_public)
        params = StdioServerParameters(command=str(mcp), cwd=str(work), env=env)
        run_transports: list[str] = []
        decisions: list[dict[str, Any]] = []
        checkpoints: list[dict[str, Any]] = []
        negative: dict[str, bool] = {}
        async with Client(params, mode="legacy") as client:
            discovered = {tool.name for tool in (await client.list_tools()).tools}
            required = {"run", "status", "approval_challenge", "approve",
                        "phase_review_challenge", "review_phase",
                        "test_execution_challenge", "record_test_execution"}
            if observed_mode:
                required |= {"test_observation_challenge", "record_test_observation"}
            _require(required <= discovered, "installed MCP server lacks required signed workflow tools")

            async def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                return _mcp_data(await client.call_tool(name, arguments), name)

            async def status_pair() -> dict[str, Any]:
                cli_state = _cli(cli, env, work, "status", path)
                mcp_state = await call("status", {"path": path})
                _require(cli_state == mcp_state, "CLI and MCP disagree on signed case status")
                return cli_state

            async def run(transport: str) -> dict[str, Any]:
                run_transports.append(transport)
                if transport == "cli":
                    return _cli(cli, env, work, "run", path, "--manifest", str(manifest_path),
                                "--actor", RUNNER)
                return await call("run", {"path": path, "manifest": manifest, "actor": RUNNER})

            async def challenge_pair(kind: str, target: str, reason: str, actor: str) -> dict[str, Any]:
                if kind == "phase":
                    cli_args = ("phase-review-challenge", path, target, "--verdict", "accept",
                                "--reason", reason, "--actor", actor)
                    tool = "phase_review_challenge"
                    arguments = {"path": path, "phase": target, "verdict": "accept",
                                 "reason": reason, "actor": actor}
                else:
                    cli_args = ("approval-challenge", path, target, "--reason", reason,
                                "--actor", actor)
                    tool = "approval_challenge"
                    arguments = {"path": path, "id": target, "reason": reason, "actor": actor}
                before = (case / "organon.json").read_bytes()
                cli_challenge = _cli(cli, env, work, *cli_args)
                mcp_challenge = await call(tool, arguments)
                _require(cli_challenge == mcp_challenge, f"CLI and MCP {kind} challenges differ")
                _require((case / "organon.json").read_bytes() == before,
                         f"{kind} challenge changed the ledger")
                return cli_challenge

            result = await run("cli")
            for decision_number in range(20):
                if result["status"] == "complete":
                    break
                _require(result["status"] == "waiting", "runner left neither a pause nor completion")
                task = result["next"]
                phase = task["phase"]
                action = task["action"]
                _require(phase in PHASES, "runner paused outside the declared nine phases")
                ledger, before = _ledger(case)
                head = ledger["events"][-1]["hash"] if ledger["events"] else ZERO_HASH
                binding = {
                    "case_id": project["case_id"],
                    "case_path": str(case.resolve(strict=True)),
                    "project_sha256": created["project_sha256"],
                    "ledger_head_sha256": head,
                }
                if action == "human_approval":
                    targets = task["approval_targets"]
                    _require(len(targets) == 1 and targets[0]["id"] in APPROVALS,
                             "runner requested an unexpected normative target")
                    item_id = targets[0]["id"]
                    reason = f"Synthetic key approval of {item_id}; no human authenticated"
                    challenge = await challenge_pair("approval", item_id, reason, APPROVER)
                    message = _message(challenge, {
                        **binding, "purpose": "specorganon.normative_approval",
                        "actor": APPROVER, "reason": reason, "item_id": item_id,
                        "item_version": targets[0]["version"],
                    })
                    if item_id == "n1":
                        rejected = await client.call_tool("approve", {
                            "path": path, "id": item_id, "reason": reason, "actor": APPROVER,
                        })
                        _require(rejected.is_error and (case / "organon.json").read_bytes() == before,
                                 "unsigned MCP approval changed the ledger")
                        negative["unsigned_normative_mcp_no_write"] = True
                    signature = base64.b64encode(approver_key.sign(message)).decode("ascii")
                    if item_id == "n1":
                        event = _cli(cli, env, work, "approve", path, item_id, "--reason", reason,
                                     "--actor", APPROVER, "--signature", signature)
                        decision_transport = "cli"
                    else:
                        event = await call("approve", {
                            "path": path, "id": item_id, "reason": reason,
                            "actor": APPROVER, "signature": signature,
                        })
                        decision_transport = "mcp"
                    _require(event["kind"] == "approval" and event["payload"]["id"] == item_id,
                             "signed normative approval did not append its event")
                    decisions.append({"kind": "approval", "target": item_id,
                                      "transport": decision_transport, "seq": event["seq"]})
                elif action == "execute_test":
                    _require(phase == "build", "runner requested test execution outside build")
                    state = await status_pair()
                    test_item = state["items"].get("t1")
                    _require(test_item is not None and test_item["kind"] == "test"
                             and test_item["data"]["argv"] == test_argv,
                             "runner requested an unexpected test execution")
                    _require(task["test_execution_targets"] == [{
                        "id": "t1", "version": test_item["version"],
                        "argv": test_argv, "command": shlex.join(test_argv),
                    }] and task["omitted_test_execution_targets"] == 0,
                             "runner did not expose the exact pending test command")
                    report = _execute_test(
                        work, env, test_argv,
                        artifact_root=home if observed_mode else None,
                        cwd=repeat_dir / "input" if observed_mode else None,
                    )
                    report_json = _canonical(report).decode("utf-8")
                    cli_challenge = _cli(
                        cli, env, work, "test-execution-challenge", path, "t1",
                        "--report", report_json, "--actor", EXECUTOR,
                    )
                    mcp_challenge = await call("test_execution_challenge", {
                        "path": path, "id": "t1", "report": report, "actor": EXECUTOR,
                    })
                    _require(cli_challenge == mcp_challenge,
                             "CLI and MCP test execution challenges differ")
                    _require((case / "organon.json").read_bytes() == before,
                             "test execution challenge changed the ledger")
                    message = _message(cli_challenge, {
                        **binding, "schema": 1, "purpose": "specorganon.test_execution",
                        "actor": EXECUTOR, "report": report, "item_id": "t1",
                        "item_version": test_item["version"],
                        "item_sha256": cli_challenge["item_sha256"],
                        "item_deps": test_item["deps"],
                    })
                    _cli_rejected(
                        cli, env, work, "record-test-execution", path, "t1",
                        "--report", report_json, "--actor", EXECUTOR,
                    )
                    _require((case / "organon.json").read_bytes() == before,
                             "unsigned test execution changed the ledger")
                    negative["unsigned_test_execution_cli_no_write"] = True
                    wrong_signature = base64.b64encode(
                        Ed25519PrivateKey.generate().sign(message)
                    ).decode("ascii")
                    rejected = await client.call_tool("record_test_execution", {
                        "path": path, "id": "t1", "report": report,
                        "actor": EXECUTOR, "signature": wrong_signature,
                    })
                    _require(rejected.is_error and (case / "organon.json").read_bytes() == before,
                             "invalid test execution signature changed the ledger")
                    negative["invalid_test_execution_mcp_no_write"] = True
                    signature = base64.b64encode(executor_key.sign(message)).decode("ascii")
                    event = _cli(
                        cli, env, work, "record-test-execution", path, "t1",
                        "--report", report_json, "--actor", EXECUTOR,
                        "--signature", signature,
                    )
                    _require(event["kind"] == "test_execution"
                             and event["payload"]["id"] == "t1"
                             and event["payload"]["report"] == report,
                             "signed test execution did not append its bound report")
                    decisions.append({"kind": "test_execution", "target": "t1",
                                      "transport": "cli", "seq": event["seq"]})
                elif action == "observe_test":
                    _require(observed_mode and phase == "build" and observer_key is not None,
                             "runner requested an unexpected test observation")
                    state = await status_pair()
                    test_item = state["items"]["t1"]
                    _require(test_item["test_execution_status"] == "signed_passed"
                             and test_item["test_observation_status"] == "missing"
                             and len(task["test_observation_targets"]) == 1
                             and task["test_observation_targets"][0]["id"] == "t1",
                             "runner did not identify the pending signed repeat")
                    audit_process = subprocess.run(
                        [str(sys.executable), str(repo / "scripts" / "audit_signed_test_execution.py"),
                         path, "t1", str(repeat_dir)],
                        cwd=work, env=env, text=True, capture_output=True, timeout=90, check=False,
                    )
                    _require(audit_process.returncode == 0,
                             f"sandboxed repeat did not pass: {audit_process.stdout} {audit_process.stderr}")
                    audit = json.loads(audit_process.stdout)
                    _require(audit["observed_passed"] and audit["report_matches_observation"]
                             and audit["checks"]["input_tree_unchanged"]
                             and audit["checks"]["ledger_unchanged"],
                             "sandboxed repeat failed its measured checks")
                    receipt = audit["receipt"]
                    _require(receipt["bundle_path"] == str(repeat_dir)
                             and receipt["report_provenance"]["seq"] == event["seq"]
                             and receipt["report_provenance"]["hash"] == event["hash"],
                             "repeat receipt is not bound to the signed execution event")
                    receipt_json = _canonical(receipt).decode("utf-8")
                    cli_challenge = _cli(
                        cli, env, work, "test-observation-challenge", path, "t1",
                        "--receipt", receipt_json, "--actor", OBSERVER,
                    )
                    mcp_challenge = await call("test_observation_challenge", {
                        "path": path, "id": "t1", "receipt": receipt, "actor": OBSERVER,
                    })
                    _require(cli_challenge == mcp_challenge
                             and (case / "organon.json").read_bytes() == before,
                             "CLI/MCP observation challenges differ or wrote the ledger")
                    message = _message(cli_challenge, {
                        **binding, "schema": 1, "purpose": "specorganon.test_observation",
                        "actor": OBSERVER, "item_id": "t1", "item_version": test_item["version"],
                        "item_deps": test_item["deps"], "report_provenance": receipt["report_provenance"],
                        "report": report, "receipt": receipt,
                    })
                    _cli_rejected(
                        cli, env, work, "record-test-observation", path, "t1",
                        "--receipt", receipt_json, "--actor", OBSERVER,
                    )
                    _require((case / "organon.json").read_bytes() == before,
                             "unsigned observation changed the ledger")
                    negative["unsigned_test_observation_cli_no_write"] = True
                    wrong_signature = base64.b64encode(
                        Ed25519PrivateKey.generate().sign(message)
                    ).decode("ascii")
                    rejected = await client.call_tool("record_test_observation", {
                        "path": path, "id": "t1", "receipt": receipt,
                        "actor": OBSERVER, "signature": wrong_signature,
                    })
                    _require(rejected.is_error and (case / "organon.json").read_bytes() == before,
                             "invalid observation signature changed the ledger")
                    negative["invalid_test_observation_mcp_no_write"] = True
                    signature = base64.b64encode(observer_key.sign(message)).decode("ascii")
                    observed_event = await call("record_test_observation", {
                        "path": path, "id": "t1", "receipt": receipt,
                        "actor": OBSERVER, "signature": signature,
                    })
                    _require(observed_event["kind"] == "test_observation"
                             and observed_event["payload"]["receipt"] == receipt,
                             "signed observation did not append its measured receipt")
                    decisions.append({"kind": "test_observation", "target": "t1",
                                      "transport": "mcp", "seq": observed_event["seq"]})
                elif action == "review_phase":
                    reason = f"Synthetic key review of {phase}; no human or field assessment"
                    challenge = await challenge_pair("phase", phase, reason, REVIEWER)
                    message = _message(challenge, {
                        **binding, "purpose": "specorganon.phase_review",
                        "phase": phase, "snapshot": result["next"]["gate"]["snapshot"],
                        "verdict": "accept", "reason": reason, "actor": REVIEWER,
                    })
                    if phase == "frame":
                        _cli_rejected(cli, env, work, "review-phase", path, phase,
                                      "--verdict", "accept", "--reason", reason,
                                      "--actor", REVIEWER)
                        _require((case / "organon.json").read_bytes() == before,
                                 "unsigned CLI phase review changed the ledger")
                        negative["unsigned_phase_cli_no_write"] = True
                    signature = base64.b64encode(reviewer_key.sign(message)).decode("ascii")
                    if PHASES.index(phase) % 2 == 0:
                        event = await call("review_phase", {
                            "path": path, "phase": phase, "verdict": "accept",
                            "reason": reason, "actor": REVIEWER, "signature": signature,
                        })
                        decision_transport = "mcp"
                    else:
                        event = _cli(cli, env, work, "review-phase", path, phase,
                                     "--verdict", "accept", "--reason", reason,
                                     "--actor", REVIEWER, "--signature", signature)
                        decision_transport = "cli"
                    _require(event["kind"] == "phase_review"
                             and event["payload"]["phase"] == phase
                             and event["payload"]["snapshot"] == result["next"]["gate"]["snapshot"],
                             "signed phase review did not append the bound event")
                    decisions.append({"kind": "phase_review", "target": phase,
                                      "transport": decision_transport, "seq": event["seq"]})
                    reviewed = await status_pair()
                    gate = reviewed["phases"][phase]
                    _require(gate["reviewed"] and gate["independent_review"]
                             and gate["review_signature_verified"]
                             and gate["review_provenance"] == "signed_verified"
                             and not gate["accepted"],
                             f"signed review did not authenticate {phase} before advance")
                else:
                    raise AssertionError(f"unexpected workflow pause: {phase}/{action}")
                transport = "mcp" if run_transports[-1] == "cli" else "cli"
                result = await run(transport)
                state = await status_pair()
                _require(state["approval_trust"] == "configured"
                         and state["phase_review_trust"] == "configured"
                         and state["test_execution_trust"] == "configured"
                         and (not observed_mode or state["test_observation_trust"] == "configured"),
                         "registered signed case lost its trust context")
                if action == "review_phase":
                    _require(state["phases"][phase]["accepted"],
                             f"runner did not advance signed phase {phase}")
                checkpoints.append({
                    "cursor": result["cursor"], "status": result["status"],
                    "reason": result["reason"], "transport": transport,
                    "revision": state["revision"],
                })
            else:
                raise AssertionError("signed workflow exceeded its 20-decision bound")
            _require(result["status"] == "complete" and result["cursor"] == len(steps),
                     "signed workflow did not complete its manifest")
            _require(source_manifest_path.read_bytes() == manifest_raw,
                     "historical synthetic fixture changed during the probe")
            _require([entry["target"] for entry in decisions if entry["kind"] == "phase_review"] == list(PHASES),
                     "signed phase reviews did not cover each phase in order")
            _require({entry["target"] for entry in decisions if entry["kind"] == "approval"} == APPROVALS,
                     "signed normative approvals did not cover both decisions")
            _require(len(decisions) == (13 if observed_mode else 12)
                     and len(run_transports) == (14 if observed_mode else 13),
                     "signed workflow used an unexpected number of pauses")
            _require(all(run_transports[index] != run_transports[index - 1]
                         for index in range(1, len(run_transports))),
                     "CLI and MCP runner invocations did not alternate")
            expected_negative = {
                "unsigned_normative_mcp_no_write": True,
                "unsigned_phase_cli_no_write": True,
                "unsigned_test_execution_cli_no_write": True,
                "invalid_test_execution_mcp_no_write": True,
            }
            if observed_mode:
                expected_negative.update({
                    "unsigned_test_observation_cli_no_write": True,
                    "invalid_test_observation_mcp_no_write": True,
                })
            _require(negative == expected_negative,
                     "missing-signature negative controls were not observed")

            final = await status_pair()
            _require(final["project"]["approval_policy"] == "signed"
                     and final["revision"] == (51 if observed_mode else 50),
                     "signed case has an unexpected final policy or revision")
            _require(set(final["items"]) == {step["id"] for step in item_steps},
                     "final signed case item set differs from the manifest")
            for step in item_steps:
                item = final["items"][step["id"]]
                _require((item["kind"], item["text"], item["data"], item["version"], item["deps"])
                         == (step["kind"], step["text"], step["data"], 1,
                             {ref: 1 for ref in step["refs"]}),
                         f"manifest artifact {step['id']} differs from its ledger state")
            for phase in PHASES:
                gate = final["phases"][phase]
                _require(gate["accepted"] and gate["reviewed"] and gate["independent_review"]
                         and gate["review_signature_verified"]
                         and gate["review_provenance"] == "signed_verified",
                         f"phase {phase} lacks a current verified acceptance")
            _require(all(final["items"][item_id]["approval_status"] == "signed_verified"
                         for item_id in APPROVALS),
                     "normative targets lack verified signed approvals")
            _require(final["items"]["ass1"]["data"]["verdict"] == "no_demostrado",
                     "synthetic field assessment claimed success")
            _require(final["items"]["ass1"]["data"]["claim_scope"] == "field",
                     "synthetic assessment changed its declared field scope")
            _require(final["items"]["t1"]["data"]["passed"] is True
                     and final["items"]["t1"]["data"]["argv"] == test_argv
                     and final["items"]["t1"]["data"]["command"] == shlex.join(test_argv)
                     and final["items"]["t1"]["test_execution_status"] == "signed_passed"
                     and final["items"]["t1"]["test_execution_actor"] == EXECUTOR,
                     "synthetic test artifact differs from its executed command")
            if observed_mode:
                _require(final["items"]["t1"]["test_observation_status"] == "observed_passed"
                         and final["items"]["t1"]["test_observation_actor"] == OBSERVER
                         and len(final["test_observation_history"]) == 1
                         and final["test_observation_history"][0]["signature_verified"],
                         "strict workflow lacks a current verified observed repeat")
            _require(len(final["test_execution_history"]) == 1
                     and final["test_execution_history"][0]["signature_verified"]
                     and final["test_execution_history"][0]["passed"],
                     "synthetic test receipt did not verify on replay")

            ledger, final_raw = _ledger(case)
            counts = dict(sorted(Counter(event["kind"] for event in ledger["events"]).items()))
            expected_counts = {
                "approval": 2, "item_put": 29, "phase_advance": 9,
                "phase_review": 9, "test_execution": 1,
            }
            if observed_mode:
                expected_counts["test_observation"] = 1
            _require(counts == expected_counts,
                     "ledger event classes differ from the full signed workflow")
            reviews = [event for event in ledger["events"] if event["kind"] == "phase_review"]
            advances = [event for event in ledger["events"] if event["kind"] == "phase_advance"]
            approvals = [event for event in ledger["events"] if event["kind"] == "approval"]
            executions = [event for event in ledger["events"] if event["kind"] == "test_execution"]
            _require([event["payload"]["phase"] for event in reviews] == list(PHASES),
                     "ledger phase review order changed")
            _require([event["payload"]["phase"] for event in advances] == list(PHASES),
                     "ledger phase advance order changed")
            for review, advance in zip(reviews, advances, strict=True):
                phase = review["payload"]["phase"]
                _require(review["actor"] == REVIEWER
                         and isinstance(review["payload"].get("signature"), str)
                         and isinstance(review["payload"].get("key_sha256"), str)
                         and review["payload"]["snapshot"] == final["phases"][phase]["snapshot"]
                         and advance["payload"]["review_seq"] == review["seq"]
                         and advance["payload"]["snapshot"] == review["payload"]["snapshot"]
                         and advance["seq"] > review["seq"],
                         f"phase {phase} advance is not tied to its signed review")
            _require({event["payload"]["id"] for event in approvals} == APPROVALS
                     and all(event["actor"] == APPROVER and event["payload"].get("signature")
                             for event in approvals),
                     "normative approval events lack signed provenance")
            _require(len(executions) == 1 and executions[0]["actor"] == EXECUTOR
                     and executions[0]["payload"]["report"] == report
                     and isinstance(executions[0]["payload"].get("signature"), str),
                     "synthetic test execution lacks its signed report")
            if observed_mode:
                observations = [event for event in ledger["events"]
                                if event["kind"] == "test_observation"]
                _require(len(observations) == 1 and observations[0]["actor"] == OBSERVER
                         and observations[0]["payload"]["receipt"] == receipt
                         and observations[0]["seq"] > executions[0]["seq"],
                         "observed repeat is not tied to the signed test report")
            _require(len(final["phase_review_history"]) == 9
                     and all(entry["signature_verified"] and entry["provenance"] == "signed_verified"
                             for entry in final["phase_review_history"]),
                     "phase review history does not verify on replay")

            cli_replay = await run("cli")
            mcp_replay = await run("mcp")
            _require(all(replay["status"] == "complete" and replay["applied"] == 0
                         and replay["skipped"] == len(steps) for replay in (cli_replay, mcp_replay)),
                     "replay did not skip every completed manifest step")
            _require((case / "organon.json").read_bytes() == final_raw,
                     "CLI/MCP replay mutated the signed ledger")
            _require(await status_pair() == final, "replay changed effective signed status")

            if observed_mode:
                repeated_artifact = repeat_dir / "artifacts" / TEST_ARTIFACT
                _require(repeated_artifact.read_bytes() == TEST_OUTPUT,
                         "sandbox did not retain the expected artifact")
                repeated_artifact.write_bytes(b"tampered repeat\n")
                changed = await status_pair()
                _require(changed["items"]["t1"]["test_observation_status"] == "unverified"
                         and not changed["phases"]["build"]["accepted"]
                         and not changed["phases"]["validate"]["accepted"]
                         and changed["phases"]["specify"]["accepted"]
                         and (case / "organon.json").read_bytes() == final_raw,
                         "changed repeat bytes did not reopen build and validate")
                repeated_artifact.write_bytes(TEST_OUTPUT)
                _require(await status_pair() == final,
                         "restoring repeat bytes did not recover the signed status")

                repeated_input = repeat_dir / "input" / "payload.txt"
                repeated_input.write_bytes(b"tampered input\n")
                changed_input = await status_pair()
                _require(changed_input["items"]["t1"]["test_observation_status"] == "unverified"
                         and not changed_input["phases"]["build"]["accepted"]
                         and not changed_input["phases"]["validate"]["accepted"]
                         and changed_input["phases"]["specify"]["accepted"]
                         and (case / "organon.json").read_bytes() == final_raw,
                         "changed repeat input did not reopen build and validate")
                repeated_input.write_bytes(TEST_OUTPUT)
                _require(await status_pair() == final,
                         "restoring repeat input did not recover the signed status")

                _registry(registry, case, project, created["project_sha256"],
                          approver_public, reviewer_public, executor_public, None)
                observer_revoked = await status_pair()
                _require(observer_revoked["test_observation_trust"] == "unavailable"
                         and observer_revoked["items"]["t1"]["test_observation_status"] == "unverified"
                         and not observer_revoked["phases"]["build"]["accepted"]
                         and not observer_revoked["phases"]["validate"]["accepted"]
                         and observer_revoked["phases"]["specify"]["accepted"]
                         and (case / "organon.json").read_bytes() == final_raw,
                         "observer revocation did not reopen build and validate")
                _registry(registry, case, project, created["project_sha256"],
                          approver_public, reviewer_public, executor_public, observer_public)
                _require(await status_pair() == final,
                         "restoring observer trust did not recover the signed status")

            _registry(registry, case, project, created["project_sha256"],
                      approver_public, reviewer_public, None, observer_public)
            executor_revoked = await status_pair()
            _require(all(not executor_revoked["phases"][phase]["accepted"]
                         for phase in ("build", "validate"))
                     and executor_revoked["phases"]["specify"]["accepted"]
                     and executor_revoked["test_execution_trust"] == "unavailable"
                     and executor_revoked["items"]["t1"]["test_execution_status"] == "unverified"
                     and not executor_revoked["test_execution_history"][0]["signature_verified"],
                     "executor revocation did not reopen build and downstream only")
            _require((case / "organon.json").read_bytes() == final_raw,
                     "executor revocation changed ledger bytes")
            _registry(registry, case, project, created["project_sha256"],
                      approver_public, reviewer_public, executor_public, observer_public)
            _require(await status_pair() == final
                     and (case / "organon.json").read_bytes() == final_raw,
                     "restoring trusted executor key did not restore the same signed status")

            _registry(registry, case, project, created["project_sha256"],
                      approver_public, None, executor_public, observer_public)
            revoked = await status_pair()
            _require(revoked["approval_trust"] == "configured"
                     and revoked["phase_review_trust"] == "unavailable",
                     "reviewer revocation affected the wrong trust domain")
            _require(all(not revoked["phases"][phase]["accepted"]
                         and not revoked["phases"][phase]["reviewed"] for phase in PHASES),
                     "reviewer revocation did not reopen every signed phase")
            _require(not revoked["phases"]["frame"]["review_signature_verified"]
                     and revoked["phases"]["frame"]["review_provenance"] == "signature_unverified",
                     "revoked frame review remained verified")
            _require((case / "organon.json").read_bytes() == final_raw,
                     "reviewer revocation changed ledger bytes")
            _registry(registry, case, project, created["project_sha256"],
                      approver_public, reviewer_public, executor_public, observer_public)
            restored = await status_pair()
            _require(restored == final and (case / "organon.json").read_bytes() == final_raw,
                     "restoring trusted reviewer key did not restore the same signed status")

            return {
                "schema": 1,
                "classification": ("synthetic_signed_observed_full_workflow_installed_cli_stdio_mcp"
                                   if observed_mode else "synthetic_signed_full_workflow_installed_cli_stdio_mcp"),
                "test_gate_policy": test_gate_policy,
                "receipt_kind": "rerunnable_summary_not_detached_attestation",
                "probe_sha256": probe_sha256,
                "manifest_sha256": _sha256(manifest_raw),
                "executed_manifest_sha256": _sha256(derived_manifest_raw),
                "child_environment_keys": sorted(env),
                "transport": {"run_sequence": run_transports[:14 if observed_mode else 13],
                              "cli_mcp_status_equal": True, "stdio_mcp_real": True,
                              "wheel_module_under_site_packages": True},
                "decisions": decisions,
                "checkpoints": checkpoints,
                "final": {"revision": final["revision"], "event_counts": counts,
                          "artifact_count": len(final["items"]),
                          "accepted_phases": list(PHASES),
                          "signed_approvals": sorted(APPROVALS),
                          "signed_reviews": len(reviews),
                          "signed_test_executions": len(executions),
                          **({"signed_test_observations": 1} if observed_mode else {}),
                          "test_report": report,
                          "phase_snapshots": {
                              phase: final["phases"][phase]["snapshot"] for phase in PHASES
                          },
                          "assessment_verdict": final["items"]["ass1"]["data"]["verdict"],
                          "assessment_claim_scope": "field",
                          "ledger_sha256": _sha256(final_raw)},
                "negative_controls": negative,
                **({"local_repeat": {
                    "audit_script_sha256": _sha256((repo / "scripts" / "audit_signed_test_execution.py").read_bytes()),
                    "landlock_abi": receipt["sandbox"]["landlock_abi"],
                    "receipt_sha256": _sha256(_canonical(receipt)),
                    "input_tree_sha256": receipt["input_tree_sha256"],
                    "stdout_sha256": receipt["observed"]["stdout_sha256"],
                    "artifact_sha256": receipt["observed"]["artifacts"][0]["sha256"],
                    "bundle_retained_through_replay": True,
                }} if observed_mode else {}),
                "replay": {"cli_applied": cli_replay["applied"],
                           "mcp_applied": mcp_replay["applied"],
                           "ledger_byte_identical": True},
                "reviewer_key_revocation": {"all_phases_reopened": True,
                                             "ledger_byte_identical": True,
                                             "restoration_recovered_status": True},
                "executor_key_revocation": {"build_and_downstream_reopened": True,
                                             "ledger_byte_identical": True,
                                             "restoration_recovered_status": True},
                **({"observer_key_revocation": {
                    "build_and_downstream_reopened": True,
                    "ledger_byte_identical": True,
                    "restoration_recovered_status": True,
                }, "bundle_tamper": {
                    "build_and_downstream_reopened": True,
                    "ledger_byte_identical": True,
                    "restoration_recovered_status": True,
                }, "input_tamper": {
                    "build_and_downstream_reopened": True,
                    "ledger_byte_identical": True,
                    "restoration_recovered_status": True,
                }} if observed_mode else {}),
                "scope": {
                    "human_identity_authenticated": False,
                    "independent_human_judgment_tested": False,
                    "field_impact_tested": False,
                    "t1_command_executed_locally": True,
                    "t1_report_signed_by_synthetic_executor": True,
                    "t1_execution_independently_verified": False,
                    **({"t1_repeat_executed_locally": True,
                        "observer_custody_external": False} if observed_mode else {}),
                    "content_is_synthetic": True,
                    "private_keys_written_to_disk": False,
                },
            }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--test-gate-policy", choices=("signed_report", "signed_observed"),
                        default="signed_report")
    args = parser.parse_args()
    receipt = asyncio.run(probe(args.repo_root.resolve(strict=True),
                                test_gate_policy=args.test_gate_policy))
    serialized = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        args.output.write_text(serialized, encoding="utf-8")
    sys.stdout.write(serialized)


if __name__ == "__main__":
    main()
