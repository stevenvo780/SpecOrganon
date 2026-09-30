"""Exercise D101 with an installed wheel, SIGKILL recovery and real stdio MCP.

All cases are new development copies. The private signing key exists only in
memory. Its public identity is synthetic: a mechanics control, not human
acceptance, scientific quality, field evidence or normative authorization.
The probe preserves raw transport responses and leaves failures inspectable.
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
from collections import Counter
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

import specorganon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_audited_bread_recipe as recipe  # noqa: E402

REVIEWER = "agent:d101_synthetic_mechanics_reviewer"
REASON = "Synthetic mechanics control only; no human or scientific acceptance"
HOOK = '''\
import os
import signal
from pathlib import Path
from specorganon import engine
_append = engine.append_event
_case = Path(os.environ["ORGANON_TEST_CRASH_CASE"]).resolve(strict=True)
def _crash(directory, kind, payload, actor, *, expected_seq=None):
    event = _append(directory, kind, payload, actor, expected_seq=expected_seq)
    if (Path(directory).resolve(strict=True) == _case and kind == "item_put"
            and event["seq"] == 16 and payload["id"] == os.environ["ORGANON_TEST_CRASH_ITEM"]):
        os.kill(os.getpid(), signal.SIGKILL)
    return event
engine.append_event = _crash
'''


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.write_bytes(recipe._render(value))


def dependents(steps, roots):
    reached = set(roots)
    while True:
        updated = reached | {s["id"] for s in steps if reached.intersection(s["refs"])}
        if updated == reached:
            return reached - roots
        reached = updated


async def probe(output: Path) -> dict:
    output = output.absolute()
    require(not output.exists(), "probe destination must be new")
    output.mkdir(parents=True)
    module = Path(specorganon.__file__).resolve(strict=True)
    purelib = Path(sysconfig.get_path("purelib")).resolve(strict=True)
    require(sys.prefix != sys.base_prefix and module.is_relative_to(purelib)
            and not module.is_relative_to(ROOT / "src"), "use an installed wheel virtual environment")
    scripts = Path(sysconfig.get_path("scripts"))
    cli, mcp = scripts / "organon", scripts / "organon-mcp"
    original_pins = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in (
        ROOT / "GOAL.md", ROOT / "cases/bread_development/source_claims.json",
        ROOT / "cases/bread_norway/survey_table1.json", recipe.auditor.CONTRACT,
        ROOT / "cases/bread_norway/source_lca.pdf", ROOT / "cases/bread_norway/source_survey.pdf",
    )}
    directory = output / "crash_recipe"
    prepared = recipe.prepare(ROOT, directory)
    case = directory / "case"
    ledger = case / "organon.json"
    path = str(case)
    manifest = recipe._json(directory / "manifest.json")
    steps = manifest["steps"]
    require(len(steps) == 37, "D101 publication size changed")
    env = {"PATH": os.pathsep.join((str(scripts), "/usr/bin", "/bin")),
           "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONNOUSERSITE": "1",
           "ORGANON_ROOT": str(output),
           "ORGANON_APPROVERS_FILE": str(directory / "public_keys.json")}
    trace = output / "transports.jsonl"

    def record(value):
        with trace.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")

    def command(*args, custom_env=None, pass_fds=()):
        result = subprocess.run([str(cli), *args], cwd=output, env=custom_env or env,
                                capture_output=True, text=True, timeout=60, pass_fds=pass_fds)
        record({"transport": "cli", "args": list(args), "returncode": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr})
        return result

    def call_cli(*args):
        result = command(*args)
        require(result.returncode == 0, f"CLI {args[0]} rejected: {result.stderr}")
        return json.loads(result.stdout)

    created = call_cli("init", path, "--title", recipe.TITLE, "--domain", recipe.DOMAIN,
                       "--actor", recipe.ACTOR, "--approval-policy", "signed")
    hook = output / "crash_hook"
    hook.mkdir()
    (hook / "sitecustomize.py").write_text(HOOK, encoding="utf-8")
    crash_env = {**env, "PYTHONPATH": str(hook), "ORGANON_TEST_CRASH_CASE": path,
                 "ORGANON_TEST_CRASH_ITEM": steps[15]["id"]}
    recipe.validate(directory)
    with recipe.sealed_manifest(manifest) as (snapshot, fd):
        killed = command("run", path, "--manifest", snapshot, "--actor", recipe.ACTOR,
                         custom_env=crash_env, pass_fds=(fd,))
    require(killed.returncode == -signal.SIGKILL, "CLI did not reach injected durable SIGKILL")
    prefix_raw = ledger.read_bytes()
    prefix = json.loads(prefix_raw)["events"]
    require(len(prefix) == 16 and all(e["kind"] == "item_put" for e in prefix)
            and [e["payload"]["id"] for e in prefix] == [s["id"] for s in steps[:16]],
            "crash did not leave exact 16-event prefix")
    (output / "durable_prefix.json").write_bytes(prefix_raw)
    require(recipe.validate(directory)["state"] == "checkpoint_verified", "crash prefix cannot resume")
    resumed = await recipe.execute(directory, "mcp", mcp=mcp)
    record({"transport": "controller_real_mcp", "result": resumed})
    require((resumed["result"]["applied"], resumed["result"]["skipped"]) == (21, 16),
            "fresh MCP did not resume exact durable prefix")
    require(json.loads(ledger.read_bytes())["events"][:16] == prefix, "MCP rewrote prefix")
    complete_raw = ledger.read_bytes()
    (output / "complete_pending.json").write_bytes(complete_raw)
    retry = await recipe.execute(directory, "cli", cli=cli)
    record({"transport": "controller_real_cli", "result": retry})
    require((retry["result"]["applied"], retry["result"]["skipped"]) == (0, 37)
            and ledger.read_bytes() == complete_raw, "CLI retry duplicated writes")
    counts = Counter(e["payload"]["id"] for e in json.loads(complete_raw)["events"])
    require(set(counts.values()) == {1}, "item publication duplicated")

    reverse = output / "mcp_first_recipe"
    recipe.prepare(ROOT, reverse)
    first = await recipe.execute(reverse, "mcp", mcp=mcp)
    reverse_raw = (reverse / "case/organon.json").read_bytes()
    second = await recipe.execute(reverse, "cli", cli=cli)
    record({"transport": "controller_reverse", "first": first, "second": second})
    require((first["result"]["applied"], second["result"]["skipped"]) == (37, 37)
            and second["result"]["applied"] == 0
            and (reverse / "case/organon.json").read_bytes() == reverse_raw,
            "MCP to CLI replay duplicated writes")

    key = Ed25519PrivateKey.generate()  # Never persisted or included in a prompt.
    public = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    write(directory / "public_keys.json", {"schema": 2, "cases": {
        created["project"]["case_id"]: {
            "path": path, "project_sha256": created["project_sha256"], "approvers": {},
            "phase_reviewers": {REVIEWER: public},
        },
    }})
    params = StdioServerParameters(command=str(mcp), cwd=str(output), env=env)
    pairs = 0
    checks = {}
    async with Client(params) as client:
        discovered = sorted(t.name for t in (await client.list_tools()).tools)
        require({"status", "gate", "next_task", "run", "advance", "put",
                 "phase_review_challenge", "review_phase"} <= set(discovered), "MCP tools missing")

        async def call(name, args, reject=False):
            response = await client.call_tool(name, args)
            record({"transport": "mcp", "tool": name, "args": args,
                    "response": response.model_dump(mode="json")})
            require(bool(response.is_error) == reject, f"MCP {name} unexpected error status")
            if reject:
                return {"is_error": True}
            return response.structured_content or json.loads(response.content[0].text)

        async def pair():
            nonlocal pairs
            before = ledger.read_bytes()
            state = call_cli("status", path)
            require(state == await call("status", {"path": path}), "CLI/MCP status differs")
            gate = call_cli("gate", path, "frame")
            require(gate == await call("gate", {"path": path, "phase": "frame"})
                    == state["phases"]["frame"], "CLI/MCP gate differs")
            task = call_cli("next-task", path)
            require(task == await call("next_task", {"path": path}), "CLI/MCP next task differs")
            require(before == ledger.read_bytes(), "read queries wrote ledger")
            pairs += 1
            return state

        pending = await pair()
        require(pending["phases"]["frame"]["ready"] and not pending["phases"]["frame"]["accepted"],
                "recipe fabricated framing acceptance")
        args = {"path": path, "phase": "frame", "verdict": "accept", "reason": REASON, "actor": REVIEWER}
        challenge = await call("phase_review_challenge", args)
        signature = base64.b64encode(key.sign(base64.b64decode(challenge["message_base64"], validate=True))).decode()
        await call("review_phase", {**args, "signature": signature})
        call_cli("advance", path, "frame", "--actor", recipe.ACTOR)
        accepted = await pair()
        require(accepted["phases"]["frame"]["accepted"], "synthetic signed control not accepted")
        signed_raw = ledger.read_bytes()
        (output / "synthetic_frame_control.json").write_bytes(signed_raw)
        # External mechanical review/advance deliberately diverges from the put-only recipe.
        try:
            recipe.validate(directory)
        except recipe.RecipeError as exc:
            external_review_rejection = str(exc)
        else:
            raise AssertionError("recipe treated external synthetic review as its checkpoint")
        archives = recipe._json(directory / "binding.json")["files"]
        for name in archives:
            archive = case / name
            raw = archive.read_bytes()
            roots = {s["id"] for s in steps if s["kind"] == "evidence" and s["data"]["archive"] == name}
            reached = dependents(steps, roots)
            equal = output / ("equal_bytes_" + name)
            equal.write_bytes(raw)
            for mode in ("mutate", "remove", "symlink"):
                label = name + ":" + mode
                try:
                    if mode == "mutate":
                        archive.write_bytes(raw + b"\nD101 synthetic mutation\n")
                    else:
                        archive.unlink()
                        if mode == "symlink":
                            archive.symlink_to(equal)
                    state = await pair()
                    frame = state["phases"]["frame"]
                    require(not frame["ready"] and not frame["accepted"]
                            and frame["snapshot"] != accepted["phases"]["frame"]["snapshot"],
                            f"{label} did not invalidate signed frame")
                    require(all(any("local archive" in issue for issue in state["items"][id]["issues"])
                                for id in roots | reached), f"{label} missing transitive archive issues")
                    require(all(not state["items"][id]["issues"] for id in ("p_seed", "a_chain", "b_seed", "s_historical")),
                            f"{label} invalidated unrelated branch")
                    rejected = command("advance", path, "frame", "--actor", recipe.ACTOR)
                    require(rejected.returncode != 0, f"{label} CLI advanced")
                    await call("advance", {"path": path, "phase": "frame", "actor": recipe.ACTOR}, reject=True)
                    replay = {**manifest, "steps": [*steps, {"op": "advance", "phase": "frame"}]}
                    run = await call("run", {"path": path, "manifest": replay, "actor": recipe.ACTOR})
                    require(run["status"] == "waiting" and run["reason"] == "invalid_or_stale_artifact"
                            and run["applied"] == 0 and run["skipped"] == 37,
                            f"{label} invalid manifest advanced")
                    try:
                        recipe.validate(directory)
                    except recipe.RecipeError as exc:
                        rejection = str(exc)
                    else:
                        raise AssertionError(f"{label} controller accepted changed archive")
                    require(ledger.read_bytes() == signed_raw, f"{label} rejected operation wrote")
                    checks[label] = {"affected_evidence_ids": sorted(roots), "dependent_issue_ids": sorted(reached),
                                     "snapshot_changed": True, "ready": False, "accepted": False,
                                     "recipe_rejection": rejection, "cli_advance_exit": rejected.returncode,
                                     "mcp_advance_is_error": True, "run": run,
                                     "ledger_byte_identical": True, "unrelated_branch_valid": True}
                finally:
                    if archive.exists() or archive.is_symlink():
                        archive.unlink()
                    archive.write_bytes(raw)
                require(await pair() == accepted and ledger.read_bytes() == signed_raw,
                        f"{label} exact-byte restoration did not recover control")
                checks[label]["exact_byte_restoration_recovered_status"] = True

        assumption = next(s for s in steps if s["id"] == "s_historical")
        await call("put", {"path": path, "id": assumption["id"], "kind": assumption["kind"],
                           "text": assumption["text"] + " Revisión de supuesto requiere nueva evaluación.",
                           "refs": assumption["refs"], "data": assumption["data"],
                           "actor": recipe.ACTOR, "expected_version": 1, "expected_deps": {"p_seed": 1}})
        changed = await pair()
        require(changed["items"]["s_historical"]["version"] == 2
                and not changed["phases"]["frame"]["accepted"], "assumption revision did not reopen frame")
        revised_raw = ledger.read_bytes()
        replay = await call("run", {"path": path, "manifest": manifest, "actor": recipe.ACTOR}, reject=True)
        require(ledger.read_bytes() == revised_raw, "old manifest overwrote new assumption")
        (output / "revised_assumption.json").write_bytes(revised_raw)

    require(all(sha((ROOT / name).read_bytes()) == digest for name, digest in original_pins.items()),
            "original sources changed")
    return {"schema": 1, "study_id": "D101", "python": ".".join(map(str, sys.version_info[:3])),
            "installed_module": str(module), "installed_passages_sha256": sha(Path(recipe.source_passages.__file__).read_bytes()),
            "probe_sha256": sha(Path(__file__).read_bytes()), "controller_code": recipe._code_pins(),
            "prepared": prepared, "manifest_steps": 37, "crash": {"exit": killed.returncode, "durable_puts": 16,
            "hook_sha256": sha(HOOK.encode()), "item": steps[15]["id"]}, "resume_mcp": resumed,
            "replay_cli": retry, "reverse_mcp_cli": {"mcp": first, "cli": second}, "queries_equal_pairs": pairs,
            "mcp_tools": discovered, "archive_controls": checks, "external_review_rejection": external_review_rejection,
            "assumption_revision": {"version": 2, "accepted": False, "old_manifest_rejected": replay["is_error"],
                                    "ledger_byte_identical_on_rejected_replay": True},
            "original_source_pins": original_pins, "original_sources_preserved": True,
            "recipe_phase_advances": 0, "recipe_human_approvals": 0,
            "external_synthetic_mechanics_events": {"phase_reviews": 1, "phase_advances": 1, "assumption_puts": 1},
            "human_quality_Q": None, "field_intervention": False, "global_acceptance": "0/5",
            "source_semantics_scope": "audited recipe boundary; direct engine puts not semantically verified",
            "archive_transaction_atomic": False, "trace_sha256": sha(trace.read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        result = asyncio.run(probe(args.output))
        write(args.output / "receipt.json", result)
        print(json.dumps({"state": "passed", "python": result["python"],
                          "controls": len(result["archive_controls"]), "pairs": result["queries_equal_pairs"],
                          "global_acceptance": "0/5"}))
    except BaseException as exc:
        if args.output.exists():
            write(args.output / "probe_failure.json", {"type": type(exc).__name__, "reason": str(exc)})
        raise


if __name__ == "__main__":
    main()
