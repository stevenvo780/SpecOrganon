"""Probe signed local PDF evidence through an installed CLI and real stdio MCP.

Only a temporary case is modified. The published PDFs are copied byte for byte;
the signing key and reviewer are synthetic. The receipt records rerunnable
checks, not publisher custody, reviewer identity, PDF meaning or field impact.
Run with the Python of an installed wheel environment and the repository root.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import subprocess
import sys
import sysconfig
import tempfile
from collections import Counter
from importlib.metadata import version
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

import specorganon


REVIEWER = "agent:synthetic-local-evidence-reviewer"
AUTHOR = "agent:synthetic-local-evidence-author"
REASON = "Synthetic signature over the current published-source framing snapshot"
ARCHIVES = ("source_lca.pdf", "source_survey.pdf")
CHANGED_ARCHIVE = ARCHIVES[0]
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _command(executable: Path, env: dict[str, str], work: Path,
             *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(executable), *args], cwd=work, env=env, text=True,
                          capture_output=True, timeout=60, check=False)


def _cli(executable: Path, env: dict[str, str], work: Path,
         *args: str) -> dict[str, Any]:
    result = _command(executable, env, work, *args)
    _require(result.returncode == 0, f"installed CLI {args[0]} failed: {result.stderr.strip()}")
    value = json.loads(result.stdout)
    _require(isinstance(value, dict), f"installed CLI {args[0]} did not return an object")
    return value


def _mcp_data(result: Any, operation: str) -> dict[str, Any]:
    _require(not result.is_error, f"MCP {operation} failed: {result.content}")
    value = result.structured_content
    if value is None:
        _require(len(result.content) == 1, f"MCP {operation} returned ambiguous content")
        value = json.loads(result.content[0].text)
    _require(isinstance(value, dict), f"MCP {operation} did not return an object")
    return value


def _dependent_ids(steps: list[dict[str, Any]], source_ids: set[str]) -> set[str]:
    reached = set(source_ids)
    while True:
        updated = reached | {step["id"] for step in steps if reached.intersection(step["refs"])}
        if updated == reached:
            return reached - source_ids
        reached = updated


def _frame_summary(status: dict[str, Any]) -> dict[str, Any]:
    frame = status["phases"]["frame"]
    return {key: frame[key] for key in (
        "ready", "reviewed", "accepted", "review_signature_verified", "snapshot",
    )}


async def probe(repo: Path, *, cli: Path | None = None,
                mcp: Path | None = None) -> dict[str, Any]:
    module = Path(specorganon.__file__).resolve(strict=True)
    purelib = Path(sysconfig.get_path("purelib")).resolve(strict=True)
    _require(sys.prefix != sys.base_prefix and module.is_relative_to(purelib)
             and not module.is_relative_to(repo / "src"),
             "specorganon must come from a wheel installed in the current virtual environment")
    scripts = Path(sysconfig.get_path("scripts")).resolve(strict=True)
    cli = cli or scripts / "organon"
    mcp = mcp or scripts / "organon-mcp"
    for executable in (cli, mcp):
        _require(executable.is_absolute() and executable.is_file()
                 and executable.resolve(strict=True).parent == scripts,
                 "CLI/MCP executables must belong to the current installed wheel environment")
    source = repo / "cases" / "bread_norway"
    manifest_raw = (source / "frame_manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    _require(manifest["schema"] == 1 and all(step["op"] in {
        "put", "advance", "review_phase", "review-phase",
    } for step in manifest["steps"]), "unexpected bread framing manifest operations")
    steps = [step for step in manifest["steps"] if step["op"] == "put"]
    _require(len(steps) == 19, "bread framing item count changed; revisit the probe contract")
    originals = {name: (source / name).read_bytes() for name in ARCHIVES}
    _require(all(0 < len(raw) <= MAX_ARCHIVE_BYTES for raw in originals.values()),
             "source PDFs must fit the local archive byte limit")
    evidence = [step for step in steps if step["kind"] == "evidence"]
    _require(len(evidence) == 9 and {step["data"].get("archive") for step in evidence}
             == set(ARCHIVES), "bread framing archive declarations changed")
    for step in evidence:
        _require(_sha256(originals[step["data"]["archive"]]) == step["data"]["source_sha256"],
                 "original PDF bytes no longer match the framing source digest")
    affected = {step["id"] for step in evidence if step["data"]["archive"] == CHANGED_ARCHIVE}
    dependents = _dependent_ids(steps, affected)
    puts_manifest = {"schema": 1, "steps": steps}
    replay_manifest = {"schema": 1, "steps": [*steps, {"op": "advance", "phase": "frame"}]}

    with tempfile.TemporaryDirectory(prefix="organon-local-evidence-") as temporary:
        work = Path(temporary)
        case = work / "case"
        path = str(case)
        registry = work / "trusted-public-keys.json"
        registry.write_text(json.dumps({"schema": 2, "cases": {}}), encoding="utf-8")
        registry.chmod(0o600)
        (work / "home").mkdir()
        (work / "tmp").mkdir()
        env = {
            "PATH": os.pathsep.join((str(scripts), "/usr/bin", "/bin")),
            "HOME": str(work / "home"), "TMPDIR": str(work / "tmp"),
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONNOUSERSITE": "1",
            "ORGANON_ROOT": str(work), "ORGANON_APPROVERS_FILE": str(registry),
        }
        created = _cli(cli, env, work, "init", path, "--title", "Local published-source gate probe",
                       "--domain", "temporary bread framing", "--actor", AUTHOR,
                       "--approval-policy", "signed")
        _require(created["project"]["approval_policy"] == "signed", "case is not signed")
        for name, raw in originals.items():
            (case / name).write_bytes(raw)
        key = Ed25519PrivateKey.generate()
        public = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode("ascii")
        registry.write_text(json.dumps({"schema": 2, "cases": {
            created["project"]["case_id"]: {
                "path": str(case.resolve(strict=True)),
                "project_sha256": created["project_sha256"], "approvers": {},
                "phase_reviewers": {REVIEWER: public},
            },
        }}), encoding="utf-8")
        puts_path = work / "puts.json"
        puts_path.write_bytes(_canonical(puts_manifest))
        replay_path = work / "replay.json"
        replay_path.write_bytes(_canonical(replay_manifest))
        applied = _cli(cli, env, work, "run", path, "--manifest", str(puts_path), "--actor", AUTHOR)
        _require(applied["applied"] == len(steps), "CLI did not build the entire framing")
        ledger = case / "organon.json"
        archive = case / CHANGED_ARCHIVE
        equal_target = work / "same-original-bytes.pdf"
        equal_target.write_bytes(originals[CHANGED_ARCHIVE])
        params = StdioServerParameters(command=str(mcp), cwd=str(work), env=env)
        status_pairs = 0
        checks: dict[str, Any] = {}
        async with Client(params, mode="legacy") as client:
            discovered = {tool.name for tool in (await client.list_tools()).tools}
            required = {"gate", "status", "advance", "run", "phase_review_challenge", "review_phase"}
            _require(required <= discovered, "installed MCP server lacks required gate/review tools")

            async def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                return _mcp_data(await client.call_tool(name, arguments), name)

            async def status_pair() -> dict[str, Any]:
                nonlocal status_pairs
                before = ledger.read_bytes()
                state = _cli(cli, env, work, "status", path)
                _require(state == await call("status", {"path": path}), "CLI/MCP statuses differ")
                gate = _cli(cli, env, work, "gate", path, "frame")
                _require(gate == await call("gate", {"path": path, "phase": "frame"})
                         == state["phases"]["frame"], "CLI/MCP frame gates differ")
                _require(ledger.read_bytes() == before, "status/gate queries wrote to the ledger")
                status_pairs += 1
                return state

            unsigned = await status_pair()
            _require(unsigned["phases"]["frame"]["ready"]
                     and not unsigned["phases"]["frame"]["accepted"], "framing is not ready for review")
            arguments = {"path": path, "phase": "frame", "verdict": "accept",
                         "reason": REASON, "actor": REVIEWER}
            before_challenge = ledger.read_bytes()
            challenge = _cli(cli, env, work, "phase-review-challenge", path, "frame",
                             "--verdict", "accept", "--reason", REASON, "--actor", REVIEWER)
            _require(challenge == await call("phase_review_challenge", arguments),
                     "CLI/MCP signing challenges differ")
            _require(ledger.read_bytes() == before_challenge, "review challenge wrote to the ledger")
            message = base64.b64decode(challenge["message_base64"], validate=True)
            _require(_sha256(message) == challenge["message_sha256"], "signing challenge digest differs")
            signature = base64.b64encode(key.sign(message)).decode("ascii")
            review = await call("review_phase", {**arguments, "signature": signature})
            _require(review["kind"] == "phase_review", "MCP did not record the signed review")
            _cli(cli, env, work, "advance", path, "frame", "--actor", AUTHOR)
            accepted = await status_pair()
            _require(all(accepted["phases"]["frame"][field] for field in (
                "ready", "reviewed", "accepted", "review_signature_verified",
            )), "signed framing was not accepted by both transports")
            before = ledger.read_bytes()

            async def replay_pair() -> dict[str, Any]:
                cli_replay = _cli(cli, env, work, "run", path, "--manifest", str(replay_path),
                                  "--actor", AUTHOR)
                mcp_replay = await call("run", {"path": path, "manifest": replay_manifest, "actor": AUTHOR})
                _require(cli_replay == mcp_replay and cli_replay["applied"] == 0
                         and cli_replay["skipped"] == len(steps) + 1,
                         "restored framing replay wrote or failed to skip the accepted advance")
                _require(ledger.read_bytes() == before, "restored replay wrote to the ledger")
                return {"cli_applied": 0, "mcp_applied": 0, "skipped_each": len(steps) + 1,
                        "ledger_byte_identical": True}

            for mode in ("mutate", "remove", "symlink"):
                try:
                    if mode == "mutate":
                        archive.write_bytes(originals[CHANGED_ARCHIVE] + b"\nlocal probe mutation\n")
                    else:
                        archive.unlink()
                        if mode == "symlink":
                            archive.symlink_to(equal_target)
                    state = await status_pair()
                    frame = state["phases"]["frame"]
                    _require(not frame["ready"] and not frame["accepted"]
                             and not frame["reviewed"] and frame["snapshot"]
                             != accepted["phases"]["frame"]["snapshot"],
                             f"{mode} did not reopen the signed framing")
                    issue = ("local archive bytes differ from source_sha256" if mode == "mutate"
                             else "local archive is missing or unsafe to read")
                    _require(all(issue in state["items"][item_id]["issues"] for item_id in affected),
                             f"{mode} did not flag every evidence citing the changed PDF")
                    _require(all(any(entry.startswith("depends on invalid local archive evidence ")
                                     for entry in state["items"][item_id]["issues"])
                                 for item_id in dependents), f"{mode} did not flag recursive dependents")
                    _require(not state["items"]["e_survey_size"]["issues"],
                             f"{mode} incorrectly invalidated the other PDF")
                    rejected = _command(cli, env, work, "advance", path, "frame", "--actor", AUTHOR)
                    _require(rejected.returncode != 0 and not rejected.stdout
                             and "phase cannot advance" in rejected.stderr,
                             f"CLI accepted an advance after {mode}")
                    mcp_rejected = await client.call_tool("advance", {
                        "path": path, "phase": "frame", "actor": AUTHOR,
                    })
                    _require(mcp_rejected.is_error, f"MCP accepted an advance after {mode}")
                    cli_run = _cli(cli, env, work, "run", path, "--manifest", str(replay_path), "--actor", AUTHOR)
                    mcp_run = await call("run", {"path": path, "manifest": replay_manifest, "actor": AUTHOR})
                    _require(cli_run == mcp_run and cli_run["status"] == "waiting"
                             and cli_run["reason"] == "invalid_or_stale_artifact"
                             and cli_run["applied"] == 0 and cli_run["skipped"] == len(steps),
                             f"CLI/MCP manifest advanced or wrote after {mode}")
                    _require(ledger.read_bytes() == before, f"{mode} observations or rejected actions wrote to ledger")
                    checks[mode] = {
                        "frame": _frame_summary(state), "affected_evidence_ids": sorted(affected),
                        "dependent_issue_ids": sorted(dependents), "evidence_issue": issue,
                        "other_pdf_evidence_valid": True, "cli_advance_exit_code": rejected.returncode,
                        "mcp_advance_is_error": True,
                        "run": {"status": cli_run["status"], "reason": cli_run["reason"],
                                "cli_applied": 0, "mcp_applied": 0, "skipped_each": len(steps)},
                        "ledger_byte_identical": True,
                    }
                    if mode == "symlink":
                        checks[mode]["symlink_target_has_original_digest"] = (
                            _sha256(equal_target.read_bytes()) == _sha256(originals[CHANGED_ARCHIVE]))
                finally:
                    if archive.exists() or archive.is_symlink():
                        archive.unlink()
                    archive.write_bytes(originals[CHANGED_ARCHIVE])
                restored = await status_pair()
                _require(restored == accepted, f"exact-byte restoration did not recover status after {mode}")
                checks[mode]["restoration_recovered_status"] = True
                checks[mode]["replay"] = await replay_pair()

            final = await status_pair()
            _require(final == accepted and ledger.read_bytes() == before, "final framing differs from accepted checkpoint")
            events = json.loads(before)["events"]
            _require(all((source / name).read_bytes() == raw for name, raw in originals.items()),
                     "original case source PDF bytes changed during the probe")
            return {
                "schema": 1, "classification": "signed_local_pdf_evidence_gate_installed_cli_stdio_mcp",
                "receipt_kind": "rerunnable_summary_not_detached_attestation",
                "python_version": ".".join(map(str, sys.version_info[:3])),
                "package_version": version("specorganon"),
                "probe_sha256": _sha256(Path(__file__).read_bytes()),
                "manifest_sha256": _sha256(manifest_raw),
                "executed_puts_manifest_sha256": _sha256(_canonical(puts_manifest)),
                "replay_manifest_sha256": _sha256(_canonical(replay_manifest)),
                "stripped_operation_counts": dict(sorted(Counter(
                    step["op"] for step in manifest["steps"] if step["op"] != "put").items())),
                "original_sources": [{"archive": name, "original_sha256": _sha256(raw),
                                      "source_sha256": next(step["data"]["source_sha256"]
                                                            for step in evidence if step["data"]["archive"] == name),
                                      "size_bytes": len(raw)} for name, raw in originals.items()],
                "transport": {"stdio_mcp_real": True, "wheel_module_under_site_packages": True,
                              "cli_mcp_status_and_gate_equal": True, "status_gate_pairs": status_pairs,
                              "required_tools_discovered": sorted(required)},
                "child_environment_keys": sorted(env),
                "accepted": {"revision": accepted["revision"], "frame": _frame_summary(accepted)},
                "controls": checks,
                "final": {"revision": final["revision"], "item_count": len(final["items"]),
                          "event_counts": dict(sorted(Counter(event["kind"] for event in events).items())),
                          "frame": _frame_summary(final), "ledger_sha256": _sha256(before),
                          "ledger_byte_identical": True, "original_case_pdf_bytes_unchanged": True},
                "limits": {
                    "changed_archive": CHANGED_ARCHIVE, "changed_archives": 1,
                    "copied_archives": len(originals), "accepted_phases_tested": ["frame"],
                    "local_archive_max_bytes": MAX_ARCHIVE_BYTES,
                    "archive_size_boundary_tested": False, "concurrent_file_replacement_tested": False,
                    "local_byte_integrity_tested": True, "recursive_dependency_invalidation_tested": True,
                    "synthetic_reviewer_signature_tested": True, "publisher_custody_authenticated": False,
                    "human_identity_authenticated": False, "independent_human_judgment_tested": False,
                    "pdf_claims_semantically_verified": False, "field_impact_tested": False,
                    "private_keys_written_to_disk": False, "paid_model_calls": 0,
                },
            }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", type=Path)
    parser.add_argument("--cli", type=Path, help="Installed CLI executable in this Python environment")
    parser.add_argument("--mcp", type=Path, help="Installed MCP executable in this Python environment")
    parser.add_argument("--output", type=Path, help="Optional sanitized JSON receipt")
    args = parser.parse_args()
    receipt = asyncio.run(probe(args.repo_root.resolve(strict=True), cli=args.cli, mcp=args.mcp))
    serialized = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        args.output.write_text(serialized, encoding="utf-8")
    sys.stdout.write(serialized)


if __name__ == "__main__":
    main()
