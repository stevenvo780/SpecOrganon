"""Build and inspect a bounded, unsealed offline toolkit wheel bundle.

Usage::

    python scripts/toolkit_bundle.py pack WHEEL_DIR UV_LOCK OUTPUT
    python scripts/toolkit_bundle.py inspect BUNDLE
    python scripts/toolkit_bundle.py extract BUNDLE /absolute/new/directory

The bundle binds its own lock bytes and the included wheel files. Its lock is
caller-supplied and unauthenticated. Dependency closure, installation, runtime
isolation, and execution are not established by this static inspection.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import io
import json
import os
import platform
import re
import stat
import struct
import sys
import tomllib
import zipfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from inspect_toolkit_wheel import (
    ToolkitWheelError,
    _read_regular_path,
    inspect_toolkit_wheel_bytes,
)


MAX_BUNDLE_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_LOCK_BYTES = 2 * 1024 * 1024
MAX_WHEELS = 128
CLASSIFICATION = "development_toolkit_bundle_unsealed"
DEFAULT_TARGET = {
    "python_implementation": "CPython",
    "python_version": "3.12",
    "platform": "linux_x86_64",
}
SUPPORTED_PYTHON_VERSIONS = frozenset({"3.11", "3.12"})
BUNDLE_FIELDS = frozenset(
    {"schema", "classification", "target", "uv_lock_sha256", "wheels", "root_wheel"}
)
WHEEL_FIELDS = frozenset({"filename", "sha256", "bytes"})
TARGET_FIELDS = frozenset(DEFAULT_TARGET)
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
WHEEL_FILENAME_RE = re.compile(
    r"[A-Za-z0-9_]+-[A-Za-z0-9._+]+-[A-Za-z0-9._]+-[A-Za-z0-9._]+-[A-Za-z0-9._]+\.whl\Z"
)
LOCAL_HEADER = struct.Struct("<IHHHHHIIIHH")
CENTRAL_HEADER = struct.Struct("<IHHHHHHIIIHHHHHII")
END_RECORD = struct.Struct("<IHHHHIIH")
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC


class ToolkitBundleError(ValueError):
    """The bundle, embedded lock, or requested wheel set is invalid."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ToolkitBundleError("bundle.json has duplicate keys")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ToolkitBundleError("bundle.json has non-JSON numeric data")


