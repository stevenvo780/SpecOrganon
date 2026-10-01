"""Archive explicit local D119 synthetic evidence, with no restoration authority."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tarfile

MAX_TOTAL = 2 * 1024 * 1024 * 1024
MAX_FILE = 64 * 1024 * 1024


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def read(path):
    path = Path(path)
    for parent in path.parents:
        assert stat.S_ISDIR(parent.lstat().st_mode), "real parent directory required"
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        assert stat.S_ISREG(before.st_mode) and before.st_size <= MAX_FILE
        data = bytearray()
        while part := os.read(fd, 65536):
            data.extend(part)
            assert len(data) <= MAX_FILE
        after = os.fstat(fd)
        assert identity(before) == identity(after) == identity(path.lstat()), "evidence changed during read"
        return bytes(data)
    finally:
        os.close(fd)


def inventory(roots):
    records, blobs, total = [], {}, 0
    for number, root in enumerate(roots):
        assert root.is_absolute() and root.parent == Path("/tmp") and root.name.startswith("specorganon-D119-")
        assert stat.S_ISDIR(root.lstat().st_mode)
        for parent, folders, files in os.walk(root, followlinks=False):
            for name in ["", *sorted(folders), *sorted(files)]:
                path = Path(parent) / name
                relative = path.relative_to(root).as_posix()
                if name == "" and relative != ".":
                    continue
                info = path.lstat()
                row = {"root": number, "path": relative, "mode": stat.S_IMODE(info.st_mode)}
                if stat.S_ISREG(info.st_mode):
                    raw = read(path)
                    total += len(raw)
                    assert total <= MAX_TOTAL
                    digest = hashlib.sha256(raw).hexdigest()
                    row.update(kind="file", bytes=len(raw), sha256=digest)
                    assert digest not in blobs or blobs[digest] == raw
                    blobs[digest] = raw
                elif stat.S_ISDIR(info.st_mode):
                    row["kind"] = "directory"
                elif stat.S_ISLNK(info.st_mode):
                    row.update(kind="symlink", target=os.readlink(path))
                    assert identity(path.lstat()) == identity(info)
                elif stat.S_ISFIFO(info.st_mode):
                    row["kind"] = "fifo"  # Negative fixture: metadata only, never open.
                else:
                    raise ValueError("unsupported device/socket evidence")
                records.append(row)
                assert len(records) <= 100000
    records.sort(key=lambda row: (row["root"], row["path"]))
    assert len({(row["root"], row["path"]) for row in records}) == len(records)
    return records, blobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roots", type=Path, nargs="+", required=True)
    parser.add_argument("--reports", type=Path, nargs="+", required=True)
    args = parser.parse_args()
    dossier = Path(__file__).resolve().parent
    roots = sorted(set(args.roots))
    reports = [{"path": str(path.relative_to(dossier)), "bytes": len(raw := read(path)),
                "sha256": hashlib.sha256(raw).hexdigest()} for path in sorted(set(args.reports))]
    records, blobs = inventory(roots)
    target = dossier / "archives"
    target.mkdir(mode=0o700)
    archive = target / "runtimes.tar.gz"
    with archive.open("xb") as output:
        with tarfile.open(fileobj=output, mode="w:gz") as stream:
            for digest, raw in sorted(blobs.items()):
                header = tarfile.TarInfo("blobs/" + digest)
                header.mode, header.size, header.mtime = 0o400, len(raw), 0
                stream.addfile(header, io.BytesIO(raw))
    raw = read(archive)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as stream:
        members = stream.getmembers()
        assert len(members) == len(blobs) and {row.name for row in members} == {"blobs/" + digest for digest in blobs}
        for row in members:
            assert row.isfile() and row.mode == 0o400 and row.mtime == 0
            assert stream.extractfile(row).read() == blobs[row.name.removeprefix("blobs/")]
    assert (records, blobs) == inventory(roots)
    result = {"schema": 1, "classification": "synthetic_runtime_forensics_not_restorable_authority",
              "roots": [str(root) for root in roots], "reports": reports, "records": records,
              "archive": archive.name, "archive_bytes": len(raw), "archive_sha256": hashlib.sha256(raw).hexdigest(),
              "regular_files": sum(row["kind"] == "file" for row in records), "unique_blobs": len(blobs),
              "restorable_authority": False, "formal_cells_executed": 0}
    (target / "runtime_manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("archive_bytes", "archive_sha256", "regular_files", "unique_blobs")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
