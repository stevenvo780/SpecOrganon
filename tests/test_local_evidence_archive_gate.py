"""Signed evidence archive bytes constrain live phase gates, not source truth."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from specorganon import approval, engine
from specorganon.ledger import read_project


BREAD = Path(__file__).resolve().parents[1] / "cases" / "bread_norway" / "source_lca.pdf"
AUTHOR = "agent:author"
REVIEWER = "agent:independent-reviewer"
APPROVER = "human:owner"


def _public(key: Ed25519PrivateKey) -> str:
    return base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode("ascii")


def _sign(key: Ed25519PrivateKey, challenge: dict) -> str:
    message = base64.b64decode(challenge["message_base64"], validate=True)
    assert hashlib.sha256(message).hexdigest() == challenge["message_sha256"]
    return base64.b64encode(key.sign(message)).decode("ascii")


def _put(case: Path, id: str, kind: str, refs: list[str] | None = None,
         data: dict | None = None, text: str | None = None) -> None:
    engine.put_item(case, id, kind, text or id, refs or [], data or {}, AUTHOR)


def _accept(case: Path, phase: str, reviewer_key: Ed25519PrivateKey) -> None:
    status = engine.gate(case, phase)
    assert status["ready"], status["blockers"]
    reason = f"Independent review of signed {phase} snapshot in a synthetic case"
    challenge = engine.phase_review_challenge(case, phase, "accept", reason, REVIEWER)
    engine.review_phase(case, phase, "accept", reason, REVIEWER, _sign(reviewer_key, challenge))
    engine.advance(case, phase, "agent:lead")
    assert engine.gate(case, phase)["accepted"]


def _signed_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[
    Path, Path, Ed25519PrivateKey,
]:
    case = tmp_path / "signed-case"
    registry = tmp_path / "trusted-public-keys.json"
    registry.write_text(json.dumps({"schema": 2, "cases": {}}), encoding="utf-8")
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(registry))
    monkeypatch.delenv("ORGANON_LEDGER_ANCHORS_FILE", raising=False)
    engine.create_case(case, "Local source byte check", "synthetic test", APPROVER)
    reviewer_key = Ed25519PrivateKey.generate()
    approver_key = Ed25519PrivateKey.generate()
    project = read_project(case)["project"]
    registry.write_text(json.dumps({"schema": 2, "cases": {
        project["case_id"]: {
            "path": str(case.resolve(strict=True)),
            "project_sha256": approval.project_fingerprint(project),
            "approvers": {APPROVER: _public(approver_key)},
            "phase_reviewers": {REVIEWER: _public(reviewer_key)},
        },
    }}), encoding="utf-8")

    _put(case, "p1", "problem")
    _put(case, "a1", "actor", ["p1"])
    _put(case, "b1", "boundary", ["p1"])
    _accept(case, "frame", reviewer_key)

    _put(case, "c1", "concept", ["p1"])
    _put(case, "s1", "assumption", ["p1"])
    _put(case, "f1", "frame_option", ["p1"], text="First framing")
    _put(case, "f2", "frame_option", ["p1"], text="Second framing")
    _put(case, "n1", "norm", ["p1", "a1"])
    reason = "Synthetic normative approval for a test case"
    signature = _sign(approver_key, engine.approval_challenge(case, "n1", reason, APPROVER))
    engine.approve(case, "n1", reason, APPROVER, signature)
    _accept(case, "critique", reviewer_key)

    _put(case, "q1", "question", ["p1"])
    _put(case, "h1", "hypothesis", ["q1"])
    _put(case, "pr1", "protocol", ["q1", "h1"], {
        "population": "synthetic", "method": "test enumeration", "comparison": "baseline",
        "uncertainty": "synthetic test only",
    })
    _put(case, "e0", "evidence", ["pr1"], {
        "origin": "simulated", "source": "synthetic fixture", "date": "2026-09-30",
        "locator": "test_local_evidence_archive_gate.py", "metric_key": "count",
        "scope": "synthetic indicator", "unit": "count", "value": 10,
    })
    _put(case, "i1", "indicator", ["p1", "n1", "e0"], {"metric": "count", "unit": "count"})
    _accept(case, "study", reviewer_key)
    return case, registry, reviewer_key


def _bread_data(archive: object = "source_lca.pdf", digest: object | None = None) -> dict:
    return {
        "origin": "published", "source": "https://doi.org/10.3390/su11010043",
        "date": "2018-12", "locator": "secciones 3.2.1 y 4.2; tabla 1",
        "metric_key": "piece_mass", "scope": "pan_comercial_estudiado",
        "unit": "g/pieza", "value": 736,
        "archive": archive,
        "source_sha256": digest if digest is not None else hashlib.sha256(BREAD.read_bytes()).hexdigest(),
    }


def _add_bread_evidence(case: Path, data: dict | None = None) -> None:
    _put(case, "e1", "evidence", ["pr1"], data if data is not None else _bread_data(),
         "Published LCA reports a 736 g commercial bread piece")
    _put(case, "inf1", "inference", ["e1", "h1"])


def test_missing_archived_bread_source_is_an_issue_without_ledger_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, _, _ = _signed_case(tmp_path, monkeypatch)
    _add_bread_evidence(case)
    ledger = (case / "organon.json").read_bytes()
    state = engine.get_state(case)
    assert "local archive is missing or unsafe to read" in state["items"]["e1"]["issues"]
    assert "depends on invalid local archive evidence e1" in state["items"]["inf1"]["issues"]
    gate = engine.gate(case, "observe")
    assert not gate["ready"] and any("e1: local archive" in blocker for blocker in gate["blockers"])
    with pytest.raises(engine.MethodError, match="phase cannot advance"):
        engine.advance(case, "observe", "agent:lead")
    assert (case / "organon.json").read_bytes() == ledger


def test_changed_bytes_revoke_signed_review_and_advance_until_original_restored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, _, reviewer_key = _signed_case(tmp_path, monkeypatch)
    original = BREAD.read_bytes()
    archive = case / "source_lca.pdf"
    archive.write_bytes(original)
    _add_bread_evidence(case)
    _accept(case, "observe", reviewer_key)
    accepted = engine.gate(case, "observe")
    assert accepted["review_signature_verified"] and accepted["accepted"]
    ledger = (case / "organon.json").read_bytes()

    archive.write_bytes(original + b"\nlocal mutation")
    changed = engine.get_state(case)
    phase = changed["phases"]["observe"]
    assert phase["snapshot"] != accepted["snapshot"]
    assert not phase["ready"] and not phase["reviewed"] and not phase["accepted"]
    assert "local archive bytes differ from source_sha256" in changed["items"]["e1"]["issues"]
    assert "depends on invalid local archive evidence e1" in changed["items"]["inf1"]["issues"]
    assert not changed["phase_review_history"][-1]["signature_verified"]
    with pytest.raises(engine.MethodError, match="phase cannot be accepted"):
        engine.phase_review_challenge(case, "observe", "accept", "After mutation", REVIEWER)
    with pytest.raises(engine.MethodError, match="phase cannot advance"):
        engine.advance(case, "observe", "agent:lead")
    assert (case / "organon.json").read_bytes() == ledger

    archive.unlink()
    missing = engine.gate(case, "observe")
    assert not missing["accepted"] and not missing["ready"]
    assert missing["snapshot"] != accepted["snapshot"]
    assert (case / "organon.json").read_bytes() == ledger

    archive.write_bytes(original)
    restored = engine.gate(case, "observe")
    assert restored["snapshot"] == accepted["snapshot"]
    assert restored["accepted"] and restored["reviewed"]
    assert (case / "organon.json").read_bytes() == ledger


def test_one_archive_cannot_support_two_declared_digests_even_if_bytes_flip_between_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, _, _ = _signed_case(tmp_path, monkeypatch)
    original = BREAD.read_bytes()
    changed = original + b"\nsecond declared version"
    archive = case / "source_lca.pdf"
    archive.write_bytes(original)
    _add_bread_evidence(case, _bread_data(digest=hashlib.sha256(original).hexdigest()))
    assert engine.gate(case, "observe")["ready"]
    second = _bread_data(digest=hashlib.sha256(changed).hexdigest())
    second["metric_key"] = "other_published_measure"
    _put(case, "e2", "evidence", ["pr1"], second,
         "A second synthetic declaration about the same archive path")
    ledger = (case / "organon.json").read_bytes()

    real_digest = engine._local_archive_digest
    reads = 0

    def swapped_archive_digest(case_path: str, parts: tuple[str, ...]) -> str:
        nonlocal reads
        # The former (archive, expected SHA) cache accepted both items: each
        # separate hash saw the bytes it expected within one status call.
        archive.write_bytes(original if reads % 2 == 0 else changed)
        reads += 1
        return real_digest(case_path, parts)

    monkeypatch.setattr(engine, "_local_archive_digest", swapped_archive_digest)
    state = engine.get_state(case)
    issue = "local archive has conflicting source_sha256 declarations"
    assert issue in state["items"]["e1"]["issues"]
    assert issue in state["items"]["e2"]["issues"]
    assert "depends on invalid local archive evidence e1" in state["items"]["inf1"]["issues"]
    assert not state["phases"]["observe"]["ready"]
    assert reads == 0  # The conflicting declarations fail before any file read.
    assert (case / "organon.json").read_bytes() == ledger


@pytest.mark.parametrize(("bad_archive", "bad_digest", "expected"), [
    ("../outside.pdf", None, "local archive path"),
    ("/tmp/outside.pdf", None, "local archive path"),
    ("nested/../source.pdf", None, "local archive path"),
    ("nested//source.pdf", None, "local archive path"),
    ("C:\\outside.pdf", None, "local archive path"),
    (None, None, "local archive path"),
    (["source_lca.pdf"], None, "local archive path"),
    ("source_lca.pdf", "0" * 63, "source_sha256"),
    ("source_lca.pdf", ["0" * 64], "source_sha256"),
])
def test_malformed_local_archive_contract_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    bad_archive: object, bad_digest: object | None, expected: str,
) -> None:
    case, _, _ = _signed_case(tmp_path, monkeypatch)
    shutil.copyfile(BREAD, case / "source_lca.pdf")
    _add_bread_evidence(case, _bread_data(bad_archive, bad_digest))
    ledger = (case / "organon.json").read_bytes()
    state = engine.get_state(case)
    assert any(expected in issue for issue in state["items"]["e1"]["issues"])
    assert not state["phases"]["observe"]["ready"]
    assert (case / "organon.json").read_bytes() == ledger


@pytest.mark.parametrize("missing_key", ["archive", "source_sha256"])
def test_partial_pair_is_invalid_in_signed_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing_key: str,
) -> None:
    case, _, _ = _signed_case(tmp_path, monkeypatch)
    shutil.copyfile(BREAD, case / "source_lca.pdf")
    data = _bread_data()
    del data[missing_key]
    _add_bread_evidence(case, data)
    state = engine.get_state(case)
    assert "local archive requires both archive and source_sha256" in state["items"]["e1"]["issues"]
    assert not state["phases"]["observe"]["ready"]


def test_symlink_ancestor_final_symlink_and_hardlink_are_not_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, _, _ = _signed_case(tmp_path, monkeypatch)
    outside = tmp_path / "outside.pdf"
    shutil.copyfile(BREAD, outside)
    archive_dir = case / "archive"
    archive_dir.symlink_to(tmp_path, target_is_directory=True)
    _add_bread_evidence(case, _bread_data("archive/outside.pdf"))
    assert not engine.gate(case, "observe")["ready"]
    assert "local archive is missing or unsafe to read" in engine.get_state(case)["items"]["e1"]["issues"]

    archive_dir.unlink()
    archive_dir.mkdir()
    (archive_dir / "outside.pdf").symlink_to(outside)
    assert "local archive is missing or unsafe to read" in engine.get_state(case)["items"]["e1"]["issues"]

    (archive_dir / "outside.pdf").unlink()
    os.link(outside, archive_dir / "outside.pdf")
    assert "local archive must be a singly linked regular file" in engine.get_state(case)["items"]["e1"]["issues"]


def test_nonregular_and_oversized_archives_fail_closed_without_hashing_unbounded_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, _, _ = _signed_case(tmp_path, monkeypatch)
    _add_bread_evidence(case)
    archive = case / "source_lca.pdf"
    archive.mkdir()
    assert "local archive must be a singly linked regular file" in engine.get_state(case)["items"]["e1"]["issues"]
    archive.rmdir()
    with archive.open("wb") as file:
        file.truncate(32 * 1024 * 1024 + 1)
    assert "local archive exceeds the 32 MiB size limit" in engine.get_state(case)["items"]["e1"]["issues"]


def test_evidence_without_opt_in_archive_contract_remains_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, _, _ = _signed_case(tmp_path, monkeypatch)
    data = _bread_data()
    del data["archive"]
    del data["source_sha256"]
    _add_bread_evidence(case, data)
    before = engine.gate(case, "observe")
    assert before["ready"]
    assert not engine.get_state(case)["items"]["e1"]["issues"]
    (case / "unrelated.pdf").write_bytes(b"changed")
    assert engine.gate(case, "observe")["snapshot"] == before["snapshot"]
