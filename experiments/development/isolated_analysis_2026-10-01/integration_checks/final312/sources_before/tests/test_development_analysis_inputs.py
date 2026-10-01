"""Common text preparation reproduces fixed public PDFs and preserves failures."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import development_analysis_inputs as inputs  # noqa: E402


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    destination = tmp_path_factory.mktemp("D113-public-texts") / "texts"
    metadata = inputs.build_text_inputs(destination)
    return destination, metadata


def source_copy(destination: Path) -> Path:
    root = destination / "source"
    paths = [inputs.ARCHIVED_MANIFEST]
    for name in inputs.DOCUMENTS:
        paths.extend([f"cases/bread_norway/{name}.pdf", str(Path(inputs.ARCHIVED_MANIFEST).parent / f"{name}.txt")])
    for relative in paths:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return root


def test_real_pinned_extraction_yields_complete_flat_private_bundle(prepared) -> None:
    destination, metadata = prepared
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert metadata["extractor_version"] == "pdftotext version 24.02.0"
    assert metadata["classification"] == "common_public_pdf_text_derivation_not_reference_answers"
    inventory = {item["path"]: item for item in metadata["files"]}
    assert set(inventory) == {path.name for path in destination.iterdir()}
    manifest = json.loads((destination / "text_extract_manifest.json").read_bytes())
    assert manifest["no_analysis_answers_added"] is True
    assert manifest["original_text_manifest_sha256"] == inputs.ARCHIVED_MANIFEST_SHA256
    assert manifest["extractor"]["host_shared_libraries_authenticated"] is False
    for document in manifest["documents"]:
        name = document["original_pdf"].removesuffix(".pdf")
        original = (ROOT / Path(inputs.ARCHIVED_MANIFEST).parent / f"{name}.txt").read_bytes()
        assert (destination / f"{name}.txt").read_bytes() == original
        pages = original.decode("utf-8").split("\f")
        if not pages[-1].strip():
            pages.pop()
        assert len(document["pages"]) == len(pages)
        assert document["license"] == "CC BY 4.0"
        for number, (page, text) in enumerate(zip(document["pages"], pages, strict=True), start=1):
            assert page["path"] == f"{name}_page_{number:02d}.txt"
            assert (destination / page["path"]).read_bytes() == text.encode("utf-8")
    for item in inventory.values():
        assert set(item) == {"path", "sha256", "bytes"}
        path = destination / item["path"]
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        assert len(raw) == item["bytes"]
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert inputs.verify_text_inputs(destination) == {name: item["sha256"] for name, item in inventory.items()}
    # Fixed originals, extractor and archival text remain the same after I/O.
    _, _, _, observed_pins = inputs._sources()
    assert observed_pins == metadata["source_pins"]


@pytest.mark.parametrize("relative", [
    "cases/bread_norway/source_lca.pdf",
    inputs.ARCHIVED_MANIFEST,
    str(Path(inputs.ARCHIVED_MANIFEST).parent / "source_survey.txt"),
])
def test_modified_source_rejects_before_mkdir_or_extractor(tmp_path, monkeypatch, relative) -> None:
    root = source_copy(tmp_path)
    altered = root / relative
    altered.write_bytes(altered.read_bytes() + b"\n")
    monkeypatch.setattr(inputs, "ROOT", root)
    def unexpected(*args, **kwargs):
        pytest.fail("extractor must not run before source pins pass")
    monkeypatch.setattr(inputs.subprocess, "run", unexpected)
    destination = tmp_path / "new"
    with pytest.raises(inputs.AnalysisInputsError, match="differ from pin"):
        inputs.build_text_inputs(destination)
    assert not destination.exists()


def test_symlink_pdf_and_wrong_extractor_reject_before_destination(tmp_path, monkeypatch) -> None:
    root = source_copy(tmp_path)
    pdf = root / "cases/bread_norway/source_lca.pdf"
    pdf.unlink()
    pdf.symlink_to(ROOT / "cases/bread_norway/source_lca.pdf")
    monkeypatch.setattr(inputs, "ROOT", root)
    with pytest.raises(inputs.AnalysisInputsError, match="pinned source"):
        inputs.build_text_inputs(tmp_path / "symlink-rejected")
    assert not (tmp_path / "symlink-rejected").exists()
    monkeypatch.setattr(inputs, "ROOT", ROOT)
    fake = tmp_path / "wrong-pdftotext"
    fake.write_bytes(b"public negative fixture, not an executable")
    monkeypatch.setattr(inputs, "TOOL", fake)
    with pytest.raises(inputs.AnalysisInputsError, match="differ from pin"):
        inputs.build_text_inputs(tmp_path / "extractor-rejected")
    assert not (tmp_path / "extractor-rejected").exists()


def test_changed_extraction_never_creates_destination(tmp_path, monkeypatch) -> None:
    calls = []
    def fake(argv, **kwargs):
        calls.append(argv)
        if "-v" in argv:
            return SimpleNamespace(stdout=b"", stderr=b"pdftotext version 24.02.0\n")
        return SimpleNamespace(stdout=b"public fake extractor output", stderr=b"")
    monkeypatch.setattr(inputs.subprocess, "run", fake)
    destination = tmp_path / "wrong-extraction"
    with pytest.raises(inputs.AnalysisInputsError, match="differs from archived text"):
        inputs.build_text_inputs(destination)
    assert len(calls) == 2 and not destination.exists()


def test_post_io_source_failure_preserves_new_artifacts(tmp_path, monkeypatch) -> None:
    original = inputs._sources
    count = 0
    def check():
        nonlocal count
        count += 1
        if count == 3:
            raise inputs.AnalysisInputsError("injected post-I/O source replacement")
        return original()
    monkeypatch.setattr(inputs, "_sources", check)
    destination = tmp_path / "retained-failure"
    with pytest.raises(inputs.AnalysisInputsError, match="post-I/O"):
        inputs.build_text_inputs(destination)
    assert (destination / "text_extract_manifest.json").is_file()
    assert inputs.verify_text_inputs(destination)


@pytest.mark.parametrize("name", ["source_lca.txt", "source_survey_page_04.txt", "text_extract_manifest.json"])
def test_bundle_tampering_is_rejected(prepared, tmp_path, name) -> None:
    destination, _ = prepared
    copied = tmp_path / "changed"
    shutil.copytree(destination, copied)
    path = copied / name
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(inputs.AnalysisInputsError, match="differ from pin"):
        inputs.verify_text_inputs(copied)


def test_existing_destination_never_relaunches_and_unsafe_parent_is_rejected(tmp_path, monkeypatch) -> None:
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "marker").write_bytes(b"preserve public negative fixture")
    def unexpected(*args, **kwargs):
        pytest.fail("existing destination must fail before external execution")
    monkeypatch.setattr(inputs.subprocess, "run", unexpected)
    with pytest.raises(inputs.AnalysisInputsError, match="already exist"):
        inputs.build_text_inputs(destination)
    assert (destination / "marker").read_bytes() == b"preserve public negative fixture"
    unsafe = tmp_path / "unsafe-parent"
    unsafe.mkdir()
    os.chmod(unsafe, 0o777)
    with pytest.raises(inputs.AnalysisInputsError, match="parent"):
        inputs.build_text_inputs(unsafe / "child")
    assert not (unsafe / "child").exists()
