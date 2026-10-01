"""Actual host/threads/HTTP checks with public synthetic transport fixtures."""

from __future__ import annotations

import copy
import json
import select
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import managed_parallel_wave as wave  # noqa: E402
from managed_token_ledger import TokenLedger  # noqa: E402
from managed_wave_ledger import WaveLedger  # noqa: E402
from run_managed_response import OpenAIResponsesHTTP  # noqa: E402


def plan() -> dict:
    return {"schema": 1, "execution_profile": "parallel_wave_v1", "run_id": "wave-public-fixture",
            "model": "offline-fixture-model", "effort": "medium",
            "price_profile": {"model": "offline-fixture-model", "input_rate_micro_usd_per_million": 1000000,
                              "cached_input_rate_micro_usd_per_million": 1000000,
                              "cache_write_rate_micro_usd_per_million": 1000000,
                              "output_rate_micro_usd_per_million": 1000000},
            "limit_tokens": 500, "max_model_requests": 3, "cost_limit_micro_usd": 500,
            "active_limit_seconds": 20, "context": "Public synthetic common facts; normative commitments pending.",
            "tasks": [{"task_id": f"task-{i}", "role": f"worker-{i}", "user": f"Propose scope {i}.",
                       "max_output_tokens": 20, "owned_node_ids": [f"node-{i}"]} for i in (1, 2)],
            "reviewer": {"user": "Review proposals without approving norms.", "max_output_tokens": 20}}


def response(task_id: str, *, output: list | None = None) -> dict:
    return {"id": "response-" + task_id, "model": "offline-fixture-model", "status": "completed",
            "service_tier": "default", "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
            "output": output if output is not None else [
                {"type": "reasoning", "encrypted_content": "PRIVATE-" + task_id, "summary": []},
                {"type": "message", "role": "assistant", "status": "completed", "content": [
                    {"type": "output_text", "text": "Pending proposal " + task_id}]}]}


class Fake:
    def __init__(self, task_id: str, *, barrier=None, run_dir=None):
        self.task_id, self.barrier, self.run_dir = task_id, barrier, run_dir
        self.counts, self.sends, self.payloads, self.timeouts = 0, 0, [], []
        self.count_hook = self.send_hook = None
        self.result = response(task_id)

    def count_input(self, payload: dict, *, timeout_seconds: float) -> int:
        self.counts += 1
        self.timeouts.append(timeout_seconds)
        if self.count_hook:
            self.count_hook(payload)
        return 5

    def send(self, payload: dict, *, timeout_seconds: float) -> dict:
        self.sends += 1
        self.payloads.append(copy.deepcopy(payload))
        self.timeouts.append(timeout_seconds)
        if self.run_dir and self.task_id != "reviewer":
            records = WaveLedger(self.run_dir / "ledger").status()["requests"]
            assert set(records) == {"task-1", "task-2"}
            assert all(record["state"] == "inflight" for record in records.values())
        if self.barrier:
            self.barrier.wait(timeout=5)
        if self.send_hook:
            self.send_hook(payload)
        return copy.deepcopy(self.result)


def prepare(tmp_path: Path, source: dict | None = None) -> tuple[Path, dict]:
    tmp_path.chmod(0o700)
    directory = tmp_path / "wave"
    return directory, wave.prepare_wave(directory, source or plan(), admission_root=tmp_path / "admission")


def transports(directory: Path, *, barrier: bool = True) -> dict:
    sync = threading.Barrier(2) if barrier else None
    return {name: Fake(name, barrier=sync if name != "reviewer" else None, run_dir=directory)
            for name in ("task-1", "task-2", "reviewer")}


def execute(directory: Path, status: dict, adapters: dict, **kwargs) -> dict:
    return wave.execute_wave(directory, adapters, expected_checkpoint=status["checkpoint_sha256"], **kwargs)


