#!/usr/bin/env python3
"""Independent, verified directory snapshots. Python 3.12, POSIX stdlib only."""

from __future__ import annotations

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
from typing import Iterator


ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z", re.ASCII)
HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
STAGE_PATTERN = re.compile(r"create-[A-Za-z0-9_-]+\Z", re.ASCII)
CHUNK_SIZE = 1024 * 1024


class BackupError(Exception):
    """An operation failed without a successful result."""


def validate_id(snapshot_id: str) -> None:
    if not ID_PATTERN.fullmatch(snapshot_id):
        raise BackupError("ID inválido: use 1–64 caracteres ASCII alfanuméricos, _ o -")


def directory_path(raw: str | Path, *, missing_ok: bool = False) -> Path:
    """Check every supplied component before normalizing '..'; never resolve links."""
    raw_string = os.fspath(raw)
    if not raw_string or "\0" in raw_string:
        raise BackupError("Ruta de directorio inválida")
    absolute = raw_string if os.path.isabs(raw_string) else os.path.join(os.getcwd(), raw_string)
    current = Path("/")
    missing = False
    for component in absolute.split("/"):
        if component in ("", "."):
            continue
        if component == "..":
            if missing:
                raise BackupError("Componente .. después de un directorio inexistente")
            current = current.parent
            continue
        current = current / component
        if missing:
            continue
        try:
            info = current.lstat()
        except FileNotFoundError:
            if not missing_ok:
                raise BackupError(f"Directorio inexistente: {current}") from None
            missing = True
            continue
        if stat.S_ISLNK(info.st_mode):
            raise BackupError(f"Symlink rechazado: {current}")
        if not stat.S_ISDIR(info.st_mode):
            raise BackupError(f"Se requiere un directorio: {current}")
    return current


