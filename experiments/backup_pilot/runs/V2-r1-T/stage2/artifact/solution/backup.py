#!/usr/bin/env python3
"""Autosufficient full snapshots. Python 3.12, standard library, Linux/POSIX."""

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
DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
REGULAR = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


class BackupError(Exception):
    pass


def reject(message):
    raise BackupError(message)


def valid_id(value):
    if not ID_RE.fullmatch(value):
        reject("invalid snapshot ID")
    return value


def checked_path(value):
    """Inspect even components preceding '..', without resolving symlinks."""
    raw = os.fspath(value)
    if not raw or "\0" in raw:
        reject("invalid directory path")
    absolute = raw if os.path.isabs(raw) else os.path.join(os.getcwd(), raw)
    current = Path("/")
    missing = False
    for part in absolute.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if missing:
                reject("nonexistent component before '..'")
            current = current.parent
            continue
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            missing = True
            continue
        if stat.S_ISLNK(info.st_mode):
            reject("symlink in directory path: " + str(current))
        if not stat.S_ISDIR(info.st_mode):
            reject("non-directory in directory path: " + str(current))
    return current


def overlaps(left, right):
    return left == right or left in right.parents or right in left.parents


def regular_fd(name, parent_fd):
    fd = os.open(name, REGULAR, dir_fd=parent_fd)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        reject("not a regular file: " + name)
    return fd


def scan_tree(root, copy_to=None, hash_files=True):
    """Traverse with directory descriptors; never follow a directory symlink."""
    records = []

    def visit(fd, prefix, target):
        with os.scandir(fd) as children:
            names = sorted(entry.name for entry in children)
        for name in names:
            relative = prefix + name
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                records.append({"path": relative, "type": "dir"})
                child_target = target / name if target is not None else None
                if child_target is not None:
                    child_target.mkdir(mode=0o700)
                child_fd = os.open(name, DIRECTORY, dir_fd=fd)
                try:
                    visit(child_fd, relative + "/", child_target)
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(info.st_mode):
                record = {"path": relative, "type": "file", "size": info.st_size}
                if hash_files or target is not None:
                    digest = hashlib.sha256()
                    size = 0
                    with os.fdopen(regular_fd(name, fd), "rb") as incoming:
                        with contextlib.ExitStack() as stack:
                            outgoing = None
                            if target is not None:
                                outgoing = stack.enter_context((target / name).open("xb"))
                            while block := incoming.read(CHUNK):
                                digest.update(block)
                                size += len(block)
                                if outgoing is not None:
                                    outgoing.write(block)
                            if outgoing is not None:
                                outgoing.flush()
                                os.fsync(outgoing.fileno())
                    record.update(size=size, sha256=digest.hexdigest())
                records.append(record)
            else:
                reject("symlink or special file: " + relative)

    fd = os.open(root, DIRECTORY)
    try:
        visit(fd, "", copy_to)
    finally:
        os.close(fd)
    return sorted(records, key=lambda entry: entry["path"])


def sync_directory(path):
    fd = os.open(path, DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def sync_tree_directories(root):
    for entry in reversed(scan_tree(root, hash_files=False)):
        if entry["type"] == "dir":
            sync_directory(root / entry["path"])
    sync_directory(root)


@contextlib.contextmanager
def repository(path, create=False):
    if not path.exists():
        if not create:
            reject("repository does not exist")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, DIRECTORY)
    try:
        # A directory lock needs no persistent file and is released after SIGKILL.
        fcntl.flock(fd, fcntl.LOCK_EX)
        scan_tree(path, hash_files=False)
        with os.scandir(fd) as entries:
            for entry in entries:
                if not entry.is_dir(follow_symlinks=False):
                    reject("unexpected file in repository root")
                if not (ID_RE.fullmatch(entry.name) or entry.name.startswith(".stage-")):
                    reject("unexpected directory in repository root")
        yield
    finally:
        os.close(fd)


def read_regular(path):
    parent = os.open(path.parent, DIRECTORY)
    try:
        with os.fdopen(regular_fd(path.name, parent), "rb") as stream:
            return stream.read()
    finally:
        os.close(parent)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            reject("duplicate JSON key")
        result[key] = value
    return result


def validate_manifest(manifest, snapshot_id):
    if not isinstance(manifest, dict) or set(manifest) != {"format", "id", "entries"}:
        reject("invalid manifest")
    if type(manifest["format"]) is not int or manifest["format"] != 1:
        reject("unsupported manifest format")
    if manifest["id"] != snapshot_id or not isinstance(manifest["entries"], list):
        reject("invalid manifest ID or entries")
    known = {}
    for entry in manifest["entries"]:
        if not isinstance(entry, dict):
            reject("invalid manifest entry")
        path = entry.get("path")
        if not isinstance(path, str) or "\0" in path:
            reject("invalid manifest path")
        parts = path.split("/")
        if any(part in ("", ".", "..") for part in parts) or path in known:
            reject("unsafe or duplicate manifest path")
        if len(parts) > 1 and known.get("/".join(parts[:-1])) != "dir":
            reject("missing parent directory in manifest")
        kind = entry.get("type")
        if kind == "dir":
            if set(entry) != {"path", "type"}:
                reject("invalid directory entry")
        elif kind == "file":
            if set(entry) != {"path", "type", "size", "sha256"}:
                reject("invalid file entry")
            if type(entry["size"]) is not int or entry["size"] < 0:
                reject("invalid file size")
            if not isinstance(entry["sha256"], str) or not HASH_RE.fullmatch(entry["sha256"]):
                reject("invalid file hash")
        else:
            reject("invalid entry type")
        known[path] = kind
    if manifest["entries"] != sorted(manifest["entries"], key=lambda entry: entry["path"]):
        reject("manifest entries must be ordered")
    return manifest["entries"]


