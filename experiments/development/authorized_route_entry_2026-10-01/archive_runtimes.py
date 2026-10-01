"""Archive finite public synthetic controls without extracting or restoring."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import tarfile


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inventory(root):
    rows = []
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        row = {"path": path.relative_to(root).as_posix(), "mode": stat.S_IMODE(info.st_mode)}
        if stat.S_ISDIR(info.st_mode):
            row["kind"] = "directory"
        else:
            assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            raw = path.read_bytes()
            row.update(kind="file", bytes=len(raw), sha256=sha(raw))
        rows.append(row)
    return {"entries": rows}


def verify(archive, manifest):
    rows = {row["path"]: row for row in json.loads(manifest.read_bytes())["entries"]}
    with tarfile.open(archive, "r:gz") as stream:
        members = stream.getmembers()
        assert len(members) == len(rows) == len({m.name for m in members})
        for member in members:
            row = rows[member.name]
            assert member.mode == row["mode"]
            if row["kind"] == "directory":
                assert member.isdir()
            else:
                assert member.isfile() and member.size == row["bytes"]
                assert sha(stream.extractfile(member).read()) == row["sha256"]
    return {"verified_entries": len(rows), "archive_bytes": archive.stat().st_size, "archive_sha256": sha(archive.read_bytes())}


def archive(root, output, manifest):
    before = inventory(root)
    manifest.write_text(json.dumps(before, indent=2) + "\n")
    with tarfile.open(output, "x:gz") as stream:
        for row in before["entries"]:
            stream.add(root / row["path"], arcname=row["path"], recursive=False)
    assert before == inventory(root)
    return {**verify(output, manifest), "original_unchanged": True, "restore_authority": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.archive, args.inventory)))
