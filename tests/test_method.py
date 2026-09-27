"""Behavioral tests using synthetic inputs and committed ledgers, not field observations."""

from pathlib import Path

import pytest

from specorganon import engine
from specorganon.ledger import read_project
from specorganon.runner import next_task
from specorganon.workflow import PHASES


pytestmark = pytest.mark.usefixtures("enable_fixture_policy")


def _put(path, id, kind, refs=(), data=None, text=None):
    return engine.put_item(path, id, kind, text or id, list(refs), data or {}, "agent:analyst")


def _accept(path, phase):
    status = engine.gate(path, phase)
    assert status["ready"], status["blockers"]
    engine.review_phase(path, phase, "accept", "fixture review", "agent:reviewer")
    engine.advance(path, phase, "agent:lead")
    assert engine.gate(path, phase)["accepted"]


def _synthetic_measured_outcome(metric, unit, value=0):
    return {
        "status": "measured", "source": "invented fixture", "date": "2026-09-27",
        "measurements": [{"metric": metric, "unit": unit, "value": value, "sample_size": 12}],
    }


def _synthetic_measured_outcomes():
    return {
        "adverse_effects": _synthetic_measured_outcome("adverse events", "count"),
        "cost": _synthetic_measured_outcome("cost", "synthetic units", 2),
    }


def _complete_synthetic_case(path, *, study_problem="p1", norm_refs=("p1", "a1"),
                             e0_refs=("pr1",), e0_origin="simulated", e0_metric_key=None, e0_unit=None,
                             e1_refs=("pr1",), e1_origin="simulated", e1_value=10,
                             e1_metric_key="count", e1_unit="count",
                             inf_refs=("e1", "h1"), sibling_protocol=False, sibling_problem="p1",
                             indicator_protocol_ref=None, indicator_extra_metric=None, indicator_extra_unit=None,
                             indicator_extra_via_inference=False,
                             disjoint_indicator=False, criterion_indicator="i1",
                             stop_before_observe=False, stop_before_specify=False):
    assert not disjoint_indicator or (study_problem == "p1" and not sibling_protocol)
    engine.create_case(path, "Synthetic control", "test", "human:fixture", approval_policy="fixture")
    _put(path, "p1", "problem")
    if disjoint_indicator:
        _put(path, "p2", "problem")
    if study_problem != "p1":
        _put(path, study_problem, "problem")
    if sibling_protocol and sibling_problem not in {"p1", study_problem}:
        _put(path, sibling_problem, "problem")
    _put(path, "a1", "actor", ["p1"])
    if disjoint_indicator:
        _put(path, "a2", "actor", ["p2"])
    _put(path, "b1", "boundary", ["p1"])
    _accept(path, "frame")

    _put(path, "c1", "concept", ["p1"])
    _put(path, "s1", "assumption", ["p1"])
    _put(path, "f1", "frame_option", ["p1"], text="one framing")
    _put(path, "f2", "frame_option", ["p1"], text="another framing")
    _put(path, "n1", "norm", norm_refs)
    if disjoint_indicator:
        _put(path, "n2", "norm", ["p2", "a2"])
    assert not engine.gate(path, "critique")["ready"]
    engine.approve(path, "n1", "synthetic human attestation for mechanics test", "human:fixture")
    if disjoint_indicator:
        engine.approve(path, "n2", "synthetic human attestation for mechanics test", "human:fixture")
    _accept(path, "critique")

    _put(path, "q1", "question", [study_problem])
    _put(path, "h1", "hypothesis", ["q1"])
    _put(path, "pr1", "protocol", ["q1", "h1"], {"population": "synthetic", "method": "enumeration", "comparison": "baseline", "uncertainty": "none in fixture"})
    if sibling_protocol:
        _put(path, "q2", "question", [sibling_problem])
        _put(path, "h2", "hypothesis", ["q2"])
        _put(path, "pr2", "protocol", ["q2", "h2"], {"population": "synthetic", "method": "enumeration", "comparison": "baseline", "uncertainty": "none in fixture"})
    if disjoint_indicator:
        _put(path, "q2", "question", ["p2"])
        _put(path, "h2", "hypothesis", ["q2"])
        _put(path, "pr2", "protocol", ["q2", "h2"], {"population": "synthetic", "method": "enumeration", "comparison": "baseline", "uncertainty": "none in fixture"})
        _put(path, "e2", "evidence", ["pr2"], {"origin": "simulated", "source": "synthetic fixture", "date": "2026-09-26", "locator": "second problem", "metric_key": "count", "scope": "second problem", "unit": "count", "value": 10})
        _put(path, "i2", "indicator", ["p2", "n2", "e2"], {"metric": "count", "unit": "count"})
    e0_data = {"origin": e0_origin, "source": "synthetic fixture", "date": "2026-09-26",
               "locator": "predeclared context"}
    if e0_metric_key is not None:
        e0_data["metric_key"] = e0_metric_key
    if e0_unit is not None:
        e0_data["unit"] = e0_unit
    _put(path, "e0", "evidence", e0_refs, e0_data)
    indicator_refs = ["p1", "n1", "e0"]
    if indicator_protocol_ref is not None:
        indicator_refs.append(indicator_protocol_ref)
    if indicator_extra_metric is not None:
        extra_data = {"origin": "simulated", "source": "synthetic fixture", "date": "2026-09-26",
                      "locator": "extra context", "metric_key": indicator_extra_metric}
        if indicator_extra_unit is not None:
            extra_data["unit"] = indicator_extra_unit
        _put(path, "ex", "evidence", ["pr1"], extra_data)
        extra_ref = "ex"
        if indicator_extra_via_inference:
            _put(path, "ix", "inference", ["ex", "h1"])
            extra_ref = "ix"
        indicator_refs.append(extra_ref)
    _put(path, "i1", "indicator", indicator_refs, {"metric": "count", "unit": "count"})
    _accept(path, "study")

    _put(path, "e1", "evidence", e1_refs, {"origin": e1_origin, "source": "synthetic fixture", "date": "2026-09-26", "locator": "test_method.py", "metric_key": e1_metric_key, "scope": "fixture", "unit": e1_unit, "value": e1_value})
    _put(path, "inf1", "inference", inf_refs)
    if stop_before_observe:
        return
    _accept(path, "observe")

    _put(path, "syn1", "synthesis", ["inf1", "e1"])
    _put(path, "u1", "uncertainty", ["syn1"])
    _accept(path, "explain")

    _put(path, "o1", "option", ["syn1", "n1"])
    _put(path, "o2", "option", ["syn1", "n1"])
    _put(path, "cmp1", "comparison", ["o1", "o2"])
    _put(path, "r1", "risk", ["o1"])
    _accept(path, "compare")

    _put(path, "d1", "decision", ["cmp1", "n1", "e1"])
    _put(path, "req1", "requirement", ["d1"])
    _put(path, "crit1", "criterion", ["req1", criterion_indicator],
         {"metric": "count", "threshold": 0, "reject": "negative count"})
    if stop_before_specify:
        return
    assert not engine.gate(path, "specify")["ready"]
    engine.approve(path, "d1", "synthetic human attestation for mechanics test", "human:fixture")
    _accept(path, "specify")

    _put(path, "impl1", "implementation", ["req1"])
    _put(path, "t1", "test", ["impl1", "crit1"], {"passed": True, "command": "synthetic fixture; no external command run"})
    _accept(path, "build")

    _put(path, "base1", "baseline", ["crit1"], {"origin": "simulation", "source": "synthetic fixture", "date": "2026-09-26"})
    _put(path, "res1", "result", ["base1", "crit1"], {"origin": "simulation", "source": "synthetic fixture", "date": "2026-09-26"})
    _put(path, "ass1", "assessment", ["res1", "r1"], {"verdict": "no_demostrado", "claim_scope": "field", "uncertainty": "synthetic only", "adverse_effects": "not measured", "cost": "not measured"})
    _accept(path, "validate")


