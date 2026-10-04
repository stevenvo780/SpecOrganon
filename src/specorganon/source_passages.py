"""Extract uniquely located passages from the exact bytes of a pinned PDF.

Selectors are reviewed caller input. Matching a passage checks a transcription;
it does not authenticate the authors, establish causality, or interpret a base.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from contextlib import contextmanager
from pathlib import Path


class SourceAuditError(ValueError):
    """A source or uniquely located passage does not satisfy its contract."""


@dataclass(frozen=True)
class SourceSpec:
    bytes: int
    sha256: str


@dataclass(frozen=True)
class ExtractorSpec:
    path: Path
    sha256: str


# Reviewed local Linux default. Other installations must supply a reviewed pin.
DEFAULT_EXTRACTOR = ExtractorSpec(
    Path("/usr/bin/pdftotext"),
    "0fb98ea179e19154a90202608c164f2a319b79f16576fa6534b2d601033565e7",
)

# Candidate installation profile: explicit opt-in, never derived from host bytes.
# Its extraction comparison is retained under goals/autonomous-software-v1.
_INSTALLATION_PROFILES = {
    "cachyos-26.08.0-x86_64-v4": ExtractorSpec(
        Path("/usr/bin/pdftotext"),
        "47253257c7a7995ea6c8ad54b47b0edece8739dd4102c7bcd5a729472c386fb4",
    ),
}


def configured_extractor(
    fallback: ExtractorSpec = DEFAULT_EXTRACTOR, *, profile: str | None = None,
) -> ExtractorSpec:
    """Select an explicit fixed pin; absence preserves the caller's contract.

    Profiles identify installation bytes, not method acceptance or authenticated
    host libraries. Unknown/empty profile names reject rather than fall back.
    """
    name = os.environ.get("SPECORGANON_EXTRACTOR_PROFILE") if profile is None else profile
    if name is None:
        return fallback
    try:
        return _INSTALLATION_PROFILES[name]
    except KeyError as exc:
        raise SourceAuditError(f"unknown extractor profile: {name!r}") from exc

# Linux constants are absent from some supported CPython 3.11 builds.
_F_ADD_SEALS = getattr(fcntl, "F_ADD_SEALS", 1033)
_F_SEALS = (getattr(fcntl, "F_SEAL_WRITE", 0x08)
            | getattr(fcntl, "F_SEAL_GROW", 0x04)
            | getattr(fcntl, "F_SEAL_SHRINK", 0x02)
            | getattr(fcntl, "F_SEAL_SEAL", 0x01))


@dataclass(frozen=True)
class PdfPages:
    pages: tuple[str, ...]
    source_sha256: str
    source_bytes: int
    text_sha256: str
    extractor_version: str
    extractor_path: str
    extractor_sha256: str


def normalize_whitespace(text: str) -> str:
    """Collapse whitespace only; preserve numbers, punctuation and dash types."""
    return re.sub(r"\s+", " ", text).strip()


@contextmanager
def _sealed_extractor(spec: ExtractorSpec):
    """Execute the verified binary bytes, without a second path lookup."""
    if not all(hasattr(os, name) for name in ("memfd_create", "MFD_CLOEXEC", "MFD_ALLOW_SEALING")):
        raise SourceAuditError("runtime lacks sealed memfd extractor support")
    if (not spec.path.is_absolute()
            or re.fullmatch(r"[0-9a-f]{64}", spec.sha256) is None):
        raise SourceAuditError("extractor needs an absolute path and reviewed digest")
    sealed = None
    try:
        fd = os.open(spec.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 20_000_000:
                raise SourceAuditError("extractor is not a bounded regular file")
            raw = stream.read(20_000_001)
        if hashlib.sha256(raw).hexdigest() != spec.sha256:
            raise SourceAuditError("extractor bytes differ from reviewed digest")
        sealed = os.memfd_create("organon-pdftotext", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        with os.fdopen(os.dup(sealed), "wb") as stream:
            stream.write(raw)
        os.fchmod(sealed, 0o500)
        fcntl.fcntl(sealed, _F_ADD_SEALS, _F_SEALS)
        yield f"/proc/self/fd/{sealed}", sealed
    except OSError as exc:
        raise SourceAuditError("cannot capture and seal reviewed extractor") from exc
    finally:
        if sealed is not None:
            os.close(sealed)


def read_pdf_pages(
    path: Path, spec: SourceSpec, extractor: ExtractorSpec | None = None,
) -> PdfPages:
    """Hash once, then extract a private snapshot of those same source bytes."""
    # An explicit caller pin always wins; environment cannot bypass its check.
    if extractor is None:
        extractor = configured_extractor()
    if (type(spec.bytes) is not int or not 0 < spec.bytes <= 20_000_000
            or not isinstance(spec.sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", spec.sha256) is None):
        raise SourceAuditError("invalid PDF source pin")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != spec.bytes:
                raise SourceAuditError("PDF source size/type differs from pin")
            raw = stream.read(spec.bytes + 1)
    except OSError as exc:
        raise SourceAuditError(f"cannot read pinned PDF: {path.name}") from exc
    if len(raw) != spec.bytes or hashlib.sha256(raw).hexdigest() != spec.sha256:
        raise SourceAuditError("PDF source bytes differ from pin")
    try:
        with _sealed_extractor(extractor) as (executable, fd), tempfile.TemporaryDirectory(
            prefix="organon-source-passage-",
        ) as folder:
            snapshot = Path(folder) / "source.pdf"
            snapshot.write_bytes(raw)
            env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
            extracted = subprocess.run(
                [str(extractor.path), "-layout", "-enc", "UTF-8", str(snapshot), "-"],
                executable=executable, pass_fds=(fd,), env=env,
                capture_output=True, timeout=20, check=True,
            )
            version = subprocess.run(
                [str(extractor.path), "-v"], executable=executable, pass_fds=(fd,), env=env,
                capture_output=True, timeout=5, check=True,
            )
        version_text = (version.stdout + version.stderr).decode("utf-8").splitlines()[0]
        text = extracted.stdout.decode("utf-8")
    except (OSError, subprocess.SubprocessError, UnicodeError, IndexError) as exc:
        raise SourceAuditError("Poppler pdftotext extraction failed") from exc
    if not text or len(extracted.stdout) > 2_000_000:
        raise SourceAuditError("PDF extraction empty or too large")
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    if not pages or any(not page.strip() for page in pages):
        raise SourceAuditError("PDF extraction contains an empty page")
    return PdfPages(
        tuple(pages), spec.sha256, len(raw),
        hashlib.sha256(extracted.stdout).hexdigest(), version_text,
        str(extractor.path), extractor.sha256,
    )


def extract_passage(
    pdf: PdfPages, page: int, start: str, end: str, pattern: str,
    required: tuple[str, ...] = (),
) -> dict:
    """Require one page, one pair of anchors, and exactly one regex match.

    Passage/match digests use whitespace-normalized UTF-8; the page digest
    uses raw extracted UTF-8. Neither is a digest of the original PDF bytes.
    """
    if type(page) is not int or not 1 <= page <= len(pdf.pages):
        raise SourceAuditError("PDF page outside extracted source")
    raw = pdf.pages[page - 1]
    text = normalize_whitespace(raw)
    begin, finish = normalize_whitespace(start), normalize_whitespace(end)
    if not begin or not finish or text.count(begin) != 1:
        raise SourceAuditError("start locator missing or ambiguous")
    if text.count(finish) != 1:
        raise SourceAuditError("end locator missing or ambiguous")
    tail = text.split(begin, 1)[1]
    if tail.count(finish) != 1:
        raise SourceAuditError("end locator missing or ambiguous")
    passage = begin + " " + tail.split(finish, 1)[0].strip()
    for context in required:
        if normalize_whitespace(context) not in passage:
            raise SourceAuditError("required unit/base/provenance context missing")
    try:
        matches = list(re.finditer(pattern, passage))
    except re.error as exc:
        raise SourceAuditError("invalid reviewed passage pattern") from exc
    if len(matches) != 1 or not matches[0].groupdict():
        raise SourceAuditError("numeric locator missing, ambiguous or unnamed")
    if any(value is None for value in matches[0].groupdict().values()):
        raise SourceAuditError("numeric locator has unmatched groups")
    match = matches[0].group(0)
    return {
        "source_sha256": pdf.source_sha256,
        "page": page,
        "page_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "passage_sha256": hashlib.sha256(passage.encode()).hexdigest(),
        "matched_sha256": hashlib.sha256(match.encode()).hexdigest(),
        "normalization": "whitespace_only",
        "groups": matches[0].groupdict(),
        "matched_text": match,
    }
