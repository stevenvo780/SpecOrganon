"""Recheck the documentary bread frame through the installed CLI and MCP client.

This verifies local bytes and interface behavior. It does not authenticate
published measurements, a human approver, or a field intervention.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases" / "bread_norway"
CLI = Path(sys.executable).parent / "organon"
MCP = Path(sys.executable).parent / "organon-mcp"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cli(*args: str) -> dict:
    result = subprocess.run([str(CLI), *args], text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def tool_data(result) -> dict:
    assert not result.is_error, result.content
    if result.structured_content is not None:
        return result.structured_content
    assert len(result.content) == 1
    return json.loads(result.content[0].text)


async def check_mcp(manifest: dict, cli_views: dict, original_hash: str) -> dict:
    environment = os.environ.copy()
    environment["ORGANON_ROOT"] = str(CASE.parent)
    params = StdioServerParameters(command=str(MCP), cwd=str(ROOT), env=environment)
    checked: list[str] = []
    async with Client(params, mode="legacy") as client:
        discovered = {tool.name for tool in (await client.list_tools()).tools}
        assert {"status", "gate", "trace", "next_task", "run"} <= discovered
        for name, arguments in (
            ("status", {"path": CASE.name}),
            ("gate_frame", {"path": CASE.name, "phase": "frame"}),
            ("gate_critique", {"path": CASE.name, "phase": "critique"}),
            ("trace", {"path": CASE.name, "id": "n_bread_harm"}),
            ("next_task", {"path": CASE.name}),
        ):
            tool = "gate" if name.startswith("gate_") else name
            assert tool_data(await client.call_tool(tool, arguments)) == cli_views[name]
            checked.append(name)
        replay = tool_data(await client.call_tool(
            "run", {"path": CASE.name, "manifest": manifest, "actor": "agent:analyst"}
        ))
        assert replay["applied"] == 0 and replay["skipped"] == 20
        assert replay["reason"] == "human_approval_required"
        assert digest(CASE / "organon.json") == original_hash
        checked.append("idempotent_run")

        invalid = await client.call_tool(
            "run", {"path": CASE.name, "manifest": {"schema": 1, "steps": [
                {"op": "approve", "id": "n_bread_harm"}
            ]}, "actor": "agent:analyst"}
        )
        assert invalid.is_error
        assert digest(CASE / "organon.json") == original_hash
        checked.append("invalid_run_no_mutation")
    return {"discovered_tools": len(discovered), "parity_checks": checked}


def main() -> None:
    manifest_path = CASE / "frame_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    put_steps = [step for step in manifest["steps"] if step["op"] == "put"]
    evidence = [step for step in put_steps if step["kind"] == "evidence"]
    assert len(manifest["steps"]) == 20 and len(put_steps) == 19 and len(evidence) == 9
    source_hashes: dict[str, str] = {}
    for step in evidence:
        archive = step["data"]["archive"]
        observed = digest(CASE / archive)
        assert observed == step["data"]["source_sha256"]
        source_hashes[archive] = observed

    ledger_path = CASE / "organon.json"
    original_hash = digest(ledger_path)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    events = Counter(event["kind"] for event in ledger["events"])
    assert events == {"item_put": 19, "phase_review": 1, "phase_advance": 1}
    review = next(event for event in ledger["events"] if event["kind"] == "phase_review")
    assert review["actor"] == "agent:independent_reviewer"
    assert review["payload"]["phase"] == "frame"
    assert review["payload"]["verdict"] == "accept" and review["payload"]["independent"]

    path = str(CASE)
    cli_views = {
        "status": cli("status", path),
        "gate_frame": cli("gate", path, "frame"),
        "gate_critique": cli("gate", path, "critique"),
        "trace": cli("trace", path, "n_bread_harm"),
        "next_task": cli("next-task", path),
    }
    status = cli_views["status"]
    assert status["revision"] == 21 and status["project"]["approval_policy"] == "signed"
    assert status["phases"]["frame"]["accepted"]
    assert status["phases"]["frame"]["independent_review"]
    assert not status["phases"]["critique"]["ready"]
    assert "n_bread_harm requires a verified human approval" in status["phases"]["critique"]["blockers"]
    assert cli_views["next_task"]["action"] == "human_approval"
    assert cli_views["next_task"]["approval_targets"] == [{"id": "n_bread_harm", "version": 1}]
    mcp = asyncio.run(check_mcp(manifest, cli_views, original_hash))
    replay = cli("run", path, "--manifest", str(manifest_path), "--actor", "agent:analyst")
    assert replay["applied"] == 0 and replay["skipped"] == 20
    assert replay["reason"] == "human_approval_required" and digest(ledger_path) == original_hash

    report = {
        "schema": 1,
        "case": "cases/bread_norway",
        "scope": "documentary_development_frame_only",
        "source_sha256": dict(sorted(source_hashes.items())),
        "manifest_sha256": digest(manifest_path),
        "ledger_sha256": original_hash,
        "ledger_revision": status["revision"],
        "events": dict(sorted(events.items())),
        "frame_accepted": status["phases"]["frame"]["accepted"],
        "independent_review_recorded": status["phases"]["frame"]["independent_review"],
        "review_actor_is_unverified_label": review["actor"],
        "critique_blockers": status["phases"]["critique"]["blockers"],
        "approval_trust": status["approval_trust"],
        "next_action": cli_views["next_task"]["action"],
        "cli_replay_skipped": replay["skipped"],
        "mcp": mcp,
        "criterion_3": "not_assessed",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