def test_full_synthetic_workflow_and_late_evidence_revision(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    assert all(engine.gate(path, phase.id)["accepted"] for phase in PHASES)
    _put(path, "e1", "evidence", ["pr1"], {"origin": "simulated", "source": "synthetic fixture", "date": "2026-09-26", "locator": "test_method.py", "metric_key": "count", "scope": "fixture", "unit": "count", "value": 11})
    state = engine.get_state(path)
    assert state["phases"]["study"]["accepted"]
    assert not state["phases"]["observe"]["accepted"]
    assert state["items"]["inf1"]["stale"]
    assert state["items"]["req1"]["stale"]
    assert not state["phases"]["validate"]["accepted"]
    assert "e1" in {item["id"] for item in engine.trace(path, "req1")["ancestors"]}


@pytest.mark.parametrize("case_name", ("mango", "citibike", "synthetic_multiagent"))
def test_existing_ledgers_without_item_reviews_keep_accepted_frame(case_name):
    path = Path(__file__).resolve().parents[1] / "cases" / case_name
    events = read_project(path)["events"]
    assert not any(event["kind"] == "item_review" for event in events)
    recorded_review = next(event for event in reversed(events)
                           if event["kind"] == "phase_review" and event["payload"]["phase"] == "frame")

    frame = engine.gate(path, "frame")
    assert frame["snapshot"] == recorded_review["payload"]["snapshot"]
    assert frame["ready"] and frame["reviewed"] and frame["accepted"]


def test_committed_no_demostrado_ledger_remains_accepted_without_result_test_link():
    path = Path(__file__).resolve().parents[1] / "cases" / "synthetic_multiagent"
    state = engine.get_state(path)
    assert state["items"]["ass1"]["data"]["verdict"] == "no_demostrado"
    assert not any(item["kind"] == "test" for item in engine.trace(path, "res1")["ancestors"])
    assert engine.gate(path, "validate")["ready"]
    assert state["phases"]["validate"]["accepted"]


def test_committed_mango_published_range_remains_valid_context():
    path = Path(__file__).resolve().parents[1] / "cases" / "mango"
    state = engine.get_state(path)
    chamber = state["items"]["e_pulp_chamber"]
    assert chamber["data"]["unit"] == "rango porcentaje"
    assert chamber["data"]["value"] == "3-6"
    assert not chamber["issues"]
    assert not any("e_pulp_chamber: evidence metric value" in blocker
                   for blocker in state["phases"]["observe"]["blockers"])


def test_rejected_item_review_revokes_dependent_phases_until_fresh_advances(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    before = engine.get_state(path)

    with pytest.raises(engine.MethodError, match="reviewer must differ"):
        engine.review_item(path, "req1", "reject", "author cannot reject own work", "agent:analyst")
    engine.review_item(path, "req1", "reject", "requirement is unsound", "agent:reviewer")
    state = engine.get_state(path)
    assert any("latest item review rejected" in issue for issue in state["items"]["req1"]["issues"])
    assert any("rejected item review of req1" in issue for issue in state["items"]["crit1"]["issues"])
    assert any("rejected item review of req1" in issue for issue in state["items"]["impl1"]["issues"])
    assert state["phases"]["compare"]["accepted"]
    assert state["phases"]["specify"]["snapshot"] != before["phases"]["specify"]["snapshot"]
    for phase in ("specify", "build", "validate"):
        assert not state["phases"][phase]["ready"]
        assert not state["phases"][phase]["accepted"]
    task = next_task(path)
    assert (task["status"], task["phase"], task["action"]) == ("pending", "specify", "repair_artifacts")
    with pytest.raises(engine.MethodError, match="phase cannot be accepted"):
        engine.review_phase(path, "specify", "accept", "premature review", "agent:reviewer")

    engine.review_item(path, "req1", "accept", "rechecked requirement", "agent:reviewer")
    state = engine.get_state(path)
    assert state["phases"]["specify"]["ready"]
    assert not state["phases"]["specify"]["accepted"]
    assert not any("rejected item review" in issue for issue in state["items"]["req1"]["issues"])
    assert next_task(path)["action"] == "review_phase"
    with pytest.raises(engine.MethodError, match="accepted review of its current snapshot"):
        engine.advance(path, "specify", "agent:lead")
    for phase in ("specify", "build", "validate"):
        _accept(path, phase)
    assert all(engine.gate(path, phase.id)["accepted"] for phase in PHASES)


def test_rejected_review_of_older_version_does_not_reject_revised_item(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    engine.review_item(path, "req1", "reject", "first version is unsound", "agent:reviewer")
    _put(path, "req1", "requirement", ["d1"], text="revised requirement")
    state = engine.get_state(path)
    assert state["items"]["req1"]["version"] == 2
    assert not any("rejected item review" in issue for issue in state["items"]["req1"]["issues"])
    assert state["items"]["crit1"]["stale"]

    for item_id in ("crit1", "impl1", "t1", "base1", "res1", "ass1"):
        item = engine.get_state(path)["items"][item_id]
        _put(path, item_id, item["kind"], item["deps"], item["data"], item["text"])
    assert engine.gate(path, "specify")["ready"]
    for phase in ("specify", "build", "validate"):
        _accept(path, phase)
    assert all(engine.gate(path, phase.id)["accepted"] for phase in PHASES)


def test_terminal_item_reacceptance_cannot_restore_old_phase_advance(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    original_snapshot = engine.gate(path, "frame")["snapshot"]
    engine.review_item(path, "b1", "reject", "boundary excludes an affected group", "agent:reviewer")
    assert not engine.gate(path, "frame")["accepted"]

    engine.review_item(path, "b1", "accept", "boundary rechecked", "agent:reviewer")
    status = engine.gate(path, "frame")
    assert status["ready"]
    assert not status["accepted"]
    assert status["snapshot"] != original_snapshot
    task = next_task(path)
    assert (task["phase"], task["action"]) == ("frame", "review_phase")


@pytest.mark.parametrize(("origin", "expected_blocker"), (
    ("simulated", "e1 must link a valid protocol"),
    ("published", "inf1 must link evidence to a valid protocol"),
))
def test_orphaned_observation_cannot_advance_workflow(tmp_path, origin, expected_blocker):
    path = tmp_path / "case"
    _complete_synthetic_case(path, e1_refs=(), e1_origin=origin, stop_before_observe=True)
    blockers = engine.gate(path, "observe")["blockers"]
    assert any(expected_blocker in blocker for blocker in blockers)
    with pytest.raises(engine.MethodError, match="phase cannot be accepted"):
        engine.review_phase(path, "observe", "accept", "orphaned fixture", "agent:reviewer")


def test_independent_published_evidence_can_be_interpreted_under_protocol(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path, study_problem="p2", sibling_protocol=True,
                             e0_refs=("pr2",), e1_refs=(), e1_origin="published", inf_refs=("e1", "pr2"))
    assert engine.get_state(path)["items"]["e1"]["deps"] == {}
    assert all(engine.gate(path, phase.id)["accepted"] for phase in PHASES)


def test_independent_published_indicator_evidence_can_use_explicit_protocol(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path, e0_refs=(), e0_origin="published", indicator_protocol_ref="pr1")
    evidence = engine.get_state(path)["items"]["e0"]
    assert evidence["deps"] == {}
    assert "metric_key" not in evidence["data"] and "unit" not in evidence["data"]
    assert all(engine.gate(path, phase.id)["accepted"] for phase in PHASES)


@pytest.mark.parametrize("e1_origin", ["simulated", "published"])
def test_inference_cannot_relabel_protocol_bound_evidence_with_sibling_protocol(tmp_path, e1_origin):
    path = tmp_path / "case"
    _complete_synthetic_case(path, study_problem="p2", sibling_protocol=True,
                             e1_origin=e1_origin, inf_refs=("e1", "pr2"), stop_before_observe=True)
    blockers = engine.gate(path, "observe")["blockers"]
    assert any("inf1 applies protocol-bound evidence to an unrelated protocol problem" in blocker
               for blocker in blockers)

    # Build the later branches without advancing them: a sibling protocol must
    # not make the same unsupported evidence look coherent at specification.
    _put(path, "syn1", "synthesis", ["inf1", "e1"])
    _put(path, "o1", "option", ["syn1", "n1"])
    _put(path, "o2", "option", ["syn1", "n1"])
    _put(path, "cmp1", "comparison", ["o1", "o2"])
    _put(path, "d1", "decision", ["cmp1", "n1", "e1"])
    _put(path, "req1", "requirement", ["d1"])
    _put(path, "crit1", "criterion", ["req1", "i1"], {"metric": "count", "threshold": 0, "reject": "negative count"})
    specification_blockers = engine.gate(path, "specify")["blockers"]
    assert any("req1 lacks a shared problem between norm and protocol-grounded evidence" in blocker
               for blocker in specification_blockers)


def test_protocol_needs_a_hypothesis_question_problem_chain(tmp_path):
    path = tmp_path / "case"
    engine.create_case(path, "Question lineage control", "test", "human:fixture", approval_policy="fixture")
    _put(path, "p1", "problem")
    _put(path, "a1", "actor", ["p1"])
    _put(path, "b1", "boundary", ["p1"])
    _accept(path, "frame")
    for id, kind, refs in (("c1", "concept", ("p1",)), ("s1", "assumption", ("p1",)),
                           ("f1", "frame_option", ("p1",)), ("f2", "frame_option", ("p1",)),
                           ("n1", "norm", ("p1", "a1"))):
        _put(path, id, kind, refs, text="second framing" if id == "f2" else id)
    engine.approve(path, "n1", "synthetic fixture approval", "human:fixture")
    _accept(path, "critique")
    _put(path, "q1", "question")
    _put(path, "h1", "hypothesis", ["q1"])
    _put(path, "pr1", "protocol", ["q1", "h1"], {
        "population": "synthetic", "method": "enumeration", "comparison": "baseline", "uncertainty": "fixture",
    })
    _put(path, "i1", "indicator", ["p1", "n1"], {"metric": "count", "unit": "count"})
    assert any("valid hypothesis → question → problem chain" in blocker
               for blocker in engine.gate(path, "study")["blockers"])


def test_specification_rejects_disjoint_evidence_and_norm_problem_lineages(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path, study_problem="p2", stop_before_specify=True)
    engine.approve(path, "d1", "synthetic fixture approval", "human:fixture")
    blockers = engine.gate(path, "specify")["blockers"]
    assert any("req1 lacks a shared problem between norm and protocol-grounded evidence" in blocker
               for blocker in blockers)
    assert any("crit1 lacks a shared problem between norm and protocol-grounded evidence" in blocker
               for blocker in blockers)


@pytest.mark.parametrize(("indicator_protocol", "ready"), (("pr2", False), ("pr1", True)))
def test_indicator_must_share_problem_with_its_normative_evidence(tmp_path, indicator_protocol, ready):
    path = tmp_path / "case"
    _complete_synthetic_case(path, sibling_protocol=True, sibling_problem="p2",
                             e0_refs=(indicator_protocol,), stop_before_specify=True)
    engine.approve(path, "d1", "synthetic fixture approval", "human:fixture")
    status = engine.gate(path, "specify")
    assert status["ready"] is ready
    indicator_blocker = "i1 lacks a shared problem between norm and protocol-grounded evidence"
    assert (indicator_blocker in status["blockers"]) is not ready
    assert not any("req1 lacks a shared problem" in blocker or "crit1 lacks a shared problem" in blocker
                   for blocker in status["blockers"])


@pytest.mark.parametrize("via_inference", [False, True])
@pytest.mark.parametrize(("extra_metric", "ready"), (("temperature", False), ("count", True)))
def test_indicator_support_problem_must_match_its_explicit_metric(tmp_path, extra_metric, ready, via_inference):
    path = tmp_path / "case"
    _complete_synthetic_case(path, sibling_protocol=True, sibling_problem="p2",
                             e0_refs=("pr2",), e0_metric_key="count",
                             indicator_extra_metric=extra_metric,
                             indicator_extra_via_inference=via_inference, stop_before_specify=True)
    engine.approve(path, "d1", "synthetic fixture approval", "human:fixture")
    status = engine.gate(path, "specify")
    assert status["ready"] is ready
    indicator_blocker = "i1 lacks a shared problem between norm and protocol-grounded evidence"
    assert (indicator_blocker in status["blockers"]) is not ready
    assert not any("req1 lacks a shared problem" in blocker or "crit1 lacks a shared problem" in blocker
                   for blocker in status["blockers"])


@pytest.mark.parametrize("via_inference", [False, True])
@pytest.mark.parametrize(("extra_unit", "ready"), (("kg", False), ("count", True)))
def test_indicator_support_problem_must_match_its_explicit_unit(tmp_path, extra_unit, ready, via_inference):
    path = tmp_path / "case"
    _complete_synthetic_case(path, sibling_protocol=True, sibling_problem="p2",
                             e0_refs=("pr2",), e0_metric_key="count", e0_unit="count",
                             indicator_extra_metric="count", indicator_extra_unit=extra_unit,
                             indicator_extra_via_inference=via_inference, stop_before_specify=True)
    engine.approve(path, "d1", "synthetic fixture approval", "human:fixture")
    status = engine.gate(path, "specify")
    assert status["ready"] is ready
    indicator_blocker = "i1 lacks a shared problem between norm and protocol-grounded evidence"
    assert (indicator_blocker in status["blockers"]) is not ready
    assert not any("req1 lacks a shared problem" in blocker or "crit1 lacks a shared problem" in blocker
                   for blocker in status["blockers"])


def test_specification_accepts_explicit_two_problem_normative_bridge(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path, study_problem="p2", norm_refs=("p1", "p2", "a1"))
    assert all(engine.gate(path, phase.id)["accepted"] for phase in PHASES)


def test_inconsistent_published_calculation_blocks_observation(tmp_path):
    path = tmp_path / "case"
    engine.create_case(path, "FAO arithmetic control", "food", "human:fixture", approval_policy="fixture")
    _put(path, "e1", "evidence", data={"origin": "published", "source": "FAO 2018", "date": "2018", "locator": "Table 18", "value": 79925.4, "unit": "t/year", "calculation": {"operator": "product", "operands": [183828.4, 0.15], "tolerance": 0.1}})
    issues = engine.get_state(path)["items"]["e1"]["issues"]
    assert any("differs from recomputed" in issue for issue in issues)
    assert not engine.gate(path, "observe")["ready"]


def test_large_integer_product_mismatch_blocks_observation_until_tolerated(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path, stop_before_observe=True)
    assert engine.gate(path, "observe")["ready"]
    data = {
        "origin": "simulated", "source": "synthetic fixture", "date": "2026-09-26",
        "locator": "independent calculation", "metric_key": "independent-count",
        "scope": "calculation", "unit": "count", "value": 2**53 + 1,
        "calculation": {"operator": "product", "operands": [2**53, 1], "tolerance": 0},
    }
    _put(path, "e2", "evidence", ["pr1"], data)
    assert any("differs from recomputed" in issue for issue in engine.get_state(path)["items"]["e2"]["issues"])
    assert not engine.gate(path, "observe")["ready"]

    tolerated = {**data, "calculation": {**data["calculation"], "tolerance": 1}}
    _put(path, "e2", "evidence", ["pr1"], tolerated)
    assert not engine.get_state(path)["items"]["e2"]["issues"]
    assert engine.gate(path, "observe")["ready"]

    for invalid in ({"operator": "product", "operands": [2**53, 1], "tolerance": -1},
                    {"operator": "product", "operands": ["Infinity", 1], "tolerance": 0}):
        _put(path, "e2", "evidence", ["pr1"], {**data, "calculation": invalid})
        assert "malformed or unsupported calculation" in engine.get_state(path)["items"]["e2"]["issues"]
        assert not engine.gate(path, "observe")["ready"]


@pytest.mark.parametrize("base", (2**53, 10**40))
def test_exact_integer_conflict_blocks_observe_and_honors_tolerance(tmp_path, base):
    path = tmp_path / "case"
    _complete_synthetic_case(path, e1_value=base, stop_before_observe=True)
    assert engine.gate(path, "observe")["ready"]
    data = {
        "origin": "simulated", "source": "second synthetic source", "date": "2026-09-26",
        "locator": "independent fixture", "metric_key": "count", "scope": "fixture",
        "unit": "count", "value": base + 1, "tolerance": 0,
    }
    _put(path, "e2", "evidence", ["pr1"], data)
    state = engine.get_state(path)
    assert any("e1 vs e2" in issue for issue in state["items"]["e1"]["issues"])
    assert any("e1 vs e2" in issue for issue in state["items"]["e2"]["issues"])
    assert not state["phases"]["observe"]["ready"]

    _put(path, "e2", "evidence", ["pr1"], {**data, "tolerance": 1})
    state = engine.get_state(path)
    assert not any("conflicting metric" in issue for id in ("e1", "e2")
                   for issue in state["items"][id]["issues"])
    assert state["phases"]["observe"]["ready"]


@pytest.mark.parametrize(("value", "unit", "valid"), (
    ("3-6", "rango porcentaje", True),
    ("6-3", "rango porcentaje", False),
    ("3-6", "porcentaje", False),
    ("unknown", "rango porcentaje", False),
    ("unknown", "porcentaje", False),
    ("1e1000000000-2", "rango porcentaje", False),
))
def test_contextual_range_requires_declared_unit_and_bounded_ordered_endpoints(tmp_path, value, unit, valid):
    path = tmp_path / "case"
    _complete_synthetic_case(path, e1_value=value, e1_unit=unit, stop_before_observe=True)
    state = engine.get_state(path)
    issues = state["items"]["e1"]["issues"]
    assert ("evidence metric value must be a finite supported number" not in issues) is valid
    assert state["phases"]["observe"]["ready"] is valid


@pytest.mark.parametrize(("other_value", "disjoint"), (
    ("7-9", True),
    (7, True),
    ("5-8", False),
    (6, False),
))
def test_range_and_scalar_conflicts_use_exact_interval_gap(tmp_path, other_value, disjoint):
    path = tmp_path / "case"
    _complete_synthetic_case(path, e1_value="3-6", e1_unit="rango porcentaje", stop_before_observe=True)
    assert engine.gate(path, "observe")["ready"]
    data = {
        "origin": "simulated", "source": "second synthetic source", "date": "2026-09-26",
        "locator": "independent fixture", "metric_key": "count", "scope": "fixture",
        "unit": "rango porcentaje", "value": other_value, "tolerance": 0,
    }
    _put(path, "e2", "evidence", ["pr1"], data)
    state = engine.get_state(path)
    assert any("e1 vs e2" in issue for issue in state["items"]["e1"]["issues"]) is disjoint
    assert state["phases"]["observe"]["ready"] is not disjoint

    if disjoint:
        _put(path, "e2", "evidence", ["pr1"], {**data, "tolerance": 1})
        state = engine.get_state(path)
        assert not any("e1 vs e2" in issue for issue in state["items"]["e1"]["issues"])
        assert state["phases"]["observe"]["ready"]


def test_range_prefix_normalizes_only_unit_representation_for_conflicts(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path, e1_value="3-6", e1_unit="rango porcentaje", stop_before_observe=True)
    base = {
        "origin": "simulated", "source": "second synthetic source", "date": "2026-09-26",
        "locator": "independent fixture", "metric_key": "count", "scope": "fixture",
        "tolerance": 0,
    }
    for value, unit, conflict in ((10, "porcentaje", True),
                                  ("7-9", "range porcentaje", True),
                                  (10, "kilogramos", False)):
        _put(path, "e2", "evidence", ["pr1"], {**base, "value": value, "unit": unit})
        state = engine.get_state(path)
        assert any("e1 vs e2" in issue for issue in state["items"]["e1"]["issues"]) is conflict
        assert state["phases"]["observe"]["ready"] is not conflict

    _put(path, "e2", "evidence", ["pr1"], {**base, "value": 10, "unit": "porcentaje", "tolerance": 4})
    state = engine.get_state(path)
    assert not any("e1 vs e2" in issue for issue in state["items"]["e1"]["issues"])
    assert state["phases"]["observe"]["ready"]


def test_contextual_range_cannot_be_used_as_scalar_calculation(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path, e1_value="3-6", e1_unit="rango porcentaje", stop_before_observe=True)
    data = dict(engine.get_state(path)["items"]["e1"]["data"])
    data["calculation"] = {"operator": "product", "operands": [3, 2], "tolerance": 0}
    _put(path, "e1", "evidence", ["pr1"], data)
    assert "malformed or unsupported calculation" in engine.get_state(path)["items"]["e1"]["issues"]
    assert not engine.gate(path, "observe")["ready"]


@pytest.mark.parametrize(("field", "invalid", "expected_issue"), (
    ("value", "unknown", "evidence metric value must be a finite supported number"),
    ("value", "1e1000000000", "evidence metric value must be a finite supported number"),
    ("value", "9" * 300, "evidence metric value must be a finite supported number"),
    ("tolerance", -1, "evidence metric tolerance must be a nonnegative finite supported number"),
    ("tolerance", "unknown", "evidence metric tolerance must be a nonnegative finite supported number"),
    ("tolerance", "1e1000000000", "evidence metric tolerance must be a nonnegative finite supported number"),
))
def test_invalid_metric_numbers_block_without_spurious_conflict(tmp_path, field, invalid, expected_issue):
    path = tmp_path / "case"
    _complete_synthetic_case(path, stop_before_observe=True)
    assert engine.gate(path, "observe")["ready"]
    data = {
        "origin": "simulated", "source": "second synthetic source", "date": "2026-09-26",
        "locator": "independent fixture", "metric_key": "count", "scope": "fixture",
        "unit": "count", "value": 10,
    }
    data[field] = invalid
    _put(path, "e2", "evidence", ["pr1"], data)
    state = engine.get_state(path)
    assert expected_issue in state["items"]["e2"]["issues"]
    assert not any("conflicting metric" in issue for id in ("e1", "e2")
                   for issue in state["items"][id]["issues"])
    assert not state["phases"]["observe"]["ready"]

    data[field] = 0 if field == "tolerance" else 10
    _put(path, "e2", "evidence", ["pr1"], data)
    assert not engine.get_state(path)["items"]["e2"]["issues"]
    assert engine.gate(path, "observe")["ready"]


@pytest.mark.parametrize("operands", (
    ["1e1000000000", 0],
    [1] * 65,
    ["1e500"] * 5,
))
def test_product_numeric_budget_blocks_observation_without_large_fraction(tmp_path, operands):
    path = tmp_path / "case"
    _complete_synthetic_case(path, stop_before_observe=True)
    data = {
        "origin": "simulated", "source": "synthetic fixture", "date": "2026-09-26",
        "locator": "bounded calculation", "metric_key": "bounded-product",
        "scope": "calculation", "unit": "count", "value": 0,
        "calculation": {"operator": "product", "operands": operands, "tolerance": 0},
    }
    _put(path, "e2", "evidence", ["pr1"], data)
    assert "malformed or unsupported calculation" in engine.get_state(path)["items"]["e2"]["issues"]
    assert not engine.gate(path, "observe")["ready"]


def test_independent_resolution_required_for_manual_challenge(tmp_path):
    path = tmp_path / "case"
    engine.create_case(path, "Challenge control", "test", "human:fixture", approval_policy="fixture")
    _put(path, "e1", "evidence", data={"origin": "published", "source": "A", "date": "2026", "locator": "1"})
    _put(path, "e2", "evidence", data={"origin": "published", "source": "B", "date": "2026", "locator": "1"})
    conflict = engine.challenge(path, "e1", "e2", "different denominators", "agent:reviewer")
    _put(path, "s1", "synthesis", ["e1", "e2"], text="The scopes differ")
    try:
        engine.resolve_challenge(path, conflict["seq"], "s1", "agent:analyst")
    except engine.MethodError:
        pass
    else:
        raise AssertionError("resolution without independent review")
    engine.review_item(path, "s1", "accept", "checked source scopes", "agent:reviewer")
    engine.resolve_challenge(path, conflict["seq"], "s1", "agent:analyst")
    assert engine.get_state(path)["open_challenges"] == []


def test_reviewed_resolution_clears_exact_automatic_pair_and_keeps_history(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    _put(path, "e2", "evidence", ["pr1"], {
        "origin": "simulated", "source": "second synthetic source", "date": "2026-09-26",
        "locator": "independent fixture", "metric_key": "count", "scope": "fixture",
        "unit": "count", "value": 12,
    })
    state = engine.get_state(path)
    assert any("e1 vs e2" in issue for issue in state["items"]["e1"]["issues"])
    assert state["items"]["inf1"]["contested"]
    assert state["items"]["ass1"]["contested"]
    assert not state["phases"]["observe"]["ready"]
    assert not state["phases"]["validate"]["accepted"]

    # Resolving a different pair must not clear the quantitative disagreement.
    other = engine.challenge(path, "e0", "e2", "compare contextual source", "agent:reviewer")
    _put(path, "syn0", "synthesis", ["e0", "e2", "inf1"], text="Contextual source checked")
    engine.review_item(path, "syn0", "accept", "checked both sources", "agent:reviewer")
    engine.resolve_challenge(path, other["seq"], "syn0", "agent:analyst")
    assert any("e1 vs e2" in issue for issue in engine.get_state(path)["items"]["e1"]["issues"])

    conflict = engine.challenge(path, "e2", "e1", "same scope disagrees", "agent:reviewer")
    _put(path, "syn2", "synthesis", ["inf1", "e1", "e2"], text="Both measurements disagree; retain both")
    with pytest.raises(engine.MethodError, match="independent accepted item review"):
        engine.resolve_challenge(path, conflict["seq"], "syn2", "agent:analyst")
    engine.review_item(path, "syn2", "accept", "reviewed disagreement and limits", "agent:reviewer")
    assert any("e1 vs e2" in issue for issue in engine.get_state(path)["items"]["e1"]["issues"])
    resolution = engine.resolve_challenge(path, conflict["seq"], "syn2", "agent:analyst")

    state = engine.get_state(path)
    assert state["items"]["e1"]["data"]["value"] == 10
    assert state["items"]["e2"]["data"]["value"] == 12
    assert not any("conflicting metric" in issue for id in ("e1", "e2") for issue in state["items"][id]["issues"])
    assert not any(state["items"][id]["contested"] for id in ("e1", "e2", "inf1", "syn1", "ass1"))
    _accept(path, "study")
    assert engine.gate(path, "observe")["ready"]
    assert not engine.gate(path, "observe")["accepted"]
    assert engine.get_state(path)["open_challenges"] == []
    for phase in PHASES[3:]:
        _accept(path, phase.id)

    events = read_project(path)["events"]
    assert events[conflict["seq"] - 1]["payload"]["left"] == "e2"
    assert events[conflict["seq"] - 1]["payload"]["right"] == "e1"
    assert events[resolution["seq"] - 1]["payload"]["challenge_seq"] == conflict["seq"]
    assert events[resolution["seq"] - 1]["payload"]["resolution_item"] == "syn2"


@pytest.mark.parametrize(("revised_evidence", "new_value"), (("e1", 11), ("e2", 13)))
def test_automatic_pair_reopens_after_resolution_or_evidence_revision(tmp_path, revised_evidence, new_value):
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    _put(path, "e2", "evidence", ["pr1"], {
        "origin": "simulated", "source": "second synthetic source", "date": "2026-09-26",
        "locator": "independent fixture", "metric_key": "count", "scope": "fixture",
        "unit": "count", "value": 12,
    })
    conflict = engine.challenge(path, "e1", "e2", "same scope disagrees", "agent:reviewer")
    _put(path, "syn2", "synthesis", ["inf1", "e1", "e2"], text="Both measurements disagree; retain both")
    engine.review_item(path, "syn2", "accept", "reviewed disagreement and limits", "agent:reviewer")
    engine.resolve_challenge(path, conflict["seq"], "syn2", "agent:analyst")
    assert engine.gate(path, "observe")["ready"]

    engine.review_item(path, "syn2", "reject", "found an unresolved limitation", "agent:reviewer")
    assert not engine.gate(path, "observe")["ready"]
    engine.review_item(path, "syn2", "accept", "limitation addressed in review", "agent:reviewer")
    assert not engine.gate(path, "observe")["ready"]
    engine.resolve_challenge(path, conflict["seq"], "syn2", "agent:analyst")
    assert engine.gate(path, "observe")["ready"]

    _put(path, "syn2", "synthesis", ["inf1", "e1", "e2"], text="Revised account of disagreement")
    state = engine.get_state(path)
    assert any("e1 vs e2" in issue for issue in state["items"]["e1"]["issues"])
    assert conflict["seq"] in {entry["seq"] for entry in state["open_challenges"]}
    assert not engine.gate(path, "observe")["ready"]
    engine.review_item(path, "syn2", "accept", "checked revised account", "agent:reviewer")
    engine.resolve_challenge(path, conflict["seq"], "syn2", "agent:analyst")
    assert engine.gate(path, "observe")["ready"]

    revised_data = dict(engine.get_state(path)["items"][revised_evidence]["data"])
    revised_data["value"] = new_value
    _put(path, revised_evidence, "evidence", ["pr1"], revised_data)
    state = engine.get_state(path)
    assert state["items"]["syn2"]["stale"]
    assert any("e1 vs e2" in issue for issue in state["items"][revised_evidence]["issues"])
    assert conflict["seq"] in {entry["seq"] for entry in state["open_challenges"]}
    assert not engine.gate(path, "observe")["ready"]


def test_each_conflicting_pair_needs_its_own_active_resolution(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    for id, value in (("e2", 12), ("e3", 14)):
        _put(path, id, "evidence", ["pr1"], {
            "origin": "simulated", "source": f"synthetic {id}", "date": "2026-09-26",
            "locator": id, "metric_key": "count", "scope": "fixture", "unit": "count", "value": value,
        })
    pairs = (("e1", "e2"), ("e1", "e3"), ("e2", "e3"))
    for index, (left, right) in enumerate(pairs):
        conflict = engine.challenge(path, left, right, "same scope disagrees", "agent:reviewer")
        synthesis = f"syn{left[-1]}{right[-1]}"
        _put(path, synthesis, "synthesis", ["inf1", left, right], text=f"Retain and reconcile {left} and {right}")
        engine.review_item(path, synthesis, "accept", "checked both sources", "agent:reviewer")
        engine.resolve_challenge(path, conflict["seq"], synthesis, "agent:analyst")
        issues = [issue for item in (left, right) for issue in engine.get_state(path)["items"][item]["issues"]]
        assert not any(f"{left} vs {right}" in issue for issue in issues)
        if index < len(pairs) - 1:
            assert not engine.gate(path, "observe")["ready"]
    assert engine.gate(path, "observe")["ready"]
    assert engine.get_state(path)["open_challenges"] == []


def test_rejection_after_advance_revokes_phase(tmp_path):
    path = tmp_path / "case"
    engine.create_case(path, "Review control", "test", "human:fixture", approval_policy="fixture")
    _put(path, "p1", "problem")
    _put(path, "a1", "actor", ["p1"])
    _put(path, "b1", "boundary", ["p1"])
    _accept(path, "frame")
    engine.review_phase(path, "frame", "reject", "newly noticed exclusion", "agent:reviewer")
    assert not engine.gate(path, "frame")["accepted"]
    try:
        engine.advance(path, "frame", "agent:analyst")
    except engine.MethodError:
        pass
    else:
        raise AssertionError("advance reused a superseded positive review")
    engine.review_phase(path, "frame", "accept", "exclusion resolved in review record", "agent:reviewer")
    assert not engine.gate(path, "frame")["accepted"]
    engine.advance(path, "frame", "agent:analyst")
    assert engine.gate(path, "frame")["accepted"]


def test_exact_review_and_advance_retries_preserve_accepted_descendants(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    events = read_project(path)["events"]
    review = next(event for event in reversed(events)
                  if event["kind"] == "phase_review" and event["payload"]["phase"] == "frame")
    marker = next(event for event in reversed(events)
                  if event["kind"] == "phase_advance" and event["payload"]["phase"] == "frame")
    before = (path / "organon.json").read_bytes()

    assert engine.review_phase(path, "frame", "accept", "fixture review", "agent:reviewer") == review
    assert engine.advance(path, "frame", "agent:lead") == marker
    assert (path / "organon.json").read_bytes() == before
    assert engine.gate(path, "frame")["advance_seq"] == marker["seq"]
    assert all(engine.gate(path, phase.id)["accepted"] for phase in PHASES)


def test_advance_retry_rejects_missing_or_different_actor_without_writing(tmp_path):
    path = tmp_path / "case"
    engine.create_case(path, "Actor retry control", "test", "human:fixture", approval_policy="fixture")
    _put(path, "p1", "problem")
    _put(path, "a1", "actor", ["p1"])
    _put(path, "b1", "boundary", ["p1"])
    _accept(path, "frame")
    marker = next(event for event in reversed(read_project(path)["events"])
                  if event["kind"] == "phase_advance")
    before = (path / "organon.json").read_bytes()

    with pytest.raises(engine.MethodError, match="nonempty actor"):
        engine.advance(path, "frame", "")
    with pytest.raises(engine.MethodError, match="nonempty actor"):
        engine.advance(path, "frame", "   ")
    with pytest.raises(engine.MethodError, match="already advanced by another actor"):
        engine.advance(path, "frame", "agent:other")
    assert engine.advance(path, "frame", " agent:lead ") == marker
    assert (path / "organon.json").read_bytes() == before


@pytest.mark.parametrize(("kind", "same_request"), (
    ("phase_review", True), ("phase_review", False),
    ("phase_advance", True), ("phase_advance", False),
))
def test_phase_transition_cas_race_recovers_only_exact_peer_event(tmp_path, monkeypatch, kind, same_request):
    path = tmp_path / "case"
    engine.create_case(path, "CAS retry control", "test", "human:fixture", approval_policy="fixture")
    _put(path, "p1", "problem")
    _put(path, "a1", "actor", ["p1"])
    _put(path, "b1", "boundary", ["p1"])
    if kind == "phase_advance":
        engine.review_phase(path, "frame", "accept", "fixture review", "agent:reviewer")
    before_count = len(read_project(path)["events"])
    append = engine.append_event
    winner = {}

    def append_after_peer(path, event_kind, payload, actor, *, expected_seq):
        assert event_kind == kind
        peer_payload = payload if same_request or kind == "phase_advance" else {**payload, "reason": "different peer review"}
        peer_actor = actor if same_request or kind == "phase_review" else "agent:other"
        winner["event"] = append(path, event_kind, peer_payload, peer_actor, expected_seq=expected_seq)
        return append(path, event_kind, payload, actor, expected_seq=expected_seq)

    monkeypatch.setattr(engine, "append_event", append_after_peer)
    def operation():
        if kind == "phase_review":
            return engine.review_phase(path, "frame", "accept", "fixture review", "agent:reviewer")
        return engine.advance(path, "frame", "agent:lead")

    if same_request:
        assert operation() == winner["event"]
    else:
        with pytest.raises(engine.ConflictError, match="revision conflict"):
            operation()
    assert len(read_project(path)["events"]) == before_count + 1
    assert read_project(path)["events"][-1] == winner["event"]


def test_new_review_and_upstream_revision_require_fresh_markers(tmp_path):
    path = tmp_path / "case"
    engine.create_case(path, "Review and revision control", "test", "human:fixture", approval_policy="fixture")
    _put(path, "p1", "problem")
    _put(path, "a1", "actor", ["p1"])
    _put(path, "b1", "boundary", ["p1"])
    _accept(path, "frame")
    original = engine.gate(path, "frame")

    revised_review = engine.review_phase(path, "frame", "accept", "clarified reason", "agent:reviewer")
    assert not engine.gate(path, "frame")["accepted"]
    revised_marker = engine.advance(path, "frame", "agent:lead")
    assert revised_marker["payload"]["review_seq"] == revised_review["seq"]
    assert revised_marker["seq"] != original["advance_seq"]

    another_reviewer = engine.review_phase(path, "frame", "accept", "clarified reason", "agent:second-reviewer")
    assert another_reviewer["seq"] != revised_review["seq"]
    assert not engine.gate(path, "frame")["accepted"]
    engine.advance(path, "frame", "agent:lead")

    _put(path, "p1", "problem", text="revised problem")
    _put(path, "a1", "actor", ["p1"])
    _put(path, "b1", "boundary", ["p1"])
    changed = engine.gate(path, "frame")
    assert changed["ready"]
    assert changed["snapshot"] != original["snapshot"]
    assert not changed["reviewed"] and not changed["accepted"]
    fresh_review = engine.review_phase(path, "frame", "accept", "reviewed revised problem", "agent:reviewer")
    fresh_marker = engine.advance(path, "frame", "agent:lead")
    assert fresh_marker["payload"]["review_seq"] == fresh_review["seq"]
    assert fresh_marker["payload"]["snapshot"] == changed["snapshot"]
    assert fresh_marker["seq"] != revised_marker["seq"]
    assert engine.gate(path, "frame")["accepted"]


def test_resolved_challenge_still_needs_fresh_phase_review(tmp_path):
    path = tmp_path / "case"
    engine.create_case(path, "Challenge control", "test", "human:fixture", approval_policy="fixture")
    _put(path, "p1", "problem")
    _put(path, "a1", "actor", ["p1"])
    _put(path, "b1", "boundary", ["p1"])
    _accept(path, "frame")
    conflict = engine.challenge(path, "p1", "a1", "actor disputes scope", "agent:reviewer")
    _put(path, "s1", "synthesis", ["p1", "a1"], text="Documented reconciliation")
    engine.review_item(path, "s1", "accept", "reviewed reconciliation", "agent:reviewer")
    engine.resolve_challenge(path, conflict["seq"], "s1", "agent:analyst")
    assert engine.gate(path, "frame")["ready"]
    assert not engine.gate(path, "frame")["accepted"]
    _accept(path, "frame")


def test_resolution_reopens_when_its_reviewed_basis_changes(tmp_path):
    path = tmp_path / "case"
    engine.create_case(path, "Resolution version control", "test", "human:fixture", approval_policy="fixture")
    _put(path, "p1", "problem")
    _put(path, "a1", "actor", ["p1"])
    _put(path, "b1", "boundary", ["p1"])
    _accept(path, "frame")
    conflict = engine.challenge(path, "p1", "a1", "actor disputes scope", "agent:reviewer")
    _put(path, "syn2", "synthesis", ["p1", "a1"], text="Reconciled accounts")
    engine.review_item(path, "syn2", "accept", "checked both accounts", "agent:reviewer")
    engine.resolve_challenge(path, conflict["seq"], "syn2", "agent:analyst")
    _accept(path, "frame")
    assert not engine.get_state(path)["open_challenges"]
    _put(path, "syn2", "synthesis", ["p1"], text="One account only")
    assert engine.get_state(path)["open_challenges"]
    assert not engine.gate(path, "frame")["accepted"]
    _put(path, "syn2", "synthesis", ["p1", "a1"], text="Both accounts restored")
    engine.review_item(path, "syn2", "accept", "rechecked both accounts", "agent:reviewer")
    engine.resolve_challenge(path, conflict["seq"], "syn2", "agent:analyst")
    assert not engine.get_state(path)["open_challenges"]
    assert not engine.gate(path, "frame")["accepted"]
    _accept(path, "frame")
    engine.review_item(path, "syn2", "reject", "new concern", "agent:reviewer")
    assert engine.get_state(path)["open_challenges"]
    assert not engine.gate(path, "frame")["accepted"]


def test_criterion_metric_must_match_linked_indicator(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    _put(path, "crit1", "criterion", ["req1", "i1"], {"metric": "revenue", "threshold": 0, "reject": "negative revenue"})
    assert any("same success metric" in blocker for blocker in engine.gate(path, "specify")["blockers"])
    assert not engine.gate(path, "specify")["accepted"]


def test_criterion_cannot_borrow_same_metric_indicator_from_another_problem(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path, disjoint_indicator=True, criterion_indicator="i2",
                             stop_before_specify=True)
    engine.approve(path, "d1", "synthetic human attestation for mechanics test", "human:fixture")
    assert all(engine.gate(path, phase)["accepted"] for phase in
               ("frame", "critique", "study", "observe", "explain", "compare"))
    assert engine.get_state(path)["items"]["i2"]["data"]["metric"] == "count"

    _put(path, "impl1", "implementation", ["req1"])
    _put(path, "t1", "test", ["impl1", "crit1"],
         {"passed": True, "command": "synthetic fixture; no external command run"})
    _put(path, "base1", "baseline", ["crit1"],
         {"origin": "simulation", "source": "synthetic fixture", "date": "2026-09-26"})
    _put(path, "res1", "result", ["base1", "crit1"],
         {"origin": "simulation", "source": "synthetic fixture", "date": "2026-09-26"})
    _put(path, "ass1", "assessment", ["res1", "r1"],
         {"verdict": "no_demostrado", "claim_scope": "field", "uncertainty": "synthetic only",
          "adverse_effects": "not measured", "cost": "not measured"})
    assert "crit1 needs a same-problem link from req1 to a same-metric indicator" in \
        engine.gate(path, "specify")["blockers"]
    for phase in ("specify", "build", "validate"):
        status = engine.gate(path, phase)
        assert not status["ready"] and not status["accepted"]
        with pytest.raises(engine.MethodError, match="phase cannot be accepted"):
            engine.review_phase(path, phase, "accept", "invalid linkage", "agent:reviewer")


def test_same_problem_indicator_accepts_requirement_evidence_with_another_metric(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path, disjoint_indicator=True,
                             e0_metric_key="count", e0_unit="count",
                             e1_metric_key="other", e1_unit="other-unit")
    items = engine.get_state(path)["items"]
    assert items["e1"]["data"]["metric_key"] == "other"
    assert items["i1"]["data"]["metric"] == items["i2"]["data"]["metric"] == "count"
    assert set(items["crit1"]["deps"]) == {"req1", "i1"}
    assert all(engine.gate(path, phase.id)["accepted"] for phase in PHASES)


def test_final_validation_requires_independent_review(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    engine.review_phase(path, "validate", "accept", "self review fixture", "agent:analyst")
    assert not engine.gate(path, "validate")["accepted"]
    try:
        engine.advance(path, "validate", "agent:analyst")
    except engine.MethodError as exc:
        assert "independent review" in str(exc)
    else:
        raise AssertionError("self review advanced final validation")


def test_simulation_cannot_claim_field_success_and_field_needs_numbers(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    _put(path, "ass1", "assessment", ["res1", "r1"], {"verdict": "cumplido", "claim_scope": "field", "uncertainty": "none", "adverse_effects": "none", "cost": "none"})
    blockers = engine.gate(path, "validate")["blockers"]
    assert any("cannot use another evidence origin" in item for item in blockers)
    _put(path, "base1", "baseline", ["crit1"], {"origin": "field", "source": "self report", "date": "2026-09-26"})
    _put(path, "res1", "result", ["base1", "crit1"], {"origin": "field", "source": "self report", "date": "2026-09-26"})
    _put(path, "ass1", "assessment", ["res1", "r1"], {"verdict": "cumplido", "claim_scope": "field", "uncertainty": "none", "adverse_effects": "none", "cost": "none"})
    blockers = engine.gate(path, "validate")["blockers"]
    assert any("structured threshold and measured effect" in item for item in blockers)


def test_simulation_cannot_claim_field_rejection_and_no_demostrado_remains_available(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    assessment = {"verdict": "incumplido", "claim_scope": "field", "uncertainty": "synthetic only",
                  "adverse_effects": "not measured", "cost": "not measured"}
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment)
    status = engine.gate(path, "validate")
    assert not status["ready"] and not status["accepted"]
    assert any("cannot use another evidence origin" in item for item in status["blockers"])

    _put(path, "base1", "baseline", ["crit1"],
         {"origin": "field", "source": "self report", "date": "2026-09-26"})
    _put(path, "res1", "result", ["base1", "crit1"],
         {"origin": "field", "source": "self report", "date": "2026-09-26"})
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment)
    assert any("structured threshold and measured effect" in item
               for item in engine.gate(path, "validate")["blockers"])

    assessment["verdict"] = "no_demostrado"
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment)
    assert engine.gate(path, "validate")["ready"]


@pytest.mark.parametrize("success_statistic", ("lower_ci", "estimate"))
def test_field_rejection_requires_measured_failure_of_prior_rule(tmp_path, success_statistic):
    # The numbers and field label are invented; this checks gate mechanics only.
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    criterion = {"metric": "count", "threshold": {"operator": ">=", "value": 0.1,
                                                 "statistic": success_statistic},
                 "reject": "upper CI below 0.1"}
    _put(path, "crit1", "criterion", ["req1", "i1"], criterion.copy())
    _put(path, "t1", "test", ["impl1", "crit1"],
         {"passed": True, "command": "synthetic fixture; no external command run"})
    _put(path, "base1", "baseline", ["crit1"],
         {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
          "metric": "count", "value": 0.2, "unit": "count"})
    effect = {"metric": "count", "estimate": 0.3, "interval": [0.05, 0.4],
              "design": "randomized fixture", "comparator": "synthetic control",
              "sample_size": 12, "unit": "count"}
    assessment = {"verdict": "incumplido", "claim_scope": "field",
                  "uncertainty": "synthetic interval", "adverse_effects": "invented fixture",
                  "cost": "invented fixture"}

    def record_result():
        _put(path, "res1", "result", ["base1", "crit1", "t1"],
             {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
              "effect": effect.copy()})
        _put(path, "ass1", "assessment", ["res1", "r1"], assessment.copy())

    def revise_criterion():
        _put(path, "crit1", "criterion", ["req1", "i1"], criterion.copy())
        _put(path, "t1", "test", ["impl1", "crit1"],
             {"passed": True, "command": "synthetic fixture; no external command run"})
        _put(path, "base1", "baseline", ["crit1"],
             {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
              "metric": "count", "value": 0.2, "unit": "count"})
        record_result()
        _accept(path, "specify")
        _accept(path, "build")

    record_result()
    _accept(path, "specify")
    _accept(path, "build")
    assert "ass1 rejection needs a structured preregistered rejection test" in \
        engine.gate(path, "validate")["blockers"]

    criterion["reject_test"] = {"operator": "<", "value": 0.1, "statistic": "lower_ci"}
    revise_criterion()
    assert "ass1 field rejection test must use upper_ci < at the success threshold" in \
        engine.gate(path, "validate")["blockers"]

    criterion["reject_test"] = {"operator": "<", "value": 0.1, "statistic": "upper_ci"}
    revise_criterion()
    assert "ass1 measured upper_ci does not meet the prior rejection test" in \
        engine.gate(path, "validate")["blockers"]

    assessment["verdict"] = "no_demostrado"
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment.copy())
    assert engine.gate(path, "validate")["ready"]
    assessment["verdict"] = "incumplido"

    effect["estimate"] = 0.03
    effect["interval"] = [0.01, 0.05]
    record_result()
    _accept(path, "validate")

    effect["sample_size"] = 0
    record_result()
    assert "ass1 field rejection lacks a positive sample size" in \
        engine.gate(path, "validate")["blockers"]

    effect["sample_size"] = 12
    effect["estimate"] = 0.3
    effect["interval"] = [0.15, 0.4]
    record_result()
    status = engine.gate(path, "validate")
    assert not status["ready"] and not status["accepted"]
    assert any("does not meet the prior rejection test" in item
               for item in status["blockers"])


def test_overlapping_success_and_rejection_tests_block_both_verdicts(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    success_test = {"operator": ">=", "value": 0.1, "statistic": "lower_ci"}
    _put(path, "crit1", "criterion", ["req1", "i1"],
         {"metric": "count", "threshold": success_test,
          "reject": "duplicate success condition", "reject_test": success_test})
    _put(path, "t1", "test", ["impl1", "crit1"],
         {"passed": True, "command": "synthetic fixture; no external command run"})
    _put(path, "base1", "baseline", ["crit1"],
         {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
          "metric": "count", "value": 0.2, "unit": "count"})
    _put(path, "res1", "result", ["base1", "crit1", "t1"],
         {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
          "effect": {"metric": "count", "estimate": 0.3, "interval": [0.15, 0.4],
                     "design": "randomized fixture", "comparator": "synthetic control",
                     "sample_size": 12, "unit": "count"}})
    _accept(path, "specify")
    _accept(path, "build")

    for verdict in ("incumplido", "cumplido"):
        _put(path, "ass1", "assessment", ["res1", "r1"],
             {"verdict": verdict, "claim_scope": "field", "uncertainty": "synthetic interval",
              **_synthetic_measured_outcomes()})
        status = engine.gate(path, "validate")
        assert not status["ready"] and not status["accepted"]
        assert "ass1 success and rejection tests both hold for the measured effect" in \
            status["blockers"]


@pytest.mark.parametrize("success_statistic", ("upper_ci", "estimate"))
def test_field_upper_bound_success_uses_lower_bound_for_rejection(tmp_path, success_statistic):
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    _put(path, "crit1", "criterion", ["req1", "i1"],
         {"metric": "count", "threshold": {"operator": "<=", "value": 0.1,
                                           "statistic": success_statistic},
          "reject": "lower CI above 0.1",
          "reject_test": {"operator": ">", "value": 0.1, "statistic": "lower_ci"}})
    _put(path, "t1", "test", ["impl1", "crit1"],
         {"passed": True, "command": "synthetic fixture; no external command run"})
    _put(path, "base1", "baseline", ["crit1"],
         {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
          "metric": "count", "value": 0.2, "unit": "count"})
    effect = {"metric": "count", "estimate": 0.3, "interval": [0.15, 0.4],
              "design": "randomized fixture", "comparator": "synthetic control",
              "sample_size": 12, "unit": "count"}

    def record_result():
        _put(path, "res1", "result", ["base1", "crit1", "t1"],
             {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
              "effect": effect.copy()})
        _put(path, "ass1", "assessment", ["res1", "r1"],
             {"verdict": "incumplido", "claim_scope": "field",
              "uncertainty": "synthetic interval", "adverse_effects": "invented fixture",
              "cost": "invented fixture"})

    record_result()
    _accept(path, "specify")
    _accept(path, "build")
    _accept(path, "validate")

    effect["interval"] = [0.05, 0.4]
    record_result()
    assert "ass1 measured lower_ci does not meet the prior rejection test" in \
        engine.gate(path, "validate")["blockers"]


def test_structured_field_claim_checks_prior_threshold_mechanically(tmp_path):
    # These are invented fixture numbers. Passing this gate is not field evidence.
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    _put(path, "crit1", "criterion", ["req1", "i1"], {"metric": "count", "threshold": {"operator": ">=", "value": 0.1, "statistic": "lower_ci"}, "reject": "lower CI below 0.1"})
    _put(path, "t1", "test", ["impl1", "crit1"], {"passed": True, "command": "synthetic fixture; no external command run"})
    _put(path, "base1", "baseline", ["crit1"], {"origin": "field", "source": "invented fixture", "date": "2026-09-26", "metric": "count", "value": 0.2, "unit": "count"})
    _put(path, "res1", "result", ["base1", "crit1", "t1"], {"origin": "field", "source": "invented fixture", "date": "2026-09-26", "effect": {"metric": "count", "estimate": 0.3, "interval": [0.15, 0.4], "design": "randomized fixture", "comparator": "synthetic control", "sample_size": 12, "unit": "count"}})
    _put(path, "ass1", "assessment", ["res1", "r1"],
         {"verdict": "cumplido", "claim_scope": "field", "uncertainty": "synthetic interval",
          **_synthetic_measured_outcomes()})
    _accept(path, "specify")
    _accept(path, "build")
    _accept(path, "validate")
    _put(path, "res1", "result", ["base1", "crit1", "t1"], {"origin": "field", "source": "invented fixture", "date": "2026-09-26", "effect": {"metric": "count", "estimate": 0.3, "interval": [0.05, 0.4], "design": "randomized fixture", "comparator": "synthetic control", "sample_size": 12, "unit": "count"}})
    _put(path, "ass1", "assessment", ["res1", "r1"],
         {"verdict": "cumplido", "claim_scope": "field", "uncertainty": "synthetic interval",
          **_synthetic_measured_outcomes()})
    blockers = engine.gate(path, "validate")["blockers"]
    assert any("does not meet the prior threshold" in item for item in blockers)
    assert not engine.gate(path, "validate")["accepted"]


@pytest.mark.parametrize("linked_tests", ((), ("t2",)))
def test_decisive_result_needs_test_of_its_criterion_and_requirement(tmp_path, linked_tests):
    # Invented measurements exercise lineage only; they do not establish field impact.
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    _put(path, "req2", "requirement", ["d1"])
    _put(path, "crit1", "criterion", ["req1", "i1"],
         {"metric": "count", "threshold": {"operator": ">=", "value": 0.1,
                                           "statistic": "lower_ci"}, "reject": "lower CI below 0.1"})
    _put(path, "t1", "test", ["impl1", "crit1"],
         {"passed": True, "command": "synthetic fixture; no external command run"})
    _put(path, "impl2", "implementation", ["req2"])
    _put(path, "t2", "test", ["impl2", "crit1"],
         {"passed": True, "command": "synthetic fixture; no external command run"})
    _put(path, "base1", "baseline", ["crit1"],
         {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
          "metric": "count", "value": 0.2, "unit": "count"})
    result_data = {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
                   "effect": {"metric": "count", "estimate": 0.3, "interval": [0.15, 0.4],
                              "design": "randomized fixture", "comparator": "synthetic control",
                              "sample_size": 12, "unit": "count"}}
    assessment_data = {"verdict": "cumplido", "claim_scope": "field",
                       "uncertainty": "synthetic interval", **_synthetic_measured_outcomes()}
    _put(path, "res1", "result", ["base1", "crit1", *linked_tests], result_data)
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment_data)
    _accept(path, "specify")
    _accept(path, "build")

    missing_test = "ass1 success needs a current passed test linked to res1 for crit1 and implementation of req1"
    status = engine.gate(path, "validate")
    assert status["blockers"] == [missing_test]
    assert not status["ready"] and not status["accepted"]

    assessment_data["verdict"] = "no_demostrado"
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment_data)
    assert engine.gate(path, "validate")["ready"]

    assessment_data["verdict"] = "cumplido"
    _put(path, "res1", "result", ["base1", "crit1", "t1"], result_data)
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment_data)
    _accept(path, "validate")


def test_decisive_result_covers_every_requirement_of_criterion(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    _put(path, "req2", "requirement", ["d1"])
    _put(path, "crit1", "criterion", ["req1", "req2", "i1"],
         {"metric": "count", "threshold": {"operator": ">=", "value": 0.1,
                                           "statistic": "lower_ci"}, "reject": "lower CI below 0.1"})
    _put(path, "t1", "test", ["impl1", "crit1"],
         {"passed": True, "command": "synthetic fixture; no external command run"})
    _put(path, "impl2", "implementation", ["req2"])
    _put(path, "t2", "test", ["impl2", "crit1"],
         {"passed": True, "command": "synthetic fixture; no external command run"})
    _put(path, "base1", "baseline", ["crit1"],
         {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
          "metric": "count", "value": 0.2, "unit": "count"})
    result_data = {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
                   "effect": {"metric": "count", "estimate": 0.3, "interval": [0.15, 0.4],
                              "design": "randomized fixture", "comparator": "synthetic control",
                              "sample_size": 12, "unit": "count"}}
    _put(path, "res1", "result", ["base1", "crit1", "t1"], result_data)
    _put(path, "ass1", "assessment", ["res1", "r1"],
         {"verdict": "cumplido", "claim_scope": "field", "uncertainty": "synthetic interval",
          **_synthetic_measured_outcomes()})
    _accept(path, "specify")
    _accept(path, "build")

    assert engine.gate(path, "validate")["blockers"] == [
        "ass1 success needs a current passed test linked to res1 for crit1 and implementation of req2"
    ]
    _put(path, "res1", "result", ["base1", "crit1", "t1", "t2"], result_data)
    _put(path, "ass1", "assessment", ["res1", "r1"],
         {"verdict": "cumplido", "claim_scope": "field", "uncertainty": "synthetic interval",
          **_synthetic_measured_outcomes()})
    _accept(path, "validate")


@pytest.mark.parametrize(
    "verdict,estimate,interval",
    [
        ("cumplido", 0.3, [0.15, 0.4]),
        ("incumplido", 0.03, [0.01, 0.05]),
    ],
)
def test_decisive_result_requires_test_link_to_each_implementation(
    tmp_path,
    verdict,
    estimate,
    interval,
):
    # A criterion can mention impl2 without t1 actually testing impl2.
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    _put(path, "req2", "requirement", ["d1"])
    _put(path, "impl2", "implementation", ["req2"])
    _put(
        path,
        "crit1",
        "criterion",
        ["req1", "req2", "i1", "impl2"],
        {
            "metric": "count",
            "threshold": {"operator": ">=", "value": 0.1, "statistic": "lower_ci"},
            "reject": "upper CI below 0.1",
            "reject_test": {"operator": "<", "value": 0.1, "statistic": "upper_ci"},
        },
    )
    test_data = {
        "passed": True,
        "command": "synthetic fixture; no external command run",
    }
    _put(path, "t1", "test", ["impl1", "crit1"], test_data)
    _put(
        path,
        "base1",
        "baseline",
        ["crit1"],
        {
            "origin": "field",
            "source": "invented fixture",
            "date": "2026-09-27",
            "metric": "count",
            "value": 0.2,
            "unit": "count",
        },
    )
    result_data = {
        "origin": "field",
        "source": "invented fixture",
        "date": "2026-09-27",
        "effect": {
            "metric": "count",
            "estimate": estimate,
            "interval": interval,
            "design": "randomized fixture",
            "comparator": "synthetic control",
            "sample_size": 12,
            "unit": "count",
        },
    }
    assessment_data = {
        "verdict": verdict,
        "claim_scope": "field",
        "uncertainty": "synthetic interval",
        **_synthetic_measured_outcomes(),
    }
    _put(path, "res1", "result", ["base1", "crit1", "t1"], result_data)
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment_data)
    _accept(path, "specify")
    _accept(path, "build")

    items = engine._project(path)["items"]
    assert "impl2" in engine._ancestors(items, "t1")
    assert "impl2" not in items["t1"]["deps"]
    claim = "success" if verdict == "cumplido" else "rejection"
    missing = (
        f"ass1 {claim} needs a current passed test linked to res1 "
        "for crit1 and implementation of req2"
    )
    status = engine.gate(path, "validate")
    assert status["blockers"] == [missing]
    assert not status["ready"] and not status["accepted"]

    _put(path, "t2", "test", ["impl2", "crit1"], test_data)
    _put(path, "res1", "result", ["base1", "crit1", "t1", "t2"], result_data)
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment_data)
    _accept(path, "build")
    _accept(path, "validate")


@pytest.mark.parametrize(
    "verdict,estimate,interval",
    [
        ("cumplido", 0.3, [0.15, 0.4]),
        ("incumplido", 0.03, [0.01, 0.05]),
    ],
)
def test_decisive_result_requires_implementation_to_name_each_requirement(
    tmp_path,
    verdict,
    estimate,
    interval,
):
    # impl1 can inherit req2 through crit1 without declaring that it implements req2.
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    _put(path, "req2", "requirement", ["d1"])
    _put(
        path,
        "crit1",
        "criterion",
        ["req1", "req2", "i1"],
        {
            "metric": "count",
            "threshold": {"operator": ">=", "value": 0.1, "statistic": "lower_ci"},
            "reject": "upper CI below 0.1",
            "reject_test": {"operator": "<", "value": 0.1, "statistic": "upper_ci"},
        },
    )
    _put(path, "impl1", "implementation", ["req1", "crit1"])
    test_data = {
        "passed": True,
        "command": "synthetic fixture; no external command run",
    }
    _put(path, "t1", "test", ["impl1", "crit1"], test_data)
    _put(
        path,
        "base1",
        "baseline",
        ["crit1"],
        {
            "origin": "field",
            "source": "invented fixture",
            "date": "2026-09-27",
            "metric": "count",
            "value": 0.2,
            "unit": "count",
        },
    )
    result_data = {
        "origin": "field",
        "source": "invented fixture",
        "date": "2026-09-27",
        "effect": {
            "metric": "count",
            "estimate": estimate,
            "interval": interval,
            "design": "randomized fixture",
            "comparator": "synthetic control",
            "sample_size": 12,
            "unit": "count",
        },
    }
    assessment_data = {
        "verdict": verdict,
        "claim_scope": "field",
        "uncertainty": "synthetic interval",
        **_synthetic_measured_outcomes(),
    }
    _put(path, "res1", "result", ["base1", "crit1", "t1"], result_data)
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment_data)
    _accept(path, "specify")
    _accept(path, "build")

    items = engine._project(path)["items"]
    assert "req2" in engine._ancestors(items, "impl1")
    assert "req2" not in items["impl1"]["deps"]
    claim = "success" if verdict == "cumplido" else "rejection"
    missing = (
        f"ass1 {claim} needs a current passed test linked to res1 "
        "for crit1 and implementation of req2"
    )
    status = engine.gate(path, "validate")
    assert status["blockers"] == [missing]
    assert not status["ready"] and not status["accepted"]

    _put(path, "impl1", "implementation", ["req1", "req2"])
    _put(path, "t1", "test", ["impl1", "crit1"], test_data)
    _put(path, "res1", "result", ["base1", "crit1", "t1"], result_data)
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment_data)
    _accept(path, "build")
    _accept(path, "validate")


def _decisive_lineage_fixture(
    path,
    verdict,
    *,
    tested_implementation,
    baseline_refs,
    result_refs,
    scope="field",
):
    _complete_synthetic_case(path)
    if tested_implementation == "impl2":
        _put(path, "impl2", "implementation", ["impl1"])
    _put(
        path,
        "crit1",
        "criterion",
        ["req1", "i1"],
        {
            "metric": "count",
            "threshold": {"operator": ">=", "value": 0.1, "statistic": "lower_ci"},
            "reject": "upper CI below 0.1",
            "reject_test": {"operator": "<", "value": 0.1, "statistic": "upper_ci"},
        },
    )
    _put(
        path,
        "t1",
        "test",
        [tested_implementation, "crit1"],
        {"passed": True, "command": "synthetic fixture; no external command run"},
    )
    _put(
        path,
        "base1",
        "baseline",
        baseline_refs,
        {
            "origin": scope,
            "source": "invented fixture",
            "date": "2026-09-27",
            "metric": "count",
            "value": 0.2,
            "unit": "count",
        },
    )
    estimate, interval = (
        (0.3, [0.15, 0.4]) if verdict == "cumplido" else (0.03, [0.01, 0.05])
    )
    result_data = {
        "origin": scope,
        "source": "invented fixture",
        "date": "2026-09-27",
        "effect": {
            "metric": "count",
            "estimate": estimate,
            "interval": interval,
            "design": "randomized fixture",
            "comparator": "synthetic control",
            "sample_size": 12,
            "unit": "count",
        },
    }
    assessment_data = {
        "verdict": verdict,
        "claim_scope": scope,
        "uncertainty": "synthetic interval",
        **_synthetic_measured_outcomes(),
    }
    _put(path, "res1", "result", result_refs, result_data)
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment_data)
    _accept(path, "specify")
    _accept(path, "build")
    return result_data, assessment_data


def test_field_success_requires_structured_adverse_effects_and_cost(tmp_path):
    # All values and the field label are synthetic; this checks schema, not observation.
    path = tmp_path / "case"
    _, assessment = _decisive_lineage_fixture(
        path, "cumplido", tested_implementation="impl1",
        baseline_refs=["crit1"], result_refs=["base1", "crit1", "t1"],
    )
    assessment["cost"] = _synthetic_measured_outcome("cost", "USD", 0)
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment)
    assert engine.gate(path, "validate")["ready"]
    assert assessment["adverse_effects"]["measurements"][0]["value"] == 0
    assert assessment["cost"]["measurements"][0]["value"] == 0

    for field in ("adverse_effects", "cost"):
        record = assessment[field]
        measure = record["measurements"][0]
        invalid_records = (
            "Adverse effects not measured", "Cost not measured",
            "No medido todavía", "not measured; no data",
            # The apparent meaning of this prose is irrelevant: it is not a record.
            "Sin datos faltantes; costo medido: 2 USD",
            "", " \t\n ", None, [], {},
            {**record, "status": "unknown"}, {**record, "status": "unmeasured"},
            {key: value for key, value in record.items() if key != "source"},
            {**record, "source": "  "}, {**record, "date": ""},
            {**record, "measurements": []},
            {**record, "measurements": ["measured"]},
            {**record, "measurements": [{**measure, "metric": " "}]},
            {**record, "measurements": [{**measure, "unit": ""}]},
            {**record, "measurements": [
                {key: value for key, value in measure.items() if key != "value"},
            ]},
            {**record, "measurements": [{**measure, "value": "0"}]},
            {**record, "measurements": [{**measure, "value": True}]},
            {**record, "measurements": [{**measure, "sample_size": 0}]},
            {**record, "measurements": [{**measure, "sample_size": 1.0}]},
            {**record, "measurements": [{**measure, "sample_size": True}]},
            {**record, "measurements": [measure, {**measure, "sample_size": 0}]},
        )
        for invalid in invalid_records:
            _put(path, "ass1", "assessment", ["res1", "r1"],
                 {**assessment, field: invalid})
            status = engine.gate(path, "validate")
            assert status["blockers"] == [f"ass1 field success lacks structured measured {field} evidence"]
            assert not status["ready"] and not status["accepted"]
        missing = {key: value for key, value in assessment.items() if key != field}
        _put(path, "ass1", "assessment", ["res1", "r1"], missing)
        assert f"ass1 field success lacks structured measured {field} evidence" in \
            engine.gate(path, "validate")["blockers"]

    _put(path, "ass1", "assessment", ["res1", "r1"],
         {**assessment, "adverse_effects": "Adverse effects not measured",
          "cost": "Cost not measured"})
    assert engine.gate(path, "validate")["blockers"] == [
        "ass1 field success lacks structured measured adverse_effects evidence",
        "ass1 field success lacks structured measured cost evidence",
    ]
    with pytest.raises(engine.MethodError, match="phase cannot advance"):
        engine.advance(path, "validate", "agent:lead")

    _put(path, "ass1", "assessment", ["res1", "r1"], assessment)
    _accept(path, "validate")

    # The ledger rejects nonfinite JSON before a gate; the validator also rejects it.
    record = assessment["cost"]
    measure = record["measurements"][0]
    for nonfinite in (float("nan"), float("inf"), float("-inf")):
        assert not engine._structured_field_outcome(
            {**record, "measurements": [{**measure, "value": nonfinite}]}
        )


