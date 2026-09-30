"""D107 installed CLI/MCP development case experiment, after committed freeze.

Usage: VENVPYTHON -I -B SCRIPT REPO NEWOUTPUT. No raw-row analysis, models,
human approvals, signatures or field intervention. Every failure is terminal.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import importlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import sysconfig
import traceback
import types
import zipfile

DOSSIER = "experiments/development/indicator_retirement_2026-09-30"
FREEZE = DOSSIER + "/source_freeze.json"
HELPER = "scripts/probe_citibike_fraction_variant.py"
HELPER_SHA = "a86896d0b4669ee82b7f349bfacc37e47f610eabf8fa22ca2e000d9671525d5b"
SOURCE_CASE = "cases/citibike_march2024_fractions"
CASE_FILES = ("organon.json", "manifest.json", "derived_ratios.json", "ratio_contract.json",
              "ratio_claim_rental.json", "ratio_claim_return.json", "source_analysis.py", "published_report.json")
D106 = "experiments/development/citibike_raw_count_audit_2026-09-30/execution.json"
D106_SHA = "8a11ffe7fd4c6bdcd0a56b5d34e5244cca4507c42a121e6e0d927fc2b1eed43b"
REPORT_SHA = "352ef988b91813912d15c465ba1e597c76eedc1461c33b29afc928c9f88c7ee1"
ACTOR = "agent:D107-technical-lifecycle"
REASON = "Retire the rejected unused composite indicator with two version-pinned descriptive replacements; no human approval or semantic equivalence certification."
REPLACEMENTS = {"i_rental_fraction": 1, "i_return_fraction": 1}
PHASES = ("frame", "critique", "study", "observe", "explain", "compare", "specify", "build", "validate")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode()


def new_file(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def regular(path):
    require(stat.S_ISREG(path.lstat().st_mode), "not a regular file: " + str(path))
    return path.read_bytes()


def expected_pin(row):
    return {key: row[key] for key in ("bytes", "sha256")}


def git(repo, *args):
    return subprocess.check_output(["git", "--no-optional-locks", *args], cwd=repo,
                                   env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})


def committed_freeze(repo):
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    raw = git(repo, "show", "HEAD:" + FREEZE)
    require(regular(repo / FREEZE) == raw, "working freeze differs from committed HEAD bytes")
    freeze = json.loads(raw)
    require(isinstance(freeze["files"], dict), "freeze files must be a mapping")
    return freeze, raw, head


def frozen_inputs(repo, freeze):
    result = {}
    for name, expected in freeze["files"].items():
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts, "noncanonical freeze path")
        path = repo / relative
        require(path.resolve(strict=True).is_relative_to(repo), "freeze path escapes repository")
        raw = regular(path)
        require(pin(raw) == expected_pin(expected), "frozen input differs: " + name)
        result[name] = raw
    for name in [HELPER, D106, *[SOURCE_CASE + "/" + n for n in CASE_FILES]]:
        require(name in result, "required source missing from committed freeze: " + name)
    require(pin(result[HELPER])["sha256"] == HELPER_SHA, "D105 capture helper differs")
    require(pin(result[D106])["sha256"] == D106_SHA, "D106 execution receipt differs")
    require(pin(result[SOURCE_CASE + "/published_report.json"])["sha256"] == REPORT_SHA,
            "D106 published report binding differs")
    return result


def verify_installed(repo, freeze, source):
    wheel_row = freeze["wheel"]
    wheel = Path(wheel_row["path"])
    if not wheel.is_absolute():
        wheel = repo / wheel
    wheel_raw = regular(wheel)
    require(pin(wheel_raw) == expected_pin(wheel_row), "frozen wheel differs")
    venv = Path(sys.prefix).resolve(strict=True)
    require(sys.prefix != sys.base_prefix and not venv.is_relative_to(repo), "external installed venv required")
    matches = [(label, item) for label, item in freeze["environments"].items()
               if Path(item["python"]).absolute().parent.parent == venv]
    require(len(matches) == 1, "current interpreter not uniquely registered in freeze")
    label, environment = matches[0]
    require(sys.version.split()[0] == {"311": "3.11.15", "312": "3.12.3"}[label], "Python version differs")
    purelib = Path(sysconfig.get_path("purelib")).resolve(strict=True)
    require(purelib.is_relative_to(venv), "purelib outside registered venv")
    production = freeze["production_modules"]
    production = {name.removeprefix("src/"): row for name, row in production.items()}
    require(len(production) == 24, "freeze must bind exactly 24 production modules")
    modules = {}
    with zipfile.ZipFile(io.BytesIO(wheel_raw)) as archive:
        wheel_names = {name for name in archive.namelist() if name.startswith("specorganon/") and name.endswith(".py")}
        require(wheel_names == set(production), "wheel/freeze module inventory differs")
        actual_names = {str(p.relative_to(repo / "src")) for p in (repo / "src/specorganon").rglob("*.py")}
        require(actual_names == wheel_names, "source module inventory differs")
        installed_names = {str(p.relative_to(purelib)) for p in (purelib / "specorganon").rglob("*.py")}
        require(installed_names == wheel_names, "installed module inventory differs")
        for name in sorted(wheel_names):
            raw = archive.read(name)
            require(pin(raw) == expected_pin(production[name]), "wheel module pin differs: " + name)
            require(regular(repo / "src" / name) == raw, "source module differs: " + name)
            target = purelib / name
            require(target.resolve(strict=True).is_relative_to(purelib) and regular(target) == raw,
                    "installed module differs: " + name)
            module_name = name[:-3].replace("/", ".").removesuffix(".__init__")
            module = importlib.import_module(module_name)
            require(Path(module.__file__).resolve(strict=True) == target.resolve(strict=True), "module imported outside wheel")
            modules[name] = {"path": str(target), **pin(raw)}
    distribution = importlib.metadata.distribution("specorganon")
    entrypoint_values = {e.name: e.value for e in distribution.entry_points if e.group == "console_scripts"}
    require(entrypoint_values == {"organon": "specorganon.cli:main", "organon-mcp": "specorganon.server:main"},
            "console entrypoint metadata differs")
    direct_url = distribution.read_text("direct_url.json")
    require(direct_url is not None, "installed wheel lacks local direct_url provenance")
    from urllib.parse import unquote, urlparse
    direct = json.loads(direct_url)
    parsed = urlparse(direct["url"])
    require(parsed.scheme == "file" and Path(unquote(parsed.path)).resolve(strict=True) == wheel.resolve(strict=True),
            "installed distribution origin is not registered local wheel")
    archive_info = direct.get("archive_info", {})
    hashes = archive_info.get("hashes", {})
    if "sha256" in hashes:
        require(hashes["sha256"] == wheel_row["sha256"], "direct_url wheel hash differs")
    executables = {}
    for name in ("organon", "organon-mcp"):
        row = environment["entrypoints"][name]
        path = Path(row["path"])
        require(path.absolute().parent == venv / "bin" and os.access(path, os.X_OK), "entrypoint location/executable differs")
        require(pin(regular(path)) == expected_pin(row), "entrypoint bytes differ: " + name)
        executables[name] = {"path": str(path), **expected_pin(row)}
    inventories = {}
    for key in ("inventory", "installed_inventory"):
        if key not in environment:
            continue
        row = environment[key]
        path = Path(row["path"])
        if not path.is_absolute():
            path = repo / path
        raw = regular(path)
        require(pin(raw) == expected_pin(row), "environment inventory pin differs")
        inventory = json.loads(raw)
        require(Path(inventory["venv"]).resolve(strict=True) == venv, "inventory belongs to another venv")
        for name, file_pin in inventory["files"].items():
            target = venv / name
            require(not Path(name).is_absolute() and ".." not in Path(name).parts
                    and target.resolve(strict=True).is_relative_to(venv), "inventory path outside venv")
            require(pin(regular(target)) == expected_pin(file_pin), "environment package file differs: " + name)
        inventories[key] = {"path": str(path), **pin(raw), "verified_files": len(inventory["files"])}
    # Verify modules already loaded by the SDK and by the compiled capture helper.
    for name, module in tuple(sys.modules.items()):
        if name == "specorganon" or name.startswith("specorganon."):
            require(Path(module.__file__).resolve(strict=True).is_relative_to(purelib / "specorganon"), "loaded module origin escaped installed package")
    return {"label": label, "python": sys.version.split()[0], "venv": str(venv), "purelib": str(purelib),
            "wheel": {"path": str(wheel), **pin(wheel_raw)}, "modules": modules,
            "executables": executables, "inventories": inventories, "direct_url": direct}


def load_capture_helper(source, repo):
    module = types.ModuleType("_d107_verified_captures")
    module.__file__ = str(repo / HELPER)
    sys.modules[module.__name__] = module
    exec(compile(source[HELPER], str(repo / HELPER), "exec"), module.__dict__)
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


def prepare(output, source):
    baseline = json.loads(source[SOURCE_CASE + "/organon.json"])
    require(len(baseline["events"]) == 52 and baseline["events"][-1]["kind"] == "item_review",
            "source must be original 52-event case")
    require(baseline["events"][-1]["payload"] == {"id": "i_rows", "version": 3, "verdict": "reject",
             "reason": "Technical rejection of legacy compound indicator; no normative decision or human approval"}, "source review differs")
    d106 = json.loads(source[D106])
    require(d106["exit_code"] == 0 and d106["row_analysis_executed"] is True
            and d106["subset_membership_verified_from_rows"] is True and d106["full_report_equal"] is True
            and d106["source_truth_authenticated"] is False, "D106 documentary scope differs")
    require(d106["executed_analysis_source_pin"] == pin(source[SOURCE_CASE + "/source_analysis.py"]),
            "archived analyzer differs from D106 executed bytes")
    items = {event["payload"]["id"]: copy.deepcopy(event["payload"])
             for event in baseline["events"] if event["kind"] == "item_put"}
    versions = {key: item["version"] for key, item in items.items()}
    steps = []

    def put(item_id, kind, text, refs, data):
        require(len(refs) == len(set(refs)), "duplicate prospective refs")
        expected = versions.get(item_id, 0)
        steps.append({"op": "put", "id": item_id, "kind": kind, "text": text, "refs": refs,
                      "data": data, "expected_version": expected,
                      "expected_deps": {ref: versions[ref] for ref in refs}})
        versions[item_id] = expected + 1

    for item_id, archive, raw, refs, locator in [
        ("e_D106_execution", "D106_execution.json", source[D106], ["pr_reanalysis", "e_archive"], "D106 execution.json: exit_code/full_report_equal/subset_membership_verified_from_rows"),
        ("e_D106_analyzer", "source_analysis.py", source[SOURCE_CASE + "/source_analysis.py"], ["pr_reanalysis", "e_D106_execution"], "Exact archived original analyzer bytes identified by D106 executed_analysis_source_pin"),
        ("e_D106_report", "published_report.json", source[SOURCE_CASE + "/published_report.json"], ["pr_reanalysis", "e_D106_execution", "e_D106_analyzer"], "Full published JSON object reproduced by D106, not a newly collected measurement"),
    ]:
        data = {"origin": "derived", "source": archive, "date": "2026-09-30", "locator": locator,
                "archive": archive, "source_sha256": pin(raw)["sha256"],
                "classification": "exposed_development_documentary_reproduction",
                "subset_membership_verified_from_rows": True,
                "scope": "D106 reproduction of this pinned archived March2024 file only",
                "source_truth_authenticated": False, "field_impact_assessed": False}
        require(not ({"metric", "metric_key", "value", "unit"} & set(data)), "documentary evidence must not fabricate a scalar")
        put(item_id, "evidence", "Documentary link to " + locator + "; local reproduction does not establish physical source truth, efficacy or human approval.", refs, data)
    put("inf_D106_reproduction", "inference",
        "D106 reproduced the complete archived report using the original pinned analyzer and pinned raw file. Its eligible mask and numerator membership were checked for that archive; irregular snapshots, exclusions and gaps still prohibit station-minute, lived-access or intervention-effect claims.",
        ["e_D106_report", "pr_reanalysis", "inf_scope", "e_eligible", "e_rental", "e_return", "e_excluded", "e_gaps"],
        {"classification": "exposed_documentary_inference", "subset_membership_verified_from_rows": True,
         "scope": "this archived file and D106 execution only", "source_truth_authenticated": False,
         "independent_implementation": False, "field_impact_assessed": False})
    for item_id in ("s_rows_pair", "o_rows_report", "cmp_reporting", "d_reporting", "req_row_report"):
        old = items[item_id]
        refs = list(old["deps"])
        data = copy.deepcopy(old["data"])
        if item_id == "s_rows_pair":
            refs += ["inf_scope", "inf_D106_reproduction", "e_D106_report"]
            data.update(documentary_reproduction="D106", historical_source_flags_unchanged=True,
                        mask_verification_scope="D106 pinned archived file; not physical source truth")
        put(item_id, old["kind"], old["text"] + " Documentary D106 reproduction is now traced through the pair; human decision and field claims remain pending.", refs, data)
    require(len(steps) == 9, "exactly nine guarded puts required")
    manifest = {"schema": 1, "steps": steps}
    prepared = output / "prepared"
    prepared.mkdir()
    cases = {}
    for transport in ("cli", "mcp"):
        case = prepared / (transport + "_case")
        case.mkdir()
        for name in CASE_FILES:
            new_file(case / name, source[SOURCE_CASE + "/" + name])
        new_file(case / "D106_execution.json", source[D106])
        require(json.loads((case / "organon.json").read_bytes()) == baseline, "source case copy differs")
        cases[transport] = case
    new_file(prepared / "manifest.json", json_bytes(manifest))
    return baseline, manifest, cases


def retire_arguments(case, version=3, review=52):
    return {"path": str(case), "id": "i_rows", "replacements": REPLACEMENTS,
            "reason": REASON, "actor": ACTOR, "expected_version": version, "expected_review_seq": review}


def retire_argv(case, version=3, review=52):
    return ["retire-indicator", str(case), "i_rows", "--replacements", json_bytes(REPLACEMENTS).decode(),
            "--expected-version", str(version), "--expected-review-seq", str(review),
            "--reason", REASON, "--actor", ACTOR]


async def reject(captures, client, case, label, version=3, review=52):
    before = regular(case / "organon.json")
    result = captures.process([captures.cli, *retire_argv(case, version, review)], label + "-cli")
    require(result.returncode != 0 and not result.stdout and bool(result.stderr), "CLI retirement guard unexpectedly accepted")
    response = await asyncio.wait_for(client.call_tool("retire_indicator", retire_arguments(case, version, review)), timeout=90)
    raw = response.model_dump(mode="json", by_alias=True)
    captures.append({"transport": "mcp", "operation": "retire_indicator", "label": label,
                     "arguments": retire_arguments(case, version, review), "response": raw,
                     "response_scope": "raw_sdk_model_not_wire_framing"})
    text = " ".join(getattr(part, "text", "") for part in response.content)
    require(response.is_error is True and bool(text), "MCP retirement guard unexpectedly accepted")
    require(regular(case / "organon.json") == before, "rejected retirement wrote event")
    return {"label": label, "cli_exit": result.returncode, "cli_stderr": result.stderr.decode(),
            "mcp_response": raw, "ledger_unchanged": True, "ledger_pin": pin(before)}


async def next_pair(captures, client, case):
    before = regular(case / "organon.json")
    cli = captures.command("next-task", str(case))
    mcp = await captures.tool(client, "next_task", {"path": str(case)})
    require(cli == mcp and regular(case / "organon.json") == before, "next_task parity/read-only failed")
    return cli


def assert_retirement(state, effective):
    item = state["items"]["i_rows"]
    require(item["retired"] is effective, "unexpected retired flag")
    require(item["retirement_status"] == ("effective" if effective else "invalidated"), "unexpected retirement status")
    require(bool(item["retirement_issues"]) is (not effective), "unexpected retirement issues")
    history = state["indicator_retirement_history"]
    require(len(history) == 1 and history[0]["seq"] == 62 and history[0]["effective"] is effective,
            "retirement history was lost or has unexpected effectiveness")
    require(all(history[0][key] == value for key, value in {
        "id": "i_rows", "version": 3, "review_seq": 52,
        "replacements": REPLACEMENTS, "reason": REASON, "actor": ACTOR,
    }.items()), "retirement declaration history changed")


def put_argv(case, item, item_id=None, refs=None):
    refs = list(item["deps"]) if refs is None else refs
    data = item["data"]
    argv = ["put", str(case), item_id or item["id"], "--kind", item["kind"], "--text", item["text"],
            "--data", json_bytes(data).decode(), "--actor", ACTOR,
            "--expected-version", str(item["version"] if item_id is None else 0),
            "--expected-deps", json_bytes(item["deps"]).decode()]
    for ref in refs:
        argv.extend(["--ref", ref])
    return argv


async def execute(helper, captures, installed, output, source, report):
    from mcp.client import Client
    from mcp.client.stdio import StdioServerParameters

    baseline, manifest, cases = prepare(output, source)
    report["manifest"] = manifest
    report["source_prefix_events"] = 52
    manifest_path = output / "prepared/manifest.json"
    cli_run = captures.command("run", str(cases["cli"]), "--manifest", str(manifest_path), "--actor", ACTOR)
    require((cli_run["applied"], cli_run["skipped"], cli_run["total_steps"]) == (9, 0, 9), "CLI did not apply exactly nine puts")
    params = StdioServerParameters(command=installed["executables"]["organon-mcp"]["path"], cwd=str(output), env=captures.env)
    async with Client(params, mode="legacy") as client:
        discovery = await asyncio.wait_for(client.list_tools(), timeout=90)
        raw_discovery = discovery.model_dump(mode="json", by_alias=True)
        new_file(output / "mcp_discovery.json", json_bytes(raw_discovery))
        report["mcp_tools"] = sorted(tool.name for tool in discovery.tools)
        require(len(report["mcp_tools"]) == len(set(report["mcp_tools"])) == 23
                and "retire_indicator" in report["mcp_tools"], "expected 23 unprefixed tools including retire_indicator")
        mcp_run = await captures.tool(client, "run", {"path": str(cases["mcp"]), "manifest": manifest, "actor": ACTOR})
        require((mcp_run["applied"], mcp_run["skipped"], mcp_run["total_steps"]) == (9, 0, 9), "MCP did not apply exactly nine puts")
        report["manifest_runs"] = {"cli": cli_run, "mcp": mcp_run}
        report["manifest_replays"] = {}
        for transport, case in cases.items():
            before = regular(case / "organon.json")
            replay = (captures.command("run", str(case), "--manifest", str(manifest_path), "--actor", ACTOR)
                      if transport == "cli" else await captures.tool(client, "run", {"path": str(case), "manifest": manifest, "actor": ACTOR}))
            require(replay["applied"] == 0 and replay["skipped"] == 9 and regular(case / "organon.json") == before,
                    "manifest replay changed case")
            report["manifest_replays"][transport] = replay
        report["retirement_guard_rejections"] = []
        for transport, case in cases.items():
            ledger = json.loads(regular(case / "organon.json"))
            require(len(ledger["events"]) == 61 and ledger["events"][:52] == baseline["events"], "pre-retirement prefix differs")
            for label, version, review in [("wrong-source-version", 2, 52), ("wrong-review-sequence", 3, 51)]:
                report["retirement_guard_rejections"].append(await reject(captures, client, case, transport + "-" + label, version, review))
            if transport == "cli":
                captures.command(*retire_argv(case))
            else:
                await captures.tool(client, "retire_indicator", retire_arguments(case))
            report["retirement_guard_rejections"].append(await reject(captures, client, case, transport + "-duplicate"))
        report["positive"] = {}
        positive_inventories = {transport: inventory(case) for transport, case in cases.items()}
        semantics = []
        for transport, case in cases.items():
            ledger = json.loads(regular(case / "organon.json"))
            require(ledger["project"] == baseline["project"] and len(ledger["events"]) == 62
                    and ledger["events"][:52] == baseline["events"], "positive case lost prefix/project")
            require(all(e["kind"] == "item_put" for e in ledger["events"][52:61])
                    and ledger["events"][-1]["kind"] == "indicator_retire"
                    and ledger["events"][-1]["payload"] == {"id": "i_rows", "version": 3,
                       "replacements": REPLACEMENTS, "review_seq": 52, "reason": REASON}, "unexpected derivative events")
            semantics.append({"project": ledger["project"], "events": [{k: e[k] for k in ("kind", "actor", "payload")} for e in ledger["events"]]})
            state = await helper._pair(captures, client, case, "status")
            helper._pending(state)
            assert_retirement(state, True)
            original = {e["payload"]["id"]: e["payload"] for e in baseline["events"] if e["kind"] == "item_put"}["i_rows"]
            require(all(state["items"]["i_rows"][key] == original[key] for key in ("version", "kind", "text", "data", "deps")), "legacy indicator changed")
            require(state["items"]["i_rows"]["issues"] == ["latest item review rejected this version"], "legacy rejection hidden")
            for item_id in [*REPLACEMENTS, "s_rows_pair", "req_row_report", "e_D106_execution", "e_D106_analyzer", "e_D106_report", "inf_D106_reproduction"]:
                item = state["items"][item_id]
                require(not item["stale"] and not item["contested"] and not item["issues"], "positive item invalid: " + item_id)
            pair = state["items"]["s_rows_pair"]
            require(pair["version"] == 2 and {"inf_scope", "inf_D106_reproduction", "e_D106_report"} <= set(pair["deps"]), "pair inference/evidence missing")
            gates = {phase: await helper._pair(captures, client, case, "gate", phase=phase) for phase in PHASES}
            for phase in ("study", "explain"):
                require(len(gates[phase]["blockers"]) == 1 and "previous phase" in gates[phase]["blockers"][0], "targeted repair retains extra blocker in " + phase)
            require(gates["specify"]["blockers"] and not gates["specify"]["ready"], "pending specification unexpectedly ready")
            traces = {key: await helper._pair(captures, client, case, "trace", id=key) for key in ("s_rows_pair", "req_row_report", "i_rows")}
            report["positive"][transport] = {"state": state, "gates": gates, "traces": traces,
                "next_task": await next_pair(captures, client, case), "ledger_pin": pin(regular(case / "organon.json")),
                "source_prefix_preserved": True, "events": 62, "chain_readable": True}
        require(semantics[0] == semantics[1], "CLI/MCP positive event payloads differ beyond timestamps/hash chain")
        report["cli_mcp_payloads_equal_ignoring_timestamps_and_hash_chain"] = True
        controls = output / "controls"
        controls.mkdir()
        report["controls"] = {}
        for label in ("replacement_revision", "replacement_rejection", "replacement_challenge", "new_consumer", "changed_archive", "missing_archive"):
            case = controls / label
            shutil.copytree(cases["cli"], case)
            before = await helper._pair(captures, client, case, "status")
            positive_ledger = regular(case / "organon.json")
            original_archive = regular(case / "derived_ratios.json")
            if label == "replacement_revision":
                captures.command(*put_argv(case, before["items"]["i_rental_fraction"]))
            elif label == "replacement_rejection":
                captures.command("review", str(case), "i_rental_fraction", "--verdict", "reject", "--reason", "D107 controlled negative replacement review", "--actor", "agent:D107-independent-control-review")
            elif label == "replacement_challenge":
                captures.command("challenge", str(case), "i_rental_fraction", "i_return_fraction", "--reason", "D107 synthetic controlled contradiction, not a claim about physical data", "--actor", ACTOR)
            elif label == "new_consumer":
                captures.command("put", str(case), "inf_legacy_consumer", "--kind", "inference", "--text", "D107 controlled new consumer of the old rejected indicator; no approval", "--ref", "i_rows", "--data", "{}", "--actor", ACTOR, "--expected-version", "0", "--expected-deps", '{"i_rows":3}')
            elif label == "changed_archive":
                (case / "derived_ratios.json").write_bytes(original_archive + b"\n")
            elif label == "missing_archive":
                (case / "derived_ratios.json").unlink()
            checkpoint = regular(case / "organon.json")
            state = await helper._pair(captures, client, case, "status")
            helper._pending(state)
            assert_retirement(state, False)
            trace = await helper._pair(captures, client, case, "trace", id="i_rows")
            dependent_trace = await helper._pair(captures, client, case, "trace", id="req_row_report")
            require(regular(case / "organon.json") == checkpoint, "control reads wrote ledger")
            if label == "replacement_revision":
                require(state["items"]["i_rental_fraction"]["version"] == 2
                        and state["items"]["i_rental_fraction"]["data"] == before["items"]["i_rental_fraction"]["data"], "revision changed measured data")
                require(all(state["items"][key]["stale"] for key in ("s_rows_pair", "o_rows_report", "cmp_reporting", "d_reporting", "req_row_report")), "replacement revision did not stale downstream")
            elif label == "replacement_rejection":
                require("latest item review rejected this version" in state["items"]["i_rental_fraction"]["issues"], "negative replacement review not detected")
            elif label == "replacement_challenge":
                require(all(state["items"][key]["contested"] for key in REPLACEMENTS) and state["open_challenges"], "replacement contradiction not detected")
            elif label == "new_consumer":
                require(state["items"]["inf_legacy_consumer"]["deps"] == {"i_rows": 3}
                        and any("current consumers" in x for x in state["items"]["i_rows"]["retirement_issues"]), "new consumer did not invalidate retirement")
            else:
                require(checkpoint == positive_ledger and all(state["items"][key]["issues"] for key in [*REPLACEMENTS, "s_rows_pair", "req_row_report"]), "archive error not detected without ledger mutation")
                (case / "derived_ratios.json").write_bytes(original_archive)
                restored = await helper._pair(captures, client, case, "status")
                require(restored == before and regular(case / "organon.json") == positive_ledger,
                        "exact archive restoration did not recover original state")
                assert_retirement(restored, True)
            report["controls"][label] = {"state": state, "trace": trace, "dependent_trace": dependent_trace,
                "read_operations_ledger_unchanged": True, "history_preserved": True,
                "mutation_events": len(json.loads(checkpoint)["events"]) - 62,
                "byte_exact_restore_effective": label in {"changed_archive", "missing_archive"}}
        for transport, case in cases.items():
            require(inventory(case) == positive_inventories[transport], "control mutated positive case")
        report["positive_cases_unchanged_after_controls"] = True


def probe(repo, output):
    repo = repo.resolve(strict=True)
    freeze, freeze_raw, head = committed_freeze(repo)
    source = frozen_inputs(repo, freeze)
    installed = verify_installed(repo, freeze, source)
    require(not output.exists() and not output.is_symlink(), "output must be exclusive and new")
    output = output.parent.resolve(strict=True) / output.name
    require(not output.is_relative_to(repo), "output must be external")
    output.mkdir(mode=0o700)
    env = {"PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1"}
    os.environ.clear()
    os.environ.update(env)
    sys.dont_write_bytecode = True
    helper = load_capture_helper(source, repo)
    report = {"schema": 1, "study_id": "D107", "classification": "exposed_installed_development_indicator_retirement", "passed": False,
              "git_head": head, "freeze_pin": pin(freeze_raw), "inputs_before": {k: pin(v) for k, v in source.items()},
              "installed_before": installed, "executed_probe_pin": pin(regular(Path(__file__))),
              "started_at_utc": helper._now(), "Q": None, "new_model_generations": 0,
              "raw_row_analysis_executed": False, "field_operations": 0, "human_approvals": 0,
              "counts_toward_required_24_runs": False, "physical_source_truth_authenticated": False,
              "independent_custody_authenticated": False, "no_automatic_retry": True}
    captures = None
    try:
        new_file(output / "source_freeze.executed.json", freeze_raw)
        new_file(output / "probe.executed.py", regular(Path(__file__)))
        captures = helper.Captures(output, env, installed["executables"]["organon"]["path"])
        asyncio.run(execute(helper, captures, installed, output, source, report))
        report["passed"] = True
    except Exception as exc:
        report.update(error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
    finally:
        if captures is not None:
            captures.stream.close()
            report["captured_calls"] = len(captures.records)
        # Failed experiments also retain preservation checks, without repairing
        # the candidate or replacing the original terminal failure.
        try:
            after = frozen_inputs(repo, freeze)
            report["inputs_after"] = {k: pin(v) for k, v in after.items()}
            require(source == after, "frozen repository bytes changed")
            report["installed_after"] = verify_installed(repo, freeze, after)
            require(installed == report["installed_after"], "installed origins/files changed")
            require(regular(repo / FREEZE) == freeze_raw and git(repo, "show", "HEAD:" + FREEZE) == freeze_raw,
                    "committed freeze changed during experiment")
            require(pin(regular(Path(__file__))) == report["executed_probe_pin"], "executed probe changed")
            report["all_source_wheel_installed_and_entrypoint_pins_verified_before_after"] = True
        except Exception as exc:
            report["passed"] = False
            report["preservation_error"] = f"{type(exc).__name__}: {exc}"
            report["preservation_traceback"] = traceback.format_exc()
        report["finished_at_utc"] = helper._now()
        report["retained_files"] = inventory(output)
        new_file(output / "report.json", json_bytes(report))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = probe(args.repo, args.output)
        print(json.dumps({"passed": result["passed"], "report": str(args.output / "report.json"), "error": result.get("error")}))
        return 0 if result["passed"] else 2
    except Exception as exc:
        print(json.dumps({"passed": False, "prelaunch_error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
