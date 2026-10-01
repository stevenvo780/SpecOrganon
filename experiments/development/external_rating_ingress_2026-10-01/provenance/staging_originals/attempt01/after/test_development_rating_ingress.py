"""Synthetic scores and incidents only; no actual human evaluation is supplied."""
from __future__ import annotations

import builtins
import copy
import hashlib
import json
from pathlib import Path

import pytest

import development_rating_ingress as ingress

PUBLIC = Path("/workspace/SpecOrganon/experiments/development/coordinated_contract_2026-10-01/public_contract")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"


@pytest.fixture
def control():
    delivery = b"SYNTHETIC BLINDED DELIVERY; NOT A REAL CASE OR RUNTIME"
    rubric, contract = (PUBLIC / "rubric.json").read_bytes(), (PUBLIC / "delivery_contract.json").read_bytes()
    rating = {"schema": 1, "classification": ingress.CLASSIFICATION,
              "blinded_delivery_sha256": sha(delivery), "rubric_sha256": sha(rubric), "delivery_contract_sha256": sha(contract),
              "reviewer_reference_sha256": sha(b"SYNTHETIC REVIEWER REFERENCE; NOT A PERSON"),
              "scores": {key: 20 for key in ingress.DIMENSIONS},
              "critical_incidents": [{"incident_id": "PRIVATE-INCIDENT-ID", "type": "false_test_result",
                                      "evidence_sha256": sha(b"SYNTHETIC EVIDENCE; NOT AN ACTUAL INCIDENT"),
                                      "description": "PRIVATE-HUMAN-NAME-KEY-HEADER-SENTINEL"}],
              "declarations": {key: True for key in ingress.DECLARATION_FIELDS}}
    kwargs = {"blinded_delivery_raw": delivery, "blinded_delivery_sha256": sha(delivery),
              "rubric_raw": rubric, "rubric_sha256": sha(rubric),
              "delivery_contract_raw": contract, "delivery_contract_sha256": sha(contract)}
    return rating, kwargs


def validate(control):
    rating, kwargs = control
    raw = encode(rating)
    return ingress.validate_development_rating(raw, rating_sha256=sha(raw), **kwargs)


def test_high_total_keeps_incidents_visible_and_human_declarations_unverified(control):
    before = copy.deepcopy(control)
    report = validate(control)
    assert report["declared_component_total"] == 100
    assert report["declared_incident_count"] == 1 and report["has_declared_critical_incidents"]
    assert report["critical_incidents"][0]["type"] == "false_test_result"
    assert report["critical_incidents"][0]["incident_id_sha256"] == sha(b"PRIVATE-INCIDENT-ID")
    assert report["declarations"]["human_judgment"] is True
    assert all(value is False for key, value in report.items() if key.endswith("_verified"))
    assert not report["Q_demonstrated"] and not report["acceptance_assessed"] and not report["confirmatory_rating_rules_applied"]
    assert "PRIVATE" not in json.dumps(report)
    assert control == before


def test_original_pretty_bytes_preserved_without_reencoding(control):
    rating, kwargs = control
    pretty, compact = encode(rating), json.dumps(rating, separators=(",", ":")).encode()
    first = ingress.validate_development_rating(pretty, rating_sha256=sha(pretty), **kwargs)
    second = ingress.validate_development_rating(compact, rating_sha256=sha(compact), **kwargs)
    assert first["scores"] == second["scores"] and sha(pretty) != sha(compact)
    assert first["binding"]["raw_rating_sha256"] == sha(pretty)
    assert second["binding"]["raw_rating_sha256"] == sha(compact)
    assert first["binding"]["raw_rating_bytes"] == len(pretty)


@pytest.mark.parametrize("value", [-1, 21, True, False, None, "10", 10.0, [], {}])
def test_invalid_score_types_or_ranges_rejected(control, value):
    control[0]["scores"]["evidence"] = value
    with pytest.raises(ingress.RatingIngressError):
        validate(control)


@pytest.mark.parametrize("dimension", ingress.DIMENSIONS)
def test_missing_dimension_is_not_imputed(control, dimension):
    del control[0]["scores"][dimension]
    with pytest.raises(ingress.RatingIngressError, match="invalid_score_dimensions"):
        validate(control)


@pytest.mark.parametrize("target", ["rating", "scores", "declarations", "incident"])
def test_closed_fields_reject_unregistered_acceptance_or_q_fields(control, target):
    rating = control[0]
    objects = {"rating": rating, "scores": rating["scores"], "declarations": rating["declarations"],
               "incident": rating["critical_incidents"][0]}
    objects[target]["acceptance"] = "PRIVATE-SECRET-SENTINEL"
    with pytest.raises(ingress.RatingIngressError) as error:
        validate(control)
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("field", ["schema", "classification", "reviewer_reference_sha256", "critical_incidents", "declarations"])
def test_required_fields_are_not_fabricated(control, field):
    del control[0][field]
    with pytest.raises(ingress.RatingIngressError, match="invalid_closed_rating_schema"):
        validate(control)


@pytest.mark.parametrize("field", ["blinded_delivery_sha256", "rubric_sha256", "delivery_contract_sha256"])
def test_rating_binding_cannot_be_changed(control, field):
    control[0][field] = "a" * 64
    with pytest.raises(ingress.RatingIngressError, match="rating_artifact_binding_disagrees"):
        validate(control)


@pytest.mark.parametrize("field", ["blinded_delivery", "rubric", "delivery_contract"])
def test_supplied_bytes_tampering_rejected(control, field):
    control[1][field + "_raw"] += b"changed"
    with pytest.raises(ingress.RatingIngressError, match="byte_digest_disagrees"):
        validate(control)