def test_parallel_barrier_shared_budget_and_private_reviewer(tmp_path):
    directory, prepared = prepare(tmp_path)
    adapters = transports(directory)
    result = execute(directory, prepared, adapters)
    assert result["state"] == "completed", result
    assert result["completed_requests"] == result["artifact_count"] == 3
    assert result["budget"]["settled_tokens"] == 21
    assert result["budget"]["request_count"] == 3
    assert result["tools_enabled"] is result["formal_cell_executed"] is result["core_mutated"] is False
    assert wave.read_wave_status(directory)["state"] == "completed"
    receipts = [json.loads((directory / "receipts" / f"task-{i}.json").read_bytes()) for i in (1, 2)]
    assert max(x["send_started_ns"] for x in receipts) < min(x["send_ended_ns"] for x in receipts)
    worker_inputs = [json.loads(adapters[f"task-{i}"].payloads[0]["input"][0]["content"]) for i in (1, 2)]
    assert worker_inputs[0]["common_context"] == worker_inputs[1]["common_context"] == plan()["context"]
    assert "worker_artifacts" not in worker_inputs[0] and "scope 2" not in str(worker_inputs[0])
    review = adapters["reviewer"].payloads[0]
    assert "PRIVATE-" not in json.dumps(review) and "Pending proposal task-1" in json.dumps(review)
    assert "tools" not in review and all(x.payloads[0]["reasoning"] == {"effort": "medium"} for x in adapters.values())
    assert b"PRIVATE-task-1" in (directory / "responses/task-1.json").read_bytes()
    assert all(0 < value <= 20 for adapter in adapters.values() for value in adapter.timeouts)
    with pytest.raises(wave.ParallelWaveError, match="never reexecutes"):
        execute(directory, prepared, adapters)


@pytest.mark.parametrize("bad", ["bool", "dev", "effort", "tools", "ownership", "role", "price", "requests"])
def test_plan_rejected_before_directory(tmp_path, bad):
    source = plan()
    if bad == "bool":
        source["limit_tokens"] = True
    elif bad == "dev":
        source["run_id"] = "dev-existing-solo"
    elif bad == "effort":
        source["effort"] = None
    elif bad == "tools":
        source["tools"] = []
    elif bad == "ownership":
        source["tasks"][1]["owned_node_ids"] = ["node-1"]
    elif bad == "role":
        source["tasks"][1]["role"] = "reviewer"
    elif bad == "price":
        source["price_profile"]["model"] = "other-model"
    else:
        source["max_model_requests"] = 2
    with pytest.raises(wave.ParallelWaveError):
        prepare(tmp_path, source)
    assert not (tmp_path / "wave").exists()


@pytest.mark.parametrize("field", ["limit_tokens", "cost_limit_micro_usd"])
def test_batch_budget_failure_has_zero_sends_and_no_partial_reservation(tmp_path, field):
    source = plan()
    source[field] = 40
    directory, prepared = prepare(tmp_path, source)
    adapters = transports(directory, barrier=False)
    result = execute(directory, prepared, adapters)
    assert result["state"] == "indeterminate"
    assert result["budget"]["requests"] == {}
    assert all(adapter.sends == 0 for adapter in adapters.values())


@pytest.mark.parametrize("bad", ["function", "reviewer_function", "model", "incomplete", "usage"])
def test_invalid_response_raw_preserved_and_no_artifact_publication(tmp_path, bad):
    directory, prepared = prepare(tmp_path)
    adapters = transports(directory)
    chosen = "reviewer" if bad == "reviewer_function" else "task-1"
    if "function" in bad:
        adapters[chosen].result["output"] = [{"type": "function_call", "name": "anything", "call_id": "public-fixture", "arguments": "{}"}]
    elif bad == "model":
        adapters[chosen].result["model"] = "other-model"
    elif bad == "incomplete":
        adapters[chosen].result["status"] = "incomplete"
    else:
        adapters[chosen].result["usage"]["total_tokens"] = 999
    result = execute(directory, prepared, adapters)
    assert result["state"] == "indeterminate"
    assert json.loads((directory / "responses" / f"{chosen}.json").read_bytes()) == adapters[chosen].result
    assert not list((directory / "artifacts").iterdir())
    assert result["budget"]["blocked"]


