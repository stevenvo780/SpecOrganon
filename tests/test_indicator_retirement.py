"""Synthetic lifecycle controls; no empirical or human-authority claims."""

from __future__ import annotations

import base64
import copy
import hashlib
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from specorganon import approval, engine
from specorganon.ledger import read_project
from specorganon.workflow import KIND_TO_PHASE


pytestmark = pytest.mark.usefixtures("enable_fixture_policy")


def _put(case, id, kind, refs=(), data=None, *, actor="agent:author", text=None):
    return engine.put_item(case, id, kind, text or id, list(refs), data or {}, actor)


def _update(case, id, *, refs=None, data=None, actor="agent:author"):
    item = engine.get_state(case)["items"][id]
    return _put(case, id, item["kind"], list(item["deps"]) if refs is None else refs,
                item["data"] if data is None else data, actor=actor, text=item["text"])


def _signature(key, challenge):
    return base64.b64encode(key.sign(base64.b64decode(challenge["message_base64"]))).decode()


def _registry(case, file):
    keys = {actor: Ed25519PrivateKey.generate() for actor in (
        "human:approver", "agent:reviewer", "agent:retirer", "agent:other-reviewer",
    )}
    public = {actor: base64.b64encode(key.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw)).decode() for actor, key in keys.items()}
    project = read_project(case)["project"]
    file.write_text(json.dumps({"schema": 2, "cases": {project["case_id"]: {
        "path": str(case.resolve()), "project_sha256": approval.project_fingerprint(project),
        "approvers": {"human:approver": public["human:approver"]},
        "phase_reviewers": {actor: value for actor, value in public.items()
                            if actor != "human:approver"},
    }}}), encoding="utf-8")
    return keys


def _accept(case, phase, keys=None, *, actor="agent:reviewer"):
    assert engine.gate(case, phase)["ready"], engine.gate(case, phase)["blockers"]
    reason = "Synthetic mechanics phase review"
    signature = None if keys is None else _signature(keys[actor], engine.phase_review_challenge(
        case, phase, "accept", reason, actor))
    review = engine.review_phase(case, phase, "accept", reason, actor, signature)
    marker = engine.advance(case, phase, "agent:lead")
    assert engine.gate(case, phase)["accepted"]
    return review, marker


def _case(tmp_path, monkeypatch, *, signed=False, accepted=False, archive=False):
    registry = tmp_path / "public-registry.json"
    registry.write_text(json.dumps({"schema": 2, "cases": {}}), encoding="utf-8")
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(registry))
    monkeypatch.delenv("ORGANON_LEDGER_ANCHORS_FILE", raising=False)
    case = tmp_path / "case"
    engine.create_case(case, "Synthetic indicator lifecycle", "test", "agent:author",
                       approval_policy="signed" if signed else "fixture")
    keys = _registry(case, registry) if signed else None
    _put(case, "p1", "problem")
    _put(case, "a1", "actor", ["p1"])
    _put(case, "b1", "boundary", ["p1"])
    if accepted:
        _accept(case, "frame", keys)
        _put(case, "c1", "concept", ["p1"])
        _put(case, "s1", "assumption", ["p1"])
        _put(case, "f1", "frame_option", ["p1"], text="Synthetic framing one")
        _put(case, "f2", "frame_option", ["p1"], text="Synthetic framing two")
    _put(case, "n1", "norm", ["p1", "a1"])
    if accepted:
        reason = "Synthetic mechanics approval, not human authority"
        signature = None if keys is None else _signature(keys["human:approver"],
            engine.approval_challenge(case, "n1", reason, "human:approver"))
        engine.approve(case, "n1", reason, "human:approver" if signed else "human:fixture", signature)
        _accept(case, "critique", keys)
    _put(case, "q1", "question", ["p1"])
    _put(case, "h1", "hypothesis", ["q1"])
    _put(case, "pr", "protocol", ["q1", "h1"], {
        "population": "synthetic control", "method": "declared fixture mechanics",
        "comparison": "same synthetic metric", "uncertainty": "no field observations",
    })
    data = {
        "origin": "derived", "source": "synthetic fixture", "date": "2026-09-30",
        "locator": "value", "metric_key": "synthetic_fraction", "scope": "synthetic",
        "unit": "fraction", "value": "0.5",
    }
    if archive:
        content = b'{"value":"0.5","classification":"synthetic"}\n'
        (case / "reading.json").write_bytes(content)
        data.update(archive="reading.json", source_sha256=hashlib.sha256(content).hexdigest())
    _put(case, "e1", "evidence", ["pr"], data)
    _put(case, "old", "indicator", ["p1", "n1", "pr"], {
        "metric": "legacy_pair", "unit": "fraction",
    })
    _put(case, "new", "indicator", ["p1", "n1", "pr", "e1"], {
        "metric": "synthetic_fraction", "unit": "fraction",
    })
    review = engine.review_item(case, "old", "reject", "Synthetic technical rejection",
                                "agent:negative-reviewer")
    args = {"path": case, "id": "old", "replacements": {"new": 1},
            "reason": "Synthetic scalar replacement", "actor": "agent:retirer",
            "expected_version": 1, "expected_review_seq": review["seq"]}
    return case, args, keys


