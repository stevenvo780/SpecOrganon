#!/usr/bin/env python3
"""Backups verificables: Python 3.12 y biblioteca estándar, POSIX/Linux."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import re
import stat
import sys
import uuid


ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z", re.ASCII)
TEMP_RE = re.compile(r"\.pending-[0-9a-f]{32}\Z", re.ASCII)
HASH_RE = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
WRITE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
CHUNK = 1024 * 1024


class BackupError(Exception):
    """Una operación no puede declararse correcta."""


def check_id(identifier: str) -> None:
    if not ID_RE.fullmatch(identifier):
        raise BackupError("ID inválido: use 1–64 caracteres ASCII de letras, números, _ o -")


def kind(info: os.stat_result) -> str:
    if stat.S_ISLNK(info.st_mode):
        raise BackupError("symlink rechazado")
    if stat.S_ISDIR(info.st_mode):
        return "dir"
    if stat.S_ISREG(info.st_mode):
        return "file"
    raise BackupError("archivo especial rechazado")


def open_dir_at(parent: int, name: str) -> int:
    if kind(os.stat(name, dir_fd=parent, follow_symlinks=False)) != "dir":
        raise BackupError("se requiere un directorio")
    return os.open(name, DIR_FLAGS, dir_fd=parent)


def open_file_at(parent: int, name: str) -> int:
    if kind(os.stat(name, dir_fd=parent, follow_symlinks=False)) != "file":
        raise BackupError("se requiere un archivo regular")
    fd = os.open(name, READ_FLAGS, dir_fd=parent)
    try:
        if kind(os.fstat(fd)) != "file":
            raise BackupError("se requiere un archivo regular")
        return fd
    except BaseException:
        os.close(fd)
        raise


def directory_path(raw: str, *, allow_missing: bool = False,
                   create: bool = False) -> tuple[str, int | None]:
    """Recorre incluso los componentes anteriores a '..', sin seguir enlaces.

    Devuelve la ruta absoluta y un descriptor propiedad del llamante, o None si
    la ruta no existe y allow_missing está activo. Nunca inspecciona contenidos
    ajenos: solo los componentes de la ruta solicitada.
    """
    if not raw or "\x00" in raw:
        raise BackupError("ruta vacía o inválida")
    absolute = raw if os.path.isabs(raw) else os.getcwd() + "/" + raw
    parts = [part for part in absolute.split("/") if part not in ("", ".")]
    resolved: list[str] = []
    fd: int | None = os.open("/", DIR_FLAGS)
    try:
        for part in parts:
            if fd is None:
                if part == "..":
                    raise BackupError("componente inexistente antes de '..'")
                resolved.append(part)
                continue
            try:
                next_fd = open_dir_at(fd, part)
            except FileNotFoundError:
                if create:
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                    next_fd = open_dir_at(fd, part)
                elif allow_missing:
                    os.close(fd)
                    fd = None
                    resolved.append(part)
                    continue
                else:
                    raise
            os.close(fd)
            fd = next_fd
            if part == "..":
                if resolved:
                    resolved.pop()
            else:
                resolved.append(part)
        result = "/" + "/".join(resolved)
        owned_fd, fd = fd, None
        return result, owned_fd
    finally:
        if fd is not None:
            os.close(fd)


def overlaps(left: str, right: str) -> bool:
    return os.path.commonpath((left, right)) in (left, right)


@contextmanager
def locked(fd: int, *, exclusive: bool = False):
    # El inode del repo es el lock: SIGKILL lo libera sin archivos de bloqueo.
    fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
    try:
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)


def safe_tree(fd: int) -> None:
    for name in sorted(os.listdir(fd)):
        if kind(os.stat(name, dir_fd=fd, follow_symlinks=False)) == "dir":
            child = open_dir_at(fd, name)
            try:
                safe_tree(child)
            finally:
                os.close(child)


def repository_inventory(fd: int) -> tuple[list[str], list[str]]:
    identifiers, temporaries = [], []
    for name in sorted(os.listdir(fd)):
        if kind(os.stat(name, dir_fd=fd, follow_symlinks=False)) != "dir":
            raise BackupError("entrada inesperada en la raíz del repo")
        if ID_RE.fullmatch(name):
            identifiers.append(name)
        elif TEMP_RE.fullmatch(name):
            temporaries.append(name)
        else:
            raise BackupError("directorio inesperado en la raíz del repo")
        child = open_dir_at(fd, name)
        try:
            safe_tree(child)
        finally:
            os.close(child)
    return identifiers, temporaries


def remove_tree(parent: int, name: str) -> None:
    child = open_dir_at(parent, name)
    try:
        for entry in os.listdir(child):
            if kind(os.stat(entry, dir_fd=child, follow_symlinks=False)) == "dir":
                remove_tree(child, entry)
            else:
                os.unlink(entry, dir_fd=child)
    finally:
        os.close(child)
    os.rmdir(name, dir_fd=parent)


def cleanup(parent: int, name: str | None) -> None:
    if name is not None:
        try:
            remove_tree(parent, name)
        except (OSError, BackupError):
            # Un temporal no publicado nunca es un snapshot. No ocultar el
            # error original ni seguir un enlace introducido durante limpieza.
            pass


def write_all(fd: int, value: bytes) -> None:
    remaining = memoryview(value)
    while remaining:
        written = os.write(fd, remaining)
        if written <= 0:
            raise BackupError("escritura incompleta")
        remaining = remaining[written:]


def write_file(parent: int, name: str, value: bytes) -> None:
    fd = os.open(name, WRITE_FLAGS, 0o600, dir_fd=parent)
    try:
        write_all(fd, value)
        os.fsync(fd)
    finally:
        os.close(fd)


def read_bytes(parent: int, name: str, *, limit: int | None = None) -> bytes:
    fd = open_file_at(parent, name)
    try:
        chunks, size = [], 0
        while chunk := os.read(fd, CHUNK if limit is None else limit + 1):
            size += len(chunk)
            if limit is not None and size > limit:
                raise BackupError("metadato de tamaño inválido")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def read_tree(source: int, target: int | None = None,
              prefix: tuple[str, ...] = ()) -> list[dict]:
    """Inventario y hashes, con copia opcional, siempre sin seguir enlaces."""
    entries = []
    for name in sorted(os.listdir(source)):
        path = prefix + (name,)
        info = os.stat(name, dir_fd=source, follow_symlinks=False)
        if kind(info) == "dir":
            entries.append({"path": list(path), "kind": "dir"})
            child = open_dir_at(source, name)
            output = None
            try:
                if target is not None:
                    os.mkdir(name, 0o700, dir_fd=target)
                    output = open_dir_at(target, name)
                entries.extend(read_tree(child, output, path))
            finally:
                if output is not None:
                    os.close(output)
                os.close(child)
        else:
            input_fd = open_file_at(source, name)
            output_fd = None
            try:
                before = os.fstat(input_fd)
                if target is not None:
                    output_fd = os.open(name, WRITE_FLAGS, 0o600, dir_fd=target)
                digest, size = hashlib.sha256(), 0
                while chunk := os.read(input_fd, CHUNK):
                    digest.update(chunk)
                    size += len(chunk)
                    if output_fd is not None:
                        write_all(output_fd, chunk)
                after = os.fstat(input_fd)
                if (size != before.st_size or before.st_size != after.st_size
                        or before.st_mtime_ns != after.st_mtime_ns
                        or before.st_ctime_ns != after.st_ctime_ns):
                    raise BackupError("archivo cambió durante la lectura")
                if output_fd is not None:
                    os.fsync(output_fd)
                entries.append({"path": list(path), "kind": "file",
                                "size": size, "sha256": digest.hexdigest()})
            finally:
                if output_fd is not None:
                    os.close(output_fd)
                os.close(input_fd)
    if target is not None:
        os.fsync(target)
    return entries


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackupError("clave duplicada en manifiesto")
        result[key] = value
    return result


def invalid_constant(value: str):
    raise BackupError("constante JSON inválida: " + value)


def parse_manifest(raw: bytes, identifier: str) -> list[dict]:
    try:
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                              parse_constant=invalid_constant)
    except (ValueError, UnicodeError) as exc:
        raise BackupError("manifiesto ilegible") from exc
    if (type(manifest) is not dict or set(manifest) != {"version", "id", "entries"}
            or type(manifest["version"]) is not int or manifest["version"] != 1
            or manifest["id"] != identifier or type(manifest["entries"]) is not list):
        raise BackupError("cabecera de manifiesto inválida")
    entries = manifest["entries"]
    paths: dict[tuple[str, ...], str] = {}
    for entry in entries:
        if type(entry) is not dict:
            raise BackupError("entrada de manifiesto inválida")
        path = entry.get("path")
        if (type(path) is not list or not path
                or any(type(part) is not str or not part or part in (".", "..")
                       or "/" in part or "\x00" in part for part in path)):
            raise BackupError("ruta insegura en manifiesto")
        key = tuple(path)
        if key in paths:
            raise BackupError("ruta repetida en manifiesto")
        entry_kind = entry.get("kind")
        if entry_kind == "dir" and set(entry) == {"path", "kind"}:
            pass
        elif entry_kind == "file" and set(entry) == {"path", "kind", "size", "sha256"}:
            if (type(entry["size"]) is not int or entry["size"] < 0
                    or type(entry["sha256"]) is not str
                    or not HASH_RE.fullmatch(entry["sha256"])):
                raise BackupError("tamaño o hash inválido")
        else:
            raise BackupError("tipo o esquema de entrada inválido")
        paths[key] = entry_kind
    if entries != sorted(entries, key=lambda item: tuple(item["path"])):
        raise BackupError("inventario desordenado")
    for path in paths:
        if len(path) > 1 and paths.get(path[:-1]) != "dir":
            raise BackupError("directorio padre ausente en manifiesto")
    return entries


@contextmanager
def snapshot_data(repo: int, name: str, identifier: str | None = None):
    snapshot = open_dir_at(repo, name)
    data = None
    try:
        if set(os.listdir(snapshot)) != {"data", "manifest.json", "seal"}:
            raise BackupError("snapshot incompleto o con entradas extra")
        seal = read_bytes(snapshot, "seal", limit=65)
        if re.fullmatch(rb"[0-9a-f]{64}\n", seal) is None:
            raise BackupError("sello inválido")
        raw = read_bytes(snapshot, "manifest.json")
        if hashlib.sha256(raw).hexdigest().encode("ascii") + b"\n" != seal:
            raise BackupError("manifiesto corrupto")
        entries = parse_manifest(raw, identifier if identifier is not None else name)
        data = open_dir_at(snapshot, "data")
        yield data, entries
    finally:
        if data is not None:
            os.close(data)
        os.close(snapshot)


def verify_snapshot(repo: int, name: str, identifier: str | None = None) -> None:
    with snapshot_data(repo, name, identifier) as (data, entries):
        if read_tree(data) != entries:
            raise BackupError("datos corruptos o inventario diferente al manifiesto")


def create(source_arg: str, repo_arg: str, identifier: str) -> dict:
    check_id(identifier)
    source_path, source = directory_path(source_arg)
    repo = None
    try:
        repo_path, repo = directory_path(repo_arg, allow_missing=True)
        if overlaps(source_path, repo_path):
            raise BackupError("fuente y repo solapados")
        safe_tree(source)
        if repo is None:
            _, repo = directory_path(repo_path, create=True)
        with locked(repo, exclusive=True):
            identifiers, temporaries = repository_inventory(repo)
            if identifier in identifiers:
                raise BackupError("el ID ya existe; no se sobrescribe")
            for old in temporaries:
                remove_tree(repo, old)
            pending = ".pending-" + uuid.uuid4().hex
            os.mkdir(pending, 0o700, dir_fd=repo)
            try:
                stage = open_dir_at(repo, pending)
                try:
                    os.mkdir("data", 0o700, dir_fd=stage)
                    data = open_dir_at(stage, "data")
                    try:
                        entries = read_tree(source, data)
                    finally:
                        os.close(data)
                    manifest = {"version": 1, "id": identifier, "entries": entries}
                    raw = (json.dumps(manifest, ensure_ascii=True, sort_keys=True,
                                      separators=(",", ":")) + "\n").encode("utf-8")
                    write_file(stage, "manifest.json", raw)
                    write_file(stage, "seal", hashlib.sha256(raw).hexdigest().encode("ascii") + b"\n")
                    os.fsync(stage)
                finally:
                    os.close(stage)
                verify_snapshot(repo, pending, identifier)
                # El bloqueo serializa nuestros escritores. Comprobar también
                # una entrada creada por otro programa antes de renombrar.
                try:
                    os.stat(identifier, dir_fd=repo, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise BackupError("el ID ya existe; no se sobrescribe")
                os.rename(pending, identifier, src_dir_fd=repo, dst_dir_fd=repo)
                pending, published = None, True
                os.fsync(repo)
                assert published
            finally:
                cleanup(repo, pending)
        return {"id": identifier}
    finally:
        if repo is not None:
            os.close(repo)
        os.close(source)


def verify(repo_arg: str, identifier: str) -> dict:
    check_id(identifier)
    _, repo = directory_path(repo_arg)
    try:
        with locked(repo):
            repository_inventory(repo)
            verify_snapshot(repo, identifier)
        return {"id": identifier, "valid": True}
    finally:
        os.close(repo)


def list_snapshots(repo_arg: str) -> dict:
    _, repo = directory_path(repo_arg, allow_missing=True)
    if repo is None:
        return {"snapshots": []}
    try:
        with locked(repo):
            identifiers, _ = repository_inventory(repo)
            complete = []
            for identifier in identifiers:
                try:
                    verify_snapshot(repo, identifier)
                except (BackupError, OSError, ValueError, UnicodeError):
                    continue
                complete.append(identifier)
        return {"snapshots": complete}
    finally:
        os.close(repo)


def empty_destination(parent: int, name: str) -> None:
    try:
        destination = open_dir_at(parent, name)
    except FileNotFoundError:
        return
    try:
        if os.listdir(destination):
            raise BackupError("destino preexistente no vacío")
    finally:
        os.close(destination)


def restore(repo_arg: str, identifier: str, dest_arg: str) -> dict:
    check_id(identifier)
    repo_path, repo = directory_path(repo_arg)
    parent = None
    try:
        dest_path, destination = directory_path(dest_arg, allow_missing=True)
        if destination is not None:
            try:
                if os.listdir(destination):
                    raise BackupError("destino preexistente no vacío")
            finally:
                os.close(destination)
        if overlaps(repo_path, dest_path):
            raise BackupError("repo y destino solapados")
        with locked(repo):
            repository_inventory(repo)
            verify_snapshot(repo, identifier)
            _, parent = directory_path(os.path.dirname(dest_path), create=True)
            name = os.path.basename(dest_path)
            empty_destination(parent, name)
            pending = ".restore-" + uuid.uuid4().hex
            os.mkdir(pending, 0o700, dir_fd=parent)
            try:
                stage = open_dir_at(parent, pending)
                try:
                    with snapshot_data(repo, identifier) as (data, entries):
                        if read_tree(data, stage) != entries:
                            raise BackupError("datos cambiaron o están corruptos")
                finally:
                    os.close(stage)
                verify_snapshot(repo, identifier)
                empty_destination(parent, name)
                os.rename(pending, name, src_dir_fd=parent, dst_dir_fd=parent)
                pending = None
                os.fsync(parent)
            finally:
                cleanup(parent, pending)
        return {"id": identifier}
    finally:
        if parent is not None:
            os.close(parent)
        os.close(repo)


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise BackupError("argumentos inválidos: " + message)


def arguments(argv: list[str]):
    # Sin salida textual de --help: todo éxito de esta CLI es un objeto JSON.
    parser = Parser(add_help=False, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
    for command in ("create", "verify", "restore", "list"):
        child = commands.add_parser(command, add_help=False, allow_abbrev=False)
        child.add_argument("--repo", required=True)
        if command != "list":
            child.add_argument("--id", required=True)
        if command == "create":
            child.add_argument("--source", required=True)
        if command == "restore":
            child.add_argument("--dest", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = arguments(sys.argv[1:] if argv is None else argv)
        if args.command == "create":
            result = create(args.source, args.repo, args.id)
        elif args.command == "verify":
            result = verify(args.repo, args.id)
        elif args.command == "restore":
            result = restore(args.repo, args.id, args.dest)
        else:
            result = list_snapshots(args.repo)
    except (BackupError, OSError, ValueError, UnicodeError, RecursionError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"error": "operación interrumpida"}), file=sys.stderr)
        return 130
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
