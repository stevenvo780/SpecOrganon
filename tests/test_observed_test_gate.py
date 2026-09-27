"""A strict test gate binds a signed repeat to the current report and bytes.

These fixtures construct bundles directly to exercise ledger semantics. The
separate D-082 integration tests execute the sandboxed repeat for real.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shlex
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from specorganon import approval, engine, runner, test_observation
from specorganon.ledger import LedgerError, append_event, read_project
from specorganon.workflow import PHASE_BY_ID

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import audit_signed_test_execution as audit  # noqa: E402
import local_replay_sandbox as sandbox  # noqa: E402


AUTHOR = "agent:author"
EXECUTOR = "executor:synthetic"
OBSERVER = "observer:synthetic"
CONTENT = b"observed result\n"


def _public(key: Ed25519PrivateKey) -> str:
    return base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()


def _sign(key: Ed25519PrivateKey, challenge: dict) -> str:
    return base64.b64encode(key.sign(base64.b64decode(challenge["message_base64"]))).decode()


def _registry(case: Path, registry: Path, executor: Ed25519PrivateKey,
              observer: Ed25519PrivateKey | None) -> None:
    project = read_project(case)["project"]
    registry.write_text(json.dumps({"schema": 2, "cases": {project["case_id"]: {
        "path": str(case.resolve(strict=True)),
        "project_sha256": approval.project_fingerprint(project),
        "approvers": {}, "phase_reviewers": {},
        "test_executors": {EXECUTOR: _public(executor)},
        "test_observers": {OBSERVER: _public(observer)} if observer else {},
    }}}), encoding="utf-8")


def _bundle(tmp_path: Path, name: str, output: bytes = CONTENT) -> Path:
    bundle = tmp_path / name
    bundle.mkdir(mode=0o700)
    (bundle / "input").mkdir(mode=0o700)
    (bundle / "artifacts").mkdir(mode=0o700)
    (bundle / "tmp").mkdir(mode=0o700)
    (bundle / "stdout.bin").write_bytes(output)
    (bundle / "stderr.bin").write_bytes(b"")
    (bundle / "artifacts" / "result.txt").write_bytes(CONTENT)
    return bundle


def _case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[
    Path, Path, Ed25519PrivateKey, Ed25519PrivateKey, dict,
]:
    case, registry = tmp_path / "case", tmp_path / "registry.json"
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(registry))
    engine.create_case(case, "Strict synthetic test", "synthetic", AUTHOR,
                       test_gate_policy="signed_observed")
    executor, observer = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    _registry(case, registry, executor, observer)
    bundle = _bundle(tmp_path, "bundle")
    executable = next((candidate for candidate in (
        Path(sys.executable).resolve(strict=True),
        Path("/usr/bin/python3").resolve(strict=True),
        Path("/usr/bin/true").resolve(strict=True),
    ) if candidate.is_file() and candidate.stat().st_size <= 16 * 1024 * 1024), None)
    if executable is None:
        pytest.skip("no local executable fits the bounded observation fixture")
    argv = [str(executable), "-c", "print('observed result')"]
    data = {
        "passed": True, "argv": argv, "command": shlex.join(argv),
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "input_tree_sha256": test_observation.hash_input_tree(bundle / "input"),
    }
    engine.put_item(case, "impl1", "implementation", "Synthetic implementation", [], {}, AUTHOR)
    engine.put_item(case, "t1", "test", "Synthetic observed test", ["impl1"], data, AUTHOR)
    report = {
        "schema": 1, "argv": argv, "exit_code": 0, "timed_out": False,
        "stdout_sha256": hashlib.sha256(CONTENT).hexdigest(),
        "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        "artifacts": [{"path": "result.txt", "sha256": hashlib.sha256(CONTENT).hexdigest()}],
    }
    return case, registry, executor, observer, report


def _report(case: Path, key: Ed25519PrivateKey, report: dict) -> dict:
    challenge = engine.test_execution_challenge(case, "t1", report, EXECUTOR)
    return engine.record_test_execution(case, "t1", report, EXECUTOR, _sign(key, challenge))


def _receipt(case: Path, report_event: dict, report: dict, bundle: Path) -> dict:
    measured = test_observation.inspect_bundle(bundle, report)
    item = engine.get_state(case)["items"]["t1"]
    return {
        "schema": 1, "case_id": read_project(case)["project"]["case_id"],
        "item_id": "t1", "item_version": item["version"],
        "report_provenance": {"seq": report_event["seq"], "hash": report_event["hash"]},
        "bundle_path": str(bundle.resolve(strict=True)),
        "executable_sha256": item["data"]["executable_sha256"],
        "input_tree_sha256": measured["input_tree_sha256"],
        "sandbox": {"policy": "landlock_seccomp_repeat_v1", "landlock_abi": 5,
                    "exit_code": 0, "timed_out": False, "launch_error": None},
        "observed": {key: measured[key] for key in ("stdout_sha256", "stderr_sha256", "artifacts")},
    }


def _observe(case: Path, key: Ed25519PrivateKey, receipt: dict) -> dict:
    challenge = engine.test_observation_challenge(case, "t1", receipt, OBSERVER)
    return engine.record_test_observation(case, "t1", receipt, OBSERVER, _sign(key, challenge))


def test_strict_policy_is_opt_in_and_malformed_combinations_fail(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    engine.create_case(legacy, "Legacy", "synthetic", AUTHOR)
    assert "test_gate_policy" not in read_project(legacy)["project"]
    with pytest.raises(LedgerError, match="requires signed"):
        engine.create_case(tmp_path / "bad", "Bad", "synthetic", AUTHOR,
                           approval_policy="fixture", test_gate_policy="signed_observed")


def test_report_only_cannot_pass_strict_gate_and_observation_binds_current_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, registry, executor, observer, report = _case(tmp_path, monkeypatch)
    report_event = _report(case, executor, report)
    item = engine.get_state(case)["items"]["t1"]
    assert item["test_execution_status"] == "signed_passed"
    assert item["test_observation_status"] == "missing"
    assert any("observed repeat receipt" in issue for issue in item["issues"])
    assert not engine.gate(case, "build")["ready"]
    before = engine.gate(case, "build")["snapshot"]

    receipt = _receipt(case, report_event, report, tmp_path / "bundle")
    observed = _observe(case, observer, receipt)
    passed = engine.get_state(case)["items"]["t1"]
    assert passed["test_observation_status"] == "observed_passed"
    assert passed["test_observation_provenance"] == (observed["seq"], observed["hash"])
    assert passed["issues"] == []
    assert engine.gate(case, "build")["snapshot"] != before

    (tmp_path / "bundle" / "stdout.bin").write_bytes(b"changed")
    altered = engine.get_state(case)["items"]["t1"]
    assert altered["test_observation_status"] == "unverified"
    assert altered["issues"]
    assert not engine.gate(case, "build")["ready"]

    (tmp_path / "bundle" / "stdout.bin").write_bytes(CONTENT)
    registry_data = json.loads(registry.read_text(encoding="utf-8"))
    case_id = read_project(case)["project"]["case_id"]
    registry_data["cases"][case_id]["test_observers"] = {}
    registry.write_text(json.dumps(registry_data), encoding="utf-8")
    revoked = engine.get_state(case)["items"]["t1"]
    assert revoked["test_observation_status"] == "unverified"
    assert revoked["issues"]


def test_latest_negative_observation_blocks_and_missing_bundle_cannot_resurrect_old_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, _, executor, observer, report = _case(tmp_path, monkeypatch)
    report_event = _report(case, executor, report)
    _observe(case, observer, _receipt(case, report_event, report, tmp_path / "bundle"))
    negative_bundle = _bundle(tmp_path, "negative", b"different\n")
    negative_receipt = _receipt(case, report_event, report, negative_bundle)
    negative = _observe(case, observer, negative_receipt)
    state = engine.get_state(case)
    assert state["items"]["t1"]["test_observation_status"] == "observed_failed"
    assert state["items"]["t1"]["test_observation_provenance"] == (negative["seq"], negative["hash"])
    monkeypatch.setattr(runner, "PHASES", (PHASE_BY_ID["build"],))
    task = runner.next_task(case)
    assert task["action"] == "observe_test"
    assert task["test_observation_targets"][0]["id"] == "t1"

    (negative_bundle / "stdout.bin").unlink()
    missing = engine.get_state(case)["items"]["t1"]
    assert missing["test_observation_status"] == "unverified"
    assert missing["issues"]
    assert runner.next_task(case)["action"] == "observe_test"


def test_unsigned_event_does_not_supersede_and_new_report_requires_new_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, _, executor, observer, report = _case(tmp_path, monkeypatch)
    report_event = _report(case, executor, report)
    receipt = _receipt(case, report_event, report, tmp_path / "bundle")
    _observe(case, observer, receipt)
    append_event(case, "test_observation", {
        "id": "t1", "version": 1, "report_provenance": receipt["report_provenance"],
        "receipt": receipt, "signature": "invalid", "key_sha256": "0" * 64,
    }, OBSERVER, expected_seq=engine.get_state(case)["revision"])
    assert engine.get_state(case)["items"]["t1"]["test_observation_status"] == "observed_passed"
    _report(case, executor, report)
    current = engine.get_state(case)["items"]["t1"]
    assert current["test_execution_status"] == "signed_passed"
    assert current["test_observation_status"] == "missing" or current["test_observation_status"] == "unverified"
    assert current["issues"]


@pytest.mark.parametrize("historical_author", [False, True])
def test_direct_signed_event_by_test_author_cannot_bypass_observer_separation(
    historical_author: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, _, executor, observer, report = _case(tmp_path, monkeypatch)
    original = engine.get_state(case)["items"]["t1"]
    engine.put_item(case, "t1", "test", "Observer authored revision", ["impl1"],
                    original["data"], OBSERVER)
    if historical_author:
        engine.put_item(case, "t1", "test", "Later author revision", ["impl1"],
                        original["data"], AUTHOR)
    report_event = _report(case, executor, report)
    receipt = _receipt(case, report_event, report, tmp_path / "bundle")
    with pytest.raises(engine.MethodError, match="distinct"):
        engine.test_observation_challenge(case, "t1", receipt, OBSERVER)
    state = engine._project(case)
    item = state["items"]["t1"]
    head = state["head_hash"]
    raw = test_observation.message(state["project"], item, report,
                                   receipt["report_provenance"], receipt, OBSERVER, case, head)
    signature = base64.b64encode(observer.sign(raw)).decode()
    forged = append_event(case, "test_observation", {
        "id": "t1", "version": item["version"], "report_provenance": receipt["report_provenance"],
        "receipt": receipt, "signature": signature,
        "key_sha256": hashlib.sha256(base64.b64decode(_public(observer))).hexdigest(),
    }, OBSERVER, expected_seq=state["revision"])
    after = engine.get_state(case)
    assert after["test_observation_history"][-1]["seq"] == forged["seq"]
    assert after["test_observation_history"][-1]["signature_verified"] is False
    assert after["items"]["t1"]["test_observation_status"] == "unverified"
    assert after["items"]["t1"]["issues"]


def test_real_sandbox_repeat_receipt_is_signed_and_replayed_by_strict_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    capability = sandbox.probe_sandbox()
    if not capability.available:
        pytest.skip(capability.reason or "local sandbox unavailable")
    executable = next((candidate for candidate in (
        Path(sys.executable).resolve(strict=True), Path("/usr/bin/python3").resolve(strict=True),
    ) if candidate.is_file() and candidate.stat().st_size <= audit.MAX_EXECUTABLE_BYTES), None)
    if executable is None:
        pytest.skip("no sealable local Python executable")
    case, registry = tmp_path / "real_case", tmp_path / "real_registry.json"
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(registry))
    engine.create_case(case, "Real local repeat", "synthetic", AUTHOR,
                       test_gate_policy="signed_observed")
    executor, observer = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    _registry(case, registry, executor, observer)
    run = tmp_path / "real_run"
    run.mkdir(mode=0o700)
    (run / "input").mkdir(mode=0o700)
    (run / "input" / "payload.txt").write_bytes(CONTENT)
    script = (
        "from pathlib import Path; import os,sys; "
        "data=Path('payload.txt').read_bytes(); "
        "(Path(os.environ['HOME'])/'result.txt').write_bytes(data); "
        "sys.stdout.buffer.write(data)"
    )
    argv = [str(executable), "-I", "-c", script]
    engine.put_item(case, "t1", "test", "Actual sandboxed repeat", [], {
        "passed": True, "argv": argv, "command": shlex.join(argv),
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "input_tree_sha256": test_observation.hash_input_tree(run / "input"),
    }, AUTHOR)
    report = {
        "schema": 1, "argv": argv, "exit_code": 0, "timed_out": False,
        "stdout_sha256": hashlib.sha256(CONTENT).hexdigest(),
        "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        "artifacts": [{"path": "result.txt", "sha256": hashlib.sha256(CONTENT).hexdigest()}],
    }
    _report(case, executor, report)
    observed = audit.audit_signed_test_execution(case, "t1", run)
    assert observed["observed_passed"] is True, observed
    event = _observe(case, observer, observed["receipt"])
    item = engine.get_state(case)["items"]["t1"]
    assert item["test_observation_status"] == "observed_passed"
    assert item["test_observation_provenance"] == (event["seq"], event["hash"])
    (run / "artifacts" / "result.txt").unlink()
    assert engine.get_state(case)["items"]["t1"]["test_observation_status"] == "unverified"
