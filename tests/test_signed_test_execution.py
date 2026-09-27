"""A signed test needs a current executor receipt; declared success is insufficient."""

from __future__ import annotations

import base64
import json
import shlex
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from specorganon import approval, engine, runner
from specorganon.ledger import append_event, read_project


EXECUTOR = "executor:synthetic"
AUTHOR = "agent:writer"
REVIEWER = "agent:reviewer"
APPROVER = "human:approver"
ARGV = ["python3", "-c", "print('synthetic test')"]
REPORT = {
    "schema": 1,
    "argv": ARGV,
    "exit_code": 0,
    "timed_out": False,
    "stdout_sha256": "0" * 64,
    "stderr_sha256": "0" * 64,
    "artifacts": [{"path": "results/output.txt", "sha256": "1" * 64}],
}


def _public(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def _sign(key: Ed25519PrivateKey, challenge: dict) -> str:
    return base64.b64encode(key.sign(base64.b64decode(challenge["message_base64"]))).decode("ascii")


def _register(case: Path, registry: Path, executor: Ed25519PrivateKey,
              reviewer: Ed25519PrivateKey | None = None,
              approver: Ed25519PrivateKey | None = None) -> None:
    project = read_project(case)["project"]
    registry.write_text(json.dumps({"schema": 2, "cases": {project["case_id"]: {
        "path": str(case.resolve(strict=True)),
        "project_sha256": approval.project_fingerprint(project),
        "approvers": {APPROVER: _public(approver)} if approver else {},
        "phase_reviewers": {REVIEWER: _public(reviewer)} if reviewer else {},
        "test_executors": {EXECUTOR: _public(executor)},
    }}}), encoding="utf-8")


def _case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Ed25519PrivateKey]:
    case, registry = tmp_path / "case", tmp_path / "registry.json"
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(registry))
    engine.create_case(case, "Signed test", "synthetic", AUTHOR)
    executor = Ed25519PrivateKey.generate()
    _register(case, registry, executor)
    engine.put_item(case, "p1", "problem", "A declared problem", [], {}, AUTHOR)
    engine.put_item(case, "req1", "requirement", "A traceable requirement", ["p1"], {}, AUTHOR)
    engine.put_item(case, "crit1", "criterion", "A prior criterion", ["req1"], {
        "metric": "count", "threshold": 0, "reject": "count < 0",
    }, AUTHOR)
    engine.put_item(case, "impl1", "implementation", "The implementation", ["req1"], {}, AUTHOR)
    engine.put_item(case, "t1", "test", "A declared test", ["impl1", "crit1"], {
        "passed": True, "argv": ARGV, "command": shlex.join(ARGV),
    }, AUTHOR)
    return case, registry, executor


def _record(case: Path, key: Ed25519PrivateKey, report: dict = REPORT) -> dict:
    challenge = engine.test_execution_challenge(case, "t1", report, EXECUTOR)
    return engine.record_test_execution(case, "t1", report, EXECUTOR, _sign(key, challenge))


def test_declared_pass_is_blocked_until_signed_receipt_then_failure_revokes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, _, key = _case(tmp_path, monkeypatch)
    missing = engine.get_state(case)["items"]["t1"]
    assert missing["test_execution_status"] == "missing"
    assert missing["issues"] and not engine.gate(case, "build")["ready"]
    first = _record(case, key)
    passed = engine.get_state(case)["items"]["t1"]
    assert passed["test_execution_status"] == "signed_passed"
    assert passed["test_execution_provenance"] == (first["seq"], first["hash"])
    assert passed["issues"] == []

    failed_report = {**REPORT, "exit_code": 2}
    second = _record(case, key, failed_report)
    failed = engine.get_state(case)["items"]["t1"]
    assert failed["test_execution_status"] == "signed_failed"
    assert failed["test_execution_provenance"] == (second["seq"], second["hash"])
    assert any("failed" in issue for issue in failed["issues"])
    assert any("t1" in blocker for blocker in engine.gate(case, "build")["blockers"])

    forged = append_event(case, "test_execution", {
        **second["payload"], "report": REPORT, "signature": "invalid",
    }, EXECUTOR, expected_seq=engine.get_state(case)["revision"])
    state = engine.get_state(case)
    assert state["test_execution_history"][-1]["seq"] == forged["seq"]
    assert state["test_execution_history"][-1]["signature_verified"] is False
    assert state["items"]["t1"]["test_execution_provenance"] == (second["seq"], second["hash"])
    assert state["items"]["t1"]["test_execution_status"] == "signed_failed"