def test_signed_field_success_rejects_self_declared_attestation(tmp_path, monkeypatch):
    # A synthetic complete graph isolates the gate branch; it is not field evidence.
    path = tmp_path / "case"
    _, assessment = _decisive_lineage_fixture(
        path, "cumplido", tested_implementation="impl1",
        baseline_refs=["crit1"], result_refs=["base1", "crit1", "t1"],
    )
    assessment["field_guardrails"] = {
        "approval_authenticated": True,
        "execution_ready": True,
        "registry_sha256": "a" * 64,
    }
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment)
    assert engine.gate(path, "validate")["ready"]  # fixture mechanics only

    state = engine._project(path)
    signed_state = {**state, "project": {**state["project"], "approval_policy": "signed"}}
    monkeypatch.setattr(engine, "_project", lambda _path: signed_state)
    status = engine.gate(path, "validate")
    assert status["blockers"] == [
        "ass1 decisive field verdict needs an independently verified field attestation (not yet supported)"
    ]
    assert not status["ready"] and not status["accepted"]


@pytest.mark.parametrize("scope", ("simulation", "technical"))
def test_unmeasured_outcome_placeholders_do_not_change_non_field_success(tmp_path, scope):
    path = tmp_path / "case"
    _, assessment = _decisive_lineage_fixture(
        path, "cumplido", tested_implementation="impl1",
        baseline_refs=["crit1"], result_refs=["base1", "crit1", "t1"], scope=scope,
    )
    assessment.update({"adverse_effects": {"status": "not measured"},
                       "cost": "sin datos (pendiente)"})
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment)
    assert engine.gate(path, "validate")["ready"]