def _blocked(case, args, *, match=None, **changes):
    before = (case / "organon.json").read_bytes()
    with pytest.raises(engine.MethodError, match=match):
        engine.retire_indicator(**(args | changes))
    assert (case / "organon.json").read_bytes() == before


def test_retirement_preserves_rejection_history_and_does_not_approve(tmp_path, monkeypatch):
    case, args, _ = _case(tmp_path, monkeypatch, signed=True)
    prefix = copy.deepcopy(read_project(case)["events"])
    event = engine.retire_indicator(**args)
    assert event["kind"] == "indicator_retire"
    assert event["payload"] == {
        "id": "old", "version": 1, "replacements": {"new": 1},
        "review_seq": args["expected_review_seq"], "reason": args["reason"],
    }
    events = read_project(case)["events"]
    assert events[:-1] == prefix and events[-1] == event
    state = engine.get_state(case)
    old = state["items"]["old"]
    assert old["retired"] and old["retirement_status"] == "effective"
    assert old["issues"] == ["latest item review rejected this version"]
    assert old["retirement_issues"] == []
    assert old["retirement_history"] == state["indicator_retirement_history"]
    assert old["retirement_history"][0]["seq"] == event["seq"]
    assert old["retirement_history"][0]["effective"] is True
    assert engine.trace(case, "old")["item"] == old
    assert not state["items"]["n1"]["approved"]
    assert all(not phase["accepted"] for phase in state["phases"].values())
    assert not any(e["kind"] in {"approval", "phase_review", "phase_advance"} for e in events)


@pytest.mark.parametrize("changes", [
    {"expected_version": True}, {"expected_version": 1.0}, {"expected_version": "1"},
    {"expected_version": 0}, {"expected_version": 2},
    {"expected_review_seq": True}, {"expected_review_seq": 0}, {"expected_review_seq": 1},
    {"replacements": {}}, {"replacements": []}, {"replacements": {"new": True}},
    {"replacements": {"new": 1.0}}, {"replacements": {"new": "1"}},
    {"replacements": {"new": 0}}, {"replacements": {"new": 2}},
    {"replacements": {"missing": 1}}, {"replacements": {"p1": 1}},
    {"replacements": {"old": 1}},
    {"replacements": {f"id{i}": 1 for i in range(33)}},
    {"id": "n1"}, {"id": "missing"}, {"id": "x"}, {"reason": " "},
    {"reason": None}, {"actor": " "}, {"actor": None},
])
def test_strict_guards_types_and_scope_leave_no_events(tmp_path, monkeypatch, changes):
    case, args, _ = _case(tmp_path, monkeypatch)
    _blocked(case, args, **changes)


def test_duplicate_api_and_forged_event_are_rejected(tmp_path, monkeypatch):
    case, args, _ = _case(tmp_path, monkeypatch)
    event = engine.retire_indicator(**args)
    _blocked(case, args)
    engine.append_event(case, "indicator_retire", event["payload"], "agent:other",
                        expected_seq=event["seq"])
    with pytest.raises(engine.MethodError, match="already effectively retired"):
        engine.get_state(case)


