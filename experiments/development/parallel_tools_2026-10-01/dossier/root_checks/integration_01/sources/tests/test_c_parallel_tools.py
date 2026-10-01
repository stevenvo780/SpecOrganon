"""Real HTTP/CLI and sealed tool effects, with explicitly synthetic model data."""

from __future__ import annotations

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

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import c_parallel_tools as c  # noqa: E402
from managed_run_context import RunContext  # noqa: E402
from managed_wave_ledger import WaveLedger  # noqa: E402
from parallel_tool_broker import ParallelToolBroker  # noqa: E402


def fixture(root: Path, domain="D-F-synthetic"):
    root.mkdir(mode=0o700)
    case, inputs = root / "case", root / "inputs"
    case.mkdir(mode=0o700)
    inputs.mkdir(mode=0o700)
    nodes = []
    for node_id, kind, phase, deps in (
        ("P1", "problem", "philosophy", []), ("P2", "assumption", "philosophy", []),
        ("N", "normative", "philosophy", ["P1"]), ("E", "evidence", "science", ["P1"]),
        ("R", "requirement", "engineering", ["E", "N"]), ("V", "test_result", "validation", ["R"]),
    ):
        nodes.append({"id": node_id, "kind": kind, "phase": phase, "depends_on": deps,
                      "status": "pending", "claim": f"Synthetic {domain} node {node_id}"})
    source, state = root / "nodes.json", root / "state.json"
    source.write_text(json.dumps({"case_id": domain, "nodes": nodes}))
    assert c.core.run("risk", ["init", "--case", str(source), "--state", str(state)]) == 0
    facts = f"Public synthetic facts for {domain}. No observed outcomes or normative approval.\n".encode()
    (case / "task.md").write_bytes(facts)
    (case / "case.json").write_text(json.dumps({"case_id": domain,
        "files": [{"path": "task.md", "bytes": len(facts), "sha256": hashlib.sha256(facts).hexdigest()}],
        "deliverables": ["report.md", "sources.json", "analysis.py"]}))
    (inputs / "arm_prompt").write_text(json.dumps({"alternative": "C", "mode": "risk",
        "instructions": "Use the same public facts. Only fixture mechanics are evaluated."}))
    config = {"run_id": "tool-wave-" + domain, "model": "offline-exact", "effort": "medium",
              "price_profile": {"model": "offline-exact", "input_rate_micro_usd_per_million": 1000000,
                                "cached_input_rate_micro_usd_per_million": 1000000,
                                "cache_write_rate_micro_usd_per_million": 1000000,
                                "output_rate_micro_usd_per_million": 1000000},
              "limit_tokens": 5000, "max_model_requests": 8, "cost_limit_micro_usd": 5000,
              "active_limit_seconds": 30, "workers": 2, "max_output_tokens": 128,
              "reviewer_max_output_tokens": 128, "max_model_turns": 3,
              "max_tool_calls": 4, "tool_wall_seconds": 4}
    return state, case, inputs, config


