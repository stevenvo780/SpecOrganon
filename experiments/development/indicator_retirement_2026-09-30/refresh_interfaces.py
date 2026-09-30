"""One frozen current-wheel interface refresh per external Python environment.

Historical signed capture code is executed byte exactly, with its wheel digest
global explicitly configured to the new committed wheel. This is an instrument
adaptation, not a rerun of D103 under its historical digest or acceptance claims.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback


DOSSIER = "experiments/development/indicator_retirement_2026-09-30"
SIGNED = "scripts/probe_installed_signed_transports.py"
SIGNED_SHA = "3b7deea460f779234f4650f20c36788ad890ff56e7e45103f4c1f5b293583013"
BOOT = (
    "import sys; raw=sys.stdin.buffer.read(); name=sys.argv[1]; "
    "sys.argv=sys.argv[1:]; exec(compile(raw,name,'exec'),"
    "{'__name__':'__main__','__file__':name,'__package__':None})"
)


def pin(raw: bytes) -> dict:
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def write(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)


def serialized(value) -> bytes:
    return (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode()


def verify(repo: Path, frozen: dict) -> dict:
    source = {}
    for name, expected in frozen["files"].items():
        path = repo / name
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(repo):
            raise ValueError(f"unsafe frozen file: {name}")
        raw = path.read_bytes()
        if pin(raw) != expected:
            raise ValueError(f"frozen input differs: {name}")
        source[name] = raw
    if pin(source[SIGNED])["sha256"] != SIGNED_SHA:
        raise ValueError("historical signed capture source differs")
    return source


def journal() -> dict:
    def load(id, kind):
        return {"load_id": id, "material_id": "invented-control-material", "kind": kind,
                "mass": {"value": 10, "unit": "kg", "uncertainty": 0},
                "basis": "wet", "dry_fraction": 0.8}
    return {"schema": 1, "classification": "lot_journal_declared_only",
            "journal_id": "D107-synthetic-interface-control", "events": [{
                "id": "synthetic-operation", "stage": "Invented mechanics test",
                "stage_role": "transformation", "actor": "agent:synthetic-recorder",
                "at_utc": "2026-09-30T10:00:00Z", "inputs": [load("feed1", "feed")],
                "outputs": [load("product1", "product")], "balance_tolerance_kg": 0,
                "source": {"source_id": "synthetic-only", "locator": "row/1",
                           "observed_at_utc": "2026-09-30T10:00:00Z",
                           "method": "invented fixture; no field observation",
                           "record_sha256": "a" * 64}}]}


async def audit_mcp(executable: str, output: Path, env: dict, value: dict) -> dict:
    from mcp.client import Client
    from mcp.client.stdio import StdioServerParameters
    async with Client(StdioServerParameters(command=executable, cwd=str(output), env=env), mode="legacy") as client:
        response = await asyncio.wait_for(client.call_tool("audit_lot_journal", {"journal": value}), 90)
        write(output / "audit_mcp.json", serialized({"tool": "audit_lot_journal", "arguments": {"journal": value},
              "response": response.model_dump(mode="json", by_alias=True),
              "response_scope": "raw SDK model, not wire framing"}))
        if response.is_error:
            raise ValueError("MCP lot journal positive call failed")
        return response.structured_content or json.loads(response.content[0].text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("env", choices=("311", "312"))
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    name = DOSSIER + "/source_freeze.json"
    committed = subprocess.check_output(["git", "show", "HEAD:" + name], cwd=repo)
    if (repo / name).read_bytes() != committed:
        raise ValueError("freeze differs from Git HEAD")
    frozen = json.loads(committed)
    source = verify(repo, frozen)
    setting = frozen["environments"][args.env]
    if Path(sys.executable).absolute() != Path(setting["python"]).absolute():
        raise ValueError("refresh must run in the frozen external interpreter")
    output = Path(frozen["runtime"]) / ("interfaces-" + args.env)
    output.mkdir(mode=0o700)  # Exclusive attempt marker; no automatic repeat.
    write(output / "started.json", serialized({"git_head": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(), "freeze": pin(committed),
        "started_at_utc": dt.datetime.now(dt.UTC).isoformat(), "attempts": 1}))
    environment = {"PATH": str(Path(sys.executable).parent) + ":/usr/local/bin:/usr/bin:/bin",
                   "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC",
                   "TMPDIR": str(output), "PYTHONDONTWRITEBYTECODE": "1",
                   "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    if "HOME" in os.environ:
        environment["HOME"] = os.environ["HOME"]
    receipt = {"classification": "development current-wheel installed interface refresh",
               "passed": False, "commands": [], "human_authority_authenticated": False,
               "field_impact_evaluated": False, "provider_calls": 0, "Q": None,
               "automatic_retry": False, "counts_toward_required_24_runs": False}

    def run(label, argv, raw=None):
        began = time.monotonic()
        record = {"label": label, "argv": argv, "cwd": str(output),
                  "started_at_utc": dt.datetime.now(dt.UTC).isoformat()}
        if raw is not None:
            write(output / (label + ".executed.py"), raw)
            record["stdin_source"] = pin(raw)
        receipt["commands"].append(record)
        process = None
        try:
            with (output / (label + ".stdout")).open("xb") as stdout, (output / (label + ".stderr")).open("xb") as stderr:
                process = subprocess.Popen(argv, stdin=subprocess.PIPE if raw is not None else subprocess.DEVNULL,
                                           cwd=output, env=environment, stdout=stdout, stderr=stderr,
                                           start_new_session=True)
                try:
                    process.communicate(input=raw, timeout=600)
                except subprocess.TimeoutExpired:
                    record["timed_out"] = True
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.communicate()
                    raise ValueError(f"{label} exceeded terminal timeout; process group killed") from None
        finally:
            record.update(exit_code=process.returncode if process is not None else None,
                          wall_seconds=time.monotonic() - began)
            for suffix in ("stdout", "stderr"):
                stream_path = output / (label + "." + suffix)
                if stream_path.exists():
                    record[suffix] = pin(stream_path.read_bytes())
        if process.returncode != 0:
            raise ValueError(f"{label} failed; retained original outputs")
        return (output / (label + ".stdout")).read_bytes()

    try:
        smoke_name = "scripts/clean_smoke.py"
        smoke = json.loads(run("smoke", [sys.executable, "-I", "-c", BOOT, str(repo / smoke_name), str(repo)], source[smoke_name]))
        if len(smoke["mcp_tools_discovered_names"]) != 23 or smoke["mcp_tools_exercised"] != 15:
            raise ValueError("smoke inventory differs from planned 15 of 23 tools")
        receipt["smoke"] = smoke
        # Compile the verified historical capture source; configure only its
        # documented wheel-digest/classification globals for this new wheel.
        configured = (
            "import sys,json,types; from pathlib import Path; raw=sys.stdin.buffer.read(); "
            "m=types.ModuleType('_D107_signed_capture'); m.__file__=sys.argv[1]; "
            "sys.modules[m.__name__]=m; exec(compile(raw,m.__file__,'exec'),m.__dict__); "
            "m.D102_WHEEL_SHA=sys.argv[5]; m.CLASSIFICATION='development_D107_signed_transport_capture'; "
            "r=m.probe(Path(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4])); "
            "print(json.dumps(r,sort_keys=True)); sys.exit(0 if r['passed'] else 2)"
        )
        wheel = frozen["wheel"]
        receipt["signed_instrument_configuration"] = {"original_source": pin(source[SIGNED]),
              "global_overrides": {"D102_WHEEL_SHA": wheel["sha256"], "CLASSIFICATION": "development_D107_signed_transport_capture"},
              "no_historical_D103_rerun_or_acceptance_claim": True}
        signed = json.loads(run("signed", [sys.executable, "-I", "-c", configured, str(repo / SIGNED),
                     str(repo), str(output / "signed"), str(repo / wheel["path"]), wheel["sha256"]], source[SIGNED]))
        receipt["signed_summary"] = {key: signed[key] for key in ("passed", "positive_operations", "collected_tests", "pytest_exit_code")}
        value = journal()
        write(output / "lot_journal.json", serialized(value))
        cli_audit = json.loads(run("audit", [setting["cli"], "audit-lot-journal", str(output / "lot_journal.json")]))
        mcp_audit = asyncio.run(audit_mcp(setting["mcp"], output, environment, value))
        if cli_audit != mcp_audit or cli_audit.get("valid") is not True or cli_audit.get("observations_authenticated") is not False:
            raise ValueError("lot journal effects/parity differ")
        receipt["audit_parity"] = {"equal": True, "declarations_only": True, "result": cli_audit}
        workflow = "scripts/probe_signed_full_workflow.py"
        receipt["signed_workflows"] = {}
        for mode in ("signed_report", "signed_observed"):
            mode_root = output / mode
            mode_root.mkdir()
            data = json.loads(run(mode, [sys.executable, "-I", "-c", BOOT, str(repo / workflow), str(repo),
                    "--test-gate-policy", mode, "--output", str(mode_root / "report.json"),
                    "--workspace-root", str(mode_root / "workspace")], source[workflow]))
            receipt["signed_workflows"][mode] = data
        verify(repo, frozen)
        receipt["frozen_sources_unchanged_after"] = True
        receipt["passed"] = True
    except Exception as exc:
        receipt.update(error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
    finally:
        try:
            verify(repo, frozen)
            receipt["frozen_sources_unchanged_after_terminal_attempt"] = True
        except Exception as exc:
            receipt["passed"] = False
            receipt["terminal_preservation_error"] = f"{type(exc).__name__}: {exc}"
        receipt["finished_at_utc"] = dt.datetime.now(dt.UTC).isoformat()
        write(output / "receipt.json", serialized(receipt))
    print(json.dumps({"env": args.env, "passed": receipt["passed"], "error": receipt.get("error"), "output": str(output)}))
    return 0 if receipt["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
