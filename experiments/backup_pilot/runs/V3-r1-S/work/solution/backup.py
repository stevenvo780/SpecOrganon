#!/usr/bin/env python3
"""Backups verificables con publicación atómica. Python 3.12 / POSIX."""

import argparse
from contextlib import contextmanager
import errno
import fcntl
import hashlib
import json
import os
import re
import stat
import sys
import uuid


ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z", re.ASCII)
HASH_RE = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
CHUNK = 1024 * 1024


class BackupError(Exception):
    """Error que nunca representa una operación exitosa."""


class UnsafePath(BackupError):
    """Enlace o archivo especial: no debe omitirse al listar."""


class InvalidSnapshot(BackupError):
    """Snapshot ausente, incompleto o corrupto."""


class ByteBudget:
    """Suma lógica de st_size, incluidos todos los archivos de metadata."""

    def __init__(self, limit, existing):
        self.limit = limit
        self.used = existing
        if limit is not None and existing > limit:
            raise BackupError("El repositorio ya supera --max-bytes")

    def charge(self, amount):
        if self.limit is not None and amount > self.limit - self.used:
            raise BackupError("El snapshot y su metadata no caben en --max-bytes")
        self.used += amount


def parse_max_bytes(value):
    if not re.fullmatch(r"[0-9]+", value, flags=re.ASCII):
        raise argparse.ArgumentTypeError("N debe ser un entero decimal no negativo")
    try:
        return int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("N no es un entero representable") from exc


def check_id(snapshot_id):
    if not ID_RE.fullmatch(snapshot_id):
        raise BackupError("ID inválido")


def absolute(path):
    if not path or "\0" in path:
        raise BackupError("Ruta vacía o inválida")
    return os.path.abspath(path)


def overlap(a, b):
    a, b = absolute(a), absolute(b)
    common = os.path.commonpath((a, b))
    return common == a or common == b


def open_directory_at(parent, name, create=False):
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError:
            pass
    try:
        return os.open(name, DIR_FLAGS, dir_fd=parent)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            try:
                info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            except OSError:
                raise exc
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise UnsafePath("Enlace o archivo especial en una ruta") from exc
        raise


def open_directory(path, create=False, missing_ok=False):
    """Recorre cada componente con dir_fd/O_NOFOLLOW, incluso antes de '..'."""
    absolute(path)  # validar, pero no normalizar antes de comprobar enlaces
    raw = path if os.path.isabs(path) else os.path.join(os.getcwd(), path)
    components = [part for part in raw.split("/") if part not in ("", ".")]
    fd = os.open("/", DIR_FLAGS)
    try:
        for index, part in enumerate(components):
            try:
                child = open_directory_at(fd, part, create=create)
            except FileNotFoundError:
                if missing_ok and not create:
                    # Un '..' posterior podría volver a una ruta existente;
                    # no normalizar silenciosamente esa entrada ambigua.
                    if ".." in components[index + 1:]:
                        raise BackupError("Componente inexistente antes de '..'")
                    os.close(fd)
                    return None
                raise
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def open_regular(parent, name, write=False):
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW |
             os.O_CLOEXEC | os.O_NONBLOCK) if write else FILE_FLAGS
    try:
        fd = os.open(name, flags, 0o600, dir_fd=parent)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise UnsafePath("Enlace en archivo gestionado") from exc
        raise
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        os.close(fd)
        if stat.S_ISDIR(info.st_mode):
            raise BackupError("Se esperaba un archivo regular")
        raise UnsafePath("Archivo especial en ruta gestionada")
    return fd


def inspect_tree(directory):
    """Valida sin seguir enlaces y suma st_size de todos los regulares."""
    total = 0
    with os.scandir(directory) as entries:
        for entry in entries:
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = open_directory_at(directory, entry.name)
                try:
                    total += inspect_tree(child)
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode):
                total += info.st_size
            else:
                raise UnsafePath("Enlace o archivo especial: " + entry.name)
    return total