def _exact_object(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise ToolkitBundleError(f"{label} has unexpected or missing fields")
    return value


def _target(value: Any) -> dict[str, str]:
    target = _exact_object(value, TARGET_FIELDS, "target")
    if (
        any(type(target[field]) is not str for field in TARGET_FIELDS)
        or target["python_implementation"] != "CPython"
        or target["python_version"] not in SUPPORTED_PYTHON_VERSIONS
        or target["platform"] != "linux_x86_64"
    ):
        raise ToolkitBundleError(
            "target must declare CPython 3.11 or 3.12 on Linux x86_64"
        )
    return dict(target)


def _filename(
    value: Any,
    *,
    target: dict[str, str] | None = None,
    require_compatible: bool = True,
) -> tuple[str, str]:
    if (
        type(value) is not str
        or len(value) > 200
        or WHEEL_FILENAME_RE.fullmatch(value) is None
    ):
        raise ToolkitBundleError("wheel filename is invalid or unsafe")
    parts = value[:-4].split("-")
    if len(parts) != 5:
        raise ToolkitBundleError("wheel filename must have five standard components")
    distribution, version, python_tag, abi_tag, platform_tag = parts
    if require_compatible:
        checked_target = _target(DEFAULT_TARGET if target is None else target)
        if not _compatible_tags(
            python_tag, abi_tag, platform_tag, checked_target["python_version"]
        ):
            raise ToolkitBundleError(
                "wheel filename is incompatible with bundle target"
            )
    return re.sub(r"[-_.]+", "-", distribution).casefold(), version


def _compatible_tags(
    python_tag: str,
    abi_tag: str,
    platform_tag: str,
    python_version: str = DEFAULT_TARGET["python_version"],
) -> bool:
    if python_version not in SUPPORTED_PYTHON_VERSIONS:
        return False
    target_minor = int(python_version.split(".")[1])
    exact_python = f"py3{target_minor}"
    exact_cpython = f"cp3{target_minor}"
    python_tags = python_tag.split(".")
    platforms = platform_tag.split(".")
    pure = (
        abi_tag == "none"
        and "any" in platforms
        and any(tag in {"py3", exact_python, exact_cpython} for tag in python_tags)
    )
    if pure:
        return True
    libc_name, libc_version = platform.libc_ver()
    if (
        sys.platform != "linux"
        or platform.machine().lower() not in {"x86_64", "amd64"}
        or libc_name != "glibc"
        or re.fullmatch(r"[0-9]+\.[0-9]+", libc_version) is None
    ):
        return False
    host_glibc = tuple(int(part) for part in libc_version.split("."))

    def supports_platform(tag: str) -> bool:
        if tag == "linux_x86_64":
            return True
        aliases = {
            "manylinux1_x86_64": (2, 5),
            "manylinux2010_x86_64": (2, 12),
            "manylinux2014_x86_64": (2, 17),
        }
        if tag in aliases:
            return aliases[tag] <= host_glibc
        match = re.fullmatch(r"manylinux_([0-9]+)_([0-9]+)_x86_64", tag)
        if match is None:
            return False
        required_glibc = tuple(map(int, match.groups()))
        if tag != f"manylinux_{required_glibc[0]}_{required_glibc[1]}_x86_64":
            return False
        return (2, 5) <= required_glibc <= host_glibc

    linux = any(supports_platform(tag) for tag in platforms)
    if not linux:
        return False
    if abi_tag == "none" and any(tag in {"py3", exact_python} for tag in python_tags):
        return True
    if abi_tag == exact_cpython and exact_cpython in python_tags:
        return True
    return abi_tag == "abi3" and any(
        tag.startswith("cp3")
        and tag[3:].isdigit()
        and 2 <= int(tag[3:]) <= target_minor
        for tag in python_tags
    )


def _manifest(data: bytes) -> dict[str, Any]:
    if not 1 <= len(data) <= MAX_MANIFEST_BYTES:
        raise ToolkitBundleError("bundle.json exceeds size bounds")
    try:
        raw = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
        manifest = _exact_object(raw, BUNDLE_FIELDS, "bundle.json")
        if _canonical(manifest) != data:
            raise ToolkitBundleError("bundle.json is not canonical JSON")
    except ToolkitBundleError:
        raise
    except (UnicodeError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise ToolkitBundleError("bundle.json is not strict canonical JSON") from exc
    if type(manifest["schema"]) is not int or manifest["schema"] != 1:
        raise ToolkitBundleError("bundle.json schema must be integer 1")
    if manifest["classification"] != CLASSIFICATION:
        raise ToolkitBundleError("bundle.json classification is invalid")
    checked_target = _target(manifest["target"])
    if (
        type(manifest["uv_lock_sha256"]) is not str
        or SHA256_RE.fullmatch(manifest["uv_lock_sha256"]) is None
    ):
        raise ToolkitBundleError("uv_lock_sha256 is invalid")
    wheels = manifest["wheels"]
    if type(wheels) is not list or not 1 <= len(wheels) <= MAX_WHEELS:
        raise ToolkitBundleError("wheels must be a bounded nonempty list")
    names: list[str] = []
    root_names: list[str] = []
    for item in wheels:
        record = _exact_object(item, WHEEL_FIELDS, "wheel record")
        name, digest, size = record["filename"], record["sha256"], record["bytes"]
        distribution, _version = _filename(name, target=checked_target)
        if type(digest) is not str or SHA256_RE.fullmatch(digest) is None:
            raise ToolkitBundleError("wheel SHA-256 is invalid")
        if type(size) is not int or not 1 <= size <= MAX_BUNDLE_BYTES:
            raise ToolkitBundleError("wheel byte count is invalid")
        names.append(name)
        if distribution == "specorganon":
            root_names.append(name)
    if names != sorted(set(names)):
        raise ToolkitBundleError("wheel records must be unique and sorted")
    if len(root_names) != 1 or manifest["root_wheel"] != root_names[0]:
        raise ToolkitBundleError(
            "bundle must have exactly one named SpecOrganon root wheel"
        )
    return manifest


def _lock_index(data: bytes) -> tuple[dict[str, tuple[str, int, str, str]], str]:
    if not 1 <= len(data) <= MAX_LOCK_BYTES:
        raise ToolkitBundleError("uv.lock exceeds size bounds")
    try:
        lock = tomllib.loads(data.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ToolkitBundleError("uv.lock is not valid UTF-8 TOML") from exc
    if type(lock) is not dict or type(lock.get("package")) is not list:
        raise ToolkitBundleError("uv.lock has no package records")
    result: dict[str, tuple[str, int, str, str]] = {}
    roots: list[str] = []
    package_names: set[str] = set()
    for package in lock["package"]:
        if (
            type(package) is not dict
            or type(package.get("name")) is not str
            or type(package.get("version")) is not str
        ):
            raise ToolkitBundleError("uv.lock package record is invalid")
        normalized = re.sub(r"[-_.]+", "-", package["name"]).casefold()
        if normalized in package_names:
            raise ToolkitBundleError("uv.lock has duplicate package names")
        package_names.add(normalized)
        if normalized == "specorganon":
            roots.append(package["version"])
        wheels = package.get("wheels", [])
        if type(wheels) is not list:
            raise ToolkitBundleError("uv.lock wheels must be a list")
        for wheel in wheels:
            if type(wheel) is not dict:
                raise ToolkitBundleError("uv.lock wheel record is invalid")
            url, digest, size = wheel.get("url"), wheel.get("hash"), wheel.get("size")
            if (
                type(url) is not str
                or type(digest) is not str
                or type(size) is not int
                or size <= 0
            ):
                raise ToolkitBundleError("uv.lock wheel URL, hash, or size is invalid")
            parsed = urlsplit(url)
            filename = parsed.path.rsplit("/", 1)[-1]
            if (
                parsed.scheme not in ("https", "file")
                or parsed.query
                or parsed.fragment
            ):
                raise ToolkitBundleError("uv.lock wheel URL is unsupported")
            dist, version = _filename(filename, require_compatible=False)
            if dist != normalized or version != package["version"]:
                raise ToolkitBundleError("uv.lock wheel filename differs from package")
            if (
                not digest.startswith("sha256:")
                or SHA256_RE.fullmatch(digest[7:]) is None
            ):
                raise ToolkitBundleError("uv.lock wheel hash is invalid")
            if filename in result and result[filename] != (
                digest[7:],
                size,
                normalized,
                version,
            ):
                raise ToolkitBundleError("uv.lock has conflicting wheel records")
            result[filename] = (digest[7:], size, normalized, version)
    if len(roots) != 1:
        raise ToolkitBundleError("uv.lock must contain exactly one SpecOrganon package")
    return result, roots[0]


def _read_bundle(path: Path | str) -> bytes:
    try:
        return _read_regular_path(path)
    except ToolkitWheelError as exc:
        raise ToolkitBundleError(
            "bundle cannot be read securely or exceeds 16 MiB"
        ) from exc


def _zip_members(data: bytes) -> tuple[dict[str, bytes], list[str]]:
    if not END_RECORD.size <= len(data) <= MAX_BUNDLE_BYTES:
        raise ToolkitBundleError("bundle exceeds 16 MiB or is truncated")
    end_offset = len(data) - END_RECORD.size
    (
        signature,
        disk,
        central_disk,
        disk_count,
        count,
        central_size,
        central_offset,
        comment,
    ) = END_RECORD.unpack_from(data, end_offset)
    if (
        signature != 0x06054B50
        or disk
        or central_disk
        or comment
        or count < 3
        or count > MAX_WHEELS + 2
        or disk_count != count
        or central_offset == 0xFFFFFFFF
        or central_size == 0xFFFFFFFF
        or central_offset + central_size != end_offset
    ):
        raise ToolkitBundleError("ZIP end record is invalid or has undeclared bytes")
    central: list[tuple[str, bytes, int, int, int, int, int, int, int]] = []
    cursor = central_offset
    seen: set[str] = set()
    for _ in range(count):
        if cursor + CENTRAL_HEADER.size > end_offset:
            raise ToolkitBundleError("ZIP central directory is truncated")
        (
            magic,
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
            comment_len,
            disk_start,
            internal_attr,
            external_attr,
            local_offset,
        ) = CENTRAL_HEADER.unpack_from(data, cursor)
        name_start = cursor + CENTRAL_HEADER.size
        if name_start + name_len > end_offset:
            raise ToolkitBundleError("ZIP central member name is truncated")
        raw_name = data[name_start : name_start + name_len]
        try:
            name = raw_name.decode(
                "utf-8" if flags & 0x800 else "ascii", errors="strict"
            )
        except UnicodeError as exc:
            raise ToolkitBundleError("ZIP member name is invalid") from exc
        if (
            magic != 0x02014B50
            or made_by >> 8 != 3
            or needed > 20
            or flags & ~0x800
            or method != zipfile.ZIP_STORED
            or compressed != uncompressed
            or extra_len
            or comment_len
            or disk_start
            or internal_attr
            or not stat.S_ISREG(external_attr >> 16)
            or external_attr & 0x10
            or not name
            or len(raw_name) > 240
        ):
            raise ToolkitBundleError("ZIP member has unsupported metadata")
        if name.casefold() in seen:
            raise ToolkitBundleError("ZIP has duplicate or case-colliding names")
        seen.add(name.casefold())
        central.append(
            (
                name,
                raw_name,
                needed,
                flags,
                mod_time,
                mod_date,
                crc,
                uncompressed,
                local_offset,
            )
        )
        cursor = name_start + name_len
    if cursor != end_offset:
        raise ToolkitBundleError("ZIP central directory has a gap or trailer")

    entries: dict[str, bytes] = {}
    local_order: list[str] = []
    cursor = 0
    for (
        name,
        raw_name,
        needed,
        flags,
        mod_time,
        mod_date,
        crc,
        size,
        local_offset,
    ) in sorted(central, key=lambda item: item[-1]):
        if local_offset != cursor or cursor + LOCAL_HEADER.size > central_offset:
            raise ToolkitBundleError("ZIP has a prefix, gap, or overlapping members")
        (
            magic,
            local_needed,
            local_flags,
            method,
            local_time,
            local_date,
            local_crc,
            compressed,
            uncompressed,
            name_len,
            extra_len,
        ) = LOCAL_HEADER.unpack_from(data, cursor)
        name_start = cursor + LOCAL_HEADER.size
        data_start = name_start + name_len
        data_end = data_start + size
        if (
            magic != 0x04034B50
            or local_needed != needed
            or local_flags != flags
            or method != zipfile.ZIP_STORED
            or (local_time, local_date) != (mod_time, mod_date)
            or (local_crc, compressed, uncompressed) != (crc, size, size)
            or extra_len
            or data_end > central_offset
            or data[name_start:data_start] != raw_name
        ):
            raise ToolkitBundleError("ZIP local header differs from directory")
        payload = data[data_start:data_end]
        if binascii.crc32(payload) & 0xFFFFFFFF != crc:
            raise ToolkitBundleError("ZIP member CRC differs from bytes")
        entries[name] = payload
        local_order.append(name)
        cursor = data_end
    if cursor != central_offset:
        raise ToolkitBundleError("ZIP has undeclared bytes before central directory")
    return entries, local_order


def _inspect_bytes(data: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    entries, local_order = _zip_members(data)
    manifest_bytes = entries.get("bundle.json")
    lock_bytes = entries.get("uv.lock")
    if manifest_bytes is None or lock_bytes is None:
        raise ToolkitBundleError("bundle.json or uv.lock is missing")
    manifest = _manifest(manifest_bytes)
    if _sha(lock_bytes) != manifest["uv_lock_sha256"]:
        raise ToolkitBundleError("uv.lock bytes differ from bundle.json")
    locked_wheels, root_version = _lock_index(lock_bytes)
    records = manifest["wheels"]
    expected_names = [
        "bundle.json",
        "uv.lock",
        *("wheels/" + item["filename"] for item in records),
    ]
    if local_order != expected_names or list(entries) != expected_names:
        raise ToolkitBundleError("ZIP members differ from sorted bundle.json records")
    seen_distributions: set[str] = set()
    root_result: dict[str, Any] | None = None
    for item in records:
        filename = item["filename"]
        payload = entries["wheels/" + filename]
        if len(payload) != item["bytes"] or _sha(payload) != item["sha256"]:
            raise ToolkitBundleError("wheel bytes differ from bundle.json")
        distribution, version = _filename(filename, target=manifest["target"])
        if distribution in seen_distributions:
            raise ToolkitBundleError("bundle has multiple wheels for one distribution")
        seen_distributions.add(distribution)
        if filename == manifest["root_wheel"]:
            if version != root_version:
                raise ToolkitBundleError("root wheel version differs from uv.lock")
            try:
                root_result = inspect_toolkit_wheel_bytes(payload)
            except ToolkitWheelError as exc:
                raise ToolkitBundleError(
                    "root SpecOrganon wheel failed static inspection"
                ) from exc
            if root_result["version"] != version:
                raise ToolkitBundleError(
                    "root wheel filename differs from METADATA version"
                )
        else:
            locked = locked_wheels.get(filename)
            if locked is None or locked != (
                item["sha256"],
                item["bytes"],
                distribution,
                version,
            ):
                raise ToolkitBundleError(
                    "dependency wheel differs from embedded uv.lock"
                )
    if root_result is None:
        raise ToolkitBundleError("root wheel is missing")
    return {
        "schema": 1,
        "classification": "development_toolkit_bundle_inspection_unsealed",
        "sha256": _sha(data),
        "version": root_result["version"],
        "wheel_count": len(records),
        "target": dict(manifest["target"]),
        "uv_lock_sha256": manifest["uv_lock_sha256"],
        "container_format_checked": True,
        "root_wheel_format_checked": True,
        "dependency_wheel_format_checked": False,
        "static_format_checked": len(records) == 1,
        "install_checked": False,
        "execution_ready": False,
    }, entries


def inspect_toolkit_bundle(path: Path | str) -> dict[str, Any]:
    """Inspect a released bundle without extraction, import, or installation."""
    result, _entries = _inspect_bytes(_read_bundle(path))
    return result


def _directory_identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), info.st_uid)


def _file_state(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _check_parent_chain(
    chain: list[tuple[int, str, int, tuple[int, int, int, int]]],
) -> None:
    for parent_fd, name, opened_fd, identity in chain:
        opened = os.fstat(opened_fd)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            _directory_identity(opened) != identity
            or _directory_identity(named) != identity
        ):
            raise ToolkitBundleError("output parent path changed during writing")


def _check_named_directory(
    parent_fd: int, name: str, opened_fd: int, identity: tuple[int, int, int, int]
) -> None:
    opened = os.fstat(opened_fd)
    named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (
        _directory_identity(opened) != identity
        or _directory_identity(named) != identity
        or stat.S_IMODE(opened.st_mode) != 0o700
        or stat.S_IMODE(named.st_mode) != 0o700
    ):
        raise ToolkitBundleError("extract destination identity changed during writing")


def _check_named_file(
    parent_fd: int, name: str, original: os.stat_result, expected: bytes
) -> None:
    fd = os.open(
        name,
        os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
        dir_fd=parent_fd,
    )
    try:
        before = os.fstat(fd)
        named_before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or _file_state(before) != _file_state(original)
            or _file_state(named_before) != _file_state(original)
        ):
            raise ToolkitBundleError("output file identity changed during writing")
        digest = hashlib.sha256()
        total = 0
        while chunk := os.read(fd, min(64 * 1024, len(expected) - total + 1)):
            total += len(chunk)
            if total > len(expected):
                raise ToolkitBundleError("output file grew during verification")
            digest.update(chunk)
        after = os.fstat(fd)
        named_after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            total != len(expected)
            or digest.hexdigest() != _sha(expected)
            or _file_state(after) != _file_state(original)
            or _file_state(named_after) != _file_state(original)
        ):
            raise ToolkitBundleError(
                "output file bytes or identity changed during writing"
            )
    finally:
        os.close(fd)


