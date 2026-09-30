"""D108 installed documentary-energy experiment, only after committed freeze.

Usage: VENVPYTHON -I -B SCRIPT REPO NEWOUTPUT. Preparation negatives invoke the
verified builder's pure derive in memory; they are not semantic CLI checks.
No norms, reviews, phases, identities, field operations or model calls are made.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import traceback
import types

DOSSIER = "experiments/development/bread_energy_derivation_2026-09-30"
FREEZE = DOSSIER + "/source_freeze.json"
BUILDER = "scripts/build_bread_energy_variant.py"
PROBE = "scripts/probe_bread_energy_variant.py"
HELPER = "scripts/probe_citibike_fraction_variant.py"
HELPER_SHA = "a86896d0b4669ee82b7f349bfacc37e47f610eabf8fa22ca2e000d9671525d5b"
VERIFIER = "scripts/probe_indicator_retirement.py"
VERIFIER_SHA = "b0da73a20e8c91a8a5982e5734f4d45692cf922e817317d0218367001f94ec09"
PHASES = ("frame", "critique", "study", "observe", "explain", "compare", "specify", "build", "validate")
NEW_IDS = ("pr_energy_documentary", "inf_energy_documentary", "e_energy_documentary", "i_energy_documentary")
SOURCE_IDS = ("e_piece_mass", "e_bakery_electricity", "e_bakery_natural_gas")
CRITERIA = ("c_r_capture", "c_r_basis", "c_r_safety", "c_r_service")
ACTOR = "agent:D108-documentary-energy-technical"
BOOTSTRAP = (
    "import sys; raw=sys.stdin.buffer.read(); name=sys.argv[1]; sys.argv=sys.argv[1:]; "
    "exec(compile(raw,name,'exec'),{'__name__':'__main__','__file__':name,'__package__':None})"
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode()


def regular(path):
    require(stat.S_ISREG(path.lstat().st_mode), "not a regular public file: " + str(path))
    return path.read_bytes()


def new_file(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def git(repo, *args):
    return subprocess.check_output(["git", "--no-optional-locks", *args], cwd=repo,
                                   env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})


def frozen_inputs(repo, freeze):
    source = {}
    for name, row in freeze["files"].items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "noncanonical frozen path")
        path = repo / name
        require(path.resolve(strict=True).is_relative_to(repo), "frozen path escapes repository")
        raw = regular(path)
        require(pin(raw) == {k: row[k] for k in ("bytes", "sha256")} and raw == git(repo, "show", "HEAD:" + name),
                "live/committed frozen input differs: " + name)
        source[name] = raw
    required = {BUILDER, PROBE, HELPER, VERIFIER, DOSSIER + "/plan.json", DOSSIER + "/plan_inputs.json"}
    require(required.issubset(source), "required builder/probe/helper/plan missing from freeze")
    record = json.loads(source[DOSSIER + "/plan_inputs.json"])
    require(set(record["files"]).issubset(source), "plan input pin missing from freeze")
    for name, row in record["files"].items():
        require(pin(source[name]) == {k: row[k] for k in ("bytes", "sha256")}, "plan input differs: " + name)
    require(pin(source[HELPER])["sha256"] == HELPER_SHA and pin(source[VERIFIER])["sha256"] == VERIFIER_SHA,
            "exact D105 capture or D107 installed-verifier helper differs")
    require(freeze["probe"] == PROBE and freeze["runtime"] == record["runtime"], "probe/runtime differs from plan")
    return source


def load(raw, path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def inventory(root):
    rows = []
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "artifact symlink forbidden")
        if path.is_file():
            rows.append({"path": str(path.relative_to(root)), **pin(regular(path))})
        else:
            require(path.is_dir(), "nonregular artifact forbidden")
    return rows


def pending(helper, state, original):
    # The frozen D105 helper names its own norm/decision. This temporary view
    # adapts names only; the real bread graph is separately checked in full.
    view = {**state, "items": {**state["items"], "n_scope": state["items"]["n_harm"],
                              "d_reporting": state["items"]["d_pending"]}}
    helper._pending(view)
    require(all(not item["approved"] for item in state["items"].values() if item["kind"] in {"norm", "decision"}),
            "a real bread norm or decision became approved")
    require(not any(phase["accepted"] for phase in state["phases"].values()), "phase accepted")
    for key in CRITERIA:
        require(state["items"][key]["data"] == original[key]["data"]
                and state["items"][key]["data"]["threshold"] is None, "intervention criterion changed: " + key)


def preparation_negatives(builder, items, claims, pdf_pin, scope, source_raw):
    """External preparation validation in memory; no CLI or ledger writer."""
    rows = []
    mutations = (
        ("source-value", lambda i, c, s: i["e_piece_mass"]["data"].update(value="737")),
        ("source-unit", lambda i, c, s: i["e_bakery_electricity"]["data"].update(unit="Wh/piece")),
        ("source-base", lambda i, c, s: i["e_bakery_natural_gas"]["data"].update(base="one kg")),
        ("source-version", lambda i, c, s: i["e_piece_mass"].update(version=2)),
        ("source-date", lambda i, c, s: i["e_piece_mass"]["data"].update(date="2018-12-22")),
        ("scope-date", lambda i, c, s: s.update(publication_date="2018-12-22")),
        ("scope-population", lambda i, c, s: s.update(population="current observed bakery lot")),
    )
    for label, mutate in mutations:
        candidate, candidate_claims, candidate_scope = copy.deepcopy(items), copy.deepcopy(claims), copy.deepcopy(scope)
        mutate(candidate, candidate_claims, candidate_scope)
        try:
            builder.derive(candidate, candidate_claims, pdf_pin, candidate_scope)
        except ValueError as exc:
            rows.append({"label": label, "rejected": True, "error": str(exc), "ledger_writes": 0,
                         "scope": "verified builder pure derive in memory; not generic CLI semantic validation",
                         "source_ledger_pin": pin(source_raw)})
        else:
            raise ValueError("preparation accepted wrong " + label)
    return rows


async def next_pair(captures, client, case):
    before = regular(case / "organon.json")
    cli = captures.command("next-task", str(case))
    mcp = await captures.tool(client, "next_task", {"path": str(case)})
    require(cli == mcp and regular(case / "organon.json") == before, "next_task parity/read-only failed")
    captures.append({"transport": "comparison", "operation": "next_task", "case": str(case),
                     "responses_equal": True, "ledger_unchanged": True, "ledger": pin(before)})
    return cli


def immutable_fields(item):
    return {key: item[key] for key in ("id", "kind", "version", "text", "data", "deps")}


def check_positive(state, ledger, baseline, manifest, derivation_raw, original, helper, builder):
    require(len(ledger["events"]) == 68 and ledger["events"][:64] == baseline["events"]
            and ledger["project"] == baseline["project"], "68 events/source64 prefix/signed project differs")
    events = ledger["events"][64:]
    require([e["kind"] for e in events] == ["item_put"] * 4
            and [e["payload"]["id"] for e in events] == list(NEW_IDS), "added events differ from four puts")
    for key, item in original.items():
        require(immutable_fields(state["items"][key]) == immutable_fields(item), "original item rewritten: " + key)
    for step in manifest["steps"]:
        item = state["items"][step["id"]]
        require(item["version"] == 1 and item["kind"] == step["kind"] and item["data"] == step["data"]
                and item["text"] == step["text"] and item["deps"] == step["expected_deps"], "manifest item differs")
        require(not item["stale"] and not item["contested"] and not item["issues"], "new item is not current/sound")
    evidence, indicator = state["items"][NEW_IDS[2]]["data"], state["items"][NEW_IDS[3]]["data"]
    require(evidence["metric_key"] == indicator["metric"] == builder.METRIC
            and evidence["unit"] == indicator["unit"] == builder.UNIT
            and evidence["value"] == indicator["value"] == "0.559782608695652173913043"
            and evidence["exact_ratio"] == {"numerator": 103, "denominator": 184}, "derived literal/metric/unit differs")
    derivation = builder.decode(derivation_raw)
    require(evidence["archive"] == "derivation.json" and evidence["source_sha256"] == pin(derivation_raw)["sha256"]
            and evidence["origin"] == "derived" and "calculation" not in evidence
            and evidence["date"] == datetime.fromisoformat(derivation["derivation_performed_at_utc"]).date().isoformat()
            and evidence["source_publication_date"] == builder.DATE
            and evidence["derivation_performed_at_utc"] == derivation["derivation_performed_at_utc"]
            and evidence["business_record_date"] == "unknown", "derived archive/origin/temporal scope differs")
    require(set(SOURCE_IDS).issubset(state["items"][NEW_IDS[0]]["deps"]), "protocol lacks three direct source pins")
    pending(helper, state, original)


async def execute(helper, builder, captures, installed, repo, output, source, report):
    from mcp.client import Client
    from mcp.client.stdio import StdioServerParameters

    record = builder.decode(source[DOSSIER + "/plan_inputs.json"])
    plan = builder.decode(source[DOSSIER + "/plan.json"])
    base = record["source_case"]["path"]
    source_raw = source[base + "/organon.json"]
    baseline = builder.decode(source_raw)
    original = {e["payload"]["id"]: copy.deepcopy(e["payload"]) for e in baseline["events"] if e["kind"] == "item_put"}
    claims = builder.decode(source[base + "/source_claims.json"])
    report["preparation_negatives"] = preparation_negatives(builder, original, claims, pin(source[base + "/source_lca.pdf"]), plan["derivation"], source_raw)
    report["preparation_negatives_no_ledger_writer_invoked"] = True
    prepared = output / "prepared"
    result = captures.process([sys.executable, "-I", "-B", "-c", BOOTSTRAP, str(output / "sources/build.py"),
                               str(repo), str(prepared)], "verified-builder", payload=source[BUILDER])
    require(result.returncode == 0, "verified builder failed; original streams retained")
    require(regular(prepared / "case/organon.json") == source_raw, "preparation changed source64 ledger")
    manifest = builder.decode(regular(prepared / "manifest.json"))
    derivation_raw = regular(prepared / "case/derivation.json")
    report["preparation"] = builder.decode(regular(prepared / "receipt.json"))
    report["manifest"] = manifest
    report["derivation"] = builder.decode(derivation_raw)
    cases = {label: output / (label + "-case") for label in ("cli", "mcp")}
    for case in cases.values():
        shutil.copytree(prepared / "case", case)
    report["positive"] = {}
    run = captures.command("run", str(cases["cli"]), "--manifest", str(prepared / "manifest.json"), "--actor", ACTOR)
    require((run["applied"], run["skipped"], run["total_steps"]) == (4, 0, 4), "CLI did not apply four puts")
    params = StdioServerParameters(command=installed["executables"]["organon-mcp"]["path"], cwd=str(output), env=captures.env)
    async with Client(params, mode="legacy") as client:
        discovery_start = now()
        discovery = await asyncio.wait_for(client.list_tools(), timeout=90)
        raw_discovery = discovery.model_dump(mode="json", by_alias=True)
        new_file(output / "mcp_discovery.json", encoded(raw_discovery))
        captures.append({"transport": "mcp", "operation": "list_tools", "started_at_utc": discovery_start,
                         "finished_at_utc": now(), "response": raw_discovery,
                         "response_scope": "raw_sdk_model_not_wire_framing"})
        report["mcp_tools"] = sorted(tool.name for tool in discovery.tools)
        require(len(report["mcp_tools"]) == len(set(report["mcp_tools"])) == 23
                and "retire_indicator" in report["mcp_tools"], "expected 23 unprefixed installed tools")
        mcp_run = await captures.tool(client, "run", {"path": str(cases["mcp"]), "manifest": manifest, "actor": ACTOR})
        require((mcp_run["applied"], mcp_run["skipped"], mcp_run["total_steps"]) == (4, 0, 4), "MCP did not apply four puts")
        positive_states, positive_inventories = {}, {}
        for label, case in cases.items():
            before = regular(case / "organon.json")
            replay = (captures.command("run", str(case), "--manifest", str(prepared / "manifest.json"), "--actor", ACTOR)
                      if label == "cli" else await captures.tool(client, "run", {"path": str(case), "manifest": manifest, "actor": ACTOR}))
            require((replay["applied"], replay["skipped"], replay["total_steps"]) == (0, 4, 4)
                    and regular(case / "organon.json") == before, "manifest replay appended")
            state = await helper._pair(captures, client, case, "status")
            check_positive(state, builder.decode(before), baseline, manifest, derivation_raw, original, helper, builder)
            gates = {phase: await helper._pair(captures, client, case, "gate", phase=phase) for phase in PHASES}
            traces = {key: await helper._pair(captures, client, case, "trace", id=key) for key in NEW_IDS}
            task = await next_pair(captures, client, case)
            report["positive"][label] = {"run": run if label == "cli" else mcp_run, "replay": replay,
                                         "ledger": pin(before), "state": state, "nine_gates": gates,
                                         "four_traces": traces, "next_task": task, "source_prefix_events": 64,
                                         "events": 68, "accepted_phases": 0}
            positive_states[label] = state
            positive_inventories[label] = inventory(case)
        require({k: immutable_fields(v) for k, v in positive_states["cli"]["items"].items()}
                == {k: immutable_fields(v) for k, v in positive_states["mcp"]["items"].items()}, "transport item payloads differ")
        report["cross_case_comparison"] = {"item_kind_version_text_data_dependencies_equal": True,
            "separate_event_timestamps_and_hashes_excluded": True,
            "shared_preparation_derivation_timestamp_and_archive": True,
            "same_case_full_CLI_MCP_response_parity_checked": True}
        control_root = output / "controls"
        control_root.mkdir(mode=0o700)
        report["source_revision_controls"] = {}
        for key in SOURCE_IDS:
            case = control_root / key
            shutil.copytree(cases["cli"], case)
            before = await helper._pair(captures, client, case, "status")
            item = before["items"][key]
            argv = ["put", str(case), key, "--kind", item["kind"], "--text", item["text"],
                    "--data", encoded(item["data"]).decode(), "--expected-version", "1",
                    "--expected-deps", encoded(item["deps"]).decode(), "--actor", ACTOR]
            for ref in item["deps"]:
                argv.extend(["--ref", ref])
            captures.command(*argv)
            checkpoint = regular(case / "organon.json")
            state = await helper._pair(captures, client, case, "status")
            require(state["items"][key]["version"] == 2 and state["items"][key]["data"] == item["data"], "source data changed")
            require(all(state["items"][new]["stale"] for new in NEW_IDS), "source revision did not stale all four additions")
            pending(helper, state, original)
            traces = {new: await helper._pair(captures, client, case, "trace", id=new) for new in NEW_IDS}
            control_ledger = builder.decode(checkpoint)
            require(len(control_ledger["events"]) == 69 and control_ledger["events"][:68] == builder.decode(regular(cases["cli"] / "organon.json"))["events"]
                    and regular(case / "organon.json") == checkpoint, "revision control reads changed ledger/prefix")
            report["source_revision_controls"][key] = {"same_data_version": 2, "new_nodes_stale": list(NEW_IDS),
                "mutation_events": 1, "query_events": 0, "ledger": pin(checkpoint), "state": state, "traces": traces}
        report["archive_controls"] = {}
        for label in ("changed_archive", "missing_archive"):
            case = control_root / label
            shutil.copytree(cases["cli"], case)
            before = await helper._pair(captures, client, case, "status")
            ledger_before = regular(case / "organon.json")
            archive = case / "derivation.json"
            if label == "changed_archive":
                archive.write_bytes(derivation_raw + b"\n")
            else:
                archive.unlink()
            state = await helper._pair(captures, client, case, "status")
            expected = ("local archive bytes differ from source_sha256" if label == "changed_archive"
                        else "local archive is missing or unsafe to read")
            require(expected in state["items"][NEW_IDS[2]]["issues"]
                    and "depends on invalid local archive evidence e_energy_documentary" in state["items"][NEW_IDS[3]]["issues"],
                    "archive issue did not propagate to derived evidence/indicator")
            pending(helper, state, original)
            traces = {key: await helper._pair(captures, client, case, "trace", id=key) for key in NEW_IDS[2:]}
            require(regular(case / "organon.json") == ledger_before, "archive queries changed ledger")
            archive.write_bytes(derivation_raw)
            restored = await helper._pair(captures, client, case, "status")
            require(restored == before and regular(case / "organon.json") == ledger_before
                    and regular(archive) == derivation_raw, "archive exact restoration did not restore original state")
            report["archive_controls"][label] = {"state": state, "traces": traces, "query_events": 0,
                "mutation_events": 0, "ledger": pin(ledger_before), "archive_original": pin(derivation_raw),
                "archive_negative": pin(derivation_raw + b"\n") if label == "changed_archive" else None,
                "byte_exact_restore": True, "restored_state_equals_before": True}
        for label, case in cases.items():
            require(inventory(case) == positive_inventories[label], "controls mutated a positive case")
        report["positive_cases_unchanged_after_controls"] = True


def probe(repo, output):
    repo = repo.resolve(strict=True)
    freeze_raw = git(repo, "show", "HEAD:" + FREEZE)
    require(regular(repo / FREEZE) == freeze_raw, "working/committed freeze differs")
    freeze = json.loads(freeze_raw)
    source = frozen_inputs(repo, freeze)
    require(regular(Path(__file__)) == source[PROBE], "executed probe differs from frozen raw")
    verifier = load(source[VERIFIER], repo / VERIFIER, "_d108_verified_installed")
    installed = verifier.verify_installed(repo, freeze, source)
    require(installed["inventories"]["installed_inventory"]["verified_files"] == 1555, "installed public inventory must have 1555 files")
    require(not output.exists() and not output.is_symlink(), "output must be new")
    output = output.parent.resolve(strict=True) / output.name
    require(output.parent == Path(freeze["runtime"]).resolve(strict=True) and output.name == installed["label"], "output differs from reserved runtime/label")
    output.mkdir(mode=0o700)
    env = {"PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1"}
    os.environ.clear()
    os.environ.update(env)
    sys.dont_write_bytecode = True
    helper = load(source[HELPER], repo / HELPER, "_d108_verified_captures")
    builder = load(source[BUILDER], repo / BUILDER, "_d108_verified_builder")
    report = {"schema": 1, "study_id": "D108", "passed": False, "classification": "exposed_installed_documentary_energy_derivative",
              "started_at_utc": now(), "freeze_pin": pin(freeze_raw), "git_head": git(repo, "rev-parse", "HEAD").decode().strip(),
              "inputs_before": {k: pin(v) for k, v in source.items()}, "installed_before": installed,
              "executed_probe_pin": pin(source[PROBE]), "Q": None, "model_generations": 0, "field_operations": 0,
              "human_approvals": 0, "counts_toward_required_24": False, "physical_source_truth_authenticated": False,
              "external_custody_authenticated": False, "generic_put_semantically_validates_arithmetic": False,
              "no_automatic_retry": True, "supports_existing_four_intervention_indicators": False,
              "compiled_helpers": {HELPER: {**pin(source[HELPER]), "used": ["Captures", "_pair", "_pending"]},
                                   VERIFIER: {**pin(source[VERIFIER]), "used": ["verify_installed"]},
                                   BUILDER: {**pin(source[BUILDER]), "used": ["derive", "verified stdin main"]}},
              "pending_helper_adaptation": "temporary n_scope=n_harm/d_reporting=d_pending view, plus all real norm/decision and four criteria assertions"}
    captures = None
    try:
        new_file(output / "source_freeze.executed.json", freeze_raw)
        (output / "sources").mkdir(mode=0o700)
        for name, relative in ((PROBE, "probe.py"), (BUILDER, "build.py"), (HELPER, "capture_helper.py"), (VERIFIER, "installed_verifier.py")):
            new_file(output / "sources" / relative, source[name])

        class TimedCaptures(helper.Captures):
            """Use frozen captures while adding start/end times to MCP records."""

            def append(self, record):
                super().append({"recorded_at_utc": now(), **record})

            async def tool(self, client, name, arguments, *, rejected=False):
                started = now()
                try:
                    return await super().tool(client, name, arguments, rejected=rejected)
                finally:
                    self.append({"transport": "mcp-timing", "operation": name, "arguments": arguments,
                                 "started_at_utc": started, "finished_at_utc": now()})

        captures = TimedCaptures(output, env, installed["executables"]["organon"]["path"])
        asyncio.run(execute(helper, builder, captures, installed, repo, output, source, report))
        report["passed"] = True
    except Exception as exc:
        report.update(error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
    finally:
        if captures is not None:
            captures.stream.close()
            report["captured_calls"] = len(captures.records)
        try:
            after = frozen_inputs(repo, freeze)
            report["inputs_after"] = {k: pin(v) for k, v in after.items()}
            require(source == after, "repository frozen bytes changed")
            report["installed_after"] = verifier.verify_installed(repo, freeze, after)
            require(installed == report["installed_after"], "installed wheel/files/entrypoints changed")
            require(regular(repo / FREEZE) == freeze_raw and git(repo, "show", "HEAD:" + FREEZE) == freeze_raw
                    and regular(Path(__file__)) == source[PROBE], "freeze or executed probe changed")
            report["all_source_wheel_installed_and_entrypoint_pins_verified_before_after"] = True
        except Exception as exc:
            report["passed"] = False
            report.update(preservation_error=f"{type(exc).__name__}: {exc}", preservation_traceback=traceback.format_exc())
        report["finished_at_utc"] = now()
        report["retained_files"] = inventory(output)
        new_file(output / "report.json", encoded(report))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = probe(args.repo, args.output)
        print(json.dumps({"passed": report["passed"], "report": str(args.output / "report.json"), "error": report.get("error")}))
        return 0 if report["passed"] else 2
    except Exception as exc:
        print(json.dumps({"passed": False, "prelaunch_error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
