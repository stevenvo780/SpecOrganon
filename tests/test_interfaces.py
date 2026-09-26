"""End-to-end parity checks using the installed CLI and a real stdio MCP client."""

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
pytestmark = pytest.mark.usefixtures("enable_fixture_policy")
TOOLS = {
    "init",
    "put",
    "status",
    "review",
    "approve",
    "approval_challenge",
    "challenge",
    "resolve_challenge",
    "gate",
    "review_phase",
    "advance",
    "trace",
    "next_task",
    "run",
}


def cli(*args: str) -> dict:
    completed = subprocess.run([str(CLI), *args], text=True, capture_output=True, check=True)
    return json.loads(completed.stdout)


def result_data(result) -> dict:
    assert not result.is_error, result.content
    if result.structured_content is not None:
        return result.structured_content
    assert len(result.content) == 1
    return json.loads(result.content[0].text)


def test_cli_and_real_stdio_mcp_share_state_and_gate(tmp_path):
    case = tmp_path / "case"
    path = str(case)
    cli("init", path, "--title", "Food chain", "--domain", "food", "--actor", "human:fixture", "--approval-policy", "fixture")
    project_file = case / "organon.json"
    assert project_file.is_file()
    assert json.loads(project_file.read_text())["project"]["title"] == "Food chain"

    async def exercise() -> None:
        params = StdioServerParameters(command=str(MCP), cwd=str(tmp_path), env=os.environ.copy())
        async with Client(params, mode="legacy") as client:
            discovered = await client.list_tools()
            assert TOOLS <= {tool.name for tool in discovered.tools}

            second = tmp_path / "mcp-case"
            result_data(
                await client.call_tool(
                    "init",
                    {"path": str(second), "title": "Second case", "domain": "test", "actor": "human:fixture", "approval_policy": "fixture"},
                )
            )
            assert (second / "organon.json").is_file()
            assert result_data(await client.call_tool("status", {"path": str(second)})) == cli(
                "status", str(second)
            )

            manifest = {"schema": 1, "steps": [
                {"op": "put", "id": "p1", "kind": "problem", "text": "Synthetic interface problem", "refs": [], "data": {}},
                {"op": "put", "id": "a1", "kind": "actor", "text": "Synthetic actor", "refs": ["p1"], "data": {}},
                {"op": "put", "id": "b1", "kind": "boundary", "text": "Synthetic boundary", "refs": ["p1", "a1"], "data": {}},
                {"op": "advance", "phase": "frame"},
            ]}
            manifest_file = tmp_path / "interface-manifest.json"
            manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
            first_run = result_data(await client.call_tool(
                "run", {"path": str(second), "manifest": manifest, "actor": "agent:writer"}
            ))
            assert first_run["reason"] == "independent_review_required"
            assert first_run["applied"] == 3
            task = result_data(await client.call_tool("next_task", {"path": str(second)}))
            assert task == cli("next-task", str(second))
            assert task["action"] == "review_phase"
            cli("review-phase", str(second), "frame", "--verdict", "accept", "--reason", "Fixture review", "--actor", "agent:reviewer")
            resumed = cli("run", str(second), "--manifest", str(manifest_file), "--actor", "agent:writer")
            assert resumed["skipped"] == 3 and resumed["applied"] == 1
            assert result_data(await client.call_tool("status", {"path": str(second)}))["phases"]["frame"]["accepted"]
            before_bad_run = (second / "organon.json").read_bytes()
            bad_run = await client.call_tool(
                "run", {"path": str(second), "manifest": {"schema": 1, "steps": [{"op": "approve", "id": "p1"}]}, "actor": "agent:writer"}
            )
            assert bad_run.is_error
            assert (second / "organon.json").read_bytes() == before_bad_run

            before = result_data(await client.call_tool("status", {"path": path}))
            assert before == cli("status", path)

            result_data(
                await client.call_tool(
                    "put",
                    {
                        "path": path,
                        "id": "problem",
                        "kind": "problem",
                        "text": "Food value changes along the chain.",
                        "refs": [],
                        "data": {},
                        "actor": "researcher",
                    },
                )
            )
            ledger = json.loads(project_file.read_text())
            assert len(ledger["events"]) == 1
            assert "problem" in json.dumps(ledger["events"][0])

            unchanged = project_file.read_bytes()
            rejected = await client.call_tool(
                "put",
                {"path": path, "id": "baditem", "kind": "not-a-kind", "text": "Invalid", "actor": "researcher"},
            )
            assert rejected.is_error
            assert project_file.read_bytes() == unchanged

            after = result_data(await client.call_tool("status", {"path": path}))
            assert after == cli("status", path)
            assert result_data(await client.call_tool("trace", {"path": path, "id": "problem"})) == cli(
                "trace", path, "problem"
            )
            blocked = result_data(await client.call_tool("gate", {"path": path, "phase": "frame"}))
            assert blocked == cli("gate", path, "frame")
            assert blocked["ready"] is False
            failed_advance = await client.call_tool(
                "advance", {"path": path, "phase": "frame", "actor": "researcher"}
            )
            assert failed_advance.is_error
            assert len(json.loads(project_file.read_text())["events"]) == 1

            cli("put", path, "affected", "--kind", "actor", "--text", "Consumers", "--actor", "researcher")
            cli("put", path, "scope", "--kind", "boundary", "--text", "One regional chain", "--actor", "researcher")
            ready = result_data(await client.call_tool("gate", {"path": path, "phase": "frame"}))
            assert ready == cli("gate", path, "frame")
            assert ready["ready"] is True

            result_data(
                await client.call_tool(
                    "review_phase",
                    {"path": path, "phase": "frame", "verdict": "accept", "reason": "Scope is explicit", "actor": "reviewer"},
                )
            )
            result_data(await client.call_tool("advance", {"path": path, "phase": "frame", "actor": "researcher"}))
            accepted = result_data(await client.call_tool("status", {"path": path}))
            assert accepted == cli("status", path)
            assert accepted["phases"]["frame"]["accepted"] is True

            cli(
                "put", path, "commitment", "--kind", "norm", "--text", "Preserve safe food access",
                "--ref", "problem", "--ref", "affected", "--actor", "researcher",
            )
            result_data(
                await client.call_tool(
                    "approve",
                    {"path": path, "id": "commitment", "reason": "Fixture approved the stated value", "actor": "human:fixture"},
                )
            )
            assert cli("status", path)["items"]["commitment"]["approved"] is True

            contested_event = result_data(
                await client.call_tool(
                    "challenge",
                    {"path": path, "left": "problem", "right": "affected", "reason": "Actor disputes the framing", "actor": "reviewer"},
                )
            )
            challenged = result_data(await client.call_tool("status", {"path": path}))
            assert challenged == cli("status", path)
            assert challenged["phases"]["frame"]["accepted"] is False
            assert len(challenged["open_challenges"]) == 1

            result_data(
                await client.call_tool(
                    "put",
                    {
                        "path": path, "id": "resolution", "kind": "synthesis",
                        "text": "Clarify the framing with both viewpoints.", "refs": ["problem", "affected"],
                        "data": {}, "actor": "researcher",
                    },
                )
            )
            result_data(
                await client.call_tool(
                    "review",
                    {"path": path, "id": "resolution", "verdict": "accept", "reason": "Addresses both items", "actor": "reviewer"},
                )
            )
            result_data(
                await client.call_tool(
                    "resolve_challenge",
                    {"path": path, "challenge_seq": contested_event["seq"], "resolution_item": "resolution", "actor": "reviewer"},
                )
            )
            resolved = result_data(await client.call_tool("status", {"path": path}))
            assert resolved == cli("status", path)
            assert resolved["open_challenges"] == []
            assert resolved["phases"]["frame"]["accepted"] is False
            assert len(json.loads(project_file.read_text())["events"]) == 11
            result_data(
                await client.call_tool(
                    "review_phase",
                    {"path": path, "phase": "frame", "verdict": "accept", "reason": "Rechecked after challenge resolution", "actor": "reviewer"},
                )
            )
            cli("advance", path, "frame", "--actor", "researcher")
            assert result_data(await client.call_tool("status", {"path": path}))["phases"]["frame"]["accepted"]

    asyncio.run(exercise())


