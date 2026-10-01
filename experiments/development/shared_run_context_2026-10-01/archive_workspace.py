"""Archive only a completed public synthetic pytest workspace; never follow links."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import tarfile
from pathlib import Path


DOSSIER = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("label", choices=("final311", "final312"))
    args = parser.parse_args()
    workspace = args.workspace
    if workspace.is_symlink() or not workspace.is_dir() or not workspace.is_absolute():
        parser.error("workspace must be an absolute regular directory")
    out = DOSSIER / "archives"
    out.mkdir(exist_ok=True)
    target = out / f"{args.label}.tar.gz"
    if target.exists():
        raise FileExistsError(target)
    files, other = [], []
    total = 0
    for path in sorted(workspace.rglob("*")):
        info = path.lstat()
        name = path.relative_to(workspace).as_posix()
        if stat.S_ISREG(info.st_mode):
            total += info.st_size
            if total > 256 * 1024 * 1024 or len(files) >= 10_000:
                raise ValueError("public fixture archive exceeds capture bounds")
            files.append({"path": name, "bytes": info.st_size, "sha256": digest(path)})
        else:
            other.append({"path": name, "mode": stat.S_IFMT(info.st_mode),
                          "preserved_as_member": False})
    with tarfile.open(target, "x:gz", dereference=True) as archive:
        for pin in files:
            archive.add(workspace / pin["path"], arcname=pin["path"], recursive=False)
    with tarfile.open(target, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) != len(files) or not all(member.isfile() for member in members):
            raise ValueError("archive member inventory differs")
        for pin in files:
            member = archive.getmember(pin["path"])
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("regular member cannot be read")
            value = hashlib.sha256()
            with stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    value.update(block)
            if member.size != pin["bytes"] or value.hexdigest() != pin["sha256"]:
                raise ValueError("archived fixture bytes differ")
            if digest(workspace / pin["path"]) != pin["sha256"]:
                raise ValueError("fixture changed during archiving")
    metadata = {"schema": "specorganon.d111.public_fixture_archive.v1",
                "classification": "public_synthetic_fixtures_not_real_reserved_data",
                "workspace": str(workspace), "regular_files": len(files),
                "archive_bytes": target.stat().st_size, "archive_sha256": digest(target),
                "regular_files_verified_after": True, "pins": files,
                "non_regular_entries_metadata_only": other,
                "empty_directories_preserved": False, "links_followed": False}
    (out / f"{args.label}.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"label": args.label, "regular_files": len(files),
                      "archive_bytes": metadata["archive_bytes"],
                      "archive_sha256": metadata["archive_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