def _parent_fd(
    path: Path | str, stack: ExitStack
) -> tuple[int, str, list[tuple[int, str, int, tuple[int, int, int, int]]]]:
    raw = os.fspath(path)
    if type(raw) is not str or not raw.startswith("/") or "\x00" in raw:
        raise ToolkitBundleError("output must be an absolute path")
    parts = raw.split("/")[1:]
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ToolkitBundleError("output path has unsafe components")
    current = os.open("/", DIRECTORY_FLAGS)
    stack.callback(os.close, current)
    chain: list[tuple[int, str, int, tuple[int, int, int, int]]] = []
    for part in parts[:-1]:
        child = os.open(part, DIRECTORY_FLAGS, dir_fd=current)
        stack.callback(os.close, child)
        chain.append((current, part, child, _directory_identity(os.fstat(child))))
        current = child
    _check_parent_chain(chain)
    parent = os.fstat(current)
    if parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
        raise ToolkitBundleError(
            "output parent must be private and owned by current UID"
        )
    return current, parts[-1], chain


def _write_new_file(path: Path | str, data: bytes) -> None:
    try:
        with ExitStack() as stack:
            parent_fd, name, chain = _parent_fd(path, stack)
            fd = os.open(name, FILE_FLAGS, 0o600, dir_fd=parent_fd)
            with os.fdopen(fd, "wb") as output:
                os.fchmod(output.fileno(), 0o600)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
                original = os.fstat(output.fileno())
            _check_parent_chain(chain)
            _check_named_file(parent_fd, name, original, data)
            _check_parent_chain(chain)
    except FileExistsError as exc:
        raise ToolkitBundleError("output already exists") from exc
    except OSError as exc:
        raise ToolkitBundleError("output could not be written securely") from exc