def test_bad_cli_json_preserves_case(tmp_path):
    case = tmp_path / "case"
    cli("init", str(case), "--title", "Case", "--domain", "test", "--actor", "human:fixture", "--approval-policy", "fixture")
    before = (case / "organon.json").read_bytes()
    failed = subprocess.run(
        [
            str(CLI),
            "put",
            str(case),
            "bad",
            "--kind",
            "problem",
            "--text",
            "Bad data",
            "--data",
            "[]",
            "--actor",
            "researcher",
        ],
        text=True,
        capture_output=True,
    )
    assert failed.returncode != 0
    assert "--data must be a JSON object" in failed.stderr
    assert (case / "organon.json").read_bytes() == before


@pytest.mark.parametrize(
    ("data", "error"),
    (
        ('{"value":NaN}', "non-finite JSON number"),
        ('{"nested":{"values":[1,Infinity]}}', "non-finite JSON number"),
        ('{"nested":{"value":-Infinity}}', "non-finite JSON number"),
        ('{"value":1e9999}', "non-finite JSON number"),
        ('{"value":1e-9999}', "JSON number underflows to zero"),
        ('{"value":-1e-9999}', "JSON number underflows to zero"),
        ('{"value":0.1234567890123456789}', "JSON number loses decimal precision"),
    ),
)
def test_cli_rejects_nonfinite_or_underflow_json_before_mutation(tmp_path, data, error):
    case = tmp_path / "strict-json-case"
    cli("init", str(case), "--title", "Case", "--domain", "test", "--actor", "agent:writer")
    project_file = case / "organon.json"
    before = project_file.read_bytes()

    failed = subprocess.run(
        [str(CLI), "put", str(case), "bad", "--kind", "problem", "--text", "Bad data",
         "--data", data, "--actor", "agent:writer"],
        text=True, capture_output=True,
    )
    assert failed.returncode != 0
    assert error in failed.stderr
    assert project_file.read_bytes() == before


