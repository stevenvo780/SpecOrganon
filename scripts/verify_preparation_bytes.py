"""Privately rehash preparation blobs and replay one fixed byte profile.

Usage: ``python scripts/verify_preparation_bytes.py schedule.json receipts.json
manifest.json private_mapping.json ratings.json records_dir blobs_dir``.

This is a deliberately narrow extension of preparation-record schema 1. The
only supported replay profile is the exact, non-executable UTF-8 blob in
TRANSFORMER_SPEC; its SHA-256 does not authenticate the original program.
Selectors are exactly ``whole input`` or canonical, nonempty half-open
``bytes[N:M]`` spans. Every selected span must contain at least one byte. A
nonempty included span from each listed source/test is required, but it can be
only a small part of that blob. An ``include`` step copies that span; a
``redact`` step replaces it with the
literal UTF-8 bytes of ``redaction``. Chunks are joined in recipe order for
each output. The acta checker accepts other declared transformer recipes, but
they are outside this verifiable subset. No private paths, identifiers, or
mapping rows are emitted in the public response.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
from collections import deque
from pathlib import Path
from typing import Any

from check_preparation_records import (
    MAX_RECORD_BYTES,
    PreparationError,
    _json_bytes,
    _read_input,
    verify_preparation_records,
)


CLASSIFICATION = "development_preparation_byte_check_unsealed"
TRANSFORMER_SPEC = b'{"algorithm":"ordered-byte-spans-v1","schema":1}\n'
TRANSFORMER_SHA256 = hashlib.sha256(TRANSFORMER_SPEC).hexdigest()
SPAN = re.compile(r"bytes\[(0|[1-9][0-9]{0,8}):(0|[1-9][0-9]{0,8})\]\Z")
MAX_BLOB_BYTES = 64 * 1024 * 1024
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_BLOB_TOTAL_BYTES = 128 * 1024 * 1024
MAX_RECORD_TOTAL_BYTES = 32 * 1024 * 1024
# The schedule permits 432 runs; these count limits admit its full candidate panel.
MAX_RECORD_COUNT = 432
MAX_BLOB_COUNT = 4096
MAX_REPLAY_TOTAL_BYTES = 128 * 1024 * 1024
MAX_IDENTIFIER_BYTES = 4096
MAX_IDENTIFIER_PATTERN_BYTES = 64 * 1024
MIN_DIRECT_IDENTIFIER_BYTES = 8
LIMITATIONS = [
    "Only the fixed ordered-byte-spans-v1 declarative replay profile is supported.",
    "The original transformer program and its execution are not authenticated.",
    "Direct run, model, and model-version byte leakage is checked for identifiers of at least 8 UTF-8 bytes.",
    "Shorter identifiers are not scanned; arm and content-blinding review remain unverified.",
    "Nonempty included source/test spans do not establish complete source/test coverage or independent judge verifiability.",
    "Local bytes and declarations do not establish external custody, independent creation, or execution history.",
    "Claimed rating-lock timestamps and physical preparation order are not externally authenticated.",
    "A forged acta, mapping, and matching blobs can pass this local unsealed check.",
    "Caller-supplied private paths and ownership are not independently authenticated.",
    "Concurrent changes after the final read can escape this local snapshot; criterion 4 is not assessed.",
]


def _fail(code: str) -> None:
    raise PreparationError(code)


def _directory(path: str | Path, code: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            _fail(code)
        return descriptor
    except OSError as exc:
        raise PreparationError(code) from exc


def _names(descriptor: int, code: str) -> set[str]:
    try:
        return set(os.listdir(descriptor))
    except OSError as exc:
        raise PreparationError(code) from exc


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _read_file(
    directory_fd: int,
    filename: str,
    maximum: int,
    invalid: str,
    too_large: str,
    changed: str,
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        file_fd = os.open(filename, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise PreparationError(invalid) from exc
    try:
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            _fail(invalid)
        if before.st_size > maximum:
            _fail(too_large)
        with os.fdopen(file_fd, "rb", closefd=False) as stream:
            data = stream.read(maximum + 1)
        after = os.fstat(file_fd)
        entry = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
        if _identity(before) != _identity(after) or _identity(after) != _identity(
            entry
        ):
            _fail(changed)
        if len(data) != before.st_size:
            _fail(changed)
        if len(data) > maximum:
            _fail(too_large)
        return data
    except OSError as exc:
        raise PreparationError(changed) from exc
    finally:
        os.close(file_fd)


def _read_records(
    mapping: dict[str, Any], directory: str | Path
) -> list[dict[str, Any]]:
    links = mapping["links"]
    if len(links) > MAX_RECORD_COUNT:
        _fail("too_many_records")
    expected = {link["preparation_record_sha256"] + ".json" for link in links}
    directory_fd = _directory(directory, "record_directory_unavailable")
    try:
        available = _names(directory_fd, "record_directory_unavailable")
        if expected - available:
            _fail("missing_record")
        if available - expected:
            _fail("extra_record")
        records = []
        total_bytes = 0
        for link in links:
            digest = link["preparation_record_sha256"]
            data = _read_file(
                directory_fd,
                digest + ".json",
                MAX_RECORD_BYTES,
                "record_file_invalid",
                "record_too_large",
                "record_changed_during_read",
            )
            if hashlib.sha256(data).hexdigest() != digest:
                _fail("record_digest_mismatch")
            total_bytes += len(data)
            if total_bytes > MAX_RECORD_TOTAL_BYTES:
                _fail("records_too_large")
            records.append(_json_bytes(data))
        available = _names(directory_fd, "record_directory_unavailable")
        if expected - available:
            _fail("missing_record")
        if available - expected:
            _fail("extra_record")
        return records
    finally:
        os.close(directory_fd)


def _required_hashes(records: list[dict[str, Any]]) -> set[str]:
    expected = {TRANSFORMER_SHA256}
    for record in records:
        recipe = record["selection_redaction_recipe"]
        if recipe["transformer_sha256"] != TRANSFORMER_SHA256:
            _fail("unsupported_transformer")
        expected.update(
            record[field]
            for field in (
                "terminal_artifact_sha256",
                "terminal_trace_sha256",
                "blind_package_sha256",
                "blind_trace_sha256",
            )
        )
        source_test = record["source_test_manifest"]
        expected.update(
            row["sha256"]
            for kind in ("sources", "test_outputs")
            for row in source_test[kind]
        )
    return expected


def _read_blobs(directory: str | Path, expected_hashes: set[str]) -> dict[str, bytes]:
    if len(expected_hashes) > MAX_BLOB_COUNT:
        _fail("too_many_blobs")
    expected = {digest + ".bin" for digest in expected_hashes}
    directory_fd = _directory(directory, "blob_directory_unavailable")
    try:
        available = _names(directory_fd, "blob_directory_unavailable")
        if expected - available:
            _fail("missing_blob")
        if available - expected:
            _fail("extra_blob")
        blobs = {}
        total_bytes = 0
        for digest in sorted(expected_hashes):
            data = _read_file(
                directory_fd,
                digest + ".bin",
                MAX_BLOB_BYTES,
                "blob_file_invalid",
                "blob_too_large",
                "blob_changed_during_read",
            )
            if hashlib.sha256(data).hexdigest() != digest:
                _fail("blob_digest_mismatch")
            total_bytes += len(data)
            if total_bytes > MAX_BLOB_TOTAL_BYTES:
                _fail("blobs_too_large")
            blobs[digest] = data
        available = _names(directory_fd, "blob_directory_unavailable")
        if expected - available:
            _fail("missing_blob")
        if available - expected:
            _fail("extra_blob")
        return blobs
    finally:
        os.close(directory_fd)


def _select(source: bytes, selector: str) -> bytes:
    if selector == "whole input":
        selected = source
    else:
        match = SPAN.fullmatch(selector)
        if match is None:
            _fail("unsupported_selector")
        start, end = (int(part) for part in match.groups())
        if start >= end or end > len(source):
            _fail("unsupported_selector")
        selected = source[start:end]
    if not selected:
        _fail("empty_selection")
    return selected


def _replay(record: dict[str, Any], blobs: dict[str, bytes]) -> tuple[bytes, bytes]:
    inputs = {
        "terminal_artifact": blobs[record["terminal_artifact_sha256"]],
        "terminal_trace": blobs[record["terminal_trace_sha256"]],
    }
    required_includes: dict[str, int] = {}
    for kind in ("sources", "test_outputs"):
        for item in record["source_test_manifest"][kind]:
            inputs[item["ref"]] = blobs[item["sha256"]]
            required_includes[item["ref"]] = 0
    output = {"blind_package": bytearray(), "blind_trace": bytearray()}
    for step in record["selection_redaction_recipe"]["steps"]:
        selected = _select(inputs[step["input_ref"]], step["selector"])
        if step["action"] == "include":
            chunk = selected
            if (
                step["output_ref"] == "blind_package"
                and step["input_ref"] in required_includes
            ):
                required_includes[step["input_ref"]] += len(chunk)
        else:
            chunk = step["redaction"].encode("utf-8")
        target = output[step["output_ref"]]
        if len(target) + len(chunk) > MAX_OUTPUT_BYTES:
            _fail("replayed_output_too_large")
        target.extend(chunk)
    if any(amount == 0 for amount in required_includes.values()):
        _fail("source_test_not_included")
    return bytes(output["blind_package"]), bytes(output["blind_trace"])


def _identifier_machine(
    identifiers: set[bytes],
) -> tuple[list[dict[int, int]], list[int], list[bool]]:
    """Build a bounded byte trie with failure links for a single-pass direct-ID scan."""
    if sum(map(len, identifiers)) > MAX_IDENTIFIER_PATTERN_BYTES or any(
        not item or len(item) > MAX_IDENTIFIER_BYTES for item in identifiers
    ):
        _fail("identifiers_too_large")
    edges: list[dict[int, int]] = [{}]
    failures = [0]
    terminal = [False]
    for identifier in identifiers:
        state = 0
        for byte in identifier:
            if byte not in edges[state]:
                edges[state][byte] = len(edges)
                edges.append({})
                failures.append(0)
                terminal.append(False)
            state = edges[state][byte]
        terminal[state] = True
    queue = deque(edges[0].values())
    while queue:
        state = queue.popleft()
        for byte, child in edges[state].items():
            fallback = failures[state]
            while fallback and byte not in edges[fallback]:
                fallback = failures[fallback]
            failures[child] = edges[fallback].get(byte, 0)
            terminal[child] |= terminal[failures[child]]
            queue.append(child)
    return edges, failures, terminal


def _has_identifier(
    output: bytes,
    machine: tuple[list[dict[int, int]], list[int], list[bool]],
) -> bool:
    edges, failures, terminal = machine
    state = 0
    for byte in output:
        while state and byte not in edges[state]:
            state = failures[state]
        state = edges[state].get(byte, 0)
        if terminal[state]:
            return True
    return False


def verify_preparation_bytes(
    schedule: Any,
    receipts: Any,
    manifest: Any,
    mapping: Any,
    ratings: Any,
    records_dir: str | Path,
    blobs_dir: str | Path,
) -> dict[str, Any]:
    """Verify declared actas, exact local bytes, and fixed-recipe replay."""
    # Keep one caller-data snapshot for the structural pass and all later reads.
    try:
        documents = copy.deepcopy((schedule, receipts, manifest, mapping, ratings))
    except (TypeError, ValueError, RecursionError) as exc:
        raise PreparationError("invalid_input") from exc
    schedule, receipts, manifest, mapping, ratings = documents
    base_report = verify_preparation_records(
        schedule,
        receipts,
        manifest,
        mapping,
        ratings,
        records_dir,
    )
    records = _read_records(mapping, records_dir)
    hashes = _required_hashes(records)
    blobs = _read_blobs(blobs_dir, hashes)
    if blobs[TRANSFORMER_SHA256] != TRANSFORMER_SPEC:
        _fail("transformer_bytes_mismatch")
    identifiers = {
        value.encode("utf-8")
        for run in schedule["runs"]
        for value in (run["run_id"], run["model_id"], run["model_version"])
    }
    scanned_identifiers = {
        item for item in identifiers if len(item) >= MIN_DIRECT_IDENTIFIER_BYTES
    }
    machine = _identifier_machine(scanned_identifiers)
    replayed_bytes = 0
    for record in records:
        package, trace = _replay(record, blobs)
        replayed_bytes += len(package) + len(trace)
        if replayed_bytes > MAX_REPLAY_TOTAL_BYTES:
            _fail("replayed_outputs_too_large")
        if (
            package != blobs[record["blind_package_sha256"]]
            or trace != blobs[record["blind_trace_sha256"]]
        ):
            _fail("blind_output_mismatch")
        if _has_identifier(package, machine) or _has_identifier(trace, machine):
            _fail("blind_identifier_leak")
    count = base_report["counts"]["records_verified"]
    return {
        "schema": 1,
        "classification": CLASSIFICATION,
        "counts": {
            "mapped_links": base_report["counts"]["mapped_links"],
            "records_verified": count,
            "blobs_verified": len(blobs),
            "recipes_replayed": count,
            "short_identifiers_not_scanned": len(identifiers - scanned_identifiers),
        },
        "limitations": LIMITATIONS,
        "criterion_4": {"status": "not_assessed"},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("schedule", "receipts", "manifest", "mapping", "ratings"):
        parser.add_argument(name, help=f"local {name} JSON path")
    parser.add_argument("records_dir", help="directory of private <sha256>.json actas")
    parser.add_argument("blobs_dir", help="directory of private <sha256>.bin blobs")
    args = parser.parse_args(argv)
    try:
        output = verify_preparation_bytes(
            _read_input(args.schedule),
            _read_input(args.receipts),
            _read_input(args.manifest),
            _read_input(args.mapping),
            _read_input(args.ratings),
            args.records_dir,
            args.blobs_dir,
        )
    except PreparationError as exc:
        output = {
            "schema": 1,
            "classification": CLASSIFICATION,
            "error": {"code": exc.code},
            "criterion_4": {"status": "not_assessed"},
        }
        status = 2
    except Exception:
        output = {
            "schema": 1,
            "classification": CLASSIFICATION,
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
