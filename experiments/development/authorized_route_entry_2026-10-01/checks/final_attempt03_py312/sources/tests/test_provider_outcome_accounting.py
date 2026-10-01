"""Synthetic accounting controls; no provider calls or runtime acceptance."""
from __future__ import annotations

import copy
import json
import stat
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import provider_outcome_accounting as reader
import prepare_coordinated_development as preparation


def document(snapshot, key):
    return json.loads(snapshot[key])


def seal(snapshot, key, value):
    snapshot[key] = reader._canonical(value)


def change_response(snapshot, transform, *, turn=2):
    name = f"leader-turn-{turn:04d}.json"
    response = json.loads(snapshot["responses"][name])
    transform(response)
    snapshot["responses"][name] = reader._canonical(response)


def bind_documents(snapshot, *, plan=None, state=None, context=None):
    plan = document(snapshot, "plan_raw") if plan is None else plan
    state = document(snapshot, "state_raw") if state is None else state
    context = document(snapshot, "context_raw") if context is None else context
    seal(snapshot, "plan_raw", plan)
    state["plan_sha256"] = reader._sha(snapshot["plan_raw"])
    context["bindings"] = reader.engine._bindings(plan, state)
    context["bindings_sha256"] = reader._sha(reader._canonical(context["bindings"]))
    seal(snapshot, "state_raw", state)
    seal(snapshot, "context_raw", context)


