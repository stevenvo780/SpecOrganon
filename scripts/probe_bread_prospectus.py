"""Run installed CLI and real stdio MCP over the D102 development prospectus.

No signatures, approvals, field observations or experimental model calls.
The journal controls are synthetic; the pending workflow stores no baseline
or result and does not accept a phase. Raw transport responses are retained.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
import subprocess
import sys
import sysconfig
from pathlib import Path

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
import specorganon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import build_bread_prospectus as prospectus  # noqa: E402
from specorganon import lot_journal  # noqa: E402


def require(value, reason):
    if not value:
        raise AssertionError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


async def probe(output: Path):
    output = output.absolute()
    require(not output.exists(), "probe destination must be new")
    output.mkdir(parents=True)
    module = Path(specorganon.__file__).resolve()
    require(sys.prefix != sys.base_prefix and module.is_relative_to(Path(sysconfig.get_path("purelib")))
            and not module.is_relative_to(ROOT / "src"), "use a wheel installed outside the repository")
    library = Path(lot_journal.__file__)
    require(library.read_bytes() == (ROOT / "src/specorganon/lot_journal.py").read_bytes(), "installed journal differs")
    scripts = Path(sysconfig.get_path("scripts"))
    cli, mcp = scripts / "organon", scripts / "organon-mcp"
    directory = output / "prospectus"
    prepared = prospectus.prepare(directory)
    case = directory / "case"
    path = str(case)
    manifest = prospectus.base._json(directory / "manifest.json")
    journal = lot_journal.read_journal(directory / "example_journal.json")
    env = {"PATH": os.pathsep.join((str(scripts), "/usr/bin", "/bin")),
           "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONNOUSERSITE": "1",
           "ORGANON_ROOT": str(output), "ORGANON_APPROVERS_FILE": str(directory / "public_keys.json")}
    trace = output / "transports.jsonl"
    def record(data):
        with trace.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(data, ensure_ascii=False, allow_nan=False) + "\n")
    def command(*args, stdin=None):
        result = subprocess.run([str(cli), *args], input=stdin, env=env, cwd=output,
                                text=True, capture_output=True, timeout=60)
        record({"transport": "cli", "args": args, "exit": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr})
        return result
    def call_cli(*args, stdin=None):
        result = command(*args, stdin=stdin)
        require(result.returncode == 0, f"CLI {args[0]} rejected: {result.stderr}")
        return json.loads(result.stdout)
    before = {str(p.relative_to(directory)): sha(p.read_bytes()) for p in directory.rglob("*") if p.is_file()}
    standalone = call_cli("audit-lot-journal", str(directory / "example_journal.json"))
    stdinput = call_cli("audit-lot-journal", "-", stdin=json.dumps(journal))
    require(standalone == stdinput == lot_journal.audit_lot_journal(journal), "CLI file/stdin/API differ")
    require(all(sha((directory / n).read_bytes()) == digest for n, digest in before.items())
            and not (case / "organon.json").exists(), "read-only journal audit wrote case data")
    call_cli("init", path, "--title", prospectus.TITLE, "--domain", "food", "--actor", prospectus.ACTOR,
             "--approval-policy", "signed")
    applied = call_cli("run", path, "--manifest", str(directory / "manifest.json"), "--actor", prospectus.ACTOR)
    require(applied["applied"] == 64 and applied["status"] == "waiting"
            and applied["reason"] == "independent_review_required", "prospectus did not publish pending64")
    ledger = case / "organon.json"
    raw = ledger.read_bytes()
    params = StdioServerParameters(command=str(mcp), args=[], cwd=str(output), env=env)
    controls = {}
    async with Client(params) as client:
        names = sorted(tool.name for tool in (await client.list_tools()).tools)
        require("audit_lot_journal" in names and {"run", "status", "gate", "trace", "next_task"} <= set(names), "MCP tool discovery missing")
        async def call(name, args, rejected=False):
            response = await client.call_tool(name, args)
            record({"transport": "mcp", "tool": name, "args": args,
                    "response": response.model_dump(mode="json")})
            require(bool(response.is_error) == rejected, f"MCP {name} unexpected error status")
            return None if rejected else response.structured_content or json.loads(response.content[0].text)
        require(await call("audit_lot_journal", {"journal": journal}) == standalone, "real MCP journal differs from CLI")
        prefix = copy.deepcopy(journal)
        prefix["events"] = prefix["events"][:1]
        prefix_cli = call_cli("audit-lot-journal", "-", stdin=json.dumps(prefix))
        require(await call("audit_lot_journal", {"journal": prefix}) == prefix_cli
                and not prefix_cli["execution_ready"], "incremental prefix needs fabricated experiment")
        for defect in ("wet_balance", "duplicate_load", "basis", "time", "transfer", "terminal_evaporation"):
            bad = copy.deepcopy(journal)
            if defect == "wet_balance":
                bad["events"][0]["outputs"][0]["mass"]["value"] += 1
            elif defect == "duplicate_load":
                bad["events"][0]["outputs"][0]["load_id"] = bad["events"][0]["inputs"][0]["load_id"]
            elif defect == "basis":
                bad["events"][0]["inputs"][0]["basis"] = "dry"
            elif defect == "time":
                bad["events"][1]["at_utc"] = "2026-09-30T07:00:00Z"
            elif defect == "transfer":
                bad["events"][1]["inputs"][0]["mass"]["value"] -= 1
            else:
                event = copy.deepcopy(bad["events"][1])
                event["id"] = "invalid_evaporation_transfer"
                event["at_utc"] = "2026-09-30T10:00:00Z"
                event["inputs"] = [copy.deepcopy(bad["events"][1]["outputs"][1])]
                event["outputs"] = [copy.deepcopy(event["inputs"][0])]
                event["outputs"][0].update({"load_id": "reused_terminal_water", "kind": "product"})
                bad["events"].append(event)
            rejected = command("audit-lot-journal", "-", stdin=json.dumps(bad))
            require(rejected.returncode != 0 and not rejected.stdout, f"CLI accepted {defect}")
            await call("audit_lot_journal", {"journal": bad}, rejected=True)
            require(ledger.read_bytes() == raw, f"audit rejection {defect} wrote ledger")
            controls[defect] = {"cli_exit": rejected.returncode, "mcp_rejected": True, "ledger_unchanged": True}
        state = call_cli("status", path)
        require(state == await call("status", {"path": path}), "status differs")
        gates = {}
        for phase in state["phases"]:
            gate = call_cli("gate", path, phase)
            require(gate == await call("gate", {"path": path, "phase": phase}), f"{phase} gate differs")
            require(not gate["accepted"], f"{phase} falsely accepted")
            gates[phase] = {"ready": gate["ready"], "accepted": gate["accepted"], "blockers": gate["blockers"]}
        for id in ("r_capture", "r_basis", "r_safety", "r_service"):
            require(call_cli("trace", path, id) == await call("trace", {"path": path, "id": id}), f"trace {id} differs")
        replay = await call("run", {"path": path, "manifest": manifest, "actor": prospectus.ACTOR})
        require(replay["applied"] == 0 and replay["skipped"] == 64 and ledger.read_bytes() == raw,
                "pending64 replay or queries wrote ledger")
        require(all(not state["items"][id]["approved"] for id in ("n_harm", "n_service", "n_permission", "d_pending")),
                "human approval fabricated")
    return {"schema": 1, "study_id": "D102", "python": ".".join(map(str, sys.version_info[:3])),
            "installed_module": str(library), "installed_journal_sha256": sha(library.read_bytes()),
            "probe_sha256": sha(Path(__file__).read_bytes()), "prepared": prepared,
            "journal_report": standalone, "mcp_tools": names, "mcp_tools_count": len(names),
            "invalid_journal_controls": controls, "gates": gates, "cli_applied": 64,
            "mcp_replay_applied": 0, "mcp_replay_skipped": 64, "ledger_sha256": sha(raw),
            "journal_audits_and_queries_read_only": True, "requirement_trace_pairs": 4,
            "source_coverage": {"published_numeric_claims": 17, "archived_survey_rows": 7},
            "normative_approvals": 0, "phase_acceptances": 0, "field_observations": 0,
            "source_authentication": False, "Q": None, "global_acceptance": "0/5",
            "trace_sha256": sha(trace.read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(probe(args.output))
    (args.output / "receipt.json").write_bytes(prospectus.base._render(result))
    print(json.dumps({"state": "passed", "python": result["python"], "tools": result["mcp_tools_count"],
                      "journal_controls": len(result["invalid_journal_controls"]), "global_acceptance": "0/5"}))


if __name__ == "__main__":
    main()
