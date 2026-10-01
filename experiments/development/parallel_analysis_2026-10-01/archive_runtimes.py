"""Retain explicit synthetic runtime roots as deduplicated blobs; never restore."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import stat
import tarfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", nargs="+", type=Path, required=True)
    args = parser.parse_args()
    args.reports = [path.resolve() for path in args.reports]
    dossier = Path(__file__).resolve().parent
    destination = dossier / "archives"
    destination.mkdir(exist_ok=False)
    roots = []
    for report_path in args.reports:
        report = json.loads(report_path.read_bytes())
        root = Path(report["runtime_root"])
        if (not root.is_absolute() or not str(root).startswith("/tmp/specorganon-D116-")
                or root.is_symlink() or not root.is_dir()):
            raise ValueError("only explicit existing D116 synthetic runtime roots may be archived")
        if root not in roots:
            roots.append(root)
    records, blobs = [], {}
    for number, root in enumerate(roots):
        for parent, directories, files in os.walk(root, followlinks=False):
            for name in ["", *sorted(directories), *sorted(files)]:
                path = Path(parent) / name
                relative = str(path.relative_to(root))
                if name == "" and relative != ".":
                    continue
                info = path.lstat()
                row = {"root": number, "path": relative, "mode": stat.S_IMODE(info.st_mode)}
                if stat.S_ISLNK(info.st_mode):
                    row.update(kind="symlink", target=os.readlink(path))
                elif stat.S_ISDIR(info.st_mode):
                    row.update(kind="directory")
                elif stat.S_ISREG(info.st_mode):
                    raw = path.read_bytes()
                    if len(raw) != info.st_size:
                        raise ValueError("runtime changed during archive read")
                    digest = hashlib.sha256(raw).hexdigest()
                    row.update(kind="file", bytes=len(raw), sha256=digest)
                    if digest in blobs and blobs[digest] != raw:
                        raise ValueError("blob digest collision")
                    blobs[digest] = raw
                else:
                    raise ValueError("unsupported runtime entry type")
                records.append(row)
    records.sort(key=lambda row: (row["root"], row["path"]))
    keys = [(row["root"], row["path"]) for row in records]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate archive inventory entry")
    archive = destination / "runtimes.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        for digest, raw in sorted(blobs.items()):
            header = tarfile.TarInfo(f"blobs/{digest}")
            header.mode, header.size, header.mtime = 0o400, len(raw), 0
            stream.addfile(header, io.BytesIO(raw))
    manifest = {"schema": 1, "classification": "synthetic_runtime_evidence_not_restorable_authority",
                "roots": [str(root) for root in roots],
                "reports": [str(path.relative_to(dossier)) for path in args.reports],
                "records": records, "regular_files": sum(row["kind"] == "file" for row in records),
                "unique_blobs": len(blobs), "archive": archive.name,
                "archive_bytes": archive.stat().st_size,
                "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "no_env_or_session_image": True}
    (destination / "runtime_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with tarfile.open(archive, "r:gz") as stream:
        members = stream.getmembers()
        if {entry.name for entry in members} != {f"blobs/{digest}" for digest in blobs}:
            raise ValueError("archive blob membership differs")
        for entry in members:
            raw = stream.extractfile(entry).read()
            if raw != blobs[entry.name.removeprefix("blobs/")]:
                raise ValueError("retained archive blob differs")
    print(json.dumps({key: manifest[key] for key in
                      ("regular_files", "unique_blobs", "archive_bytes", "archive_sha256")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
