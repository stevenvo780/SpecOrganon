"""Observer orchestration negatives; synthetic snapshots are not native runs."""
from __future__ import annotations

import copy
from contextlib import nullcontext
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import observed_coordinated_runtime as observer
import coordinated_observation_journal as journal_module
pytest_plugins = ["test_measure_coordinated_runtime"]


def call_for(role="leader", request=None):
    request = request or {"model": "fixture", "input": [], "max_output_tokens": 8, "service_tier": "default"}
    count, send = observer._payloads(request)
    return {"role": role, "request_id": role + "-turn-0001",
            "request_sha256": observer.runtime._sha(observer._json_bytes(request)),
            "count_payload_sha256": observer.runtime._sha(observer._json_bytes(count)),
            "send_payload_sha256": observer.runtime._sha(observer._json_bytes(send))}, count, send


def new_journal(tmp_path):
    return observer.ObservationJournal.create(tmp_path / "observation", {
        "run_dir": str(tmp_path / "run"), "run_id": "fixture-run", "plan_sha256": "a" * 64,
        "schedule_sha256": "b" * 64, "initial_checkpoint_sha256": "c" * 64,
        "observer_source_digests": {"scripts/observed_coordinated_runtime.py": "d" * 64}})


def test_original_http_adapter_is_observed_once_via_protocol_proxy(tmp_path, monkeypatch):
    journal = new_journal(tmp_path)
    call, count, send = call_for()
    token = journal.begin_step("c" * 64, [call])
    seen = []
    def post(self, endpoint, payload):
        seen.append((endpoint, payload, self._timeout))
        return {"object": "response.input_tokens", "input_tokens": 5} if endpoint.endswith("input_tokens") else {"id": "fixture"}
    monkeypatch.setattr(observer.OpenAIResponsesHTTP, "_post", post)
    original = observer.OpenAIResponsesHTTP("public-synthetic-no-credential", base_url="http://127.0.0.1:1/v1")
    proxy = observer.ObservedTransport(original, journal, token, call)
    assert not isinstance(proxy, observer.OpenAIResponsesHTTP)
    deadline = time.monotonic() + 5
    assert observer.wave._RemainingTransport(proxy, deadline).operation("count_input", count) == 5
    assert observer.wave._RemainingTransport(proxy, deadline).operation("send", send) == {"id": "fixture"}
    journal.end_step(token, "e" * 64, "completed")
    report = journal.finish("f" * 64)
    assert [item[0] for item in seen] == ["/responses/input_tokens", "/responses"]
    assert all(0 < item[2] <= 5 for item in seen)
    assert report["metrics"]["by_kind"]["count_input"]["completed_intervals"] == 1
    assert report["metrics"]["by_kind"]["send"]["completed_intervals"] == 1


def test_journal_io_consumes_transport_timeout(tmp_path, monkeypatch):
    journal = new_journal(tmp_path)
    call, count, _ = call_for()
    token = journal.begin_step("c" * 64, [call])
    begin = journal.begin_operation
    def delayed(*args):
        time.sleep(0.025)
        return begin(*args)
    monkeypatch.setattr(journal, "begin_operation", delayed)
    remaining = []
    original = SimpleNamespace(count_input=lambda _payload, *, timeout_seconds: remaining.append(timeout_seconds) or 5)
    assert observer.ObservedTransport(original, journal, token, call).count_input(count, timeout_seconds=1) == 5
    assert 0 < remaining[0] < 0.98
    journal.fail_step(token)


def test_expiry_during_observation_does_not_delegate(tmp_path, monkeypatch):
    journal = new_journal(tmp_path)
    call, count, _ = call_for()
    token = journal.begin_step("c" * 64, [call])
    begin = journal.begin_operation
    def delayed(*args):
        time.sleep(0.015)
        return begin(*args)
    monkeypatch.setattr(journal, "begin_operation", delayed)
    original = SimpleNamespace(count_input=lambda *_args, **_kwargs: pytest.fail("expired request delegated"))
    with pytest.raises(observer.ObservationError, match="observed transport failed"):
        observer.ObservedTransport(original, journal, token, call).count_input(count, timeout_seconds=0.001)
    journal.fail_step(token)
    assert journal.report()["state"] == "uncertain"


def test_transport_error_does_not_export_exception_material(tmp_path):
    journal = new_journal(tmp_path)
    call, count, _ = call_for()
    token = journal.begin_step("c" * 64, [call])
    def fail(*_args, **_kwargs):
        raise ValueError("PRIVATE-ERROR-MATERIAL")
    with pytest.raises(observer.ObservationError) as error:
        observer.ObservedTransport(SimpleNamespace(count_input=fail), journal, token, call).count_input(count, timeout_seconds=5)
    journal.fail_step(token)
    assert "PRIVATE-" not in str(error.value) + json.dumps(journal.report())