@pytest.mark.parametrize("bad_data", [{"unit": "fraction"}, {"metric": "legacy_pair"}])
def test_source_rejection_cannot_hide_own_structural_errors(tmp_path, monkeypatch, bad_data):
    case, args, _ = _case(tmp_path, monkeypatch)
    _update(case, "old", data=bad_data)
    review = engine.review_item(case, "old", "reject", "Synthetic rejection", "agent:negative-reviewer")
    args.update(expected_version=2, expected_review_seq=review["seq"])
    assert len(engine.get_state(case)["items"]["old"]["issues"]) == 2
    _blocked(case, args)


@pytest.mark.parametrize("stale_consumer", [False, True])
def test_any_current_consumer_even_an_outdated_reference_blocks(tmp_path, monkeypatch, stale_consumer):
    case, args, _ = _case(tmp_path, monkeypatch)
    _put(case, "consumer", "synthesis", ["old"])
    if stale_consumer:
        _update(case, "old")
        review = engine.review_item(case, "old", "reject", "Synthetic rejection", "agent:negative-reviewer")
        args.update(expected_version=2, expected_review_seq=review["seq"])
        assert engine.get_state(case)["items"]["consumer"]["stale"]
    _blocked(case, args)


@pytest.mark.parametrize("mutation", [
    "accept_review", "challenge_source", "ancestor_issue", "stale_source",
    "uncovered_problem", "uncovered_norm", "source_dependency", "no_numeric_evidence",
    "wrong_metric", "wrong_unit", "replacement_rejected", "replacement_contested",
])
def test_semantic_preconditions_are_not_bypassed(tmp_path, monkeypatch, mutation):
    case, args, _ = _case(tmp_path, monkeypatch)
    if mutation == "accept_review":
        engine.review_item(case, "old", "accept", "Synthetic latest review", "agent:negative-reviewer")
    elif mutation == "challenge_source":
        engine.challenge(case, "old", "new", "Synthetic contradiction", "agent:critic")
    elif mutation == "ancestor_issue":
        _update(case, "pr", data={})
        _update(case, "old")
        review = engine.review_item(case, "old", "reject", "Synthetic rejection", "agent:negative-reviewer")
        args.update(expected_version=2, expected_review_seq=review["seq"])
    elif mutation == "stale_source":
        _update(case, "p1")
    elif mutation in {"uncovered_problem", "uncovered_norm"}:
        _put(case, "p2", "problem")
        refs = ["p1", "n1", "pr", "p2"]
        if mutation == "uncovered_norm":
            _put(case, "n2", "norm", ["p2", "a1"])
            refs.append("n2")
        _update(case, "old", refs=refs)
        review = engine.review_item(case, "old", "reject", "Synthetic rejection", "agent:negative-reviewer")
        args.update(expected_version=2, expected_review_seq=review["seq"])
    elif mutation == "source_dependency":
        _update(case, "new", refs=["old", "p1", "n1", "pr", "e1"])
        args["replacements"] = {"new": 2}
    elif mutation == "no_numeric_evidence":
        _update(case, "new", refs=["p1", "n1", "pr"])
        args["replacements"] = {"new": 2}
    elif mutation in {"wrong_metric", "wrong_unit"}:
        data = {"metric": "synthetic_fraction", "unit": "fraction"}
        data["metric" if mutation == "wrong_metric" else "unit"] = "unrelated"
        _update(case, "new", data=data)
        args["replacements"] = {"new": 2}
    elif mutation == "replacement_rejected":
        engine.review_item(case, "new", "reject", "Synthetic rejection", "agent:negative-reviewer")
    else:
        engine.challenge(case, "new", "e1", "Synthetic contradiction", "agent:critic")
    _blocked(case, args)


