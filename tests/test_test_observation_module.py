"""Byte and signature boundaries for signed observed test receipts."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from specorganon import approval, test_observation


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _public(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


@pytest.fixture
def observed_case(tmp_path: Path) -> dict:
    case = tmp_path / "case"
    case.mkdir()
    executable = tmp_path / "tool"
    executable.write_bytes(b"#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    bundle = tmp_path / "bundle"
    bundle.mkdir(mode=0o700)
    (bundle / "input").mkdir(mode=0o700)
    (bundle / "input" / "data.txt").write_bytes(b"input bytes")
    (bundle / "artifacts").mkdir(mode=0o700)
    (bundle / "artifacts" / "result.txt").write_bytes(b"result bytes")
    (bundle / "stdout.bin").write_bytes(b"stdout bytes")
    (bundle / "stderr.bin").write_bytes(b"")
    project = {"case_id": "case-1", "approval_policy": "signed",
               "test_gate_policy": "signed_observed"}
    report = {
        "schema": 1, "argv": [str(executable)], "exit_code": 0, "timed_out": False,
        "stdout_sha256": _sha(b"stdout bytes"), "stderr_sha256": _sha(b""),
        "artifacts": [{"path": "result.txt", "sha256": _sha(b"result bytes")}],
    }
    item = {
        "id": "t1", "version": 1, "kind": "test", "deps": {"impl1": 1},
        "data": {"argv": report["argv"], "executable_sha256": _sha(executable.read_bytes()),
                 "input_tree_sha256": test_observation.hash_input_tree(bundle / "input")},
    }
    provenance = {"seq": 7, "hash": "a" * 64}
    return {"case": case, "bundle": bundle, "executable": executable,
            "project": project, "item": item, "report": report, "provenance": provenance}


def _receipt(context: dict, report: dict | None = None) -> dict:
    report = report or context["report"]
    observed = test_observation.inspect_bundle(context["bundle"], report)
    return {
        "schema": 1, "case_id": context["project"]["case_id"], "item_id": context["item"]["id"],
        "item_version": context["item"]["version"],
        "report_provenance": context["provenance"],
        "bundle_path": str(context["bundle"]),
        "executable_sha256": context["item"]["data"]["executable_sha256"],
        "input_tree_sha256": context["item"]["data"]["input_tree_sha256"],
        "sandbox": {"policy": "landlock_seccomp_repeat_v1", "landlock_abi": 5,
                    "exit_code": report["exit_code"], "timed_out": report["timed_out"],
                    "launch_error": None},
        "observed": {"stdout_sha256": observed["stdout_sha256"],
                     "stderr_sha256": observed["stderr_sha256"],
                     "artifacts": observed["artifacts"]},
    }


def _validated(context: dict, receipt: dict, report: dict | None = None) -> bool:
    return test_observation.validate_receipt(
        receipt, context["project"], context["item"], report or context["report"],
        context["provenance"],
    )


def test_inspection_binds_regular_input_tree_and_declared_output_bytes(observed_case: dict) -> None:
    context = observed_case
    bundle = context["bundle"]
    receipt = _receipt(context)
    assert _validated(context, receipt) is True
    assert receipt["observed"]["artifacts"] == context["report"]["artifacts"]

    (bundle / "input" / "empty").mkdir()
    assert test_observation.hash_input_tree(bundle / "input") != receipt["input_tree_sha256"]
    with pytest.raises(ValueError, match="input tree"):
        _validated(context, receipt)
    (bundle / "input" / "empty").rmdir()

    (bundle / "stdout.bin").write_bytes(b"changed bytes")
    with pytest.raises(ValueError, match="observed digests"):
        _validated(context, receipt)


def test_bundle_requires_complete_private_regular_layout(observed_case: dict, tmp_path: Path) -> None:
    context = observed_case
    bundle = context["bundle"]
    report = context["report"]
    (bundle / "stderr.bin").unlink()
    with pytest.raises(ValueError, match="incomplete"):
        test_observation.inspect_bundle(bundle, report)
    (bundle / "stderr.bin").write_bytes(b"")

    (bundle / "input" / "link").symlink_to(bundle / "stdout.bin")
    with pytest.raises(ValueError, match="symlink"):
        test_observation.inspect_bundle(bundle, report)
    (bundle / "input" / "link").unlink()

    bundle.chmod(0o755)
    with pytest.raises(ValueError, match="0700"):
        test_observation.inspect_bundle(bundle, report)
    bundle.chmod(0o700)

    fake = tmp_path / "plain-directory"
    fake.mkdir(mode=0o700)
    with pytest.raises(ValueError, match="incomplete"):
        test_observation.inspect_bundle(fake, report)


def test_missing_declared_artifact_is_valid_negative_observation(observed_case: dict) -> None:
    context = observed_case
    (context["bundle"] / "artifacts" / "result.txt").unlink()
    receipt = _receipt(context)
    assert receipt["observed"]["artifacts"] == []
    assert _validated(context, receipt) is False
    receipt["sandbox"]["exit_code"] = None
    assert _validated(context, receipt) is False


def test_negative_receipt_can_be_signed_and_replay_checks_signature_without_bundle(
    observed_case: dict,
) -> None:
    context = observed_case
    report = {**context["report"], "stdout_sha256": "b" * 64}
    receipt = _receipt(context, report)
    assert _validated(context, receipt, report) is False
    key = Ed25519PrivateKey.generate()
    actor = "observer:repeat"
    challenge = test_observation.challenge(
        context["project"], context["item"], report, context["provenance"],
        receipt, actor, context["case"], "c" * 64,
    )
    payload = base64.b64decode(challenge["message_base64"], validate=True)
    assert hashlib.sha256(payload).hexdigest() == challenge["message_sha256"]
    signed = json.loads(payload)
    assert signed["purpose"] == "specorganon.test_observation"
    assert signed["receipt"] == receipt
    signature = base64.b64encode(key.sign(payload)).decode("ascii")
    public_raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
    )
    args = (context["project"], context["item"], report, context["provenance"],
            receipt, actor, signature, _sha(public_raw), {actor: public_raw},
            context["case"], "c" * 64)
    assert test_observation.verify(*args)
    assert not test_observation.verify(*args[:-1], "d" * 64)
    assert not test_observation.verify(*args[:6], signature, _sha(public_raw), {},
                                       context["case"], "c" * 64)
    tampered = {**receipt, "sandbox": {**receipt["sandbox"], "exit_code": 1}}
    assert not test_observation.verify(*args[:4], tampered, *args[5:])

    (context["bundle"] / "stdout.bin").unlink()
    assert test_observation.verify(*args)
    with pytest.raises(ValueError):
        _validated(context, receipt, report)


def test_receipt_rejects_untrusted_claims_and_changed_executable(observed_case: dict) -> None:
    context = observed_case
    receipt = _receipt(context)
    with pytest.raises(ValueError, match="exact schema"):
        _validated(context, {**receipt, "observed_passed": True})
    with pytest.raises(ValueError, match="report event"):
        _validated(context, {**receipt, "report_provenance": {"seq": 8, "hash": "a" * 64}})
    with pytest.raises(ValueError, match="sandbox"):
        _validated(context, {**receipt, "sandbox": {**receipt["sandbox"], "landlock_abi": 4}})
    context["executable"].write_bytes(b"#!/bin/sh\nexit 1\n")
    with pytest.raises(ValueError, match="executable bytes"):
        _validated(context, receipt)


def test_registry_observer_keys_are_separate_and_legacy_views_stable(
    observed_case: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = observed_case
    actors = ("human:owner", "agent:review", "executor:run", "observer:repeat")
    keys = [Ed25519PrivateKey.generate() for _ in actors]
    registry = tmp_path / "registry.json"
    entry = {
        "path": str(context["case"]),
        "project_sha256": approval.project_fingerprint(context["project"]),
        "approvers": {actors[0]: _public(keys[0])},
        "phase_reviewers": {actors[1]: _public(keys[1])},
        "test_executors": {actors[2]: _public(keys[2])},
        "test_observers": {actors[3]: _public(keys[3])},
    }
    registry.write_text(json.dumps({"schema": 2, "cases": {"case-1": entry}}), encoding="utf-8")
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(registry))
    approvers, reviewers, executors, observers, status = approval.trust_contexts_with_observers(
        context["project"], context["case"],
    )
    assert status == "configured"
    assert set(approvers) == {actors[0]}
    assert set(reviewers) == {actors[1]}
    assert set(executors) == {actors[2]}
    assert set(observers) == {actors[3]}
    assert approval.trust_contexts_with_executors(context["project"], context["case"]) == (
        approvers, reviewers, executors, status,
    )
    assert approval.trust_contexts(context["project"], context["case"]) == (
        approvers, reviewers, status,
    )

    entry["test_observers"] = {actors[3]: _public(keys[2])}
    registry.write_text(json.dumps({"schema": 2, "cases": {"case-1": entry}}), encoding="utf-8")
    with pytest.raises(ValueError, match="overlaps"):
        approval.trust_contexts_with_observers(context["project"], context["case"])
    entry["test_observers"] = {"executor:bad": _public(keys[3])}
    registry.write_text(json.dumps({"schema": 2, "cases": {"case-1": entry}}), encoding="utf-8")
    with pytest.raises(ValueError, match="observer entry"):
        approval.trust_contexts_with_observers(context["project"], context["case"])
