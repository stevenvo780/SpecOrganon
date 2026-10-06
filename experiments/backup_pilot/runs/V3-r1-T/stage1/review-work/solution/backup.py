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


ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z", re.ASCII)
HASH_RE = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
BLOCK = 1024 * 1024


class BackupError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise BackupError(message)


def safe_path(value):
    """Inspect the original spelling, including components preceding '..'."""
    require(bool(value), "empty path")
    p = Path(value)
    current = Path(p.anchor) if p.is_absolute() else Path.cwd()
    parts = p.parts[1:] if p.is_absolute() else p.parts
    # Also inspect all ancestors of the working directory / absolute root.
    for ancestor in reversed((current, *current.parents)):
        st = ancestor.lstat()
        require(stat.S_ISDIR(st.st_mode), f"unsafe path component: {ancestor}")
    missing = False
    for part in parts:
        current = current / part
        try:
            st = current.lstat()
        except FileNotFoundError:
            missing = True
            continue
        require(not stat.S_ISLNK(st.st_mode), f"symlink rejected: {current}")
        require(stat.S_ISDIR(st.st_mode), f"not a directory: {current}")
    # '..' through an absent component is not a valid traversable input path.
    require(not (missing and ".." in parts), "missing component before '..'")
    return Path(os.path.abspath(value))


def overlaps(a, b):
    return a == b or a in b.parents or b in a.parents


def inventory(root):
    """Return relative paths/types, rejecting links and special files."""
    require(stat.S_ISDIR(root.lstat().st_mode), f"not a directory: {root}")
    result = {}
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as children:
            for child in children:
                mode = child.stat(follow_symlinks=False).st_mode
                relative = Path(child.path).relative_to(root).as_posix()
                if stat.S_ISDIR(mode):
                    result[relative] = "dir"
                    pending.append(Path(child.path))
                elif stat.S_ISREG(mode):
                    result[relative] = "file"
                else:
                    raise BackupError(f"symlink or special file rejected: {child.path}")
    return result


@contextmanager
def regular_reader(path):
    # NONBLOCK prevents waiting on a FIFO if a file changes after inventory.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), f"not a regular file: {path}")
        with os.fdopen(fd, "rb") as stream:
            fd = None
            yield stream
    finally:
        if fd is not None:
            os.close(fd)


def read_bytes(path):
    with regular_reader(path) as stream:
        return stream.read()


