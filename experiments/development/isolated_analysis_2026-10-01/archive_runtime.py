"""Archive exact local fixture bytes once per SHA, retaining every path mapping."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import stat
import tarfile
from pathlib import Path


def identity(info: os.stat_result) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def content(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > 20_000_000:
            raise ValueError("runtime file is not bounded and regular")
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(20_000_001)
        if len(raw) != before.st_size or identity(before) != identity(os.fstat(fd)):
            raise ValueError("runtime file changed during archive")
        if identity(before) != identity(path.lstat()):
            raise ValueError("runtime path changed during archive")
        return raw
    finally:
        os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("roots", nargs="+", help="unique label=/absolute/fixture/path")
    args = parser.parse_args()
    roots = {}
    for item in args.roots:
        label, name = item.split("=", 1)
        root = Path(name)
        if not label or "/" in label or label in roots or not root.is_absolute() or root.is_symlink():
            raise ValueError("root labels and absolute directories must be unique")
        if not stat.S_ISDIR(root.lstat().st_mode):
            raise ValueError("runtime root is not a real directory")
        roots[label] = root
    seen, records = set(), []
    with args.output.open("xb") as file:
        with gzip.GzipFile(filename="", fileobj=file, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|") as archive:
                for label, root in roots.items():
                    for directory, directories, files in os.walk(root, followlinks=False):
                        directories.sort()
                        for name in sorted(directories + files):
                            path = Path(directory) / name
                            info = path.lstat()
                            record = {"root": label, "path": str(path.relative_to(root)),
                                      "mode": stat.S_IMODE(info.st_mode), "bytes": info.st_size}
                            secret_name = (name in {".env", "settings.local.json"}
                                           or name.endswith((".pem", ".key", ".token")))
                            if secret_name:
                                record["kind"] = "sensitive_name_metadata_only"
                            elif stat.S_ISREG(info.st_mode):
                                raw = content(path)
                                digest = hashlib.sha256(raw).hexdigest()
                                record.update(kind="regular", sha256=digest, bytes=len(raw))
                                if digest not in seen:
                                    header = tarfile.TarInfo("blobs/" + digest)
                                    header.size, header.mode = len(raw), 0o600
                                    archive.addfile(header, io.BytesIO(raw))
                                    seen.add(digest)
                            elif stat.S_ISLNK(info.st_mode):
                                record.update(kind="symlink_metadata_only", target=os.readlink(path))
                            elif stat.S_ISDIR(info.st_mode):
                                record["kind"] = "directory_metadata_only"
                            else:
                                record["kind"] = "nonregular_metadata_only"
                            records.append(record)
                mapping = {"schema": 1, "classification": "public_fixture_fake_transport_runtime_evidence",
                           "root_paths": {key: str(value) for key, value in roots.items()},
                           "regular_files": sum(row["kind"] == "regular" for row in records),
                           "unique_blobs": len(seen), "records": records,
                           "complete_session_restore_supported": False}
                raw = (json.dumps(mapping, indent=2, sort_keys=True) + "\n").encode()
                header = tarfile.TarInfo("mapping.json")
                header.size, header.mode = len(raw), 0o600
                archive.addfile(header, io.BytesIO(raw))
    # Reopen every retained byte, then compare mappings against preserved originals.
    with tarfile.open(args.output, "r:gz") as archive:
        actual = {member.name: archive.extractfile(member).read() for member in archive.getmembers()}
    restored = json.loads(actual.pop("mapping.json"))
    if restored != mapping:
        raise ValueError("runtime mapping changed while archiving")
    for row in records:
        if row["kind"] == "regular":
            raw = actual["blobs/" + row["sha256"]]
            if hashlib.sha256(raw).hexdigest() != row["sha256"] or len(raw) != row["bytes"]:
                raise ValueError("retained blob differs from mapping")
            if raw != content(roots[row["root"]] / row["path"]):
                raise ValueError("retained blob differs from preserved original")
    container = args.output.read_bytes()
    receipt = {"path": str(args.output), "bytes": len(container),
               "sha256": hashlib.sha256(container).hexdigest(),
               "regular_files": mapping["regular_files"], "unique_blobs": len(seen),
               "all_blobs_reopened_and_mapped_to_originals": True,
               "sensitive_name_metadata_only": sum(row["kind"] == "sensitive_name_metadata_only" for row in records)}
    with args.output.with_suffix(".json").open("x") as file:
        file.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
