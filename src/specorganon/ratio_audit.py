"""Pure-data audit of a declared fraction derived from a pinned JSON report.

The contract is an independent, versionable statement of what source fields
mean and which target metric may use them. It does not authenticate the
contract author's interpretation of the underlying observations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,9})?\Z")
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_CONTRACT_BYTES = 1024 * 1024
MAX_CLAIM_BYTES = 64 * 1024


class RatioAuditError(ValueError):
    """The source, contract, or proposed target cannot support this ratio."""


def _pairs_unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RatioAuditError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise RatioAuditError(f"non-finite JSON value: {value}")


def _json_object(raw: bytes, label: str, maximum: int) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > maximum:
        raise RatioAuditError(f"{label} must be nonempty bytes within the size limit")
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs_unique,
            parse_constant=_invalid_constant,
        )
    except RatioAuditError:
        raise
    except (ValueError, RecursionError) as exc:
        raise RatioAuditError(f"{label} must be a UTF-8 JSON object") from exc
    return _object(parsed, label)


def _object(value: Any, label: str, fields: set[str] | None = None) -> dict[str, Any]:
    if type(value) is not dict or (fields is not None and set(value) != fields):
        suffix = "" if fields is None else f" with exactly {sorted(fields)}"
        raise RatioAuditError(f"{label} must be an object{suffix}")
    return value


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise RatioAuditError(f"{label} must be nonempty trimmed text")
    return value


def _sha256(value: Any, label: str) -> str:
    if type(value) is not str or SHA256.fullmatch(value) is None:
        raise RatioAuditError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _utc(value: Any, label: str) -> str:
    _text(value, label)
    if UTC.fullmatch(value) is None:
        raise RatioAuditError(
            f"{label} must be a whole-second UTC timestamp ending in Z"
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RatioAuditError(f"{label} must be a valid UTC timestamp") from exc
    if parsed.utcoffset().total_seconds() != 0:
        raise RatioAuditError(f"{label} must be UTC")
    return value


def _scope(value: Any, label: str) -> dict[str, str]:
    item = _object(value, label, {"id", "start_utc", "end_utc"})
    scope = {
        "id": _text(item["id"], f"{label}.id"),
        "start_utc": _utc(item["start_utc"], f"{label}.start_utc"),
        "end_utc": _utc(item["end_utc"], f"{label}.end_utc"),
    }
    if datetime.fromisoformat(scope["start_utc"][:-1]) > datetime.fromisoformat(
        scope["end_utc"][:-1]
    ):
        raise RatioAuditError(f"{label} starts after it ends")
    return scope


def _locator(source: dict[str, Any], locator: Any, label: str) -> Any:
    path = _text(locator, label)
    parts = path.split(".")
    if any(not part or part in {"__proto__", "constructor"} for part in parts):
        raise RatioAuditError(f"{label} is not a supported dotted locator")
    value: Any = source
    for part in parts:
        if type(value) is not dict or part not in value:
            raise RatioAuditError(f"{label} is absent from source: {path}")
        value = value[part]
    return value


def _quantity(
    source: dict[str, Any],
    quantity_id: str,
    raw: Any,
) -> tuple[dict[str, Any], Fraction]:
    label = f"contract.quantities.{quantity_id}"
    item = _object(
        raw,
        label,
        {
            "locator",
            "value_type",
            "unit",
            "observation_unit",
            "population",
            "time_scope",
        },
    )
    value_type = _text(item["value_type"], f"{label}.value_type")
    if value_type not in {"integer_count", "decimal_quantity"}:
        raise RatioAuditError(f"{label}.value_type is unsupported")
    locator = _text(item["locator"], f"{label}.locator")
    value = _locator(source, locator, f"{label}.locator")
    if value_type == "integer_count":
        if type(value) is not int or not 0 <= value <= 10**18:
            raise RatioAuditError(f"{label} must locate a nonnegative integer count")
        exact = Fraction(value)
    else:
        if type(value) is not str or DECIMAL.fullmatch(value) is None:
            raise RatioAuditError(f"{label} must locate a nonnegative decimal string")
        exact = Fraction(Decimal(value))
    normalized = {
        "quantity_id": quantity_id,
        "locator": locator,
        "value_type": value_type,
        "value": value,
        "unit": _text(item["unit"], f"{label}.unit"),
        "observation_unit": _text(
            item["observation_unit"], f"{label}.observation_unit"
        ),
        "population": _text(item["population"], f"{label}.population"),
        "time_scope": _scope(item["time_scope"], f"{label}.time_scope"),
    }
    return normalized, exact


def audit_derived_ratio(
    source_bytes: bytes,
    contract_bytes: bytes,
    claim_bytes: bytes,
    contract_sha256: str,
) -> dict[str, Any]:
    """Audit one claim against a pinned source and an independent target contract.

    Inputs are caller-opened bytes plus an external expected contract digest;
    this function does no I/O. The returned rational is reduced exactly and
    contains no floating-point approximation.
    """
    if (
        type(source_bytes) is not bytes
        or not source_bytes
        or len(source_bytes) > MAX_SOURCE_BYTES
    ):
        raise RatioAuditError("source must be nonempty bytes within the size limit")
    if (
        type(contract_bytes) is not bytes
        or not contract_bytes
        or len(contract_bytes) > MAX_CONTRACT_BYTES
    ):
        raise RatioAuditError("contract must be nonempty bytes within the size limit")
    if hashlib.sha256(contract_bytes).hexdigest() != _sha256(
        contract_sha256, "contract_sha256"
    ):
        raise RatioAuditError(
            "contract SHA-256 differs from the external expected digest"
        )
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    contract = _json_object(contract_bytes, "contract", MAX_CONTRACT_BYTES)
    _object(
        contract,
        "contract",
        {
            "schema",
            "classification",
            "source_sha256",
            "source_assertions",
            "source_window",
            "quantities",
            "targets",
        },
    )
    if type(contract["schema"]) is not int or contract["schema"] != 1:
        raise RatioAuditError("contract.schema must be 1")
    classification = _text(contract["classification"], "contract.classification")
    if source_digest != _sha256(contract["source_sha256"], "contract.source_sha256"):
        raise RatioAuditError("source SHA-256 differs from the pinned contract digest")
    source = _json_object(source_bytes, "source", MAX_SOURCE_BYTES)
    assertions = _object(contract["source_assertions"], "contract.source_assertions")
    if not assertions:
        raise RatioAuditError("contract.source_assertions must not be empty")
    for path, expected in assertions.items():
        observed = _locator(source, path, "contract.source_assertions locator")
        if type(expected) not in {str, int, bool} or (
            type(observed) is not type(expected) or observed != expected
        ):
            raise RatioAuditError(f"source assertion differs at {path}")
    window_locators = _object(
        contract["source_window"],
        "contract.source_window",
        {
            "start_locator",
            "end_locator",
        },
    )
    source_window = {
        "start_utc": _utc(
            _locator(
                source, window_locators["start_locator"], "source_window.start_locator"
            ),
            "source_window.start_utc",
        ),
        "end_utc": _utc(
            _locator(
                source, window_locators["end_locator"], "source_window.end_locator"
            ),
            "source_window.end_utc",
        ),
    }
    if source_window["start_utc"] > source_window["end_utc"]:
        raise RatioAuditError("source window starts after it ends")

    claim = _json_object(claim_bytes, "claim", MAX_CLAIM_BYTES)
    _object(
        claim,
        "claim",
        {
            "schema",
            "target_id",
            "metric",
            "unit",
            "observation_unit",
            "population",
            "time_scope",
        },
    )
    if type(claim["schema"]) is not int or claim["schema"] != 1:
        raise RatioAuditError("claim.schema must be 1")
    target_id = _text(claim["target_id"], "claim.target_id")
    targets = _object(contract["targets"], "contract.targets")
    if target_id not in targets:
        raise RatioAuditError(f"target {target_id} is not predeclared in contract")
    target = _object(
        targets[target_id],
        f"contract.targets.{target_id}",
        {
            "metric",
            "unit",
            "observation_unit",
            "population",
            "time_scope",
            "numerator_quantity",
            "denominator_quantity",
            "relation",
        },
    )
    target_scope = _scope(
        target["time_scope"], f"contract.targets.{target_id}.time_scope"
    )
    claim_scope = _scope(claim["time_scope"], "claim.time_scope")
    if any(target_scope[key] != source_window[key] for key in ("start_utc", "end_utc")):
        raise RatioAuditError(
            f"target {target_id} time_scope differs from source window"
        )
    if claim_scope != target_scope:
        raise RatioAuditError(
            f"claim.time_scope differs from predeclared target {target_id}"
        )
    for field in ("observation_unit", "population", "unit", "metric"):
        expected = _text(target[field], f"contract.targets.{target_id}.{field}")
        actual = _text(claim[field], f"claim.{field}")
        if actual != expected:
            raise RatioAuditError(
                f"claim.{field} differs from predeclared target {target_id}"
            )
    if target["unit"] != "fraction" or target["relation"] != "subset_fraction":
        raise RatioAuditError(f"target {target_id} must be a declared subset fraction")

    quantities = _object(contract["quantities"], "contract.quantities")
    selected: dict[str, tuple[dict[str, Any], Fraction]] = {}
    for role in ("numerator", "denominator"):
        quantity_id = _text(target[f"{role}_quantity"], f"target.{role}_quantity")
        if quantity_id not in quantities:
            raise RatioAuditError(
                f"target {role} quantity {quantity_id} is not declared"
            )
        selected[role] = _quantity(source, quantity_id, quantities[quantity_id])
    numerator, numerator_exact = selected["numerator"]
    denominator, denominator_exact = selected["denominator"]
    if numerator["value_type"] != denominator["value_type"]:
        raise RatioAuditError("numerator and denominator value types differ")
    for field in ("unit", "observation_unit", "population", "time_scope"):
        if numerator[field] != denominator[field]:
            raise RatioAuditError(f"numerator and denominator {field} differ")
    for field in ("observation_unit", "population", "time_scope"):
        if numerator[field] != (
            target_scope if field == "time_scope" else target[field]
        ):
            raise RatioAuditError(f"quantities {field} differs from target {target_id}")
    if denominator_exact <= 0:
        raise RatioAuditError("denominator must be positive")
    if numerator_exact > denominator_exact:
        raise RatioAuditError("subset numerator exceeds denominator")

    ratio = numerator_exact / denominator_exact
    return {
        "classification": "derived_ratio_audit",
        "source_sha256": source_digest,
        "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "claim_sha256": hashlib.sha256(claim_bytes).hexdigest(),
        "contract_classification": classification,
        "target_id": target_id,
        "metric": target["metric"],
        "unit": "fraction",
        "observation_unit": target["observation_unit"],
        "population": target["population"],
        "time_scope": target_scope,
        "numerator": numerator,
        "denominator": denominator,
        "exact_ratio": {"numerator": ratio.numerator, "denominator": ratio.denominator},
        "source_truth_authenticated": False,
        "subset_membership_verified_from_rows": False,
    }


def _read_limited(path: Path, maximum: int, label: str) -> bytes:
    """Open one input once; reject large regular files and bound every read."""
    with path.open("rb") as stream:
        if os.fstat(stream.fileno()).st_size > maximum:
            raise RatioAuditError(f"{label} exceeds the {maximum}-byte limit")
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise RatioAuditError(f"{label} exceeds the {maximum}-byte limit")
    return raw


def main(argv: list[str] | None = None) -> int:
    """Run the data audit from an installed wheel or source checkout."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--claim", required=True, type=Path, action="append")
    args = parser.parse_args(argv)
    try:
        source_bytes = _read_limited(args.source, MAX_SOURCE_BYTES, "source")
        contract_bytes = _read_limited(args.contract, MAX_CONTRACT_BYTES, "contract")
        expected = _sha256(args.contract_sha256, "contract_sha256")
        if hashlib.sha256(contract_bytes).hexdigest() != expected:
            raise RatioAuditError(
                "contract SHA-256 differs from the external expected digest"
            )
        results = [
            audit_derived_ratio(
                source_bytes,
                contract_bytes,
                _read_limited(path, MAX_CLAIM_BYTES, "claim"),
                expected,
            )
            for path in args.claim
        ]
        target_ids = [result["target_id"] for result in results]
        if len(target_ids) != len(set(target_ids)):
            raise RatioAuditError("a target is claimed more than once")
        receipt = {
            "classification": "derived_ratio_audit_batch",
            "results": results,
        }
        rendered = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2)
    except (OSError, RatioAuditError) as exc:
        print(f"derived ratio audit failed: {exc}", file=sys.stderr)
        return 2
    except MemoryError:
        print(
            "derived ratio audit failed: input exceeds available memory",
            file=sys.stderr,
        )
        return 2
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
