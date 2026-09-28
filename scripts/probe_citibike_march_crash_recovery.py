"""Kill an installed CLI after a durable March seed event, then resume by MCP.

The crash is injected in a temporary sitecustomize module. All ledger writes,
CLI/MCP calls and source checks use the real installed toolkit. The exposed
March development case is not a reserved case or a field intervention.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import signal
import subprocess
import sys
import sysconfig
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

import specorganon
import verify_citibike_march_workflow as baseline


CRASH_SEQ = 16
CRASH_ITEM = "e_rental"
ZERO_HASH = "0" * 64
REVIEWER = "agent:march_crash_probe_reviewer"
HOOK = """\
import os
import signal
from pathlib import Path
from specorganon import engine

_original_append = engine.append_event
_target = Path(os.environ["ORGANON_TEST_CRASH_CASE"]).resolve(strict=True)
_expected_id = os.environ["ORGANON_TEST_CRASH_ITEM"]

def _crash_after_durable_event(directory, kind, payload, actor, *, expected_seq=None):
    event = _original_append(directory, kind, payload, actor, expected_seq=expected_seq)
    if (Path(directory).resolve(strict=True) == _target and kind == "item_put"
            and event["seq"] == 16 and payload["id"] == _expected_id):
        os.kill(os.getpid(), signal.SIGKILL)
    return event

