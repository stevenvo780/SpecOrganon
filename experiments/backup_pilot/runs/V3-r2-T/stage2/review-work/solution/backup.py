#!/usr/bin/env python3
"""Verifiable, self-contained backups. Python 3.12, standard library (POSIX)."""

import argparse
import contextlib
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


ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z", re.ASCII)
HASH_RE = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
CHUNK = 1024 * 1024


class BackupError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise BackupError(message)


def safe_path(value):
    """Inspect ancestors before normalizing '..', so links cannot be hidden."""
    path = Path(value)
    if not path.is_absolute():
        path = Path.cwd() / path
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(mode), f"symlink rejected: {current}")
        require(stat.S_ISDIR(mode) or stat.S_ISREG(mode),
                f"special file rejected: {current}")
    return Path(os.path.abspath(path))


def directory(path):
    require(stat.S_ISDIR(path.lstat().st_mode), f"not a directory: {path}")


def disjoint(left, right):
    require(left != right and left not in right.parents and right not in left.parents,
            f"overlapping paths: {left}, {right}")


def tree(path):
    """Return relative component tuples and kinds; never traverse links."""
    directory(path)
    found = []
    stack = [(path, ())]
    while stack:
        folder, prefix = stack.pop()
        with os.scandir(folder) as entries:
            children = sorted(entries, key=lambda entry: entry.name)
        for entry in children:
            rel = prefix + (entry.name,)
            mode = entry.stat(follow_symlinks=False).st_mode
            if stat.S_ISDIR(mode):
                found.append((rel, "dir"))
                stack.append((Path(entry.path), rel))
            elif stat.S_ISREG(mode):
                found.append((rel, "file"))
            else:
                raise BackupError(f"symlink or special file rejected: {entry.path}")
    return sorted(found)


def regular_bytes(path):
    """Count logical bytes of every regular file, including private metadata."""
    return sum(path.joinpath(*rel).lstat().st_size
               for rel, kind in tree(path) if kind == "file")


def check_budget(repo, max_bytes):
    if max_bytes is not None:
        measured = regular_bytes(repo)
        require(measured <= max_bytes,
                f"repository needs {measured} bytes; --max-bytes is {max_bytes}")


def recover_staging(repo):
    """Called under the repository lock: no other CLI create can own a stage."""
    staging = repo / ".staging"
    for child in staging.iterdir():
        # This directory namespace is reserved for disposable, unpublished work.
        # Standalone regular files remain in place and count against the limit.
        if stat.S_ISDIR(child.lstat().st_mode):
            shutil.rmtree(child)
    sync_dir(staging)


@contextlib.contextmanager
def regular_read(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        require(stat.S_ISREG(os.fstat(descriptor).st_mode),
                f"not a regular file: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            yield stream
    finally:
        os.close(descriptor)


def digest_file(path, target=None):
    sha = hashlib.sha256()
    size = 0
    with regular_read(path) as stream:
        while block := stream.read(CHUNK):
            sha.update(block)
            size += len(block)
            if target is not None:
                target.write(block)
    return size, sha.hexdigest()


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_bytes(path, content):
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


@contextlib.contextmanager
def repository(path, create=False):
    if create:
        path.mkdir(parents=True, exist_ok=True)
    directory(path)
    tree(path)  # Reject unsafe objects anywhere in the managed repository.
    fd = os.open(path / ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), "invalid repository lock")
        fcntl.flock(fd, fcntl.LOCK_EX)
        tree(path)
        for name in ("snapshots", ".staging"):
            child = path / name
            child.mkdir(exist_ok=True)
            directory(child)
        yield
    finally:
        os.close(fd)  # Also releases the advisory lock after SIGKILL.


def no_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "duplicate manifest key")
        value[key] = item
    return value


