"""Check preexisting private preparation records after blind ratings are locked.

Usage: ``python scripts/check_preparation_records.py schedule.json receipts.json
manifest.json private_mapping.json records_dir``. All inputs are local and
read-only. The directory must contain exactly one regular ``<sha256>.json``
file per schema-2 mapping link; the filename and the SHA-256 of its *raw bytes*
must equal that link's ``preparation_record_sha256``. No record is generated.

Preparation-record schema 1 has exactly these fields::

    {"schema": 1, "opaque_id": "<32 lowercase hex>", "run_id": "conf-...",
     "run_sha256": "<digest>", "prepared_at_utc": "2026-01-01T00:00:11Z",
     "terminal_attempt": {"attempt_number": 1, "session_id": "...",
       "status": "completed", "started_at_utc": "...", "ended_at_utc": "..."},
     "terminal_artifact_sha256": "<digest>",
     "terminal_trace_sha256": "<digest>",
     "blind_package_sha256": "<digest>", "blind_trace_sha256": "<digest>",
     "source_test_manifest": {"schema": 1,
       "sources": [{"ref": "source/one", "sha256": "<digest>"}],
       "test_outputs": [{"ref": "test/one", "sha256": "<digest>"}]},
     "selection_redaction_recipe": {"schema": 1,
       "transformer_sha256": "<digest>", "steps": [
         {"order": 1, "input_ref": "terminal_artifact",
          "selector": "whole input", "output_ref": "blind_package",
          "action": "include", "redaction": null}, ...]}}

The source and test-output lists may be empty but must be explicit. Recipe
steps are ordered. Every listed source and test output, plus the terminal
artifact, must feed ``blind_package``; the terminal trace must feed
``blind_trace``. The selector and
redaction strings are interpreted by the declared transformer; this checker
does not execute it. Manifest hashes, transformer bytes, terminal/blind bytes,
external custody, and timing relative to rating locks require separate audit.
Rehashing forged actas and changing the private mapping together can pass.
The public JSON response contains aggregate counts and fixed error codes only;
it never prints acta contents or a run-to-opaque mapping.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path
from typing import Any

from analyze_confirmatory import AnalysisError, _validate_schedule
from audit_blind_ratings import RatingError, _validate_manifest
from audit_run_receipts import ReceiptError, audit_receipts


CLASSIFICATION = "development_preparation_record_check_unsealed"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
OPAQUE_ID = re.compile(r"[0-9a-f]{32}\Z")
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
MAX_RECORD_BYTES = 4 * 1024 * 1024
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAPPING_FIELDS = frozenset({
    "schema", "schedule_sha256", "receipts_sha256", "manifest_sha256",
    "ratings_sha256", "links",
})
LINK_FIELDS = frozenset({
    "opaque_id", "run_id", "run_sha256", "terminal_artifact_sha256",
    "terminal_trace_sha256", "blind_package_sha256", "blind_trace_sha256",
    "preparation_record_sha256",
})
RECORD_FIELDS = frozenset({
    "schema", "opaque_id", "run_id", "run_sha256", "prepared_at_utc",
    "terminal_attempt", "terminal_artifact_sha256", "terminal_trace_sha256",
    "blind_package_sha256", "blind_trace_sha256", "source_test_manifest",
    "selection_redaction_recipe",
})
ATTEMPT_FIELDS = frozenset({
    "attempt_number", "session_id", "status", "started_at_utc", "ended_at_utc",
})
RECIPE_FIELDS = frozenset({"schema", "transformer_sha256", "steps"})
STEP_FIELDS = frozenset({
    "order", "input_ref", "selector", "output_ref", "action", "redaction",
})
LIMITATIONS = [
    "Declared source and test-output hashes and transformer bytes are not opened or authenticated.",
    "Terminal and blind artifact or trace bytes are not opened; recipe completeness, execution, and redaction correctness are not proven.",
    "The private mapping's ratings digest is syntax-checked only; rating records and locks are not opened.",
    "External custody, independent creation, release order, and preparation before rating locks are not authenticated.",
    "Forged records rehashed together with a changed private mapping can pass this local check.",
    "Concurrent changes during or after the final directory scan can escape this local snapshot.",
    "This is an unsealed development check; criterion 4 is not assessed.",
]


class PreparationError(ValueError):
    """A private preparation check failed; ``code`` is safe for public output."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise PreparationError(code)


