"""Finite read-only audit of captured D123 runs; never count/send/step."""
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[4]
DOSSIER = Path(__file__).resolve().parents[1]
REVIEW = DOSSIER / "review"
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def inventory(root):
    rows = {}
    for path in sorted(root.rglob("*")):
        mode = path.lstat()
        assert stat.S_ISDIR(mode.st_mode) or stat.S_ISREG(mode.st_mode)
        row = {"path": path.relative_to(root).as_posix(), "mode": stat.S_IMODE(mode.st_mode),
               "kind": "directory" if stat.S_ISDIR(mode.st_mode) else "file"}
        if row["kind"] == "file":
            assert mode.st_nlink == 1
            raw = path.read_bytes()
            row.update(bytes=len(raw), sha256=sha(raw))
        rows[row["path"]] = row
    return rows


def union(intervals):
    result, end = 0, -1
    for start, stop in sorted(intervals):
        assert stop >= start
        result += max(0, stop - max(start, end))
        end = max(end, stop)
    return result


def reopen(python, arguments, name, expected):
    argv = [python, "-I", "-B", *map(str, arguments)]
    result = subprocess.run(argv, cwd=ROOT, env=ENV, capture_output=True, timeout=180)
    (REVIEW / (name + ".stdout")).write_bytes(result.stdout)
    (REVIEW / (name + ".stderr")).write_bytes(result.stderr)
    meta = {"argv": argv, "exit_code": result.returncode,
            "stdout_sha256": sha(result.stdout), "stderr_sha256": sha(result.stderr)}
    (REVIEW / (name + ".command.json")).write_text(json.dumps(meta, indent=2) + "\n")
    assert result.returncode == 0 and not result.stderr
    assert json.loads(result.stdout) == expected
    return meta


