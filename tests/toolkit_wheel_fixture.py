"""Synthetic SpecOrganon wheel bytes for static inspection tests."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import stat
import zipfile
from collections.abc import Mapping
from pathlib import Path


DIST_INFO = "specorganon-0.1.0.dist-info"
CORE_MODULES = (
    "__init__.py",
    "anchor.py",
    "approval.py",
    "cli.py",
    "engine.py",
    "ledger.py",
    "runner.py",
    "server.py",
    "workflow.py",
)


def wheel_members() -> dict[str, bytes]:
    """Return the uncompressed regular members of a minimal valid wheel."""
    members = {
        f"specorganon/{name}": b"# Synthetic wheel fixture.\n" for name in CORE_MODULES
    }
    members[f"{DIST_INFO}/METADATA"] = (
        b"Metadata-Version: 2.5\n"
        b"Name: specorganon\n"
        b"Version: 0.1.0\n"
        b"Requires-Python: >=3.11\n"
        b"Requires-Dist: cryptography<51,>=41\n"
        b"Requires-Dist: mcp==2.2.0\n"
        b"Provides-Extra: dev\n"
        b"Requires-Dist: pytest<10,>=8; extra == 'dev'\n"
        b"\nSynthetic fixture.\n"
    )
    members[f"{DIST_INFO}/WHEEL"] = (
        b"Wheel-Version: 1.0\n"
        b"Generator: synthetic-test\n"
        b"Root-Is-Purelib: true\n"
        b"Tag: py3-none-any\n"
        b"\n"
    )
    members[f"{DIST_INFO}/entry_points.txt"] = (
        b"[console_scripts]\n"
        b"organon = specorganon.cli:main\n"
        b"organon-mcp = specorganon.server:main\n"
    )
    return members


def build_toolkit_wheel(
    path: Path,
    *,
    overrides: Mapping[str, bytes] | None = None,
    omit: tuple[str, ...] = (),
    extra: Mapping[str, bytes] | None = None,
) -> bytes:
    """Build a fixture at any filename, with a matching RECORD by default."""
    members = wheel_members()
    members.update(overrides or {})
    for name in omit:
        members.pop(name)
    members.update(extra or {})
    record_path = f"{DIST_INFO}/RECORD"
    record_buffer = io.StringIO(newline="")
    writer = csv.writer(record_buffer, lineterminator="\n")
    for name, payload in members.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=")
        writer.writerow((name, "sha256=" + digest.decode("ascii"), str(len(payload))))
    writer.writerow((record_path, "", ""))
    members[record_path] = record_buffer.getvalue().encode("utf-8")
    with zipfile.ZipFile(path, "w", allowZip64=False) as archive:
        for name, payload in members.items():
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, payload)
    return path.read_bytes()