def test_problem_and_norm_coverage_is_union_of_replacements(tmp_path, monkeypatch):
    case, args, _ = _case(tmp_path, monkeypatch)
    _put(case, "p2", "problem")
    _put(case, "a2", "actor", ["p2"])
    _put(case, "n2", "norm", ["p2", "a2"])
    _put(case, "q2", "question", ["p2"])
    _put(case, "h2", "hypothesis", ["q2"])
    _put(case, "pr2", "protocol", ["q2", "h2"], {
        "population": "synthetic", "method": "fixture", "comparison": "fixture", "uncertainty": "fixture",
    })
    _put(case, "e2", "evidence", ["pr2"], engine.get_state(case)["items"]["e1"]["data"])
    _put(case, "new2", "indicator", ["p2", "n2", "pr2", "e2"], {
        "metric": "synthetic_fraction", "unit": "fraction",
    })
    _update(case, "old", refs=["p1", "n1", "pr", "p2", "n2"])
    review = engine.review_item(case, "old", "reject", "Synthetic rejection", "agent:negative-reviewer")
    args.update(expected_version=2, expected_review_seq=review["seq"])
    _blocked(case, args)
    engine.retire_indicator(**(args | {"replacements": {"new": 1, "new2": 1}}))
    assert engine.get_state(case)["items"]["old"]["retired"]


@pytest.mark.parametrize("mutation", [
    "replacement_version", "source_version", "replacement_reject", "source_review",
    "replacement_challenge", "source_challenge", "consumer", "evidence_version",
])
def test_retirement_dynamically_invalidates_without_hiding_history(tmp_path, monkeypatch, mutation):
    case, args, _ = _case(tmp_path, monkeypatch, accepted=True)
    retirement = engine.retire_indicator(**args)
    _accept(case, "study")
    snapshot = engine.gate(case, "study")["snapshot"]
    if mutation in {"replacement_version", "source_version", "evidence_version"}:
        _update(case, {"replacement_version": "new", "source_version": "old", "evidence_version": "e1"}[mutation])
    elif mutation in {"replacement_reject", "source_review"}:
        engine.review_item(case, "new" if mutation == "replacement_reject" else "old", "reject",
                           "A later synthetic negative review", "agent:negative-reviewer")
    elif mutation in {"replacement_challenge", "source_challenge"}:
        engine.challenge(case, "new" if mutation == "replacement_challenge" else "old", "e1",
                         "Synthetic contradiction", "agent:critic")
    else:
        _put(case, "consumer", "synthesis", ["old"])
    old = engine.get_state(case)["items"]["old"]
    assert not old["retired"] and old["retirement_issues"]
    assert old["retirement_history"][0]["seq"] == retirement["seq"]
    status = engine.gate(case, "study")
    assert not status["accepted"]
    assert status["snapshot"] != snapshot
    if mutation == "source_version":
        # A new source revision can repair its rejection; retirement must not
        # manufacture an issue or revive the earlier phase acceptance.
        assert old["retirement_status"] == "superseded"
        assert old["issues"] == [] and status["ready"]
    else:
        assert not status["ready"]
        assert any("old" in blocker for blocker in status["blockers"])


def test_new_declaration_after_invalidation_requires_new_review_and_advance(tmp_path, monkeypatch):
    case, args, _ = _case(tmp_path, monkeypatch, accepted=True)
    first = engine.retire_indicator(**args)
    _, old_marker = _accept(case, "study")
    _update(case, "new")
    assert not engine.get_state(case)["items"]["old"]["retired"]
    second = engine.retire_indicator(**(args | {"replacements": {"new": 2}}))
    status = engine.gate(case, "study")
    assert status["ready"] and not status["reviewed"] and not status["accepted"]
    before = (case / "organon.json").read_bytes()
    with pytest.raises(engine.MethodError, match="accepted review"):
        engine.advance(case, "study", "agent:lead")
    assert (case / "organon.json").read_bytes() == before
    new_review, new_marker = _accept(case, "study")
    assert new_marker["seq"] > old_marker["seq"] and new_review["seq"] > second["seq"]
    history = engine.get_state(case)["indicator_retirement_history"]
    assert [entry["seq"] for entry in history] == [first["seq"], second["seq"]]
    assert history[0]["effective"] is False and history[1]["effective"] is True


