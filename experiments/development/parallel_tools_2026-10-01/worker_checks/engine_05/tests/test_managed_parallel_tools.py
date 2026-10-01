"""Synthetic model turns with actual private sandbox tool effects."""

from __future__ import annotations

import copy
import json
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import managed_parallel_tools as tools  # noqa: E402
import managed_parallel_wave as wave  # noqa: E402
import parallel_tool_broker as broker_module  # noqa: E402
from local_replay_sandbox import probe_sandbox  # noqa: E402
from parallel_tool_broker import ParallelToolBroker, prepare_branch_manifest  # noqa: E402
from run_managed_conversation import _canonical  # noqa: E402


TOOL = '''import json,sys
from pathlib import Path
case,inputs,work=map(Path,sys.argv[1:4])
outer=json.loads(sys.argv[4]);request=json.loads(outer["request"])
(work/"answer.txt").write_text(request["content"],encoding="utf-8")
print(json.dumps({"ok":True,"method_exit_code":0,"method_state_sha256":"1"*64}))
'''


def private(path: Path) -> Path:
    path.mkdir(mode=0o700)
    return path


def plan(tmp_path: Path) -> dict:
    tmp_path.chmod(0o700)
    root = private(tmp_path / "branches")
    executable = root / "tool"
    executable.write_bytes(f"#!{sys.executable}\n{TOOL}".encode())
    executable.chmod(0o500)
    specs = []
    for number in (1, 2):
        stage = private(root / f"task-{number}")
        for name in ("case", "inputs", "work"):
            private(stage / name)
        (stage / "case/case.json").write_text('{"case_id":"public-fixture"}')
        (stage / "inputs/task.txt").write_text("Public task")
        (stage / "stage.json").write_text('{"classification":"public-fixture"}')
        specs.append({"task_id": f"task-{number}", "owned_node_ids": [f"node-{number}"],
                      "stage_dir": stage, "functions": [{"name": "method", "executable": executable,
                                                         "profile": "workspace"}]})
    return {"schema": 2, "execution_profile": tools.PROFILE, "run_id": "tool-wave-public-fixture",
            "model": "offline-fixture-model", "effort": "medium",
            "price_profile": {"model": "offline-fixture-model", "input_rate_micro_usd_per_million": 1000000,
                              "cached_input_rate_micro_usd_per_million": 1000000,
                              "cache_write_rate_micro_usd_per_million": 1000000,
                              "output_rate_micro_usd_per_million": 1000000},
            "limit_tokens": 1000, "max_model_requests": 5, "cost_limit_micro_usd": 1000,
            "active_limit_seconds": 30, "context": "Common public facts; norms pending.",
            "tasks": [{"task_id": f"task-{n}", "role": f"worker-{n}", "user": f"Work scope {n}.",
                       "owned_node_ids": [f"node-{n}"], "max_output_tokens": 20,
                       "max_model_turns": 2} for n in (1, 2)],
            "reviewer": {"user": "Review artifacts, no approval.", "max_output_tokens": 20},
            "functions": [{"type": "function", "name": "method", "description": "Private branch method",
                           "strict": True, "parameters": {"type": "object", "additionalProperties": False,
                            "properties": {"request": {"type": "string"}}, "required": ["request"]}}],
            "branch_manifest": prepare_branch_manifest(root, specs), "max_tool_calls": 2,
            "tool_wall_seconds": 5}


def response(task_id: str, call: bool = False) -> dict:
    output = [{"type": "reasoning", "encrypted_content": "PRIVATE-" + task_id, "summary": []}]
    if call:
        output.append({"type": "function_call", "name": "method", "call_id": "call-" + task_id,
                       "arguments": json.dumps({"request": json.dumps({"op": "write", "content": task_id})}),
                       "status": "completed"})
    else:
        output.append({"type": "message", "role": "assistant", "status": "completed", "content": [
            {"type": "output_text", "text": "Public result " + task_id}]})
    return {"id": "response-" + task_id, "model": "offline-fixture-model", "status": "completed",
            "service_tier": "default", "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
            "output": output}


class Fake:
    def __init__(self, task_id: str, barrier=None):
        self.task_id, self.barrier = task_id, barrier
        self.counts = self.sends = 0
        self.payloads = []
        self.hook = None
        self.result = None
        self.call_first = task_id != "reviewer"

    def count_input(self, payload: dict, *, timeout_seconds: float) -> int:
        assert timeout_seconds > 0
        self.counts += 1
        return 5

    def send(self, payload: dict, *, timeout_seconds: float) -> dict:
        assert timeout_seconds > 0
        self.sends += 1
        self.payloads.append(copy.deepcopy(payload))
        if self.barrier:
            self.barrier.wait(5)
        if self.hook:
            self.hook(payload)
        return copy.deepcopy(self.result or response(self.task_id, self.call_first and self.sends == 1))