@pytest.mark.parametrize("phase", ["count", "send"])
def test_deadline_returns_without_join_and_late_result_never_writes(tmp_path, phase):
    source = plan()
    source["active_limit_seconds"] = 2
    directory, prepared = prepare(tmp_path, source)
    adapters = transports(directory, barrier=False)
    release = threading.Event()
    if phase == "count":
        adapters["task-2"].count_hook = lambda _: release.wait(10)
    else:
        adapters["task-2"].send_hook = lambda _: release.wait(10)
    start = time.monotonic()
    result = execute(directory, prepared, adapters)
    assert result["state"] == "indeterminate"
    assert time.monotonic() - start < 3.5
    before = {str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    assert not list((directory / "artifacts").iterdir())
    if phase == "send":
        assert (directory / "responses/task-1.json").exists()
        assert result["budget"]["indeterminate_tokens"] == 25
        assert result["budget"]["settled_tokens"] == 7
    else:
        assert result["budget"]["requests"] == {}
    release.set()
    time.sleep(0.15)
    after = {str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    assert before == after
    with pytest.raises(wave.ParallelWaveError, match="never reexecutes"):
        execute(directory, prepared, adapters)


@pytest.mark.parametrize("tamper", ["source", "plan", "base", "payload", "claim"])
def test_binding_mutation_blocks_effects(tmp_path, monkeypatch, tamper):
    directory, prepared = prepare(tmp_path)
    adapters = transports(directory, barrier=False)
    kwargs = {}
    if tamper == "source":
        original = wave._sources()
        monkeypatch.setattr(wave, "_sources", lambda: {**original, "new-source": "0" * 64})
    elif tamper == "plan":
        p = directory / "plan.json"
        p.write_bytes(p.read_bytes() + b"\n")
    elif tamper == "base":
        def guard():
            raise ValueError("public source base changed")
        kwargs["guard"] = guard
    elif tamper == "payload":
        adapters["task-1"].count_hook = lambda payload: payload.update(model="changed")
    else:
        def mutate(_):
            claim = next((tmp_path / "admission").glob("*.json"))
            claim.write_bytes(claim.read_bytes() + b"\n")
        adapters["task-1"].count_hook = mutate
    if tamper in {"source", "plan"}:
        with pytest.raises(ValueError):
            execute(directory, prepared, adapters, **kwargs)
    else:
        assert execute(directory, prepared, adapters, **kwargs)["state"] == "indeterminate"
    assert all(adapter.sends == 0 for adapter in adapters.values())
    assert WaveLedger(directory / "ledger").status()["requests"] == {}


def test_another_owner_cannot_count_or_change_winner_ledger(tmp_path):
    directory, first = prepare(tmp_path)
    second_dir = tmp_path / "second"
    second = wave.prepare_wave(second_dir, plan(), admission_root=tmp_path / "admission")
    assert execute(directory, first, transports(directory))["state"] == "completed"
    raw = (directory / "ledger/ledger.json").read_bytes()
    losing = transports(second_dir, barrier=False)
    assert execute(second_dir, second, losing)["state"] == "indeterminate"
    assert all(item.counts == item.sends == 0 for item in losing.values())
    assert (directory / "ledger/ledger.json").read_bytes() == raw


def test_post_send_guard_failure_preserves_timely_raw_without_artifacts(tmp_path):
    directory, prepared = prepare(tmp_path)
    adapters = transports(directory)
    changed = threading.Event()
    adapters["task-1"].send_hook = lambda _: changed.set()

    def guard():
        if changed.is_set():
            raise ValueError("public synthetic base changed after response")

    result = execute(directory, prepared, adapters, guard=guard)
    assert result["state"] == "indeterminate" and result["artifact_count"] == 0
    raw_responses = list((directory / "responses").iterdir())
    assert raw_responses and any(b"PRIVATE-" in p.read_bytes() for p in raw_responses)


def test_finish_failure_keeps_artifacts_forensic_and_status_does_not_read_fifo(tmp_path, monkeypatch):
    directory, prepared = prepare(tmp_path)

    def fail_finish(self, cursor):
        raise OSError("public synthetic checkpoint failure")

    monkeypatch.setattr(wave.RunContext, "finish", fail_finish)
    result = execute(directory, prepared, transports(directory))
    assert result["state"] == "indeterminate" and result["artifact_count"] == 0 and result["artifacts"] == []
    assert result["forensic_artifact_entry_count"] == 3
    import os
    artifact = directory / "artifacts/task-1.json"
    artifact.rename(directory / "forensic-original-task-1.json")
    os.mkfifo(artifact, 0o600)
    status = wave.read_wave_status(directory)
    assert status["state"] == "indeterminate" and status["artifacts"] == []


def test_ledger_cap_mutation_during_count_refuses_send(tmp_path):
    directory, prepared = prepare(tmp_path)
    adapters = transports(directory, barrier=False)

    def tamper(_):
        path = directory / "ledger/ledger.json"
        value = json.loads(path.read_bytes())
        value["limit_tokens"] = 1000
        path.write_bytes(wave._canonical(value))

    adapters["task-1"].count_hook = tamper
    result = execute(directory, prepared, adapters)
    assert result["state"] == "indeterminate"
    assert all(adapter.sends == 0 for adapter in adapters.values())


def test_actual_local_http_sends_overlap_and_legacy_adapter_timeout_unchanged(tmp_path):
    sync = threading.Barrier(2)
    intervals = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path.endswith("input_tokens"):
                result = {"object": "response.input_tokens", "input_tokens": 5}
            else:
                content = json.loads(body["input"][0]["content"])
                task_id = content.get("task_id", "reviewer")
                started = time.monotonic_ns()
                if task_id != "reviewer":
                    sync.wait(timeout=5)
                result = response(task_id)
                ended = time.monotonic_ns()
                if task_id != "reviewer":
                    intervals.append((started, ended))
            raw = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        directory, prepared = prepare(tmp_path)
        base = f"http://127.0.0.1:{server.server_port}/v1"
        adapters = {name: OpenAIResponsesHTTP("public-local-fixture-only", timeout_seconds=90, base_url=base)
                    for name in ("task-1", "task-2", "reviewer")}
        assert execute(directory, prepared, adapters)["state"] == "completed"
        assert len(intervals) == 2 and max(x[0] for x in intervals) < min(x[1] for x in intervals)
        assert all(adapter._timeout == 90 for adapter in adapters.values())
    finally:
        server.shutdown()
        server.server_close()


def test_real_process_crash_retains_inflight_and_cannot_resume(tmp_path):
    directory, prepared = prepare(tmp_path)
    script = """
import sys, threading
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from managed_parallel_wave import execute_wave
barrier=threading.Barrier(2)
class T:
 def count_input(self,payload,*,timeout_seconds): return 5
 def send(self,payload,*,timeout_seconds):
  number=barrier.wait(timeout=5)
  if number==0: print('INFLIGHT',flush=True)
  threading.Event().wait(60)
execute_wave(Path(sys.argv[2]),{k:T() for k in ('task-1','task-2','reviewer')},expected_checkpoint=sys.argv[3])
"""
    with (tmp_path / "crash.stderr").open("wb") as stderr:
        process = subprocess.Popen([sys.executable, "-B", "-c", script,
                                    str(Path(wave.__file__).parent), str(directory), prepared["checkpoint_sha256"]],
                                   stdout=subprocess.PIPE, stderr=stderr)
        try:
            assert select.select([process.stdout], [], [], 10)[0]
            assert process.stdout.readline() == b"INFLIGHT\n"
            process.kill()
            assert process.wait(timeout=5) < 0
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    status = wave.read_wave_status(directory)
    assert status["state"] == "indeterminate" and status["stored_state"] == "started"
    assert status["budget"]["inflight_tokens"] == 50
    with pytest.raises(wave.ParallelWaveError, match="never reexecutes"):
        execute(directory, prepared, transports(directory))


def test_legacy_token_ledger_keeps_its_schema_and_pending_rule(tmp_path):
    tmp_path.chmod(0o700)
    ledger = TokenLedger.create(tmp_path / "legacy", 100, 3)
    assert ledger.status()["schema"] == 1
    ledger.reserve("legacy-one", "role", "a" * 64, 5, 10)
    with pytest.raises(Exception, match="unresolved reserved request"):
        ledger.reserve("legacy-two", "role", "b" * 64, 5, 10)
