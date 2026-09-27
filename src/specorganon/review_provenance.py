"""Revocable Ed25519 proof for one phase review of an exact ledger snapshot.

The external public-key registry authenticates the configured actor. It does
not establish reviewer competence or the truth of the case's source material.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import approval


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def message(
    project: dict[str, Any], path: str | Path, ledger_head_sha256: str,
    phase: str, snapshot: str, verdict: str, reason: str, actor: str,
) -> bytes:
    case_id = project.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("case lacks case_id for a signed phase review")
    return _canonical({
        "schema": 1,
        "purpose": "specorganon.phase_review",
        "case_id": case_id,
        "case_path": approval.case_path(path),
        "project_sha256": approval.project_fingerprint(project),
        "ledger_head_sha256": ledger_head_sha256,
        "phase": phase,
        "snapshot": snapshot,
        "verdict": verdict,
        "reason": reason,
        "actor": actor,
    })


def challenge(
    project: dict[str, Any], path: str | Path, ledger_head_sha256: str,
    phase: str, snapshot: str, verdict: str, reason: str, actor: str,
) -> dict[str, Any]:
    raw = message(project, path, ledger_head_sha256, phase, snapshot,
                  verdict, reason, actor)
    return {
        "algorithm": "Ed25519",
        "encoding": "base64",
        "message_base64": base64.b64encode(raw).decode("ascii"),
        "message_sha256": hashlib.sha256(raw).hexdigest(),
        "actor": actor,
        "phase": phase,
        "snapshot": snapshot,
        "case_path": approval.case_path(path),
        "project_sha256": approval.project_fingerprint(project),
        "ledger_head_sha256": ledger_head_sha256,
    }


def verify(
    project: dict[str, Any], path: str | Path, ledger_head_sha256: str,
    phase: str, snapshot: str, verdict: str, reason: str, actor: str,
    signature: str, key_sha256: str, reviewers: dict[str, bytes],
) -> bool:
    key = reviewers.get(actor)
    if key is None or not isinstance(key_sha256, str):
        return False
    if approval.key_fingerprint(key) != key_sha256:
        return False
    try:
        raw_signature = base64.b64decode(signature, validate=True)
        if len(raw_signature) != 64:
            return False
        Ed25519PublicKey.from_public_bytes(key).verify(
            raw_signature,
            message(project, path, ledger_head_sha256, phase, snapshot,
                    verdict, reason, actor),
        )
    except (binascii.Error, InvalidSignature, TypeError, ValueError):
        return False
    return True
