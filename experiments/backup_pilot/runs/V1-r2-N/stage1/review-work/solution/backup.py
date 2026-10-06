#!/usr/bin/env python3
"""Self-contained, checksummed directory snapshots (Python 3.12, stdlib)."""

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


ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", re.ASCII)
HASH_PATTERN = re.compile(r"[0-9a-f]{64}", re.ASCII)
BLOCK_SIZE = 1024 * 1024


class BackupError(Exception):
    """An operation could not meet the backup contract."""


def check_id(value):
    if not isinstance(value, str) or ID_PATTERN.fullmatch(value) is None:
        raise BackupError("ID inválido: use [A-Za-z0-9][A-Za-z0-9_-]{0,63}")
    return value


def directory_path(value):
    """Normalize a directory path, inspecting even components before '..'."""
    if not value or "\0" in value:
        raise BackupError("Ruta de directorio inválida")
    raw = value if os.path.isabs(value) else str(Path.cwd()) + "/" + value
    current = Path("/")
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            current = current.parent
            continue
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise BackupError(f"Symlink rechazado: {current}")
        if not stat.S_ISDIR(info.st_mode):
            raise BackupError(f"Se requiere un directorio: {current}")
    return current


def require_directory(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise BackupError(f"Se requiere un directorio sin symlinks: {path}")


def reject_overlap(first, second):
    common = Path(os.path.commonpath((first, second)))
    if common == first or common == second:
        raise BackupError(f"Directorios solapados: {first} y {second}")


def inventory(root):
    """Return every relative entry; never intentionally traverse a link."""
    require_directory(root)
    result = {}
    pending = [(root, "")]
    while pending:
        directory, prefix = pending.pop()
        require_directory(directory)
        with os.scandir(directory) as entries:
            children = sorted(entries, key=lambda entry: entry.name)
        for entry in children:
            relative = prefix + entry.name
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                raise BackupError(f"Symlink rechazado: {root / relative}")
            if stat.S_ISDIR(info.st_mode):
                result[relative] = "dir"
                pending.append((root / relative, relative + "/"))
            elif stat.S_ISREG(info.st_mode):
                result[relative] = "file"
            else:
                raise BackupError(f"Archivo especial rechazado: {root / relative}")
    return result


def open_regular(path):
    # NONBLOCK avoids blocking on a FIFO substituted between inspection/open.
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise BackupError(f"Se requiere un archivo regular: {path}")
        stream = os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise
    return stream


def new_regular(path):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    return os.fdopen(descriptor, "wb")


def read_regular(path):
    with open_regular(path) as stream:
        return stream.read()


def write_regular(path, data):
    with new_regular(path) as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def digest_file(source, destination=None):
    """Hash all bytes, optionally copying to a newly created file."""
    digest = hashlib.sha256()
    size = 0
    with open_regular(source) as original:
        if destination is None:
            while block := original.read(BLOCK_SIZE):
                digest.update(block)
                size += len(block)
        else:
            with new_regular(destination) as copied:
                while block := original.read(BLOCK_SIZE):
                    copied.write(block)
                    digest.update(block)
                    size += len(block)
                copied.flush()
                os.fsync(copied.fileno())
    return size, digest.hexdigest()


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def sync_tree_directories(root, entries):
    directories = [name for name, kind in entries.items() if kind == "dir"]
    for name in sorted(directories, key=lambda name: name.count("/"), reverse=True):
        sync_directory(root / name)
    sync_directory(root)


def check_repository(repo):
    """Allow an empty/missing repo and unfinished private staging directories."""
    try:
        repo.lstat()
    except FileNotFoundError:
        return False
    entries = inventory(repo)
    for name, kind in entries.items():
        parts = name.split("/")
        if parts[0] not in ("snapshots", ".staging"):
            raise BackupError(f"Entrada desconocida en repositorio: {name}")
        if len(parts) == 1 and kind != "dir":
            raise BackupError(f"Directorio de repositorio inválido: {name}")
        if parts[0] == "snapshots" and len(parts) == 2:
            check_id(parts[1])
            if kind != "dir":
                raise BackupError(f"Snapshot no es un directorio: {name}")
    return True


def prepare_repository(repo):
    repo.mkdir(mode=0o700, parents=True, exist_ok=True)
    require_directory(repo)
    for name in ("snapshots", ".staging"):
        (repo / name).mkdir(mode=0o700, exist_ok=True)
        require_directory(repo / name)
    sync_directory(repo)


def relative_name(value):
    if not isinstance(value, str) or not value or "\0" in value:
        raise BackupError("Ruta inválida en manifiesto")
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise BackupError("Ruta insegura en manifiesto")
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackupError("Claves duplicadas en manifiesto")
        result[key] = value
    return result


def load_snapshot(snapshot, verify_bytes=True):
    actual = inventory(snapshot)
    if actual.get("manifest.json") != "file" or actual.get("manifest.sha256") != "file":
        raise BackupError("Snapshot incompleto: falta manifiesto o checksum")
    manifest_bytes = read_regular(snapshot / "manifest.json")
    checksum = read_regular(snapshot / "manifest.sha256")
    expected_checksum = (hashlib.sha256(manifest_bytes).hexdigest() + "\n").encode("ascii")
    if checksum != expected_checksum:
        raise BackupError("Checksum del manifiesto incorrecto")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"), object_pairs_hook=unique_object)
    except (ValueError, UnicodeError) as error:
        raise BackupError("Manifiesto JSON inválido") from error
    if not isinstance(manifest, dict) or set(manifest) != {"version", "directories", "files"}:
        raise BackupError("Formato de manifiesto inválido")
    if type(manifest["version"]) is not int or manifest["version"] != 1:
        raise BackupError("Versión de manifiesto no admitida")
    if not isinstance(manifest["directories"], list) or not isinstance(manifest["files"], list):
        raise BackupError("Listas del manifiesto inválidas")
    directories = set()
    files = {}
    for value in manifest["directories"]:
        name = relative_name(value)
        if name in directories:
            raise BackupError("Directorio duplicado en manifiesto")
        directories.add(name)
    for record in manifest["files"]:
        if not isinstance(record, dict) or set(record) != {"path", "size", "sha256"}:
            raise BackupError("Registro de archivo inválido")
        name = relative_name(record["path"])
        if name in files or name in directories:
            raise BackupError("Ruta duplicada en manifiesto")
        if type(record["size"]) is not int or record["size"] < 0:
            raise BackupError("Tamaño de archivo inválido")
        if not isinstance(record["sha256"], str) or HASH_PATTERN.fullmatch(record["sha256"]) is None:
            raise BackupError("Hash de archivo inválido")
        files[name] = record
    for name in directories | files.keys():
        parts = name.split("/")
        for index in range(1, len(parts)):
            if "/".join(parts[:index]) not in directories:
                raise BackupError("Falta un directorio padre en manifiesto")
    expected = {"manifest.json": "file", "manifest.sha256": "file", "tree": "dir"}
    expected.update({"tree/" + name: "dir" for name in directories})
    expected.update({"tree/" + name: "file" for name in files})
    if actual != expected:
        raise BackupError("El árbol del snapshot no coincide con el manifiesto")
    if verify_bytes:
        for name, record in files.items():
            size, digest = digest_file(snapshot / "tree" / name)
            if size != record["size"] or digest != record["sha256"]:
                raise BackupError(f"Archivo corrupto: {name}")
    return directories, files


def create(source_value, repo_value, identifier):
    check_id(identifier)
    source = directory_path(source_value)
    repo = directory_path(repo_value)
    reject_overlap(source, repo)
    source_entries = inventory(source)
    check_repository(repo)
    snapshot = repo / "snapshots" / identifier
    if snapshot.exists():
        raise BackupError("El ID ya existe; no se sobrescribe")
    prepare_repository(repo)
    temporary = Path(tempfile.mkdtemp(prefix=f"create-{identifier}-", dir=repo / ".staging"))
    try:
        tree = temporary / "tree"
        tree.mkdir(mode=0o700)
        directories = sorted(name for name, kind in source_entries.items() if kind == "dir")
        for name in directories:
            (tree / name).mkdir(mode=0o700)
        records = []
        for name in sorted(name for name, kind in source_entries.items() if kind == "file"):
            size, digest = digest_file(source / name, tree / name)
            records.append({"path": name, "size": size, "sha256": digest})
        manifest = {"version": 1, "directories": directories, "files": records}
        encoded = (json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        write_regular(temporary / "manifest.json", encoded)
        write_regular(temporary / "manifest.sha256", (hashlib.sha256(encoded).hexdigest() + "\n").encode("ascii"))
        # Re-read stored bytes before declaring the staging tree publishable.
        load_snapshot(temporary)
        sync_tree_directories(tree, source_entries)
        sync_directory(temporary)
        if snapshot.exists():
            raise BackupError("El ID ya existe; no se sobrescribe")
        os.rename(temporary, snapshot)
        sync_directory(repo / "snapshots")
        sync_directory(repo / ".staging")
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {"id": identifier}


def verify(repo_value, identifier):
    check_id(identifier)
    repo = directory_path(repo_value)
    check_repository(repo)
    load_snapshot(repo / "snapshots" / identifier)
    return {"id": identifier, "valid": True}


def check_destination(destination):
    try:
        destination.lstat()
    except FileNotFoundError:
        return
    require_directory(destination)
    with os.scandir(destination) as entries:
        if next(entries, None) is not None:
            raise BackupError("El destino preexistente no está vacío")


def restore(repo_value, identifier, dest_value):
    check_id(identifier)
    repo = directory_path(repo_value)
    destination = directory_path(dest_value)
    reject_overlap(repo, destination)
    check_repository(repo)
    check_destination(destination)
    snapshot = repo / "snapshots" / identifier
    # Data is hashed while copying; no restoration is published before all match.
    directories, files = load_snapshot(snapshot, verify_bytes=False)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".backup-restore-", dir=destination.parent))
    try:
        for name in sorted(directories):
            (temporary / name).mkdir(mode=0o700)
        for name, record in files.items():
            size, digest = digest_file(snapshot / "tree" / name, temporary / name)
            if size != record["size"] or digest != record["sha256"]:
                raise BackupError(f"Archivo corrupto: {name}")
        entries = {name: "dir" for name in directories}
        sync_tree_directories(temporary, entries)
        check_destination(destination)
        # POSIX rename can replace an existing empty directory atomically.
        os.rename(temporary, destination)
        sync_directory(destination.parent)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {"id": identifier}


