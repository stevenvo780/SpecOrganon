"""Audit an incremental, declared journal of physical lots and wet-mass flows.

This audit checks supplied declarations. It does not observe operations, open
source records, authenticate physical identities, or establish field coverage.
Known transfers retain their complete declared load definition. No experimental
arms, assignment, pre/post periods or terminal outcomes are invented.

Masses and uncertainties use the bounded numeric parser from field_flows and
exact rational kg arithmetic. Transfers may change equivalent kg/g/t notation;
their physical quantity, uncertainty, kind, material, basis and dry fraction
must agree. Event times cannot decrease. Source observation times are checked
as UTC declarations without inventing a relation to the event timestamp.
Evaporation declares release outside this journal and is terminal. Captured
water that will be reused is a product load with material water and a zero
dry fraction, rather than an evaporation loss.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

from . import field_flows
from .ledger import strict_json_loads

INPUT_KINDS = frozenset(field_flows.INPUT_KINDS)
OUTPUT_KINDS = frozenset(field_flows.OUTPUT_KINDS | {"evaporation"})
WATER_KINDS = frozenset({"water_addition", "moisture", "evaporation"})
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MAX_EVENTS = 2048
MAX_LOADS_PER_SIDE = 128
MAX_INPUT_BYTES = 1_048_576
CLASSIFICATION = "lot_journal_audit_declared_only"


class LotJournalError(ValueError):
    """The declared journal is malformed or internally inconsistent."""


def _object(value: Any, label: str, fields: set[str]) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise LotJournalError(f"{label} must have exactly {sorted(fields)}")
    return value


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > 4096:
        raise LotJournalError(f"{label} must be bounded nonempty trimmed text")
    return value


def _array(value: Any, label: str, maximum: int) -> list:
    if type(value) is not list or not 0 < len(value) <= maximum:
        raise LotJournalError(f"{label} must be a nonempty bounded array")
    return value


def _source(value: Any, label: str) -> dict:
    source = _object(value, label, {
        "source_id", "locator", "observed_at_utc", "method", "record_sha256",
    })
    for key in ("source_id", "locator", "method"):
        _text(source[key], f"{label}.{key}")
    field_flows._utc(source["observed_at_utc"], f"{label}.observed_at_utc")
    if type(source["record_sha256"]) is not str or not SHA256.fullmatch(source["record_sha256"]):
        raise LotJournalError(f"{label}.record_sha256 must be a lowercase SHA-256 pointer")
    return source


def _load(value: Any, label: str) -> dict:
    load = _object(value, label, {
        "load_id", "material_id", "kind", "mass", "basis", "dry_fraction",
    })
    for key in ("load_id", "material_id"):
        _text(load[key], f"{label}.{key}")
    if type(load["kind"]) is not str or load["kind"] not in INPUT_KINDS | OUTPUT_KINDS:
        raise LotJournalError(f"{label}.kind is unsupported")
    if load["basis"] != "wet" or type(load["basis"]) is not str:
        raise LotJournalError(f"{label}.basis must be wet; no implicit dry conversion")
    mass, uncertainty = field_flows._mass(load["mass"], f"{label}.mass")
    fraction = load["dry_fraction"]
    if fraction is not None:
        number = field_flows._number(fraction, f"{label}.dry_fraction")
        if number > 1:
            raise LotJournalError(f"{label}.dry_fraction must be between zero and one")
        fraction = Fraction(number)
    if load["kind"] in WATER_KINDS and fraction != 0:
        raise LotJournalError(f"{label} water or evaporation requires dry_fraction zero")
    return {
        "load_id": load["load_id"], "material_id": load["material_id"],
        "kind": load["kind"], "mass": mass, "uncertainty": uncertainty,
        "basis": "wet", "dry_fraction": fraction,
    }


def _balance(inputs: list[dict], outputs: list[dict], tolerance: Fraction, *, dry: bool) -> dict:
    if dry and any(load["dry_fraction"] is None for load in inputs + outputs):
        return {"status": "pending_missing_dry_fraction"}

    def amount(load: dict, key: str) -> Fraction:
        coefficient = load["dry_fraction"] if dry else Fraction(1)
        return load[key] * coefficient

    input_mass = sum((amount(load, "mass") for load in inputs), Fraction(0))
    output_mass = sum((amount(load, "mass") for load in outputs), Fraction(0))
    allowance = tolerance + sum((amount(load, "uncertainty") for load in inputs + outputs), Fraction(0))
    residual = input_mass - output_mass
    if abs(residual) > allowance:
        basis = "dry" if dry else "wet"
        raise LotJournalError(f"{basis} mass balance exceeds uncertainty and tolerance")
    return {
        "status": "balanced", "input_kg": field_flows._exact_decimal(input_mass),
        "output_kg": field_flows._exact_decimal(output_mass),
        "residual_kg": field_flows._exact_decimal(residual),
        "allowance_kg": field_flows._exact_decimal(allowance),
    }


def audit_lot_journal(data: dict) -> dict:
    """Return exact declared balances; a valid journal remains unready for field execution."""
    try:
        return _audit(data)
    except field_flows.FieldFlowError as exc:
        raise LotJournalError(str(exc)) from exc


def _audit(data: dict) -> dict:
    root = _object(data, "journal", {"schema", "classification", "journal_id", "events"})
    if type(root["schema"]) is not int or root["schema"] != 1:
        raise LotJournalError("journal schema must be integer one")
    if type(root["classification"]) is not str or root["classification"] != "lot_journal_declared_only":
        raise LotJournalError("journal classification must be lot_journal_declared_only")
    journal_id = _text(root["journal_id"], "journal_id")
    events = _array(root["events"], "events", MAX_EVENTS)
    event_ids: set[str] = set()
    definitions: dict[str, dict] = {}
    consumed: set[str] = set()
    available: set[str] = set()
    previous_at = None
    balances = []
    external_inputs = transfers = 0
    for index, raw in enumerate(events):
        label = f"events[{index}]"
        event = _object(raw, label, {
            "id", "stage", "stage_role", "actor", "at_utc", "inputs", "outputs",
            "balance_tolerance_kg", "source",
        })
        event_id = _text(event["id"], f"{label}.id")
        if event_id in event_ids:
            raise LotJournalError("duplicate event id")
        event_ids.add(event_id)
        for key in ("stage", "actor"):
            _text(event[key], f"{label}.{key}")
        if type(event["stage_role"]) is not str or event["stage_role"] not in field_flows.STAGE_ROLES:
            raise LotJournalError(f"{label}.stage_role is unsupported")
        at = field_flows._utc(event["at_utc"], f"{label}.at_utc")
        if previous_at is not None and at < previous_at:
            raise LotJournalError("event timestamps decrease")
        previous_at = at
        _source(event["source"], f"{label}.source")
        tolerance = Fraction(field_flows._number(event["balance_tolerance_kg"], f"{label}.balance_tolerance_kg"))
        inputs = [_load(load, f"{label}.inputs[{i}]") for i, load in enumerate(
            _array(event["inputs"], f"{label}.inputs", MAX_LOADS_PER_SIDE))]
        outputs = [_load(load, f"{label}.outputs[{i}]") for i, load in enumerate(
            _array(event["outputs"], f"{label}.outputs", MAX_LOADS_PER_SIDE))]
        for load in inputs:
            id = load["load_id"]
            if id in consumed:
                raise LotJournalError(f"physical load consumed more than once: {id}")
            if id in definitions:
                if definitions[id]["kind"] == "evaporation":
                    raise LotJournalError(f"terminal evaporation load cannot be consumed: {id}")
                if id not in available or load != definitions[id]:
                    raise LotJournalError(f"transferred load definition differs: {id}")
                available.remove(id)
                transfers += 1
            else:
                if load["kind"] not in INPUT_KINDS:
                    raise LotJournalError("unknown external input must be feed, ingredient or water_addition")
                definitions[id] = load
                external_inputs += 1
            consumed.add(id)
        for load in outputs:
            id = load["load_id"]
            if id in definitions:
                raise LotJournalError(f"output physical load id already exists: {id}")
            if load["kind"] not in OUTPUT_KINDS:
                raise LotJournalError("output must be product, coproduct, residue, moisture or evaporation")
            definitions[id] = load
            available.add(id)
        balances.append({"event_id": event_id,
                         "wet": _balance(inputs, outputs, tolerance, dry=False),
                         "dry": _balance(inputs, outputs, tolerance, dry=True)})
    pending_dry = [row["event_id"] for row in balances if row["dry"]["status"] != "balanced"]
    return {
        "schema": 1, "classification": CLASSIFICATION, "journal_id": journal_id,
        "valid": True, "counts": {"events": len(events), "loads": len(definitions),
                                 "external_inputs": external_inputs, "transfers": transfers},
        "balances": balances, "unconsumed_output_load_ids": sorted(available),
        "terminal_output_load_ids": sorted(id for id in available if definitions[id]["kind"] == "evaporation"),
        "capture_status": "incremental_declared_events_only",
        "pending": {"capture_completeness": "not_established", "dry_balance_event_ids": pending_dry},
        "observations_authenticated": False, "field_scope_complete": False, "execution_ready": False,
        "criterion_3": {"status": "not_assessed"},
        "notice": "Declared balances only. Source hashes are pointers; source bytes, physical identity, "
                  "dry fractions, calibration and capture completeness are not authenticated. "
                  "Dry uncertainty uses declared fractions as exact coefficients.",
    }


def _read_bounded(name: str) -> bytes:
    if name == "-":
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    else:
        path = Path(name)
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise LotJournalError("journal input has a symlink component")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise LotJournalError("journal input must be a regular file")
            raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise LotJournalError("journal input exceeds byte limit")
    return raw


def read_journal(path: Path | str) -> dict:
    """Read bounded UTF-8 JSON with the same precision boundary as CLI/MCP.

    ``-`` reads stdin. This reader requires an object; journal schema and flow
    checks belong to audit_lot_journal. The pure Python auditor can also accept
    Decimal values supplied directly, without silently rounding them.
    """
    try:
        data = strict_json_loads(_read_bounded(os.fspath(path)).decode("utf-8"))
    except (ValueError, RecursionError, OSError, UnicodeError) as exc:
        raise LotJournalError(str(exc)) from exc
    if type(data) is not dict:
        raise LotJournalError("journal JSON must be an object")
    return data


def main(argv: list[str] | None = None) -> int:
    """Read one bounded strict JSON journal from a file or stdin; write only stdout."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("journal", help="schema-1 lot journal JSON path, or - for stdin")
    args = parser.parse_args(argv)
    try:
        data = read_journal(args.journal)
        result = audit_lot_journal(data)
    except (ValueError, RecursionError, OSError, UnicodeError) as exc:
        result = {"schema": 1, "classification": CLASSIFICATION, "valid": False,
                  "error": str(exc), "observations_authenticated": False,
                  "field_scope_complete": False, "execution_ready": False,
                  "criterion_3": {"status": "not_assessed"}}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0
