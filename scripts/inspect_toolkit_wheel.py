"""Read-only, static inspection of a released SpecOrganon toolkit wheel.

The release may name the file ``toolkit`` rather than ``*.whl``. This module
does not import, install, or execute anything from the candidate archive.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import configparser
import csv
import hashlib
import io
import json
import os
import re
import stat
import struct
import sys
import unicodedata
import zlib
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any


CLASSIFICATION = "development_toolkit_wheel_inspection_unsealed"
MAX_WHEEL_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 256
MAX_ENTRY_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_PATH_BYTES = 1024
MAX_RATIO = 200
CHUNK_BYTES = 64 * 1024
LOCAL_HEADER = struct.Struct("<IHHHHHIIIHH")
CENTRAL_HEADER = struct.Struct("<IHHHHHHIIIHHHHHII")
END_RECORD = struct.Struct("<IHHHHIIH")
DATA_DESCRIPTOR = struct.Struct("<III")
SIGNED_DATA_DESCRIPTOR = struct.Struct("<IIII")
VERSION_RE = re.compile(
    r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){1,3}"
    r"(?:(?:a|b|rc)[0-9]+)?(?:\.post[0-9]+)?(?:\.dev[0-9]+)?\Z"
)
HEADER_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]*\Z")
REQUIREMENT_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)\s*(.*)\Z")
SPECIFIER_RE = re.compile(r"(<=|>=|==|!=|~=|<|>)\s*([0-9][A-Za-z0-9.!+_-]*)\Z")
CORE_MODULES = frozenset(
    {
        "__init__.py",
        "anchor.py",
        "approval.py",
        "cli.py",
        "engine.py",
        "ledger.py",
        "runner.py",
        "server.py",
        "workflow.py",
    }
)


class ToolkitWheelError(ValueError):
    """The candidate toolkit is not a bounded, internally consistent wheel."""


def _identity(item: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
    )


def _directory_identity(item: os.stat_result) -> tuple[int, int, int]:
    return item.st_dev, item.st_ino, stat.S_IFMT(item.st_mode)


def _check_directory_chain(
    root_fd: int,
    root_name: str,
    root_identity: tuple[int, int, int],
    links: list[tuple[int, str, int, tuple[int, int, int]]],
) -> None:
    if (
        _directory_identity(os.fstat(root_fd)) != root_identity
        or _directory_identity(os.stat(root_name, follow_symlinks=False))
        != root_identity
    ):
        raise ToolkitWheelError("toolkit directory chain changed while being read")
    for parent_fd, name, child_fd, expected in links:
        if (
            _directory_identity(os.fstat(child_fd)) != expected
            or _directory_identity(
                os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            )
            != expected
        ):
            raise ToolkitWheelError("toolkit directory chain changed while being read")


@dataclass(frozen=True)
class _Member:
    name: str
    raw_name: bytes
    flags: int
    method: int
    crc: int
    compressed: int
    uncompressed: int
    local_offset: int
    modified: tuple[int, int]
    external_attr: int
    needed: int
    data_offset: int = 0


def _read_regular_path(path: Path | str) -> bytes:
    """Open each path component without following symlinks and bound the read."""
    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw or "\x00" in raw or raw.endswith("/"):
        raise ToolkitWheelError("toolkit path is invalid")
    parts = [part for part in raw.split("/") if part]
    if not parts or any(part in (".", "..") for part in parts):
        raise ToolkitWheelError("toolkit path must name a regular file")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    file_flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        with ExitStack() as opened:
            root_name = "/" if raw.startswith("/") else "."
            directory = os.open(root_name, directory_flags)
            opened.callback(os.close, directory)
            root_fd = directory
            root_identity = _directory_identity(os.fstat(root_fd))
            links: list[tuple[int, str, int, tuple[int, int, int]]] = []
            _check_directory_chain(root_fd, root_name, root_identity, links)
            for part in parts[:-1]:
                next_directory = os.open(part, directory_flags, dir_fd=directory)
                opened.callback(os.close, next_directory)
                expected = _directory_identity(os.fstat(next_directory))
                links.append((directory, part, next_directory, expected))
                directory = next_directory
                _check_directory_chain(root_fd, root_name, root_identity, links)
            fd = os.open(parts[-1], file_flags, dir_fd=directory)
            opened.callback(os.close, fd)
            before = os.fstat(fd)
            path_before = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(before.st_mode):
                raise ToolkitWheelError("toolkit is not a regular file")
            if _identity(before) != _identity(path_before):
                raise ToolkitWheelError("toolkit changed before being read")
            if not END_RECORD.size <= before.st_size <= MAX_WHEEL_BYTES:
                raise ToolkitWheelError("toolkit exceeds wheel size bounds")
            chunks: list[bytes] = []
            total = 0
            while chunk := os.read(fd, min(CHUNK_BYTES, MAX_WHEEL_BYTES + 1 - total)):
                total += len(chunk)
                if total > MAX_WHEEL_BYTES:
                    raise ToolkitWheelError("toolkit exceeds wheel size bounds")
                chunks.append(chunk)
            after = os.fstat(fd)
            path_after = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
            if (
                total != before.st_size
                or _identity(before) != _identity(after)
                or _identity(before) != _identity(path_after)
            ):
                raise ToolkitWheelError("toolkit changed while being read")
            _check_directory_chain(root_fd, root_name, root_identity, links)
            return b"".join(chunks)
    except OSError as exc:
        raise ToolkitWheelError("toolkit cannot be read securely") from exc


def _at(data: bytes, offset: int, length: int, boundary: int) -> bytes:
    if offset < 0 or length < 0 or offset + length > boundary:
        raise ToolkitWheelError("ZIP structure is truncated or overlaps another region")
    return data[offset : offset + length]


def _safe_name(raw: bytes, flags: int) -> str:
    try:
        name = raw.decode("utf-8" if flags & 0x800 else "ascii", errors="strict")
    except UnicodeError as exc:
        raise ToolkitWheelError("ZIP member path is not valid UTF-8 or ASCII") from exc
    if (
        not name
        or len(raw) > MAX_PATH_BYTES
        or name.startswith("/")
        or "\\" in name
        or "\x00" in name
        or PureWindowsPath(name).drive
        or any(ord(char) < 32 or ord(char) == 127 for char in name)
    ):
        raise ToolkitWheelError("ZIP member has an unsafe path")
    parts = name.split("/")
    if any(
        part in ("", ".", "..") or part.endswith((" ", ".")) or ":" in part
        for part in parts
    ):
        raise ToolkitWheelError("ZIP member has an unsafe path")
    return name


def _member_limit(name: str) -> int:
    leaf = name.rsplit("/", 1)[-1]
    if leaf == "METADATA":
        return 1024 * 1024
    if leaf in ("WHEEL", "entry_points.txt"):
        return 16 * 1024
    if leaf == "RECORD":
        return 256 * 1024
    return MAX_ENTRY_BYTES


def _parse_central(data: bytes) -> tuple[list[_Member], int]:
    end_offset = len(data) - END_RECORD.size
    (
        signature,
        disk,
        central_disk,
        disk_entries,
        total_entries,
        central_size,
        central_offset,
        comment_size,
    ) = END_RECORD.unpack(_at(data, end_offset, END_RECORD.size, len(data)))
    if signature != 0x06054B50 or disk or central_disk or comment_size:
        raise ToolkitWheelError("ZIP must have a plain final end record")
    if not 1 <= total_entries <= MAX_ENTRIES or disk_entries != total_entries:
        raise ToolkitWheelError("ZIP entry count is invalid")
    if (
        total_entries == 0xFFFF
        or central_size == 0xFFFFFFFF
        or central_offset == 0xFFFFFFFF
        or central_offset + central_size != end_offset
    ):
        raise ToolkitWheelError(
            "ZIP64, prefix, trailer, or undeclared bytes are unsupported"
        )
    members: list[_Member] = []
    cursor = central_offset
    seen: set[str] = set()
    total_size = 0
    for _ in range(total_entries):
        values = CENTRAL_HEADER.unpack(
            _at(data, cursor, CENTRAL_HEADER.size, end_offset)
        )
        (
            magic,
            made_by,
            needed,
            flags,
            method,
            modified_time,
            modified_date,
            crc,
            compressed,
            uncompressed,
            name_size,
            extra_size,
            comment_size,
            disk_start,
            internal_attr,
            external_attr,
            local_offset,
        ) = values
        if magic != 0x02014B50 or made_by >> 8 != 3 or needed > 20:
            raise ToolkitWheelError("ZIP central header is unsupported")
        if flags & ~(0x800 | 0x08) or method not in (0, 8):
            raise ToolkitWheelError(
                "ZIP encryption, flags, or compression are unsupported"
            )
        if extra_size or comment_size or disk_start or internal_attr:
            raise ToolkitWheelError("ZIP member has unsupported extra metadata")
        raw_name = _at(data, cursor + CENTRAL_HEADER.size, name_size, end_offset)
        name = _safe_name(raw_name, flags)
        path_key = unicodedata.normalize("NFC", name).casefold()
        if path_key in seen:
            raise ToolkitWheelError("ZIP has duplicate or case-colliding paths")
        seen.add(path_key)
        mode = external_attr >> 16
        if (
            stat.S_IFMT(mode) not in (0, stat.S_IFREG)
            or external_attr & 0x10
            or name.endswith("/")
        ):
            raise ToolkitWheelError("ZIP member is not a regular file")
        if (
            uncompressed > _member_limit(name)
            or compressed > MAX_WHEEL_BYTES
            or (method == 0 and compressed != uncompressed)
            or (method == 8 and uncompressed > max(compressed, 1) * MAX_RATIO)
        ):
            raise ToolkitWheelError("ZIP member exceeds size or compression bounds")
        total_size += uncompressed
        if total_size > MAX_TOTAL_BYTES:
            raise ToolkitWheelError("ZIP uncompressed content exceeds total limit")
        members.append(
            _Member(
                name,
                raw_name,
                flags,
                method,
                crc,
                compressed,
                uncompressed,
                local_offset,
                (modified_time, modified_date),
                external_attr,
                needed,
            )
        )
        cursor += CENTRAL_HEADER.size + name_size
    if cursor != end_offset:
        raise ToolkitWheelError("ZIP central directory has undeclared bytes")
    return members, central_offset


def _parse_locals(
    data: bytes, members: list[_Member], central_offset: int
) -> list[_Member]:
    cursor = 0
    located: dict[str, _Member] = {}
    for member in sorted(members, key=lambda item: item.local_offset):
        if member.local_offset != cursor:
            raise ToolkitWheelError("ZIP has a prefix, gap, or overlapping members")
        (
            magic,
            needed,
            flags,
            method,
            modified_time,
            modified_date,
            crc,
            compressed,
            uncompressed,
            name_size,
            extra_size,
        ) = LOCAL_HEADER.unpack(_at(data, cursor, LOCAL_HEADER.size, central_offset))
        raw_name = _at(data, cursor + LOCAL_HEADER.size, name_size, central_offset)
        if (
            magic != 0x04034B50
            or needed != member.needed
            or flags != member.flags
            or method != member.method
            or (modified_time, modified_date) != member.modified
            or raw_name != member.raw_name
            or extra_size
        ):
            raise ToolkitWheelError("ZIP local header differs from central directory")
        if flags & 0x08:
            if crc or compressed or uncompressed:
                raise ToolkitWheelError("ZIP data-descriptor header is inconsistent")
        elif (crc, compressed, uncompressed) != (
            member.crc,
            member.compressed,
            member.uncompressed,
        ):
            raise ToolkitWheelError("ZIP local sizes or CRC differ from directory")
        data_offset = cursor + LOCAL_HEADER.size + name_size
        cursor = data_offset + member.compressed
        _at(data, data_offset, member.compressed, central_offset)
        if flags & 0x08:
            signed = _at(data, cursor, 4, central_offset) == b"PK\x07\x08"
            descriptor = SIGNED_DATA_DESCRIPTOR if signed else DATA_DESCRIPTOR
            values = descriptor.unpack(
                _at(data, cursor, descriptor.size, central_offset)
            )
            if signed:
                signature, *values = values
                if signature != 0x08074B50:
                    raise ToolkitWheelError("ZIP data descriptor signature is invalid")
            if tuple(values) != (
                member.crc,
                member.compressed,
                member.uncompressed,
            ):
                raise ToolkitWheelError("ZIP data descriptor differs from directory")
            cursor += descriptor.size
        located[member.name] = _Member(
            member.name,
            member.raw_name,
            member.flags,
            member.method,
            member.crc,
            member.compressed,
            member.uncompressed,
            member.local_offset,
            member.modified,
            member.external_attr,
            member.needed,
            data_offset,
        )
    if cursor != central_offset:
        raise ToolkitWheelError("ZIP has undeclared bytes before central directory")
    return [located[member.name] for member in members]


def _unpack_member(data: bytes, member: _Member) -> bytes:
    compressed = memoryview(data)[
        member.data_offset : member.data_offset + member.compressed
    ]
    output = bytearray()
    crc = 0

    def consume(chunk: bytes) -> None:
        nonlocal crc
        if len(output) + len(chunk) > _member_limit(member.name):
            raise ToolkitWheelError("ZIP member expands beyond its size limit")
        output.extend(chunk)
        crc = binascii.crc32(chunk, crc)

    if member.method == 0:
        for offset in range(0, len(compressed), CHUNK_BYTES):
            consume(bytes(compressed[offset : offset + CHUNK_BYTES]))
    else:
        decompressor = zlib.decompressobj(-15)
        try:
            for offset in range(0, len(compressed), CHUNK_BYTES):
                pending = bytes(compressed[offset : offset + CHUNK_BYTES])
                while pending:
                    remaining = _member_limit(member.name) + 1 - len(output)
                    produced = decompressor.decompress(pending, remaining)
                    consume(produced)
                    if decompressor.unused_data:
                        raise ToolkitWheelError("ZIP member has hidden compressed data")
                    next_pending = decompressor.unconsumed_tail
                    if next_pending == pending and not produced:
                        raise ToolkitWheelError("ZIP decompression made no progress")
                    pending = next_pending
            if not decompressor.eof or decompressor.unused_data:
                raise ToolkitWheelError("ZIP compressed stream is incomplete")
            consume(decompressor.flush())
        except zlib.error as exc:
            raise ToolkitWheelError("ZIP member cannot be decompressed") from exc
    if len(output) != member.uncompressed or crc & 0xFFFFFFFF != member.crc:
        raise ToolkitWheelError("ZIP member size or CRC does not match")
    return bytes(output)


def _headers(
    data: bytes, label: str, *, require_separator: bool = True
) -> dict[str, list[str]]:
    if b"\x00" in data or b"\r" in data.replace(b"\r\n", b""):
        raise ToolkitWheelError(f"{label} has invalid control bytes")
    try:
        text = data.replace(b"\r\n", b"\n").decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ToolkitWheelError(f"{label} is not UTF-8") from exc
    block, separator, _body = text.partition("\n\n")
    if require_separator and not separator:
        raise ToolkitWheelError(f"{label} is missing its header separator")
    result: dict[str, list[str]] = {}
    previous: str | None = None
    for line in block.rstrip("\n").split("\n"):
        if line.startswith((" ", "\t")):
            if previous is None:
                raise ToolkitWheelError(f"{label} has invalid folded headers")
            result[previous][-1] += " " + line.strip()
            continue
        key, colon, value = line.partition(":")
        if not colon or not HEADER_NAME_RE.fullmatch(key):
            raise ToolkitWheelError(f"{label} has a malformed header")
        if any(ord(char) < 32 and char != "\t" for char in value):
            raise ToolkitWheelError(f"{label} has a control character in a header")
        previous = key.casefold()
        result.setdefault(previous, []).append(value.strip())
    return result


def _single(headers: dict[str, list[str]], key: str, label: str) -> str:
    values = headers.get(key.casefold(), [])
    if len(values) != 1 or not values[0]:
        raise ToolkitWheelError(f"{label} must have one {key} header")
    return values[0]


def _specifiers(value: str, label: str) -> frozenset[str]:
    if value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    parts = [part.strip() for part in value.split(",")]
    if not parts or any(not SPECIFIER_RE.fullmatch(part) for part in parts):
        raise ToolkitWheelError(f"{label} has invalid version constraints")
    normalized = frozenset(
        "".join(SPECIFIER_RE.fullmatch(part).groups()) for part in parts
    )
    if len(normalized) != len(parts):
        raise ToolkitWheelError(f"{label} repeats a version constraint")
    return normalized


def _metadata(data: bytes) -> tuple[str, list[str]]:
    headers = _headers(data, "METADATA")
    metadata_version = _single(headers, "Metadata-Version", "METADATA")
    if not re.fullmatch(r"2\.[0-9]+", metadata_version):
        raise ToolkitWheelError("METADATA version is unsupported")
    if _single(headers, "Name", "METADATA") != "specorganon":
        raise ToolkitWheelError("METADATA names a different distribution")
    version = _single(headers, "Version", "METADATA")
    if not VERSION_RE.fullmatch(version):
        raise ToolkitWheelError("METADATA version is not a sensible release version")
    if _single(headers, "Requires-Python", "METADATA").replace(" ", "") != ">=3.11":
        raise ToolkitWheelError("METADATA does not require Python >=3.11")
    extras = headers.get("provides-extra", [])
    if len(extras) != len(set(extras)) or set(extras) - {"dev"}:
        raise ToolkitWheelError("METADATA declares unexpected extras")
    runtime: dict[str, str] = {}
    optional: dict[str, str] = {}
    for requirement in headers.get("requires-dist", []):
        body, semicolon, marker = requirement.partition(";")
        match = REQUIREMENT_RE.fullmatch(body.strip())
        if match is None:
            raise ToolkitWheelError("METADATA has a malformed dependency")
        raw_name, raw_spec = match.groups()
        name = re.sub(r"[-_.]+", "-", raw_name).casefold()
        specs = _specifiers(raw_spec.strip(), f"{name} dependency")
        if semicolon:
            if marker.strip() not in ("extra == 'dev'", 'extra == "dev"'):
                raise ToolkitWheelError(
                    "METADATA has an unexpected conditional dependency"
                )
            if name != "pytest" or specs != frozenset({">=8", "<10"}):
                raise ToolkitWheelError("METADATA has an unexpected dev dependency")
            if name in optional or "dev" not in extras:
                raise ToolkitWheelError("METADATA has a duplicate or undeclared extra")
            optional[name] = requirement
        else:
            expected = {
                "cryptography": frozenset({">=41", "<51"}),
                "mcp": frozenset({">=2.2", "<3"}),
            }
            if name not in expected or specs != expected[name] or name in runtime:
                raise ToolkitWheelError("METADATA has unexpected runtime dependencies")
            runtime[name] = requirement
    if set(runtime) != {"cryptography", "mcp"}:
        raise ToolkitWheelError("METADATA is missing a required runtime dependency")
    return version, [runtime[name] for name in sorted(runtime)]


def _wheel_metadata(data: bytes) -> None:
    headers = _headers(data, "WHEEL", require_separator=False)
    if (
        _single(headers, "Wheel-Version", "WHEEL") != "1.0"
        or _single(headers, "Root-Is-Purelib", "WHEEL").casefold() != "true"
        or headers.get("tag") != ["py3-none-any"]
    ):
        raise ToolkitWheelError("WHEEL is not a pure py3-none-any wheel")


def _entry_points(data: bytes) -> None:
    try:
        text = data.decode("utf-8", errors="strict")
        parser = configparser.RawConfigParser(strict=True, interpolation=None)
        parser.optionxform = str
        parser.read_string(text)
    except (UnicodeError, configparser.Error) as exc:
        raise ToolkitWheelError("entry_points.txt is malformed") from exc
    if (
        parser.defaults()
        or parser.sections() != ["console_scripts"]
        or dict(parser.items("console_scripts"))
        != {
            "organon": "specorganon.cli:main",
            "organon-mcp": "specorganon.server:main",
        }
    ):
        raise ToolkitWheelError("entry_points.txt has unexpected console scripts")


def _record(data: bytes, entries: dict[str, bytes], record_path: str) -> None:
    try:
        text = data.decode("utf-8", errors="strict")
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except (UnicodeError, csv.Error) as exc:
        raise ToolkitWheelError("RECORD is malformed") from exc
    seen: set[str] = set()
    for row in rows:
        if len(row) != 3:
            raise ToolkitWheelError("RECORD row must have three fields")
        name, encoded_digest, encoded_size = row
        if name in seen or name not in entries:
            raise ToolkitWheelError("RECORD has a duplicate or unknown path")
        seen.add(name)
        if name == record_path:
            if encoded_digest or encoded_size:
                raise ToolkitWheelError(
                    "RECORD self-entry must have empty hash and size"
                )
            continue
        if not re.fullmatch(r"sha256=[A-Za-z0-9_-]{43}", encoded_digest):
            raise ToolkitWheelError("RECORD hash is not unpadded URL-safe SHA-256")
        digest = base64.urlsafe_b64encode(hashlib.sha256(entries[name]).digest())
        if encoded_digest != "sha256=" + digest.decode("ascii").rstrip("="):
            raise ToolkitWheelError("RECORD hash differs from member bytes")
        if not re.fullmatch(r"0|[1-9][0-9]*", encoded_size):
            raise ToolkitWheelError("RECORD member size is invalid")
        if int(encoded_size) != len(entries[name]):
            raise ToolkitWheelError("RECORD size differs from member bytes")
    if seen != set(entries):
        raise ToolkitWheelError("RECORD does not list every wheel member exactly once")


def inspect_toolkit_wheel(path: Path | str) -> dict[str, Any]:
    """Validate the candidate's bounded ZIP and wheel metadata without execution."""
    data = _read_regular_path(path)
    members, central_offset = _parse_central(data)
    members = _parse_locals(data, members, central_offset)
    names = {member.name for member in members}
    path_keys = {unicodedata.normalize("NFC", name).casefold() for name in names}
    for name in names:
        parts = name.split("/")
        for length in range(1, len(parts)):
            prefix = unicodedata.normalize("NFC", "/".join(parts[:length])).casefold()
            if prefix in path_keys:
                raise ToolkitWheelError("wheel file path collides with a directory")
    dist_info_roots = {
        name.split("/", 1)[0]
        for name in names
        if name.startswith("specorganon-") and ".dist-info/" in name
    }
    if len(dist_info_roots) != 1:
        raise ToolkitWheelError(
            "wheel must contain one SpecOrganon dist-info directory"
        )
    dist_info = next(iter(dist_info_roots))
    if not re.fullmatch(r"specorganon-[A-Za-z0-9.+_-]+\.dist-info", dist_info):
        raise ToolkitWheelError("wheel dist-info directory is invalid")
    for name in names:
        if not (name.startswith("specorganon/") or name.startswith(dist_info + "/")):
            raise ToolkitWheelError(
                "wheel has a member outside the package or dist-info"
            )
        if name.casefold().endswith((".so", ".pyd", ".dll", ".dylib")):
            raise ToolkitWheelError("pure wheel contains a native binary")
    required = {f"specorganon/{name}" for name in CORE_MODULES}
    required |= {
        f"{dist_info}/METADATA",
        f"{dist_info}/WHEEL",
        f"{dist_info}/entry_points.txt",
        f"{dist_info}/RECORD",
    }
    if not required <= names:
        raise ToolkitWheelError("wheel is missing core modules or metadata")
    entries = {member.name: _unpack_member(data, member) for member in members}
    version, dependencies = _metadata(entries[f"{dist_info}/METADATA"])
    if dist_info != f"specorganon-{version}.dist-info":
        raise ToolkitWheelError(
            "wheel dist-info directory disagrees with METADATA version"
        )
    _wheel_metadata(entries[f"{dist_info}/WHEEL"])
    _entry_points(entries[f"{dist_info}/entry_points.txt"])
    _record(entries[f"{dist_info}/RECORD"], entries, f"{dist_info}/RECORD")
    return {
        "schema": 1,
        "classification": CLASSIFICATION,
        "sha256": hashlib.sha256(data).hexdigest(),
        "version": version,
        "dependencies": dependencies,
        "file_count": len(entries),
        "static_format_checked": True,
        "install_checked": False,
        "execution_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("toolkit", help="path to released toolkit bytes")
    args = parser.parse_args(argv)
    try:
        result = inspect_toolkit_wheel(args.toolkit)
    except ToolkitWheelError as exc:
        print(f"Toolkit wheel inspection failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
