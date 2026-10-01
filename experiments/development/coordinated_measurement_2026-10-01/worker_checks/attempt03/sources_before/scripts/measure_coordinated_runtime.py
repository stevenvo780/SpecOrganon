"""Read and reconcile completed D119 journals without sending requests.

The original cooperative lock protects a local snapshot, not custody against a
same-UID writer. All prices and provider identities remain local declarations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import coordinated_prototype_runtime as runtime
import managed_coordinated_prototype as engine
from development_delivery_contract import parse_json
from managed_token_ledger import _canonical as price_bytes, _price_profile, _settled_cost
from run_managed_conversation import _canonical, _private_dir, _private_file, _run_lock
from run_managed_response import _json_bytes
from tool_policy import _read_bounded_file

ROLES = engine.ROLES
SHA = re.compile(r"[0-9a-f]{64}\Z")
REQUEST_ID = re.compile(r"(leader|worker-1|worker-2|reviewer)-turn-([0-9]{4})\Z")
DETAILS = ("cache_read_tokens", "cache_write_tokens", "uncached_tokens", "reasoning_tokens")
DOCUMENTS = {"plan": "plan.json", "state": "run.json", "ledger": "ledger/ledger.json",
             "context": "context/run.json", "publication": "publication.json"}
JOURNALS = ("requests", "responses", "receipts", "tool_reservations", "tool_receipts")
COORDINATES = ("stratum_id", "block_id", "family", "tier", "model_id", "model_version",
               "effort", "effort_provider_value", "agents", "agent_count", "coordination_sha256",
               "case_id", "case_package_sha256", "case_reference_sha256", "replica",
               "order_position", "arm", "mode", "input_sha256", "round", "release_block_order")


class MeasurementError(ValueError):
    """A sanitized rejection: messages never contain participant material."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MeasurementError(message)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _integer(value: Any, message: str, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, message)
    return value


def _duration(value: Any) -> float:
    _require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
             "invalid local duration")
    return float(value)


def _digest(value: Any) -> str:
    _require(type(value) is str and SHA.fullmatch(value) is not None, "invalid digest")
    return value


def _same(left: Any, right: Any) -> bool:
    """JSON equality preserves the distinction between booleans and numbers."""
    return _json_bytes(left) == _json_bytes(right)


def _identifier(value: Any) -> str:
    _require(type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,256}", value) is not None,
             "invalid declared identifier")
    return value


def _parsed(raw: Any) -> dict:
    _require(type(raw) is bytes, "snapshot journal is not bytes")
    try:
        value = parse_json(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise MeasurementError("invalid journal JSON") from None
    _require(type(value) is dict, "journal is not an object")
    _require(raw == _canonical(value), "journal bytes are not canonical")
    return value


def _capture_files(run_dir: Path) -> dict:
    documents = {key: _read_bounded_file(run_dir / name, "measurement document", 20_000_000)
                 for key, name in DOCUMENTS.items()}
    journals = {}
    for folder in JOURNALS:
        _private_dir(run_dir / folder)
        journals[folder] = {path.name: _read_bounded_file(path, "measurement journal", 20_000_000)
                            for path in sorted((run_dir / folder).iterdir())}
    streams = {}
    for path in sorted((run_dir / "broker").iterdir()):
        if path.name == ".lock":
            continue
        _private_dir(path)
        _require({entry.name for entry in path.iterdir()} == {"stdout", "stderr"},
                 "tool stream inventory changed")
        streams[path.name] = {key: _read_bounded_file(path / key, "measurement tool stream", 20_000_000)
                              for key in ("stdout", "stderr")}
    return {"documents": documents, "journals": journals, "streams": streams}


def snapshot_runtime(run_dir: Path) -> dict:
    """Capture under ONE original lock, with native wrapper guard and replay.

    Prechecking the broker directories prevents its lazy constructor from
    creating missing runtime artifacts. Nothing in the run is written here.
    """
    run_dir = Path(run_dir)
    try:
        with _run_lock(run_dir):
            for name in (*JOURNALS, "broker", "ledger", "context"):
                _private_dir(run_dir / name)
            for name in ("broker/.lock", "ledger/.lock", "context/.lock"):
                _private_file(run_dir / name)
            plan, state, ledger, context, broker = engine._load(run_dir)
            runtime.guard_coordinated_runtime(plan, state, broker)
            _require(state["state"] == "completed", "runtime is not completed")
            engine._audit(run_dir, plan, state, ledger, broker)
            for row in state["delegations"]:
                engine._bound_receipt(row["activation"], "epoch activation")
            for row in state["merges"]:
                engine._bound_receipt(row["receipt"], "epoch merge")
            engine._bound_receipt(state["delivery"], "delivery")
            _require(broker.current_metrics("leader") == state["delivery"]["current_metrics"],
                     "published host metrics are stale")
            status = engine._view(run_dir, plan, state, ledger, context)
            _require(status["state"] == "completed" and status["publication_valid"] is True,
                     "runtime publication is not valid")
            files = _capture_files(run_dir)
            budget = ledger.snapshot()
            runtime.guard_coordinated_runtime(plan, state, broker)
            _require(files == _capture_files(run_dir) and status == engine._view(run_dir, plan, state, ledger, context),
                     "snapshot changed during capture")
            return {**files, "budget": budget, "status": status}
    except MeasurementError:
        raise
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, IndexError, AttributeError):
        raise MeasurementError("native runtime guard or replay rejected snapshot") from None