def digest_file(path, target=None):
    digest = hashlib.sha256()
    size = 0
    with regular_reader(path) as stream:
        while chunk := stream.read(BLOCK):
            digest.update(chunk)
            size += len(chunk)
            if target is not None:
                target.write(chunk)
    return size, digest.hexdigest()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_bytes(path, value):
    with open(path, "xb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def repository(path, create=False):
    if not path.exists():
        if not create:
            yield False
            return
        path.mkdir(parents=True, mode=0o700)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        # Directory inode lock: kernel releases it even after SIGKILL.
        fcntl.flock(fd, fcntl.LOCK_EX if create else fcntl.LOCK_SH)
        inventory(path)
        require(set(os.listdir(path)) <= {"snapshots", ".staging"},
                "unknown repository entries")
        for name in ("snapshots", ".staging"):
            child = path / name
            if child.exists():
                require(stat.S_ISDIR(child.lstat().st_mode), f"invalid repo directory: {name}")
            elif create:
                child.mkdir(mode=0o700)
        if (path / "snapshots").exists():
            for child in (path / "snapshots").iterdir():
                require(ID_RE.fullmatch(child.name) is not None and child.is_dir(),
                        "invalid published snapshot entry")
        yield True
    finally:
        os.close(fd)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def manifest_entries(snapshot, identifier):
    require(set(os.listdir(snapshot)) == {"tree", "manifest.json", "seal.sha256"},
            "incomplete or unexpected snapshot contents")
    require(stat.S_ISDIR((snapshot / "tree").lstat().st_mode), "missing snapshot tree")
    raw = read_bytes(snapshot / "manifest.json")
    require(read_bytes(snapshot / "seal.sha256") ==
            (hashlib.sha256(raw).hexdigest() + "\n").encode("ascii"),
            "manifest seal mismatch")
    try:
        manifest = json.loads(raw, object_pairs_hook=unique_object)
    except (ValueError, UnicodeError) as exc:
        raise BackupError("invalid manifest JSON") from exc
    require(isinstance(manifest, dict) and set(manifest) == {"format", "id", "entries"},
            "invalid manifest schema")
    require(type(manifest["format"]) is int and manifest["format"] == 1
            and manifest["id"] == identifier, "wrong manifest version or ID")
    entries = manifest["entries"]
    require(isinstance(entries, dict), "invalid manifest entries")
    for relative, entry in entries.items():
        require(isinstance(relative, str) and relative and "\x00" not in relative
                and all(p not in ("", ".", "..") for p in relative.split("/")),
                "unsafe manifest path")
        require(isinstance(entry, dict) and entry.get("type") in ("dir", "file"),
                "invalid manifest entry")
        if entry["type"] == "dir":
            require(set(entry) == {"type"}, "invalid directory entry")
        else:
            require(set(entry) == {"type", "size", "sha256"}
                    and type(entry["size"]) is int and entry["size"] >= 0
                    and isinstance(entry["sha256"], str)
                    and HASH_RE.fullmatch(entry["sha256"]) is not None,
                    "invalid file entry")
        parent = relative.rpartition("/")[0]
        if parent:
            require(entries.get(parent) == {"type": "dir"}, "missing parent directory")
    return entries


def verify_snapshot(snapshot, identifier):
    require(snapshot.exists() and stat.S_ISDIR(snapshot.lstat().st_mode),
            f"snapshot does not exist: {identifier}")
    inventory(snapshot)  # Check even unexpected paths without following links.
    entries = manifest_entries(snapshot, identifier)
    tree = snapshot / "tree"
    require(inventory(tree) == {p: e["type"] for p, e in entries.items()},
            "snapshot tree differs from manifest")
    for relative, entry in entries.items():
        if entry["type"] == "file":
            size, digest = digest_file(tree / relative)
            require(size == entry["size"] and digest == entry["sha256"],
                    f"corrupt snapshot file: {relative}")
    return entries


def sync_tree(root):
    dirs = [root] + [root / p for p, kind in inventory(root).items() if kind == "dir"]
    for directory in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        sync_directory(directory)


def create(source, repo, identifier):
    require(not overlaps(source, repo), "source and repository overlap")
    source_entries = inventory(source)
    with repository(repo, create=True):
        final = repo / "snapshots" / identifier
        require(not final.exists(), "snapshot ID already exists")
        stage = Path(tempfile.mkdtemp(prefix="create-", dir=repo / ".staging"))
        try:
            tree = stage / "tree"
            tree.mkdir(mode=0o700)
            entries = {}
            for relative in sorted(source_entries, key=lambda p: (p.count("/"), p)):
                kind = source_entries[relative]
                target = tree / relative
                if kind == "dir":
                    target.mkdir(mode=0o700)
                    entries[relative] = {"type": "dir"}
                else:
                    with open(target, "xb") as output:
                        size, digest = digest_file(source / relative, output)
                        output.flush()
                        os.fsync(output.fileno())
                    entries[relative] = {"type": "file", "size": size, "sha256": digest}
            manifest = {"format": 1, "id": identifier, "entries": entries}
            raw = json.dumps(manifest, sort_keys=True, ensure_ascii=True,
                             separators=(",", ":")).encode("utf-8")
            write_bytes(stage / "manifest.json", raw)
            write_bytes(stage / "seal.sha256", (hashlib.sha256(raw).hexdigest() + "\n").encode())
            verify_snapshot(stage, identifier)
            sync_tree(stage)
            # Lock serializes writers. Only this rename makes the ID visible.
            os.rename(stage, final)
            sync_directory(repo / "snapshots")
            sync_directory(repo / ".staging")
            sync_directory(repo)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return {"id": identifier}


def verify(repo, identifier):
    with repository(repo) as present:
        require(present, "repository does not exist")
        verify_snapshot(repo / "snapshots" / identifier, identifier)
    return {"id": identifier, "valid": True}


def restore(repo, identifier, dest):
    require(not overlaps(repo, dest), "destination and repository overlap")
    if dest.exists():
        require(not any(dest.iterdir()), "destination must be empty")
    with repository(repo) as present:
        require(present, "repository does not exist")
        snapshot = repo / "snapshots" / identifier
        entries = verify_snapshot(snapshot, identifier)
        dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        stage = Path(tempfile.mkdtemp(prefix=".restore-", dir=dest.parent))
        try:
            for relative in sorted(entries, key=lambda p: (p.count("/"), p)):
                entry = entries[relative]
                target = stage / relative
                if entry["type"] == "dir":
                    target.mkdir(mode=0o700)
                else:
                    with open(target, "xb") as output:
                        size, digest = digest_file(snapshot / "tree" / relative, output)
                        output.flush()
                        os.fsync(output.fileno())
                    require(size == entry["size"] and digest == entry["sha256"],
                            f"corruption during restore: {relative}")
            sync_tree(stage)
            # Repeat the destination check immediately before publication.
            safe_path(str(dest))
            if dest.exists():
                require(not any(dest.iterdir()), "destination must be empty")
            os.rename(stage, dest)
            sync_directory(dest.parent)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return {"id": identifier}


def list_snapshots(repo):
    ids = []
    with repository(repo) as present:
        snapshots = repo / "snapshots"
        if present and snapshots.exists():
            for snapshot in sorted(snapshots.iterdir()):
                try:
                    verify_snapshot(snapshot, snapshot.name)
                except (BackupError, OSError, ValueError):
                    continue  # Incomplete/corrupt snapshots are never listed.
                ids.append(snapshot.name)
    return {"snapshots": ids}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "verify", "restore", "list"):
        command = sub.add_parser(name)
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
            require(ID_RE.fullmatch(args.id) is not None, "invalid snapshot ID")
        repo = safe_path(args.repo)
        if args.command == "create":
            result = create(safe_path(args.source), repo, args.id)
        elif args.command == "verify":
            result = verify(repo, args.id)
        elif args.command == "restore":
            result = restore(repo, args.id, safe_path(args.dest))
        else:
            result = list_snapshots(repo)
    except (BackupError, OSError, ValueError, RecursionError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