def test_mcp_status_rejects_nonfinite_ledger_and_keeps_valid_json_structured(tmp_path):
    case = tmp_path / "strict-mcp-case"
    path = str(case)
    cli("init", path, "--title", "Case", "--domain", "test", "--actor", "agent:writer")
    cli("put", path, "valid", "--kind", "problem", "--text", "Valid decimal and Unicode",
        "--data", '{"measurement":{"value":0.125,"label":"piñón"}}', "--actor", "agent:writer")
    project_file = case / "organon.json"

    async def exercise() -> None:
        params = StdioServerParameters(command=str(MCP), cwd=str(tmp_path), env=os.environ.copy())
        async with Client(params, mode="legacy") as client:
            valid = await client.call_tool("status", {"path": path})
            assert isinstance(valid.structured_content, dict)
            assert result_data(valid)["items"]["valid"]["data"] == {
                "measurement": {"value": 0.125, "label": "piñón"}
            }

            poisoned = json.loads(project_file.read_text(encoding="utf-8"))
            poisoned["events"][0]["payload"]["data"]["measurement"]["value"] = float("nan")
            project_file.write_text(json.dumps(poisoned, ensure_ascii=False), encoding="utf-8")
            rejected = await client.call_tool("status", {"path": path})
            assert rejected.is_error
            assert any("non-finite JSON number NaN" in part.text for part in rejected.content)

    asyncio.run(exercise())


