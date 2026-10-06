#!/usr/bin/env python3
"""Verifiable, self-contained tree backups. Python 3.12, standard library."""

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile


ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z", re.ASCII)
HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
CHUNK_SIZE = 1024 * 1024


class BackupError(Exception):
    """A rejected operation; never represented as success."""


def require(condition, message):
    if not condition:
        raise BackupError(message)


def check_id(snapshot_id):
    require(ID_PATTERN.fullmatch(snapshot_id) is not None, "invalid snapshot ID")


def checked_path(value):
    """Check original components before normalizing, including before '..'."""
    require(bool(value), "empty filesystem path")
    raw = value if os.path.isabs(value) else os.path.join(os.getcwd(), value)
    components = [part for part in raw.split(os.sep) if part]
    current = os.sep
    for index, part in enumerate(components):
        current = os.path.join(current, part)
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(mode), f"symlink rejected: {current}")
        require(stat.S_ISDIR(mode) or stat.S_ISREG(mode),
                f"special file rejected: {current}")
        if index < len(components) - 1:
            require(stat.S_ISDIR(mode), f"path component is not a directory: {current}")
    return os.path.abspath(raw)


def directory(path):
    require(stat.S_ISDIR(os.lstat(path).st_mode), f"not a directory: {path}")


def overlaps(first, second):
    return os.path.commonpath([first, second]) in (first, second)


def inventory(root):
    """Return sorted relative directories/files, refusing to follow symlinks."""
    directory(root)
    directories, files = [], []
    pending = [(root, "")]
    while pending:
        absolute, relative = pending.pop()
        with os.scandir(absolute) as entries:
            for entry in entries:
                name = f"{relative}/{entry.name}" if relative else entry.name
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISDIR(mode):
                    directories.append(name)
                    pending.append((entry.path, name))
                elif stat.S_ISREG(mode):
                    files.append(name)
                else:
                    raise BackupError(f"symlink or special file rejected: {entry.path}")
    return sorted(directories), sorted(files)


def regular_reader(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0))
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), f"not a regular file: {path}")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def read_regular(path):
    with regular_reader(path) as stream:
        return stream.read()


def digest_file(path, target=None):
    digest = hashlib.sha256()
    size = 0
    with regular_reader(path) as source:
        if target is None:
            while chunk := source.read(CHUNK_SIZE):
                digest.update(chunk)
                size += len(chunk)
        else:
            with open(target, "xb") as output:
                while chunk := source.read(CHUNK_SIZE):
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                output.flush()
                os.fsync(output.fileno())
    return size, digest.hexdigest()