@pytest.fixture
def control(tmp_path):
    profile = {"model": "offline-outcome-fixture", "input_rate_micro_usd_per_million": 1_000_000,
               "cached_input_rate_micro_usd_per_million": 100_000,
               "cache_write_rate_micro_usd_per_million": 1_250_000,
               "output_rate_micro_usd_per_million": 2_000_000}
    config = {"schema": 1, "seed": 123,
              "model": {"model_id": profile["model"], "version": "synthetic-v1", "family": "fixture",
                        "tier": "bounded", "effort": "high", "effort_provider_value": "high"},
              "price_profile": profile,
              "per_run_limits": {"measured_tokens": 1000, "active_seconds": 60, "tool_calls": 64},
              "max_model_requests": 128, "cost_limit_micro_usd": 100_000,
              "provider_route": {"provider": "fixture", "api": "responses", "version": "offline", "service_tier": "default"}}
    manifest = preparation._manifest(config, {name: b"synthetic contract" for name in preparation.CONTRACT_NAMES}, "f" * 64)
    schedule = reader.planner.compile_schedule(manifest)
    run_id = schedule["runs"][0]["run_id"]
    descriptor = reader.planner.runtime_descriptor(schedule, run_id)
    limits = {"limit_tokens": 1000, "active_limit_seconds": 60, "max_tool_calls": 64,
              "max_model_requests": 128, "cost_limit_micro_usd": 100_000, "tool_wall_seconds": 5}
    plan = {"schema": 1, "execution_profile": reader.engine.PROFILE, "run_id": run_id,
            "schedule": schedule, "descriptor": descriptor, "case_dir": str(tmp_path / "case"),
            "inputs_dir": str(tmp_path / "inputs"), "model": profile["model"], "effort": "high",
            "price_profile": profile, "functions": reader.runtime._functions(),
            "role_config": {role: {"max_output_tokens": 8, "max_model_turns": 1 if role == "reviewer" else 32}
                            for role in reader.engine.ROLES}, "max_epochs": 8, "limits": limits,
            "context": "SYNTHETIC PUBLIC CONTEXT", "journal_roots": [str(tmp_path / "broker_stages")],
            "runtime_source_digests": {"scripts/managed_coordinated_prototype.py": "e" * 64}}
    ledger = reader.WaveLedger.create(tmp_path / "ledger", 1000, 128,
                                      cost_limit_micro_usd=100_000, price_profile=profile, effort="high")
    journals = {key: {} for key in reader.JOURNALS}
    for turn in (1, 2):
        request_id = f"leader-turn-{turn:04d}"
        request = {"model": profile["model"], "max_output_tokens": 8, "service_tier": "default",
                   "reasoning": {"effort": "high"}, "input": [{"role": "user", "content": "PRIVATE-PROMPT-SENTINEL"}]}
        response = {"id": "PRIVATE-PROVIDER-ID-SENTINEL", "model": profile["model"], "service_tier": "default",
                    "status": "completed" if turn == 1 else "incomplete",
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": "PRIVATE-OUTPUT-SENTINEL"}]}],
                    "error": {"message": "PRIVATE-ERROR-SENTINEL"},
                    "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12,
                              "input_tokens_details": {"cache_read_tokens": 2, "cached_tokens": 2, "cache_write_tokens": 1, "uncached_tokens": 3},
                              "output_tokens_details": {"reasoning_tokens": 1, "private_metadata": "PRIVATE-DETAIL-SENTINEL"}}}
        raw_response = reader._canonical(response)
        item = {"request_id": request_id, "role": "leader", "payload_sha256": reader._sha(reader._json_bytes(request)),
                "input_tokens": 10, "max_output_tokens": 8, "model": profile["model"], "effort": "high"}
        permit = ledger.reserve_wave(f"wave-{turn}", [item])
        permit.begin_send(request_id, item["payload_sha256"])
        if turn == 1:
            usage = {key: response["usage"][key] for key in ("input_tokens", "output_tokens", "total_tokens")}
            details = {key: response["usage"][key] for key in ("input_tokens_details", "output_tokens_details")}
            settled = ledger.settle(request_id, reader._sha(raw_response), usage, usage_details=details)
            receipt = {"request_id": request_id, "role": "leader", "classification": reader.engine.CLASSIFICATION,
                       "payload_sha256": item["payload_sha256"], "response_sha256": reader._sha(raw_response),
                       "send_started_ns": 100, "send_ended_ns": 200, "settled": settled}
            journals["receipts"][request_id + ".json"] = reader._canonical(receipt)
        else:
            # This is the original retained reservation, not a synthetic settlement.
            ledger.mark_indeterminate(request_id, "incomplete")
        journals["requests"][request_id + ".json"] = reader._canonical(request)
        journals["responses"][request_id + ".json"] = raw_response
    state = {key: None for key in reader.engine.STATE_KEYS}
    state.update(schema=1, classification=reader.engine.CLASSIFICATION, state="indeterminate", runtime_stage="leader",
                 run_id=run_id, admission_descriptor=descriptor, source_digests=plan["runtime_source_digests"],
                 claim_sha256="c" * 64, side_binding={"path": str(tmp_path / "binding"), "sha256": "a" * 64},
                 broker_binding={"path": str(tmp_path / "manifest"), "sha256": "b" * 64},
                 completed_requests=1, tool_calls_completed=0, cursor=0, epoch=0,
                 roles={role: {"turns": 1 if role == "leader" else 0, "finished": False, "history_sha256": "a" * 64}
                        for role in reader.engine.ROLES}, assignments=[], timeline=[], delegations=[], merges=[],
                 initialized=False, reviewer_done=False, reason="PRIVATE-STATE-REASON-SENTINEL")
    context = {"schema": 2, "state": "indeterminate", "ledger_kind": "wave_v1", "ledger_schema": 3,
               "checkpoint_sha256": "d" * 64}
    snapshot = {"schema": 1, **journals, "ledger_raw": (ledger.directory / "ledger.json").read_bytes(),
                "status": {"state": "indeterminate", "stored_state": "indeterminate", "runtime_stage": "leader",
                           "publication_valid": False, "checkpoint_sha256": "d" * 64}}
    bind_documents(snapshot, plan=plan, state=state, context=context)
    return SimpleNamespace(snapshot=snapshot, ledger=ledger)


def inventory(path):
    return {str(item.relative_to(path)): (stat.S_IMODE(item.lstat().st_mode), item.read_bytes() if item.is_file() else None)
            for item in path.rglob("*")}


