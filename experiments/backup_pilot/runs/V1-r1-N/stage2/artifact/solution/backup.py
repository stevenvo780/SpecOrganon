#!/usr/bin/env python3
"""Backups autosuficientes, comprobados y publicados de forma atómica."""

import argparse
import contextlib
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile


ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", re.ASCII)
DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}", re.ASCII)
CHUNK_SIZE = 1024 * 1024


class BackupError(Exception):
    """Error de entrada, estructura o integridad."""


def validate_id(value):
    if not isinstance(value, str) or ID_PATTERN.fullmatch(value) is None:
        raise BackupError("ID inválido")
    return value


def checked_directory(value, *, must_exist=False):
    """Comprueba también los ancestros y la ruta antes de normalizar '..'."""
    raw = os.fspath(value)
    if not raw or "\0" in raw:
        raise BackupError("Ruta de directorio inválida")
    if not os.path.isabs(raw):
        raw = os.path.join(os.getcwd(), raw)
    normalized = os.path.abspath(raw)
    for spelling in (raw, normalized):
        current = os.path.sep
        for component in spelling.split(os.path.sep):
            if not component:
                continue
            current = os.path.join(current, component)
            try:
                mode = os.lstat(current).st_mode
            except FileNotFoundError:
                continue
            if not stat.S_ISDIR(mode):
                raise BackupError(f"La ruta contiene un enlace o no es un directorio: {current}")
    result = Path(normalized)
    if must_exist and not result.exists():
        raise BackupError(f"Directorio inexistente: {result}")
    return result


def overlaps(left, right):
    common = os.path.commonpath((str(left), str(right)))
    return common in (str(left), str(right))


def walk_tree(root):
    """Iterador determinista; nunca sigue enlaces ni acepta archivos especiales."""
    pending = [(root, ())]
    while pending:
        directory, relative = pending.pop()
        with os.scandir(directory) as iterator:
            children = sorted(iterator, key=lambda entry: entry.name)
        subdirectories = []
        for entry in children:
            parts = relative + (entry.name,)
            mode = entry.stat(follow_symlinks=False).st_mode
            path = directory / entry.name
            if stat.S_ISDIR(mode):
                yield parts, "directory", path
                subdirectories.append((path, parts))
            elif stat.S_ISREG(mode):
                yield parts, "file", path
            else:
                raise BackupError(f"Enlace o archivo especial rechazado: {path}")
        pending.extend(reversed(subdirectories))


@contextlib.contextmanager
def read_regular(path):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise BackupError(f"Se esperaba un archivo regular: {path}")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            yield stream
    finally:
        if descriptor is not None:
            os.close(descriptor)


