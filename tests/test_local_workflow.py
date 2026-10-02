"""Local workflow mechanics: labeled test data, with a measured external test.

The reused synthetic manifest is test data only. These tests establish gates
and persistence, never a pilot, human identity, scientific finding or field impact.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from specorganon import approval, engine
from specorganon.ledger import LedgerError, read_project
from specorganon.runner import ManifestError, describe_task, next_task, run_manifest
from specorganon.workflow import PHASES


OWNER = "human:test-owner"
AUTHOR = "agent:test-author"
REVIEWER = "agent:test-reviewer"
MANIFEST = Path(__file__).resolve().parents[1] / "workflows" / "synthetic_full.json"


@pytest.fixture(autouse=True)
def isolate_operator_configuration(monkeypatch):
    for name in ("ORGANON_APPROVERS_FILE", "ORGANON_ALLOW_FIXTURES",
                 "ORGANON_LEDGER_ANCHORS_FILE", "ORGANON_FIELD_ASSESSORS_FILE"):
        monkeypatch.delenv(name, raising=False)


def _receipt_data(argv=None):
    argv = argv or [sys.executable, "-c", "assert sum(range(5)) == 10; print(10)"]
    process = subprocess.run(argv, capture_output=True, timeout=10, check=False)
    data = {
        "passed": process.returncode == 0, "argv": argv, "command": shlex.join(argv),
        "receipt": {
            "argv": argv, "exit_code": process.returncode, "timed_out": False,
            "stdout_sha256": hashlib.sha256(process.stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(process.stderr).hexdigest(),
        },
    }
    data["receipt"]["result_sha256"] = engine.local_test_result_sha256(data)
    return data


def _put(case, id, kind, refs=(), data=None, text=None, actor=AUTHOR):
    return engine.put_item(case, id, kind, text or f"Test data: {id}", list(refs), data or {}, actor)


def _accept(case, phase):
    status = engine.gate(case, phase)
    assert status["ready"], status["blockers"]
    review = engine.review_phase(case, phase, "accept", "Review of labeled test data", REVIEWER)
    advance = engine.advance(case, phase, AUTHOR)
    status = engine.gate(case, phase)
    assert status["accepted"] and status["independent_review"]
    assert status["review_provenance"] == "local_declared"
    assert not status["review_signature_verified"] and not status["review_identity_authenticated"]
    return review, advance


def _complete(case, *, stop_at=None, approve_norms=True, scope="technical"):
    """Adapt the explicitly synthetic test manifest; measure the real test process."""
    engine.create_case(case, "Labeled local workflow test data", "test data", OWNER,
                       approval_policy="local")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for step in manifest["steps"]:
        if step["op"] == "advance":
            phase = step["phase"]
            if phase == stop_at:
                return
            if phase in {"critique", "specify"}:
                if not approve_norms:
                    return
                target = "n1" if phase == "critique" else "d1"
                engine.approve(case, target, "Explicit owner approval of test data", OWNER)
            _accept(case, phase)
            continue
        data, refs = copy.deepcopy(step["data"]), list(step["refs"])
        if step["id"] == "e0":
            data.update(metric_key="count", scope="predeclared test data", unit="count", value=10)
        elif step["kind"] == "criterion":
            data["threshold"] = {"operator": ">=", "statistic": "estimate", "value": 0}
        elif step["kind"] == "test":
            data = _receipt_data()
        elif step["kind"] == "baseline":
            data.update(origin=scope, metric="count", unit="count", value=0)
        elif step["kind"] == "result":
            data.update(origin=scope, effect={"metric": "count", "unit": "count",
                                             "estimate": 10, "interval": [10, 10]})
            refs.append("t1")
        elif step["kind"] == "assessment":
            data.update(verdict="cumplido", claim_scope=scope)
        _put(case, step["id"], step["kind"], refs, data, step["text"])


def _frame(case, first_actor=AUTHOR):
    engine.create_case(case, "Local test frame", "test data", OWNER, approval_policy="local")
    _put(case, "p1", "problem", actor=first_actor)
    _put(case, "a1", "actor", ["p1"], actor=first_actor)
    _put(case, "b1", "boundary", ["p1"], actor=first_actor)


def _rewrite_project(case, **changes):
    ledger = read_project(case)
    ledger["project"].update(changes)
    (case / "organon.json").write_text(json.dumps(ledger), encoding="utf-8")


def test_local_policy_is_explicit_and_normalizes_test_gate(tmp_path):
    case = tmp_path / "case"
    state = engine.create_case(case, "Local", "test data", OWNER, approval_policy="local")
    assert state["project"]["test_gate_policy"] == "local_report"
    assert state["approval_trust"] == state["phase_review_trust"] == "local_declared"
    assert state["test_execution_trust"] == "local_declared"
    assert not state["approval_identity_authenticated"]
    signed = engine.create_case(tmp_path / "signed", "Signed", "test data", OWNER)
    assert signed["project"]["approval_policy"] == "signed"
    assert signed["approval_trust"] == "unavailable"


@pytest.mark.parametrize("actor", [AUTHOR, "human:fixture", "human:", " human:owner", "human: owner", "human:owner "])
def test_local_requires_normalized_declared_human_owner(tmp_path, actor):
    with pytest.raises(LedgerError, match="human:<owner>"):
        engine.create_case(tmp_path / "case", "Local", "test data", actor, approval_policy="local")
    assert not (tmp_path / "case" / "organon.json").exists()


@pytest.mark.parametrize("approval_policy,test_gate_policy", [
    ("local", "signed_observed"), ("signed", "local_report"), ("fixture", "local_report"),
])
def test_local_and_signed_test_gate_policies_cannot_mix(tmp_path, approval_policy, test_gate_policy):
    with pytest.raises(LedgerError):
        engine.create_case(tmp_path / "case", "Test", "test data", OWNER,
                           approval_policy=approval_policy, test_gate_policy=test_gate_policy)


def test_normative_gate_requires_owner_reason_and_rejects_signatures(tmp_path):
    case = tmp_path / "case"
    _complete(case, stop_at="critique")
    assert not engine.gate(case, "critique")["ready"]
    assert next_task(case)["action"] == "human_approval"
    unchanged = (case / "organon.json").read_bytes()
    for actor, reason, signature in ((AUTHOR, "Reason", None), ("human:other", "Reason", None),
                                     ("human:fixture", "Reason", None), (OWNER, " ", None),
                                     (OWNER, "Reason", "fake-signed-proof")):
        with pytest.raises(engine.MethodError):
            engine.approve(case, "n1", reason, actor, signature)
    assert (case / "organon.json").read_bytes() == unchanged
    event = engine.approve(case, "n1", "Explicit test-data mandate", OWNER)
    assert event["payload"]["provenance"] == "local_declared"
    assert "signature" not in event["payload"]
    item = engine.get_state(case)["items"]["n1"]
    assert item["approved"] and item["approval_status"] == "local_declared"
    assert engine.gate(case, "critique")["ready"]
    _accept(case, "critique")


def test_historical_author_cannot_launder_authorship_by_republication(tmp_path):
    case = tmp_path / "case"
    _frame(case, first_actor=REVIEWER)
    for id, kind, refs in (("p1", "problem", []), ("a1", "actor", ["p1"]), ("b1", "boundary", ["p1"])):
        _put(case, id, kind, refs)
    with pytest.raises(engine.MethodError, match="historical phase authors"):
        engine.review_phase(case, "frame", "accept", "Attempted author wash", REVIEWER)
    status = engine.gate(case, "frame")
    forged = engine.append_event(case, "phase_review", {
        "phase": "frame", "snapshot": status["snapshot"], "verdict": "accept",
        "reason": "Forged independence", "independent": True, "provenance": "local_declared",
    }, REVIEWER)
    engine.append_event(case, "phase_advance", {
        "phase": "frame", "snapshot": status["snapshot"], "review_seq": forged["seq"],
    }, AUTHOR)
    assert not engine.gate(case, "frame")["reviewed"]
    assert not engine.gate(case, "frame")["accepted"]
    assert not engine.get_state(case)["phase_review_history"][-1]["independent"]
    engine.review_phase(case, "frame", "accept", "Distinct reviewer", "agent:independent")
    engine.advance(case, "frame", AUTHOR)
    assert engine.gate(case, "frame")["accepted"]


@pytest.mark.parametrize("scope", ["technical", "simulation"])
def test_all_nine_local_phases_persist_with_real_measured_test_receipt(tmp_path, scope):
    case = tmp_path / "case"
    _complete(case, scope=scope)
    state = engine.get_state(case)
    assert all(state["phases"][phase.id]["accepted"] for phase in PHASES)
    assert len(state["items"]) == 29
    assert len(state["phase_review_history"]) == 9
    assert next_task(case)["action"] == "complete"
    test = state["items"]["t1"]
    assert test["data"]["receipt"]["stdout_sha256"] == hashlib.sha256(b"10\n").hexdigest()
    assert test["test_execution_status"] == "local_reported_passed"
    assert not test["test_execution_signature_verified"]
    assert not test["test_execution_identity_authenticated"]
    assert state["items"]["ass1"]["data"]["claim_scope"] == scope
    code = "import json,sys; from specorganon.engine import get_state; print(json.dumps(get_state(sys.argv[1])))"
    restarted = subprocess.run([sys.executable, "-c", code, str(case)],
                               capture_output=True, text=True, check=True)
    assert json.loads(restarted.stdout) == json.loads(json.dumps(state))


def test_manifest_cannot_supply_local_approval_or_review(tmp_path):
    case = tmp_path / "case"
    engine.create_case(case, "Local manifest", "test data", OWNER, approval_policy="local")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    first = run_manifest(case, manifest, AUTHOR)
    assert first["status"] == "waiting" and first["reason"] == "independent_review_required"
    assert not engine.gate(case, "frame")["accepted"]
    _accept(case, "frame")
    second = run_manifest(case, manifest, AUTHOR)
    assert second["status"] == "waiting" and second["next"]["action"] == "human_approval"
    assert not engine.get_state(case)["items"]["n1"]["approved"]


def test_new_normative_approval_reopens_reviews_and_dependent_advances(tmp_path):
    case = tmp_path / "case"
    _complete(case)
    previous = engine.get_state(case)
    engine.approve(case, "n1", "New explicit record locator", OWNER)
    state = engine.get_state(case)
    assert state["phases"]["frame"] == previous["phases"]["frame"]
    assert state["phases"]["critique"]["ready"]
    assert state["phases"]["critique"]["snapshot"] != previous["phases"]["critique"]["snapshot"]
    assert not state["phases"]["critique"]["reviewed"]
    assert not state["phases"]["validate"]["accepted"]
    with pytest.raises(engine.MethodError, match="accepted review"):
        engine.advance(case, "critique", AUTHOR)
    for phase in PHASES[1:]:
        _accept(case, phase.id)
    assert engine.gate(case, "validate")["accepted"]


def test_revisions_and_rejected_item_reviews_invalidate_local_dependents(tmp_path):
    case = tmp_path / "case"
    _complete(case)
    engine.review_item(case, "req1", "reject", "Unsound test requirement", REVIEWER)
    assert not engine.gate(case, "specify")["accepted"]
    engine.review_item(case, "req1", "accept", "Corrected interpretation", REVIEWER)
    assert not engine.gate(case, "specify")["reviewed"]
    _accept(case, "specify")
    _accept(case, "build")
    _accept(case, "validate")
    item = engine.get_state(case)["items"]["e1"]
    _put(case, "e1", "evidence", item["deps"], item["data"], "New test evidence revision")
    state = engine.get_state(case)
    assert state["phases"]["study"]["accepted"]
    assert state["items"]["inf1"]["stale"] and state["items"]["req1"]["stale"]
    assert not state["phases"]["observe"]["accepted"]
    assert not state["phases"]["validate"]["accepted"]


@pytest.mark.parametrize("mutation", ["passed", "command", "argv", "exit_code", "timed_out", "stdout", "result", "signature", "receipt"])
def test_invalid_local_receipts_cannot_advance_or_keep_acceptance(tmp_path, mutation):
    case = tmp_path / "case"
    _complete(case)
    test = engine.get_state(case)["items"]["t1"]
    data = copy.deepcopy(test["data"])
    if mutation == "passed":
        data["passed"] = False
    elif mutation == "command":
        data["command"] = "incoherent command"
    elif mutation == "argv":
        data["receipt"]["argv"] = [sys.executable, "-c", "raise SystemExit(0)"]
    elif mutation == "exit_code":
        data["receipt"]["exit_code"] = 1
    elif mutation == "timed_out":
        data["receipt"]["timed_out"] = True
    elif mutation == "stdout":
        data["receipt"]["stdout_sha256"] = "bad hash"
    elif mutation == "result":
        data["receipt"]["result_sha256"] = "0" * 64
    elif mutation == "signature":
        data["signature"] = "signed-looking report"
    else:
        data.pop("receipt")
    _put(case, "t1", "test", test["deps"], data)
    state = engine.get_state(case)
    assert state["items"]["t1"]["issues"]
    assert not state["phases"]["build"]["ready"] and not state["phases"]["build"]["accepted"]
    assert not state["phases"]["validate"]["accepted"]
    with pytest.raises(engine.MethodError, match="cannot be accepted"):
        engine.review_phase(case, "build", "accept", "False success", REVIEWER)


def test_failed_real_external_execution_is_preserved_and_runner_requests_execution(tmp_path):
    case = tmp_path / "case"
    _complete(case)
    item = engine.get_state(case)["items"]["t1"]
    data = _receipt_data([sys.executable, "-c", "print('failure'); raise SystemExit(3)"])
    _put(case, "t1", "test", item["deps"], data)
    assert data["receipt"]["exit_code"] == 3 and data["passed"] is False
    assert next_task(case)["action"] == "execute_test"
    assert "local_declared" in next_task(case)["task"]
    assert not engine.gate(case, "build")["accepted"]
    test_events = [e for e in read_project(case)["events"] if e["kind"] == "item_put" and e["payload"]["id"] == "t1"]
    assert test_events[0]["payload"]["data"]["receipt"]["exit_code"] == 0
    assert test_events[-1]["payload"]["data"]["receipt"]["exit_code"] == 3


@pytest.mark.parametrize("kind,verdict", [("baseline", None), ("result", None),
                                          ("assessment", "cumplido"), ("assessment", "incumplido")])
def test_local_field_claims_block_even_with_other_valid_technical_assessment(tmp_path, kind, verdict):
    case = tmp_path / "case"
    _complete(case)
    source_id = {"baseline": "base1", "result": "res1", "assessment": "ass1"}[kind]
    item = engine.get_state(case)["items"][source_id]
    data = copy.deepcopy(item["data"])
    if kind == "assessment":
        data.update(claim_scope="field", verdict=verdict)
    else:
        data["origin"] = "field"
    _put(case, "field_item", kind, item["deps"], data)
    state = engine.get_state(case)
    assert state["items"]["field_item"]["issues"]
    assert any("local policy cannot substantiate" in blocker
               for blocker in state["phases"]["validate"]["blockers"])
    assert not state["phases"]["validate"]["accepted"]


@pytest.mark.parametrize("configuration", ["path", "uuid", "malformed", "unreadable", "bad_entry"])
def test_local_registry_conflicts_and_errors_revoke_all_effective_acceptance(tmp_path, monkeypatch, configuration):
    case = tmp_path / "case"
    _frame(case)
    _accept(case, "frame")
    project = read_project(case)["project"]
    registry = tmp_path / "registry.json"
    entry = {"path": str(case.resolve()), "project_sha256": approval.project_fingerprint(project), "approvers": {}}
    if configuration == "uuid":
        entry["path"] = str(tmp_path / "other-canonical-case")
    payload = {"schema": 2, "cases": {project["case_id"]: entry}}
    if configuration == "malformed":
        payload = {"schema": 1}
    elif configuration == "bad_entry":
        payload = {"schema": 2, "cases": {"unrelated": {"path": str(tmp_path / "other")}}}
    if configuration != "unreadable":
        registry.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(registry))
    unchanged = (case / "organon.json").read_bytes()
    state = engine.get_state(case)
    assert state["approval_trust"] == state["phase_review_trust"] == "unavailable"
    assert state["test_execution_trust"] == "unavailable"
    assert not state["phases"]["frame"]["accepted"] and not state["phases"]["frame"]["reviewed"]
    assert "local policy is unavailable" in state["phases"]["frame"]["blockers"][0]
    with pytest.raises(engine.MethodError):
        engine.review_phase(case, "frame", "accept", "Conflict", REVIEWER)
    with pytest.raises(engine.MethodError):
        engine.advance(case, "frame", AUTHOR)
    assert (case / "organon.json").read_bytes() == unchanged


def test_local_can_coexist_with_unrelated_valid_signed_registration(tmp_path, monkeypatch):
    case = tmp_path / "case"
    _frame(case)
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"schema": 2, "cases": {"other-case": {
        "path": str(tmp_path / "signed-case"), "project_sha256": "0" * 64, "approvers": {},
    }}}), encoding="utf-8")
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(registry))
    assert engine.get_state(case)["approval_trust"] == "local_declared"
    _accept(case, "frame")


def test_registered_signed_case_cannot_downgrade_to_local(tmp_path, monkeypatch):
    case = tmp_path / "case"
    engine.create_case(case, "Registered signed", "test data", OWNER)
    project = read_project(case)["project"]
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"schema": 2, "cases": {project["case_id"]: {
        "path": str(case.resolve()), "project_sha256": approval.project_fingerprint(project), "approvers": {},
    }}}), encoding="utf-8")
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(registry))
    _rewrite_project(case, approval_policy="local", test_gate_policy="local_report")
    state = engine.get_state(case)
    assert state["project"]["approval_policy"] == "local"
    assert state["approval_trust"] == "unavailable"
    assert not any(status["ready"] or status["accepted"] for status in state["phases"].values())


def test_local_signatures_and_signed_challenges_are_rejected(tmp_path):
    case = tmp_path / "case"
    _frame(case)
    unchanged = (case / "organon.json").read_bytes()
    with pytest.raises(engine.MethodError, match="signature"):
        engine.review_phase(case, "frame", "accept", "Fake proof", REVIEWER, "fake-signature")
    with pytest.raises(engine.MethodError, match="challenges"):
        engine.phase_review_challenge(case, "frame", "accept", "Reason", REVIEWER)
    assert (case / "organon.json").read_bytes() == unchanged
    status = engine.gate(case, "frame")
    event = engine.append_event(case, "phase_review", {
        "phase": "frame", "snapshot": status["snapshot"], "verdict": "accept", "reason": "Fake proof",
        "independent": True, "provenance": "local_declared", "signature": "fake-signature",
    }, REVIEWER)
    engine.append_event(case, "phase_advance", {
        "phase": "frame", "snapshot": status["snapshot"], "review_seq": event["seq"],
    }, AUTHOR)
    status = engine.gate(case, "frame")
    assert not status["reviewed"] and not status["accepted"]
    assert status["review_provenance"] == "local_unavailable"


def test_describe_task_uses_supplied_snapshot_when_external_trust_changes(tmp_path, monkeypatch):
    case = tmp_path / "case"
    _frame(case)
    state = engine.get_state(case)
    original = copy.deepcopy(state)
    expected = next_task(case, {"reviewer": " agent:selected "})
    registry = tmp_path / "malformed-registry.json"
    registry.write_text('{"schema": 1}', encoding="utf-8")
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(registry))
    live = next_task(case)
    assert live["revision"] == state["revision"]
    assert live["action"] == "repair_artifacts"
    assert live["phase_review_trust"] == "unavailable"

    def forbid_read(*args, **kwargs):
        pytest.fail("describe_task must not read live case or trust configuration")

    monkeypatch.setattr(engine, "get_state", forbid_read)
    task = describe_task(state, {"reviewer": " agent:selected "})
    assert task == expected
    assert task["action"] == "review_phase" and task["actor"] == "agent:selected"
    assert task["phase_review_trust"] == "local_declared"
    assert state == original


def test_next_task_and_describe_task_validate_roles_before_any_live_read(tmp_path, monkeypatch):
    def forbid_read(*args, **kwargs):
        pytest.fail("invalid roles must fail before get_state")

    monkeypatch.setattr(engine, "get_state", forbid_read)
    with pytest.raises(ManifestError, match="roles must map"):
        next_task(tmp_path / "missing-case", {"unknown-role": "agent:invalid"})
    with pytest.raises(ManifestError, match="roles must map"):
        describe_task({}, {"unknown-role": "agent:invalid"})