def load_snapshot(snapshot, snapshot_id):
    inventory = tree(snapshot)
    require(set(p.name for p in snapshot.iterdir()) == {"data", "manifest.json", "COMPLETE"},
            "snapshot layout is incomplete or has unexpected entries")
    directory(snapshot / "data")
    with regular_read(snapshot / "manifest.json") as stream:
        raw = stream.read()
    with regular_read(snapshot / "COMPLETE") as stream:
        seal = stream.read(66)
    require(seal == (hashlib.sha256(raw).hexdigest() + "\n").encode("ascii"),
            "manifest seal mismatch")
    manifest = json.loads(raw, object_pairs_hook=no_duplicate_keys)
    require(isinstance(manifest, dict) and set(manifest) == {"format", "id", "entries"},
            "invalid manifest")
    require(type(manifest["format"]) is int and manifest["format"] == 1
            and manifest["id"] == snapshot_id, "snapshot identity or format mismatch")
    require(isinstance(manifest["entries"], list), "invalid entries")
    paths = {}
    blobs = set()
    for entry in manifest["entries"]:
        require(isinstance(entry, dict), "invalid entry")
        kind = entry.get("kind")
        fields = {"path", "kind"} if kind == "dir" else {"path", "kind", "blob", "size", "sha256"}
        require(kind in ("dir", "file") and set(entry) == fields, "invalid entry fields")
        parts = entry["path"]
        require(isinstance(parts, list) and len(parts) > 0, "invalid relative path")
        require(all(isinstance(p, str) and p not in ("", ".", "..")
                    and "/" not in p and "\x00" not in p for p in parts),
                "unsafe manifest path")
        rel = tuple(parts)
        require(rel not in paths, "duplicate manifest path")
        paths[rel] = kind
        if kind == "file":
            blob = entry["blob"]
            require(isinstance(blob, str) and re.fullmatch(r"[0-9]{8,}", blob, re.ASCII),
                    "invalid blob name")
            require(blob not in blobs, "duplicate blob")
            require(type(entry["size"]) is int and entry["size"] >= 0, "invalid size")
            require(isinstance(entry["sha256"], str) and HASH_RE.fullmatch(entry["sha256"]),
                    "invalid digest")
            blobs.add(blob)
    for rel in paths:
        require(all(paths.get(rel[:i]) == "dir" for i in range(1, len(rel))),
                "missing or conflicting parent directory")
    expected = {(('data',), 'dir'), (('manifest.json',), 'file'), (('COMPLETE',), 'file')}
    expected.update((("data", blob), "file") for blob in blobs)
    require(set(inventory) == expected, "missing or unexpected snapshot objects")
    return manifest["entries"]


def check_blobs(snapshot, entries):
    for entry in entries:
        if entry["kind"] == "file":
            measured = digest_file(snapshot / "data" / entry["blob"])
            require(measured == (entry["size"], entry["sha256"]),
                    f"corrupt blob: {entry['blob']}")


