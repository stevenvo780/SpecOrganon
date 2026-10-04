"""The generic passage primitive binds unique matches to pinned PDF bytes."""
from __future__ import annotations

import hashlib
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from specorganon import source_passages
from specorganon.source_passages import (
    DEFAULT_EXTRACTOR,
    configured_extractor,
    ExtractorSpec,
    SourceAuditError,
    SourceSpec,
    extract_passage,
    read_pdf_pages,
)

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "cases/bread_norway/source_lca.pdf"
SPEC = SourceSpec(bytes=2212666, sha256="9d64c0538b76ebaa19af86fb7ec231243cb5e1272316105ad979cfb9b6de3a32")


@pytest.fixture(scope="module")
def source_pdf():
    return read_pdf_pages(PDF, SPEC)


def _synthetic(pdf, text):
    return replace(pdf, pages=(text,))


def _extract(pdf, *, page=1, start="BEGIN", end="END", pattern=r"(?P<value>\d+) (?P<unit>kWh/t_flour)", required=()):
    return extract_passage(pdf, page, start, end, pattern, required)


def test_read_real_pdf_retains_page_and_extractor_provenance(source_pdf):
    assert isinstance(source_pdf.pages, tuple)
    assert len(source_pdf.pages) >= 8
    assert source_pdf.source_sha256 == SPEC.sha256
    assert len(source_pdf.text_sha256) == 64
    assert source_pdf.extractor_version
    assert source_pdf.extractor_path == str(configured_extractor().path)
    assert source_pdf.extractor_sha256 == configured_extractor().sha256
    assert "736" in source_pdf.pages[5]


