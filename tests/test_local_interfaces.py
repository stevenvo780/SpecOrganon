"""Local development through the installed CLI and a real MCP stdio client."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters


BIN = Path(sys.executable).parent
CLI = BIN / "organon"
MCP = BIN / "organon-mcp"
OWNER = "human:owner"
WRITER = "agent:writer"
REVIEWER = "agent:reviewer"
TOOLS = {
    "init", "put", "status", "report", "review", "retire_indicator", "approve",
    "approval_challenge", "test_execution_challenge", "record_test_execution",
    "test_observation_challenge", "record_test_observation", "field_attestation_challenge",
    "attest_field", "challenge", "resolve_challenge", "gate", "phase_review_challenge",
    "review_phase", "advance", "trace", "next_task", "run", "audit_lot_journal",
}


@pytest.fixture(autouse=True)
def isolated_local_environment(monkeypatch):
    for variable in (
        "ORGANON_ALLOW_FIXTURES", "ORGANON_APPROVERS_FILE", "ORGANON_LEDGER_ANCHORS_FILE",
        "ORGANON_ROOT",
    ):
        monkeypatch.delenv(variable, raising=False)


def _command(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(CLI), *args], text=True, capture_output=True, check=check)


def _cli(*args: str) -> dict:
    return json.loads(_command(*args).stdout)


def _data(result) -> dict:
    assert not result.is_error, result.content
    return result.structured_content or json.loads(result.content[0].text)


def _parameters(tmp_path: Path) -> StdioServerParameters:
    return StdioServerParameters(command=str(MCP), cwd=str(tmp_path), env=os.environ.copy())


def _init(path: Path, *, policy: str = "local") -> dict:
    return _cli(
        "init", str(path), "--title", "Local development", "--domain", "test",
        "--actor", OWNER, "--approval-policy", policy,
    )


def test_local_cli_and_stdio_mcp_persist_declared_decisions_and_resume(tmp_path):
    case = tmp_path / "local-case"
    path = str(case)
    initial = _init(case)
    ledger = case / "organon.json"
    assert initial["project"]["approval_policy"] == "local"
    assert initial["project"]["test_gate_policy"] == "local_report"
    assert initial["approval_trust"] == "local_declared"
    manifest = {"schema": 1, "steps": [
        {"op": "put", "id": "p1", "kind": "problem", "text": "A bounded development problem",
         "refs": [], "data": {}},
        {"op": "put", "id": "a1", "kind": "actor", "text": "Affected people",
         "refs": ["p1"], "data": {}},
        {"op": "put", "id": "b1", "kind": "boundary", "text": "One local development scope",
         "refs": ["p1", "a1"], "data": {}},
        {"op": "advance", "phase": "frame"},
    ]}
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

    async def exercise() -> dict:
        async with Client(_parameters(tmp_path), mode="legacy") as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            assert set(tools) == TOOLS
            init_schema = tools["init"].input_schema["properties"]
            assert init_schema["approval_policy"]["enum"] == ["signed", "local", "fixture"]
            assert init_schema["approval_policy"]["default"] == "signed"
            assert "local_report" in init_schema["test_gate_policy"]["enum"]

            second = tmp_path / "mcp-local-case"
            second_state = _data(await client.call_tool("init", {
                "path": str(second), "title": "MCP local", "domain": "test", "actor": OWNER,
                "approval_policy": "local", "test_gate_policy": "local_report",
            }))
            assert second_state["project"]["test_gate_policy"] == "local_report"
            assert (second / "organon.json").is_file()
            assert _data(await client.call_tool("status", {"path": str(second)})) == _cli(
                "status", str(second),
            )

            stopped = _data(await client.call_tool("run", {
                "path": path, "manifest": manifest, "actor": WRITER,
            }))
            assert stopped["reason"] == "independent_review_required"
            assert stopped["applied"] == 3
            assert set(_cli("status", path)["items"]) == {"p1", "a1", "b1"}
            task = _data(await client.call_tool("next_task", {"path": path}))
            assert task == _cli("next-task", path)
            assert task["action"] == "review_phase"

            before_review = ledger.read_bytes()
            rejected_review = await client.call_tool("review_phase", {
                "path": path, "phase": "frame", "verdict": "accept",
                "reason": "Author cannot supply the separate review", "actor": WRITER,
            })
            assert rejected_review.is_error
            assert ledger.read_bytes() == before_review
            review = _cli(
                "review-phase", path, "frame", "--verdict", "accept",
                "--reason", "I checked the local scope", "--actor", REVIEWER,
            )
            assert review["payload"]["provenance"] == "local_declared"
            assert "signature" not in review["payload"]
            resumed = _cli("run", path, "--manifest", str(manifest_file), "--actor", WRITER)
            assert resumed["skipped"] == 3 and resumed["applied"] == 1
            state = _data(await client.call_tool("status", {"path": path}))
            assert state == _cli("status", path)
            assert state["phases"]["frame"]["accepted"]
            assert not state["phase_review_history"][-1]["signature_verified"]
            assert state["phase_review_history"][-1]["provenance"] == "local_declared"

            _data(await client.call_tool("put", {
                "path": path, "id": "n1", "kind": "norm", "text": "Preserve participants' access",
                "refs": ["p1", "a1"], "actor": WRITER,
            }))
            approval = _data(await client.call_tool("approve", {
                "path": path, "id": "n1", "reason": "I authorize this development commitment",
                "actor": OWNER,
            }))
            assert approval["payload"]["provenance"] == "local_declared"
            assert "signature" not in approval["payload"]
            item = _cli("status", path)["items"]["n1"]
            assert item["approved"]
            assert item["approval_status"] == "local_declared"

            before_report = ledger.read_bytes()
            report = _data(await client.call_tool("report", {"path": path}))
            assert report == _cli("report", path)
            assert _command("report", path, "--format", "markdown").stdout == report["markdown"]
            assert report["next"] == _cli("next-task", path)
            assert report["artifact_count"] == 4
            assert report["accepted_phases"] == 1
            assert "limitations" in report and report["limitations"]
            assert ledger.read_bytes() == before_report
            return report

    report = asyncio.run(exercise())
    persisted = json.loads(ledger.read_text(encoding="utf-8"))
    assert persisted["project"]["approval_policy"] == "local"
    assert any(event["kind"] == "approval" for event in persisted["events"])
    assert _cli("status", path)["items"]["n1"]["approved"]

    async def reopen() -> None:
        async with Client(_parameters(tmp_path), mode="legacy") as client:
            assert _data(await client.call_tool("report", {"path": path})) == report

    asyncio.run(reopen())


def test_local_approval_rejects_other_actors_without_mutating_ledger(tmp_path):
    case = tmp_path / "local-approval"
    path = str(case)
    _init(case)
    _cli("put", path, "n1", "--kind", "norm", "--text", "A development commitment", "--actor", WRITER)
    ledger = case / "organon.json"
    before = ledger.read_bytes()

    async def exercise() -> None:
        async with Client(_parameters(tmp_path), mode="legacy") as client:
            for actor in ("human:other", "human:fixture", WRITER):
                failed = _command("approve", path, "n1", "--reason", "Explicit declaration",
                                  "--actor", actor, check=False)
                assert failed.returncode != 0 and not failed.stdout
                rejected = await client.call_tool("approve", {
                    "path": path, "id": "n1", "reason": "Explicit declaration", "actor": actor,
                })
                assert rejected.is_error
                assert ledger.read_bytes() == before

    asyncio.run(exercise())
    assert not _cli("status", path)["items"]["n1"]["approved"]


@pytest.mark.parametrize(("policy", "test_policy"), [
    ("local", "signed_observed"), ("signed", "local_report"), ("fixture", "local_report"),
])
def test_invalid_init_policy_pairs_preserve_existing_ledger_and_create_no_case(
    tmp_path, policy, test_policy,
):
    existing = tmp_path / "existing"
    _init(existing)
    before = (existing / "organon.json").read_bytes()
    missing = tmp_path / "missing"

    async def exercise() -> None:
        async with Client(_parameters(tmp_path), mode="legacy") as client:
            for case in (existing, missing):
                failed = _command(
                    "init", str(case), "--title", "Invalid policy", "--domain", "test",
                    "--actor", OWNER, "--approval-policy", policy, "--test-gate-policy", test_policy,
                    check=False,
                )
                assert failed.returncode != 0 and not failed.stdout
                rejected = await client.call_tool("init", {
                    "path": str(case), "title": "Invalid policy", "domain": "test", "actor": OWNER,
                    "approval_policy": policy, "test_gate_policy": test_policy,
                })
                assert rejected.is_error
                assert (existing / "organon.json").read_bytes() == before
                assert not missing.exists()

    asyncio.run(exercise())


def test_cli_and_mcp_keep_signed_default_and_reject_unsigned_approval(tmp_path):
    case = tmp_path / "signed-default"
    path = str(case)
    initial = _cli("init", path, "--title", "Default signed case", "--domain", "test", "--actor", OWNER)
    assert initial["project"]["approval_policy"] == "signed"
    assert "test_gate_policy" not in json.loads((case / "organon.json").read_text())["project"]
    _cli("put", path, "n1", "--kind", "norm", "--text", "A signed commitment", "--actor", WRITER)
    ledger = case / "organon.json"
    before = ledger.read_bytes()
    failed = _command("approve", path, "n1", "--reason", "Unsigned declaration", "--actor", OWNER, check=False)
    assert failed.returncode != 0
    assert "signature" in failed.stderr.lower()

    async def exercise() -> None:
        async with Client(_parameters(tmp_path), mode="legacy") as client:
            second = tmp_path / "mcp-default"
            state = _data(await client.call_tool("init", {
                "path": str(second), "title": "MCP default", "domain": "test", "actor": OWNER,
            }))
            assert state["project"]["approval_policy"] == "signed"
            rejected = await client.call_tool("approve", {
                "path": path, "id": "n1", "reason": "Unsigned declaration", "actor": OWNER,
            })
            assert rejected.is_error
            assert ledger.read_bytes() == before

    asyncio.run(exercise())