def list_snapshots(repo_value):
    repo = directory_path(repo_value)
    if not check_repository(repo) or not (repo / "snapshots").exists():
        return {"snapshots": []}
    identifiers = []
    for snapshot in sorted((repo / "snapshots").iterdir()):
        try:
            load_snapshot(snapshot)
        except (BackupError, FileNotFoundError):
            continue
        identifiers.append(snapshot.name)
    return {"snapshots": identifiers}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise BackupError(message)


def main():
    parser = Parser(description="Backup verificable de archivos y directorios")
    commands = parser.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser("create")
    create_parser.add_argument("--source", required=True)
    create_parser.add_argument("--repo", required=True)
    create_parser.add_argument("--id", required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--repo", required=True)
    verify_parser.add_argument("--id", required=True)
    restore_parser = commands.add_parser("restore")
    restore_parser.add_argument("--repo", required=True)
    restore_parser.add_argument("--id", required=True)
    restore_parser.add_argument("--dest", required=True)
    list_parser = commands.add_parser("list")
    list_parser.add_argument("--repo", required=True)
    try:
        arguments = parser.parse_args()
        if arguments.command == "create":
            result = create(arguments.source, arguments.repo, arguments.id)
        elif arguments.command == "verify":
            result = verify(arguments.repo, arguments.id)
        elif arguments.command == "restore":
            result = restore(arguments.repo, arguments.id, arguments.dest)
        else:
            result = list_snapshots(arguments.repo)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except (BackupError, OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"error": "Operación interrumpida"}), file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
