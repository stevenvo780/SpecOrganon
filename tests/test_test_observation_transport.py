"""The observation policy and receipt boundary are shared by CLI, MCP and runner."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from mcp.shared.exceptions import MCPError

from specorganon import approval, engine, runner, test_observation
from specorganon.ledger import read_project
from specorganon.workflow import PHASE_BY_ID


CLI = Path(sys.executable).parent / "organon"
MCP = Path(sys.executable).parent / "organon-mcp"
AUTHOR = "agent:writer"
EXECUTOR = "executor:synthetic"
OBSERVER = "observer:synthetic"
ARGV = ["python3", "-c", "print('synthetic test')"]
REPORT = {
    "schema": 1,
    "argv": ARGV,
    "exit_code": 0,
    "timed_out": False,
    "stdout_sha256": "0" * 64,
    "stderr_sha256": "0" * 64,
    "artifacts": [{"path": "results/output.txt", "sha256": "1" * 64}],
}


def _public(key: Ed25519PrivateKey) -> str:
    return base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode("ascii")


def _cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    assert CLI.is_file()
    return subprocess.run([str(CLI), *args], text=True, capture_output=True, check=False, env=env)


def _mcp_value(result: Any) -> dict[str, Any]:
    assert not result.is_error, result.content
    value = result.structured_content
    if value is None:
        assert len(result.content) == 1
        value = json.loads(result.content[0].text)
    assert isinstance(value, dict)
    return value


def test_cli_and_real_mcp_expose_policy_and_reject_ambiguous_receipts(tmp_path: Path) -> None:
    assert MCP.is_file()
    case = tmp_path / "case"
    created = _cli(
        "init", str(case), "--title", "Observed test transport", "--domain", "synthetic",
        "--actor", AUTHOR, "--test-gate-policy", "signed_observed",
    )
    assert created.returncode == 0, created.stderr
    assert json.loads(created.stdout)["project"]["test_gate_policy"] == "signed_observed"
    ledger = case / "organon.json"
    before = ledger.read_bytes()

    for command in ("test-observation-challenge", "record-test-observation"):
        arguments = [command, str(case), "t1", "--receipt", '{"value":1,"value":2}',
                     "--actor", OBSERVER]
        if command == "record-test-observation":
            arguments += ["--signature", "invalid"]
        invalid = _cli(*arguments)
        assert invalid.returncode != 0
        assert "duplicate" in invalid.stderr.lower()
        assert ledger.read_bytes() == before

        arguments[4] = "[]"
        invalid_array = _cli(*arguments)
        assert invalid_array.returncode != 0
        assert "receipt must be a JSON object" in invalid_array.stderr
        assert ledger.read_bytes() == before

    async def exercise() -> None:
        params = StdioServerParameters(
            command=str(MCP), cwd=str(tmp_path),
            env={**os.environ, "ORGANON_ROOT": str(tmp_path)},
        )
        async with Client(params, mode="legacy") as client:
            discovered = {tool.name: tool for tool in (await client.list_tools()).tools}
            assert {"test_observation_challenge", "record_test_observation"} <= discovered.keys()
            for name in ("test_observation_challenge", "record_test_observation"):
                schema = discovered[name].input_schema
                assert schema["properties"]["receipt"]["type"] == "object"
                arguments = {"path": str(case), "id": "t1", "receipt": '{"value":1,"value":2}',
                             "actor": OBSERVER}
                if name == "record_test_observation":
                    arguments["signature"] = "invalid"
                with pytest.raises(MCPError, match="test observation receipt must be a JSON object"):
                    await client.call_tool(name, arguments)
                assert ledger.read_bytes() == before

            second = tmp_path / "mcp-case"
            mcp_created = _mcp_value(await client.call_tool("init", {
                "path": str(second), "title": "MCP observed test transport", "domain": "synthetic",
                "actor": AUTHOR, "test_gate_policy": "signed_observed",
            }))
            assert mcp_created["project"]["test_gate_policy"] == "signed_observed"
            assert _mcp_value(await client.call_tool("status", {"path": str(second)})) == (
                json.loads(_cli("status", str(second)).stdout)
            )

    asyncio.run(exercise())


def test_runner_requests_observation_after_signed_report_and_waits_for_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, registry = tmp_path / "case", tmp_path / "registry.json"
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(registry))
    engine.create_case(case, "Observed runner", "synthetic", AUTHOR,
                       test_gate_policy="signed_observed")
    executor, observer = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    project = read_project(case)["project"]
    registry.write_text(json.dumps({"schema": 2, "cases": {project["case_id"]: {
        "path": str(case.resolve(strict=True)),
        "project_sha256": approval.project_fingerprint(project),
        "approvers": {}, "phase_reviewers": {},
        "test_executors": {EXECUTOR: _public(executor)},
        "test_observers": {OBSERVER: _public(observer)},
    }}}), encoding="utf-8")
    engine.put_item(case, "p1", "problem", "A declared problem", [], {}, AUTHOR)
    engine.put_item(case, "req1", "requirement", "A requirement", ["p1"], {}, AUTHOR)
    engine.put_item(case, "crit1", "criterion", "A prior criterion", ["req1"], {
        "metric": "count", "threshold": 0, "reject": "count < 0",
    }, AUTHOR)
    engine.put_item(case, "impl1", "implementation", "The implementation", ["req1"], {}, AUTHOR)
    executable = Path(sys.executable).resolve(strict=True)
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    argv = [str(executable), "-c", "print('synthetic test')"]
    report = {**REPORT, "argv": argv}
    engine.put_item(case, "t1", "test", "A declared test", ["impl1", "crit1"], {
        "passed": True, "argv": argv, "command": shlex.join(argv),
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "input_tree_sha256": test_observation.hash_input_tree(input_dir),
    }, AUTHOR)

    monkeypatch.setattr(runner, "PHASES", (PHASE_BY_ID["build"],))
    before = runner.next_task(case)
    assert before["action"] == "execute_test"
    assert before["test_execution_targets"][0]["id"] == "t1"

    challenge = engine.test_execution_challenge(case, "t1", report, EXECUTOR)
    signature = base64.b64encode(executor.sign(base64.b64decode(challenge["message_base64"]))).decode("ascii")
    execution = engine.record_test_execution(case, "t1", report, EXECUTOR, signature)
    task = runner.next_task(case, {"observer": OBSERVER})
    assert task["action"] == "observe_test"
    assert task["role"] == "observer" and task["actor"] == OBSERVER
    assert task["test_execution_targets"] == []
    assert task["test_observation_targets"] == [{
        "id": "t1", "version": 1,
        "report_provenance": (execution["seq"], execution["hash"]),
        "observation_status": "missing",
    }]
    assert runner.run_manifest(case, {"schema": 1, "steps": [{"op": "advance", "phase": "build"}]}, AUTHOR)[
        "reason"
    ] == "signed_test_observation_required"


def test_valid_observation_roundtrips_through_cli_and_real_mcp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, registry = tmp_path / "valid-case", tmp_path / "valid-registry.json"
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(registry))
    engine.create_case(case, "Observed transport", "synthetic", AUTHOR,
                       test_gate_policy="signed_observed")
    executor, observer = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    project = read_project(case)["project"]
    registry.write_text(json.dumps({"schema": 2, "cases": {project["case_id"]: {
        "path": str(case.resolve(strict=True)),
        "project_sha256": approval.project_fingerprint(project),
        "approvers": {}, "phase_reviewers": {},
        "test_executors": {EXECUTOR: _public(executor)},
        "test_observers": {OBSERVER: _public(observer)},
    }}}), encoding="utf-8")
    executable = next((candidate for candidate in (
        Path(sys.executable).resolve(strict=True),
        Path("/usr/bin/python3").resolve(strict=True),
        Path("/usr/bin/true").resolve(strict=True),
    ) if candidate.is_file() and candidate.stat().st_size <= 16 * 1024 * 1024), None)
    if executable is None:
        pytest.skip("no bounded local executable")
    bundle = tmp_path / "bundle"
    bundle.mkdir(mode=0o700)
    (bundle / "input").mkdir(mode=0o700)
    (bundle / "artifacts").mkdir(mode=0o700)
    (bundle / "stdout.bin").write_bytes(b"ok\n")
    (bundle / "stderr.bin").write_bytes(b"")
    (bundle / "artifacts" / "result.txt").write_bytes(b"ok\n")
    argv = [str(executable)]
    engine.put_item(case, "t1", "test", "Synthetic transport receipt", [], {
        "passed": True, "argv": argv, "command": shlex.join(argv),
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "input_tree_sha256": test_observation.hash_input_tree(bundle / "input"),
    }, AUTHOR)
    digest = hashlib.sha256(b"ok\n").hexdigest()
    report = {"schema": 1, "argv": argv, "exit_code": 0, "timed_out": False,
              "stdout_sha256": digest, "stderr_sha256": hashlib.sha256(b"").hexdigest(),
              "artifacts": [{"path": "result.txt", "sha256": digest}]}
    execution_challenge = engine.test_execution_challenge(case, "t1", report, EXECUTOR)
    execution_signature = base64.b64encode(executor.sign(
        base64.b64decode(execution_challenge["message_base64"]),
    )).decode("ascii")
    execution = engine.record_test_execution(case, "t1", report, EXECUTOR, execution_signature)
    inspected = test_observation.inspect_bundle(bundle, report)
    receipt = {
        "schema": 1, "case_id": project["case_id"], "item_id": "t1", "item_version": 1,
        "report_provenance": {"seq": execution["seq"], "hash": execution["hash"]},
        "bundle_path": str(bundle.resolve(strict=True)),
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "input_tree_sha256": inspected["input_tree_sha256"],
        "sandbox": {"policy": "landlock_seccomp_repeat_v1", "landlock_abi": 5,
                    "exit_code": 0, "timed_out": False, "launch_error": None},
        "observed": {key: inspected[key] for key in ("stdout_sha256", "stderr_sha256", "artifacts")},
    }
    receipt_arg = json.dumps(receipt, ensure_ascii=False, sort_keys=True)

    async def exercise() -> None:
        params = StdioServerParameters(command=str(MCP), cwd=str(tmp_path),
                                       env={**os.environ, "ORGANON_ROOT": str(tmp_path)})
        async with Client(params, mode="legacy") as client:
            cli_challenge = _cli("test-observation-challenge", str(case), "t1",
                                 "--receipt", receipt_arg, "--actor", OBSERVER)
            assert cli_challenge.returncode == 0, cli_challenge.stderr
            first = json.loads(cli_challenge.stdout)
            assert first == _mcp_value(await client.call_tool("test_observation_challenge", {
                "path": str(case), "id": "t1", "receipt": receipt, "actor": OBSERVER,
            }))
            signature = base64.b64encode(observer.sign(base64.b64decode(first["message_base64"]))).decode()
            cli_event = _cli("record-test-observation", str(case), "t1", "--receipt", receipt_arg,
                             "--actor", OBSERVER, "--signature", signature)
            assert cli_event.returncode == 0, cli_event.stderr
            assert json.loads(cli_event.stdout)["kind"] == "test_observation"
            second = _mcp_value(await client.call_tool("test_observation_challenge", {
                "path": str(case), "id": "t1", "receipt": receipt, "actor": OBSERVER,
            }))
            second_signature = base64.b64encode(observer.sign(
                base64.b64decode(second["message_base64"]),
            )).decode()
            mcp_event = _mcp_value(await client.call_tool("record_test_observation", {
                "path": str(case), "id": "t1", "receipt": receipt, "actor": OBSERVER,
                "signature": second_signature,
            }))
            assert mcp_event["kind"] == "test_observation"
            assert engine.get_state(case)["items"]["t1"]["test_observation_status"] == "observed_passed"
            assert _mcp_value(await client.call_tool("status", {"path": str(case)})) == json.loads(
                _cli("status", str(case)).stdout,
            )

    asyncio.run(exercise())
