"""Read declared provider outcomes without settling or repairing native state.

Private snapshot schema 1 is closed: schema, plan_raw, state_raw, context_raw,
ledger_raw, requests/responses/receipts (filename -> bytes), and status. Status
contains only state, stored_state, runtime_stage, publication_valid and
checkpoint_sha256. The pure reconciler attests no native guard or replay.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import coordinated_prototype_runtime as runtime
import managed_coordinated_prototype as engine
import plan_coordinated_development as planner
from development_delivery_contract import parse_json
from managed_token_ledger import _canonical as price_bytes, _price_profile, _settled_cost
from managed_wave_ledger import WaveLedger
from run_managed_conversation import _canonical, _private_dir, _private_file, _run_lock
from run_managed_response import MAX_JSON_BYTES, _json_bytes, _validated_request
from tool_policy import _read_bounded_file

SNAPSHOT_KEYS = {"schema", "plan_raw", "state_raw", "context_raw", "ledger_raw", "requests", "responses", "receipts", "status"}
STATUS_KEYS = {"state", "stored_state", "runtime_stage", "publication_valid", "checkpoint_sha256"}
JOURNALS = ("requests", "responses", "receipts")
DOCS = {"plan_raw": "plan.json", "state_raw": "run.json", "context_raw": "context/run.json", "ledger_raw": "ledger/ledger.json"}
SHA = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"(leader|worker-1|worker-2|reviewer)-turn-([0-9]{4})\.json\Z")
DETAIL_COUNTS = ("cache_read_tokens", "cache_write_tokens", "uncached_tokens", "reasoning_tokens")


class ProviderOutcomeError(ValueError):
    """A fixed, sanitized accounting rejection."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ProviderOutcomeError(reason)


def _integer(value: Any, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, "invalid_accounting_integer")
    return value


def _digest(value: Any) -> str:
    _require(type(value) is str and SHA.fullmatch(value) is not None, "invalid_accounting_digest")
    return value


def _identifier(value: Any) -> str:
    _require(type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,256}", value) is not None,
             "invalid_declared_identifier")
    return value


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _same(left: Any, right: Any) -> bool:
    return _json_bytes(left) == _json_bytes(right)


def _parse(raw: Any) -> Any:
    _require(type(raw) is bytes and len(raw) <= MAX_JSON_BYTES, "invalid_snapshot_bytes")
    value = parse_json(raw)
    _require(raw == _canonical(value), "noncanonical_snapshot_bytes")
    return value


def _document(raw: Any) -> dict:
    value = _parse(raw)
    _require(type(value) is dict, "invalid_snapshot_document")
    return value


def _capture(run_dir: Path) -> dict:
    documents = {key: _read_bounded_file(run_dir / name, "outcome document", MAX_JSON_BYTES)
                 for key, name in DOCS.items()}
    journals = {}
    for name in JOURNALS:
        journals[name] = {}
        for path in sorted((run_dir / name).iterdir()):
            _private_file(path)
            journals[name][path.name] = _read_bounded_file(path, "outcome journal", MAX_JSON_BYTES)
    return {"schema": 1, **documents, **journals}


