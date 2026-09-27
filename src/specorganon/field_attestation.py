"""Independent, revocable signature over a field assessment and its source bytes.

This authenticates the configured assessor's statement and locally readable
materials. It cannot establish that a person is competent or that field
measurements, causal attribution, or source custody are true.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import stat
from decimal import Decimal
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import approval


MANIFEST_CLASSIFICATION = "field_attestation_sources"
REPORT_CLASSIFICATION = "independent_field_assessment"
REQUIRED_ROLES = frozenset({"plan", "field", "registry", "measurements", "analysis"})
OPTIONAL_ROLES = frozenset({"source_record", "approval_record"})
REPORT_REVIEWS = (
    "source_custody", "causal_attribution", "value_metric", "harms_by_actor_stage",
    "costs", "uncertainty", "limitations", "conclusion",
)
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_REPORT_BYTES = 4 * 1024 * 1024
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_SOURCE_COUNT = 64
MAX_TOTAL_SOURCE_BYTES = 256 * 1024 * 1024


class FieldAttestationError(ValueError):
    """An assessor trust anchor or field evidence bundle is invalid."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FieldAttestationError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise FieldAttestationError(f"invalid JSON numeric constant: {value}")


def _json_object(raw: bytes, name: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), parse_float=Decimal,
                           parse_constant=_reject_constant, object_pairs_hook=_json_pairs)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise FieldAttestationError(f"invalid {name} JSON") from exc
    if type(value) is not dict:
        raise FieldAttestationError(f"{name} must be a JSON object")
    return value