def test_cli_and_mcp_guarded_puts_reject_stale_versions_without_writing(tmp_path):
    case = tmp_path / "guarded-case"
    path = str(case)
    cli("init", path, "--title", "Guarded writes", "--domain", "test", "--actor", "human:fixture",
        "--approval-policy", "fixture")
    project_file = case / "organon.json"
    cli("put", path, "p1", "--kind", "problem", "--text", "Initial problem", "--actor", "agent:writer",
        "--expected-version", "0", "--expected-deps", "{}")

    async def exercise() -> None:
        params = StdioServerParameters(command=str(MCP), cwd=str(tmp_path), env=os.environ.copy())
        async with Client(params, mode="legacy") as client:
            result_data(await client.call_tool("put", {
                "path": path, "id": "a1", "kind": "actor", "text": "Initial actor", "refs": ["p1"],
                "data": {}, "actor": "agent:writer", "expected_version": 0, "expected_deps": {"p1": 1},
            }))
            assert cli("status", path)["items"]["a1"]["deps"] == {"p1": 1}

            cli("put", path, "p1", "--kind", "problem", "--text", "Revised problem",
                "--actor", "agent:writer", "--expected-version", "1", "--expected-deps", "{}")
            before = project_file.read_bytes()
            stale_target = subprocess.run([
                str(CLI), "put", path, "p1", "--kind", "problem", "--text", "Lost update",
                "--actor", "agent:writer", "--expected-version", "1", "--expected-deps", "{}",
            ], text=True, capture_output=True)
            assert stale_target.returncode != 0
            assert "item version conflict" in stale_target.stderr
            assert project_file.read_bytes() == before

            stale_target_mcp = await client.call_tool("put", {
                "path": path, "id": "p1", "kind": "problem", "text": "Lost update", "refs": [],
                "data": {}, "actor": "agent:writer", "expected_version": 1, "expected_deps": {},
            })
            assert stale_target_mcp.is_error
            assert project_file.read_bytes() == before

            stale_ref = subprocess.run([
                str(CLI), "put", path, "a1", "--kind", "actor", "--text", "Stale actor",
                "--ref", "p1", "--actor", "agent:writer", "--expected-version", "1",
                "--expected-deps", '{"p1": 1}',
            ], text=True, capture_output=True)
            assert stale_ref.returncode != 0
            assert "dependency version conflict" in stale_ref.stderr
            assert project_file.read_bytes() == before

            stale_ref_mcp = await client.call_tool("put", {
                "path": path, "id": "a1", "kind": "actor", "text": "Stale actor", "refs": ["p1"],
                "data": {}, "actor": "agent:writer", "expected_version": 1, "expected_deps": {"p1": 1},
            })
            assert stale_ref_mcp.is_error
            assert project_file.read_bytes() == before

            cli("put", path, "a1", "--kind", "actor", "--text", "Actor with revised problem",
                "--ref", "p1", "--actor", "agent:writer", "--expected-version", "1",
                "--expected-deps", '{"p1": 2}')
            result_data(await client.call_tool("put", {
                "path": path, "id": "a1", "kind": "actor", "text": "Actor clarified", "refs": ["p1"],
                "data": {}, "actor": "agent:writer", "expected_version": 2, "expected_deps": {"p1": 2},
            }))
            state = cli("status", path)
            assert state["items"]["p1"]["version"] == 2
            assert state["items"]["a1"]["version"] == 3
            assert state["items"]["a1"]["deps"] == {"p1": 2}
            assert len(json.loads(project_file.read_text())["events"]) == 5

    asyncio.run(exercise())


def test_mcp_auto_mode_confines_cases_to_explicit_root(tmp_path):
    root = tmp_path / "allowed"
    launch = tmp_path / "launch"
    outside = tmp_path / "outside"
    for directory in (root, launch, outside):
        directory.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)

    async def exercise() -> None:
        params = StdioServerParameters(
            command=str(MCP), cwd=str(launch), env={**os.environ, "ORGANON_ROOT": str(root)}
        )
        async with Client(params, mode="auto") as client:
            discovered = await client.list_tools()
            assert TOOLS <= {tool.name for tool in discovered.tools}

            for candidate in ("../outside/blocked", str(outside / "blocked"), "escape/blocked"):
                rejected = await client.call_tool(
                    "init", {"path": candidate, "title": "Blocked", "domain": "test", "actor": "human:fixture", "approval_policy": "fixture"}
                )
                assert rejected.is_error, candidate
                assert not (outside / "blocked" / "organon.json").exists()

            result_data(
                await client.call_tool(
                    "init", {"path": "case", "title": "Allowed", "domain": "test", "actor": "human:fixture", "approval_policy": "fixture"},
                )
            )
            project_file = root / "case" / "organon.json"
            assert project_file.is_file()
            assert json.loads(project_file.read_text())["project"]["title"] == "Allowed"
            assert result_data(await client.call_tool("status", {"path": "case"})) == cli("status", str(root / "case"))

            (root / "alias").symlink_to(root / "case", target_is_directory=True)
            assert result_data(await client.call_tool("status", {"path": "alias"})) == cli("status", str(root / "case"))

    asyncio.run(exercise())
