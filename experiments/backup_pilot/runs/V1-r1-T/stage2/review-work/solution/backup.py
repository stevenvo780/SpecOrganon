#!/usr/bin/env python3
"""Self-contained, verified snapshots. Python 3.12, standard library, POSIX."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile


ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", re.ASCII)
HASH_PATTERN = re.compile(r"[0-9a-f]{64}", re.ASCII)
BLOCK = 1024 * 1024


class BackupError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise BackupError(message)


def valid_id(value):
    require(isinstance(value, str) and ID_PATTERN.fullmatch(value), "invalid ID")
    return value


def checked_path(raw, *, missing=False):
    """Check even the unnormalized components (link/.. must not hide a link)."""
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    normalized = Path(os.path.abspath(path))
    for candidate in (path, normalized):
        current = Path(candidate.anchor)
        for index, part in enumerate(candidate.parts[1:]):
            current = current / part
            try:
                mode = current.lstat().st_mode
            except FileNotFoundError:
                if missing:
                    continue
                raise BackupError(f"path does not exist: {current}") from None
            require(not stat.S_ISLNK(mode), f"symlink rejected: {current}")
            require(stat.S_ISDIR(mode) or stat.S_ISREG(mode),
                    f"special file rejected: {current}")
            if index < len(candidate.parts) - 2:
                require(stat.S_ISDIR(mode), f"parent is not a directory: {current}")
    return normalized


def directory(path):
    require(stat.S_ISDIR(path.lstat().st_mode), f"not a directory: {path}")


def disjoint(left, right):
    require(left != right and left not in right.parents and right not in left.parents,
            "managed directories overlap")


def inventory(root):
    """Return every directory (including empty ones) and regular file, no links."""
    directory(root)
    result = {}
    pending = [root]
    while pending:
        parent = pending.pop()
        with os.scandir(parent) as stream:
            children = sorted(stream, key=lambda entry: entry.name)
        for child in children:
            path = parent / child.name
            mode = path.lstat().st_mode
            name = path.relative_to(root).as_posix()
            if stat.S_ISDIR(mode):
                result[name] = "dir"
                pending.append(path)
            elif stat.S_ISREG(mode):
                result[name] = "file"
            else:
                raise BackupError(f"symlink or special file rejected: {path}")
    return result


@contextmanager
def regular_reader(path):
    # NONBLOCK avoids blocking on a FIFO substituted since the inventory check.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), f"not a regular file: {path}")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            yield stream
    finally:
        os.close(fd)


def digest_file(path):
    digest = hashlib.sha256()
    size = 0
    with regular_reader(path) as stream:
        while block := stream.read(BLOCK):
            digest.update(block)
            size += len(block)
    return size, digest.hexdigest()


def copy_file(source, target):
    digest = hashlib.sha256()
    size = 0
    with regular_reader(source) as stream:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as output:
            while block := stream.read(BLOCK):
                output.write(block)
                digest.update(block)
                size += len(block)
            output.flush()
            os.fsync(output.fileno())
    return size, digest.hexdigest()


def write_bytes(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def sync_tree(root):
    paths = [root / name for name, kind in inventory(root).items() if kind == "dir"]
    for path in sorted(paths, key=lambda p: len(p.parts), reverse=True):
        sync_directory(path)
    sync_directory(root)


@contextmanager
def repository(root, *, initialize=False):
    if initialize:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory(root)
    inventory(root)  # Reject unsafe objects, including those in abandoned staging.
    allowed = {"snapshots", "staging", ".lock"}
    require(set(os.listdir(root)) <= allowed, "unknown repository layout")
    lock = root / ".lock"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), "invalid repository lock")
        fcntl.flock(fd, fcntl.LOCK_EX)
        # Cooperating commands cannot mutate the repository while this lock is held.
        checked_path(root)
        inventory(root)
        for name in ("snapshots", "staging"):
            path = root / name
            path.mkdir(mode=0o700, exist_ok=True)
            directory(path)
        yield root / "snapshots", root / "staging"
    finally:
        os.close(fd)


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def read_manifest(snapshot, identity):
    directory(snapshot)
    require(set(os.listdir(snapshot)) == {"data", "manifest.json", "manifest.sha256"},
            "incomplete or unexpected snapshot contents")
    with regular_reader(snapshot / "manifest.json") as stream:
        raw = stream.read()
    with regular_reader(snapshot / "manifest.sha256") as stream:
        seal = stream.read(66)
    expected = hashlib.sha256(raw).hexdigest().encode("ascii") + b"\n"
    require(seal == expected, "manifest checksum mismatch")
    try:
        manifest = json.loads(raw, object_pairs_hook=no_duplicate_keys)
    except (ValueError, UnicodeError) as error:
        raise BackupError("invalid manifest JSON") from error
    require(isinstance(manifest, dict) and set(manifest) == {"format", "id", "entries"},
            "invalid manifest schema")
    require(type(manifest["format"]) is int and manifest["format"] == 1,
            "unknown snapshot format")
    require(manifest["id"] == identity and isinstance(manifest["entries"], list),
            "invalid snapshot identity or entries")
    entries = {}
    for item in manifest["entries"]:
        require(isinstance(item, dict), "invalid manifest entry")
        name = item.get("path")
        require(isinstance(name, str) and name and "\0" not in name,
                "invalid relative path")
        require(all(part not in ("", ".", "..") for part in name.split("/")),
                "unsafe relative path")
        require(name not in entries, "duplicate manifest path")
        kind = item.get("kind")
        if kind == "dir":
            require(set(item) == {"path", "kind"}, "invalid directory entry")
        elif kind == "file":
            require(set(item) == {"path", "kind", "size", "sha256"},
                    "invalid file entry")
            require(type(item["size"]) is int and item["size"] >= 0,
                    "invalid file size")
            require(isinstance(item["sha256"], str) and HASH_PATTERN.fullmatch(item["sha256"]),
                    "invalid file checksum")
        else:
            raise BackupError("unknown entry kind")
        entries[name] = item
    for name in entries:
        parent = name.rpartition("/")[0]
        require(not parent or (parent in entries and entries[parent]["kind"] == "dir"),
                "missing parent directory entry")
    return entries


def verify_data(data, entries):
    actual = inventory(data)
    require(actual == {name: item["kind"] for name, item in entries.items()},
            "snapshot inventory mismatch")
    for name, item in entries.items():
        if item["kind"] == "file":
            require(digest_file(data / name) == (item["size"], item["sha256"]),
                    f"file checksum mismatch: {name}")


def verify_snapshot(snapshot, identity):
    entries = read_manifest(snapshot, identity)
    verify_data(snapshot / "data", entries)
    return entries


def create(source, repo, identity):
    source = checked_path(source)
    repo = checked_path(repo, missing=True)
    disjoint(source, repo)
    source_entries = inventory(source)
    with repository(repo, initialize=True) as (snapshots, staging):
        target = snapshots / identity
        require(not target.exists(), "ID already exists")
        # Abandoned stages never reserve an ID. Do not remove previous snapshots.
        work = Path(tempfile.mkdtemp(prefix="create-", dir=staging))
        try:
            data = work / "data"
            data.mkdir(mode=0o700)
            entries = []
            for name, kind in sorted(source_entries.items()):
                item = {"path": name, "kind": kind}
                if kind == "dir":
                    (data / name).mkdir(mode=0o700)
                else:
                    item["size"], item["sha256"] = copy_file(source / name, data / name)
                entries.append(item)
            manifest = {"format": 1, "id": identity, "entries": entries}
            raw = json.dumps(manifest, ensure_ascii=True, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
            write_bytes(work / "manifest.json", raw)
            write_bytes(work / "manifest.sha256", hashlib.sha256(raw).hexdigest().encode() + b"\n")
            verify_snapshot(work, identity)
            sync_tree(work)
            os.rename(work, target)
            sync_directory(snapshots)
        finally:
            if work.exists():
                shutil.rmtree(work)
    return {"id": identity}


def verify(repo, identity):
    repo = checked_path(repo)
    with repository(repo) as (snapshots, _):
        verify_snapshot(snapshots / identity, identity)
    return {"id": identity, "valid": True}


def empty_destination(dest):
    if dest.exists():
        directory(dest)
        require(not os.listdir(dest), "destination is not empty")


def restore(repo, identity, dest):
    repo = checked_path(repo)
    dest = checked_path(dest, missing=True)
    disjoint(repo, dest)
    empty_destination(dest)
    with repository(repo) as (snapshots, _):
        snapshot = snapshots / identity
        entries = verify_snapshot(snapshot, identity)
        dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        work = Path(tempfile.mkdtemp(prefix=".backup-restore-", dir=dest.parent))
        try:
            for name, item in sorted(entries.items()):
                if item["kind"] == "dir":
                    (work / name).mkdir(mode=0o700)
                else:
                    copied = copy_file(snapshot / "data" / name, work / name)
                    require(copied == (item["size"], item["sha256"]),
                            f"file changed during restore: {name}")
            verify_data(work, entries)
            sync_tree(work)
            checked_path(dest, missing=True)
            empty_destination(dest)
            os.replace(work, dest)
            sync_directory(dest.parent)
        finally:
            if work.exists():
                shutil.rmtree(work)
    return {"id": identity}


def list_snapshots(repo):
    repo = checked_path(repo, missing=True)
    if not repo.exists():
        return {"snapshots": []}
    ids = []
    with repository(repo) as (snapshots, _):
        for path in sorted(snapshots.iterdir()):
            valid_id(path.name)
            try:
                verify_snapshot(path, path.name)
            except (BackupError, OSError):
                continue  # Incomplete/corrupt regular snapshots are never listed.
            ids.append(path.name)
    return {"snapshots": ids}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
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
    args = parser.parse_args()
    try:
        if args.command != "list":
            valid_id(args.id)
        if args.command == "create":
            result = create(args.source, args.repo, args.id)
        elif args.command == "verify":
            result = verify(args.repo, args.id)
        elif args.command == "restore":
            result = restore(args.repo, args.id, args.dest)
        else:
            result = list_snapshots(args.repo)
    except (BackupError, OSError, ValueError, RecursionError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"error": "interrupted"}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
