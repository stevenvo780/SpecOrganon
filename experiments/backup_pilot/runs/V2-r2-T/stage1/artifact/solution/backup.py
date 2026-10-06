#!/usr/bin/env python3
"""Self-contained, checksummed snapshots. Python 3.12, standard library."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import sys
import tempfile


MAGIC = b"PYBACK01"
CHUNK = 1024 * 1024
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", re.ASCII)


class BackupError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise BackupError(message)


def check_id(value):
    require(ID_PATTERN.fullmatch(value) is not None, "invalid snapshot ID")
    return value


def checked_path(value):
    """Check the spelling before normalizing: link/.. must also be rejected."""
    raw = value if os.path.isabs(value) else os.path.join(os.getcwd(), value)
    current = Path("/")
    parts = raw.split("/")
    for index, part in enumerate(parts):
        if not part or part == ".":
            continue
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(mode), "symlink in managed path")
        require(stat.S_ISDIR(mode) or stat.S_ISREG(mode), "special managed path")
        if any(p and p != "." for p in parts[index + 1:]):
            require(stat.S_ISDIR(mode), "non-directory path component")
    normalized = Path(os.path.abspath(raw))
    for path in (*reversed(normalized.parents), normalized):
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(mode), "symlink in normalized managed path")
        require(stat.S_ISDIR(mode) or stat.S_ISREG(mode), "special managed path")
        if path != normalized:
            require(stat.S_ISDIR(mode), "non-directory path component")
    return normalized


def directory(path):
    require(stat.S_ISDIR(path.lstat().st_mode), "expected a directory")


def scan_tree(root):
    """No following links. Return every relative entry, including empty dirs."""
    directory(root)
    entries = []
    pending = [root]
    while pending:
        parent = pending.pop()
        with os.scandir(parent) as iterator:
            children = list(iterator)
        for child in children:
            info = child.stat(follow_symlinks=False)
            relative = Path(child.path).relative_to(root).as_posix()
            if stat.S_ISDIR(info.st_mode):
                entries.append({"path": relative, "kind": "dir"})
                pending.append(Path(child.path))
            elif stat.S_ISREG(info.st_mode):
                entries.append({"path": relative, "kind": "file", "size": info.st_size})
            else:
                raise BackupError("symlink or special file in managed tree")
    return sorted(entries, key=lambda entry: entry["path"])


def overlaps(left, right):
    return left == right or left in right.parents or right in left.parents


def open_regular(path):
    # O_NONBLOCK prevents a raced-in FIFO from blocking before fstat.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), "expected a regular file")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def inspect_repo(repo, missing=False):
    if not repo.exists():
        require(missing, "repository does not exist")
        return
    scan_tree(repo)
    for name in ("snapshots", ".work"):
        child = repo / name
        if child.exists():
            directory(child)


def prepare_repo(repo):
    inspect_repo(repo, missing=True)
    repo.mkdir(parents=True, exist_ok=True)
    for name in ("snapshots", ".work"):
        (repo / name).mkdir(exist_ok=True, mode=0o700)


def create(source, repo, snapshot_id):
    require(not overlaps(source, repo), "source and repository overlap")
    entries = scan_tree(source)
    prepare_repo(repo)
    final = repo / "snapshots" / (snapshot_id + ".bak")
    require(not final.exists(), "snapshot ID already exists")
    manifest = json.dumps({"format": 1, "id": snapshot_id, "entries": entries},
                          ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix="create-", dir=repo / ".work")
    try:
        with os.fdopen(fd, "wb") as output:
            digest = hashlib.sha256()

            def emit(block):
                output.write(block)
                digest.update(block)

            emit(MAGIC + struct.pack(">Q", len(manifest)))
            emit(manifest)
            for entry in entries:
                if entry["kind"] != "file":
                    continue
                with open_regular(source / entry["path"]) as stream:
                    remaining = entry["size"]
                    while remaining:
                        block = stream.read(min(CHUNK, remaining))
                        require(bool(block), "source changed or read was incomplete")
                        emit(block)
                        remaining -= len(block)
                    require(not stream.read(1), "source changed size")
            output.write(digest.digest())
            output.flush()
            os.fsync(output.fileno())
        # Atomic, same-filesystem publication; fails if the ID already exists.
        os.link(temporary, final, follow_symlinks=False)
        sync_directory(repo / "snapshots")
    finally:
        os.unlink(temporary)
    return {"id": snapshot_id}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate metadata key")
        result[key] = value
    return result


def validate_manifest(manifest, snapshot_id):
    require(isinstance(manifest, dict) and set(manifest) == {"format", "id", "entries"},
            "invalid snapshot metadata")
    require(type(manifest["format"]) is int and manifest["format"] == 1,
            "unsupported snapshot format")
    require(manifest["id"] == snapshot_id, "snapshot ID mismatch")
    entries = manifest["entries"]
    require(isinstance(entries, list), "invalid entry list")
    seen = {}
    for entry in entries:
        require(isinstance(entry, dict), "invalid entry")
        name = entry.get("path")
        kind = entry.get("kind")
        require(isinstance(name, str) and name and "\x00" not in name and
                all(part not in ("", ".", "..") for part in name.split("/")),
                "invalid relative path")
        require(name not in seen, "duplicate entry")
        require(kind in ("dir", "file"), "invalid entry type")
        expected = {"path", "kind", "size"} if kind == "file" else {"path", "kind"}
        require(set(entry) == expected, "invalid entry fields")
        if kind == "file":
            require(type(entry["size"]) is int and entry["size"] >= 0, "invalid size")
        parent = name.rpartition("/")[0]
        require(not parent or seen.get(parent) == "dir", "missing parent directory")
        seen[name] = kind
    require([e["path"] for e in entries] == sorted(seen), "unordered entries")
    return entries


def consume_snapshot(repo, snapshot_id, stage=None):
    path = repo / "snapshots" / (snapshot_id + ".bak")
    with open_regular(path) as stream:
        total = os.fstat(stream.fileno()).st_size
        digest = hashlib.sha256()

        def read_exact(length):
            block = stream.read(length)
            require(len(block) == length, "truncated snapshot")
            digest.update(block)
            return block

        require(read_exact(8) == MAGIC, "invalid snapshot header")
        header_length = struct.unpack(">Q", read_exact(8))[0]
        require(header_length <= total - 48, "invalid metadata length")
        manifest = json.loads(read_exact(header_length), object_pairs_hook=unique_object)
        entries = validate_manifest(manifest, snapshot_id)
        payload_length = sum(e["size"] for e in entries if e["kind"] == "file")
        require(total == 16 + header_length + payload_length + 32, "snapshot length mismatch")
        for entry in entries:
            target = stage / entry["path"] if stage is not None else None
            if entry["kind"] == "dir":
                if target is not None:
                    target.mkdir(mode=0o700)
                continue
            output = target.open("xb") if target is not None else None
            try:
                remaining = entry["size"]
                while remaining:
                    block = read_exact(min(CHUNK, remaining))
                    if output is not None:
                        output.write(block)
                    remaining -= len(block)
                if output is not None:
                    output.flush()
                    os.fsync(output.fileno())
            finally:
                if output is not None:
                    output.close()
        require(stream.read(32) == digest.digest(), "snapshot checksum mismatch")
        require(not stream.read(1), "unexpected trailing bytes")


def verify(repo, snapshot_id):
    inspect_repo(repo)
    consume_snapshot(repo, snapshot_id)
    return {"id": snapshot_id, "valid": True}


def restore(repo, snapshot_id, destination):
    require(not overlaps(repo, destination), "repository and destination overlap")
    inspect_repo(repo)
    if destination.exists():
        directory(destination)
        require(not scan_tree(destination), "destination is not empty")
    # Validate before creating even a parent directory in the destination path.
    consume_snapshot(repo, snapshot_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".restore-", dir=destination.parent))
    try:
        # Check the bytes again while copying; corrupted data never gets published.
        consume_snapshot(repo, snapshot_id, stage)
        if destination.exists():
            directory(destination)
            destination.rmdir()  # Nonempty destinations cannot be removed.
        os.rename(stage, destination)
        sync_directory(destination.parent)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return {"id": snapshot_id}


def list_snapshots(repo):
    inspect_repo(repo, missing=True)
    snapshots = repo / "snapshots"
    if not snapshots.exists():
        return {"snapshots": []}
    ids = []
    for child in sorted(snapshots.iterdir()):
        require(child.is_file() and child.name.endswith(".bak"), "invalid repository entry")
        snapshot_id = check_id(child.name[:-4])
        consume_snapshot(repo, snapshot_id)
        ids.append(snapshot_id)
    return {"snapshots": sorted(ids)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="operation", required=True)
    for name in ("create", "verify", "restore", "list"):
        command = subcommands.add_parser(name)
        command.add_argument("--repo", required=True)
        if name != "list":
            command.add_argument("--id", required=True)
        if name == "create":
            command.add_argument("--source", required=True)
        if name == "restore":
            command.add_argument("--dest", required=True)
    args = parser.parse_args()
    try:
        if args.operation != "list":
            check_id(args.id)
        repo = checked_path(args.repo)
        if args.operation == "create":
            result = create(checked_path(args.source), repo, args.id)
        elif args.operation == "verify":
            result = verify(repo, args.id)
        elif args.operation == "restore":
            result = restore(repo, args.id, checked_path(args.dest))
        else:
            result = list_snapshots(repo)
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return 0
    except (BackupError, OSError, ValueError, TypeError, RecursionError, OverflowError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
