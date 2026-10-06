#!/usr/bin/env python3
"""Atomic, self-contained backups; Python 3.12 and the POSIX standard library."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import struct
import sys
from dataclasses import dataclass
from typing import BinaryIO, Iterator


MAGIC = b"PYBACKUP\x00\x02\r\n"
HEADER = struct.Struct(">12sQ")
DIGEST_SIZE = 32
CHUNK = 1024 * 1024
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z", re.ASCII)
STAGE_PATTERN = re.compile(r"\.backup-stage-[0-9a-f]{32}\.tmp\Z", re.ASCII)
SNAPSHOT_PATTERN = re.compile(r"([A-Za-z0-9][A-Za-z0-9_-]{0,63})\.bkp\Z", re.ASCII)
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class BackupError(Exception):
    pass


def valid_id(value: str) -> str:
    if not ID_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError("ID debe cumplir [A-Za-z0-9][A-Za-z0-9_-]{0,63}")
    return value


def byte_limit(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value, re.ASCII):
        raise argparse.ArgumentTypeError("--max-bytes debe ser un entero no negativo")
    try:
        return int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--max-bytes demasiado largo") from exc


@contextlib.contextmanager
def directory(path: str, *, create: bool = False) -> Iterator[int]:
    """Open every component independently, including before any '..'."""
    if not path or "\x00" in path:
        raise BackupError("ruta de directorio inválida")
    fd = os.open("/" if os.path.isabs(path) else ".", DIR_FLAGS)
    try:
        for part in path.split("/"):
            if not part or part == ".":
                continue
            try:
                child = os.open(part, DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                if not create or part == "..":
                    raise
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


@contextlib.contextmanager
def relative_directory(root: int, parts: tuple[str, ...]) -> Iterator[int]:
    fd = os.dup(root)
    try:
        for part in parts:
            child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


@contextlib.contextmanager
def regular_file(root: int, parts: tuple[str, ...]) -> Iterator[BinaryIO]:
    with relative_directory(root, parts[:-1]) as parent:
        fd = os.open(parts[-1], READ_FLAGS, dir_fd=parent)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise BackupError("se rechaza un archivo especial")
        stream = os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise
    with stream:
        yield stream


def identity(fd: int) -> tuple[int, int]:
    info = os.fstat(fd)
    return info.st_dev, info.st_ino


def ancestor(first: int, second: int) -> bool:
    wanted = identity(first)
    fd = os.dup(second)
    try:
        while True:
            here = identity(fd)
            if here == wanted:
                return True
            parent = os.open("..", DIR_FLAGS, dir_fd=fd)
            if identity(parent) == here:
                os.close(parent)
                return False
            os.close(fd)
            fd = parent
    finally:
        os.close(fd)


def tree(root: int) -> tuple[list[str], dict[str, os.stat_result]]:
    """Reject links/specials everywhere, without opening a FIFO or following links."""
    dirs = [""]
    files: dict[str, os.stat_result] = {}
    pending: list[tuple[str, ...]] = [()]
    while pending:
        parts = pending.pop()
        with relative_directory(root, parts) as current:
            with os.scandir(current) as entries:
                for entry in entries:
                    info = entry.stat(follow_symlinks=False)
                    components = parts + (entry.name,)
                    path = "/".join(components)
                    if stat.S_ISDIR(info.st_mode):
                        dirs.append(path)
                        pending.append(components)
                    elif stat.S_ISREG(info.st_mode):
                        files[path] = info
                    else:
                        raise BackupError(f"symlink o archivo especial rechazado: {path!r}")
    return sorted(dirs), dict(sorted(files.items()))


@contextlib.contextmanager
def repository(path: str, *, create: bool = False) -> Iterator[int]:
    with directory(path, create=create) as root:
        # The lock is kernel state, not persistent metadata. All our commands lock.
        fcntl.flock(root, fcntl.LOCK_EX)
        try:
            tree(root)
            yield root
        finally:
            fcntl.flock(root, fcntl.LOCK_UN)


def clean_stages(root: int) -> None:
    changed = False
    for name in os.listdir(root):
        if STAGE_PATTERN.fullmatch(name):
            info = os.stat(name, dir_fd=root, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise BackupError("temporal de repositorio inválido")
            os.unlink(name, dir_fd=root)
            changed = True
    if changed:
        os.fsync(root)


def repo_bytes(root: int) -> int:
    return sum(info.st_size for info in tree(root)[1].values())


def canonical(manifest: dict) -> bytes:
    return json.dumps(manifest, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":")).encode("ascii")


def read_exact(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise BackupError("snapshot truncado")
    return data


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackupError("claves duplicadas en metadata")
        result[key] = value
    return result


def path_valid(value: object, *, root: bool = False) -> bool:
    if not isinstance(value, str):
        return False
    if value == "":
        return root
    return "\x00" not in value and all(part not in ("", ".", "..")
                                      for part in value.split("/"))


@dataclass
class Snapshot:
    manifest: dict
    prefix: bytes
    size: int


def inspect_snapshot(stream: BinaryIO, expected_id: str) -> Snapshot:
    info = os.fstat(stream.fileno())
    size = info.st_size
    if not stat.S_ISREG(info.st_mode) or size < HEADER.size + DIGEST_SIZE:
        raise BackupError("snapshot inválido o truncado")
    stream.seek(0)
    remaining = size - DIGEST_SIZE
    digest = hashlib.sha256()
    while remaining:
        block = read_exact(stream, min(CHUNK, remaining))
        digest.update(block)
        remaining -= len(block)
    if not hmac.compare_digest(digest.digest(), read_exact(stream, DIGEST_SIZE)):
        raise BackupError("checksum del snapshot incorrecto")
    if stream.read(1):
        raise BackupError("snapshot cambió durante la lectura")
    stream.seek(0)
    header = read_exact(stream, HEADER.size)
    magic, length = HEADER.unpack(header)
    if magic != MAGIC or length > size - HEADER.size - DIGEST_SIZE:
        raise BackupError("cabecera del snapshot inválida")
    raw = read_exact(stream, length)
    try:
        manifest = json.loads(raw.decode("ascii"), object_pairs_hook=unique_object)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise BackupError("metadata del snapshot inválida") from exc
    if (not isinstance(manifest, dict)
            or set(manifest) != {"format", "id", "dirs", "files"}
            or type(manifest["format"]) is not int or manifest["format"] != 2
            or manifest["id"] != expected_id
            or not ID_PATTERN.fullmatch(expected_id)):
        raise BackupError("identidad o formato de snapshot inválido")
    dirs, files = manifest["dirs"], manifest["files"]
    if (not isinstance(dirs, list) or not dirs
            or not all(path_valid(path, root=True) for path in dirs)
            or dirs != sorted(set(dirs)) or dirs[0] != ""
            or not isinstance(files, list)):
        raise BackupError("directorios del snapshot inválidos")
    dir_set = set(dirs)
    for path in dirs[1:]:
        if path.rpartition("/")[0] not in dir_set:
            raise BackupError("directorio padre ausente")
    paths = []
    payload_size = 0
    for item in files:
        if (not isinstance(item, dict) or set(item) != {"path", "size"}
                or not path_valid(item["path"])
                or type(item["size"]) is not int or item["size"] < 0):
            raise BackupError("archivo del snapshot inválido")
        path = item["path"]
        if path in dir_set or path.rpartition("/")[0] not in dir_set:
            raise BackupError("ruta de archivo inconsistente")
        paths.append(path)
        payload_size += item["size"]
    if paths != sorted(set(paths)):
        raise BackupError("archivos duplicados o desordenados")
    if (payload_size != size - HEADER.size - length - DIGEST_SIZE
            or canonical(manifest) != raw):
        raise BackupError("longitud o representación de metadata inválida")
    return Snapshot(manifest, header + raw, size)


def create(args: argparse.Namespace) -> dict:
    with directory(args.source) as source:
        # Check existing ancestors before creating a repository inside the source.
        # Missing components are harmless to inspect, but must not be created there.
        absolute_repo = args.repo if os.path.isabs(args.repo) else os.path.join(os.getcwd(), args.repo)
        components = absolute_repo.split("/")
        probe = os.open("/", DIR_FLAGS)
        try:
            if ancestor(source, probe):
                raise BackupError("fuente y repositorio solapados")
            for component in components:
                if not component or component == ".":
                    continue
                try:
                    child = os.open(component, DIR_FLAGS, dir_fd=probe)
                except FileNotFoundError:
                    break
                os.close(probe)
                probe = child
            if ancestor(source, probe):
                raise BackupError("fuente y repositorio solapados")
        finally:
            os.close(probe)
        with repository(args.repo, create=True) as root:
            if ancestor(source, root) or ancestor(root, source):
                raise BackupError("fuente y repositorio solapados")
            clean_stages(root)
            target = args.id + ".bkp"
            if target in os.listdir(root):
                raise BackupError("el ID ya existe")
            existing = repo_bytes(root)
            if args.max_bytes is not None and existing > args.max_bytes:
                raise BackupError("los bytes existentes superan --max-bytes")
            dirs, files = tree(source)
            manifest = {"format": 2, "id": args.id, "dirs": dirs,
                        "files": [{"path": path, "size": info.st_size}
                                  for path, info in files.items()]}
            raw = canonical(manifest)
            prefix = HEADER.pack(MAGIC, len(raw)) + raw
            needed = len(prefix) + sum(info.st_size for info in files.values()) + DIGEST_SIZE
            if args.max_bytes is not None and existing + needed > args.max_bytes:
                raise BackupError("el snapshot y su metadata no caben en --max-bytes")
            stage = ".backup-stage-" + secrets.token_hex(16) + ".tmp"
            fd = os.open(stage, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=root)
            try:
                with os.fdopen(fd, "w+b") as output:
                    digest = hashlib.sha256()

                    def write(block: bytes) -> None:
                        output.write(block)
                        digest.update(block)

                    write(prefix)
                    for path, original in files.items():
                        with regular_file(source, tuple(path.split("/"))) as input_file:
                            current = os.fstat(input_file.fileno())
                            if ((current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)
                                    != (original.st_dev, original.st_ino, original.st_size, original.st_mtime_ns)):
                                raise BackupError("fuente cambió durante create")
                            remaining = original.st_size
                            while remaining:
                                block = read_exact(input_file, min(CHUNK, remaining))
                                write(block)
                                remaining -= len(block)
                            if input_file.read(1) or os.fstat(input_file.fileno()).st_mtime_ns != original.st_mtime_ns:
                                raise BackupError("fuente cambió durante create")
                    output.write(digest.digest())
                    output.flush()
                    os.fsync(output.fileno())
                    inspect_snapshot(output, args.id)
                if args.max_bytes is not None and repo_bytes(root) > args.max_bytes:
                    raise BackupError("el repositorio supera --max-bytes")
                # link() publishes the complete regular file without overwriting an ID.
                os.link(stage, target, src_dir_fd=root, dst_dir_fd=root, follow_symlinks=False)
                os.unlink(stage, dir_fd=root)
                os.fsync(root)
            finally:
                try:
                    os.unlink(stage, dir_fd=root)
                    os.fsync(root)
                except FileNotFoundError:
                    pass
    return {"id": args.id}


def verify(args: argparse.Namespace) -> dict:
    with repository(args.repo) as root:
        with regular_file(root, (args.id + ".bkp",)) as stream:
            inspect_snapshot(stream, args.id)
    return {"id": args.id, "valid": True}


def list_snapshots(args: argparse.Namespace) -> dict:
    snapshots = []
    try:
        with repository(args.repo) as root:
            for name in sorted(os.listdir(root)):
                match = SNAPSHOT_PATTERN.fullmatch(name)
                if match:
                    with regular_file(root, (name,)) as stream:
                        inspect_snapshot(stream, match[1])
                    snapshots.append(match[1])
    except FileNotFoundError:
        # Only a missing repository denotes an empty new repository. A missing
        # snapshot during scanning must not be mistaken for an empty repository.
        try:
            with directory(args.repo):
                pass
        except FileNotFoundError:
            return {"snapshots": []}
        raise BackupError("el repositorio cambió durante list")
    return {"snapshots": sorted(snapshots)}


def remove_tree(parent: int, name: str) -> None:
    """Remove our own restore staging directory; never follow a link."""
    root = os.open(name, DIR_FLAGS, dir_fd=parent)
    try:
        dirs, files = tree(root)
        for path in files:
            parts = tuple(path.split("/"))
            with relative_directory(root, parts[:-1]) as current:
                os.unlink(parts[-1], dir_fd=current)
        for path in sorted(dirs[1:], key=lambda path: path.count("/"), reverse=True):
            parts = tuple(path.split("/"))
            with relative_directory(root, parts[:-1]) as current:
                os.rmdir(parts[-1], dir_fd=current)
    finally:
        os.close(root)
    os.rmdir(name, dir_fd=parent)


def check_destination(parent: int, name: str) -> None:
    try:
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(info.st_mode):
        raise BackupError("el destino no es un directorio real")
    with relative_directory(parent, (name,)) as dest:
        if os.listdir(dest):
            raise BackupError("el destino preexistente no está vacío")


def restore(args: argparse.Namespace) -> dict:
    with repository(args.repo) as root:
        with regular_file(root, (args.id + ".bkp",)) as stream:
            snapshot = inspect_snapshot(stream, args.id)
            # Preserve the original components until directory() has checked them.
            dest = args.dest.rstrip("/")
            parent_path, name = os.path.split(dest)
            if not name or name in (".", "..") or "\x00" in name:
                raise BackupError("ruta de destino inválida")
            with directory(parent_path or ".", create=True) as parent:
                check_destination(parent, name)
                stage = ".backup-restore-" + secrets.token_hex(16)
                os.mkdir(stage, mode=0o700, dir_fd=parent)
                published = False
                try:
                    with relative_directory(parent, (stage,)) as output:
                        for path in snapshot.manifest["dirs"][1:]:
                            parts = tuple(path.split("/"))
                            with relative_directory(output, parts[:-1]) as current:
                                os.mkdir(parts[-1], mode=0o700, dir_fd=current)
                        stream.seek(0)
                        prefix = read_exact(stream, len(snapshot.prefix))
                        if prefix != snapshot.prefix:
                            raise BackupError("metadata cambió durante restore")
                        digest = hashlib.sha256(prefix)
                        for item in snapshot.manifest["files"]:
                            parts = tuple(item["path"].split("/"))
                            with relative_directory(output, parts[:-1]) as current:
                                fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                             0o600, dir_fd=current)
                            with os.fdopen(fd, "wb") as restored:
                                remaining = item["size"]
                                while remaining:
                                    block = read_exact(stream, min(CHUNK, remaining))
                                    digest.update(block)
                                    restored.write(block)
                                    remaining -= len(block)
                                restored.flush()
                                os.fsync(restored.fileno())
                        if (not hmac.compare_digest(digest.digest(), read_exact(stream, DIGEST_SIZE))
                                or stream.read(1) or os.fstat(stream.fileno()).st_size != snapshot.size):
                            raise BackupError("snapshot cambió durante restore")
                        for path in reversed(snapshot.manifest["dirs"]):
                            parts = tuple(path.split("/")) if path else ()
                            with relative_directory(output, parts) as current:
                                os.fsync(current)
                    check_destination(parent, name)
                    os.rename(stage, name, src_dir_fd=parent, dst_dir_fd=parent)
                    published = True
                    os.fsync(parent)
                finally:
                    if not published:
                        remove_tree(parent, stage)
    return {"id": args.id}


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup verificable, autocontenido y atómico")
    commands = parser.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser("create")
    create_parser.add_argument("--source", required=True)
    create_parser.add_argument("--repo", required=True)
    create_parser.add_argument("--id", required=True, type=valid_id)
    create_parser.add_argument("--max-bytes", type=byte_limit)
    for command in ("verify", "restore"):
        child = commands.add_parser(command)
        child.add_argument("--repo", required=True)
        child.add_argument("--id", required=True, type=valid_id)
        if command == "restore":
            child.add_argument("--dest", required=True)
    commands.add_parser("list").add_argument("--repo", required=True)
    args = parser.parse_args()
    actions = {"create": create, "verify": verify, "restore": restore, "list": list_snapshots}
    try:
        result = actions[args.command](args)
    except (BackupError, OSError, ValueError, OverflowError, RecursionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("error: operación interrumpida", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
