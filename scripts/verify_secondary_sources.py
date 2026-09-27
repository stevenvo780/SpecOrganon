"""Verify local secondary-source bytes and a narrow model-invoice profile.

Usage: ``python scripts/verify_secondary_sources.py schedule.json receipts.json
assembly.json secondary.json blobs_dir``. Every source is a regular
``<sha256>.bin`` file in the private directory. The rate card and each invoice
extract are strict UTF-8 JSON. This local check does not authenticate a provider,
price authority, source author, timestamps, or independent custody.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
from collections import defaultdict
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

from analyze_confirmatory import (
    AnalysisError,
    _canonical_digest,
    _validate_schedule,
)
from analyze_secondary_metrics import (
    SecondaryError,
    _validate_assembly,
    _validate_secondary,
    _money,
)
from audit_run_receipts import ReceiptError, audit_receipts
from specorganon.ledger import strict_json_loads
from verify_preparation_bytes import (
    PreparationError,
    _directory,
    _names,
    _read_file,
)


CLASSIFICATION = "development_secondary_source_check_unsealed"
MAX_BLOB_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_BLOB_COUNT = 4096
MAX_INPUT_BYTES = 64 * 1024 * 1024
RATE_FIELDS = frozenset({"schema", "currency", "models"})
RATE_ROW_FIELDS = frozenset(
    {
        "model_id",
        "model_version",
        "input_uncached_usd_per_million",
        "input_cached_usd_per_million",
        "output_usd_per_million",
    }
)
INVOICE_FIELDS = frozenset({"schema", "run_id", "lines"})
LINE_FIELDS = frozenset({"attempt_number", "request_id", "model_usd"})
LIMITATIONS = [
    "Only local bytes named by supplied digests are checked; joint forgery remains possible.",
    "Audit, reference, injection, human, and wall source contents are not interpreted.",
    "The model invoice profile recalculates declared tokens against a supplied rate card.",
    "One rate per model/version is assumed; time, effort, and provider-specific charges are outside this profile.",
    "Nonzero tool or human charges are outside this narrow profile and are rejected.",
    "Zero declared tool or human charges do not prove that no such expense occurred.",
    "Provider usage, invoice origin, rate authority, real times, and custody are not authenticated.",
]


class SourceError(ValueError):
    """A fixed public error code for a private source check."""


def _fail(code: str) -> None:
    raise SourceError(code)


def _object(value: Any, fields: frozenset[str], code: str) -> dict[str, Any]:
    if type(value) is not dict or value.keys() != fields:
        _fail(code)
    return value


def _array(value: Any, code: str) -> list[Any]:
    if type(value) is not list:
        _fail(code)
    return value


def _decimal(value: Any, code: str) -> Decimal:
    try:
        return _money(value, code)
    except SecondaryError:
        _fail(code)


def _json_blob(data: bytes, code: str) -> Any:
    try:
        return strict_json_loads(data.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        _fail(code)


def _read_json_input(path: str) -> Any:
    if path == "-":
        data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(data) > MAX_INPUT_BYTES:
            _fail("input_too_large")
    else:
        candidate = Path(path)
        try:
            descriptor = _directory(candidate.parent, "input_unavailable")
        except PreparationError:
            _fail("input_unavailable")
        try:
            try:
                data = _read_file(
                    descriptor,
                    candidate.name,
                    MAX_INPUT_BYTES,
                    "input_unavailable",
                    "input_too_large",
                    "input_changed_during_read",
                )
            except PreparationError as exc:
                _fail(str(exc))
        finally:
            os.close(descriptor)
    return _json_blob(data, "invalid_json")


def _read_sources(
    directory: str | Path, expected: set[str], parse: set[str]
) -> dict[str, bytes]:
    if len(expected) > MAX_BLOB_COUNT:
        _fail("too_many_blobs")
    filenames = {digest + ".bin" for digest in expected}
    try:
        descriptor = _directory(directory, "blob_directory_unavailable")
    except PreparationError:
        _fail("blob_directory_unavailable")
    selected: dict[str, bytes] = {}
    total = 0
    try:
        try:
            names = _names(descriptor, "blob_directory_unavailable")
        except PreparationError:
            _fail("blob_directory_unavailable")
        if filenames - names:
            _fail("missing_blob")
        if names - filenames:
            _fail("extra_blob")
        for digest in sorted(expected):
            try:
                data = _read_file(
                    descriptor,
                    digest + ".bin",
                    MAX_BLOB_BYTES,
                    "blob_file_invalid",
                    "blob_too_large",
                    "blob_changed_during_read",
                )
            except PreparationError as exc:
                _fail(str(exc))
            if hashlib.sha256(data).hexdigest() != digest:
                _fail("blob_digest_mismatch")
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                _fail("blobs_too_large")
            if digest in parse:
                selected[digest] = data
        try:
            names = _names(descriptor, "blob_directory_unavailable")
        except PreparationError:
            _fail("blob_directory_unavailable")
        if filenames - names:
            _fail("missing_blob")
        if names - filenames:
            _fail("extra_blob")
        return selected
    finally:
        os.close(descriptor)


def _rate_card(
    data: bytes, used_models: set[tuple[str, str]]
) -> dict[tuple[str, str], tuple[Decimal, ...]]:
    card = _object(
        _json_blob(data, "rate_card_invalid"), RATE_FIELDS, "rate_card_invalid"
    )
    if (
        type(card["schema"]) is not int
        or card["schema"] != 1
        or card["currency"] != "USD"
    ):
        _fail("rate_card_invalid")
    rates: dict[tuple[str, str], tuple[Decimal, ...]] = {}
    for raw in _array(card["models"], "rate_card_invalid"):
        row = _object(raw, RATE_ROW_FIELDS, "rate_card_invalid")
        model, version = row["model_id"], row["model_version"]
        if (
            type(model) is not str
            or not model
            or type(version) is not str
            or not version
            or (model, version) in rates
        ):
            _fail("rate_card_invalid")
        rates[(model, version)] = tuple(
            _decimal(row[field], "rate_card_invalid")
            for field in (
                "input_uncached_usd_per_million",
                "input_cached_usd_per_million",
                "output_usd_per_million",
            )
        )
    if not used_models <= set(rates):
        _fail("rate_card_model_set_mismatch")
    return rates


def _invoice(data: bytes, run_id: str) -> dict[tuple[int, str], Decimal]:
    invoice = _object(
        _json_blob(data, "invoice_invalid"), INVOICE_FIELDS, "invoice_invalid"
    )
    if (
        type(invoice["schema"]) is not int
        or invoice["schema"] != 1
        or invoice["run_id"] != run_id
    ):
        _fail("invoice_invalid")
    lines: dict[tuple[int, str], Decimal] = {}
    for raw in _array(invoice["lines"], "invoice_invalid"):
        line = _object(raw, LINE_FIELDS, "invoice_invalid")
        number, request_id = line["attempt_number"], line["request_id"]
        if (
            type(number) is not int
            or number < 1
            or type(request_id) is not str
            or not request_id
            or (number, request_id) in lines
        ):
            _fail("invoice_invalid")
        lines[(number, request_id)] = _decimal(line["model_usd"], "invoice_invalid")
    return lines


def verify_secondary_sources(
    raw_schedule: Any,
    raw_receipts: Any,
    raw_assembly: Any,
    raw_secondary: Any,
    blobs_dir: str | Path,
) -> dict[str, Any]:
    """Check source bytes and exact model charges without assessing criterion 4."""
    raw_schedule, raw_receipts, raw_assembly, raw_secondary = copy.deepcopy(
        (raw_schedule, raw_receipts, raw_assembly, raw_secondary)
    )
    schedule, _, _ = _validate_schedule(raw_schedule)
    receipt_audit = audit_receipts(schedule, raw_receipts)
    if receipt_audit["violations"]:
        _fail("receipt_audit_violations")
    assembly, _, _ = _validate_assembly(
        raw_assembly, schedule, raw_receipts, receipt_audit
    )
    measured = _validate_secondary(
        raw_secondary, schedule, receipt_audit, _canonical_digest(assembly)
    )
    expected = {raw_secondary["rate_card_sha256"]}
    parse = {raw_secondary["rate_card_sha256"]}
    counts = {
        "reference": 0,
        "audit": 0,
        "injection": 0,
        "human": 0,
        "wall": 0,
        "invoice": 0,
    }
    used_models: set[tuple[str, str]] = set()
    for run in schedule["runs"]:
        row = measured[run["run_id"]]
        if row["status"] == "missing":
            continue
        used_models.add((run["model_id"], run["model_version"]))
        for kind, digest in (
            ("reference", row["reference_sha256"]),
            ("audit", row["audit_sha256"]),
            ("human", row["human"]["events_sha256"]),
            ("wall", row["wall"]["event_sha256"]),
            ("invoice", row["cost"]["invoice_sha256"]),
        ):
            expected.add(digest)
            counts[kind] += 1
        parse.add(row["cost"]["invoice_sha256"])
        if row["recovery"].get("status") != "missing":
            expected.add(row["recovery"]["injection_sha256"])
            counts["injection"] += 1
    blobs = _read_sources(blobs_dir, expected, parse)
    rates = _rate_card(blobs[raw_secondary["rate_card_sha256"]], used_models)
    attempts_by_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in raw_receipts["attempts"]:
        attempts_by_run[attempt["run_id"]].append(attempt)
    checked_runs = 0
    invoice_lines = 0
    for run in schedule["runs"]:
        run_id = run["run_id"]
        row = measured[run_id]
        if row["status"] == "missing":
            continue
        charges = row["cost"]
        if (
            _decimal(charges["tools_usd"], "cost_invalid") != 0
            or _decimal(charges["human_usd"], "cost_invalid") != 0
        ):
            _fail("unsupported_nonmodel_cost")
        invoice = _invoice(blobs[charges["invoice_sha256"]], run_id)
        invoice_lines += len(invoice)
        rate = rates[(run["model_id"], run["model_version"])]
        calculated: dict[tuple[int, str], Decimal] = {}
        with localcontext() as context:
            # A 256-character integer rate and a separate 255-place fractional
            # rate can coexist in one sum; leave room for token multiplication.
            context.prec = 600
            for attempt in attempts_by_run[run_id]:
                for agent in attempt["agent_usage"]:
                    for call in agent["provider_calls"]:
                        key = (attempt["attempt_number"], call["request_id"])
                        calculated[key] = (
                            (call["input_total"] - call["cached_input"]) * rate[0]
                            + call["cached_input"] * rate[1]
                            + call["output_total"] * rate[2]
                        ) / Decimal(1_000_000)
            if set(invoice) != set(calculated):
                _fail("invoice_request_set_mismatch")
            if any(invoice[key] != amount for key, amount in calculated.items()):
                _fail("invoice_line_amount_mismatch")
            model_total = sum(calculated.values(), Decimal(0))
            if (
                _decimal(charges["model_usd"], "cost_invalid") != model_total
                or _decimal(charges["total_usd"], "cost_invalid") != model_total
            ):
                _fail("declared_model_cost_mismatch")
        checked_runs += 1
    return {
        "schema": 1,
        "classification": CLASSIFICATION,
        "schedule_sha256": schedule["schedule_sha256"],
        "receipts_sha256": receipt_audit["receipts_sha256"],
        "assembly_sha256": _canonical_digest(assembly),
        "secondary_sha256": _canonical_digest(raw_secondary),
        "counts": {
            "measured_runs": checked_runs,
            "unique_blobs": len(expected),
            "source_links": counts,
            "model_invoice_lines": invoice_lines,
        },
        "verified_scope": "local_source_bytes_and_model_cost_arithmetic_only",
        "limitations": LIMITATIONS,
        "criterion_4": {
            "status": "not_assessed",
            "reason": "Local sources and supplied rates are unsealed.",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("schedule", "receipts", "assembly", "secondary"):
        parser.add_argument(name, help=f"{name} JSON path, or - for stdin")
    parser.add_argument("blobs_dir", help="private content-addressed source directory")
    args = parser.parse_args(argv)
    paths = [args.schedule, args.receipts, args.assembly, args.secondary]
    try:
        if paths.count("-") > 1:
            _fail("multiple_stdin_inputs")
        result = verify_secondary_sources(
            *(_read_json_input(path) for path in paths), args.blobs_dir
        )
    except SourceError as exc:
        result = {
            "schema": 1,
            "classification": CLASSIFICATION,
            "error": {"code": str(exc)},
            "criterion_4": {
                "status": "not_assessed",
                "reason": "Local source check failed.",
            },
        }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    except (
        AnalysisError,
        SecondaryError,
        ReceiptError,
        PreparationError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ArithmeticError,
        OverflowError,
        TypeError,
        ValueError,
        RecursionError,
    ):
        result = {
            "schema": 1,
            "classification": CLASSIFICATION,
            "error": {"code": "invalid_input"},
            "criterion_4": {
                "status": "not_assessed",
                "reason": "Local source check failed.",
            },
        }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
