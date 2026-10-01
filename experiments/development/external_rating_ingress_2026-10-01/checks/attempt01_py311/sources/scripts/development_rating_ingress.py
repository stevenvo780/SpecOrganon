"""Pure ingress for externally supplied, declared human DEV ratings.

No files are opened and no judges or scores are generated. The caller retains
all original bytes and any external evidence. Byte bindings and a valid schema
establish local consistency; identity, independence, blinding, chronology,
custody and quality remain unverified. Confirmatory judging rules do not govern
this DEV ingress.

Rating schema 1 has exactly: schema, classification, blinded_delivery_sha256,
rubric_sha256, delivery_contract_sha256, reviewer_reference_sha256, scores,
critical_incidents and declarations. Reviewer reference may be null. Incidents
have exactly incident_id, type, evidence_sha256, description. Declarations are
six explicit bool/null values listed in DECLARATION_FIELDS; absence is invalid,
null means unknown. The original bytes need not be canonical JSON.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

DIMENSIONS = ("formulation", "evidence", "intervention", "technical", "validation")
CRITICAL_TYPES = ("invented_observation", "false_test_result", "unapproved_normative_commitment",
                  "unjustified_advance", "unfounded_requirement", "safety_harm")
DECLARATION_FIELDS = ("human_judgment", "independent_reviewer", "blinded_review", "chronology_preserved",
                      "external_custody", "critical_review_complete")
RATING_FIELDS = {"schema", "classification", "blinded_delivery_sha256", "rubric_sha256",
                 "delivery_contract_sha256", "reviewer_reference_sha256", "scores", "critical_incidents", "declarations"}
INCIDENT_FIELDS = {"incident_id", "type", "evidence_sha256", "description"}
CLASSIFICATION = "declared_human_development_rating"
RUBRIC_SHA256 = "bf46f946eed27cf603477c8ec8cff31d7fa58098bac6444dffcff7a706fcac7b"
DELIVERY_CONTRACT_SHA256 = "5bc13e976593d9edbd40b7378da21d6483ca0e0d0887ad63ecd3726b9afe0ab8"
PROTOCOL_REFERENCE_SHA256 = "3fd27c7cdb1842732f9fe37191a844e0d1e74bd1f1019331eb98ab8584eb0341"
MAX_RATING_BYTES = 256 * 1024
MAX_BLINDED_DELIVERY_BYTES = 4 * 1024 * 1024
MAX_PUBLIC_CONTRACT_BYTES = 1024 * 1024
MAX_INCIDENTS = 128
SHA = re.compile(r"[0-9a-f]{64}\Z")
INCIDENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")


class RatingIngressError(ValueError):
    """Rejection with a fixed message that contains no supplied content."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise RatingIngressError(reason)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: Any) -> str:
    _require(type(value) is str and SHA.fullmatch(value) is not None, "invalid_digest")
    return value


def _bound_bytes(raw: Any, digest: Any, maximum: int) -> str:
    checked = _digest(digest)
    _require(type(raw) is bytes and 1 <= len(raw) <= maximum, "invalid_input_bytes")
    _require(_sha(raw) == checked, "byte_digest_disagrees")
    return checked


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate_json_field")
        result[key] = value
    return result


def _reject_number(_: str) -> None:
    raise RatingIngressError("noninteger_json_number")


def _json(raw: bytes) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_float=_reject_number, parse_constant=_reject_number)
    except RatingIngressError:
        raise
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise RatingIngressError("invalid_rating_json") from None
    _require(type(value) is dict, "invalid_rating_object")
    return value


def validate_development_rating(
    rating_raw: bytes, *, rating_sha256: str,
    blinded_delivery_raw: bytes, blinded_delivery_sha256: str,
    rubric_raw: bytes, rubric_sha256: str,
    delivery_contract_raw: bytes, delivery_contract_sha256: str,
) -> dict:
    """Check exact supplied byte bindings and return an allowlisted summary.

    An arbitrary opaque delivery is hashed; its actual content, provenance and
    successful redaction are not evaluated. Descriptions and reviewer references
    remain in the caller's original rating. This API does not save a replacement
    rating, evaluate an artifact, or decide acceptance.
    """
    try:
        return _validate(rating_raw, rating_sha256, blinded_delivery_raw, blinded_delivery_sha256,
                         rubric_raw, rubric_sha256, delivery_contract_raw, delivery_contract_sha256)
    except RatingIngressError:
        raise
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise RatingIngressError("rating_schema_rejected") from None


