"""Kill an installed MCP server during run, then reconnect and resume.

Run with a fresh virtual environment containing the installed wheel::

    /path/to/venv/bin/python scripts/probe_mcp_server_crash.py /path/to/repo

This synthetic probe covers a process crash around ledger replacement, not a
host or power failure. The caller must receive a transport failure.
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

from mcp import MCPError
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from mcp_types import CONNECTION_CLOSED

import probe_ledger_commit_crash as base


HOOK = base.HOOK


def _stdio_wrapper(mcp: Path) -> None:
    """Expose the child's stdio and retain its observed wait status."""
    child_env = os.environ.copy()
    child_env["PYTHONPATH"] = child_env.pop("ORGANON_PROBE_HOOK_DIR")
    status_path = Path(child_env.pop("ORGANON_PROBE_CHILD_STATUS"))
    child = subprocess.Popen(
        [str(mcp)],
        stdin=sys.stdin.buffer,
        stdout=sys.stdout.buffer,
        stderr=sys.stderr.buffer,
        env=child_env,
    )
    returncode = child.wait()
    with status_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps({"pid": child.pid, "returncode": returncode}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _leaf_errors(error: BaseException) -> list[BaseException]:
    if isinstance(error, BaseExceptionGroup):
        return [leaf for nested in error.exceptions for leaf in _leaf_errors(nested)]
    return [error]


async def _interrupt_server(
    phase: str, root: Path, cli: Path, mcp: Path, env: dict[str, str], module: Path
) -> tuple[Path, int, list[str]]:
    case = root / phase
    base._cli(
        cli,
        [
            "init", str(case), "--title", "Synthetic MCP crash fixture",
            "--domain", "fixture", "--actor", "human:fixture",
            "--approval-policy", "fixture",
        ],
        root,
        env,
    )
    hook_dir = root / f"{phase}-hook"
    hook_dir.mkdir()
    (hook_dir / "sitecustomize.py").write_text(HOOK, encoding="utf-8")
    marker = root / f"{phase}-hook.jsonl"
    child_status = root / f"{phase}-child-status.json"
    wrapper_env = {
        **env,
        "ORGANON_PROBE_HOOK_DIR": str(hook_dir),
        "ORGANON_PROBE_CHILD_STATUS": str(child_status),
        "ORGANON_PROBE_LEDGER": str(case / "organon.json"),
        "ORGANON_PROBE_MARKER": str(marker),
        "ORGANON_PROBE_PHASE": phase,
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).resolve()), "--stdio-wrapper", str(mcp)],
        cwd=str(root),
        env=wrapper_env,
    )
    call_started = False
    call_returned = False
    call_failure: Exception | None = None
    cleanup_failure: Exception | None = None
    try:
        async with Client(params, mode="legacy") as client:
            tools = {tool.name for tool in (await client.list_tools()).tools}
            base._require({"run", "status"} <= tools, "installed MCP lacks run or status")
            call_started = True
            try:
                await asyncio.wait_for(
                    client.call_tool(
                        "run",
                        {"path": str(case), "manifest": base.MANIFEST, "actor": "agent:runner"},
                    ),
                    timeout=15,
                )
            except Exception as exc:
                call_failure = exc
            else:
                call_returned = True
    except Exception as exc:
        if not call_started:
            raise
        cleanup_failure = exc
    if call_returned:
        raise AssertionError(f"{phase}: MCP run returned without a server crash")
    if call_failure is None:
        raise AssertionError(f"{phase}: MCP run did not report a transport failure") from cleanup_failure
    leaves = _leaf_errors(call_failure)
    if not leaves or any(
        not isinstance(leaf, MCPError) or leaf.code != CONNECTION_CLOSED
        for leaf in leaves
    ):
        raise AssertionError(
            f"{phase}: MCP call failed for a reason other than connection closure"
        ) from call_failure
    transport_error_types = sorted({type(leaf).__name__ for leaf in leaves})

    if not marker.is_file():
        raise AssertionError(
            f"{phase}: MCP transport failed without commit-window injection"
        )
    proofs = marker.read_text(encoding="utf-8").splitlines()
    base._require(len(proofs) == 1, f"{phase}: hook activated {len(proofs)} times")
    proof = json.loads(proofs[0])
    base._require(proof["phase"] == phase, f"{phase}: hook phase differs")
    base._require(
        proof["candidate_revision"] == 2,
        f"{phase}: hook candidate revision differs",
    )
    base._require(
        proof["ledger_module"] == str(module.parent / "ledger.py"),
        f"{phase}: hook loaded an unexpected ledger module",
    )
    if not child_status.is_file():
        raise AssertionError(f"{phase}: MCP child wait status is missing")
    status = json.loads(child_status.read_text(encoding="utf-8"))
    base._require(status["pid"] == proof["pid"], f"{phase}: child PID differs")
    base._require(
        status["returncode"] == -signal.SIGKILL,
        f"{phase}: MCP server did not exit with SIGKILL ({status['returncode']})",
    )
    try:
        os.kill(proof["pid"], 0)
    except ProcessLookupError:
        pass
    else:
        raise AssertionError(f"{phase}: killed MCP server process remains live")

    raw, events = base._ledger(case)
    expected_revision = 1 if phase == "before_replace" else 2
    base._require(len(events) == expected_revision, f"{phase}: checkpoint differs")
    base._require(
        [event["payload"]["id"] for event in events]
        == [step["id"] for step in base.STEPS[:expected_revision]],
        f"{phase}: checkpoint prefix differs",
    )
    if phase == "after_replace":
        base._require(
            hashlib.sha256(raw).hexdigest() == proof["candidate_sha256"],
            f"{phase}: published bytes differ from replacement candidate",
        )
    return case, expected_revision, transport_error_types


async def _exercise() -> dict[str, Any]:
    module = base._installed_module()
    bin_dir = Path(sys.executable).parent
    cli, mcp = bin_dir / "organon", bin_dir / "organon-mcp"
    base._require(cli.is_file() and mcp.is_file(), "installed entry points are missing")
    with tempfile.TemporaryDirectory(prefix="specorganon-mcp-crash-") as directory:
        root = Path(directory)
        env = base._env(root)
        windows = {}
        for phase in ("before_replace", "after_replace"):
            case, checkpoint, transport_error_types = await _interrupt_server(
                phase, root, cli, mcp, env, module
            )
            resumed = await base._resume(case, checkpoint, root, mcp, env)
            cli_status = base._cli(cli, ["status", str(case)], root, env)
            params = StdioServerParameters(command=str(mcp), cwd=str(root), env=env)
            async with Client(params, mode="legacy") as client:
                mcp_status = base._result_data(
                    await client.call_tool("status", {"path": str(case)})
                )
            base._require(cli_status == mcp_status, f"{phase}: CLI/MCP status differs")
            windows[phase] = {
                **resumed,
                "transport_failed": True,
                "transport_error_types": transport_error_types,
                "cli_mcp_status_equal": True,
            }
    return {
        "classification": "installed_wheel_mcp_server_sigkill_commit_window_probe",
        "windows": windows,
        "hook_activations_per_window": 1,
        "host_or_power_loss_durability_tested": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    base._require(
        (repo / "scripts" / Path(__file__).name).resolve() == Path(__file__).resolve(),
        "probe script is not under the supplied repository",
    )
    print(json.dumps(asyncio.run(_exercise()), sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--stdio-wrapper":
        _stdio_wrapper(Path(sys.argv[2]))
    else:
        main()
