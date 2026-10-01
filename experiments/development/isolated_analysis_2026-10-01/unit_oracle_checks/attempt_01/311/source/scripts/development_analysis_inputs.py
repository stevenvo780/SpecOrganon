"""Build common, pinned PDF text inputs outside the participant sandbox.

Only the two exposed bread PDFs are extracted. Original source manifests and
tasks remain unchanged. The returned file inventory can extend a new case.json.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOL = Path("/usr/bin/pdftotext")
TOOL_SHA256 = "0fb98ea179e19154a90202608c164f2a319b79f16576fa6534b2d601033565e7"
TOOL_VERSION = "pdftotext version 24.02.0"
ARCHIVED_MANIFEST = "experiments/development/bread_continuation_2026-09-30/raw_texts/text_manifest.json"
ARCHIVED_MANIFEST_SHA256 = "5c93953df0ec933bf06e9eebe419612be555df7f00a48c718c7354b64a7b41fa"
DOCUMENTS = {
    "source_lca": {
        "pdf_sha256": "9d64c0538b76ebaa19af86fb7ec231243cb5e1272316105ad979cfb9b6de3a32",
        "pdf_bytes": 2_212_666,
        "text_sha256": "e65be3ae44b90aa7a78eabde032d874d97897db0ba458e8015e7c8f6d8c10582",
        "text_bytes": 93_076,
    },
    "source_survey": {
        "pdf_sha256": "61b3b63cc7b5748138335fa2eaebde2f4ab0e454750e4592582fb80a5043dcee",
        "pdf_bytes": 526_604,
        "text_sha256": "1ee82f5fe6c51981b640995d9ddcaebd1077cf0315f45744f5ffdd1981b514f3",
        "text_bytes": 75_822,
    },
}
CLASSIFICATION = "common_public_pdf_text_derivation_not_reference_answers"


class AnalysisInputsError(ValueError):
    """A source pin, extractor or new destination cannot be accepted."""


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def read_pinned(path: Path, expected: str, size: int | None = None) -> bytes:
    """Read one bounded regular file without following its final symlink."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= 20_000_000:
                raise AnalysisInputsError(f"source is not a bounded regular file: {path.name}")
            raw = stream.read(20_000_001)
            after = os.fstat(stream.fileno())
        attrs = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, key) != getattr(after, key) for key in attrs):
            raise AnalysisInputsError(f"source changed during read: {path.name}")
    except OSError as exc:
        raise AnalysisInputsError(f"cannot read pinned source: {path.name}") from exc
    if len(raw) > 20_000_000 or (size is not None and len(raw) != size) or sha(raw) != expected:
        raise AnalysisInputsError(f"source bytes differ from pin: {path.name}")
    return raw


