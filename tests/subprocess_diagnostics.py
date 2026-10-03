"""Bounded failure notes for captured, non-secret test subprocess output.

Known credential-like lines and private-key blocks are suppressed as a safety
net. This is not a sanitizer for arbitrary secret-bearing programs: the original
exception and its captured output remain intact, and unlabeled secrets cannot
be identified reliably. Never include environment or command arguments in notes.
"""

from __future__ import annotations

import re
import subprocess
from contextlib import contextmanager


_OUTPUT_LIMIT = 4096  # Rendered characters per stream, after escaping/redaction.
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?"
    r"(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)",
    re.DOTALL,
)
_CREDENTIAL = re.compile(
    r"password|passwd|passphrase|secret|token|authorization|cookie|credential|"
    r"(?:private|api|access)[_ -]?key|--signature|bearer\s|basic\s|"
    r"[a-z][a-z0-9+.-]*://[^\s/]*@|"
    r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,}|"
    r"github_pat_[A-Za-z0-9_]{16,}|"
    r"AKIA[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.)",
    re.IGNORECASE,
)


def _output_note(raw: str | bytes | None) -> str:
    if raw is None:
        return "<not captured>"
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    text = _PRIVATE_KEY.sub("[private key redacted]", raw)
    lines = []
    redacting = False
    for line in text.splitlines(keepends=True):
        # Suppress indented continuations too (e.g. multiline JSON values).
        redacting = bool(_CREDENTIAL.search(line)) or (
            redacting and bool(line[:1].isspace())
        )
        lines.append("[credential-like line redacted]\n" if redacting else line)
    rendered = ascii("".join(lines))  # Escape terminal controls and invalid bytes.
    omitted = max(0, len(rendered) - _OUTPUT_LIMIT)
    if omitted:
        return (
            f"[{omitted} earlier rendered characters omitted] "
            + rendered[-_OUTPUT_LIMIT:]
        )
    return rendered


@contextmanager
def captured_subprocess_diagnostics():
    """Annotate the original run(check=True) failure; do not run/retry anything."""
    try:
        yield
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        try:
            if isinstance(error, subprocess.CalledProcessError):
                detail = f"CalledProcessError; returncode={error.returncode!r}"
            else:
                detail = f"TimeoutExpired; timeout={error.timeout!r}"
            note = (
                f"captured subprocess failure: {detail}\n"
                f"stdout={_output_note(error.stdout)}\n"
                f"stderr={_output_note(error.stderr)}"
            )
        except Exception:
            # Diagnostic rendering must never replace the originating failure,
            # including with an exception message that might contain raw data.
            note = "captured subprocess failure: output diagnostics unavailable"
        error.add_note(note)
        raise