def _validate(rating_raw, rating_sha256, blinded_delivery_raw, blinded_delivery_sha256,
              rubric_raw, rubric_sha256, delivery_contract_raw, delivery_contract_sha256):
    raw_sha = _bound_bytes(rating_raw, rating_sha256, MAX_RATING_BYTES)
    delivery_sha = _bound_bytes(blinded_delivery_raw, blinded_delivery_sha256, MAX_BLINDED_DELIVERY_BYTES)
    rubric_sha = _bound_bytes(rubric_raw, rubric_sha256, MAX_PUBLIC_CONTRACT_BYTES)
    contract_sha = _bound_bytes(delivery_contract_raw, delivery_contract_sha256, MAX_PUBLIC_CONTRACT_BYTES)
    _require(rubric_sha == RUBRIC_SHA256 and contract_sha == DELIVERY_CONTRACT_SHA256,
             "public_contract_pin_disagrees")
    value = _json(rating_raw)
    _require(set(value) == RATING_FIELDS and type(value["schema"]) is int and value["schema"] == 1
             and value["classification"] == CLASSIFICATION, "invalid_closed_rating_schema")
    _require(_digest(value["blinded_delivery_sha256"]) == delivery_sha
             and _digest(value["rubric_sha256"]) == rubric_sha
             and _digest(value["delivery_contract_sha256"]) == contract_sha, "rating_artifact_binding_disagrees")
    reviewer = value["reviewer_reference_sha256"]
    if reviewer is not None:
        _digest(reviewer)
    scores = value["scores"]
    _require(type(scores) is dict and set(scores) == set(DIMENSIONS), "invalid_score_dimensions")
    for score in scores.values():
        _require(type(score) is int and 0 <= score <= 20, "invalid_component_score")
    declarations = value["declarations"]
    _require(type(declarations) is dict and set(declarations) == set(DECLARATION_FIELDS)
             and all(item is None or type(item) is bool for item in declarations.values()), "invalid_closed_declarations")
    incidents = value["critical_incidents"]
    _require(type(incidents) is list and len(incidents) <= MAX_INCIDENTS, "invalid_incident_inventory")
    seen, public_incidents = set(), []
    for incident in incidents:
        _require(type(incident) is dict and set(incident) == INCIDENT_FIELDS, "invalid_closed_incident")
        identifier = incident["incident_id"]
        _require(type(identifier) is str and INCIDENT_ID.fullmatch(identifier) is not None,
                 "invalid_incident_identifier")
        _require(identifier not in seen, "duplicate_incident_identifier")
        seen.add(identifier)
        kind = incident["type"]
        _require(type(kind) is str and kind in CRITICAL_TYPES, "invalid_incident_type")
        evidence_sha = _digest(incident["evidence_sha256"])
        description = incident["description"]
        _require(type(description) is str and description.strip() and len(description.encode("utf-8")) <= 4096,
                 "invalid_incident_description")
        public_incidents.append({"incident_id_sha256": _sha(identifier.encode("utf-8")), "type": kind,
                                 "evidence_sha256": evidence_sha, "description_sha256": _sha(description.encode("utf-8"))})
    return {"schema": 1, "classification": "development_rating_ingress_local_declarations_unverified",
            "schema_and_byte_bindings_valid": True,
            "binding": {"raw_rating_sha256": raw_sha, "raw_rating_bytes": len(rating_raw),
                        "blinded_delivery_sha256": delivery_sha, "blinded_delivery_bytes": len(blinded_delivery_raw),
                        "rubric_sha256": rubric_sha, "delivery_contract_sha256": contract_sha,
                        "protocol_reference_sha256": PROTOCOL_REFERENCE_SHA256,
                        "reviewer_reference_sha256": reviewer},
            "scores": {key: scores[key] for key in DIMENSIONS}, "declared_component_total": sum(scores.values()),
            "critical_incidents": public_incidents, "declared_incident_count": len(public_incidents),
            "has_declared_critical_incidents": bool(public_incidents),
            "declared_incident_counts_by_type": {key: sum(row["type"] == key for row in public_incidents) for key in CRITICAL_TYPES},
            "declarations": {key: declarations[key] for key in DECLARATION_FIELDS},
            "human_judgment_verified": False, "reviewer_identity_verified": False, "reviewer_independence_verified": False,
            "blinding_verified": False, "chronology_verified": False, "custody_verified": False,
            "critical_review_complete_verified": False, "incident_evidence_verified": False,
            "canonical_incident_equivalence_verified": False, "independent_source_or_test_verification": False,
            "quality_verified": False, "Q_demonstrated": False, "acceptance_assessed": False,
            "formal_cell_executed": False, "confirmatory_rating_rules_applied": False,
            "scope": "one_supplied_DEV_rating_shape_and_byte_binding_only",
            "missing": ["authenticated_reviewer_identity", "verified_independence", "verified_blinding",
                        "externally_verified_chronology_and_custody", "independent_artifact_source_and_test_checks",
                        "verified_incident_evidence", "verified_quality_and_acceptance"]}