def test_recorded_retirement_cannot_be_a_replacement_even_after_invalidation(tmp_path, monkeypatch):
    case, args, _ = _case(tmp_path, monkeypatch)
    _update(case, "old", refs=["p1", "n1", "pr", "e1"],
            data={"metric": "synthetic_fraction", "unit": "fraction"})
    first_review = engine.review_item(case, "old", "reject", "Synthetic rejection", "agent:negative-reviewer")
    args.update(expected_version=2, expected_review_seq=first_review["seq"])
    engine.retire_indicator(**args)
    _put(case, "old2", "indicator", ["p1", "n1", "pr"], {"metric": "legacy_pair", "unit": "fraction"})
    review = engine.review_item(case, "old2", "reject", "Synthetic rejection", "agent:negative-reviewer")
    _blocked(case, args, id="old2", replacements={"old": 2}, expected_version=1,
             expected_review_seq=review["seq"])
    engine.review_item(case, "old", "accept", "Synthetic acceptance invalidates retirement", "agent:negative-reviewer")
    old = engine.get_state(case)["items"]["old"]
    assert old["issues"] == [] and not old["retired"]
    _blocked(case, args, match="retirement declared on its current version", id="old2",
             replacements={"old": 2}, expected_version=1, expected_review_seq=review["seq"])


@pytest.mark.parametrize("archive_change", ["altered", "missing"])
def test_archive_failure_keeps_replay_readable_and_reopens_retirement(tmp_path, monkeypatch, archive_change):
    case, args, _ = _case(tmp_path, monkeypatch, signed=True, accepted=True, archive=True)
    engine.retire_indicator(**args)
    content = (case / "reading.json").read_bytes()
    before = (case / "organon.json").read_bytes()
    previous = engine.get_state(case)
    if archive_change == "altered":
        (case / "reading.json").write_bytes(content + b"\n")
    else:
        (case / "reading.json").unlink()
    state = engine.get_state(case)
    assert state["indicator_retirement_history"][0]["effective"] is False
    assert not state["items"]["old"]["retired"]
    assert state["items"]["e1"]["issues"]
    assert engine.trace(case, "old")["item"]["retirement_history"]
    assert not engine.gate(case, "study")["ready"]
    assert (case / "organon.json").read_bytes() == before
    (case / "reading.json").write_bytes(content)
    assert engine.get_state(case) == previous
    assert (case / "organon.json").read_bytes() == before


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(extra=True), lambda p: p.pop("reason"),
    lambda p: p.update(version=True), lambda p: p.update(review_seq=0),
    lambda p: p.update(replacements={"new": True}), lambda p: p.update(replacements={}),
    lambda p: p.update(replacements={"new": 2}), lambda p: p.update(replacements={"n1": 1}),
    lambda p: p.update(id="n1"), lambda p: p.update(reason=" trailing "),
])
def test_reducer_rejects_forged_retirement_schema_and_guards(tmp_path, monkeypatch, mutate):
    case, args, _ = _case(tmp_path, monkeypatch)
    payload = {"id": "old", "version": 1, "replacements": {"new": 1},
               "review_seq": args["expected_review_seq"], "reason": "Synthetic retirement"}
    mutate(payload)
    engine.append_event(case, "indicator_retire", payload, "agent:forger",
                        expected_seq=len(read_project(case)["events"]))
    read_project(case)  # Valid hash chain does not make the semantic event valid.
    with pytest.raises(engine.MethodError):
        engine.get_state(case)


def test_reducer_rejects_forged_retirement_over_consumer(tmp_path, monkeypatch):
    case, args, _ = _case(tmp_path, monkeypatch)
    _put(case, "consumer", "synthesis", ["old"])
    payload = {"id": "old", "version": 1, "replacements": {"new": 1},
               "review_seq": args["expected_review_seq"], "reason": "Synthetic retirement"}
    engine.append_event(case, "indicator_retire", payload, "agent:forger",
                        expected_seq=len(read_project(case)["events"]))
    with pytest.raises(engine.MethodError, match="consumers"):
        engine.get_state(case)


def test_retirement_never_counts_itself_or_changes_kind(tmp_path, monkeypatch):
    case, args, _ = _case(tmp_path, monkeypatch, accepted=True)
    engine.retire_indicator(**args)
    assert engine.gate(case, "study")["ready"]
    engine.review_item(case, "new", "reject", "Synthetic replacement rejection", "agent:negative-reviewer")
    assert "needs 1 valid indicator; has 0" in engine.gate(case, "study")["blockers"]
    before = (case / "organon.json").read_bytes()
    with pytest.raises(engine.MethodError, match="kind cannot change"):
        _put(case, "old", "synthesis", ["new"])
    assert (case / "organon.json").read_bytes() == before


