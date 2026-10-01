"""Pure journal reconciliation and mocked native-reader orchestration.

These snapshots are synthetic unit controls, not real D119 runtime acceptance.
"""
from __future__ import annotations

import copy
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import measure_coordinated_runtime as reader


def seal(snapshot, kind, name, value):
    snapshot["journals"][kind][name] = reader._canonical(value)


def document(snapshot, name):
    return json.loads(snapshot["documents"][name])


def sync_budget(snapshot):
    ledger = document(snapshot, "ledger")
    ledger["requests"] = copy.deepcopy(snapshot["budget"]["requests"])
    snapshot["documents"]["ledger"] = reader._canonical(ledger)
    snapshot["budget"]["ledger_sha256"] = reader._sha(snapshot["documents"]["ledger"])
    snapshot["status"]["budget"] = {key: copy.deepcopy(value) for key, value in snapshot["budget"].items()
                                     if key != "ledger_sha256"}


def sync_response(snapshot, request_id, response):
    name = request_id + ".json"
    seal(snapshot, "responses", name, response)
    record = snapshot["budget"]["requests"][request_id]
    record["response_sha256"] = reader._sha(snapshot["journals"]["responses"][name])
    receipt = json.loads(snapshot["journals"]["receipts"][name])
    receipt["response_sha256"] = record["response_sha256"]
    receipt["settled"] = copy.deepcopy(record)
    seal(snapshot, "receipts", name, receipt)
    sync_budget(snapshot)