def _hex_digest(value: Any, name: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise FieldAttestationError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _absolute_regular_bytes(value: Any, name: str, limit: int) -> tuple[str, bytes]:
    if type(value) is not str or not value:
        raise FieldAttestationError(f"{name} must be an absolute regular file path")
    path = Path(value)
    if not path.is_absolute():
        raise FieldAttestationError(f"{name} must be an absolute regular file path")
    try:
        canonical = path.resolve(strict=True)
        if str(canonical) != value:
            raise FieldAttestationError(f"{name} must be canonical and free of symlinks")
        fd = os.open(canonical, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise FieldAttestationError(f"{name} must be a private regular file")
            if metadata.st_size > limit:
                raise FieldAttestationError(f"{name} exceeds the supported byte limit")
            with os.fdopen(fd, "rb", closefd=False) as source:
                raw = source.read(limit + 1)
            if len(raw) > limit:
                raise FieldAttestationError(f"{name} exceeds the supported byte limit")
            return value, raw
        finally:
            os.close(fd)
    except (OSError, RuntimeError) as exc:
        raise FieldAttestationError(f"cannot read {name}") from exc


def trust_context(project: dict[str, Any], path: str | Path) -> tuple[dict[str, bytes], str]:
    """Read an independently custodied assessor registry on each replay."""
    configured = os.environ.get("ORGANON_FIELD_ASSESSORS_FILE")
    if not configured or not Path(configured).is_absolute():
        raise FieldAttestationError("signed field attestation requires ORGANON_FIELD_ASSESSORS_FILE")
    _, raw = _absolute_regular_bytes(configured, "assessor registry", MAX_MANIFEST_BYTES)
    registry = _json_object(raw, "assessor registry")
    if (set(registry) != {"schema", "cases"} or type(registry["schema"]) is not int
            or registry["schema"] != 1 or type(registry["cases"]) is not dict):
        raise FieldAttestationError("malformed assessor registry")
    case_id = project.get("case_id")
    entry = registry["cases"].get(case_id)
    actual = approval.case_path(path)
    path_matches = [key for key, candidate in registry["cases"].items()
                    if type(candidate) is dict and candidate.get("path") == actual]
    if len(path_matches) != 1 or path_matches[0] != case_id or type(entry) is not dict:
        raise FieldAttestationError("case is not uniquely registered for field assessment at this path")
    if set(entry) != {"path", "project_sha256", "assessors"}:
        raise FieldAttestationError("malformed assessor registry case entry")
    if entry["project_sha256"] != approval.project_fingerprint(project):
        raise FieldAttestationError("assessor registry project fingerprint differs")
    raw_assessors = entry["assessors"]
    if type(raw_assessors) is not dict or not raw_assessors:
        raise FieldAttestationError("assessor registry has no public keys")
    assessors: dict[str, bytes] = {}
    for actor, encoded in raw_assessors.items():
        if type(actor) is not str or not actor.startswith("assessor:") or len(actor) <= 9:
            raise FieldAttestationError("invalid assessor actor")
        try:
            key = base64.b64decode(encoded, validate=True)
        except (binascii.Error, TypeError, ValueError) as exc:
            raise FieldAttestationError("invalid assessor public key") from exc
        if len(key) != 32:
            raise FieldAttestationError("invalid assessor public key")
        assessors[actor] = key
    return assessors, "configured"


def inspect_materials(
    project: dict[str, Any], assessment_id: str, assessment_version: int, verdict: str,
    manifest_path: str, report_path: str,
) -> dict[str, Any]:
    """Reopen every declared source and rerun the declared structural preflight."""
    manifest_path, manifest_raw = _absolute_regular_bytes(
        manifest_path, "source manifest", MAX_MANIFEST_BYTES)
    manifest = _json_object(manifest_raw, "source manifest")
    if (set(manifest) != {"schema", "classification", "sources"}
            or type(manifest["schema"]) is not int or manifest["schema"] != 1
            or manifest["classification"] != MANIFEST_CLASSIFICATION
            or type(manifest["sources"]) is not list
            or not 5 <= len(manifest["sources"]) <= MAX_SOURCE_COUNT):
        raise FieldAttestationError("malformed field source manifest")
    sources: dict[str, list[tuple[str, bytes]]] = {}
    seen_paths: set[str] = set()
    total_bytes = 0
    for index, source in enumerate(manifest["sources"]):
        name = f"sources[{index}]"
        if type(source) is not dict or set(source) != {"role", "path", "sha256"}:
            raise FieldAttestationError(f"{name} must declare role, path and SHA-256")
        role = source["role"]
        if type(role) is not str or role not in REQUIRED_ROLES | OPTIONAL_ROLES:
            raise FieldAttestationError(f"{name} has an unsupported role")
        path, raw = _absolute_regular_bytes(source["path"], name, MAX_SOURCE_BYTES)
        if path in seen_paths:
            raise FieldAttestationError("source manifest repeats a file path")
        seen_paths.add(path)
        if _sha256(raw) != _hex_digest(source["sha256"], f"{name}.sha256"):
            raise FieldAttestationError(f"{name} source bytes differ from manifest")
        total_bytes += len(raw)
        if total_bytes > MAX_TOTAL_SOURCE_BYTES:
            raise FieldAttestationError("field sources exceed the supported total byte limit")
        sources.setdefault(role, []).append((path, raw))
    if any(len(sources.get(role, ())) != 1 for role in REQUIRED_ROLES):
        raise FieldAttestationError("source manifest needs one plan, field, registry, measurements and analysis")

    from .field_effect_analysis import FieldEffectAnalysisError, audit_field_effect_analysis
    from .field_guardrails import audit_field_guardrails, canonical_sha256

    plan, field, registry, measurements = (
        _json_object(sources[role][0][1], role)
        for role in ("plan", "field", "registry", "measurements")
    )
    try:
        preflight = audit_field_guardrails(
            plan, field, registry, measurements,
            plan_sha256=canonical_sha256(plan), registry_sha256=canonical_sha256(registry),
        )
    except ValueError as exc:
        raise FieldAttestationError(f"field guardrail preflight failed: {exc}") from exc
    if preflight.get("structural_match_at_read") is not True:
        raise FieldAttestationError("field guardrail preflight did not match")
    preflight_sha256 = _sha256(_canonical(preflight))
    analysis = _json_object(sources["analysis"][0][1], "analysis")
    try:
        analysis_preflight = audit_field_effect_analysis(
            plan, field, registry, measurements, analysis,
        )
    except FieldEffectAnalysisError as exc:
        raise FieldAttestationError(f"field effect analysis preflight failed: {exc}") from exc
    if analysis_preflight.get("decision_ready") is not False:
        raise FieldAttestationError("field effect analysis preflight must remain non-decisive")
    analysis_preflight_sha256 = _sha256(_canonical(analysis_preflight))

    report_path, report_raw = _absolute_regular_bytes(report_path, "assessor report", MAX_REPORT_BYTES)
    report = _json_object(report_raw, "assessor report")
    expected = {"schema", "classification", "case_id", "assessment_id", "assessment_version",
                "verdict", "source_manifest_sha256", "preflight_sha256", "analysis_sha256",
                *REPORT_REVIEWS}
    if (set(report) != expected or type(report.get("schema")) is not int
            or report["schema"] != 1 or report.get("classification") != REPORT_CLASSIFICATION):
        raise FieldAttestationError("malformed independent field assessment report")
    if (report.get("case_id") != project.get("case_id")
            or report.get("assessment_id") != assessment_id
            or type(report.get("assessment_version")) is not int
            or report["assessment_version"] != assessment_version
            or report.get("verdict") != verdict):
        raise FieldAttestationError("assessor report targets another case, item or verdict")
    manifest_sha256 = _sha256(manifest_raw)
    analysis_sha256 = _sha256(sources["analysis"][0][1])
    if (report.get("source_manifest_sha256") != manifest_sha256
            or report.get("preflight_sha256") != preflight_sha256
            or report.get("analysis_sha256") != analysis_sha256):
        raise FieldAttestationError("assessor report does not bind current source or preflight bytes")
    if any(type(report.get(field)) is not str or not report[field].strip() for field in REPORT_REVIEWS):
        raise FieldAttestationError("assessor report lacks substantive review fields")
    if report["conclusion"] != verdict:
        raise FieldAttestationError("assessor conclusion differs from the attested verdict")
    return {
        "source_manifest_path": manifest_path,
        "source_manifest_sha256": manifest_sha256,
        "report_path": report_path,
        "report_sha256": _sha256(report_raw),
        "preflight_sha256": preflight_sha256,
        "analysis_sha256": analysis_sha256,
        "analysis_preflight_sha256": analysis_preflight_sha256,
    }


def message(
    project: dict[str, Any], path: str | Path, binding: dict[str, Any],
    materials: dict[str, Any], actor: str, reason: str, ledger_head_sha256: str,
) -> bytes:
    return _canonical({
        "schema": 1,
        "purpose": "specorganon.independent_field_attestation",
        "decision": "attest",
        "case_id": project["case_id"],
        "case_path": approval.case_path(path),
        "project_sha256": approval.project_fingerprint(project),
        "ledger_head_sha256": ledger_head_sha256,
        "binding": binding,
        "materials": materials,
        "actor": actor,
        "reason": reason,
    })


def challenge(
    project: dict[str, Any], path: str | Path, binding: dict[str, Any],
    materials: dict[str, Any], actor: str, reason: str, ledger_head_sha256: str,
) -> dict[str, Any]:
    raw = message(project, path, binding, materials, actor, reason, ledger_head_sha256)
    return {
        "algorithm": "Ed25519", "encoding": "base64",
        "message_base64": base64.b64encode(raw).decode("ascii"),
        "message_sha256": _sha256(raw),
        "actor": actor,
        "assessment_id": binding["assessment_id"],
        "assessment_version": binding["assessment_version"],
        "source_manifest_sha256": materials["source_manifest_sha256"],
        "report_sha256": materials["report_sha256"],
        "ledger_head_sha256": ledger_head_sha256,
    }


def verify(
    project: dict[str, Any], path: str | Path, binding: dict[str, Any],
    materials: dict[str, Any], actor: str, reason: str, ledger_head_sha256: str,
    signature: str, key_sha256: str, assessors: dict[str, bytes],
) -> bool:
    key = assessors.get(actor)
    if key is None or _sha256(key) != key_sha256:
        return False
    try:
        raw_signature = base64.b64decode(signature, validate=True)
        if len(raw_signature) != 64:
            return False
        Ed25519PublicKey.from_public_bytes(key).verify(
            raw_signature, message(project, path, binding, materials, actor, reason,
                                   ledger_head_sha256))
    except (InvalidSignature, TypeError, ValueError, binascii.Error, KeyError):
        return False
    return True
