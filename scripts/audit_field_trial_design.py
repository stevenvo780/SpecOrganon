"""Compare a declared field trial plan with declared food-chain observations.

Usage: ``python scripts/audit_field_trial_design.py PLAN.json FIELD.json``.
Both inputs remain under the caller's custody. A structural match does not
authenticate registration, randomization, measurement, or field impact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from audit_field_flows import (
    FieldFlowError,
    _invalid_constant,
    _object,
    _text,
    _unique_pairs,
    _utc,
    audit_field_flows,
)


CLASSIFICATION = "field_trial_design_preflight_declared_only"
PLAN_CLASSIFICATION = "field_trial_design_candidate_unsealed"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
NOTICE = (
    "The supplied candidate plan and schema-3 observation graph agree on groups, "
    "arms, strata and period windows; declared group counts and window lengths "
    "meet the protocol minimum. This does not authenticate prior registration, "
    "random assignment, weekly measurement coverage, eligible inputs, source "
    "truth, approval, causal attribution, safety, or field impact. No V or G "
    "is calculated; criterion 3 is not assessed."
)


class FieldTrialDesignError(ValueError):
    """A candidate trial plan and observation graph are inconsistent."""


def _plan_groups(value: Any) -> dict[str, tuple[str, str]]:
    if type(value) is not list or not value:
        raise FieldTrialDesignError("plan.groups must be a nonempty array")
    result: dict[str, tuple[str, str]] = {}
    for index, raw in enumerate(value):
        item = _object(raw, f"plan.groups[{index}]", {"id", "arm", "stratum"})
        group_id = _text(item["id"], f"plan.groups[{index}].id")
        arm = _text(item["arm"], f"plan.groups[{index}].arm")
        if arm not in {"control", "intervention"}:
            raise FieldTrialDesignError("plan group arm must be control or intervention")
        stratum = _text(item["stratum"], f"plan.groups[{index}].stratum")
        if group_id in result:
            raise FieldTrialDesignError(f"duplicate plan group: {group_id}")
        result[group_id] = arm, stratum
    return result


def _periods(value: Any, label: str) -> dict[str, tuple[Any, Any]]:
    if type(value) is not list or len(value) != 2:
        raise FieldTrialDesignError(f"{label} must have exactly pre and post")
    result = {}
    for index, raw in enumerate(value):
        item = _object(raw, f"{label}[{index}]", {"id", "start_utc", "end_utc"},
                       {"source"} if label == "field.periods" else None)
        period_id = _text(item["id"], f"{label}[{index}].id")
        if period_id in result:
            raise FieldTrialDesignError(f"duplicate {label} period: {period_id}")
        start = _utc(item["start_utc"], f"{label}[{index}].start_utc")
        end = _utc(item["end_utc"], f"{label}[{index}].end_utc")
        if end <= start:
            raise FieldTrialDesignError(f"{label}[{index}] has a nonpositive window")
        result[period_id] = start, end
    if set(result) != {"pre", "post"}:
        raise FieldTrialDesignError(f"{label} must have exactly pre and post")
    return result


def audit_field_trial_design(plan: Any, field: Any) -> dict[str, Any]:
    try:
        candidate = _object(plan, "plan", {
            "schema", "classification", "study_id", "registered_at_utc",
            "allocation_method", "allocation_record_sha256", "groups", "periods",
        }, {"baseline_release"})
        if type(candidate["schema"]) is not int or candidate["schema"] != 1:
            raise FieldTrialDesignError("plan.schema must be 1")
        if candidate["classification"] != PLAN_CLASSIFICATION:
            raise FieldTrialDesignError("plan.classification must identify an unsealed candidate")
        study_id = _text(candidate["study_id"], "plan.study_id")
        registered_at = _utc(candidate["registered_at_utc"], "plan.registered_at_utc")
        if candidate["allocation_method"] != "stratified_random":
            raise FieldTrialDesignError("plan must declare stratified_random allocation")
        allocation_digest = _text(candidate["allocation_record_sha256"],
                                  "plan.allocation_record_sha256")
        if SHA256.fullmatch(allocation_digest) is None:
            raise FieldTrialDesignError("plan.allocation_record_sha256 must be lowercase SHA-256")
        planned_groups = _plan_groups(candidate["groups"])
        planned_periods = _periods(candidate["periods"], "plan.periods")

        field_report = audit_field_flows(field)
        if field_report["schema"] != 3 or field.get("service") is None:
            raise FieldTrialDesignError("field must pass schema 3 with service rows")
        if field_report["study_id"] != study_id:
            raise FieldTrialDesignError("plan and field study_id differ")
        observed_groups = {
            group["id"]: (group["arm"], group["stratum"])
            for group in field["groups"]
        }
        if observed_groups != planned_groups:
            raise FieldTrialDesignError("plan and field group IDs, arms or strata differ")
        observed_periods = _periods(field["periods"], "field.periods")
        if observed_periods != planned_periods:
            raise FieldTrialDesignError("plan and field period windows differ")

        counts = Counter(arm for arm, _stratum in planned_groups.values())
        if (len(planned_groups) < 12 or counts["control"] < 6
                or counts["intervention"] < 6 or counts["control"] != counts["intervention"]):
            raise FieldTrialDesignError("trial needs at least 12 groups and balanced arms of at least 6 each")
        strata: dict[str, Counter[str]] = defaultdict(Counter)
        for arm, stratum in planned_groups.values():
            strata[stratum][arm] += 1
        if any(not arm_counts["control"] or not arm_counts["intervention"]
               for arm_counts in strata.values()):
            raise FieldTrialDesignError("each declared stratum needs both arms")
        if planned_periods["pre"][1] - planned_periods["pre"][0] < timedelta(weeks=4):
            raise FieldTrialDesignError("pre window is shorter than four weeks")
        if planned_periods["post"][1] - planned_periods["post"][0] < timedelta(weeks=8):
            raise FieldTrialDesignError("post window is shorter than eight weeks")
        baseline_release = candidate.get("baseline_release")
        if baseline_release is None and registered_at >= planned_periods["pre"][0]:
            raise FieldTrialDesignError(
                "registration after the pre window begins needs a declared baseline release"
            )
        if baseline_release is not None:
            release = _object(baseline_release, "plan.baseline_release",
                              {"first_access_at_utc", "record_sha256", "custodian_id"})
            release_at = _utc(release["first_access_at_utc"],
                              "plan.baseline_release.first_access_at_utc")
            _text(release["custodian_id"], "plan.baseline_release.custodian_id")
            release_digest = _text(release["record_sha256"],
                                   "plan.baseline_release.record_sha256")
            if SHA256.fullmatch(release_digest) is None:
                raise FieldTrialDesignError("plan.baseline_release.record_sha256 must be lowercase SHA-256")
            if release_at <= registered_at:
                raise FieldTrialDesignError("declared baseline first access must follow registration")
        first_assignment = min(_utc(group["assigned_at_utc"], "field.groups.assigned_at_utc")
                               for group in field["groups"])
        if registered_at >= first_assignment:
            raise FieldTrialDesignError("declared registration must predate every assignment")
        if any(_utc(group["source"]["observed_at_utc"], "field.groups.source.observed_at_utc")
               <= registered_at for group in field["groups"]):
            raise FieldTrialDesignError("declared assignment source predates registration")
    except FieldFlowError as exc:
        raise FieldTrialDesignError(f"field or plan structure failed: {exc}") from exc

    return {
        "schema": 1,
        "classification": CLASSIFICATION,
        "structural_match_at_read": True,
        "study_id": study_id,
        "groups": {"total": len(planned_groups), "control": counts["control"],
                   "intervention": counts["intervention"]},
        "strata": {stratum: dict(sorted(arm_counts.items()))
                   for stratum, arm_counts in sorted(strata.items())},
        "window_days": {
            period: (end - start).total_seconds() / 86400
            for period, (start, end) in sorted(planned_periods.items())
        },
        "field_scope_status": field_report["scope_status"],
        "randomization_verified": False,
        "registration_authenticated": False,
        "baseline_release_declared": baseline_release is not None,
        "baseline_release_authenticated": False,
        "weekly_measurement_coverage_verified": False,
        "execution_ready": False,
        "notice": NOTICE,
        "criterion_3": {"status": "not_assessed", "reason": NOTICE},
    }


def _read_json(path: Path) -> tuple[Any, str]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), parse_float=Decimal,
                           parse_constant=_invalid_constant, object_pairs_hook=_unique_pairs)
    except (UnicodeError, ValueError) as exc:
        raise FieldTrialDesignError(f"invalid JSON in {path}: {exc}") from exc
    return value, hashlib.sha256(raw).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan", type=Path)
    parser.add_argument("field", type=Path)
    args = parser.parse_args(argv)
    try:
        plan, plan_sha256 = _read_json(args.plan)
        field, field_sha256 = _read_json(args.field)
        report = audit_field_trial_design(plan, field)
    except (OSError, FieldTrialDesignError) as exc:
        print(f"Field trial design preflight failed: {exc}", file=sys.stderr)
        return 2
    report["input_sha256"] = {"plan": plan_sha256, "field": field_sha256}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
