"""Compare every retained blob and metadata entry with its recorded runtime."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tarfile


def main() -> None:
    dossier = Path(__file__).resolve().parents[1]
    manifest_path = dossier / "archives/runtime_manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    archive = dossier / "archives" / manifest["archive"]
    raw = archive.read_bytes()
    assert len(raw) == manifest["archive_bytes"]
    assert hashlib.sha256(raw).hexdigest() == manifest["archive_sha256"]
    records = []
    blobs = {}
    for number, name in enumerate(manifest["roots"]):
        root = Path(name)
        assert root.is_dir() and not root.is_symlink()
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
                else:
                    assert stat.S_ISREG(info.st_mode), str(path)
                    body = path.read_bytes()
                    assert len(body) == info.st_size
                    digest = hashlib.sha256(body).hexdigest()
                    row.update(kind="file", bytes=len(body), sha256=digest)
                    if digest in blobs:
                        assert blobs[digest] == body
                    blobs[digest] = body
                records.append(row)
    records.sort(key=lambda row: (row["root"], row["path"]))
    assert records == manifest["records"], "original inventory differs from retained metadata"
    with tarfile.open(archive, "r:gz") as stream:
        members = stream.getmembers()
        assert len(members) == len(blobs) == manifest["unique_blobs"]
        assert {entry.name for entry in members} == {"blobs/" + digest for digest in blobs}
        for entry in members:
            assert entry.isfile() and entry.mode == 0o400 and entry.mtime == 0
            assert stream.extractfile(entry).read() == blobs[entry.name.removeprefix("blobs/")]
    for row in manifest["missing_failed_gate_roots"]:
        report = json.loads((dossier / row["report"]).read_bytes())
        assert report["all_exit_zero"] is False and report["runtime_root"] == row["root"]
        assert not Path(row["root"]).exists()
    report = {"schema": 1, "classification": "complete_original_archive_byte_and_metadata_comparison",
              "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              "archive_sha256": manifest["archive_sha256"], "archive_bytes": len(raw),
              "runtime_roots": len(manifest["roots"]), "regular_files": manifest["regular_files"],
              "unique_blobs": len(blobs), "inventory_entries": len(records),
              "symlinks_not_followed": sum(row["kind"] == "symlink" for row in records),
              "missing_failed_gate_roots": len(manifest["missing_failed_gate_roots"]),
              "all_original_bytes_modes_and_targets_equal": True, "restorable_authority": False}
    (dossier / "checks/archive_verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
