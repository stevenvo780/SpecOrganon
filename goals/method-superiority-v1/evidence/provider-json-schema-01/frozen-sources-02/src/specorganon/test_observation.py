"""Bounded byte inspection and revocable signatures for local test observations.

An observer signature authenticates a statement about one repeat run. It does
not prove who controlled the machine, that the child really ran, or physical
independence from the executor. Replay verifies the signature without opening
the bundle; callers then validate current bundle bytes separately.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import stat
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import approval, test_execution


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_EXECUTABLE_BYTES = 16 * 1024 * 1024
_MAX_TREE_BYTES = 64 * 1024 * 1024
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
_MAX_TREE_ENTRIES = 1024
_MAX_DEPTH = 16
_RECEIPT_FIELDS = {
    "schema", "case_id", "item_id", "item_version", "report_provenance",
    "bundle_path", "executable_sha256", "input_tree_sha256", "sandbox", "observed",
}
_SANDBOX_FIELDS = {"policy", "landlock_abi", "exit_code", "timed_out", "launch_error"}
_OBSERVED_FIELDS = {"stdout_sha256", "stderr_sha256", "artifacts"}


class ObservationError(ValueError):
    """The receipt, current executable, or inspection bundle is invalid."""


def _digest(value: Any) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _state(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _absolute_path(value: str | Path, label: str) -> Path:
    raw = str(value)
    if (not raw or len(raw.encode("utf-8")) > 4096 or not os.path.isabs(raw)
            or os.path.normpath(raw) != raw or str(Path(raw)) != raw):
        raise ObservationError(f"{label} must be an absolute canonical path")
    return Path(raw)


def _open_absolute_directory(path: Path) -> int:
    """Open every component without following a symlink, including parents."""
    fd = os.open("/", _DIR_FLAGS)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, _DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        if _state(os.fstat(fd)) != _state(os.stat(path, follow_symlinks=False)):
            raise ObservationError("directory changed while being opened")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _open_child_directory(parent_fd: int, name: str) -> int:
    fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
    try:
        if _state(os.fstat(fd)) != _state(os.stat(name, dir_fd=parent_fd, follow_symlinks=False)):
            raise ObservationError("directory changed while being opened")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _file_hash(parent_fd: int, name: str, maximum: int, *, executable: bool = False) -> tuple[str, int]:
    fd = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or (not executable and before.st_nlink != 1):
            raise ObservationError("bundle entry is not a singly linked regular file")
        if executable and not before.st_mode & 0o111:
            raise ObservationError("pinned executable is not executable")
        if before.st_size < 0 or before.st_size > maximum or (executable and before.st_size == 0):
            raise ObservationError("file exceeds the byte limit")
        digest = hashlib.sha256()
        total = 0
        while chunk := os.read(fd, min(1024 * 1024, maximum - total + 1)):
            total += len(chunk)
            if total > maximum:
                raise ObservationError("file exceeds the byte limit")
            digest.update(chunk)
        after = os.fstat(fd)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if total != before.st_size or _state(before) != _state(after) or _state(before) != _state(named):
            raise ObservationError("file changed while being read")
        return digest.hexdigest(), total
    finally:
        os.close(fd)


def _relative_name(path: str) -> None:
    if (not path or len(path.encode("utf-8")) > 4096
            or any(ord(char) < 32 for char in path) or "\\" in path
            or path.startswith("/") or re.match(r"^[A-Za-z]:", path)
            or any(part in {"", ".", ".."} for part in path.split("/"))):
        raise ObservationError("bundle entry has a noncanonical relative path")


def _hash_tree_fd(root_fd: int) -> str:
    records: list[dict[str, Any]] = []
    remaining = _MAX_TREE_BYTES
    entries = 0

    def visit(directory_fd: int, prefix: str, depth: int) -> None:
        nonlocal remaining, entries
        if depth > _MAX_DEPTH:
            raise ObservationError("input tree exceeds the depth limit")
        before = os.fstat(directory_fd)
        for name in sorted(os.listdir(directory_fd)):
            relative = f"{prefix}/{name}" if prefix else name
            _relative_name(relative)
            entries += 1
            if entries > _MAX_TREE_ENTRIES:
                raise ObservationError("input tree exceeds the entry limit")
            initial = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISDIR(initial.st_mode):
                records.append({"path": relative, "type": "directory"})
                child_fd = _open_child_directory(directory_fd, name)
                try:
                    if _state(initial) != _state(os.fstat(child_fd)):
                        raise ObservationError("input directory changed while being opened")
                    visit(child_fd, relative, depth + 1)
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(initial.st_mode):
                digest, size = _file_hash(directory_fd, name, min(_MAX_FILE_BYTES, remaining))
                if _state(initial) != _state(os.stat(name, dir_fd=directory_fd, follow_symlinks=False)):
                    raise ObservationError("input file changed while being read")
                remaining -= size
                records.append({"path": relative, "type": "file",
                                "sha256": digest, "size": size})
            else:
                raise ObservationError("input tree contains a symlink or special file")
        if _state(before) != _state(os.fstat(directory_fd)):
            raise ObservationError("input directory changed while being scanned")

    visit(root_fd, "", 0)
    records.sort(key=lambda record: record["path"])
    return hashlib.sha256(approval._canonical(records)).hexdigest()


def hash_input_tree(input_dir: str | Path) -> str:
    """Hash canonical sorted directory and file records for a bounded tree."""
    path = _absolute_path(input_dir, "input directory")
    try:
        fd = _open_absolute_directory(path)
        try:
            before = os.fstat(fd)
            digest = _hash_tree_fd(fd)
            if (_state(before) != _state(os.fstat(fd))
                    or _state(before) != _state(os.stat(path, follow_symlinks=False))):
                raise ObservationError("input directory changed while being inspected")
            return digest
        finally:
            os.close(fd)
    except OSError as exc:
        raise ObservationError("input tree cannot be inspected safely") from exc


def _declared_artifact_hash(root_fd: int, relative: str, maximum: int) -> tuple[str, int] | None:
    parts = relative.split("/")
    opened: list[tuple[int, os.stat_result]] = [(root_fd, os.fstat(root_fd))]
    try:
        for part in parts[:-1]:
            try:
                child_fd = _open_child_directory(opened[-1][0], part)
            except FileNotFoundError:
                if any(_state(before) != _state(os.fstat(fd)) for fd, before in opened):
                    raise ObservationError("artifact directory changed while being inspected") from None
                return None
            opened.append((child_fd, os.fstat(child_fd)))
        try:
            result = _file_hash(opened[-1][0], parts[-1], maximum)
        except FileNotFoundError:
            if any(_state(before) != _state(os.fstat(fd)) for fd, before in opened):
                raise ObservationError("artifact directory changed while being inspected") from None
            return None
        if any(_state(before) != _state(os.fstat(fd)) for fd, before in opened):
            raise ObservationError("artifact directory changed while being inspected")
        return result
    finally:
        for fd, _ in reversed(opened[1:]):
            os.close(fd)


def inspect_bundle(bundle_path: str | Path, report: dict[str, Any]) -> dict[str, Any]:
    """Rehash a complete private bundle without reading undeclared artifacts.

    Missing declared artifacts are omitted from the observed list, representing
    a valid negative observation. All other missing required entries, links,
    special files, unstable reads, and exceeded limits raise ObservationError.
    """
    test_execution.validate_report(report)
    path = _absolute_path(bundle_path, "bundle path")
    try:
        root_fd = _open_absolute_directory(path)
        try:
            before = os.fstat(root_fd)
            if before.st_uid != os.geteuid() or stat.S_IMODE(before.st_mode) != 0o700:
                raise ObservationError("bundle must be owned by the current UID with mode 0700")
            input_fd = _open_child_directory(root_fd, "input")
            try:
                input_tree_sha256 = _hash_tree_fd(input_fd)
            finally:
                os.close(input_fd)
            stdout_sha256, _ = _file_hash(root_fd, "stdout.bin", _MAX_FILE_BYTES)
            stderr_sha256, _ = _file_hash(root_fd, "stderr.bin", _MAX_FILE_BYTES)
            artifacts_fd = _open_child_directory(root_fd, "artifacts")
            try:
                observed: list[dict[str, str]] = []
                remaining = _MAX_ARTIFACT_BYTES
                for artifact in report["artifacts"]:
                    result = _declared_artifact_hash(artifacts_fd, artifact["path"],
                                                     min(_MAX_FILE_BYTES, remaining))
                    if result is not None:
                        digest, size = result
                        remaining -= size
                        observed.append({"path": artifact["path"], "sha256": digest})
            finally:
                os.close(artifacts_fd)
            if (_state(before) != _state(os.fstat(root_fd))
                    or _state(before) != _state(os.stat(path, follow_symlinks=False))):
                raise ObservationError("bundle changed while being inspected")
            return {"input_tree_sha256": input_tree_sha256,
                    "stdout_sha256": stdout_sha256, "stderr_sha256": stderr_sha256,
                    "artifacts": observed}
        finally:
            os.close(root_fd)
    except OSError as exc:
        raise ObservationError("bundle is incomplete or cannot be inspected safely") from exc


def _read_pinned_executable(path_value: str, expected_sha256: str) -> None:
    path = _absolute_path(path_value, "pinned executable")
    try:
        parent_fd = _open_absolute_directory(path.parent)
        try:
            actual, _ = _file_hash(parent_fd, path.name, _MAX_EXECUTABLE_BYTES, executable=True)
        finally:
            os.close(parent_fd)
    except OSError as exc:
        raise ObservationError("pinned executable cannot be read safely") from exc
    if actual != expected_sha256:
        raise ObservationError("current executable bytes differ from the item pin")


def _checked_receipt(
    receipt: Any, project: dict[str, Any], item: dict[str, Any],
    report: dict[str, Any], report_provenance: dict[str, Any],
) -> None:
    test_execution.validate_report(report)
    if (type(receipt) is not dict or set(receipt) != _RECEIPT_FIELDS
            or type(receipt["schema"]) is not int or receipt["schema"] != 1):
        raise ObservationError("observation receipt must have exact schema 1 fields")
    if (type(report_provenance) is not dict or set(report_provenance) != {"seq", "hash"}
            or type(report_provenance["seq"]) is not int or report_provenance["seq"] < 1
            or not _digest(report_provenance["hash"])):
        raise ObservationError("report provenance must contain a positive seq and lowercase hash")
    receipt_provenance = receipt["report_provenance"]
    if (type(receipt_provenance) is not dict or set(receipt_provenance) != {"seq", "hash"}
            or type(receipt_provenance["seq"]) is not int
            or not _digest(receipt_provenance["hash"])
            or receipt["report_provenance"] != report_provenance):
        raise ObservationError("observation receipt is bound to a different report event")
    if (project.get("test_gate_policy") != "signed_observed"
            or type(project.get("case_id")) is not str or not project["case_id"]
            or receipt["case_id"] != project["case_id"]
            or item.get("kind") != "test" or receipt["item_id"] != item.get("id")
            or type(item.get("version")) is not int or item["version"] < 1
            or type(receipt["item_version"]) is not int
            or receipt["item_version"] != item["version"]):
        raise ObservationError("observation receipt does not match the signed test item")
    data = item.get("data")
    if (type(data) is not dict or data.get("argv") != report["argv"]
            or not _digest(data.get("executable_sha256"))
            or not _digest(data.get("input_tree_sha256"))
            or receipt["executable_sha256"] != data["executable_sha256"]
            or receipt["input_tree_sha256"] != data["input_tree_sha256"]):
        raise ObservationError("observation receipt does not match item byte pins")
    if type(receipt["bundle_path"]) is not str:
        raise ObservationError("observation bundle path must be a string")
    _absolute_path(receipt["bundle_path"], "bundle path")
    sandbox = receipt["sandbox"]
    if (type(sandbox) is not dict or set(sandbox) != _SANDBOX_FIELDS
            or sandbox["policy"] != "landlock_seccomp_repeat_v1"
            or type(sandbox["landlock_abi"]) is not int or sandbox["landlock_abi"] < 5
            or (sandbox["exit_code"] is not None and type(sandbox["exit_code"]) is not int)
            or type(sandbox["timed_out"]) is not bool
            or (sandbox["launch_error"] is not None
                and (type(sandbox["launch_error"]) is not str
                     or not sandbox["launch_error"] or len(sandbox["launch_error"]) > 4096))):
        raise ObservationError("observation receipt has an invalid sandbox result")
    observed = receipt["observed"]
    if (type(observed) is not dict or set(observed) != _OBSERVED_FIELDS
            or not _digest(observed["stdout_sha256"])
            or not _digest(observed["stderr_sha256"])
            or type(observed["artifacts"]) is not list
            or len(observed["artifacts"]) > len(report["artifacts"])):
        raise ObservationError("observation receipt has invalid observed digests")
    declared = {artifact["path"] for artifact in report["artifacts"]}
    seen: set[str] = set()
    for artifact in observed["artifacts"]:
        if (type(artifact) is not dict or set(artifact) != {"path", "sha256"}
                or type(artifact["path"]) is not str
                or artifact["path"] not in declared or artifact["path"] in seen
                or not _digest(artifact["sha256"])):
            raise ObservationError("observation receipt has invalid artifact digests")
        seen.add(artifact["path"])


def validate_receipt(
    receipt: dict[str, Any], project: dict[str, Any], item: dict[str, Any],
    report: dict[str, Any], report_provenance: dict[str, Any],
) -> bool:
    """Raise on invalid receipt or changed bytes; return report match, including failures.

    False is a valid negative observation, not a malformed receipt. A matching
    failed report returns True; the caller separately requires exit code zero
    and no timeout when deciding whether the test passed.
    """
    _checked_receipt(receipt, project, item, report, report_provenance)
    _read_pinned_executable(report["argv"][0], receipt["executable_sha256"])
    inspected = inspect_bundle(receipt["bundle_path"], report)
    if inspected["input_tree_sha256"] != receipt["input_tree_sha256"]:
        raise ObservationError("input tree bytes differ from the item pin")
    if receipt["observed"] != {key: inspected[key] for key in _OBSERVED_FIELDS}:
        raise ObservationError("observed digests differ from current bundle bytes")
    sandbox = receipt["sandbox"]
    observed = receipt["observed"]
    return bool(
        sandbox["launch_error"] is None
        and sandbox["exit_code"] is not None
        and sandbox["exit_code"] == report["exit_code"]
        and sandbox["timed_out"] == report["timed_out"]
        and observed["stdout_sha256"] == report["stdout_sha256"]
        and observed["stderr_sha256"] == report["stderr_sha256"]
        and observed["artifacts"] == report["artifacts"]
    )


def message(
    project: dict[str, Any], item: dict[str, Any], report: dict[str, Any],
    report_provenance: dict[str, Any], receipt: dict[str, Any], actor: str,
    path: str | Path, ledger_head_sha256: str,
) -> bytes:
    """Canonical signed payload; intentionally performs no bundle I/O on replay."""
    _checked_receipt(receipt, project, item, report, report_provenance)
    if (type(actor) is not str or not actor.startswith("observer:")
            or not actor.removeprefix("observer:").strip() or actor != actor.strip()
            or not _digest(ledger_head_sha256)):
        raise ObservationError("invalid observation actor or ledger head")
    return approval._canonical({
        "schema": 1,
        "purpose": "specorganon.test_observation",
        "case_id": project["case_id"],
        "case_path": approval.case_path(path),
        "project_sha256": approval.project_fingerprint(project),
        "ledger_head_sha256": ledger_head_sha256,
        "item_id": item["id"],
        "item_version": item["version"],
        "item_sha256": hashlib.sha256(approval._canonical(item)).hexdigest(),
        "item_deps": item["deps"],
        "report_provenance": report_provenance,
        "report": report,
        "receipt": receipt,
        "actor": actor,
    })


def challenge(
    project: dict[str, Any], item: dict[str, Any], report: dict[str, Any],
    report_provenance: dict[str, Any], receipt: dict[str, Any], actor: str,
    path: str | Path, ledger_head_sha256: str,
) -> dict[str, Any]:
    validate_receipt(receipt, project, item, report, report_provenance)
    payload = message(project, item, report, report_provenance, receipt,
                      actor, path, ledger_head_sha256)
    return {
        "algorithm": "Ed25519",
        "encoding": "base64",
        "message_base64": base64.b64encode(payload).decode("ascii"),
        "message_sha256": hashlib.sha256(payload).hexdigest(),
        "purpose": "specorganon.test_observation",
        "case_id": project["case_id"],
        "actor": actor,
        "item_id": item["id"],
        "item_version": item["version"],
        "report_provenance": report_provenance,
        "case_path": approval.case_path(path),
        "project_sha256": approval.project_fingerprint(project),
        "ledger_head_sha256": ledger_head_sha256,
    }


def verify(
    project: dict[str, Any], item: dict[str, Any], report: dict[str, Any],
    report_provenance: dict[str, Any], receipt: dict[str, Any], actor: str,
    signature: str, key_sha256: str, observers: dict[str, bytes],
    path: str | Path, ledger_head_sha256: str,
) -> bool:
    """Authenticate a registered observer without touching mutable bundle bytes."""
    key = observers.get(actor)
    raw_signature = approval._decode(signature, 64)
    if (key is None or raw_signature is None or not _digest(key_sha256)
            or approval.key_fingerprint(key) != key_sha256):
        return False
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(
            raw_signature,
            message(project, item, report, report_provenance, receipt,
                    actor, path, ledger_head_sha256),
        )
    except (InvalidSignature, ValueError, KeyError, TypeError, OSError):
        return False
    return True
