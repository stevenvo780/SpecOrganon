"""Tests for pure physical evidence snapshot exporter (t_common_snapshot).

Synthetic tests only, testing physical boundaries, schema 2 conformance,
invariants, atomicity, crash recovery, and refusal of invalid evidence.
Never claims native pass, common_complete, or independent F.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import pytest

from specorganon.common_evidence import read_snapshot, validate_bound_audit
from specorganon.common_review import checklist
from specorganon.role_jobs import canonical, digest, JobError
from specorganon.software_controller import encoded_contribution
from specorganon.t_common_snapshot import export_snapshot


def _make_valid_payload():
    contract = "Pre-measurement host contract for method T development."
    policy = {
        "schema": 1,
        "method": "T",
        "attempt_id": "att-001",
        "scope": "Synthetic test fixture for physical snapshot export",
    }
    doc_initial = {
        "SPEC.md": "Specification of the bounded pure exporter.",
        "CRITERIA.md": "Criteria 1: atomic writes; Criteria 2: immutability.",
    }
    doc_phase = {
        **doc_initial,
        "TASKS.md": "Task 1: input validation; Task 2: atomic flush.",
    }
    deliv_code = {
        "pkg/exporter.py": "def run():\n    return 42\n",
        "README.md": "Pure exporter docs with reproducible examples.",
    }
    deliv_tests = {
        **deliv_code,
        "tests/test_exporter.py": "def test_run():\n    assert True\n",
    }
    captures = [
        {
            "id": "cp0001",
            "kind": "criteria",
            "job_id": "job-init",
            "request_sha256": "0" * 64,
            "delivery": {},
            "documents": doc_initial,
        },
        {
            "id": "cp0002",
            "kind": "planning",
            "job_id": "job-plan",
            "request_sha256": "1" * 64,
            "delivery": {},
            "documents": doc_phase,
        },
        {
            "id": "cp0003",
            "kind": "delivery",
            "job_id": "job-code",
            "request_sha256": "2" * 64,
            "delivery": deliv_code,
            "documents": doc_phase,
        },
        {
            "id": "cp0004",
            "kind": "tests",
            "job_id": "job-tests",
            "request_sha256": "3" * 64,
            "delivery": deliv_tests,
            "documents": doc_phase,
        },
        {
            "id": "cp0005",
            "kind": "execution",
            "job_id": "job-exec",
            "request_sha256": "4" * 64,
            "delivery": deliv_tests,
            "documents": doc_phase,
        },
        {
            "id": "cp0006",
            "kind": "review",
            "job_id": "job-rev",
            "request_sha256": "5" * 64,
            "delivery": deliv_tests,
            "documents": doc_phase,
        },
    ]

    stdout_raw = b"test suite ran 1 test: ok\n"
    stderr_raw = b""

    receipts = {
        "job-exec": {
            "kind": "test",
            "value": {
                "schema": 1,
                "test_job_ref": "job-exec",
                "stdout_sha256": digest(stdout_raw),
                "stdout_bytes": len(stdout_raw),
                "stderr_sha256": digest(stderr_raw),
                "stderr_bytes": len(stderr_raw),
                "exit_code": 0,
            },
        },
        "job-rev": {
            "kind": "role",
            "value": {
                "schema": 1,
                "role": "review",
                "verdict": "inconclusive",
                "reason": "Synthetic fixture review packet",
                "findings": [{"id": "f1", "severity": "info", "description": "Synthetic review"}],
                "tests_executed": False,
            },
        },
    }

    streams = {
        "job-exec/stdout": stdout_raw,
        "job-exec/stderr": stderr_raw,
    }

    return contract, policy, captures, receipts, streams


def test_roundtrip_allhistorical_pre_postemptyfiles(tmp_path):
    root = tmp_path / "snapshot_root"
    contract, policy, captures, receipts, streams = _make_valid_payload()

    snapshot, reference = export_snapshot(
        root,
        contract=contract,
        policy=policy,
        captures=captures,
        receipts=receipts,
        streams=streams,
    )

    assert reference["path"] == str(root.resolve())
    assert reference["manifest_sha256"] == snapshot["manifest_sha256"]
    assert snapshot["method"] == "T"
    assert snapshot["delivery"] == captures[-1]["delivery"]
    assert snapshot["documents"] == captures[-1]["documents"]
    assert len(snapshot["history"]) == 6

    # Verify historical checkpoints chain
    for i, event in enumerate(snapshot["history"]):
        assert event["id"] == captures[i]["id"]
        assert event["sequence"] == i + 1
        assert event["kind"] == captures[i]["kind"]

    # First checkpoints had empty delivery
    assert snapshot["history"][0]["delivery_sha256"] == digest(canonical({}))
    assert snapshot["history"][1]["delivery_sha256"] == digest(canonical({}))

    # Final checkpoint matches final delivery
    assert snapshot["history"][-1]["delivery_sha256"] == digest(canonical(captures[-1]["delivery"]))

    # Verify bound audit without claiming native pass or completion
    decl = {
        "schema": 1,
        "format": "common-audit-v1",
        "method": "T",
        "binding": snapshot["binding"],
        "locators": sorted(snapshot["locators"]),
    }
    review = {
        "schema": 1,
        "verdict": "inconclusive",
        "reason": "Synthetic review for dev10 snapshot export test",
        "findings": [],
        "tests_executed": False,
        "audit": {
            "binding": decl["binding"],
            **{
                g: {p: {"status": "inconclusive", "reason": "Fixture", "evidence": []} for p in pts}
                for g, pts in checklist("T").items()
            },
        },
    }
    audited = validate_bound_audit(snapshot, decl, review, verify_receipt=lambda *_: True)
    assert "common_complete" not in audited
    assert "passed" not in audited
    assert "nativepass" not in audited
    assert audited["review"] == review


def test_completephase_docs_rolepacket_reason_findings(tmp_path):
    root = tmp_path / "snapshot_phase"
    contract, policy, captures, receipts, streams = _make_valid_payload()

    snapshot, _ = export_snapshot(
        root,
        contract=contract,
        policy=policy,
        captures=captures,
        receipts=receipts,
        streams=streams,
    )

    # Complete documents
    assert "SPEC.md" in snapshot["documents"]
    assert "CRITERIA.md" in snapshot["documents"]
    assert "TASKS.md" in snapshot["documents"]

    # Role packet preserved completely
    role_receipt = snapshot["receipts"]["job-rev"]
    assert role_receipt["kind"] == "role"
    assert role_receipt["value"]["reason"] == "Synthetic fixture review packet"
    assert role_receipt["value"]["findings"] == [{"id": "f1", "severity": "info", "description": "Synthetic review"}]
    assert role_receipt["value"]["tests_executed"] is False


def test_streams2exact(tmp_path):
    root = tmp_path / "snapshot_streams"
    contract, policy, captures, receipts, streams = _make_valid_payload()

    snapshot, _ = export_snapshot(
        root,
        contract=contract,
        policy=policy,
        captures=captures,
        receipts=receipts,
        streams=streams,
    )

    assert set(snapshot["streams"]) == {"job-exec/stdout", "job-exec/stderr"}
    assert snapshot["streams"]["job-exec/stdout"] == b"test suite ran 1 test: ok\n"
    assert snapshot["streams"]["job-exec/stderr"] == b""
    assert "stream:job-exec/stdout" in snapshot["locators"]
    assert "stream:job-exec/stderr" in snapshot["locators"]


def test_root_symlink_tamper(tmp_path):
    contract, policy, captures, receipts, streams = _make_valid_payload()

    # 1. Symlink root is rejected
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir(mode=0o700)
    symlink_dir = tmp_path / "symlink_dir"
    symlink_dir.symlink_to(real_dir)
    with pytest.raises((ValueError, JobError)):
        export_snapshot(
            symlink_dir,
            contract=contract,
            policy=policy,
            captures=captures,
            receipts=receipts,
            streams=streams,
        )

    # 2. Insecure directory mode is rejected
    insecure_dir = tmp_path / "insecure_dir"
    insecure_dir.mkdir(mode=0o755)
    os.chmod(insecure_dir, 0o755)
    with pytest.raises(ValueError, match="mode0700"):
        export_snapshot(
            insecure_dir,
            contract=contract,
            policy=policy,
            captures=captures,
            receipts=receipts,
            streams=streams,
        )

    # 3. Successful export followed by tamper fails closed and does not overwrite
    good_root = tmp_path / "good_root"
    export_snapshot(
        good_root,
        contract=contract,
        policy=policy,
        captures=captures,
        receipts=receipts,
        streams=streams,
    )

    # Tamper contract file
    contract_file = good_root / "host/contract.txt"
    contract_file.write_bytes(b"Tampered contract bytes")

    with pytest.raises(ValueError, match="immutable snapshot bytes changed"):
        export_snapshot(
            good_root,
            contract=contract,
            policy=policy,
            captures=captures,
            receipts=receipts,
            streams=streams,
        )

    # The tampered content remains unchanged (not silently overwritten)
    assert contract_file.read_bytes() == b"Tampered contract bytes"


def test_missing_bad_streams_oversize_invalidkind_dupid(tmp_path):
    contract, policy, captures, receipts, streams = _make_valid_payload()
    root = tmp_path / "err_root"

    # Missing stream (missing stderr)
    bad_streams = {"job-exec/stdout": streams["job-exec/stdout"]}
    with pytest.raises(ValueError, match="measured test streams missing"):
        export_snapshot(
            root,
            contract=contract,
            policy=policy,
            captures=captures,
            receipts=receipts,
            streams=bad_streams,
        )

    # Extra stream
    bad_streams2 = {**streams, "extra/stdout": b""}
    with pytest.raises(ValueError, match="measured test streams missing"):
        export_snapshot(
            root,
            contract=contract,
            policy=policy,
            captures=captures,
            receipts=receipts,
            streams=bad_streams2,
        )

    # Bad stream SHA
    bad_streams3 = {**streams, "job-exec/stdout": b"different stdout\n"}
    with pytest.raises(ValueError, match="stream sha differs"):
        export_snapshot(
            root,
            contract=contract,
            policy=policy,
            captures=captures,
            receipts=receipts,
            streams=bad_streams3,
        )

    # Bad stream byte count
    bad_receipts = copy.deepcopy(receipts)
    bad_receipts["job-exec"]["value"]["stdout_bytes"] = len(streams["job-exec/stdout"]) + 10
    with pytest.raises(ValueError, match="stream bytes differ"):
        export_snapshot(
            root,
            contract=contract,
            policy=policy,
            captures=captures,
            receipts=bad_receipts,
            streams=streams,
        )

    # Oversize stream (> 4000 encoded contribution)
    huge_stdout = b"x" * 4001
    bad_receipts2 = copy.deepcopy(receipts)
    bad_receipts2["job-exec"]["value"]["stdout_bytes"] = len(huge_stdout)
    bad_receipts2["job-exec"]["value"]["stdout_sha256"] = digest(huge_stdout)
    bad_streams4 = {**streams, "job-exec/stdout": huge_stdout}
    with pytest.raises(ValueError, match="stream exceeds budget"):
        export_snapshot(
            root,
            contract=contract,
            policy=policy,
            captures=captures,
            receipts=bad_receipts2,
            streams=bad_streams4,
        )

    # Invalid UTF-8 stream bytes
    bad_utf8_stdout = b"\xff\xfe\xfa"
    bad_receipts3 = copy.deepcopy(receipts)
    bad_receipts3["job-exec"]["value"]["stdout_bytes"] = len(bad_utf8_stdout)
    bad_receipts3["job-exec"]["value"]["stdout_sha256"] = digest(bad_utf8_stdout)
    bad_streams5 = {**streams, "job-exec/stdout": bad_utf8_stdout}
    with pytest.raises(ValueError, match="stream bytes must be valid utf-8"):
        export_snapshot(
            root,
            contract=contract,
            policy=policy,
            captures=captures,
            receipts=bad_receipts3,
            streams=bad_streams5,
        )

    # Invalid capture kind
    bad_captures = copy.deepcopy(captures)
    bad_captures[0]["kind"] = "unsupported_kind"
    with pytest.raises(ValueError, match="invalid capture kind"):
        export_snapshot(
            root,
            contract=contract,
            policy=policy,
            captures=bad_captures,
            receipts=receipts,
            streams=streams,
        )

    # Duplicate checkpoint ID
    bad_captures2 = copy.deepcopy(captures)
    bad_captures2[1]["id"] = bad_captures2[0]["id"]
    with pytest.raises(ValueError, match="duplicate checkpoint id"):
        export_snapshot(
            root,
            contract=contract,
            policy=policy,
            captures=bad_captures2,
            receipts=receipts,
            streams=streams,
        )

    # Empty captures list
    with pytest.raises(ValueError, match="captures list must be non-empty"):
        export_snapshot(
            root,
            contract=contract,
            policy=policy,
            captures=[],
            receipts=receipts,
            streams=streams,
        )

    # Empty final delivery
    bad_captures3 = copy.deepcopy(captures)
    bad_captures3[-1]["delivery"] = {}
    with pytest.raises(ValueError, match="final delivery map cannot be empty"):
        export_snapshot(
            root,
            contract=contract,
            policy=policy,
            captures=bad_captures3,
            receipts=receipts,
            streams=streams,
        )

    # Empty contract
    with pytest.raises(ValueError, match="empty common contract"):
        export_snapshot(
            root,
            contract="   \n",
            policy=policy,
            captures=captures,
            receipts=receipts,
            streams=streams,
        )

    # Empty policy
    with pytest.raises(ValueError, match="empty common policy"):
        export_snapshot(
            root,
            contract=contract,
            policy={},
            captures=captures,
            receipts=receipts,
            streams=streams,
        )

    # Incompatible policy method
    with pytest.raises(ValueError, match="policy method must be T"):
        export_snapshot(
            root,
            contract=contract,
            policy={"method": "S"},
            captures=captures,
            receipts=receipts,
            streams=streams,
        )


def test_immutable_recovery_interrupted_write(tmp_path):
    root = tmp_path / "snapshot_recovery"
    contract, policy, captures, receipts, streams = _make_valid_payload()

    # Pre-populate partial state with identical content (simulating crash after first writes)
    root.mkdir(mode=0o700)
    host_dir = root / "host"
    host_dir.mkdir(mode=0o700)
    (host_dir / "contract.txt").write_bytes(contract.encode("utf-8"))
    (host_dir / "policy.json").write_bytes(canonical(policy))

    # Crash recovery: exporter must resume, reuse matching files, and complete snapshot
    snapshot1, ref1 = export_snapshot(
        root,
        contract=contract,
        policy=policy,
        captures=captures,
        receipts=receipts,
        streams=streams,
    )
    assert ref1["path"] == str(root.resolve())
    assert snapshot1["method"] == "T"

    # Idempotent re-run on fully completed snapshot succeeds identically
    snapshot2, ref2 = export_snapshot(
        root,
        contract=contract,
        policy=policy,
        captures=captures,
        receipts=receipts,
        streams=streams,
    )
    assert ref2 == ref1
    assert snapshot2["manifest_sha256"] == snapshot1["manifest_sha256"]


def test_validfixture_neverclaims_nativepass_or_common_complete(tmp_path):
    root = tmp_path / "snapshot_fixture_proof"
    contract, policy, captures, receipts, streams = _make_valid_payload()

    snapshot, _ = export_snapshot(
        root,
        contract=contract,
        policy=policy,
        captures=captures,
        receipts=receipts,
        streams=streams,
    )

    # Snapshot dictionary has no completion or pass claim
    assert "common_complete" not in snapshot
    assert "passed" not in snapshot
    assert "F" not in snapshot


def test_oversize_budgets_and_locators_guard(tmp_path):
    contract, policy, captures, receipts, streams = _make_valid_payload()
    root = tmp_path / "budget_root"

    # Oversize delivery contribution (> 20000)
    bad_deliv_cap = copy.deepcopy(captures)
    bad_deliv_cap[-1]["delivery"]["big.py"] = "a = 1\n" * 3500
    with pytest.raises(ValueError, match="delivery exceeds encoded contribution budget"):
        export_snapshot(
            root,
            contract=contract,
            policy=policy,
            captures=bad_deliv_cap,
            receipts=receipts,
            streams=streams,
        )

    # Oversize documents contribution (> 54000)
    bad_docs_cap = copy.deepcopy(captures)
    bad_docs_cap[-1]["documents"]["big.md"] = "# Big doc\n" * 4500
    with pytest.raises(ValueError, match="documents exceed encoded contribution budget"):
        export_snapshot(
            root,
            contract=contract,
            policy=policy,
            captures=bad_docs_cap,
            receipts=receipts,
            streams=streams,
        )

    # Individual physical file > 128000 bytes
    huge_contract = "a" * 128001
    with pytest.raises(ValueError, match="contract exceeds byte limit"):
        export_snapshot(
            root,
            contract=huge_contract,
            policy=policy,
            captures=captures,
            receipts=receipts,
            streams=streams,
        )

    # Captures count > 80
    too_many_caps = []
    for i in range(81):
        c = copy.deepcopy(captures[-1])
        c["id"] = f"cp{i:04d}"
        too_many_caps.append(c)
    with pytest.raises(ValueError, match="captures list must be non-empty and <= 80"):
        export_snapshot(
            root,
            contract=contract,
            policy=policy,
            captures=too_many_caps,
            receipts=receipts,
            streams=streams,
        )

    # Receipts count > 80
    too_many_receipts = {
        f"job-{i:03d}": {"kind": "role", "value": {"schema": 1, "role": "test"}}
        for i in range(81)
    }
    with pytest.raises(ValueError, match="invalid bounded receipt map"):
        export_snapshot(
            root,
            contract=contract,
            policy=policy,
            captures=captures,
            receipts=too_many_receipts,
            streams={},
        )


def test_internal_symlink_rejection(tmp_path):
    contract, policy, captures, receipts, streams = _make_valid_payload()
    root = tmp_path / "sym_target_root"
    root.mkdir(mode=0o700)

    # Create a symlinked subdirectory inside root
    outside = tmp_path / "outside_dir"
    outside.mkdir(mode=0o700)
    (root / "host").symlink_to(outside)

    with pytest.raises((ValueError, JobError)):
        export_snapshot(
            root,
            contract=contract,
            policy=policy,
            captures=captures,
            receipts=receipts,
            streams=streams,
        )


def test_historical_captures_deduplication(tmp_path):
    contract, policy, captures, receipts, streams = _make_valid_payload()
    root = tmp_path / "dedup_root"

    # Captures 4, 5, 6 share identical delivery and documents
    snapshot, _ = export_snapshot(
        root,
        contract=contract,
        policy=policy,
        captures=captures,
        receipts=receipts,
        streams=streams,
    )

    # Check that deduplication occurred: 6 checkpoints, but fewer unique captures
    assert len(snapshot["history"]) == 6
    assert len(snapshot["captures"]) < len(snapshot["history"])
    # Specifically, cp0001 (empty deliv, doc_initial), cp0002 (empty deliv, doc_phase),
    # cp0003 (code deliv, doc_phase), and cp0004..0006 (tests deliv, doc_phase) -> 4 unique captures
    assert len(snapshot["captures"]) == 4



@pytest.mark.parametrize('count', [False, True, -1, '0', None])
def test_stream_counts_require_exact_bounded_integer_before_mutation(tmp_path, count):
    contract, policy, captures, receipts, streams = _make_valid_payload()
    receipts['job-exec']['value']['stderr_bytes'] = count
    with pytest.raises(ValueError, match='bounded integer'):
        export_snapshot(tmp_path / 'snapshot', contract=contract, policy=policy,
                        captures=captures, receipts=receipts, streams=streams)
    assert not (tmp_path / 'snapshot').exists()


def test_namespace_conflict_rejected_before_snapshot_mutation(tmp_path):
    contract, policy, captures, receipts, streams = _make_valid_payload()
    captures[-1]['delivery']['pkg'] = 'file shadows directory'
    with pytest.raises(ValueError, match='namespace conflict'):
        export_snapshot(tmp_path / 'snapshot', contract=contract, policy=policy,
                        captures=captures, receipts=receipts, streams=streams)
    assert not (tmp_path / 'snapshot').exists()


def test_competing_changed_export_preserves_original_manifest_and_files(tmp_path):
    contract, policy, captures, receipts, streams = _make_valid_payload()
    root = tmp_path / 'snapshot'
    _, reference = export_snapshot(root, contract=contract, policy=policy,
                                   captures=captures, receipts=receipts, streams=streams)
    original_manifest = (root / 'snapshot.json').read_bytes()
    original_delivery = (root / 'delivery/README.md').read_bytes()
    altered = copy.deepcopy(captures); altered[-1]['delivery']['README.md'] = 'Changed independent export'
    with pytest.raises(ValueError, match='manifest changed'):
        export_snapshot(root, contract=contract, policy=policy,
                        captures=altered, receipts=receipts, streams=streams)
    assert (root / 'snapshot.json').read_bytes() == original_manifest
    assert (root / 'delivery/README.md').read_bytes() == original_delivery
    assert read_snapshot(root, reference['manifest_sha256'])['delivery'] == captures[-1]['delivery']


def test_export_refuses_symlink_directory_without_changing_target_permissions(tmp_path):
    contract, policy, captures, receipts, streams = _make_valid_payload()
    root = tmp_path / 'snapshot'; root.mkdir(mode=0o700)
    outside = tmp_path / 'outside'; outside.mkdir(mode=0o755)
    before = outside.stat().st_mode
    (root / 'host').symlink_to(outside, target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        export_snapshot(root, contract=contract, policy=policy,
                        captures=captures, receipts=receipts, streams=streams)
    assert outside.stat().st_mode == before
    assert not list(outside.iterdir())


def test_input_mutation_after_validation_cannot_change_committed_snapshot(tmp_path, monkeypatch):
    from specorganon import t_common_snapshot as module
    from contextlib import contextmanager
    contract, policy, captures, receipts, streams = _make_valid_payload()
    expected = copy.deepcopy(captures[-1]['delivery']); original = module._export_lock
    @contextmanager
    def mutate_while_waiting(root):
        captures[-1]['delivery']['README.md'] = 'Concurrent caller mutation'
        captures[-1]['documents']['SPEC.md'] = 'Concurrent caller mutation'
        with original(root): yield
    monkeypatch.setattr(module, '_export_lock', mutate_while_waiting)
    snapshot, _ = export_snapshot(tmp_path / 'snapshot', contract=contract, policy=policy,
                                  captures=captures, receipts=receipts, streams=streams)
    assert snapshot['delivery'] == expected
    assert snapshot['documents']['SPEC.md'] != 'Concurrent caller mutation'
