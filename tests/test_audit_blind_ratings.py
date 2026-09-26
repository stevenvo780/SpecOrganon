"""Synthetic structural checks for blinded, independent rating declarations."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_blind_ratings.py"
sys.path.insert(0, str(SCRIPT.parent))
from audit_blind_ratings import RatingError, audit_blind_ratings  # noqa: E402


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _artifact(label: str) -> dict[str, str]:
    return {
        "opaque_id": _digest("opaque-" + label)[:32],
        "artifact_sha256": _digest("artifact-" + label),
        "rubric_sha256": _digest("rubric-" + label),
        "trace_sha256": _digest("trace-" + label),
    }


def _failure(label: str, code: str) -> dict[str, str]:
    return {"incident_id": _digest("incident-" + label)[:32], "code": code}


Q_RATIONALE = (
    "The third locked rating follows an independent review of the blinded "
    "sources and test evidence before inspection of process traces."
)
INCIDENT_RATIONALE = (
    "The trace evidence and test output support this explicit incident "
    "decision after comparison with both primary judgments."
)


def _resolution(label: str, resolved_code: str | None) -> dict[str, Any]:
    return {
        "incident_id": _failure(label, "unused")["incident_id"],
        "resolved_code": resolved_code,
        "rationale": INCIDENT_RATIONALE,
    }


def _rating(
    artifact: dict[str, str], evaluator: str, components: list[int],
    *, failures: list[dict[str, str]] | None = None, role: str = "primary", reveal: bool = False,
    q_resolution: bool = True, resolutions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        **artifact,
        "evaluator_id": evaluator,
        "role": role,
        "external_to_execution": True,
        "outcome_stage": {
            "recorded_at_utc": "2026-01-01T00:02:00Z" if role == "adjudicator" else "2026-01-01T00:00:00Z",
            "q_components": dict(zip(
                ("formulation", "evidence", "alternatives", "technical", "validation"),
                components, strict=True,
            )),
            "q_total": sum(components),
            "artifact_form_reveal": {
                "revealed": reveal,
                "detail": "Template identified the arm" if reveal else None,
            },
        },
        "trace_stage": {
            "recorded_at_utc": "2026-01-01T00:03:00Z" if role == "adjudicator" else "2026-01-01T00:01:00Z",
            "critical_failures": failures or [],
        },
    }
    if role == "adjudicator":
        row["adjudication"] = {
            "q_resolution": {
                "basis": "third_locked_rating", "rationale": Q_RATIONALE,
            } if q_resolution else None,
            "critical_failure_resolutions": resolutions or [],
        }
    return row


def _bundle(labels: tuple[str, ...] = ("a",)) -> tuple[dict[str, Any], dict[str, Any]]:
    artifacts = [_artifact(label) for label in labels]
    manifest = {"schema": 1, "artifacts": artifacts}
    ratings = {
        "schema": 1,
        "manifest_sha256": _canonical_digest(manifest),
        "ratings": [
            _rating(artifact, evaluator, [12, 12, 12, 12, 12])
            for artifact in artifacts for evaluator in ("external-a", "external-b")
        ],
    }
    return manifest, ratings


def test_complete_manifest_keeps_raw_scores_and_reports_simple_agreement() -> None:
    manifest, ratings = _bundle(("a", "b"))
    second = manifest["artifacts"][1]
    ratings["ratings"][2] = _rating(second, "external-a", [14] * 5,
                                     failures=[_failure("test", "false_test")], reveal=True)
    ratings["ratings"][3] = _rating(second, "external-b", [16, 16, 16, 16, 18],
                                     failures=[_failure("claim", "invented_claim")])
    ratings["ratings"].append(_rating(second, "external-c", [15] * 5,
                                       failures=[_failure("test", "false_test")],
                                       role="adjudicator", q_resolution=True,
                                       resolutions=[_resolution("test", "false_test"),
                                                    _resolution("claim", None)]))
    ratings["ratings"].reverse()

    result = audit_blind_ratings(manifest, ratings)

    assert result["classification"] == "structural_blind_rating_audit_unsealed"
    assert result["counts"] == {
        "artifacts": 2,
        "primary_ratings": 4,
        "adjudicator_ratings": 1,
        "q_total_exact_agreements": 1,
        "q_total_disagreements_over_10": 1,
        "critical_failure_exact_agreements": 1,
        "critical_failure_presence_agreements": 2,
        "disputed_critical_failure_incidents": 2,
        "component_exact_agreements": {
            "formulation": 1, "evidence": 1, "alternatives": 1,
            "technical": 1, "validation": 1,
        },
        "primary_artifact_form_reveals": 1,
        "adjudicator_artifact_form_reveals": 0,
    }
    assert [item["opaque_id"] for item in result["artifacts"]] == [
        item["opaque_id"] for item in manifest["artifacts"]
    ]
    disputed = result["artifacts"][1]
    assert [row["outcome_stage"]["q_total"] for row in disputed["primary_ratings"]] == [70, 82]
    assert disputed["adjudicator_rating"]["outcome_stage"]["q_total"] == 75
    assert disputed["agreement"]["q_total_absolute_difference"] == 12
    assert disputed["agreement"]["adjudication_triggers"] == [
        "q_total_difference_gt_10", "critical_failure_disagreement"
    ]
    assert disputed["agreement"]["adjudication_status"] == "decision_declared_unverified"
    assert disputed["agreement"]["disputed_incident_ids"] == sorted([
        _failure("test", "false_test")["incident_id"],
        _failure("claim", "invented_claim")["incident_id"],
    ])
    assert disputed["primary_ratings"][0]["outcome_stage"]["artifact_form_reveal"]["revealed"]
    assert "consolidated_q" not in result and "q" not in disputed
    assert result["criterion_4"]["status"] == "not_assessed"
    for phrase in ("bytes", "identity", "blindness", "independence", "chronology", "consolidated Q"):
        assert phrase in result["notice"]
    assert "mapping from raw evidence anchors" in result["notice"]
    assert "no preregistered" not in result["notice"]


def test_difference_of_exactly_ten_needs_no_adjudicator() -> None:
    manifest, ratings = _bundle()
    ratings["ratings"][1]["outcome_stage"]["q_components"]["formulation"] = 2
    ratings["ratings"][1]["outcome_stage"]["q_total"] = 50
    result = audit_blind_ratings(manifest, ratings)
    assert result["artifacts"][0]["agreement"]["q_total_absolute_difference"] == 10
    assert result["counts"]["adjudicator_ratings"] == 0


def test_every_manifest_id_requires_its_own_two_ratings() -> None:
    manifest, ratings = _bundle(("a", "b"))
    ratings["ratings"] = ratings["ratings"][:2]
    with pytest.raises(RatingError, match="requires exactly two distinct primary ratings; found 0"):
        audit_blind_ratings(manifest, ratings)


@pytest.mark.parametrize("field,value,match", [
    ("component", 20.0, "integer from 0 to 20"),
    ("component", 12.5, "integer from 0 to 20"),
    ("total", 60.0, "integer from 0 to 100"),
    ("total", 60.5, "integer from 0 to 100"),
    ("total", True, "integer from 0 to 100"),
])
def test_q_scores_require_json_integers(field: str, value: Any, match: str) -> None:
    manifest, ratings = _bundle()
    outcome = ratings["ratings"][0]["outcome_stage"]
    if field == "component":
        outcome["q_components"]["formulation"] = value
    else:
        outcome["q_total"] = value
    with pytest.raises(RatingError, match=match):
        audit_blind_ratings(manifest, ratings)


def test_critical_failure_code_divergence_requires_third_even_if_both_flag_failure() -> None:
    manifest, ratings = _bundle()
    ratings["ratings"][0]["trace_stage"]["critical_failures"] = [_failure("same", "false_test")]
    ratings["ratings"][1]["trace_stage"]["critical_failures"] = [_failure("same", "invented_claim")]
    with pytest.raises(RatingError, match="requires a distinct third adjudicator"):
        audit_blind_ratings(manifest, ratings)
    ratings["ratings"].append(_rating(manifest["artifacts"][0], "external-c", [12] * 5,
                                       failures=[_failure("same", "false_test")],
                                       role="adjudicator",
                                       resolutions=[_resolution("same", "false_test")]))
    result = audit_blind_ratings(manifest, ratings)
    assert result["counts"]["critical_failure_presence_agreements"] == 1
    assert result["counts"]["critical_failure_exact_agreements"] == 0


def test_same_code_on_distinct_incidents_requires_adjudication() -> None:
    manifest, ratings = _bundle()
    ratings["ratings"][0]["trace_stage"]["critical_failures"] = [_failure("one", "false_test")]
    ratings["ratings"][1]["trace_stage"]["critical_failures"] = [_failure("two", "false_test")]
    with pytest.raises(RatingError, match="requires a distinct third adjudicator"):
        audit_blind_ratings(manifest, ratings)
    ratings["ratings"].append(_rating(manifest["artifacts"][0], "external-c", [12] * 5,
                                       failures=[_failure("one", "false_test")],
                                       role="adjudicator", resolutions=[
                                           _resolution("one", "false_test"), _resolution("two", None),
                                       ]))
    result = audit_blind_ratings(manifest, ratings)
    assert result["counts"]["disputed_critical_failure_incidents"] == 2
    assert result["counts"]["critical_failure_presence_agreements"] == 1
    assert result["counts"]["critical_failure_exact_agreements"] == 0


def test_nonresolving_third_record_is_rejected() -> None:
    manifest, ratings = _bundle()
    ratings["ratings"][0] = _rating(manifest["artifacts"][0], "external-a", [0] * 5,
                                     failures=[_failure("one", "false_test")])
    ratings["ratings"][1] = _rating(manifest["artifacts"][0], "external-b", [20] * 5,
                                     failures=[_failure("two", "invented_claim")])
    adjudicator = _rating(manifest["artifacts"][0], "external-c", [10] * 5,
                          role="adjudicator", q_resolution=False)
    ratings["ratings"].append(adjudicator)
    with pytest.raises(RatingError, match="q_resolution must be an object"):
        audit_blind_ratings(manifest, ratings)

    adjudicator["adjudication"]["q_resolution"] = {
        "basis": "third_locked_rating", "rationale": "ok",
    }
    with pytest.raises(RatingError, match="substantive rationale"):
        audit_blind_ratings(manifest, ratings)

    adjudicator["adjudication"]["q_resolution"]["rationale"] = Q_RATIONALE
    adjudicator["adjudication"]["q_resolution"]["basis"] = "first_primary"
    with pytest.raises(RatingError, match="basis must be third_locked_rating"):
        audit_blind_ratings(manifest, ratings)
    adjudicator["adjudication"]["q_resolution"]["basis"] = "third_locked_rating"
    with pytest.raises(RatingError, match="every disputed critical failure incident"):
        audit_blind_ratings(manifest, ratings)

    adjudicator["adjudication"]["critical_failure_resolutions"] = [
        _resolution("one", None), _resolution("two", None),
    ]
    result = audit_blind_ratings(manifest, ratings)
    assert result["artifacts"][0]["agreement"]["adjudication_status"] == "decision_declared_unverified"
    assert "q" not in result["artifacts"][0]


def test_third_only_incident_requires_explicit_decision() -> None:
    manifest, ratings = _bundle()
    ratings["ratings"][1]["outcome_stage"]["q_components"] = dict.fromkeys(
        ratings["ratings"][1]["outcome_stage"]["q_components"], 15
    )
    ratings["ratings"][1]["outcome_stage"]["q_total"] = 75
    adjudicator = _rating(manifest["artifacts"][0], "external-c", [14] * 5,
                          failures=[_failure("new", "safety_harm")],
                          role="adjudicator", q_resolution=True)
    ratings["ratings"].append(adjudicator)
    with pytest.raises(RatingError, match="every disputed critical failure incident"):
        audit_blind_ratings(manifest, ratings)
    adjudicator["adjudication"]["critical_failure_resolutions"] = [
        _resolution("new", "safety_harm")
    ]
    result = audit_blind_ratings(manifest, ratings)
    assert result["artifacts"][0]["agreement"]["disputed_incident_ids"] == [
        _failure("new", "safety_harm")["incident_id"]
    ]
    assert result["artifacts"][0]["adjudicator_rating"]["trace_stage"]["critical_failures"] == [
        _failure("new", "safety_harm")
    ]


def test_adjudicator_claimed_score_lock_follows_both_primaries() -> None:
    manifest, ratings = _bundle()
    ratings["ratings"][1]["outcome_stage"]["q_components"]["formulation"] = 0
    ratings["ratings"][1]["outcome_stage"]["q_total"] = 48
    adjudicator = _rating(manifest["artifacts"][0], "external-c", [10] * 5,
                          role="adjudicator", q_resolution=True)
    ratings["ratings"].append(adjudicator)
    adjudicator["outcome_stage"]["recorded_at_utc"] = "2025-12-31T23:59:00Z"
    adjudicator["trace_stage"]["recorded_at_utc"] = "2025-12-31T23:59:30Z"
    with pytest.raises(RatingError, match="adjudicator outcome stage must follow both primary trace audits"):
        audit_blind_ratings(manifest, ratings)


def test_adjudicator_claimed_score_lock_precedes_its_trace_audit() -> None:
    manifest, ratings = _bundle()
    ratings["ratings"][1]["outcome_stage"]["q_components"]["formulation"] = 0
    ratings["ratings"][1]["outcome_stage"]["q_total"] = 48
    adjudicator = _rating(manifest["artifacts"][0], "external-c", [10] * 5,
                          role="adjudicator")
    adjudicator["trace_stage"]["recorded_at_utc"] = adjudicator["outcome_stage"]["recorded_at_utc"]
    ratings["ratings"].append(adjudicator)
    with pytest.raises(RatingError, match="outcome stage must precede trace audit stage"):
        audit_blind_ratings(manifest, ratings)


def test_agreed_primary_incident_remains_visible_without_third_revote() -> None:
    manifest, ratings = _bundle()
    for row in ratings["ratings"]:
        row["trace_stage"]["critical_failures"] = [_failure("agreed", "false_test")]
    ratings["ratings"][1]["outcome_stage"]["q_components"]["formulation"] = 0
    ratings["ratings"][1]["outcome_stage"]["q_total"] = 48
    ratings["ratings"].append(_rating(manifest["artifacts"][0], "external-c", [10] * 5,
                                       role="adjudicator", q_resolution=True))
    result = audit_blind_ratings(manifest, ratings)
    assert result["counts"]["critical_failure_exact_agreements"] == 1
    assert result["artifacts"][0]["agreement"]["disputed_incident_ids"] == []
    assert all(row["trace_stage"]["critical_failures"] == [_failure("agreed", "false_test")]
               for row in result["artifacts"][0]["primary_ratings"])


def test_incident_resolution_must_match_third_trace_rating() -> None:
    manifest, ratings = _bundle()
    ratings["ratings"][0]["trace_stage"]["critical_failures"] = [_failure("one", "false_test")]
    ratings["ratings"].append(_rating(manifest["artifacts"][0], "external-c", [12] * 5,
                                       failures=[_failure("one", "false_test")],
                                       role="adjudicator", resolutions=[_resolution("one", None)]))
    with pytest.raises(RatingError, match="contradicts the adjudicator trace rating"):
        audit_blind_ratings(manifest, ratings)


@pytest.mark.parametrize("change,match", [
    ("duplicate_resolution", "duplicate adjudication incident_id"),
    ("extra_resolution", "every disputed critical failure incident"),
    ("short_rationale", "substantive rationale"),
])
def test_incident_decision_shape_is_bounded(change: str, match: str) -> None:
    manifest, ratings = _bundle()
    ratings["ratings"][0]["trace_stage"]["critical_failures"] = [_failure("one", "false_test")]
    adjudicator = _rating(manifest["artifacts"][0], "external-c", [12] * 5,
                          failures=[_failure("one", "false_test")], role="adjudicator",
                          resolutions=[_resolution("one", "false_test")])
    ratings["ratings"].append(adjudicator)
    decisions = adjudicator["adjudication"]["critical_failure_resolutions"]
    if change == "duplicate_resolution":
        decisions.append(copy.deepcopy(decisions[0]))
    elif change == "extra_resolution":
        decisions.append(_resolution("other", None))
    elif change == "short_rationale":
        decisions[0]["rationale"] = "ok"
    with pytest.raises(RatingError, match=match):
        audit_blind_ratings(manifest, ratings)


@pytest.mark.parametrize("change,match", [
    ("missing_primary", "exactly two distinct primary"),
    ("extra_primary", "exactly two distinct primary"),
    ("duplicate_evaluator", "duplicate evaluator_id"),
    ("unrecognized_id", "unrecognized rating opaque_id"),
    ("duplicate_manifest_id", "duplicate manifest opaque_id"),
    ("bad_opaque_id", "32 lowercase hexadecimal"),
    ("bad_manifest_digest", "rating manifest digest mismatch"),
    ("bad_artifact_binding", "artifact_sha256 does not match"),
    ("bad_rubric_binding", "rubric_sha256 does not match"),
    ("bad_trace_binding", "trace_sha256 does not match"),
    ("bad_schema", "ratings.schema must be integer 1"),
    ("hidden_arm", "unexpected keys"),
    ("not_external", "external_to_execution must be true"),
    ("bad_role", "role must be primary or adjudicator"),
    ("component_over_cap", "integer from 0 to 20"),
    ("negative_component", "integer from 0 to 20"),
    ("boolean_component", "integer from 0 to 20"),
    ("nan_component", "integer from 0 to 20"),
    ("wrong_total", "must equal the five-component sum"),
    ("missing_component", "missing keys"),
    ("reverse_stage", "outcome stage must precede"),
    ("equal_stage", "outcome stage must precede"),
    ("invalid_time", "valid UTC timestamp"),
    ("revealed_without_detail", "nonempty, trimmed string"),
    ("detail_without_reveal", "detail must be null"),
    ("duplicate_failure", "duplicate critical failure incident_id"),
    ("bad_failure_code", "lowercase code"),
    ("untriggered_adjudicator", "without a protocol trigger"),
    ("adjudicator_not_distinct", "duplicate evaluator_id"),
    ("duplicate_adjudicator", "duplicate adjudicator row"),
    ("missing_adjudication", "missing keys"),
])
def test_invalid_structures_are_rejected(change: str, match: str) -> None:
    manifest, ratings = _bundle()
    row = ratings["ratings"][0]
    if change == "missing_primary":
        ratings["ratings"].pop()
    elif change == "extra_primary":
        ratings["ratings"].append(_rating(manifest["artifacts"][0], "external-c", [12] * 5))
    elif change == "duplicate_evaluator":
        ratings["ratings"][1]["evaluator_id"] = row["evaluator_id"]
    elif change == "unrecognized_id":
        row["opaque_id"] = _digest("unknown")[:32]
    elif change == "duplicate_manifest_id":
        manifest["artifacts"].append(copy.deepcopy(manifest["artifacts"][0]))
    elif change == "bad_opaque_id":
        row["opaque_id"] = "R-F-N"
    elif change == "bad_manifest_digest":
        ratings["manifest_sha256"] = _digest("other")
    elif change == "bad_artifact_binding":
        row["artifact_sha256"] = _digest("other")
    elif change == "bad_rubric_binding":
        row["rubric_sha256"] = _digest("other")
    elif change == "bad_trace_binding":
        row["trace_sha256"] = _digest("other")
    elif change == "bad_schema":
        ratings["schema"] = True
    elif change == "hidden_arm":
        row["arm"] = "T"
    elif change == "not_external":
        row["external_to_execution"] = False
    elif change == "bad_role":
        row["role"] = "executor"
    elif change == "component_over_cap":
        row["outcome_stage"]["q_components"]["formulation"] = 21
    elif change == "negative_component":
        row["outcome_stage"]["q_components"]["formulation"] = -1
    elif change == "boolean_component":
        row["outcome_stage"]["q_components"]["formulation"] = True
    elif change == "nan_component":
        row["outcome_stage"]["q_components"]["formulation"] = float("nan")
    elif change == "wrong_total":
        row["outcome_stage"]["q_total"] = 61
    elif change == "missing_component":
        del row["outcome_stage"]["q_components"]["technical"]
    elif change == "reverse_stage":
        row["trace_stage"]["recorded_at_utc"] = "2025-12-31T23:59:59Z"
    elif change == "equal_stage":
        row["trace_stage"]["recorded_at_utc"] = row["outcome_stage"]["recorded_at_utc"]
    elif change == "invalid_time":
        row["outcome_stage"]["recorded_at_utc"] = "2026-02-30T00:00:00Z"
    elif change == "revealed_without_detail":
        row["outcome_stage"]["artifact_form_reveal"] = {"revealed": True, "detail": None}
    elif change == "detail_without_reveal":
        row["outcome_stage"]["artifact_form_reveal"]["detail"] = "Suspected T"
    elif change == "duplicate_failure":
        row["trace_stage"]["critical_failures"] = [
            _failure("same", "false_test"), _failure("same", "invented_claim")
        ]
    elif change == "bad_failure_code":
        row["trace_stage"]["critical_failures"] = [_failure("same", "False Test")]
    elif change == "untriggered_adjudicator":
        ratings["ratings"].append(_rating(manifest["artifacts"][0], "external-c", [12] * 5,
                                           role="adjudicator"))
    elif change == "adjudicator_not_distinct":
        ratings["ratings"][1]["outcome_stage"]["q_components"]["formulation"] = 0
        ratings["ratings"][1]["outcome_stage"]["q_total"] = 48
        ratings["ratings"].append(_rating(manifest["artifacts"][0], "external-a", [12] * 5,
                                           role="adjudicator"))
    elif change == "duplicate_adjudicator":
        ratings["ratings"][1]["outcome_stage"]["q_components"]["formulation"] = 0
        ratings["ratings"][1]["outcome_stage"]["q_total"] = 48
        ratings["ratings"].extend([
            _rating(manifest["artifacts"][0], evaluator, [12] * 5, role="adjudicator")
            for evaluator in ("external-c", "external-d")
        ])
    elif change == "missing_adjudication":
        ratings["ratings"][1]["outcome_stage"]["q_components"]["formulation"] = 0
        ratings["ratings"][1]["outcome_stage"]["q_total"] = 48
        adjudicator = _rating(manifest["artifacts"][0], "external-c", [12] * 5,
                              role="adjudicator")
        del adjudicator["adjudication"]
        ratings["ratings"].append(adjudicator)
    with pytest.raises(RatingError, match=match):
        audit_blind_ratings(manifest, ratings)


def test_cli_success_and_safe_failure_modes(tmp_path: Path) -> None:
    manifest, ratings = _bundle()
    manifest_path = tmp_path / "manifest.json"
    ratings_path = tmp_path / "ratings.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    ratings_path.write_text(json.dumps(ratings), encoding="utf-8")

    success = subprocess.run([sys.executable, str(SCRIPT), str(manifest_path), str(ratings_path)],
                             capture_output=True, text=True, check=False)
    assert success.returncode == 0 and success.stderr == ""
    output = json.loads(success.stdout)
    assert output["counts"]["primary_ratings"] == 2
    assert sorted(path.name for path in tmp_path.iterdir()) == ["manifest.json", "ratings.json"]

    stdin_success = subprocess.run([sys.executable, str(SCRIPT), "-", str(ratings_path)],
                                   input=json.dumps(manifest), capture_output=True, text=True, check=False)
    assert stdin_success.returncode == 0
    assert json.loads(stdin_success.stdout)["manifest_sha256"] == _canonical_digest(manifest)

    for raw, expected_error in (
        ('{"schema":1,"schema":1,"artifacts":[]}', "duplicate JSON object key"),
        ('{"schema":1,"artifacts":[NaN]}', "non-JSON numeric constant"),
        ('{"schema":' + "9" * 5000 + ',"artifacts":[]}', "invalid JSON input:"),
        ("[" * 10000 + "0" + "]" * 10000, "invalid JSON input:"),
    ):
        failure = subprocess.run([sys.executable, str(SCRIPT), "-", str(ratings_path)],
                                 input=raw, capture_output=True, text=True, check=False)
        assert failure.returncode == 2 and failure.stderr == ""
        assert expected_error in json.loads(failure.stdout)["error"]

    both_stdin = subprocess.run([sys.executable, str(SCRIPT), "-", "-"],
                                input="{}", capture_output=True, text=True, check=False)
    assert both_stdin.returncode == 2
    assert "only one input may use stdin" in json.loads(both_stdin.stdout)["error"]

    ratings["ratings"][0]["rubric_sha256"] = _digest("wrong")
    ratings_path.write_text(json.dumps(ratings), encoding="utf-8")
    failure = subprocess.run([sys.executable, str(SCRIPT), str(manifest_path), str(ratings_path)],
                             capture_output=True, text=True, check=False)
    assert failure.returncode == 2
    assert "rubric_sha256 does not match" in json.loads(failure.stdout)["error"]


@pytest.mark.parametrize("kind,literal,field", [
    ("total", "60.0", "q_total"),
    ("total", "60.0000000000000001", "q_total"),
    ("component", "20.0", "formulation"),
    ("component", "20.0000000000000001", "formulation"),
])
def test_cli_rejects_decimal_q_literals_even_when_float_rounds_to_integer(
    tmp_path: Path, kind: str, literal: str, field: str,
) -> None:
    manifest, ratings = _bundle()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    if kind == "total":
        ratings["ratings"][1]["outcome_stage"]["q_components"] = dict.fromkeys(
            ratings["ratings"][1]["outcome_stage"]["q_components"], 10
        )
        ratings["ratings"][1]["outcome_stage"]["q_total"] = 50
        old = '"q_total":60'
        new = f'"q_total":{literal}'
    else:
        ratings["ratings"][0]["outcome_stage"]["q_components"] = {
            "formulation": 20, "evidence": 10, "alternatives": 10,
            "technical": 10, "validation": 10,
        }
        old = '"formulation":20'
        new = f'"formulation":{literal}'
    raw = json.dumps(ratings, separators=(",", ":"))
    assert raw.count(old) == 1
    raw = raw.replace(old, new, 1)
    failure = subprocess.run([sys.executable, str(SCRIPT), str(manifest_path), "-"],
                             input=raw, capture_output=True, text=True, check=False)
    assert failure.returncode == 2 and failure.stderr == ""
    error = json.loads(failure.stdout)
    assert field in error["error"]
    assert "must be an integer" in error["error"]
    assert "ratings_sha256" not in error