def hash_or_copy(path, output=None, *, max_bytes=None):
    digest = hashlib.sha256()
    size = 0
    with read_regular(path) as stream:
        while block := stream.read(CHUNK_SIZE):
            digest.update(block)
            size += len(block)
            if max_bytes is not None and size > max_bytes:
                raise BackupError("El snapshot supera --max-bytes")
            if output is not None:
                output.write(block)
    return size, digest.hexdigest()


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_bytes(path, value):
    with path.open("xb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


class Repository:
    """El bloqueo del directorio se libera incluso tras SIGKILL."""

    def __init__(self, root, *, create=False):
        self.root = root
        self.create = create
        self.snapshots = root / "snapshots"
        self.staging = root / ".staging"
        self.descriptor = None

    def __enter__(self):
        if self.create:
            self.root.mkdir(parents=True, exist_ok=True)
        checked_directory(self.root, must_exist=True)
        self.descriptor = os.open(
            self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
            fcntl.flock(self.descriptor, fcntl.LOCK_EX)
            self.check_safe()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None

    def check_safe(self):
        for _, _, _ in walk_tree(self.root):
            pass
        for entry in self.root.iterdir():
            if entry.name not in {"snapshots", ".staging"} or not entry.is_dir():
                raise BackupError(f"Entrada ajena al formato del repositorio: {entry}")

    def snapshot(self, identifier):
        path = self.snapshots / identifier
        if not path.is_dir():
            raise BackupError(f"Snapshot inexistente o incompleto: {identifier}")
        return path

    def regular_bytes(self):
        """Incluye todos los archivos regulares, también metadata y staging."""
        return sum(path.stat(follow_symlinks=False).st_size
                   for _, kind, path in walk_tree(self.root) if kind == "file")

    def clean_staging(self):
        # El bloqueo exclusivo prueba que ninguna otra operación está usando
        # estas copias sin publicar; SIGKILL libera automáticamente el bloqueo.
        if self.staging.exists():
            for path in self.staging.iterdir():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            sync_directory(self.staging)


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackupError("Claves duplicadas en el manifiesto")
        result[key] = value
    return result


def valid_parts(value):
    if not isinstance(value, list) or not value:
        raise BackupError("Ruta vacía o inválida en el manifiesto")
    for part in value:
        if (
            not isinstance(part, str)
            or part in {"", ".", ".."}
            or "\0" in part
            or os.path.sep in part
            or (os.path.altsep is not None and os.path.altsep in part)
        ):
            raise BackupError("Componente de ruta inválido en el manifiesto")
    return tuple(value)


def read_manifest(snapshot, identifier):
    with read_regular(snapshot / "manifest.json") as stream:
        raw = stream.read()
    with read_regular(snapshot / "manifest.sha256") as stream:
        seal = stream.read(66)
    expected_seal = (hashlib.sha256(raw).hexdigest() + "\n").encode("ascii")
    if not hmac.compare_digest(seal, expected_seal):
        raise BackupError("Manifiesto corrupto o sello inválido")
    try:
        manifest = json.loads(raw, object_pairs_hook=no_duplicate_keys)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise BackupError("Manifiesto ilegible") from exc
    if not isinstance(manifest, dict) or set(manifest) != {
        "version", "id", "directories", "files"
    }:
        raise BackupError("Formato de manifiesto inválido")
    if type(manifest["version"]) is not int or manifest["version"] != 1:
        raise BackupError("Versión de manifiesto inválida")
    if manifest["id"] != identifier:
        raise BackupError("ID del manifiesto incorrecto")
    if not isinstance(manifest["directories"], list) or not isinstance(manifest["files"], list):
        raise BackupError("Listas de entradas inválidas")

    directories = set()
    for entry in manifest["directories"]:
        parts = valid_parts(entry)
        if parts in directories:
            raise BackupError("Directorio duplicado")
        directories.add(parts)
    files = set()
    for entry in manifest["files"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "size", "sha256"}:
            raise BackupError("Entrada de archivo inválida")
        parts = valid_parts(entry["path"])
        if parts in files or parts in directories:
            raise BackupError("Rutas duplicadas o incompatibles")
        files.add(parts)
        if type(entry["size"]) is not int or entry["size"] < 0:
            raise BackupError("Tamaño de archivo inválido")
        digest = entry["sha256"]
        if not isinstance(digest, str) or DIGEST_PATTERN.fullmatch(digest) is None:
            raise BackupError("Hash de archivo inválido")
    for parts in directories | files:
        if len(parts) > 1 and parts[:-1] not in directories:
            raise BackupError("Falta un directorio padre en el manifiesto")

    expected_entries = {
        ("manifest.json",): "file",
        ("manifest.sha256",): "file",
        ("data",): "directory",
    }
    for index in range(len(manifest["files"])):
        expected_entries[("data", str(index))] = "file"
    actual_entries = {parts: kind for parts, kind, _ in walk_tree(snapshot)}
    if actual_entries != expected_entries:
        raise BackupError("El snapshot contiene entradas ausentes, adicionales o de tipo incorrecto")
    return manifest


def check_data(snapshot, manifest, destination=None):
    if destination is not None:
        for parts in sorted(manifest["directories"], key=lambda item: (len(item), item)):
            destination.joinpath(*parts).mkdir()
    for index, entry in enumerate(manifest["files"]):
        data_path = snapshot / "data" / str(index)
        if destination is None:
            size, digest = hash_or_copy(data_path)
        else:
            with destination.joinpath(*entry["path"]).open("xb") as output:
                size, digest = hash_or_copy(data_path, output)
                output.flush()
                os.fsync(output.fileno())
        if size != entry["size"] or not hmac.compare_digest(digest, entry["sha256"]):
            raise BackupError(f"Contenido corrupto: {entry['path']!r}")


def create_snapshot(source_value, repo_value, identifier, max_bytes=None):
    if max_bytes is not None and (type(max_bytes) is not int or max_bytes < 0):
        raise BackupError("--max-bytes debe ser un entero no negativo")
    identifier = validate_id(identifier)
    source = checked_directory(source_value, must_exist=True)
    root = checked_directory(repo_value)
    if overlaps(source, root):
        raise BackupError("Fuente y repositorio solapados")
    # Rechazar toda la fuente antes de crear entradas en el repositorio.
    entries = list(walk_tree(source))
    with Repository(root, create=True) as repo:
        final = repo.snapshots / identifier
        if os.path.lexists(final):
            raise BackupError(f"El ID ya existe: {identifier}")
        repo.clean_staging()
        existing_bytes = repo.regular_bytes()
        if max_bytes is not None and existing_bytes > max_bytes:
            raise BackupError("El repositorio existente supera --max-bytes")
        repo.snapshots.mkdir(exist_ok=True)
        repo.staging.mkdir(exist_ok=True)
        sync_directory(repo.root)
        stage = Path(tempfile.mkdtemp(prefix=identifier + "-", dir=repo.staging))
        try:
            (stage / "data").mkdir()
            manifest = {"version": 1, "id": identifier, "directories": [], "files": []}
            copied_bytes = 0
            for parts, kind, path in entries:
                if kind == "directory":
                    manifest["directories"].append(list(parts))
                else:
                    data_path = stage / "data" / str(len(manifest["files"]))
                    with data_path.open("xb") as output:
                        available = (None if max_bytes is None else
                                     max_bytes - existing_bytes - copied_bytes)
                        size, digest = hash_or_copy(path, output, max_bytes=available)
                        output.flush()
                        os.fsync(output.fileno())
                    copied_bytes += size
                    manifest["files"].append({"path": list(parts), "size": size, "sha256": digest})
            raw = json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
            seal = (hashlib.sha256(raw).hexdigest() + "\n").encode("ascii")
            if (max_bytes is not None and
                    existing_bytes + copied_bytes + len(raw) + len(seal) > max_bytes):
                raise BackupError("Los datos y la metadata superan --max-bytes")
            write_bytes(stage / "manifest.json", raw)
            write_bytes(stage / "manifest.sha256", seal)
            # Verificar la copia almacenada antes de publicar el directorio completo.
            check_data(stage, read_manifest(stage, identifier))
            sync_directory(stage / "data")
            sync_directory(stage)
            # La suma real de st_size incluye cualquier archivo del repositorio.
            # El rename posterior no añade archivos ni cambia sus tamaños.
            if max_bytes is not None and repo.regular_bytes() > max_bytes:
                raise BackupError("El repositorio completo supera --max-bytes")
            if os.path.lexists(final):
                raise BackupError(f"El ID ya existe: {identifier}")
            os.rename(stage, final)
            sync_directory(repo.snapshots)
            sync_directory(repo.staging)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
                sync_directory(repo.staging)
    return {"id": identifier}


def verify_snapshot(repo_value, identifier):
    identifier = validate_id(identifier)
    root = checked_directory(repo_value, must_exist=True)
    with Repository(root) as repo:
        snapshot = repo.snapshot(identifier)
        check_data(snapshot, read_manifest(snapshot, identifier))
    return {"id": identifier, "valid": True}


def require_empty_destination(path):
    checked_directory(path)
    if path.exists():
        with os.scandir(path) as iterator:
            if next(iterator, None) is not None:
                raise BackupError("El destino preexistente no está vacío")


def restore_snapshot(repo_value, identifier, dest_value):
    identifier = validate_id(identifier)
    root = checked_directory(repo_value, must_exist=True)
    destination = checked_directory(dest_value)
    require_empty_destination(destination)
    if overlaps(root, destination):
        raise BackupError("Destino y repositorio solapados")
    with Repository(root) as repo:
        snapshot = repo.snapshot(identifier)
        manifest = read_manifest(snapshot, identifier)
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".backup-restore-", dir=destination.parent))
        try:
            check_data(snapshot, manifest, stage)
            # Los directorios también deben estar sincronizados antes de publicar.
            directories = [path for _, kind, path in walk_tree(stage) if kind == "directory"]
            for directory in reversed(directories):
                sync_directory(directory)
            sync_directory(stage)
            require_empty_destination(destination)
            os.replace(stage, destination)
            sync_directory(destination.parent)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return {"id": identifier}


