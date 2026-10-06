#!/usr/bin/env python3
"""Standalone, checksummed snapshots. Python 3.12, standard library only."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import sys
import tempfile


MAGIC = b"PYBACKUP\x00\x01\n"
FOOTER_SIZE = 8 + 32
CHUNK = 1024 * 1024
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z", re.ASCII)
HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class BackupError(Exception):
    """Invalid input, repository, or snapshot."""


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise BackupError(f"Argumentos inválidos: {message}")


def validate_id(identifier: str) -> None:
    if not ID_PATTERN.fullmatch(identifier):
        raise BackupError("ID inválido")


def plain_path(value: str) -> Path:
    """Check components before resolving '..'; never resolve a symlink."""
    if not value or "\x00" in value:
        raise BackupError("Ruta vacía o inválida")
    raw = Path(value)
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    current = Path(raw.anchor)
    for component in raw.parts[1:]:
        if component == "..":
            # A nonexistent component followed by '..' is not traversable.
            if not current.is_dir():
                raise BackupError(f"Directorio inexistente: {current}")
            current = current.parent
            continue
        current /= component
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise BackupError(f"Symlink rechazado: {current}")
        if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise BackupError(f"Archivo especial rechazado: {current}")
    return current


def directory(path: Path) -> None:
    mode = path.lstat().st_mode
    if not stat.S_ISDIR(mode):
        raise BackupError(f"No es un directorio: {path}")


def scan_tree(root: Path):
    """Yield directories and regular files, including empty directories."""
    directory(root)
    pending = [(root, "")]
    while pending:
        parent, relative = pending.pop()
        with os.scandir(parent) as scan:
            children = sorted(scan, key=lambda entry: entry.name)
        subdirs = []
        for entry in children:
            name = f"{relative}/{entry.name}" if relative else entry.name
            mode = entry.stat(follow_symlinks=False).st_mode
            path = Path(entry.path)
            if stat.S_ISDIR(mode):
                yield name, "dir", path
                subdirs.append((path, name))
            elif stat.S_ISREG(mode):
                yield name, "file", path
            else:
                raise BackupError(f"Symlink o archivo especial rechazado: {path}")
        pending.extend(reversed(subdirs))


def open_regular(path: Path):
    # O_NONBLOCK avoids hanging if a regular file is replaced by a FIFO.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise BackupError(f"No es un archivo regular: {path}")
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise BackupError(f"No es un archivo regular: {path}")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def overlaps(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def prepare_repo(path: Path, *, create: bool = False) -> Path:
    if not path.exists():
        if create:
            path.mkdir(parents=True, mode=0o700, exist_ok=True)
        else:
            return path / "snapshots"
    # Scan all managed paths, including remnants of interrupted operations.
    for _ in scan_tree(path):
        pass
    snapshots = path / "snapshots"
    if snapshots.exists():
        directory(snapshots)
    elif create:
        snapshots.mkdir(mode=0o700, exist_ok=True)
    return snapshots


@contextmanager
def repository_lock(repo: Path, *, create: bool = False):
    """Serialize CLI operations without introducing persistent lock metadata."""
    if create:
        repo.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not repo.exists():
        yield
        return
    directory(repo)
    fd = os.open(repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        # flock is released by the kernel even after SIGKILL. The directory is
        # only a lock handle; every byte of snapshot metadata is in regular files.
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def repository_bytes(repo: Path) -> int:
    """Count every regular pathname, including foreign files and metadata."""
    return sum(path.lstat().st_size for _, kind, path in scan_tree(repo) if kind == "file")


def cleanup_pending(repo: Path) -> None:
    # Called only under the repository lock, after rejecting unsafe tree entries.
    # A crash between link and unlink leaves two names for the same inode;
    # removing the pending name preserves the published snapshot.
    removed = False
    for path in repo.glob(".pending-*"):
        if stat.S_ISREG(path.lstat().st_mode):
            path.unlink()
            removed = True
    if removed:
        sync_directory(repo)


def byte_limit(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value, re.ASCII):
        raise BackupError("--max-bytes debe ser un entero decimal no negativo")
    return int(value)


def sync_directory(path: Path) -> None:
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def create(source: Path, repo: Path, identifier: str, max_bytes: int | None = None) -> dict:
    directory(source)
    if overlaps(source, repo):
        raise BackupError("La fuente y el repositorio se solapan")
    snapshots = prepare_repo(repo, create=True)
    cleanup_pending(repo)
    target = snapshots / f"{identifier}.snap"
    if os.path.lexists(target):
        raise BackupError("El ID ya existe")
    existing_bytes = repository_bytes(repo)
    if max_bytes is not None and existing_bytes > max_bytes:
        raise BackupError("El repositorio existente supera --max-bytes")
    fd, temporary_name = tempfile.mkstemp(prefix=".pending-", dir=repo)
    temporary = Path(temporary_name)
    try:
        entries = []
        offset = 0
        checksum = hashlib.sha256()
        with os.fdopen(fd, "wb") as output:
            written = 0

            def emit(data: bytes) -> None:
                nonlocal written
                if max_bytes is not None and existing_bytes + written + len(data) > max_bytes:
                    raise BackupError("El snapshot y la metadata no caben en --max-bytes")
                output.write(data)
                written += len(data)

            def write(data: bytes) -> None:
                emit(data)
                checksum.update(data)

            write(MAGIC)
            for name, kind, path in scan_tree(source):
                record = {"path": name, "type": kind}
                if kind == "file":
                    file_hash = hashlib.sha256()
                    size = 0
                    with open_regular(path) as input_file:
                        while data := input_file.read(CHUNK):
                            write(data)
                            file_hash.update(data)
                            size += len(data)
                    record.update(size=size, offset=offset, sha256=file_hash.hexdigest())
                    offset += size
                entries.append(record)
            manifest = json.dumps(
                {"version": 1, "entries": entries},
                ensure_ascii=True, separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
            write(manifest)
            write(struct.pack(">Q", len(manifest)))
            emit(checksum.digest())
            output.flush()
            os.fsync(output.fileno())
        # link() atomically publishes a complete file and cannot replace an ID.
        os.link(temporary, target, follow_symlinks=False)
        sync_directory(snapshots)
        temporary.unlink()
        sync_directory(repo)
    finally:
        temporary.unlink(missing_ok=True)
    return {"id": identifier}


def unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackupError("Clave duplicada en los metadatos")
        result[key] = value
    return result


def invalid_constant(value: str):
    raise BackupError(f"Constante JSON inválida: {value}")


def validate_manifest(raw: bytes, payload_size: int) -> list[dict]:
    try:
        manifest = json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise BackupError("Metadatos ilegibles") from error
    if (not isinstance(manifest, dict) or set(manifest) != {"version", "entries"}
            or type(manifest["version"]) is not int or manifest["version"] != 1
            or not isinstance(manifest["entries"], list)):
        raise BackupError("Formato de metadatos inválido")
    entries = manifest["entries"]
    paths = {}
    offset = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise BackupError("Entrada inválida")
        name, kind = entry.get("path"), entry.get("type")
        if (not isinstance(name, str) or not name or "\x00" in name
                or any(part in ("", ".", "..") for part in name.split("/"))
                or Path(name).is_absolute() or name in paths):
            raise BackupError("Ruta de snapshot inválida o duplicada")
        if kind == "dir":
            if set(entry) != {"path", "type"}:
                raise BackupError("Entrada de directorio inválida")
        elif kind == "file":
            if (set(entry) != {"path", "type", "offset", "size", "sha256"}
                    or type(entry["size"]) is not int or entry["size"] < 0
                    or type(entry["offset"]) is not int or entry["offset"] != offset
                    or not isinstance(entry["sha256"], str)
                    or not HASH_PATTERN.fullmatch(entry["sha256"])):
                raise BackupError("Entrada de archivo inválida")
            offset += entry["size"]
            if offset > payload_size:
                raise BackupError("Longitud de archivo inválida")
        else:
            raise BackupError("Tipo de entrada inválido")
        paths[name] = kind
    if offset != payload_size:
        raise BackupError("Hay datos ausentes o no declarados")
    for name in paths:
        parent = name.rpartition("/")[0]
        if parent and paths.get(parent) != "dir":
            raise BackupError("Directorio padre ausente o inválido")
    return entries


def read_exact(input_file, size: int) -> bytes:
    data = input_file.read(size)
    if len(data) != size:
        raise BackupError("Snapshot truncado")
    return data


def check_snapshot(input_file) -> list[dict]:
    before = os.fstat(input_file.fileno())
    size = before.st_size
    if size < len(MAGIC) + FOOTER_SIZE:
        raise BackupError("Snapshot truncado")
    input_file.seek(0)
    if read_exact(input_file, len(MAGIC)) != MAGIC:
        raise BackupError("Cabecera de snapshot inválida")
    input_file.seek(size - FOOTER_SIZE)
    length_bytes = read_exact(input_file, 8)
    manifest_size = struct.unpack(">Q", length_bytes)[0]
    expected_digest = read_exact(input_file, 32)
    manifest_start = size - FOOTER_SIZE - manifest_size
    if manifest_start < len(MAGIC):
        raise BackupError("Longitud de metadatos inválida")
    input_file.seek(manifest_start)
    raw = read_exact(input_file, manifest_size)
    entries = validate_manifest(raw, manifest_start - len(MAGIC))
    checksum = hashlib.sha256(MAGIC)
    input_file.seek(len(MAGIC))
    for entry in entries:
        if entry["type"] != "file":
            continue
        file_hash = hashlib.sha256()
        remaining = entry["size"]
        while remaining:
            data = read_exact(input_file, min(CHUNK, remaining))
            checksum.update(data)
            file_hash.update(data)
            remaining -= len(data)
        if not hmac.compare_digest(file_hash.hexdigest(), entry["sha256"]):
            raise BackupError(f"Contenido corrupto: {entry['path']}")
    checksum.update(raw)
    checksum.update(length_bytes)
    if not hmac.compare_digest(checksum.digest(), expected_digest):
        raise BackupError("Checksum del snapshot inválido")
    after = os.fstat(input_file.fileno())
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise BackupError("El snapshot cambió durante la comprobación")
    return entries


def snapshot_path(repo: Path, identifier: str) -> Path:
    snapshots = prepare_repo(repo)
    path = snapshots / f"{identifier}.snap"
    if not path.exists():
        raise BackupError("El ID no existe")
    return path


def verify(repo: Path, identifier: str) -> dict:
    with open_regular(snapshot_path(repo, identifier)) as input_file:
        check_snapshot(input_file)
    return {"id": identifier, "valid": True}


def empty_destination(dest: Path):
    """Return the existing directory's identity, or None if it does not exist."""
    try:
        info = dest.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(info.st_mode):
        raise BackupError("El destino no es un directorio normal")
    with os.scandir(dest) as entries:
        if next(entries, None) is not None:
            raise BackupError("El destino preexistente no está vacío")
    return info.st_dev, info.st_ino


