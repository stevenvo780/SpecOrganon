#!/usr/bin/env python3
"""Autosufficient, checksummed directory snapshots (Python 3.12 / POSIX)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile


ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", re.ASCII)
HASH_RE = re.compile(r"[0-9a-f]{64}", re.ASCII)
CHUNK = 1024 * 1024


class BackupError(Exception):
    """Expected input, safety or integrity error."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BackupError(message)


def valid_id(value: str) -> str:
    require(ID_RE.fullmatch(value) is not None, "invalid snapshot ID")
    return value


def node_stat(path: Path):
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def kind(info, path: Path) -> str:
    if stat.S_ISDIR(info.st_mode):
        return "dir"
    if stat.S_ISREG(info.st_mode):
        return "file"
    raise BackupError(f"symlink or special file rejected: {path}")


def safe_path(value: str | Path) -> Path:
    """Check even components erased by lexical '..' normalization."""
    raw = os.fspath(value)
    require("\0" not in raw, "NUL in path")
    if not os.path.isabs(raw):
        raw = os.path.join(os.getcwd(), raw)
    current = Path("/")
    parts = raw.split("/")
    for index, part in enumerate(parts):
        if part in ("", "."):
            continue
        if part == "..":
            current = current.parent
        else:
            current = current / part
        info = node_stat(current)
        if info is not None:
            node_kind = kind(info, current)
            if any(p not in ("", ".") for p in parts[index + 1 :]):
                require(node_kind == "dir", f"not a directory: {current}")
    return Path(os.path.abspath(raw))


def directory(path: Path, *, optional: bool = False) -> bool:
    info = node_stat(path)
    if info is None:
        require(optional, f"directory does not exist: {path}")
        return False
    require(kind(info, path) == "dir", f"not a directory: {path}")
    return True


def overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def inventory(root: Path) -> dict[str, str]:
    """Inventory regular files/directories, rejecting all other node types."""
    directory(root)
    found: dict[str, str] = {}
    pending = [root]
    while pending:
        parent = pending.pop()
        # O_NOFOLLOW prevents opening a replaced directory as a symlink.
        fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with os.scandir(fd) as listing:
                entries = sorted(list(listing), key=lambda item: item.name)
            for entry in entries:
                path = parent / entry.name
                info = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                node_kind = kind(info, path)
                found[path.relative_to(root).as_posix()] = node_kind
                if node_kind == "dir":
                    pending.append(path)
        finally:
            os.close(fd)
    return found


def open_regular(path: Path):
    safe_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), f"not a regular file: {path}")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def file_data(path: Path, target: Path | None = None) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    output = None
    try:
        with open_regular(path) as source:
            before = os.fstat(source.fileno())
            if target is not None:
                output = target.open("xb")
            while block := source.read(CHUNK):
                digest.update(block)
                size += len(block)
                if output is not None:
                    output.write(block)
            after = os.fstat(source.fileno())
            require(
                (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                == (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                and size == after.st_size,
                f"file changed while reading: {path}",
            )
        if output is not None:
            output.flush()
            os.fsync(output.fileno())
        return size, digest.hexdigest()
    finally:
        if output is not None:
            output.close()


def write_bytes(path: Path, data: bytes) -> None:
    with path.open("xb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def check_repo(repo: Path, *, optional: bool = False) -> bool:
    if not directory(repo, optional=optional):
        return False
    inventory(repo)  # All managed paths must be free of symlinks/special nodes.
    directory(repo / "snapshots", optional=True)
    directory(repo / ".staging", optional=True)
    return True


def create(source: Path, repo: Path, snapshot_id: str) -> dict:
    require(not overlap(source, repo), "source and repository overlap")
    entries = inventory(source)
    check_repo(repo, optional=True)
    final = repo / "snapshots" / snapshot_id
    require(node_stat(final) is None, "snapshot ID already exists")
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "snapshots").mkdir(exist_ok=True)
    (repo / ".staging").mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f"{snapshot_id}-", dir=repo / ".staging"))
    try:
        data = stage / "data"
        data.mkdir()
        records = []
        for relative in sorted(entries):
            node_kind = entries[relative]
            target = data / relative
            record = {"path": relative, "type": node_kind}
            if node_kind == "dir":
                target.mkdir()
            else:
                size, digest = file_data(source / relative, target)
                record.update(size=size, sha256=digest)
            records.append(record)
        # Check that the stable source still has exactly the inventoried paths.
        require(inventory(source) == entries, "source tree changed during create")
        manifest = canonical({"version": 1, "id": snapshot_id, "entries": records})
        write_bytes(stage / "manifest.json", manifest)
        write_bytes(stage / "COMMIT", (hashlib.sha256(manifest).hexdigest() + "\n").encode("ascii"))
        sync_directory(stage)
        safe_path(final)
        require(node_stat(final) is None, "snapshot ID already exists")
        # A complete concurrent snapshot is nonempty: rename cannot replace it.
        os.rename(stage, final)
        sync_directory(repo / "snapshots")
        return {"id": snapshot_id}
    finally:
        if node_stat(stage) is not None:
            shutil.rmtree(stage)


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def manifest_entries(snapshot: Path, snapshot_id: str) -> list[dict]:
    directory(snapshot)
    require(
        {item.name for item in snapshot.iterdir()} == {"data", "manifest.json", "COMMIT"},
        "snapshot layout is incomplete or contains extra entries",
    )
    with open_regular(snapshot / "manifest.json") as source:
        raw = source.read()
    with open_regular(snapshot / "COMMIT") as source:
        marker = source.read(66)
    expected = (hashlib.sha256(raw).hexdigest() + "\n").encode("ascii")
    require(marker == expected, "manifest checksum mismatch")
    try:
        manifest = json.loads(raw, object_pairs_hook=strict_object)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise BackupError("invalid manifest JSON") from error
    require(type(manifest) is dict and set(manifest) == {"version", "id", "entries"}, "invalid manifest schema")
    require(type(manifest["version"]) is int and manifest["version"] == 1, "unsupported manifest version")
    require(manifest["id"] == snapshot_id, "manifest ID mismatch")
    require(canonical(manifest) == raw, "noncanonical manifest")
    records = manifest["entries"]
    require(type(records) is list, "invalid entries")
    known: dict[str, str] = {}
    for record in records:
        require(type(record) is dict, "invalid entry")
        relative, node_kind = record.get("path"), record.get("type")
        require(type(relative) is str and relative != "" and "\0" not in relative, "invalid entry path")
        require(all(part not in ("", ".", "..") for part in relative.split("/")), "unsafe entry path")
        require(node_kind in ("file", "dir"), "invalid entry type")
        keys = {"path", "type", "size", "sha256"} if node_kind == "file" else {"path", "type"}
        require(set(record) == keys, "invalid entry schema")
        require(relative not in known, "duplicate entry path")
        if node_kind == "file":
            require(type(record["size"]) is int and record["size"] >= 0, "invalid file size")
            require(type(record["sha256"]) is str and HASH_RE.fullmatch(record["sha256"]) is not None, "invalid file hash")
        known[relative] = node_kind
    require(list(known) == sorted(known), "entries are not sorted")
    for relative in known:
        parent = relative.rpartition("/")[0]
        require(not parent or known.get(parent) == "dir", "missing parent directory")
    require(inventory(snapshot / "data") == known, "snapshot inventory mismatch")
    return records