def test_unmeasured_outcome_placeholders_do_not_change_non_success_verdicts(tmp_path):
    path = tmp_path / "case"
    _, assessment = _decisive_lineage_fixture(
        path, "incumplido", tested_implementation="impl1",
        baseline_refs=["crit1"], result_refs=["base1", "crit1", "t1"],
    )
    assessment.update({"adverse_effects": [{"status": "unknown"}],
                       "cost": "sin datos (pendiente)"})
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment)
    assert engine.gate(path, "validate")["ready"]

    assessment["verdict"] = "no_demostrado"
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment)
    assert engine.gate(path, "validate")["ready"]


@pytest.mark.parametrize("verdict", ("cumplido", "incumplido"))
def test_decisive_result_accepts_implementation_only_chain(tmp_path, verdict):
    path = tmp_path / "case"
    _decisive_lineage_fixture(
        path,
        verdict,
        tested_implementation="impl2",
        baseline_refs=["crit1"],
        result_refs=["base1", "crit1", "t1"],
    )

    items = engine._project(path)["items"]
    assert items["impl2"]["deps"].keys() == {"impl1"}
    assert items["impl1"]["deps"].keys() == {"req1"}
    assert engine.gate(path, "validate")["ready"]
    _accept(path, "validate")


@pytest.mark.parametrize("verdict", ("cumplido", "incumplido"))
def test_decisive_result_does_not_inherit_baseline_test(tmp_path, verdict):
    path = tmp_path / "case"
    result_data, assessment_data = _decisive_lineage_fixture(
        path,
        verdict,
        tested_implementation="impl1",
        baseline_refs=["crit1", "t1"],
        result_refs=["base1", "crit1"],
    )

    items = engine._project(path)["items"]
    assert "t1" in engine._ancestors(items, "res1")
    assert "t1" not in items["res1"]["deps"]
    claim = "success" if verdict == "cumplido" else "rejection"
    missing = (
        f"ass1 {claim} needs a current passed test linked to res1 "
        "for crit1 and implementation of req1"
    )
    status = engine.gate(path, "validate")
    assert status["blockers"] == [missing]
    assert not status["ready"] and not status["accepted"]

    _put(path, "res1", "result", ["base1", "crit1", "t1"], result_data)
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment_data)
    _accept(path, "validate")


