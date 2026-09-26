"""Pack, inspect, and safely extract a visible schema-1 case package.

The ZIP contains exactly ``case.json`` and the source files named by it. A
case package is executor-visible material only; reference answers and rubrics
belong outside it. Inspection verifies the complete archive before extraction
creates a destination. A failed copy can leave a partial, untrusted destination.

Usage::

    python scripts/case_package.py pack SOURCE_DIR NEW_ARCHIVE
    python scripts/case_package.py inspect ARCHIVE [--expected-case-id ID]
    python scripts/case_package.py extract ARCHIVE NEW_DIR [--expected-case-id ID]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import struct
import sys
import unicodedata
import zipfile
from contextlib import ExitStack
from pathlib import Path, PureWindowsPath
from typing import Any, BinaryIO


CHUNK_SIZE = 1024 * 1024
MAX_CASE_JSON_BYTES = 1024 * 1024
MAX_ENTRY_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_FILES = 256
MAX_PATH_BYTES = 1024
MAX_ARCHIVE_BYTES = MAX_TOTAL_BYTES + 2 * MAX_CASE_JSON_BYTES + (MAX_FILES + 1) * 2048
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
CASE_FIELDS = frozenset(
    {"schema", "classification", "case_id", "task_file", "files", "deliverables"}
)
FILE_FIELDS = frozenset({"path", "sha256", "bytes"})
CASE_ID_RE = re.compile(r"[DR]-[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
LOCAL_HEADER = struct.Struct("<IHHHHHIIIHH")
CENTRAL_HEADER = struct.Struct("<IHHHHHHIIIHHHHHII")
END_RECORD = struct.Struct("<IHHHHIIH")


class CasePackageError(ValueError):
    """The visible case package or a destination failed validation."""


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CasePackageError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise CasePackageError("nonfinite JSON number")


def _finite_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value):
        raise CasePackageError("nonfinite JSON number")
    return value


def _parse_json(data: bytes) -> Any:
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except CasePackageError:
        raise
    except (UnicodeError, ValueError, OverflowError, RecursionError) as exc:
        raise CasePackageError("case.json is not strict UTF-8 JSON") from exc


def _exact_object(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise CasePackageError(f"{label} must have exactly {sorted(fields)}")
    return value


def _safe_path(value: Any, label: str, *, flat: bool = False) -> str:
    if (
        type(value) is not str
        or not value
        or len(value.encode("utf-8")) > MAX_PATH_BYTES
    ):
        raise CasePackageError(f"{label} must be a bounded relative file path")
    if (
        value.startswith("/")
        or "\\" in value
        or "\x00" in value
        or PureWindowsPath(value).drive
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise CasePackageError(f"{label} has an unsafe path")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts) or (flat and len(parts) != 1):
        raise CasePackageError(f"{label} has an unsafe path")
    if any(part.endswith((" ", ".")) or ":" in part for part in parts):
        raise CasePackageError(f"{label} has a nonportable path")
    return value


def _path_key(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


def _validate_manifest(raw: Any) -> dict[str, Any]:
    manifest = _exact_object(raw, CASE_FIELDS, "case.json")
    if type(manifest["schema"]) is not int or manifest["schema"] != 1:
        raise CasePackageError("case.json schema must be integer 1")
    if (
        manifest["classification"] != "executor_visible_case_package"
        or type(manifest["classification"]) is not str
    ):
        raise CasePackageError("case.json classification is invalid")
    case_id = manifest["case_id"]
    if (
        type(case_id) is not str
        or len(case_id) > 64
        or not CASE_ID_RE.fullmatch(case_id)
    ):
        raise CasePackageError("case.json case_id is invalid")
    task_file = _safe_path(manifest["task_file"], "task_file")
    files = manifest["files"]
    if type(files) is not list or not 1 <= len(files) <= MAX_FILES:
        raise CasePackageError("files must contain 1 to 256 entries")
    paths: set[str] = {_path_key("case.json")}
    listed: set[str] = set()
    total = 0
    for index, raw_file in enumerate(files):
        item = _exact_object(raw_file, FILE_FIELDS, f"files[{index}]")
        path = _safe_path(item["path"], f"files[{index}].path")
        key = _path_key(path)
        if key in paths:
            raise CasePackageError("duplicate case-insensitive source path")
        paths.add(key)
        listed.add(path)
        digest = item["sha256"]
        if type(digest) is not str or not SHA256_RE.fullmatch(digest):
            raise CasePackageError(f"files[{index}].sha256 must be lowercase SHA-256")
        size = item["bytes"]
        if type(size) is not int or not 0 <= size <= MAX_ENTRY_BYTES:
            raise CasePackageError(f"files[{index}].bytes exceeds entry limit")
        total += size
        if total > MAX_TOTAL_BYTES:
            raise CasePackageError("case source bytes exceed total limit")
    if task_file not in listed:
        raise CasePackageError("task_file must name a listed source file")
    for path in listed:
        parts = path.split("/")
        for length in range(1, len(parts)):
            if _path_key("/".join(parts[:length])) in paths:
                raise CasePackageError("source file path collides with a directory")
    deliverables = manifest["deliverables"]
    if type(deliverables) is not list or not 1 <= len(deliverables) <= MAX_FILES:
        raise CasePackageError("deliverables must contain 1 to 256 names")
    for index, raw_path in enumerate(deliverables):
        path = _safe_path(raw_path, f"deliverables[{index}]", flat=True)
        key = _path_key(path)
        if key in paths:
            raise CasePackageError("duplicate or source-colliding deliverable path")
        paths.add(key)
    return manifest


def _state(file: BinaryIO) -> tuple[int, int, int, int, int]:
    stat_result = os.fstat(file.fileno())
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
        stat_result.st_ctime_ns,
    )


def _read_bounded(fd: int, maximum: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := os.read(fd, min(CHUNK_SIZE, maximum + 1 - total)):
        total += len(chunk)
        if total > maximum:
            raise CasePackageError("case.json exceeds size limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _open_source_file(root_fd: int, path: str, stack: ExitStack) -> int:
    parts = path.split("/")
    with ExitStack() as directories:
        current = root_fd
        for part in parts[:-1]:
            current = os.open(part, DIRECTORY_FLAGS, dir_fd=current)
            directories.callback(os.close, current)
        fd = os.open(parts[-1], FILE_FLAGS, dir_fd=current)
    stack.callback(os.close, fd)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        raise CasePackageError(f"{path} is not a regular source file")
    return fd


def _hash_fd(fd: int, limit: int) -> tuple[int, str]:
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    count = 0
    while chunk := os.read(fd, CHUNK_SIZE):
        count += len(chunk)
        if count > limit:
            raise CasePackageError("source file exceeds entry limit")
        digest.update(chunk)
    return count, digest.hexdigest()


def _zip_info(path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    return info


def pack_package(source_dir: Path | str, archive_path: Path | str) -> dict[str, Any]:
    """Write a deterministic package to a new archive, without replacing files."""
    created = False
    try:
        with ExitStack() as stack:
            root_fd = os.open(source_dir, DIRECTORY_FLAGS)
            stack.callback(os.close, root_fd)
            manifest_fd = _open_source_file(root_fd, "case.json", stack)
            manifest_size = os.fstat(manifest_fd).st_size
            if manifest_size > MAX_CASE_JSON_BYTES:
                raise CasePackageError("case.json exceeds size limit")
            manifest_bytes = _read_bounded(manifest_fd, MAX_CASE_JSON_BYTES)
            if len(manifest_bytes) != manifest_size:
                raise CasePackageError("case.json changed while being read")
            manifest = _validate_manifest(_parse_json(manifest_bytes))
            source_fds = {"case.json": manifest_fd}
            for item in manifest["files"]:
                path = item["path"]
                fd = _open_source_file(root_fd, path, stack)
                before = os.fstat(fd)
                if before.st_size != item["bytes"]:
                    raise CasePackageError(f"{path} size differs from case.json")
                size, digest = _hash_fd(fd, MAX_ENTRY_BYTES)
                after = os.fstat(fd)
                if (
                    size != item["bytes"]
                    or digest != item["sha256"]
                    or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                ):
                    raise CasePackageError(
                        f"{path} bytes differ from case.json or changed"
                    )
                source_fds[path] = fd

            output_parent_fd, output_name = _open_parent_chain(archive_path, stack)
            output_fd = os.open(
                output_name,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=output_parent_fd,
            )
            created = True
            with os.fdopen(output_fd, "w+b") as output:
                os.fchmod(output.fileno(), 0o600)
                with zipfile.ZipFile(
                    output, "w", compression=zipfile.ZIP_STORED, allowZip64=False
                ) as archive:
                    expected = {
                        item["path"]: (item["bytes"], item["sha256"])
                        for item in manifest["files"]
                    }
                    expected["case.json"] = (
                        len(manifest_bytes),
                        hashlib.sha256(manifest_bytes).hexdigest(),
                    )
                    for path in [
                        "case.json",
                        *sorted(source_fds.keys() - {"case.json"}),
                    ]:
                        fd = source_fds[path]
                        os.lseek(fd, 0, os.SEEK_SET)
                        digest = hashlib.sha256()
                        copied = 0
                        with archive.open(_zip_info(path), "w") as member:
                            while chunk := os.read(fd, CHUNK_SIZE):
                                copied += len(chunk)
                                if copied > expected[path][0]:
                                    raise CasePackageError(
                                        f"{path} changed during packing"
                                    )
                                digest.update(chunk)
                                member.write(chunk)
                        if (copied, digest.hexdigest()) != expected[path]:
                            raise CasePackageError(f"{path} changed during packing")
                output.flush()
                os.fsync(output.fileno())
        # Read back the written ZIP through the same verifier used by consumers.
        inspected = inspect_package(archive_path, expected_case_id=manifest["case_id"])
        if inspected != manifest:
            raise CasePackageError("packed manifest changed")
        return manifest
    except CasePackageError as exc:
        if created:
            raise CasePackageError(f"{exc}; partial archive is untrusted") from exc
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError, UnicodeError) as exc:
        raise CasePackageError(
            "package could not be packed; any partial archive is untrusted"
        ) from exc


def _read_at(file: BinaryIO, offset: int, size: int) -> bytes:
    file.seek(offset)
    data = file.read(size)
    if len(data) != size:
        raise CasePackageError("ZIP structure is truncated")
    return data


def _verify_structure(
    file: BinaryIO, archive: zipfile.ZipFile
) -> dict[str, zipfile.ZipInfo]:
    size = os.fstat(file.fileno()).st_size
    if size < END_RECORD.size or size > MAX_ARCHIVE_BYTES:
        raise CasePackageError("ZIP size is outside package bounds")
    end = END_RECORD.unpack(_read_at(file, size - END_RECORD.size, END_RECORD.size))
    (
        signature,
        disk,
        central_disk,
        disk_entries,
        total_entries,
        central_size,
        central_start,
        comment_len,
    ) = end
    infos = archive.infolist()
    if (
        signature != 0x06054B50
        or disk
        or central_disk
        or comment_len
        or archive.comment
    ):
        raise CasePackageError("ZIP must have a plain, final end record")
    if (
        not 1 <= len(infos) <= MAX_FILES + 1
        or disk_entries != total_entries
        or total_entries != len(infos)
    ):
        raise CasePackageError("ZIP entry count is invalid")
    if central_start + central_size != size - END_RECORD.size:
        raise CasePackageError("ZIP has trailing, leading, or undeclared bytes")

    by_name: dict[str, zipfile.ZipInfo] = {}
    keys: set[str] = set()
    local_cursor = 0
    total_bytes = 0
    for info in sorted(infos, key=lambda item: item.header_offset):
        name = _safe_path(info.filename, "ZIP member")
        key = _path_key(name)
        if key in keys:
            raise CasePackageError("duplicate case-insensitive ZIP member")
        keys.add(key)
        by_name[name] = info
        if (
            info.header_offset != local_cursor
            or info.compress_type != zipfile.ZIP_STORED
            or info.compress_size != info.file_size
        ):
            raise CasePackageError("ZIP members must be contiguous and stored")
        if (
            info.flag_bits & ~0x800
            or info.extra
            or info.comment
            or info.create_system != 3
        ):
            raise CasePackageError("ZIP member has unsupported flags or metadata")
        mode = info.external_attr >> 16
        if not stat.S_ISREG(mode) or info.external_attr & 0x10 or info.is_dir():
            raise CasePackageError("ZIP member is not a regular file")
        limit = MAX_CASE_JSON_BYTES if name == "case.json" else MAX_ENTRY_BYTES
        if info.file_size > limit:
            raise CasePackageError("ZIP member exceeds entry limit")
        total_bytes += info.file_size
        if total_bytes > MAX_TOTAL_BYTES + MAX_CASE_JSON_BYTES:
            raise CasePackageError("ZIP content exceeds total limit")
        encoded = name.encode("utf-8" if info.flag_bits & 0x800 else "ascii")
        local = LOCAL_HEADER.unpack(_read_at(file, local_cursor, LOCAL_HEADER.size))
        (
            local_sig,
            local_version,
            local_flags,
            local_method,
            _local_time,
            _local_date,
            local_crc,
            local_compressed,
            local_size,
            local_name_len,
            local_extra_len,
        ) = local
        if (
            local_sig != 0x04034B50
            or local_version > 20
            or local_flags != info.flag_bits
            or local_method != zipfile.ZIP_STORED
            or local_crc != info.CRC
            or local_compressed != info.compress_size
            or local_size != info.file_size
            or local_name_len != len(encoded)
            or local_extra_len
            or _read_at(file, local_cursor + LOCAL_HEADER.size, local_name_len)
            != encoded
        ):
            raise CasePackageError("ZIP local header differs from directory")
        local_cursor += LOCAL_HEADER.size + local_name_len + info.file_size
        if local_cursor > central_start:
            raise CasePackageError("ZIP member overlaps central directory")
    if local_cursor != central_start:
        raise CasePackageError("ZIP has undeclared bytes before central directory")

    central_cursor = central_start
    for info in infos:
        raw = CENTRAL_HEADER.unpack(_read_at(file, central_cursor, CENTRAL_HEADER.size))
        (
            central_sig,
            made_by,
            needed,
            flags,
            method,
            mod_time,
            mod_date,
            crc,
            compressed,
            uncompressed,
            name_len,
            extra_len,
            member_comment_len,
            member_disk,
            internal_attr,
            external_attr,
            local_offset,
        ) = raw
        if flags & ~0x800:
            raise CasePackageError("ZIP member has unsupported flags")
        encoded = info.filename.encode("utf-8" if flags & 0x800 else "ascii")
        if (
            central_sig != 0x02014B50
            or made_by >> 8 != 3
            or needed > 20
            or method != zipfile.ZIP_STORED
            or flags != info.flag_bits
            or crc != info.CRC
            or compressed != info.compress_size
            or uncompressed != info.file_size
            or name_len != len(encoded)
            or extra_len
            or member_comment_len
            or member_disk
            or internal_attr
            or external_attr != info.external_attr
            or local_offset != info.header_offset
            or _read_at(file, central_cursor + CENTRAL_HEADER.size, name_len) != encoded
        ):
            raise CasePackageError(
                "ZIP central directory is noncanonical or inconsistent"
            )
        local = LOCAL_HEADER.unpack(_read_at(file, local_offset, LOCAL_HEADER.size))
        if (local[4], local[5]) != (mod_time, mod_date):
            raise CasePackageError("ZIP timestamp differs between headers")
        central_cursor += CENTRAL_HEADER.size + name_len
    if central_cursor != central_start + central_size:
        raise CasePackageError("ZIP central directory has undeclared bytes")
    return by_name


def _hash_member(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int
) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    with archive.open(info, "r") as member:
        while chunk := member.read(CHUNK_SIZE):
            count += len(chunk)
            if count > limit:
                raise CasePackageError("ZIP member exceeds entry limit")
            digest.update(chunk)
    return count, digest.hexdigest()


def _inspect_open(
    file: BinaryIO, archive: zipfile.ZipFile, expected_case_id: str | None
) -> tuple[dict[str, Any], dict[str, zipfile.ZipInfo], str]:
    before = _state(file)
    by_name = _verify_structure(file, archive)
    if "case.json" not in by_name:
        raise CasePackageError("ZIP is missing case.json")
    with archive.open(by_name["case.json"], "r") as member:
        manifest_bytes = member.read(MAX_CASE_JSON_BYTES + 1)
        if len(manifest_bytes) > MAX_CASE_JSON_BYTES or member.read(1):
            raise CasePackageError("case.json exceeds size limit")
    manifest = _validate_manifest(_parse_json(manifest_bytes))
    if expected_case_id is not None and manifest["case_id"] != expected_case_id:
        raise CasePackageError("case_id differs from expected case_id")
    declared = {item["path"]: item for item in manifest["files"]}
    if set(by_name) != {"case.json", *declared}:
        raise CasePackageError("ZIP members differ from case.json files")
    for path, item in declared.items():
        info = by_name[path]
        if info.file_size != item["bytes"]:
            raise CasePackageError(f"{path} size differs from case.json")
        size, digest = _hash_member(archive, info, MAX_ENTRY_BYTES)
        if size != item["bytes"] or digest != item["sha256"]:
            raise CasePackageError(f"{path} hash differs from case.json")
    if _state(file) != before:
        raise CasePackageError("ZIP changed during inspection")
    return manifest, by_name, hashlib.sha256(manifest_bytes).hexdigest()


def _open_package(
    archive_path: Path | str, stack: ExitStack
) -> tuple[BinaryIO, zipfile.ZipFile]:
    parent_fd, name = _open_parent_chain(archive_path, stack)
    fd = os.open(name, FILE_FLAGS, dir_fd=parent_fd)
    file = stack.enter_context(os.fdopen(fd, "rb"))
    source = os.fstat(fd)
    if (
        not stat.S_ISREG(source.st_mode)
        or not END_RECORD.size <= source.st_size <= MAX_ARCHIVE_BYTES
    ):
        raise CasePackageError("archive must be a bounded regular file")
    end = END_RECORD.unpack(
        _read_at(file, source.st_size - END_RECORD.size, END_RECORD.size)
    )
    (
        signature,
        disk,
        central_disk,
        disk_entries,
        total_entries,
        central_size,
        central_start,
        comment_len,
    ) = end
    if (
        signature != 0x06054B50
        or disk
        or central_disk
        or comment_len
        or not 1 <= total_entries <= MAX_FILES + 1
        or disk_entries != total_entries
        or central_size > (MAX_FILES + 1) * (CENTRAL_HEADER.size + MAX_PATH_BYTES)
        or central_start + central_size != source.st_size - END_RECORD.size
    ):
        raise CasePackageError("ZIP end record is invalid or exceeds package bounds")
    archive = stack.enter_context(zipfile.ZipFile(file, "r"))
    return file, archive


def inspect_package(
    archive_path: Path | str, expected_case_id: str | None = None
) -> dict[str, Any]:
    """Read and verify every member, returning the visible case manifest."""
    try:
        with ExitStack() as stack:
            file, archive = _open_package(archive_path, stack)
            manifest, _, _ = _inspect_open(file, archive, expected_case_id)
            return manifest
    except CasePackageError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError, UnicodeError) as exc:
        raise CasePackageError("archive is not a valid visible case package") from exc


def _destination_directory(root_fd: int, parts: list[str], stack: ExitStack) -> int:
    current = root_fd
    for part in parts:
        try:
            os.mkdir(part, 0o700, dir_fd=current)
        except FileExistsError:
            pass
        current = os.open(part, DIRECTORY_FLAGS, dir_fd=current)
        stack.callback(os.close, current)
        info = os.fstat(current)
        if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
            raise CasePackageError("extraction directory is not private")
    return current


def _open_parent_chain(
    path: Path | str,
    stack: ExitStack,
    chain: list[tuple[int, str, int]] | None = None,
) -> tuple[int, str]:
    raw = os.fspath(path)
    if not isinstance(raw, str) or "\x00" in raw or ".." in raw.split(os.sep):
        raise CasePackageError("file path is unsafe")
    absolute = Path(os.path.abspath(raw))
    if not absolute.name:
        raise CasePackageError("path must name a file or directory")
    current = os.open("/", DIRECTORY_FLAGS)
    stack.callback(os.close, current)
    for part in absolute.parts[1:-1]:
        parent_fd = current
        current = os.open(part, DIRECTORY_FLAGS, dir_fd=parent_fd)
        stack.callback(os.close, current)
        if chain is not None:
            chain.append((parent_fd, part, current))
    return current, absolute.name


def _check_parent_chain(chain: list[tuple[int, str, int]]) -> None:
    """Verify the named path still reaches the pinned parent directory.

    Root-owned sticky directories such as /tmp may contain a private child;
    other group/other-writable ancestors and foreign-owned links are rejected.
    Same-UID actors can still race any point-in-time path check.
    """
    allowed_owners = {0, os.geteuid()}
    for parent_fd, name, child_fd in chain:
        parent = os.fstat(parent_fd)
        opened = os.fstat(child_fd)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISDIR(parent.st_mode)
            or not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(named.st_mode)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
            or parent.st_uid not in allowed_owners
            or opened.st_uid not in allowed_owners
            or (parent.st_mode & 0o022 and not parent.st_mode & stat.S_ISVTX)
        ):
            raise CasePackageError(
                "destination ancestor identity or permissions changed"
            )


def _destination_identity(root_fd: int, parent_fd: int, name: str) -> tuple[int, int]:
    root = os.fstat(root_fd)
    named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    parent = os.fstat(parent_fd)
    identity = (root.st_dev, root.st_ino)
    if (
        not stat.S_ISDIR(root.st_mode)
        or not stat.S_ISDIR(named.st_mode)
        or identity != (named.st_dev, named.st_ino)
        or root.st_uid != os.geteuid()
        or stat.S_IMODE(root.st_mode) != 0o700
        or parent.st_uid != os.geteuid()
        or parent.st_mode & 0o022
    ):
        raise CasePackageError("destination identity or parent permissions changed")
    return identity


def _check_destination_path(
    chain: list[tuple[int, str, int]],
    root_fd: int,
    parent_fd: int,
    name: str,
    created_identity: tuple[int, int],
) -> None:
    _check_parent_chain(chain)
    if _destination_identity(root_fd, parent_fd, name) != created_identity:
        raise CasePackageError("destination identity changed")


def _copy_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    root_fd: int,
    path: str,
    expected_size: int,
    expected_digest: str,
) -> None:
    with ExitStack() as stack:
        parts = path.split("/")
        directory_fd = _destination_directory(root_fd, parts[:-1], stack)
        name = parts[-1]
        fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(fd, "wb") as output, archive.open(info, "r") as member:
            os.fchmod(output.fileno(), 0o600)
            while chunk := member.read(CHUNK_SIZE):
                size += len(chunk)
                if size > expected_size:
                    raise CasePackageError(f"{path} changed during extraction")
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if (size, digest.hexdigest()) != (expected_size, expected_digest):
            raise CasePackageError(f"{path} changed during extraction")
        check_fd = os.open(name, FILE_FLAGS, dir_fd=directory_fd)
        try:
            if _hash_fd(check_fd, expected_size) != (expected_size, expected_digest):
                raise CasePackageError(f"{path} copied bytes differ")
        finally:
            os.close(check_fd)
        os.fsync(directory_fd)


def extract_package(
    archive_path: Path | str,
    destination: Path | str,
    expected_case_id: str | None = None,
) -> dict[str, Any]:
    """Validate first, then copy to a new mode-0700 directory with rehashing."""
    created = False
    try:
        with ExitStack() as stack:
            file, archive = _open_package(archive_path, stack)
            manifest, by_name, manifest_digest = _inspect_open(
                file, archive, expected_case_id
            )
            source_state = _state(file)
            parent_chain: list[tuple[int, str, int]] = []
            parent_fd, name = _open_parent_chain(destination, stack, parent_chain)
            _check_parent_chain(parent_chain)
            parent = os.fstat(parent_fd)
            if parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
                raise CasePackageError(
                    "destination parent must be owned by current UID and not group/other writable"
                )
            os.mkdir(name, 0o700, dir_fd=parent_fd)
            created = True
            created_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            created_identity = (created_stat.st_dev, created_stat.st_ino)
            root_fd = os.open(name, DIRECTORY_FLAGS, dir_fd=parent_fd)
            stack.callback(os.close, root_fd)
            _check_destination_path(
                parent_chain, root_fd, parent_fd, name, created_identity
            )
            expected = {
                item["path"]: (item["bytes"], item["sha256"])
                for item in manifest["files"]
            }
            expected["case.json"] = (by_name["case.json"].file_size, manifest_digest)
            for path in ["case.json", *sorted(expected.keys() - {"case.json"})]:
                size, digest = expected[path]
                _copy_member(archive, by_name[path], root_fd, path, size, digest)
                _check_destination_path(
                    parent_chain, root_fd, parent_fd, name, created_identity
                )
            if _state(file) != source_state:
                raise CasePackageError("ZIP changed during extraction")
            os.fsync(root_fd)
            os.fsync(parent_fd)
            _check_destination_path(
                parent_chain, root_fd, parent_fd, name, created_identity
            )
            return manifest
    except CasePackageError as exc:
        if created:
            raise CasePackageError(f"{exc}; partial destination is untrusted") from exc
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError, UnicodeError) as exc:
        suffix = "; partial destination is untrusted" if created else ""
        raise CasePackageError(f"package extraction failed{suffix}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pack_parser = commands.add_parser(
        "pack", help="pack a source directory to a new ZIP"
    )
    pack_parser.add_argument("source_dir")
    pack_parser.add_argument("archive")
    inspect_parser = commands.add_parser(
        "inspect", help="validate and display a visible case"
    )
    inspect_parser.add_argument("archive")
    inspect_parser.add_argument("--expected-case-id")
    extract_parser = commands.add_parser(
        "extract", help="validate and copy to a new private directory"
    )
    extract_parser.add_argument("archive")
    extract_parser.add_argument("destination")
    extract_parser.add_argument("--expected-case-id")
    args = parser.parse_args(argv)
    try:
        if args.command == "pack":
            manifest = pack_package(args.source_dir, args.archive)
        elif args.command == "inspect":
            manifest = inspect_package(args.archive, args.expected_case_id)
        else:
            manifest = extract_package(
                args.archive, args.destination, args.expected_case_id
            )
    except CasePackageError as exc:
        print(f"case package error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
