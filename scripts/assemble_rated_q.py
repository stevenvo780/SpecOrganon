"""Assemble declared blind ratings into per-run Q evaluations, without a result claim.

Usage: ``python scripts/assemble_rated_q.py schedule.json receipts.json
manifest.json ratings.json private_mapping.json``. At most one input may be
``-`` for stdin. The command reads JSON and writes one JSON response to stdout.

The private mapping has schema 1 (legacy equal-digest mode)::

    {"schema": 1, "schedule_sha256": "<digest>",
     "receipts_sha256": "<digest>", "manifest_sha256": "<digest>",
     "ratings_sha256": "<digest>", "links": [
       {"opaque_id": "<32 hex>", "run_id": "conf-...",
        "run_sha256": "<digest>"}]}

Schema 2 keeps those top-level fields and instead requires each link to add
``terminal_artifact_sha256``, ``terminal_trace_sha256``,
``blind_package_sha256``, ``blind_trace_sha256``, and
``preparation_record_sha256``. The terminal digests bind to the receipt; the
blind digests bind to the manifest. They need not be equal across documents.
The preparation digest is only an externally custodied pointer.
Schema 2 permits repeated terminal digest pairs with distinct declared
preparation pointers and flags them for external verification.

Every manifest opaque ID must have one link to a distinct scheduled run with
a terminal completed or truncated receipt carrying an artifact. Schema 1
requires receipt and blind digests to match. Unmapped terminal runs remain
explicit missing/truncated evaluations; no Q is imputed.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

from analyze_confirmatory import (
    AnalysisError,
    _canonical_digest,
    _nonempty_text,
    _read_json,
    _sha256,
    _validate_evaluations,
    _validate_schedule,
)
from audit_blind_ratings import RatingError, audit_blind_ratings
from audit_run_receipts import ReceiptError, audit_receipts


CLASSIFICATION = "development_rated_q_assembly_unsealed"
NOTICE = (
    "Development-only assembly of declared JSON; no real-world validity or "
    "criterion 4 result claim. Schema 1 equates terminal and blind digest "
    "labels; schema 2 binds them separately through a declared preparation "
    "record SHA-256 pointer. This script does not open or verify that record, "
    "the full blinded result package, its source or test bytes, terminal or "
    "blind artifact or trace bytes, or an external seal. Declared timestamp "
    "order is checked, but actual chronology, evaluator identity, blindness, "
    "independence, score locks, and private mapping provenance are not "
    "authenticated. Schema 2 duplicate terminal pairs require external "
    "preparation-record verification."
)
MAPPING_FIELDS = frozenset({
    "schema", "schedule_sha256", "receipts_sha256", "manifest_sha256",
    "ratings_sha256", "links",
})
LINK_FIELDS_V1 = frozenset({"opaque_id", "run_id", "run_sha256"})
LINK_FIELDS_V2 = LINK_FIELDS_V1 | frozenset({
    "terminal_artifact_sha256", "terminal_trace_sha256",
    "blind_package_sha256", "blind_trace_sha256",
    "preparation_record_sha256",
})


class AssemblyError(AnalysisError):
    """The declared evidence cannot be assembled unambiguously."""


def _exact_object(value: Any, label: str, fields: frozenset[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise AssemblyError(f"{label} must be an object")
    missing, extra = fields - value.keys(), value.keys() - fields
    if missing or extra:
        raise AssemblyError(
            f"{label} has missing keys {sorted(missing)} or unexpected keys {sorted(extra)}"
        )
    return value


def _mapping_sha256(value: Any, label: str) -> str:
    try:
        return _sha256(value, label)
    except AnalysisError as exc:
        raise AssemblyError(str(exc)) from exc


def _validate_mapping(
    raw_mapping: Any,
    *,
    schedule_digest: str,
    receipts_digest: str,
    manifest_digest: str,
    ratings_digest: str,
    scheduled: dict[str, dict[str, Any]],
    receipt_runs: dict[str, dict[str, Any]],
    artifacts: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    mapping = _exact_object(raw_mapping, "mapping", MAPPING_FIELDS)
    schema = mapping["schema"]
    if type(schema) is not int or schema not in (1, 2):
        raise AssemblyError("mapping.schema must be integer 1 or 2")
    expected_digests = {
        "schedule_sha256": schedule_digest,
        "receipts_sha256": receipts_digest,
        "manifest_sha256": manifest_digest,
        "ratings_sha256": ratings_digest,
    }
    for key, expected in expected_digests.items():
        if _mapping_sha256(mapping[key], f"mapping.{key}") != expected:
            raise AssemblyError(f"mapping.{key} digest mismatch")
    links = mapping["links"]
    if type(links) is not list:
        raise AssemblyError("mapping.links must be an array")
    terminal_pairs: dict[tuple[str, str], list[str]] = {}
    for run_id, receipt in receipt_runs.items():
        if receipt["outcome"] not in ("completed", "truncated") or not receipt["attempts"]:
            continue
        terminal = receipt["attempts"][-1]
        if terminal["artifact_sha256"] is None:
            continue
        pair = (terminal["artifact_sha256"], terminal["trace_sha256"])
        terminal_pairs.setdefault(pair, []).append(run_id)
    by_opaque: dict[str, dict[str, Any]] = {}
    seen_runs: set[str] = set()
    seen_preparation_records: dict[str, str] = {}
    for index, raw_link in enumerate(links):
        label = f"mapping.links[{index}]"
        link = _exact_object(
            raw_link, label, LINK_FIELDS_V1 if schema == 1 else LINK_FIELDS_V2
        )
        opaque_id = _nonempty_text(link["opaque_id"], f"{label}.opaque_id")
        if opaque_id not in artifacts:
            raise AssemblyError(f"{label} references an unknown manifest opaque_id: {opaque_id}")
        if opaque_id in by_opaque:
            raise AssemblyError(f"duplicate mapping opaque_id: {opaque_id}")
        run_id = _nonempty_text(link["run_id"], f"{label}.run_id")
        if run_id not in scheduled:
            raise AssemblyError(f"{label} references an unscheduled run_id: {run_id}")
        if run_id in seen_runs:
            raise AssemblyError(f"duplicate mapping run_id: {run_id}")
        if _mapping_sha256(link["run_sha256"], f"{label}.run_sha256") != scheduled[run_id]["run_sha256"]:
            raise AssemblyError(f"{label}.run_sha256 mismatch for {run_id}")
        receipt = receipt_runs[run_id]
        if receipt["outcome"] not in ("completed", "truncated") or not receipt["attempts"]:
            raise AssemblyError(f"{label} run {run_id} lacks a terminal completed/truncated receipt")
        terminal = receipt["attempts"][-1]
        if terminal["artifact_sha256"] is None:
            raise AssemblyError(f"{label} run {run_id} has no terminal artifact")
        binding = artifacts[opaque_id]["bindings"]
        if schema == 1:
            if terminal["artifact_sha256"] != binding["artifact_sha256"]:
                raise AssemblyError(f"{label} terminal artifact_sha256 mismatch for {run_id}")
            if terminal["trace_sha256"] != binding["trace_sha256"]:
                raise AssemblyError(f"{label} terminal trace_sha256 mismatch for {run_id}")
            preparation_record_sha256 = None
        else:
            expected_link_digests = {
                "terminal_artifact_sha256": terminal["artifact_sha256"],
                "terminal_trace_sha256": terminal["trace_sha256"],
                "blind_package_sha256": binding["artifact_sha256"],
                "blind_trace_sha256": binding["trace_sha256"],
            }
            for key, expected in expected_link_digests.items():
                if _mapping_sha256(link[key], f"{label}.{key}") != expected:
                    raise AssemblyError(f"{label}.{key} mismatch for {run_id}")
            preparation_record_sha256 = _mapping_sha256(
                link["preparation_record_sha256"], f"{label}.preparation_record_sha256"
            )
            previous_run = seen_preparation_records.get(preparation_record_sha256)
            if previous_run is not None:
                raise AssemblyError(
                    "duplicate preparation_record_sha256 for mapped runs "
                    f"{previous_run} and {run_id}"
                )
            seen_preparation_records[preparation_record_sha256] = run_id
        pair = (terminal["artifact_sha256"], terminal["trace_sha256"])
        if schema == 1 and len(terminal_pairs[pair]) > 1:
            raise AssemblyError(
                "ambiguous terminal artifact/trace digest pair for mapped run "
                f"{run_id}; matching terminal runs: {sorted(terminal_pairs[pair])}"
            )
        terminal_ended = datetime.fromisoformat(terminal["ended_at_utc"].replace("Z", "+00:00"))
        rating_rows = artifacts[opaque_id]["primary_ratings"][:]
        adjudicator = artifacts[opaque_id]["adjudicator_rating"]
        if adjudicator is not None:
            rating_rows.append(adjudicator)
        for rating in rating_rows:
            locked_at = datetime.fromisoformat(
                rating["outcome_stage"]["recorded_at_utc"].replace("Z", "+00:00")
            )
            if locked_at <= terminal_ended:
                raise AssemblyError(
                    f"{label} {rating['role']} outcome_stage recorded_at_utc must be "
                    f"after terminal receipt ended_at_utc for {run_id}"
                )
        by_opaque[opaque_id] = {
            "run_id": run_id,
            "terminal_artifact_sha256": terminal["artifact_sha256"],
            "terminal_trace_sha256": terminal["trace_sha256"],
            "blind_package_sha256": binding["artifact_sha256"],
            "blind_trace_sha256": binding["trace_sha256"],
            "preparation_record_sha256": preparation_record_sha256,
        }
        seen_runs.add(run_id)
    omitted = artifacts.keys() - by_opaque.keys()
    if omitted:
        raise AssemblyError(
            f"mapping omits {len(omitted)} manifest opaque_id values; first: {sorted(omitted)[0]}"
        )
    warnings = [
        {
            "terminal_artifact_sha256": pair[0],
            "terminal_trace_sha256": pair[1],
            "terminal_run_ids": sorted(run_ids),
            "mapped_run_ids": sorted(seen_runs.intersection(run_ids)),
        }
        for pair, run_ids in sorted(terminal_pairs.items())
        if schema == 2 and len(run_ids) > 1 and seen_runs.intersection(run_ids)
    ]
    return by_opaque, warnings


def _incident_map(rating: dict[str, Any]) -> dict[str, str]:
    return {
        item["incident_id"]: item["code"]
        for item in rating["trace_stage"]["critical_failures"]
    }


def _consolidate(
    report: dict[str, Any], run_id: str, binding: dict[str, Any]
) -> tuple[int | float, dict[str, Any]]:
    primary = report["primary_ratings"]
    left, right = primary
    raw_q = [
        {
            "evaluator_id": row["evaluator_id"],
            "q_components": row["outcome_stage"]["q_components"],
            "q_total": row["outcome_stage"]["q_total"],
        }
        for row in primary
    ]
    primary_mean = (raw_q[0]["q_total"] + raw_q[1]["q_total"]) / 2
    left_incidents, right_incidents = _incident_map(left), _incident_map(right)
    triggers = report["agreement"]["adjudication_triggers"]
    adjudicator = report["adjudicator_rating"]
    if triggers:
        # The blind-rating audit requires a third locked Q and one decision for
        # every disputed/new incident. Primary-agreed incidents survive even
        # when the third evaluator does not repeat them.
        if adjudicator is None:
            raise AssemblyError(f"run {run_id} has an adjudication trigger without a third rating")
        q = adjudicator["outcome_stage"]["q_total"]
        agreed = {
            incident_id: code for incident_id, code in left_incidents.items()
            if right_incidents.get(incident_id) == code
        }
        resolutions = adjudicator["adjudication"]["critical_failure_resolutions"]
        final_incidents = dict(agreed)
        for decision in resolutions:
            if decision["resolved_code"] is not None:
                final_incidents[decision["incident_id"]] = decision["resolved_code"]
        resolution = {
            "basis": "third_locked_rating",
            "triggers": triggers,
            "q_resolution": adjudicator["adjudication"]["q_resolution"],
            "critical_failure_resolutions": resolutions,
        }
        third_q = {
            "evaluator_id": adjudicator["evaluator_id"],
            "q_components": adjudicator["outcome_stage"]["q_components"],
            "q_total": q,
        }
    else:
        q = primary_mean
        final_incidents = left_incidents
        resolution = {"basis": "primary_arithmetic_mean", "triggers": []}
        third_q = None
    detail = {
        "run_id": run_id,
        "opaque_id": report["opaque_id"],
        "terminal_artifact_sha256": binding["terminal_artifact_sha256"],
        "terminal_trace_sha256": binding["terminal_trace_sha256"],
        "blind_package_sha256": binding["blind_package_sha256"],
        "blind_trace_sha256": binding["blind_trace_sha256"],
        "preparation_record_sha256": binding["preparation_record_sha256"],
        "raw_q": {"primary": raw_q, "adjudicator": third_q},
        "raw_critical_incidents": {
            "primary": [
                {"evaluator_id": row["evaluator_id"], "incidents": _incident_map(row)}
                for row in primary
            ],
            "adjudicator": (
                {"evaluator_id": adjudicator["evaluator_id"],
                 "incidents": _incident_map(adjudicator)}
                if adjudicator is not None else None
            ),
        },
        "adjudication": resolution,
        "sensitivity": {
            "primary_mean_q": primary_mean,
            "selected_q": q,
            "selected_minus_primary_mean_q": q - primary_mean,
        },
        "critical_incidents": dict(sorted(final_incidents.items())),
        "E": int(bool(final_incidents)),
    }
    return q, detail


def assemble_rated_q(
    raw_schedule: Any,
    raw_receipts: Any,
    raw_manifest: Any,
    raw_ratings: Any,
    raw_mapping: Any,
) -> dict[str, Any]:
    """Validate and bind declarations, then emit Q-only analyzer evaluations."""
    schedule, _, _ = _validate_schedule(raw_schedule)
    receipt_audit = audit_receipts(schedule, raw_receipts)
    if receipt_audit["violations"]:
        first = receipt_audit["violations"][0]
        raise AssemblyError(
            f"receipt audit reports {len(receipt_audit['violations'])} violation(s); "
            f"first code: {first['code']}"
        )
    rating_audit = audit_blind_ratings(raw_manifest, raw_ratings)
    scheduled = {run["run_id"]: run for run in schedule["runs"]}
    receipt_runs = {row["run_id"]: row for row in receipt_audit["runs"]}
    artifacts = {row["opaque_id"]: row for row in rating_audit["artifacts"]}
    scheduled_rubric = schedule["inputs"]["rubric"]["sha256"]
    for opaque_id, report in artifacts.items():
        if report["bindings"]["rubric_sha256"] != scheduled_rubric:
            raise AssemblyError(
                f"manifest opaque_id {opaque_id} rubric_sha256 differs from scheduled rubric"
            )
    by_opaque, duplicate_terminal_warnings = _validate_mapping(
        raw_mapping,
        schedule_digest=schedule["schedule_sha256"],
        receipts_digest=receipt_audit["receipts_sha256"],
        manifest_digest=rating_audit["manifest_sha256"],
        ratings_digest=rating_audit["ratings_sha256"],
        scheduled=scheduled,
        receipt_runs=receipt_runs,
        artifacts=artifacts,
    )
    reports_by_run = {
        binding["run_id"]: (artifacts[opaque_id], binding)
        for opaque_id, binding in by_opaque.items()
    }
    missing_receipts = {row["run_id"]: row["reason"] for row in receipt_audit["missing_runs"]}
    evaluations: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    for run in schedule["runs"]:
        run_id = run["run_id"]
        receipt = receipt_runs[run_id]
        outcome = receipt["outcome"]
        if run_id in reports_by_run:
            report, binding = reports_by_run[run_id]
            q, detail = _consolidate(report, run_id, binding)
            row = {
                "run_id": run_id,
                "status": "truncated" if outcome == "truncated" else "scored",
                "q": q,
                "artifact_sha256": binding["terminal_artifact_sha256"],
            }
            if outcome == "truncated":
                row["reason"] = "terminal receipt truncated; Q uses the available artifact"
            details.append(detail)
        elif outcome == "completed":
            row = {
                "run_id": run_id, "status": "missing",
                "reason": "terminal completed receipt has no blind rating mapping",
            }
        elif outcome == "truncated":
            terminal = receipt["attempts"][-1]
            reason = (
                "terminal truncated receipt has no artifact"
                if terminal["artifact_sha256"] is None
                else "terminal truncated receipt has no blind rating mapping"
            )
            row = {"run_id": run_id, "status": "truncated", "reason": reason}
        else:
            row = {
                "run_id": run_id, "status": "missing",
                "reason": missing_receipts[run_id],
            }
        evaluations.append(row)
    evaluation_document = {
        "schema": 1,
        "schedule_sha256": schedule["schedule_sha256"],
        "runs": evaluations,
    }
    _validate_evaluations(evaluation_document, schedule["schedule_sha256"], set(scheduled))
    return {
        "schema": 1,
        "classification": CLASSIFICATION,
        "notice": NOTICE,
        "mapping_schema": raw_mapping["schema"],
        "schedule_sha256": schedule["schedule_sha256"],
        "receipts_sha256": receipt_audit["receipts_sha256"],
        "manifest_sha256": rating_audit["manifest_sha256"],
        "ratings_sha256": rating_audit["ratings_sha256"],
        "mapping_sha256": _canonical_digest(raw_mapping),
        "duplicate_terminal_pairs_requiring_external_preparation_verification": (
            duplicate_terminal_warnings
        ),
        "evaluations": evaluation_document,
        "details": details,
        "counts": {
            "scheduled_runs": len(scheduled),
            "mapped_runs": len(details),
            "scored_runs": sum(row["status"] == "scored" for row in evaluations),
            "truncated_runs": sum(row["status"] == "truncated" for row in evaluations),
            "truncated_scored_runs": sum(
                row["status"] == "truncated" and "q" in row for row in evaluations
            ),
            "missing_runs": sum(row["status"] == "missing" for row in evaluations),
            "adjudicated_runs": sum(
                bool(detail["adjudication"]["triggers"]) for detail in details
            ),
            "critical_incident_runs": sum(detail["E"] for detail in details),
        },
        "criterion_4": {"status": "not_assessed", "reason": NOTICE},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("schedule", "receipts", "manifest", "ratings", "mapping"):
        parser.add_argument(name, help=f"{name} JSON path, or - for stdin")
    args = parser.parse_args(argv)
    paths = [args.schedule, args.receipts, args.manifest, args.ratings, args.mapping]
    try:
        if paths.count("-") > 1:
            raise AssemblyError("only one input may use stdin")
        output = assemble_rated_q(*(_read_json(path) for path in paths))
    except (AnalysisError, ReceiptError, RatingError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        output = {
            "schema": 1, "classification": CLASSIFICATION,
            "error": {"code": "invalid_input", "message": str(exc)},
        }
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
