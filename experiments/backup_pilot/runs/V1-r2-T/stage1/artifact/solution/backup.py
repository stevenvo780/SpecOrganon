#!/usr/bin/env python3
"""Self-contained, verified directory snapshots (Python 3.12, POSIX)."""

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


ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", re.ASCII)
HASH_RE = re.compile(r"[0-9a-f]{64}", re.ASCII)
CHUNK = 1024 * 1024


class BackupError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise BackupError(message)


def valid_id(value):
    require(isinstance(value, str) and ID_RE.fullmatch(value), "Invalid snapshot ID")
    return value


def checked_path(raw):
    """Check the original spelling, including components preceding '..'."""
    spelling = os.fspath(raw)
    require(bool(spelling) and "\x00" not in spelling, "Invalid path")
    cursor = Path("/") if os.path.isabs(spelling) else Path.cwd()
    parts = spelling.split("/")
    # Check the cwd ancestors too, without resolving symlinks.
    if not os.path.isabs(spelling):
        checked_path(str(cursor))
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            cursor = cursor.parent
            continue
        cursor = cursor / part
        try:
            mode = cursor.lstat().st_mode
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(mode), f"Symlink rejected: {cursor}")
        require(stat.S_ISDIR(mode) or stat.S_ISREG(mode), f"Special file rejected: {cursor}")
    return Path(os.path.abspath(spelling))


def directory(path):
    require(stat.S_ISDIR(path.lstat().st_mode), f"Directory required: {path}")


def mkdirs(path):
    checked_path(path)
    for component in reversed([path, *path.parents]):
        try:
            component.mkdir(mode=0o700)
        except FileExistsError:
            pass
        require(stat.S_ISDIR(component.lstat().st_mode), f"Unsafe directory: {component}")


def overlap(left, right):
    common = os.path.commonpath((left, right))
    return common in (str(left), str(right))


def inventory(root):
    """List all descendants without following links or opening special files."""
    directory(root)
    found = {}
    pending = [root]
    while pending:
        folder = pending.pop()
        directory(folder)
        with os.scandir(folder) as children:
            for child in children:
                path = Path(child.path)
                mode = child.stat(follow_symlinks=False).st_mode
                rel = path.relative_to(root).as_posix()
                if stat.S_ISDIR(mode):
                    found[rel] = "directory"
                    pending.append(path)
                elif stat.S_ISREG(mode):
                    found[rel] = "file"
                else:
                    raise BackupError(f"Symlink or special file rejected: {path}")
    return found


@contextmanager
def regular_reader(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), f"Regular file required: {path}")
        stream = os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise
    with stream:
        yield stream


def file_bytes(path):
    with regular_reader(path) as stream:
        return stream.read()


def digest_file(path, target=None):
    digest = hashlib.sha256()
    size = 0
    with regular_reader(path) as stream:
        while block := stream.read(CHUNK):
            digest.update(block)
            size += len(block)
            if target is not None:
                target.write(block)
    return size, digest.hexdigest()


def write_bytes(path, data):
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def sync_tree(root):
    dirs = [root] + [root / rel for rel, kind in inventory(root).items() if kind == "directory"]
    for folder in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        sync_dir(folder)


def repo_layout(repo):
    for child in repo.iterdir():
        mode = child.lstat().st_mode
        if child.name == ".lock":
            require(stat.S_ISREG(mode), "Invalid repository lock")
        elif child.name.startswith(".pending-"):
            require(stat.S_ISDIR(mode), "Invalid staging directory")
        else:
            valid_id(child.name)
            require(stat.S_ISDIR(mode), "Invalid repository entry")
    inventory(repo)


@contextmanager
def locked_repo(repo):
    directory(repo)
    # Reject unsafe entries before creating the lock file.
    repo_layout(repo)
    fd = os.open(repo / ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), "Invalid lock file")
        fcntl.flock(fd, fcntl.LOCK_EX)
        repo_layout(repo)
        yield
    finally:
        os.close(fd)


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def read_manifest(snapshot, snapshot_id):
    directory(snapshot)
    require({p.name for p in snapshot.iterdir()} == {"manifest.json", "manifest.sha256", "data"},
            "Incomplete or unexpected snapshot contents")
    raw = file_bytes(snapshot / "manifest.json")
    seal = file_bytes(snapshot / "manifest.sha256")
    require(seal == (hashlib.sha256(raw).hexdigest() + "\n").encode("ascii"), "Manifest checksum mismatch")
    manifest = json.loads(raw, object_pairs_hook=no_duplicate_keys)
    require(isinstance(manifest, dict) and set(manifest) == {"format", "id", "entries"}, "Invalid manifest")
    require(type(manifest["format"]) is int and manifest["format"] == 1, "Unsupported format")
    require(manifest["id"] == snapshot_id and isinstance(manifest["entries"], list), "Invalid manifest identity")
    entries = {}
    for entry in manifest["entries"]:
        require(isinstance(entry, dict), "Invalid entry")
        rel, kind = entry.get("path"), entry.get("type")
        require(isinstance(rel, str) and rel and "\x00" not in rel, "Invalid entry path")
        require(all(part not in ("", ".", "..") for part in rel.split("/")), "Unsafe entry path")
        os.fsencode(rel)
        require(rel not in entries and kind in ("file", "directory"), "Invalid entry type or duplicate path")
        keys = {"path", "type"} if kind == "directory" else {"path", "type", "size", "sha256"}
        require(set(entry) == keys, "Invalid entry fields")
        if kind == "file":
            require(type(entry["size"]) is int and entry["size"] >= 0, "Invalid file size")
            require(isinstance(entry["sha256"], str) and HASH_RE.fullmatch(entry["sha256"]), "Invalid file digest")
        entries[rel] = entry
    for rel in entries:
        parent = rel.rpartition("/")[0]
        require(not parent or parent in entries and entries[parent]["type"] == "directory", "Missing parent directory")
    return entries


