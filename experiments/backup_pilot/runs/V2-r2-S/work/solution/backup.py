#!/usr/bin/env python3
"""Snapshots independientes, verificables y publicados de forma atómica."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
from typing import BinaryIO


ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z", re.ASCII)
HASH_RE = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
CHUNK = 1024 * 1024
FORMAT = 1


class BackupError(Exception):
    """Una condición que impide garantizar el resultado contractual."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BackupError(message)


def valid_id(value: str) -> str:
    require(ID_RE.fullmatch(value) is not None, "ID no válido")
    return value


def maximum_bytes(value: str) -> int:
    require(re.fullmatch(r"[0-9]+", value, re.ASCII) is not None,
            "--max-bytes requiere un entero decimal no negativo")
    return int(value)


def checked_path(raw: str | Path, *, missing: bool = False) -> Path:
    """Comprobar también los componentes originales anteriores a un '..'."""
    text = os.fspath(raw)
    require(bool(text) and "\0" not in text, "Ruta no válida")
    original = Path(text) if os.path.isabs(text) else Path.cwd() / text
    current = Path(original.anchor)
    parts = original.parts[1:]
    for index, part in enumerate(parts):
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            if missing:
                continue
            raise BackupError(f"Ruta inexistente: {current}") from None
        require(not stat.S_ISLNK(mode), f"Enlace simbólico rechazado: {current}")
        if index < len(parts) - 1:
            require(stat.S_ISDIR(mode), f"Componente no directorio: {current}")
        else:
            require(stat.S_ISDIR(mode), f"Se requiere un directorio: {current}")
    result = Path(os.path.abspath(text))
    # Un componente inexistente seguido de '..' puede ocultar ancestros de la
    # ruta normalizada; comprobarlos antes de mkdir, además de la ruta original.
    if result != original:
        return checked_path(result, missing=missing)
    if result.exists():
        require(stat.S_ISDIR(result.lstat().st_mode), f"Se requiere un directorio: {result}")
    elif not missing:
        raise BackupError(f"Ruta inexistente: {result}")
    return result


def overlaps(first: Path, second: Path) -> bool:
    common = os.path.commonpath((first, second))
    return common == str(first) or common == str(second)


def inventory(root: Path) -> tuple[list[tuple[str, ...]], list[tuple[str, ...]]]:
    """Inventariar sin seguir enlaces, rechazando todos los tipos especiales."""
    directories: list[tuple[str, ...]] = []
    files: list[tuple[str, ...]] = []
    pending = [(root, ())]
    while pending:
        directory, relative = pending.pop()
        require(stat.S_ISDIR(directory.lstat().st_mode), f"Directorio no válido: {directory}")
        with os.scandir(directory) as entries:
            for entry in entries:
                path = relative + (entry.name,)
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISDIR(mode):
                    directories.append(path)
                    pending.append((directory / entry.name, path))
                elif stat.S_ISREG(mode):
                    files.append(path)
                else:
                    raise BackupError(f"Enlace o archivo especial rechazado: {directory / entry.name}")
    return sorted(directories), sorted(files)


def repository(raw: str, *, missing: bool = False) -> Path:
    repo = checked_path(raw, missing=missing)
    if not repo.exists():
        return repo
    inventory(repo)
    with os.scandir(repo) as entries:
        for entry in entries:
            require(entry.is_dir(follow_symlinks=False), f"Entrada de repositorio no válida: {entry.name}")
            require(
                ID_RE.fullmatch(entry.name) is not None or entry.name.startswith(".incomplete-"),
                f"Entrada de repositorio desconocida: {entry.name}",
            )
    return repo


def repository_bytes(repo: Path) -> int:
    """Suma contractual: st_size de cada archivo regular, incluida metadata."""
    if not repo.exists():
        return 0
    _, files = inventory(repo)
    total = 0
    for relative in files:
        path = repo.joinpath(*relative)
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode), f"Archivo regular requerido: {path}")
        total += info.st_size
    return total