@contextmanager
def _sealed(raw: bytes, name: str, *, executable: bool = False):
    fd = None
    try:
        fd = os.memfd_create(name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        with os.fdopen(os.dup(fd), "wb") as stream:
            stream.write(raw)
        os.fchmod(fd, 0o500 if executable else 0o400)
        seals = sum(getattr(fcntl, key, default) for key, default in (
            ("F_SEAL_SEAL", 1), ("F_SEAL_SHRINK", 2), ("F_SEAL_GROW", 4), ("F_SEAL_WRITE", 8),
        ))
        fcntl.fcntl(fd, getattr(fcntl, "F_ADD_SEALS", 1033), seals)
        yield fd
    except OSError as exc:
        raise AnalysisInputsError("cannot seal public source/extractor snapshot") from exc
    finally:
        if fd is not None:
            os.close(fd)


def _sources() -> tuple[dict[str, bytes], dict[str, bytes], bytes, dict[str, str]]:
    manifest_raw = read_pinned(ROOT / ARCHIVED_MANIFEST, ARCHIVED_MANIFEST_SHA256)
    manifest = json.loads(manifest_raw)
    if (manifest["tool_sha256"] != TOOL_SHA256
            or manifest["tool_version"].splitlines()[0] != TOOL_VERSION):
        raise AnalysisInputsError("archived extraction identity differs")
    pdfs, texts = {}, {}
    pins = {ARCHIVED_MANIFEST: ARCHIVED_MANIFEST_SHA256, str(TOOL): TOOL_SHA256}
    tool = read_pinned(TOOL, TOOL_SHA256)
    for name, info in DOCUMENTS.items():
        pdf_path = f"cases/bread_norway/{name}.pdf"
        text_path = str(Path(ARCHIVED_MANIFEST).parent / f"{name}.txt")
        pdfs[name] = read_pinned(ROOT / pdf_path, info["pdf_sha256"], info["pdf_bytes"])
        texts[name] = read_pinned(ROOT / text_path, info["text_sha256"], info["text_bytes"])
        record = manifest["records"][f"{name}.txt"]
        if (record["sha256"] != info["text_sha256"] or record["bytes"] != info["text_bytes"]
                or record["original_pdf_sha256"] != info["pdf_sha256"]):
            raise AnalysisInputsError("archived text provenance differs")
        pins[pdf_path], pins[text_path] = info["pdf_sha256"], info["text_sha256"]
    return pdfs, texts, tool, pins


def expected_bundle(texts: dict[str, bytes]) -> dict[str, bytes]:
    """Deterministic bundle shared by creation and independent source checking."""
    files, documents = {}, []
    for name, info in DOCUMENTS.items():
        raw = texts[name]
        if len(raw) != info["text_bytes"] or sha(raw) != info["text_sha256"]:
            raise AnalysisInputsError("full text differs from pinned public extraction")
        try:
            pages = raw.decode("utf-8").split("\f")
        except UnicodeError as exc:
            raise AnalysisInputsError("public extraction is not UTF-8") from exc
        if not pages[-1].strip():
            pages.pop()
        if not pages or any(not page.strip() for page in pages):
            raise AnalysisInputsError("public extraction has an empty page")
        full_name = f"{name}.txt"
        files[full_name] = raw
        page_records = []
        for page, content in enumerate(pages, start=1):
            page_name = f"{name}_page_{page:02d}.txt"
            encoded = content.encode("utf-8")
            files[page_name] = encoded
            page_records.append({"page": page, "path": page_name, "sha256": sha(encoded), "bytes": len(encoded)})
        documents.append({
            "original_pdf": f"{name}.pdf", "original_pdf_sha256": info["pdf_sha256"],
            "original_pdf_bytes": info["pdf_bytes"],
            "license": "CC BY 4.0", "license_basis": "license declaration in archived article text",
            "full_text": {"path": full_name, "sha256": info["text_sha256"], "bytes": len(raw)},
            "pages": page_records,
        })
    manifest = {
        "schema": 1, "classification": CLASSIFICATION,
        "original_text_manifest_sha256": ARCHIVED_MANIFEST_SHA256,
        "extractor": {"path": str(TOOL), "sha256": TOOL_SHA256, "version": TOOL_VERSION,
                      "host_shared_libraries_authenticated": False},
        "extraction": "pdftotext -layout -enc UTF-8; full PDFs; formfeed page boundaries",
        "documents": documents,
        "no_analysis_answers_added": True,
    }
    files["text_extract_manifest.json"] = canonical(manifest)
    return files


def verify_text_inputs(directory: Path) -> dict[str, str]:
    """Verify complete text, every page and manifest without executing an extractor."""
    texts = {name: read_pinned(directory / f"{name}.txt", info["text_sha256"], info["text_bytes"])
             for name, info in DOCUMENTS.items()}
    expected = expected_bundle(texts)
    for name, raw in expected.items():
        read_pinned(directory / name, sha(raw), len(raw))
    return {name: sha(raw) for name, raw in expected.items()}


def _parent(destination: Path) -> int:
    if not destination.is_absolute() or destination.name in ("", ".", ".."):
        raise AnalysisInputsError("destination must be a new absolute directory")
    try:
        fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
            os.close(fd)
            raise AnalysisInputsError("destination parent must be owned and not writable by others")
        try:
            os.stat(destination.name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            os.close(fd)
            raise AnalysisInputsError("destination must not already exist")
    except OSError as exc:
        raise AnalysisInputsError("destination parent cannot be opened") from exc
    return fd


def build_text_inputs(destination: Path) -> dict[str, Any]:
    """Reproduce pinned texts, then exclusively create a private flat bundle."""
    destination = Path(destination)
    parent_fd = _parent(destination)
    try:
        # Every fixed original is checked before creating the destination.
        pdfs, archived_texts, tool, pins = _sources()
        generated = {}
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        with _sealed(tool, "development-pdftotext", executable=True) as tool_fd:
            executable = f"/proc/self/fd/{tool_fd}"
            version = subprocess.run([str(TOOL), "-v"], executable=executable, pass_fds=(tool_fd,),
                                     env=env, capture_output=True, timeout=5, check=True)
            actual_version = (version.stdout + version.stderr).decode("utf-8").splitlines()[0]
            if actual_version != TOOL_VERSION:
                raise AnalysisInputsError("extractor version differs from archived identity")
            for name, raw in pdfs.items():
                with _sealed(raw, "development-public-pdf") as pdf_fd:
                    process = subprocess.run(
                        [str(TOOL), "-layout", "-enc", "UTF-8", f"/proc/self/fd/{pdf_fd}", "-"],
                        executable=executable, pass_fds=(tool_fd, pdf_fd), env=env,
                        capture_output=True, timeout=20, check=True,
                    )
                if process.stdout != archived_texts[name]:
                    raise AnalysisInputsError(f"current extraction differs from archived text: {name}")
                generated[name] = process.stdout
        files = expected_bundle(generated)
        _sources()  # Original paths must still satisfy the fixed pins.
        try:
            os.mkdir(destination.name, 0o700, dir_fd=parent_fd)
            directory_fd = os.open(destination.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        except OSError as exc:
            raise AnalysisInputsError("destination must be a new private directory") from exc
        try:
            os.fchmod(directory_fd, 0o700)
            for name, raw in files.items():
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
                with os.fdopen(fd, "wb") as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
            os.fsync(directory_fd)
            os.fsync(parent_fd)
        finally:
            os.close(directory_fd)
        verify_text_inputs(destination)
        _sources()  # Detect source/extractor replacement after output I/O.
        return {
            "schema": 1, "classification": CLASSIFICATION,
            "files": [{"path": name, "sha256": sha(raw), "bytes": len(raw)} for name, raw in files.items()],
            "source_pins": pins, "extractor_version": actual_version,
            "text_extract_manifest_sha256": sha(files["text_extract_manifest.json"]),
        }
    except (subprocess.SubprocessError, UnicodeError, IndexError) as exc:
        raise AnalysisInputsError("pinned external PDF extraction failed") from exc
    finally:
        os.close(parent_fd)
