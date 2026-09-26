"""Structurally audit independent, two-stage, blinded artifact ratings.

Usage: ``python scripts/audit_blind_ratings.py manifest.json ratings.json``.
Either path may be ``-`` for stdin, but not both. The script reads JSON and
prints JSON; it never opens the referenced blinded result package, rubric,
or blinded trace bytes. Here ``artifact_sha256`` names the blinded package,
which can differ from a terminal execution receipt's artifact digest after
selection or redaction. ``trace_sha256`` similarly names the blinded trace.

Schema 1 uses this shape (digests are lowercase SHA-256 hex strings)::

    manifest = {"schema": 1, "artifacts": [
      {"opaque_id": "<32 lowercase hex digits>",
       "artifact_sha256": "<digest>", "rubric_sha256": "<digest>",
       "trace_sha256": "<digest>"}]}
    ratings = {"schema": 1, "manifest_sha256": "<canonical JSON digest>",
      "ratings": [
        {"opaque_id": "<same opaque ID>", "evaluator_id": "external-1",
         "role": "primary", "external_to_execution": true,
         "artifact_sha256": "<digest>", "rubric_sha256": "<digest>",
         "trace_sha256": "<digest>",
         "outcome_stage": {
           "recorded_at_utc": "2026-01-01T00:00:00Z",
           "q_components": {"formulation": 0, "evidence": 0,
                            "alternatives": 0, "technical": 0, "validation": 0},
           "q_total": 0,
           "artifact_form_reveal": {"revealed": false, "detail": null}},
         "trace_stage": {"recorded_at_utc": "2026-01-01T00:01:00Z",
                         "critical_failures": [
                           {"incident_id": "<32 lowercase hex digits>",
                            "code": "false_test"}]}}
      ]}

All five Q components and ``q_total`` must be JSON integers. Decimal literals,
including ``20.0``, are rejected; a downstream pair mean may be fractional.

Each opaque ID needs two distinct primary evaluator records. If their total Q
differs by more than 10, or their critical-failure incident/code maps differ,
it also needs one distinct ``role: adjudicator`` record. Each incident ID may
occur once per rating, including when several incidents share a code. The
adjudicator adds ``adjudication`` with ``q_resolution`` and
``critical_failure_resolutions``. A Q resolution declares
``basis: third_locked_rating`` and a rationale for that independent score,
consistent with the protocol's adjudication rule. Each
critical-failure resolution declares ``incident_id``, ``resolved_code`` (null
means absent), and a rationale. Exactly one resolution is needed for each
incident disputed by the primaries, newly found by the third evaluator, or
reclassified by the third evaluator. An agreed primary incident remains
visible even if absent from the third rating. The adjudicator's stage-one
time must follow both primaries' stage-two times, and precede the adjudicator's
own stage-two time. An unsolicited adjudicator is rejected.

The checks enforce declarations and claimed timestamp order only. The stage-one
timestamp is the claimed score-lock time; the JSON cannot prove a real lock.
The rationale check enforces length, not meaning. Digests bind
labels in these JSON documents; they do not prove possession of bytes, real
evaluator identity, blindness, independence, or when either stage occurred.
Incident IDs are also supplied labels; this audit cannot verify the custodian's
mapping from raw evidence anchors to canonical incident IDs.
This structural auditor leaves Q values separate. The protocol now specifies a
downstream consolidation rule, but applying it requires the externally
custodied blind evidence and incident decisions that this JSON cannot verify.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


CLASSIFICATION = "structural_blind_rating_audit_unsealed"
COMPONENTS = ("formulation", "evidence", "alternatives", "technical", "validation")
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
OPAQUE_ID = re.compile(r"[0-9a-f]{32}\Z")
FAILURE_CODE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
UTC_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
NOTICE = (
    "Structural audit only. Declared SHA-256 values bind labels here but do not "
    "prove the artifact, rubric, or trace bytes; evaluator identity, external "
    "status, blindness, independence, or the claimed stage chronology are not "
    "authenticated. The custodian's mapping from raw evidence anchors to "
    "canonical incident IDs is not verified. Adjudication decisions and "
    "rationales are declared, not "
    "substantively verified. Raw ratings remain separate; no consolidated Q "
    "is produced here. This audit does not apply the protocol's downstream Q "
    "consolidation rule. Criterion 4 "
    "is not assessed by this audit."
)


class RatingError(ValueError):
    """The manifest or rating declarations do not satisfy schema 1."""


def _object(value: Any, name: str, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise RatingError(f"{name} must be an object")
    missing, extra = keys - value.keys(), value.keys() - keys
    if missing or extra:
        raise RatingError(f"{name} has missing keys {sorted(missing)} or unexpected keys {sorted(extra)}")
    return value


def _array(value: Any, name: str, *, nonempty: bool = False) -> list[Any]:
    if type(value) is not list or (nonempty and not value):
        raise RatingError(f"{name} must be {'a nonempty' if nonempty else 'an'} array")
    return value


def _text(value: Any, name: str, *, max_length: int = 512) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > max_length:
        raise RatingError(f"{name} must be a nonempty, trimmed string of at most {max_length} characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise RatingError(f"{name} contains a control character")
    return value


def _rationale(value: Any, name: str) -> str:
    rationale = _text(value, name, max_length=2000)
    if len(rationale) < 40 or len(rationale.split()) < 8:
        raise RatingError(f"{name} needs a substantive rationale of at least 40 characters and 8 words")
    return rationale


def _sha256(value: Any, name: str) -> str:
    if type(value) is not str or HEX_SHA256.fullmatch(value) is None:
        raise RatingError(f"{name} must be a lowercase 64-character SHA-256 digest")
    return value


def _opaque_id(value: Any, name: str) -> str:
    if type(value) is not str or OPAQUE_ID.fullmatch(value) is None:
        raise RatingError(f"{name} must be 32 lowercase hexadecimal digits")
    return value


def _failure_code(value: Any, name: str) -> str:
    code = _text(value, name, max_length=64)
    if FAILURE_CODE.fullmatch(code) is None:
        raise RatingError(f"{name} must be a lowercase code")
    return code


def _utc(value: Any, name: str) -> datetime:
    if type(value) is not str or UTC_TIMESTAMP.fullmatch(value) is None:
        raise RatingError(f"{name} must be a UTC ISO-8601 timestamp ending in Z")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RatingError(f"{name} is not a valid UTC timestamp") from exc


def _score(value: Any, name: str, ceiling: int) -> int:
    if type(value) is not int or not 0 <= value <= ceiling:
        raise RatingError(f"{name} must be an integer from 0 to {ceiling}")
    return value


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_manifest(raw: Any) -> tuple[dict[str, dict[str, str]], str]:
    manifest = _object(raw, "manifest", {"schema", "artifacts"})
    if type(manifest["schema"]) is not int or manifest["schema"] != 1:
        raise RatingError("manifest.schema must be integer 1")
    artifacts = _array(manifest["artifacts"], "manifest.artifacts", nonempty=True)
    expected: dict[str, dict[str, str]] = {}
    for index, value in enumerate(artifacts):
        name = f"manifest.artifacts[{index}]"
        artifact = _object(value, name, {
            "opaque_id", "artifact_sha256", "rubric_sha256", "trace_sha256"
        })
        opaque_id = _opaque_id(artifact["opaque_id"], f"{name}.opaque_id")
        if opaque_id in expected:
            raise RatingError(f"duplicate manifest opaque_id: {opaque_id}")
        for key in ("artifact_sha256", "rubric_sha256", "trace_sha256"):
            _sha256(artifact[key], f"{name}.{key}")
        expected[opaque_id] = artifact
    return expected, _canonical_digest(manifest)


def _validate_rating(raw: Any, index: int, expected: dict[str, dict[str, str]]) -> dict[str, Any]:
    name = f"ratings.ratings[{index}]"
    if type(raw) is not dict:
        raise RatingError(f"{name} must be an object")
    role = raw.get("role")
    if type(role) is not str or role not in ("primary", "adjudicator"):
        raise RatingError(f"{name}.role must be primary or adjudicator")
    keys = {
        "opaque_id", "evaluator_id", "role", "external_to_execution",
        "artifact_sha256", "rubric_sha256", "trace_sha256", "outcome_stage", "trace_stage"
    }
    if role == "adjudicator":
        keys.add("adjudication")
    row = _object(raw, name, keys)
    opaque_id = _opaque_id(row["opaque_id"], f"{name}.opaque_id")
    if opaque_id not in expected:
        raise RatingError(f"unrecognized rating opaque_id: {opaque_id}")
    _text(row["evaluator_id"], f"{name}.evaluator_id", max_length=128)
    if row["external_to_execution"] is not True:
        raise RatingError(f"{name}.external_to_execution must be true")
    for key in ("artifact_sha256", "rubric_sha256", "trace_sha256"):
        digest = _sha256(row[key], f"{name}.{key}")
        if digest != expected[opaque_id][key]:
            raise RatingError(f"{name}.{key} does not match manifest binding")

    outcome = _object(row["outcome_stage"], f"{name}.outcome_stage", {
        "recorded_at_utc", "q_components", "q_total", "artifact_form_reveal"
    })
    scored_at = _utc(outcome["recorded_at_utc"], f"{name}.outcome_stage.recorded_at_utc")
    components = _object(outcome["q_components"], f"{name}.outcome_stage.q_components", set(COMPONENTS))
    component_scores = [
        _score(components[key], f"{name}.outcome_stage.q_components.{key}", 20)
        for key in COMPONENTS
    ]
    total = _score(outcome["q_total"], f"{name}.outcome_stage.q_total", 100)
    if total != sum(component_scores):
        raise RatingError(f"{name}.outcome_stage.q_total must equal the five-component sum")
    reveal = _object(outcome["artifact_form_reveal"],
                     f"{name}.outcome_stage.artifact_form_reveal", {"revealed", "detail"})
    if type(reveal["revealed"]) is not bool:
        raise RatingError(f"{name}.outcome_stage.artifact_form_reveal.revealed must be a boolean")
    if reveal["revealed"]:
        _text(reveal["detail"], f"{name}.outcome_stage.artifact_form_reveal.detail")
    elif reveal["detail"] is not None:
        raise RatingError(f"{name}.outcome_stage.artifact_form_reveal.detail must be null when not revealed")

    trace = _object(row["trace_stage"], f"{name}.trace_stage", {
        "recorded_at_utc", "critical_failures"
    })
    audited_at = _utc(trace["recorded_at_utc"], f"{name}.trace_stage.recorded_at_utc")
    if scored_at >= audited_at:
        raise RatingError(f"{name} outcome stage must precede trace audit stage")
    failures = _array(trace["critical_failures"], f"{name}.trace_stage.critical_failures")
    seen_incidents: set[str] = set()
    for failure_index, value in enumerate(failures):
        failure_name = f"{name}.trace_stage.critical_failures[{failure_index}]"
        failure = _object(value, failure_name, {"incident_id", "code"})
        incident_id = _opaque_id(failure["incident_id"], f"{failure_name}.incident_id")
        _failure_code(failure["code"], f"{failure_name}.code")
        if incident_id in seen_incidents:
            raise RatingError(f"{name} has duplicate critical failure incident_id: {incident_id}")
        seen_incidents.add(incident_id)
    if role == "adjudicator":
        adjudication = _object(row["adjudication"], f"{name}.adjudication", {
            "q_resolution", "critical_failure_resolutions"
        })
        q_resolution = _object(adjudication["q_resolution"],
                               f"{name}.adjudication.q_resolution", {"basis", "rationale"})
        if q_resolution["basis"] != "third_locked_rating":
            raise RatingError(f"{name}.adjudication.q_resolution.basis must be third_locked_rating")
        _rationale(q_resolution["rationale"], f"{name}.adjudication.q_resolution.rationale")
        resolutions = _array(adjudication["critical_failure_resolutions"],
                             f"{name}.adjudication.critical_failure_resolutions")
        seen_resolutions: set[str] = set()
        for resolution_index, value in enumerate(resolutions):
            resolution_name = f"{name}.adjudication.critical_failure_resolutions[{resolution_index}]"
            resolution = _object(value, resolution_name, {"incident_id", "resolved_code", "rationale"})
            incident_id = _opaque_id(resolution["incident_id"], f"{resolution_name}.incident_id")
            if incident_id in seen_resolutions:
                raise RatingError(f"{name} has duplicate adjudication incident_id: {incident_id}")
            seen_resolutions.add(incident_id)
            if resolution["resolved_code"] is not None:
                _failure_code(resolution["resolved_code"], f"{resolution_name}.resolved_code")
            _rationale(resolution["rationale"], f"{resolution_name}.rationale")
    return row


def _incident_map(row: dict[str, Any]) -> dict[str, str]:
    return {
        item["incident_id"]: item["code"]
        for item in row["trace_stage"]["critical_failures"]
    }


def audit_blind_ratings(raw_manifest: Any, raw_ratings: Any) -> dict[str, Any]:
    """Validate complete declared ratings and report agreement without pooling Q."""
    expected, manifest_digest = _validate_manifest(raw_manifest)
    ratings = _object(raw_ratings, "ratings", {"schema", "manifest_sha256", "ratings"})
    if type(ratings["schema"]) is not int or ratings["schema"] != 1:
        raise RatingError("ratings.schema must be integer 1")
    if _sha256(ratings["manifest_sha256"], "ratings.manifest_sha256") != manifest_digest:
        raise RatingError("rating manifest digest mismatch")
    rows = _array(ratings["ratings"], "ratings.ratings")
    by_artifact: dict[str, list[dict[str, Any]]] = {opaque_id: [] for opaque_id in expected}
    for index, value in enumerate(rows):
        row = _validate_rating(value, index, expected)
        group = by_artifact[row["opaque_id"]]
        if any(existing["evaluator_id"] == row["evaluator_id"] for existing in group):
            raise RatingError(f"duplicate evaluator_id for opaque_id {row['opaque_id']}: {row['evaluator_id']}")
        if row["role"] == "adjudicator" and any(existing["role"] == "adjudicator" for existing in group):
            raise RatingError(f"duplicate adjudicator row for opaque_id {row['opaque_id']}")
        group.append(row)

    counts: dict[str, Any] = {
        "artifacts": len(expected), "primary_ratings": 0, "adjudicator_ratings": 0,
        "q_total_exact_agreements": 0, "q_total_disagreements_over_10": 0,
        "critical_failure_exact_agreements": 0,
        "critical_failure_presence_agreements": 0,
        "disputed_critical_failure_incidents": 0,
        "component_exact_agreements": {key: 0 for key in COMPONENTS},
        "primary_artifact_form_reveals": 0, "adjudicator_artifact_form_reveals": 0,
    }
    reports = []
    for opaque_id, group in by_artifact.items():
        primary = sorted((item for item in group if item["role"] == "primary"),
                         key=lambda item: item["evaluator_id"])
        adjudicators = [item for item in group if item["role"] == "adjudicator"]
        if len(primary) != 2:
            raise RatingError(f"opaque_id {opaque_id} requires exactly two distinct primary ratings; found {len(primary)}")
        left, right = primary
        left_outcome, right_outcome = left["outcome_stage"], right["outcome_stage"]
        q_difference = abs(left_outcome["q_total"] - right_outcome["q_total"])
        component_differences = {
            key: abs(left_outcome["q_components"][key] - right_outcome["q_components"][key])
            for key in COMPONENTS
        }
        left_failures = _incident_map(left)
        right_failures = _incident_map(right)
        critical_disagreement = left_failures != right_failures
        triggers = []
        if q_difference > 10:
            triggers.append("q_total_difference_gt_10")
        if critical_disagreement:
            triggers.append("critical_failure_disagreement")
        if triggers and not adjudicators:
            raise RatingError(f"opaque_id {opaque_id} requires a distinct third adjudicator")
        if not triggers and adjudicators:
            raise RatingError(f"opaque_id {opaque_id} has an adjudicator without a protocol trigger")
        disputed_incident_ids: list[str] = []
        if adjudicators:
            adjudicator = adjudicators[0]
            primary_finished = max(
                _utc(item["trace_stage"]["recorded_at_utc"], "primary trace time")
                for item in primary
            )
            adjudicator_started = _utc(
                adjudicator["outcome_stage"]["recorded_at_utc"], "adjudicator outcome time"
            )
            if adjudicator_started <= primary_finished:
                raise RatingError(f"opaque_id {opaque_id} adjudicator outcome stage must follow both primary trace audits")
            decision = adjudicator["adjudication"]
            third_failures = _incident_map(adjudicator)
            all_incidents = left_failures.keys() | right_failures.keys() | third_failures.keys()
            disputed_incident_ids = sorted(
                incident_id for incident_id in all_incidents
                if left_failures.get(incident_id) != right_failures.get(incident_id)
                or (incident_id in third_failures
                    and third_failures[incident_id] != left_failures.get(incident_id))
            )
            resolutions = {
                item["incident_id"]: item["resolved_code"]
                for item in decision["critical_failure_resolutions"]
            }
            if set(resolutions) != set(disputed_incident_ids):
                raise RatingError(
                    f"opaque_id {opaque_id} must adjudicate every disputed critical failure incident "
                    "exactly once, with no undisputed incident"
                )
            for incident_id in disputed_incident_ids:
                if resolutions[incident_id] != third_failures.get(incident_id):
                    raise RatingError(
                        f"opaque_id {opaque_id} adjudication for incident {incident_id} "
                        "contradicts the adjudicator trace rating"
                    )
        counts["primary_ratings"] += 2
        counts["adjudicator_ratings"] += len(adjudicators)
        counts["q_total_exact_agreements"] += q_difference == 0
        counts["q_total_disagreements_over_10"] += q_difference > 10
        counts["critical_failure_exact_agreements"] += not critical_disagreement
        counts["critical_failure_presence_agreements"] += bool(left_failures) == bool(right_failures)
        counts["disputed_critical_failure_incidents"] += len(disputed_incident_ids)
        for key, difference in component_differences.items():
            counts["component_exact_agreements"][key] += difference == 0
        counts["primary_artifact_form_reveals"] += sum(
            item["outcome_stage"]["artifact_form_reveal"]["revealed"] for item in primary
        )
        counts["adjudicator_artifact_form_reveals"] += sum(
            item["outcome_stage"]["artifact_form_reveal"]["revealed"] for item in adjudicators
        )
        reports.append({
            "opaque_id": opaque_id,
            "bindings": deepcopy(expected[opaque_id]),
            "primary_ratings": deepcopy(primary),
            "adjudicator_rating": deepcopy(adjudicators[0]) if adjudicators else None,
            "agreement": {
                "q_total_absolute_difference": q_difference,
                "component_absolute_differences": component_differences,
                "critical_failure_exact_agreement": not critical_disagreement,
                "critical_failure_presence_agreement": bool(left_failures) == bool(right_failures),
                "disputed_incident_ids": disputed_incident_ids,
                "adjudication_triggers": triggers,
                "adjudication_status": "decision_declared_unverified" if adjudicators else "not_required",
            },
        })
    return {
        "schema": 1,
        "classification": CLASSIFICATION,
        "notice": NOTICE,
        "manifest_sha256": manifest_digest,
        "ratings_sha256": _canonical_digest(ratings),
        "counts": counts,
        "artifacts": reports,
        "criterion_4": {"status": "not_assessed", "reason": NOTICE},
    }


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RatingError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise RatingError(f"non-JSON numeric constant: {value}")


def _read_json(path: str) -> Any:
    source = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(source, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant)
    except RatingError:
        raise
    except (ValueError, RecursionError) as exc:
        raise RatingError(f"invalid JSON input: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", help="expected opaque artifact manifest JSON, or - for stdin")
    parser.add_argument("ratings", help="schema-1 rating records JSON, or - for stdin")
    args = parser.parse_args(argv)
    try:
        if args.manifest == args.ratings == "-":
            raise RatingError("only one input may use stdin")
        output = audit_blind_ratings(_read_json(args.manifest), _read_json(args.ratings))
    except (RatingError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": 1, "classification": CLASSIFICATION, "error": str(exc)},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