def test_unique_named_match_is_bound_to_page_and_passage(source_pdf):
    text = "BEGIN Reported energy 129 kWh/t_flour END"
    pdf = _synthetic(source_pdf, text)
    result = _extract(pdf, required=("Reported energy", "kWh/t_flour"))
    assert result["groups"] == {"value": "129", "unit": "kWh/t_flour"}
    assert len(result["page_sha256"]) == len(result["passage_sha256"]) == 64
    assert "129 kWh/t_flour" in result["matched_text"]
    assert result["page_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert result["matched_sha256"] == hashlib.sha256(result["matched_text"].encode()).hexdigest()
    assert result["source_sha256"] == SPEC.sha256


def test_only_whitespace_is_normalized_without_losing_original_page_binding(source_pdf):
    plain = _synthetic(source_pdf, "BEGIN Reported energy 129 kWh/t_flour END")
    spaces = _synthetic(source_pdf, "BEGIN\n Reported\tenergy  \n129\t kWh/t_flour \nEND")
    first = _extract(plain, required=("Reported energy",))
    second = _extract(spaces, required=("Reported energy",))
    assert first["groups"] == second["groups"]
    assert first["page_sha256"] != second["page_sha256"]
    assert first["passage_sha256"] == second["passage_sha256"]


@pytest.mark.parametrize("text", [
    "BEGIN 129 kWh/t_flour END BEGIN 130 kWh/t_flour END",
    "BEGIN 129 kWh/t_flour END END",
    "BEGIN BEGIN 129 kWh/t_flour END",
    "BEGIN 129 kWh/t_flour and 130 kWh/t_flour END",
    "END BEGIN 129 kWh/t_flour END",
])
def test_ambiguous_anchor_or_match_is_rejected(source_pdf, text):
    with pytest.raises(SourceAuditError):
        _extract(_synthetic(source_pdf, text))


@pytest.mark.parametrize("text", [
    "129 kWh/t_flour END", "BEGIN 129 kWh/t_flour", "END 129 kWh/t_flour BEGIN",
    "BEGIN 129 KWH/t_flour END", "BEGIN 129 kWh/t_flóur END",
])
def test_missing_or_reversed_anchor_and_non_whitespace_changes_fail(source_pdf, text):
    with pytest.raises(SourceAuditError):
        _extract(_synthetic(source_pdf, text))


def test_required_context_cannot_be_satisfied_outside_the_passage(source_pdf):
    pdf = _synthetic(source_pdf, "Reported energy BEGIN 129 kWh/t_flour END")
    with pytest.raises(SourceAuditError):
        _extract(pdf, required=("Reported energy",))


@pytest.mark.parametrize("page", [0, -1, 2, True, 1.5])
def test_page_selection_requires_valid_one_based_integer(source_pdf, page):
    pdf = _synthetic(source_pdf, "BEGIN 129 kWh/t_flour END")
    with pytest.raises(SourceAuditError):
        _extract(pdf, page=page)


@pytest.mark.parametrize("field,value", [
    ("start", ""), ("end", ""), ("pattern", ""), ("pattern", "("),
])
def test_invalid_contract_patterns_fail_closed(source_pdf, field, value):
    pdf = _synthetic(source_pdf, "BEGIN 129 kWh/t_flour END")
    with pytest.raises(SourceAuditError):
        _extract(pdf, **{field: value})


def test_changed_pdf_bytes_reject_before_extraction(tmp_path):
    changed = tmp_path / "changed.pdf"
    changed.write_bytes(PDF.read_bytes() + b"\nchanged\n")
    with pytest.raises(SourceAuditError):
        read_pdf_pages(changed, SPEC)


def test_same_size_pdf_mutation_is_not_hidden_by_size_check(tmp_path):
    changed = tmp_path / "changed.pdf"
    raw = bytearray(PDF.read_bytes())
    raw[-10] ^= 1
    changed.write_bytes(raw)
    assert changed.stat().st_size == SPEC.bytes
    assert hashlib.sha256(changed.read_bytes()).hexdigest() != SPEC.sha256
    with pytest.raises(SourceAuditError):
        read_pdf_pages(changed, SPEC)


def test_symlink_pdf_is_not_an_authenticated_regular_archive(tmp_path):
    linked = tmp_path / "linked.pdf"
    linked.symlink_to(PDF)
    with pytest.raises(SourceAuditError):
        read_pdf_pages(linked, SPEC)


def test_path_shim_is_not_invoked_for_pinned_extraction(tmp_path, monkeypatch, source_pdf):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shim = bindir / "pdftotext"
    shim.write_text("#!/bin/sh\nexit 99\n")
    shim.chmod(0o700)
    monkeypatch.setenv("PATH", str(bindir))
    actual = read_pdf_pages(PDF, SPEC)
    assert actual.pages == source_pdf.pages
    assert actual.text_sha256 == source_pdf.text_sha256
    assert actual.extractor_sha256 == configured_extractor().sha256


def test_wrong_extractor_digest_rejects_before_process_launch(monkeypatch):
    def unexpected_launch(*args, **kwargs):
        pytest.fail("wrong reviewed extractor digest must fail before launching a process")
    monkeypatch.setattr(source_passages.subprocess, "run", unexpected_launch)
    wrong = ExtractorSpec(DEFAULT_EXTRACTOR.path, "0" * 64)
    with pytest.raises(SourceAuditError, match="extractor bytes"):
        read_pdf_pages(PDF, SPEC, extractor=wrong)


def test_pdf_snapshot_survives_original_path_change_after_hash(tmp_path, monkeypatch, source_pdf):
    local = tmp_path / "source.pdf"
    shutil.copyfile(PDF, local)
    temporary_directory = source_passages.tempfile.TemporaryDirectory
    changed = False

    def replace_before_snapshot(*args, **kwargs):
        nonlocal changed
        if not changed:
            local.write_bytes(b"changed after source capture and hash")
            changed = True
        return temporary_directory(*args, **kwargs)

    # Folder creation occurs after source verification and before snapshot write.
    monkeypatch.setattr(source_passages.tempfile, "TemporaryDirectory", replace_before_snapshot)
    actual = read_pdf_pages(local, SPEC)
    assert changed and local.read_bytes() != PDF.read_bytes()
    assert actual.pages == source_pdf.pages
    assert actual.source_sha256 == SPEC.sha256
    assert actual.text_sha256 == source_pdf.text_sha256


def test_sealed_binary_survives_extractor_path_change_after_capture(tmp_path, monkeypatch, source_pdf):
    local = tmp_path / "pdftotext"
    shutil.copyfile(configured_extractor().path, local)
    local.chmod(0o700)
    run = source_passages.subprocess.run
    launches = []

    def replace_after_capture(*args, **kwargs):
        if not launches:
            local.write_text("#!/bin/sh\nexit 99\n")
        launches.append(kwargs.get("executable"))
        return run(*args, **kwargs)

    monkeypatch.setattr(source_passages.subprocess, "run", replace_after_capture)
    actual = read_pdf_pages(PDF, SPEC, extractor=ExtractorSpec(local, configured_extractor().sha256))
    assert len(launches) == 2
    assert all(path.startswith("/proc/self/fd/") for path in launches)
    assert local.read_text() == "#!/bin/sh\nexit 99\n"
    assert actual.pages == source_pdf.pages
    assert actual.extractor_sha256 == configured_extractor().sha256
    assert actual.extractor_version == source_pdf.extractor_version