def test_dependency_cycle_and_source_dependent_replacement_cannot_retire(tmp_path, monkeypatch):
    case, args, _ = _case(tmp_path, monkeypatch)
    _put(case, "bridge", "synthesis", ["old"])
    _update(case, "new", refs=["p1", "n1", "pr", "e1", "bridge"])
    before = (case / "organon.json").read_bytes()
    with pytest.raises(engine.MethodError, match="dependency cycle"):
        _update(case, "old", refs=["p1", "n1", "pr", "new"])
    assert (case / "organon.json").read_bytes() == before
    _blocked(case, args, replacements={"new": 2})


def test_specification_omits_only_effective_retirements(tmp_path, monkeypatch):
    case, args, _ = _case(tmp_path, monkeypatch)
    state = engine._project(case)
    blockers = engine._phase_blockers(state, "specify", True, engine._flags(state))
    assert "old lacks a path to evidence before specification" in blockers
    engine.retire_indicator(**args)
    state = engine._project(case)
    assert not any(b.startswith("old ") for b in engine._phase_blockers(state, "specify", True, engine._flags(state)))
    _update(case, "new")
    state = engine._project(case)
    assert "old lacks a path to evidence before specification" in engine._phase_blockers(state, "specify", True, engine._flags(state))


def test_no_retirement_snapshot_uses_legacy_payload(tmp_path, monkeypatch):
    case, _, _ = _case(tmp_path, monkeypatch, accepted=True)
    state = engine._project(case)
    flags = engine._flags(state)
    phases = engine._phase_statuses(state)
    ids = {id for id, item in state["items"].items() if KIND_TO_PHASE[item["kind"]] == "study"}
    relevant = set().union(*(engine._ancestors(state["items"], id) for id in ids))
    reviews = sorted((id, review["seq"], review["verdict"]) for id in relevant
                     if (review := state["item_reviews"].get((id, state["items"][id]["version"]))))
    legacy = {"phase": "study", "previous_marker": phases["critique"]["advance_seq"], "challenges": [],
              "items": sorted((id, state["items"][id]["version"], flags[id]["stale"],
                               flags[id]["contested"], flags[id]["issues"]) for id in ids)}
    if reviews:
        legacy["item_reviews"] = reviews
    assert phases["study"]["snapshot"] == engine._hash(legacy)


def test_signed_negative_review_must_be_independent_of_historical_authors(tmp_path, monkeypatch):
    case, args, _ = _case(tmp_path, monkeypatch, signed=True)
    _update(case, "old", actor="agent:new-author")
    review = engine.review_item(case, "old", "reject", "Synthetic rejection by historical author", "agent:author")
    args.update(expected_version=2, expected_review_seq=review["seq"])
    _blocked(case, args)
    independent = engine.review_item(case, "old", "reject", "Synthetic independent rejection", "agent:negative-reviewer")
    args["expected_review_seq"] = independent["seq"]
    engine.retire_indicator(**args)
    assert engine.get_state(case)["items"]["old"]["retired"]


def test_all_signed_retirement_authors_cannot_accept_study(tmp_path, monkeypatch):
    case, args, keys = _case(tmp_path, monkeypatch, signed=True, accepted=True)
    first = engine.retire_indicator(**args)
    assert engine.gate(case, "study")["ready"]
    before = (case / "organon.json").read_bytes()
    with pytest.raises(engine.MethodError, match="independent"):
        engine.phase_review_challenge(case, "study", "accept", "Synthetic review", "agent:retirer")
    assert (case / "organon.json").read_bytes() == before
    _accept(case, "study", keys)
    _update(case, "new")
    second = engine.retire_indicator(**(args | {"replacements": {"new": 2}, "actor": "agent:other-reviewer"}))
    authors = engine._phase_authors(engine._project(case), "study")
    assert {first["actor"], second["actor"]} <= authors
    for actor in (first["actor"], second["actor"]):
        with pytest.raises(engine.MethodError, match="independent"):
            engine.phase_review_challenge(case, "study", "accept", "Synthetic review", actor)
    _accept(case, "study", keys)