def read_provider_outcomes(run_dir: Path) -> dict:
    """Read under one native run lock, retaining every original native hold.

    Indeterminate state receives the original guard and lifecycle/binding
    validation, but no claim of a successful full native replay.
    """
    run_dir = Path(run_dir)
    try:
        with _run_lock(run_dir):
            for name in (*engine.JOURNALS, "ledger", "context", "broker", "tool_reservations", "tool_receipts"):
                _private_dir(run_dir / name)
            for name in ("ledger/.lock", "context/.lock", "broker/.lock"):
                _private_file(run_dir / name)
            plan, state, ledger, context, broker = engine._load(run_dir)
            runtime.guard_coordinated_runtime(plan, state, broker)
            replayed = state["state"] in {"prepared", "paused", "completed"}
            if replayed:
                engine._audit(run_dir, plan, state, ledger, broker)
                for row in state["delegations"]:
                    engine._bound_receipt(row["activation"], "epoch activation")
                for row in state["merges"]:
                    engine._bound_receipt(row["receipt"], "epoch merge")
            if state["state"] == "completed":
                engine._bound_receipt(state["delivery"], "delivery")
                _require(broker.current_metrics("leader") == state["delivery"]["current_metrics"], "published_metrics_stale")
            view = engine._view(run_dir, plan, state, ledger, context)
            status = {key: view[key] for key in STATUS_KEYS}
            snapshot = {**_capture(run_dir), "status": status}
            result = reconcile_provider_outcomes(snapshot)
            runtime.guard_coordinated_runtime(plan, state, broker)
            after = engine._view(run_dir, plan, state, ledger, context)
            _require(snapshot == {**_capture(run_dir), "status": {key: after[key] for key in STATUS_KEYS}},
                     "snapshot_changed_during_read")
            result.update(native_guard_verified=True, native_replay_verified=replayed)
            return result
    except ProviderOutcomeError:
        raise
    except Exception:
        raise ProviderOutcomeError("native_guard_or_snapshot_rejected") from None


def _journal_map(value: Any) -> dict:
    _require(type(value) is dict and len(value) <= 10000, "invalid_journal_inventory")
    for name, raw in value.items():
        _require(type(name) is str and NAME.fullmatch(name) is not None and int(NAME.fullmatch(name).group(2)) > 0,
                 "invalid_journal_entry_name")
        _require(type(raw) is bytes and len(raw) <= MAX_JSON_BYTES, "invalid_journal_bytes")
    return value


def _reported(raw: bytes | None, record: dict, model: str, profile: dict) -> tuple[dict | None, int | None, str | None, str | None, dict | None]:
    if raw is None:
        return None, None, "response_missing", None, None
    try:
        response = _parse(raw)
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        return None, None, "response_json_invalid", None, None
    if (type(response) is not dict or type(response.get("id")) is not str or not response["id"].strip()
            or response.get("model") != model or response.get("service_tier") != "default"
            or type(response.get("status")) is not str or response["status"] not in {"completed", "incomplete"}):
        return None, None, "response_identity_invalid", None, None
    response_status = response["status"]
    usage = response.get("usage")
    if usage is None:
        return None, None, "usage_missing", response_status, None
    try:
        _require(type(usage) is dict, "usage_invalid")
        counts = {key: _integer(usage.get(key)) for key in ("input_tokens", "output_tokens", "total_tokens")}
        _require(counts["input_tokens"] == record["input_tokens"]
                 and counts["output_tokens"] <= record["max_output_tokens"]
                 and counts["total_tokens"] == counts["input_tokens"] + counts["output_tokens"], "usage_invalid")
        details = {key: usage[key] for key in ("input_tokens_details", "output_tokens_details") if key in usage}
        cost = _settled_cost(counts, details, profile)
        inp, out = details.get("input_tokens_details", {}), details.get("output_tokens_details", {})
        detail_counts = {"cache_read_tokens": inp.get("cache_read_tokens", inp.get("cached_tokens")),
                         "cache_write_tokens": inp.get("cache_write_tokens"), "uncached_tokens": inp.get("uncached_tokens"),
                         "reasoning_tokens": out.get("reasoning_tokens")}
        unclassified = counts["input_tokens"] - sum(value for key, value in detail_counts.items()
                                                    if key != "reasoning_tokens" and value is not None)
        return {**counts, **detail_counts, "input_unclassified_tokens": unclassified}, cost, None, response_status, details
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return None, None, "usage_invalid", response_status, None


