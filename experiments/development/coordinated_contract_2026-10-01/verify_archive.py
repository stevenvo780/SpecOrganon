"""Independently compare D118 originals, receipt pins, and all archive blobs."""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tarfile

IMPORTS = ["hashlib", "io", "json", "os", "pathlib", "re", "stat", "sys", "tarfile"]
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_ENTRIES = 100_000


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       allow_nan=False, indent=2) + "\n").encode()


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("nonfinite JSON constant: " + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def chain(path: Path) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("absolute evidence path without traversal required")
    current = Path(path.anchor)
    for part in path.parent.parts[1:]:
        current /= part
        if not stat.S_ISDIR(current.lstat().st_mode):
            raise ValueError("evidence parent is a symlink or non-directory")
    return path


def regular(path: Path, cap=MAX_FILE_BYTES) -> bytes:
    chain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        start = os.fstat(fd)
        if not stat.S_ISREG(start.st_mode) or not 0 <= start.st_size <= cap:
            raise ValueError("bounded regular evidence file required")
        pieces, count = [], 0
        while piece := os.read(fd, min(65536, cap + 1 - count)):
            count += len(piece)
            if count > cap:
                raise ValueError("evidence file exceeds byte limit")
            pieces.append(piece)
        end, named = os.fstat(fd), path.lstat()
        def identity(info):
            return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                    info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if identity(start) != identity(end) or identity(end) != identity(named):
            raise ValueError("original evidence changed during read")
        return b"".join(pieces)
    finally:
        os.close(fd)


def check_root(value: str) -> Path:
    if type(value) is not str:
        raise ValueError("runtime root must be a string")
    root = chain(Path(value))
    if (root.parent != Path("/tmp") or not root.name.startswith("specorganon-D118-")
            or not stat.S_ISDIR(root.lstat().st_mode)):
        raise ValueError("original D118 runtime must exist as a real /tmp directory")
    return root


def original_inventory(roots: list[Path]):
    records, contents, total = [], {}, 0
    for index, root in enumerate(roots):
        for parent, directories, files in os.walk(root, followlinks=False):
            chain(Path(parent) / ".entry")
            for name in ["", *sorted(directories), *sorted(files)]:
                path = Path(parent) / name
                relative = path.relative_to(root).as_posix()
                if name == "" and relative != ".":
                    continue
                info = path.lstat()
                row = {"root": index, "path": relative, "mode": stat.S_IMODE(info.st_mode)}
                if stat.S_ISLNK(info.st_mode):
                    target = os.readlink(path)
                    after = path.lstat()
                    if (info.st_dev, info.st_ino, info.st_mode, info.st_mtime_ns, info.st_ctime_ns) != (
                            after.st_dev, after.st_ino, after.st_mode, after.st_mtime_ns, after.st_ctime_ns):
                        raise ValueError("original symlink changed during verification")
                    row.update(kind="symlink", target=target)
                elif stat.S_ISDIR(info.st_mode):
                    row.update(kind="directory")
                elif stat.S_ISFIFO(info.st_mode):
                    # Intentionally retained negative fixture: compare metadata, never read.
                    row.update(kind="fifo")
                elif stat.S_ISREG(info.st_mode):
                    body = regular(path)
                    total += len(body)
                    if total > MAX_TOTAL_BYTES:
                        raise ValueError("original inventory exceeds total byte limit")
                    digest = sha(body)
                    row.update(kind="file", bytes=len(body), sha256=digest)
                    if digest in contents and contents[digest] != body:
                        raise ValueError("blob digest collision in original evidence")
                    contents[digest] = body
                else:
                    raise ValueError("original contains socket/device/unsupported entry")
                records.append(row)
                if len(records) > MAX_ENTRIES:
                    raise ValueError("original inventory exceeds entry limit")
    records.sort(key=lambda row: (row["root"], row["path"]))
    if len({(row["root"], row["path"]) for row in records}) != len(records):
        raise ValueError("duplicate original inventory entry")
    return records, contents


def main() -> int:
    dossier = Path(__file__).resolve().parent
    manifest_path = dossier / "archives/runtime_manifest.json"
    raw_manifest = regular(manifest_path, 32 * 1024 * 1024)
    manifest = parse(raw_manifest)
    expected_keys = {
        "schema", "classification", "roots", "reports", "records", "regular_files",
        "symlinks_metadata_only", "fifo_metadata_only", "unique_blobs", "archive",
        "archive_bytes", "archive_sha256", "restorable_authority", "nonregular_policy", "archiver"}
    if (type(manifest) is not dict or set(manifest) != expected_keys
            or type(manifest["schema"]) is not int or manifest["schema"] != 1
            or manifest["classification"] != "synthetic_runtime_evidence_not_restorable_authority"
            or manifest["restorable_authority"] is not False
            or manifest["archive"] != "runtimes.tar.gz"
            or type(manifest["roots"]) is not list or not manifest["roots"]
            or type(manifest["reports"]) is not list or not manifest["reports"]
            or raw_manifest != canonical(manifest)):
        raise ValueError("archive manifest schema or canonical bytes differ")
    roots = [check_root(value) for value in manifest["roots"]]
    if len(roots) != len(set(roots)):
        raise ValueError("runtime roots were not deduplicated")
    for row in manifest["reports"]:
        if type(row) is not dict or set(row) != {
                "path", "bytes", "sha256", "result_field", "result", "runtime_root"}:
            raise ValueError("retained report binding fields differ")
        parts = Path(row["path"]).parts
        if (len(parts) != 3 or parts[0] not in {"checks", "worker_checks"}
                or (parts[0] == "checks" and parts[2] != "report.json")
                or (parts[0] == "worker_checks" and
                    (not parts[1].startswith("preparer_") or parts[2] != "receipt.json"))):
            raise ValueError("retained report path differs from explicit D118 gate scope")
        body = regular(dossier / row["path"], 1024 * 1024)
        value = parse(body)
        field = "all_exit_zero" if parts[0] == "checks" else "passed"
        if (len(body) != row["bytes"] or sha(body) != row["sha256"]
                or type(value) is not dict or type(value.get(field)) is not bool
                or field != row["result_field"] or type(row["result"]) is not bool
                or value[field] != row["result"]
                or value["runtime_root"] != row["runtime_root"]
                or check_root(value["runtime_root"]) not in roots
                or parts[0] == "worker_checks" and type(value.get("records")) is not list):
            raise ValueError("original gate receipt differs from retained binding")
    if (len({row["path"] for row in manifest["reports"]}) != len(manifest["reports"])
            or {str(root) for root in roots} != {row["runtime_root"] for row in manifest["reports"]}):
        raise ValueError("reports and deduplicated runtime roots differ")
    archiver = manifest["archiver"]
    if (type(archiver) is not dict or set(archiver) != {"path", "sha256", "imports", "argv"}
            or archiver["path"] != str(dossier / "archive_runtimes.py")
            or sha(regular(Path(archiver["path"]))) != archiver["sha256"]
            or type(archiver["imports"]) is not list or type(archiver["argv"]) is not list):
        raise ValueError("archiving helper source binding differs")
    records, blobs = original_inventory(roots)
    if (records != manifest["records"]
            or sum(row["kind"] == "file" for row in records) != manifest["regular_files"]
            or sum(row["kind"] == "symlink" for row in records) != manifest["symlinks_metadata_only"]
            or sum(row["kind"] == "fifo" for row in records) != manifest["fifo_metadata_only"]
            or len(blobs) != manifest["unique_blobs"]):
        raise ValueError("every original byte/mode/target inventory must equal retained metadata")
    archive_path = dossier / "archives/runtimes.tar.gz"
    raw_archive = regular(archive_path, MAX_TOTAL_BYTES)
    if len(raw_archive) != manifest["archive_bytes"] or sha(raw_archive) != manifest["archive_sha256"]:
        raise ValueError("compressed archive byte pin differs")
    with tarfile.open(fileobj=io.BytesIO(raw_archive), mode="r:gz") as stream:
        members = stream.getmembers()
        names = {f"blobs/{digest}" for digest in blobs}
        if len(members) != len(blobs) or {entry.name for entry in members} != names:
            raise ValueError("archive contains missing/duplicate/extra blob members")
        for entry in members:
            if (not entry.isfile() or re.fullmatch(r"blobs/[0-9a-f]{64}", entry.name) is None
                    or entry.mode != 0o400 or entry.mtime != 0
                    or entry.size != len(blobs[entry.name.removeprefix("blobs/")])
                    or stream.extractfile(entry).read() != blobs[entry.name.removeprefix("blobs/")]):
                raise ValueError("tar member byte/type/mode/size differs from original blob")
    final_records, final_blobs = original_inventory(roots)
    if final_records != records or final_blobs != blobs:
        raise ValueError("original evidence changed during verification")
    if raw_manifest != regular(manifest_path, 32 * 1024 * 1024):
        raise ValueError("archive manifest changed during verification")
    report = {
        "schema": 1, "classification": "complete_original_archive_byte_and_metadata_comparison",
        "manifest_sha256": sha(raw_manifest), "archive_sha256": manifest["archive_sha256"],
        "archive_bytes": len(raw_archive), "runtime_roots": len(roots),
        "regular_files": manifest["regular_files"], "unique_blobs": len(blobs),
        "inventory_entries": len(records), "symlinks_not_followed": manifest["symlinks_metadata_only"],
        "fifo_metadata_only": manifest["fifo_metadata_only"],
        "all_original_bytes_modes_and_targets_equal": True, "restorable_authority": False,
        "verifier": {"path": str(Path(__file__).resolve()),
                     "sha256": sha(regular(Path(__file__).resolve())),
                     "imports": IMPORTS, "argv": [sys.executable, *sys.argv]},
    }
    destination = dossier / "checks/archive_verification.json"
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(canonical(report))
        output.flush()
        os.fsync(output.fileno())
    dirfd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)
    print(json.dumps({key: report[key] for key in (
        "runtime_roots", "regular_files", "unique_blobs", "symlinks_not_followed",
        "fifo_metadata_only", "all_original_bytes_modes_and_targets_equal",
        "archive_sha256")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