@pytest.mark.parametrize("revised_kind", ("test", "implementation"))
def test_decisive_result_loses_acceptance_after_linked_build_revision(tmp_path, revised_kind):
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    _put(path, "crit1", "criterion", ["req1", "i1"],
         {"metric": "count", "threshold": {"operator": ">=", "value": 0.1,
                                           "statistic": "lower_ci"}, "reject": "lower CI below 0.1"})
    test_data = {"passed": True, "command": "synthetic fixture; no external command run"}
    _put(path, "t1", "test", ["impl1", "crit1"], test_data)
    _put(path, "base1", "baseline", ["crit1"],
         {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
          "metric": "count", "value": 0.2, "unit": "count"})
    result_data = {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
                   "effect": {"metric": "count", "estimate": 0.3, "interval": [0.15, 0.4],
                              "design": "randomized fixture", "comparator": "synthetic control",
                              "sample_size": 12, "unit": "count"}}
    assessment_data = {"verdict": "cumplido", "claim_scope": "field",
                       "uncertainty": "synthetic interval", **_synthetic_measured_outcomes()}
    _put(path, "res1", "result", ["base1", "crit1", "t1"], result_data)
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment_data)
    _accept(path, "specify")
    _accept(path, "build")
    _accept(path, "validate")

    if revised_kind == "implementation":
        _put(path, "impl1", "implementation", ["req1"], text="revised implementation")
        assert engine.get_state(path)["items"]["t1"]["stale"]
        _put(path, "t1", "test", ["impl1", "crit1"], test_data)
    else:
        _put(path, "t1", "test", ["impl1", "crit1"],
             {**test_data, "command": "revised synthetic fixture; no external command run"})
    state = engine.get_state(path)
    assert state["items"]["res1"]["stale"]
    assert not state["phases"]["validate"]["accepted"]
    _accept(path, "build")
    with pytest.raises(engine.MethodError, match="phase cannot be accepted"):
        engine.review_phase(path, "validate", "accept", "stale result", "agent:reviewer")

    _put(path, "res1", "result", ["base1", "crit1", "t1"], result_data)
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment_data)
    status = engine.gate(path, "validate")
    assert status["ready"] and not status["accepted"]
    with pytest.raises(engine.MethodError, match="accepted review of its current snapshot"):
        engine.advance(path, "validate", "agent:lead")
    _accept(path, "validate")