def remove_tree(parent, name):
    directory = open_directory_at(parent, name)
    try:
        for entry in os.listdir(directory):
            info = os.stat(entry, dir_fd=directory, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                remove_tree(directory, entry)
            elif stat.S_ISREG(info.st_mode):
                os.unlink(entry, dir_fd=directory)
            else:
                raise UnsafePath("Temporal con enlace o archivo especial")
    finally:
        os.close(directory)
    os.rmdir(name, dir_fd=parent)


@contextmanager
def repository(path, initialize=False):
    root = open_directory(path, create=initialize)
    lock = snapshots = staging = None
    try:
        try:
            lock = os.open(".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW |
                           os.O_CLOEXEC | os.O_NONBLOCK, 0o600, dir_fd=root)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise UnsafePath("El bloqueo del repositorio es un enlace") from exc
            raise
        if not stat.S_ISREG(os.fstat(lock).st_mode):
            raise UnsafePath("El bloqueo no es un archivo regular")
        fcntl.flock(lock, fcntl.LOCK_EX)
        inspect_tree(root)
        if set(os.listdir(root)) - {".lock", "snapshots", ".staging"}:
            raise BackupError("El repositorio contiene entradas ajenas al formato")
        snapshots = open_directory_at(root, "snapshots", create=initialize)
        staging = open_directory_at(root, ".staging", create=initialize)
        os.fsync(root)
        yield root, snapshots, staging
    finally:
        for fd in (staging, snapshots, lock, root):
            if fd is not None:
                os.close(fd)


def source_inventory(root):
    directories, files = [], []

    def visit(directory, prefix):
        for name in sorted(os.listdir(directory)):
            path = prefix + name
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                directories.append(path)
                child = open_directory_at(directory, name)
                try:
                    visit(child, path + "/")
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode):
                files.append(path)
            else:
                raise UnsafePath("Enlace o archivo especial en fuente: " + path)

    visit(root, "")
    return sorted(directories), sorted(files)


def open_relative_file(root, path):
    parts = path.split("/")
    directory = os.dup(root)
    try:
        for part in parts[:-1]:
            child = open_directory_at(directory, part)
            os.close(directory)
            directory = child
        return open_regular(directory, parts[-1])
    finally:
        os.close(directory)


def digest_stream(source, destination=None, budget=None):
    digest, size = hashlib.sha256(), 0
    while True:
        block = os.read(source, CHUNK)
        if not block:
            break
        digest.update(block)
        size += len(block)
        if destination is not None:
            if budget is not None:
                budget.charge(len(block))
            view = memoryview(block)
            while view:
                written = os.write(destination, view)
                if written <= 0:
                    raise BackupError("Escritura incompleta")
                view = view[written:]
    if destination is not None:
        os.fsync(destination)
    return size, digest.hexdigest()


def write_bytes(directory, name, content, budget=None):
    if budget is not None:
        budget.charge(len(content))
    fd = open_regular(directory, name, write=True)
    try:
        view = memoryview(content)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise BackupError("Escritura incompleta")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def read_bytes(directory, name):
    fd = open_regular(directory, name)
    try:
        with os.fdopen(fd, "rb", closefd=False) as stream:
            return stream.read()
    finally:
        os.close(fd)


def blob_name(index):
    return f"{index:016x}"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidSnapshot("Clave duplicada en manifiesto")
        result[key] = value
    return result


def valid_relative(path):
    return (isinstance(path, str) and bool(path) and "\0" not in path and
            all(part not in ("", ".", "..") for part in path.split("/")))


def validate_manifest(manifest, snapshot_id):
    if (type(manifest) is not dict or
            set(manifest) != {"format", "id", "directories", "files"} or
            type(manifest["format"]) is not int or manifest["format"] != 1 or
            manifest["id"] != snapshot_id or
            type(manifest["directories"]) is not list or
            type(manifest["files"]) is not list):
        raise InvalidSnapshot("Formato o identidad de manifiesto inválidos")
    directories = manifest["directories"]
    if not all(valid_relative(path) for path in directories):
        raise InvalidSnapshot("Ruta de directorio inválida")
    if directories != sorted(set(directories)):
        raise InvalidSnapshot("Directorios duplicados o desordenados")
    directory_set, file_paths = set(directories), []
    for item in manifest["files"]:
        if (type(item) is not dict or set(item) != {"path", "size", "sha256"} or
                not valid_relative(item["path"]) or
                type(item["size"]) is not int or item["size"] < 0 or
                not isinstance(item["sha256"], str) or
                not HASH_RE.fullmatch(item["sha256"])):
            raise InvalidSnapshot("Registro de archivo inválido")
        file_paths.append(item["path"])
    if file_paths != sorted(set(file_paths)) or directory_set.intersection(file_paths):
        raise InvalidSnapshot("Rutas duplicadas o incompatibles")
    for path in directories + file_paths:
        parent = path.rpartition("/")[0]
        if parent and parent not in directory_set:
            raise InvalidSnapshot("Directorio padre ausente en manifiesto")