def test_retained_incomplete_cost_is_separate_and_reader_is_pure(control):
    before_snapshot, before_disk = copy.deepcopy(control.snapshot), inventory(control.ledger.directory)
    report = reader.reconcile_provider_outcomes(control.snapshot)
    assert report["totals"]["ledger_commitment"] == {"held_tokens": 30, "held_cost_micro_usd": 43}
    assert report["totals"]["reported_usage"]["complete_cost_micro_usd"] == 28  # ceil(13.45) twice
    assert report["totals"]["reported_usage"]["complete_token_sum"]["total_tokens"] == 24
    incomplete = report["requests"][1]
    assert incomplete["response_status"] == "incomplete" and incomplete["native_state"] == "indeterminate"
    assert incomplete["response_binding"] == "unbound_retained_raw"
    assert incomplete["native_held_cost_micro_usd"] == 29 and incomplete["declared_reported_cost_micro_usd"] == 14
    assert incomplete["reported_usage"]["input_unclassified_tokens"] == 4
    assert incomplete["reported_usage"]["reasoning_tokens"] == 1
    assert not report["native_guard_verified"] and not report["native_replay_verified"]
    assert not report["Q_demonstrated"] and not report["identity_authenticated"]
    assert "PRIVATE-" not in json.dumps(report)
    assert control.snapshot == before_snapshot and inventory(control.ledger.directory) == before_disk
    assert control.ledger.status()["requests"]["leader-turn-0002"]["state"] == "indeterminate"


def test_missing_response_is_unknown_not_zero(control):
    del control.snapshot["responses"]["leader-turn-0002.json"]
    report = reader.reconcile_provider_outcomes(control.snapshot)
    row = report["requests"][1]
    assert row["unknown_reason"] == "response_missing" and row["declared_reported_cost_micro_usd"] is None
    usage = report["totals"]["reported_usage"]
    assert usage["known_cost_sum_micro_usd"] == 14 and usage["complete_cost_micro_usd"] is None
    assert usage["unknown_requests"] == 1 and report["totals"]["ledger_commitment"]["held_cost_micro_usd"] == 43


@pytest.mark.parametrize("field,value", [("id", None), ("id", " "), ("model", "wrong-model"),
                                        ("service_tier", "priority"), ("status", "failed"), ("status", True)])
def test_invalid_response_identity_is_unpriced(control, field, value):
    change_response(control.snapshot, lambda response: response.update({field: value}))
    row = reader.reconcile_provider_outcomes(control.snapshot)["requests"][1]
    assert row["unknown_reason"] == "response_identity_invalid" and row["reported_usage"] is None
    assert row["declared_reported_cost_micro_usd"] is None and row["native_held_cost_micro_usd"] == 29


@pytest.mark.parametrize("changes", [
    {"input_tokens": True}, {"input_tokens": 9, "total_tokens": 11},
    {"output_tokens": 9, "total_tokens": 19}, {"output_tokens": 1.0}, {"total_tokens": 13},
    {"input_tokens_details": None}, {"input_tokens_details": {"cache_read_tokens": 2, "cached_tokens": 3}},
    {"input_tokens_details": {"cache_read_tokens": 8, "cache_write_tokens": 3}},
    {"input_tokens_details": {"uncached_tokens": -1}}, {"input_tokens_details": {"cache_write_tokens": True}},
    {"output_tokens_details": {"reasoning_tokens": 3}}, {"output_tokens_details": {"reasoning_tokens": True}},
])
def test_invalid_usage_retains_full_native_hold(control, changes):
    change_response(control.snapshot, lambda response: response["usage"].update(changes))
    row = reader.reconcile_provider_outcomes(control.snapshot)["requests"][1]
    assert row["unknown_reason"] == "usage_invalid" and row["reported_usage"] is None
    assert row["native_held_tokens"] == 18 and row["native_held_cost_micro_usd"] == 29


@pytest.mark.parametrize("value", [None, {}, []])
def test_missing_or_unstructured_usage_is_unknown(control, value):
    change_response(control.snapshot, lambda response: response.update(usage=value))
    row = reader.reconcile_provider_outcomes(control.snapshot)["requests"][1]
    assert row["unknown_reason"] == ("usage_missing" if value is None else "usage_invalid")
    assert row["declared_reported_cost_micro_usd"] is None


def test_absent_cache_details_are_unknown_with_conservative_residual_price(control):
    change_response(control.snapshot, lambda response: response.update(usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}))
    report = reader.reconcile_provider_outcomes(control.snapshot)
    row = report["requests"][1]
    assert row["declared_reported_cost_micro_usd"] == 17  # ceil(10*1.25+2*2)
    assert row["reported_usage"]["input_unclassified_tokens"] == 10
    assert all(row["reported_usage"][key] is None for key in reader.DETAIL_COUNTS)
    assert report["totals"]["reported_usage"]["token_details"]["reasoning_tokens"]["unknown_requests"] == 1


