"""Offline Ed25519 approvals bound to a case and an exact item revision.

The configured public-key file is a deployment trust anchor, not part of the
case ledger. Its custody and the signer's identity must be checked externally.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode(raw: str, length: int) -> bytes | None:
    try:
        value = base64.b64decode(raw, validate=True)
    except (binascii.Error, TypeError, ValueError):
        return None
    return value if len(value) == length else None


def project_fingerprint(project: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(project)).hexdigest()


def case_path(path: str | Path) -> str:
    return str(Path(path).resolve(strict=True))


def _unique_registry_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key in trusted case registry")
        result[key] = value
    return result


def _registry() -> dict[str, Any] | None:
    """Read the operator-controlled case registry outside the ledger."""
    configured = os.environ.get("ORGANON_APPROVERS_FILE")
    if configured is None:
        return None
    if not configured or not Path(configured).is_absolute():
        raise ValueError("ORGANON_APPROVERS_FILE must be an absolute path to a trusted case registry")
    try:
        data = json.loads(Path(configured).read_text(encoding="utf-8"),
                          object_pairs_hook=_unique_registry_keys)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read trusted case registry") from exc
    if not isinstance(data, dict) or data.get("schema") != 2 or not isinstance(data.get("cases"), dict):
        raise ValueError("malformed trusted case registry")
    return data["cases"]


def trust_contexts(
    project: dict[str, Any], path: str | Path,
) -> tuple[dict[str, bytes], dict[str, bytes], str]:
    approvers, reviewers, _, status = trust_contexts_with_executors(project, path)
    return approvers, reviewers, status


def trust_contexts_with_executors(
    project: dict[str, Any], path: str | Path,
) -> tuple[dict[str, bytes], dict[str, bytes], dict[str, bytes], str]:
    approvers, reviewers, executors, _, status = trust_contexts_with_observers(project, path)
    return approvers, reviewers, executors, status


def trust_contexts_with_observers(
    project: dict[str, Any], path: str | Path,
) -> tuple[dict[str, bytes], dict[str, bytes], dict[str, bytes], dict[str, bytes], str]:
    """Resolve effective approval mode from external registration and fixture flag.

    A registered path can never be downgraded to an unsigned fixture by editing
    project metadata. Without a valid registration, signed approvals fail closed.
    """
    actual_path = case_path(path)
    cases = _registry()
    path_registration: str | None = None
    if cases is not None:
        for registered_id, entry in cases.items():
            if not isinstance(registered_id, str) or not isinstance(entry, dict):
                raise ValueError("malformed trusted case registry entry")
            registered_path = entry.get("path")
            if not isinstance(registered_path, str) or not Path(registered_path).is_absolute():
                raise ValueError("malformed trusted case path")
            if str(Path(registered_path).resolve()) == actual_path:
                if path_registration is not None:
                    raise ValueError("duplicate trusted case path")
                path_registration = registered_id
    if project.get("approval_policy") == "local":
        if path_registration is not None or (cases is not None and project.get("case_id") in cases):
            raise ValueError("registered signed case cannot become a local case")
        # A configured registry is always a trust boundary. An unrelated valid
        # signed case may coexist with local development; malformed entries
        # must never silently disable the operator's registration controls.
        for entry in (cases or {}).values():
            fingerprint = entry.get("project_sha256")
            if (type(fingerprint) is not str or re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None
                    or type(entry.get("approvers")) is not dict):
                raise ValueError("malformed trusted case registry entry")
            key_owners: dict[bytes, str] = {}
            for role, prefix in (("approvers", "human:"), ("phase_reviewers", ""),
                                 ("test_executors", "executor:"), ("test_observers", "observer:")):
                actors = entry.get(role, {})
                if type(actors) is not dict:
                    raise ValueError(f"malformed trusted {role}")
                for actor, encoded in actors.items():
                    key = _decode(encoded, 32)
                    if (type(actor) is not str or not actor.strip() or actor != actor.strip()
                            or not actor.startswith(prefix) or not actor.removeprefix(prefix).strip()
                            or key is None):
                        raise ValueError(f"malformed trusted {role} entry")
                    if key in key_owners and (key_owners[key] != actor or prefix in {"executor:", "observer:"}):
                        raise ValueError("trusted public key is registered under multiple actors or roles")
                    key_owners[key] = actor
        owner = project.get("created_by")
        if (not isinstance(owner, str) or not owner.startswith("human:")
                or not owner.removeprefix("human:").strip()
                or owner != "human:" + owner.removeprefix("human:").strip()
                or owner == "human:fixture"):
            raise ValueError("local case requires a declared human:<owner>")
        if project.get("test_gate_policy") != "local_report":
            raise ValueError("local case requires local_report test gate policy")
        return {}, {}, {}, {}, "local_declared"
    if project.get("approval_policy") == "fixture":
        if path_registration is not None:
            raise ValueError("registered signed case cannot become a fixture")
        if os.environ.get("ORGANON_ALLOW_FIXTURES") != "1":
            raise ValueError("fixture approvals disabled; set ORGANON_ALLOW_FIXTURES=1 only in synthetic runs")
        return {}, {}, {}, {}, "fixture"
    if project.get("approval_policy") != "signed" or cases is None:
        raise ValueError("signed case requires a trusted case registry")
    case_id = project.get("case_id")
    entry = cases.get(case_id)
    if not isinstance(entry, dict) or path_registration != case_id:
        raise ValueError("case is not registered at this canonical path")
    if entry.get("project_sha256") != project_fingerprint(project):
        raise ValueError("case metadata differs from trusted registration")
    raw_approvers = entry.get("approvers")
    if not isinstance(raw_approvers, dict):
        raise ValueError("malformed trusted approvers")
    result: dict[str, bytes] = {}
    for actor, encoded in raw_approvers.items():
        key = _decode(encoded, 32)
        if not isinstance(actor, str) or not actor.startswith("human:") or key is None:
            raise ValueError("malformed trusted approver entry")
        result[actor] = key
    raw_reviewers = entry.get("phase_reviewers", {})
    if not isinstance(raw_reviewers, dict):
        raise ValueError("malformed trusted phase reviewers")
    raw_executors = entry.get("test_executors", {})
    if not isinstance(raw_executors, dict):
        raise ValueError("malformed trusted test executors")
    raw_observers = entry.get("test_observers", {})
    if not isinstance(raw_observers, dict):
        raise ValueError("malformed trusted test observers")
    reviewers: dict[str, bytes] = {}
    executors: dict[str, bytes] = {}
    observers: dict[str, bytes] = {}
    key_owners: dict[bytes, str] = {}
    for actor, key in result.items():
        owner = key_owners.get(key)
        if owner is not None and owner != actor:
            raise ValueError("trusted public key is registered under multiple actors")
        key_owners[key] = actor
    for actor, encoded in raw_reviewers.items():
        key = _decode(encoded, 32)
        if (not isinstance(actor, str) or not actor or actor != actor.strip()
                or key is None):
            raise ValueError("malformed trusted phase reviewer entry")
        owner = key_owners.get(key)
        if owner is not None and owner != actor:
            raise ValueError("trusted public key is registered under multiple actors")
        key_owners[key] = actor
        reviewers[actor] = key
    for actor, encoded in raw_executors.items():
        key = _decode(encoded, 32)
        if (not isinstance(actor, str) or not actor.startswith("executor:")
                or not actor.removeprefix("executor:").strip() or actor != actor.strip()
                or key is None):
            raise ValueError("malformed trusted test executor entry")
        if actor in result or actor in reviewers or key in key_owners:
            raise ValueError("trusted test executor overlaps another actor or public key")
        key_owners[key] = actor
        executors[actor] = key
    for actor, encoded in raw_observers.items():
        key = _decode(encoded, 32)
        if (not isinstance(actor, str) or not actor.startswith("observer:")
                or not actor.removeprefix("observer:").strip() or actor != actor.strip()
                or key is None):
            raise ValueError("malformed trusted test observer entry")
        if actor in result or actor in reviewers or actor in executors or key in key_owners:
            raise ValueError("trusted test observer overlaps another actor or public key")
        key_owners[key] = actor
        observers[actor] = key
    return result, reviewers, executors, observers, "configured"


def trust_context(project: dict[str, Any], path: str | Path) -> tuple[dict[str, bytes], str]:
    approvers, _, status = trust_contexts(project, path)
    return approvers, status


def message(
    project: dict[str, Any], item: dict[str, Any], actor: str, reason: str,
    path: str | Path, ledger_head_sha256: str,
) -> bytes:
    case_id = project.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("case lacks case_id; migrate its project metadata before signed approval")
    return _canonical({
        "schema": 1,
        "purpose": "specorganon.normative_approval",
        "decision": "approve",
        "case_id": case_id,
        "case_path": case_path(path),
        "project_sha256": project_fingerprint(project),
        "ledger_head_sha256": ledger_head_sha256,
        "item_id": item["id"],
        "item_version": item["version"],
        "item_sha256": hashlib.sha256(_canonical(item)).hexdigest(),
        "actor": actor,
        "reason": reason,
    })


def challenge(
    project: dict[str, Any], item: dict[str, Any], actor: str, reason: str,
    path: str | Path, ledger_head_sha256: str,
) -> dict[str, Any]:
    payload = message(project, item, actor, reason, path, ledger_head_sha256)
    return {
        "algorithm": "Ed25519",
        "encoding": "base64",
        "message_base64": base64.b64encode(payload).decode("ascii"),
        "message_sha256": hashlib.sha256(payload).hexdigest(),
        "actor": actor,
        "item_id": item["id"],
        "item_version": item["version"],
        "case_path": case_path(path),
        "project_sha256": project_fingerprint(project),
        "ledger_head_sha256": ledger_head_sha256,
    }


def verify(
    project: dict[str, Any], item: dict[str, Any], actor: str, reason: str,
    signature: str, key_sha256: str, approvers: dict[str, bytes],
    path: str | Path, ledger_head_sha256: str,
) -> bool:
    key = approvers.get(actor)
    raw_signature = _decode(signature, 64)
    if key is None or raw_signature is None or hashlib.sha256(key).hexdigest() != key_sha256:
        return False
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(
            raw_signature, message(project, item, actor, reason, path, ledger_head_sha256)
        )
    except (InvalidSignature, ValueError, KeyError, TypeError):
        return False
    return True


def key_fingerprint(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()