def test_report_and_signature_must_bind_exact_command_version_and_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, _, key = _case(tmp_path, monkeypatch)
    initial = (case / "organon.json").read_bytes()
    for report in (
        {**REPORT, "argv": ["true"]},
        {**REPORT, "exit_code": True},
        {**REPORT, "stdout_sha256": "A" * 64},
        {**REPORT, "artifacts": [{"path": "../escape", "sha256": "1" * 64}]},
        {**REPORT, "artifacts": [REPORT["artifacts"][0]] * 2},
        {**REPORT, "artifacts": [], "argv": ARGV * 129},
    ):
        with pytest.raises(engine.MethodError):
            engine.test_execution_challenge(case, "t1", report, EXECUTOR)
        assert (case / "organon.json").read_bytes() == initial

    first_challenge = engine.test_execution_challenge(case, "t1", REPORT, EXECUTOR)
    with pytest.raises(engine.MethodError, match="invalid or stale"):
        engine.record_test_execution(case, "t1", REPORT, EXECUTOR,
                                     _sign(Ed25519PrivateKey.generate(), first_challenge))
    assert (case / "organon.json").read_bytes() == initial
    engine.review_item(case, "p1", "accept", "Separate intervening event", REVIEWER)
    with pytest.raises(engine.MethodError, match="invalid or stale"):
        engine.record_test_execution(case, "t1", REPORT, EXECUTOR, _sign(key, first_challenge))

    engine.put_item(case, "t1", "test", "Revised test", ["impl1", "crit1"], {
        "passed": True, "argv": ARGV, "command": shlex.join(ARGV),
    }, AUTHOR)
    assert engine.get_state(case)["items"]["t1"]["test_execution_status"] == "missing"
    with pytest.raises(engine.MethodError, match="invalid or stale"):
        engine.record_test_execution(case, "t1", REPORT, EXECUTOR, _sign(key, first_challenge))
    _record(case, key)
    assert engine.get_state(case)["items"]["t1"]["test_execution_status"] == "signed_passed"


def test_revoked_executor_key_removes_pass_and_decisive_verdict_cannot_bypass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, registry, key = _case(tmp_path, monkeypatch)
    engine.put_item(case, "risk1", "risk", "A relevant risk", ["p1"], {}, AUTHOR)
    engine.put_item(case, "base1", "baseline", "A simulated baseline", ["crit1"], {
        "origin": "simulation", "source": "synthetic", "date": "2026-09-27",
    }, AUTHOR)
    engine.put_item(case, "res1", "result", "A simulated result", ["base1", "crit1", "t1"], {
        "origin": "simulation", "source": "synthetic", "date": "2026-09-27",
    }, AUTHOR)
    engine.put_item(case, "ass1", "assessment", "A decisive declared claim", ["res1", "risk1"], {
        "verdict": "cumplido", "claim_scope": "simulation", "uncertainty": "synthetic",
        "adverse_effects": "synthetic", "cost": "synthetic",
    }, AUTHOR)
    assert any("current passed test" in issue for issue in engine.gate(case, "validate")["blockers"])
    replay = engine._project(case)
    assert any("current passed test" in issue for issue in engine._success_claim_issues(
        replay["items"], replay["items"]["ass1"], "signed",
    ))
    _record(case, key)
    assert not any("current passed test" in issue for issue in engine.gate(case, "validate")["blockers"])

    registry_data = json.loads(registry.read_text(encoding="utf-8"))
    registry_data["cases"][read_project(case)["project"]["case_id"]]["test_executors"] = {}
    registry.write_text(json.dumps(registry_data), encoding="utf-8")
    revoked = engine.get_state(case)
    assert revoked["test_execution_trust"] == "unavailable"
    assert revoked["items"]["t1"]["test_execution_status"] == "unverified"
    assert revoked["test_execution_history"][-1]["signature_verified"] is False
    assert any("current passed test" in issue for issue in engine.gate(case, "validate")["blockers"])
    with pytest.raises(engine.MethodError, match="trusted public key"):
        engine.test_execution_challenge(case, "t1", REPORT, EXECUTOR)


