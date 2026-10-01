"""C proposals over real local HTTP, with synthetic public case/model data."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import c_parallel_work as c  # noqa: E402
from managed_wave_ledger import WaveLedger  # noqa: E402


def case(root: Path, domain="D-F-synthetic"):
    root.mkdir(mode=0o700)
    nodes = []
    for node_id, kind, phase, deps in (
        ("P1", "problem", "philosophy", []), ("P2", "assumption", "philosophy", []),
        ("N", "normative", "philosophy", ["P1"]),
        ("E", "evidence", "science", ["P1"]),
        ("R", "requirement", "engineering", ["E", "N"]),
        ("V", "test_result", "validation", ["R"]),
    ):
        nodes.append({"id": node_id, "kind": kind, "phase": phase, "depends_on": deps,
                      "status": "pending", "claim": f"synthetic {domain} {node_id}"})
    source, state, facts = root / "case.json", root / "state.json", root / "facts.txt"
    source.write_text(json.dumps({"case_id": domain, "nodes": nodes}))
    assert c.core.run("risk", ["init", "--case", str(source), "--state", str(state)]) == 0
    facts.write_text(f"Public synthetic facts for {domain}. No observed field outcomes.\n")
    config = {"run_id": "wave-" + domain, "model": "offline-exact", "effort": "medium",
              "price_profile": {"model": "offline-exact",
                                "input_rate_micro_usd_per_million": 1000000,
                                "cached_input_rate_micro_usd_per_million": 1000000,
                                "cache_write_rate_micro_usd_per_million": 1000000,
                                "output_rate_micro_usd_per_million": 1000000},
              "limit_tokens": 5000, "max_model_requests": 8,
              "cost_limit_micro_usd": 5000, "active_limit_seconds": 20,
              "workers": 2, "max_output_tokens": 64, "reviewer_max_output_tokens": 64}
    return state, facts, config


def response(task_id):
    return {"id": f"response-{task_id}", "model": "offline-exact", "status": "completed",
            "service_tier": "default",
            "usage": {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
            "output": [{"type": "reasoning", "id": f"reasoning-{task_id}",
                        "summary": [{"type": "summary_text", "text": f"PRIVATE:{task_id}"}]},
                       {"type": "message", "id": f"message-{task_id}", "role": "assistant",
                        "status": "completed", "content": [{"type": "output_text",
                        "text": f"artifact:{task_id}", "annotations": []}]}]}


class LocalHTTP:
    def __init__(self, address, task):
        self.address, self.task = address, task

    def post(self, endpoint, payload, timeout_seconds):
        request = urllib.request.Request(self.address + f"/{self.task}/{endpoint}",
                                         data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=timeout_seconds) as stream:
            return json.loads(stream.read())

    def count_input(self, payload, *, timeout_seconds):
        return self.post("count", payload, timeout_seconds)["input_tokens"]

    def send(self, payload, *, timeout_seconds):
        return self.post("send", payload, timeout_seconds)


@pytest.mark.parametrize("domain", ["D-F-synthetic", "D-E-synthetic"])
def test_real_http_c_wave_overlaps_and_reviewer_shares_only_artifacts(tmp_path, domain):
    state, facts, config = case(tmp_path / "inputs", domain)
    originals = state.read_bytes(), facts.read_bytes()
    run = tmp_path / "run"
    prepared = c.prepare_c_wave(run, state, facts, config, admission_root=tmp_path / "admissions")
    trace, lock, barrier = [], threading.Lock(), threading.Barrier(2)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            task, operation = self.path.strip("/").split("/")
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            record = {"task": task, "operation": operation, "request": payload,
                      "started_ns": time.monotonic_ns()}
            if operation == "count":
                result = {"input_tokens": 10}
            else:
                budget = WaveLedger(run / "ledger").snapshot()
                record["budget_at_send_entry"] = budget
                assert budget["request_count"] == (3 if task == "reviewer" else 2)
                assert "tools" not in payload
                assert payload["reasoning"] == {"effort": "medium"}
                if task != "reviewer":
                    barrier.wait(timeout=5)
                result = response(task)
            raw = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            record["finished_ns"] = time.monotonic_ns()
            with lock:
                trace.append(record)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    address = f"http://127.0.0.1:{server.server_port}"
    transports = {task: LocalHTTP(address, task) for task in ("c-task-1", "c-task-2", "reviewer")}
    try:
        result = c.execute_c_wave(run, transports,
                                  expected_checkpoint=prepared["checkpoint_sha256"])
    finally:
        server.shutdown()
        server.server_close()
    (tmp_path / "http_trace.json").write_text(json.dumps(trace, indent=2) + "\n")
    (tmp_path / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    assert result["state"] == "completed"
    assert result["budget"]["settled_tokens"] == 39
    assert result["budget"]["request_count"] == 3
    assert result["formal_cell_executed"] is False
    assert result["tools_enabled"] is False
    assert result["artifact_count"] == 3
    sends = [item for item in trace if item["operation"] == "send"]
    workers = [item for item in sends if item["task"] != "reviewer"]
    assert max(item["started_ns"] for item in workers) < min(item["finished_ns"] for item in workers)
    review = next(item for item in sends if item["task"] == "reviewer")
    assert review["started_ns"] > max(item["finished_ns"] for item in workers)
    assert "PRIVATE:" not in json.dumps(review["request"])
    assert all(f"artifact:{task}" in json.dumps(review["request"])
               for task in ("c-task-1", "c-task-2"))
    plan = json.loads((run / "plan.json").read_bytes())
    assert [task["owned_node_ids"] for task in plan["tasks"]] == [["P1"], ["P2"]]
    assert state.read_bytes() == originals[0] and facts.read_bytes() == originals[1]
    assert json.loads(state.read_bytes())["nodes"]["N"]["status"] == "pending"
    for record in result["artifacts"]:
        assert hashlib.sha256(Path(record["path"]).read_bytes()).hexdigest() == record["sha256"]


@pytest.mark.parametrize("mutation", ["approved_norm", "dependent_work", "mode"])
def test_c_rejects_unverified_norms_and_noneligible_wave_before_prepare(tmp_path, mutation):
    state, facts, config = case(tmp_path / "inputs")
    value = json.loads(state.read_bytes())
    if mutation == "approved_norm":
        value["nodes"]["N"]["status"] = "approved"
    elif mutation == "dependent_work":
        value["nodes"]["P2"]["depends_on"] = ["P1"]
    else:
        value["mode"] = "graph"
    state.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        c.prepare_c_wave(tmp_path / "run", state, facts, config,
                          admission_root=tmp_path / "admissions")
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("target", ["state", "facts"])
def test_c_bound_input_change_cannot_launch_model_io(tmp_path, target):
    state, facts, config = case(tmp_path / "inputs")
    run = tmp_path / "run"
    prepared = c.prepare_c_wave(run, state, facts, config, admission_root=tmp_path / "admissions")
    path = state if target == "state" else facts
    path.write_bytes(path.read_bytes() + b"\n")

    class Never:
        def count_input(self, *args, **kwargs):
            pytest.fail("changed base must not count or send")

        send = count_input

    try:
        result = c.execute_c_wave(run, {name: Never() for name in ("c-task-1", "c-task-2", "reviewer")},
                                  expected_checkpoint=prepared["checkpoint_sha256"])
    except ValueError:
        result = {"state": "rejected"}
    assert result["state"] != "completed"
    assert WaveLedger(run / "ledger").snapshot()["request_count"] == 0


def test_c_cli_prepare_and_status_use_new_identity_without_model_io(tmp_path):
    state, facts, config = case(tmp_path / "inputs")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    run = tmp_path / "run"
    command = [sys.executable, "-I", "-B", str(SCRIPTS / "c_parallel_work.py")]
    commands = [command + ["prepare", "--state", str(state), "--facts", str(facts),
                          "--config", str(config_path), "--run-dir", str(run),
                          "--admission-root", str(tmp_path / "admissions")],
                command + ["status", "--run-dir", str(run)]]
    for index, args in enumerate(commands, 1):
        completed = subprocess.run(args, capture_output=True, timeout=30, check=False)
        (tmp_path / f"cli-{index}.stdout").write_bytes(completed.stdout)
        (tmp_path / f"cli-{index}.stderr").write_bytes(completed.stderr)
        assert completed.returncode == 0, completed.stdout
        result = json.loads(completed.stdout)
        assert result["state"] == "prepared"
        assert result["budget"]["request_count"] == 0
        assert result["formal_cell_executed"] is False
    prepared = result
    barrier, trace = threading.Barrier(2), []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            content = json.loads(payload["input"][0]["content"])
            task = content.get("task_id", "reviewer")
            if self.path.endswith("/input_tokens"):
                value = {"input_tokens": 10}
            else:
                if task != "reviewer":
                    barrier.wait(timeout=5)
                value = response(task)
            trace.append({"path": self.path, "request": payload})
            raw = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        completed = subprocess.run(command + ["execute", "--run-dir", str(run),
                                   "--expected-checkpoint", prepared["checkpoint_sha256"],
                                   "--local-http-fixture", f"http://127.0.0.1:{server.server_port}/v1"],
                                   capture_output=True, timeout=30, check=False)
    finally:
        server.shutdown()
        server.server_close()
    (tmp_path / "cli-3.stdout").write_bytes(completed.stdout)
    (tmp_path / "cli-3.stderr").write_bytes(completed.stderr)
    (tmp_path / "cli-http-trace.json").write_text(json.dumps(trace, indent=2) + "\n")
    assert completed.returncode == 0, completed.stdout
    result = json.loads(completed.stdout)
    assert result["state"] == "completed" and result["local_http_fixture"] is True
    assert result["budget"]["request_count"] == 3
    assert result["budget"]["settled_tokens"] == 39
    assert result["formal_cell_executed"] is False
    assert len(trace) == 6