def validate_snapshot(directory, snapshot_id):
    """Comprueba metadatos, estructura exacta y cada byte de datos."""
    try:
        if set(os.listdir(directory)) != {"manifest.json", "manifest.sha256", "data"}:
            raise InvalidSnapshot("Estructura de snapshot incompleta o inesperada")
        content = read_bytes(directory, "manifest.json")
        seal = read_bytes(directory, "manifest.sha256")
        if seal != (hashlib.sha256(content).hexdigest() + "\n").encode("ascii"):
            raise InvalidSnapshot("Checksum del manifiesto incorrecto")
        try:
            manifest = json.loads(content.decode("utf-8"), object_pairs_hook=unique_object)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise InvalidSnapshot("Manifiesto ilegible") from exc
        validate_manifest(manifest, snapshot_id)
        data = open_directory_at(directory, "data")
        try:
            expected = {blob_name(index) for index in range(len(manifest["files"]))}
            if set(os.listdir(data)) != expected:
                raise InvalidSnapshot("Archivos de datos ausentes o inesperados")
            for index, item in enumerate(manifest["files"]):
                fd = open_regular(data, blob_name(index))
                try:
                    size, digest = digest_stream(fd)
                finally:
                    os.close(fd)
                if size != item["size"] or digest != item["sha256"]:
                    raise InvalidSnapshot("Datos corruptos: " + item["path"])
        finally:
            os.close(data)
        return manifest
    except UnsafePath:
        raise
    except InvalidSnapshot:
        raise
    except (OSError, BackupError) as exc:
        raise InvalidSnapshot("Snapshot incompleto o inválido: " + str(exc)) from exc


def open_snapshot(snapshots, snapshot_id):
    try:
        return open_directory_at(snapshots, snapshot_id)
    except FileNotFoundError as exc:
        raise InvalidSnapshot("ID inexistente: " + snapshot_id) from exc


def create(source_path, repo_path, snapshot_id, max_bytes=None):
    check_id(snapshot_id)
    if max_bytes is not None and (type(max_bytes) is not int or max_bytes < 0):
        raise BackupError("--max-bytes debe ser un entero no negativo")
    if overlap(source_path, repo_path):
        raise BackupError("Fuente y repositorio solapados")
    source = open_directory(source_path)
    try:
        directories, paths = source_inventory(source)
        # Comprobar ancestros antes de crear directorios del repositorio.
        probe = open_directory(repo_path, missing_ok=True)
        if probe is not None:
            os.close(probe)
        with repository(repo_path, initialize=True) as (root, snapshots, staging):
            if snapshot_id in os.listdir(snapshots):
                raise BackupError("El ID ya existe: " + snapshot_id)
            for abandoned in os.listdir(staging):
                remove_tree(staging, abandoned)
            os.fsync(staging)
            # El bloqueo abarca limpieza, conteo, escrituras y publicación.
            budget = ByteBudget(max_bytes, inspect_tree(root))
            name = "create-" + uuid.uuid4().hex
            os.mkdir(name, mode=0o700, dir_fd=staging)
            temporary = open_directory_at(staging, name)
            published = False
            try:
                data = open_directory_at(temporary, "data", create=True)
                records = []
                try:
                    for index, path in enumerate(paths):
                        input_fd = open_relative_file(source, path)
                        try:
                            output_fd = open_regular(data, blob_name(index), write=True)
                            try:
                                size, digest = digest_stream(input_fd, output_fd, budget)
                            finally:
                                os.close(output_fd)
                        finally:
                            os.close(input_fd)
                        records.append({"path": path, "size": size, "sha256": digest})
                    os.fsync(data)
                finally:
                    os.close(data)
                manifest = {"format": 1, "id": snapshot_id,
                            "directories": directories, "files": records}
                content = (json.dumps(manifest, ensure_ascii=True, sort_keys=True,
                                      separators=(",", ":")) + "\n").encode("utf-8")
                write_bytes(temporary, "manifest.json", content, budget)
                write_bytes(temporary, "manifest.sha256",
                            (hashlib.sha256(content).hexdigest() + "\n").encode("ascii"),
                            budget)
                os.fsync(temporary)
                validate_snapshot(temporary, snapshot_id)
                # Staging ya incluye todos los bytes que quedarán publicados;
                # el renombrado no agrega archivos ni metadata persistente.
                if max_bytes is not None and inspect_tree(root) > max_bytes:
                    raise BackupError("El repositorio supera --max-bytes antes de publicar")
                os.rename(name, snapshot_id, src_dir_fd=staging, dst_dir_fd=snapshots)
                published = True
                os.fsync(snapshots)
                os.fsync(staging)
            finally:
                os.close(temporary)
                if not published:
                    remove_tree(staging, name)
        return {"id": snapshot_id}
    finally:
        os.close(source)


