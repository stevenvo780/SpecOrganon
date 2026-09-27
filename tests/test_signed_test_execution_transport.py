"""Exercise both positive test-receipt transports from the interpreter's installed package."""

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

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters


def _mcp_value(result: Any) -> dict[str, Any]:
    assert not result.is_error, result.content
    value = result.structured_content
    if value is None:
        assert len(result.content) == 1
        value = json.loads(result.content[0].text)
    assert isinstance(value, dict)
    return value


def test_installed_cli_and_mcp_record_actual_synthetic_test(tmp_path: Path) -> None:
    bin_dir = Path(sys.executable).parent
    cli_executable, mcp_executable = bin_dir / "organon", bin_dir / "organon-mcp"
    assert cli_executable.is_file() and mcp_executable.is_file()
    home, scratch = tmp_path / "home", tmp_path / "tmp"
    home.mkdir()
    scratch.mkdir()
    env = {
        "PATH": os.pathsep.join((str(bin_dir), "/usr/bin", "/bin")),
        "HOME": str(home), "TMPDIR": str(scratch),
        "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONNOUSERSITE": "1",
    }
    case, registry = tmp_path / "case", tmp_path / "trusted.json"
    actor = "executor:synthetic-installed"
    key = Ed25519PrivateKey.generate()

    def cli(*args: str, trusted: bool = True) -> dict[str, Any]:
        child_env = {**env, **({"ORGANON_APPROVERS_FILE": str(registry)} if trusted else {})}
        result = subprocess.run(
            [str(cli_executable), *args], cwd=tmp_path, env=child_env,
            text=True, capture_output=True, timeout=30, check=False,
        )
        assert result.returncode == 0, result.stderr
        value = json.loads(result.stdout)
        assert isinstance(value, dict)
        return value

    created = cli(
        "init", str(case), "--title", "Installed test receipt transport",
        "--domain", "synthetic", "--actor", "agent:writer", trusted=False,
    )
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
    )
    registry.write_text(json.dumps({"schema": 2, "cases": {
        created["project"]["case_id"]: {
            "path": str(case.resolve(strict=True)),
            "project_sha256": created["project_sha256"],
            "approvers": {}, "phase_reviewers": {},
            "test_executors": {actor: base64.b64encode(public).decode("ascii")},
        },
    }}), encoding="utf-8")

    expected = b"installed transport result\n"
    script = "from pathlib import Path; Path('t1-output.txt').write_bytes(b'installed transport result\\n'); print('installed transport result')"
    argv = [sys.executable, "-c", script]
    cli(
        "put", str(case), "t1", "--kind", "test", "--text", "Synthetic installed transport test",
        "--data", json.dumps({"argv": argv, "command": shlex.join(argv), "passed": True}),
        "--actor", "agent:writer",
    )
    assert cli("status", str(case))["items"]["t1"]["test_execution_status"] == "missing"

    process = subprocess.run(argv, cwd=tmp_path, env=env, capture_output=True, timeout=15, check=False)
    artifact = tmp_path / "t1-output.txt"
    assert process.returncode == 0 and process.stdout == expected and process.stderr == b""
    assert artifact.read_bytes() == expected
    report = {
        "schema": 1, "argv": argv, "exit_code": process.returncode, "timed_out": False,
        "stdout_sha256": hashlib.sha256(process.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(process.stderr).hexdigest(),
        "artifacts": [{"path": artifact.name, "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}],
    }
    report_json = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    ledger = case / "organon.json"

    async def exercise() -> None:
        params = StdioServerParameters(
            command=str(mcp_executable), cwd=str(tmp_path),
            env={**env, "ORGANON_ROOT": str(tmp_path), "ORGANON_APPROVERS_FILE": str(registry)},
        )
        async with Client(params, mode="legacy") as client:
            async def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                return _mcp_value(await client.call_tool(name, arguments))

            arguments = {"path": str(case), "id": "t1", "report": report, "actor": actor}
            before = ledger.read_bytes()
            first = cli("test-execution-challenge", str(case), "t1", "--report", report_json,
                        "--actor", actor)
            assert first == await call("test_execution_challenge", arguments)
            assert ledger.read_bytes() == before
            message = base64.b64decode(first["message_base64"], validate=True)
            assert hashlib.sha256(message).hexdigest() == first["message_sha256"]
            signature = base64.b64encode(key.sign(message)).decode("ascii")
            cli_event = cli("record-test-execution", str(case), "t1", "--report", report_json,
                            "--actor", actor, "--signature", signature)
            assert cli_event["kind"] == "test_execution" and cli_event["payload"]["report"] == report
            assert cli("status", str(case)) == await call("status", {"path": str(case)})

            second = await call("test_execution_challenge", arguments)
            assert second == cli("test-execution-challenge", str(case), "t1", "--report", report_json,
                                 "--actor", actor)
            assert second["ledger_head_sha256"] != first["ledger_head_sha256"]
            second_message = base64.b64decode(second["message_base64"], validate=True)
            second_signature = base64.b64encode(key.sign(second_message)).decode("ascii")
            mcp_event = await call("record_test_execution", {**arguments, "signature": second_signature})
            assert mcp_event["kind"] == "test_execution" and mcp_event["payload"]["report"] == report
            assert mcp_event["seq"] == cli_event["seq"] + 1
            final = cli("status", str(case))
            assert final == await call("status", {"path": str(case)})
            assert final["items"]["t1"]["test_execution_status"] == "signed_passed"
            assert final["items"]["t1"]["test_execution_provenance"] == [mcp_event["seq"], mcp_event["hash"]]
            assert len(final["test_execution_history"]) == 2
            assert all(entry["signature_verified"] and entry["passed"]
                       for entry in final["test_execution_history"])
            assert artifact.read_bytes() == expected

    asyncio.run(exercise())
