"""Retain existing D107 interface captures, without executing any experiment."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tarfile


RUNTIME = Path("/tmp/specorganon-D107-probes-8mcviiwp")
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_FILES = 10_000
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
FORBIDDEN_NAMES = {
    ".codex", ".ssh", ".aws", ".env", "auth.json", "credentials.json",
    "environment.json", "environment.txt", "environ", "session.json", "sessions.json",
    "id_rsa", "id_ed25519", "settings.local.json",
}
PRIVATE_FIELDS = {
    "private_key", "private_keys", "private_key_base64", "private_key_pem",
    "secret_key", "api_key", "access_token", "refresh_token", "session_token",
    "authorization", "password", "cookie", "cookies",
}
PRIVATE_PEM = re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def identity(metadata):
    return (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_nlink,
            metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns)


def public_name(name):
    lower = name.lower()
    require(lower not in FORBIDDEN_NAMES and not lower.startswith(".env.")
            and not lower.endswith((".pem", ".key", ".p12", ".pfx", ".token"))
            and "private-key" not in lower and "private_key" not in lower,
            "possible private or environment file; stopped before reading: " + name)


def public_json(value, name):
    if isinstance(value, dict):
        for key, content in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
            require(normalized not in PRIVATE_FIELDS or content in (None, "", [], {}),
                    "possible serialized credential; stopped without printing contents: " + name)
            public_json(content, name)
    elif isinstance(value, list):
        for content in value:
            public_json(content, name)


def public_bytes(raw, name):
    require(PRIVATE_PEM.search(raw) is None,
            "possible private key; stopped without printing contents: " + name)
    if name.endswith(".json"):
        public_json(json.loads(raw), name)
    elif name.endswith(".jsonl"):
        for line in raw.splitlines():
            if line.strip():
                public_json(json.loads(line), name)


def read_regular(directory_fd, name, expected):
    require(stat.S_ISREG(expected.st_mode) and expected.st_nlink == 1,
            "only singly linked regular source files allowed: " + name)
    require(expected.st_size <= MAX_FILE_BYTES, "source file exceeds archive bound: " + name)
    fd = os.open(name, FILE_FLAGS, dir_fd=directory_fd)
    try:
        require(identity(os.fstat(fd)) == identity(expected), "source changed before read: " + name)
        chunks = []
        length = 0
        while chunk := os.read(fd, min(1024 * 1024, MAX_FILE_BYTES - length + 1)):
            chunks.append(chunk)
            length += len(chunk)
            require(length <= MAX_FILE_BYTES, "source grew beyond archive bound: " + name)
        require(length == expected.st_size and identity(os.fstat(fd)) == identity(expected)
                and identity(os.stat(name, dir_fd=directory_fd, follow_symlinks=False)) == identity(expected),
                "source changed during read: " + name)
        return b"".join(chunks)
    finally:
        os.close(fd)


def open_directory(path):
    require(path.is_absolute() and ".." not in path.parts, "source path must be absolute and canonical")
    fd = os.open("/", DIR_FLAGS)
    try:
        for part in path.parts[1:]:
            child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def snapshot(source):
    files = {}
    nonregular = []
    directories = []
    total = 0

    def visit(fd, prefix=""):
        nonlocal total
        names = sorted(os.listdir(fd))
        for name in names:
            public_name(name)
            relative = prefix + name
            metadata = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode):
                child = os.open(name, DIR_FLAGS, dir_fd=fd)
                try:
                    require(identity(os.fstat(child)) == identity(metadata), "source directory changed: " + relative)
                    directories.append(relative)
                    visit(child, relative + "/")
                    require(identity(os.fstat(child)) == identity(metadata)
                            and identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) == identity(metadata),
                            "source directory changed during inventory: " + relative)
                finally:
                    os.close(child)
            elif stat.S_ISREG(metadata.st_mode):
                raw = read_regular(fd, name, metadata)
                public_bytes(raw, relative)
                files[relative] = raw
                total += len(raw)
                require(len(files) <= MAX_FILES and total <= MAX_TOTAL_BYTES, "archive inventory exceeds bound")
            elif stat.S_ISLNK(metadata.st_mode):
                target = os.readlink(name, dir_fd=fd)
                require(identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) == identity(metadata),
                        "symlink changed during metadata inventory: " + relative)
                nonregular.append({"path": relative, "type": "symlink", "link_target": target})
            elif stat.S_ISFIFO(metadata.st_mode):
                nonregular.append({"path": relative, "type": "fifo"})
            else:
                raise ValueError("unsupported nonregular source entry: " + relative)
        require(names == sorted(os.listdir(fd)), "source directory entries changed during inventory")

    root_fd = open_directory(source)
    try:
        visit(root_fd)
    finally:
        os.close(root_fd)
    return files, sorted(nonregular, key=lambda item: item["path"]), sorted(directories)


def exclusive(destination):
    return os.fdopen(os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644), "wb")


def write_exclusive(destination, raw):
    with exclusive(destination) as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(destination.read_bytes() == raw, "exclusive output copy differs: " + destination.name)


def archive(source, env):
    require(source == RUNTIME / ("interfaces-" + env), "source is not the designated new external runtime")
    dossier = Path(__file__).absolute().parent
    tar_path = dossier / ("interfaces_" + env + ".tar.gz")
    receipt_path = dossier / ("interfaces_" + env + ".json")
    inventory_path = dossier / ("archive_interfaces_" + env + ".json")
    require(all(not os.path.lexists(path) for path in (tar_path, receipt_path, inventory_path)),
            "archive output already exists; no overwrite or rerun")
    own_raw = Path(__file__).read_bytes()
    files, nonregular, directories = snapshot(source)
    require("receipt.json" in files and json.loads(files["receipt.json"]).get("passed") is True,
            "missing successful original interface receipt")
    rows = [{"path": name, **pin(raw)} for name, raw in sorted(files.items())]
    with exclusive(tar_path) as stream:
        with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as stored:
                for name, raw in sorted(files.items()):
                    member = tarfile.TarInfo(name)
                    member.type = tarfile.REGTYPE
                    member.size = len(raw)
                    member.mode = 0o644
                    member.mtime = 0
                    stored.addfile(member, io.BytesIO(raw))
        stream.flush()
        os.fsync(stream.fileno())
    with tarfile.open(tar_path, mode="r:gz") as reopened:
        members = reopened.getmembers()
        require(len(members) == len(rows), "reopened archive member count differs")
        for member, row in zip(members, rows, strict=True):
            require(member.isfile() and member.name == row["path"], "reopened member kind/name differs")
            stream = reopened.extractfile(member)
            require(stream is not None, "reopened member is unreadable")
            with stream:
                raw = stream.read(MAX_FILE_BYTES + 1)
            require(raw == files[member.name] and pin(raw) == {k: row[k] for k in ("bytes", "sha256")},
                    "reopened archive member bytes/hash differ: " + member.name)
    require(snapshot(source) == (files, nonregular, directories), "source changed during archive")
    write_exclusive(receipt_path, files["receipt.json"])
    record = {
        "schema": 1, "classification": "existing_public_interface_runtime_archive_no_experiments_executed",
        "env": env, "source_directory": str(source), "archive": tar_path.name,
        "archive_pin": pin(tar_path.read_bytes()), "regular_files": len(rows),
        "regular_bytes": sum(row["bytes"] for row in rows), "files": rows,
        "symlinks": sum(item["type"] == "symlink" for item in nonregular),
        "fifos": sum(item["type"] == "fifo" for item in nonregular),
        "nonregular_metadata": nonregular, "directory_paths": directories,
        "all_reopened_bytes_match": True, "source_unchanged_after": True,
        "receipt_copy": {"path": receipt_path.name, **pin(files["receipt.json"])},
        "archiver": {"path": Path(__file__).name, **pin(own_raw)},
        "policy": {"source_reads_no_follow": True, "symlink_targets_read": False,
                   "fifo_contents_read": False, "nonregular_entries_in_tar": False,
                   "private_or_environment_files_allowed": False,
                   "max_file_bytes": MAX_FILE_BYTES, "max_total_bytes": MAX_TOTAL_BYTES,
                   "max_files": MAX_FILES, "experiments_rerun": False},
    }
    write_exclusive(inventory_path, (json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
    directory_fd = os.open(dossier, DIR_FLAGS)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return {"env": env, "regular_files": len(rows), "regular_bytes": record["regular_bytes"],
            "symlinks": record["symlinks"], "fifos": record["fifos"],
            "archive_pin": record["archive_pin"], "receipt_pin": record["receipt_copy"],
            "inventory_pin": pin(inventory_path.read_bytes()), "archiver_pin": pin(own_raw)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("env", choices=("311", "312"))
    args = parser.parse_args()
    try:
        result = archive(args.source, args.env)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"state": "failed", "error_type": type(exc).__name__, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