def prepare(tmp_path: Path, edit=None):
    source = plan(tmp_path)
    if edit:
        edit(source)
    directory = tmp_path / "run"
    status = tools.prepare_tool_wave(directory, source, admission_root=tmp_path / "admission")
    sync = threading.Barrier(2)
    adapters = {name: Fake(name, sync if name != "reviewer" else None)
                for name in ("task-1", "task-2", "reviewer")}
    return directory, status, adapters


def step(directory, status, adapters, **kwargs):
    def fixture_merge(plan, state, broker, context, guard):
        guard()
        effects = []
        for task in plan["tasks"]:
            work = Path(broker.branch(task["task_id"])["stage_dir"]) / "work"
            files = [{"name": path.name, "sha256": wave._sha(path.read_bytes())}
                     for path in sorted(work.iterdir()) if path.is_file()]
            effects.append({"task_id": task["task_id"], "files": files})
        value = {"classification": "synthetic_fixture_branch_effect_merge",
                 "operations": len(broker.operations()), "branch_effects": effects}
        target = directory / "merge/fixture.json"
        tools._new_private_file(target, _canonical(value))
        guard()
        return {"path": str(target), "sha256": wave._sha(target.read_bytes()),
                "classification": "synthetic_fixture_branch_effect_merge"}
    kwargs.setdefault("merge", fixture_merge)
    return tools.execute_tool_wave_step(directory, adapters, expected_checkpoint=status["checkpoint_sha256"], **kwargs)


def sandbox():
    capability = probe_sandbox()
    if not capability.available:
        pytest.skip(capability.reason)


def test_two_real_branches_pause_resume_same_budget_and_private_review(tmp_path):
    sandbox()
    directory, status, adapters = prepare(tmp_path)
    first = step(directory, status, adapters)
    assert first["state"] == "paused", first
    assert first["completed_requests"] == first["tool_calls_completed"] == 2
    assert first["artifact_count"] == 0 and first["merge_result"] is None
    assert first["budget"]["settled_tokens"] == 14
    assert tools.read_tool_wave_status(directory)["checkpoint_sha256"] == first["checkpoint_sha256"]
    broker = ParallelToolBroker(directory, json.loads((directory / "plan.json").read_bytes())["branch_manifest"])
    for task_id in ("task-1", "task-2"):
        assert (Path(broker.branch(task_id)["stage_dir"]) / "work/answer.txt").read_text() == task_id
    receipts = [json.loads((directory / "receipts" / f"task-{n}-turn-0001.json").read_bytes()) for n in (1, 2)]
    assert max(r["send_started_ns"] for r in receipts) < min(r["send_ended_ns"] for r in receipts)
    with pytest.raises(ValueError):
        step(directory, status, adapters)
    assert sum(t.sends for t in adapters.values()) == 2

    def merge(plan, state, broker, context, guard):
        guard()
        target = directory / "merge/result.json"
        tools._new_private_file(target, _canonical({"operations": len(broker.operations())}))
        guard()
        return {"path": str(target), "sha256": wave._sha(target.read_bytes())}

    final = step(directory, first, adapters, merge=merge)
    assert final["state"] == "completed", final
    assert final["completed_requests"] == final["budget"]["request_count"] == 5
    assert final["budget"]["settled_tokens"] == 35
    assert final["artifact_count"] == 3 and final["tool_calls_completed"] == 2
    assert final["context"]["active_seconds"] >= first["context"]["active_seconds"] > 0
    assert tools.read_tool_wave_status(directory)["state"] == "completed"
    assert "PRIVATE-task-1" in json.dumps(adapters["task-1"].payloads[1])
    assert "PRIVATE-task-2" not in json.dumps(adapters["task-1"].payloads[1])
    review = adapters["reviewer"].payloads[0]
    assert "PRIVATE-" not in json.dumps(review) and "function_call_output" not in json.dumps(review)
    assert "tools" not in review and "Public result task-1" in json.dumps(review)
    assert (directory / "publication.json").is_file()


