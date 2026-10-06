#!/usr/bin/env python3
"""Backups autosuficientes, verificables y publicados atómicamente (Python 3.12)."""

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


ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
HASH_RE = re.compile(r"[0-9a-f]{64}")
CHUNK_SIZE = 1024 * 1024
ROOT_NAMES = {".lock", ".staging", "snapshots"}
SNAPSHOT_NAMES = {"data", "manifest.json", "manifest.sha256"}


class BackupError(Exception):
    """Error de entrada, integridad o estado del repositorio."""


def check_id(snapshot_id: str) -> None:
    if ID_RE.fullmatch(snapshot_id) is None:
        raise BackupError("ID inválido: se requiere [A-Za-z0-9][A-Za-z0-9_-]{0,63}")


def kind(path: Path) -> str:
    """lstat: nunca desreferenciar un enlace para clasificarlo."""
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise BackupError(f"Symlink rechazado: {path}")
    if stat.S_ISDIR(mode):
        return "dir"
    if stat.S_ISREG(mode):
        return "file"
    raise BackupError(f"Archivo especial rechazado: {path}")


def checked_path(value: str | Path) -> Path:
    """Comprobar también los ancestros existentes, antes de acceder al árbol."""
    path = Path(os.path.abspath(value))
    current = Path(path.anchor)
    for i, component in enumerate(path.parts[1:]):
        current = current / component
        try:
            node_kind = kind(current)
        except FileNotFoundError:
            break
        if i < len(path.parts) - 2 and node_kind != "dir":
            raise BackupError(f"Un ancestro no es directorio: {current}")
    return path


def exists(path: Path) -> bool:
    # Path.exists() omite enlaces colgantes; lstat permite rechazarlos.
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


def require_dir(path: Path) -> None:
    if kind(path) != "dir":
        raise BackupError(f"Se requiere un directorio: {path}")


def no_overlap(a: Path, b: Path) -> None:
    common = Path(os.path.commonpath((a, b)))
    if common == a or common == b:
        raise BackupError(f"Rutas solapadas: {a} y {b}")


def inventory(root: Path) -> dict[str, str]:
    """Inventario sin seguir enlaces; registra todos los directorios, incluso vacíos."""
    require_dir(root)
    found: dict[str, str] = {}
    pending = [(root, "")]
    while pending:
        directory, prefix = pending.pop()
        with os.scandir(directory) as children:
            for child in children:
                relative = f"{prefix}/{child.name}" if prefix else child.name
                child_path = directory / child.name
                node_kind = kind(child_path)
                found[relative] = node_kind
                if node_kind == "dir":
                    pending.append((child_path, relative))
    return found