def response(task, turn, owned):
    if task == "reviewer" or turn == 3:
        output = [{"type": "message", "id": f"message-{task}", "role": "assistant",
                   "status": "completed", "content": [{"type": "output_text",
                   "text": f"Public artifact {task}; synthetic facts, norms remain pending.", "annotations": []}]}]
    else:
        request = ({"op": "revise", "id": owned[0], "status": "supported",
                    "reason": "Synthetic control-flow assertion; not verified field support."}
                   if turn == 1 else {"op": "write", "path": "report.md", "offset": 0,
                                       "content": f"Public synthetic report of actual branch {task}.\n"})
        output = [{"type": "function_call", "id": f"function-{task}-{turn}",
                   "call_id": f"call-{task}-{turn}", "name": "development_method",
                   "status": "completed", "arguments": json.dumps({"request": json.dumps(request)})}]
    return {"id": f"response-{task}-{turn}", "model": "offline-exact", "status": "completed",
            "service_tier": "default", "usage": {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
            "output": [{"type": "reasoning", "id": f"reasoning-{task}-{turn}",
                        "encrypted_content": f"SYNTHETIC-PRIVATE:{task}:{turn}", "summary": []}, *output]}


@contextmanager
def server(run: Path):
    trace, lock, barrier = [], threading.Lock(), threading.Barrier(2)
    turns = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            first = json.loads(payload["input"][0]["content"])
            task = first.get("task_id", "reviewer")
            count = self.path.endswith("count") or self.path.endswith("input_tokens")
            record = {"task": task, "operation": "count" if count else "send",
                      "request": payload, "started_ns": time.monotonic_ns()}
            if count:
                result = {"object": "response.input_tokens", "input_tokens": 10}
            else:
                with lock:
                    turns[task] = turn = turns.get(task, 0) + 1
                record["budget_at_send"] = WaveLedger(run / "ledger").snapshot()
                record["turn"] = turn
                if task != "reviewer":
                    barrier.wait(timeout=8)
                result = response(task, turn, first.get("owned_node_ids", []))
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
    def __init__(self, address):
        self.address = address

    def post(self, endpoint, payload, timeout):
        request = urllib.request.Request(self.address + "/" + endpoint,
                                         data=json.dumps(payload).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as stream:
            return json.loads(stream.read())

    def count_input(self, payload, *, timeout_seconds):
        return self.post("count", payload, timeout_seconds)["input_tokens"]

    def send(self, payload, *, timeout_seconds):
        return self.post("send", payload, timeout_seconds)


def verify_complete(run, result, original, state_path):
    assert result["state"] == "completed", result
    assert state_path.read_bytes() == original
    merged = json.loads((run / "merge" / "method_state.json").read_bytes())
    for node in ("P1", "P2"):
        assert merged["nodes"][node]["status"] == "supported"
        assert merged["nodes"][node]["version"] == 2
    for node in ("N", "E", "R", "V"):
        assert merged["nodes"][node]["stale"]
    assert merged["nodes"]["N"]["status"] == "pending"
    assert set(merged["phase_status"].values()) == {"not_started"}
    assert result["budget"]["request_count"] == 7
    assert result["budget"]["settled_tokens"] == 91
    assert result["tool_calls_completed"] == 4
    assert result["formal_cell_executed"] is False
    assert (run / "publication.json").is_file()
    receipt = json.loads((run / "merge" / "receipt.json").read_bytes())
    assert len(receipt["operations"]) == 2 and len(receipt["artifacts"]) == 2
    for artifact in receipt["artifacts"]:
        raw = Path(artifact["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == artifact["sha256"]
        assert artifact["task_id"].encode() in raw
    return merged


@pytest.mark.parametrize("domain", ["D-F-synthetic", "D-E-synthetic"])
def test_real_http_private_tools_checkpoints_and_actual_merge(tmp_path, domain):
    state, case, inputs, config = fixture(tmp_path / "inputs", domain)
    original = state.read_bytes()
    run = tmp_path / "run"
    result = c.prepare_c_tool_wave(run, state, case, inputs, config, admission_root=tmp_path / "admissions")
    checkpoints = [result]
    with server(run) as (address, trace):
        transports = {task: LocalHTTP(address) for task in ("c-task-1", "c-task-2", "reviewer")}
        for step in range(3):
            before = result
            result = c.execute_c_tool_wave_step(run, transports, expected_checkpoint=result["checkpoint_sha256"])
            checkpoints.append(result)
            if step < 2:
                assert result["state"] == "paused", result
                assert result["budget"]["request_count"] == (step + 1) * 2
                assert result["active_seconds"] >= before["active_seconds"]
                assert result["artifacts"] == []
                assert c.read_tool_wave_status(run)["checkpoint_sha256"] == result["checkpoint_sha256"]
                with pytest.raises(ValueError):
                    c.execute_c_tool_wave_step(run, transports, expected_checkpoint=before["checkpoint_sha256"])
        verify_complete(run, result, original, state)
        sends = [entry for entry in trace if entry["operation"] == "send"]
        for turn in (1, 2, 3):
            pair = [entry for entry in sends if entry["task"] != "reviewer" and entry["turn"] == turn]
            assert len(pair) == 2
            assert max(entry["started_ns"] for entry in pair) < min(entry["ended_ns"] for entry in pair)
            assert all(entry["budget_at_send"]["request_count"] == turn * 2 for entry in pair)
        reviewer = next(entry for entry in sends if entry["task"] == "reviewer")
        assert reviewer["started_ns"] > max(entry["ended_ns"] for entry in sends if entry["task"] != "reviewer")
        assert "SYNTHETIC-PRIVATE:" not in json.dumps(reviewer["request"])
        assert "tools" not in reviewer["request"]
        for task in ("c-task-1", "c-task-2"):
            assert task in json.dumps(reviewer["request"])
        followups = [entry for entry in sends if entry["task"] != "reviewer" and entry["turn"] > 1]
        assert all(any(item.get("type") == "function_call_output" for item in entry["request"]["input"])
                   for entry in followups)
    (tmp_path / "checkpoints.json").write_text(json.dumps(checkpoints, indent=2) + "\n")


def test_real_cli_local_http_has_three_steps_and_merged_effects(tmp_path):
    state, case, inputs, config = fixture(tmp_path / "inputs", "D-F-cli-synthetic")
    original = state.read_bytes()
    run, config_path = tmp_path / "run", tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    def cli(command, *args):
        process = subprocess.run([sys.executable, "-B", str(SCRIPTS / "c_parallel_tools.py"), command,
                                  "--run-dir", str(run), *map(str, args)], capture_output=True, text=True, timeout=25)
        (tmp_path / f"cli-{command}-{len(list(tmp_path.glob('cli-*.json'))):02d}.json").write_text(
            json.dumps({"args": process.args, "returncode": process.returncode,
                        "stdout": process.stdout, "stderr": process.stderr}, indent=2) + "\n")
        assert process.returncode == 0, process.stdout + process.stderr
        return json.loads(process.stdout)

    result = cli("prepare", "--state", state, "--case-dir", case, "--inputs-dir", inputs,
                 "--config", config_path, "--admission-root", tmp_path / "admissions")
    with server(run) as (address, _):
        for _ in range(3):
            result = cli("step", "--expected-checkpoint", result["checkpoint_sha256"],
                         "--local-http-fixture", address)
        result = cli("status")
    verify_complete(run, result, original, state)


def test_invalid_scalar_config_does_not_consume_branch_or_run_paths(tmp_path):
    state, case, inputs, config = fixture(tmp_path / "inputs")
    run = tmp_path / "run"
    for key, value in (("limit_tokens", 0), ("max_model_turns", 0), ("tool_wall_seconds", float("inf"))):
        invalid = {**config, key: value}
        with pytest.raises(ValueError):
            c.prepare_c_tool_wave(run, state, case, inputs, invalid, admission_root=tmp_path / "admissions")
        assert not run.exists() and not (tmp_path / "run-branches").exists()
    assert c.prepare_c_tool_wave(run, state, case, inputs, config,
                                admission_root=tmp_path / "admissions")["state"] == "prepared"


def test_final_checkpoint_failure_keeps_merge_prepared_and_unpublished(tmp_path, monkeypatch):
    state, case, inputs, config = fixture(tmp_path / "inputs")
    run = tmp_path / "run"
    result = c.prepare_c_tool_wave(run, state, case, inputs, config, admission_root=tmp_path / "admissions")
    with server(run) as (address, _):
        transports = {task: LocalHTTP(address) for task in ("c-task-1", "c-task-2", "reviewer")}
        for _ in range(2):
            result = c.execute_c_tool_wave_step(run, transports, expected_checkpoint=result["checkpoint_sha256"])

        def fail_finish(self, cursor):
            raise OSError("synthetic checkpoint failure after actual merge")

        monkeypatch.setattr(RunContext, "finish", fail_finish)
        result = c.execute_c_tool_wave_step(run, transports, expected_checkpoint=result["checkpoint_sha256"])
    assert result["state"] == "indeterminate"
    assert result["artifacts"] == []
    assert result.get("merge_result") is None
    assert (run / "merge" / ".pending.json").is_file()
    assert (run / "merge" / "method_state.json").is_file()
    assert not (run / "publication.json").exists()
    assert ParallelToolBroker(run, json.loads((run / "plan.json").read_bytes())["branch_manifest"]).verify()["blocked"] is False
