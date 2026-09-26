"""The manifest is a synthetic mechanics fixture, never empirical evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from specorganon import engine
from specorganon.ledger import read_project
from specorganon.runner import ManifestError, next_task, run_manifest
from specorganon.workflow import PHASES


MANIFEST = Path(__file__).resolve().parents[1] / "workflows" / "synthetic_full.json"
pytestmark = pytest.mark.usefixtures("enable_fixture_policy")


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _subprocess_run(case: Path) -> dict:
    code = (
        "import json, sys; "
        "from specorganon.runner import run_manifest; "
        "manifest=json.load(open(sys.argv[2], encoding='utf-8')); "
        "print(json.dumps(run_manifest(sys.argv[1], manifest, 'agent:runner')))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(case), str(MANIFEST)],
        text=True, capture_output=True, check=True,
    )
    return json.loads(result.stdout)


def test_manifest_restarts_and_completes_synthetic_case(tmp_path):
    case = tmp_path / "case"
    engine.create_case(case, "Synthetic runner control", "fixture", "human:fixture", approval_policy="fixture")
    first = run_manifest(case, _manifest(), "agent:runner")
    assert first["status"] == "waiting"
    assert first["reason"] == "independent_review_required"
    assert first["next"]["phase"] == "frame"
    assert first["next"]["role"] == "reviewer"
    assert {item["id"] for item in first["next"]["artifacts"]["items"]} == {"p1", "a1", "b1"}
    revision = engine.get_state(case)["revision"]
    restarted = _subprocess_run(case)
    assert restarted["reason"] == "independent_review_required"
    assert restarted["applied"] == 0
    assert restarted["skipped"] == 3
    assert engine.get_state(case)["revision"] == revision

    decisions = []
    for _ in range(24):
        task = next_task(case)
        if task["status"] == "done":
            break
        if task["action"] == "human_approval":
            for target in task["approval_targets"]:
                engine.approve(case, target["id"], "Explicit synthetic fixture attestation", "human:fixture")
                decisions.append(("approve", target["id"]))
        elif task["action"] == "review_phase":
            engine.review_phase(case, task["phase"], "accept", "Independent synthetic fixture review", "agent:reviewer")
            decisions.append(("review", task["phase"]))
        else:
            pytest.fail(f"unexpected task during replay: {task['action']} {task['blockers']}")
        result = _subprocess_run(case)
        assert result["status"] in {"waiting", "complete"}
    else:
        pytest.fail("workflow did not reach final phase within its decision budget")

    state = engine.get_state(case)
    assert len(decisions) == 11  # Nine independent reviews and two human approvals.
    assert len(state["items"]) == 29
    assert all(state["phases"][phase.id]["accepted"] for phase in PHASES)
    assert state["items"]["ass1"]["data"]["verdict"] == "no_demostrado"
    assert all(event["kind"] != "approval" or event["actor"] == "human:fixture" for event in read_project(case)["events"])
    revision = state["revision"]
    again = _subprocess_run(case)
    assert again["status"] == "complete"
    assert again["applied"] == 0
    assert again["skipped"] == len(_manifest()["steps"])
    assert engine.get_state(case)["revision"] == revision


def test_next_task_is_bounded_and_exposes_versioned_inputs(tmp_path):
    case = tmp_path / "case"
    engine.create_case(case, "Context control", "fixture", "human:fixture", approval_policy="fixture")
    engine.put_item(case, "p1", "problem", "x" * 900, [], {}, "agent:writer")
    for index in range(30):
        engine.put_item(case, f"a{index}", "actor", f"actor {index}", ["p1"], {}, "agent:writer")
    engine.put_item(case, "b1", "boundary", "fixture boundary", ["p1", *(f"a{index}" for index in range(30))], {}, "agent:writer")
    task = next_task(case, {"reviewer": "agent:independent"})
    assert task["action"] == "review_phase"
    assert task["actor"] == "agent:independent"
    assert len(task["artifacts"]["items"]) == 24
    assert task["artifacts"]["omitted"] == 8
    assert all(item["version"] == 1 for item in task["artifacts"]["items"])
    assert task["artifacts"]["items"][0]["omitted_refs"] == 19
    assert len(json.dumps(task)) < 25_000
    with pytest.raises(ManifestError):
        next_task(case, {"human": ""})


def test_invalid_manifest_is_rejected_before_any_write(tmp_path):
    case = tmp_path / "case"
    engine.create_case(case, "Invalid control", "fixture", "human:fixture", approval_policy="fixture")
    good = {"op": "put", "id": "p1", "kind": "problem", "text": "Problem", "refs": [], "data": {}}
    bad_shapes = [
        {"schema": 1, "steps": [good, {"op": "approve", "id": "n1"}]},
        {"schema": 1, "steps": [good, {"op": "put", "id": "a1", "kind": [], "text": "Actor", "refs": [], "data": {}}]},
        {"schema": 1, "steps": [good, {"op": "put", "id": "a1", "kind": "actor", "text": "Actor", "refs": ["later"], "data": {}}]},
        {"schema": 1, "steps": [good, {"op": "advance", "phase": []}]},
        {"schema": 1, "steps": [good, {"op": "put", "id": "p1", "kind": "problem", "text": "Other", "refs": [], "data": {}}]},
    ]
    before = (case / "organon.json").read_bytes()
    for manifest in bad_shapes:
        with pytest.raises(ManifestError):
            run_manifest(case, manifest, "agent:runner")
        assert (case / "organon.json").read_bytes() == before


def test_checkpoint_divergence_and_stale_dependency_need_explicit_revision(tmp_path):
    case = tmp_path / "case"
    engine.create_case(case, "Revision control", "fixture", "human:fixture", approval_policy="fixture")
    manifest = {"schema": 1, "steps": [
        {"op": "put", "id": "p1", "kind": "problem", "text": "Initial", "refs": [], "data": {}},
        {"op": "put", "id": "a1", "kind": "actor", "text": "Actor", "refs": ["p1"], "data": {}},
    ]}
    result = run_manifest(case, manifest, "agent:runner")
    assert result["applied"] == 2
    engine.put_item(case, "p1", "problem", "Revised", [], {}, "agent:researcher")
    task = next_task(case)
    assert task["action"] == "repair_artifacts"
    assert any("older revision" in blocker for blocker in task["blockers"])
    with pytest.raises(ManifestError, match="expected item p1 version 0, found 2"):
        run_manifest(case, manifest, "agent:runner")
    assert engine.get_state(case)["revision"] == 3


def test_explicit_item_revision_is_idempotent(tmp_path):
    case = tmp_path / "case"
    engine.create_case(case, "Explicit revision", "fixture", "human:fixture", approval_policy="fixture")
    engine.put_item(case, "p1", "problem", "Initial", [], {}, "agent:researcher")
    manifest = {"schema": 1, "steps": [
        {"op": "put", "id": "p1", "kind": "problem", "text": "Revised", "refs": [], "data": {}, "expected_version": 1},
    ]}
    first = run_manifest(case, manifest, "agent:runner")
    assert first["applied"] == 1
    assert engine.get_state(case)["items"]["p1"]["version"] == 2
    again = _subprocess_custom(case, manifest)
    assert again["applied"] == 0 and again["skipped"] == 1
    assert engine.get_state(case)["revision"] == 2


def test_concurrent_replays_do_not_duplicate_events(tmp_path):
    case = tmp_path / "case"
    engine.create_case(case, "Concurrent replay", "fixture", "human:fixture", approval_policy="fixture")
    manifest = {"schema": 1, "steps": [
        {"op": "put", "id": "p1", "kind": "problem", "text": "Problem", "refs": [], "data": {}},
        {"op": "put", "id": "a1", "kind": "actor", "text": "Actor", "refs": ["p1"], "data": {}},
        {"op": "put", "id": "b1", "kind": "boundary", "text": "Boundary", "refs": ["p1"], "data": {}},
    ]}
    code = (
        "import json, sys; "
        "from specorganon.runner import run_manifest; "
        "print(json.dumps(run_manifest(sys.argv[1], json.loads(sys.argv[2]), 'agent:runner')))"
    )
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(case), json.dumps(manifest)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    results = [process.communicate(timeout=10) for process in processes]
    assert all(process.returncode == 0 for process in processes), results
    assert sorted(json.loads(stdout)["applied"] for stdout, _ in results) == [0, 3]
    assert len(read_project(case)["events"]) == 3


def _subprocess_custom(case: Path, manifest: dict) -> dict:
    code = (
        "import json, sys; "
        "from specorganon.runner import run_manifest; "
        "print(json.dumps(run_manifest(sys.argv[1], json.loads(sys.argv[2]), 'agent:runner')))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(case), json.dumps(manifest)],
        text=True, capture_output=True, check=True,
    )
    return json.loads(result.stdout)


def test_next_task_does_not_recommend_review_when_gate_has_semantic_blocker(tmp_path):
    case = tmp_path / "case"
    engine.create_case(case, "Semantic blocker", "fixture", "human:fixture", approval_policy="fixture")
    engine.put_item(case, "p1", "problem", "Problem", [], {}, "agent:writer")
    engine.put_item(case, "a1", "actor", "Actor", ["p1"], {}, "agent:writer")
    engine.put_item(case, "b1", "boundary", "Boundary", ["p1"], {}, "agent:writer")
    engine.review_phase(case, "frame", "accept", "Fixture review", "agent:reviewer")
    engine.advance(case, "frame", "agent:writer")
    for id, kind, text, refs in [
        ("c1", "concept", "Concept", ["p1"]),
        ("s1", "assumption", "Assumption", ["p1"]),
        ("f1", "frame_option", "Same option", ["p1"]),
        ("f2", "frame_option", "Same option", ["p1"]),
        ("n1", "norm", "Norm", ["p1", "a1"]),
    ]:
        engine.put_item(case, id, kind, text, refs, {}, "agent:writer")
    engine.approve(case, "n1", "Fixture decision", "human:fixture")
    task = next_task(case)
    assert task["missing"] == []
    assert task["action"] == "repair_artifacts"
    assert any("frame options must differ" in blocker for blocker in task["blockers"])


def test_contradiction_stops_manifest_without_advancing(tmp_path):
    case = tmp_path / "case"
    engine.create_case(case, "Challenge control", "fixture", "human:fixture", approval_policy="fixture")
    engine.put_item(case, "p1", "problem", "Problem", [], {}, "agent:writer")
    engine.put_item(case, "a1", "actor", "Actor", ["p1"], {}, "agent:writer")
    engine.challenge(case, "p1", "a1", "Framing disputed", "agent:reviewer")
    manifest = {"schema": 1, "steps": [
        {"op": "put", "id": "p1", "kind": "problem", "text": "Problem", "refs": [], "data": {}},
        {"op": "put", "id": "a1", "kind": "actor", "text": "Actor", "refs": ["p1"], "data": {}},
        {"op": "put", "id": "b1", "kind": "boundary", "text": "Boundary", "refs": ["p1"], "data": {}},
    ]}
    result = run_manifest(case, manifest, "agent:runner")
    assert result["reason"] == "contradiction"
    assert result["next"]["action"] == "resolve_contradiction"
    assert "b1" in engine.get_state(case)["items"]
    assert engine.get_state(case)["items"]["b1"]["contested"]
    assert not engine.gate(case, "frame")["ready"]


def test_runner_repairs_stale_item_and_keeps_unrelated_branch_open(tmp_path):
    case = tmp_path / "case"
    engine.create_case(case, "Repair and branching", "fixture", "human:fixture", approval_policy="fixture")
    engine.put_item(case, "p1", "problem", "First framing", [], {}, "agent:writer")
    engine.put_item(case, "a1", "actor", "Affected group", ["p1"], {}, "agent:writer")
    engine.put_item(case, "p1", "problem", "Revised framing", [], {}, "agent:writer")
    assert engine.get_state(case)["items"]["a1"]["stale"]
    repair = {"schema": 1, "steps": [
        {"op": "put", "id": "a1", "kind": "actor", "text": "Affected group under revised framing", "refs": ["p1"], "data": {}, "expected_version": 1},
    ]}
    result = run_manifest(case, repair, "agent:runner")
    assert result["applied"] == 1
    assert not engine.get_state(case)["items"]["a1"]["stale"]

    engine.challenge(case, "p1", "a1", "Framing disputed", "agent:reviewer")
    independent = {"schema": 1, "steps": [
        {"op": "put", "id": "p2", "kind": "problem", "text": "Independent branch", "refs": [], "data": {}},
    ]}
    result = run_manifest(case, independent, "agent:runner")
    assert result["applied"] == 1
    assert "p2" in engine.get_state(case)["items"]
    assert not engine.get_state(case)["items"]["p2"]["contested"]
    assert result["next"]["action"] == "resolve_contradiction"
