"""Original public sources, actual sealed tools, synthetic local HTTP responses."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import threading
import time
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import c_parallel_analysis as c  # noqa: E402
import c_parallel_tools as legacy  # noqa: E402
from managed_wave_ledger import WaveLedger  # noqa: E402
from parallel_analysis_broker import AnalysisParallelToolBroker  # noqa: E402
from prepare_development_round import ANALYSIS_COMMON, TASK_CONTRACT, _capsules  # noqa: E402


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


VALID_SCRIPT = """import csv, hashlib, json, sys
from pathlib import Path
p = Path(sys.argv[1])
case = json.loads((p / 'case.json').read_bytes())['case_id']
if case == 'D-F':
    raw = (p / 'survey_table1.json').read_bytes()
    table = json.loads(raw)
    texts = json.loads((p / 'text_extract_manifest.json').read_bytes())
    result = {'respondent_count': sum(x['count'] for x in table['categories']),
              'reported_total': table['reported_total'],
              'pdf_page_count': sum(len(x['pages']) for x in texts['documents'])}
else:
    raw = (p / 'sample_first_complete_week.csv').read_bytes()
    rows = list(csv.DictReader(raw.decode('utf-8').splitlines()))
    result = {'row_count': len(rows),
              'appliance_Wh': sum(int(x['Appliances']) for x in rows)}
print(json.dumps({'classification': 'documentary_mechanical_calculation_not_impact',
                  'case_id': case, 'source_sha256': hashlib.sha256(raw).hexdigest(),
                  'observations': result}))