def verify_snapshot(snapshot, snapshot_id):
    if not snapshot.is_dir() or snapshot.is_symlink():
        reject("snapshot does not exist or is not a directory")
    if set(os.listdir(snapshot)) != {"tree", "manifest.json", "manifest.sha256"}:
        reject("incomplete or unexpected snapshot structure")
    raw = read_regular(snapshot / "manifest.json")
    checksum = read_regular(snapshot / "manifest.sha256")
    if checksum != (hashlib.sha256(raw).hexdigest() + "\n").encode("ascii"):
        reject("manifest checksum mismatch")
    manifest = json.loads(raw, object_pairs_hook=unique_object)
    expected = validate_manifest(manifest, snapshot_id)
    actual = scan_tree(snapshot / "tree")
    if actual != expected:
        reject("snapshot data or directory structure mismatch")
    return expected


def write_synced(path, data):
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def repository_bytes(repo):
    """Logical sizes of ALL regular files, including manifests and staging."""
    return sum(entry["size"] for entry in scan_tree(repo, hash_files=False)
               if entry["type"] == "file")


def remove_abandoned_stages(repo):
    # The exclusive repository lock ensures no CLI writer still owns a stage.
    # repository() already checked every entry for symlinks and special files.
    for path in repo.iterdir():
        if path.name.startswith(".stage-"):
            shutil.rmtree(path)
    sync_directory(repo)


def create(source, repo, snapshot_id, max_bytes=None):
    if overlaps(source, repo):
        reject("source and repository overlap")
    with repository(repo, create=True):
        snapshot = repo / snapshot_id
        if snapshot.exists():
            reject("snapshot ID already exists")
        remove_abandoned_stages(repo)
        if max_bytes is not None and repository_bytes(repo) > max_bytes:
            reject("repository already exceeds --max-bytes")
        stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=repo))
        try:
            tree = stage / "tree"
            tree.mkdir(mode=0o700)
            entries = scan_tree(source, copy_to=tree)
            raw = json.dumps({"format": 1, "id": snapshot_id, "entries": entries},
                             ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
            write_synced(stage / "manifest.json", raw)
            write_synced(stage / "manifest.sha256", (hashlib.sha256(raw).hexdigest() + "\n").encode("ascii"))
            verify_snapshot(stage, snapshot_id)
            sync_tree_directories(stage)
            # The stage is already inside the repository. Rename preserves the
            # sum, so this includes prior snapshots, candidate data and metadata.
            if max_bytes is not None and repository_bytes(repo) > max_bytes:
                reject("snapshot would exceed --max-bytes")
            # All CLI writers hold the directory lock. No partial ID is exposed.
            os.rename(stage, snapshot)
            sync_directory(repo)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
                sync_directory(repo)
    return {"id": snapshot_id}


def verify(repo, snapshot_id):
    with repository(repo):
        verify_snapshot(repo / snapshot_id, snapshot_id)
    return {"id": snapshot_id, "valid": True}


def restore(repo, snapshot_id, dest):
    if overlaps(repo, dest):
        reject("destination and repository overlap")
    with repository(repo):
        expected = verify_snapshot(repo / snapshot_id, snapshot_id)
        existed = dest.exists()
        original = dest.stat() if existed else None
        if existed and any(dest.iterdir()):
            reject("destination is not empty")
        dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".backup-restore-", dir=dest.parent))
        try:
            copied = scan_tree(repo / snapshot_id / "tree", copy_to=stage)
            if copied != expected or scan_tree(stage) != expected:
                reject("restored data failed verification")
            sync_tree_directories(stage)
            # Recheck before publication, including directory identity.
            checked_path(dest)
            if existed:
                now = dest.stat()
                if (now.st_dev, now.st_ino) != (original.st_dev, original.st_ino) or any(dest.iterdir()):
                    reject("destination changed during restore")
            elif dest.exists():
                reject("destination appeared during restore")
            os.rename(stage, dest)
            sync_directory(dest.parent)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return {"id": snapshot_id}


def list_snapshots(repo):
    snapshots = []
    with repository(repo, create=True):
        for path in sorted(repo.iterdir()):
            if not ID_RE.fullmatch(path.name):
                continue
            try:
                verify_snapshot(path, path.name)
            except (BackupError, OSError, ValueError, UnicodeError):
                # Neither interrupted nor corrupt snapshots are advertised.
                continue
            snapshots.append(path.name)
    return {"snapshots": snapshots}


def byte_limit(value):
    if not re.fullmatch(r"[0-9]+", value, re.ASCII):
        raise argparse.ArgumentTypeError("--max-bytes must be a nonnegative integer")
    return int(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "verify", "restore", "list"):
        sub = commands.add_parser(name)
        sub.add_argument("--repo", required=True)
        if name != "list":
            sub.add_argument("--id", required=True)
        if name == "create":
            sub.add_argument("--source", required=True)
            sub.add_argument("--max-bytes", type=byte_limit,
                             help="maximum sum of all repository regular-file sizes")
        if name == "restore":
            sub.add_argument("--dest", required=True)
    args = parser.parse_args()
    try:
        if args.command != "list":
            valid_id(args.id)
        repo = checked_path(args.repo)
        if args.command == "create":
            result = create(checked_path(args.source), repo, args.id, args.max_bytes)
        elif args.command == "verify":
            result = verify(repo, args.id)
        elif args.command == "restore":
            result = restore(repo, args.id, checked_path(args.dest))
        else:
            result = list_snapshots(repo)
    except (BackupError, OSError, ValueError, UnicodeError, RecursionError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