@contextmanager
def regular_reader(path: Path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise BackupError(f"Se requiere un archivo regular: {path}")
        stream = os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise
    with stream:
        yield stream


def file_digest(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with regular_reader(path) as stream:
        while block := stream.read(CHUNK_SIZE):
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def copy_file(source: Path, dest: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with regular_reader(source) as input_stream, dest.open("xb") as output_stream:
        while block := input_stream.read(CHUNK_SIZE):
            output_stream.write(block)
            size += len(block)
            digest.update(block)
        output_stream.flush()
        os.fsync(output_stream.fileno())
    return size, digest.hexdigest()


def write_bytes(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def canonical_json(document: object) -> bytes:
    return (json.dumps(document, ensure_ascii=True, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


def check_repository(repo: Path) -> None:
    # Incluye restos de operaciones interrumpidas: tampoco se admiten enlaces allí.
    tree = inventory(repo)
    for relative, node_kind in tree.items():
        parts = relative.split("/")
        top = parts[0]
        if top not in ROOT_NAMES:
            raise BackupError(f"Entrada ajena al formato del repositorio: {relative}")
        if len(parts) == 1:
            expected = "file" if top == ".lock" else "dir"
            if node_kind != expected:
                raise BackupError(f"Tipo incorrecto en el repositorio: {relative}")
        elif top == "snapshots" and len(parts) == 2:
            check_id(parts[1])
            if node_kind != "dir":
                raise BackupError(f"Snapshot no es un directorio: {relative}")
        elif top == ".staging" and len(parts) == 2:
            if not parts[1].startswith("create-") or node_kind != "dir":
                raise BackupError(f"Área temporal inválida: {relative}")


@contextmanager
def repository(repo: Path, *, create: bool = False):
    if create:
        repo.mkdir(parents=True, exist_ok=True)
    checked_path(repo)
    require_dir(repo)
    lock_path = repo / ".lock"
    if exists(lock_path) and kind(lock_path) != "file":
        raise BackupError("El bloqueo del repositorio no es un archivo regular")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise BackupError("Bloqueo del repositorio inválido")
        # flock se libera también tras SIGKILL. Serializa nuestras operaciones.
        fcntl.flock(fd, fcntl.LOCK_EX)
        check_repository(repo)
        if create:
            (repo / "snapshots").mkdir(exist_ok=True)
            (repo / ".staging").mkdir(exist_ok=True)
            sync_dir(repo)
        yield
    finally:
        os.close(fd)


def read_manifest(snapshot: Path, snapshot_id: str) -> list[dict]:
    require_dir(snapshot)
    with os.scandir(snapshot) as children:
        names = {child.name for child in children}
    if names != SNAPSHOT_NAMES:
        raise BackupError(f"Snapshot incompleto o con entradas inesperadas: {snapshot_id}")
    require_dir(snapshot / "data")
    with regular_reader(snapshot / "manifest.sha256") as stream:
        # Una longitud distinta también es corrupción; nunca ignorar bytes extra.
        seal = stream.read(66)
    with regular_reader(snapshot / "manifest.json") as stream:
        raw = stream.read()
    expected_seal = hashlib.sha256(raw).hexdigest().encode("ascii") + b"\n"
    if seal != expected_seal:
        raise BackupError(f"Hash del manifiesto incorrecto: {snapshot_id}")
    try:
        manifest = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise BackupError(f"Manifiesto ilegible: {snapshot_id}") from exc
    if (type(manifest) is not dict or set(manifest) != {"version", "id", "entries"}
            or type(manifest["version"]) is not int or manifest["version"] != 1
            or manifest["id"] != snapshot_id or type(manifest["entries"]) is not list):
        raise BackupError(f"Formato del manifiesto incorrecto: {snapshot_id}")
    if canonical_json(manifest) != raw:
        raise BackupError(f"El manifiesto no tiene la codificación canónica: {snapshot_id}")
    previous = None
    directories = {""}
    for entry in manifest["entries"]:
        if type(entry) is not dict:
            raise BackupError("Entrada de manifiesto inválida")
        path = entry.get("path")
        node_kind = entry.get("type")
        if type(path) is not str or not path or "\0" in path:
            raise BackupError("Ruta de manifiesto inválida")
        parts = path.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise BackupError("Ruta fuera del árbol de datos")
        if previous is not None and path <= previous:
            raise BackupError("Rutas duplicadas o desordenadas en el manifiesto")
        previous = path
        parent = path.rpartition("/")[0]
        if parent not in directories:
            raise BackupError("Falta un directorio padre en el manifiesto")
        if node_kind == "dir" and set(entry) == {"path", "type"}:
            directories.add(path)
        elif node_kind == "file" and set(entry) == {"path", "type", "size", "sha256"}:
            if (type(entry["size"]) is not int or entry["size"] < 0
                    or type(entry["sha256"]) is not str
                    or HASH_RE.fullmatch(entry["sha256"]) is None):
                raise BackupError("Tamaño o hash inválido en el manifiesto")
        else:
            raise BackupError("Tipo o campos de entrada inválidos")
    return manifest["entries"]


def verify_snapshot(repo: Path, snapshot_id: str) -> list[dict]:
    snapshot = repo / "snapshots" / snapshot_id
    if not exists(snapshot):
        raise BackupError(f"ID inexistente: {snapshot_id}")
    entries = read_manifest(snapshot, snapshot_id)
    actual = inventory(snapshot / "data")
    expected = {entry["path"]: entry["type"] for entry in entries}
    if actual != expected:
        raise BackupError(f"El árbol de datos no coincide con el manifiesto: {snapshot_id}")
    for entry in entries:
        if entry["type"] == "file":
            size, digest = file_digest(snapshot / "data" / entry["path"])
            if size != entry["size"] or digest != entry["sha256"]:
                raise BackupError(f"Contenido corrupto: {snapshot_id}/{entry['path']}")
    return entries


def create_backup(source: Path, repo: Path, snapshot_id: str) -> dict:
    no_overlap(source, repo)
    require_dir(source)
    # Rechazar toda la fuente antes de escribir datos del backup.
    tree = inventory(source)
    with repository(repo, create=True):
        final = repo / "snapshots" / snapshot_id
        if exists(final):
            raise BackupError(f"El ID ya existe: {snapshot_id}")
        stage = Path(tempfile.mkdtemp(prefix="create-", dir=repo / ".staging"))
        try:
            data = stage / "data"
            data.mkdir()
            entries = []
            for relative, node_kind in sorted(tree.items()):
                output_path = data / relative
                if node_kind == "dir":
                    output_path.mkdir()
                    entries.append({"path": relative, "type": "dir"})
                else:
                    size, digest = copy_file(source / relative, output_path)
                    entries.append({"path": relative, "type": "file",
                                    "size": size, "sha256": digest})
            raw = canonical_json({"version": 1, "id": snapshot_id, "entries": entries})
            write_bytes(stage / "manifest.json", raw)
            write_bytes(stage / "manifest.sha256", hashlib.sha256(raw).hexdigest().encode("ascii") + b"\n")
            for relative, node_kind in sorted(tree.items(), reverse=True):
                if node_kind == "dir":
                    sync_dir(data / relative)
            sync_dir(data)
            sync_dir(stage)
            # Bajo el bloqueo ningún otro proceso del programa puede tomar este ID.
            # El único nombre público aparece después de terminar todos los archivos.
            os.rename(stage, final)
            sync_dir(repo / "snapshots")
            sync_dir(repo / ".staging")
        finally:
            if exists(stage):
                shutil.rmtree(stage)
    return {"id": snapshot_id}


def check_dest(dest: Path) -> None:
    checked_path(dest)
    if exists(dest):
        require_dir(dest)
        # Rechazar además enlaces y especiales, sin tocar los bytes del destino.
        if inventory(dest):
            raise BackupError(f"El destino preexistente no está vacío: {dest}")


def restore_backup(repo: Path, snapshot_id: str, dest: Path) -> dict:
    no_overlap(repo, dest)
    check_dest(dest)
    with repository(repo):
        entries = verify_snapshot(repo, snapshot_id)
        # La corrupción se comprueba antes de crear incluso el área temporal.
        dest.parent.mkdir(parents=True, exist_ok=True)
        checked_path(dest.parent)
        stage = Path(tempfile.mkdtemp(prefix=".backup-restore-", dir=dest.parent))
        try:
            data = repo / "snapshots" / snapshot_id / "data"
            for entry in entries:
                output_path = stage / entry["path"]
                if entry["type"] == "dir":
                    output_path.mkdir()
                else:
                    size, digest = copy_file(data / entry["path"], output_path)
                    if size != entry["size"] or digest != entry["sha256"]:
                        raise BackupError(f"El contenido cambió durante restore: {entry['path']}")
            for entry in reversed(entries):
                if entry["type"] == "dir":
                    sync_dir(stage / entry["path"])
            sync_dir(stage)
            check_dest(dest)
            # POSIX permite sustituir un directorio vacío con un único rename.
            # Un destino no vacío no puede ser reemplazado por este rename.
            os.rename(stage, dest)
            sync_dir(dest.parent)
        finally:
            if exists(stage):
                shutil.rmtree(stage)
    return {"id": snapshot_id}


def list_backups(repo: Path) -> dict:
    if not exists(repo):
        return {"snapshots": []}
    with repository(repo):
        snapshots = repo / "snapshots"
        if not exists(snapshots):
            return {"snapshots": []}
        ids = []
        for snapshot in sorted(snapshots.iterdir()):
            # Sólo mostrar snapshots completos que verifican todos sus bytes.
            try:
                verify_snapshot(repo, snapshot.name)
            except (BackupError, OSError, ValueError):
                continue
            ids.append(snapshot.name)
    return {"snapshots": ids}


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise BackupError(message)


def main(argv: list[str] | None = None) -> int:
    try:
        parser = Parser(description=__doc__)
        commands = parser.add_subparsers(dest="command", required=True)
        for name in ("create", "verify", "restore", "list"):
            command = commands.add_parser(name)
            command.add_argument("--repo", required=True)
            if name != "list":
                command.add_argument("--id", required=True)
            if name == "create":
                command.add_argument("--source", required=True)
            elif name == "restore":
                command.add_argument("--dest", required=True)
        args = parser.parse_args(argv)
        if args.command != "list":
            check_id(args.id)
        repo = checked_path(args.repo)
        if args.command == "create":
            result = create_backup(checked_path(args.source), repo, args.id)
        elif args.command == "verify":
            with repository(repo):
                verify_snapshot(repo, args.id)
            result = {"id": args.id, "valid": True}
        elif args.command == "restore":
            result = restore_backup(repo, args.id, checked_path(args.dest))
        else:
            result = list_backups(repo)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except (BackupError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"error": "Operación interrumpida"}), file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