def pack_toolkit_bundle(
    wheel_dir: Path | str,
    lock_path: Path | str,
    target: dict[str, str],
    output_path: Path | str,
) -> dict[str, Any]:
    """Pack one deterministic bundle from local wheels and an unauthenticated lock."""
    checked_target = _target(target)
    try:
        lock_bytes = _read_regular_path(lock_path)
    except ToolkitWheelError as exc:
        raise ToolkitBundleError("uv.lock cannot be read securely") from exc
    locked_wheels, root_version = _lock_index(lock_bytes)
    directory = Path(wheel_dir)
    if not directory.is_dir() or directory.is_symlink():
        raise ToolkitBundleError("wheel_dir must be a real directory")
    wheel_files = sorted(directory.iterdir(), key=lambda item: item.name)
    if not 1 <= len(wheel_files) <= MAX_WHEELS:
        raise ToolkitBundleError("wheel_dir has an invalid wheel count")
    records: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    roots: list[str] = []
    distributions: set[str] = set()
    for path in wheel_files:
        distribution, version = _filename(path.name, target=checked_target)
        if distribution in distributions:
            raise ToolkitBundleError(
                "wheel_dir has multiple wheels for one distribution"
            )
        distributions.add(distribution)
        try:
            payload = _read_regular_path(path)
        except ToolkitWheelError as exc:
            raise ToolkitBundleError("wheel cannot be read securely") from exc
        digest, size = _sha(payload), len(payload)
        if distribution == "specorganon":
            roots.append(path.name)
            if version != root_version:
                raise ToolkitBundleError("root wheel version differs from uv.lock")
            try:
                inspected = inspect_toolkit_wheel_bytes(payload)
            except ToolkitWheelError as exc:
                raise ToolkitBundleError("root wheel failed static inspection") from exc
            if inspected["version"] != version:
                raise ToolkitBundleError("root filename differs from METADATA version")
        elif locked_wheels.get(path.name) != (digest, size, distribution, version):
            raise ToolkitBundleError("dependency wheel differs from uv.lock")
        records.append({"filename": path.name, "sha256": digest, "bytes": size})
        payloads[path.name] = payload
    if len(roots) != 1:
        raise ToolkitBundleError(
            "wheel_dir must contain exactly one SpecOrganon root wheel"
        )
    manifest = {
        "schema": 1,
        "classification": CLASSIFICATION,
        "target": checked_target,
        "uv_lock_sha256": _sha(lock_bytes),
        "wheels": records,
        "root_wheel": roots[0],
    }
    manifest_bytes = _canonical(manifest)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise ToolkitBundleError("bundle.json exceeds size bounds")
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer, "w", compression=zipfile.ZIP_STORED, allowZip64=False
    ) as archive:
        for name, payload in [
            ("bundle.json", manifest_bytes),
            ("uv.lock", lock_bytes),
            *[("wheels/" + name, payloads[name]) for name in sorted(payloads)],
        ]:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, payload)
    data = buffer.getvalue()
    result, _entries = _inspect_bytes(data)
    _write_new_file(output_path, data)
    return result


