"""Public synthetic conversations with real readonly analysis in private stages."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import c_parallel_analysis as c  # noqa: E402
import c_parallel_tools as original  # noqa: E402
from local_replay_sandbox import probe_sandbox  # noqa: E402
from parallel_analysis_broker import AnalysisParallelToolBroker  # noqa: E402


GOOD = "import json\nprint(json.dumps({'public_fixture_value':1}))\n"
BAD = "print('ordinary invalid JSON')\n"


def fixture(tmp_path, *, turns=3):
    tmp_path.chmod(0o700)
    case, inputs = tmp_path / "case", tmp_path / "inputs"
    case.mkdir(mode=0o700)
    inputs.mkdir(mode=0o700)
    nodes = []
    for node_id, kind, phase, deps in (
        ("P1", "problem", "philosophy", []), ("P2", "assumption", "philosophy", []),
        ("N", "normative", "philosophy", ["P1"]), ("E", "evidence", "science", ["P1"]),
        ("R", "requirement", "engineering", ["E", "N"]), ("V", "test_result", "validation", ["R"]),
    ):
        nodes.append({"id": node_id, "kind": kind, "phase": phase, "depends_on": deps,
                      "status": "pending", "claim": "Public synthetic control " + node_id})
    proposal, state = tmp_path / "proposal.json", tmp_path / "state.json"
    proposal.write_text(json.dumps({"case_id": "D116-public-fixture", "nodes": nodes}))
    assert original.core.run("risk", ["init", "--case", str(proposal), "--state", str(state)]) == 0
    facts = b"Public synthetic control; not a scientific result.\n"
    (case / "task.md").write_bytes(facts)
    (case / "case.json").write_text(json.dumps({"case_id": "D116-public-fixture",
        "files": [{"path": "task.md", "bytes": len(facts), "sha256": c._sha(facts)}],
        "deliverables": ["report.md", "sources.json", "analysis.py"]}))
    (inputs / "arm_prompt").write_text(json.dumps({"alternative": "C", "mode": "risk", "instructions": "Synthetic mechanics only."}))
    config = {"run_id": "tool-wave-D116-public-fixture", "model": "offline-fixture-model", "effort": "medium",
              "price_profile": {"model": "offline-fixture-model", "input_rate_micro_usd_per_million": 1000000,
                "cached_input_rate_micro_usd_per_million": 1000000, "cache_write_rate_micro_usd_per_million": 1000000,
                "output_rate_micro_usd_per_million": 1000000}, "limit_tokens": 5000,
              "max_model_requests": 2 * turns + 1, "cost_limit_micro_usd": 5000,
              "active_limit_seconds": 120, "workers": 2, "max_output_tokens": 128,
              "reviewer_max_output_tokens": 128, "max_model_turns": turns,
              "max_tool_calls": 2 * (turns - 1), "tool_wall_seconds": 5}
    return state, case, inputs, config


def write(source):
    return {"name": "development_method", "arguments": {"request": json.dumps({
        "op": "write", "path": "analysis.py", "offset": 0, "content": source})}}


def analyze(source):
    return {"name": "development_analysis", "arguments": {"script_sha256": c._sha(source.encode())}}


def replace(old, new):
    return {"name": "development_method", "arguments": {"request": json.dumps({
        "op": "replace", "path": "analysis.py", "expected_sha256": c._sha(old.encode()), "content": new})}}


class Fake:
    def __init__(self, task, operations, barrier=None):
        self.task, self.operations, self.barrier = task, operations, barrier
        self.counts = self.sends = 0
        self.payloads = []

    def count_input(self, payload, *, timeout_seconds):
        assert timeout_seconds > 0
        self.counts += 1
        return 5

    def send(self, payload, *, timeout_seconds):
        assert timeout_seconds > 0
        self.sends += 1
        self.payloads.append(copy.deepcopy(payload))
        if self.barrier:
            self.barrier.wait(10)
        operation = self.operations[self.sends - 1]
        output = [{"type": "reasoning", "encrypted_content": "PRIVATE-" + self.task, "summary": []}]
        if operation is None:
            output.append({"type": "message", "role": "assistant", "status": "completed", "content": [
                {"type": "output_text", "text": "Public synthetic artifact " + self.task}]})
        else:
            output.append({"type": "function_call", "status": "completed", "name": operation["name"],
                           "call_id": f"call-{self.task}-{self.sends}", "arguments": json.dumps(operation["arguments"])})
        return {"id": f"response-{self.task}-{self.sends}", "model": "offline-fixture-model", "status": "completed",
                "service_tier": "default", "output": output,
                "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}}


def prepare(tmp_path, *, turns=3, edit=None):
    state, case, inputs, config = fixture(tmp_path, turns=turns)
    if edit:
        edit(config)
    run = tmp_path / "run"
    before = state.read_bytes()
    prepared = c.prepare_c_analysis_wave(run, state, case, inputs, config, admission_root=tmp_path / "admission")
    return run, prepared, before


def adapters(first=None, second=None):
    sync = threading.Barrier(2)
    operations = [write(GOOD), analyze(GOOD), None]
    return {"c-task-1": Fake("c-task-1", first or operations, sync),
            "c-task-2": Fake("c-task-2", second or operations, sync),
            "reviewer": Fake("reviewer", [None])}


def step(run, status, transports):
    return c.execute_c_analysis_wave_step(run, transports, expected_checkpoint=status["checkpoint_sha256"])


def sandbox():
    capability = probe_sandbox()
    if not capability.available:
        pytest.skip(capability.reason)


def test_readonly_analysis_fresh_process_status_and_fresh_merge(tmp_path):
    sandbox()
    run, status, original_bytes = prepare(tmp_path)
    transports = adapters()
    status = step(run, status, transports)
    assert status["state"] == "paused", status
    command = [sys.executable, "-B", "-I", str(SCRIPTS / "c_parallel_analysis.py"), "status", "--run-dir", str(run)]
    reopened = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert reopened.returncode == 0, reopened.stdout + reopened.stderr
    observed = json.loads(reopened.stdout)
    assert observed["checkpoint_sha256"] == status["checkpoint_sha256"]
    assert observed["execution_profile"] == "parallel_analysis_wave_v1"
    status = step(run, status, transports)
    assert status["state"] == "paused", status
    status = step(run, status, transports)
    assert status["state"] == "completed", status
    assert status["completed_requests"] == status["budget"]["request_count"] == 7
    assert status["tool_calls_completed"] == 4 and status["budget"]["settled_tokens"] == 49
    merged = status["merge_result"]
    assert len(merged["analysis_artifacts"]) == 2 and merged["missing_or_stale_tasks"] == []
    for entry in merged["analysis_artifacts"]:
        metrics = Path(entry["metrics_path"])
        assert json.loads(metrics.read_bytes()) == {"public_fixture_value": 1}
        assert c._sha(metrics.read_bytes()) == entry["metrics_sha256"]
        provenance = json.loads(Path(entry["provenance_path"]).read_bytes())
        assert provenance["analysis_script_sha256"] == c._sha(GOOD.encode())
        assert provenance["global_ordinal"] == entry["global_ordinal"]
        assert provenance["empirical_support_verified"] is provenance["formal_cell_executed"] is False
    assert (tmp_path / "state.json").read_bytes() == original_bytes
    assert "PRIVATE-" not in json.dumps(transports["reviewer"].payloads)
    assert "function_call_output" not in json.dumps(transports["reviewer"].payloads)
    assert c.read_c_analysis_wave_status(run)["state"] == "completed"


def test_failed_analysis_cas_repair_no_budget_reset(tmp_path):
    sandbox()
    run, status, _ = prepare(tmp_path, turns=5)
    first = [write(BAD), analyze(BAD), replace(BAD, GOOD), analyze(GOOD), None]
    report = {"name": "development_method", "arguments": {"request": json.dumps({
        "op": "write", "path": "report.md", "offset": 0, "content": "Public repair fixture."})}}
    second = [write(GOOD), analyze(GOOD), report, analyze(GOOD), None]
    transports = adapters(first, second)
    checkpoints = []
    for _ in range(5):
        status = step(run, status, transports)
        assert status["state"] in {"paused", "completed"}, status
        checkpoints.append(status["checkpoint_sha256"])
    assert status["state"] == "completed"
    assert len(set(checkpoints)) == 5 and status["completed_requests"] == 11
    assert status["tool_calls_completed"] == 8 and status["budget"]["settled_tokens"] == 77
    broker = AnalysisParallelToolBroker(run, json.loads((run / "plan.json").read_bytes())["branch_manifest"])
    analyzed = [op for op in broker.operations() if op["profile"] == "analysis_readonly"]
    assert analyzed[0]["terminal"]["analysis_status"] == "invalid_json"
    assert all(broker.current_metrics(task) is not None for task in ("c-task-1", "c-task-2"))
    assert len(status["merge_result"]["analysis_artifacts"]) == 2


@pytest.mark.parametrize("mutation", ["source_cas", "report_write"])
def test_work_change_makes_old_metrics_stale_not_exported(tmp_path, mutation):
    sandbox()
    run, status, _ = prepare(tmp_path, turns=4)
    newer = "print('{\"public_fixture_value\":2}')\n"
    change = replace(GOOD, newer) if mutation == "source_cas" else {
        "name": "development_method", "arguments": {"request": json.dumps({
            "op": "write", "path": "report.md", "offset": 0, "content": "Changed after analysis."})}}
    transports = adapters([write(GOOD), analyze(GOOD), change, None],
                          [write(GOOD), analyze(GOOD), change, None])
    for _ in range(4):
        status = step(run, status, transports)
        assert status["state"] in {"paused", "completed"}, status
    assert status["merge_result"]["analysis_artifacts"] == []
    assert status["merge_result"]["missing_or_stale_tasks"] == ["c-task-1", "c-task-2"]
    assert not (run / "merge/analysis").exists()


@pytest.mark.parametrize("bad", ["bool", "profile", "requests"])
def test_invalid_config_no_branch_preparation(tmp_path, bad):
    state, case, inputs, config = fixture(tmp_path)
    if bad == "bool":
        config["max_tool_calls"] = True
    elif bad == "profile":
        config["extra"] = "unsafe"
    else:
        config["max_model_requests"] = 2
    with pytest.raises(ValueError):
        c.prepare_c_analysis_wave(tmp_path / "run", state, case, inputs, config, admission_root=tmp_path / "admission")
    assert not (tmp_path / "run").exists() and not (tmp_path / "run-branches").exists()


def test_cli_has_no_provider_option_or_auth_dependency(tmp_path):
    command = [sys.executable, "-B", "-I", str(SCRIPTS / "c_parallel_analysis.py"), "step",
               "--run-dir", str(tmp_path / "run"), "--expected-checkpoint", "0" * 64, "--provider", "openai"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    assert "--local-http-fixture" in result.stderr