def _usage(response: dict) -> tuple[dict, dict]:
    value = response.get("usage")
    _require(type(value) is dict, "response usage is missing")
    usage = {key: _integer(value.get(key), "invalid response usage")
             for key in ("input_tokens", "output_tokens", "total_tokens")}
    _require(usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"],
             "response token total disagrees")
    details = {key: value[key] for key in ("input_tokens_details", "output_tokens_details") if key in value}
    return usage, details


def _detail_counts(usage: dict, details: dict) -> dict:
    inp, out = details.get("input_tokens_details", {}), details.get("output_tokens_details", {})
    _require(type(inp) is dict and type(out) is dict, "invalid token detail group")
    read = inp.get("cache_read_tokens", inp.get("cached_tokens"))
    counts = {"cache_read_tokens": read, "cache_write_tokens": inp.get("cache_write_tokens"),
              "uncached_tokens": inp.get("uncached_tokens"), "reasoning_tokens": out.get("reasoning_tokens")}
    for value in counts.values():
        if value is not None:
            _integer(value, "invalid token detail count")
    _require(not ("cached_tokens" in inp and "cache_read_tokens" in inp)
             or inp["cached_tokens"] == inp["cache_read_tokens"], "cache read aliases disagree")
    classified = sum(value for key, value in counts.items() if key != "reasoning_tokens" and value is not None)
    _require(classified <= usage["input_tokens"], "classified input exceeds input usage")
    _require(counts["reasoning_tokens"] is None or counts["reasoning_tokens"] <= usage["output_tokens"],
             "reasoning exceeds output usage")
    return {**counts, "input_unclassified_tokens": usage["input_tokens"] - classified}


def _aggregate(requests: list[dict], tools: list[dict]) -> dict:
    result = {"request_count": len(requests), "tool_count": len(tools)}
    for key in ("input_tokens", "output_tokens", "total_tokens", "declared_cost_micro_usd", "send_duration_ns",
                "input_unclassified_tokens"):
        result[key] = sum(row[key] for row in requests)
    result["token_details"] = {
        key: {"known_sum": sum(row[key] for row in requests if row[key] is not None),
              "unknown_requests": sum(row[key] is None for row in requests),
              "complete_total": sum(row[key] for row in requests) if all(row[key] is not None for row in requests) else None}
        for key in DETAILS}
    result["send_duration_seconds_sum"] = result["send_duration_ns"] / 1_000_000_000
    for key in ("sandbox_duration_seconds", "host_elapsed_seconds"):
        result[key + "_sum"] = _duration(math.fsum(row[key] for row in tools))
    return result


def reconcile_snapshot(snapshot: dict) -> dict:
    """Pure reconciliation of a private snapshot; return only an allowlist.

    This function alone cannot attest that native guard/replay was performed.
    The CLI always obtains its snapshot through snapshot_runtime first.
    """
    try:
        return _reconcile(snapshot)
    except MeasurementError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, IndexError, AttributeError):
        raise MeasurementError("snapshot schema or declared accounting is invalid") from None