def create(source, repo, snapshot_id, max_bytes=None):
    disjoint(source, repo)
    inventory = tree(source)
    with repository(repo, create=True):
        final = repo / "snapshots" / snapshot_id
        require(not final.exists(), "snapshot ID already exists")
        recover_staging(repo)
        check_budget(repo, max_bytes)
        stage = Path(tempfile.mkdtemp(prefix=snapshot_id + "-", dir=repo / ".staging"))
        try:
            (stage / "data").mkdir()
            entries = []
            blob_number = 0
            for rel, kind in inventory:
                entry = {"path": list(rel), "kind": kind}
                if kind == "file":
                    blob = f"{blob_number:08d}"
                    blob_number += 1
                    with (stage / "data" / blob).open("xb") as target:
                        size, sha = digest_file(source.joinpath(*rel), target)
                        target.flush()
                        os.fsync(target.fileno())
                    entry.update(blob=blob, size=size, sha256=sha)
                entries.append(entry)
            raw = json.dumps({"format": 1, "id": snapshot_id, "entries": entries},
                             ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
            write_bytes(stage / "manifest.json", raw)
            write_bytes(stage / "COMPLETE", (hashlib.sha256(raw).hexdigest() + "\n").encode("ascii"))
            checked = load_snapshot(stage, snapshot_id)
            check_blobs(stage, checked)
            sync_dir(stage / "data")
            sync_dir(stage)
            # The stage becomes the snapshot via rename: no regular bytes are
            # added by publication. Count the entire repo while holding flock.
            check_budget(repo, max_bytes)
            require(not final.exists(), "snapshot ID already exists")
            os.rename(stage, final)
            sync_dir(repo / "snapshots")
        finally:
            if stage.exists():
                shutil.rmtree(stage)
                sync_dir(repo / ".staging")
    return {"id": snapshot_id}


def verify(repo, snapshot_id):
    with repository(repo):
        snapshot = repo / "snapshots" / snapshot_id
        entries = load_snapshot(snapshot, snapshot_id)
        check_blobs(snapshot, entries)
    return {"id": snapshot_id, "valid": True}


def empty_destination(dest):
    if dest.exists():
        directory(dest)
        require(not any(dest.iterdir()), "destination is not empty")


def restore(repo, snapshot_id, dest):
    disjoint(repo, dest)
    empty_destination(dest)
    with repository(repo):
        snapshot = repo / "snapshots" / snapshot_id
        entries = load_snapshot(snapshot, snapshot_id)
        check_blobs(snapshot, entries)
        dest.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".backup-restore-", dir=dest.parent))
        try:
            for entry in sorted(entries, key=lambda e: (len(e["path"]), e["path"])):
                target_path = stage.joinpath(*entry["path"])
                if entry["kind"] == "dir":
                    target_path.mkdir()
                else:
                    with target_path.open("xb") as target:
                        measured = digest_file(snapshot / "data" / entry["blob"], target)
                        require(measured == (entry["size"], entry["sha256"]), "corruption during restore")
                        target.flush()
                        os.fsync(target.fileno())
            for rel, kind in reversed(tree(stage)):
                if kind == "dir":
                    sync_dir(stage.joinpath(*rel))
            sync_dir(stage)
            safe_path(dest)
            empty_destination(dest)
            os.rename(stage, dest)  # Atomically replaces only an empty directory.
            sync_dir(dest.parent)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return {"id": snapshot_id}


def list_snapshots(repo):
    with repository(repo, create=True):
        snapshots = []
        for path in sorted((repo / "snapshots").iterdir()):
            require(ID_RE.fullmatch(path.name), "invalid snapshot directory name")
            directory(path)
            try:
                entries = load_snapshot(path, path.name)
                check_blobs(path, entries)
            except (BackupError, OSError, ValueError, TypeError, KeyError):
                continue  # Incomplete/corrupt snapshots are never listed as complete.
            snapshots.append(path.name)
    return {"snapshots": snapshots}


def nonnegative_bytes(value):
    if not re.fullmatch(r"[0-9]+", value, re.ASCII):
        raise argparse.ArgumentTypeError("--max-bytes must be a nonnegative decimal integer")
    try:
        return int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("--max-bytes integer is too long") from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "verify", "restore", "list"):
        command = commands.add_parser(name)
        command.add_argument("--repo", required=True)
        if name != "list":
            command.add_argument("--id", required=True)
        if name == "create":
            command.add_argument("--source", required=True)
            command.add_argument("--max-bytes", type=nonnegative_bytes,
                                 help="maximum total regular-file bytes after success")
        if name == "restore":
            command.add_argument("--dest", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command != "list":
            require(ID_RE.fullmatch(args.id), "invalid snapshot ID")
        repo = safe_path(args.repo)
        if args.command == "create":
            result = create(safe_path(args.source), repo, args.id, args.max_bytes)
        elif args.command == "verify":
            result = verify(repo, args.id)
        elif args.command == "restore":
            result = restore(repo, args.id, safe_path(args.dest))
        else:
            result = list_snapshots(repo)
    except (BackupError, OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
