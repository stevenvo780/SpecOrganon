"""Replay the March 2024 seed through the installed CLI and a real stdio MCP client.

The only writable case is in a temporary directory. This proves workflow
transport, checkpointing, and traceability, not empirical impact or criterion 5.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters


ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "cases/citibike_march2024/seed.json"
PUBLISHED_RESULT = ROOT / "experiments/development/citibike_sample_status_2026-09-27.json"
ANALYSIS_SCRIPT = ROOT / "cases/citibike/analyze_sample_status.py"
REAL_LEDGERS = (
    ROOT / "cases/citibike_march2024/organon.json",
    ROOT / "cases/citibike/organon.json",
)
CLI = Path(sys.executable).with_name("organon")
MCP = Path(sys.executable).with_name("organon-mcp")
REVIEWER = "agent:march_workflow_reviewer"
EVIDENCE_IDS = ("e_eligible", "e_rental", "e_return", "e_excluded", "e_gaps")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def build_manifest(seed: dict[str, Any]) -> dict[str, Any]:
    """Use only the seed's ordered items, pinned to absent version and ref v1."""
    steps = [
        {
            "op": "put",
            "id": item["id"],
            "kind": item["kind"],
            "text": item["text"],
            "refs": item.get("refs", []),
            "data": item.get("data", {}),
            "expected_version": 0,
            "expected_deps": {ref: 1 for ref in item.get("refs", [])},
        }
        for item in seed["items"]
    ]
    if len(steps) != 22 or len({step["id"] for step in steps}) != 22:
        raise ValueError("March seed must contain 22 distinct items")
    if {ref for step in steps for ref in step["refs"]} - {step["id"] for step in steps}:
        raise ValueError("March seed references an item outside the manifest")
    return {
        "schema": 1,
        "name": "citibike_march2024_frame_replay",
        "steps": [*steps, {"op": "advance", "phase": "frame"}],
    }


def _cli(env: dict[str, str], *args: str) -> dict[str, Any]:
    result = subprocess.run(
        [str(CLI), *args], cwd=ROOT, env=env, text=True,
        capture_output=True, check=True, timeout=60,
    )
    return json.loads(result.stdout)


def _mcp_data(result: Any) -> dict[str, Any]:
    if result.is_error:
        raise AssertionError(f"MCP tool failed: {result.content}")
    return result.structured_content or json.loads(result.content[0].text)


