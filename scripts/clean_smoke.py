"""Exercise a built wheel through its CLI and a real stdio MCP client.

Run this with the Python interpreter of a fresh virtual environment that has
installed the wheel, passing the repository root as the sole argument. All
case content and human labels are synthetic fixtures.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters


def main() -> None:
    repo = Path(sys.argv[1]).resolve()
    manifest = json.loads((repo / "workflows" / "synthetic_full.json").read_text(encoding="utf-8"))
    bin_dir = Path(sys.executable).parent
    cli = bin_dir / "organon"
    mcp = bin_dir / "organon-mcp"
    smoke_env = {key: value for key, value in os.environ.items()
                 if key not in {"ORGANON_APPROVERS_FILE", "ORGANON_LEDGER_ANCHORS_FILE"}}
    smoke_env["ORGANON_ALLOW_FIXTURES"] = "1"
    cli_commands_seen: set[str] = set()
    expected_cli_commands = {
        "init", "put", "status", "review", "approve", "approval-challenge", "challenge",
        "resolve-challenge", "gate", "review-phase", "advance", "trace", "next-task", "run",
    }

    def command(*args: str) -> dict:
        result = subprocess.run([str(cli), *args], text=True, capture_output=True, check=True, env=smoke_env)
        parsed = json.loads(result.stdout)
        cli_commands_seen.add(args[0])
        return parsed

    def command_rejected(*args: str) -> None:
        result = subprocess.run([str(cli), *args], text=True, capture_output=True, env=smoke_env)
        assert result.returncode != 0 and not result.stdout
        assert "signed approval requires an Ed25519 signature" in result.stderr

    def data(result) -> dict:
        assert not result.is_error, result.content
        return result.structured_content or json.loads(result.content[0].text)

    async def exercise() -> dict:
        with tempfile.TemporaryDirectory(prefix="specorganon-wheel-") as directory:
            case = Path(directory) / "case"
            path = str(case)
            trust_file = Path(directory) / "trusted-approvers.json"
            trust_file.write_text(json.dumps({"schema": 2, "cases": {}}), encoding="utf-8")
            smoke_env["ORGANON_APPROVERS_FILE"] = str(trust_file)
            params = StdioServerParameters(command=str(mcp), cwd=directory, env=smoke_env)
            async with Client(params, mode="legacy") as client:
                tools = {tool.name for tool in (await client.list_tools()).tools}
                assert tools == {name.replace("-", "_") for name in expected_cli_commands}
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

                # Exercise the full signed protocol using only synthetic data and an in-memory private key.
                signed_dir = Path(directory) / "signed-case"
                signed_case = str(signed_dir)
                signed_actor = "human:synthetic-signer"
                signed_reason = "Synthetic signature for the exact normative commitment"
                signer = Ed25519PrivateKey.generate()
                initial = command("init", signed_case, "--title", "Synthetic signed approval", "--domain", "fixture", "--actor", signed_actor)
                assert initial["project"]["approval_policy"] == "signed"
                public_key = signer.public_key().public_bytes(
                    encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
                )
                trust_file.write_text(json.dumps({
                    "schema": 2,
                    "cases": {initial["project"]["case_id"]: {
                        "path": str(signed_dir.resolve(strict=True)),
                        "project_sha256": initial["project_sha256"],
                        "approvers": {signed_actor: base64.b64encode(public_key).decode("ascii")},
                    }},
                }), encoding="utf-8")
                assert command("status", signed_case)["approval_trust"] == "configured"
                command("put", signed_case, "p1", "--kind", "problem", "--text", "Synthetic problem", "--actor", "agent:writer")
                command("put", signed_case, "a1", "--kind", "actor", "--text", "Synthetic affected group", "--ref", "p1", "--actor", "agent:writer")
                command("put", signed_case, "b1", "--kind", "boundary", "--text", "Synthetic boundary", "--ref", "p1", "--actor", "agent:writer")
                command("review-phase", signed_case, "frame", "--verdict", "accept", "--reason", "Synthetic frame review", "--actor", "agent:reviewer")
                command("advance", signed_case, "frame", "--actor", "agent:runner")
                for item_id, kind, description in (
                    ("c1", "concept", "Synthetic concept"),
                    ("s1", "assumption", "Synthetic assumption"),
                    ("f1", "frame_option", "First synthetic framing"),
                    ("f2", "frame_option", "Second synthetic framing"),
                ):
                    command("put", signed_case, item_id, "--kind", kind, "--text", description, "--ref", "p1", "--actor", "agent:writer")
                command("put", signed_case, "n1", "--kind", "norm", "--text", "Synthetic normative commitment",
                        "--ref", "p1", "--ref", "a1", "--actor", "agent:writer")
                unsigned_gate = command("gate", signed_case, "critique")
                assert not unsigned_gate["ready"] and any("approval" in blocker for blocker in unsigned_gate["blockers"])
                before_challenge = (signed_dir / "organon.json").read_bytes()
                cli_challenge = command("approval-challenge", signed_case, "n1", "--reason", signed_reason, "--actor", signed_actor)
                mcp_challenge = data(await client.call_tool("approval_challenge", {
                    "path": signed_case, "id": "n1", "reason": signed_reason, "actor": signed_actor,
                }))
                assert mcp_challenge == cli_challenge
                assert (signed_dir / "organon.json").read_bytes() == before_challenge
                message = base64.b64decode(cli_challenge["message_base64"], validate=True)
                assert cli_challenge["algorithm"] == "Ed25519"
                assert hashlib.sha256(message).hexdigest() == cli_challenge["message_sha256"]
                signed_fields = json.loads(message)
                assert signed_fields["actor"] == signed_actor and signed_fields["reason"] == signed_reason
                assert signed_fields["item_id"] == "n1" and signed_fields["item_version"] == 1
                assert signed_fields["case_path"] == str(signed_dir.resolve(strict=True))
                assert signed_fields["project_sha256"] == initial["project_sha256"]
                assert signed_fields["ledger_head_sha256"] == json.loads(before_challenge)["events"][-1]["hash"]

                approval_args = {"path": signed_case, "id": "n1", "reason": signed_reason, "actor": signed_actor}
                command_rejected("approve", signed_case, "n1", "--reason", signed_reason, "--actor", signed_actor)
                wrong_signature = base64.b64encode(bytes(64)).decode("ascii")
                rejected_signature = await client.call_tool("approve", {**approval_args, "signature": wrong_signature})
                assert rejected_signature.is_error
                assert "approval signature is invalid" in str(rejected_signature.content)
                assert (signed_dir / "organon.json").read_bytes() == before_challenge
                assert command("gate", signed_case, "critique") == unsigned_gate

                signature = base64.b64encode(signer.sign(message)).decode("ascii")
                data(await client.call_tool("approve", {**approval_args, "signature": signature}))
                signed_status = command("status", signed_case)
                assert signed_status == data(await client.call_tool("status", {"path": signed_case}))
                assert signed_status["items"]["n1"]["approved"]
                assert signed_status["items"]["n1"]["approval_status"] == "signed_verified"
                signed_gate = command("gate", signed_case, "critique")
                assert signed_gate == data(await client.call_tool("gate", {"path": signed_case, "phase": "critique"}))
                assert signed_gate["ready"] and not signed_gate["accepted"]
                command("review-phase", signed_case, "critique", "--verdict", "accept", "--reason", "Synthetic independent review", "--actor", "agent:reviewer")
                command("advance", signed_case, "critique", "--actor", "agent:runner")
                assert command("gate", signed_case, "critique")["accepted"]

                approved_ledger = (signed_dir / "organon.json").read_bytes()
                trust_file.write_text(json.dumps({"schema": 2, "cases": {}}), encoding="utf-8")
                reopened = data(await client.call_tool("status", {"path": signed_case}))
                assert reopened == command("status", signed_case)
                assert reopened["approval_trust"] == "unavailable"
                assert not reopened["items"]["n1"]["approved"]
                reopened_gate = data(await client.call_tool("gate", {"path": signed_case, "phase": "critique"}))
                assert reopened_gate == command("gate", signed_case, "critique")
                assert not reopened_gate["ready"] and not reopened_gate["accepted"]
                assert any("approval" in blocker for blocker in reopened_gate["blockers"])
                assert (signed_dir / "organon.json").read_bytes() == approved_ledger
                assert cli_commands_seen == expected_cli_commands
                return {"phases_accepted": len(status["phases"]), "items": len(status["items"]),
                        "decisions": decisions, "revision": status["revision"], "invalid_input_preserved_ledger": True,
                        "idempotent_replay": True, "cli_commands_exercised": len(cli_commands_seen),
                        "signed_approval_verified": True, "invalid_signatures_rejected": True,
                        "trust_removal_reopened": True}

    print(json.dumps(asyncio.run(exercise()), sort_keys=True))


if __name__ == "__main__":
    main()