@pytest.fixture
def snapshot():
    profile = {"model": "fixture-model", "input_rate_micro_usd_per_million": 3,
               "cached_input_rate_micro_usd_per_million": 1,
               "cache_write_rate_micro_usd_per_million": 5, "output_rate_micro_usd_per_million": 2}
    coordinates = {key: "fixture" for key in reader.COORDINATES}
    coordinates.update(arm="C", mode="risk", case_id="D-E", case_reference_sha256=None,
                       agent_count=4, replica=1, order_position=1, round=1, release_block_order=1)
    plan = {"run_id": "fixture-run", "model": "fixture-model", "effort": "low", "price_profile": profile,
            "role_config": {role: {"max_output_tokens": 8} for role in reader.ROLES},
            "descriptor": {"coordinates": coordinates, "schedule_sha256": "a" * 64,
                           "model": {"price_profile_sha256": reader._sha(reader.price_bytes(profile))},
                           "provider_route": {"provider": "fixture", "api": "offline", "version": "fixture-v1", "service_tier": "default"}}}
    state = {"state": "completed", "runtime_stage": "finished", "run_id": plan["run_id"],
             "classification": reader.engine.CLASSIFICATION, "plan_sha256": reader._sha(reader._canonical(plan)),
             "completed_requests": 4, "tool_calls_completed": 2, "claim_sha256": "c" * 64,
             "broker_binding": {"sha256": "d" * 64}, "roles": {role: {"turns": 1} for role in reader.ROLES}, "timeline": []}
    context = {"state": "completed", "checkpoint_sha256": "b" * 64, "active_seconds": 3.0,
               "paused_seconds": 4.0, "held_active_seconds": 0.0, "active_limit_seconds": 100.0}
    publication = {"run_id": plan["run_id"], "plan_sha256": state["plan_sha256"],
                   "checkpoint_sha256": "b" * 64, "schedule_sha256": "a" * 64}
    result = {"documents": {}, "journals": {kind: {} for kind in reader.JOURNALS}, "streams": {}}
    records, waves = {}, {}
    for number, role in enumerate(reader.ROLES, 1):
        request_id, wave_id = role + "-turn-0001", f"wave-{number}"
        request = {"model": plan["model"], "reasoning": {"effort": "low"}, "max_output_tokens": 8,
                   "input": [{"role": "user", "content": "PRIVATE-PROMPT-SENTINEL"}]}
        output = [{"type": "message", "content": [{"type": "output_text", "text": "PRIVATE-TEXT-SENTINEL"}]}]
        if number <= 2:
            output = [{"type": "function_call", "call_id": f"call-{number}", "name": "development_method",
                       "arguments": '{"request":"PRIVATE-ARGUMENT-SENTINEL"}'}]
        response = {"id": f"response-{number}", "model": plan["model"], "status": "completed",
                    "service_tier": "default", "output": output,
                    "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}}
        if number == 1:
            response["usage"].update(input_tokens_details={"cached_tokens": 2, "cache_read_tokens": 2,
                                                          "cache_write_tokens": 1, "uncached_tokens": 3},
                                     output_tokens_details={"reasoning_tokens": 1, "private_metadata": "PRIVATE-DETAIL-SENTINEL"})
        usage, details = reader._usage(response)
        record = {"request_id": request_id, "role": role, "model": plan["model"], "effort": "low", "wave_id": wave_id,
                  "state": "settled", "payload_sha256": reader._sha(reader._json_bytes(request)),
                  "response_sha256": reader._sha(reader._canonical(response)), "input_tokens": 20,
                  "max_output_tokens": 8, "send_started_ns": 1_790_000_000_000_000_000,
                  "held_tokens": 12, "held_cost_micro_usd": reader._settled_cost(usage, details, profile),
                  "usage": usage, "usage_details": details}
        records[request_id] = record
        waves[wave_id] = {"wave_id": wave_id, "request_ids": [request_id]}
        # Identical monotonic intervals deliberately overlap: no clock union.
        receipt = {"request_id": request_id, "role": role, "classification": state["classification"],
                   "payload_sha256": record["payload_sha256"], "response_sha256": record["response_sha256"],
                   "send_started_ns": 100_000_000, "send_ended_ns": 200_000_000, "settled": record}
        for kind, value in (("requests", request), ("responses", response), ("receipts", receipt)):
            seal(result, kind, request_id + ".json", value)
        state["timeline"].append({"kind": "model", "role": role, "request_id": request_id, "turn": 1, "epoch": 1})
        if number <= 2:
            reservation = {"schema": 1, "manifest_sha256": "d" * 64, "claim_sha256": "c" * 64,
                           "task_id": role, "request_id": request_id, "call_id": f"call-{number}",
                           "function_name": "development_method", "profile": "workspace", "global_ordinal": number,
                           "local_ordinal": 1, "epoch": 1, "arguments": output[0]["arguments"],
                           "arguments_sha256": reader._sha(output[0]["arguments"].encode())}
            name = f"{number:04d}.json"
            streams = {"stdout": b"PRIVATE-STDOUT-SENTINEL", "stderr": b"PRIVATE-STDERR-SENTINEL"}
            result["streams"][name[:-5]] = streams
            terminal = {key: value for key, value in reservation.items() if key not in {"arguments", "arguments_sha256"}}
            terminal.update(reservation_sha256=reader._sha(reader._canonical(reservation)), status="success",
                            sandbox={"exit_code": 0, "timed_out": False, "launch_error": None,
                                     "duration_seconds": 0.2, "host_elapsed_seconds": 0.3})
            for key, raw in streams.items():
                terminal[key + "_sha256"], terminal[key + "_bytes"] = reader._sha(raw), len(raw)
            seal(result, "tool_reservations", name, reservation)
            seal(result, "tool_receipts", name, terminal)
    ledger = {"schema": 3, "model": plan["model"], "effort": plan["effort"], "price_profile": profile,
              "price_profile_sha256": reader._sha(reader.price_bytes(profile)), "requests": records, "waves": waves}
    for key, value in (("plan", plan), ("state", state), ("ledger", ledger), ("context", context), ("publication", publication)):
        result["documents"][key] = reader._canonical(value)
    budget = {**copy.deepcopy(ledger), "ledger_sha256": reader._sha(result["documents"]["ledger"]),
              "blocked": False, "request_count": 4, "wave_count": 4, "settled_tokens": 48, "committed_tokens": 48,
              "settled_cost_micro_usd": 4, "committed_cost_micro_usd": 4}
    budget.update({key: 0 for key in ("reserved_tokens", "inflight_tokens", "indeterminate_tokens",
                                    "reserved_cost_micro_usd", "inflight_cost_micro_usd", "indeterminate_cost_micro_usd")})
    result["budget"] = budget
    result["status"] = {"state": "completed", "publication_valid": True, "run_id": plan["run_id"],
                        "schedule_sha256": "a" * 64, "checkpoint_sha256": "b" * 64, "completed_requests": 4,
                        "tool_calls_completed": 2,
                        "context": {**context, "tools_reserved": 2}}
    sync_budget(result)
    return result


def test_token_cost_and_clock_scopes(snapshot):
    report = reader.reconcile_snapshot(snapshot)
    assert report["totals"]["input_tokens"] == 40
    assert report["totals"]["output_tokens"] == 8  # reasoning is included, not added
    assert report["totals"]["total_tokens"] == 48
    assert report["totals"]["declared_cost_micro_usd"] == 4  # ceil per request, not aggregate ceil=1
    assert report["totals"]["send_duration_ns"] == 400_000_000
    assert report["totals"]["sandbox_duration_seconds_sum"] == 0.4
    assert report["totals"]["host_elapsed_seconds_sum"] == 0.6
    assert report["totals"]["input_unclassified_tokens"] == 34
    assert report["totals"]["token_details"]["cache_read_tokens"] == {
        "known_sum": 2, "unknown_requests": 3, "complete_total": None}
    assert report["by_role"]["worker-2"]["tool_count"] == 0
    assert report["context_local_accounting"]["active_seconds"] == 3
    assert not report["coverage"]["full_activity_coverage"]
    assert not report["Q_demonstrated"] and not report["paid_route_authorized"]
    assert report["provenance"]["synthetic_route_declared"] is True
    serialized = json.dumps(report)
    assert "PRIVATE-" not in serialized
    assert "send_started_ns" not in serialized and "W_seconds" not in serialized


def test_explicit_zero_details_are_known_and_missing_are_unknown(snapshot):
    request_id = "leader-turn-0001"
    response = json.loads(snapshot["journals"]["responses"][request_id + ".json"])
    response["usage"]["input_tokens_details"] = {"cache_read_tokens": 0, "cache_write_tokens": 0, "uncached_tokens": 10}
    response["usage"]["output_tokens_details"] = {"reasoning_tokens": 0}
    _, details = reader._usage(response)
    snapshot["budget"]["requests"][request_id]["usage_details"] = details
    sync_response(snapshot, request_id, response)
    report = reader.reconcile_snapshot(snapshot)
    leader = report["by_role"]["leader"]["token_details"]
    assert leader["reasoning_tokens"] == {"known_sum": 0, "unknown_requests": 0, "complete_total": 0}
    assert leader["cache_read_tokens"]["complete_total"] == 0
    assert report["by_role"]["worker-1"]["token_details"]["reasoning_tokens"]["complete_total"] is None
    assert report["totals"]["input_unclassified_tokens"] == 30


def test_known_input_rates_and_conservative_unknown_rate(snapshot):
    plan = document(snapshot, "plan")
    profile = {**plan["price_profile"], "input_rate_micro_usd_per_million": 1_000_000,
               "cached_input_rate_micro_usd_per_million": 0, "cache_write_rate_micro_usd_per_million": 2_000_000,
               "output_rate_micro_usd_per_million": 1_000_000}
    plan["price_profile"] = profile
    price_sha = reader._sha(reader.price_bytes(profile))
    plan["descriptor"]["model"]["price_profile_sha256"] = price_sha
    snapshot["documents"]["plan"] = reader._canonical(plan)
    state, publication = document(snapshot, "state"), document(snapshot, "publication")
    state["plan_sha256"] = publication["plan_sha256"] = reader._sha(snapshot["documents"]["plan"])
    snapshot["documents"]["state"] = reader._canonical(state)
    snapshot["documents"]["publication"] = reader._canonical(publication)
    ledger = document(snapshot, "ledger")
    ledger.update(price_profile=profile, price_profile_sha256=price_sha)
    snapshot["documents"]["ledger"] = reader._canonical(ledger)
    snapshot["budget"].update(price_profile=profile, price_profile_sha256=price_sha)
    for request_id, record in snapshot["budget"]["requests"].items():
        record["held_cost_micro_usd"] = reader._settled_cost(record["usage"], record["usage_details"], profile)
        response = json.loads(snapshot["journals"]["responses"][request_id + ".json"])
        sync_response(snapshot, request_id, response)
    snapshot["budget"]["settled_cost_micro_usd"] = snapshot["budget"]["committed_cost_micro_usd"] = 81
    sync_budget(snapshot)
    report = reader.reconcile_snapshot(snapshot)
    assert report["by_role"]["leader"]["declared_cost_micro_usd"] == 15
    assert report["by_role"]["worker-1"]["declared_cost_micro_usd"] == 22
    assert report["totals"]["declared_cost_micro_usd"] == 81


def test_ledger_boolean_cannot_equal_numeric_response_usage(snapshot):
    request_id = "leader-turn-0001"
    record = snapshot["budget"]["requests"][request_id]
    record["usage_details"]["output_tokens_details"]["reasoning_tokens"] = True
    receipt = json.loads(snapshot["journals"]["receipts"][request_id + ".json"])
    receipt["settled"] = copy.deepcopy(record)
    seal(snapshot, "receipts", request_id + ".json", receipt)
    sync_budget(snapshot)
    with pytest.raises(reader.MeasurementError, match="settled usage"):
        reader.reconcile_snapshot(snapshot)


@pytest.mark.parametrize("kind", ["requests", "responses", "receipts", "tool_reservations", "tool_receipts"])
@pytest.mark.parametrize("operation", ["missing", "extra"])
def test_exact_journal_sets(snapshot, kind, operation):
    journal = snapshot["journals"][kind]
    if operation == "missing":
        journal.pop(next(iter(journal)))
    else:
        journal["phantom.json"] = reader._canonical({})
    with pytest.raises(reader.MeasurementError):
        reader.reconcile_snapshot(snapshot)


@pytest.mark.parametrize("field,value", [("request_id", "phantom"), ("role", "reviewer"),
                                          ("payload_sha256", "0" * 64), ("send_ended_ns", 1),
                                          ("send_started_ns", True), ("send_ended_ns", 200_000_000.0)])
def test_request_receipt_identity_digest_and_clock(snapshot, field, value):
    name = "leader-turn-0001.json"
    receipt = json.loads(snapshot["journals"]["receipts"][name])
    receipt[field] = value
    seal(snapshot, "receipts", name, receipt)
    with pytest.raises(reader.MeasurementError):
        reader.reconcile_snapshot(snapshot)


@pytest.mark.parametrize("mutation", ["usage", "details", "alias", "excess", "reasoning", "bool"])
def test_actual_response_usage_not_just_matching_digests(snapshot, mutation):
    request_id = "leader-turn-0001"
    response = json.loads(snapshot["journals"]["responses"][request_id + ".json"])
    if mutation == "usage":
        response["usage"].update(input_tokens=11, total_tokens=13)
    elif mutation == "details":
        response["usage"]["output_tokens_details"]["private_metadata"] = "changed"
    elif mutation == "alias":
        response["usage"]["input_tokens_details"]["cached_tokens"] = 3
    elif mutation == "excess":
        response["usage"]["input_tokens_details"]["uncached_tokens"] = 11
    elif mutation == "reasoning":
        response["usage"]["output_tokens_details"]["reasoning_tokens"] = 3
    else:
        response["usage"]["input_tokens"] = True
    sync_response(snapshot, request_id, response)  # all digests agree, usage must still reconcile
    with pytest.raises(reader.MeasurementError):
        reader.reconcile_snapshot(snapshot)


@pytest.mark.parametrize("target", ["price", "held_cost", "global_cost", "held_tokens", "role_turn", "timeline", "publication", "ledger_digest"])
def test_accounting_and_publication_corruption(snapshot, target):
    if target == "price":
        snapshot["budget"]["price_profile"]["output_rate_micro_usd_per_million"] += 1
    elif target in ("held_cost", "held_tokens"):
        key = "held_cost_micro_usd" if target == "held_cost" else "held_tokens"
        snapshot["budget"]["requests"]["leader-turn-0001"][key] += 1
        receipt = json.loads(snapshot["journals"]["receipts"]["leader-turn-0001.json"])
        receipt["settled"] = copy.deepcopy(snapshot["budget"]["requests"]["leader-turn-0001"])
        seal(snapshot, "receipts", "leader-turn-0001.json", receipt)
    elif target == "global_cost":
        snapshot["budget"]["settled_cost_micro_usd"] = 1
    elif target in ("role_turn", "timeline"):
        state = document(snapshot, "state")
        if target == "role_turn":
            state["roles"]["leader"]["turns"] = 2
        else:
            state["timeline"].pop()
        snapshot["documents"]["state"] = reader._canonical(state)
    elif target == "publication":
        snapshot["status"]["publication_valid"] = False
    else:
        snapshot["budget"]["ledger_sha256"] = "0" * 64
    if target != "ledger_digest":
        sync_budget(snapshot)
    with pytest.raises(reader.MeasurementError):
        reader.reconcile_snapshot(snapshot)


@pytest.mark.parametrize("target,value", [("request_id", "worker-2-turn-0001"), ("local_ordinal", 2),
                                         ("call_id", "other"), ("duration_seconds", True),
                                         ("host_elapsed_seconds", -1), ("host_elapsed_seconds", float("inf")),
                                         ("arguments_sha256", "0" * 64), ("stdout_sha256", "0" * 64)])
def test_tool_binding_streams_and_durations(snapshot, target, value):
    name = "0001.json"
    reservation = json.loads(snapshot["journals"]["tool_reservations"][name])
    receipt = json.loads(snapshot["journals"]["tool_receipts"][name])
    if target in ("duration_seconds", "host_elapsed_seconds"):
        if value == float("inf"):
            # Strict parser rejects Infinity before duration validation as well.
            snapshot["journals"]["tool_receipts"][name] = snapshot["journals"]["tool_receipts"][name].replace(b'"host_elapsed_seconds":0.3', b'"host_elapsed_seconds":Infinity')
        else:
            receipt["sandbox"][target] = value
            seal(snapshot, "tool_receipts", name, receipt)
    elif target == "stdout_sha256":
        receipt[target] = value
        seal(snapshot, "tool_receipts", name, receipt)
    else:
        reservation[target] = value
        if target in receipt:
            receipt[target] = value
        seal(snapshot, "tool_reservations", name, reservation)
        receipt["reservation_sha256"] = reader._sha(snapshot["journals"]["tool_reservations"][name])
        seal(snapshot, "tool_receipts", name, receipt)
    with pytest.raises(reader.MeasurementError):
        reader.reconcile_snapshot(snapshot)


def test_cli_uses_native_snapshot_boundary_and_sanitizes(snapshot, monkeypatch, capsys):
    captured = []
    monkeypatch.setattr(reader, "snapshot_runtime", lambda path: captured.append(path) or snapshot)
    assert reader.main(["--run-dir", "/mock/run"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert captured == [Path("/mock/run")]
    assert report["native_D119_guard_replay_publication_verified"] is True
    assert "PRIVATE-" not in json.dumps(report)


def test_native_rejection_does_not_leak_exception(monkeypatch, tmp_path, capsys):
    @contextmanager
    def lock(path):
        yield
    monkeypatch.setattr(reader, "_run_lock", lock)
    monkeypatch.setattr(reader, "_private_dir", lambda path: None)
    monkeypatch.setattr(reader, "_private_file", lambda path: None)
    def fail(path):
        raise ValueError("PRIVATE-RAW-SENTINEL")
    monkeypatch.setattr(reader.engine, "_load", fail)
    assert reader.main(["--run-dir", str(tmp_path)]) == 2
    output = capsys.readouterr().out
    assert "PRIVATE-" not in output and "native runtime guard" in output


def test_one_original_lock_and_native_guard_replay_view(snapshot, monkeypatch):
    calls, held = [], False
    @contextmanager
    def lock(path):
        nonlocal held
        assert not held
        held = True
        calls.append("lock")
        yield
        held = False
    monkeypatch.setattr(reader, "_run_lock", lock)
    monkeypatch.setattr(reader, "_private_dir", lambda path: None)
    monkeypatch.setattr(reader, "_private_file", lambda path: None)
    plan, state = document(snapshot, "plan"), document(snapshot, "state")
    state.update(delegations=[{"activation": {}}], merges=[{"receipt": {}}], delivery={"current_metrics": {}})
    def guard(*args):
        assert held
        calls.append("guard")
    ledger = SimpleNamespace(snapshot=lambda: snapshot["budget"])
    broker = SimpleNamespace(current_metrics=lambda role: {})
    monkeypatch.setattr(reader.engine, "_load", lambda path: (plan, state, ledger, object(), broker))
    monkeypatch.setattr(reader.runtime, "guard_coordinated_runtime", guard)
    monkeypatch.setattr(reader.engine, "_audit", lambda *args: calls.append("replay"))
    monkeypatch.setattr(reader.engine, "_bound_receipt", lambda *args: calls.append("receipt"))
    monkeypatch.setattr(reader.engine, "_view", lambda *args: snapshot["status"])
    monkeypatch.setattr(reader, "_capture_files", lambda path: {key: snapshot[key] for key in ("documents", "journals", "streams")})
    assert reader.snapshot_runtime(Path("/mock/run"))["budget"] == snapshot["budget"]
    assert calls == ["lock", "guard", "replay", "receipt", "receipt", "receipt", "guard"]
    assert not held