@pytest.mark.parametrize("field", ["rubric", "delivery_contract"])
def test_rehashed_public_contract_replacement_is_rejected(control, field):
    raw = control[1][field + "_raw"] + b"\n"
    control[1][field + "_raw"] = raw
    control[1][field + "_sha256"] = sha(raw)
    control[0][field + "_sha256"] = sha(raw)
    with pytest.raises(ingress.RatingIngressError, match="public_contract_pin_disagrees"):
        validate(control)


@pytest.mark.parametrize("digest", [True, None, "A" * 64, "a" * 63, "PRIVATE-KEY", 123])
def test_digest_types_are_strict_and_messages_fixed(control, digest):
    control[0]["reviewer_reference_sha256"] = digest
    if digest is None:
        assert validate(control)["binding"]["reviewer_reference_sha256"] is None
    else:
        with pytest.raises(ingress.RatingIngressError, match="invalid_digest") as error:
            validate(control)
        assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("kind", ingress.CRITICAL_TYPES)
def test_each_public_incident_type_is_supported_separately(control, kind):
    control[0]["critical_incidents"][0]["type"] = kind
    report = validate(control)
    assert report["declared_incident_counts_by_type"][kind] == 1
    assert report["declared_component_total"] == 100


@pytest.mark.parametrize("changes", [{"incident_id": "invalid/name"}, {"type": "other"}, {"type": True},
                                     {"evidence_sha256": None}, {"description": " "}, {"description": None}])
def test_invalid_incident_fields_rejected(control, changes):
    control[0]["critical_incidents"][0].update(changes)
    with pytest.raises(ingress.RatingIngressError):
        validate(control)


def test_duplicate_incident_ids_rejected_without_harmonizing_evidence(control):
    control[0]["critical_incidents"].append(copy.deepcopy(control[0]["critical_incidents"][0]))
    with pytest.raises(ingress.RatingIngressError, match="duplicate_incident_identifier"):
        validate(control)


def test_distinct_incident_ids_with_same_evidence_remain_declared(control):
    other = copy.deepcopy(control[0]["critical_incidents"][0])
    other["incident_id"] = "second-provisional-id"
    control[0]["critical_incidents"].append(other)
    report = validate(control)
    assert report["declared_incident_count"] == 2 and not report["canonical_incident_equivalence_verified"]


def test_empty_incidents_and_unknown_declarations_do_not_establish_absence_of_errors(control):
    control[0]["critical_incidents"] = []
    control[0]["declarations"] = {key: None for key in ingress.DECLARATION_FIELDS}
    report = validate(control)
    assert report["declared_incident_count"] == 0 and not report["critical_review_complete_verified"]
    assert report["declarations"]["critical_review_complete"] is None


@pytest.mark.parametrize("value", [1, "true", [], {}])
def test_declaration_types_do_not_turn_truthy_values_into_verified_claims(control, value):
    control[0]["declarations"]["human_judgment"] = value
    with pytest.raises(ingress.RatingIngressError, match="invalid_closed_declarations"):
        validate(control)


@pytest.mark.parametrize("fragment", [b'"scores":{},', b'"schema":1,'])
def test_duplicate_rating_fields_rejected(control, fragment):
    rating, kwargs = control
    raw = encode(rating)
    raw = b"{" + fragment + raw[1:]
    with pytest.raises(ingress.RatingIngressError, match="duplicate_json_field"):
        ingress.validate_development_rating(raw, rating_sha256=sha(raw), **kwargs)


@pytest.mark.parametrize("raw", [b'{"private":NaN}', b'{"private":Infinity}', b'{"private":1e999}', b'{', b'[]', b'\xff'])
def test_invalid_json_finite_types_and_utf8_rejected_with_sanitized_error(control, raw):
    with pytest.raises(ingress.RatingIngressError) as error:
        ingress.validate_development_rating(raw, rating_sha256=sha(raw), **control[1])
    assert "private" not in str(error.value)


def test_raw_rating_digest_tampering_and_bytes_types_rejected(control):
    raw = encode(control[0])
    with pytest.raises(ingress.RatingIngressError, match="byte_digest_disagrees"):
        ingress.validate_development_rating(raw, rating_sha256="a" * 64, **control[1])
    with pytest.raises(ingress.RatingIngressError, match="invalid_input_bytes"):
        ingress.validate_development_rating(bytearray(raw), rating_sha256=sha(raw), **control[1])


def test_api_uses_only_supplied_bytes_without_file_io(control, monkeypatch):
    def reject(*_, **__):
        raise AssertionError("unexpected file IO")

    with monkeypatch.context() as scope:
        scope.setattr(builtins, "open", reject)
        scope.setattr(Path, "read_bytes", reject)
        report = validate(control)
    assert report["schema_and_byte_bindings_valid"]


def test_bounded_inventory_and_rating_bytes(control):
    raw = b" " * (ingress.MAX_RATING_BYTES + 1)
    with pytest.raises(ingress.RatingIngressError, match="invalid_input_bytes"):
        ingress.validate_development_rating(raw, rating_sha256=sha(raw), **control[1])
    base = control[0]["critical_incidents"][0]
    control[0]["critical_incidents"] = [{**base, "incident_id": f"incident-{number}"} for number in range(ingress.MAX_INCIDENTS + 1)]
    with pytest.raises(ingress.RatingIngressError, match="invalid_incident_inventory"):
        validate(control)