def test_payload_mismatch_rejects_before_delegate(tmp_path):
    journal = new_journal(tmp_path)
    call, _, _ = call_for()
    token = journal.begin_step("c" * 64, [call])
    original = SimpleNamespace(count_input=lambda *_args, **_kwargs: pytest.fail("mismatched payload delegated"))
    with pytest.raises(observer.ObservationError, match="payload differs"):
        observer.ObservedTransport(original, journal, token, call).count_input({}, timeout_seconds=5)
    assert len(journal.report()["events"]) == 2
    journal.fail_step(token)


def test_guard_instruments_actual_broker_once_without_global_patch(tmp_path, monkeypatch):
    journal = new_journal(tmp_path)
    call, count, send = call_for()
    token = journal.begin_step("c" * 64, [call])
    original = SimpleNamespace(count_input=lambda *_args, **_kw: 5, send=lambda *_args, **_kw: {})
    proxy = observer.ObservedTransport(original, journal, token, call)
    proxy.count_input(count, timeout_seconds=5)
    proxy.send(send, timeout_seconds=5)
    seen = []
    class Broker:
        def invoke(self, *args):
            seen.append(args)
            guard(plan, {}, self)  # Native invoke calls the guard again.
            return {"type": "function_call_output", "call_id": "fixture", "output": "PRIVATE-TOOL-OUTPUT"}
    native_method = Broker.invoke
    broker = Broker()
    plan = {"run_id": "fixture-run"}
    sources = {"scripts/observed_coordinated_runtime.py": "d" * 64}
    monkeypatch.setattr(observer.runtime, "guard_coordinated_runtime", lambda *_args: None)
    monkeypatch.setattr(observer, "_source_digests", lambda: sources)
    guard = observer._instrument_guard(journal, token, {"run_id": "fixture-run",
        "plan_sha256": observer.runtime._sha(observer._canonical(plan)), "observer_source_digests": sources})
    guard(plan, {}, broker)
    wrapped = broker.invoke
    guard(plan, {}, broker)
    assert broker.invoke is wrapped and Broker.invoke is native_method
    result = broker.invoke("leader", call["request_id"], {"name": "fixture", "call_id": "fixture", "arguments": "{}"}, None, guard)
    assert result["type"] == "function_call_output" and len(seen) == 1
    journal.end_step(token, "e" * 64, "completed")
    assert journal.report()["metrics"]["by_kind"]["tool"]["completed_intervals"] == 1
    assert "PRIVATE-" not in json.dumps(journal.report())


@pytest.mark.parametrize("state,cursor,requests,tools", [("completed", 4, 4, 2), ("paused", 1, 1, 0),
                                                       ("prepared", True, 0, 0), ("prepared", 0, 1, 0)])
def test_no_retrospective_release(tmp_path, monkeypatch, state, cursor, requests, tools):
    status = {"budget": {"request_count": requests}, "tool_calls_completed": tools}
    def native(_run, *, expected_checkpoint, visitor):
        return visitor({}, {"state": state, "cursor": cursor}, status, [])
    monkeypatch.setattr(observer, "_native_snapshot", native)
    with pytest.raises(observer.ObservationError, match="untouched prepared"):
        observer.release_observation(tmp_path / "run", tmp_path / "observation", expected_checkpoint="c" * 64)
    assert not (tmp_path / "observation").exists()


def test_observation_cannot_live_inside_native_tree(tmp_path):
    plan = {"case_dir": str(tmp_path / "case"), "inputs_dir": str(tmp_path / "inputs"),
            "context": json.dumps({"wrapper_binding": {"profile": observer.runtime.PROFILE, "bundle": str(tmp_path / "bundle")}})}
    for directory in (tmp_path, tmp_path / "run/observer", tmp_path / "case", tmp_path / "bundle/logs"):
        with pytest.raises(observer.ObservationError, match="overlaps"):
            observer._separate(directory, tmp_path / "run", plan)
    observer._separate(tmp_path / "observer", tmp_path / "run", plan)


@pytest.mark.parametrize("receipt_kind", ["delegation", "merge", "delivery"])
def test_snapshot_rejects_changed_bound_receipts_before_visitor(tmp_path, monkeypatch, receipt_kind):
    monkeypatch.setattr(observer, "_run_lock", lambda _path: nullcontext())
    monkeypatch.setattr(observer, "_private_dir", lambda _path: None)
    monkeypatch.setattr(observer, "_private_file", lambda _path: None)
    monkeypatch.setattr(observer.runtime, "guard_coordinated_runtime", lambda *_args: None)
    monkeypatch.setattr(observer.engine, "_audit", lambda *_args: None)
    state = {"state": "completed" if receipt_kind == "delivery" else "paused", "delegations": [], "merges": [], "delivery": {}}
    if receipt_kind == "delegation":
        state["delegations"] = [{"activation": {}}]
    elif receipt_kind == "merge":
        state["merges"] = [{"receipt": {}}]
    monkeypatch.setattr(observer.engine, "_load", lambda _path: ({}, state, None, None, None))
    def reject(*_args):
        raise observer.ObservationError("bound receipt changed")
    monkeypatch.setattr(observer.engine, "_bound_receipt", reject)
    with pytest.raises(observer.ObservationError, match="bound receipt changed"):
        observer._native_snapshot(tmp_path / "run", visitor=lambda *_args: pytest.fail("unbound receipt reached visitor"))