def test_success_requires_effect_and_declared_baseline_units_to_match_indicator(tmp_path):
    # The numbers and the field label are synthetic; this checks gate mechanics only.
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    _put(path, "crit1", "criterion", ["req1", "i1"],
         {"metric": "count", "threshold": {"operator": ">=", "value": 0.1, "statistic": "lower_ci"},
          "reject": "lower CI below 0.1"})
    _put(path, "t1", "test", ["impl1", "crit1"],
         {"passed": True, "command": "synthetic fixture; no external command run"})
    baseline = {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
                "metric": "count", "value": 0.2, "unit": "count"}
    effect = {"metric": "count", "estimate": 0.3, "interval": [0.15, 0.4],
              "design": "randomized fixture", "comparator": "synthetic control",
              "sample_size": 12, "unit": "fraction"}
    assessment = {"verdict": "cumplido", "claim_scope": "field", "uncertainty": "synthetic interval",
                  **_synthetic_measured_outcomes()}

    def record_result():
        _put(path, "res1", "result", ["base1", "crit1", "t1"],
             {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
              "effect": effect.copy()})
        _put(path, "ass1", "assessment", ["res1", "r1"], assessment.copy())

    _put(path, "base1", "baseline", ["crit1"], baseline.copy())
    record_result()
    _accept(path, "specify")
    _accept(path, "build")
    assert "ass1 effect unit differs from linked indicator" in engine.gate(path, "validate")["blockers"]
    assert not engine.gate(path, "validate")["ready"]

    assessment["verdict"] = "no_demostrado"
    _put(path, "ass1", "assessment", ["res1", "r1"], assessment.copy())
    _accept(path, "validate")

    assessment["verdict"] = "cumplido"
    effect["unit"] = "count"
    record_result()
    _accept(path, "validate")

    effect["unit"] = ""
    record_result()
    assert "ass1 success lacks a measured effect unit" in engine.gate(path, "validate")["blockers"]

    effect["unit"] = "count"
    baseline.pop("unit")
    _put(path, "base1", "baseline", ["crit1"], baseline.copy())
    record_result()
    missing_unit = engine.gate(path, "validate")
    assert "ass1 success lacks a declared baseline unit" in missing_unit["blockers"]
    assert not missing_unit["ready"] and not missing_unit["accepted"]

    baseline["unit"] = " "
    _put(path, "base1", "baseline", ["crit1"], baseline.copy())
    record_result()
    assert "ass1 success lacks a declared baseline unit" in engine.gate(path, "validate")["blockers"]

    baseline["unit"] = "fraction"
    _put(path, "base1", "baseline", ["crit1"], baseline.copy())
    record_result()
    assert "ass1 baseline unit differs from measured effect" in engine.gate(path, "validate")["blockers"]


