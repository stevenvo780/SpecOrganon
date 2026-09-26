"""Reconcile declared execution attempts with Q rows for one candidate matrix.

Usage: ``python scripts/reconcile_matrix_evidence.py schedule.json receipts.json evaluations.json``.
Each input is read only; at most one may be ``-`` for stdin. Findings are data
in a development report, not proof that a provider ran or an evaluator was
independent. A scored row must name the same declared artifact digest as the
terminal receipt. This compares declarations; it does not hash artifact bytes.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from analyze_confirmatory import (
    AnalysisError,
    _canonical_digest,
    _read_json,
    _validate_evaluations,
    _validate_schedule,
)
from audit_run_receipts import ReceiptError, audit_receipts


CLASSIFICATION = "development_matrix_reconciliation_unsealed"
NOTICE = (
    "Concordance is limited to supplied JSON and declared artifact digests. "
    "It does not authenticate provider calls, artifact bytes, evaluator identity "
    "or blinding, custodied release events, or a prior study seal. A complete "
    "declaration does not establish criterion 4."
)


def reconcile(raw_schedule: Any, raw_receipts: Any, raw_evaluations: Any) -> dict[str, Any]:
    """Report every mismatch between terminal attempts and supplied Q records."""
    schedule, _, _ = _validate_schedule(raw_schedule)
    receipt_audit = audit_receipts(schedule, raw_receipts)
    scores = _validate_evaluations(
        raw_evaluations, schedule["schedule_sha256"],
        {run["run_id"] for run in schedule["runs"]},
    )
    receipt_by_run = {row["run_id"]: row for row in receipt_audit["runs"]}
    issues: list[dict[str, Any]] = []
    concordant = scored = unrated_terminal = 0
    for run in schedule["runs"]:
        run_id = run["run_id"]
        receipt = receipt_by_run[run_id]
        evaluation = scores[run_id]
        outcome = receipt["outcome"]
        status = evaluation["status"]
        q_present = "q" in evaluation
        run_issues: list[dict[str, Any]] = []

        if outcome == "completed":
            if status != "scored":
                run_issues.append({"code": "completed_run_not_scored"})
        elif outcome == "truncated":
            if status != "truncated":
                run_issues.append({"code": "truncation_status_mismatch"})
        elif status != "missing":
            run_issues.append({"code": "evaluation_without_terminal_receipt"})

        if q_present:
            scored += 1
            declared_artifact = evaluation.get("artifact_sha256")
            terminal_artifact = receipt["attempts"][-1]["artifact_sha256"] if outcome in ("completed", "truncated") else None
            if declared_artifact is None:
                run_issues.append({"code": "score_artifact_digest_missing"})
            if terminal_artifact is None:
                run_issues.append({"code": "score_without_terminal_artifact"})
            elif declared_artifact is not None and declared_artifact != terminal_artifact:
                run_issues.append({"code": "scored_artifact_digest_mismatch"})
        elif outcome in ("completed", "truncated"):
            unrated_terminal += 1

        if run_issues:
            issues.extend({"run_id": run_id, "receipt_outcome": outcome,
                           "evaluation_status": status, **issue} for issue in run_issues)
        elif q_present:
            concordant += 1

    all_q = scored == len(schedule["runs"])
    return {
        "schema": 1,
        "classification": CLASSIFICATION,
        "notice": NOTICE,
        "schedule_sha256": schedule["schedule_sha256"],
        "receipts_sha256": receipt_audit["receipts_sha256"],
        "evaluations_sha256": _canonical_digest(raw_evaluations),
        "declared_joint_coverage_complete": (
            all_q and not issues and receipt_audit["matrix_receipts_complete"]
        ),
        "counts": {
            "scheduled_runs": len(schedule["runs"]),
            "scored_runs": scored,
            "concordant_scored_runs": concordant,
            "unrated_terminal_runs": unrated_terminal,
            "missing_terminal_runs": receipt_audit["counts"]["missing_runs"],
            "receipt_violations": len(receipt_audit["violations"]),
            "reconciliation_issues": len(issues),
        },
        "receipt_violations": receipt_audit["violations"],
        "issues": issues,
        "criterion_4": {"status": "not_assessed", "reason": NOTICE},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("schedule", help="candidate schedule JSON path, or - for stdin")
    parser.add_argument("receipts", help="schema-1 attempts JSON path, or - for stdin")
    parser.add_argument("evaluations", help="schema-1 Q evaluations JSON path, or - for stdin")
    args = parser.parse_args(argv)
    try:
        if (args.schedule, args.receipts, args.evaluations).count("-") > 1:
            raise AnalysisError("only one input may use stdin")
        output = reconcile(
            _read_json(args.schedule), _read_json(args.receipts), _read_json(args.evaluations)
        )
    except (AnalysisError, ReceiptError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": 1, "classification": CLASSIFICATION, "error": str(exc)},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
