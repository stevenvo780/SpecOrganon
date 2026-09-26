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
import signal
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
    mcp_tools_seen: set[str] = set()
    expected_cli_commands = {
        "init", "put", "status", "review", "approve", "approval-challenge", "challenge",
        "resolve-challenge", "gate", "review-phase", "advance", "trace", "next-task", "run",
    }
    expected_mcp_tools = {name.replace("-", "_") for name in expected_cli_commands}

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
                async def call_tool(name: str, arguments: dict):
                    result = await client.call_tool(name, arguments)
                    mcp_tools_seen.add(name)
                    return result

                discovered_tools = {tool.name for tool in (await client.list_tools()).tools}
                assert discovered_tools == expected_mcp_tools
                data(await call_tool("init", {
                    "path": path, "title": "Synthetic clean install fixture", "domain": "fixture", "actor": "human:fixture", "approval_policy": "fixture",
                }))
                first = command("run", path, "--manifest", str(repo / "workflows" / "synthetic_full.json"), "--actor", "agent:runner")
                assert first["reason"] == "independent_review_required"
                assert first["next"] == data(await call_tool("next_task", {"path": path}))

                decisions = 0
                for _ in range(24):
                    task = data(await call_tool("next_task", {"path": path}))
                    if task["status"] == "done":
                        break
                    if task["action"] == "human_approval":
                        for target in task["approval_targets"]:
                            command("approve", path, target["id"], "--reason", "Synthetic fixture approval", "--actor", "human:fixture")
                            decisions += 1
                    elif task["action"] == "review_phase":
                        data(await call_tool("review_phase", {
                            "path": path, "phase": task["phase"], "verdict": "accept",
                            "reason": "Synthetic fixture review", "actor": "agent:reviewer",
                        }))
                        decisions += 1
                    else:
                        raise AssertionError((task["phase"], task["action"], task["blockers"]))
                    result = data(await call_tool("run", {"path": path, "manifest": manifest, "actor": "agent:runner"}))
                    assert result["status"] in {"waiting", "complete"}
                else:
                    raise AssertionError("decision budget exceeded")

                status = command("status", path)
                assert status == data(await call_tool("status", {"path": path}))
                assert len(status["items"]) == 29
                assert all(phase["accepted"] for phase in status["phases"].values())
                assert status["items"]["n1"]["approval_status"] == "fixture"
                assert status["items"]["ass1"]["data"]["verdict"] == "no_demostrado"
                before = (case / "organon.json").read_bytes()
                rejected = await call_tool("put", {
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
                command("put", cli_case, "p1", "--kind", "problem", "--text", "Fixture problem", "--actor", "agent:writer",
                        "--expected-version", "0")
                cli_ledger = Path(cli_case) / "organon.json"
                before_stale = cli_ledger.read_bytes()
                stale = subprocess.run([
                    str(cli), "put", cli_case, "p1", "--kind", "problem", "--text", "Competing create",
                    "--actor", "agent:other", "--expected-version", "0",
                ], text=True, capture_output=True, env=smoke_env)
                assert stale.returncode != 0 and cli_ledger.read_bytes() == before_stale
                command("put", cli_case, "a1", "--kind", "actor", "--text", "Fixture actor", "--ref", "p1",
                        "--actor", "agent:writer", "--expected-version", "0", "--expected-deps", '{"p1":1}')
                command("put", cli_case, "b1", "--kind", "boundary", "--text", "Fixture boundary", "--ref", "p1",
                        "--actor", "agent:writer", "--expected-version", "0", "--expected-deps", '{"p1":1}')
                command("review-phase", cli_case, "frame", "--verdict", "accept", "--reason", "Fixture review", "--actor", "agent:reviewer")
                command("advance", cli_case, "frame", "--actor", "agent:writer")
                objection = command("challenge", cli_case, "p1", "a1", "--reason", "Fixture dispute", "--actor", "agent:reviewer")
                command("put", cli_case, "syn2", "--kind", "synthesis", "--text", "Fixture reconciliation", "--ref", "p1", "--ref", "a1",
                        "--actor", "agent:writer", "--expected-version", "0", "--expected-deps", '{"p1":1,"a1":1}')
                command("review", cli_case, "syn2", "--verdict", "accept", "--reason", "Fixture source review", "--actor", "agent:reviewer")
                command("resolve-challenge", cli_case, str(objection["seq"]), "syn2", "--actor", "agent:writer")
                assert command("status", cli_case)["open_challenges"] == []
                assert not command("gate", cli_case, "frame")["accepted"]

                # Invoke the remaining MCP operations on an isolated synthetic fixture.
                mcp_case = Path(directory) / "mcp-inventory-case"
                mcp_path = str(mcp_case)
                data(await call_tool("init", {
                    "path": mcp_path, "title": "MCP inventory fixture", "domain": "fixture",
                    "actor": "human:fixture", "approval_policy": "fixture",
                }))
                for item_id, kind, description, refs, expected_deps in (
                    ("p1", "problem", "Synthetic problem", [], {}),
                    ("a1", "actor", "Synthetic affected actor", ["p1"], {"p1": 1}),
                    ("b1", "boundary", "Synthetic boundary", ["p1"], {"p1": 1}),
                ):
                    data(await call_tool("put", {
                        "path": mcp_path, "id": item_id, "kind": kind, "text": description,
                        "refs": refs, "actor": "agent:writer", "expected_version": 0,
                        "expected_deps": expected_deps,
                    }))
                before_stale = (mcp_case / "organon.json").read_bytes()
                stale_ref = await call_tool("put", {
                    "path": mcp_path, "id": "stale", "kind": "actor", "text": "Stale reference",
                    "refs": ["p1"], "actor": "agent:other", "expected_version": 0,
                    "expected_deps": {"p1": 2},
                })
                assert stale_ref.is_error and (mcp_case / "organon.json").read_bytes() == before_stale
                assert command("gate", mcp_path, "frame")["ready"]
                data(await call_tool("review_phase", {
                    "path": mcp_path, "phase": "frame", "verdict": "accept",
                    "reason": "Synthetic frame review", "actor": "agent:reviewer",
                }))
                advanced = data(await call_tool("advance", {
                    "path": mcp_path, "phase": "frame", "actor": "agent:writer",
                }))
                ledger_path = mcp_case / "organon.json"
                events = json.loads(ledger_path.read_text(encoding="utf-8"))["events"]
                assert [event["kind"] for event in events] == [
                    "item_put", "item_put", "item_put", "phase_review", "phase_advance",
                ]
                assert advanced == events[-1]
                assert command("status", mcp_path)["phases"]["frame"]["accepted"]

                contested = data(await call_tool("challenge", {
                    "path": mcp_path, "left": "p1", "right": "a1",
                    "reason": "Synthetic framing dispute", "actor": "agent:reviewer",
                }))
                challenged_status = command("status", mcp_path)
                assert contested == json.loads(ledger_path.read_text(encoding="utf-8"))["events"][-1]
                assert [entry["seq"] for entry in challenged_status["open_challenges"]] == [contested["seq"]]
                assert not challenged_status["phases"]["frame"]["accepted"]
                assert challenged_status == data(await call_tool("status", {"path": mcp_path}))

                data(await call_tool("put", {
                    "path": mcp_path, "id": "syn1", "kind": "synthesis",
                    "text": "Synthetic reconciliation", "refs": ["p1", "a1"], "actor": "agent:writer",
                    "expected_version": 0, "expected_deps": {"p1": 1, "a1": 1},
                }))
                reviewed = data(await call_tool("review", {
                    "path": mcp_path, "id": "syn1", "verdict": "accept",
                    "reason": "Addresses both synthetic items", "actor": "agent:reviewer",
                }))
                assert reviewed == json.loads(ledger_path.read_text(encoding="utf-8"))["events"][-1]
                resolved = data(await call_tool("resolve_challenge", {
                    "path": mcp_path, "challenge_seq": contested["seq"],
                    "resolution_item": "syn1", "actor": "agent:writer",
                }))
                events = json.loads(ledger_path.read_text(encoding="utf-8"))["events"]
                assert [event["kind"] for event in events] == [
                    "item_put", "item_put", "item_put", "phase_review", "phase_advance",
                    "challenge", "item_put", "item_review", "challenge_resolved",
                ]
                assert resolved == events[-1]
                assert resolved["payload"]["challenge_seq"] == contested["seq"]
                assert resolved["payload"]["resolution_item"] == "syn1"
                assert resolved["payload"]["review_seq"] == reviewed["seq"]
                resolved_status = command("status", mcp_path)
                assert resolved_status == data(await call_tool("status", {"path": mcp_path}))
                assert resolved_status["open_challenges"] == []
                assert not resolved_status["phases"]["frame"]["accepted"]
                mcp_trace = data(await call_tool("trace", {"path": mcp_path, "id": "syn1"}))
                assert mcp_trace == command("trace", mcp_path, "syn1")
                assert mcp_trace["item"]["id"] == "syn1"
                assert {item["id"] for item in mcp_trace["ancestors"]} == {"p1", "a1"}

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
                mcp_challenge = data(await call_tool("approval_challenge", {
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
                rejected_signature = await call_tool("approve", {**approval_args, "signature": wrong_signature})
                assert rejected_signature.is_error
                assert "approval signature is invalid" in str(rejected_signature.content)
                assert (signed_dir / "organon.json").read_bytes() == before_challenge
                assert command("gate", signed_case, "critique") == unsigned_gate

                signature = base64.b64encode(signer.sign(message)).decode("ascii")
                data(await call_tool("approve", {**approval_args, "signature": signature}))
                signed_status = command("status", signed_case)
                assert signed_status == data(await call_tool("status", {"path": signed_case}))
                assert signed_status["items"]["n1"]["approved"]
                assert signed_status["items"]["n1"]["approval_status"] == "signed_verified"
                signed_gate = command("gate", signed_case, "critique")
                assert signed_gate == data(await call_tool("gate", {"path": signed_case, "phase": "critique"}))
                assert signed_gate["ready"] and not signed_gate["accepted"]
                command("review-phase", signed_case, "critique", "--verdict", "accept", "--reason", "Synthetic independent review", "--actor", "agent:reviewer")
                command("advance", signed_case, "critique", "--actor", "agent:runner")
                assert command("gate", signed_case, "critique")["accepted"]

                approved_ledger = (signed_dir / "organon.json").read_bytes()
                trust_file.write_text(json.dumps({"schema": 2, "cases": {}}), encoding="utf-8")
                reopened = data(await call_tool("status", {"path": signed_case}))
                assert reopened == command("status", signed_case)
                assert reopened["approval_trust"] == "unavailable"
                assert not reopened["items"]["n1"]["approved"]
                reopened_gate = data(await call_tool("gate", {"path": signed_case, "phase": "critique"}))
                assert reopened_gate == command("gate", signed_case, "critique")
                assert not reopened_gate["ready"] and not reopened_gate["accepted"]
                assert any("approval" in blocker for blocker in reopened_gate["blockers"])
                assert (signed_dir / "organon.json").read_bytes() == approved_ledger

                # Kill an installed CLI runner after a durable checkpoint, then resume that manifest via MCP.
                interrupted_case = Path(directory) / "interrupted-case"
                interrupted_path = str(interrupted_case)
                command("init", interrupted_path, "--title", "Synthetic interrupted runner", "--domain", "fixture",
                        "--actor", "human:fixture", "--approval-policy", "fixture")
                interrupted_steps = [
                    {"op": "put", "id": "p1", "kind": "problem", "text": "Synthetic problem", "refs": [], "data": {}},
                    {"op": "put", "id": "b1", "kind": "boundary", "text": "Synthetic boundary", "refs": ["p1"], "data": {}},
                ]
                interrupted_steps.extend(
                    {"op": "put", "id": f"a{index}", "kind": "actor", "text": f"Synthetic actor {index}",
                     "refs": ["p1"], "data": {}}
                    for index in range(160)
                )
                interrupted_manifest = {"schema": 1, "steps": interrupted_steps}
                interrupted_file = Path(directory) / "interrupted-manifest.json"
                interrupted_file.write_text(json.dumps(interrupted_manifest), encoding="utf-8")
                interrupted_ledger = interrupted_case / "organon.json"
                interrupted_process = await asyncio.create_subprocess_exec(
                    str(cli), "run", interrupted_path, "--manifest", str(interrupted_file), "--actor", "agent:runner",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=smoke_env,
                )
                try:
                    deadline = asyncio.get_running_loop().time() + 10
                    observed = 0
                    while asyncio.get_running_loop().time() < deadline:
                        observed = len(json.loads(interrupted_ledger.read_text(encoding="utf-8"))["events"])
                        if observed >= 3:
                            assert interrupted_process.returncode is None, "CLI runner finished before SIGKILL"
                            break
                        if interrupted_process.returncode is not None:
                            stdout, stderr = await interrupted_process.communicate()
                            raise AssertionError(f"CLI runner exited before checkpoint: {stdout!r} {stderr!r}")
                        await asyncio.sleep(0.002)
                    else:
                        raise AssertionError("installed CLI runner did not persist a checkpoint within 10 seconds")
                    interrupted_process.send_signal(signal.SIGKILL)
                    stdout, stderr = await asyncio.wait_for(interrupted_process.communicate(), timeout=10)
                    assert interrupted_process.returncode == -signal.SIGKILL, (stdout, stderr)
                finally:
                    if interrupted_process.returncode is None:
                        interrupted_process.kill()
                        await asyncio.wait_for(interrupted_process.communicate(), timeout=10)

                checkpoint_events = json.loads(interrupted_ledger.read_text(encoding="utf-8"))["events"]
                checkpoint = len(checkpoint_events)
                assert 3 <= observed <= checkpoint < len(interrupted_steps)
                resumed = data(await call_tool("run", {
                    "path": interrupted_path, "manifest": interrupted_manifest, "actor": "agent:runner",
                }))
                assert resumed["applied"] == len(interrupted_steps) - checkpoint
                assert resumed["skipped"] == checkpoint
                assert resumed["cursor"] == resumed["total_steps"] == len(interrupted_steps)
                assert resumed["status"] == "waiting"
                interrupted_events = json.loads(interrupted_ledger.read_text(encoding="utf-8"))["events"]
                interrupted_ids = [event["payload"]["id"] for event in interrupted_events]
                planned_ids = {step["id"] for step in interrupted_steps}
                assert len(interrupted_events) == len(interrupted_steps)
                assert interrupted_events[:checkpoint] == checkpoint_events
                assert all(event["kind"] == "item_put" for event in interrupted_events)
                assert [event["seq"] for event in interrupted_events] == list(range(1, len(interrupted_steps) + 1))
                assert len({event["hash"] for event in interrupted_events}) == len(interrupted_events)
                assert len(interrupted_ids) == len(set(interrupted_ids)) and set(interrupted_ids) == planned_ids
                interrupted_status = command("status", interrupted_path)
                assert interrupted_status == data(await call_tool("status", {"path": interrupted_path}))
                assert interrupted_status["revision"] == len(interrupted_steps)
                assert set(interrupted_status["items"]) == planned_ids
                assert all(item["version"] == 1 and not item["issues"] and not item["stale"]
                           for item in interrupted_status["items"].values())
                before_replay = interrupted_ledger.read_bytes()
                replay = data(await call_tool("run", {
                    "path": interrupted_path, "manifest": interrupted_manifest, "actor": "agent:runner",
                }))
                assert replay["applied"] == 0 and replay["skipped"] == len(interrupted_steps)
                assert replay["cursor"] == len(interrupted_steps) and replay["status"] == resumed["status"]
                assert interrupted_ledger.read_bytes() == before_replay

                # Release two installed CLI writers together; neither caller retries a failed put.
                # This checks preservation of both writes, not that their ledger reads collided.
                concurrent_case = Path(directory) / "concurrent-case"
                concurrent_path = str(concurrent_case)
                command("init", concurrent_path, "--title", "Synthetic concurrent writers", "--domain", "fixture",
                        "--actor", "human:fixture", "--approval-policy", "fixture")
                command("put", concurrent_path, "p1", "--kind", "problem", "--text", "Stable synthetic reference",
                        "--actor", "agent:writer", "--expected-version", "0")
                barrier = 'printf "READY\\n"; IFS= read -r start || exit 97; exec "$@"'
                writers = []
                try:
                    for item_id, kind, writer_actor in (
                        ("a1", "actor", "agent:writer_a"),
                        ("b1", "boundary", "agent:writer_b"),
                    ):
                        writer = await asyncio.create_subprocess_exec(
                            "/bin/sh", "-c", barrier, "organon-ready", str(cli), "put", concurrent_path, item_id,
                            "--kind", kind, "--text", f"Synthetic concurrent {kind}", "--ref", "p1",
                            "--actor", writer_actor, "--expected-version", "0", "--expected-deps", '{"p1":1}',
                            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE, env=smoke_env,
                        )
                        writers.append(writer)
                    ready = await asyncio.wait_for(
                        asyncio.gather(*(writer.stdout.readline() for writer in writers)), timeout=10,
                    )
                    assert ready == [b"READY\n", b"READY\n"]
                    assert all(writer.returncode is None for writer in writers)
                    for writer in writers:
                        writer.stdin.write(b"go\n")
                    await asyncio.wait_for(asyncio.gather(*(writer.stdin.drain() for writer in writers)), timeout=5)
                    outputs = await asyncio.wait_for(
                        asyncio.gather(*(writer.communicate() for writer in writers)), timeout=15,
                    )
                    assert all(writer.returncode == 0 for writer in writers), outputs
                    written = [json.loads(stdout) for stdout, _ in outputs]
                    assert {item["id"] for item in written} == {"a1", "b1"}
                    assert {item["seq"] for item in written} == {2, 3}
                finally:
                    for writer in writers:
                        if writer.returncode is None:
                            writer.kill()
                    await asyncio.wait_for(asyncio.gather(*(writer.wait() for writer in writers)), timeout=10)

                concurrent_events = json.loads((concurrent_case / "organon.json").read_text(encoding="utf-8"))["events"]
                assert [event["seq"] for event in concurrent_events] == [1, 2, 3]
                assert len({event["hash"] for event in concurrent_events}) == 3
                assert {event["payload"]["id"] for event in concurrent_events} == {"p1", "a1", "b1"}
                assert all(event["kind"] == "item_put" for event in concurrent_events)
                assert {(event["payload"]["id"], event["actor"]) for event in concurrent_events[1:]} == {
                    ("a1", "agent:writer_a"), ("b1", "agent:writer_b"),
                }
                assert all(concurrent_events[item["seq"] - 1]["payload"]["id"] == item["id"] for item in written)
                concurrent_status = command("status", concurrent_path)
                assert concurrent_status == data(await call_tool("status", {"path": concurrent_path}))
                assert concurrent_status["revision"] == 3 and set(concurrent_status["items"]) == {"p1", "a1", "b1"}
                assert concurrent_status["items"]["p1"]["version"] == 1
                assert all(concurrent_status["items"][item_id]["version"] == 1
                           and concurrent_status["items"][item_id]["deps"] == {"p1": 1}
                           and not concurrent_status["items"][item_id]["issues"]
                           for item_id in ("a1", "b1"))
                assert cli_commands_seen == expected_cli_commands
                assert mcp_tools_seen == expected_mcp_tools
                return {"phases_accepted": len(status["phases"]), "items": len(status["items"]),
                        "decisions": decisions, "revision": status["revision"], "invalid_input_preserved_ledger": True,
                        "idempotent_replay": True, "cli_commands_exercised": len(cli_commands_seen),
                        "mcp_tools_exercised": len(mcp_tools_seen),
                        "guarded_put": True,
                        "sigkill_mcp_resume": True, "sigkill_checkpoint_events": checkpoint,
                        "paired_cli_writers_preserved_items": True,
                        "signed_approval_verified": True, "invalid_signatures_rejected": True,
                        "trust_removal_reopened": True}

    print(json.dumps(asyncio.run(exercise()), sort_keys=True))


if __name__ == "__main__":
    main()
