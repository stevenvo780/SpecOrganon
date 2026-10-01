"""Retain explicit D118 public runtime evidence as blobs; never restore authority."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tarfile

IMPORTS = ["argparse", "hashlib", "io", "json", "os", "pathlib", "stat", "sys", "tarfile"]
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_ENTRIES = 100_000


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       allow_nan=False, indent=2) + "\n").encode()


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def parse(raw: bytes):
    def invalid(value):
        raise ValueError("nonfinite JSON constant: " + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def real_chain(path: Path) -> Path:
    if ".." in path.parts:
        raise ValueError("parent traversal is not accepted")
    path = path.absolute()
    current = Path(path.anchor)
    for part in path.parent.parts[1:]:
        current /= part
        if not stat.S_ISDIR(current.lstat().st_mode):
            raise ValueError("path parent must be a real directory, without symlinks")
    return path


def read_regular(path: Path, cap=MAX_FILE_BYTES) -> bytes:
    path = real_chain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= cap:
            raise ValueError("bounded regular evidence file required")
        blocks, size = [], 0
        while block := os.read(fd, min(65536, cap + 1 - size)):
            size += len(block)
            if size > cap:
                raise ValueError("file exceeds byte limit")
            blocks.append(block)
        after, named = os.fstat(fd), path.lstat()
        def identity(info):
            return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                    info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if identity(before) != identity(after) or identity(after) != identity(named):
            raise ValueError("evidence changed during bounded read")
        return b"".join(blocks)
    finally:
        os.close(fd)


def runtime_root(raw: str) -> Path:
    if type(raw) is not str:
        raise ValueError("runtime root must be an explicit path string")
    root = Path(raw)
    if (not root.is_absolute() or root.parent != Path("/tmp")
            or not root.name.startswith("specorganon-D118-")):
        raise ValueError("only existing /tmp/specorganon-D118-* roots are accepted")
    root = real_chain(root)
    if not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError("runtime root must exist as a real directory, without symlinks")
    return root


def inventory(roots: list[Path]) -> tuple[list[dict], dict[str, bytes]]:
    records, blobs, total = [], {}, 0
    for number, root in enumerate(roots):
        runtime_root(str(root))
        for parent, directories, files in os.walk(root, followlinks=False):
            real_chain(Path(parent) / ".entry")
            for name in ["", *sorted(directories), *sorted(files)]:
                path = Path(parent) / name
                relative = path.relative_to(root).as_posix()
                if name == "" and relative != ".":
                    continue
                info = path.lstat()
                row = {"root": number, "path": relative, "mode": stat.S_IMODE(info.st_mode)}
                if stat.S_ISLNK(info.st_mode):
                    target = os.readlink(path)
                    after = path.lstat()
                    if (info.st_dev, info.st_ino, info.st_mode, info.st_mtime_ns, info.st_ctime_ns) != (
                            after.st_dev, after.st_ino, after.st_mode, after.st_mtime_ns, after.st_ctime_ns):
                        raise ValueError("symlink metadata changed during inventory")
                    row.update(kind="symlink", target=target)
                elif stat.S_ISDIR(info.st_mode):
                    row.update(kind="directory")
                elif stat.S_ISFIFO(info.st_mode):
                    # Known negative fixtures: metadata only, no open/read of a stream.
                    row.update(kind="fifo")
                elif stat.S_ISREG(info.st_mode):
                    raw = read_regular(path)
                    total += len(raw)
                    if total > MAX_TOTAL_BYTES:
                        raise ValueError("runtime evidence exceeds total byte limit")
                    sha = digest(raw)
                    row.update(kind="file", bytes=len(raw), sha256=sha)
                    if sha in blobs and blobs[sha] != raw:
                        raise ValueError("blob digest collision")
                    blobs[sha] = raw
                else:
                    raise ValueError("socket/device/unsupported runtime entry type")
                records.append(row)
                if len(records) > MAX_ENTRIES:
                    raise ValueError("runtime inventory exceeds entry limit")
    records.sort(key=lambda row: (row["root"], row["path"]))
    if len({(row["root"], row["path"]) for row in records}) != len(records):
        raise ValueError("duplicate runtime inventory entry")
    return records, blobs


def exclusive(path: Path, raw: bytes):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", nargs="+", type=Path, required=True)
    args = parser.parse_args()
    dossier = Path(__file__).resolve().parent
    roots, reports, seen = [], [], set()
    for report_path in args.reports:
        report_path = real_chain(report_path)
        relative = report_path.relative_to(dossier).as_posix()
        parts = Path(relative).parts
        if (len(parts) != 3 or parts[0] not in {"checks", "worker_checks"}
                or (parts[0] == "checks" and parts[2] != "report.json")
                or (parts[0] == "worker_checks" and
                    (not parts[1].startswith("preparer_") or parts[2] != "receipt.json"))):
            raise ValueError("report must be an explicit D118 check/preparer gate receipt")
        if report_path in seen:
            continue
        seen.add(report_path)
        raw = read_regular(report_path, 1024 * 1024)
        report = parse(raw)
        field = "all_exit_zero" if parts[0] == "checks" else "passed"
        if type(report) is not dict or type(report.get(field)) is not bool:
            raise ValueError("gate receipt must retain its original boolean result")
        if parts[0] == "worker_checks" and type(report.get("records")) is not list:
            raise ValueError("preparer receipt must retain its command records")
        root = runtime_root(report["runtime_root"])
        if root not in roots:
            roots.append(root)
        reports.append({"path": relative, "bytes": len(raw), "sha256": digest(raw),
                        "result_field": field, "result": report[field], "runtime_root": str(root)})
    records, blobs = inventory(roots)
    destination = dossier / "archives"
    destination.mkdir(mode=0o700, exist_ok=False)
    archive = destination / "runtimes.tar.gz"
    fd = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        with tarfile.open(fileobj=output, mode="w:gz") as stream:
            for sha, raw in sorted(blobs.items()):
                header = tarfile.TarInfo(f"blobs/{sha}")
                header.mode, header.size, header.mtime = 0o400, len(raw), 0
                stream.addfile(header, io.BytesIO(raw))
        output.flush()
        os.fsync(output.fileno())
    archive_raw = read_regular(archive, MAX_TOTAL_BYTES)
    with tarfile.open(fileobj=io.BytesIO(archive_raw), mode="r:gz") as stream:
        members = stream.getmembers()
        if (len(members) != len(blobs)
                or {entry.name for entry in members} != {f"blobs/{sha}" for sha in blobs}):
            raise ValueError("archive blob membership differs")
        for entry in members:
            if not entry.isfile() or entry.mode != 0o400 or entry.mtime != 0:
                raise ValueError("tar member type or metadata differs")
            if stream.extractfile(entry).read() != blobs[entry.name.removeprefix("blobs/")]:
                raise ValueError("retained archive blob differs")
    after_records, after_blobs = inventory(roots)
    if after_records != records or after_blobs != blobs:
        raise ValueError("original runtime evidence changed during archiving")
    for row in reports:
        if digest(read_regular(dossier / row["path"], 1024 * 1024)) != row["sha256"]:
            raise ValueError("source receipt changed during archiving")
    manifest = {
        "schema": 1, "classification": "synthetic_runtime_evidence_not_restorable_authority",
        "roots": [str(root) for root in roots], "reports": reports, "records": records,
        "regular_files": sum(row["kind"] == "file" for row in records),
        "symlinks_metadata_only": sum(row["kind"] == "symlink" for row in records),
        "fifo_metadata_only": sum(row["kind"] == "fifo" for row in records),
        "unique_blobs": len(blobs), "archive": archive.name,
        "archive_bytes": len(archive_raw), "archive_sha256": digest(archive_raw),
        "restorable_authority": False,
        "nonregular_policy": "symlinks_and_known_negative_FIFO_metadata_only; sockets_devices_other_types_rejected",
        "archiver": {"path": str(Path(__file__).resolve()),
                     "sha256": digest(read_regular(Path(__file__).resolve())),
                     "imports": IMPORTS, "argv": [sys.executable, *sys.argv]},
    }
    exclusive(destination / "runtime_manifest.json", canonical(manifest))
    dirfd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)
    print(json.dumps({key: manifest[key] for key in (
        "regular_files", "unique_blobs", "symlinks_metadata_only", "fifo_metadata_only",
        "archive_bytes", "archive_sha256")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
