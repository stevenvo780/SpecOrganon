"""Verify one unsealed development release against an independently supplied schedule.

Usage: ``python scripts/verify_released_run.py schedule.json /absolute/release``.

This command only reads files. It checks point-in-time byte and metadata
consistency against the caller's candidate schedule. It does not establish a
seal, custody, human review, execution, a receipt, or authorization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from preflight_assets import PreflightError, _candidate_schedule, _selected_assets


CHUNK_SIZE = 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_SCHEDULE_BYTES = 16 * 1024 * 1024
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
MANIFEST_FIELDS = frozenset(
    {
        "schema",
        "classification",
        "notice",
        "run_id",
        "run_sha256",
        "schedule_sha256",
        "coordinates",
        "limits",
        "files",
    }
)
COORDINATE_FIELDS = (
    "stratum_id",
    "block_id",
    "family",
    "tier",
    "model_id",
    "model_version",
    "effort",
    "effort_provider_value",
    "agents",
    "case_id",
    "replica",
    "order_position",
    "release_block_order",
    "arm",
)
RELEASE_NOTICE = "Independent human content review and external custody are required before case reservation."
VERIFICATION_NOTICE = (
    "Offline consistency against the caller-supplied candidate schedule only; "
    "no seal, custody, human content review, execution, receipt, or authorization is established."
)


class ReleaseVerificationError(ValueError):
    """The candidate schedule or released directory failed a read-only check."""


def _object(raw: Any, label: str, keys: set[str] | frozenset[str]) -> dict[str, Any]:
    if type(raw) is not dict or set(raw) != set(keys):
        raise ReleaseVerificationError(f"{label} must have exactly {sorted(keys)}")
    return raw


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ReleaseVerificationError("duplicate JSON object key")
        value[key] = item
    return value


def _reject_constant(_value: str) -> None:
    raise ReleaseVerificationError("non-JSON numeric constant")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ReleaseVerificationError("nonfinite JSON number")
    return number


def _parse_json(data: bytes, label: str) -> Any:
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except ReleaseVerificationError:
        raise
    except (UnicodeError, ValueError, OverflowError, RecursionError) as exc:
        raise ReleaseVerificationError(f"{label} is not valid strict JSON") from exc


def _read_schedule(path: str) -> Any:
    try:
        fd = os.open(path, FILE_FLAGS)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_SCHEDULE_BYTES:
                raise ReleaseVerificationError(
                    "candidate schedule must be a bounded regular file"
                )
            chunks: list[bytes] = []
            total = 0
            while chunk := os.read(fd, CHUNK_SIZE):
                total += len(chunk)
                if total > MAX_SCHEDULE_BYTES:
                    raise ReleaseVerificationError("candidate schedule is too large")
                chunks.append(chunk)
            after = os.fstat(fd)
            named = os.stat(path, follow_symlinks=False)
            if (
                total != before.st_size
                or not _same_file_state(before, after)
                or not _same_file_state(before, named)
            ):
                raise ReleaseVerificationError(
                    "candidate schedule changed while being read"
                )
        finally:
            os.close(fd)
    except OSError as exc:
        raise ReleaseVerificationError(
            "candidate schedule cannot be read securely"
        ) from exc
    return _parse_json(b"".join(chunks), "candidate schedule")


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ReleaseVerificationError(
            "release manifest contains invalid JSON data"
        ) from exc


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _same_file_state(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        _same_identity(left, right)
        and left.st_mode == right.st_mode
        and left.st_uid == right.st_uid
        and left.st_nlink == right.st_nlink
        and left.st_size == right.st_size
        and left.st_mtime_ns == right.st_mtime_ns
        and left.st_ctime_ns == right.st_ctime_ns
    )


def _open_directory_chain(
    release_dir: Path | str, stack: ExitStack
) -> tuple[int, int, str, list[tuple[int, str, int]], os.stat_result]:
    raw = os.fspath(release_dir)
    if not isinstance(raw, str) or not raw.startswith("/") or "\x00" in raw:
        raise ReleaseVerificationError("release directory must be an absolute path")
    components = raw.split("/")[1:]
    if not components or any(component in ("", ".", "..") for component in components):
        raise ReleaseVerificationError(
            "release directory path contains an unsafe component"
        )
    try:
        current_fd = os.open("/", DIRECTORY_FLAGS)
        stack.callback(os.close, current_fd)
        chain: list[tuple[int, str, int]] = []
        for component in components:
            next_fd = os.open(component, DIRECTORY_FLAGS, dir_fd=current_fd)
            stack.callback(os.close, next_fd)
            chain.append((current_fd, component, next_fd))
            current_fd = next_fd
        parent_fd, name, release_fd = chain[-1]
        parent = os.fstat(parent_fd)
        released = os.fstat(release_fd)
        if parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
            raise ReleaseVerificationError(
                "release parent must be owned by current UID and not group/other writable"
            )
        if released.st_uid != os.geteuid() or stat.S_IMODE(released.st_mode) != 0o700:
            raise ReleaseVerificationError(
                "release directory must be owned by current UID with mode 0700"
            )
        return release_fd, parent_fd, name, chain, released
    except OSError as exc:
        raise ReleaseVerificationError(
            "release directory cannot be opened securely"
        ) from exc


def _check_directory_chain(
    chain: list[tuple[int, str, int]], original: os.stat_result
) -> None:
    try:
        for parent_fd, name, fd in chain:
            opened = os.fstat(fd)
            named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or not stat.S_ISDIR(named.st_mode)
                or not _same_identity(opened, named)
            ):
                raise ReleaseVerificationError(
                    "release directory path identity changed"
                )
        parent = os.fstat(chain[-1][0])
        released = os.fstat(chain[-1][2])
        if parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
            raise ReleaseVerificationError("release parent permissions changed")
        if not _same_file_state(original, released):
            raise ReleaseVerificationError(
                "release directory metadata changed during verification"
            )
    except OSError as exc:
        raise ReleaseVerificationError(
            "release directory path cannot be rechecked"
        ) from exc


def _open_release_file(
    directory_fd: int, name: str, stack: ExitStack
) -> tuple[int, os.stat_result]:
    try:
        fd = os.open(name, FILE_FLAGS, dir_fd=directory_fd)
        stack.callback(os.close, fd)
        info = os.fstat(fd)
    except OSError as exc:
        raise ReleaseVerificationError(f"{name} cannot be opened securely") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
    ):
        raise ReleaseVerificationError(f"{name} is not a private, regular release file")
    return fd, info


def _check_release_file(
    directory_fd: int, name: str, fd: int, original: os.stat_result
) -> None:
    try:
        opened = os.fstat(fd)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as exc:
        raise ReleaseVerificationError(f"{name} cannot be rechecked") from exc
    if not _same_file_state(original, opened) or not _same_file_state(original, named):
        raise ReleaseVerificationError(
            f"{name} identity or metadata changed during verification"
        )


def _read_manifest(fd: int, size: int) -> bytes:
    if size > MAX_MANIFEST_BYTES:
        raise ReleaseVerificationError("manifest.json is too large")
    chunks: list[bytes] = []
    total = 0
    while chunk := os.read(fd, CHUNK_SIZE):
        total += len(chunk)
        if total > MAX_MANIFEST_BYTES:
            raise ReleaseVerificationError("manifest.json is too large")
        chunks.append(chunk)
    if total != size:
        raise ReleaseVerificationError("manifest.json size changed during verification")
    return b"".join(chunks)


def _hash_fd(fd: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    while chunk := os.read(fd, CHUNK_SIZE):
        digest.update(chunk)
        total += len(chunk)
    return digest.hexdigest(), total


def _expected_digest(
    schedule: dict[str, Any], run: dict[str, Any], source_label: str
) -> str:
    if source_label.startswith("case:"):
        return run["case_package_sha256"]
    if source_label.startswith("prompt:"):
        return schedule["inputs"]["arm_prompts"][run["arm"]]["sha256"]
    return schedule["inputs"][source_label.removeprefix("input:")]["sha256"]


def _validate_manifest(
    raw: Any, schedule: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    manifest = _object(raw, "release manifest", MANIFEST_FIELDS)
    if type(manifest["schema"]) is not int or manifest["schema"] != 1:
        raise ReleaseVerificationError("release manifest schema must be integer 1")
    if (
        manifest["classification"] != "development_release_unsealed"
        or type(manifest["classification"]) is not str
    ):
        raise ReleaseVerificationError("release manifest classification is invalid")
    if manifest["notice"] != RELEASE_NOTICE or type(manifest["notice"]) is not str:
        raise ReleaseVerificationError("release manifest notice is invalid")
    run_id = manifest["run_id"]
    if type(run_id) is not str:
        raise ReleaseVerificationError("release manifest run_id must be a string")
    run = next((item for item in schedule["runs"] if item["run_id"] == run_id), None)
    if run is None:
        raise ReleaseVerificationError(
            "release manifest run_id is absent from schedule"
        )
    if (
        manifest["run_sha256"] != run["run_sha256"]
        or type(manifest["run_sha256"]) is not str
    ):
        raise ReleaseVerificationError(
            "release manifest run_sha256 differs from schedule"
        )
    if (
        manifest["schedule_sha256"] != schedule["schedule_sha256"]
        or type(manifest["schedule_sha256"]) is not str
    ):
        raise ReleaseVerificationError(
            "release manifest schedule_sha256 differs from schedule"
        )
    expected_coordinates = {field: run[field] for field in COORDINATE_FIELDS}
    _object(manifest["coordinates"], "release coordinates", set(COORDINATE_FIELDS))
    if _canonical(manifest["coordinates"]) != _canonical(expected_coordinates):
        raise ReleaseVerificationError("release coordinates differ from scheduled run")
    _object(manifest["limits"], "release limits", set(schedule["per_run_limits"]))
    if _canonical(manifest["limits"]) != _canonical(schedule["per_run_limits"]):
        raise ReleaseVerificationError("release limits differ from schedule")
    selected = _selected_assets(run)
    files = _object(manifest["files"], "release files", set(selected))
    expected_digests = {
        role: _expected_digest(schedule, run, source_label)
        for role, source_label in selected.items()
    }
    for role, digest in expected_digests.items():
        entry = _object(
            files[role], f"release file entry {role}", {"file", "sha256", "bytes"}
        )
        if type(entry["file"]) is not str or entry["file"] != role:
            raise ReleaseVerificationError(
                f"release file entry {role} has a wrong file name"
            )
        if type(entry["sha256"]) is not str or entry["sha256"] != digest:
            raise ReleaseVerificationError(
                f"release file entry {role} digest differs from schedule"
            )
        if type(entry["bytes"]) is not int or entry["bytes"] < 0:
            raise ReleaseVerificationError(
                f"release file entry {role} has invalid byte count"
            )
    return manifest, expected_digests


def verify_release(schedule_raw: Any, release_dir: Path | str) -> dict[str, Any]:
    """Check one release at a point in time without writing or executing it."""
    try:
        schedule = _candidate_schedule(schedule_raw)
    except PreflightError as exc:
        raise ReleaseVerificationError("invalid candidate schedule") from exc

    try:
        with ExitStack() as stack:
            release_fd, _parent_fd, _name, chain, directory_info = (
                _open_directory_chain(release_dir, stack)
            )
            _check_directory_chain(chain, directory_info)
            manifest_fd, manifest_info = _open_release_file(
                release_fd, "manifest.json", stack
            )
            manifest = _parse_json(
                _read_manifest(manifest_fd, manifest_info.st_size), "manifest.json"
            )
            _check_release_file(release_fd, "manifest.json", manifest_fd, manifest_info)
            manifest, digests = _validate_manifest(manifest, schedule)
            expected_names = set(digests) | {"manifest.json"}
            if set(os.listdir(release_fd)) != expected_names:
                raise ReleaseVerificationError(
                    "release directory has missing or extra entries"
                )

            opened: dict[str, tuple[int, os.stat_result]] = {
                "manifest.json": (manifest_fd, manifest_info)
            }
            verified_bytes = 0
            for role, expected_digest in digests.items():
                fd, info = _open_release_file(release_fd, role, stack)
                opened[role] = (fd, info)
                actual_digest, actual_bytes = _hash_fd(fd)
                if actual_digest != expected_digest:
                    raise ReleaseVerificationError(f"{role} bytes differ from schedule")
                if actual_bytes != manifest["files"][role]["bytes"]:
                    raise ReleaseVerificationError(
                        f"{role} byte count differs from manifest"
                    )
                _check_release_file(release_fd, role, fd, info)
                verified_bytes += actual_bytes

            for name, (fd, info) in opened.items():
                _check_release_file(release_fd, name, fd, info)
            if set(os.listdir(release_fd)) != expected_names:
                raise ReleaseVerificationError(
                    "release directory entries changed during verification"
                )
            _check_directory_chain(chain, directory_info)
    except OSError as exc:
        raise ReleaseVerificationError("release could not be read securely") from exc

    return {
        "schema": 1,
        "classification": "development_release_verification_unsealed",
        "notice": VERIFICATION_NOTICE,
        "run_id": manifest["run_id"],
        "run_sha256": manifest["run_sha256"],
        "schedule_sha256": schedule["schedule_sha256"],
        "verified_files": len(digests),
        "verified_bytes": verified_bytes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "schedule", help="independently supplied candidate schedule JSON"
    )
    parser.add_argument(
        "release_dir", help="absolute path to one existing development release"
    )
    args = parser.parse_args(argv)
    try:
        result = verify_release(_read_schedule(args.schedule), args.release_dir)
    except ReleaseVerificationError as exc:
        print(f"Release verification failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
