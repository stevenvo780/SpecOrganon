"""Read-only arithmetic for declared criterion-4 secondary metrics.

Usage: ``python scripts/analyze_secondary_metrics.py schedule.json receipts.json
rated_q_assembly.json secondary.json``. At most one path may be ``-`` for stdin.
Every response is unsealed and criterion 4 remains not assessed.

The schema-1 secondary document has exactly ``schema``, ``schedule_sha256``,
``receipts_sha256``, ``assembly_sha256``, ``rate_card_sha256``, and ``runs``.
Every scheduled run has either ``{run_id, status: missing, reason}`` or the
measured row described by the field sets below. Digests are pointers to
externally held evidence; this command does not authenticate their bytes.
``recovery.resume_seconds`` may be null only for a failed recovery that never
resumed; a failed recovery that did resume keeps its measured duration.
``recovery`` may instead be ``{status: missing, reason: ...}`` while the other
secondary metrics remain measured. Human active durations use five disjoint
event categories whose declared sum equals ``human.active_seconds``.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal, localcontext
from statistics import median
from typing import Any

from analyze_confirmatory import (
    AGENTS, ARMS, CASES, DEFAULT_RESAMPLES, REPLICAS, AnalysisError,
    _canonical_digest, _nonempty_text, _percentile, _read_json, _sha256,
    _validate_evaluations, _validate_schedule,
)
from audit_run_receipts import ReceiptError, _utc_time, audit_receipts
from reconcile_matrix_evidence import reconcile


CLASSIFICATION = "development_secondary_analysis_unsealed"
NOTICE = (
    "Read-only arithmetic over declared JSON. Schedule, receipts, assembly and "
    "secondary digests bind these declarations only; source/reference, audit, "
    "injection, human, wall, invoice and rate-card bytes are not opened. The "
    "assembly is checked for internal Q/incident/E consistency but raw judge "
    "files, identity, independence, blinding, custody, provider telemetry, prices, "
    "and release events are not authenticated. The injection digest has no "
    "declared start/end times, so recovery duration cannot be anchored to the "
    "injection event. Recovery-only missing data leave R unavailable. Within-run "
    "human event categories and nonoverlapping active-time allocation are declarations; "
    "independent final outcome-rating time/cost is outside per-run H/P. "
    "No criterion 4 threshold or "
    "external seal is assessed."
)
TOP_FIELDS = frozenset({
    "schema", "schedule_sha256", "receipts_sha256", "assembly_sha256",
    "rate_card_sha256", "runs",
})
MEASURED_FIELDS = frozenset({
    "run_id", "status", "reference_sha256", "audit_sha256", "compliance",
    "traceability", "recovery", "human", "wall", "cost",
})
COMPLIANCE_FIELDS = frozenset({"met", "required", "critical_omissions"})
TRACE_FIELDS = frozenset({
    "tp", "fp", "fn", "complete_requirements", "required_requirements",
    "complete_indicators", "required_indicators",
})
RECOVERY_FIELDS = frozenset({
    "injection_sha256", "recovered", "resume_seconds", "repeated_decisions",
})
RECOVERY_MISSING_FIELDS = frozenset({"status", "reason"})
HUMAN_FIELDS = frozenset({
    "active_seconds", "active_seconds_by_type", "wait_seconds", "events_sha256",
    "event_counts",
})
HUMAN_EVENT_TYPES = frozenset({
    "approvals", "external_reviews", "blocks", "corrections", "unblocks",
})
WALL_FIELDS = frozenset({"released_at_utc", "delivered_at_utc", "event_sha256"})
COST_FIELDS = frozenset({
    "model_usd", "tools_usd", "human_usd", "total_usd", "invoice_sha256",
})
ASSEMBLY_FIELDS = frozenset({
    "schema", "classification", "notice", "mapping_schema", "schedule_sha256",
    "receipts_sha256", "manifest_sha256", "ratings_sha256", "mapping_sha256",
    "duplicate_terminal_pairs_requiring_external_preparation_verification",
    "evaluations", "details", "counts", "criterion_4",
})
DETAIL_FIELDS = frozenset({
    "run_id", "opaque_id", "terminal_artifact_sha256", "terminal_trace_sha256",
    "blind_package_sha256", "blind_trace_sha256", "preparation_record_sha256",
    "raw_q", "raw_critical_incidents", "adjudication", "sensitivity",
    "critical_incidents", "E",
})
DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
MAX_COUNT = 10**12
MAX_SECONDS = 10**12
MAX_MONEY_CHARS = 256
INCIDENT_ID = re.compile(r"[0-9a-f]{32}\Z")
FAILURE_CODE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
Q_COMPONENTS = frozenset({
    "formulation", "evidence", "alternatives", "technical", "validation",
})


class SecondaryError(AnalysisError):
    """Inconsistent or invalid declared secondary evidence."""


def _exact(value: Any, label: str, fields: frozenset[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise SecondaryError(f"{label} must be an object")
    missing, extra = fields - value.keys(), value.keys() - fields
    if missing or extra:
        raise SecondaryError(
            f"{label} has missing keys {sorted(missing)} or unexpected keys {sorted(extra)}"
        )
    return value


def _rows(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise SecondaryError(f"{label} must be an array")
    return value


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= MAX_COUNT:
        raise SecondaryError(f"{label} must be an integer from {minimum} through {MAX_COUNT}")
    return value


def _seconds(value: Any, label: str) -> int | float:
    if (type(value) not in (int, float) or value < 0 or value > MAX_SECONDS
            or (type(value) is float and not math.isfinite(value))):
        raise SecondaryError(f"{label} must be a finite number from 0 through {MAX_SECONDS}")
    return value


def _money(value: Any, label: str) -> Decimal:
    if (type(value) is not str or len(value) > MAX_MONEY_CHARS
            or DECIMAL.fullmatch(value) is None):
        raise SecondaryError(
            f"{label} must be a nonnegative decimal string of at most {MAX_MONEY_CHARS} characters"
        )
    try:
        return Decimal(value)
    except ArithmeticError as exc:
        raise SecondaryError(f"{label} is not a valid decimal amount") from exc


def _incident_map(value: Any, label: str) -> dict[str, str]:
    if type(value) is not dict:
        raise SecondaryError(f"{label} must be an incident-id-to-code object")
    for incident_id, code in value.items():
        if type(incident_id) is not str or INCIDENT_ID.fullmatch(incident_id) is None:
            raise SecondaryError(f"{label} has an invalid incident_id")
        if type(code) is not str or FAILURE_CODE.fullmatch(code) is None:
            raise SecondaryError(f"{label}.{incident_id} has an invalid failure code")
    return value


def _rating_q(value: Any, label: str) -> tuple[str, int]:
    row = _exact(value, label, frozenset({"evaluator_id", "q_components", "q_total"}))
    evaluator = _nonempty_text(row["evaluator_id"], f"{label}.evaluator_id")
    components = _exact(row["q_components"], f"{label}.q_components", Q_COMPONENTS)
    total = sum(_integer(score, f"{label}.q_components.{name}") for name, score in components.items())
    if any(score > 20 for score in components.values()):
        raise SecondaryError(f"{label}.q_components must be 0..20")
    declared = _integer(row["q_total"], f"{label}.q_total")
    if declared > 100 or declared != total:
        raise SecondaryError(f"{label}.q_total differs from its five components")
    return evaluator, declared


def _rating_incidents(value: Any, label: str) -> tuple[str, dict[str, str]]:
    row = _exact(value, label, frozenset({"evaluator_id", "incidents"}))
    evaluator = _nonempty_text(row["evaluator_id"], f"{label}.evaluator_id")
    return evaluator, _incident_map(row["incidents"], f"{label}.incidents")


def _validate_detail(
    value: Any, index: int, evaluations: dict[str, dict[str, Any]],
    receipts: dict[str, dict[str, Any]], mapping_schema: int,
) -> tuple[str, int, bool, dict[str, str]]:
    label = f"assembly.details[{index}]"
    detail = _exact(value, label, DETAIL_FIELDS)
    run_id = _nonempty_text(detail["run_id"], f"{label}.run_id")
    if run_id not in evaluations or "q" not in evaluations[run_id]:
        raise SecondaryError(f"{label} does not identify a scored scheduled run")
    if type(detail["opaque_id"]) is not str or INCIDENT_ID.fullmatch(detail["opaque_id"]) is None:
        raise SecondaryError(f"{label}.opaque_id must be 32 lowercase hex digits")
    receipt = receipts[run_id]
    if receipt["outcome"] not in ("completed", "truncated") or not receipt["attempts"]:
        raise SecondaryError(f"{label} has no terminal receipt")
    terminal = receipt["attempts"][-1]
    for key, expected in (
        ("terminal_artifact_sha256", terminal["artifact_sha256"]),
        ("terminal_trace_sha256", terminal["trace_sha256"]),
    ):
        if _sha256(detail[key], f"{label}.{key}") != expected:
            raise SecondaryError(f"{label}.{key} differs from terminal receipt")
    if detail["terminal_artifact_sha256"] != evaluations[run_id].get("artifact_sha256"):
        raise SecondaryError(f"{label} differs from scored evaluation artifact")
    _sha256(detail["blind_package_sha256"], f"{label}.blind_package_sha256")
    _sha256(detail["blind_trace_sha256"], f"{label}.blind_trace_sha256")
    if mapping_schema == 1:
        if detail["preparation_record_sha256"] is not None:
            raise SecondaryError(f"{label}.preparation_record_sha256 must be null for schema 1")
        if (detail["blind_package_sha256"] != detail["terminal_artifact_sha256"]
                or detail["blind_trace_sha256"] != detail["terminal_trace_sha256"]):
            raise SecondaryError(f"{label} schema-1 blind and terminal digests differ")
    else:
        _sha256(detail["preparation_record_sha256"], f"{label}.preparation_record_sha256")

    raw_q = _exact(detail["raw_q"], f"{label}.raw_q", frozenset({"primary", "adjudicator"}))
    primary_q = _rows(raw_q["primary"], f"{label}.raw_q.primary")
    if len(primary_q) != 2:
        raise SecondaryError(f"{label}.raw_q.primary must contain two ratings")
    q_values = [_rating_q(row, f"{label}.raw_q.primary[{n}]") for n, row in enumerate(primary_q)]
    if q_values[0][0] == q_values[1][0]:
        raise SecondaryError(f"{label} has duplicate primary evaluator_id")
    raw_incidents = _exact(
        detail["raw_critical_incidents"], f"{label}.raw_critical_incidents",
        frozenset({"primary", "adjudicator"}),
    )
    primary_inc = _rows(raw_incidents["primary"], f"{label}.raw_critical_incidents.primary")
    if len(primary_inc) != 2:
        raise SecondaryError(f"{label}.raw_critical_incidents.primary must contain two ratings")
    incident_values = [
        _rating_incidents(row, f"{label}.raw_critical_incidents.primary[{n}]")
        for n, row in enumerate(primary_inc)
    ]
    if [row[0] for row in q_values] != [row[0] for row in incident_values]:
        raise SecondaryError(f"{label} primary Q and incident evaluator_id values differ")
    left, right = incident_values[0][1], incident_values[1][1]
    triggers = []
    if abs(q_values[0][1] - q_values[1][1]) > 10:
        triggers.append("q_total_difference_gt_10")
    if left != right:
        triggers.append("critical_failure_disagreement")
    adjudication = detail["adjudication"]
    if triggers:
        adj = _exact(adjudication, f"{label}.adjudication", frozenset({
            "basis", "triggers", "q_resolution", "critical_failure_resolutions",
        }))
        if adj["basis"] != "third_locked_rating" or adj["triggers"] != triggers:
            raise SecondaryError(f"{label}.adjudication triggers or basis mismatch")
        third_evaluator, selected_q = _rating_q(raw_q["adjudicator"], f"{label}.raw_q.adjudicator")
        incident_evaluator, third_incidents = _rating_incidents(
            raw_incidents["adjudicator"], f"{label}.raw_critical_incidents.adjudicator"
        )
        if third_evaluator != incident_evaluator or third_evaluator in (q_values[0][0], q_values[1][0]):
            raise SecondaryError(f"{label} has inconsistent adjudicator evaluator_id")
        resolution = _exact(adj["q_resolution"], f"{label}.adjudication.q_resolution",
                            frozenset({"basis", "rationale"}))
        if resolution["basis"] != "third_locked_rating":
            raise SecondaryError(f"{label}.adjudication.q_resolution.basis mismatch")
        _nonempty_text(resolution["rationale"], f"{label}.adjudication.q_resolution.rationale")
        required_resolutions = {
            incident_id for incident_id in left.keys() | right.keys() | third_incidents.keys()
            if left.get(incident_id) != right.get(incident_id)
            or (incident_id in third_incidents and third_incidents[incident_id] != left.get(incident_id))
        }
        decisions: dict[str, str | None] = {}
        for n, value in enumerate(_rows(adj["critical_failure_resolutions"],
                                        f"{label}.adjudication.critical_failure_resolutions")):
            decision_label = f"{label}.adjudication.critical_failure_resolutions[{n}]"
            decision = _exact(value, decision_label,
                              frozenset({"incident_id", "resolved_code", "rationale"}))
            incident_id = decision["incident_id"]
            if type(incident_id) is not str or INCIDENT_ID.fullmatch(incident_id) is None or incident_id in decisions:
                raise SecondaryError(f"{decision_label}.incident_id is invalid or duplicate")
            code = decision["resolved_code"]
            if code is not None and (type(code) is not str or FAILURE_CODE.fullmatch(code) is None):
                raise SecondaryError(f"{decision_label}.resolved_code is invalid")
            _nonempty_text(decision["rationale"], f"{decision_label}.rationale")
            decisions[incident_id] = code
        if set(decisions) != required_resolutions or any(
            decisions[incident_id] != third_incidents.get(incident_id)
            for incident_id in required_resolutions
        ):
            raise SecondaryError(f"{label}.adjudication incident resolutions mismatch")
        final_incidents = {
            incident_id: code for incident_id, code in left.items()
            if right.get(incident_id) == code
        }
        final_incidents.update({incident_id: code for incident_id, code in decisions.items() if code is not None})
    else:
        _exact(adjudication, f"{label}.adjudication", frozenset({"basis", "triggers"}))
        if adjudication != {"basis": "primary_arithmetic_mean", "triggers": []}:
            raise SecondaryError(f"{label}.adjudication must use the primary mean")
        if raw_q["adjudicator"] is not None or raw_incidents["adjudicator"] is not None:
            raise SecondaryError(f"{label} has an adjudicator without a trigger")
        selected_q = (q_values[0][1] + q_values[1][1]) / 2
        final_incidents = left
    if evaluations[run_id]["q"] != selected_q:
        raise SecondaryError(f"{label} selected Q differs from evaluation")
    sensitivity = _exact(detail["sensitivity"], f"{label}.sensitivity", frozenset({
        "primary_mean_q", "selected_q", "selected_minus_primary_mean_q",
    }))
    primary_mean = (q_values[0][1] + q_values[1][1]) / 2
    if (type(sensitivity["primary_mean_q"]) not in (int, float)
            or type(sensitivity["selected_q"]) not in (int, float)
            or type(sensitivity["selected_minus_primary_mean_q"]) not in (int, float)
            or sensitivity["primary_mean_q"] != primary_mean
            or sensitivity["selected_q"] != selected_q
            or sensitivity["selected_minus_primary_mean_q"] != selected_q - primary_mean):
        raise SecondaryError(f"{label}.sensitivity differs from ratings")
    if _incident_map(detail["critical_incidents"], f"{label}.critical_incidents") != final_incidents:
        raise SecondaryError(f"{label}.critical_incidents differs from declared decisions")
    computed_e = int(bool(final_incidents))
    if type(detail["E"]) is not int or detail["E"] != computed_e:
        raise SecondaryError(f"{label}.E differs from critical_incidents")
    return run_id, computed_e, bool(triggers), dict(final_incidents)


def _validate_assembly(
    raw: Any, schedule: dict[str, Any], raw_receipts: Any,
    receipt_audit: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, int], dict[str, dict[str, str]]]:
    assembly = _exact(raw, "assembly", ASSEMBLY_FIELDS)
    if type(assembly["schema"]) is not int or assembly["schema"] != 1:
        raise SecondaryError("assembly.schema must be integer 1")
    if assembly["classification"] != "development_rated_q_assembly_unsealed":
        raise SecondaryError("assembly classification must be development_rated_q_assembly_unsealed")
    _nonempty_text(assembly["notice"], "assembly.notice")
    mapping_schema = assembly["mapping_schema"]
    if type(mapping_schema) is not int or mapping_schema not in (1, 2):
        raise SecondaryError("assembly.mapping_schema must be integer 1 or 2")
    for key, expected in (
        ("schedule_sha256", schedule["schedule_sha256"]),
        ("receipts_sha256", receipt_audit["receipts_sha256"]),
    ):
        if _sha256(assembly[key], f"assembly.{key}") != expected:
            raise SecondaryError(f"assembly.{key} digest mismatch")
    for key in ("manifest_sha256", "ratings_sha256", "mapping_sha256"):
        _sha256(assembly[key], f"assembly.{key}")
    declared_duplicate_pairs = _rows(
        assembly["duplicate_terminal_pairs_requiring_external_preparation_verification"],
        "assembly.duplicate_terminal_pairs_requiring_external_preparation_verification",
    )
    criterion = _exact(assembly["criterion_4"], "assembly.criterion_4",
                       frozenset({"status", "reason"}))
    if criterion["status"] != "not_assessed":
        raise SecondaryError("assembly.criterion_4 must be not_assessed")
    _nonempty_text(criterion["reason"], "assembly.criterion_4.reason")
    scheduled_ids = {run["run_id"] for run in schedule["runs"]}
    evaluations = _validate_evaluations(
        assembly["evaluations"], schedule["schedule_sha256"], scheduled_ids
    )
    receipt_by_run = {row["run_id"]: row for row in receipt_audit["runs"]}
    reconciliation = reconcile(schedule, raw_receipts, assembly["evaluations"])
    unacceptable = [
        issue for issue in reconciliation["issues"]
        if issue["code"] != "completed_run_not_scored"
    ]
    if unacceptable:
        raise SecondaryError(
            f"assembly evaluation/receipt reconciliation mismatch: {unacceptable[0]['code']}"
        )
    if reconciliation["receipt_violations"]:
        raise SecondaryError("assembly receipts have audit violations")
    details = _rows(assembly["details"], "assembly.details")
    e_by_run: dict[str, int] = {}
    incidents_by_run: dict[str, dict[str, str]] = {}
    opaque_ids: set[str] = set()
    preparation_records: set[str] = set()
    adjudicated = 0
    for index, detail in enumerate(details):
        run_id, e, has_trigger, incidents = _validate_detail(
            detail, index, evaluations, receipt_by_run, mapping_schema
        )
        if run_id in e_by_run:
            raise SecondaryError(f"duplicate assembly detail run_id: {run_id}")
        if detail["opaque_id"] in opaque_ids:
            raise SecondaryError(f"duplicate assembly detail opaque_id: {detail['opaque_id']}")
        if mapping_schema == 2:
            preparation_record = detail["preparation_record_sha256"]
            if preparation_record in preparation_records:
                raise SecondaryError(
                    f"duplicate preparation_record_sha256 in assembly details: {preparation_record}"
                )
            preparation_records.add(preparation_record)
        opaque_ids.add(detail["opaque_id"])
        e_by_run[run_id] = e
        incidents_by_run[run_id] = incidents
        adjudicated += has_trigger
    terminal_pairs: dict[tuple[str, str], list[str]] = {}
    for run_id, receipt in receipt_by_run.items():
        if receipt["outcome"] not in ("completed", "truncated") or not receipt["attempts"]:
            continue
        terminal = receipt["attempts"][-1]
        if terminal["artifact_sha256"] is None:
            continue
        pair = (terminal["artifact_sha256"], terminal["trace_sha256"])
        terminal_pairs.setdefault(pair, []).append(run_id)
    if mapping_schema == 1 and any(
        len(run_ids) > 1 and set(run_ids) & e_by_run.keys()
        for run_ids in terminal_pairs.values()
    ):
        raise SecondaryError("schema-1 assembly has an ambiguous terminal artifact/trace pair")
    expected_duplicate_pairs = [
        {
            "terminal_artifact_sha256": pair[0],
            "terminal_trace_sha256": pair[1],
            "terminal_run_ids": sorted(run_ids),
            "mapped_run_ids": sorted(set(run_ids) & e_by_run.keys()),
        }
        for pair, run_ids in sorted(terminal_pairs.items())
        if mapping_schema == 2 and len(run_ids) > 1 and set(run_ids) & e_by_run.keys()
    ]
    if declared_duplicate_pairs != expected_duplicate_pairs:
        raise SecondaryError("assembly duplicate terminal pair warnings differ from receipts and details")
    scored_ids = {run_id for run_id, row in evaluations.items() if "q" in row}
    if set(e_by_run) != scored_ids:
        raise SecondaryError("assembly details must cover every Q-scored run exactly once")
    counts = _exact(assembly["counts"], "assembly.counts", frozenset({
        "scheduled_runs", "mapped_runs", "scored_runs", "truncated_runs",
        "truncated_scored_runs", "missing_runs", "adjudicated_runs",
        "critical_incident_runs",
    }))
    expected_counts = {
        "scheduled_runs": len(schedule["runs"]),
        "mapped_runs": len(details),
        "scored_runs": sum(row["status"] == "scored" for row in evaluations.values()),
        "truncated_runs": sum(row["status"] == "truncated" for row in evaluations.values()),
        "truncated_scored_runs": sum(
            row["status"] == "truncated" and "q" in row for row in evaluations.values()
        ),
        "missing_runs": sum(row["status"] == "missing" for row in evaluations.values()),
        "adjudicated_runs": adjudicated,
        "critical_incident_runs": sum(e_by_run.values()),
    }
    if counts != expected_counts or any(type(value) is not int for value in counts.values()):
        raise SecondaryError("assembly.counts differ from evaluations and details")
    return assembly, e_by_run, incidents_by_run


def _validate_secondary(
    raw: Any, schedule: dict[str, Any], receipt_audit: dict[str, Any],
    assembly_digest: str,
) -> dict[str, dict[str, Any]]:
    secondary = _exact(raw, "secondary", TOP_FIELDS)
    if type(secondary["schema"]) is not int or secondary["schema"] != 1:
        raise SecondaryError("secondary.schema must be integer 1")
    for key, expected in (
        ("schedule_sha256", schedule["schedule_sha256"]),
        ("receipts_sha256", receipt_audit["receipts_sha256"]),
        ("assembly_sha256", assembly_digest),
    ):
        if _sha256(secondary[key], f"secondary.{key}") != expected:
            raise SecondaryError(f"secondary.{key} digest mismatch")
    _sha256(secondary["rate_card_sha256"], "secondary.rate_card_sha256")
    runs = {run["run_id"]: run for run in schedule["runs"]}
    receipts = {row["run_id"]: row for row in receipt_audit["runs"]}
    by_run: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(_rows(secondary["runs"], "secondary.runs")):
        label = f"secondary.runs[{index}]"
        if type(value) is not dict:
            raise SecondaryError(f"{label} must be an object")
        run_id = _nonempty_text(value.get("run_id"), f"{label}.run_id")
        if run_id not in runs:
            raise SecondaryError(f"{label} references an unscheduled run_id")
        if run_id in by_run:
            raise SecondaryError(f"duplicate secondary run_id: {run_id}")
        if value.get("status") == "missing":
            _exact(value, label, frozenset({"run_id", "status", "reason"}))
            _nonempty_text(value["reason"], f"{label}.reason")
            by_run[run_id] = value
            continue
        if value.get("status") != "measured":
            raise SecondaryError(f"{label}.status must be missing or measured")
        row = _exact(value, label, MEASURED_FIELDS)
        run, receipt = runs[run_id], receipts[run_id]
        if receipt["outcome"] not in ("completed", "truncated"):
            raise SecondaryError(f"{label} measured run lacks completed/truncated terminal receipt")
        if _sha256(row["reference_sha256"], f"{label}.reference_sha256") != run["case_reference_sha256"]:
            raise SecondaryError(f"{label}.reference_sha256 differs from scheduled case reference")
        _sha256(row["audit_sha256"], f"{label}.audit_sha256")
        compliance = _exact(row["compliance"], f"{label}.compliance", COMPLIANCE_FIELDS)
        c_met = _integer(compliance["met"], f"{label}.compliance.met")
        c_required = _integer(compliance["required"], f"{label}.compliance.required", 1)
        c_critical = _integer(compliance["critical_omissions"], f"{label}.compliance.critical_omissions")
        if c_met > c_required or c_critical > c_required - c_met:
            raise SecondaryError(f"{label}.compliance counts are inconsistent")
        trace = _exact(row["traceability"], f"{label}.traceability", TRACE_FIELDS)
        counts = {
            key: _integer(value, f"{label}.traceability.{key}",
                          1 if key.startswith("required_") else 0)
            for key, value in trace.items()
        }
        if counts["tp"] + counts["fn"] == 0:
            raise SecondaryError(f"{label}.traceability requires a nonempty reference link set")
        for category in ("requirements", "indicators"):
            if counts[f"complete_{category}"] > counts[f"required_{category}"]:
                raise SecondaryError(f"{label}.traceability {category} counts are inconsistent")
        raw_recovery = row["recovery"]
        if type(raw_recovery) is dict and raw_recovery.get("status") == "missing":
            recovery = _exact(raw_recovery, f"{label}.recovery", RECOVERY_MISSING_FIELDS)
            _nonempty_text(recovery["reason"], f"{label}.recovery.reason")
            resume_seconds = None
        else:
            recovery = _exact(raw_recovery, f"{label}.recovery", RECOVERY_FIELDS)
            _sha256(recovery["injection_sha256"], f"{label}.recovery.injection_sha256")
            if type(recovery["recovered"]) is not bool:
                raise SecondaryError(f"{label}.recovery.recovered must be a boolean")
            resume_seconds = recovery["resume_seconds"]
            if resume_seconds is None:
                if recovery["recovered"]:
                    raise SecondaryError(
                        f"{label}.recovery.resume_seconds must be numeric when recovered"
                    )
            else:
                _seconds(resume_seconds, f"{label}.recovery.resume_seconds")
            _integer(recovery["repeated_decisions"], f"{label}.recovery.repeated_decisions")
        human = _exact(row["human"], f"{label}.human", HUMAN_FIELDS)
        _seconds(human["active_seconds"], f"{label}.human.active_seconds")
        _seconds(human["wait_seconds"], f"{label}.human.wait_seconds")
        _sha256(human["events_sha256"], f"{label}.human.events_sha256")
        human_counts = _exact(human["event_counts"], f"{label}.human.event_counts",
                              HUMAN_EVENT_TYPES)
        for key, count in human_counts.items():
            _integer(count, f"{label}.human.event_counts.{key}")
        active_by_type = _exact(
            human["active_seconds_by_type"], f"{label}.human.active_seconds_by_type",
            HUMAN_EVENT_TYPES,
        )
        for key, seconds in active_by_type.items():
            _seconds(seconds, f"{label}.human.active_seconds_by_type.{key}")
        with localcontext() as context:
            context.prec = max(len(str(value)) for value in active_by_type.values()) + 20
            active_parts = sum((Decimal(str(value)) for value in active_by_type.values()),
                               Decimal(0))
        if abs(active_parts - Decimal(str(human["active_seconds"]))) > Decimal("0.000001"):
            raise SecondaryError(
                f"{label}.human.active_seconds differs from active_seconds_by_type sum"
            )
        wall = _exact(row["wall"], f"{label}.wall", WALL_FIELDS)
        released = _utc_time(wall["released_at_utc"], f"{label}.wall.released_at_utc")
        delivered = _utc_time(wall["delivered_at_utc"], f"{label}.wall.delivered_at_utc")
        _sha256(wall["event_sha256"], f"{label}.wall.event_sha256")
        if delivered < released:
            raise SecondaryError(f"{label}.wall delivered before release")
        attempts = receipt["attempts"]
        first = _utc_time(attempts[0]["started_at_utc"], f"{label} first receipt start")
        last = _utc_time(attempts[-1]["ended_at_utc"], f"{label} terminal receipt end")
        elapsed = math.fsum(
            (_utc_time(item["ended_at_utc"], f"{label} receipt end")
             - _utc_time(item["started_at_utc"], f"{label} receipt start")).total_seconds()
            for item in attempts
        )
        wall_seconds = (delivered - released).total_seconds()
        if released > first or delivered < last or wall_seconds + 1e-9 < elapsed:
            raise SecondaryError(f"{label}.wall must include all receipt attempts and elapsed time")
        span = delivered - released
        wall_exact = (Decimal(span.days) * 86400 + Decimal(span.seconds)
                      + Decimal(span.microseconds) / 1_000_000)
        if resume_seconds is not None and Decimal(str(resume_seconds)) > wall_exact:
            raise SecondaryError(f"{label}.recovery.resume_seconds exceeds wall duration")
        # Receipt waits cover attempts only; H may include additional waiting
        # before the first attempt, between attempts, or after the terminal one.
        with localcontext() as context:
            context.prec = max(len(str(item["human_wait_seconds"])) for item in attempts) + 20
            receipt_wait = sum(
                (Decimal(str(item["human_wait_seconds"])) for item in attempts),
                Decimal(0),
            )
        if Decimal(str(human["wait_seconds"])) + Decimal("0.000001") < receipt_wait:
            raise SecondaryError(f"{label}.human.wait_seconds is below receipt human_wait_seconds")
        cost = _exact(row["cost"], f"{label}.cost", COST_FIELDS)
        money_fields = ("model_usd", "tools_usd", "human_usd", "total_usd")
        amounts = {key: _money(cost[key], f"{label}.cost.{key}") for key in money_fields}
        # A large integer plus a tiny fractional component needs precision
        # spanning both magnitudes, even when the declared total omits the latter.
        with localcontext() as context:
            context.prec = _decimal_places(amounts.values()) + 4
            components = sum((amounts[key] for key in money_fields[:3]), Decimal(0))
        if components != amounts["total_usd"]:
            raise SecondaryError(f"{label}.cost.total_usd differs from exact component sum")
        _sha256(cost["invoice_sha256"], f"{label}.cost.invoice_sha256")
        by_run[run_id] = row
    omitted = runs.keys() - by_run.keys()
    if omitted:
        raise SecondaryError(
            f"secondary.runs omit {len(omitted)} scheduled run_id values; first: {sorted(omitted)[0]}"
        )
    return by_run


def _tokens_for_run(raw_attempts: list[dict[str, Any]]) -> dict[str, int] | None:
    tokens = {
        "input_uncached": 0, "input_cached": 0,
        "output_nonreasoning": 0, "output_reasoning": 0,
        "total": 0, "provider_calls": 0,
    }
    for attempt in raw_attempts:
        for agent in attempt["agent_usage"]:
            for call in agent["provider_calls"]:
                tokens["input_uncached"] += call["input_total"] - call["cached_input"]
                tokens["input_cached"] += call["cached_input"]
                tokens["output_nonreasoning"] += call["output_total"] - call["reasoning_output"]
                tokens["output_reasoning"] += call["reasoning_output"]
                tokens["total"] += call["input_total"] + call["output_total"]
                tokens["provider_calls"] += 1
    return tokens if tokens["provider_calls"] else None


def _incident_counts(incidents: dict[str, str]) -> dict[str, Any]:
    by_type: dict[str, int] = defaultdict(int)
    for code in incidents.values():
        by_type[code] += 1
    return {"total_unique": len(incidents), "by_type": dict(sorted(by_type.items()))}


def _balanced(
    schedule: dict[str, Any], values: dict[str, float],
) -> dict[str, Any]:
    missing_count = len(schedule["runs"]) - len(values)
    arms = ("N", "S", "T")
    model_ids = [model["model_id"] for model in schedule["models"]]
    if missing_count:
        return {
            "missing_count": missing_count,
            "by_arm": {arm: None for arm in arms},
            "by_model": {arm: {model: None for model in model_ids} for arm in arms},
            "T_minus_S_pp": None,
        }
    cells: dict[tuple[str, str, str, str, str], list[float]] = defaultdict(list)
    for run in schedule["runs"]:
        cells[(run["arm"], run["model_id"], run["effort"],
               run["agents"], run["case_id"])].append(values[run["run_id"]])
    model_means: dict[str, dict[str, float]] = {arm: {} for arm in arms}
    for arm in arms:
        for model in schedule["models"]:
            model_id = model["model_id"]
            effort_means = []
            for effort in model["efforts"]:
                effort_label = effort["label"]
                case_agent_means = [
                    math.fsum(cells[(arm, model_id, effort_label, agents, case_id)]) / 3
                    for agents in ("solo", "trio")
                    for case_id in ("R-F", "R-M", "R-S")
                ]
                effort_means.append(math.fsum(case_agent_means) / len(case_agent_means))
            model_means[arm][model_id] = math.fsum(effort_means) / len(effort_means)
    by_arm = {
        arm: math.fsum(model_means[arm].values()) / len(model_ids)
        for arm in arms
    }
    return {
        "missing_count": 0, "by_arm": by_arm, "by_model": model_means,
        "T_minus_S_pp": (by_arm["T"] - by_arm["S"]) * 100,
    }


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _model_medians(
    schedule: dict[str, Any], values: dict[str, float | Decimal], *, money: bool,
) -> dict[str, Any]:
    missing_count = len(schedule["runs"]) - len(values)
    arms = ("N", "S", "T")
    model_ids = [model["model_id"] for model in schedule["models"]]
    if missing_count:
        return {
            "missing_count": missing_count,
            "by_model_arm": {arm: {model: None for model in model_ids} for arm in arms},
            "by_arm": {arm: None for arm in arms}, "T_over_S": None,
        }
    groups: dict[tuple[str, str], list[float | Decimal]] = defaultdict(list)
    for run in schedule["runs"]:
        groups[(run["arm"], run["model_id"])].append(values[run["run_id"]])
    with localcontext() as context:
        if money:
            context.prec = _decimal_places(values.values()) + 30
        model_medians = {
            arm: {model: median(groups[(arm, model)]) for model in model_ids}
            for arm in arms
        }
        arm_medians = {arm: median(model_medians[arm].values()) for arm in arms}
        ratio = None if arm_medians["S"] == 0 else arm_medians["T"] / arm_medians["S"]
    if money:
        return {
            "missing_count": 0,
            "by_model_arm": {
                arm: {model: _decimal_text(value) for model, value in rows.items()}
                for arm, rows in model_medians.items()
            },
            "by_arm": {arm: _decimal_text(value) for arm, value in arm_medians.items()},
            "T_over_S": None if ratio is None else _decimal_text(ratio),
        }
    return {
        "missing_count": 0, "by_model_arm": model_medians,
        "by_arm": arm_medians, "T_over_S": ratio,
    }


def _decimal_places(values: Iterable[Decimal]) -> int:
    """Count both integer magnitude and fractional scale, including leading zeros."""
    integer_places = 0
    fractional_places = 0
    for value in values:
        if value:
            integer_places = max(integer_places, value.adjusted() + 1)
        fractional_places = max(fractional_places, -value.as_tuple().exponent)
    return max(integer_places, 0) + fractional_places


def _decimal_percentile(sorted_values: list[Decimal], proportion: Decimal) -> Decimal:
    position = Decimal(len(sorted_values) - 1) * proportion
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    with localcontext() as context:
        context.prec = _decimal_places(sorted_values) + 30
        return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def _secondary_uncertainty(
    schedule: dict[str, Any], triplets: dict[tuple[Any, ...], dict[str, dict[str, Any]]],
    effort_counts: dict[str, int], values: dict[str, dict[str, float | Decimal]],
    aggregates: dict[str, dict[str, Any]], resamples: int,
) -> dict[str, Any]:
    """Use one replica draw per sorted stratum for every complete metric."""
    complete = {metric for metric, rows in values.items() if len(rows) == len(schedule["runs"])}
    strata: dict[tuple[str, str, str, str], list[dict[str, dict[str, Any]]]] = defaultdict(list)
    for key, arms in sorted(triplets.items()):
        strata[key[:4]].append(arms)
    ordered = sorted(strata.items())
    if any(len(replicas) != len(REPLICAS) for _, replicas in ordered):
        raise SecondaryError("secondary bootstrap requires three replicas per stratum")
    model_ids = sorted(effort_counts)
    weights = [
        1 / (len(model_ids) * effort_counts[key[0]] * len(AGENTS) * len(CASES))
        for key, _ in ordered
    ]
    panels = {
        metric: [
            tuple(tuple(rows[arms[arm]["run_id"]] for arms in replicas) for arm in ARMS)
            for _, replicas in ordered
        ]
        for metric, rows in values.items() if metric in complete
    }
    draws: dict[str, dict[str, list[Any]]] = {
        metric: {"T": [], "T_minus_S_pp": []} for metric in ("E", "T", "R")
        if metric in complete
    }
    for metric in ("W", "P"):
        if metric in complete:
            draws[metric] = {**{arm: [] for arm in ARMS}, "T_over_S": []}
    zero_s_draws = {metric: 0 for metric in ("W", "P") if metric in complete}
    money_places = _decimal_places(values["P"].values()) if "P" in complete else 1
    rng = random.Random(schedule["seed"])

    for _ in range(resamples if complete else 0):
        sampled = [tuple(rng.randrange(3) for _ in REPLICAS) for _ in ordered]
        for metric in ("E", "T", "R"):
            if metric not in complete:
                continue
            panels_for_metric = panels[metric]
            s_mean = math.fsum(
                weight * math.fsum(panel[1][index] for index in indices) / 3
                for weight, panel, indices in zip(weights, panels_for_metric, sampled, strict=True)
            )
            t_mean = math.fsum(
                weight * math.fsum(panel[2][index] for index in indices) / 3
                for weight, panel, indices in zip(weights, panels_for_metric, sampled, strict=True)
            )
            if metric != "E":
                draws[metric]["T"].append(t_mean)
            draws[metric]["T_minus_S_pp"].append((t_mean - s_mean) * 100)

        for metric in ("W", "P"):
            if metric not in complete:
                continue
            grouped: dict[str, dict[str, list[float | Decimal]]] = {
                model: {arm: [] for arm in ARMS} for model in model_ids
            }
            for (key, _), panel, indices in zip(ordered, panels[metric], sampled, strict=True):
                for arm_number, arm in enumerate(ARMS):
                    grouped[key[0]][arm].extend(panel[arm_number][index] for index in indices)
            with localcontext() as context:
                if metric == "P":
                    # Four-model medians and ratios need headroom beyond input precision.
                    context.prec = 2 * money_places + 40
                arm_medians = {
                    arm: median(median(grouped[model][arm]) for model in model_ids)
                    for arm in ARMS
                }
                for arm in ARMS:
                    draws[metric][arm].append(arm_medians[arm])
                if arm_medians["S"] == 0:
                    zero_s_draws[metric] += 1
                else:
                    draws[metric]["T_over_S"].append(arm_medians["T"] / arm_medians["S"])

    intervals: dict[str, Any] = {}
    for metric in ("E", "T", "R"):
        labels = ("T_minus_S_pp",) if metric == "E" else ("T", "T_minus_S_pp")
        if metric in complete:
            for label in labels:
                draws[metric][label].sort()
        intervals[metric] = {
            "ci95_percentile": {
                label: ([_percentile(draws[metric][label], 0.025),
                         _percentile(draws[metric][label], 0.975)]
                        if metric in complete else None)
                for label in labels
            }
        }
    for metric in ("W", "P"):
        if metric in complete:
            for arm in ARMS:
                draws[metric][arm].sort()
            if zero_s_draws[metric] == 0:
                draws[metric]["T_over_S"].sort()
        def interval(label: str) -> list[float] | list[str] | None:
            if metric not in complete or (label == "T_over_S" and (
                aggregates[metric]["by_arm"]["S"] == ("0" if metric == "P" else 0)
                or zero_s_draws[metric]
            )):
                return None
            ordered_values = draws[metric][label]
            if metric == "P":
                return [
                    _decimal_text(_decimal_percentile(ordered_values, proportion))
                    for proportion in (Decimal("0.025"), Decimal("0.975"))
                ]
            return [_percentile(ordered_values, 0.025), _percentile(ordered_values, 0.975)]
        intervals[metric] = {
            "ci95_percentile": {
                "by_arm": {arm: interval(arm) for arm in ARMS},
                "T_over_S": interval("T_over_S"),
            },
            "zero_S_bootstrap_draws": zero_s_draws.get(metric),
        }
    return {
        "bootstrap": {
            "seed": schedule["seed"], "resamples": resamples if complete else 0,
            "default_resamples": DEFAULT_RESAMPLES,
        },
        "intervals": intervals,
    }


def analyze_secondary_metrics(
    raw_schedule: Any, raw_receipts: Any, raw_assembly: Any, raw_secondary: Any,
    *, development_resamples: int | None = None,
) -> dict[str, Any]:
    """Validate declared bindings and calculate secondary metrics without a seal."""
    schedule, triplets, effort_counts = _validate_schedule(raw_schedule)
    if development_resamples is None:
        resamples = DEFAULT_RESAMPLES
    elif type(development_resamples) is int and 1 <= development_resamples <= DEFAULT_RESAMPLES:
        resamples = development_resamples
    else:
        raise SecondaryError("development_resamples must be an integer from 1 through 10000")
    receipt_audit = audit_receipts(schedule, raw_receipts)
    if receipt_audit["violations"]:
        raise SecondaryError(
            f"receipt audit reports {len(receipt_audit['violations'])} violation(s); "
            f"first code: {receipt_audit['violations'][0]['code']}"
        )
    assembly, e_by_run, incidents_by_run = _validate_assembly(
        raw_assembly, schedule, raw_receipts, receipt_audit
    )
    assembly_digest = _canonical_digest(assembly)
    secondary_by_run = _validate_secondary(raw_secondary, schedule, receipt_audit, assembly_digest)
    raw_attempts_by_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in raw_receipts["attempts"]:
        raw_attempts_by_run[attempt["run_id"]].append(attempt)
    receipt_by_run = {row["run_id"]: row for row in receipt_audit["runs"]}
    e_values: dict[str, float] = {}
    t_values: dict[str, float] = {}
    r_values: dict[str, float] = {}
    w_values: dict[str, float] = {}
    p_values: dict[str, Decimal] = {}
    output_runs = []
    for run in schedule["runs"]:
        run_id = run["run_id"]
        source = secondary_by_run[run_id]
        e = e_by_run.get(run_id)
        if e is not None:
            e_values[run_id] = float(e)
        k = _tokens_for_run(raw_attempts_by_run[run_id])
        row: dict[str, Any] = {
            "run_id": run_id, "model_id": run["model_id"], "effort": run["effort"],
            "agents": run["agents"], "case_id": run["case_id"],
            "replica": run["replica"], "arm": run["arm"],
            "receipt_outcome": receipt_by_run[run_id]["outcome"],
            "status": source["status"], "E": e,
            "E_incidents": (_incident_counts(incidents_by_run[run_id])
                            if run_id in incidents_by_run else None),
            "K": k,
            "C": None, "T": None, "R": None, "H": None,
            "W": None, "P": None,
        }
        if source["status"] == "missing":
            row["reason"] = source["reason"]
        else:
            compliance, trace, recovery = (
                source["compliance"], source["traceability"], source["recovery"]
            )
            c = compliance["met"] / compliance["required"]
            f1 = 2 * trace["tp"] / (2 * trace["tp"] + trace["fp"] + trace["fn"])
            wall = source["wall"]
            wall_seconds = (_utc_time(wall["delivered_at_utc"], "wall delivery")
                            - _utc_time(wall["released_at_utc"], "wall release")).total_seconds()
            cost = Decimal(source["cost"]["total_usd"])
            row.update({
                "C": {"fraction": c, "met": compliance["met"],
                      "required": compliance["required"],
                      "critical_omissions": compliance["critical_omissions"]},
                "T": {"f1": f1, **trace},
                "H": {"active_seconds": source["human"]["active_seconds"],
                      "active_seconds_by_type": source["human"]["active_seconds_by_type"],
                      "wait_seconds": source["human"]["wait_seconds"],
                      "event_counts": source["human"]["event_counts"]},
                "W": {"seconds": wall_seconds},
                "P": {"total_usd": _decimal_text(cost)},
            })
            if recovery.get("status") == "missing":
                row["R_missing_reason"] = recovery["reason"]
            else:
                recovered = int(recovery["recovered"])
                row["R"] = {
                    "recovered": recovered,
                    "resume_seconds": recovery["resume_seconds"],
                    "repeated_decisions": recovery["repeated_decisions"],
                }
                r_values[run_id] = float(recovered)
            t_values[run_id] = f1
            w_values[run_id] = wall_seconds
            p_values[run_id] = cost
        output_runs.append(row)
    descriptive: dict[str, Any] = {"descriptive_only": True}
    for metric in ("C", "H", "K"):
        available = [row for row in output_runs if row[metric] is not None]
        descriptive[metric] = {
            "available_runs": len(available),
            "missing_count": len(output_runs) - len(available),
        }
    descriptive["C"]["by_arm_available_mean_fraction"] = {
        arm: (math.fsum(row["C"]["fraction"] for row in output_runs
                        if row["arm"] == arm and row["C"] is not None)
              / count if (count := sum(row["arm"] == arm and row["C"] is not None
                                    for row in output_runs)) else None)
        for arm in ("N", "S", "T")
    }
    descriptive["H"]["total_active_seconds"] = math.fsum(
        row["H"]["active_seconds"] for row in output_runs if row["H"] is not None
    )
    descriptive["H"]["total_active_seconds_by_type"] = {
        key: math.fsum(row["H"]["active_seconds_by_type"][key] for row in output_runs
                       if row["H"] is not None)
        for key in sorted(HUMAN_EVENT_TYPES)
    }
    descriptive["H"]["total_wait_seconds"] = math.fsum(
        row["H"]["wait_seconds"] for row in output_runs if row["H"] is not None
    )
    descriptive["H"]["total_event_counts"] = {
        key: sum(row["H"]["event_counts"][key] for row in output_runs
                 if row["H"] is not None)
        for key in sorted(HUMAN_EVENT_TYPES)
    }
    descriptive["H"]["by_arm_available_totals"] = {
        arm: {
            "runs": sum(row["arm"] == arm and row["H"] is not None for row in output_runs),
            "active_seconds": math.fsum(
                row["H"]["active_seconds"] for row in output_runs
                if row["arm"] == arm and row["H"] is not None
            ),
            "active_seconds_by_type": {
                key: math.fsum(row["H"]["active_seconds_by_type"][key]
                               for row in output_runs
                               if row["arm"] == arm and row["H"] is not None)
                for key in sorted(HUMAN_EVENT_TYPES)
            },
            "wait_seconds": math.fsum(
                row["H"]["wait_seconds"] for row in output_runs
                if row["arm"] == arm and row["H"] is not None
            ),
            "event_counts": {
                key: sum(row["H"]["event_counts"][key] for row in output_runs
                         if row["arm"] == arm and row["H"] is not None)
                for key in sorted(HUMAN_EVENT_TYPES)
            },
        }
        for arm in ("N", "S", "T")
    }
    descriptive["K"]["available_total_tokens"] = sum(
        row["K"]["total"] for row in output_runs if row["K"] is not None
    )
    descriptive["K"]["by_arm_available_totals"] = {
        arm: {
            "runs": sum(row["arm"] == arm and row["K"] is not None for row in output_runs),
            **{
                key: sum(row["K"][key] for row in output_runs
                         if row["arm"] == arm and row["K"] is not None)
                for key in ("input_uncached", "input_cached", "output_nonreasoning",
                            "output_reasoning", "total", "provider_calls")
            },
        }
        for arm in ("N", "S", "T")
    }
    e_aggregate = _balanced(schedule, e_values)
    incident_by_arm = {}
    for arm in ("N", "S", "T"):
        arm_incidents = {
            run["run_id"]: incidents_by_run[run["run_id"]]
            for run in schedule["runs"]
            if run["arm"] == arm and run["run_id"] in incidents_by_run
        }
        by_type: dict[str, int] = defaultdict(int)
        for incidents in arm_incidents.values():
            for code in incidents.values():
                by_type[code] += 1
        incident_by_arm[arm] = {
            "available_runs": len(arm_incidents),
            "total_unique_available": sum(len(incidents) for incidents in arm_incidents.values()),
            "by_type_available": dict(sorted(by_type.items())),
        }
    all_types = sorted({
        code for incidents in incidents_by_run.values() for code in incidents.values()
    })
    e_aggregate["incident_counts"] = {
        "available_runs": len(incidents_by_run),
        "missing_count": len(schedule["runs"]) - len(incidents_by_run),
        "total_unique_available": sum(len(incidents) for incidents in incidents_by_run.values()),
        "by_type_available": {
            code: sum(code == incident_code for incidents in incidents_by_run.values()
                      for incident_code in incidents.values())
            for code in all_types
        },
        "by_arm_available": incident_by_arm,
    }
    aggregates = {
        "E": e_aggregate,
        "T": _balanced(schedule, t_values),
        "R": _balanced(schedule, r_values),
        "W": _model_medians(schedule, w_values, money=False),
        "P": _model_medians(schedule, p_values, money=True),
        **descriptive,
    }
    uncertainty = _secondary_uncertainty(
        schedule, triplets, effort_counts,
        {"E": e_values, "T": t_values, "R": r_values, "W": w_values, "P": p_values},
        aggregates, resamples,
    )
    for metric, interval in uncertainty["intervals"].items():
        aggregates[metric].update(interval)
    return {
        "schema": 1, "classification": CLASSIFICATION, "notice": NOTICE,
        "schedule_sha256": schedule["schedule_sha256"],
        "receipts_sha256": receipt_audit["receipts_sha256"],
        "assembly_sha256": assembly_digest,
        "secondary_sha256": _canonical_digest(raw_secondary),
        "rate_card_sha256": raw_secondary["rate_card_sha256"],
        "bootstrap": uncertainty["bootstrap"],
        "counts": {
            "scheduled_runs": len(schedule["runs"]),
            "secondary_measured_runs": len(t_values),
            "secondary_missing_runs": len(schedule["runs"]) - len(t_values),
            "assembly_E_available_runs": len(e_values),
        },
        "runs": output_runs,
        "aggregate": aggregates,
        "criterion_4": {"status": "not_assessed", "reason": NOTICE},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("schedule", "receipts", "assembly", "secondary"):
        parser.add_argument(name, help=f"{name} JSON path, or - for stdin")
    args = parser.parse_args(argv)
    paths = [args.schedule, args.receipts, args.assembly, args.secondary]
    try:
        if paths.count("-") > 1:
            raise SecondaryError("only one input may use stdin")
        output = analyze_secondary_metrics(*(_read_json(path) for path in paths))
    except (AnalysisError, ReceiptError, OSError, UnicodeError, json.JSONDecodeError,
            ArithmeticError, OverflowError, TypeError, ValueError, RecursionError) as exc:
        output = {
            "schema": 1, "classification": CLASSIFICATION,
            "error": {"code": "invalid_input", "message": str(exc)},
            "criterion_4": {"status": "not_assessed", "reason": NOTICE},
        }
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                     allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
