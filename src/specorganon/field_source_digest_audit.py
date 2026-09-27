"""Match declared primary field-record digests to already opened source entries.

Call this after the existing field preflights and after the attestation reader has
checked each manifest entry against its file bytes. This pure audit performs no
I/O. It only links declared digests to source entries of the expected role;
matching bytes cannot establish source truth, physical custody, or approval.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any


CLASSIFICATION = "field_primary_source_digest_coverage_declared_only"
PRIMARY_ROLES = ("source_record", "approval_record")
MANIFEST_ROLES = frozenset({
    "plan", "field", "registry", "measurements", "analysis", *PRIMARY_ROLES,
})
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MAX_EXAMPLES = 5
MAX_REFERENCE_EXAMPLES = 3
NOTICE = (
    "Only digest links to caller-verified source bytes were compared. Source truth, "
    "physical custody, approval authority, temporal custody, population coverage, "
    "causal attribution and field impact are not authenticated; criterion 3 is not assessed."
)


class FieldSourceDigestAuditError(ValueError):
    """The supplied digest references or manifest projections are malformed."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise FieldSourceDigestAuditError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise FieldSourceDigestAuditError(f"{label} must be an array")
    return value


def _digest(value: Any, label: str) -> str:
    if type(value) is not str or SHA256.fullmatch(value) is None:
        raise FieldSourceDigestAuditError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _required_digest(item: dict[str, Any], key: str, label: str) -> str:
    if key not in item:
        raise FieldSourceDigestAuditError(f"{label}.{key} is required")
    return _digest(item[key], f"{label}.{key}")


