"""Cooperative, durable admission for one local attempt of a scheduled run.

All invocations on a host must use the same registry root. The default is fixed
from the effective UID's passwd entry, never HOME or TMPDIR. An explicit root
override is for tests or an operator who configures *every* invoker alike.
This protects against cooperating processes of the same UID; it is not external
custody and cannot prevent that UID from modifying its own files.

The caller must establish retry eligibility against the separate block release
gate before using an attempt greater than one. This registry only prevents two
local owners from claiming the same scheduled attempt.
"""

from __future__ import annotations

import ctypes
import errno
import fcntl
import hashlib
import json
import os
import pwd
import secrets
import stat
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Iterator

from tool_policy import _check_directory_chain, _open_directory_chain, _same_file_state


SCHEMA = 1
SCOPE = "same_uid_host_one_registry_root"
ROOT_ENV = "SPECORGANON_LOCAL_ADMISSION_ROOT"
MAX_CLAIM_BYTES = 4096
MAX_ATTEMPT_NUMBER = 11
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
_RENAME_NOREPLACE = 1


class AdmissionError(ValueError):
    """A local run claim is absent, malformed, claimed, or cannot be trusted."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(value: Any) -> str:
    return _sha(_canonical(value))


def _sha256(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def configured_root(override: Path | str | None = None) -> Path:
    """Select exactly one registry root for this invocation."""
    declared = override if override is not None else os.environ.get(ROOT_ENV)
    if declared is None:
        declared = Path(pwd.getpwuid(os.geteuid()).pw_dir) / ".specorganon-local-admissions-v1"
    path = Path(declared)
    raw = os.fspath(declared)
    if (not path.is_absolute() or path == Path("/") or raw.endswith("/")
        or any(part in (".", "..", "") for part in raw.split("/")[1:])
        or "\x00" in raw):
        raise AdmissionError("admission root must be an absolute path without dot components")
    return path


def owner(mode: str, stage: Path | str, destination: Path | str) -> dict[str, str]:
    if mode not in {"staged", "oneshot"}:
        raise AdmissionError("unknown local admission owner mode")
    stage_path, target_path = Path(stage), Path(destination)
    for path in (stage_path, target_path):
        if not path.is_absolute() or any(part in (".", "..") for part in path.parts):
            raise AdmissionError("local admission owner paths must be absolute")
    return {"mode": mode, "stage_dir": str(stage_path),
            "session_dir" if mode == "staged" else "receipt_dir": str(target_path)}


def _rename_noreplace(directory_fd: int, source: str, target: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise AdmissionError("atomic no-overwrite rename is unavailable on this host")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                          ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(directory_fd, os.fsencode(source), directory_fd,
                 os.fsencode(target), _RENAME_NOREPLACE) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), target)


@contextmanager
def _root_fd(path: Path, *, create: bool) -> Iterator[int]:
    with ExitStack() as stack:
        parent_fd, name, chain = _open_directory_chain(path, "admission root", stack)
        _check_directory_chain(chain, "admission root")
        parent = os.fstat(parent_fd)
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid()
            or parent.st_mode & 0o022):
            raise AdmissionError("admission root parent must be owned by UID and not writable by others")
        if create:
            try:
                os.mkdir(name, 0o700, dir_fd=parent_fd)
            except FileExistsError:
                pass
            else:
                os.fsync(parent_fd)
        fd = os.open(name, DIR_FLAGS, dir_fd=parent_fd)
        stack.callback(os.close, fd)
        opened = os.fstat(fd)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (not stat.S_ISDIR(opened.st_mode) or not _same_file_state(opened, named)
            or opened.st_uid != os.geteuid() or stat.S_IMODE(opened.st_mode) != 0o700):
            raise AdmissionError("admission root is not a private unchanged directory")
        _check_directory_chain(chain, "admission root")
        yield fd
        if not _same_file_state(os.fstat(fd), os.stat(name, dir_fd=parent_fd, follow_symlinks=False)):
            raise AdmissionError("admission root changed during operation")
        _check_directory_chain(chain, "admission root")


def descriptor(override: Path | str | None = None, *, create: bool = True) -> dict[str, str]:
    path = configured_root(override)
    with _root_fd(path, create=create) as fd:
        return _descriptor_fd(path, fd)


def _descriptor_fd(path: Path, fd: int) -> dict[str, str]:
    info = os.fstat(fd)
    identity = _digest({"path": str(path), "device": info.st_dev, "inode": info.st_ino})
    return {"local_run_admission_root": str(path),
            "local_run_admission_root_identity": identity,
            "local_run_admission_scope": SCOPE}


def _key(schedule_sha256: str, run_id: str, attempt_number: int = 1) -> str:
    if not _sha256(schedule_sha256) or type(run_id) is not str or not run_id or len(run_id) > 256:
        raise AdmissionError("invalid validated schedule/run identity for local admission")
    if type(attempt_number) is not int or not 1 <= attempt_number <= MAX_ATTEMPT_NUMBER:
        raise AdmissionError("invalid local admission attempt number")
    identity = {"schedule_sha256": schedule_sha256, "run_id": run_id}
    if attempt_number > 1:
        identity["attempt_number"] = attempt_number
    return _digest(identity)


def _claim(schedule_sha256: str, run_id: str, selected_owner: dict[str, str],
           root_descriptor: dict[str, str], attempt_number: int = 1) -> dict[str, Any]:
    _key(schedule_sha256, run_id, attempt_number)
    if selected_owner != owner(selected_owner.get("mode", ""),
                               selected_owner.get("stage_dir", ""),
                               selected_owner.get("session_dir", selected_owner.get("receipt_dir", ""))):
        raise AdmissionError("invalid local admission owner")
    return {"schema": SCHEMA, "classification": "development_local_run_admission_unsealed",
            "schedule_sha256": schedule_sha256, "run_id": run_id, "attempt_number": attempt_number,
            "owner": selected_owner, **root_descriptor}


def claim_digest(schedule_sha256: str, run_id: str, selected_owner: dict[str, str],
                 root_descriptor: dict[str, str], *, attempt_number: int = 1) -> str:
    return _digest(_claim(schedule_sha256, run_id, selected_owner, root_descriptor,
                          attempt_number))


def _read_claim(fd: int, name: str) -> bytes:
    file_fd = os.open(name, FILE_FLAGS, dir_fd=fd)
    try:
        before = os.fstat(file_fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1
            or before.st_size > MAX_CLAIM_BYTES):
            raise AdmissionError("local admission claim is not a private bounded file")
        data = os.read(file_fd, MAX_CLAIM_BYTES + 1)
        after = os.fstat(file_fd)
        named = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if len(data) != before.st_size or not _same_file_state(before, after) or not _same_file_state(before, named):
            raise AdmissionError("local admission claim changed during reading")
        os.fsync(file_fd)
        os.fsync(fd)
        return data
    finally:
        os.close(file_fd)


def _parse_claim(data: bytes) -> dict[str, Any]:
    try:
        value = json.loads(data)
        if type(value) is not dict or _canonical(value) != data:
            raise ValueError("noncanonical claim")
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise AdmissionError("local admission claim is malformed") from exc
    return value


def publish_claim(schedule_sha256: str, run_id: str, selected_owner: dict[str, str],
                  root_descriptor: dict[str, str], *,
                  override: Path | str | None = None, attempt_number: int = 1) -> str:
    """Fsync a temporary claim, then publish it once under an exclusive lock."""
    expected = _claim(schedule_sha256, run_id, selected_owner, root_descriptor,
                      attempt_number)
    data = _canonical(expected)
    if len(data) > MAX_CLAIM_BYTES:
        raise AdmissionError("local admission claim exceeds byte limit")
    path = configured_root(override)
    if root_descriptor != descriptor(path, create=False):
        raise AdmissionError("admission registry root identity changed")
    name = f"{_key(schedule_sha256, run_id, attempt_number)}.json"
    temp = f".{name}.{secrets.token_hex(16)}.tmp"
    with _root_fd(path, create=False) as fd:
        temporary_fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                               0o600, dir_fd=fd)
        try:
            offset = 0
            while offset < len(data):
                count = os.write(temporary_fd, data[offset:])
                if count <= 0:
                    raise OSError("local admission temporary write made no progress")
                offset += count
            os.fsync(temporary_fd)
        finally:
            os.close(temporary_fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            if root_descriptor != _descriptor_fd(path, fd):
                raise AdmissionError("admission registry root identity changed")
            try:
                os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise AdmissionError("scheduled run already has a local admission claim")
            try:
                _rename_noreplace(fd, temp, name)
            except OSError as exc:
                if exc.errno == errno.EEXIST:
                    raise AdmissionError("scheduled run already has a local admission claim") from exc
                raise
            os.fsync(fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    return _sha(data)


def require_claim(schedule_sha256: str, run_id: str, selected_owner: dict[str, str],
                  root_descriptor: dict[str, str], *,
                  override: Path | str | None = None, allow_missing: bool = False,
                  attempt_number: int = 1) -> str | None:
    """Read and durably confirm the owner's immutable claim before launch."""
    expected = _claim(schedule_sha256, run_id, selected_owner, root_descriptor,
                      attempt_number)
    path = configured_root(override)
    if root_descriptor != descriptor(path, create=False):
        raise AdmissionError("admission registry root identity differs from recorded root")
    with _root_fd(path, create=False) as fd:
        fcntl.flock(fd, fcntl.LOCK_SH)
        try:
            if root_descriptor != _descriptor_fd(path, fd):
                raise AdmissionError("admission registry root identity differs from recorded root")
            try:
                data = _read_claim(fd, f"{_key(schedule_sha256, run_id, attempt_number)}.json")
            except FileNotFoundError as exc:
                os.fsync(fd)
                if allow_missing:
                    return None
                raise AdmissionError("local admission claim is missing") from exc
            claim = _parse_claim(data)
            if data != _canonical(expected):
                if claim.get("owner") != selected_owner:
                    raise AdmissionError("scheduled run is claimed by another local owner")
                raise AdmissionError("local admission claim identity is malformed or changed")
            return _sha(data)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)


def acquire_staged_claim(schedule_sha256: str, run_id: str,
                         selected_owner: dict[str, str], root_descriptor: dict[str, str],
                         *, override: Path | str | None = None,
                         attempt_number: int = 1) -> str:
    """First call claims; the same owner may recover before its first reservation."""
    existing = require_claim(schedule_sha256, run_id, selected_owner, root_descriptor,
                             override=override, allow_missing=True,
                             attempt_number=attempt_number)
    if existing is not None:
        return existing
    try:
        return publish_claim(schedule_sha256, run_id, selected_owner, root_descriptor,
                             override=override, attempt_number=attempt_number)
    except AdmissionError as exc:
        if "already has a local admission claim" not in str(exc):
            raise
        # Another claimant may have won after the missing-claim read. Only the
        # exact same stage/session owner can continue from this point.
        confirmed = require_claim(schedule_sha256, run_id, selected_owner,
                                  root_descriptor, override=override,
                                  attempt_number=attempt_number)
        assert confirmed is not None
        return confirmed