@pytest.mark.parametrize("bad", ["identity", "schema", "extra", "bool", "functions", "turns", "tools", "wall"])
def test_strict_optin_validation_before_run_creation(tmp_path, bad):
    source = plan(tmp_path)
    if bad == "identity":
        source["run_id"] = "wave-old-identity"
    elif bad == "schema":
        source["schema"] = 1
    elif bad == "extra":
        source["approval"] = True
    elif bad == "bool":
        source["max_tool_calls"] = True
    elif bad == "functions":
        source["functions"][0]["executable"] = "/not/provider/field"
    elif bad == "turns":
        source["tasks"][0]["max_model_turns"] = True
    elif bad == "tools":
        source["max_tool_calls"] = 65
    else:
        source["tool_wall_seconds"] = 301
    with pytest.raises(ValueError):
        tools.prepare_tool_wave(tmp_path / "run", source, admission_root=tmp_path / "admission")
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("cap", ["tools", "turns", "requests"])
def test_shared_caps_block_effects_without_reset(tmp_path, cap):
    sandbox()
    def edit(source):
        if cap == "tools":
            source["max_tool_calls"] = 1
        elif cap == "turns":
            source["tasks"][0]["max_model_turns"] = 1
        else:
            source["max_model_requests"] = 3
    directory, status, adapters = prepare(tmp_path, edit)
    first = step(directory, status, adapters)
    if cap == "requests":
        assert first["state"] == "paused", first
        result = step(directory, first, adapters)
        assert result["budget"]["request_count"] == 2
    else:
        result = first
        assert not list((directory / "tool_reservations").iterdir())
    assert result["state"] == "indeterminate" and result["artifact_count"] == 0


def test_repeated_call_ids_rejected_before_any_tool(tmp_path):
    directory, status, adapters = prepare(tmp_path)
    adapters["task-2"].result = response("task-2", True)
    adapters["task-2"].result["output"][-1]["call_id"] = "call-task-1"
    result = step(directory, status, adapters)
    assert result["state"] == "indeterminate"
    assert not list((directory / "tool_reservations").iterdir())


@pytest.mark.parametrize("changed", ["history", "work", "source"])
def test_pause_checkpoint_tamper_rejects_before_transport(tmp_path, monkeypatch, changed):
    sandbox()
    directory, status, adapters = prepare(tmp_path)
    paused = step(directory, status, adapters)
    assert paused["state"] == "paused", paused
    if changed == "history":
        path = directory / "histories/task-1/run.json"
        path.write_bytes(path.read_bytes() + b"\n")
    elif changed == "work":
        (tmp_path / "branches/task-1/work/answer.txt").write_text("tampered")
    else:
        original = tools._sources()
        monkeypatch.setattr(tools, "_sources", lambda: {**original, "new": "0" * 64})
    before = sum(t.counts + t.sends for t in adapters.values())
    with pytest.raises(ValueError):
        step(directory, paused, adapters)
    assert sum(t.counts + t.sends for t in adapters.values()) == before


def test_tool_reviewer_rejected_raw_preserved_no_publication(tmp_path):
    directory, status, adapters = prepare(tmp_path)
    for name in ("task-1", "task-2"):
        adapters[name].call_first = False
    adapters["reviewer"].result = response("reviewer", True)
    result = step(directory, status, adapters)
    assert result["state"] == "indeterminate" and result["artifact_count"] == 0
    assert (directory / "responses/reviewer-turn-0001.json").exists()
    assert not (directory / "publication.json").exists()


@pytest.mark.parametrize("failure", ["finish", "publication"])
def test_final_commit_failure_never_publishes_or_reexecutes(tmp_path, monkeypatch, failure):
    directory, status, adapters = prepare(tmp_path)
    for name in ("task-1", "task-2"):
        adapters[name].call_first = False
    if failure == "finish":
        def fail(*args):
            raise OSError("injected final commit failure")
        monkeypatch.setattr(tools.RunContext, "finish", fail)
    else:
        original = tools._new_private_file
        def fail(path, raw):
            if path.name == "publication.json":
                raise OSError("injected publication failure")
            return original(path, raw)
        monkeypatch.setattr(tools, "_new_private_file", fail)
    result = step(directory, status, adapters)
    assert result["state"] == "indeterminate" and result["artifact_count"] == 0
    assert result["merge_result"] is None and not (directory / "publication.json").exists()
    assert tools.read_tool_wave_status(directory)["state"] == "indeterminate"
    with pytest.raises(ValueError):
        step(directory, result, adapters)