def _reconcile(snapshot: dict) -> dict:
    _require(set(snapshot["documents"]) == set(DOCUMENTS) and set(snapshot["journals"]) == set(JOURNALS),
             "snapshot document inventory disagrees")
    docs = {key: _parsed(snapshot["documents"][key]) for key in DOCUMENTS}
    plan, state, raw_ledger, context, publication = (docs[key] for key in DOCUMENTS)
    status, budget = snapshot["status"], snapshot["budget"]
    _require(state["state"] == context["state"] == status["state"] == "completed"
             and status["publication_valid"] is True and state["runtime_stage"] == "finished",
             "completed publication is required")
    _require(state["plan_sha256"] == _sha(snapshot["documents"]["plan"]), "plan digest disagrees")
    _require(budget["ledger_sha256"] == _sha(snapshot["documents"]["ledger"]), "ledger digest disagrees")
    _require(budget["schema"] == raw_ledger["schema"] == 3 and budget["blocked"] is False,
             "settled wave ledger is required")
    _require(_same(status["budget"], {key: value for key, value in budget.items() if key != "ledger_sha256"}),
             "status and ledger accounting disagree")
    _require(_same(budget["requests"], raw_ledger["requests"]) and _same(budget["waves"], raw_ledger["waves"]),
             "raw ledger and snapshot disagree")
    profile = _price_profile(plan["price_profile"])
    price_sha = _sha(price_bytes(profile))
    _require(_same(profile, budget["price_profile"]) and _same(profile, raw_ledger["price_profile"])
             and price_sha == budget["price_profile_sha256"] == raw_ledger["price_profile_sha256"],
             "declared price profile disagrees")
    _require(price_sha == plan["descriptor"]["model"]["price_profile_sha256"],
             "descriptor declared price digest disagrees")
    _require(plan["model"] == profile["model"] == budget["model"] == raw_ledger["model"]
             and plan["effort"] == budget["effort"] == raw_ledger["effort"], "model or effort disagrees")
    run_id = _identifier(plan["run_id"])
    _require(run_id == state["run_id"] == status["run_id"] == publication["run_id"], "run identity disagrees")
    _require(publication["plan_sha256"] == state["plan_sha256"]
             and publication["checkpoint_sha256"] == status["checkpoint_sha256"] == context["checkpoint_sha256"]
             and publication["schedule_sha256"] == plan["descriptor"]["schedule_sha256"] == status["schedule_sha256"],
             "publication binding disagrees")
    journals = {kind: {name: _parsed(raw) for name, raw in snapshot["journals"][kind].items()} for kind in JOURNALS}
    records = budget["requests"]
    _require(type(records) is dict and records, "request ledger is empty")
    names = {request_id + ".json" for request_id in records}
    _require(all(set(journals[kind]) == names for kind in ("requests", "responses", "receipts")),
             "request response receipt sets disagree")
    request_count = _integer(state["completed_requests"], "invalid request counter")
    _require(request_count == _integer(budget["request_count"], "invalid ledger request counter")
             == _integer(status["completed_requests"], "invalid status request counter") == len(records),
             "request counters disagree")
    timeline = [row for row in state["timeline"] if row["kind"] == "model"]
    _require(len(timeline) == len(records) and {row["request_id"] for row in timeline} == set(records),
             "timeline request coverage disagrees")
    events = {row["request_id"]: row for row in timeline}
    waves = budget["waves"]
    _require(_integer(budget["wave_count"], "invalid wave counter") == len(waves), "wave counter disagrees")
    _require(all(row["wave_id"] == key for key, row in waves.items()), "wave identity disagrees")
    wave_members = [request_id for row in waves.values() for request_id in row["request_ids"]]
    _require(len(wave_members) == len(records) and set(wave_members) == set(records), "wave request coverage disagrees")
    request_rows, calls = [], {}
    turns = {role: [] for role in ROLES}
    for request_id, record in sorted(records.items()):
        match = REQUEST_ID.fullmatch(request_id)
        _require(match is not None, "invalid request identity")
        role, turn = match.group(1), int(match.group(2))
        turns[role].append(turn)
        filename = request_id + ".json"
        request, response, receipt = (journals[kind][filename] for kind in ("requests", "responses", "receipts"))
        _require(record["request_id"] == receipt["request_id"] == request_id
                 and record["role"] == receipt["role"] == events[request_id]["role"] == role
                 and _integer(events[request_id]["turn"], "invalid timeline turn", 1) == turn and record["state"] == "settled"
                 and _same(receipt["settled"], record) and receipt["classification"] == state["classification"],
                 "request receipt settlement or role disagrees")
        _require(record["model"] == request["model"] == response["model"] == plan["model"]
                 and record["effort"] == request["reasoning"]["effort"] == plan["effort"]
                 and response["status"] == "completed" and response["service_tier"] == "default",
                 "request response model or effort disagrees")
        _require(record["wave_id"] in waves and request_id in waves[record["wave_id"]]["request_ids"],
                 "request wave binding disagrees")
        payload_sha = _sha(_json_bytes(request))
        response_sha = _sha(snapshot["journals"]["responses"][filename])
        _require(record["payload_sha256"] == receipt["payload_sha256"] == payload_sha
                 and record["response_sha256"] == receipt["response_sha256"] == response_sha,
                 "request or response digest disagrees")
        _require(_integer(record["max_output_tokens"], "invalid output cap", 1)
                 == _integer(request["max_output_tokens"], "invalid output cap", 1)
                 == _integer(plan["role_config"][role]["max_output_tokens"], "invalid output cap", 1),
                 "request output cap disagrees")
        _integer(record["input_tokens"], "invalid reserved input count")
        _integer(record["send_started_ns"], "invalid ledger wall timestamp")
        usage, details = _usage(response)
        _require(_same(record["usage"], usage) and _same(record["usage_details"], details), "response and settled usage disagree")
        _require(record["input_tokens"] == usage["input_tokens"] and usage["output_tokens"] <= record["max_output_tokens"],
                 "counted input or output reservation disagrees with usage")
        detail_counts = _detail_counts(usage, details)
        cost = _settled_cost(usage, details, profile)
        _require(_integer(record["held_tokens"], "invalid settled token count") == usage["total_tokens"]
                 and _integer(record["held_cost_micro_usd"], "invalid declared cost") == cost,
                 "settled tokens or recalculated price disagree")
        started = _integer(receipt["send_started_ns"], "invalid monotonic send timestamp")
        ended = _integer(receipt["send_ended_ns"], "invalid monotonic send timestamp")
        _require(ended >= started, "send timestamps are reversed")
        output = response.get("output")
        _require(type(output) is list, "response output is missing")
        function_calls = [item for item in output if type(item) is dict and item.get("type") == "function_call"]
        _require(len(function_calls) <= 1 and (role != "reviewer" or not function_calls), "function call coverage is invalid")
        if function_calls:
            calls[request_id] = function_calls[0]
        request_rows.append({"request_id": request_id, "role": role, "turn": turn,
                             "epoch": _integer(events[request_id]["epoch"], "invalid request epoch"),
                             "wave_id": _identifier(record["wave_id"]), "payload_sha256": payload_sha,
                             "provider_response_id_declared": _identifier(response["id"]),
                             "response_sha256": response_sha, "receipt_sha256": _sha(snapshot["journals"]["receipts"][filename]),
                             **usage, **detail_counts, "declared_cost_micro_usd": cost,
                             "send_duration_ns": ended - started})
    for role in ROLES:
        _require(sorted(turns[role]) == list(range(1, len(turns[role]) + 1))
                 and _integer(state["roles"][role]["turns"], "invalid role counter") == len(turns[role]),
                 "role turn counters disagree")
    tool_rows = _tools(snapshot, journals, calls, records, state)
    total = _aggregate(request_rows, tool_rows)
    for key in ("settled_tokens", "committed_tokens"):
        _require(_integer(budget[key], "invalid ledger token total") == total["total_tokens"], "ledger token totals disagree")
    for key in ("settled_cost_micro_usd", "committed_cost_micro_usd"):
        _require(_integer(budget[key], "invalid ledger cost total") == total["declared_cost_micro_usd"], "ledger cost totals disagree")
    for key in ("reserved_tokens", "inflight_tokens", "indeterminate_tokens", "reserved_cost_micro_usd",
                "inflight_cost_micro_usd", "indeterminate_cost_micro_usd"):
        _require(type(budget[key]) is int and budget[key] == 0, "unsettled ledger accounting remains")
    local_context = {key: _duration(context[key]) for key in ("active_seconds", "paused_seconds", "held_active_seconds", "active_limit_seconds")}
    _require(local_context["held_active_seconds"] == 0, "completed context has held activity")
    _require(local_context["active_seconds"] <= local_context["active_limit_seconds"], "local active accounting exceeds limit")
    _require(status["context"]["active_seconds"] == context["active_seconds"]
             and status["context"]["paused_seconds"] == context["paused_seconds"]
             and status["context"]["tools_reserved"] == len(tool_rows), "context accounting disagrees")
    coordinates = {key: plan["descriptor"]["coordinates"][key] for key in COORDINATES}
    for value in coordinates.values():
        _require(value is None or type(value) in (str, int), "invalid coordinate type")
        if type(value) is str:
            _identifier(value)
    route = {key: _identifier(plan["descriptor"]["provider_route"][key]) for key in ("provider", "api", "version", "service_tier")}
    return {"schema": 1, "classification": "development_coordinated_runtime_measurement",
            "run_id": run_id, "coordinates": coordinates, "model": _identifier(plan["model"]),
            "effort_declared": _identifier(plan["effort"]), "provider_route_declared": route,
            "provenance": {"provider_route_scope": "local_declaration_not_authenticated_provider_identity",
                           "synthetic_route_declared": route["provider"] == "fixture",
                           "usage_scope": "journal_response_telemetry_not_authenticated_provider_usage",
                           "tools_scope": "local_D119_sandbox_host_receipts_not_remote_activity"},
            "schedule_sha256": _digest(status["schedule_sha256"]),
            "snapshot_sha256": {key: _sha(raw) for key, raw in snapshot["documents"].items()},
            "checkpoint_sha256": _digest(status["checkpoint_sha256"]), "price_profile_declared": profile,
            "price_profile_sha256": price_sha, "requests": request_rows, "tools": tool_rows,
            "totals": total, "by_role": {role: _aggregate([row for row in request_rows if row["role"] == role],
                                                          [row for row in tool_rows if row["role"] == role]) for role in ROLES},
            "context_local_accounting": local_context,
            "coverage": {"request_response_receipt_ledger_exact": True, "tool_reservation_receipt_response_exact": True,
                         "full_activity_coverage": False},
            "scopes": {"send": "sum_of_per_request_monotonic_elapsed_intervals_no_clock_union",
                       "tools": "sandbox_and_host_sums_separate_host_includes_sandbox",
                       "context": "local_active_lease_and_pause_accounting_not_remote_activity",
                       "cost": "local_declared_profile_ceil_each_request_then_sum_unclassified_input_at_max_rate",
                       "token_details": "absence_unknown_reasoning_subset_of_output_cache_subset_of_input",
                       "snapshot": "cooperative_original_lock_same_uid_hashes_not_custody_authentication"},
            "missing": ["W_release_to_delivery_with_identified_clock", "H_human_time", "input_count_timing",
                        "remote_activity", "global_clock_or_boot_identity", "full_activity_coverage", "tool_pricing",
                        "human_review_cost", "scoring_cost", "total_study_cost", "authenticated_provider_invoice",
                        "effective_effort", "quality_scoring"]
                       + (["complete_cache_and_reasoning_breakdown"] if any(total["token_details"][key]["unknown_requests"] for key in DETAILS) else []),
            "identity_authenticated": False, "cost_authenticated": False, "bundle_custody_authenticated": False,
            "paid_route_authorized": False, "formal_cell_executed": False, "comparable_development_cell": False,
            "quality_assessed": False, "method_phases_accepted": False, "Q_demonstrated": False}