def audit_field_source_digest_coverage(
    plan: dict[str, Any],
    field: dict[str, Any],
    registry: dict[str, Any],
    measurements: dict[str, Any],
    sources: list[dict[str, str]],
    *,
    analysis: Any = None,
) -> dict[str, Any]:
    """Compare every current primary digest reference with manifest role and hash.

    ``sources`` is the caller's projection of the *already byte-verified* source
    manifest to ``{role, sha256}`` records. A repeated reference to one digest
    is allowed; duplicate manifest entries and unreferenced primary entries
    prevent an exact match. Core manifest roles are outside this comparison.
    Schema-2 analysis adds baseline input volume source references. This
    function does not replace structural preflight of its inputs.
    """
    plan = _object(plan, "plan")
    field = _object(field, "field")
    registry = _object(registry, "registry")
    measurements = _object(measurements, "measurements")
    sources = _list(sources, "sources")

    required: dict[tuple[str, str], list[str]] = defaultdict(list)

    def add(role: str, digest: str, reference: str) -> None:
        required[(role, digest)].append(reference)

    add("source_record", _required_digest(plan, "allocation_record_sha256", "plan"),
        "plan.allocation_record_sha256")
    if "baseline_release" in plan:
        release = _object(plan["baseline_release"], "plan.baseline_release")
        add("source_record", _required_digest(release, "record_sha256", "plan.baseline_release"),
            "plan.baseline_release.record_sha256")

    service = field.get("service")
    if service is not None:
        service = _object(service, "field.service")
        service_schema = service.get("schema")
        if "schema" in service and (type(service_schema) is not int or service_schema != 2):
            raise FieldSourceDigestAuditError("field.service.schema must be integer 2 when present")
        if "equivalence" not in service:
            raise FieldSourceDigestAuditError("field.service.equivalence is required")
        equivalence = _object(service["equivalence"], "field.service.equivalence")
        add("approval_record", _required_digest(equivalence, "record_sha256",
                                                 "field.service.equivalence"),
            "field.service.equivalence.record_sha256")
        if service_schema == 2:
            if "rows" not in service:
                raise FieldSourceDigestAuditError("field.service.rows is required")
            seen_service_references: set[tuple[str, str]] = set()
            for index, raw_row in enumerate(_list(service["rows"], "field.service.rows")):
                label = f"field.service.rows[{index}]"
                service_row = _object(raw_row, label)
                if "source" not in service_row:
                    raise FieldSourceDigestAuditError(f"{label}.source is required")
                source = _object(service_row["source"], f"{label}.source")
                digest = _required_digest(source, "record_sha256", f"{label}.source")
                locator = source.get("locator")
                if type(locator) is not str or not locator.strip() or locator != locator.strip():
                    raise FieldSourceDigestAuditError(f"{label}.source.locator must be nonempty trimmed text")
                reference = digest, locator
                if reference in seen_service_references:
                    raise FieldSourceDigestAuditError(
                        f"{label}.source repeats a service digest and locator reference"
                    )
                seen_service_references.add(reference)
                add("source_record", digest, f"{label}.source.record_sha256")

    if "cells" not in registry:
        raise FieldSourceDigestAuditError("registry.cells is required")
    for index, cell in enumerate(_list(registry["cells"], "registry.cells")):
        label = f"registry.cells[{index}]"
        cell = _object(cell, label)
        status = cell.get("status")
        if status == "excluded":
            add("approval_record", _required_digest(cell, "approval_record_sha256", label),
                f"{label}.approval_record_sha256")
        elif status != "measured":
            raise FieldSourceDigestAuditError(f"{label}.status must be measured or excluded")

    if "rows" not in measurements:
        raise FieldSourceDigestAuditError("measurements.rows is required")
    for index, row in enumerate(_list(measurements["rows"], "measurements.rows")):
        label = f"measurements.rows[{index}]"
        row = _object(row, label)
        if "source" not in row:
            raise FieldSourceDigestAuditError(f"{label}.source is required")
        source = _object(row["source"], f"{label}.source")
        add("source_record", _required_digest(source, "record_sha256", f"{label}.source"),
            f"{label}.source.record_sha256")

    has_baseline_volume = type(analysis) is dict and type(analysis.get("schema")) is int \
        and analysis["schema"] == 2
    if has_baseline_volume:
        if "baseline_input_volume_manifest" not in analysis:
            raise FieldSourceDigestAuditError("analysis.baseline_input_volume_manifest is required")
        volume_manifest = _object(analysis["baseline_input_volume_manifest"],
                                  "analysis.baseline_input_volume_manifest")
        if "rows" not in volume_manifest:
            raise FieldSourceDigestAuditError("analysis.baseline_input_volume_manifest.rows is required")
        volume_rows = _list(volume_manifest["rows"],
                            "analysis.baseline_input_volume_manifest.rows")
        if not volume_rows:
            raise FieldSourceDigestAuditError(
                "analysis.baseline_input_volume_manifest.rows must be nonempty"
            )
        seen_volume_references: set[tuple[str, str]] = set()
        for index, raw_row in enumerate(volume_rows):
            label = f"analysis.baseline_input_volume_manifest.rows[{index}]"
            volume_row = _object(raw_row, label)
            if "source" not in volume_row:
                raise FieldSourceDigestAuditError(f"{label}.source is required")
            source = _object(volume_row["source"], f"{label}.source")
            digest = _required_digest(source, "record_sha256", f"{label}.source")
            locator = source.get("locator")
            if type(locator) is not str or not locator.strip() or locator != locator.strip():
                raise FieldSourceDigestAuditError(
                    f"{label}.source.locator must be nonempty trimmed text"
                )
            reference = digest, locator
            if reference in seen_volume_references:
                raise FieldSourceDigestAuditError(
                    f"{label}.source repeats a volume digest and locator reference"
                )
            seen_volume_references.add(reference)
            add("source_record", digest, f"{label}.source.record_sha256")

    opened: Counter[tuple[str, str]] = Counter()
    non_primary_entries = 0
    for index, item in enumerate(sources):
        label = f"sources[{index}]"
        item = _object(item, label)
        if set(item) != {"role", "sha256"}:
            raise FieldSourceDigestAuditError(f"{label} must contain exactly role and sha256")
        role = item["role"]
        if type(role) is not str or role not in MANIFEST_ROLES:
            raise FieldSourceDigestAuditError(f"{label}.role is unsupported")
        digest = _digest(item["sha256"], f"{label}.sha256")
        if role in PRIMARY_ROLES:
            opened[(role, digest)] += 1
        else:
            non_primary_entries += 1

    required_keys = set(required)
    opened_keys = set(opened)
    missing = sorted(required_keys - opened_keys)
    extra = sorted(opened_keys - required_keys)
    duplicates = sorted((key, count) for key, count in opened.items() if count > 1)
    wrong_role = [
        (role, digest, next(other for other in PRIMARY_ROLES if other != role))
        for role, digest in missing
        if any(opened[(other, digest)] for other in PRIMARY_ROLES if other != role)
    ]
    exact = not missing and not extra and not duplicates

    by_role: dict[str, dict[str, int]] = {}
    for role in PRIMARY_ROLES:
        refs = sum(len(paths) for (kind, _), paths in required.items() if kind == role)
        distinct = sum(kind == role for kind, _ in required_keys)
        role_missing = sum(kind == role for kind, _ in missing)
        role_extra = sum(kind == role for kind, _ in extra)
        role_opened = sum(count for (kind, _), count in opened.items() if kind == role)
        role_duplicates = sum(count - 1 for (kind, _), count in opened.items()
                              if kind == role)
        by_role[role] = {
            "required_references": refs,
            "unique_required_digests": distinct,
            "repeated_references": refs - distinct,
            "opened_entries": role_opened,
            "matched_unique_digests": distinct - role_missing,
            "missing_unique_digests": role_missing,
            "missing_references": sum(len(required[key]) for key in missing if key[0] == role),
            "extra_unique_digests": role_extra,
            "duplicate_opened_entries": role_duplicates,
        }

    return {
        "schema": 1,
        "classification": CLASSIFICATION,
        "exact_primary_source_coverage": exact,
        **({"service_v_input_byte_bound": False}
           if type(field.get("service")) is dict and field["service"].get("schema") == 2
           else {}),
        **({"baseline_volume_input_byte_bound": False} if has_baseline_volume else {}),
        "counts": {
            "required_references": sum(len(paths) for paths in required.values()),
            "unique_required_role_digests": len(required_keys),
            "repeated_references": sum(len(paths) for paths in required.values()) - len(required_keys),
            "opened_primary_entries": sum(opened.values()),
            "missing_unique_role_digests": len(missing),
            "missing_references": sum(len(required[key]) for key in missing),
            "wrong_role_unique_digests": len(wrong_role),
            "extra_unique_role_digests": len(extra),
            "duplicate_opened_entries": sum(count - 1 for _, count in duplicates),
        },
        "by_role": by_role,
        "non_primary_manifest_entries": non_primary_entries,
        "missing_examples": [
            {"role": role, "sha256": digest, "reference_count": len(required[(role, digest)]),
             "reference_examples": sorted(required[(role, digest)])[:MAX_REFERENCE_EXAMPLES]}
            for role, digest in missing[:MAX_EXAMPLES]
        ],
        "wrong_role_examples": [
            {"expected_role": role, "found_role": other, "sha256": digest}
            for role, digest, other in wrong_role[:MAX_EXAMPLES]
        ],
        "extra_examples": [
            {"role": role, "sha256": digest}
            for role, digest in extra[:MAX_EXAMPLES]
        ],
        "duplicate_opened_examples": [
            {"role": role, "sha256": digest, "entry_count": count}
            for (role, digest), count in duplicates[:MAX_EXAMPLES]
        ],
        "missing_example_limit": MAX_EXAMPLES,
        "source_truth_authenticated": False,
        "physical_custody_authenticated": False,
        "approval_authenticated": False,
        "execution_ready": False,
        "criterion_3": {"status": "not_assessed", "reason": NOTICE},
        "notice": NOTICE,
    }