def test_explicit_cache_zeros_are_known(control):
    change_response(control.snapshot, lambda response: response["usage"].update(
        input_tokens_details={"cached_tokens": 0, "cache_write_tokens": 0, "uncached_tokens": 10},
        output_tokens_details={"reasoning_tokens": 0}))
    row = reader.reconcile_provider_outcomes(control.snapshot)["requests"][1]
    assert row["declared_reported_cost_micro_usd"] == 14
    assert row["reported_usage"]["cache_read_tokens"] == 0 and row["reported_usage"]["reasoning_tokens"] == 0


@pytest.mark.parametrize("raw", [b'{"usage":null,"usage":{}}\n', b'{"usage":NaN}\n', b'not json', b'{}'])
def test_invalid_response_json_is_unpriced(control, raw):
    control.snapshot["responses"]["leader-turn-0002.json"] = raw
    row = reader.reconcile_provider_outcomes(control.snapshot)["requests"][1]
    assert row["unknown_reason"] == "response_json_invalid" and row["reported_usage"] is None


def test_bound_raw_tamper_is_rejected(control):
    change_response(control.snapshot, lambda response: response.update(id="different-private-id"), turn=1)
    with pytest.raises(reader.ProviderOutcomeError, match="bound_response_digest_disagrees"):
        reader.reconcile_provider_outcomes(control.snapshot)


def test_request_payload_tamper_is_rejected(control):
    name = "leader-turn-0002.json"
    request = json.loads(control.snapshot["requests"][name])
    request["input"][0]["content"] = "changed prompt"
    control.snapshot["requests"][name] = reader._canonical(request)
    with pytest.raises(reader.ProviderOutcomeError, match="request_payload_or_policy_disagrees"):
        reader.reconcile_provider_outcomes(control.snapshot)


def test_receipt_strict_types_and_record_binding(control):
    name = "leader-turn-0001.json"
    receipt = json.loads(control.snapshot["receipts"][name])
    receipt["settled"]["usage"]["output_tokens"] = True
    control.snapshot["receipts"][name] = reader._canonical(receipt)
    with pytest.raises(reader.ProviderOutcomeError, match="receipt_binding_disagrees"):
        reader.reconcile_provider_outcomes(control.snapshot)


def test_rehashed_response_details_still_must_match_native_settlement(control):
    snapshot = control.snapshot
    name = "leader-turn-0001.json"
    change_response(snapshot, lambda response: response["usage"]["output_tokens_details"].update(reasoning_tokens=2), turn=1)
    ledger = document(snapshot, "ledger_raw")
    record = ledger["requests"]["leader-turn-0001"]
    record["response_sha256"] = reader._sha(snapshot["responses"][name])
    seal(snapshot, "ledger_raw", ledger)
    receipt = json.loads(snapshot["receipts"][name])
    receipt["response_sha256"] = record["response_sha256"]
    receipt["settled"] = copy.deepcopy(record)
    snapshot["receipts"][name] = reader._canonical(receipt)
    with pytest.raises(reader.ProviderOutcomeError, match="settled_reported_accounting_disagrees"):
        reader.reconcile_provider_outcomes(snapshot)


def test_settled_crash_without_receipt_reports_original_settlement(control):
    del control.snapshot["receipts"]["leader-turn-0001.json"]
    row = reader.reconcile_provider_outcomes(control.snapshot)["requests"][0]
    assert row["native_state"] == "settled" and not row["native_receipt_present"]
    assert row["declared_reported_cost_micro_usd"] == row["native_held_cost_micro_usd"] == 14


@pytest.mark.parametrize("mutation", ["descriptor_caps", "price", "context", "sources", "status", "outer", "request_id", "orphan"])
def test_forged_bindings_and_inventories_are_rejected(control, mutation):
    snapshot = control.snapshot
    if mutation in {"descriptor_caps", "price", "sources"}:
        plan = document(snapshot, "plan_raw")
        if mutation == "descriptor_caps":
            plan["limits"]["limit_tokens"] = 2000
        elif mutation == "price":
            plan["price_profile"]["output_rate_micro_usd_per_million"] += 1
        else:
            plan["runtime_source_digests"]["scripts/managed_coordinated_prototype.py"] = "f" * 64
        bind_documents(snapshot, plan=plan)
    elif mutation == "context":
        context = document(snapshot, "context_raw")
        context["bindings"]["claim_sha256"] = "a" * 64
        context["bindings_sha256"] = reader._sha(reader._canonical(context["bindings"]))
        seal(snapshot, "context_raw", context)
    elif mutation == "status":
        snapshot["status"]["publication_valid"] = True
    elif mutation == "outer":
        snapshot["native_guard_verified"] = True
    elif mutation == "request_id":
        ledger = document(snapshot, "ledger_raw")
        ledger["requests"]["leader-turn-0002"]["request_id"] = "worker-1-turn-0002"
        seal(snapshot, "ledger_raw", ledger)
    else:
        snapshot["receipts"]["worker-1-turn-0001.json"] = reader._canonical({})
    with pytest.raises(reader.ProviderOutcomeError):
        reader.reconcile_provider_outcomes(snapshot)


