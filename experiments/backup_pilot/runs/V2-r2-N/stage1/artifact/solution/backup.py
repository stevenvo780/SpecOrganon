#!/usr/bin/env python3
"""Backups autocontenidos, verificables y publicados atómicamente (stdlib)."""

import argparse
import contextlib
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


MAGIC = b"BKUPV2\r\n"
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", re.ASCII)
EXTENSION = ".bkp"
CHUNK = 1024 * 1024
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


class BackupError(Exception):
    pass


def check_id(value):
    if not isinstance(value, str) or ID_RE.fullmatch(value) is None:
        raise BackupError("ID inválido")
    return value


@contextlib.contextmanager
def directory(path, create=False):
    """Abre cada componente sin seguir enlaces, incluso antes de un '..'."""
    path = os.fspath(path)
    if not path or "\0" in path:
        raise BackupError("Ruta de directorio inválida")
    components = path.split(os.sep)
    if not os.path.isabs(path):
        components = os.getcwd().split(os.sep) + components
    fd = os.open(os.sep, DIR_FLAGS)
    try:
        for component in components:
            if component in ("", "."):
                continue
            try:
                next_fd = os.open(component, DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(component, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                next_fd = os.open(component, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


@contextlib.contextmanager
def relative_directory(root_fd, components):
    fd = os.dup(root_fd)
    try:
        for component in components:
            next_fd = os.open(component, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


@contextlib.contextmanager
def regular_file(parent_fd, name):
    fd = os.open(name, READ_FLAGS, dir_fd=parent_fd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise BackupError("Solo se permiten archivos regulares: " + name)
        yield fd
    finally:
        os.close(fd)


def overlap(first, second):
    first, second = os.path.abspath(first), os.path.abspath(second)
    common = os.path.commonpath((first, second))
    return common == first or common == second


def source_entries(root_fd):
    entries = []
    pending = [()]
    while pending:
        components = pending.pop()
        with relative_directory(root_fd, components) as fd:
            with os.scandir(fd) as scan:
                names = sorted(entry.name for entry in scan)
            for name in names:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                parts = components + (name,)
                path = "/".join(parts)
                if stat.S_ISDIR(info.st_mode):
                    entries.append({"path": path, "type": "dir"})
                    pending.append(parts)
                elif stat.S_ISREG(info.st_mode):
                    entries.append({"path": path, "type": "file", "size": info.st_size})
                else:
                    raise BackupError("Enlace o archivo especial en fuente: " + path)
    return sorted(entries, key=lambda entry: entry["path"])


@contextlib.contextmanager
def repository(path, initialize=False):
    with directory(path, create=initialize) as root_fd:
        with os.scandir(root_fd) as scan:
            names = [entry.name for entry in scan]
        for name in names:
            info = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            if name not in ("snapshots", "staging") or not stat.S_ISDIR(info.st_mode):
                raise BackupError("Entrada no permitida en repositorio: " + name)
        if initialize:
            for name in ("snapshots", "staging"):
                try:
                    os.mkdir(name, 0o700, dir_fd=root_fd)
                except FileExistsError:
                    pass
            os.fsync(root_fd)
        with contextlib.ExitStack() as stack:
            dirs = {}
            for name in ("snapshots", "staging"):
                try:
                    dirs[name] = stack.enter_context(relative_directory(root_fd, (name,)))
                except FileNotFoundError:
                    dirs[name] = None
                    continue
                with os.scandir(dirs[name]) as scan:
                    children = [entry.name for entry in scan]
                for child in children:
                    info = os.stat(child, dir_fd=dirs[name], follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode):
                        raise BackupError("Enlace o archivo especial en repositorio: " + child)
                    if name == "snapshots":
                        if not child.endswith(EXTENSION):
                            raise BackupError("Nombre de snapshot inválido: " + child)
                        check_id(child[:-len(EXTENSION)])
            yield dirs


def write_all(fd, data):
    remaining = memoryview(data)
    while remaining:
        written = os.write(fd, remaining)
        if written <= 0:
            raise BackupError("No se pudo escribir el archivo completo")
        remaining = remaining[written:]


def read_exact(fd, size):
    chunks = []
    while size:
        chunk = os.read(fd, min(size, CHUNK))
        if not chunk:
            raise BackupError("Snapshot truncado")
        chunks.append(chunk)
        size -= len(chunk)
    return b"".join(chunks)


def create(source, repo, snapshot_id):
    check_id(snapshot_id)
    if overlap(source, repo):
        raise BackupError("Fuente y repositorio no pueden solaparse")
    with directory(source) as source_fd:
        entries = source_entries(source_fd)
        manifest = json.dumps(
            {"version": 1, "id": snapshot_id, "entries": entries},
            ensure_ascii=True, separators=(",", ":"), allow_nan=False,
        ).encode("ascii")
        with repository(repo, initialize=True) as dirs:
            snapshots_fd, staging_fd = dirs["snapshots"], dirs["staging"]
            final_name = snapshot_id + EXTENSION
            try:
                os.stat(final_name, dir_fd=snapshots_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise BackupError("El ID ya existe")
            temporary = ".create-" + uuid.uuid4().hex
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=staging_fd)
            try:
                digest = hashlib.sha256()

                def emit(data):
                    write_all(fd, data)
                    digest.update(data)

                emit(MAGIC + struct.pack(">Q", len(manifest)))
                emit(manifest)
                for entry in entries:
                    if entry["type"] != "file":
                        continue
                    parts = entry["path"].split("/")
                    with relative_directory(source_fd, parts[:-1]) as parent_fd:
                        with regular_file(parent_fd, parts[-1]) as input_fd:
                            if os.fstat(input_fd).st_size != entry["size"]:
                                raise BackupError("La fuente cambió durante create")
                            remaining = entry["size"]
                            while remaining:
                                chunk = os.read(input_fd, min(remaining, CHUNK))
                                if not chunk:
                                    raise BackupError("La fuente cambió durante create")
                                emit(chunk)
                                remaining -= len(chunk)
                            if os.read(input_fd, 1):
                                raise BackupError("La fuente cambió durante create")
                write_all(fd, digest.digest())
                os.fsync(fd)
                # link es una publicación atómica que nunca reemplaza otro ID.
                os.link(temporary, final_name, src_dir_fd=staging_fd,
                        dst_dir_fd=snapshots_fd, follow_symlinks=False)
                os.fsync(snapshots_fd)
            finally:
                os.close(fd)
                try:
                    os.unlink(temporary, dir_fd=staging_fd)
                    os.fsync(staging_fd)
                except FileNotFoundError:
                    pass
    return {"id": snapshot_id}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackupError("Clave duplicada en el índice")
        result[key] = value
    return result


def validate_manifest(data, snapshot_id, payload_size):
    try:
        manifest = json.loads(data.decode("ascii"), object_pairs_hook=unique_object)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise BackupError("Índice ilegible") from error
    if not isinstance(manifest, dict) or set(manifest) != {"version", "id", "entries"}:
        raise BackupError("Índice inválido")
    if type(manifest["version"]) is not int or manifest["version"] != 1:
        raise BackupError("Versión de formato no admitida")
    if manifest["id"] != snapshot_id or not isinstance(manifest["entries"], list):
        raise BackupError("Identidad o entradas inválidas")
    known = {}
    previous = ""
    total = 0
    for entry in manifest["entries"]:
        if not isinstance(entry, dict):
            raise BackupError("Entrada de índice inválida")
        path = entry.get("path")
        kind = entry.get("type")
        if not isinstance(path, str) or not path or "\0" in path or path <= previous:
            raise BackupError("Ruta duplicada, desordenada o inválida")
        parts = path.split("/")
        for part in parts:
            if part in ("", ".", "..") or os.path.isabs(part):
                raise BackupError("Ruta fuera del snapshot")
            if os.sep != "/" and os.sep in part:
                raise BackupError("Separador de ruta inválido")
            try:
                os.fsencode(part)
            except UnicodeError as error:
                raise BackupError("Nombre no representable en este sistema") from error
        parent = "/".join(parts[:-1])
        if parent and known.get(parent) != "dir":
            raise BackupError("Directorio padre ausente o inválido")
        expected = {"path", "type"}
        if kind == "file":
            expected.add("size")
            size = entry.get("size")
            if type(size) is not int or size < 0:
                raise BackupError("Tamaño de archivo inválido")
            total += size
            if total > payload_size:
                raise BackupError("Contenido truncado o tamaños inválidos")
        elif kind != "dir":
            raise BackupError("Tipo de entrada inválido")
        if set(entry) != expected:
            raise BackupError("Campos de entrada inválidos")
        known[path] = kind
        previous = path
    if total != payload_size:
        raise BackupError("Tamaño total del snapshot inválido")
    return manifest["entries"]


def consume_snapshot(fd, snapshot_id, destination_fd=None):
    """Valida todo el archivo; si extrae, el árbol permanece privado hasta el final."""
    os.lseek(fd, 0, os.SEEK_SET)
    file_size = os.fstat(fd).st_size
    if file_size < len(MAGIC) + 8 + 32:
        raise BackupError("Snapshot truncado")
    header = read_exact(fd, len(MAGIC) + 8)
    if header[:len(MAGIC)] != MAGIC:
        raise BackupError("Cabecera de snapshot inválida")
    manifest_size = struct.unpack(">Q", header[len(MAGIC):])[0]
    payload_size = file_size - len(header) - 32 - manifest_size
    if payload_size < 0:
        raise BackupError("Índice truncado")
    manifest = read_exact(fd, manifest_size)
    entries = validate_manifest(manifest, snapshot_id, payload_size)
    digest = hashlib.sha256(header)
    digest.update(manifest)
    for entry in entries:
        parts = entry["path"].split("/")
        output_fd = None
        if destination_fd is not None:
            with relative_directory(destination_fd, parts[:-1]) as parent_fd:
                if entry["type"] == "dir":
                    os.mkdir(parts[-1], 0o700, dir_fd=parent_fd)
                else:
                    output_fd = os.open(
                        parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600, dir_fd=parent_fd,
                    )
        if entry["type"] == "dir":
            continue
        try:
            remaining = entry["size"]
            while remaining:
                chunk = os.read(fd, min(remaining, CHUNK))
                if not chunk:
                    raise BackupError("Contenido truncado")
                digest.update(chunk)
                if output_fd is not None:
                    write_all(output_fd, chunk)
                remaining -= len(chunk)
            if output_fd is not None:
                os.fsync(output_fd)
        finally:
            if output_fd is not None:
                os.close(output_fd)
    stored_digest = read_exact(fd, 32)
    if os.read(fd, 1) or not hmac.compare_digest(digest.digest(), stored_digest):
        raise BackupError("Integridad SHA-256 incorrecta")
    if os.fstat(fd).st_size != file_size:
        raise BackupError("El snapshot cambió durante la operación")


@contextlib.contextmanager
def snapshot_file(dirs, snapshot_id):
    if dirs["snapshots"] is None:
        raise BackupError("El ID no existe")
    try:
        with regular_file(dirs["snapshots"], snapshot_id + EXTENSION) as fd:
            yield fd
    except FileNotFoundError as error:
        raise BackupError("El ID no existe") from error


def verify(repo, snapshot_id):
    check_id(snapshot_id)
    with repository(repo) as dirs:
        with snapshot_file(dirs, snapshot_id) as fd:
            consume_snapshot(fd, snapshot_id)
    return {"id": snapshot_id, "valid": True}


def destination_state(parent_fd, name):
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(info.st_mode):
        raise BackupError("El destino debe ser un directorio sin enlaces")
    with relative_directory(parent_fd, (name,)) as fd:
        if os.listdir(fd):
            raise BackupError("El destino preexistente no está vacío")
        actual = os.fstat(fd)
    return actual.st_dev, actual.st_ino


def restore(repo, snapshot_id, dest):
    check_id(snapshot_id)
    if overlap(repo, dest):
        raise BackupError("Destino y repositorio no pueden solaparse")
    # Conserva los componentes originales para rechazar enlaces antes de '..'.
    trimmed = dest.rstrip(os.sep)
    parent, name = os.path.split(trimmed)
    if name in ("", ".", ".."):
        raise BackupError("El destino debe nombrar un directorio hijo")
    with repository(repo) as dirs:
        with snapshot_file(dirs, snapshot_id) as input_fd:
            # Detecta corrupción antes de crear incluso el directorio padre.
            consume_snapshot(input_fd, snapshot_id)
            with directory(parent or ".", create=True) as parent_fd:
                initial = destination_state(parent_fd, name)
                temporary = ".restore-" + uuid.uuid4().hex
                os.mkdir(temporary, 0o700, dir_fd=parent_fd)
                published = False
                try:
                    with relative_directory(parent_fd, (temporary,)) as stage_fd:
                        consume_snapshot(input_fd, snapshot_id, stage_fd)
                        os.fsync(stage_fd)
                    if destination_state(parent_fd, name) != initial:
                        raise BackupError("El destino cambió durante restore")
                    os.rename(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
                    published = True
                    os.fsync(parent_fd)
                finally:
                    if not published:
                        shutil.rmtree(temporary, dir_fd=parent_fd)
    return {"id": snapshot_id}


def list_snapshots(repo):
    # Un repositorio inexistente o un directorio nuevo vacío contiene cero IDs.
    try:
        with directory(repo):
            pass
    except FileNotFoundError:
        return {"snapshots": []}
    snapshots = []
    with repository(repo) as dirs:
        if dirs["snapshots"] is not None:
            for name in sorted(os.listdir(dirs["snapshots"])):
                snapshot_id = name[:-len(EXTENSION)]
                with regular_file(dirs["snapshots"], name) as fd:
                    try:
                        consume_snapshot(fd, snapshot_id)
                    except BackupError:
                        # Solo se enumeran snapshots íntegros y completos.
                        continue
                snapshots.append(snapshot_id)
    return {"snapshots": sorted(snapshots)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("create", "verify", "restore", "list"):
        subparser = commands.add_parser(command, allow_abbrev=False)
        subparser.add_argument("--repo", required=True)
        if command != "list":
            subparser.add_argument("--id", required=True)
        if command == "create":
            subparser.add_argument("--source", required=True)
        if command == "restore":
            subparser.add_argument("--dest", required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            result = create(args.source, args.repo, args.id)
        elif args.command == "verify":
            result = verify(args.repo, args.id)
        elif args.command == "restore":
            result = restore(args.repo, args.id, args.dest)
        else:
            result = list_snapshots(args.repo)
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return 0
    except (BackupError, OSError, ValueError, OverflowError, RecursionError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