def extract_toolkit_bundle(path: Path | str, output_dir: Path | str) -> dict[str, Any]:
    """Write validated member bytes into one new private directory."""
    result, entries = _inspect_bytes(_read_bundle(path))
    try:
        with ExitStack() as stack:
            parent_fd, name, chain = _parent_fd(output_dir, stack)
            os.mkdir(name, 0o700, dir_fd=parent_fd)
            created_root = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            root_fd = os.open(name, DIRECTORY_FLAGS, dir_fd=parent_fd)
            stack.callback(os.close, root_fd)
            os.fchmod(root_fd, 0o700)
            root_identity = _directory_identity(created_root)
            _check_parent_chain(chain)
            _check_named_directory(parent_fd, name, root_fd, root_identity)
            os.mkdir("wheels", 0o700, dir_fd=root_fd)
            created_wheels = os.stat("wheels", dir_fd=root_fd, follow_symlinks=False)
            wheels_fd = os.open("wheels", DIRECTORY_FLAGS, dir_fd=root_fd)
            stack.callback(os.close, wheels_fd)
            os.fchmod(wheels_fd, 0o700)
            wheels_identity = _directory_identity(created_wheels)
            _check_parent_chain(chain)
            _check_named_directory(parent_fd, name, root_fd, root_identity)
            _check_named_directory(root_fd, "wheels", wheels_fd, wheels_identity)
            originals: dict[str, os.stat_result] = {}
            for entry_name, payload in entries.items():
                directory_fd, file_name = (
                    (wheels_fd, entry_name.removeprefix("wheels/"))
                    if entry_name.startswith("wheels/")
                    else (root_fd, entry_name)
                )
                fd = os.open(file_name, FILE_FLAGS, 0o600, dir_fd=directory_fd)
                with os.fdopen(fd, "wb") as output:
                    os.fchmod(output.fileno(), 0o600)
                    output.write(payload)
                    output.flush()
                    os.fsync(output.fileno())
                    originals[entry_name] = os.fstat(output.fileno())
                _check_parent_chain(chain)
                _check_named_directory(parent_fd, name, root_fd, root_identity)
                _check_named_directory(root_fd, "wheels", wheels_fd, wheels_identity)
            for entry_name, payload in entries.items():
                directory_fd, file_name = (
                    (wheels_fd, entry_name.removeprefix("wheels/"))
                    if entry_name.startswith("wheels/")
                    else (root_fd, entry_name)
                )
                _check_named_file(
                    directory_fd, file_name, originals[entry_name], payload
                )
            _check_parent_chain(chain)
            _check_named_directory(parent_fd, name, root_fd, root_identity)
            _check_named_directory(root_fd, "wheels", wheels_fd, wheels_identity)
    except FileExistsError as exc:
        raise ToolkitBundleError(
            "extract destination already exists; no files were overwritten"
        ) from exc
    except OSError as exc:
        raise ToolkitBundleError(
            "extract failed; any partial destination is untrusted"
        ) from exc
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("pack")
    pack.add_argument("wheel_dir")
    pack.add_argument("uv_lock")
    pack.add_argument("output")
    pack.add_argument(
        "--python-version", choices=sorted(SUPPORTED_PYTHON_VERSIONS), default="3.12"
    )
    inspect = commands.add_parser("inspect")
    inspect.add_argument("bundle")
    extract = commands.add_parser("extract")
    extract.add_argument("bundle")
    extract.add_argument("output_dir")
    args = parser.parse_args(argv)
    try:
        if args.command == "pack":
            result = pack_toolkit_bundle(
                args.wheel_dir,
                args.uv_lock,
                {**DEFAULT_TARGET, "python_version": args.python_version},
                args.output,
            )
        elif args.command == "extract":
            result = extract_toolkit_bundle(args.bundle, args.output_dir)
        else:
            result = inspect_toolkit_bundle(args.bundle)
    except ToolkitBundleError as exc:
        print(f"Toolkit bundle failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