"""
INVALID_SCRIPT = "print('{invalid JSON')\n"


def fixture(root: Path, case_id: str):
    root.mkdir(mode=0o700)
    capsule_root = root / "capsules"
    capsule_root.mkdir(mode=0o700)
    _capsules(capsule_root, analysis=True)
    case, inputs = capsule_root / case_id, root / "inputs"
    inputs.mkdir(mode=0o700)
    for name, value in (("common_prompt", ANALYSIS_COMMON), ("task_contract", TASK_CONTRACT)):
        (inputs / name).write_text(value)
    (inputs / "arm_prompt").write_text(json.dumps({"alternative": "C", "mode": "risk",
        "instructions": "Mechanical private-branch integration with a caller-supplied graph; not a formal cell."}))
    nodes = []
    for node_id, kind, phase, deps in (
        ("P1", "problem", "philosophy", []), ("P2", "assumption", "philosophy", []),
        ("N", "normative", "philosophy", ["P1"]), ("E", "evidence", "science", ["P1"]),
        ("R", "requirement", "engineering", ["E", "N"]), ("V", "test_result", "validation", ["R"]),
    ):
        nodes.append({"id": node_id, "kind": kind, "phase": phase, "depends_on": deps,
                      "status": "pending", "claim": f"Mechanical node {node_id}; no independently verified claim."})
    source, state = root / "nodes.json", root / "state.json"
    source.write_text(json.dumps({"case_id": case_id, "nodes": nodes}))
    assert legacy.core.run("risk", ["init", "--case", str(source), "--state", str(state)]) == 0
    config = {"run_id": f"tool-wave-{case_id}-original-analysis", "model": "offline-exact",
              "effort": "medium", "price_profile": {
                  "model": "offline-exact", "input_rate_micro_usd_per_million": 1000000,
                  "cached_input_rate_micro_usd_per_million": 1000000,
                  "cache_write_rate_micro_usd_per_million": 1000000,
                  "output_rate_micro_usd_per_million": 1000000},
              "limit_tokens": 8000, "max_model_requests": 12,
              "cost_limit_micro_usd": 8000, "active_limit_seconds": 120,
              "workers": 2, "max_output_tokens": 256, "reviewer_max_output_tokens": 256,
              "max_model_turns": 5, "max_tool_calls": 8, "tool_wall_seconds": 4}
    return state, case, inputs, config


def response(task: str, turn: int) -> dict:
    if task == "reviewer" or turn == 5:
        output = [{"type": "message", "id": f"message-{task}", "role": "assistant",
                   "status": "completed", "content": [{"type": "output_text",
                   "text": f"Public artifact {task}: documentary calculation and actual tools; norms pending. No impact or model-quality evidence.",
                   "annotations": []}]}]
    else:
        initial = INVALID_SCRIPT if task == "c-task-1" else VALID_SCRIPT
        if turn == 1:
            name, arguments = "development_method", {"request": json.dumps({
                "op": "write", "path": "analysis.py", "offset": 0, "content": initial})}
        elif turn in (2, 4):
            name, arguments = "development_analysis", {"script_sha256": sha(
                (initial if turn == 2 else VALID_SCRIPT).encode())}
        elif task == "c-task-1":
            name, arguments = "development_method", {"request": json.dumps({
                "op": "replace", "path": "analysis.py", "expected_sha256": sha(initial.encode()),
                "content": VALID_SCRIPT})}
        else:
            name, arguments = "development_method", {"request": json.dumps({
                "op": "write", "path": "report.md", "offset": 0,
                "content": "Actual documentary calculation from the public package, not intervention impact.\n"})}
        output = [{"type": "function_call", "id": f"function-{task}-{turn}",
                   "call_id": f"call-{task}-{turn}", "name": name, "status": "completed",
                   "arguments": json.dumps(arguments)}]
    return {"id": f"response-{task}-{turn}", "model": "offline-exact", "status": "completed",
            "service_tier": "default", "usage": {
                "input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
            "output": [{"type": "reasoning", "id": f"reasoning-{task}-{turn}",
                        "encrypted_content": f"SYNTHETIC-PRIVATE:{task}:{turn}", "summary": []}, *output]}


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
            record = {"task": task, "operation": "count" if counting else "send",
                      "request": payload, "started_ns": time.monotonic_ns()}
            if counting:
                result = {"object": "response.input_tokens", "input_tokens": 10}
            else:
                with lock:
                    turns[task] = turn = turns.get(task, 0) + 1
                record.update(turn=turn, budget_at_send=WaveLedger(run / "ledger").snapshot())
                if task != "reviewer":
                    barrier.wait(timeout=15)
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
    serving = threading.Thread(target=http.serve_forever, daemon=True)
    serving.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}", trace
    finally:
        http.shutdown()
        http.server_close()
        (run.parent / "http_trace.json").write_text(json.dumps(trace, indent=2) + "\n")


class LocalHTTP:
    def __init__(self, address: str):
        self.address = address

    def post(self, endpoint: str, payload: dict, timeout: float):
        request = urllib.request.Request(self.address + "/" + endpoint,
                                         data=json.dumps(payload).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as stream:
            return json.loads(stream.read())

    def count_input(self, payload: dict, *, timeout_seconds):
        return self.post("count", payload, timeout_seconds)["input_tokens"]

    def send(self, payload: dict, *, timeout_seconds):
        return self.post("send", payload, timeout_seconds)


def cli(root: Path, run: Path, command: str, *args):
    process = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/c_parallel_analysis.py"),
                              command, "--run-dir", str(run), *map(str, args)],
                             capture_output=True, text=True, check=False, timeout=35)
    name = f"cli-{command}-{len(list(root.glob('cli-*.json'))):02d}.json"
    (root / name).write_text(json.dumps({"argv": process.args, "returncode": process.returncode,
        "stdout": process.stdout, "stderr": process.stderr}, indent=2) + "\n")
    assert process.returncode == 0, process.stdout + process.stderr
    return json.loads(process.stdout)


def verify(run: Path, case: Path, result: dict, original: bytes, state: Path, trace: list):
    assert result["state"] == "completed", result
    assert state.read_bytes() == original
    assert result["budget"]["request_count"] == 11
    assert result["budget"]["settled_tokens"] == 143
    assert result["tool_calls_completed"] == 8
    assert result["formal_cell_executed"] is False
    assert result["comparable_development_cell"] is False
    assert len(list((run.parent / "admissions/claims").glob("*.json"))) == 1
    assert (run / "publication.json").is_file()
    merged = json.loads((run / "merge/method_state.json").read_bytes())
    assert merged == json.loads(original)
    sends = [entry for entry in trace if entry["operation"] == "send"]
    assert len(sends) == 11
    for turn in range(1, 6):
        pair = [entry for entry in sends if entry["task"] != "reviewer" and entry["turn"] == turn]
        assert len(pair) == 2
        assert max(entry["started_ns"] for entry in pair) < min(entry["ended_ns"] for entry in pair)
        assert all(entry["budget_at_send"]["request_count"] == 2 * turn for entry in pair)
    reviewer = next(entry for entry in sends if entry["task"] == "reviewer")
    assert reviewer["started_ns"] > max(entry["ended_ns"] for entry in sends if entry["task"] != "reviewer")
    assert "SYNTHETIC-PRIVATE:" not in json.dumps(reviewer["request"])
    assert "tools" not in reviewer["request"]
    plan = json.loads((run / "plan.json").read_bytes())
    broker = AnalysisParallelToolBroker(run, plan["branch_manifest"])
    operations = broker.operations()
    assert len(operations) == 8
    assert [item["global_ordinal"] for item in operations] == list(range(1, 9))
    analysis = [item["terminal"] for item in operations if item["profile"] == "analysis_readonly"]
    assert len(analysis) == 4
    assert sum(item["analysis_status"] == "valid" for item in analysis) == 3
    assert sum(item["analysis_status"] == "invalid_json" for item in analysis) == 1
    assert all(item["analysis_work_before"] == item["analysis_work_after_child"] for item in analysis)
    if json.loads((case / "case.json").read_bytes())["case_id"] == "D-F":
        raw = (case / "survey_table1.json").read_bytes()
        table = json.loads(raw)
        texts = json.loads((case / "text_extract_manifest.json").read_bytes())
        observations = {"respondent_count": sum(item["count"] for item in table["categories"]),
                        "reported_total": table["reported_total"],
                        "pdf_page_count": sum(len(item["pages"]) for item in texts["documents"])}
    else:
        raw = (case / "sample_first_complete_week.csv").read_bytes()
        with (case / "sample_first_complete_week.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        observations = {"row_count": len(rows),
                        "appliance_Wh": sum(int(row["Appliances"]) for row in rows)}
    metrics_paths = list((run / "merge").rglob("metrics.json"))
    assert len(metrics_paths) == 2, metrics_paths
    for path in metrics_paths:
        metrics = json.loads(path.read_bytes())
        assert metrics["source_sha256"] == sha(raw)
        assert metrics["observations"] == observations
    exported = result["merge_result"]["analysis_artifacts"]
    assert len(exported) == 2
    for entry in exported:
        fresh = broker.current_metrics(entry["task_id"])
        assert fresh is not None
        assert entry["metrics_sha256"] == fresh["analysis_metrics_sha256"]
        assert entry["analysis_script_sha256"] == sha(VALID_SCRIPT.encode())
        assert entry["global_ordinal"] == fresh["global_ordinal"]
        assert entry["broker_receipt_sha256"] == fresh["receipt_sha256"]
        provenance_raw = Path(entry["provenance_path"]).read_bytes()
        assert sha(provenance_raw) == entry["provenance_sha256"]
        provenance = json.loads(provenance_raw)
        assert provenance["empirical_support_verified"] is False
        assert provenance["task_id"] == entry["task_id"]
        assert provenance["analysis_script_sha256"] == entry["analysis_script_sha256"]
    (run.parent / "independent_calculation.json").write_text(json.dumps({
        "classification": "fixture_calculation_only_not_Q_or_field", "source_sha256": sha(raw),
        "observations": observations, "metrics_paths": [str(path) for path in metrics_paths],
        "formal_cells_executed": 0}, indent=2) + "\n")


@pytest.mark.parametrize("case_id", ["D-F", "D-E"])
def test_original_sources_http_repair_same_budget_and_fresh_status(tmp_path, case_id):
    state, case, inputs, config = fixture(tmp_path / "inputs", case_id)
    original, run = state.read_bytes(), tmp_path / "run"
    result = c.prepare_c_analysis_wave(run, state, case, inputs, config,
                                      admission_root=tmp_path / "admissions")
    checkpoints = [result]
    with server(run) as (address, trace):
        transports = {task: LocalHTTP(address) for task in ("c-task-1", "c-task-2", "reviewer")}
        for step in range(5):
            old = result
            result = c.execute_c_analysis_wave_step(run, transports,
                                                   expected_checkpoint=result["checkpoint_sha256"])
            checkpoints.append(result)
            assert result["context"]["active_seconds"] >= old["context"]["active_seconds"]
            fresh = cli(tmp_path, run, "status")
            assert fresh["checkpoint_sha256"] == result["checkpoint_sha256"]
            if step < 4:
                assert result["state"] == "paused", result
                assert result["budget"]["request_count"] == 2 * (step + 1)
                assert result["artifacts"] == []
        verify(run, case, result, original, state, trace)
    (tmp_path / "checkpoints.json").write_text(json.dumps(checkpoints, indent=2) + "\n")


def test_original_energy_cli_repair_and_reconstruction(tmp_path):
    state, case, inputs, config = fixture(tmp_path / "inputs", "D-E")
    original, run, config_path = state.read_bytes(), tmp_path / "run", tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    result = cli(tmp_path, run, "prepare", "--state", state, "--case-dir", case,
                 "--inputs-dir", inputs, "--config", config_path,
                 "--admission-root", tmp_path / "admissions")
    with server(run) as (address, trace):
        for _ in range(5):
            result = cli(tmp_path, run, "step", "--expected-checkpoint", result["checkpoint_sha256"],
                         "--local-http-fixture", address)
        result = cli(tmp_path, run, "status")
        verify(run, case, result, original, state, trace)
