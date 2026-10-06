"""Read-only verification against an externally held ledger head.

The anchor file is a deployment trust boundary. Its custody and freshness must
be protected outside the case directory and outside this module.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from . import approval


_ENV = "ORGANON_LEDGER_ANCHORS_FILE"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ZERO_HASH = "0" * 64
_ENTRY_KEYS = {"path", "project_sha256", "seq", "head_hash"}


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key in ledger anchor file")
        result[key] = value
    return result


def _canonical_registered_path(raw: Any) -> str:
    if not isinstance(raw, str) or not raw or not Path(raw).is_absolute():
        raise ValueError("malformed ledger anchor path")
    try:
        canonical = str(Path(raw).resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("malformed ledger anchor path") from exc
    if raw != canonical:
        raise ValueError("ledger anchor path is not canonical")
    return canonical


def _validated_cases(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict) or set(raw) != {"schema", "cases"}:
        raise ValueError("malformed ledger anchor file")
    if type(raw["schema"]) is not int or raw["schema"] != 1 or not isinstance(raw["cases"], dict):
        raise ValueError("malformed ledger anchor file")
    cases: dict[str, dict[str, Any]] = raw["cases"]
    seen_paths: set[str] = set()
    for case_id, entry in cases.items():
        try:
            canonical_id = str(uuid.UUID(case_id)) if isinstance(case_id, str) else None
        except (ValueError, AttributeError):
            canonical_id = None
        if canonical_id != case_id or not isinstance(entry, dict) or set(entry) != _ENTRY_KEYS:
            raise ValueError("malformed ledger anchor entry")
        path = _canonical_registered_path(entry["path"])
        if path in seen_paths:
            raise ValueError("duplicate canonical path in ledger anchor file")
        seen_paths.add(path)
        if (
            not isinstance(entry["project_sha256"], str)
            or _SHA256.fullmatch(entry["project_sha256"]) is None
            or type(entry["seq"]) is not int
            or entry["seq"] < 0
            or not isinstance(entry["head_hash"], str)
            or _SHA256.fullmatch(entry["head_hash"]) is None
            or (entry["seq"] == 0 and entry["head_hash"] != _ZERO_HASH)
        ):
            raise ValueError("malformed ledger anchor entry")
    return cases


def verify(data: dict[str, Any], directory: str | Path) -> None:
    """Require the locally validated ledger to equal its external anchor.

    An unregistered fixture may run only with the explicit fixture capability.
    The caller validates the local event chain before calling this function.
    """
    configured = os.environ.get(_ENV)
    if configured is None:
        return
    if not configured or not Path(configured).is_absolute():
        raise ValueError(f"{_ENV} must be an absolute path")
    try:
        actual_path = approval.case_path(directory)
        anchor_path = Path(configured).resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("cannot resolve case or ledger anchor path") from exc
    if Path(actual_path) in anchor_path.parents:
        raise ValueError("ledger anchor file must be outside the case directory")
    try:
        raw = json.loads(
            Path(configured).read_text(encoding="utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("cannot read ledger anchor file") from exc
    cases = _validated_cases(raw)
    registered = next(
        ((case_id, entry) for case_id, entry in cases.items() if entry["path"] == actual_path),
        None,
    )
    project = data.get("project") if isinstance(data, dict) else None
    if not isinstance(project, dict):
        raise ValueError("malformed project metadata for ledger anchor")
    if registered is None:
        policy = project.get("approval_policy", "signed")
        if policy == "fixture" and os.environ.get("ORGANON_ALLOW_FIXTURES") == "1":
            return
        raise ValueError("case is not registered in ledger anchor file")
    case_id, entry = registered
    if project.get("case_id") != case_id:
        raise ValueError("case identity differs from ledger anchor")
    if approval.project_fingerprint(project) != entry["project_sha256"]:
        raise ValueError("project metadata differs from ledger anchor")
    events = data.get("events")
    if not isinstance(events, list):
        raise ValueError("malformed events for ledger anchor")
    if len(events) != entry["seq"]:
        raise ValueError("ledger sequence differs from ledger anchor")
    if events and not isinstance(events[-1], dict):
        raise ValueError("malformed events for ledger anchor")
    head_hash = events[-1].get("hash") if events else _ZERO_HASH
    if head_hash != entry["head_hash"]:
        raise ValueError("ledger head differs from ledger anchor")
