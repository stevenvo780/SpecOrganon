"""Exercise a built wheel through its CLI and a real stdio MCP client.

Run this with the Python interpreter of a fresh virtual environment that has
installed the wheel, passing the repository root as the sole argument. All
case content and human labels are synthetic fixtures.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters


def main() -> None:
    repo = Path(sys.argv[1]).resolve()
    manifest = json.loads((repo / "workflows" / "synthetic_full.json").read_text(encoding="utf-8"))
    bin_dir = Path(sys.executable).parent
    cli = bin_dir / "organon"
    mcp = bin_dir / "organon-mcp"
    smoke_env = {key: value for key, value in os.environ.items() if key != "ORGANON_APPROVERS_FILE"}
    smoke_env["ORGANON_ALLOW_FIXTURES"] = "1"

    def command(*args: str) -> dict:
        result = subprocess.run([str(cli), *args], text=True, capture_output=True, check=True, env=smoke_env)
        return json.loads(result.stdout)

    def data(result) -> dict:
        assert not result.is_error, result.content
        return result.structured_content or json.loads(result.content[0].text)

    async def exercise() -> dict:
        with tempfile.TemporaryDirectory(prefix="specorganon-wheel-") as directory:
            case = Path(directory) / "case"
            path = str(case)
            params = StdioServerParameters(command=str(mcp), cwd=directory, env=smoke_env)
            async with Client(params, mode="legacy") as client:
                tools = {tool.name for tool in (await client.list_tools()).tools}
                assert {"init", "put", "status", "next_task", "run", "review_phase", "approve", "approval_challenge"} <= tools
                data(await client.call_tool("init", {
                    "path": path, "title": "Synthetic clean install fixture", "domain": "fixture", "actor": "human:fixture", "approval_policy": "fixture",
                }))
                first = command("run", path, "--manifest", str(repo / "workflows" / "synthetic_full.json"), "--actor", "agent:runner")
                assert first["reason"] == "independent_review_required"
                assert first["next"] == data(await client.call_tool("next_task", {"path": path}))

                decisions = 0
                for _ in range(24):
                    task = data(await client.call_tool("next_task", {"path": path}))
                    if task["status"] == "done":
                        break
                    if task["action"] == "human_approval":
                        for target in task["approval_targets"]:
                            command("approve", path, target["id"], "--reason", "Synthetic fixture approval", "--actor", "human:fixture")
                            decisions += 1
                    elif task["action"] == "review_phase":
                        data(await client.call_tool("review_phase", {
                            "path": path, "phase": task["phase"], "verdict": "accept",
                            "reason": "Synthetic fixture review", "actor": "agent:reviewer",
                        }))
                        decisions += 1
                    else:
                        raise AssertionError((task["phase"], task["action"], task["blockers"]))
                    result = data(await client.call_tool("run", {"path": path, "manifest": manifest, "actor": "agent:runner"}))
                    assert result["status"] in {"waiting", "complete"}
                else:
                    raise AssertionError("decision budget exceeded")

                status = command("status", path)
                assert status == data(await client.call_tool("status", {"path": path}))
                assert len(status["items"]) == 29
                assert all(phase["accepted"] for phase in status["phases"].values())
                assert status["items"]["n1"]["approval_status"] == "fixture"
                assert status["items"]["ass1"]["data"]["verdict"] == "no_demostrado"
                before = (case / "organon.json").read_bytes()
                rejected = await client.call_tool("put", {
                    "path": path, "id": "bad", "kind": "invented-kind", "text": "invalid", "actor": "agent:runner",
                })
                assert rejected.is_error
                assert (case / "organon.json").read_bytes() == before
                replay = command("run", path, "--manifest", str(repo / "workflows" / "synthetic_full.json"), "--actor", "agent:runner")
                assert replay["applied"] == 0 and replay["status"] == "complete"
                assert (case / "organon.json").read_bytes() == before
                assert command("next-task", path)["status"] == "done"
                assert command("gate", path, "validate")["accepted"]
                assert command("trace", path, "ass1")["item"]["kind"] == "assessment"

                # Complete the CLI command inventory on a separate synthetic case.
                cli_case = str(Path(directory) / "cli-case")
                command("init", cli_case, "--title", "CLI inventory fixture", "--domain", "fixture", "--actor", "human:fixture", "--approval-policy", "fixture")
                command("put", cli_case, "p1", "--kind", "problem", "--text", "Fixture problem", "--actor", "agent:writer")
                command("put", cli_case, "a1", "--kind", "actor", "--text", "Fixture actor", "--ref", "p1", "--actor", "agent:writer")
                command("put", cli_case, "b1", "--kind", "boundary", "--text", "Fixture boundary", "--ref", "p1", "--actor", "agent:writer")
                command("review-phase", cli_case, "frame", "--verdict", "accept", "--reason", "Fixture review", "--actor", "agent:reviewer")
                command("advance", cli_case, "frame", "--actor", "agent:writer")
                objection = command("challenge", cli_case, "p1", "a1", "--reason", "Fixture dispute", "--actor", "agent:reviewer")
                command("put", cli_case, "syn2", "--kind", "synthesis", "--text", "Fixture reconciliation", "--ref", "p1", "--ref", "a1", "--actor", "agent:writer")
                command("review", cli_case, "syn2", "--verdict", "accept", "--reason", "Fixture source review", "--actor", "agent:reviewer")
                command("resolve-challenge", cli_case, str(objection["seq"]), "syn2", "--actor", "agent:writer")
                assert command("status", cli_case)["open_challenges"] == []
                assert not command("gate", cli_case, "frame")["accepted"]

                # Exercise the read-only signed protocol without a private key or trust file.
                signed_case = str(Path(directory) / "signed-case")
                signed_actor = "human:synthetic-signer"
                signed_reason = "Synthetic signing challenge only"
                command("init", signed_case, "--title", "Signed challenge inventory", "--domain", "fixture", "--actor", signed_actor)
                command("put", signed_case, "n1", "--kind", "norm", "--text", "Synthetic commitment", "--actor", "agent:writer")
                assert command("status", signed_case)["project"]["approval_policy"] == "signed"
                before_challenge = (Path(signed_case) / "organon.json").read_bytes()
                cli_challenge = command("approval-challenge", signed_case, "n1", "--reason", signed_reason, "--actor", signed_actor)
                mcp_challenge = data(await client.call_tool("approval_challenge", {
                    "path": signed_case, "id": "n1", "reason": signed_reason, "actor": signed_actor,
                }))
                assert mcp_challenge == cli_challenge
                assert (Path(signed_case) / "organon.json").read_bytes() == before_challenge
                return {"phases_accepted": len(status["phases"]), "items": len(status["items"]),
                        "decisions": decisions, "revision": status["revision"], "invalid_input_preserved_ledger": True,
                        "idempotent_replay": True, "cli_commands_exercised": 14}

    print(json.dumps(asyncio.run(exercise()), sort_keys=True))


if __name__ == "__main__":
    main()
