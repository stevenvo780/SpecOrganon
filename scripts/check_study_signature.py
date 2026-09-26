"""Build or verify an offline, unsealed Ed25519 matrix-design challenge.

Usage::

    python scripts/check_study_signature.py challenge schedule.json assets.json \
        --goal GOAL.md --protocol docs/protocolo_experimental.md
    python scripts/check_study_signature.py verify schedule.json assets.json \
        --goal GOAL.md --protocol docs/protocolo_experimental.md \
        --attestation attestation.json --trust /absolute/trust.json

This tool never generates or reads a private key. A successful signature only
proves control of a key whose public half appears in the supplied trust file;
it does not establish the signer's identity or authority, prior timing,
independent custody, or authorization to spend or run the matrix.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from plan_confirmatory import canonical_bytes
from preflight_assets import PreflightError, _read_json, preflight


PURPOSE = "specorganon.matrix-design.v1"
EXPECTED_GOAL_SHA256 = "e8341bea380cc357ad9e02ec4689a4ed47fe198ba06e4c98639f29264c314c36"
KEY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
NOTICE = (
    "The signature proves only control of the key supplied in the trust file; "
    "it does not prove identity or authority, prior timing, independent custody, "
    "or budget authorization. Compare the GOAL digest with an independently held "
    "baseline and keep signed evidence in independent custody."
)


class SignatureCheckError(ValueError):
    """The candidate or signature evidence is invalid."""


def _json_file(path: str, label: str) -> Any:
    try:
        return _read_json(path)
    except PreflightError as exc:
        raise SignatureCheckError(f"{label} JSON is invalid") from exc


def _file_sha256(path: str, label: str) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError as exc:
        raise SignatureCheckError(f"{label} cannot be read") from exc


def _exact_object(raw: Any, label: str, keys: set[str]) -> dict[str, Any]:
    if type(raw) is not dict or set(raw) != keys:
        raise SignatureCheckError(f"{label} must have exactly {sorted(keys)}")
    return raw


def _sha256(raw: Any, label: str) -> str:
    if type(raw) is not str or SHA256.fullmatch(raw) is None:
        raise SignatureCheckError(f"{label} must be a lowercase SHA-256 digest")
    return raw


def _b64(raw: Any, label: str, length: int | None) -> bytes:
    if type(raw) is not str:
        raise SignatureCheckError(f"{label} must be canonical base64")
    try:
        decoded = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SignatureCheckError(f"{label} must be canonical base64") from exc
    if (length is not None and len(decoded) != length) or base64.b64encode(decoded).decode("ascii") != raw:
        raise SignatureCheckError(f"{label} has invalid length or noncanonical base64")
    return decoded


def _key_id(raw: Any) -> str:
    if type(raw) is not str or KEY_ID.fullmatch(raw) is None:
        raise SignatureCheckError("key_id must be a short path-free identifier")
    return raw


def build_challenge(
    schedule_raw: Any, assets_raw: Any, *, goal: str, protocol: str
) -> dict[str, Any]:
    """Bind current real bytes to the fully validated candidate schedule."""
    try:
        checked = preflight(schedule_raw, assets_raw)
    except PreflightError as exc:
        raise SignatureCheckError("schedule or asset preflight failed") from exc
    if checked["verified_assets"] != 15:
        raise SignatureCheckError("asset preflight did not verify all 15 files")
    protocol_sha256 = _file_sha256(protocol, "protocol")
    if protocol_sha256 != schedule_raw["protocol_sha256"]:
        raise SignatureCheckError("protocol bytes differ from candidate schedule")
    goal_sha256 = _file_sha256(goal, "GOAL")
    if goal_sha256 != EXPECTED_GOAL_SHA256:
        raise SignatureCheckError("GOAL bytes differ from the required study baseline")
    message = {
        "purpose": PURPOSE,
        "schema": 1,
        "goal_sha256": goal_sha256,
        "protocol_sha256": protocol_sha256,
        "schedule_sha256": checked["schedule_sha256"],
        "input_sha256": checked["input_sha256"],
        "asset_digest_binding_sha256": checked["asset_digest_binding_sha256"],
    }
    encoded = canonical_bytes(message)
    return {
        "schema": 1,
        "classification": "development_registry_challenge_unsealed",
        "message_base64": base64.b64encode(encoded).decode("ascii"),
        "message_sha256": hashlib.sha256(encoded).hexdigest(),
        "notice": NOTICE,
    }


def _challenge_bytes(challenge_raw: Any) -> tuple[dict[str, Any], bytes]:
    challenge = _exact_object(challenge_raw, "challenge", {
        "schema", "classification", "message_base64", "message_sha256", "notice"
    })
    if type(challenge["schema"]) is not int or challenge["schema"] != 1:
        raise SignatureCheckError("challenge schema must be integer 1")
    if challenge["classification"] != "development_registry_challenge_unsealed":
        raise SignatureCheckError("challenge classification is invalid")
    if challenge["notice"] != NOTICE:
        raise SignatureCheckError("challenge notice is invalid")
    message_bytes = _b64(challenge["message_base64"], "challenge message_base64", None)
    if _sha256(challenge["message_sha256"], "challenge message_sha256") != _sha_digest(message_bytes):
        raise SignatureCheckError("challenge message digest differs from its bytes")
    try:
        message = json.loads(message_bytes.decode("utf-8"))
        if message_bytes != canonical_bytes(message):
            raise SignatureCheckError("challenge message is not canonical JSON")
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SignatureCheckError("challenge message is not canonical JSON") from exc
    message = _exact_object(message, "challenge message", {
        "purpose", "schema", "goal_sha256", "protocol_sha256", "schedule_sha256",
        "input_sha256", "asset_digest_binding_sha256",
    })
    if message["purpose"] != PURPOSE or type(message["schema"]) is not int or message["schema"] != 1:
        raise SignatureCheckError("challenge message purpose or schema is invalid")
    for field in (
        "goal_sha256", "protocol_sha256", "schedule_sha256", "input_sha256",
        "asset_digest_binding_sha256",
    ):
        _sha256(message[field], f"challenge message {field}")
    if message["goal_sha256"] != EXPECTED_GOAL_SHA256:
        raise SignatureCheckError("challenge GOAL digest differs from the required study baseline")
    return challenge, message_bytes


def _sha_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_attestation(challenge_raw: Any, attestation_raw: Any, trust_raw: Any) -> dict[str, Any]:
    """Verify a detached signature against a separately supplied public key."""
    challenge, message_bytes = _challenge_bytes(challenge_raw)
    attestation = _exact_object(
        attestation_raw, "attestation", {"schema", "key_id", "message_sha256", "signature_base64"}
    )
    if type(attestation["schema"]) is not int or attestation["schema"] != 1:
        raise SignatureCheckError("attestation schema must be integer 1")
    key_id = _key_id(attestation["key_id"])
    if _sha256(attestation["message_sha256"], "attestation message_sha256") != challenge["message_sha256"]:
        raise SignatureCheckError("attestation message digest differs from current inputs")
    signature = _b64(attestation["signature_base64"], "signature_base64", 64)

    trust = _exact_object(trust_raw, "trust", {"schema", "keys"})
    if type(trust["schema"]) is not int or trust["schema"] != 1:
        raise SignatureCheckError("trust schema must be integer 1")
    keys = trust["keys"]
    if type(keys) is not dict or not keys:
        raise SignatureCheckError("trust keys must be a nonempty object")
    for supplied_id, supplied_key in keys.items():
        _key_id(supplied_id)
        _b64(supplied_key, "trusted public key", 32)
    if key_id not in keys:
        raise SignatureCheckError("key_id is absent from supplied trust")
    public_bytes = _b64(keys[key_id], "trusted public key", 32)
    try:
        Ed25519PublicKey.from_public_bytes(public_bytes).verify(signature, message_bytes)
    except (InvalidSignature, ValueError) as exc:
        raise SignatureCheckError("signature verification failed") from exc
    return {
        "schema": 1,
        "classification": "development_registry_signature_verified_unsealed",
        "message_sha256": challenge["message_sha256"],
        "key_id": key_id,
        "public_key_sha256": _sha_digest(public_bytes),
        "trust_sha256": _sha_digest(canonical_bytes(trust)),
        "notice": NOTICE,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("challenge", "verify"):
        command = subcommands.add_parser(name)
        command.add_argument("schedule", help="candidate schedule JSON")
        command.add_argument("assets", help="schema-1 absolute asset map JSON")
        command.add_argument("--goal", default="GOAL.md", help="current GOAL.md")
        command.add_argument("--protocol", default="docs/protocolo_experimental.md", help="current protocol")
        if name == "verify":
            command.add_argument("--attestation", required=True, help="detached attestation JSON")
            command.add_argument("--trust", required=True, help="absolute path to separate public-key trust JSON")
    args = parser.parse_args(argv)
    try:
        challenge = build_challenge(
            _json_file(args.schedule, "schedule"),
            _json_file(args.assets, "asset map"),
            goal=args.goal,
            protocol=args.protocol,
        )
        if args.command == "verify":
            if not Path(args.trust).is_absolute():
                raise SignatureCheckError("trust path must be absolute")
            result = verify_attestation(
                challenge,
                _json_file(args.attestation, "attestation"),
                _json_file(args.trust, "trust"),
            )
        else:
            result = challenge
    except SignatureCheckError as exc:
        print(f"Study signature check failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