async def _resume_mcp(
    env: dict[str, str], case: Path, manifest: dict[str, Any], actor: str
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    params = StdioServerParameters(command=str(MCP), cwd=str(ROOT), env=env)
    async with Client(params, mode="legacy") as client:
        discovered = sorted(tool.name for tool in (await client.list_tools()).tools)
        if not {"run", "status"} <= set(discovered):
            raise AssertionError("MCP server did not expose run and status")
        resumed = _mcp_data(await client.call_tool(
            "run", {"path": str(case), "manifest": manifest, "actor": actor}
        ))
        status = _mcp_data(await client.call_tool("status", {"path": str(case)}))
    return discovered, resumed, status


def _source_checks(seed: dict[str, Any], published: dict[str, Any]) -> None:
    """Check available local bytes and every recorded numeric locator."""
    result_hash = _sha256(PUBLISHED_RESULT.read_bytes())
    script_hash = _sha256(ANALYSIS_SCRIPT.read_bytes())
    evidence = {item["id"]: item for item in seed["items"] if item["id"] in EVIDENCE_IDS}
    if set(evidence) != set(EVIDENCE_IDS):
        raise AssertionError("March seed is missing a published-result evidence item")
    for item in evidence.values():
        data = item["data"]
        if data["sha256_source"] != result_hash or data["sha256_script"] != script_hash:
            raise AssertionError(f"source digest differs for {item['id']}")
        if ROOT / data["source"] != PUBLISHED_RESULT or ROOT / data["script"] != ANALYSIS_SCRIPT:
            raise AssertionError(f"source path differs for {item['id']}")
        value: Any = published
        for component in data["locator"].split("."):
            value = value[component]
        if type(value) is not int or data["value"] != value:
            raise AssertionError(f"published numeric locator differs for {item['id']}")
    archive = next(item for item in seed["items"] if item["id"] == "e_archive")
    if archive["data"]["sha256_source"] != published["input_sha256"]:
        raise AssertionError("Parquet digest declaration differs from published analysis")
    if published["criterion_5"] != "not_assessed":
        raise AssertionError("published analysis changed its criterion 5 limitation")


def run_probe() -> dict[str, Any]:
    if not CLI.is_file() or not MCP.is_file():
        raise FileNotFoundError("installed organon and organon-mcp executables are required")
    seed_bytes = SEED.read_bytes()
    seed = json.loads(seed_bytes)
    result_bytes = PUBLISHED_RESULT.read_bytes()
    published = json.loads(result_bytes)
    _source_checks(seed, published)
    manifest = build_manifest(seed)
    manifest_bytes = _json_bytes(manifest)
    ledger_before = {path: _sha256(path.read_bytes()) for path in REAL_LEDGERS}

    with tempfile.TemporaryDirectory(prefix="organon-march-workflow-") as temporary:
        work = Path(temporary)
        case = work / "case"
        manifest_path = work / "manifest.json"
        manifest_path.write_bytes(manifest_bytes)
        env = os.environ.copy()
        for key in ("ORGANON_APPROVERS_FILE", "ORGANON_ALLOW_FIXTURES", "ORGANON_LEDGER_ANCHORS_FILE"):
            env.pop(key, None)
        env["ORGANON_ROOT"] = str(work)

        initialized = _cli(
            env, "init", str(case), "--title", seed["title"], "--domain", seed["domain"],
            "--actor", seed["actor"], "--approval-policy", "signed",
        )
        if initialized["project"]["approval_policy"] != "signed":
            raise AssertionError("temporary case did not use signed approval policy")
        first = _cli(
            env, "run", str(case), "--manifest", str(manifest_path), "--actor", seed["actor"]
        )
        if (first["status"], first["cursor"], first["applied"], first["skipped"], first["reason"]) != (
            "waiting", 22, 22, 0, "independent_review_required"
        ):
            raise AssertionError(f"unexpected first workflow checkpoint: {first}")
        before_review = _cli(env, "status", str(case))
        if before_review["revision"] != 22 or not before_review["phases"]["frame"]["ready"]:
            raise AssertionError("first checkpoint did not leave 22 items ready for frame review")

        reviewed = _cli(
            env, "review-phase", str(case), "frame", "--verdict", "accept",
            "--reason", "Automated actor-separation transport probe for historical sample frame; no human or field assessment",
            "--actor", REVIEWER,
        )
        if reviewed["actor"] == seed["actor"] or reviewed["payload"]["independent"] is not True:
            raise AssertionError("frame review was not independent of its author")

        discovered, resumed, mcp_status = asyncio.run(
            _resume_mcp(env, case, manifest, seed["actor"])
        )
        if (resumed["status"], resumed["cursor"], resumed["applied"], resumed["skipped"]) != (
            "waiting", 23, 1, 22
        ):
            raise AssertionError(f"MCP did not resume the frame advance: {resumed}")
        if resumed["reason"] != "human_approval_required":
            raise AssertionError("workflow did not stop at the unapproved norm")

        ledger_after_mcp = (case / "organon.json").read_bytes()
        retry = _cli(
            env, "run", str(case), "--manifest", str(manifest_path), "--actor", seed["actor"]
        )
        if (retry["status"], retry["cursor"], retry["applied"], retry["skipped"]) != (
            "waiting", 23, 0, 23
        ) or (case / "organon.json").read_bytes() != ledger_after_mcp:
            raise AssertionError("CLI replay changed a completed checkpoint")

        cli_status = _cli(env, "status", str(case))
        if cli_status != mcp_status or cli_status["revision"] != 24:
            raise AssertionError("CLI and MCP final status diverged")
        events = json.loads(ledger_after_mcp)["events"]
        event_counts = dict(sorted(Counter(event["kind"] for event in events).items()))
        if event_counts != {"item_put": 22, "phase_advance": 1, "phase_review": 1}:
            raise AssertionError(f"unexpected ledger event kinds: {event_counts}")
        if [event["payload"]["id"] for event in events[:22]] != [
            item["id"] for item in seed["items"]
        ]:
            raise AssertionError("ledger item order differs from the seed")
        review_event, advance_event = events[-2:]
        if (
            review_event["seq"] != reviewed["seq"]
            or advance_event["payload"]["review_seq"] != review_event["seq"]
            or review_event["actor"] == seed["actor"]
        ):
            raise AssertionError("advance did not bind to the independent review")

        traced: dict[str, list[str]] = {}
        for item_id in EVIDENCE_IDS:
            trace = _cli(env, "trace", str(case), item_id)
            ancestors = sorted(item["id"] for item in trace["ancestors"])
            if not {"p_access", "pr_reanalysis"} <= set(ancestors):
                raise AssertionError(f"published evidence {item_id} lost problem or protocol ancestry")
            traced[item_id] = ancestors
        critique = _cli(env, "gate", str(case), "critique")
        if (
            critique["ready"] or critique["accepted"]
            or critique["blockers"] != ["n_scope requires a verified human approval"]
            or cli_status["items"]["n_scope"]["approved"]
            or any(event["kind"] == "approval" for event in events)
        ):
            raise AssertionError("unapproved norm did not block critique")
        if not cli_status["phases"]["frame"]["accepted"]:
            raise AssertionError("frame did not advance")

        receipt = {
            "schema": 1,
            "case": "citibike_march2024",
            "transport": {"first": "installed_cli", "resume": "stdio_mcp", "retry": "installed_cli"},
            "sha256": {
                "seed": _sha256(seed_bytes),
                "manifest": _sha256(manifest_bytes),
                "published_result": _sha256(result_bytes),
                "analysis_script": _sha256(ANALYSIS_SCRIPT.read_bytes()),
                "source_parquet_declared": published["input_sha256"],
                "temporary_ledger_after_resume": _sha256(ledger_after_mcp),
            },
            "steps": {"put": 22, "advance": 1, "total": len(manifest["steps"])},
            "first": {key: first[key] for key in ("status", "cursor", "applied", "skipped", "reason")},
            "review": {
                "seq": review_event["seq"], "actor": review_event["actor"],
                "independent": review_event["payload"]["independent"],
                "scope": "automated_actor_separation_only",
            },
            "mcp": {
                "discovered_tools": discovered,
                "resume": {key: resumed[key] for key in ("status", "cursor", "applied", "skipped", "reason")},
                "status_equal_to_cli": True,
            },
            "retry": {key: retry[key] for key in ("status", "cursor", "applied", "skipped", "reason")},
            "final": {
                "revision": cli_status["revision"],
                "event_kinds": event_counts,
                "frame_accepted": True,
                "critique": {key: critique[key] for key in ("ready", "accepted", "blockers")},
                "norm_approved": cli_status["items"]["n_scope"]["approved"],
                "evidence_ancestors": traced,
            },
            "criterion_5": published["criterion_5"],
            "real_ledgers_unchanged": all(
                _sha256(path.read_bytes()) == digest for path, digest in ledger_before.items()
            ),
        }
        if not receipt["real_ledgers_unchanged"]:
            raise AssertionError("a committed case ledger changed during the probe")
        return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write the receipt as JSON in addition to stdout")
    args = parser.parse_args()
    result = run_probe()
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