def write_bytes(path, data):
    with open(path, "xb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                 | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def sync_tree(root, directories):
    for relative in sorted(directories, key=lambda item: item.count("/"), reverse=True):
        sync_directory(tree_path(root, relative))
    sync_directory(root)


def tree_path(root, relative):
    return os.path.join(root, *relative.split("/"))


def inspect_repo(repo):
    """Accept absent/empty repositories; check safety even in abandoned staging."""
    if not os.path.lexists(repo):
        return
    inventory(repo)
    names = set(os.listdir(repo))
    require(names <= {"snapshots", ".staging"}, "unrecognized repository layout")
    for name in names:
        directory(os.path.join(repo, name))
    snapshots = os.path.join(repo, "snapshots")
    if os.path.isdir(snapshots):
        for name in os.listdir(snapshots):
            check_id(name)
            directory(os.path.join(snapshots, name))


def initialize_repo(repo):
    os.makedirs(repo, mode=0o700, exist_ok=True)
    for name in ("snapshots", ".staging"):
        os.makedirs(os.path.join(repo, name), mode=0o700, exist_ok=True)
    sync_directory(repo)


def create(source, repo, snapshot_id):
    require(not overlaps(source, repo), "source and repository overlap")
    directories, files = inventory(source)
    inspect_repo(repo)
    target = os.path.join(repo, "snapshots", snapshot_id)
    require(not os.path.lexists(target), "snapshot ID already exists")
    initialize_repo(repo)
    staging = tempfile.mkdtemp(prefix=f"{snapshot_id}-", dir=os.path.join(repo, ".staging"))
    try:
        data = os.path.join(staging, "data")
        os.mkdir(data, mode=0o700)
        for relative in directories:
            os.mkdir(tree_path(data, relative), mode=0o700)
        records = []
        for relative in files:
            size, digest = digest_file(tree_path(source, relative), tree_path(data, relative))
            records.append({"path": relative, "size": size, "sha256": digest})
        manifest = {"version": 1, "id": snapshot_id,
                    "directories": directories, "files": records}
        raw = (json.dumps(manifest, ensure_ascii=True, sort_keys=True,
                          separators=(",", ":")) + "\n").encode("utf-8")
        write_bytes(os.path.join(staging, "manifest.json"), raw)
        write_bytes(os.path.join(staging, "manifest.sha256"),
                    (hashlib.sha256(raw).hexdigest() + "\n").encode("ascii"))
        sync_tree(data, directories)
        sync_directory(staging)
        require(not os.path.lexists(target), "snapshot ID already exists")
        # Complete snapshots are nonempty: concurrent creates cannot replace one.
        os.rename(staging, target)
        sync_directory(os.path.join(repo, "snapshots"))
        sync_directory(os.path.join(repo, ".staging"))
    finally:
        if os.path.lexists(staging):
            shutil.rmtree(staging)
    return {"id": snapshot_id}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate manifest key")
        result[key] = value
    return result


def relative_path(value):
    require(isinstance(value, str) and bool(value) and "\0" not in value,
            "invalid manifest path")
    parts = value.split("/")
    require(all(part not in ("", ".", "..") for part in parts), "unsafe manifest path")
    require(not os.path.isabs(value), "absolute manifest path")
    if os.altsep:
        require(os.altsep not in value, "unsupported path separator")


def validate_manifest(manifest, snapshot_id):
    require(type(manifest) is dict
            and set(manifest) == {"version", "id", "directories", "files"},
            "invalid manifest schema")
    require(type(manifest["version"]) is int and manifest["version"] == 1,
            "unsupported manifest version")
    require(manifest["id"] == snapshot_id, "manifest ID mismatch")
    directories, files = manifest["directories"], manifest["files"]
    require(type(directories) is list and type(files) is list, "invalid manifest entries")
    for relative in directories:
        relative_path(relative)
    require(directories == sorted(set(directories)), "duplicate or unsorted directories")
    paths = []
    for record in files:
        require(type(record) is dict and set(record) == {"path", "size", "sha256"},
                "invalid file record")
        relative_path(record["path"])
        require(type(record["size"]) is int and record["size"] >= 0, "invalid file size")
        require(isinstance(record["sha256"], str)
                and HASH_PATTERN.fullmatch(record["sha256"]) is not None,
                "invalid file hash")
        paths.append(record["path"])
    require(paths == sorted(set(paths)), "duplicate or unsorted files")
    known_dirs = set(directories)
    require(not known_dirs.intersection(paths), "file/directory path collision")
    for relative in directories + paths:
        if "/" in relative:
            require(relative.rsplit("/", 1)[0] in known_dirs, "missing parent directory")


def verified_snapshot(repo, snapshot_id):
    snapshot = os.path.join(repo, "snapshots", snapshot_id)
    require(os.path.lexists(snapshot), "snapshot ID does not exist")
    directory(snapshot)
    # Checking the full tree also rejects hidden extra links/special files.
    inventory(snapshot)
    require(set(os.listdir(snapshot)) == {"manifest.json", "manifest.sha256", "data"},
            "incomplete or unexpected snapshot structure")
    raw = read_regular(os.path.join(snapshot, "manifest.json"))
    seal = read_regular(os.path.join(snapshot, "manifest.sha256"))
    require(seal == (hashlib.sha256(raw).hexdigest() + "\n").encode("ascii"),
            "manifest checksum mismatch")
    try:
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise BackupError("invalid manifest JSON") from error
    validate_manifest(manifest, snapshot_id)
    data = os.path.join(snapshot, "data")
    directories, files = inventory(data)
    require(directories == manifest["directories"]
            and files == [record["path"] for record in manifest["files"]],
            "snapshot tree differs from manifest")
    for record in manifest["files"]:
        actual = digest_file(tree_path(data, record["path"]))
        require(actual == (record["size"], record["sha256"]),
                f"file checksum/size mismatch: {record['path']}")
    return manifest


def verify(repo, snapshot_id):
    inspect_repo(repo)
    verified_snapshot(repo, snapshot_id)
    return {"id": snapshot_id, "valid": True}


def empty_destination(dest):
    checked_path(dest)
    if os.path.lexists(dest):
        directory(dest)
        require(not os.listdir(dest), "destination is not empty")


def restore(repo, snapshot_id, dest):
    require(not overlaps(repo, dest), "destination and repository overlap")
    empty_destination(dest)
    inspect_repo(repo)
    manifest = verified_snapshot(repo, snapshot_id)
    parent = os.path.dirname(dest)
    os.makedirs(parent, mode=0o700, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=f".{os.path.basename(dest)}.restore-", dir=parent)
    try:
        for relative in manifest["directories"]:
            os.mkdir(tree_path(staging, relative), mode=0o700)
        data = os.path.join(repo, "snapshots", snapshot_id, "data")
        for record in manifest["files"]:
            actual = digest_file(tree_path(data, record["path"]),
                                 tree_path(staging, record["path"]))
            require(actual == (record["size"], record["sha256"]),
                    f"file changed while restoring: {record['path']}")
        sync_tree(staging, manifest["directories"])
        empty_destination(dest)
        os.rename(staging, dest)
        sync_directory(parent)
    finally:
        if os.path.lexists(staging):
            shutil.rmtree(staging)
    return {"id": snapshot_id}


def list_snapshots(repo):
    inspect_repo(repo)
    snapshots = os.path.join(repo, "snapshots")
    result = []
    if os.path.isdir(snapshots):
        for snapshot_id in sorted(os.listdir(snapshots)):
            try:
                verified_snapshot(repo, snapshot_id)
            except (BackupError, OSError):
                continue
            result.append(snapshot_id)
    return {"snapshots": result}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("create", "verify", "restore", "list"):
        command = commands.add_parser(name)
        command.add_argument("--repo", required=True)
        if name != "list":
            command.add_argument("--id", required=True)
        if name == "create":
            command.add_argument("--source", required=True)
        if name == "restore":
            command.add_argument("--dest", required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command != "list":
            check_id(args.id)
        repo = checked_path(args.repo)
        if args.command == "create":
            result = create(checked_path(args.source), repo, args.id)
        elif args.command == "verify":
            result = verify(repo, args.id)
        elif args.command == "restore":
            result = restore(repo, args.id, checked_path(args.dest))
        else:
            result = list_snapshots(repo)
    except (BackupError, OSError, ValueError, RecursionError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
