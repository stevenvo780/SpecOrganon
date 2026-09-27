"""Exercise all nine signed phases with an installed wheel's CLI and stdio MCP.

Run with the Python interpreter of an environment containing the installed
wheel, passing the repository root. Private keys exist only in this process;
all case content and actor names are synthetic. This authenticates local
signatures and transport behavior, not a human reviewer or field impact.
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
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

import specorganon


PHASES = (
    "frame", "critique", "study", "observe", "explain", "compare",
    "specify", "build", "validate",
)
APPROVALS = {"n1", "d1"}
RUNNER = "agent:synthetic-runner"
APPROVER = "human:synthetic-approver-key"
REVIEWER = "human:synthetic-reviewer-key"
ZERO_HASH = "0" * 64


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _public(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def _registry(
    file: Path, case: Path, project: dict[str, Any],
    project_sha256: str, approver_public: str, reviewer_public: str | None,
) -> None:
    entry = {
        "path": str(case.resolve(strict=True)),
        "project_sha256": project_sha256,
        "approvers": {APPROVER: approver_public},
        "phase_reviewers": {REVIEWER: reviewer_public} if reviewer_public else {},
    }
    file.write_text(json.dumps({"schema": 2, "cases": {project["case_id"]: entry}}), encoding="utf-8")
    file.chmod(0o600)


def _cli(executable: Path, env: dict[str, str], work: Path, *args: str) -> dict[str, Any]:
    result = subprocess.run(
        [str(executable), *args], cwd=work, env=env, text=True,
        capture_output=True, timeout=90, check=False,
    )
    _require(result.returncode == 0, f"installed CLI {args[0]} failed: {result.stderr.strip()}")
    value = json.loads(result.stdout)
    _require(isinstance(value, dict), f"installed CLI {args[0]} did not return an object")
    return value


def _cli_rejected(executable: Path, env: dict[str, str], work: Path, *args: str) -> None:
    result = subprocess.run(
        [str(executable), *args], cwd=work, env=env, text=True,
        capture_output=True, timeout=90, check=False,
    )
    _require(result.returncode != 0 and not result.stdout and "signature" in result.stderr.lower(),
             f"installed CLI {args[0]} accepted a missing signature")


def _mcp_data(result: Any, operation: str) -> dict[str, Any]:
    _require(not result.is_error, f"MCP {operation} failed: {result.content}")
    value = result.structured_content
    if value is None:
        _require(len(result.content) == 1, f"MCP {operation} returned ambiguous content")
        value = json.loads(result.content[0].text)
    _require(isinstance(value, dict), f"MCP {operation} did not return an object")
    return value


def _ledger(case: Path) -> tuple[dict[str, Any], bytes]:
    raw = (case / "organon.json").read_bytes()
    data = json.loads(raw)
    _require(isinstance(data, dict), "case ledger is not a JSON object")
    previous = ZERO_HASH
    for number, event in enumerate(data["events"], start=1):
        _require(event["seq"] == number and event["prev_hash"] == previous,
                 f"broken event sequence {number}")
        expected = _sha256(_canonical({key: value for key, value in event.items() if key != "hash"}))
        _require(event["hash"] == expected, f"event {number} digest mismatch")
        previous = expected
    return data, raw


def _message(challenge: dict[str, Any], expected: dict[str, Any]) -> bytes:
    _require(challenge["algorithm"] == "Ed25519" and challenge["encoding"] == "base64",
             "challenge did not declare Ed25519/base64")
    raw = base64.b64decode(challenge["message_base64"], validate=True)
    _require(_sha256(raw) == challenge["message_sha256"], "challenge message hash differs")
    body = json.loads(raw)
    for key, value in expected.items():
        _require(body.get(key) == value, f"challenge did not bind {key}")
    return raw


async def probe(repo: Path) -> dict[str, Any]:
    module_path = Path(specorganon.__file__).resolve()
    site_packages = Path(sysconfig.get_path("purelib")).resolve()
    _require(sys.prefix != sys.base_prefix
             and module_path.is_relative_to(site_packages)
             and not module_path.is_relative_to(repo / "src"),
             "specorganon must be loaded from a wheel installed in this virtual environment")
    probe_sha256 = _sha256(Path(__file__).read_bytes())
    manifest_path = repo / "workflows" / "synthetic_full.json"
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    steps = manifest["steps"]
    item_steps = [step for step in steps if step["op"] == "put"]
    advance_steps = [step for step in steps if step["op"] == "advance"]
    _require(len(item_steps) == 29 and [step["phase"] for step in advance_steps] == list(PHASES),
             "synthetic_full.json no longer matches the nine-phase probe contract")
    _require({step["id"] for step in item_steps if step["kind"] in {"norm", "decision"}} == APPROVALS,
             "synthetic_full.json normative targets changed")
    bin_dir = Path(sys.executable).parent
    cli = bin_dir / "organon"
    mcp = bin_dir / "organon-mcp"
    _require(cli.is_file() and mcp.is_file(), "installed wheel CLI and MCP executables are required")
    with tempfile.TemporaryDirectory(prefix="organon-signed-full-") as temporary:
        work = Path(temporary)
        case = work / "case"
        path = str(case)
        registry = work / "trusted-public-keys.json"
        registry.write_text(json.dumps({"schema": 2, "cases": {}}), encoding="utf-8")
        registry.chmod(0o600)
        home = work / "home"
        scratch = work / "tmp"
        home.mkdir()
        scratch.mkdir()
        env = {
            "PATH": os.pathsep.join((str(bin_dir), "/usr/bin", "/bin")),
            "HOME": str(home),
            "TMPDIR": str(scratch),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONNOUSERSITE": "1",
            "ORGANON_APPROVERS_FILE": str(registry),
            "ORGANON_ROOT": str(work),
        }
        created = _cli(cli, env, work, "init", path, "--title", "Synthetic signed full workflow",
                       "--domain", "synthetic mechanics only", "--actor", RUNNER,
                       "--approval-policy", "signed")
        project = created["project"]
        _require(project["approval_policy"] == "signed", "temporary case was not signed")
        approver_key = Ed25519PrivateKey.generate()
        reviewer_key = Ed25519PrivateKey.generate()
        approver_public = _public(approver_key)
        reviewer_public = _public(reviewer_key)
        _registry(registry, case, project, created["project_sha256"],
                  approver_public, reviewer_public)
        params = StdioServerParameters(command=str(mcp), cwd=str(work), env=env)
        run_transports: list[str] = []
        decisions: list[dict[str, Any]] = []
        checkpoints: list[dict[str, Any]] = []
        negative: dict[str, bool] = {}
        async with Client(params, mode="legacy") as client:
            discovered = {tool.name for tool in (await client.list_tools()).tools}
            required = {"run", "status", "approval_challenge", "approve",
                        "phase_review_challenge", "review_phase"}
            _require(required <= discovered, "installed MCP server lacks required signed workflow tools")

            async def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                return _mcp_data(await client.call_tool(name, arguments), name)

            async def status_pair() -> dict[str, Any]:
                cli_state = _cli(cli, env, work, "status", path)
                mcp_state = await call("status", {"path": path})
                _require(cli_state == mcp_state, "CLI and MCP disagree on signed case status")
                return cli_state

            async def run(transport: str) -> dict[str, Any]:
                run_transports.append(transport)
                if transport == "cli":
                    return _cli(cli, env, work, "run", path, "--manifest", str(manifest_path),
                                "--actor", RUNNER)
                return await call("run", {"path": path, "manifest": manifest, "actor": RUNNER})

            async def challenge_pair(kind: str, target: str, reason: str, actor: str) -> dict[str, Any]:
                if kind == "phase":
                    cli_args = ("phase-review-challenge", path, target, "--verdict", "accept",
                                "--reason", reason, "--actor", actor)
                    tool = "phase_review_challenge"
                    arguments = {"path": path, "phase": target, "verdict": "accept",
                                 "reason": reason, "actor": actor}
                else:
                    cli_args = ("approval-challenge", path, target, "--reason", reason,
                                "--actor", actor)
                    tool = "approval_challenge"
                    arguments = {"path": path, "id": target, "reason": reason, "actor": actor}
                before = (case / "organon.json").read_bytes()
                cli_challenge = _cli(cli, env, work, *cli_args)
                mcp_challenge = await call(tool, arguments)
                _require(cli_challenge == mcp_challenge, f"CLI and MCP {kind} challenges differ")
                _require((case / "organon.json").read_bytes() == before,
                         f"{kind} challenge changed the ledger")
                return cli_challenge

            result = await run("cli")
            for decision_number in range(20):
                if result["status"] == "complete":
                    break
                _require(result["status"] == "waiting", "runner left neither a pause nor completion")
                task = result["next"]
                phase = task["phase"]
                action = task["action"]
                _require(phase in PHASES, "runner paused outside the declared nine phases")
                ledger, before = _ledger(case)
                head = ledger["events"][-1]["hash"] if ledger["events"] else ZERO_HASH
                binding = {
                    "case_id": project["case_id"],
                    "case_path": str(case.resolve(strict=True)),
                    "project_sha256": created["project_sha256"],
                    "ledger_head_sha256": head,
                }
                if action == "human_approval":
                    targets = task["approval_targets"]
                    _require(len(targets) == 1 and targets[0]["id"] in APPROVALS,
                             "runner requested an unexpected normative target")
                    item_id = targets[0]["id"]
                    reason = f"Synthetic key approval of {item_id}; no human authenticated"
                    challenge = await challenge_pair("approval", item_id, reason, APPROVER)
                    message = _message(challenge, {
                        **binding, "purpose": "specorganon.normative_approval",
                        "actor": APPROVER, "reason": reason, "item_id": item_id,
                        "item_version": targets[0]["version"],
                    })
                    if item_id == "n1":
                        rejected = await client.call_tool("approve", {
                            "path": path, "id": item_id, "reason": reason, "actor": APPROVER,
                        })
                        _require(rejected.is_error and (case / "organon.json").read_bytes() == before,
                                 "unsigned MCP approval changed the ledger")
                        negative["unsigned_normative_mcp_no_write"] = True
                    signature = base64.b64encode(approver_key.sign(message)).decode("ascii")
                    if item_id == "n1":
                        event = _cli(cli, env, work, "approve", path, item_id, "--reason", reason,
                                     "--actor", APPROVER, "--signature", signature)
                        decision_transport = "cli"
                    else:
                        event = await call("approve", {
                            "path": path, "id": item_id, "reason": reason,
                            "actor": APPROVER, "signature": signature,
                        })
                        decision_transport = "mcp"
                    _require(event["kind"] == "approval" and event["payload"]["id"] == item_id,
                             "signed normative approval did not append its event")
                    decisions.append({"kind": "approval", "target": item_id,
                                      "transport": decision_transport, "seq": event["seq"]})
                elif action == "review_phase":
                    reason = f"Synthetic key review of {phase}; no human or field assessment"
                    challenge = await challenge_pair("phase", phase, reason, REVIEWER)
                    message = _message(challenge, {
                        **binding, "purpose": "specorganon.phase_review",
                        "phase": phase, "snapshot": result["next"]["gate"]["snapshot"],
                        "verdict": "accept", "reason": reason, "actor": REVIEWER,
                    })
                    if phase == "frame":
                        _cli_rejected(cli, env, work, "review-phase", path, phase,
                                      "--verdict", "accept", "--reason", reason,
                                      "--actor", REVIEWER)
                        _require((case / "organon.json").read_bytes() == before,
                                 "unsigned CLI phase review changed the ledger")
                        negative["unsigned_phase_cli_no_write"] = True
                    signature = base64.b64encode(reviewer_key.sign(message)).decode("ascii")
                    if PHASES.index(phase) % 2 == 0:
                        event = await call("review_phase", {
                            "path": path, "phase": phase, "verdict": "accept",
                            "reason": reason, "actor": REVIEWER, "signature": signature,
                        })
                        decision_transport = "mcp"
                    else:
                        event = _cli(cli, env, work, "review-phase", path, phase,
                                     "--verdict", "accept", "--reason", reason,
                                     "--actor", REVIEWER, "--signature", signature)
                        decision_transport = "cli"
                    _require(event["kind"] == "phase_review"
                             and event["payload"]["phase"] == phase
                             and event["payload"]["snapshot"] == result["next"]["gate"]["snapshot"],
                             "signed phase review did not append the bound event")
                    decisions.append({"kind": "phase_review", "target": phase,
                                      "transport": decision_transport, "seq": event["seq"]})
                    reviewed = await status_pair()
                    gate = reviewed["phases"][phase]
                    _require(gate["reviewed"] and gate["independent_review"]
                             and gate["review_signature_verified"]
                             and gate["review_provenance"] == "signed_verified"
                             and not gate["accepted"],
                             f"signed review did not authenticate {phase} before advance")
                else:
                    raise AssertionError(f"unexpected workflow pause: {phase}/{action}")
                transport = "mcp" if run_transports[-1] == "cli" else "cli"
                result = await run(transport)
                state = await status_pair()
                _require(state["approval_trust"] == "configured"
                         and state["phase_review_trust"] == "configured",
                         "registered signed case lost its trust context")
                if action == "review_phase":
                    _require(state["phases"][phase]["accepted"],
                             f"runner did not advance signed phase {phase}")
                checkpoints.append({
                    "cursor": result["cursor"], "status": result["status"],
                    "reason": result["reason"], "transport": transport,
                    "revision": state["revision"],
                })
            else:
                raise AssertionError("signed workflow exceeded its 20-decision bound")
            _require(result["status"] == "complete" and result["cursor"] == len(steps),
                     "signed workflow did not complete its manifest")
            _require([entry["target"] for entry in decisions if entry["kind"] == "phase_review"] == list(PHASES),
                     "signed phase reviews did not cover each phase in order")
            _require({entry["target"] for entry in decisions if entry["kind"] == "approval"} == APPROVALS,
                     "signed normative approvals did not cover both decisions")
            _require(len(decisions) == 11 and len(run_transports) == 12,
                     "signed workflow used an unexpected number of pauses")
            _require(all(run_transports[index] != run_transports[index - 1]
                         for index in range(1, len(run_transports))),
                     "CLI and MCP runner invocations did not alternate")
            _require(negative == {
                "unsigned_normative_mcp_no_write": True,
                "unsigned_phase_cli_no_write": True,
            }, "missing-signature negative controls were not observed")

            final = await status_pair()
            _require(final["project"]["approval_policy"] == "signed"
                     and final["revision"] == 49,
                     "signed case has an unexpected final policy or revision")
            _require(set(final["items"]) == {step["id"] for step in item_steps},
                     "final signed case item set differs from the manifest")
            for step in item_steps:
                item = final["items"][step["id"]]
                _require((item["kind"], item["text"], item["data"], item["version"], item["deps"])
                         == (step["kind"], step["text"], step["data"], 1,
                             {ref: 1 for ref in step["refs"]}),
                         f"manifest artifact {step['id']} differs from its ledger state")
            for phase in PHASES:
                gate = final["phases"][phase]
                _require(gate["accepted"] and gate["reviewed"] and gate["independent_review"]
                         and gate["review_signature_verified"]
                         and gate["review_provenance"] == "signed_verified",
                         f"phase {phase} lacks a current verified acceptance")
            _require(all(final["items"][item_id]["approval_status"] == "signed_verified"
                         for item_id in APPROVALS),
                     "normative targets lack verified signed approvals")
            _require(final["items"]["ass1"]["data"]["verdict"] == "no_demostrado",
                     "synthetic field assessment claimed success")
            _require(final["items"]["ass1"]["data"]["claim_scope"] == "field",
                     "synthetic assessment changed its declared field scope")
            _require(final["items"]["t1"]["data"]["passed"] is True
                     and final["items"]["t1"]["data"]["command"].startswith("fixture-only:"),
                     "synthetic test artifact changed its invented command declaration")

            ledger, final_raw = _ledger(case)
            counts = dict(sorted(Counter(event["kind"] for event in ledger["events"]).items()))
            _require(counts == {
                "approval": 2, "item_put": 29, "phase_advance": 9, "phase_review": 9,
            }, "ledger event classes differ from the full signed workflow")
            reviews = [event for event in ledger["events"] if event["kind"] == "phase_review"]
            advances = [event for event in ledger["events"] if event["kind"] == "phase_advance"]
            approvals = [event for event in ledger["events"] if event["kind"] == "approval"]
            _require([event["payload"]["phase"] for event in reviews] == list(PHASES),
                     "ledger phase review order changed")
            _require([event["payload"]["phase"] for event in advances] == list(PHASES),
                     "ledger phase advance order changed")
            for review, advance in zip(reviews, advances, strict=True):
                phase = review["payload"]["phase"]
                _require(review["actor"] == REVIEWER
                         and isinstance(review["payload"].get("signature"), str)
                         and isinstance(review["payload"].get("key_sha256"), str)
                         and review["payload"]["snapshot"] == final["phases"][phase]["snapshot"]
                         and advance["payload"]["review_seq"] == review["seq"]
                         and advance["payload"]["snapshot"] == review["payload"]["snapshot"]
                         and advance["seq"] > review["seq"],
                         f"phase {phase} advance is not tied to its signed review")
            _require({event["payload"]["id"] for event in approvals} == APPROVALS
                     and all(event["actor"] == APPROVER and event["payload"].get("signature")
                             for event in approvals),
                     "normative approval events lack signed provenance")
            _require(len(final["phase_review_history"]) == 9
                     and all(entry["signature_verified"] and entry["provenance"] == "signed_verified"
                             for entry in final["phase_review_history"]),
                     "phase review history does not verify on replay")

            cli_replay = await run("cli")
            mcp_replay = await run("mcp")
            _require(all(replay["status"] == "complete" and replay["applied"] == 0
                         and replay["skipped"] == len(steps) for replay in (cli_replay, mcp_replay)),
                     "replay did not skip every completed manifest step")
            _require((case / "organon.json").read_bytes() == final_raw,
                     "CLI/MCP replay mutated the signed ledger")
            _require(await status_pair() == final, "replay changed effective signed status")

            _registry(registry, case, project, created["project_sha256"], approver_public, None)
            revoked = await status_pair()
            _require(revoked["approval_trust"] == "configured"
                     and revoked["phase_review_trust"] == "unavailable",
                     "reviewer revocation affected the wrong trust domain")
            _require(all(not revoked["phases"][phase]["accepted"]
                         and not revoked["phases"][phase]["reviewed"] for phase in PHASES),
                     "reviewer revocation did not reopen every signed phase")
            _require(not revoked["phases"]["frame"]["review_signature_verified"]
                     and revoked["phases"]["frame"]["review_provenance"] == "signature_unverified",
                     "revoked frame review remained verified")
            _require((case / "organon.json").read_bytes() == final_raw,
                     "reviewer revocation changed ledger bytes")
            _registry(registry, case, project, created["project_sha256"],
                      approver_public, reviewer_public)
            restored = await status_pair()
            _require(restored == final and (case / "organon.json").read_bytes() == final_raw,
                     "restoring trusted reviewer key did not restore the same signed status")

            return {
                "schema": 1,
                "classification": "synthetic_signed_full_workflow_installed_cli_stdio_mcp",
                "receipt_kind": "rerunnable_summary_not_detached_attestation",
                "probe_sha256": probe_sha256,
                "manifest_sha256": _sha256(manifest_raw),
                "child_environment_keys": sorted(env),
                "transport": {"run_sequence": run_transports[:12],
                              "cli_mcp_status_equal": True, "stdio_mcp_real": True,
                              "wheel_module_under_site_packages": True},
                "decisions": decisions,
                "checkpoints": checkpoints,
                "final": {"revision": final["revision"], "event_counts": counts,
                          "artifact_count": len(final["items"]),
                          "accepted_phases": list(PHASES),
                          "signed_approvals": sorted(APPROVALS),
                          "signed_reviews": len(reviews),
                          "phase_snapshots": {
                              phase: final["phases"][phase]["snapshot"] for phase in PHASES
                          },
                          "assessment_verdict": final["items"]["ass1"]["data"]["verdict"],
                          "assessment_claim_scope": "field",
                          "ledger_sha256": _sha256(final_raw)},
                "negative_controls": negative,
                "replay": {"cli_applied": cli_replay["applied"],
                           "mcp_applied": mcp_replay["applied"],
                           "ledger_byte_identical": True},
                "reviewer_key_revocation": {"all_phases_reopened": True,
                                             "ledger_byte_identical": True,
                                             "restoration_recovered_status": True},
                "scope": {
                    "human_identity_authenticated": False,
                    "independent_human_judgment_tested": False,
                    "field_impact_tested": False,
                    "t1_passed_is_invented_manifest_data": True,
                    "t1_command_executed_or_authenticated": False,
                    "content_is_synthetic": True,
                    "private_keys_written_to_disk": False,
                },
            }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = asyncio.run(probe(args.repo_root.resolve(strict=True)))
    serialized = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        args.output.write_text(serialized, encoding="utf-8")
    sys.stdout.write(serialized)


if __name__ == "__main__":
    main()
