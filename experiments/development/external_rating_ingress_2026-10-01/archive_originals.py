"""Archive and verify finite synthetic originals; never extract or restore."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tarfile

HELPER_SHA256 = "ac11678d2312bd3c0bc77aac72a56ca9659e7ffb478c29a0e09f9676ff38d456"
HELPER = Path(__file__).resolve().parent.parent / "authorized_route_entry_2026-10-01" / "archive_runtimes.py"


class ArchiveOriginalsError(ValueError):
    """A fixed rejection without archived contents or caller text."""


def _require(condition):
    if not condition:
        raise ArchiveOriginalsError("archive_or_verification_rejected")


def _absolute_path(path):
    value = Path(path)
    _require(".." not in value.parts)
    return value.absolute()


def _directory(path):
    for component in (*reversed(path.parents), path):
        _require(stat.S_ISDIR(component.lstat().st_mode))


def _file(path):
    info = path.lstat()
    _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)


def _tree(root):
    _directory(root)
    pending = [root]
    while pending:
        for path in sorted(pending.pop().iterdir()):
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
            else:
                _file(path)


def _helper():
    _directory(HELPER.parent)
    _file(HELPER)
    raw = HELPER.read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == HELPER_SHA256)
    spec = importlib.util.spec_from_file_location("d123_frozen_originals_archive", HELPER)
    module = importlib.util.module_from_spec(spec)
    # Import only the pinned helper bytes, without writing its bytecode cache.
    # Archived source files are data and are never compiled or executed.
    exec(compile(raw, str(HELPER), "exec"), module.__dict__)
    return module


def archive_originals(root: Path, output: Path, manifest: Path) -> dict:
    try:
        root, output, manifest = (_absolute_path(path) for path in (root, output, manifest))
        _tree(root)
        _require(output != manifest)
        for path in (output, manifest):
            _directory(path.parent)
            _require(path != root and root not in path.parents and not os.path.lexists(path))
        result = _helper().archive(root, output, manifest)
        return {**result, "helper_sha256": HELPER_SHA256, "scope": "finite_synthetic_original_bytes_modes_and_hashes",
                "custody_authenticated": False, "archived_code_executed": False, "originals_extracted": False}
    except (OSError, ValueError, TypeError, KeyError, AssertionError, tarfile.TarError):
        raise ArchiveOriginalsError("archive_or_verification_rejected") from None


def verify_originals(archive_path: Path, manifest: Path) -> dict:
    try:
        archive_path, manifest = (_absolute_path(path) for path in (archive_path, manifest))
        for path in (archive_path, manifest):
            _directory(path.parent)
            _file(path)
        result = _helper().verify(archive_path, manifest)
        return {**result, "helper_sha256": HELPER_SHA256, "restore_authority": False,
                "custody_authenticated": False, "archived_code_executed": False, "originals_extracted": False}
    except (OSError, ValueError, TypeError, KeyError, AssertionError, tarfile.TarError):
        raise ArchiveOriginalsError("archive_or_verification_rejected") from None


archive = archive_originals
verify = verify_originals


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    try:
        _require((args.root is None) == args.verify)
        result = verify_originals(args.archive, args.inventory) if args.verify else archive_originals(args.root, args.archive, args.inventory)
        print(json.dumps(result, sort_keys=True))
    except ArchiveOriginalsError as error:
        parser.exit(2, json.dumps({"error": str(error)}) + "\n")
