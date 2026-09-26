"""Twenty-one developmental fault injections against durable workflow behavior.

Run with pytest for regression checks or directly with ``--report`` for a
machine-readable record. The synthetic fixtures do not prove real-world impact,
source authenticity, or independently reviewed methodology quality.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

from specorganon import engine
from specorganon.ledger import read_project
from specorganon.workflow import PHASES


ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "C01": ("contradiction", "Two same-scope numeric sources disagree"),
    "C02": ("contradiction", "Reported product disagrees with operands"),
    "C03": ("contradiction", "Actor disputes an accepted frame"),
    "C04": ("contradiction", "Numeric disagreement exceeds declared tolerance"),
    "C05": ("contradiction", "Observation contests a working assumption"),
    "C06": ("contradiction", "Reviewed resolution loses validity after revision"),
    "E01": ("insufficient_evidence", "Evidence has no source"),
    "E02": ("insufficient_evidence", "Evidence has no date"),
    "E03": ("insufficient_evidence", "Evidence has no locator"),
    "E04": ("insufficient_evidence", "Observed evidence lacks collection method"),
    "E05": ("insufficient_evidence", "Protocol lacks a comparison"),
    "E06": ("insufficient_evidence", "Success indicator has no evidence path"),
    "A01": ("assumption_change", "Revised assumption invalidates question branch"),
    "A02": ("assumption_change", "Revised assumption invalidates protocol branch"),
    "A03": ("assumption_change", "Revised assumption invalidates observation branch"),
    "A04": ("assumption_change", "Revised assumption invalidates synthesis branch"),
    "A05": ("assumption_change", "Revised assumption invalidates one intervention option"),
    "A06": ("assumption_change", "Revised assumption invalidates decision branch"),
    "N01": ("unapproved_norm", "Norm has no human approval"),
    "N02": ("unapproved_norm", "Revised norm loses its former approval"),
    "N03": ("unapproved_norm", "Revised decision loses its former approval"),
}


def _seq(path: Path) -> int:
    return len(read_project(path)["events"])


def _put(path: Path, item_id: str, kind: str, refs=(), data=None, *, text=None) -> None:
    engine.put_item(path, item_id, kind, text or item_id, list(refs), data or {}, "agent:fixture-author")


def _accept(path: Path, phase: str) -> None:
    status = engine.gate(path, phase)
    assert status["ready"], (phase, status["blockers"])
    engine.review_phase(path, phase, "accept", "synthetic fixture review", "agent:fixture-reviewer")
    engine.advance(path, phase, "agent:fixture-lead")
    assert engine.gate(path, phase)["accepted"]


def _blocked(path: Path, phase: str, fragment: str) -> dict:
    status = engine.gate(path, phase)
    assert not status["ready"], (phase, status)
    assert not status["accepted"], (phase, status)
    assert any(fragment in blocker for blocker in status["blockers"]), (phase, fragment, status["blockers"])
    seq_before = _seq(path)
    with pytest.raises(engine.MethodError):
        engine.advance(path, phase, "agent:fixture-lead")
    assert _seq(path) == seq_before, "a rejected advance must not append to the ledger"
    return {"phase": phase, "accepted": status["accepted"], "blockers": status["blockers"], "ledger_events": seq_before}


def _frame(path: Path) -> None:
    engine.create_case(path, "Development injection fixture", "synthetic", "agent:fixture-lead", approval_policy="fixture")
    _put(path, "p1", "problem")
    _put(path, "a1", "actor", ["p1"])
    _put(path, "b1", "boundary", ["p1"])
    _accept(path, "frame")


def _critique(path: Path, *, approve_norm: bool = True) -> None:
    _put(path, "c1", "concept", ["p1"])
    _put(path, "s1", "assumption", ["p1"])
    _put(path, "f1", "frame_option", ["p1"], text="Scope A")
    _put(path, "f2", "frame_option", ["p1"], text="Scope B")
    _put(path, "n1", "norm", ["p1", "a1"])
    if approve_norm:
        engine.approve(path, "n1", "fixture attestation; no real human approval", "human:fixture")
        _accept(path, "critique")


def _full(path: Path, *, assumption_target: str | None = None, evidence_tolerance: float = 0.0) -> None:
    """An accepted synthetic graph with one optional dependency on assumption s1."""
    _frame(path)
    _critique(path)

    def refs(target: str, base: list[str]) -> list[str]:
        return base + (["s1"] if assumption_target == target else [])

    _put(path, "q1", "question", refs("q1", ["p1"]))
    _put(path, "h1", "hypothesis", ["q1"])
    _put(path, "pr1", "protocol", refs("pr1", ["q1", "h1"]), {
        "population": "synthetic", "method": "fixture enumeration",
        "comparison": "fixture baseline", "uncertainty": "unknown",
    })
    _put(path, "e0", "evidence", ["pr1"], {
        "origin": "simulated", "source": "fixture", "date": "2026-09-26", "locator": "predeclared synthetic context",
    })
    _put(path, "i1", "indicator", ["p1", "n1", "e0"], {"metric": "count", "unit": "items"})
    _accept(path, "study")

    _put(path, "e1", "evidence", refs("e1", ["pr1"]), {
        "origin": "simulated", "source": "fixture", "date": "2026-09-26", "locator": "synthetic observation",
        "metric_key": "count", "scope": "synthetic population", "unit": "items", "value": 10,
        "tolerance": evidence_tolerance,
    })
    _put(path, "inf1", "inference", ["e1", "h1"])
    _accept(path, "observe")

    _put(path, "syn1", "synthesis", refs("syn1", ["inf1", "e1"]))
    _put(path, "u1", "uncertainty", ["syn1"])
    _accept(path, "explain")

    _put(path, "o1", "option", refs("o1", ["syn1", "n1"]))
    _put(path, "o2", "option", ["syn1", "n1"])
    _put(path, "cmp1", "comparison", ["o1", "o2"])
    _put(path, "r1", "risk", ["o1"])
    _accept(path, "compare")

    _put(path, "d1", "decision", refs("d1", ["cmp1", "n1", "e1"]))
    engine.approve(path, "d1", "fixture attestation; no real human approval", "human:fixture")
    _put(path, "req1", "requirement", ["d1"])
    _put(path, "crit1", "criterion", ["req1", "i1"], {
        "metric": "count", "threshold": 0, "reject": "negative count",
    })
    _accept(path, "specify")

    _put(path, "impl1", "implementation", ["req1"])
    _put(path, "t1", "test", ["impl1", "crit1"], {
        "passed": True, "command": "fixture only; no external command",
    })
    _accept(path, "build")

    _put(path, "base1", "baseline", ["crit1"], {
        "origin": "simulation", "source": "fixture", "date": "2026-09-26",
    })
    _put(path, "res1", "result", ["base1", "crit1"], {
        "origin": "simulation", "source": "fixture", "date": "2026-09-26",
    })
    _put(path, "ass1", "assessment", ["res1", "r1"], {
        "verdict": "no_demostrado", "claim_scope": "field", "uncertainty": "not measured",
        "adverse_effects": "not measured", "cost": "not measured",
    })
    _accept(path, "validate")
    assert all(engine.gate(path, phase.id)["accepted"] for phase in PHASES)


def _run_contradiction(case_id: str, path: Path) -> dict:
    _full(path, evidence_tolerance=0.5 if case_id == "C04" else 0.0)
    if case_id in {"C01", "C04"}:
        value = 12 if case_id == "C01" else 10.6
        _put(path, "e2", "evidence", ["pr1"], {
            "origin": "published", "source": "second fixture", "date": "2026-09-26", "locator": "synthetic second record",
            "metric_key": "count", "scope": "synthetic population", "unit": "items", "value": value,
            "tolerance": 0.5 if case_id == "C04" else 0,
        })
        state = engine.get_state(path)
        assert any("conflicting metric" in issue for issue in state["items"]["e1"]["issues"])
        assert any("conflicting metric" in issue for issue in state["items"]["e2"]["issues"])
        assert not state["phases"]["validate"]["accepted"]
        return _blocked(path, "observe", "conflicting metric") | {"affected_items": ["e1", "e2"]}
    if case_id == "C02":
        data = dict(engine.get_state(path)["items"]["e1"]["data"])
        data["calculation"] = {"operator": "product", "operands": [4, 3], "tolerance": 0}
        _put(path, "e1", "evidence", ["pr1"], data)
        state = engine.get_state(path)
        assert state["items"]["inf1"]["stale"]
        assert any("differs from recomputed" in issue for issue in state["items"]["e1"]["issues"])
        return _blocked(path, "observe", "differs from recomputed") | {"stale_items": ["inf1"]}
    if case_id == "C03":
        event = engine.challenge(path, "p1", "a1", "actor contests the accepted scope", "agent:fixture-reviewer")
        state = engine.get_state(path)
        assert state["items"]["req1"]["contested"]
        assert any(challenge["seq"] == event["seq"] for challenge in state["open_challenges"])
        return _blocked(path, "frame", "unresolved contradiction") | {"contested_items": ["p1", "req1"]}
    if case_id == "C05":
        engine.challenge(path, "s1", "e1", "observation contradicts working assumption", "agent:fixture-reviewer")
        state = engine.get_state(path)
        assert state["items"]["s1"]["contested"]
        assert state["items"]["req1"]["contested"]
        return _blocked(path, "critique", "unresolved contradiction") | {"contested_items": ["s1", "e1", "req1"]}
    if case_id == "C06":
        event = engine.challenge(path, "e0", "e1", "records disagree about provenance", "agent:fixture-reviewer")
        _put(path, "syn2", "synthesis", ["e0", "e1"], text="The two records concern different collection paths")
        engine.review_item(path, "syn2", "accept", "fixture review of both records", "agent:fixture-reviewer")
        engine.resolve_challenge(path, event["seq"], "syn2", "agent:fixture-lead")
        assert not engine.get_state(path)["open_challenges"]
        _put(path, "syn2", "synthesis", ["e0", "e1"], text="Revised resolution requires a new review")
        state = engine.get_state(path)
        assert any(challenge["seq"] == event["seq"] for challenge in state["open_challenges"])
        assert state["items"]["i1"]["contested"]
        return _blocked(path, "observe", "unresolved contradiction") | {"reopened_challenge_seq": event["seq"], "contested_items": ["i1", "e1"]}
    raise AssertionError(case_id)


def _run_evidence(case_id: str, path: Path) -> dict:
    _full(path)
    if case_id in {"E01", "E02", "E03", "E04"}:
        data = dict(engine.get_state(path)["items"]["e1"]["data"])
        expected = {"E01": "lacks source", "E02": "lacks date", "E03": "lacks locator", "E04": "lacks collection method"}[case_id]
        if case_id == "E01":
            data.pop("source")
        elif case_id == "E02":
            data.pop("date")
        elif case_id == "E03":
            data.pop("locator")
        else:
            data["origin"] = "observed"
            data.pop("method", None)
        _put(path, "e1", "evidence", ["pr1"], data)
        state = engine.get_state(path)
        assert state["items"]["inf1"]["stale"]
        assert state["items"]["req1"]["stale"]
        return _blocked(path, "observe", expected) | {"stale_items": ["inf1", "req1"]}
    if case_id == "E05":
        data = dict(engine.get_state(path)["items"]["pr1"]["data"])
        data.pop("comparison")
        _put(path, "pr1", "protocol", ["q1", "h1"], data)
        state = engine.get_state(path)
        assert state["items"]["e1"]["stale"]
        assert state["items"]["i1"]["stale"]
        return _blocked(path, "study", "protocol lacks comparison") | {"stale_items": ["e1", "i1"]}
    if case_id == "E06":
        _put(path, "i1", "indicator", ["p1", "n1"], {"metric": "count", "unit": "items"})
        state = engine.get_state(path)
        assert not state["items"]["i1"]["stale"]
        assert state["items"]["crit1"]["stale"]
        # Study does not require empirical backing; specification does.
        assert state["phases"]["study"]["ready"]
        return _blocked(path, "specify", "lacks a path to evidence") | {
            "stale_items": ["crit1"], "negative_finding": "indicator has no evidence path while study gate remains ready",
        }
    raise AssertionError(case_id)


def _run_assumption(case_id: str, path: Path) -> dict:
    targets = {
        "A01": ("q1", "h1", "f1", "study"),
        "A02": ("pr1", "e1", "q1", "study"),
        "A03": ("e1", "inf1", "e0", "observe"),
        "A04": ("syn1", "o1", "e1", "explain"),
        "A05": ("o1", "cmp1", "o2", "compare"),
        "A06": ("d1", "req1", "cmp1", "specify"),
    }
    target, downstream, unaffected, phase = targets[case_id]
    _full(path, assumption_target=target)
    _put(path, "s1", "assumption", ["p1"], text="Revised synthetic assumption")
    state = engine.get_state(path)
    assert state["items"][target]["stale"]
    assert state["items"][downstream]["stale"]
    assert not state["items"][unaffected]["stale"]
    assert state["items"]["req1"]["stale"]
    assert not state["phases"][phase]["accepted"]
    trace = engine.trace(path, "s1")
    dependent_ids = {item["id"] for item in trace["dependents"]}
    assert target in dependent_ids
    assert all(state["items"][item_id]["stale"] for item_id in dependent_ids), dependent_ids
    return _blocked(path, phase, "older revision") | {
        "revised_assumption": "s1", "stale_items": sorted(dependent_ids), "unaffected_item": unaffected,
    }


def _run_norm(case_id: str, path: Path) -> dict:
    if case_id == "N01":
        _frame(path)
        _critique(path, approve_norm=False)
        state = engine.get_state(path)
        assert not state["items"]["n1"]["approved"]
        seq_before = _seq(path)
        with pytest.raises(engine.MethodError, match="approval actor must be human"):
            engine.approve(path, "n1", "AI approval attempt", "agent:fixture-author")
        assert _seq(path) == seq_before
        outcome = _blocked(path, "critique", "requires a fixture approval")
        with pytest.raises(engine.MethodError, match="fixture approval requires human:fixture"):
            engine.approve(path, "n1", "fictional approval attempt", "human:fictional-fixture")
        assert _seq(path) == seq_before
        engine.approve(path, "n1", "explicit synthetic fixture approval", "human:fixture")
        assert engine.gate(path, "critique")["ready"]
        seq_after_approval = _seq(path)
        os.environ.pop("ORGANON_ALLOW_FIXTURES")
        try:
            state_without_flag = engine.get_state(path)
            assert state_without_flag["approval_trust"] == "unavailable"
            assert not state_without_flag["items"]["n1"]["approved"]
            assert not state_without_flag["phases"]["critique"]["ready"]
            with pytest.raises(engine.MethodError, match="fixture approval is disabled"):
                engine.approve(path, "n1", "fixture approval without runtime flag", "human:fixture")
            assert _seq(path) == seq_after_approval
        finally:
            os.environ["ORGANON_ALLOW_FIXTURES"] = "1"
        assert engine.get_state(path)["items"]["n1"]["approved"]
        return outcome | {"unapproved_item": "n1", "rejected_actors": ["agent:fixture-author", "human:fictional-fixture"],
                          "fixture_approval_status": engine.get_state(path)["items"]["n1"]["approval_status"],
                          "replay_without_runtime_flag": "approval unverified; gate blocked; no new event"}
    _full(path)
    if case_id == "N02":
        _put(path, "n1", "norm", ["p1", "a1"], text="Revised fixture norm requiring fresh human decision")
        state = engine.get_state(path)
        assert not state["items"]["n1"]["approved"]
        assert state["items"]["d1"]["stale"]
        assert state["items"]["req1"]["stale"]
        outcome = _blocked(path, "critique", "requires a fixture approval")
        assert not engine.gate(path, "specify")["accepted"]
        return outcome | {"unapproved_item": "n1", "stale_items": ["d1", "req1"]}
    if case_id == "N03":
        _put(path, "d1", "decision", ["cmp1", "n1", "e1"], text="Revised fixture decision requiring fresh human approval")
        state = engine.get_state(path)
        assert not state["items"]["d1"]["approved"]
        assert state["items"]["req1"]["stale"]
        assert state["items"]["impl1"]["stale"]
        return _blocked(path, "specify", "requires a fixture approval") | {
            "unapproved_item": "d1", "stale_items": ["req1", "impl1"],
        }
    raise AssertionError(case_id)


@contextmanager
def _fixture_capability():
    """Confine the synthetic approval capability to a single test scenario."""
    previous = os.environ.get("ORGANON_ALLOW_FIXTURES")
    os.environ["ORGANON_ALLOW_FIXTURES"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("ORGANON_ALLOW_FIXTURES", None)
        else:
            os.environ["ORGANON_ALLOW_FIXTURES"] = previous


def _run_case_enabled(case_id: str, path: Path) -> dict:
    group, description = CASES[case_id]
    if group == "contradiction":
        evidence = _run_contradiction(case_id, path)
    elif group == "insufficient_evidence":
        evidence = _run_evidence(case_id, path)
    elif group == "assumption_change":
        evidence = _run_assumption(case_id, path)
    else:
        evidence = _run_norm(case_id, path)
    # read_project verifies the complete hash chain after all mutations.
    ledger = read_project(path)
    assert len(ledger["events"]) == _seq(path)
    evidence["ledger_head_hash"] = ledger["events"][-1]["hash"]
    return {"id": case_id, "group": group, "scenario": description, "status": "pass", "evidence": evidence}


def run_case(case_id: str, path: Path) -> dict:
    with _fixture_capability():
        return _run_case_enabled(case_id, path)


@pytest.mark.parametrize("case_id", list(CASES))
def test_development_injection(case_id: str, tmp_path: Path) -> None:
    previous = os.environ.get("ORGANON_ALLOW_FIXTURES")
    run_case(case_id, tmp_path / case_id)
    assert os.environ.get("ORGANON_ALLOW_FIXTURES") == previous


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    results = []
    with tempfile.TemporaryDirectory(prefix="organon-injection-bank-") as folder:
        for case_id, (group, description) in CASES.items():
            try:
                results.append(run_case(case_id, Path(folder) / case_id))
            except Exception as exc:  # development record preserves every failure
                results.append({
                    "id": case_id, "group": group, "scenario": description, "status": "fail",
                    "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc(),
                })
    report = {
        "kind": "development_behavioral_injection_bank",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "classification": "synthetic development regression; not sealed confirmatory or independent evaluation",
        "fixture_runtime_capability": "ORGANON_ALLOW_FIXTURES=1 scoped to each synthetic case and restored afterward",
        "command": "uv run python tests/test_injection_bank.py --report experiments/development/injection_bank_2026-09-26.json",
        "inputs_sha256": {
            str(path.relative_to(ROOT)): _sha256(path) for path in (
                ROOT / "GOAL.md",
                ROOT / "docs/protocolo_experimental.md",
                ROOT / "src/specorganon/engine.py",
                ROOT / "src/specorganon/ledger.py",
                ROOT / "src/specorganon/workflow.py",
                ROOT / "tests/test_injection_bank.py",
            )
        },
        "counts": {
            "total": len(results), "pass": sum(result["status"] == "pass" for result in results),
            "fail": sum(result["status"] == "fail" for result in results),
            **{group: sum(result["group"] == group for result in results) for group in sorted({item[0] for item in CASES.values()})},
        },
        "results": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{report['counts']['pass']}/{report['counts']['total']} passed; report: {args.report}")
    return 1 if report["counts"]["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
