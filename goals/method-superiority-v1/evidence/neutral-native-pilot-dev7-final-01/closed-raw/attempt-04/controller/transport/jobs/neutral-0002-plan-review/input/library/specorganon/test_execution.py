"""Offline signatures over externally produced test execution reports.

The signature authenticates a registered executor's statement. This module
does not execute commands or establish that the executor reported honestly.
"""

from __future__ import annotations

import base64
import hashlib
import re
import shlex
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import approval


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REPORT_FIELDS = {
    "schema", "argv", "exit_code", "timed_out", "stdout_sha256",
    "stderr_sha256", "artifacts",
}


def item_issues(item: dict[str, Any], *, observed: bool = False) -> list[str]:
    """Structural checks for a signed test declaration, independent of receipts."""
    data = item["data"]
    command, argv = data.get("command"), data.get("argv")
    if not isinstance(command, str) or not command.strip() or len(command) > 32768:
        return ["signed test needs a nonempty command"]
    if (not isinstance(argv, list) or not 0 < len(argv) <= 128
            or any(type(arg) is not str or len(arg) > 4096 for arg in argv)
            or not argv[0] or sum(len(arg) for arg in argv) > 16384):
        return ["signed test needs a nonempty argv list of strings"]
    if command != shlex.join(argv):
        return ["signed test command must equal shlex.join(argv)"]
    if observed:
        if not Path(argv[0]).is_absolute() or any(part in {".", ".."} for part in Path(argv[0]).parts):
            return ["observed test argv[0] must be an absolute canonical executable path"]
        for field in ("executable_sha256", "input_tree_sha256"):
            value = data.get(field)
            if type(value) is not str or not _SHA256.fullmatch(value):
                return [f"observed test needs a lowercase {field} pin"]
    return []


def validate_report(report: Any) -> dict[str, Any]:
    """Require the exact schema 1 report shape and canonical artifact locators."""
    if type(report) is not dict or set(report) != _REPORT_FIELDS or report["schema"] != 1 or type(report["schema"]) is not int:
        raise ValueError("test execution report must have the exact schema 1 fields")
    argv = report["argv"]
    if (type(argv) is not list or not 0 < len(argv) <= 128
            or any(type(arg) is not str or len(arg) > 4096 for arg in argv)
            or not argv[0] or sum(len(arg) for arg in argv) > 16384):
        raise ValueError("test execution report argv must be a nonempty list of strings")
    if type(report["exit_code"]) is not int:
        raise ValueError("test execution report exit_code must be an integer")
    if type(report["timed_out"]) is not bool:
        raise ValueError("test execution report timed_out must be a boolean")
    for field in ("stdout_sha256", "stderr_sha256"):
        if (type(report[field]) is not str or len(report[field]) != 64
                or not _SHA256.fullmatch(report[field])):
            raise ValueError(f"test execution report {field} must be a lowercase SHA-256 digest")
    artifacts = report["artifacts"]
    if type(artifacts) is not list or len(artifacts) > 128:
        raise ValueError("test execution report artifacts must be a list of at most 128 entries")
    seen: set[str] = set()
    path_bytes = 0
    for artifact in artifacts:
        if type(artifact) is not dict or set(artifact) != {"path", "sha256"}:
            raise ValueError("test execution artifact must have exactly path and sha256")
        path, digest = artifact["path"], artifact["sha256"]
        if (type(path) is not str or not path or len(path) > 1024
                or any(ord(char) < 32 for char in path)
                or "\\" in path or path.startswith("/")
                or re.match(r"^[A-Za-z]:", path)
                or any(part in {"", ".", ".."} for part in path.split("/"))):
            raise ValueError("test execution artifact path must be canonical and relative")
        path_bytes += len(path.encode("utf-8"))
        if path_bytes > 16384:
            raise ValueError("test execution artifact paths exceed the size limit")
        if path in seen:
            raise ValueError("test execution artifact paths must be distinct")
        seen.add(path)
        if type(digest) is not str or len(digest) != 64 or not _SHA256.fullmatch(digest):
            raise ValueError("test execution artifact sha256 must be a lowercase SHA-256 digest")
    return report


def message(
    project: dict[str, Any], item: dict[str, Any], report: dict[str, Any],
    actor: str, path: str | Path, ledger_head_sha256: str,
) -> bytes:
    validate_report(report)
    return approval._canonical({
        "schema": 1,
        "purpose": "specorganon.test_execution",
        "case_id": project["case_id"],
        "case_path": approval.case_path(path),
        "project_sha256": approval.project_fingerprint(project),
        "ledger_head_sha256": ledger_head_sha256,
        "item_id": item["id"],
        "item_version": item["version"],
        "item_sha256": hashlib.sha256(approval._canonical(item)).hexdigest(),
        "item_deps": item["deps"],
        "actor": actor,
        "report": report,
    })


def challenge(
    project: dict[str, Any], item: dict[str, Any], report: dict[str, Any],
    actor: str, path: str | Path, ledger_head_sha256: str,
) -> dict[str, Any]:
    payload = message(project, item, report, actor, path, ledger_head_sha256)
    return {
        "algorithm": "Ed25519",
        "encoding": "base64",
        "message_base64": base64.b64encode(payload).decode("ascii"),
        "message_sha256": hashlib.sha256(payload).hexdigest(),
        "purpose": "specorganon.test_execution",
        "case_id": project["case_id"],
        "actor": actor,
        "report": report,
        "item_id": item["id"],
        "item_version": item["version"],
        "item_sha256": hashlib.sha256(approval._canonical(item)).hexdigest(),
        "item_deps": item["deps"],
        "case_path": approval.case_path(path),
        "project_sha256": approval.project_fingerprint(project),
        "ledger_head_sha256": ledger_head_sha256,
    }


def verify(
    project: dict[str, Any], item: dict[str, Any], report: dict[str, Any],
    actor: str, signature: str, key_sha256: str, executors: dict[str, bytes],
    path: str | Path, ledger_head_sha256: str,
) -> bool:
    key = executors.get(actor)
    raw_signature = approval._decode(signature, 64)
    if (key is None or raw_signature is None or type(key_sha256) is not str
            or hashlib.sha256(key).hexdigest() != key_sha256):
        return False
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(
            raw_signature, message(project, item, report, actor, path, ledger_head_sha256)
        )
    except (InvalidSignature, ValueError, KeyError, TypeError):
        return False
    return True