def _totals(rows: list[dict]) -> dict:
    known = [row for row in rows if row["reported_usage"] is not None]
    unknown = len(rows) - len(known)
    token_sum = {key: sum(row["reported_usage"][key] for row in known)
                 for key in ("input_tokens", "output_tokens", "total_tokens", "input_unclassified_tokens")}
    known_cost = sum(row["declared_reported_cost_micro_usd"] for row in known)
    return {"request_count": len(rows),
            "ledger_commitment": {"held_tokens": sum(row["native_held_tokens"] or 0 for row in rows),
                                  "held_cost_micro_usd": sum(row["native_held_cost_micro_usd"] or 0 for row in rows)},
            "reported_usage": {"known_requests": len(known), "unknown_requests": unknown,
                               "known_token_sum": token_sum, "complete_token_sum": token_sum if not unknown else None,
                               "known_cost_sum_micro_usd": known_cost, "complete_cost_micro_usd": known_cost if not unknown else None,
                               "token_details": {key: {"known_sum": sum(row["reported_usage"][key] for row in known
                                                                        if row["reported_usage"][key] is not None),
                                                        "unknown_requests": sum(row["reported_usage"][key] is None for row in known) + unknown}
                                                 for key in DETAIL_COUNTS}},
            "columns_are_alternative_not_additive": True}


def reconcile_provider_outcomes(snapshot: dict) -> dict:
    """Pure accounting: no files, models, guard, settlement, or repair."""
    try:
        return _reconcile(snapshot)
    except ProviderOutcomeError:
        raise
    except Exception:
        raise ProviderOutcomeError("snapshot_binding_or_schema_rejected") from None


