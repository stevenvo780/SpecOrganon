"""Probe an installed wheel's ledger commit window with real process SIGKILL.

Run with the Python from a virtual environment containing an installed wheel::

    /path/to/venv/bin/python scripts/probe_ledger_commit_crash.py /path/to/repo

The cases and manifest are private, synthetic fixtures. This tests process
interruption around ``os.replace``; it does not simulate power or host loss.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import specorganon
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from specorganon.ledger import ZERO_HASH, read_project


HOOK = '''\
"""Temporary, child-only commit-window injection for the installed wheel."""
import hashlib
import json
import os
import signal
from pathlib import Path

import specorganon.ledger as ledger

target = Path(os.environ["ORGANON_PROBE_LEDGER"]).resolve()
marker = Path(os.environ["ORGANON_PROBE_MARKER"])
phase = os.environ["ORGANON_PROBE_PHASE"]
original_replace = os.replace

def intercepted_replace(source, destination):
    if Path(destination).resolve() != target:
        return original_replace(source, destination)
    # MCP pins the case directory via /proc/self/fd; compare the actual parent.
    if Path(source).parent.resolve(strict=True) != target.parent or not Path(source).name.startswith(".organon-"):
        raise AssertionError("unexpected ledger replacement source")
    candidate = Path(source).read_bytes()
    document = ledger.strict_json_loads(candidate.decode("utf-8"))
    events = document["events"]
    if len(events) != 2:
        return original_replace(source, destination)
    if events[-1]["kind"] != "item_put" or events[-1]["payload"]["id"] != "a1":
        raise AssertionError("commit-window target was not the second manifest item")
    if phase == "after_replace":
        original_replace(source, destination)
    elif phase != "before_replace":
        raise AssertionError("invalid commit-window phase")
    proof = {
        "phase": phase,
        "candidate_revision": len(events),
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "ledger_module": str(Path(ledger.__file__).resolve()),
        "pid": os.getpid(),
    }
    with marker.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(proof, sort_keys=True) + "\\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.kill(os.getpid(), signal.SIGKILL)
    raise AssertionError("SIGKILL unexpectedly returned")

ledger.os.replace = intercepted_replace
'''

STEPS: list[dict[str, Any]] = [
    {
        "op": "put",
        "id": "p1",
        "kind": "problem",
        "text": "Synthetic commit fixture problem",
        "refs": [],
        "data": {},
    },
    {
        "op": "put",
        "id": "a1",
        "kind": "actor",
        "text": "Synthetic commit fixture actor",
        "refs": ["p1"],
        "data": {},
    },
    {
        "op": "put",
        "id": "b1",
        "kind": "boundary",
        "text": "Synthetic commit fixture boundary",
        "refs": ["p1", "a1"],
        "data": {},
    },
]
MANIFEST = {"schema": 1, "steps": STEPS}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _installed_module() -> Path:
    module = Path(specorganon.__file__).resolve()
    if not module.is_relative_to(Path(sys.prefix).resolve()):
        raise AssertionError(
            f"SpecOrganon is not installed in this Python environment: {module}"
        )
    return module


def _env(root: Path) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "PYTHONPATH",
            "PYTHONHOME",
            "ORGANON_APPROVERS_FILE",
            "ORGANON_LEDGER_ANCHORS_FILE",
        }
        and not key.startswith("ORGANON_PROBE_")
    }
    env["ORGANON_ALLOW_FIXTURES"] = "1"
    env["ORGANON_ROOT"] = str(root)
    return env


def _cli(
    command: Path, args: list[str], cwd: Path, env: dict[str, str]
) -> dict[str, Any]:
    result = subprocess.run(
        [str(command), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"installed CLI failed ({result.returncode}): {result.stderr[-1000:]}"
        )
    return json.loads(result.stdout)


def _ledger(case: Path) -> tuple[bytes, list[dict[str, Any]]]:
    raw = (case / "organon.json").read_bytes()
    document = read_project(case)
    events = document["events"]
    prior = ZERO_HASH
    for seq, event in enumerate(events, 1):
        _require(
            event["seq"] == seq and event["prev_hash"] == prior,
            "ledger event sequence or previous hash differs",
        )
        payload = {key: value for key, value in event.items() if key != "hash"}
        digest = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        _require(event["hash"] == digest, "ledger event hash differs")
        prior = digest
    return raw, events


def _interrupted_case(
    phase: str, root: Path, cli: Path, env: dict[str, str], module: Path
) -> tuple[Path, int]:
    case = root / phase
    _cli(
        cli,
        [
            "init",
            str(case),
            "--title",
            "Synthetic commit fixture",
            "--domain",
            "fixture",
            "--actor",
            "human:fixture",
            "--approval-policy",
            "fixture",
        ],
        root,
        env,
    )
    manifest_file = root / f"{phase}-manifest.json"
    manifest_file.write_text(json.dumps(MANIFEST), encoding="utf-8")
    hook_dir = root / f"{phase}-hook"
    hook_dir.mkdir()
    (hook_dir / "sitecustomize.py").write_text(HOOK, encoding="utf-8")
    marker = root / f"{phase}-hook.jsonl"
    child_env = {
        **env,
        "PYTHONPATH": str(hook_dir),
        "ORGANON_PROBE_LEDGER": str(case / "organon.json"),
        "ORGANON_PROBE_MARKER": str(marker),
        "ORGANON_PROBE_PHASE": phase,
    }
    result = subprocess.run(
        [
            str(cli),
            "run",
            str(case),
            "--manifest",
            str(manifest_file),
            "--actor",
            "agent:runner",
        ],
        cwd=root,
        env=child_env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    if not marker.is_file():
        raise AssertionError(
            f"{phase}: commit-window injection did not fire; exit={result.returncode}; "
            f"stderr={result.stderr[-1000:]}"
        )
    proofs = marker.read_text(encoding="utf-8").splitlines()
    _require(len(proofs) == 1, f"{phase}: hook activated {len(proofs)} times")
    proof = json.loads(proofs[0])
    _require(proof["phase"] == phase, f"{phase}: hook phase differs")
    _require(
        proof["candidate_revision"] == 2, f"{phase}: hook candidate revision differs"
    )
    _require(
        proof["ledger_module"] == str(module.parent / "ledger.py"),
        f"{phase}: hook loaded an unexpected ledger module",
    )
    _require(
        result.returncode == -signal.SIGKILL,
        f"{phase}: runner was not killed at the commit window ({result.returncode})",
    )
    _require(not result.stdout, f"{phase}: killed runner unexpectedly returned output")
    raw, events = _ledger(case)
    expected_revision = 1 if phase == "before_replace" else 2
    _require(len(events) == expected_revision, f"{phase}: recovered revision differs")
    _require(
        [event["payload"]["id"] for event in events]
        == [step["id"] for step in STEPS[:expected_revision]],
        f"{phase}: recovered manifest prefix differs",
    )
    if phase == "after_replace":
        _require(
            hashlib.sha256(raw).hexdigest() == proof["candidate_sha256"],
            f"{phase}: published bytes differ from replacement candidate",
        )
    return case, expected_revision


def _result_data(result: Any) -> dict[str, Any]:
    _require(not result.is_error, "MCP tool returned an error")
    if result.structured_content is not None:
        return result.structured_content
    _require(len(result.content) == 1, "MCP tool did not return one result")
    return json.loads(result.content[0].text)


async def _resume(
    case: Path, checkpoint: int, root: Path, mcp: Path, env: dict[str, str]
) -> dict[str, Any]:
    _, checkpoint_events = _ledger(case)
    _require(len(checkpoint_events) == checkpoint, "checkpoint revision differs")
    params = StdioServerParameters(command=str(mcp), cwd=str(root), env=env)
    async with Client(params, mode="legacy") as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        _require({"run", "status"} <= tools, "installed MCP server lacks run or status")
        result = _result_data(
            await client.call_tool(
                "run",
                {
                    "path": str(case),
                    "manifest": MANIFEST,
                    "actor": "agent:runner",
                },
            )
        )
        _require(
            result["applied"] == len(STEPS) - checkpoint,
            "MCP resume applied unexpected step count",
        )
        _require(
            result["skipped"] == checkpoint, "MCP resume skipped unexpected step count"
        )
        _require(
            result["cursor"] == result["total_steps"] == len(STEPS),
            "MCP resume cursor differs",
        )
        _require(result["status"] == "waiting", "MCP resume status differs")
        raw, events = _ledger(case)
        ids = [event["payload"]["id"] for event in events]
        _require(len(events) == len(STEPS), "MCP resume ledger length differs")
        _require(
            events[:checkpoint] == checkpoint_events,
            "MCP resume changed checkpoint prefix",
        )
        _require(
            all(event["kind"] == "item_put" for event in events),
            "MCP resume contains an unexpected event kind",
        )
        _require(ids == [step["id"] for step in STEPS], "MCP resume item order differs")
        _require(len(set(ids)) == len(STEPS), "MCP resume duplicated an item")
        status = _result_data(await client.call_tool("status", {"path": str(case)}))
        _require(status["revision"] == len(STEPS), "MCP status revision differs")
        _require(set(status["items"]) == set(ids), "MCP status items differ")
        _require(
            all(item["version"] == 1 for item in status["items"].values()),
            "MCP status item versions differ",
        )
        replay = _result_data(
            await client.call_tool(
                "run",
                {
                    "path": str(case),
                    "manifest": MANIFEST,
                    "actor": "agent:runner",
                },
            )
        )
        _require(
            replay["applied"] == 0 and replay["skipped"] == len(STEPS),
            "MCP replay was not idempotent",
        )
        _require(
            replay["cursor"] == replay["total_steps"] == len(STEPS),
            "MCP replay cursor differs",
        )
        byte_identical_replay = (case / "organon.json").read_bytes() == raw
        _require(byte_identical_replay, "MCP replay changed ledger bytes")
    return {
        "checkpoint_revision": checkpoint,
        "resume_applied": result["applied"],
        "resume_skipped": result["skipped"],
        "final_revision": len(STEPS),
        "unique_manifest_ids": len(ids),
        "byte_identical_replay": byte_identical_replay,
    }


async def _exercise() -> dict[str, Any]:
    module = _installed_module()
    bin_dir = Path(sys.executable).parent
    cli, mcp = bin_dir / "organon", bin_dir / "organon-mcp"
    _require(
        cli.is_file() and mcp.is_file(), "installed wheel entry points are missing"
    )
    with tempfile.TemporaryDirectory(prefix="specorganon-commit-probe-") as directory:
        root = Path(directory)
        env = _env(root)
        windows = {}
        for phase in ("before_replace", "after_replace"):
            case, checkpoint = _interrupted_case(phase, root, cli, env, module)
            windows[phase] = await _resume(case, checkpoint, root, mcp, env)
    return {
        "classification": "installed_wheel_process_sigkill_commit_window_probe",
        "windows": windows,
        "hook_activations_per_window": 1,
        "host_or_power_loss_durability_tested": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "repo", type=Path, help="repository path containing this probe script"
    )
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    _require(
        (repo / "scripts" / Path(__file__).name).resolve() == Path(__file__).resolve(),
        "probe script is not under the supplied repository",
    )
    print(json.dumps(asyncio.run(_exercise()), sort_keys=True))


if __name__ == "__main__":
    main()