def overlaps(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def kind(info: os.stat_result, path: Path) -> str:
    if stat.S_ISLNK(info.st_mode):
        raise BackupError(f"Symlink rechazado: {path}")
    if stat.S_ISDIR(info.st_mode):
        return "dir"
    if stat.S_ISREG(info.st_mode):
        return "file"
    raise BackupError(f"Archivo especial rechazado: {path}")


def inventory(root: Path) -> dict[str, str]:
    """Inventory regular files and directories, using lstat without following links."""
    directory_path(root)
    found: dict[str, str] = {}
    pending = [(root, "")]
    while pending:
        directory, prefix = pending.pop()
        with os.scandir(directory) as stream:
            children = sorted(stream, key=lambda item: item.name)
        for child in children:
            path = directory / child.name
            relative = prefix + child.name
            item_kind = kind(child.stat(follow_symlinks=False), path)
            found[relative] = item_kind
            if item_kind == "dir":
                pending.append((path, relative + "/"))
    return dict(sorted(found.items()))


def repository_bytes(repo: Path) -> int:
    """Logical bytes of every regular file, including metadata and staging.

    Call under the repository lock. Inventory rejects links/special files;
    lstat counts directory entries independently (including hardlinks).
    """
    total = 0
    for relative, item_kind in inventory(repo).items():
        if item_kind == "file":
            path = repo / relative
            info = path.lstat()
            if kind(info, path) != "file":
                raise BackupError(f"El archivo cambió de tipo: {path}")
            total += info.st_size
    return total


@contextmanager
def regular_reader(path: Path) -> Iterator[object]:
    # NONBLOCK also prevents waiting forever on a FIFO substituted before open.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise BackupError(f"Se requiere un archivo regular: {path}")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            yield stream
    finally:
        os.close(fd)


def read_regular(path: Path) -> bytes:
    with regular_reader(path) as stream:
        return stream.read()


def write_regular(path: Path, content: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with regular_reader(path) as stream:
        while chunk := stream.read(CHUNK_SIZE):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def copy_file(source: Path, target: Path, expected: dict | None = None) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with regular_reader(source) as incoming:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as outgoing:
            while chunk := incoming.read(CHUNK_SIZE):
                outgoing.write(chunk)
                size += len(chunk)
                digest.update(chunk)
            result_hash = digest.hexdigest()
            if expected is not None and (size != expected["size"] or result_hash != expected["sha256"]):
                raise BackupError(f"Datos corruptos durante la copia: {source}")
            outgoing.flush()
            os.fsync(outgoing.fileno())
    return size, result_hash


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def sync_tree(root: Path, entries: list[dict]) -> None:
    for entry in reversed(entries):
        if entry["type"] == "dir":
            sync_directory(root / entry["path"])
    sync_directory(root)


def validate_repository(repo: Path) -> None:
    tree = inventory(repo)
    allowed = {"snapshots": "dir", ".staging": "dir", ".lock": "file"}
    for name, item_kind in tree.items():
        if "/" not in name and allowed.get(name) != item_kind:
            raise BackupError(f"Entrada ajena al formato de repositorio: {name}")
        if name.startswith("snapshots/") and name.count("/") == 1:
            if item_kind != "dir" or not ID_PATTERN.fullmatch(name.split("/")[1]):
                raise BackupError(f"Entrada de snapshot inválida: {name}")
        if name.startswith(".staging/") and name.count("/") == 1:
            if item_kind != "dir" or not STAGE_PATTERN.fullmatch(name.split("/")[1]):
                raise BackupError(f"Temporal de repositorio inválido: {name}")


@contextmanager
def repository(raw: str | Path, *, create: bool = False) -> Iterator[Path | None]:
    repo = directory_path(raw, missing_ok=True)
    if not repo.exists():
        if not create:
            yield None
            return
        repo.mkdir(parents=True)
    validate_repository(repo)
    lock_fd = os.open(repo / ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
            raise BackupError("El bloqueo de repositorio debe ser un archivo regular")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        validate_repository(repo)
        yield repo
    finally:
        os.close(lock_fd)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


def reject_duplicate_keys(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackupError("Claves JSON duplicadas")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise BackupError(f"Constante JSON inválida: {value}")


def validate_manifest(manifest: object, snapshot_id: str) -> list[dict]:
    if not isinstance(manifest, dict) or set(manifest) != {"format", "id", "entries"}:
        raise BackupError("Estructura de manifiesto inválida")
    if type(manifest["format"]) is not int or manifest["format"] != 1 or manifest["id"] != snapshot_id:
        raise BackupError("Versión o ID del manifiesto inválidos")
    entries = manifest["entries"]
    if not isinstance(entries, list):
        raise BackupError("Inventario de manifiesto inválido")
    known: dict[str, str] = {}
    paths = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") not in ("dir", "file"):
            raise BackupError("Tipo de entrada inválido")
        expected_keys = {"path", "type"} if entry["type"] == "dir" else {"path", "type", "size", "sha256"}
        if set(entry) != expected_keys:
            raise BackupError("Campos de entrada inválidos")
        path = entry["path"]
        if not isinstance(path, str) or not path or "\0" in path:
            raise BackupError("Ruta de manifiesto inválida")
        parts = path.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise BackupError("Ruta de manifiesto fuera del árbol")
        if path in known:
            raise BackupError("Ruta duplicada en manifiesto")
        parent = "/".join(parts[:-1])
        if parent and known.get(parent) != "dir":
            raise BackupError("Directorio padre ausente del manifiesto")
        if entry["type"] == "file":
            if type(entry["size"]) is not int or entry["size"] < 0:
                raise BackupError("Tamaño de archivo inválido")
            if not isinstance(entry["sha256"], str) or not HASH_PATTERN.fullmatch(entry["sha256"]):
                raise BackupError("Hash de archivo inválido")
        known[path] = entry["type"]
        paths.append(path)
    if paths != sorted(paths):
        raise BackupError("Inventario de manifiesto desordenado")
    return entries


def verify_snapshot(repo: Path, snapshot_id: str) -> tuple[Path, list[dict]]:
    snapshot = directory_path(repo / "snapshots" / snapshot_id)
    with os.scandir(snapshot) as stream:
        root_entries = {item.name: kind(item.stat(follow_symlinks=False), snapshot / item.name) for item in stream}
    if root_entries != {"manifest.json": "file", "manifest.sha256": "file", "data": "dir"}:
        raise BackupError("Snapshot incompleto o con entradas adicionales")
    raw_manifest = read_regular(snapshot / "manifest.json")
    if read_regular(snapshot / "manifest.sha256") != (hashlib.sha256(raw_manifest).hexdigest() + "\n").encode("ascii"):
        raise BackupError("Checksum del manifiesto incorrecto")
    try:
        manifest = json.loads(raw_manifest.decode("ascii"), object_pairs_hook=reject_duplicate_keys, parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise BackupError("JSON de manifiesto inválido") from error
    entries = validate_manifest(manifest, snapshot_id)
    if canonical_json(manifest) != raw_manifest:
        raise BackupError("Manifiesto no canónico")
    data = snapshot / "data"
    if inventory(data) != {entry["path"]: entry["type"] for entry in entries}:
        raise BackupError("Inventario de datos diferente del manifiesto")
    for entry in entries:
        if entry["type"] == "file":
            size, digest = hash_file(data / entry["path"])
            if size != entry["size"] or digest != entry["sha256"]:
                raise BackupError(f"Archivo corrupto: {entry['path']}")
    return data, entries


def create_snapshot(source_raw: str, repo_raw: str, snapshot_id: str, max_bytes: int | None = None) -> dict:
    validate_id(snapshot_id)
    if max_bytes is not None and (type(max_bytes) is not int or max_bytes < 0):
        raise BackupError("max-bytes debe ser un entero no negativo")
    source = directory_path(source_raw)
    repo_path = directory_path(repo_raw, missing_ok=True)
    if overlaps(source, repo_path):
        raise BackupError("Fuente y repositorio solapados")
    source_tree = inventory(source)
    with repository(repo_path, create=True) as repo:
        published = repo / "snapshots" / snapshot_id
        if published.exists():
            raise BackupError("El ID ya existe")
        snapshots = repo / "snapshots"
        staging = repo / ".staging"
        snapshots.mkdir(exist_ok=True)
        staging.mkdir(exist_ok=True)
        sync_directory(repo)
        # Exclusive lock: no other operation of this program can own these orphans.
        for orphan in staging.iterdir():
            shutil.rmtree(orphan)
        sync_directory(staging)
        if max_bytes is not None:
            used = repository_bytes(repo)
            if used > max_bytes:
                raise BackupError(f"El repositorio ya ocupa {used} bytes; límite {max_bytes}")
        temporary = Path(tempfile.mkdtemp(prefix="create-", dir=staging))
        try:
            data = temporary / "data"
            data.mkdir()
            entries = []
            for relative, item_kind in source_tree.items():
                target = data / relative
                entry = {"path": relative, "type": item_kind}
                if item_kind == "dir":
                    target.mkdir()
                else:
                    size, digest = copy_file(source / relative, target)
                    entry.update(size=size, sha256=digest)
                entries.append(entry)
            manifest_bytes = canonical_json({"format": 1, "id": snapshot_id, "entries": entries})
            write_regular(temporary / "manifest.json", manifest_bytes)
            write_regular(temporary / "manifest.sha256", (hashlib.sha256(manifest_bytes).hexdigest() + "\n").encode("ascii"))
            sync_tree(data, entries)
            sync_directory(temporary)
            # Rename only changes directory entries: this is the final total.
            # Count all regular files, rather than estimating payload sizes.
            if max_bytes is not None:
                used = repository_bytes(repo)
                if used > max_bytes:
                    raise BackupError(f"El create requiere {used} bytes; límite {max_bytes}")
            # No ID is visible until the complete snapshot moves to this namespace.
            if published.exists():
                raise BackupError("El ID ya existe")
            os.rename(temporary, published)
            sync_directory(snapshots)
            sync_directory(staging)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
                sync_directory(staging)
    return {"id": snapshot_id}


def verify_command(repo_raw: str, snapshot_id: str) -> dict:
    validate_id(snapshot_id)
    with repository(repo_raw) as repo:
        if repo is None:
            raise BackupError("Repositorio inexistente")
        verify_snapshot(repo, snapshot_id)
    return {"id": snapshot_id, "valid": True}


def destination_is_empty(destination: Path) -> None:
    directory_path(destination, missing_ok=True)
    if destination.exists():
        with os.scandir(destination) as stream:
            if next(stream, None) is not None:
                raise BackupError("El destino preexistente no está vacío")


def restore_snapshot(repo_raw: str, snapshot_id: str, dest_raw: str) -> dict:
    validate_id(snapshot_id)
    destination = directory_path(dest_raw, missing_ok=True)
    repo_path = directory_path(repo_raw, missing_ok=True)
    if overlaps(destination, repo_path):
        raise BackupError("Destino y repositorio solapados")
    destination_is_empty(destination)
    with repository(repo_path) as repo:
        if repo is None:
            raise BackupError("Repositorio inexistente")
        data, entries = verify_snapshot(repo, snapshot_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".backup-restore-", dir=destination.parent))
        try:
            for entry in entries:
                target = temporary / entry["path"]
                if entry["type"] == "dir":
                    target.mkdir()
                else:
                    copy_file(data / entry["path"], target, expected=entry)
            sync_tree(temporary, entries)
            destination_is_empty(destination)
            os.rename(temporary, destination)
            sync_directory(destination.parent)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return {"id": snapshot_id}


def list_snapshots(repo_raw: str) -> dict:
    result = []
    with repository(repo_raw) as repo:
        if repo is not None and (repo / "snapshots").exists():
            for snapshot in sorted((repo / "snapshots").iterdir()):
                try:
                    verify_snapshot(repo, snapshot.name)
                except (BackupError, OSError, ValueError, RecursionError):
                    # A published but damaged/incomplete directory is not a valid listing.
                    continue
                result.append(snapshot.name)
    return {"snapshots": result}


class JsonParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, json.dumps({"error": message}, ensure_ascii=True) + "\n")


def nonnegative_bytes(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value, re.ASCII):
        raise argparse.ArgumentTypeError("N debe ser un entero decimal no negativo")
    try:
        return int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("N excede el tamaño de entero admitido por Python") from error


def main(argv: list[str] | None = None) -> int:
    parser = JsonParser(description="Backup verificable de directorios (V2)")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=JsonParser)
    for name in ("create", "verify", "restore", "list"):
        command = commands.add_parser(name)
        command.add_argument("--repo", required=True)
        if name != "list":
            command.add_argument("--id", required=True)
        if name == "create":
            command.add_argument("--source", required=True)
            command.add_argument("--max-bytes", type=nonnegative_bytes, metavar="N",
                                 help="máximo de bytes regulares del repo final, incluidos metadatos")
        if name == "restore":
            command.add_argument("--dest", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            result = create_snapshot(args.source, args.repo, args.id, args.max_bytes)
        elif args.command == "verify":
            result = verify_command(args.repo, args.id)
        elif args.command == "restore":
            result = restore_snapshot(args.repo, args.id, args.dest)
        else:
            result = list_snapshots(args.repo)
    except (BackupError, OSError, ValueError, RecursionError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