def test_unmatched_response_is_unknown_and_has_no_added_hold(control):
    control.snapshot["responses"]["reviewer-turn-0001.json"] = reader._canonical({"id": "PRIVATE-ID"})
    report = reader.reconcile_provider_outcomes(control.snapshot)
    row = report["requests"][-1]
    assert row["unknown_reason"] == "unmatched_response" and row["native_held_cost_micro_usd"] is None
    assert report["counts"]["unmatched_responses"] == 1
    assert report["totals"]["ledger_commitment"]["held_cost_micro_usd"] == 43
    assert report["totals"]["reported_usage"]["complete_cost_micro_usd"] is None


def test_missing_request_archive_is_unknown_only_for_unsettled(control):
    del control.snapshot["requests"]["leader-turn-0002.json"]
    assert reader.reconcile_provider_outcomes(control.snapshot)["requests"][1]["unknown_reason"] == "request_missing"
    del control.snapshot["requests"]["leader-turn-0001.json"]
    with pytest.raises(reader.ProviderOutcomeError, match="settled_request_missing"):
        reader.reconcile_provider_outcomes(control.snapshot)


def test_unsafe_journal_filename_is_rejected_without_echo(control):
    control.snapshot["responses"]["PRIVATE-KEY-SENTINEL"] = b"{}"
    with pytest.raises(reader.ProviderOutcomeError, match="invalid_journal_entry_name") as error:
        reader.reconcile_provider_outcomes(control.snapshot)
    assert "PRIVATE" not in str(error.value)


