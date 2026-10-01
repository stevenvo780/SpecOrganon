"""Original cases, empty bootstrap, real sealed tools and synthetic local HTTP."""

from __future__ import annotations

import csv
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import c_parent_analysis as c  # noqa: E402
from managed_wave_ledger import WaveLedger  # noqa: E402
from parent_analysis_broker import ParentAnalysisBroker  # noqa: E402
from prepare_development_round import ANALYSIS_COMMON, TASK_CONTRACT, _capsules  # noqa: E402

# Reuse the recorded D116 fixture script/Responses shape without invoking its
# preparer, creating a graph on the host, or changing that historical module.
PRIOR_FIXTURE = ROOT / "experiments/development/parallel_analysis_2026-10-01/integration_checks.py"
spec = importlib.util.spec_from_file_location("d116_public_fixture", PRIOR_FIXTURE)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
VALID_SCRIPT, INVALID_SCRIPT = prior.VALID_SCRIPT, prior.INVALID_SCRIPT
LocalHTTP = prior.LocalHTTP


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def fixture(root: Path, case_id: str):
    root.mkdir(mode=0o700)
    capsules = root / "capsules"
    capsules.mkdir(mode=0o700)
    _capsules(capsules, analysis=True)
    case, inputs = capsules / case_id, root / "inputs"
    inputs.mkdir(mode=0o700)
    (inputs / "tool_policy").write_bytes(b'{"schema":2}\n')
    for name, value in (("common_prompt", ANALYSIS_COMMON), ("task_contract", TASK_CONTRACT)):
        (inputs / name).write_text(value)
    (inputs / "arm_prompt").write_text(json.dumps({"alternative": "C", "mode": "risk",
        "instructions": "Mechanical parent integration from empty work; synthetic model, no formal cell."}))
    config = {"run_id": "parent-wave-" + case_id + "-original", "model": "offline-exact", "effort": "medium",
              "price_profile": {"model": "offline-exact", "input_rate_micro_usd_per_million": 1000000,
                  "cached_input_rate_micro_usd_per_million": 1000000, "cache_write_rate_micro_usd_per_million": 1000000,
                  "output_rate_micro_usd_per_million": 1000000},
              "limit_tokens": 8000, "max_model_requests": 15, "cost_limit_micro_usd": 8000,
              "active_limit_seconds": 300, "workers": 2, "max_output_tokens": 256,
              "reviewer_max_output_tokens": 256, "max_model_turns": 5, "max_tool_calls": 10,
              "tool_wall_seconds": 5, "leader_max_model_turns": 3, "leader_max_output_tokens": 512}
    return case, inputs, config


def response(task: str, turn: int) -> dict:
    if task != "leader":
        return prior.response(task, turn)
    result = prior.response("reviewer", turn)
    result["id"] = "response-leader-" + str(turn)
    if turn in (1, 2):
        request = ({"op": "read", "path": "task.md", "offset": 0, "length": 4096} if turn == 1 else
                   {"op": "init", "nodes": [
                       {"id": key, "kind": kind, "phase": phase, "depends_on": deps, "status": "pending",
                        "claim": "Synthetic model proposal " + key + "; not independently verified."}
                       for key, kind, phase, deps in (
                           ("P1", "problem", "philosophy", []), ("P2", "assumption", "philosophy", []),
                           ("N", "normative", "philosophy", ["P1"]), ("E", "evidence", "science", ["P1"]),
                           ("R", "requirement", "engineering", ["E", "N"]), ("V", "test_result", "validation", ["R"]))]})
        result["output"] = [{"type": "reasoning", "id": "reasoning-leader-" + str(turn),
                             "encrypted_content": "SYNTHETIC-PRIVATE:leader:" + str(turn), "summary": []},
                            {"type": "function_call", "id": "function-leader-" + str(turn),
                             "call_id": "call-leader-" + str(turn), "name": "development_method", "status": "completed",
                             "arguments": json.dumps({"request": json.dumps(request)})}]
    else:
        result["output"][0]["encrypted_content"] = "SYNTHETIC-PRIVATE:leader:final"
        result["output"][1]["content"][0]["text"] = "Public leader artifact: proposed graph from sealed init; norms pending, no causal impact."
    return result