def test_historical_signed_test_without_argv_remains_readable_but_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, _, _ = _case(tmp_path, monkeypatch)
    engine.put_item(case, "t1", "test", "Old declaration", ["impl1", "crit1"], {
        "passed": True, "command": "fixture-only: no command was executed",
    }, AUTHOR)
    history = read_project(case)["events"]
    state = engine.get_state(case)
    assert len(history) == state["revision"]
    assert state["items"]["t1"]["test_execution_status"] == "missing"
    assert any("argv" in issue for issue in state["items"]["t1"]["issues"])
    assert not engine.gate(case, "build")["ready"]
    with pytest.raises(engine.MethodError, match="argv"):
        engine.test_execution_challenge(case, "t1", REPORT, EXECUTOR)


def test_new_signed_receipt_requires_new_build_review_and_advance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, registry = tmp_path / "full", tmp_path / "registry.json"
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(registry))
    engine.create_case(case, "Signed workflow", "synthetic", AUTHOR)
    executor, reviewer, approver = (Ed25519PrivateKey.generate() for _ in range(3))
    _register(case, registry, executor, reviewer, approver)
    manifest = json.loads((Path(__file__).resolve().parents[1] / "workflows" / "synthetic_full.json").read_text())
    test_step = next(step for step in manifest["steps"] if step.get("id") == "t1")
    test_step["data"] = {"passed": True, "argv": ARGV, "command": shlex.join(ARGV)}

    result = runner.run_manifest(case, manifest, AUTHOR)
    for _ in range(16):
        task = result["next"]
        if task["action"] == "execute_test":
            break
        if task["action"] == "human_approval":
            target = task["approval_targets"][0]["id"]
            reason = f"Synthetic approval of {target}"
            challenge = engine.approval_challenge(case, target, reason, APPROVER)
            engine.approve(case, target, reason, APPROVER, _sign(approver, challenge))
        elif task["action"] == "review_phase":
            phase = task["phase"]
            reason = f"Independent synthetic review of {phase}"
            challenge = engine.phase_review_challenge(case, phase, "accept", reason, REVIEWER)
            engine.review_phase(case, phase, "accept", reason, REVIEWER, _sign(reviewer, challenge))
        else:
            raise AssertionError(task)
        result = runner.run_manifest(case, manifest, AUTHOR)
    else:
        pytest.fail("signed runner never requested test execution")
    assert task["test_execution_targets"][0]["id"] == "t1"
    assert task["test_execution_targets"][0]["argv"] == ARGV
    assert not engine.gate(case, "build")["ready"]

    _record(case, executor)
    reason = "Independent synthetic build review"
    first_review = engine.phase_review_challenge(case, "build", "accept", reason, REVIEWER)
    engine.review_phase(case, "build", "accept", reason, REVIEWER, _sign(reviewer, first_review))
    engine.advance(case, "build", AUTHOR)
    first = engine.gate(case, "build")
    assert first["accepted"]

    _record(case, executor)
    changed = engine.gate(case, "build")
    assert changed["ready"] and not changed["reviewed"] and not changed["accepted"]
    assert changed["snapshot"] != first["snapshot"]
    with pytest.raises(engine.MethodError, match="accepted review"):
        engine.advance(case, "build", AUTHOR)
    next_review = engine.phase_review_challenge(case, "build", "accept", reason, REVIEWER)
    engine.review_phase(case, "build", "accept", reason, REVIEWER, _sign(reviewer, next_review))
    engine.advance(case, "build", AUTHOR)
    assert engine.gate(case, "build")["accepted"]
