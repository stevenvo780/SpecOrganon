#!/usr/bin/env python3
"""Self-contained, verified directory snapshots (Python 3.12, POSIX)."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import uuid
from contextlib import contextmanager


ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
STAGE_RE = re.compile(r"create-[0-9a-f]{32}\Z")
OBJECT_RE = re.compile(r"[0-9a-f]{16}\Z")
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
WRITE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
CHUNK = 1024 * 1024


class BackupError(Exception):
    pass


class ByteBudget:
    """Remaining regular-file bytes, including persistent metadata."""

    def __init__(self, remaining):
        self.remaining = remaining

    def charge(self, size):
        if self.remaining is not None:
            require(size <= self.remaining, "El repositorio excedería --max-bytes")
            self.remaining -= size


def require(condition, message):
    if not condition:
        raise BackupError(message)


def check_id(snapshot_id):
    require(ID_RE.fullmatch(snapshot_id) is not None, "ID inválido")


@contextmanager
def owned_fd(fd):
    try:
        yield fd
    finally:
        os.close(fd)


def open_path(path, *, create=False, missing_ok=False):
    """Walk every supplied component, including those before '..', without links."""
    require(bool(path) and "\x00" not in path, "Ruta inválida")
    raw = path if os.path.isabs(path) else os.getcwd() + "/" + path
    fd = os.open("/", DIR_FLAGS)
    try:
        for name in raw.split("/"):
            if not name or name == ".":
                continue
            try:
                child = os.open(name, DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                if create:
                    try:
                        os.mkdir(name, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                    child = os.open(name, DIR_FLAGS, dir_fd=fd)
                elif missing_ok:
                    os.close(fd)
                    return None
                else:
                    raise
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def checked_path(path):
    # Check the spelling first; abspath alone could hide a symlink before '..'.
    fd = open_path(path, missing_ok=True)
    if fd is not None:
        os.close(fd)
    canonical = os.path.abspath(path)
    fd = open_path(canonical, missing_ok=True)
    if fd is not None:
        os.close(fd)
    return canonical


def overlaps(first, second):
    common = os.path.commonpath((first, second))
    return common == first or common == second


def kind_at(parent, name):
    return os.stat(name, dir_fd=parent, follow_symlinks=False).st_mode


def entries(parent):
    with os.scandir(parent) as scan:
        return sorted((entry.name for entry in scan))


def check_tree(parent):
    """Reject links/special files and sum st_size of EVERY regular file."""
    total = 0
    for name in entries(parent):
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            with owned_fd(os.open(name, DIR_FLAGS, dir_fd=parent)) as child:
                total += check_tree(child)
        else:
            require(stat.S_ISREG(info.st_mode), "Symlink o archivo especial en árbol gestionado")
            total += info.st_size
    return total


def ensure_subdir(parent, name):
    try:
        os.mkdir(name, 0o700, dir_fd=parent)
        os.fsync(parent)
    except FileExistsError:
        pass
    return os.open(name, DIR_FLAGS, dir_fd=parent)


def open_regular(parent, name):
    require(stat.S_ISREG(kind_at(parent, name)), "Se esperaba un archivo regular")
    fd = os.open(name, READ_FLAGS, dir_fd=parent)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise BackupError("Se esperaba un archivo regular")
    return fd


def write_all(fd, data):
    pending = memoryview(data)
    while pending:
        count = os.write(fd, pending)
        require(count > 0, "Escritura incompleta")
        pending = pending[count:]


def stream_file(reader, writer=None, budget=None):
    digest = hashlib.sha256()
    size = 0
    while True:
        block = os.read(reader, CHUNK)
        if not block:
            break
        digest.update(block)
        size += len(block)
        if writer is not None:
            if budget is not None:
                budget.charge(len(block))
            write_all(writer, block)
    if writer is not None:
        os.fsync(writer)
    return size, digest.hexdigest()


def copy_source(source, objects, records, parts=(), budget=None):
    for name in entries(source):
        path = parts + (name,)
        mode = kind_at(source, name)
        if stat.S_ISDIR(mode):
            records.append({"path": list(path), "type": "dir"})
            with owned_fd(os.open(name, DIR_FLAGS, dir_fd=source)) as child:
                copy_source(child, objects, records, path, budget)
        elif stat.S_ISREG(mode):
            object_name = f"{len(records):016x}"
            with owned_fd(open_regular(source, name)) as reader:
                with owned_fd(os.open(object_name, WRITE_FLAGS, 0o600, dir_fd=objects)) as writer:
                    size, digest = stream_file(reader, writer, budget)
            records.append({"path": list(path), "type": "file", "object": object_name,
                            "size": size, "sha256": digest})
        else:
            raise BackupError("Symlink o archivo especial en fuente")


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Clave duplicada en manifiesto")
        result[key] = value
    return result


def read_manifest(snapshot, snapshot_id):
    names = entries(snapshot)
    require(set(names) == {"objects", "manifest.json", "manifest.sha256"},
            "Snapshot incompleto o estructura inválida")
    with owned_fd(open_regular(snapshot, "manifest.json")) as fd:
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read()
    with owned_fd(open_regular(snapshot, "manifest.sha256")) as fd:
        with os.fdopen(os.dup(fd), "rb") as stream:
            checksum = stream.read(66)
    expected = (hashlib.sha256(raw).hexdigest() + "\n").encode("ascii")
    require(checksum == expected, "Manifiesto o checksum corrupto")
    try:
        document = json.loads(raw, object_pairs_hook=unique_keys)
    except (ValueError, UnicodeError) as exc:
        raise BackupError("Manifiesto ilegible") from exc
    require(type(document) is dict and set(document) == {"format", "id", "entries"},
            "Formato de manifiesto inválido")
    require(type(document["format"]) is int and document["format"] == 2 and
            document["id"] == snapshot_id and type(document["entries"]) is list,
            "Versión o ID de manifiesto inválido")
    paths = {}
    objects = set()
    for record in document["entries"]:
        require(type(record) is dict, "Entrada de manifiesto inválida")
        path = record.get("path")
        require(type(path) is list and len(path) > 0, "Ruta de manifiesto inválida")
        require(all(type(part) is str and part not in ("", ".", "..") and
                    "/" not in part and "\x00" not in part for part in path),
                "Ruta de manifiesto insegura")
        path = tuple(path)
        require(path not in paths, "Ruta duplicada")
        record_type = record.get("type")
        if record_type == "dir":
            require(set(record) == {"path", "type"}, "Directorio inválido")
        elif record_type == "file":
            require(set(record) == {"path", "type", "object", "size", "sha256"},
                    "Archivo inválido")
            object_name = record["object"]
            require(type(object_name) is str and OBJECT_RE.fullmatch(object_name) is not None,
                    "Nombre de objeto inválido")
            require(object_name not in objects, "Objeto duplicado")
            require(type(record["size"]) is int and record["size"] >= 0 and
                    type(record["sha256"]) is str and HASH_RE.fullmatch(record["sha256"]) is not None,
                    "Tamaño o hash inválido")
            objects.add(object_name)
        else:
            raise BackupError("Tipo de entrada inválido")
        paths[path] = record_type
    for path in paths:
        require(all(paths.get(path[:length]) == "dir" for length in range(1, len(path))),
                "Directorio padre ausente o inválido")
    return document["entries"], objects


def verify_snapshot(snapshot, snapshot_id):
    records, expected_objects = read_manifest(snapshot, snapshot_id)
    with owned_fd(os.open("objects", DIR_FLAGS, dir_fd=snapshot)) as objects:
        require(set(entries(objects)) == expected_objects, "Objetos ausentes o adicionales")
        for record in records:
            if record["type"] == "file":
                with owned_fd(open_regular(objects, record["object"])) as reader:
                    size, digest = stream_file(reader)
                require(size == record["size"] and digest == record["sha256"],
                        "Datos del snapshot corruptos")
    return records


def exists_at(parent, name):
    try:
        kind_at(parent, name)
        return True
    except FileNotFoundError:
        return False


def remove_stage(parent, name):
    # Python 3.12 uses descriptor-based traversal here and never follows links.
    if exists_at(parent, name):
        shutil.rmtree(name, dir_fd=parent)


def reclaim_stages(repo):
    """Called under the exclusive repository lock: no live creator owns a stage."""
    if exists_at(repo, ".staging"):
        with owned_fd(os.open(".staging", DIR_FLAGS, dir_fd=repo)) as staging:
            for name in entries(staging):
                if STAGE_RE.fullmatch(name):
                    require(stat.S_ISDIR(kind_at(staging, name)), "Etapa inválida")
                    remove_stage(staging, name)
            os.fsync(staging)


def create(source_path, repo_path, snapshot_id, max_bytes=None):
    check_id(snapshot_id)
    require(max_bytes is None or (type(max_bytes) is int and max_bytes >= 0),
            "--max-bytes debe ser un entero no negativo")
    source_path = checked_path(source_path)
    repo_path = checked_path(repo_path)
    require(not overlaps(source_path, repo_path), "Fuente y repositorio se solapan")
    with owned_fd(open_path(source_path)) as source:
        check_tree(source)
        with repository(repo_path, create=True, exclusive=True) as repo:
            reclaim_stages(repo)
            existing_bytes = check_tree(repo)
            require(max_bytes is None or existing_bytes <= max_bytes,
                    "El repositorio existente supera --max-bytes")
            budget = ByteBudget(None if max_bytes is None else max_bytes - existing_bytes)
            with owned_fd(ensure_subdir(repo, "snapshots")) as snapshots:
                require(not exists_at(snapshots, snapshot_id), "El ID ya existe")
                with owned_fd(ensure_subdir(repo, ".staging")) as staging:
                    stage_name = "create-" + uuid.uuid4().hex
                    os.mkdir(stage_name, 0o700, dir_fd=staging)
                    try:
                        with owned_fd(os.open(stage_name, DIR_FLAGS, dir_fd=staging)) as stage:
                            with owned_fd(ensure_subdir(stage, "objects")) as objects:
                                records = []
                                copy_source(source, objects, records, (), budget)
                                os.fsync(objects)
                            raw = json.dumps({"format": 2, "id": snapshot_id, "entries": records},
                                             ensure_ascii=True, sort_keys=True,
                                             separators=(",", ":")).encode("ascii")
                            checksum = (hashlib.sha256(raw).hexdigest() + "\n").encode("ascii")
                            for name, content in (("manifest.json", raw),
                                                  ("manifest.sha256", checksum)):
                                budget.charge(len(content))
                                with owned_fd(os.open(name, WRITE_FLAGS, 0o600, dir_fd=stage)) as fd:
                                    write_all(fd, content)
                                    os.fsync(fd)
                            verify_snapshot(stage, snapshot_id)
                            os.fsync(stage)
                        require(not exists_at(snapshots, snapshot_id), "El ID ya existe")
                        # This includes stages, unrelated regular files and all metadata.
                        # Rename only changes a pathname, so it cannot change this sum.
                        final_bytes = check_tree(repo)
                        require(max_bytes is None or final_bytes <= max_bytes,
                                "El repositorio excedería --max-bytes")
                        os.rename(stage_name, snapshot_id, src_dir_fd=staging, dst_dir_fd=snapshots)
                        os.fsync(snapshots)
                        os.fsync(staging)
                    finally:
                        remove_stage(staging, stage_name)
                        os.fsync(staging)
    return {"id": snapshot_id}


@contextmanager
def repository(repo_path, *, create=False, exclusive=False):
    repo_path = checked_path(repo_path)
    with owned_fd(open_path(repo_path, create=create)) as repo:
        # The lock is kernel state, released even by SIGKILL; no lock file or
        # persistent metadata is hidden outside the regular-file byte count.
        fcntl.flock(repo, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        check_tree(repo)
        yield repo


def verify(repo_path, snapshot_id):
    check_id(snapshot_id)
    with repository(repo_path) as repo:
        with owned_fd(os.open("snapshots", DIR_FLAGS, dir_fd=repo)) as snapshots:
            with owned_fd(os.open(snapshot_id, DIR_FLAGS, dir_fd=snapshots)) as snapshot:
                verify_snapshot(snapshot, snapshot_id)
    return {"id": snapshot_id, "valid": True}


def list_snapshots(repo_path):
    repo_path = checked_path(repo_path)
    repo_fd = open_path(repo_path, missing_ok=True)
    if repo_fd is None:
        return {"snapshots": []}
    result = []
    with owned_fd(repo_fd) as repo:
        fcntl.flock(repo, fcntl.LOCK_SH)
        check_tree(repo)
        if exists_at(repo, "snapshots"):
            with owned_fd(os.open("snapshots", DIR_FLAGS, dir_fd=repo)) as snapshots:
                for snapshot_id in entries(snapshots):
                    if ID_RE.fullmatch(snapshot_id) is None:
                        continue
                    try:
                        with owned_fd(os.open(snapshot_id, DIR_FLAGS, dir_fd=snapshots)) as snapshot:
                            verify_snapshot(snapshot, snapshot_id)
                    except (BackupError, OSError, ValueError, RecursionError):
                        continue
                    result.append(snapshot_id)
    return {"snapshots": result}


def destination_state(parent, name):
    if exists_at(parent, name):
        with owned_fd(os.open(name, DIR_FLAGS, dir_fd=parent)) as dest:
            require(not entries(dest), "El destino preexistente no está vacío")


def open_relative_dir(root, parts):
    fd = os.dup(root)
    try:
        for part in parts:
            child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def restore_records(snapshot, stage, records):
    # Parent directories are explicit; build them first, irrespective of manifest order.
    directories = sorted((tuple(r["path"]) for r in records if r["type"] == "dir"),
                         key=lambda path: (len(path), path))
    for path in directories:
        with owned_fd(open_relative_dir(stage, path[:-1])) as parent:
            os.mkdir(path[-1], 0o700, dir_fd=parent)
    with owned_fd(os.open("objects", DIR_FLAGS, dir_fd=snapshot)) as objects:
        for record in records:
            if record["type"] != "file":
                continue
            with owned_fd(open_relative_dir(stage, record["path"][:-1])) as parent:
                with owned_fd(open_regular(objects, record["object"])) as reader:
                    with owned_fd(os.open(record["path"][-1], WRITE_FLAGS, 0o600, dir_fd=parent)) as writer:
                        size, digest = stream_file(reader, writer)
                require(size == record["size"] and digest == record["sha256"],
                        "Datos corruptos durante restauración")
    for path in reversed(directories):
        with owned_fd(open_relative_dir(stage, path)) as directory:
            os.fsync(directory)
    os.fsync(stage)


def restore(repo_path, snapshot_id, dest_path):
    check_id(snapshot_id)
    repo_path = checked_path(repo_path)
    dest_path = checked_path(dest_path)
    require(not overlaps(repo_path, dest_path), "Destino y repositorio se solapan")
    parent_path, dest_name = os.path.split(dest_path)
    require(bool(dest_name), "Destino inválido")
    # A missing parent is allowed, but only created after validating all snapshot bytes.
    with repository(repo_path) as repo:
        with owned_fd(os.open("snapshots", DIR_FLAGS, dir_fd=repo)) as snapshots:
            with owned_fd(os.open(snapshot_id, DIR_FLAGS, dir_fd=snapshots)) as snapshot:
                records = verify_snapshot(snapshot, snapshot_id)
                with owned_fd(open_path(parent_path, create=True)) as parent:
                    destination_state(parent, dest_name)
                    stage_name = ".backup-restore-" + uuid.uuid4().hex
                    os.mkdir(stage_name, 0o700, dir_fd=parent)
                    try:
                        with owned_fd(os.open(stage_name, DIR_FLAGS, dir_fd=parent)) as stage:
                            restore_records(snapshot, stage, records)
                            # Recheck metadata and all objects before publication, too.
                            verify_snapshot(snapshot, snapshot_id)
                        destination_state(parent, dest_name)
                        os.rename(stage_name, dest_name, src_dir_fd=parent, dst_dir_fd=parent)
                        os.fsync(parent)
                    finally:
                        remove_stage(parent, stage_name)
    return {"id": snapshot_id}


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("create", "verify", "restore", "list"):
        command = commands.add_parser(name)
        command.add_argument("--repo", required=True)
        if name != "list":
            command.add_argument("--id", required=True)
        if name == "create":
            command.add_argument("--source", required=True)
            command.add_argument("--max-bytes", metavar="N")
        if name == "restore":
            command.add_argument("--dest", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "create":
            max_bytes = None
            if args.max_bytes is not None:
                require(re.fullmatch(r"[0-9]+", args.max_bytes) is not None,
                        "--max-bytes debe ser un entero no negativo")
                max_bytes = int(args.max_bytes)
            result = create(args.source, args.repo, args.id, max_bytes)
        elif args.command == "verify":
            result = verify(args.repo, args.id)
        elif args.command == "restore":
            result = restore(args.repo, args.id, args.dest)
        else:
            result = list_snapshots(args.repo)
    except (BackupError, OSError, ValueError, RecursionError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