def list_snapshots(repo_value):
    root = checked_directory(repo_value, must_exist=True)
    identifiers = []
    with Repository(root) as repo:
        if repo.snapshots.exists():
            for path in sorted(repo.snapshots.iterdir(), key=lambda item: item.name):
                if ID_PATTERN.fullmatch(path.name) is None or not path.is_dir():
                    continue
                try:
                    manifest = read_manifest(path, path.name)
                    check_data(path, manifest)
                except (BackupError, OSError):
                    # Una entrada incompleta o corrupta nunca se anuncia como válida.
                    continue
                identifiers.append(path.name)
    return {"snapshots": identifiers}


def nonnegative_bytes(value):
    if re.fullmatch(r"[0-9]+", value, re.ASCII) is None:
        raise argparse.ArgumentTypeError("N debe ser un entero decimal no negativo")
    try:
        return int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("N es demasiado largo") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Crear un snapshot")
    create.add_argument("--source", required=True)
    create.add_argument("--repo", required=True)
    create.add_argument("--id", required=True)
    create.add_argument("--max-bytes", type=nonnegative_bytes,
                        help="Máximo de bytes regulares del repositorio completo")
    verify = commands.add_parser("verify", help="Comprobar un snapshot completo")
    verify.add_argument("--repo", required=True)
    verify.add_argument("--id", required=True)
    restore = commands.add_parser("restore", help="Restaurar en un destino vacío o nuevo")
    restore.add_argument("--repo", required=True)
    restore.add_argument("--id", required=True)
    restore.add_argument("--dest", required=True)
    listing = commands.add_parser("list", help="Listar snapshots íntegros")
    listing.add_argument("--repo", required=True)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "create":
            result = create_snapshot(arguments.source, arguments.repo, arguments.id,
                                     arguments.max_bytes)
        elif arguments.command == "verify":
            result = verify_snapshot(arguments.repo, arguments.id)
        elif arguments.command == "restore":
            result = restore_snapshot(arguments.repo, arguments.id, arguments.dest)
        else:
            result = list_snapshots(arguments.repo)
    except (BackupError, OSError, ValueError, RecursionError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