def verified_entries(repo: Path, snapshot_id: str) -> list[dict]:
    snapshot = repo / "snapshots" / snapshot_id
    records = manifest_entries(snapshot, snapshot_id)
    for record in records:
        if record["type"] == "file":
            size, digest = file_data(snapshot / "data" / record["path"])
            require((size, digest) == (record["size"], record["sha256"]), f"corrupt file: {record['path']}")
    return records


def verify(repo: Path, snapshot_id: str) -> dict:
    check_repo(repo)
    verified_entries(repo, snapshot_id)
    return {"id": snapshot_id, "valid": True}


def empty_destination(dest: Path) -> None:
    safe_path(dest)
    if directory(dest, optional=True):
        require(not any(dest.iterdir()), "destination is not empty")


def restore(repo: Path, snapshot_id: str, dest: Path) -> dict:
    require(not overlap(repo, dest), "destination and repository overlap")
    empty_destination(dest)
    check_repo(repo)
    records = verified_entries(repo, snapshot_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".backup-restore-", dir=dest.parent))
    try:
        for record in records:
            target = stage / record["path"]
            if record["type"] == "dir":
                target.mkdir()
            else:
                size, digest = file_data(repo / "snapshots" / snapshot_id / "data" / record["path"], target)
                require((size, digest) == (record["size"], record["sha256"]), f"corrupt file: {record['path']}")
        sync_directory(stage)
        empty_destination(dest)
        os.replace(stage, dest)  # Replaces only an empty directory or absent path.
        sync_directory(dest.parent)
        return {"id": snapshot_id}
    finally:
        if node_stat(stage) is not None:
            shutil.rmtree(stage)


def list_snapshots(repo: Path) -> dict:
    if not check_repo(repo, optional=True) or not directory(repo / "snapshots", optional=True):
        return {"snapshots": []}
    snapshots = []
    for path in sorted((repo / "snapshots").iterdir(), key=lambda item: item.name):
        valid_id(path.name)
        directory(path)
        if node_stat(path / "COMMIT") is None:
            continue
        verified_entries(repo, path.name)
        snapshots.append(path.name)
    return {"snapshots": snapshots}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise BackupError(message)


def main(argv: list[str] | None = None) -> int:
    parser = Parser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "verify", "restore", "list"):
        command = commands.add_parser(name)
        command.add_argument("--repo", required=True)
        if name != "list":
            command.add_argument("--id", required=True)
        if name == "create":
            command.add_argument("--source", required=True)
        if name == "restore":
            command.add_argument("--dest", required=True)
    try:
        args = parser.parse_args(argv)
        if args.command != "list":
            valid_id(args.id)
        repo = safe_path(args.repo)
        if args.command == "create":
            result = create(safe_path(args.source), repo, args.id)
        elif args.command == "verify":
            result = verify(repo, args.id)
        elif args.command == "restore":
            result = restore(repo, args.id, safe_path(args.dest))
        else:
            result = list_snapshots(repo)
    except (BackupError, OSError, ValueError, RecursionError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