def test_deadline_late_callback_no_journal_effects(tmp_path):
    directory, status, adapters = prepare(tmp_path, lambda p: p.update(active_limit_seconds=2))
    entered, release = threading.Event(), threading.Event()
    for adapter in adapters.values():
        adapter.barrier = None
    def block(payload):
        entered.set()
        release.wait(8)
    adapters["task-2"].hook = block
    start = time.monotonic()
    result = step(directory, status, adapters)
    assert entered.is_set() and result["state"] == "indeterminate"
    assert time.monotonic() - start < 4
    assert not list((directory / "tool_reservations").iterdir())
    before = {str(p): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    release.set()
    time.sleep(0.1)
    assert before == {str(p): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


def test_legacy_profile_still_rejects_tool_fields(tmp_path):
    source = plan(tmp_path)
    source.update(schema=1, execution_profile=wave.PROFILE, run_id="wave-legacy")
    with pytest.raises(wave.ParallelWaveError):
        wave.prepare_wave(tmp_path / "run", source, admission_root=tmp_path / "admission")
    assert not (tmp_path / "run").exists()


def test_source_cache_detects_changed_bytes_and_new_local_import(tmp_path, monkeypatch):
    source = tmp_path / "runner.py"
    source.write_text("import helper\nimport future\n")
    (tmp_path / "helper.py").write_text("VALUE=1\n")
    monkeypatch.setattr(tools, "__file__", str(source))
    monkeypatch.setattr(tools, "_SOURCE_CACHE", None)
    first = tools._sources()
    original = tools.ast.parse
    monkeypatch.setattr(tools.ast, "parse", lambda raw: pytest.fail("unchanged closure reparsed"))
    assert tools._sources() == first
    monkeypatch.setattr(tools.ast, "parse", original)
    (tmp_path / "future.py").write_text("VALUE=2\n")
    second = tools._sources()
    assert "scripts/future.py" in second and second != first
    (tmp_path / "helper.py").write_text("VALUE=3\n")
    assert tools._sources()["scripts/helper.py"] != first["scripts/helper.py"]


def test_interrupted_tool_reservation_stays_pending_and_never_resumes(tmp_path, monkeypatch):
    directory, status, adapters = prepare(tmp_path)
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt("injected sandbox interruption after durable reserve")
    monkeypatch.setattr(broker_module, "run_sandboxed", interrupt)
    with pytest.raises(KeyboardInterrupt):
        step(directory, status, adapters)
    assert len(list((directory / "tool_reservations").iterdir())) == 1
    assert not list((directory / "tool_receipts").iterdir())
    observed = tools.read_tool_wave_status(directory)
    assert observed["state"] == "indeterminate" and observed["artifact_count"] == 0
    before = sum(t.counts + t.sends for t in adapters.values())
    with pytest.raises(ValueError):
        step(directory, observed, adapters)
    assert sum(t.counts + t.sends for t in adapters.values()) == before


def test_current_raw_tampered_after_batch_rejects_before_tools(tmp_path, monkeypatch):
    directory, status, adapters = prepare(tmp_path)
    original = wave._batch
    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        path = directory / "responses/task-1-turn-0001.json"
        raw = json.loads(path.read_bytes())
        raw["output"][-1]["arguments"] = json.dumps({"request": json.dumps({"op": "write", "content": "changed"})})
        path.write_bytes(_canonical(raw))
        # Even changing the outer receipt cannot change the settled ledger pin.
        receipt_path = directory / "receipts/task-1-turn-0001.json"
        receipt = json.loads(receipt_path.read_bytes())
        receipt["response_sha256"] = wave._sha(path.read_bytes())
        receipt_path.write_bytes(_canonical(receipt))
        return result
    monkeypatch.setattr(wave, "_batch", mutate)
    result = step(directory, status, adapters)
    assert result["state"] == "indeterminate"
    assert "replay differs" in result["reason"]
    assert not list((directory / "tool_reservations").iterdir())


def test_active_history_tamper_blocks_batch_before_tools(tmp_path):
    directory, status, adapters = prepare(tmp_path)
    path = directory / "histories/task-1/run.json"
    def mutate(payload):
        path.write_bytes(_canonical({"history": [{"role": "user", "content": "changed private context"}]}))
    adapters["task-1"].hook = mutate
    result = step(directory, status, adapters)
    assert result["state"] == "indeterminate"
    assert not list((directory / "tool_reservations").iterdir())


def test_missing_merge_rejected_before_lease_claim_count_or_tools(tmp_path):
    directory, status, adapters = prepare(tmp_path)
    before = (directory / "run.json").read_bytes()
    with pytest.raises(tools.ParallelToolsError, match="merge callback is required"):
        tools.execute_tool_wave_step(directory, adapters, expected_checkpoint=status["checkpoint_sha256"])
    assert (directory / "run.json").read_bytes() == before
    current = tools.read_tool_wave_status(directory)
    assert current["state"] == "prepared" and current["checkpoint_sha256"] == status["checkpoint_sha256"]
    assert current["budget"]["requests"] == {}
    assert all(adapter.counts == adapter.sends == 0 for adapter in adapters.values())
    assert not list((directory / "tool_reservations").iterdir())
    assert not list((tmp_path / "admission").glob("claims/*"))