def private_tree(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir(mode=0o700)
    (run_dir / ".lock").write_bytes(b"")
    (run_dir / ".lock").chmod(0o600)
    for name in {*reader.engine.JOURNALS, "ledger", "context", "broker", "tool_reservations", "tool_receipts"}:
        (run_dir / name).mkdir(mode=0o700)
    for name in ("ledger/.lock", "context/.lock", "broker/.lock"):
        (run_dir / name).write_bytes(b"")
        (run_dir / name).chmod(0o600)
    return run_dir


@pytest.mark.parametrize("missing", ["broker", "tool_receipts", "histories", "context/.lock", "broker/.lock"])
def test_native_precheck_prevents_lazy_creation(tmp_path, monkeypatch, missing):
    run_dir = private_tree(tmp_path)
    path = run_dir / missing
    if path.is_dir():
        for item in path.iterdir():
            item.unlink()
        path.rmdir()
    else:
        path.unlink()
    before = inventory(run_dir)
    called = []
    monkeypatch.setattr(reader.engine, "_load", lambda *_: called.append(True))
    with pytest.raises(reader.ProviderOutcomeError, match="native_guard_or_snapshot_rejected"):
        reader.read_provider_outcomes(run_dir)
    assert not called and inventory(run_dir) == before


@pytest.mark.parametrize("lifecycle,replayed", [("indeterminate", False), ("paused", True), ("prepared", True), ("completed", True)])
def test_native_reader_uses_one_lock_guard_and_replay_allowlist(control, tmp_path, monkeypatch, lifecycle, replayed):
    snapshot = control.snapshot
    state = document(snapshot, "state_raw")
    state["state"] = lifecycle
    state["delivery"] = {"current_metrics": {"sha256": "a" * 64}}
    context = document(snapshot, "context_raw")
    context["state"] = lifecycle
    bind_documents(snapshot, state=state, context=context)
    snapshot["status"].update(state=lifecycle, stored_state=lifecycle, publication_valid=lifecycle == "completed")
    plan = document(snapshot, "plan_raw")
    run_dir = private_tree(tmp_path)
    events = []
    locked = False

    @contextmanager
    def lock(path):
        nonlocal locked
        assert path == run_dir and not locked
        locked = True
        events.append("lock")
        try:
            yield
        finally:
            locked = False
            events.append("unlock")

    def guarded(*_):
        assert locked
        events.append("guard")

    monkeypatch.setattr(reader, "_run_lock", lock)
    broker = SimpleNamespace(current_metrics=lambda _: state["delivery"]["current_metrics"])
    monkeypatch.setattr(reader.engine, "_load", lambda _: (plan, state, None, None, broker))
    monkeypatch.setattr(reader.runtime, "guard_coordinated_runtime", guarded)
    monkeypatch.setattr(reader.engine, "_audit", lambda *_: events.append("audit"))
    monkeypatch.setattr(reader.engine, "_bound_receipt", lambda *_: events.append("bound"))
    monkeypatch.setattr(reader.engine, "_view", lambda *_: {**snapshot["status"], "reason": "PRIVATE-REASON"})
    monkeypatch.setattr(reader, "_capture", lambda _: {key: value for key, value in snapshot.items() if key != "status"})
    report = reader.read_provider_outcomes(run_dir)
    assert events.count("lock") == 1 and events.count("guard") == 2 and events[-1] == "unlock"
    assert events.count("audit") == int(replayed)
    assert report["native_guard_verified"] and report["native_replay_verified"] is replayed
    assert "PRIVATE" not in json.dumps(report)


def test_native_guard_error_has_no_private_message(tmp_path, monkeypatch):
    run_dir = private_tree(tmp_path)

    def reject(*_):
        raise ValueError("PRIVATE-HEADER-SECRET")

    monkeypatch.setattr(reader.engine, "_load", reject)
    with pytest.raises(reader.ProviderOutcomeError) as error:
        reader.read_provider_outcomes(run_dir)
    assert str(error.value) == "native_guard_or_snapshot_rejected"


def test_native_reader_rejects_snapshot_changed_under_cooperative_lock(control, tmp_path, monkeypatch):
    run_dir = private_tree(tmp_path)
    snapshot = control.snapshot
    plan, state = document(snapshot, "plan_raw"), document(snapshot, "state_raw")
    monkeypatch.setattr(reader.engine, "_load", lambda _: (plan, state, None, None, None))
    monkeypatch.setattr(reader.runtime, "guard_coordinated_runtime", lambda *_: None)
    monkeypatch.setattr(reader.engine, "_view", lambda *_: snapshot["status"])
    captures = 0

    def capture(_):
        nonlocal captures
        captures += 1
        value = {key: copy.deepcopy(item) for key, item in snapshot.items() if key != "status"}
        if captures == 2:
            value["responses"].pop("leader-turn-0002.json")
        return value

    monkeypatch.setattr(reader, "_capture", capture)
    with pytest.raises(reader.ProviderOutcomeError, match="snapshot_changed_during_read"):
        reader.read_provider_outcomes(run_dir)
    assert captures == 2


@pytest.mark.parametrize("bad_name", ["responses/leader-turn-0001.json", "plan.json"])
def test_native_capture_checks_private_file_modes(tmp_path, bad_name):
    run_dir = private_tree(tmp_path)
    for name in reader.DOCS.values():
        path = run_dir / name
        path.write_bytes(reader._canonical({}))
        path.chmod(0o600)
    bad = run_dir / bad_name
    bad.write_bytes(reader._canonical({}))
    bad.chmod(0o644)
    with pytest.raises(ValueError):
        reader._capture(run_dir)


def test_native_capture_preserves_private_documents_and_raw_bytes(tmp_path):
    run_dir = private_tree(tmp_path)
    for name in reader.DOCS.values():
        path = run_dir / name
        path.write_bytes(reader._canonical({"private": "PRIVATE-DOCUMENT"}))
        path.chmod(0o600)
    response = run_dir / "responses" / "leader-turn-0001.json"
    response.write_bytes(reader._canonical({"private": "PRIVATE-RESPONSE"}))
    response.chmod(0o600)
    before = inventory(run_dir)
    with reader._run_lock(run_dir):
        capture = reader._capture(run_dir)
    assert capture["plan_raw"] == before["plan.json"][1]
    assert capture["responses"][response.name] == before[str(response.relative_to(run_dir))][1]
    assert inventory(run_dir) == before