def read_regular(path: Path) -> BinaryIO:
    """O_NOFOLLOW protege la apertura final; O_NONBLOCK evita bloquear en un FIFO."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), f"Archivo regular requerido: {path}")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def digest_file(path: Path) -> tuple[int, str]:
    count = 0
    digest = hashlib.sha256()
    with read_regular(path) as stream:
        while chunk := stream.read(CHUNK):
            count += len(chunk)
            digest.update(chunk)
    return count, digest.hexdigest()


def copy_checked(source: Path, target: Path, expected: tuple[int, str] | None = None) -> tuple[int, str]:
    count = 0
    digest = hashlib.sha256()
    with read_regular(source) as incoming, target.open("xb") as outgoing:
        initial_size = os.fstat(incoming.fileno()).st_size
        while chunk := incoming.read(CHUNK):
            outgoing.write(chunk)
            count += len(chunk)
            digest.update(chunk)
        require(count == initial_size, f"Tamaño cambiado durante copia: {source}")
        result = count, digest.hexdigest()
        if expected is not None:
            require(result == expected, f"Corrupción durante copia: {source}")
        outgoing.flush()
        os.fsync(outgoing.fileno())
    return result


def write_synced(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        require(stat.S_ISDIR(os.fstat(fd).st_mode), f"Directorio requerido: {path}")
        os.fsync(fd)
    finally:
        os.close(fd)


def create(source_arg: str, repo_arg: str, identifier: str, max_bytes: int | None = None) -> dict:
    identifier = valid_id(identifier)
    require(max_bytes is None or (type(max_bytes) is int and max_bytes >= 0),
            "--max-bytes requiere un entero no negativo")
    source = checked_path(source_arg)
    repo = repository(repo_arg, missing=True)
    require(not overlaps(source, repo), "Fuente y repositorio solapados")
    directories, files = inventory(source)
    published = repo / identifier
    require(not os.path.lexists(published), "El ID ya existe")
    if max_bytes is not None:
        require(repository_bytes(repo) <= max_bytes, "El repositorio ya supera --max-bytes")
    repo.mkdir(parents=True, exist_ok=True)
    checked_path(repo)
    temporary: Path | None = Path(tempfile.mkdtemp(prefix=".incomplete-", dir=repo))
    try:
        data = temporary / "data"
        data.mkdir()
        records = []
        for index, path in enumerate(files):
            name = f"{index:08d}.bin"
            size, digest = copy_checked(source.joinpath(*path), data / name)
            records.append({"path": list(path), "object": name, "size": size, "sha256": digest})
        manifest = {
            "format": FORMAT,
            "id": identifier,
            "directories": [list(path) for path in directories],
            "files": records,
        }
        encoded = json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
        write_synced(temporary / "manifest.json", encoded)
        write_synced(temporary / "manifest.sha256", (hashlib.sha256(encoded).hexdigest() + "\n").encode("ascii"))
        if max_bytes is not None:
            require(repository_bytes(repo) <= max_bytes,
                    "El snapshot y la metadata no caben en --max-bytes")
        sync_directory(data)
        sync_directory(temporary)
        require(not os.path.lexists(published), "El ID ya existe")
        os.rename(temporary, published)
        temporary = None
        sync_directory(repo)
    finally:
        if temporary is not None:
            shutil.rmtree(temporary)
    return {"id": identifier}


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, "Clave JSON duplicada")
        result[key] = value
    return result


def manifest_path(value: object) -> tuple[str, ...]:
    require(type(value) is list and len(value) > 0, "Ruta de manifiesto no válida")
    for component in value:
        require(type(component) is str, "Componente de ruta no textual")
        require(component not in ("", ".", ".."), "Componente de ruta no válido")
        require("\0" not in component and "/" not in component, "Separador o NUL en ruta")
        if os.altsep:
            require(os.altsep not in component, "Separador alternativo en ruta")
    return tuple(value)


def load_snapshot(repo: Path, identifier: str) -> dict:
    snapshot = repo / identifier
    require(snapshot.exists(), "ID inexistente")
    require(stat.S_ISDIR(snapshot.lstat().st_mode), "Snapshot no válido")
    inventory(snapshot)
    require({entry.name for entry in snapshot.iterdir()} == {"manifest.json", "manifest.sha256", "data"},
            "Estructura de snapshot incompleta o alterada")
    require(stat.S_ISDIR((snapshot / "data").lstat().st_mode), "Directorio de datos no válido")
    with read_regular(snapshot / "manifest.json") as stream:
        encoded = stream.read()
    with read_regular(snapshot / "manifest.sha256") as stream:
        seal = stream.read(66)
    require(seal == (hashlib.sha256(encoded).hexdigest() + "\n").encode("ascii"), "Sello del manifiesto incorrecto")
    try:
        manifest = json.loads(encoded.decode("utf-8"), object_pairs_hook=unique_object)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise BackupError("Manifiesto JSON no válido") from error
    require(type(manifest) is dict and set(manifest) == {"format", "id", "directories", "files"},
            "Campos del manifiesto no válidos")
    require(type(manifest["format"]) is int and manifest["format"] == FORMAT, "Formato no admitido")
    require(manifest["id"] == identifier, "ID del manifiesto incorrecto")
    require(type(manifest["directories"]) is list and type(manifest["files"]) is list, "Inventario no válido")
    directory_paths = [manifest_path(path) for path in manifest["directories"]]
    directory_set = set(directory_paths)
    require(len(directory_paths) == len(directory_set), "Directorios duplicados")
    require(directory_paths == sorted(directory_paths), "Directorios sin ordenar")
    file_paths = []
    objects = set()
    for index, record in enumerate(manifest["files"]):
        require(type(record) is dict and set(record) == {"path", "object", "size", "sha256"},
                "Registro de archivo no válido")
        path = manifest_path(record["path"])
        file_paths.append(path)
        require(record["object"] == f"{index:08d}.bin", "Nombre de objeto no válido")
        objects.add(record["object"])
        require(type(record["size"]) is int and record["size"] >= 0, "Tamaño no válido")
        require(type(record["sha256"]) is str and HASH_RE.fullmatch(record["sha256"]) is not None,
                "Hash no válido")
    file_set = set(file_paths)
    require(len(file_paths) == len(file_set) and file_paths == sorted(file_paths), "Archivos duplicados o sin ordenar")
    require(not file_set.intersection(directory_set), "Colisión entre archivo y directorio")
    for path in directory_paths + file_paths:
        require(len(path) == 1 or path[:-1] in directory_set, "Directorio padre ausente")
    with os.scandir(snapshot / "data") as entries:
        actual = set()
        for entry in entries:
            require(entry.is_file(follow_symlinks=False), "Objeto de datos no regular")
            actual.add(entry.name)
    require(actual == objects, "Objetos ausentes o adicionales")
    for record in manifest["files"]:
        require(digest_file(snapshot / "data" / record["object"]) == (record["size"], record["sha256"]),
                f"Datos corruptos: {record['object']}")
    return manifest


def verify(repo_arg: str, identifier: str) -> dict:
    identifier = valid_id(identifier)
    repo = repository(repo_arg)
    load_snapshot(repo, identifier)
    return {"id": identifier, "valid": True}


def list_snapshots(repo_arg: str) -> dict:
    repo = repository(repo_arg, missing=True)
    identifiers = []
    if repo.exists():
        for candidate in sorted(repo.iterdir()):
            if ID_RE.fullmatch(candidate.name) is None:
                continue
            try:
                load_snapshot(repo, candidate.name)
            except (BackupError, OSError):
                continue
            identifiers.append(candidate.name)
    return {"snapshots": identifiers}


def empty_destination(dest: Path) -> None:
    if os.path.lexists(dest):
        checked_path(dest)
        directories, files = inventory(dest)
        require(not directories and not files, "El destino preexistente no está vacío")


def restore(repo_arg: str, identifier: str, dest_arg: str) -> dict:
    identifier = valid_id(identifier)
    repo = repository(repo_arg)
    manifest = load_snapshot(repo, identifier)
    dest = checked_path(dest_arg, missing=True)
    require(not overlaps(repo, dest), "Destino y repositorio solapados")
    empty_destination(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    checked_path(dest.parent)
    temporary: Path | None = Path(tempfile.mkdtemp(prefix=".restore-", dir=dest.parent))
    try:
        for path in sorted(manifest["directories"], key=lambda components: (len(components), components)):
            temporary.joinpath(*path).mkdir()
        for record in manifest["files"]:
            copy_checked(repo / identifier / "data" / record["object"],
                         temporary.joinpath(*record["path"]), (record["size"], record["sha256"]))
        directories, _ = inventory(temporary)
        for path in sorted(directories, key=len, reverse=True):
            sync_directory(temporary.joinpath(*path))
        sync_directory(temporary)
        checked_path(dest, missing=True)
        empty_destination(dest)
        os.rename(temporary, dest)
        temporary = None
        sync_directory(dest.parent)
    finally:
        if temporary is not None:
            shutil.rmtree(temporary)
    return {"id": identifier}


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise BackupError(message)


def main(argv: list[str] | None = None) -> int:
    parser = Parser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
    for command in ("create", "verify", "restore", "list"):
        sub = commands.add_parser(command)
        sub.add_argument("--repo", required=True)
        if command != "list":
            sub.add_argument("--id", required=True)
        if command == "create":
            sub.add_argument("--source", required=True)
            sub.add_argument("--max-bytes", type=maximum_bytes,
                             help="máximo de bytes de todos los archivos regulares del repositorio")
        if command == "restore":
            sub.add_argument("--dest", required=True)
    try:
        args = parser.parse_args(argv)
        if args.command == "create":
            result = create(args.source, args.repo, args.id, args.max_bytes)
        elif args.command == "verify":
            result = verify(args.repo, args.id)
        elif args.command == "restore":
            result = restore(args.repo, args.id, args.dest)
        else:
            result = list_snapshots(args.repo)
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return 0
    except (BackupError, OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"error": "Operación interrumpida"}), file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
