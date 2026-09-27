"""Audit *declared* execution receipts against an unsealed candidate schedule.

Usage: ``python scripts/audit_run_receipts.py schedule.json attempts.json``.
Either argument may be ``-`` for stdin, but not both. The command only reads
JSON and prints JSON; it never runs a provider or authenticates a receipt.

Schema 1 for the second input::

    {
      "schema": 1, "schedule_sha256": "<schedule digest>",
      "attempts": [{
        "run_id": "conf-...", "run_sha256": "<run digest>",
        "attempt_number": 1, "session_id": "unique-session-id",
        "status": "completed", "model_id": "model-id",
        "model_version": "version", "effort": "low",
        "effort_provider_value": "low", "agents": "solo",
        "case_id": "R-F", "replica": 1, "arm": "T",
        "started_at_utc": "2026-01-01T00:00:00Z",
        "ended_at_utc": "2026-01-01T00:00:12Z",
        "human_wait_seconds": 2, "active_seconds": 10,
        "trace_sha256": "<trace digest>",
        "artifact_sha256": "<artifact digest>",
        "agent_usage": [{"agent_id": "main", "tool_calls": 1,
          "provider_calls": [{"request_id": "provider-request-id",
            "input_total": 80, "cached_input": 10,
            "output_total": 20, "reasoning_output": 5}]}]
      }]
    }

Use ``external_failure`` with an ``incident_sha256`` and without an artifact
for an externally caused failed attempt. Only such a failure may precede the
next attempt of the same run. ``truncated`` may omit its artifact digest when
no usable artifact exists; it is terminal even in that case. All timestamps
are UTC RFC 3339 with a literal Z and at most microsecond precision.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from analyze_confirmatory import (
    AnalysisError,
    _canonical_digest,
    _nonempty_text as _analysis_nonempty_text,
    _read_json,
    _sha256 as _analysis_sha256,
    _validate_schedule,
)


CLASSIFICATION = "development_receipt_audit_unsealed"
NOTICE = (
    "Offline audit of declared JSON only. Provider telemetry and identity, "
    "session isolation, prices, and costs are not authenticated; trace and "
    "artifact digests are declared only, not checked against bytes or signed. "
    "Global release_block_order requires a separately custodied release event; "
    "start timestamps alone do not prove it. "
    "Receipt coverage does not establish a complete Q matrix. This is never "
    "confirmatory evidence or criterion 4 compliance."
)
TOKEN_CAP = 80_000
ACTIVE_SECONDS_CAP = 5_400
EXTERNAL_RETRY_CAP = 10
SIMULTANEOUS_CAP = 4
UTC_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
BASE_FIELDS = frozenset({
    "run_id", "run_sha256", "attempt_number", "session_id", "status",
    "model_id", "model_version", "effort", "effort_provider_value",
    "agents", "case_id", "replica", "arm", "started_at_utc",
    "ended_at_utc", "human_wait_seconds", "active_seconds",
    "trace_sha256", "agent_usage",
})
CALL_FIELDS = frozenset({
    "request_id", "input_total", "cached_input", "output_total", "reasoning_output",
})


class ReceiptError(AnalysisError):
    """Malformed or inconsistently bound receipt declaration."""


def _nonempty_text(value: Any, label: str) -> str:
    try:
        return _analysis_nonempty_text(value, label)
    except AnalysisError as exc:
        raise ReceiptError(str(exc)) from exc


def _sha256(value: Any, label: str) -> str:
    try:
        return _analysis_sha256(value, label)
    except AnalysisError as exc:
        raise ReceiptError(str(exc)) from exc


def _object(value: Any, label: str, *, required: frozenset[str], optional: frozenset[str] = frozenset()) -> dict[str, Any]:
    if type(value) is not dict:
        raise ReceiptError(f"{label} must be an object")
    missing = required - value.keys()
    extra = value.keys() - required - optional
    if missing or extra:
        raise ReceiptError(f"{label} has missing keys {sorted(missing)} or unexpected keys {sorted(extra)}")
    return value


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ReceiptError(f"{label} must be an integer >= {minimum}")
    return value


def _seconds(value: Any, label: str) -> int | float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ReceiptError(f"{label} must be a finite nonnegative number")
    return value


def _utc_time(value: Any, label: str) -> datetime:
    if type(value) is not str or UTC_TIMESTAMP.fullmatch(value) is None:
        raise ReceiptError(f"{label} must be a UTC RFC 3339 timestamp ending in Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as exc:
        raise ReceiptError(f"{label} is not a valid UTC timestamp") from exc


def _limits(schedule: dict[str, Any]) -> int:
    limits = _object(
        schedule.get("per_run_limits"), "schedule.per_run_limits",
        required=frozenset({"measured_tokens", "active_seconds", "tool_calls"}),
    )
    if type(limits["measured_tokens"]) is not int or limits["measured_tokens"] != TOKEN_CAP:
        raise ReceiptError(f"schedule.per_run_limits.measured_tokens must be {TOKEN_CAP}")
    if type(limits["active_seconds"]) is not int or limits["active_seconds"] != ACTIVE_SECONDS_CAP:
        raise ReceiptError(f"schedule.per_run_limits.active_seconds must be {ACTIVE_SECONDS_CAP}")
    study = _object(
        schedule.get("study_limits"), "schedule.study_limits",
        required=frozenset({
            "max_confirmatory_runs", "max_simultaneous_runs", "external_retry_slots_studywide",
        }),
    )
    if type(study["external_retry_slots_studywide"]) is not int or study["external_retry_slots_studywide"] != EXTERNAL_RETRY_CAP:
        raise ReceiptError(f"schedule.study_limits.external_retry_slots_studywide must be {EXTERNAL_RETRY_CAP}")
    if type(study["max_simultaneous_runs"]) is not int or study["max_simultaneous_runs"] != SIMULTANEOUS_CAP:
        raise ReceiptError(f"schedule.study_limits.max_simultaneous_runs must be {SIMULTANEOUS_CAP}")
    return limits["tool_calls"]


def _agent_usage(
    value: Any,
    label: str,
    expected_agents: str,
    request_ids: set[str],
    *,
    require_positive_input: bool,
    require_trio_participation: bool,
) -> tuple[int, int, int]:
    count = 1 if expected_agents == "solo" else 3
    if type(value) is not list or len(value) != count:
        raise ReceiptError(f"{label} must contain exactly {count} agents")
    agent_ids: set[str] = set()
    tokens = calls = tool_calls = 0
    for index, raw_agent in enumerate(value):
        agent_label = f"{label}[{index}]"
        agent = _object(
            raw_agent, agent_label,
            required=frozenset({"agent_id", "tool_calls", "provider_calls"}),
        )
        agent_id = _nonempty_text(agent["agent_id"], f"{agent_label}.agent_id")
        if agent_id in agent_ids:
            raise ReceiptError(f"duplicate agent_id within attempt: {agent_id}")
        agent_ids.add(agent_id)
        tool_calls += _integer(agent["tool_calls"], f"{agent_label}.tool_calls")
        rows = agent["provider_calls"]
        if type(rows) is not list:
            raise ReceiptError(f"{agent_label}.provider_calls must be an array")
        if require_trio_participation and expected_agents == "trio" and not rows:
            raise ReceiptError(
                f"{agent_label}.provider_calls requires a positive-input call for a completed trio"
            )
        for call_index, raw_call in enumerate(rows):
            call_label = f"{agent_label}.provider_calls[{call_index}]"
            call = _object(raw_call, call_label, required=CALL_FIELDS)
            request_id = _nonempty_text(call["request_id"], f"{call_label}.request_id")
            if request_id in request_ids:
                raise ReceiptError(f"duplicate provider request_id: {request_id}")
            request_ids.add(request_id)
            measured = {
                key: _integer(call[key], f"{call_label}.{key}")
                for key in (
                    "input_total",
                    "cached_input",
                    "output_total",
                    "reasoning_output",
                )
            }
            if require_positive_input and measured["input_total"] == 0:
                raise ReceiptError(
                    f"{call_label}.input_total must be positive for a terminal attempt"
                )
            if measured["cached_input"] > measured["input_total"]:
                raise ReceiptError(f"{call_label}.cached_input exceeds input_total")
            if measured["reasoning_output"] > measured["output_total"]:
                raise ReceiptError(f"{call_label}.reasoning_output exceeds output_total")
            # Cached input and reasoning output are already included in their
            # respective provider totals; neither contributes a second time.
            tokens += measured["input_total"] + measured["output_total"]
            calls += 1
    return tokens, calls, tool_calls


def _validate_attempt(
    raw: Any, index: int, scheduled: dict[str, dict[str, Any]],
    sessions: set[str], request_ids: set[str],
) -> dict[str, Any]:
    label = f"attempts[{index}]"
    attempt = _object(
        raw, label, required=BASE_FIELDS,
        optional=frozenset({"artifact_sha256", "incident_sha256"}),
    )
    run_id = _nonempty_text(attempt["run_id"], f"{label}.run_id")
    if run_id not in scheduled:
        raise ReceiptError(f"unscheduled run_id: {run_id}")
    run = scheduled[run_id]
    if _sha256(attempt["run_sha256"], f"{label}.run_sha256") != run["run_sha256"]:
        raise ReceiptError(f"run_sha256 mismatch for {run_id}")
    number = _integer(attempt["attempt_number"], f"{label}.attempt_number", minimum=1)
    session = _nonempty_text(attempt["session_id"], f"{label}.session_id")
    if session in sessions:
        raise ReceiptError(f"duplicate session_id: {session}")
    sessions.add(session)
    status = attempt["status"]
    if type(status) is not str or status not in ("completed", "truncated", "external_failure"):
        raise ReceiptError(f"{label}.status must be completed, truncated, or external_failure")
    for key in ("model_id", "model_version", "effort", "effort_provider_value", "agents", "case_id", "replica", "arm"):
        if type(attempt[key]) is not type(run[key]) or attempt[key] != run[key]:
            raise ReceiptError(f"{label}.{key} differs from scheduled {run_id}")
    start = _utc_time(attempt["started_at_utc"], f"{label}.started_at_utc")
    end = _utc_time(attempt["ended_at_utc"], f"{label}.ended_at_utc")
    if end < start:
        raise ReceiptError(f"{label} ends before it starts")
    wait = _seconds(attempt["human_wait_seconds"], f"{label}.human_wait_seconds")
    active = _seconds(attempt["active_seconds"], f"{label}.active_seconds")
    elapsed = (end - start).total_seconds()
    if not math.isclose(wait + active, elapsed, rel_tol=0, abs_tol=0.001):
        raise ReceiptError(f"{label} active_seconds + human_wait_seconds differs from elapsed UTC time")
    _sha256(attempt["trace_sha256"], f"{label}.trace_sha256")
    if status == "external_failure":
        if "artifact_sha256" in attempt:
            raise ReceiptError(f"{label} external_failure cannot carry an artifact")
        _sha256(attempt.get("incident_sha256"), f"{label}.incident_sha256")
    else:
        if "incident_sha256" in attempt:
            raise ReceiptError(f"{label} terminal status cannot carry incident_sha256")
        if status == "completed" or "artifact_sha256" in attempt:
            _sha256(attempt.get("artifact_sha256"), f"{label}.artifact_sha256")
    tokens, calls, tool_calls = _agent_usage(
        attempt["agent_usage"],
        f"{label}.agent_usage",
        run["agents"],
        request_ids,
        require_positive_input=status in ("completed", "truncated"),
        require_trio_participation=status == "completed",
    )
    if status in ("completed", "truncated") and calls == 0:
        raise ReceiptError(f"{label} terminal attempt requires a declared provider call")
    return {
        "run_id": run_id, "run_sha256": run["run_sha256"],
        "attempt_number": number, "session_id": session, "status": status,
        "started_at_utc": attempt["started_at_utc"],
        "ended_at_utc": attempt["ended_at_utc"],
        "start": start, "end": end,
        "active_seconds": active, "human_wait_seconds": wait,
        "provider_calls": calls, "measured_tokens": tokens, "tool_calls": tool_calls,
        "trace_sha256": attempt["trace_sha256"],
        "artifact_sha256": attempt.get("artifact_sha256"),
        "incident_sha256": attempt.get("incident_sha256"),
    }


def audit_receipts(raw_schedule: Any, raw_receipts: Any) -> dict[str, Any]:
    """Validate declarations and report complete coverage and every cap breach."""
    schedule, _, _ = _validate_schedule(raw_schedule)
    tool_cap = _limits(schedule)
    receipts = _object(
        raw_receipts, "receipts",
        required=frozenset({"schema", "schedule_sha256", "attempts"}),
    )
    if type(receipts["schema"]) is not int or receipts["schema"] != 1:
        raise ReceiptError("receipts.schema must be integer 1")
    if _sha256(receipts["schedule_sha256"], "receipts.schedule_sha256") != schedule["schedule_sha256"]:
        raise ReceiptError("receipt schedule_sha256 mismatch")
    if type(receipts["attempts"]) is not list:
        raise ReceiptError("receipts.attempts must be an array")
    scheduled = {run["run_id"]: run for run in schedule["runs"]}
    sessions: set[str] = set()
    request_ids: set[str] = set()
    by_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
    intervals: list[tuple[datetime, int]] = []
    for index, raw in enumerate(receipts["attempts"]):
        item = _validate_attempt(raw, index, scheduled, sessions, request_ids)
        by_run[item["run_id"]].append(item)
        if item["end"] > item["start"]:
            intervals.extend(((item["start"], 1), (item["end"], -1)))

    violations: list[dict[str, Any]] = []
    run_reports: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    first_attempt_by_run: dict[str, dict[str, Any]] = {}
    terminal_attempt_by_run: dict[str, dict[str, Any]] = {}
    retries = 0
    completed = truncated = failures = provider_calls = measured_tokens = tool_calls = 0
    active_seconds = human_wait_seconds = 0.0
    for run in schedule["runs"]:
        run_id = run["run_id"]
        attempts = sorted(by_run.get(run_id, []), key=lambda item: item["attempt_number"])
        numbers = [item["attempt_number"] for item in attempts]
        if numbers != list(range(1, len(attempts) + 1)):
            raise ReceiptError(f"attempt numbers for {run_id} must be consecutive from 1")
        for previous, current in zip(attempts, attempts[1:]):
            if previous["status"] != "external_failure":
                raise ReceiptError(f"terminal {previous['status']} attempt for {run_id} cannot be retried")
            if current["start"] < previous["end"]:
                raise ReceiptError(f"attempts for {run_id} overlap or are out of time order")
        if attempts:
            first_attempt_by_run[run_id] = attempts[0]
            if attempts[-1]["status"] in ("completed", "truncated"):
                terminal_attempt_by_run[run_id] = attempts[-1]
        retries += max(0, len(attempts) - 1)
        run_tokens = sum(item["measured_tokens"] for item in attempts)
        run_active = math.fsum(item["active_seconds"] for item in attempts)
        run_wait = math.fsum(item["human_wait_seconds"] for item in attempts)
        run_tools = sum(item["tool_calls"] for item in attempts)
        failures += sum(item["status"] == "external_failure" for item in attempts)
        provider_calls += sum(item["provider_calls"] for item in attempts)
        measured_tokens += run_tokens
        tool_calls += run_tools
        active_seconds += run_active
        human_wait_seconds += run_wait
        for item in attempts:
            if item["provider_calls"] and item["active_seconds"] == 0:
                violations.append(
                    {
                        "code": "zero_active_time_with_provider_call",
                        "run_id": run_id,
                        "attempt_number": item["attempt_number"],
                        "provider_calls": item["provider_calls"],
                    }
                )
            attempt_limits = (
                ("measured_tokens", item["measured_tokens"], TOKEN_CAP),
                ("active_seconds", item["active_seconds"], ACTIVE_SECONDS_CAP),
                ("tool_calls", item["tool_calls"], tool_cap),
            )
            for metric, actual, limit in attempt_limits:
                if actual > limit:
                    violations.append(
                        {
                            "code": f"{metric}_over_cap",
                            "run_id": run_id,
                            "attempt_number": item["attempt_number"],
                            "actual": actual,
                            "limit": limit,
                        }
                    )
            if item["status"] == "truncated" and all(
                actual < limit for _, actual, limit in attempt_limits
            ):
                violations.append(
                    {
                        "code": "truncation_without_exhausted_limit",
                        "run_id": run_id,
                        "attempt_number": item["attempt_number"],
                        "actual": {
                            metric: actual for metric, actual, _ in attempt_limits
                        },
                        "limits": {
                            metric: limit for metric, _, limit in attempt_limits
                        },
                    }
                )
        outcome = attempts[-1]["status"] if attempts else "missing"
        if outcome == "completed":
            completed += 1
        elif outcome == "truncated":
            truncated += 1
        else:
            missing.append({"run_id": run_id,
                            "reason": "external_failure_without_terminal_receipt" if attempts else "no_attempt_receipt"})
        run_reports.append({
            "run_id": run_id, "run_sha256": run["run_sha256"],
            "outcome": outcome, "attempt_count": len(attempts),
            "measured_tokens": run_tokens, "active_seconds": run_active,
            "human_wait_seconds": run_wait, "tool_calls": run_tools,
            "provider_calls": sum(item["provider_calls"] for item in attempts),
            "attempts": [{key: value for key, value in item.items() if key not in ("start", "end", "run_id", "run_sha256")}
                         for item in attempts],
        })
    blocks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in schedule["runs"]:
        blocks[run["block_id"]].append(run)
    for block_id, runs in blocks.items():
        ordered = sorted(runs, key=lambda run: run["order_position"])
        if all(run["run_id"] in first_attempt_by_run for run in ordered):
            first_attempts = [first_attempt_by_run[run["run_id"]] for run in ordered]
            if not all(left["start"] < right["start"]
                       for left, right in zip(first_attempts, first_attempts[1:])):
                violations.append({
                    "code": "arm_start_order_mismatch", "block_id": block_id,
                    "run_ids_by_order_position": [run["run_id"] for run in ordered],
                    "first_started_at_utc": [item["started_at_utc"] for item in first_attempts],
                })
        # A later arm can start only after every retry of the previous arm has
        # ended in a completed or truncated terminal receipt. A failure without
        # a terminal retry, or no prior attempt at all, stops that block.
        for prior, later in zip(ordered, ordered[1:]):
            later_first = first_attempt_by_run.get(later["run_id"])
            if later_first is None:
                continue
            prior_terminal = terminal_attempt_by_run.get(prior["run_id"])
            if prior_terminal is None or later_first["start"] < prior_terminal["end"]:
                prior_attempts = by_run.get(prior["run_id"], [])
                prior_last = max(prior_attempts, key=lambda item: item["attempt_number"]) if prior_attempts else None
                violations.append({
                    "code": "block_advanced_before_prior_terminal", "block_id": block_id,
                    "prior_run_id": prior["run_id"], "next_run_id": later["run_id"],
                    "prior_status": prior_last["status"] if prior_last else "missing",
                    "prior_last_ended_at_utc": prior_last["ended_at_utc"] if prior_last else None,
                    "next_first_started_at_utc": later_first["started_at_utc"],
                })
    if retries > EXTERNAL_RETRY_CAP:
        violations.append({"code": "external_retry_slots_over_cap", "actual": retries,
                           "limit": EXTERNAL_RETRY_CAP})
    # Half-open intervals let a new run start exactly when another ends.
    simultaneous = peak_simultaneous = 0
    for _, delta in sorted(intervals, key=lambda event: (event[0], event[1])):
        simultaneous += delta
        peak_simultaneous = max(peak_simultaneous, simultaneous)
    if peak_simultaneous > SIMULTANEOUS_CAP:
        violations.append({"code": "simultaneous_runs_over_cap",
                           "actual": peak_simultaneous, "limit": SIMULTANEOUS_CAP})
    return {
        "schema": 1,
        "classification": CLASSIFICATION,
        "notice": NOTICE,
        "schedule_sha256": schedule["schedule_sha256"],
        "receipts_sha256": _canonical_digest(receipts),
        "matrix_receipts_complete": not missing and not violations,
        "counts": {
            "scheduled_runs": len(scheduled), "attempted_runs": len(by_run),
            "completed_runs": completed, "truncated_runs": truncated,
            "missing_runs": len(missing), "external_failures": failures,
            "total_attempts": len(receipts["attempts"]), "retry_attempts": retries,
            "provider_calls": provider_calls, "measured_tokens": measured_tokens,
            "tool_calls": tool_calls, "active_seconds": active_seconds,
            "human_wait_seconds": human_wait_seconds,
            "peak_simultaneous_runs": peak_simultaneous,
            "violations": len(violations),
        },
        "missing_runs": missing,
        "violations": violations,
        "runs": run_reports,
        "criterion_4": {"status": "not_assessed", "reason": NOTICE},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("schedule", help="candidate schedule JSON path, or - for stdin")
    parser.add_argument("receipts", help="schema-1 attempts JSON path, or - for stdin")
    args = parser.parse_args(argv)
    try:
        if args.schedule == args.receipts == "-":
            raise ReceiptError("only one input may use stdin")
        output = audit_receipts(_read_json(args.schedule), _read_json(args.receipts))
    except (AnalysisError, ReceiptError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": 1, "classification": CLASSIFICATION, "error": str(exc)},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