@contextmanager
def server(run: Path):
    trace, lock, barrier, turns = [], threading.Lock(), threading.Barrier(2), {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            first = json.loads(payload["input"][0]["content"])
            task = first.get("task_id", "reviewer")
            counting = self.path.endswith("count") or self.path.endswith("input_tokens")
            record = {"task": task, "operation": "count" if counting else "send", "request": payload,
                      "started_ns": time.monotonic_ns()}
            if counting:
                result = {"object": "response.input_tokens", "input_tokens": 10}
            else:
                with lock:
                    turns[task] = turn = turns.get(task, 0) + 1
                record.update(turn=turn, budget_at_send=WaveLedger(run / "ledger").snapshot())
                if task not in {"leader", "reviewer"}:
                    barrier.wait(timeout=30)
                result = response(task, turn)
            raw = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            record["ended_ns"] = time.monotonic_ns()
            with lock:
                trace.append(record)

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    http.daemon_threads = True
    threading.Thread(target=http.serve_forever, daemon=True).start()
    try:
        yield "http://127.0.0.1:" + str(http.server_port), trace
    finally:
        http.shutdown()
        http.server_close()
        (run.parent / "http_trace.json").write_text(json.dumps(trace, indent=2) + "\n")


def cli(root: Path, run: Path, command: str, *args):
    process = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "scripts/c_parent_analysis.py"),
                              command, "--run-dir", str(run), *map(str, args)],
                             capture_output=True, text=True, check=False, timeout=90)
    name = "cli-" + command + "-" + str(len(list(root.glob("cli-*.json")))) + ".json"
    (root / name).write_text(json.dumps({"argv": process.args, "returncode": process.returncode,
                                       "stdout": process.stdout, "stderr": process.stderr}, indent=2) + "\n")
    assert process.returncode == 0, process.stdout + process.stderr
    return json.loads(process.stdout)