def verify(repo_path, snapshot_id):
    check_id(snapshot_id)
    with repository(repo_path) as (_, snapshots, _staging):
        snapshot = open_snapshot(snapshots, snapshot_id)
        try:
            validate_snapshot(snapshot, snapshot_id)
        finally:
            os.close(snapshot)
    return {"id": snapshot_id, "valid": True}


def list_snapshots(repo_path):
    result = []
    with repository(repo_path, initialize=True) as (_, snapshots, _staging):
        for snapshot_id in sorted(os.listdir(snapshots)):
            if not ID_RE.fullmatch(snapshot_id):
                continue
            snapshot = None
            try:
                snapshot = open_snapshot(snapshots, snapshot_id)
                validate_snapshot(snapshot, snapshot_id)
            except UnsafePath:
                raise
            except (InvalidSnapshot, OSError):
                continue
            finally:
                if snapshot is not None:
                    os.close(snapshot)
            result.append(snapshot_id)
    return {"snapshots": result}


def destination_state(path):
    directory = open_directory(path, missing_ok=True)
    if directory is None:
        return None
    try:
        if os.listdir(directory):
            raise BackupError("El destino preexistente no está vacío")
        info = os.fstat(directory)
        return info.st_dev, info.st_ino
    finally:
        os.close(directory)


def make_relative_directory(root, path):
    directory = os.dup(root)
    try:
        for part in path.split("/"):
            child = open_directory_at(directory, part, create=True)
            os.close(directory)
            directory = child
        os.fsync(directory)
    finally:
        os.close(directory)


def restored_file_parent(root, path):
    directory = os.dup(root)
    try:
        for part in path.split("/")[:-1]:
            child = open_directory_at(directory, part)
            os.close(directory)
            directory = child
        return directory
    except BaseException:
        os.close(directory)
        raise


def sync_tree(root):
    for name in os.listdir(root):
        info = os.stat(name, dir_fd=root, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            child = open_directory_at(root, name)
            try:
                sync_tree(child)
            finally:
                os.close(child)
    os.fsync(root)


def restore(repo_path, snapshot_id, dest_path):
    check_id(snapshot_id)
    if overlap(repo_path, dest_path):
        raise BackupError("Destino y repositorio solapados")
    original_state = destination_state(dest_path)
    dest = absolute(dest_path)
    with repository(repo_path) as (_, snapshots, _staging):
        snapshot = open_snapshot(snapshots, snapshot_id)
        try:
            manifest = validate_snapshot(snapshot, snapshot_id)
            # No se crean temporales ni padres de destino antes de validar.
            parent = open_directory(os.path.dirname(dest), create=True)
            name = ".backup-restore-" + uuid.uuid4().hex
            temporary = None
            published = False
            try:
                os.mkdir(name, mode=0o700, dir_fd=parent)
                temporary = open_directory_at(parent, name)
                for path in manifest["directories"]:
                    make_relative_directory(temporary, path)
                data = open_directory_at(snapshot, "data")
                try:
                    for index, item in enumerate(manifest["files"]):
                        input_fd = open_regular(data, blob_name(index))
                        output_parent = None
                        try:
                            output_parent = restored_file_parent(temporary, item["path"])
                            output_fd = open_regular(output_parent,
                                                     item["path"].split("/")[-1], write=True)
                            try:
                                size, digest = digest_stream(input_fd, output_fd)
                            finally:
                                os.close(output_fd)
                            if size != item["size"] or digest != item["sha256"]:
                                raise InvalidSnapshot("Datos cambiaron durante restore")
                        finally:
                            os.close(input_fd)
                            if output_parent is not None:
                                os.close(output_parent)
                finally:
                    os.close(data)
                sync_tree(temporary)
                if destination_state(dest_path) != original_state:
                    raise BackupError("El destino cambió durante restore")
                os.rename(name, os.path.basename(dest), src_dir_fd=parent, dst_dir_fd=parent)
                published = True
                os.fsync(parent)
            finally:
                if temporary is not None:
                    os.close(temporary)
                    if not published:
                        remove_tree(parent, name)
                os.close(parent)
        finally:
            os.close(snapshot)
    return {"id": snapshot_id}


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
            command.add_argument("--max-bytes", type=parse_max_bytes,
                                 help="máximo de bytes regulares del repo, incluida metadata")
        if name == "restore":
            command.add_argument("--dest", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            result = create(args.source, args.repo, args.id, args.max_bytes)
        elif args.command == "verify":
            result = verify(args.repo, args.id)
        elif args.command == "restore":
            result = restore(args.repo, args.id, args.dest)
        else:
            result = list_snapshots(args.repo)
    except (BackupError, OSError, ValueError, RecursionError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"error": "Operación interrumpida"}), file=sys.stderr)
        return 130
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