def restore(repo: Path, identifier: str, dest: Path) -> dict:
    destination_identity = empty_destination(dest)
    with open_regular(snapshot_path(repo, identifier)) as input_file:
        entries = check_snapshot(input_file)
        # No destination or staging writes occur before full verification.
        dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = Path(tempfile.mkdtemp(prefix=".backup-restore-", dir=dest.parent))
        try:
            directories = [entry["path"] for entry in entries if entry["type"] == "dir"]
            for name in sorted(directories, key=lambda name: (name.count("/"), name)):
                (temporary / name).mkdir(mode=0o700)
            for entry in entries:
                if entry["type"] != "file":
                    continue
                input_file.seek(len(MAGIC) + entry["offset"])
                remaining = entry["size"]
                file_hash = hashlib.sha256()
                output_path = temporary / entry["path"]
                fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as output:
                    while remaining:
                        data = read_exact(input_file, min(CHUNK, remaining))
                        file_hash.update(data)
                        output.write(data)
                        remaining -= len(data)
                    output.flush()
                    os.fsync(output.fileno())
                if not hmac.compare_digest(file_hash.hexdigest(), entry["sha256"]):
                    raise BackupError("El contenido cambió durante la restauración")
            for name in sorted(directories, key=lambda name: name.count("/"), reverse=True):
                sync_directory(temporary / name)
            sync_directory(temporary)
            plain_path(str(dest))
            if empty_destination(dest) != destination_identity:
                raise BackupError("El destino cambió durante la restauración")
            os.replace(temporary, dest)
            sync_directory(dest.parent)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return {"id": identifier}