def test_success_checks_explicit_criterion_and_threshold_units(tmp_path):
    # Synthetic numbers isolate the unit gate from any claim of field impact.
    path = tmp_path / "case"
    _complete_synthetic_case(path)

    def record_claim(criterion_unit, threshold_unit):
        criterion = {"metric": "count", "unit": criterion_unit,
                     "threshold": {"operator": ">=", "value": 0.1,
                                   "statistic": "lower_ci", "unit": threshold_unit},
                     "reject": "lower CI below 0.1"}
        _put(path, "crit1", "criterion", ["req1", "i1"], criterion)
        _put(path, "t1", "test", ["impl1", "crit1"],
             {"passed": True, "command": "synthetic fixture; no external command run"})
        _put(path, "base1", "baseline", ["crit1"],
             {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
              "metric": "count", "value": 0.2, "unit": "count"})
        _put(path, "res1", "result", ["base1", "crit1", "t1"],
             {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
              "effect": {"metric": "count", "estimate": 0.3, "interval": [0.15, 0.4],
                         "design": "randomized fixture", "comparator": "synthetic control",
                         "sample_size": 12, "unit": "count"}})
        _put(path, "ass1", "assessment", ["res1", "r1"],
             {"verdict": "cumplido", "claim_scope": "field", "uncertainty": "synthetic interval",
              **_synthetic_measured_outcomes()})
        _accept(path, "specify")
        _accept(path, "build")
        return engine.gate(path, "validate")

    for criterion_unit, threshold_unit, expected in (
        ("count", "fraction", "threshold unit differs from measured effect"),
        ("fraction", "count", "criterion unit differs from measured effect"),
        ("count", None, "threshold declares an invalid unit"),
        ("", "count", "criterion declares an invalid unit"),
    ):
        status = record_claim(criterion_unit, threshold_unit)
        assert f"ass1 {expected}" in status["blockers"]
        assert not status["ready"] and not status["accepted"]

    assert record_claim("count", "count")["ready"]
    _accept(path, "validate")