@pytest.fixture
def observed_snapshot(tmp_path, monkeypatch, snapshot):
    """Construct a replayed synthetic journal around the D120 pure fixture."""
    value = copy.deepcopy(snapshot)
    for name, raw in value["journals"]["receipts"].items():
        receipt = json.loads(raw)
        receipt.update(send_started_ns=0, send_ended_ns=10**15)
        value["journals"]["receipts"][name] = observer._canonical(receipt)
    for name, raw in value["journals"]["tool_receipts"].items():
        receipt = json.loads(raw)
        receipt["output"] = "PRIVATE-TOOL-SENTINEL"
        value["journals"]["tool_receipts"][name] = observer._canonical(receipt)
    clock = [0]
    def sample():
        clock[0] += 10**9
        return {"monotonic_ns": clock[0], "wall_ns": clock[0], "boot_sha256": "e" * 64}
    monkeypatch.setattr(journal_module, "_sample", sample)
    plan = json.loads(value["documents"]["plan"])
    binding = {"run_dir": str(tmp_path / "run"), "run_id": plan["run_id"],
        "plan_sha256": observer.runtime._sha(value["documents"]["plan"]), "schedule_sha256": "a" * 64,
        "initial_checkpoint_sha256": "c" * 64, "observer_source_digests": {"scripts/observed_coordinated_runtime.py": "d" * 64}}
    journal = observer.ObservationJournal.create(tmp_path / "observation", binding)
    for role in observer.runtime.ROLES:
        request_id = role + "-turn-0001"
        request = json.loads(value["journals"]["requests"][request_id + ".json"])
        response = json.loads(value["journals"]["responses"][request_id + ".json"])
        call, _, _ = call_for(role, request)
        token = journal.begin_step(journal.report()["checkpoint_sha256"], [call])
        for kind, result in (("count_input", 10), ("send", response)):
            op = journal.begin_operation(token, kind, role, request_id, call[observer._payload_key(kind)])
            journal.end_operation(token, op, result_sha256=observer.runtime._sha(observer._canonical(result)),
                                  input_tokens=result if kind == "count_input" else None)
        function = next((item for item in response["output"] if item.get("type") == "function_call"), None)
        if function:
            function = {key: function[key] for key in ("name", "call_id", "arguments")}
            op = journal.begin_operation(token, "tool", role, request_id, observer.runtime._sha(observer._json_bytes(function)))
            result = {"type": "function_call_output", "call_id": function["call_id"], "output": "PRIVATE-TOOL-SENTINEL"}
            journal.end_operation(token, op, result_sha256=observer.runtime._sha(observer._canonical(result)))
        journal.end_step(token, "b" * 64, "completed" if role == "reviewer" else "paused")
    _, digest = observer._coverage(value, journal.report())
    return value, journal.finish(digest)


def test_final_pure_reconciliation_has_exact_sets_but_no_native_attestation(observed_snapshot):
    snapshot, observation = observed_snapshot
    report = observer._final_report(snapshot, observation)
    assert report["coverage"]["count_send_tool_exact"] is True
    assert report["coverage"]["local_release_to_delivery"] is True
    assert report["native_D119_guard_replay_publication_verified"] is False
    assert "PRIVATE-" not in json.dumps(report)
    assert not report["formal_cell_executed"] and not report["Q_demonstrated"]


@pytest.mark.parametrize("kind", ["missing", "duplicate", "count", "response", "tool", "role", "containment", "delivery"])
def test_final_reconciliation_rejects_native_observation_disagreement(observed_snapshot, kind):
    snapshot, observation = copy.deepcopy(observed_snapshot)
    start = next(event for event in observation["events"] if event["type"] == "operation_begin" and event["data"]["kind"] == "send")
    end = next(event for event in observation["events"] if event["type"] == "operation_end" and event["data"]["op_id"] == start["data"]["op_id"])
    if kind == "missing":
        observation["events"].remove(start)
    elif kind == "duplicate":
        observation["events"].insert(3, copy.deepcopy(start))
    elif kind == "count":
        next(event for event in observation["events"] if event["type"] == "operation_end" and event["data"]["input_tokens"] is not None)["data"]["input_tokens"] = True
    elif kind == "response":
        end["data"]["result_sha256"] = "0" * 64
    elif kind == "tool":
        next(event for event in observation["events"] if event["type"] == "operation_begin" and event["data"]["kind"] == "tool")["data"]["payload_sha256"] = "0" * 64
    elif kind == "role":
        start["data"]["role"] = "reviewer"
    elif kind == "containment":
        start["monotonic_ns"] = -1
    else:
        observation["events"][-1]["data"]["measurement_sha256"] = "0" * 64
    with pytest.raises(observer.ObservationError):
        observer._final_report(snapshot, observation)