def list_snapshots(repo: Path) -> dict:
    snapshots = prepare_repo(repo)
    identifiers = []
    if snapshots.exists():
        for path in sorted(snapshots.iterdir()):
            if path.suffix != ".snap" or not ID_PATTERN.fullmatch(path.stem):
                continue
            with open_regular(path) as input_file:
                try:
                    check_snapshot(input_file)
                except BackupError:
                    # Corrupt or incomplete snapshots are not listed as complete.
                    continue
            identifiers.append(path.stem)
    return {"snapshots": sorted(identifiers)}


def main(argv: list[str] | None = None) -> int:
    parser = JsonArgumentParser(description="Backup verificable (V3)")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "verify", "restore", "list"):
        command = commands.add_parser(name)
        command.add_argument("--repo", required=True)
        if name != "list":
            command.add_argument("--id", required=True)
        if name == "create":
            command.add_argument("--source", required=True)
            command.add_argument("--max-bytes", type=byte_limit)
        if name == "restore":
            command.add_argument("--dest", required=True)
    try:
        args = parser.parse_args(argv)
        if args.command != "list":
            validate_id(args.id)
        repo = plain_path(args.repo)
        if args.command == "create":
            source = plain_path(args.source)
            directory(source)
            if overlaps(source, repo):
                raise BackupError("La fuente y el repositorio se solapan")
            with repository_lock(repo, create=True):
                result = create(source, repo, args.id, args.max_bytes)
        else:
            dest = plain_path(args.dest) if args.command == "restore" else None
            with repository_lock(repo):
                if args.command == "verify":
                    result = verify(repo, args.id)
                elif args.command == "restore":
                    result = restore(repo, args.id, dest)
                else:
                    result = list_snapshots(repo)
    except (BackupError, OSError, ValueError, OverflowError, RecursionError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
