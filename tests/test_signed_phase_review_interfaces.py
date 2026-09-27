"""Installed CLI and real stdio MCP share signed phase-review semantics."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from specorganon import engine
from specorganon.ledger import read_project


BIN = Path(sys.executable).parent
CLI = BIN / "organon"
MCP = BIN / "organon-mcp"
REVIEWER = "agent:independent-reviewer"
REASON = "I independently checked this exact framing snapshot"


def _command(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(CLI), *args], text=True, capture_output=True, check=check)


def _cli(*args: str) -> dict:
    return json.loads(_command(*args).stdout)


def _result_data(result) -> dict:
    assert not result.is_error, result.content
    return result.structured_content or json.loads(result.content[0].text)


def _sign(key: Ed25519PrivateKey, challenge: dict) -> str:
    message = base64.b64decode(challenge["message_base64"], validate=True)
    assert hashlib.sha256(message).hexdigest() == challenge["message_sha256"]
    return base64.b64encode(key.sign(message)).decode("ascii")


def _frame_case(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Ed25519PrivateKey]:
    registry = tmp_path / "trusted-public-keys.json"
    registry.write_text(json.dumps({"schema": 2, "cases": {}}), encoding="utf-8")
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(registry))
    case = tmp_path / "signed-frame"
    path = str(case)
    _cli("init", path, "--title", "Signed review interface", "--domain", "test",
         "--actor", "human:owner")
    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    project = read_project(case)["project"]
    registry.write_text(json.dumps({
        "schema": 2,
        "cases": {
            project["case_id"]: {
                "path": str(case.resolve(strict=True)),
                "project_sha256": engine.get_state(case)["project_sha256"],
                "approvers": {},
                "phase_reviewers": {REVIEWER: base64.b64encode(public_key).decode("ascii")},
            },
        },
    }), encoding="utf-8")
    _cli("put", path, "p1", "--kind", "problem", "--text", "A bounded problem",
         "--actor", "agent:author")
    _cli("put", path, "a1", "--kind", "actor", "--text", "Affected people",
         "--ref", "p1", "--actor", "agent:author")
    _cli("put", path, "b1", "--kind", "boundary", "--text", "One test boundary",
         "--ref", "p1", "--actor", "agent:author")
    assert _cli("gate", path, "frame")["ready"]
    return case, registry, key


def test_signed_review_cli_and_real_mcp_share_challenge_and_persist_proof(tmp_path, monkeypatch):
    case, registry, key = _frame_case(tmp_path, monkeypatch)
    path = str(case)
    arguments = {
        "path": path, "phase": "frame", "verdict": "accept",
        "reason": REASON, "actor": REVIEWER,
    }
    cli_args = ("phase-review-challenge", path, "frame", "--verdict", "accept",
                "--reason", REASON, "--actor", REVIEWER)
    ledger = case / "organon.json"

    async def exercise() -> None:
        params = StdioServerParameters(
            command=str(MCP), cwd=str(tmp_path),
            env={"ORGANON_ROOT": str(tmp_path), "ORGANON_APPROVERS_FILE": str(registry)},
        )
        async with Client(params, mode="legacy") as client:
            tools = {tool.name for tool in (await client.list_tools()).tools}
            assert {"phase_review_challenge", "review_phase"} <= tools

            before = ledger.read_bytes()
            challenge = _cli(*cli_args)
            assert _result_data(await client.call_tool("phase_review_challenge", arguments)) == challenge
            assert ledger.read_bytes() == before

            missing_cli_signature = _command(
                "review-phase", path, "frame", "--verdict", "accept", "--reason", REASON,
                "--actor", REVIEWER, check=False,
            )
            assert missing_cli_signature.returncode != 0
            assert "signature" in missing_cli_signature.stderr.lower()
            missing_mcp_signature = await client.call_tool("review_phase", arguments)
            assert missing_mcp_signature.is_error
            assert ledger.read_bytes() == before

            # A new ledger head invalidates the earlier challenge even if the
            # phase remains ready and the review request is otherwise identical.
            _cli("put", path, "b2", "--kind", "boundary", "--text", "A second boundary",
                 "--ref", "p1", "--actor", "agent:author")
            before_stale = ledger.read_bytes()
            stale = await client.call_tool(
                "review_phase", {**arguments, "signature": _sign(key, challenge)},
            )
            assert stale.is_error
            assert ledger.read_bytes() == before_stale
            challenge = _result_data(await client.call_tool("phase_review_challenge", arguments))
            assert challenge == _cli(*cli_args)

            signed = _result_data(await client.call_tool(
                "review_phase", {**arguments, "signature": _sign(key, challenge)},
            ))
            assert signed["kind"] == "phase_review"
            assert signed["actor"] == REVIEWER
            assert signed["payload"]["signature"] == _sign(key, challenge)
            assert _cli("status", path)["phases"]["frame"]["reviewed"]
            assert _result_data(await client.call_tool("status", {"path": path})) == _cli(
                "status", path,
            )

            # CLI can sign and record a fresh review of the current ledger head too.
            second_reason = "I rechecked the unchanged framing after the MCP review"
            second_args = ("phase-review-challenge", path, "frame", "--verdict", "accept",
                           "--reason", second_reason, "--actor", REVIEWER)
            second_challenge = _result_data(await client.call_tool(
                "phase_review_challenge", {**arguments, "reason": second_reason},
            ))
            assert second_challenge == _cli(*second_args)
            second_review = _cli(
                "review-phase", path, "frame", "--verdict", "accept", "--reason", second_reason,
                "--actor", REVIEWER, "--signature", _sign(key, second_challenge),
            )
            assert second_review["seq"] > signed["seq"]
            assert second_review["payload"]["signature"] == _sign(key, second_challenge)
            _result_data(await client.call_tool(
                "advance", {"path": path, "phase": "frame", "actor": "agent:lead"},
            ))
            assert _cli("gate", path, "frame")["accepted"]

            before_revocation = ledger.read_bytes()
            registry.write_text(json.dumps({"schema": 2, "cases": {}}), encoding="utf-8")
            assert not _cli("gate", path, "frame")["accepted"]
            assert not _result_data(await client.call_tool(
                "gate", {"path": path, "phase": "frame"},
            ))["accepted"]
            assert ledger.read_bytes() == before_revocation

    asyncio.run(exercise())


def test_fixture_review_keeps_unsigned_interface(tmp_path, monkeypatch, enable_fixture_policy):
    monkeypatch.delenv("ORGANON_APPROVERS_FILE", raising=False)
    case = tmp_path / "fixture-frame"
    path = str(case)
    _cli("init", path, "--title", "Synthetic review interface", "--domain", "fixture",
         "--actor", "human:fixture", "--approval-policy", "fixture")
    _cli("put", path, "p1", "--kind", "problem", "--text", "Synthetic problem",
         "--actor", "agent:author")
    _cli("put", path, "a1", "--kind", "actor", "--text", "Synthetic people",
         "--actor", "agent:author")
    _cli("put", path, "b1", "--kind", "boundary", "--text", "Synthetic boundary",
         "--actor", "agent:author")
    review = _cli("review-phase", path, "frame", "--verdict", "accept",
                  "--reason", "Explicit fixture review", "--actor", REVIEWER)
    assert review["kind"] == "phase_review"
    assert review["payload"]["independent"] is True