def run():
    freeze_raw = (DOSSIER / "source_freeze.json").read_bytes()
    freeze = json.loads(freeze_raw)
    evidence = load(DOSSIER / "evidence.json")
    assert sha(freeze_raw) == evidence["source_freeze_sha256"]
    commit = evidence["current_source_commit"]
    source_path = str((DOSSIER / "source_freeze.json").relative_to(ROOT))
    assert subprocess.run(["git", "show", f"{commit}:{source_path}"], cwd=ROOT,
                          capture_output=True, check=True).stdout == freeze_raw
    rows = []
    for index, label in enumerate(("311", "312")):
        folder = DOSSIER / "checks" / ("final_attempt03_py" + label)
        report = load(folder / "report.json")
        python = report["python"]
        assert report["all_exit_zero"] and report["sources_unchanged"]
        assert report["source_freeze_sha256"] == sha(freeze_raw)
        assert evidence["environments"][index]["python"] == python
        labels = ("baseline_before", "entry_tests", "accounting_tests", "ruff", "compile", "integration", "baseline_after", "diff")
        assert len(report["commands"]) == len(labels)
        for name, command in zip(labels, report["commands"], strict=True):
            assert command["exit_code"] == 0
            for stream in ("stdout", "stderr"):
                assert sha((folder / (name + "." + stream)).read_bytes()) == command[stream + "_sha256"]
            if command["argv"][0] != python:
                assert name in {"ruff", "diff"}
        assert b"Ran 15 tests" in (folder / "entry_tests.stderr").read_bytes()
        assert b"59 passed" in (folder / "accounting_tests.stdout").read_bytes()
        for pin in freeze["sources"]:
            raw = (ROOT / pin["path"]).read_bytes()
            assert raw == (folder / "sources" / pin["path"]).read_bytes()
            assert len(raw) == pin["bytes"] and sha(raw) == pin["sha256"]
            assert raw == subprocess.run(["git", "show", f"{commit}:" + pin["path"]], cwd=ROOT,
                                         capture_output=True, check=True).stdout
        root = Path(report["runtime_dir"])
        before = inventory(root)
        manifest = load(folder / "runtimes_inventory.json")
        expected = {r["path"]: r for r in manifest["entries"]}
        assert len(expected) == len(manifest["entries"]) == 1720 and expected == before
        archive = folder / "runtimes.tar.gz"
        archive_raw = archive.read_bytes()
        assert sha(archive_raw) == report["archive"]["archive_sha256"]
        assert len(archive_raw) == report["archive"]["archive_bytes"]
        with tarfile.open(archive, "r:gz") as stream:
            members = stream.getmembers()
            assert len(members) == len(expected) and {m.name for m in members} == set(expected)
            for member in members:
                pin = expected[member.name]
                assert not Path(member.name).is_absolute() and ".." not in Path(member.name).parts
                assert member.mode == pin["mode"]
                if pin["kind"] == "directory":
                    assert member.isdir()
                else:
                    assert member.isfile() and member.size == pin["bytes"]
                    assert sha(stream.extractfile(member).read()) == pin["sha256"]
        calls = load(root / "cli_calls.json")
        assert len(calls) == 73
        assert load(folder / "integration_result.json") == load(root / "integration_result.json") == evidence["environments"][index]["integration"]
        assert load(folder / "integration.stdout") == load(root / "integration_result.json")
        finals, outcomes, negatives = {}, {}, []
        for call in calls:
            assert call["argv"][:3] == [python, "-I", "-B"]
            assert call["exit_code"] == call["expected_exit_code"]
            for stream in ("stdout", "stderr"):
                assert sha((root / call[stream]).read_bytes()) == call[stream + "_sha256"]
            value = load(root / call["stdout"])
            argv = call["argv"]
            if "--run-dir" in argv:
                name = Path(argv[argv.index("--run-dir") + 1]).parent.name
                if "outcomes" in argv:
                    outcomes[name] = value
                if "native_measurement" in value.get("result", {}):
                    finals[name] = value["result"]
            if call["exit_code"] == 2:
                negatives.append({"argv": argv, "stdout_sha256": call["stdout_sha256"]})
        assert len(negatives) == 4 and set(finals) == {"A-D-E", "B-D-E", "C-D-E"}
        reconstructed = []
        for arm in "ABC":
            name = arm + "-D-E"
            native = finals[name]
            assert native["native_D119_guard_replay_publication_verified"]
            m, observation = native["native_measurement"], native["observation"]
            assert m["coordinates"]["arm"] == arm and m["coordinates"]["case_id"] == "D-E" and m["coordinates"]["replica"] == 1
            assert observation["state"] == "delivered" and not native["formal_cell_executed"] and not native["quality_assessed"]
            run_dir = root / name / "run"
            raw_response_tokens = 0
            for request in m["requests"]:
                identity = request["request_id"] + ".json"
                receipt_raw = (run_dir / "receipts" / identity).read_bytes()
                response_raw = (run_dir / "responses" / identity).read_bytes()
                receipt, response = json.loads(receipt_raw), json.loads(response_raw)
                assert sha(receipt_raw) == request["receipt_sha256"]
                assert sha(response_raw) == request["response_sha256"] == receipt["response_sha256"]
                assert receipt["payload_sha256"] == request["payload_sha256"]
                usage = response["usage"]
                assert usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"] == 7
                assert request["declared_cost_micro_usd"] == 7
                raw_response_tokens += usage["total_tokens"]
            expected_requests = 19 if arm == "A" else 18
            assert len(m["requests"]) == m["totals"]["request_count"] == expected_requests
            assert raw_response_tokens == m["totals"]["total_tokens"] == m["totals"]["declared_cost_micro_usd"]
            assert len(m["tools"]) == m["totals"]["tool_count"] == 11
            event_raw = [p.read_bytes() for p in sorted((root / name / "observation/events").glob("*.json"))]
            events = [json.loads(raw) for raw in event_raw]
            assert events == observation["events"]
            previous = "0" * 64
            starts, intervals = {}, []
            for event, raw in zip(events, event_raw, strict=True):
                assert event["prev_sha256"] == previous
                previous = sha(raw)
                if event["type"] == "operation_begin":
                    starts[event["data"]["op_id"]] = event
                elif event["type"] == "operation_end":
                    begin = starts.pop(event["data"]["op_id"])
                    assert event["data"]["error"] is None
                    intervals.append((begin["data"]["kind"], begin["data"]["role"], begin["monotonic_ns"], event["monotonic_ns"]))
            assert not starts and previous == observation["last_event_sha256"]
            assert events[-1]["monotonic_ns"] - events[0]["monotonic_ns"] == observation["W_local_elapsed_ns"]
            assert observation["metrics"]["all"]["sum_ns"] == sum(stop - start for _, _, start, stop in intervals)
            assert observation["metrics"]["all"]["union_ns"] == union([(a, b) for _, _, a, b in intervals])
            assert sum(kind == "send" for kind, *_ in intervals) == expected_requests
            assert sum(kind == "count_input" for kind, *_ in intervals) == expected_requests
            assert sum(kind == "tool" for kind, *_ in intervals) == 11
            workers = [v for v in intervals if v[0] == "send" and v[1].startswith("worker-")]
            overlap = any(a[1] != b[1] and max(a[2], b[2]) < min(a[3], b[3]) for i, a in enumerate(workers) for b in workers[i + 1:])
            assert overlap is (arm != "A")
            row = next(r for r in evidence["environments"][index]["integration"]["runs"] if r["arm"] == arm)
            assert row["report_sha256"] == sha(json.dumps(native, sort_keys=True).encode())
            reopen(python, [ROOT / "scripts/observed_coordinated_runtime.py", "report", "--run-dir", run_dir,
                           "--observation-dir", root / name / "observation"], f"reopen_{label}_{arm}_observation", native)
            reconstructed.append({"arm": arm, "requests": expected_requests, "tools": 11, "tokens": raw_response_tokens,
                                  "W_local_elapsed_ns": observation["W_local_elapsed_ns"], "local_worker_send_overlap": overlap,
                                  "native_report_sha256": row["report_sha256"]})
        for name, outcome in outcomes.items():
            assert outcome["native_guard_verified"] and not outcome["quality_assessed"] and not outcome["formal_cell_executed"]
            assert outcome["totals"]["columns_are_alternative_not_additive"]
            assert outcome["totals"]["reported_usage"]["unknown_requests"] == 0
            assert outcome["native_replay_verified"] is (name != "incomplete")
            reopen(python, [ROOT / "scripts/authorized_coordinated_runtime.py", "outcomes", "--run-dir", root / name / "run"],
                   f"reopen_{label}_{name}_outcomes", outcome)
        incomplete = outcomes["incomplete"]
        assert incomplete["totals"]["ledger_commitment"] == {"held_cost_micro_usd": 133, "held_tokens": 133}
        assert incomplete["totals"]["reported_usage"]["complete_cost_micro_usd"] == 7
        assert not incomplete["indeterminate_state_resumable"]
        assert incomplete["requests"][0]["response_status"] == "incomplete"
        assert incomplete["requests"][0]["response_binding"] == "unbound_retained_raw"
        assert list((root / "openai_unapproved/run/requests").iterdir()) == []
        assert inventory(root) == before
        rows.append({"python": python, "captured_commands": 8, "captured_tests": 74, "captured_CLI": 73,
                     "archive": report["archive"], "all_archive_members_bytes_modes_origin_verified": True,
                     "reopen_count": 7, "reopens_equal_and_whole_runtime_unchanged": True,
                     "runs": reconstructed, "incomplete": evidence["environments"][index]["incomplete"],
                     "negative_CLI": negatives})
    output = {"classification": "independent_local_runtime_audit_not_R1", "source_freeze_commit": commit,
              "source_freeze_sha256": sha(freeze_raw), "source_count": len(freeze["sources"]), "environments": rows,
              "all_CLI": 146, "completed_requests": 110, "incomplete_requests": 2,
              "remote_HTTP_overlap_limit": "HTTP server trace was asserted by captured integration code but not archived; independently recomputed overlap is local observer send intervals.",
              "formal_cells_executed": 0, "quality_assessed": False, "reviewer_new_provider_requests": 0}
    (REVIEW / "final_runtime_audit.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"environments": 2, "archive_entries": [1720, 1720], "reopens": 14, "new_requests": 0}))


if __name__ == "__main__":
    run()