def _tools(snapshot: dict, journals: dict, calls: dict, records: dict, state: dict) -> list[dict]:
    reservations, receipts = journals["tool_reservations"], journals["tool_receipts"]
    count = _integer(state["tool_calls_completed"], "invalid tool counter")
    _require(_integer(snapshot["status"]["tool_calls_completed"], "invalid status tool counter") == count,
             "tool counters disagree")
    names = {f"{number:04d}.json" for number in range(1, count + 1)}
    _require(set(reservations) == set(receipts) == names and len(calls) == count
             and set(snapshot["streams"]) == {name[:-5] for name in names}, "tool journal or response call sets disagree")
    seen, used, counters, result = set(), set(), dict.fromkeys(ROLES, 0), []
    for number in range(1, count + 1):
        name = f"{number:04d}.json"
        reservation, receipt = reservations[name], receipts[name]
        role, request_id = reservation["task_id"], reservation["request_id"]
        _require(role in ROLES and role != "reviewer" and request_id in calls and request_id not in used
                 and records[request_id]["role"] == role, "tool request or role binding disagrees")
        used.add(request_id)
        counters[role] += 1
        for key in ("manifest_sha256", "claim_sha256", "task_id", "request_id", "call_id", "function_name", "profile",
                    "global_ordinal", "local_ordinal", "epoch"):
            _require(_same(reservation[key], receipt[key]), "tool reservation and receipt disagree")
        _require(_integer(reservation["schema"], "invalid tool reservation schema") == 1
                 and _integer(receipt["schema"], "invalid tool receipt schema") == 1,
                 "tool journal schema disagrees")
        for key in ("global_ordinal", "local_ordinal", "epoch"):
            _integer(receipt[key], "invalid tool receipt ordinal")
        _require(_integer(reservation["global_ordinal"], "invalid tool ordinal", 1) == number
                 and _integer(reservation["local_ordinal"], "invalid local tool ordinal", 1) == counters[role]
                 and reservation["manifest_sha256"] == state["broker_binding"]["sha256"]
                 and reservation["claim_sha256"] == state["claim_sha256"], "tool ordinal or immutable binding disagrees")
        if role != "leader":
            event = next(row for row in state["timeline"] if row["kind"] == "model" and row["request_id"] == request_id)
            _require(_integer(reservation["epoch"], "invalid tool epoch") == event["epoch"],
                     "tool request epoch disagrees")
        else:
            _require(type(reservation["epoch"]) is int and reservation["epoch"] == 0,
                     "leader tool epoch must be original broker epoch zero")
        _require(receipt["reservation_sha256"] == _sha(snapshot["journals"]["tool_reservations"][name]),
                 "tool reservation digest disagrees")
        call = calls[request_id]
        _require(reservation["call_id"] == call["call_id"] and reservation["call_id"] not in seen
                 and reservation["function_name"] == call["name"], "tool call identity disagrees")
        seen.add(reservation["call_id"])
        _require(type(reservation["arguments"]) is str and type(call["arguments"]) is str,
                 "tool arguments are invalid")
        _require(reservation["arguments_sha256"] == _sha(reservation["arguments"].encode())
                 and parse_json(reservation["arguments"].encode()) == parse_json(call["arguments"].encode()),
                 "tool response arguments and reservation disagree")
        for stream, raw in snapshot["streams"][name[:-5]].items():
            _require(type(raw) is bytes and receipt[stream + "_sha256"] == _sha(raw)
                     and _integer(receipt[stream + "_bytes"], "invalid tool stream size") == len(raw),
                     "tool stream bytes or digest disagree")
        sandbox = receipt["sandbox"]
        _require(set(snapshot["streams"][name[:-5]]) == {"stdout", "stderr"}, "tool stream inventory disagrees")
        _require((reservation["function_name"], reservation["profile"])
                 in {("development_method", "workspace"), ("development_analysis", "analysis_readonly")},
                 "tool function or profile disagrees")
        _require(sandbox["timed_out"] is False and sandbox["launch_error"] is None
                 and type(sandbox["exit_code"]) is int and sandbox["exit_code"] >= 0,
                 "tool execution is uncertain")
        result.append({"role": role, "request_id": request_id, "call_id": _identifier(reservation["call_id"]),
                       "function_name": _identifier(reservation["function_name"]), "profile": _identifier(reservation["profile"]),
                       "global_ordinal": number, "local_ordinal": counters[role],
                       "epoch": _integer(reservation["epoch"], "invalid tool epoch"),
                       "reservation_sha256": _sha(snapshot["journals"]["tool_reservations"][name]),
                       "receipt_sha256": _sha(snapshot["journals"]["tool_receipts"][name]),
                       "stdout_sha256": _digest(receipt["stdout_sha256"]), "stderr_sha256": _digest(receipt["stderr_sha256"]),
                       "status": _identifier(receipt["status"]), "exit_code": sandbox["exit_code"],
                       "sandbox_duration_seconds": _duration(sandbox["duration_seconds"]),
                       "host_elapsed_seconds": _duration(sandbox["host_elapsed_seconds"])})
    _require(used == set(calls), "response tool calls are not fully reconciled")
    return result


def measure_run(run_dir: Path) -> dict:
    report = reconcile_snapshot(snapshot_runtime(run_dir))
    report["native_D119_guard_replay_publication_verified"] = True
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = measure_run(args.run_dir)
    except MeasurementError as exc:
        print(json.dumps({"error": "measurement_rejected", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