def verify(run: Path, case: Path, result: dict, trace: list, context_before: bytes, bootstrap_binding: dict):
    assert result["state"] == "completed", result
    assert result["budget"]["request_count"] == result["completed_requests"] == 14
    assert result["budget"]["settled_tokens"] == 182 and result["tool_calls_completed"] == 10
    assert result["caller_graph_required"] is False and result["comparable_development_cell"] is False
    assert result["formal_cell_executed"] is False
    assert len(list((run.parent / "admissions").glob("*.json"))) == 1
    assert (run / "publication.json").is_file()
    before, after = json.loads(context_before), json.loads((run / "context/run.json").read_bytes())
    assert before["bindings"] == after["bindings"] and before["ledger_dir"] == after["ledger_dir"]
    assert before["journal_roots"] == after["journal_roots"]
    assert before["active_limit_seconds"] == after["active_limit_seconds"]
    assert len(list(run.rglob("ledger.json"))) == 1
    original = (run / "seed/method_state.json").read_bytes()
    assert json.loads(original) == json.loads((run / "merge/method_state.json").read_bytes())
    assert json.loads(original)["history"][0]["action"] == "init"
    assert json.loads(original)["nodes"]["N"]["status"] == "pending"
    plan = json.loads((run / "plan.json").read_bytes())
    assert plan["bootstrap_manifest"] == bootstrap_binding
    broker = ParentAnalysisBroker(run, bootstrap_binding)
    operations = broker.operations()
    assert len(operations) == 10 and [o["global_ordinal"] for o in operations] == list(range(1, 11))
    assert [o["request"]["op"] for o in operations[:2]] == ["read", "init"]
    assert all(o["task_id"] == "leader" for o in operations[:2])
    assert all(o["task_id"] != "leader" for o in operations[2:])
    analysis = [o["terminal"] for o in operations if o["profile"] == "analysis_readonly"]
    assert len(analysis) == 4 and sum(o["analysis_status"] == "valid" for o in analysis) == 3
    assert sum(o["analysis_status"] == "invalid_json" for o in analysis) == 1
    assert all(o["analysis_work_before"] == o["analysis_work_after_child"] for o in analysis)
    sends = [entry for entry in trace if entry["operation"] == "send"]
    assert len(sends) == 14
    leader = [entry for entry in sends if entry["task"] == "leader"]
    assert len(leader) == 3
    workers = [entry for entry in sends if entry["task"] not in {"leader", "reviewer"}]
    assert min(e["started_ns"] for e in workers) > max(e["ended_ns"] for e in leader)
    for turn in range(1, 6):
        pair = [entry for entry in workers if entry["turn"] == turn]
        assert len(pair) == 2 and max(e["started_ns"] for e in pair) < min(e["ended_ns"] for e in pair)
        assert all(e["budget_at_send"]["request_count"] == 3 + 2 * turn for e in pair)
        assert all("SYNTHETIC-PRIVATE:leader:" not in json.dumps(e["request"]) for e in pair)
    reviewer = next(e for e in sends if e["task"] == "reviewer")
    assert reviewer["started_ns"] > max(e["ended_ns"] for e in workers)
    assert "SYNTHETIC-PRIVATE:" not in json.dumps(reviewer["request"]) and "tools" not in reviewer["request"]
    case_id = json.loads((case / "case.json").read_bytes())["case_id"]
    if case_id == "D-F":
        raw = (case / "survey_table1.json").read_bytes()
        table = json.loads(raw)
        texts = json.loads((case / "text_extract_manifest.json").read_bytes())
        observations = {"respondent_count": sum(x["count"] for x in table["categories"]),
                        "reported_total": table["reported_total"],
                        "pdf_page_count": sum(len(x["pages"]) for x in texts["documents"])}
    else:
        raw = (case / "sample_first_complete_week.csv").read_bytes()
        with (case / "sample_first_complete_week.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        observations = {"row_count": len(rows), "appliance_Wh": sum(int(row["Appliances"]) for row in rows)}
    exports = result["merge_result"]["analysis_artifacts"]
    assert len(exports) == 2
    for entry in exports:
        metrics = json.loads(Path(entry["metrics_path"]).read_bytes())
        fresh = broker.current_metrics(entry["task_id"])
        assert fresh is not None and metrics["source_sha256"] == sha(raw) and metrics["observations"] == observations
        assert entry["metrics_sha256"] == fresh["analysis_metrics_sha256"]
        assert entry["global_ordinal"] == fresh["global_ordinal"]
        assert entry["broker_receipt_sha256"] == fresh["receipt_sha256"]
        assert entry["analysis_script_sha256"] == sha(VALID_SCRIPT.encode())
        assert sha(Path(entry["provenance_path"]).read_bytes()) == entry["provenance_sha256"]
    (run.parent / "independent_calculation.json").write_text(json.dumps({
        "classification": "documentary_mechanical_fixture_not_Q_or_field", "source_sha256": sha(raw),
        "observations": observations, "formal_cells_executed": 0}, indent=2) + "\n")


def execute_original(tmp_path: Path, case_id: str, use_cli: bool):
    case, inputs, config = fixture(tmp_path / "public", case_id)
    run = tmp_path / "run"
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    if use_cli:
        status = cli(tmp_path, run, "prepare", "--case-dir", case, "--inputs-dir", inputs,
                     "--config", config_path, "--admission-root", tmp_path / "admissions")
    else:
        status = c.prepare_c_parent_analysis(run, case, inputs, config, admission_root=tmp_path / "admissions")
    bootstrap = json.loads((run / "plan.json").read_bytes())["bootstrap_manifest"]
    context_before = (run / "context/run.json").read_bytes()
    assert list((tmp_path / "run-stages/leader/work").iterdir()) == []
    assert not list((tmp_path / "admissions").glob("*.json"))
    checkpoints = [status]
    with server(run) as (address, trace):
        for index in range(8):
            before = status
            if use_cli:
                status = cli(tmp_path, run, "step", "--expected-checkpoint", status["checkpoint_sha256"],
                             "--local-http-fixture", address)
            else:
                ids = ["leader"] if status["phase"] == "bootstrap" else ["c-task-1", "c-task-2", "reviewer"]
                status = c.execute_c_parent_analysis_step(run, {key: LocalHTTP(address) for key in ids},
                                                          expected_checkpoint=status["checkpoint_sha256"])
            checkpoints.append(status)
            assert status["context"]["active_seconds"] >= before["context"]["active_seconds"]
            fresh = cli(tmp_path, run, "status")
            assert fresh["checkpoint_sha256"] == status["checkpoint_sha256"]
            if index < 7:
                assert status["state"] == "paused", status
                assert status["artifacts"] == []
            if index == 0:
                assert status["phase"] == "bootstrap" and status["budget"]["request_count"] == 1
                assert not (tmp_path / "run-stages/leader/work/method_state.json").exists()
            if index == 1:
                assert status["phase"] == "bootstrap" and status["budget"]["request_count"] == 2
                assert (tmp_path / "run-stages/leader/work/method_state.json").is_file()
                assert not list((run / "seed").iterdir())
            if index == 2:
                assert status["phase"] == "wave" and status["budget"]["request_count"] == 3
                assert status["tool_calls_completed"] == 2
        verify(run, case, status, trace, context_before, bootstrap)
    (tmp_path / "checkpoints.json").write_text(json.dumps(checkpoints, indent=2) + "\n")


@pytest.mark.parametrize("case_id", ["D-F", "D-E"])
def test_original_sources_parent_http_bootstrap_repair_and_fresh_status(tmp_path, case_id):
    execute_original(tmp_path, case_id, False)


def test_original_energy_parent_cli_bootstrap_and_reconstruction(tmp_path):
    execute_original(tmp_path, "D-E", True)
