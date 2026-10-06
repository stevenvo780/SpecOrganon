#!/usr/bin/env python3
"""Self-contained, checksummed snapshots; Python 3.12 standard library only."""

import argparse
import contextlib
import fcntl
import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import struct
import sys
import uuid


MAGIC = b"PYBACKUP\x00V1\r\n\x1a\n"
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", re.ASCII)
PENDING_PATTERN = re.compile(r"\.pending-[0-9a-f]{32}", re.ASCII)
SUFFIX = ".snapshot"
CHUNK = 1024 * 1024
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class BackupError(Exception):
    pass


def check_id(value):
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise BackupError("ID inválido")
    return value


def encode_json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


@contextlib.contextmanager
def directory(path, create=False):
    """Walk components with O_NOFOLLOW, including all ancestor directories."""
    absolute = path if os.path.isabs(path) else os.path.join(os.getcwd(), path)
    fd = os.open("/", DIR_FLAGS)
    try:
        for part in absolute.split("/"):
            if not part or part == ".":
                continue
            try:
                child = os.open(part, DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def checked_path(path, allow_missing=False):
    if not path or "\x00" in path:
        raise BackupError("Ruta de directorio inválida")
    # Check the original spelling before normalization: link/.. must reject.
    for spelling in (path, os.path.abspath(path)):
        try:
            with directory(spelling):
                pass
        except FileNotFoundError:
            if not allow_missing:
                raise
    return os.path.abspath(path)


def overlap(left, right):
    return os.path.commonpath((left, right)) in (left, right)


@contextlib.contextmanager
def relative_directory(root_fd, parts):
    fd = os.dup(root_fd)
    try:
        for part in parts:
            child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


@contextlib.contextmanager
def regular_file(parent_fd, name):
    fd = os.open(name, FILE_FLAGS, dir_fd=parent_fd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise BackupError("Se esperaba un archivo regular")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            yield stream
    finally:
        os.close(fd)


def walk_tree(root_fd):
    """Iterative traversal; no symlinks, no special files, bounded open fds."""
    pending = [()]
    while pending:
        parent = pending.pop()
        with relative_directory(root_fd, parent) as fd:
            with os.scandir(fd) as scan:
                items = sorted(scan, key=lambda item: item.name)
            for item in items:
                info = item.stat(follow_symlinks=False)
                path = parent + (item.name,)
                if stat.S_ISDIR(info.st_mode):
                    pending.append(path)
                    yield path, "dir", info
                elif stat.S_ISREG(info.st_mode):
                    yield path, "file", info
                else:
                    raise BackupError("Symlink o archivo especial: " + repr("/".join(path)))


def repository_size(repo_fd):
    return sum(info.st_size for _, kind, info in walk_tree(repo_fd)
               if kind == "file")


def clean_pending(repo_fd):
    # Validate everything before deleting anything. The prefix is reserved.
    repository_size(repo_fd)
    with os.scandir(repo_fd) as scan:
        names = [item.name for item in scan if PENDING_PATTERN.fullmatch(item.name)]
    for name in names:
        info = os.stat(name, dir_fd=repo_fd, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            raise BackupError("Temporal de repositorio inválido")
        os.unlink(name, dir_fd=repo_fd)
    if names:
        os.fsync(repo_fd)


def source_manifest(source_fd, snapshot_id):
    records = sorted(walk_tree(source_fd), key=lambda record: record[0])
    entries = []
    for path, kind, info in records:
        entry = {"path": list(path), "kind": kind}
        if kind == "file":
            entry["size"] = info.st_size
        entries.append(entry)
    return {"version": 1, "id": snapshot_id, "entries": entries}


def exists_at(fd, name):
    try:
        return os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def create(args):
    snapshot_id = check_id(args.id)
    source = checked_path(args.source)
    repo = checked_path(args.repo, allow_missing=True)
    if overlap(source, repo):
        raise BackupError("Fuente y repositorio solapados")
    with directory(source) as source_fd, directory(repo, create=True) as repo_fd:
        fcntl.flock(repo_fd, fcntl.LOCK_EX)
        clean_pending(repo_fd)
        name = snapshot_id + SUFFIX
        if exists_at(repo_fd, name) is not None:
            raise BackupError("El ID ya existe")
        baseline = repository_size(repo_fd)
        if args.max_bytes is not None and baseline > args.max_bytes:
            raise BackupError("El repositorio existente excede --max-bytes")
        manifest = source_manifest(source_fd, snapshot_id)
        metadata = encode_json(manifest)
        header = MAGIC + struct.pack(">Q", len(metadata))
        total = len(header) + len(metadata) + 32 + sum(
            entry.get("size", 0) for entry in manifest["entries"])
        if args.max_bytes is not None and baseline + total > args.max_bytes:
            raise BackupError("El snapshot no cabe en --max-bytes (necesita "
                              + str(baseline + total) + " bytes totales)")
        temporary = ".pending-" + uuid.uuid4().hex
        published = False
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=repo_fd)
            with os.fdopen(fd, "wb") as output:
                digest = hashlib.sha256()

                def write(data):
                    output.write(data)
                    digest.update(data)

                write(header)
                write(metadata)
                for entry in manifest["entries"]:
                    if entry["kind"] != "file":
                        continue
                    parts = entry["path"]
                    with relative_directory(source_fd, parts[:-1]) as parent_fd:
                        with regular_file(parent_fd, parts[-1]) as input_file:
                            if os.fstat(input_file.fileno()).st_size != entry["size"]:
                                raise BackupError("La fuente cambió durante create")
                            remaining = entry["size"]
                            while remaining:
                                data = input_file.read(min(CHUNK, remaining))
                                if not data:
                                    raise BackupError("La fuente se truncó durante create")
                                write(data)
                                remaining -= len(data)
                            if input_file.read(1):
                                raise BackupError("La fuente creció durante create")
                output.write(digest.digest())
                output.flush()
                if os.fstat(output.fileno()).st_size != total:
                    raise BackupError("Tamaño de snapshot inesperado")
                os.fsync(output.fileno())
            # Includes unrelated files, nested regular files and all metadata.
            actual = repository_size(repo_fd)
            if args.max_bytes is not None and actual > args.max_bytes:
                raise BackupError("El repositorio excedería --max-bytes")
            if exists_at(repo_fd, name) is not None:
                raise BackupError("El ID ya existe")
            os.rename(temporary, name, src_dir_fd=repo_fd, dst_dir_fd=repo_fd)
            published = True
            os.fsync(repo_fd)
        finally:
            if not published and exists_at(repo_fd, temporary) is not None:
                os.unlink(temporary, dir_fd=repo_fd)
                os.fsync(repo_fd)
    return {"id": snapshot_id}


def read_exact(stream, count):
    data = stream.read(count)
    if len(data) != count:
        raise BackupError("Snapshot truncado")
    return data


def invalid_constant(value):
    raise BackupError("Constante JSON inválida: " + value)


def validate_manifest(raw, snapshot_id):
    try:
        manifest = json.loads(raw.decode("ascii"), parse_constant=invalid_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise BackupError("Metadata inválida") from exc
    if not isinstance(manifest, dict) or set(manifest) != {"version", "id", "entries"}:
        raise BackupError("Estructura de metadata inválida")
    if type(manifest["version"]) is not int or manifest["version"] != 1:
        raise BackupError("Versión de snapshot inválida")
    if manifest["id"] != snapshot_id or not isinstance(manifest["entries"], list):
        raise BackupError("ID o entradas de metadata inválidos")
    if encode_json(manifest) != raw:
        raise BackupError("Metadata no canónica o corrupta")
    seen = {(): "dir"}
    previous = ()
    for entry in manifest["entries"]:
        if not isinstance(entry, dict):
            raise BackupError("Entrada de metadata inválida")
        kind = entry.get("kind")
        if kind not in ("file", "dir"):
            raise BackupError("Tipo de entrada inválido")
        fields = {"path", "kind", "size"} if kind == "file" else {"path", "kind"}
        if set(entry) != fields:
            raise BackupError("Campos de entrada inválidos")
        parts = entry["path"]
        if not isinstance(parts, list) or not parts or any(
                not isinstance(part, str) or part in ("", ".", "..") or
                "/" in part or "\x00" in part for part in parts):
            raise BackupError("Ruta interna insegura")
        path = tuple(parts)
        if path <= previous or seen.get(path[:-1]) != "dir":
            raise BackupError("Árbol de metadata inválido")
        if kind == "file" and (type(entry["size"]) is not int or entry["size"] < 0):
            raise BackupError("Tamaño de archivo inválido")
        previous = path
        seen[path] = kind
    return manifest


def check_snapshot(repo_fd, snapshot_id, destination_fd=None):
    """Validate structure and every byte, optionally extract into a private tree."""
    with regular_file(repo_fd, snapshot_id + SUFFIX) as input_file:
        size = os.fstat(input_file.fileno()).st_size
        digest = hashlib.sha256()

        def read(count):
            data = read_exact(input_file, count)
            digest.update(data)
            return data

        if read(len(MAGIC)) != MAGIC:
            raise BackupError("Cabecera de snapshot corrupta")
        metadata_size = struct.unpack(">Q", read(8))[0]
        if metadata_size > size - len(MAGIC) - 8 - 32:
            raise BackupError("Longitud de metadata inválida")
        manifest = validate_manifest(read(metadata_size), snapshot_id)
        expected = len(MAGIC) + 8 + metadata_size + 32 + sum(
            entry.get("size", 0) for entry in manifest["entries"])
        if expected != size:
            raise BackupError("Longitud de snapshot inválida")
        for entry in manifest["entries"]:
            parts = entry["path"]
            if entry["kind"] == "dir":
                if destination_fd is not None:
                    with relative_directory(destination_fd, parts[:-1]) as parent_fd:
                        os.mkdir(parts[-1], 0o700, dir_fd=parent_fd)
                continue
            with contextlib.ExitStack() as stack:
                output = None
                if destination_fd is not None:
                    parent_fd = stack.enter_context(
                        relative_directory(destination_fd, parts[:-1]))
                    fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                 os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent_fd)
                    output = stack.enter_context(os.fdopen(fd, "wb"))
                remaining = entry["size"]
                while remaining:
                    data = read(min(CHUNK, remaining))
                    if output is not None:
                        output.write(data)
                    remaining -= len(data)
                if output is not None:
                    output.flush()
                    os.fsync(output.fileno())
        checksum = read_exact(input_file, 32)
        if not hmac.compare_digest(digest.digest(), checksum) or input_file.read(1):
            raise BackupError("Checksum de snapshot incorrecto")


def verify(args):
    snapshot_id = check_id(args.id)
    repo = checked_path(args.repo)
    with directory(repo) as repo_fd:
        fcntl.flock(repo_fd, fcntl.LOCK_SH)
        repository_size(repo_fd)
        check_snapshot(repo_fd, snapshot_id)
    return {"id": snapshot_id, "valid": True}


def list_snapshots(args):
    repo = checked_path(args.repo, allow_missing=True)
    with contextlib.ExitStack() as stack:
        try:
            repo_fd = stack.enter_context(directory(repo))
        except FileNotFoundError:
            return {"snapshots": []}
        fcntl.flock(repo_fd, fcntl.LOCK_SH)
        repository_size(repo_fd)
        with os.scandir(repo_fd) as scan:
            names = [item.name for item in scan]
        snapshots = []
        for name in sorted(names):
            if not name.endswith(SUFFIX):
                continue
            snapshot_id = check_id(name[:-len(SUFFIX)])
            check_snapshot(repo_fd, snapshot_id)
            snapshots.append(snapshot_id)
        return {"snapshots": sorted(snapshots)}


def ensure_empty(fd):
    with os.scandir(fd) as scan:
        if next(scan, None) is not None:
            raise BackupError("El destino preexistente no está vacío")


def restore(args):
    snapshot_id = check_id(args.id)
    repo = checked_path(args.repo)
    dest = checked_path(args.dest, allow_missing=True)
    parent, base = os.path.split(dest)
    if not base:
        raise BackupError("El destino no puede ser la raíz")
    with directory(repo) as repo_fd:
        fcntl.flock(repo_fd, fcntl.LOCK_EX)
        repository_size(repo_fd)
        # Check protected destinations before creating anything.
        original = None
        try:
            with directory(dest) as dest_fd:
                ensure_empty(dest_fd)
                original = os.fstat(dest_fd)
        except FileNotFoundError:
            pass
        with directory(parent, create=True) as parent_fd:
            stage = ".restore-" + uuid.uuid4().hex
            os.mkdir(stage, 0o700, dir_fd=parent_fd)
            published = False
            try:
                with relative_directory(parent_fd, (stage,)) as stage_fd:
                    check_snapshot(repo_fd, snapshot_id, stage_fd)
                    # Persist nested directory entries before publication.
                    for parts, kind, _ in walk_tree(stage_fd):
                        if kind == "dir":
                            with relative_directory(stage_fd, parts) as fd:
                                os.fsync(fd)
                    os.fsync(stage_fd)
                current = exists_at(parent_fd, base)
                if original is None:
                    if current is not None:
                        raise BackupError("El destino apareció durante restore")
                else:
                    if current is None or not stat.S_ISDIR(current.st_mode) or (
                            current.st_dev, current.st_ino) != (original.st_dev, original.st_ino):
                        raise BackupError("El destino cambió durante restore")
                    with relative_directory(parent_fd, (base,)) as dest_fd:
                        ensure_empty(dest_fd)
                os.rename(stage, base, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
                published = True
                os.fsync(parent_fd)
            finally:
                if not published:
                    shutil.rmtree(stage, dir_fd=parent_fd)
    return {"id": snapshot_id}


def byte_limit(value):
    if not re.fullmatch(r"[0-9]+", value, re.ASCII):
        raise argparse.ArgumentTypeError("N debe ser un entero no negativo")
    try:
        return int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("N es demasiado grande") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, function in (("create", create), ("verify", verify),
                           ("restore", restore), ("list", list_snapshots)):
        command = commands.add_parser(name)
        command.add_argument("--repo", required=True)
        if name != "list":
            command.add_argument("--id", required=True)
        if name == "create":
            command.add_argument("--source", required=True)
            command.add_argument("--max-bytes", type=byte_limit)
        if name == "restore":
            command.add_argument("--dest", required=True)
        command.set_defaults(function=function)
    args = parser.parse_args()
    try:
        result = args.function(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