def _reconcile(snapshot: dict) -> dict:
    _require(type(snapshot) is dict and set(snapshot) == SNAPSHOT_KEYS
             and type(snapshot["schema"]) is int and snapshot["schema"] == 1, "invalid_closed_snapshot")
    plan, state, context, ledger = (_document(snapshot[key]) for key in DOCS)
    _require(set(plan) == engine.PLAN_KEYS and set(state) == engine.STATE_KEYS, "invalid_native_document_fields")
    _require(type(plan["schema"]) is int and plan["schema"] == 1
             and type(state["schema"]) is int and state["schema"] == 1, "invalid_native_document_schema")
    planner.validate_runtime_binding(plan["schedule"], plan["run_id"], plan["descriptor"])
    _require(plan["execution_profile"] == engine.PROFILE and state["classification"] == engine.CLASSIFICATION,
             "native_profile_disagrees")
    _require(state["plan_sha256"] == _sha(snapshot["plan_raw"]) and state["run_id"] == plan["run_id"], "plan_binding_disagrees")
    sources = plan["runtime_source_digests"]
    _require(type(sources) is dict and sources and _same(sources, state["source_digests"]), "source_binding_disagrees")
    for name, digest in sources.items():
        _require(type(name) is str and re.fullmatch(r"scripts/[A-Za-z0-9_]+\.py|prototypes/core\.py", name) is not None,
                 "invalid_source_binding_path")
        _digest(digest)
    _require(type(context["schema"]) is int and context["schema"] == 2
             and context["ledger_kind"] == "wave_v1" and type(context["ledger_schema"]) is int and context["ledger_schema"] == 3
             and _same(context["bindings"], engine._bindings(plan, state))
             and context["bindings_sha256"] == _sha(_canonical(context["bindings"])), "context_binding_disagrees")
    _digest(state["claim_sha256"])
    status = snapshot["status"]
    _require(type(status) is dict and set(status) == STATUS_KEYS and type(status["publication_valid"]) is bool,
             "invalid_closed_status")
    _require(status["stored_state"] == state["state"] and state["state"] in {"prepared", "paused", "started", "completed", "indeterminate"}
             and status["state"] in {"prepared", "paused", "active", "completed", "indeterminate", "exhausted"}
             and status["runtime_stage"] == state["runtime_stage"] and state["runtime_stage"] in engine.STAGES,
             "lifecycle_binding_disagrees")
    _require(_digest(status["checkpoint_sha256"]) == context["checkpoint_sha256"], "checkpoint_binding_disagrees")
    _require(not status["publication_valid"] or status["state"] == state["state"] == context["state"] == "completed",
             "publication_lifecycle_disagrees")
    WaveLedger._validate(ledger)
    profile = _price_profile(plan["price_profile"])
    _require(_same(profile, ledger["price_profile"]) and ledger["model"] == plan["model"] == plan["descriptor"]["model"]["model_id"]
             and ledger["effort"] == plan["effort"] == (plan["descriptor"]["model"]["effort_provider_value"] or "default")
             and _sha(price_bytes(profile)) == plan["descriptor"]["model"]["price_profile_sha256"], "price_model_or_effort_binding_disagrees")
    descriptor = plan["descriptor"]
    limits = plan["limits"]
    expected_caps = {"limit_tokens": descriptor["per_run_limits"]["measured_tokens"],
                     "active_limit_seconds": descriptor["per_run_limits"]["active_seconds"],
                     "max_tool_calls": descriptor["per_run_limits"]["tool_calls"],
                     "max_model_requests": descriptor["max_model_requests"],
                     "cost_limit_micro_usd": descriptor["cost_limit_micro_usd"]}
    _require(type(limits) is dict and set(limits) == {*expected_caps, "tool_wall_seconds"}
             and all(type(limits[key]) is int and limits[key] == cap for key, cap in expected_caps.items())
             and type(limits["tool_wall_seconds"]) is int
             and 1 <= limits["tool_wall_seconds"] <= min(300, limits["active_limit_seconds"]), "descriptor_caps_disagree")
    _require(type(plan["role_config"]) is dict and set(plan["role_config"]) == set(engine.ROLES), "invalid_role_config")
    for role, config in plan["role_config"].items():
        _require(type(config) is dict and set(config) == {"max_output_tokens", "max_model_turns"}
                 and 1 <= _integer(config["max_output_tokens"], 1) <= min(8192, limits["limit_tokens"])
                 and 1 <= _integer(config["max_model_turns"], 1) <= limits["max_model_requests"]
                 and (role != "reviewer" or config["max_model_turns"] == 1), "invalid_role_config")
    for field, cap in (("limit_tokens", "limit_tokens"), ("max_requests", "max_model_requests"), ("cost_limit_micro_usd", "cost_limit_micro_usd")):
        _require(type(plan["limits"][cap]) is int and ledger[field] == plan["limits"][cap], "ledger_caps_disagree")
    requests, responses, receipts = (_journal_map(snapshot[key]) for key in JOURNALS)
    records = ledger["requests"]
    names = {request_id + ".json" for request_id in records}
    _require(set(requests) <= names and set(receipts) <= names, "orphan_request_or_receipt")
    rows = []
    for request_id, record in sorted(records.items()):
        name = request_id + ".json"
        _require(NAME.fullmatch(name) is not None and NAME.fullmatch(name).group(1) == record["role"]
                 and record["role"] in engine.ROLES, "request_identity_or_role_disagrees")
        cap = plan["role_config"][record["role"]]["max_output_tokens"]
        _require(_integer(cap, 1) == record["max_output_tokens"], "role_output_cap_disagrees")
        raw = responses.get(name)
        bound_sha = record["response_sha256"]
        if bound_sha is not None:
            _require(raw is not None and _sha(raw) == bound_sha, "bound_response_digest_disagrees")
        usage, cost, reason, response_status, details = _reported(raw, record, plan["model"], profile)
        if name not in requests:
            _require(record["state"] != "settled", "settled_request_missing")
            usage, cost, reason = None, None, "request_missing"
        else:
            request = _validated_request(_document(requests[name]))
            _require(_sha(_json_bytes(request)) == record["payload_sha256"]
                     and request["model"] == record["model"] and request["reasoning"]["effort"] == record["effort"]
                     and type(request["max_output_tokens"]) is int and request["max_output_tokens"] == record["max_output_tokens"]
                     and request["service_tier"] == "default", "request_payload_or_policy_disagrees")
        if name in receipts:
            receipt = _document(receipts[name])
            _require(record["state"] == "settled" and _same(receipt["settled"], record)
                     and receipt["request_id"] == request_id and receipt["role"] == record["role"]
                     and receipt["payload_sha256"] == record["payload_sha256"] and receipt["response_sha256"] == bound_sha
                     and receipt["classification"] == state["classification"], "receipt_binding_disagrees")
        if record["state"] == "settled":
            _require(reason is None and response_status == "completed" and cost == record["held_cost_micro_usd"]
                     and _same(record["usage"], {key: usage[key] for key in ("input_tokens", "output_tokens", "total_tokens")})
                     and _same(record["usage_details"], details), "settled_reported_accounting_disagrees")
        rows.append({"request_id": request_id, "role": record["role"], "native_state": record["state"],
                     "counted_input_tokens": record["input_tokens"], "max_output_tokens": record["max_output_tokens"],
                     "payload_sha256": record["payload_sha256"], "response_sha256": None if raw is None else _sha(raw),
                     "response_binding": "native_ledger_bound" if bound_sha is not None else "unbound_retained_raw" if raw is not None else "missing",
                     "native_receipt_present": name in receipts, "response_status": response_status,
                     "reported_usage": usage, "declared_reported_cost_micro_usd": cost, "unknown_reason": reason,
                     "native_held_tokens": record["held_tokens"], "native_held_cost_micro_usd": record["held_cost_micro_usd"]})
    for name in sorted(set(responses) - names):
        rows.append({"request_id": name[:-5], "role": NAME.fullmatch(name).group(1), "native_state": None,
                     "counted_input_tokens": None, "max_output_tokens": None, "payload_sha256": None,
                     "response_sha256": _sha(responses[name]), "response_binding": "unmatched_response",
                     "native_receipt_present": False, "response_status": None, "reported_usage": None,
                     "declared_reported_cost_micro_usd": None, "unknown_reason": "unmatched_response",
                     "native_held_tokens": None, "native_held_cost_micro_usd": None})
    return {"schema": 1, "classification": "development_provider_outcome_accounting_local",
            "run_id": _identifier(plan["run_id"]), "model_declared": _identifier(plan["model"]), "effort_declared": _identifier(plan["effort"]),
            "lifecycle": status["state"], "stored_state": state["state"], "runtime_stage": status["runtime_stage"],
            "publication_valid": status["publication_valid"], "requests": rows,
            "binding": {"schedule_sha256": _digest(plan["descriptor"]["schedule_sha256"]),
                        "plan_sha256": _sha(snapshot["plan_raw"]), "state_sha256": _sha(snapshot["state_raw"]),
                        "context_sha256": _sha(snapshot["context_raw"]), "ledger_sha256": _sha(snapshot["ledger_raw"]),
                        "checkpoint_sha256": status["checkpoint_sha256"], "source_digests_sha256": _sha(_canonical(sources)),
                        "price_profile_sha256": _sha(price_bytes(profile)),
                        "journal_inventory_sha256": _sha(_canonical({key: {name: _sha(raw) for name, raw in snapshot[key].items()} for key in JOURNALS}))},
            "counts": {"ledger_requests": len(records), "responses_present": len(responses), "unmatched_responses": len(set(responses) - names),
                       "missing_request_archives": len(names - set(requests)), "missing_responses": len(names - set(responses))},
            "totals": _totals(rows), "by_role": {role: _totals([row for row in rows if row["role"] == role]) for role in engine.ROLES},
            "native_guard_verified": False, "native_replay_verified": False, "accepted_artifacts_claimed": False,
            "identity_authenticated": False, "effort_authenticated": False, "usage_authenticated": False, "cost_authenticated": False,
            "full_cost_complete": False, "formal_cell_executed": False, "comparable_development_cell": False, "quality_assessed": False,
            "Q_demonstrated": False, "indeterminate_state_resumable": False,
            "scope": "declared_reported_usage_cost_and_native_preventive_commitment_are_separate_not_additive_not_invoice",
            "missing": ["authenticated_provider_identity", "served_model_snapshot", "effective_effort", "authenticated_usage_or_invoice",
                        "tool_pricing", "taxes_and_regional_adjustments", "human_and_evaluation_cost", "total_study_cost", "quality_scoring"]}
