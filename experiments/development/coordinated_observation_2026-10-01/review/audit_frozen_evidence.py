"""Independent finite D121 evidence audit; never execute native runtimes/tools.

Archives are read in place, never extracted. PURE reconciliation checks declared
bytes; recorded native CLI guards are not an authenticated custody statement.
Only --output, if supplied, creates a NEW report inside this review directory.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
from types import SimpleNamespace

REVIEW = Path(__file__).resolve().parent
DOSSIER = REVIEW.parent
ROOT = DOSSIER.parents[2]
FREEZE_COMMIT = "892d6a8731252adfadd499793dc7d192c5f09c47"
DOCS = {"docs/estado.md", "docs/decisiones.md", "docs/activacion_validacion.md", "docs/validacion_actual.md"}
sys.path.insert(0, str(ROOT / "scripts"))
import coordinated_observation_journal as journal  # noqa: E402
import measure_coordinated_runtime as measurement  # noqa: E402
import observed_coordinated_runtime as observer  # noqa: E402
from managed_wave_ledger import WaveLedger  # noqa: E402


def require(condition, label):
    if not condition:
        raise ValueError(label)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def same(left, right):
    return journal._canonical(left) == journal._canonical(right)


def read_json(path):
    return json.loads(path.read_bytes())


def pin(path):
    raw = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(raw), "sha256": sha(raw)}


def git_bytes(commit, path):
    return subprocess.check_output(["git", "show", commit + ":" + path], cwd=ROOT)


def inventory(root):
    """nofollow metadata checks before reading regular bytes; never open FIFOs."""
    require(stat.S_ISDIR(root.lstat().st_mode), "inventory root is not a directory")
    entries, total = [], 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(directory) / name
            info = path.lstat()
            row = {"path": path.relative_to(root).as_posix(), "mode": stat.S_IMODE(info.st_mode)}
            if stat.S_ISDIR(info.st_mode):
                row["kind"] = "directory"
            else:
                require(stat.S_ISREG(info.st_mode), "special entry in regular-only inventory")
                require(info.st_size <= 64 * 1024 * 1024, "inventory file exceeds finite bound")
                raw = path.read_bytes()
                row.update(kind="regular", bytes=len(raw), sha256=sha(raw))
                total += len(raw)
            entries.append(row)
    return {"root": str(root), "entries": sorted(entries, key=lambda row: PurePosixPath(row["path"]).parts), "regular_bytes": total}


def source_audit():
    freeze_path = DOSSIER / "source_freeze.json"
    frozen = read_json(freeze_path)
    rows = frozen["records"]
    require(len(rows) == 104 == len({row["path"] for row in rows}), "freeze inventory count or uniqueness")
    for row in rows:
        path = ROOT / row["path"]
        require(stat.S_ISREG(path.lstat().st_mode), "frozen source is not regular")
        require(pin(path) == row, "frozen source live bytes disagree")
        raw = git_bytes(FREEZE_COMMIT, row["path"])
        require((len(raw), sha(raw)) == (row["bytes"], row["sha256"]), "freeze commit source bytes disagree")
    require(freeze_path.read_bytes() == git_bytes(FREEZE_COMMIT, str(freeze_path.relative_to(ROOT))), "freeze self commit differs")
    for row in frozen["external_tools"]:
        raw = Path(row["path"]).read_bytes()
        require((len(raw), sha(raw)) == (row["bytes"], row["sha256"]), "external tool changed")
    return rows + [pin(freeze_path)]


def baseline_audit(before):
    result = {}
    for name, commit, receipt_sha in (
        ("coordinated_runtime_2026-10-01", "c64169c15c5cbe6dd35c5fc4c25704fc042332a7", "cd41baa29e59e1e75d7ed9e46412e0885b13c0b02e72629ea1af1dc55ab28b07"),
        ("coordinated_measurement_2026-10-01", "f05bb9ca00914ac5b17b2e05c95d726522bb0a2b", "87ed0c79a38e35bb6f0788b95ef1ef81029062ba68ff67e2827960e923313cdd"),
    ):
        receipt_path = ROOT / "experiments/development" / name / "receipt.json"
        raw = receipt_path.read_bytes()
        require(sha(raw) == receipt_sha, "prior receipt changed")
        rows = json.loads(raw)["records"]
        require(len(rows) == len({row["path"] for row in rows}), "prior pins duplicated")
        for row in rows:
            if row["path"] in DOCS:
                data = git_bytes(commit, row["path"])
            else:
                path = ROOT / row["path"]
                info = path.lstat()
                require(stat.S_ISREG(info.st_mode), "prior live pin not regular")
                require(("100755" if info.st_mode & 0o111 else "100644") == row["mode"], "prior pin mode differs")
                data = path.read_bytes()
            require((len(data), sha(data)) == (row["bytes"], row["sha256"]), "prior pin bytes differ")
        require(before[name]["receipt_sha256"] == receipt_sha and before[name]["pins"] == len(rows) + 1,
                "captured baseline receipt count differs")
        result[name] = {"pins_plus_self": len(rows) + 1, "receipt_sha256": receipt_sha,
                        "historical_doc_blobs_verified": len(DOCS)}
    require(len(before["original_runtimes"]) == 12, "original runtime inventory count")
    for row in before["original_runtimes"]:
        require(same(row, inventory(Path(row["root"]))), "original runtime inventory differs live")
    result["original_runtimes_verified"] = 12
    return result


def captured_commands(directory, report):
    for index, row in enumerate(report["commands"], 1):
        require(row["exit_code"] == 0 and row["timed_out"] is False, "captured command failed or timed out")
        for kind in ("stdout", "stderr"):
            raw = (directory / (str(index) + "." + kind)).read_bytes()
            require((len(raw), sha(raw)) == (row[kind + "_bytes"], row[kind + "_sha256"]), "raw command stream pin differs")
        require(row["capture_duration_seconds"] >= 0 and row["capture_ended_wall_ns"] >= row["capture_started_wall_ns"],
                "capture timing is invalid")
        require(row["time_scope"] == "measurement_command_only_not_original_run_W", "capture mislabeled as native W")


def attempts_audit():
    output = []
    for name in ("wrapper01", "wrapper02", "wrapper03"):
        directory = DOSSIER / "attempts" / name
        report = read_json(directory / "report.json")
        for index, row in enumerate(report["sources"]):
            before, after = (directory / f"source-{index}.before").read_bytes(), (directory / f"source-{index}.after").read_bytes()
            require(before == after and sha(before) == row["sha256"], "early wrapper source provenance differs")
        streams = [(directory / f"{index}.stdout").read_bytes() for index in range(len(report["commands"]))]
        codes = [row["exit_code"] for row in report["commands"]]
        require(codes == ([1, 1] if name == "wrapper01" else [0, 0]), "wrapper early exit history differs")
        if name == "wrapper01":
            require(b"6 failed, 5 passed, 9 errors" in streams[0] and b"count_input_payload_sha256" in streams[0],
                    "first wrapper error trace not preserved")
        else:
            require((b"20 passed" if name == "wrapper02" else b"23 passed") in streams[0], "early wrapper pass count differs")
        output.append({"attempt": name, "exit_codes": codes, "source_bytes_before_after_verified": True})
    for name in ("journal01", "journal02", "journal03"):
        directory = DOSSIER / "attempts" / name
        report = read_json(directory / "report.json")
        require(report["sources_before"] == report["sources_after"], "early journal source hashes differ")
        for path, digest in report["sources_before"].items():
            before, after = (directory / "sources_before" / path).read_bytes(), (directory / "sources_after" / path).read_bytes()
            require(before == after and sha(before) == digest, "early journal source bytes differ")
        codes = [row["exit_code"] for row in report["commands"]]
        require(codes == ([0, 0, 1, 0, 0] if name == "journal01" else [0] * 5), "journal early exit history differs")
        expected_count = b"65 passed" if name == "journal03" else b"55 passed"
        if name == "journal02":
            expected_count = b"61 passed"
        for index in (1, 2):
            require(expected_count in (directory / f"{index:02d}.stdout").read_bytes(), "journal early pass count differs")
        output.append({"attempt": name, "exit_codes": codes, "source_bytes_before_after_verified": True})
    directory = DOSSIER / "attempts/helperlint01"
    require(read_json(directory / "report.json")["exit_code"] == 1, "helper lint failure erased")
    require(b"F401" in (directory / "stdout.txt").read_bytes(), "helper lint raw F401 missing")
    compile((directory / "seal_evidence.before.py.txt").read_bytes(), "preserved_pre_lint_sealer", "exec")
    output.append({"attempt": "helperlint01", "exit_codes": [1], "raw_F401_preserved": True})
    return output


def gates_audit():
    sources = source_audit()
    gates, baseline = [], None
    for interpreter in ("311", "312"):
        directory = DOSSIER / "checks" / ("final" + interpreter)
        report = read_json(directory / "report.json")
        require(report["head"] == report["head_before"] == FREEZE_COMMIT and report["interpreter"] == interpreter,
                "gate freeze or interpreter differs")
        require(report["integration"] is False and len(report["commands"]) == 4, "gate command scope differs")
        require(all(report[key] is True for key in ("all_exit_zero", "sources_unchanged", "baseline_unchanged")), "gate declared failure")
        require(report["formal_cells_executed"] == report["paid_model_requests"] == 0 and report["external_spending_authorized"] is False,
                "gate formal/spending scope differs")
        require(same(read_json(directory / "sources_before.json"), sources)
                and same(read_json(directory / "sources_after.json"), sources), "gate captured source records differ")
        before, after = read_json(directory / "baseline_before.json"), read_json(directory / "baseline_after.json")
        require(same(before, after), "gate baseline before/after differs")
        if baseline is None:
            baseline = baseline_audit(before)
        else:
            require(same(before, read_json(DOSSIER / "checks/final311/baseline_before.json")), "cross-interpreter baseline differs")
        captured_commands(directory, report)
        command = report["commands"][0]["argv"]
        require(command[0] == f"/tmp/specorganon-D107-deps-re8v1j45/venv-{interpreter}/bin/python", "gate interpreter argv differs")
        require(command[1:] == ["-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                              "tests/test_coordinated_observation_journal.py", "tests/test_observed_coordinated_runtime.py"],
                "gate test scope differs")
        require(re.search(rb"\b88 passed in [0-9.]+s", (directory / "1.stdout").read_bytes()) is not None, "raw 88-pass result missing")
        require((directory / "2.stdout").read_bytes() == b"All checks passed!\n" and (directory / "3.stdout").read_bytes() == b"syntax OK\n",
                "raw lint/syntax result missing")
        require(all((directory / f"{index}.stderr").read_bytes() == b"" for index in range(1, 5)), "unexpected raw gate stderr")
        gates.append({"interpreter": interpreter, "tests_passed": 88, "journal_test_cases": 65,
                      "wrapper_test_cases": 23, "commands_verified": 4, "sources_plus_freeze_verified": len(sources),
                      "report_pin": pin(directory / "report.json")})
    require(sources == source_audit(), "sources changed during independent audit")
    return {"phase": "frozen_sources_and_final_gates_only", "open_material_findings": [],
            "source_freeze_commit": FREEZE_COMMIT, "source_freeze_pin": sources[-1], "gates": gates,
            "baseline": baseline, "early_attempts": attempts_audit(), "formal_cells_executed": 0,
            "limits": ["No native runtime, pytest suite, model request or tool executed by this auditor",
                       "Integration/archive/final evidence verdict awaits separate finite followup",
                       "C1 technical; C2-C5 and formal acceptance remain unproved"]}


def wanted(name):
    if name.startswith("cli-") or name in ("cli_calls.json", "integration_result.json", "bundle/schedule.json"):
        return True
    parts = PurePosixPath(name).parts
    if len(parts) > 2 and parts[1] == "observation":
        return True
    if name.endswith(("/integration_result.json", "/http_trace.json")):
        return True
    if len(parts) > 2 and parts[1] == "run":
        relative = "/".join(parts[2:])
        return relative in measurement.DOCUMENTS.values() or parts[2] in (*measurement.JOURNALS, "broker", "control")
    return False


def archive_audit(directory):
    declared = read_json(directory / "runtime_inventory.json")
    rows = {row["path"]: row for row in declared["entries"]}
    require(len(rows) == len(declared["entries"]), "archive inventory duplicated")
    retained, seen, regular_bytes = {}, set(), 0
    with tarfile.open(directory / "runtimes.tar.gz", "r:gz") as archive:
        for member in archive:
            name = member.name
            path = PurePosixPath(name)
            require(not path.is_absolute() and ".." not in path.parts and str(path) == name, "unsafe archive member")
            require(name in rows and name not in seen, "archive member extra or duplicated")
            row = rows[name]
            seen.add(name)
            require(member.mode == row["mode"], "archive mode differs")
            if row["kind"] == "directory":
                require(member.isdir(), "archive directory header differs")
                continue
            require(row["kind"] == "regular" and member.isfile() and member.size == row["bytes"], "archive regular header differs")
            digest, total, chunks = hashlib.sha256(), 0, []
            stream = archive.extractfile(member)
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                total += len(chunk)
                if wanted(name):
                    chunks.append(chunk)
            require(total == row["bytes"] and digest.hexdigest() == row["sha256"], "archive bytes differ")
            regular_bytes += total
            if wanted(name):
                retained[name] = b"".join(chunks)
    require(seen == set(rows) and regular_bytes == declared["regular_bytes"], "archive coverage differs")
    require(same(declared, inventory(Path(declared["root"]))), "archive origins changed")
    return retained, rows, {"entries": len(rows), "regular_bytes": regular_bytes,
                            "archive_pin": pin(directory / "runtimes.tar.gz"), "origin_inventory_equal": True}


def ledger_budget(raw):
    value = measurement._parsed(raw)
    WaveLedger._validate(value)  # Static PURE validation; no constructor or lock.
    requests = value["requests"]
    result = {key: value[key] for key in ("schema", "limit_tokens", "max_requests", "cost_limit_micro_usd",
                                         "model", "effort", "price_profile", "price_profile_sha256", "waves", "requests")}
    result.update(ledger_sha256=sha(raw), request_count=len(requests), wave_count=len(value["waves"]),
                  blocked=any(row["state"] != "settled" for row in requests.values()))
    for state in ("reserved", "inflight", "indeterminate", "settled"):
        result[state + "_tokens"] = sum(row["held_tokens"] for row in requests.values() if row["state"] == state)
        result[state + "_cost_micro_usd"] = sum(row["held_cost_micro_usd"] for row in requests.values() if row["state"] == state)
    result["committed_tokens"] = sum(result[state + "_tokens"] for state in ("reserved", "inflight", "indeterminate", "settled"))
    result["remaining_tokens"] = value["limit_tokens"] - result["committed_tokens"]
    result["committed_cost_micro_usd"] = sum(result[state + "_cost_micro_usd"] for state in ("reserved", "inflight", "indeterminate", "settled"))
    result["remaining_cost_micro_usd"] = value["cost_limit_micro_usd"] - result["committed_cost_micro_usd"]
    return result


def interval_metrics(intervals):
    merged = []
    for begin, end in sorted(intervals):
        require(type(begin) is int and type(end) is int and 0 <= begin <= end, "interval types or order differ")
        if merged and begin <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((begin, end))
    summed, union = sum(end - begin for begin, end in intervals), sum(end - begin for begin, end in merged)
    return {"sum_ns": summed, "union_ns": union, "sum_seconds": summed / 1e9,
            "union_seconds": union / 1e9, "completed_intervals": len(intervals)}


def journal_audit(label, raw, observation):
    binding_raw = raw[label + "/observation/binding.json"]
    binding = journal._binding(json.loads(binding_raw))
    require(binding_raw == journal._canonical(binding), "archived observation binding is not canonical")
    names = sorted(name for name in raw if name.startswith(label + "/observation/events/"))
    require([PurePosixPath(name).name for name in names] == [f"{index:06d}.json" for index in range(1, len(names) + 1)], "archived event inventory differs")
    raws = [raw[name] for name in names]
    events = [json.loads(data) for data in raws]
    require(all(data == journal._canonical(event) for data, event in zip(raws, events)), "archived events not canonical")
    state = journal._replay(binding, events, raws)  # PURE chain/lifecycle/types.
    require(state["state"] == "delivered" and same(observation["binding"], binding)
            and same(observation["events"], events), "CLI observation differs from archived typed journal")
    operations = list(state["operations"].values())
    def intervals(role=None, kind=None):
        return [(op["begin"]["monotonic_ns"], op["end"]["monotonic_ns"]) for op in operations
                if op["end"] is not None and (role is None or op["role"] == role) and (kind is None or op["kind"] == kind)]
    metrics = {"by_kind": {kind: interval_metrics(intervals(kind=kind)) for kind in journal.KINDS},
               "all": interval_metrics(intervals()),
               "by_role": {role: {"by_kind": {kind: interval_metrics(intervals(role, kind)) for kind in journal.KINDS},
                                  "all": interval_metrics(intervals(role))} for role in journal.ROLES},
               "incomplete_operations": sum(op["end"] is None for op in operations),
               "failed_operations": sum(op["end"] is not None and op["end"]["data"]["error"] is not None for op in operations)}
    delivery = state["delivery"]
    elapsed = delivery["monotonic_ns"] - events[0]["monotonic_ns"]
    metrics["outside_operation_union_seconds"] = (elapsed - metrics["all"]["union_ns"]) / 1e9
    require(same(metrics, observation["metrics"]), "CLI interval sums/unions differ from raw event math")
    require(observation["W_local_elapsed_ns"] == elapsed and type(observation["W_local_elapsed_ns"]) is int
            and observation["W_local_elapsed_seconds"] == elapsed / 1e9, "CLI W differs from same boot release/delivery")
    require(observation["wall_delta_seconds"] == (delivery["wall_ns"] - events[0]["wall_ns"]) / 1e9, "CLI wall delta differs")
    require(observation["last_event_sha256"] == sha(raws[-1]) and observation["checkpoint_sha256"] == state["checkpoint_sha256"], "CLI journal checkpoint differs")
    # Reproduce all closed report fields from typed bytes, without consulting a
    # current boot clock or opening any original journal. Math above is separate.
    pure_self = SimpleNamespace(_locked=lambda: contextlib.nullcontext(),
                                _read=lambda: (binding, events, raws, state),
                                _clock_check=lambda _events: None)
    require(same(journal.ObservationJournal.report(pure_self), observation), "CLI journal projection has extra or altered fields")
    return state


def integrations_audit():
    source_audit()
    runs, archives = [], []
    for interpreter in ("311", "312"):
        directory = DOSSIER / "checks" / ("integration" + interpreter)
        gate = read_json(directory / "report.json")
        require(gate["head"] == gate["head_before"] == FREEZE_COMMIT and gate["interpreter"] == interpreter,
                "integration freeze or interpreter differs")
        require(gate["all_exit_zero"] is True and gate["sources_unchanged"] is True and gate["baseline_unchanged"] is True,
                "integration gate failed")
        captured_commands(directory, gate)
        raw, rows, archived = archive_audit(directory)
        archives.append(archived | {"interpreter": interpreter})
        recorded = json.loads(raw["integration_result.json"])
        require(same(recorded, gate["integration_result"]) and recorded["formal_cells_executed"] == 0,
                "archived integration aggregate differs")
        require({row["arm"] for row in recorded["runs"]} == set("ABC") and len(recorded["runs"]) == 3,
                "integration run matrix differs")
        cli = json.loads(raw["cli_calls.json"])
        require(len(cli) == recorded["actual_cli_calls"] and all(row["exit_code"] == 0 for row in cli), "CLI inventory count/exit differs")
        for index, call in enumerate(cli, 1):
            require(call["stdout"] == f"cli-{index:03d}.stdout" and call["stderr"] == f"cli-{index:03d}.stderr",
                    "CLI stream inventory identity differs")
            require(call["argv"][:3] == [f"/tmp/specorganon-D107-deps-re8v1j45/venv-{interpreter}/bin/python", "-I", "-B"], "CLI registered interpreter differs")
            require(raw[call["stderr"]] == b"", "CLI stderr was not empty")
        schedule = json.loads(raw["bundle/schedule.json"])
        for row in recorded["runs"]:
            arm, label = row["arm"], row["arm"] + "-D-E"
            require(row["case_id"] == "D-E" and row["formal_cell_executed"] is False and row["quality_assessed"] is False,
                    "integration row scope differs")
            selected = next(item for item in schedule["runs"] if item["run_id"] == row["run_id"])
            require(selected["arm"] == arm and selected["case_id"] == "D-E" and selected["replica"] == 1,
                    "scheduled integration coordinate differs")
            require(same(row, json.loads(raw[label + "/integration_result.json"])), "per-run result differs aggregate")
            run_dir = str(Path(gate["runtime_destination"]) / label / "run")
            commands = [call for call in cli if "--run-dir" in call["argv"] and call["argv"][call["argv"].index("--run-dir") + 1] == run_dir]
            require(len(commands) >= 4, "per-run CLI lifecycle incomplete")
            require(commands[0]["argv"][3:5] == [str(ROOT / "scripts/coordinated_prototype_runtime.py"), "prepare"], "native prepare command missing")
            require(commands[1]["argv"][3:5] == [str(ROOT / "scripts/observed_coordinated_runtime.py"), "release"], "prospective release command missing")
            require(commands[-1]["argv"][3:5] == [str(ROOT / "scripts/observed_coordinated_runtime.py"), "report"], "final report command missing")
            prepared = json.loads(raw[commands[0]["stdout"]])
            released = json.loads(raw[commands[1]["stdout"]])
            require(prepared["state"] == "prepared" and type(prepared["cursor"]) is int and prepared["cursor"] == 0
                    and prepared["budget"]["request_count"] == prepared["tool_calls_completed"] == 0, "release was not an untouched prepared run")
            require(released["state"] == "released" and released["binding"]["initial_checkpoint_sha256"] == prepared["checkpoint_sha256"], "release initial checkpoint differs")
            checkpoint = prepared["checkpoint_sha256"]
            for index, command in enumerate(commands[1:-1]):
                argv = command["argv"]
                require(argv[argv.index("--expected-checkpoint") + 1] == checkpoint, "CLI checkpoint CAS chain differs")
                require(argv[argv.index("--observation-dir") + 1] == row["observation_dir"], "CLI observation binding directory differs")
                result = json.loads(raw[command["stdout"]])
                if index == 0:
                    continue
                require(argv[3:5] == [str(ROOT / "scripts/observed_coordinated_runtime.py"), "step"], "CLI lifecycle has a non-step command")
                observer.runtime._fixture_endpoint(argv[argv.index("--local-http-fixture") + 1])
                if "native_measurement" in result:
                    require(command is commands[-2], "delivery was followed by another effectful step")
                    checkpoint = result["native_measurement"]["checkpoint_sha256"]
                else:
                    require(result["state"] == result["observation"]["state"] == "paused", "step failed or resumed uncertain state")
                    checkpoint = result["checkpoint_sha256"]
                    require(checkpoint == result["observation"]["checkpoint_sha256"], "paused native/observer checkpoint differs")
            reports = [json.loads(raw[call["stdout"]]) for call in commands if "native_measurement" in json.loads(raw[call["stdout"]])]
            require(len(reports) == 2 and same(reports[0], reports[1]), "delivery/report reopen bytes differ")
            final = reports[0]
            require(final["native_D119_guard_replay_publication_verified"] is True and final["formal_cell_executed"] is False,
                    "recorded native verification flag or formal scope differs")
            journal_audit(label, raw, final["observation"])
            documents = {key: raw[label + "/run/" + name] for key, name in measurement.DOCUMENTS.items()}
            journals = {kind: {PurePosixPath(name).name: data for name, data in raw.items()
                              if name.startswith(label + "/run/" + kind + "/")} for kind in measurement.JOURNALS}
            streams = {}
            for name, data in raw.items():
                prefix = label + "/run/broker/"
                if name.startswith(prefix) and PurePosixPath(name).name in ("stdout", "stderr"):
                    streams.setdefault(PurePosixPath(name).parent.name, {})[PurePosixPath(name).name] = data
            plan, state, context = [json.loads(documents[key]) for key in ("plan", "state", "context")]
            publication = json.loads(documents["publication"])
            expected_publication = {"schema": 1, "classification": observer.engine.CLASSIFICATION,
                "profile": observer.engine.PROFILE, "schedule_sha256": plan["descriptor"]["schedule_sha256"],
                "run_id": plan["run_id"], "plan_sha256": state["plan_sha256"],
                "checkpoint_sha256": context["checkpoint_sha256"], "delivery_sha256": state["delivery"]["sha256"],
                "delegations_sha256": sha(observer._canonical(state["delegations"])),
                "merges_sha256": sha(observer._canonical(state["merges"])),
                "artifacts": [{"path": str(Path(run_dir) / "artifacts" / PurePosixPath(name).name), "sha256": item["sha256"]}
                              for name, item in sorted(rows.items()) if name.startswith(label + "/run/artifacts/")],
                "method_phases_accepted": False, "quality_assessed": False, "formal_cell_executed": False}
            require(same(publication, expected_publication), "archive publication marker differs checkpoint/state/artifact hashes")
            for receipt in ([item["activation"] for item in state["delegations"]]
                            + [item["receipt"] for item in state["merges"]] + [state["delivery"]]):
                name = label + "/run/" + Path(receipt["path"]).relative_to(Path(run_dir)).as_posix()
                require(name in rows and rows[name]["sha256"] == receipt["sha256"], "archived bound control receipt differs")
            budget = ledger_budget(documents["ledger"])
            status = {"state": state["state"], "publication_valid": True, "run_id": plan["run_id"],
                      "checkpoint_sha256": context["checkpoint_sha256"], "schedule_sha256": plan["descriptor"]["schedule_sha256"],
                      "completed_requests": state["completed_requests"], "tool_calls_completed": state["tool_calls_completed"],
                      "context": {"active_seconds": context["active_seconds"], "paused_seconds": context["paused_seconds"],
                                  "tools_reserved": len(journals["tool_reservations"])},
                      "budget": {key: value for key, value in budget.items() if key != "ledger_sha256"}}
            snapshot = {"documents": documents, "journals": journals, "streams": streams, "status": status, "budget": budget}
            base, digest = observer._coverage(snapshot, final["observation"])
            require(same(base, final["native_measurement"]) and digest == final["native_measurement_sha256"], "archived D120 PURE reconciliation differs final CLI")
            expected = observer._final_report(snapshot, final["observation"])
            expected["native_D119_guard_replay_publication_verified"] = True  # Compare recorded flag; do not attest custody.
            require(same(expected, final), "final CLI schema/projection differs frozen producer")
            require(row["report_sha256"] == sha(json.dumps(final, sort_keys=True).encode()), "per-run report pin differs")
            trace = json.loads(raw[label + "/http_trace.json"])
            sends, counts = [item for item in trace if item["operation"] == "send"], [item for item in trace if item["operation"] == "count"]
            count_identity = {}
            for item in base["requests"]:
                request = json.loads(journals["requests"][item["request_id"] + ".json"])
                count_payload, _ = observer._payloads(request)
                key = (item["role"], sha(json.dumps(count_payload, sort_keys=True).encode()))
                require(key not in count_identity, "count payload identity ambiguous")
                count_identity[key] = item["turn"]
            # The frozen fixture's count trace has no turn or timestamps.
            # Bind it by exact payload digest; timing comes from the journal.
            def ids(values):
                return {(item["role"], item["turn"] if "turn" in item else
                         count_identity[item["role"], item["request_sha256"]]) for item in values}
            require(len(sends) == len(counts) == len(ids(sends)) == len(ids(counts)) == row["native_requests"] == len(base["requests"]),
                    "HTTP exact request/count/send coverage differs")
            require(ids(sends) == ids(counts) == {(item["role"], item["turn"]) for item in base["requests"]}, "HTTP role/global IDs differ")
            operation_begins = {(item["data"]["kind"], item["data"]["request_id"]): item for item in final["observation"]["events"] if item["type"] == "operation_begin"}
            operation_ends = {item["data"]["op_id"]: item for item in final["observation"]["events"] if item["type"] == "operation_end"}
            for item in trace:
                turn = item["turn"] if "turn" in item else count_identity[item["role"], item["request_sha256"]]
                request_id = item["role"] + "-turn-" + f"{turn:04d}"
                request = json.loads(journals["requests"][request_id + ".json"])
                count, send = observer._payloads(request)
                kind = "count_input" if item["operation"] == "count" else "send"
                payload = count if kind == "count_input" else send
                require(item["request_sha256"] == sha(json.dumps(payload, sort_keys=True).encode()), "HTTP payload hash differs transformed archived request")
                begin = operation_begins[kind, request_id]
                end = operation_ends[begin["data"]["op_id"]]
                if kind == "send":
                    require(type(item["started_ns"]) is int and type(item["ended_ns"]) is int
                            and begin["monotonic_ns"] <= item["started_ns"] <= item["ended_ns"] <= end["monotonic_ns"], "HTTP interval outside observed delegate interval")
                else:
                    require(item["declared_input_tokens"] == next(value["input_tokens"] for value in base["requests"] if value["request_id"] == request_id),
                            "HTTP declared count differs ledger usage")
                if "response_sha256" in item and kind == "send":
                    response = json.loads(journals["responses"][request_id + ".json"])
                    require(item["response_sha256"] == sha(json.dumps(response, sort_keys=True).encode()), "HTTP response hash differs archived response")
            overlap = any(a["role"] != b["role"] and a["role"].startswith("worker-") and b["role"].startswith("worker-")
                          and max(a["started_ns"], b["started_ns"]) < min(a["ended_ns"], b["ended_ns"])
                          for index, a in enumerate(sends) for b in sends[index + 1:])
            require(overlap is (arm != "A") and row["worker_http_overlap"] is overlap, "original A serial versus B/C parallel overlap differs")
            require(row["native_tools"] == len(base["tools"]) and row["fixture_declared_tokens"] == base["totals"]["total_tokens"] == 7 * len(sends),
                    "tool/token aggregates differ")
            require(same(row["metrics"], final["observation"]["metrics"]), "row metrics differ final report")
            require(all(value not in json.dumps(final) for value in ("PRIVATE-", "SYNTHETIC-PRIVATE")), "synthetic private sentinel leaked into published projection")
            runs.append({"interpreter": interpreter, "arm": arm, "run_id": row["run_id"], "requests": len(sends),
                         "tools": len(base["tools"]), "declared_tokens": base["totals"]["total_tokens"],
                         "W_local_elapsed_seconds": final["observation"]["W_local_elapsed_seconds"],
                         "worker_http_overlap": overlap, "typed_journal_and_PURE_accounting_verified": True,
                         "recorded_native_guard_flag": True})
    require(len(runs) == len({row["run_id"] for row in runs}) == 6, "cross-interpreter run IDs duplicated")
    source_audit()
    return {"phase": "six_archived_synthetic_integrations", "open_material_findings": [], "runs": runs, "archives": archives,
            "formal_cells_executed": 0, "limits": ["Read-only archive/inventory/CLI audit; no extraction or native reexecution",
            "Native guard flag cotejado against recorded CLI and frozen source, not authenticated custody",
            "Prices/usage/model identity synthetic declarations; C2-C5, H, Q and formal acceptance remain unproved"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("gates", "integrations"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = gates_audit() if args.phase == "gates" else integrations_audit()
    if args.output:
        require(args.output.absolute().parent == REVIEW, "audit output must be a new direct child of review")
        with args.output.open("x") as stream:
            json.dump(result, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
    print(json.dumps({"phase": args.phase, "completed": True, "output": str(args.output) if args.output else None,
                      "open_material_findings": []}))


if __name__ == "__main__":
    main()
