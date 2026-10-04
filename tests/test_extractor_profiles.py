"""Profiles must opt in, fail closed, and disclose historical divergence."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import audit_bread_sources as auditor
from specorganon.source_passages import SourceAuditError, SourceSpec, read_pdf_pages

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "cachyos-26.08.0-x86_64-v4"
CURRENT_PIN = "47253257c7a7995ea6c8ad54b47b0edece8739dd4102c7bcd5a729472c386fb4"
HISTORICAL_PIN = "0fb98ea179e19154a90202608c164f2a319b79f16576fa6534b2d601033565e7"
PDF = ROOT / "cases/bread_norway/source_lca.pdf"
SPEC = SourceSpec(2212666, "9d64c0538b76ebaa19af86fb7ec231243cb5e1272316105ad979cfb9b6de3a32")


@pytest.fixture
def candidate_host():
    if (not Path("/usr/bin/pdftotext").is_file()
            or hashlib.sha256(Path("/usr/bin/pdftotext").read_bytes()).hexdigest() != CURRENT_PIN):
        pytest.skip("integration requires the explicitly pinned candidate installation")


@pytest.mark.parametrize("name", ["not-registered", ""])
def test_unknown_profile_rejects_even_when_host_binary_is_available(monkeypatch, name):
    # A silent fallback here would turn a misspelled deployment into false success.
    monkeypatch.setenv("SPECORGANON_EXTRACTOR_PROFILE", name)
    with pytest.raises(SourceAuditError, match="profile"):
        read_pdf_pages(PDF, SPEC)


def test_explicit_profile_revalidates_without_rewriting_historical_contract(monkeypatch, candidate_host):
    # Removing profile selection would reproduce the host portability failure;
    # dropping provenance would falsely suggest the historical binary was used.
    monkeypatch.setenv("SPECORGANON_EXTRACTOR_PROFILE", PROFILE)
    before = auditor.CONTRACT.read_bytes()
    result = auditor.audit_bread_sources()
    assert result["verified_claims"] == 17
    assert result["verified_survey_rows"] == 7
    assert result["extractor_selection"]["historical_binary_reproduced"] is False
    assert result["extractor_selection"]["contract_sha256"] == HISTORICAL_PIN
    assert result["extractor_selection"]["profile"] == PROFILE
    assert result["extractor_selection"]["profile_review_status"] == "candidate_pending_independent_review"
    assert result["source_extraction"]["lca"]["extractor_sha256"] == CURRENT_PIN
    assert result["input_pins"]["contract"]["sha256"] == hashlib.sha256(before).hexdigest()
    assert auditor.CONTRACT.read_bytes() == before


def test_no_profile_does_not_auto_trust_new_host_binary(monkeypatch, candidate_host):
    monkeypatch.delenv("SPECORGANON_EXTRACTOR_PROFILE", raising=False)
    assert hashlib.sha256(Path("/usr/bin/pdftotext").read_bytes()).hexdigest() == CURRENT_PIN
    with pytest.raises(SourceAuditError, match="extractor bytes"):
        auditor.audit_bread_sources()


def test_cli_profile_is_explicit_and_unknown_profile_emits_no_receipt(tmp_path, monkeypatch, candidate_host):
    monkeypatch.delenv("SPECORGANON_EXTRACTOR_PROFILE", raising=False)
    receipt = tmp_path / "receipt.json"
    command = [sys.executable, str(ROOT / "scripts/audit_bread_sources.py"),
               "--extractor-profile", PROFILE, "--output", str(receipt)]
    completed = subprocess.run(command, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(receipt.read_text())["extractor_selection"]["profile"] == PROFILE
    receipt.unlink()
    command[command.index(PROFILE)] = "not-registered"
    rejected = subprocess.run(command, capture_output=True, text=True)
    assert rejected.returncode == 2
    assert not receipt.exists()
    assert "profile" in rejected.stderr


def test_runtime_without_memfd_rejects_with_domain_error(monkeypatch, candidate_host):
    # Removing capability admission would leak AttributeError to CLI consumers.
    monkeypatch.setenv("SPECORGANON_EXTRACTOR_PROFILE", PROFILE)
    monkeypatch.delattr(os, "memfd_create", raising=False)
    with pytest.raises(SourceAuditError, match="sealed"):
        read_pdf_pages(PDF, SPEC)