engine.append_event = _crash_after_durable_event
"""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _ledger(case: Path) -> tuple[dict[str, Any], bytes]:
    raw = (case / "organon.json").read_bytes()
    data = json.loads(raw)
    previous = ZERO_HASH
    for seq, event in enumerate(data["events"], start=1):
        expected = _sha256(baseline._json_bytes({key: value for key, value in event.items()
                                                 if key != "hash"}))
        _require(event["seq"] == seq and event["prev_hash"] == previous
                 and event["hash"] == expected, f"invalid ledger event {seq}")
        previous = expected
    return data, raw


def _cli(env: dict[str, str], work: Path, *args: str) -> dict[str, Any]:
    result = subprocess.run(
        [str(baseline.CLI), *args], cwd=work, env=env, text=True,
        capture_output=True, timeout=90, check=False,
    )
    _require(result.returncode == 0, f"installed CLI {args[0]} failed: {result.stderr.strip()}")
    value = json.loads(result.stdout)
    _require(isinstance(value, dict), f"installed CLI {args[0]} returned no object")
    return value


def _mcp_value(result: Any, operation: str) -> dict[str, Any]:
    _require(not result.is_error, f"MCP {operation} failed: {result.content}")
    value = result.structured_content or json.loads(result.content[0].text)
    _require(isinstance(value, dict), f"MCP {operation} returned no object")
    return value


async def _resume_mcp(env: dict[str, str], work: Path, case: Path,
                      manifest: dict[str, Any], actor: str) -> tuple[list[str], dict, dict]:
    params = StdioServerParameters(command=str(baseline.MCP), cwd=str(work), env=env)
    async with Client(params, mode="legacy") as client:
        discovered = sorted(tool.name for tool in (await client.list_tools()).tools)
        _require({"run", "status"} <= set(discovered), "installed MCP lacks run/status")
        resumed = _mcp_value(await client.call_tool("run", {
            "path": str(case), "manifest": manifest, "actor": actor,
        }), "run")
        status = _mcp_value(await client.call_tool("status", {"path": str(case)}), "status")
    return discovered, resumed, status


def run_probe() -> dict[str, Any]:
    repo = baseline.ROOT
    installed = Path(specorganon.__file__).resolve()
    site_packages = Path(sysconfig.get_path("purelib")).resolve()
    _require(sys.prefix != sys.base_prefix and installed.is_relative_to(site_packages)
             and not installed.is_relative_to(repo / "src"),
             "the toolkit must come from a wheel installed outside the repository")
    _require(baseline.CLI.is_file() and baseline.MCP.is_file(),
             "installed CLI and MCP executables are required")
    seed_raw = baseline.SEED.read_bytes()
    seed = json.loads(seed_raw)
    published_raw = baseline.PUBLISHED_RESULT.read_bytes()
    published = json.loads(published_raw)
    baseline._source_checks(seed, published)
    _require(seed["items"][CRASH_SEQ - 1]["id"] == CRASH_ITEM,
             "the pinned crash item changed in the March seed")
    manifest = baseline.build_manifest(seed)
    manifest_raw = baseline._json_bytes(manifest)
    historical = {path: _sha256(path.read_bytes()) for path in baseline.REAL_LEDGERS}

    with tempfile.TemporaryDirectory(prefix="organon-march-crash-") as temporary:
        work = Path(temporary)
        case = work / "case"
        home = work / "home"
        scratch = work / "tmp"
        home.mkdir()
        scratch.mkdir()
        manifest_path = work / "manifest.json"
        manifest_path.write_bytes(manifest_raw)
        env = {
            "PATH": os.pathsep.join((str(Path(sys.executable).parent), "/usr/bin", "/bin")),
            "HOME": str(home), "TMPDIR": str(scratch), "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8", "PYTHONNOUSERSITE": "1", "ORGANON_ROOT": str(work),
        }
        created = _cli(env, work, "init", str(case), "--title", seed["title"],
                       "--domain", seed["domain"], "--actor", seed["actor"],
                       "--approval-policy", "signed")
        _require(created["project"]["approval_policy"] == "signed"
                 and _ledger(case)[0]["events"] == [],
                 "temporary signed case was not initially empty")
        reviewer_key = Ed25519PrivateKey.generate()
        public_key = reviewer_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
        )
        registry = work / "synthetic-reviewer-registry.json"
        registry.write_text(json.dumps({"schema": 2, "cases": {
            created["project"]["case_id"]: {
                "path": str(case.resolve(strict=True)),
                "project_sha256": created["project_sha256"],
                "approvers": {},
                "phase_reviewers": {REVIEWER: base64.b64encode(public_key).decode("ascii")},
            },
        }}), encoding="utf-8")
        registry.chmod(0o600)
        env["ORGANON_APPROVERS_FILE"] = str(registry)

        hook_dir = work / "crash-hook"
        hook_dir.mkdir(mode=0o700)
        hook_file = hook_dir / "sitecustomize.py"
        hook_file.write_text(HOOK, encoding="utf-8")
        hook_file.chmod(0o600)
        crash_env = {**env, "PYTHONPATH": str(hook_dir),
                     "ORGANON_TEST_CRASH_CASE": str(case),
                     "ORGANON_TEST_CRASH_ITEM": CRASH_ITEM}
        _require("PYTHONPATH" not in env and "ORGANON_TEST_CRASH_CASE" not in env,
                 "the uninstrumented resume environment is contaminated")
        killed = subprocess.run(
            [str(baseline.CLI), "run", str(case), "--manifest", str(manifest_path),
             "--actor", seed["actor"]],
            cwd=work, env=crash_env, text=True, capture_output=True,
            timeout=90, check=False,
        )
        _require(killed.returncode == -signal.SIGKILL and not killed.stdout,
                 "installed CLI did not die at the durable checkpoint")
        prefix, prefix_raw = _ledger(case)
        _require(len(prefix["events"]) == CRASH_SEQ
                 and [event["payload"]["id"] for event in prefix["events"]] == [
                     item["id"] for item in seed["items"][:CRASH_SEQ]
                 ] and all(event["kind"] == "item_put" for event in prefix["events"]),
                 "killed CLI did not leave the exact March seed prefix")
        _require(_cli(env, work, "status", str(case))["revision"] == CRASH_SEQ,
                 "a fresh installed CLI could not read the killed ledger")
        _require(not list(case.glob(".organon-*")),
                 "the crash left an uncommitted ledger temporary file")

        discovered, resumed, mcp_status = asyncio.run(
            _resume_mcp(env, work, case, manifest, seed["actor"])
        )
        _require((resumed["status"], resumed["cursor"], resumed["applied"],
                  resumed["skipped"], resumed["reason"]) == (
                      "waiting", 22, 22 - CRASH_SEQ, CRASH_SEQ, "independent_review_required"
                  ) and mcp_status["revision"] == 22
                 and mcp_status["phases"]["frame"]["ready"],
                 "MCP did not resume the exact durable prefix")
        after_mcp, after_mcp_raw = _ledger(case)
        _require(after_mcp["events"][:CRASH_SEQ] == prefix["events"],
                 "MCP rewrote the preserved seed prefix")
        pre_review_retry = _cli(env, work, "run", str(case), "--manifest",
                                str(manifest_path), "--actor", seed["actor"])
        _require((pre_review_retry["status"], pre_review_retry["cursor"],
                  pre_review_retry["applied"], pre_review_retry["skipped"],
                  pre_review_retry["reason"]) == (
                      "waiting", 22, 0, 22, "independent_review_required"
                  ) and (case / "organon.json").read_bytes() == after_mcp_raw,
                 "CLI retry before review duplicated an event")

        reason = "Synthetic review of March crash recovery; no human or field assessment"
        challenge = _cli(env, work, "phase-review-challenge", str(case), "frame",
                         "--verdict", "accept", "--reason", reason, "--actor", REVIEWER)
        signed = base64.b64encode(reviewer_key.sign(
            base64.b64decode(challenge["message_base64"], validate=True)
        )).decode("ascii")
        reviewed = _cli(env, work, "review-phase", str(case), "frame",
                        "--verdict", "accept", "--reason", reason,
                        "--actor", REVIEWER, "--signature", signed)
        _require(reviewed["kind"] == "phase_review" and reviewed["seq"] == 23
                 and reviewed["actor"] != seed["actor"],
                 "synthetic signed frame review did not append")
        _, advanced, final_mcp_status = asyncio.run(
            _resume_mcp(env, work, case, manifest, seed["actor"])
        )
        _require((advanced["status"], advanced["cursor"], advanced["applied"],
                  advanced["skipped"], advanced["reason"]) == (
                      "waiting", 23, 1, 22, "human_approval_required"
                  ), "MCP did not advance only the reviewed frame")
        final_ledger, final_raw = _ledger(case)
        retry = _cli(env, work, "run", str(case), "--manifest", str(manifest_path),
                     "--actor", seed["actor"])
        cli_status = _cli(env, work, "status", str(case))
        _require((retry["status"], retry["cursor"], retry["applied"],
                  retry["skipped"], retry["reason"]) == (
                      "waiting", 23, 0, 23, "human_approval_required"
                  ) and (case / "organon.json").read_bytes() == final_raw
                 and cli_status == final_mcp_status,
                 "CLI retry changed the MCP checkpoint or final status")

        counts = dict(sorted(Counter(event["kind"] for event in final_ledger["events"]).items()))
        _require(counts == {"item_put": 22, "phase_review": 1, "phase_advance": 1}
                 and len(final_ledger["events"]) == 24
                 and final_ledger["events"][:CRASH_SEQ] == prefix["events"]
                 and final_ledger["events"][22]["seq"] == reviewed["seq"]
                 and final_ledger["events"][23]["payload"]["review_seq"] == reviewed["seq"],
                 "final ledger lost order, uniqueness or review linkage")
        traced: dict[str, list[str]] = {}
        for item_id in baseline.EVIDENCE_IDS:
            trace = _cli(env, work, "trace", str(case), item_id)
            ancestors = sorted(item["id"] for item in trace["ancestors"])
            _require({"p_access", "pr_reanalysis"} <= set(ancestors),
                     f"evidence {item_id} lost its problem/protocol ancestry")
            traced[item_id] = ancestors
        critique = _cli(env, work, "gate", str(case), "critique")
        _require(not critique["ready"] and not critique["accepted"]
                 and critique["blockers"] == ["n_scope requires a verified human approval"]
                 and not cli_status["items"]["n_scope"]["approved"]
                 and not any(event["kind"] == "approval" for event in final_ledger["events"]),
                 "crash recovery bypassed the unapproved norm")
        _require(cli_status["phases"]["frame"]["accepted"]
                 and cli_status["phases"]["frame"]["review_signature_verified"],
                 "frame review did not remain signed and accepted")
        _require(all(_sha256(path.read_bytes()) == digest for path, digest in historical.items()),
                 "a committed case ledger changed during the crash probe")
        return {
            "schema": 1,
            "classification": "development_citibike_march_durable_crash_recovery",
            "receipt_kind": "rerunnable_summary_not_detached_attestation",
            "case": "citibike_march2024_exposed_development",
            "sha256": {
                "seed": _sha256(seed_raw), "manifest": _sha256(manifest_raw),
                "published_result": _sha256(published_raw),
                "analysis_script": _sha256(baseline.ANALYSIS_SCRIPT.read_bytes()),
                "crash_hook": _sha256(HOOK.encode("utf-8")),
                "interrupted_prefix": _sha256(prefix_raw),
                "after_mcp_resume": _sha256(after_mcp_raw),
                "final_ledger": _sha256(final_raw),
            },
            "transport": {"crashed": "installed_cli_with_temporary_sitecustomize_hook",
                          "resume": "real_stdio_mcp", "retry": "installed_cli",
                          "discovered_tools": discovered, "status_equal": True,
                          "wheel_module_under_site_packages": True},
            "crash": {"signal": "SIGKILL", "returncode": killed.returncode,
                      "after_durable_item_put_seq": CRASH_SEQ, "item_id": CRASH_ITEM,
                      "prefix_events": len(prefix["events"]),
                      "prefix_head_hash": prefix["events"][-1]["hash"]},
            "mcp_resume": {key: resumed[key] for key in
                           ("status", "cursor", "applied", "skipped", "reason")},
            "cli_pre_review_retry": {key: pre_review_retry[key] for key in
                                     ("status", "cursor", "applied", "skipped", "reason")},
            "mcp_advance": {key: advanced[key] for key in
                            ("status", "cursor", "applied", "skipped", "reason")},
            "cli_final_retry": {key: retry[key] for key in
                                ("status", "cursor", "applied", "skipped", "reason")},
            "final": {
                "revision": cli_status["revision"], "event_counts": counts,
                "frame_accepted": True,
                "critique": {key: critique[key] for key in ("ready", "accepted", "blockers")},
                "norm_approved": False, "evidence_ancestors": traced,
            },
            "source_parquet_sha256_declared": published["input_sha256"],
            "real_ledgers_unchanged": True,
            "criterion_5": "not_assessed",
            "scope": {"historical_sample_exposed": True,
                      "crash_injection_in_temporary_process_only": True,
                      "hook_removed_from_mcp_and_retry_environment": True,
                      "power_loss_or_storage_fault_tested": False,
                      "source_parquet_reopened_in_this_probe": False,
                      "independent_human_review": False,
                      "reserved_case_or_field_intervention": False},
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_probe()
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)


if __name__ == "__main__":
    main()