def _object(value: Any, fields: frozenset[str], code: str) -> dict[str, Any]:
    if type(value) is not dict or value.keys() != fields:
        _fail(code)
    return value


def _digest(value: Any, code: str) -> str:
    if type(value) is not str or SHA256.fullmatch(value) is None:
        _fail(code)
    return value


def _text(value: Any, code: str, *, maximum: int = 4096) -> str:
    if (
        type(value) is not str or not value or value != value.strip()
        or len(value) > maximum or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        _fail(code)
    return value


def _utc(value: Any, code: str) -> datetime:
    if type(value) is not str or UTC.fullmatch(value) is None:
        _fail(code)
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail(code)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("invalid_json")
        result[key] = value
    return result


def _invalid_constant(_value: str) -> None:
    _fail("invalid_json")


def _json_bytes(data: bytes) -> Any:
    try:
        return json.loads(
            data.decode("utf-8"), object_pairs_hook=_unique_pairs,
            parse_constant=_invalid_constant,
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, PreparationError):
            raise
        raise PreparationError("invalid_json") from exc


def _read_input(path: str) -> Any:
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        file_fd = os.open(path, flags)
        try:
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                _fail("input_unavailable")
            with os.fdopen(file_fd, "rb", closefd=False) as stream:
                data = stream.read(MAX_INPUT_BYTES + 1)
        finally:
            os.close(file_fd)
    except OSError as exc:
        raise PreparationError("input_unavailable") from exc
    if len(data) > MAX_INPUT_BYTES:
        _fail("input_too_large")
    return _json_bytes(data)


def _validate_manifest_and_recipe(record: dict[str, Any]) -> None:
    code = "record_schema_invalid"
    source_test = _object(
        record["source_test_manifest"],
        frozenset({"schema", "sources", "test_outputs"}), code,
    )
    if type(source_test["schema"]) is not int or source_test["schema"] != 1:
        _fail(code)
    refs = {"terminal_artifact", "terminal_trace"}
    package_refs: set[str] = {"terminal_artifact"}
    for kind in ("sources", "test_outputs"):
        rows = source_test[kind]
        if type(rows) is not list:
            _fail(code)
        for value in rows:
            item = _object(value, frozenset({"ref", "sha256"}), code)
            ref = _text(item["ref"], code, maximum=256)
            _digest(item["sha256"], code)
            if ref in refs:
                _fail(code)
            refs.add(ref)
            package_refs.add(ref)
    recipe = _object(record["selection_redaction_recipe"], RECIPE_FIELDS, code)
    if type(recipe["schema"]) is not int or recipe["schema"] != 1:
        _fail(code)
    _digest(recipe["transformer_sha256"], code)
    steps = recipe["steps"]
    if type(steps) is not list or not steps:
        _fail(code)
    used_refs: set[str] = set()
    package_covered_refs: set[str] = set()
    outputs: set[str] = set()
    for index, raw_step in enumerate(steps, start=1):
        step = _object(raw_step, STEP_FIELDS, code)
        if type(step["order"]) is not int or step["order"] != index:
            _fail(code)
        input_ref = _text(step["input_ref"], code, maximum=256)
        if input_ref not in refs:
            _fail(code)
        used_refs.add(input_ref)
        _text(step["selector"], code)
        if step["output_ref"] not in ("blind_package", "blind_trace"):
            _fail(code)
        if input_ref == "terminal_trace" and step["output_ref"] != "blind_trace":
            _fail(code)
        if step["output_ref"] == "blind_package":
            package_covered_refs.add(input_ref)
        outputs.add(step["output_ref"])
        if step["action"] == "redact":
            _text(step["redaction"], code)
        elif step["action"] == "include":
            if step["redaction"] is not None:
                _fail(code)
        else:
            _fail(code)
    if (
        used_refs != refs or not package_refs <= package_covered_refs
        or outputs != {"blind_package", "blind_trace"}
    ):
        _fail(code)


def _validate_record(
    raw: Any, link: dict[str, Any], terminal: dict[str, Any],
) -> None:
    code = "record_schema_invalid"
    record = _object(raw, RECORD_FIELDS, code)
    if type(record["schema"]) is not int or record["schema"] != 1:
        _fail(code)
    if type(record["opaque_id"]) is not str or OPAQUE_ID.fullmatch(record["opaque_id"]) is None:
        _fail(code)
    _text(record["run_id"], code, maximum=256)
    for field in (
        "run_sha256", "terminal_artifact_sha256", "terminal_trace_sha256",
        "blind_package_sha256", "blind_trace_sha256",
    ):
        _digest(record[field], code)
    prepared_at = _utc(record["prepared_at_utc"], code)
    if prepared_at <= _utc(terminal["ended_at_utc"], code):
        _fail("record_chronology_mismatch")
    attempt = _object(record["terminal_attempt"], ATTEMPT_FIELDS, code)
    if type(attempt["attempt_number"]) is not int or attempt["attempt_number"] < 1:
        _fail(code)
    _text(attempt["session_id"], code, maximum=256)
    if attempt["status"] not in ("completed", "truncated"):
        _fail(code)
    _utc(attempt["started_at_utc"], code)
    _utc(attempt["ended_at_utc"], code)
    for field in ATTEMPT_FIELDS:
        if type(attempt[field]) is not type(terminal[field]) or attempt[field] != terminal[field]:
            _fail("record_binding_mismatch")
    for field in LINK_FIELDS - {"preparation_record_sha256"}:
        if record[field] != link[field]:
            _fail("record_binding_mismatch")
    _validate_manifest_and_recipe(record)


def _read_record(directory_fd: int, filename: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        file_fd = os.open(filename, flags, dir_fd=directory_fd)
        try:
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                _fail("record_file_invalid")
            with os.fdopen(file_fd, "rb", closefd=False) as stream:
                data = stream.read(MAX_RECORD_BYTES + 1)
        finally:
            os.close(file_fd)
    except OSError as exc:
        raise PreparationError("record_file_invalid") from exc
    if len(data) > MAX_RECORD_BYTES:
        _fail("record_too_large")
    return data


def _check_records(
    records_dir: Path, links: list[dict[str, Any]],
    terminals: dict[str, dict[str, Any]],
) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_fd = os.open(records_dir, flags)
    except OSError as exc:
        raise PreparationError("record_directory_unavailable") from exc
    try:
        if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
            _fail("record_directory_unavailable")
        try:
            available = set(os.listdir(directory_fd))
        except OSError as exc:
            raise PreparationError("record_directory_unavailable") from exc
        expected = {link["preparation_record_sha256"] + ".json" for link in links}
        if expected - available:
            _fail("missing_record")
        if available - expected:
            _fail("extra_record")
        for link in links:
            digest = link["preparation_record_sha256"]
            data = _read_record(directory_fd, digest + ".json")
            if hashlib.sha256(data).hexdigest() != digest:
                _fail("record_digest_mismatch")
            _validate_record(_json_bytes(data), link, terminals[link["run_id"]])
        try:
            final_available = set(os.listdir(directory_fd))
        except OSError as exc:
            raise PreparationError("record_directory_unavailable") from exc
        if expected - final_available:
            _fail("missing_record")
        if final_available - expected:
            _fail("extra_record")
    finally:
        os.close(directory_fd)


def verify_preparation_records(
    raw_schedule: Any, raw_receipts: Any, raw_manifest: Any,
    raw_mapping: Any, records_dir: str | Path,
) -> dict[str, Any]:
    """Check schema-2 declared bindings and preexisting acta bytes, read-only."""
    try:
        schedule, _, _ = _validate_schedule(raw_schedule)
    except (AnalysisError, TypeError, ValueError, OverflowError) as exc:
        raise PreparationError("invalid_schedule") from exc
    try:
        receipt_audit = audit_receipts(schedule, raw_receipts)
    except (AnalysisError, ReceiptError, TypeError, ValueError, OverflowError) as exc:
        raise PreparationError("invalid_receipts") from exc
    if receipt_audit["violations"]:
        _fail("receipt_violations")
    try:
        artifacts, manifest_digest = _validate_manifest(raw_manifest)
    except (RatingError, TypeError, ValueError, OverflowError) as exc:
        raise PreparationError("invalid_manifest") from exc
    if any(
        artifact["rubric_sha256"] != schedule["inputs"]["rubric"]["sha256"]
        for artifact in artifacts.values()
    ):
        _fail("manifest_rubric_mismatch")

    mapping = _object(raw_mapping, MAPPING_FIELDS, "invalid_mapping")
    if type(mapping["schema"]) is not int or mapping["schema"] != 2:
        _fail("invalid_mapping")
    expected_digests = {
        "schedule_sha256": schedule["schedule_sha256"],
        "receipts_sha256": receipt_audit["receipts_sha256"],
        "manifest_sha256": manifest_digest,
    }
    for field, expected in expected_digests.items():
        if _digest(mapping[field], "invalid_mapping") != expected:
            _fail("mapping_document_mismatch")
    _digest(mapping["ratings_sha256"], "invalid_mapping")
    links = mapping["links"]
    if type(links) is not list:
        _fail("invalid_mapping")
    scheduled = {run["run_id"]: run for run in schedule["runs"]}
    receipt_runs = {run["run_id"]: run for run in receipt_audit["runs"]}
    seen_opaque: set[str] = set()
    seen_runs: set[str] = set()
    seen_records: set[str] = set()
    terminals: dict[str, dict[str, Any]] = {}
    checked_links: list[dict[str, Any]] = []
    for raw_link in links:
        link = _object(raw_link, LINK_FIELDS, "invalid_mapping")
        opaque_id = link["opaque_id"]
        if type(opaque_id) is not str or OPAQUE_ID.fullmatch(opaque_id) is None:
            _fail("invalid_mapping")
        run_id = _text(link["run_id"], "invalid_mapping", maximum=256)
        if opaque_id in seen_opaque or run_id in seen_runs:
            _fail("duplicate_mapping_link")
        seen_opaque.add(opaque_id)
        seen_runs.add(run_id)
        if opaque_id not in artifacts or run_id not in scheduled:
            _fail("unknown_mapping_link")
        record_digest = _digest(link["preparation_record_sha256"], "invalid_mapping")
        if record_digest in seen_records:
            _fail("duplicate_record_pointer")
        seen_records.add(record_digest)
        if _digest(link["run_sha256"], "invalid_mapping") != scheduled[run_id]["run_sha256"]:
            _fail("link_binding_mismatch")
        receipt = receipt_runs[run_id]
        if receipt["outcome"] not in ("completed", "truncated") or not receipt["attempts"]:
            _fail("link_missing_terminal")
        terminal = receipt["attempts"][-1]
        if terminal["artifact_sha256"] is None:
            _fail("link_missing_terminal")
        bindings = {
            "terminal_artifact_sha256": terminal["artifact_sha256"],
            "terminal_trace_sha256": terminal["trace_sha256"],
            "blind_package_sha256": artifacts[opaque_id]["artifact_sha256"],
            "blind_trace_sha256": artifacts[opaque_id]["trace_sha256"],
        }
        for field, expected in bindings.items():
            if _digest(link[field], "invalid_mapping") != expected:
                _fail("link_binding_mismatch")
        terminals[run_id] = terminal
        checked_links.append(link)
    if seen_opaque != artifacts.keys():
        _fail("mapping_manifest_coverage_mismatch")
    _check_records(Path(records_dir), checked_links, terminals)
    return {
        "schema": 1,
        "classification": CLASSIFICATION,
        "counts": {"mapped_links": len(checked_links), "records_verified": len(checked_links)},
        "limitations": LIMITATIONS,
        "criterion_4": {"status": "not_assessed"},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("schedule", "receipts", "manifest", "mapping"):
        parser.add_argument(name, help=f"local {name} JSON path")
    parser.add_argument("records_dir", help="directory of preexisting <sha256>.json actas")
    args = parser.parse_args(argv)
    try:
        output = verify_preparation_records(
            _read_input(args.schedule), _read_input(args.receipts),
            _read_input(args.manifest), _read_input(args.mapping), args.records_dir,
        )
    except PreparationError as exc:
        output = {
            "schema": 1, "classification": CLASSIFICATION,
            "error": {"code": exc.code},
            "criterion_4": {"status": "not_assessed"},
        }
        status = 2
    except Exception:
        output = {
            "schema": 1, "classification": CLASSIFICATION,
            "error": {"code": "internal_error"},
            "criterion_4": {"status": "not_assessed"},
        }
        status = 2
    else:
        status = 0
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
