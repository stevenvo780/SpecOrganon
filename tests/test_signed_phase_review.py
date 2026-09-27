"""Signed phase reviews authenticate exact snapshots; fixtures stay synthetic."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from specorganon import approval, engine, review_provenance
from specorganon.ledger import read_project


REVIEWER = "human:reviewer"
AUTHOR = "human:author"
REASON = "I reviewed the exact frame snapshot and its evidence"


def _public(key: Ed25519PrivateKey) -> str:
    return base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode("ascii")


def _sign(key: Ed25519PrivateKey, challenge: dict) -> str:
    raw = base64.b64decode(challenge["message_base64"], validate=True)
    assert hashlib.sha256(raw).hexdigest() == challenge["message_sha256"]
    return base64.b64encode(key.sign(raw)).decode("ascii")


def _registry(case: Path, file: Path, reviewers: dict[str, str]) -> None:
    project = read_project(case)["project"]
    file.write_text(json.dumps({"schema": 2, "cases": {project["case_id"]: {
        "path": str(case.resolve(strict=True)),
        "project_sha256": approval.project_fingerprint(project),
        "approvers": {},
        "phase_reviewers": reviewers,
    }}}), encoding="utf-8")


def _case(tmp_path: Path, monkeypatch, *, item_actor: str = AUTHOR):
    case = tmp_path / "case"
    key = Ed25519PrivateKey.generate()
    registry = tmp_path / "trusted-reviewers.json"
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(registry))
    engine.create_case(case, "Signed review test", "synthetic test", AUTHOR)
    _registry(case, registry, {REVIEWER: _public(key)})
    engine.put_item(case, "p1", "problem", "A stated problem", [], {}, item_actor)
    engine.put_item(case, "a1", "actor", "The affected actor", ["p1"], {}, item_actor)
    engine.put_item(case, "b1", "boundary", "A defined boundary", ["p1"], {}, item_actor)
    assert engine.gate(case, "frame")["ready"]
    return case, registry, key


def _challenge(case: Path) -> dict:
    before = (case / "organon.json").read_bytes()
    challenge = engine.phase_review_challenge(case, "frame", "accept", REASON, REVIEWER)
    assert (case / "organon.json").read_bytes() == before
    message = json.loads(base64.b64decode(challenge["message_base64"], validate=True))
    assert message["purpose"] == "specorganon.phase_review"
    assert message["case_id"] == read_project(case)["project"]["case_id"]
    assert message["case_path"] == str(case.resolve(strict=True))
    assert message["project_sha256"] == approval.project_fingerprint(read_project(case)["project"])
    assert message["snapshot"] == engine.gate(case, "frame")["snapshot"]
    assert message["ledger_head_sha256"] == read_project(case)["events"][-1]["hash"]
    return challenge


def _write_rehashed_ledger(case: Path, ledger: dict) -> None:
    previous = "0" * 64
    for event in ledger["events"]:
        event["prev_hash"] = previous
        event["hash"] = hashlib.sha256(json.dumps(
            {key: value for key, value in event.items() if key != "hash"},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        previous = event["hash"]
    (case / "organon.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert read_project(case)["events"][-1]["hash"] == previous


def test_signed_review_acceptance_and_idempotent_retry(tmp_path, monkeypatch):
    case, _, key = _case(tmp_path, monkeypatch)
    signature = _sign(key, _challenge(case))
    event = engine.review_phase(case, "frame", "accept", REASON, REVIEWER, signature)
    status = engine.gate(case, "frame")
    assert status["reviewed"] and status["independent_review"]
    assert status["review_signature_verified"]
    assert status["review_provenance"] == "signed_verified"
    assert not status["accepted"]
    marker = engine.advance(case, "frame", AUTHOR)
    assert marker["payload"]["review_seq"] == event["seq"]
    assert engine.gate(case, "frame")["accepted"]
    before = (case / "organon.json").read_bytes()
    assert engine.review_phase(case, "frame", "accept", REASON, REVIEWER, signature) == event
    assert (case / "organon.json").read_bytes() == before


def test_invalid_unsigned_wrong_actor_and_stale_head_do_not_append(tmp_path, monkeypatch):
    case, _, key = _case(tmp_path, monkeypatch)
    challenge = _challenge(case)
    signature = _sign(key, challenge)
    before = (case / "organon.json").read_bytes()
    attempts = (
        (REVIEWER, None, REASON),
        (REVIEWER, _sign(Ed25519PrivateKey.generate(), challenge), REASON),
        (REVIEWER, signature, "Different reason"),
        (AUTHOR, signature, REASON),
    )
    for actor, submitted, reason in attempts:
        with pytest.raises(engine.MethodError):
            engine.review_phase(case, "frame", "accept", reason, actor, submitted)
        assert (case / "organon.json").read_bytes() == before
    engine.review_item(case, "p1", "accept", "An independent item review", REVIEWER)
    after_item_review = (case / "organon.json").read_bytes()
    with pytest.raises(engine.MethodError, match="invalid or stale"):
        engine.review_phase(case, "frame", "accept", REASON, REVIEWER, signature)
    assert (case / "organon.json").read_bytes() == after_item_review


def test_legacy_unsigned_review_and_forged_advance_remain_ineffective(tmp_path, monkeypatch):
    case, _, _ = _case(tmp_path, monkeypatch)
    status = engine.gate(case, "frame")
    legacy = engine.append_event(case, "phase_review", {
        "phase": "frame", "verdict": "accept", "reason": REASON,
        "snapshot": status["snapshot"], "independent": True,
    }, REVIEWER, expected_seq=engine.get_state(case)["revision"])
    result = engine.gate(case, "frame")
    assert result["review_provenance"] == "legacy_unverified"
    assert not result["review_signature_verified"]
    assert not result["reviewed"] and not result["independent_review"]
    history = engine.get_state(case)["phase_review_history"]
    assert history[-1]["seq"] == legacy["seq"]
    assert history[-1]["provenance"] == "legacy_unverified"
    with pytest.raises(engine.MethodError, match="accepted review"):
        engine.advance(case, "frame", AUTHOR)
    engine.append_event(case, "phase_advance", {
        "phase": "frame", "snapshot": status["snapshot"], "review_seq": legacy["seq"],
    }, AUTHOR, expected_seq=engine.get_state(case)["revision"])
    assert not engine.gate(case, "frame")["accepted"]
    assert any(e["seq"] == legacy["seq"] for e in read_project(case)["events"])


def test_reviewer_key_revocation_reopens_accepted_phase(tmp_path, monkeypatch):
    case, registry, key = _case(tmp_path, monkeypatch)
    signature = _sign(key, _challenge(case))
    engine.review_phase(case, "frame", "accept", REASON, REVIEWER, signature)
    engine.advance(case, "frame", AUTHOR)
    assert engine.gate(case, "frame")["accepted"]
    before = (case / "organon.json").read_bytes()
    _registry(case, registry, {})
    status = engine.gate(case, "frame")
    assert not status["accepted"] and not status["reviewed"]
    assert not status["review_signature_verified"]
    assert status["review_provenance"] == "signature_unverified"
    with pytest.raises(engine.MethodError, match="registry"):
        engine.phase_review_challenge(case, "frame", "accept", REASON, REVIEWER)
    assert (case / "organon.json").read_bytes() == before


def test_reviewer_alias_key_collision_fails_closed(tmp_path, monkeypatch):
    case, registry, key = _case(tmp_path, monkeypatch)
    _registry(case, registry, {REVIEWER: _public(key), "human:alias": _public(key)})
    assert engine.get_state(case)["phase_review_trust"] == "unavailable"
    with pytest.raises(engine.MethodError, match="registry"):
        engine.phase_review_challenge(case, "frame", "accept", REASON, REVIEWER)


def test_signed_self_review_cannot_claim_independence_even_with_a_valid_signature(tmp_path, monkeypatch):
    case, registry, key = _case(tmp_path, monkeypatch, item_actor=REVIEWER)
    with pytest.raises(engine.MethodError, match="independent"):
        engine.phase_review_challenge(case, "frame", "accept", REASON, REVIEWER)
    state = engine._project(case)
    snapshot = engine.gate(case, "frame")["snapshot"]
    raw = review_provenance.message(
        state["project"], case, state["head_hash"], "frame", snapshot,
        "accept", REASON, REVIEWER,
    )
    signature = base64.b64encode(key.sign(raw)).decode("ascii")
    event = engine.append_event(case, "phase_review", {
        "phase": "frame", "verdict": "accept", "reason": REASON,
        "snapshot": snapshot, "independent": True, "signature": signature,
        "key_sha256": approval.key_fingerprint(base64.b64decode(_public(key))),
    }, REVIEWER, expected_seq=state["revision"])
    status = engine.gate(case, "frame")
    assert status["review_signature_verified"] and status["review_provenance"] == "signed_verified"
    assert not status["reviewed"] and not status["independent_review"]
    with pytest.raises(engine.MethodError, match="accepted review"):
        engine.advance(case, "frame", AUTHOR)
    assert read_project(case)["events"][-1] == event
    assert registry.exists()


def test_fixture_review_rejects_signature_and_reports_synthetic(tmp_path, monkeypatch):
    monkeypatch.setenv("ORGANON_ALLOW_FIXTURES", "1")
    case = tmp_path / "fixture"
    engine.create_case(case, "Fixture", "synthetic test", AUTHOR, approval_policy="fixture")
    engine.put_item(case, "p1", "problem", "Problem", [], {}, AUTHOR)
    engine.put_item(case, "a1", "actor", "Actor", ["p1"], {}, AUTHOR)
    engine.put_item(case, "b1", "boundary", "Boundary", ["p1"], {}, AUTHOR)
    before = (case / "organon.json").read_bytes()
    with pytest.raises(engine.MethodError, match="fixture"):
        engine.phase_review_challenge(case, "frame", "accept", REASON, REVIEWER)
    with pytest.raises(engine.MethodError, match="signature"):
        engine.review_phase(case, "frame", "accept", REASON, REVIEWER, "not-a-signature")
    assert (case / "organon.json").read_bytes() == before
    engine.review_phase(case, "frame", "accept", REASON, REVIEWER)
    status = engine.gate(case, "frame")
    assert status["review_provenance"] == "synthetic_fixture"
    assert not status["review_signature_verified"]
    assert status["reviewed"]


def test_rehashed_review_payload_mutation_invalidates_signed_acceptance(tmp_path, monkeypatch):
    case, _, key = _case(tmp_path, monkeypatch)
    signature = _sign(key, _challenge(case))
    engine.review_phase(case, "frame", "accept", REASON, REVIEWER, signature)
    engine.advance(case, "frame", AUTHOR)
    assert engine.gate(case, "frame")["accepted"]
    ledger = read_project(case)
    review = next(event for event in ledger["events"] if event["kind"] == "phase_review")
    review["payload"]["reason"] = "An attacker changed the review reason"
    _write_rehashed_ledger(case, ledger)
    status = engine.gate(case, "frame")
    assert status["review_provenance"] == "signature_unverified"
    assert not status["review_signature_verified"]
    assert not status["reviewed"] and not status["accepted"]


def test_signed_review_cas_race_recovers_only_exact_peer_event(tmp_path, monkeypatch):
    case, _, key = _case(tmp_path, monkeypatch)
    signature = _sign(key, _challenge(case))
    append = engine.append_event
    winner: dict = {}

    def peer_first(path, kind, payload, actor, *, expected_seq):
        winner["event"] = append(path, kind, payload, actor, expected_seq=expected_seq)
        return append(path, kind, payload, actor, expected_seq=expected_seq)

    monkeypatch.setattr(engine, "append_event", peer_first)
    assert engine.review_phase(case, "frame", "accept", REASON, REVIEWER, signature) == winner["event"]
    assert sum(event["kind"] == "phase_review" for event in read_project(case)["events"]) == 1
    assert engine.gate(case, "frame")["reviewed"]


def test_rehashed_signed_policy_downgrade_cannot_enable_fixture_review(tmp_path, monkeypatch):
    case, _, key = _case(tmp_path, monkeypatch)
    signature = _sign(key, _challenge(case))
    engine.review_phase(case, "frame", "accept", REASON, REVIEWER, signature)
    engine.advance(case, "frame", AUTHOR)
    assert engine.gate(case, "frame")["accepted"]
    ledger = read_project(case)
    ledger["project"]["approval_policy"] = "fixture"
    _write_rehashed_ledger(case, ledger)
    monkeypatch.delenv("ORGANON_ALLOW_FIXTURES", raising=False)
    before = (case / "organon.json").read_bytes()
    state = engine.get_state(case)
    status = state["phases"]["frame"]
    assert state["approval_trust"] == "unavailable"
    assert state["phase_review_trust"] == "unavailable"
    assert status["review_provenance"] == "fixture_unavailable"
    assert not status["ready"] and not status["reviewed"]
    assert not status["independent_review"] and not status["accepted"]
    with pytest.raises(engine.MethodError):
        engine.review_phase(case, "frame", "accept", "Unsigned attack", "agent:attacker")
    with pytest.raises(engine.MethodError):
        engine.advance(case, "frame", "agent:attacker")
    assert (case / "organon.json").read_bytes() == before
    forged = engine.append_event(case, "phase_review", {
        "phase": "frame", "verdict": "accept", "reason": "forged fixture review",
        "snapshot": status["snapshot"], "independent": True,
    }, "agent:attacker", expected_seq=state["revision"])
    engine.append_event(case, "phase_advance", {
        "phase": "frame", "snapshot": status["snapshot"], "review_seq": forged["seq"],
    }, "agent:attacker", expected_seq=forged["seq"])
    assert not engine.gate(case, "frame")["accepted"]
    assert engine.get_state(case)["phase_review_history"][-1]["provenance"] == "fixture_unavailable"


def test_fixture_loses_effective_acceptance_when_opt_in_is_removed(tmp_path, monkeypatch):
    monkeypatch.setenv("ORGANON_ALLOW_FIXTURES", "1")
    case = tmp_path / "fixture"
    engine.create_case(case, "Fixture", "synthetic test", AUTHOR, approval_policy="fixture")
    engine.put_item(case, "p1", "problem", "Problem", [], {}, AUTHOR)
    engine.put_item(case, "a1", "actor", "Actor", ["p1"], {}, AUTHOR)
    engine.put_item(case, "b1", "boundary", "Boundary", ["p1"], {}, AUTHOR)
    engine.review_phase(case, "frame", "accept", REASON, REVIEWER)
    engine.advance(case, "frame", AUTHOR)
    assert engine.gate(case, "frame")["accepted"]
    monkeypatch.delenv("ORGANON_ALLOW_FIXTURES")
    before = (case / "organon.json").read_bytes()
    status = engine.gate(case, "frame")
    assert not status["ready"] and not status["reviewed"] and not status["accepted"]
    assert status["review_provenance"] == "fixture_unavailable"
    with pytest.raises(engine.MethodError):
        engine.review_phase(case, "frame", "accept", "Unsigned retry", REVIEWER)
    with pytest.raises(engine.MethodError):
        engine.advance(case, "frame", AUTHOR)
    assert (case / "organon.json").read_bytes() == before
    monkeypatch.setenv("ORGANON_ALLOW_FIXTURES", "1")
    assert engine.gate(case, "frame")["accepted"]