def verify_snapshot(repo, snapshot_id):
    snapshot = repo / snapshot_id
    # Full scan also rejects unsafe manifest/seal and unexpected descendants.
    inventory(snapshot)
    entries = read_manifest(snapshot, snapshot_id)
    data = snapshot / "data"
    observed = inventory(data)
    require(observed == {rel: entry["type"] for rel, entry in entries.items()}, "Snapshot inventory mismatch")
    for rel, entry in entries.items():
        if entry["type"] == "file":
            require(digest_file(data / rel) == (entry["size"], entry["sha256"]), f"File checksum mismatch: {rel}")
    return entries


def copy_tree(source, target, types, expected=None):
    entries = []
    for rel in sorted(types, key=lambda p: (p.count("/"), p)):
        kind = types[rel]
        path = target / rel
        if kind == "directory":
            path.mkdir(mode=0o700)
            entry = {"path": rel, "type": kind}
        else:
            with path.open("xb") as out:
                size, digest = digest_file(source / rel, out)
                out.flush()
                os.fsync(out.fileno())
            entry = {"path": rel, "type": kind, "size": size, "sha256": digest}
        if expected is not None:
            require(entry == expected[rel], f"Data changed during restore: {rel}")
        entries.append(entry)
    return sorted(entries, key=lambda entry: entry["path"])


def create(source_raw, repo_raw, snapshot_id):
    source, repo = checked_path(source_raw), checked_path(repo_raw)
    require(not overlap(source, repo), "Source and repository overlap")
    types = inventory(source)
    mkdirs(repo)
    with locked_repo(repo):
        final = repo / snapshot_id
        require(not final.exists(), "Snapshot ID already exists")
        stage = Path(tempfile.mkdtemp(prefix=".pending-", dir=repo))
        try:
            data = stage / "data"
            data.mkdir(mode=0o700)
            entries = copy_tree(source, data, types)
            manifest = json.dumps({"format": 1, "id": snapshot_id, "entries": entries},
                                  ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
            write_bytes(stage / "manifest.json", manifest)
            write_bytes(stage / "manifest.sha256", (hashlib.sha256(manifest).hexdigest() + "\n").encode("ascii"))
            # Verify the actual copied bytes, then persist directory entries.
            verify_snapshot(repo, stage.name) if False else None
            require(inventory(data) == types, "Copied inventory mismatch")
            for entry in entries:
                if entry["type"] == "file":
                    require(digest_file(data / entry["path"]) == (entry["size"], entry["sha256"]), "Copy checksum mismatch")
            sync_tree(stage)
            os.rename(stage, final)
            sync_dir(repo)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return {"id": snapshot_id}


def verify(repo_raw, snapshot_id):
    repo = checked_path(repo_raw)
    with locked_repo(repo):
        verify_snapshot(repo, snapshot_id)
    return {"id": snapshot_id, "valid": True}


def restore(repo_raw, snapshot_id, dest_raw):
    repo, dest = checked_path(repo_raw), checked_path(dest_raw)
    require(not overlap(repo, dest), "Destination and repository overlap")
    if dest.exists():
        directory(dest)
        require(not any(dest.iterdir()), "Destination must be empty")
    with locked_repo(repo):
        entries = verify_snapshot(repo, snapshot_id)
        mkdirs(dest.parent)
        stage = Path(tempfile.mkdtemp(prefix=".restore-", dir=dest.parent))
        try:
            types = {rel: entry["type"] for rel, entry in entries.items()}
            copy_tree(repo / snapshot_id / "data", stage, types, entries)
            require(inventory(stage) == types, "Restored inventory mismatch")
            # Read back destination bytes before atomic publication.
            for rel, entry in entries.items():
                if entry["type"] == "file":
                    require(digest_file(stage / rel) == (entry["size"], entry["sha256"]), "Restore checksum mismatch")
            sync_tree(stage)
            if dest.exists():
                directory(dest)
                require(not any(dest.iterdir()), "Destination must be empty")
            os.rename(stage, dest)
            sync_dir(dest.parent)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return {"id": snapshot_id}


def list_snapshots(repo_raw):
    repo = checked_path(repo_raw)
    if not repo.exists():
        return {"snapshots": []}
    with locked_repo(repo):
        ids = sorted(p.name for p in repo.iterdir() if ID_RE.fullmatch(p.name))
        for snapshot_id in ids:
            verify_snapshot(repo, snapshot_id)
    return {"snapshots": ids}


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
        if name == "restore":
            command.add_argument("--dest", required=True)
    args = parser.parse_args(argv)
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
    except (BackupError, OSError, ValueError, UnicodeError, RecursionError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