def test_decisive_threshold_preserves_large_integer_precision(tmp_path):
    # These field-labelled values are invented; only exact gate arithmetic is tested.
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    below = 2**53
    threshold = below + 1
    _put(path, "crit1", "criterion", ["req1", "i1"],
         {"metric": "count", "threshold": {"operator": ">=", "value": threshold,
                                           "statistic": "lower_ci"},
          "reject": "upper CI below threshold",
          "reject_test": {"operator": "<", "value": threshold, "statistic": "upper_ci"}})
    _put(path, "t1", "test", ["impl1", "crit1"],
         {"passed": True, "command": "synthetic fixture; no external command run"})
    _put(path, "base1", "baseline", ["crit1"],
         {"origin": "field", "source": "invented fixture", "date": "2026-09-27",
          "metric": "count", "value": below, "unit": "count"})

    def record_claim(value, verdict):
        _put(path, "res1", "result", ["base1", "crit1", "t1"],
             {"origin": "field", "source": "invented fixture", "date": "2026-09-27",
              "effect": {"metric": "count", "estimate": value, "interval": [value, value],
                         "design": "synthetic comparison", "comparator": "invented control",
                         "sample_size": 12, "unit": "count"}})
        _put(path, "ass1", "assessment", ["res1", "r1"],
             {"verdict": verdict, "claim_scope": "field", "uncertainty": "invented interval",
              **_synthetic_measured_outcomes()})
        return engine.gate(path, "validate")

    record_claim(below, "cumplido")
    _accept(path, "specify")
    _accept(path, "build")
    assert "ass1 measured lower_ci does not meet the prior threshold" in \
        engine.gate(path, "validate")["blockers"]
    assert record_claim(threshold, "cumplido")["ready"]
    assert "ass1 measured upper_ci does not meet the prior rejection test" in \
        record_claim(threshold, "incumplido")["blockers"]
    assert record_claim(below, "incumplido")["ready"]


def test_success_rejects_missing_or_ambiguous_linked_indicator_units(tmp_path):
    path = tmp_path / "case"
    _complete_synthetic_case(path)
    _put(path, "crit1", "criterion", ["req1", "i1"],
         {"metric": "count", "threshold": {"operator": ">=", "value": 0.1, "statistic": "lower_ci"},
          "reject": "lower CI below 0.1"})
    _put(path, "t1", "test", ["impl1", "crit1"],
         {"passed": True, "command": "synthetic fixture; no external command run"})
    _put(path, "base1", "baseline", ["crit1"],
         {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
          "metric": "count", "value": 0.2, "unit": "count"})
    _put(path, "res1", "result", ["base1", "crit1", "t1"],
         {"origin": "field", "source": "invented fixture", "date": "2026-09-26",
          "effect": {"metric": "count", "estimate": 0.3, "interval": [0.15, 0.4],
                     "design": "randomized fixture", "comparator": "synthetic control",
                     "sample_size": 12, "unit": "count"}})
    _put(path, "ass1", "assessment", ["res1", "r1"],
         {"verdict": "cumplido", "claim_scope": "field", "uncertainty": "synthetic interval",
          **_synthetic_measured_outcomes()})

    # Exercise the success guard directly for malformed graph states that an
    # earlier study gate would already reject.
    items = engine._project(path)["items"]
    items["i1"]["data"]["unit"] = ""
    assert "ass1 success lacks a declared linked indicator unit" in \
        engine._success_claim_issues(items, items["ass1"], "fixture")

    items = engine._project(path)["items"]
    extra = {**items["i1"], "id": "i_extra", "data": {**items["i1"]["data"]}}
    items["i_extra"] = extra
    items["crit1"]["deps"]["i_extra"] = 1
    assert not engine._success_claim_issues(items, items["ass1"], "fixture")
    extra["data"]["unit"] = "fraction"
    assert "ass1 success has ambiguous linked indicator units" in \
        engine._success_claim_issues(items, items["ass1"], "fixture")
