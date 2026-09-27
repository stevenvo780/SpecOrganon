"""Byte-level checks use real fixture bytes and keep private identifiers out of reports."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import test_check_preparation_records as base  # noqa: E402


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "verify_preparation_bytes.py"
sys.path.insert(0, str(SCRIPTS))
import verify_preparation_bytes as verifier  # noqa: E402
from check_preparation_records import PreparationError  # noqa: E402


def _blob(directory: Path, data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()
    path = directory / f"{digest}.bin"
    if path.exists():
        assert path.read_bytes() == data
    else:
        path.write_bytes(data)
    return digest


def _make_prepared(
    schedule: dict[str, Any],
    tmp_path: Path,
) -> tuple[tuple[dict[str, Any], ...], Path, Path]:
    bundle = base._bundle(schedule)
    receipts, manifest, mapping, ratings = bundle[1:]
    records = tmp_path / "records"
    blobs = tmp_path / "blobs"
    records.mkdir()
    blobs.mkdir()
    _blob(blobs, verifier.TRANSFORMER_SPEC)
    attempts = {item["run_id"]: item for item in receipts["attempts"]}
    runs = {item["run_id"]: item for item in schedule["runs"]}
    artifacts = {item["opaque_id"]: item for item in manifest["artifacts"]}
    for number, link in enumerate(mapping["links"], start=1):
        run = runs[link["run_id"]]
        secret = (run["run_id"] + "|" + run["model_id"]).encode()
        terminal_artifact = b"head|" + secret + b"|tail"
        terminal_trace = f"trace-{number}|".encode()
        source = f"source-{number}|".encode()
        test = f"test-{number}|".encode()
        blind_package = b"head|[redacted]|tail" + source + test
        artifact = artifacts[link["opaque_id"]]
        attempt = attempts[link["run_id"]]
        attempt["artifact_sha256"] = link["terminal_artifact_sha256"] = _blob(
            blobs,
            terminal_artifact,
        )
        attempt["trace_sha256"] = link["terminal_trace_sha256"] = _blob(
            blobs,
            terminal_trace,
        )
        artifact["artifact_sha256"] = link["blind_package_sha256"] = _blob(
            blobs,
            blind_package,
        )
        artifact["trace_sha256"] = link["blind_trace_sha256"] = _blob(
            blobs,
            terminal_trace,
        )
        for rating in ratings["ratings"]:
            if rating["opaque_id"] == link["opaque_id"]:
                rating["artifact_sha256"] = artifact["artifact_sha256"]
                rating["trace_sha256"] = artifact["trace_sha256"]
        record = base._record(link, attempt)
        record["source_test_manifest"]["sources"][0]["sha256"] = _blob(blobs, source)
        record["source_test_manifest"]["test_outputs"][0]["sha256"] = _blob(blobs, test)
        record["selection_redaction_recipe"] = {
            "schema": 1,
            "transformer_sha256": verifier.TRANSFORMER_SHA256,
            "steps": [
                {
                    "order": 1,
                    "input_ref": "terminal_artifact",
                    "selector": "bytes[0:5]",
                    "output_ref": "blind_package",
                    "action": "include",
                    "redaction": None,
                },
                {
                    "order": 2,
                    "input_ref": "terminal_artifact",
                    "selector": f"bytes[5:{5 + len(secret)}]",
                    "output_ref": "blind_package",
                    "action": "redact",
                    "redaction": "[redacted]",
                },
                {
                    "order": 3,
                    "input_ref": "terminal_artifact",
                    "selector": f"bytes[{5 + len(secret)}:{len(terminal_artifact)}]",
                    "output_ref": "blind_package",
                    "action": "include",
                    "redaction": None,
                },
                {
                    "order": 4,
                    "input_ref": "source/input",
                    "selector": "whole input",
                    "output_ref": "blind_package",
                    "action": "include",
                    "redaction": None,
                },
                {
                    "order": 5,
                    "input_ref": "test/output",
                    "selector": "whole input",
                    "output_ref": "blind_package",
                    "action": "include",
                    "redaction": None,
                },
                {
                    "order": 6,
                    "input_ref": "terminal_trace",
                    "selector": "whole input",
                    "output_ref": "blind_trace",
                    "action": "include",
                    "redaction": None,
                },
            ],
        }
        base._write_record(records, link, record)
    mapping["receipts_sha256"] = base._digest(receipts)
    mapping["manifest_sha256"] = base._digest(manifest)
    ratings["manifest_sha256"] = base._digest(manifest)
    mapping["ratings_sha256"] = base._digest(ratings)
    return bundle, records, blobs


def _first_record(
    bundle: tuple[dict[str, Any], ...], records: Path
) -> tuple[dict[str, Any], Path]:
    link = bundle[3]["links"][0]
    path = records / f"{link['preparation_record_sha256']}.json"
    return json.loads(path.read_bytes()), path


def _rewrite_first(
    bundle: tuple[dict[str, Any], ...],
    records: Path,
    record: dict[str, Any],
    path: Path,
) -> None:
    path.unlink()
    base._write_record(records, bundle[3]["links"][0], record)


def _error(
    bundle: tuple[dict[str, Any], ...],
    records: Path,
    blobs: Path,
) -> str:
    with pytest.raises(PreparationError) as caught:
        verifier.verify_preparation_bytes(*bundle, records, blobs)
    return caught.value.code


@pytest.fixture
def prepared(
    tmp_path: Path,
) -> tuple[tuple[dict[str, Any], ...], Path, Path]:
    return _make_prepared(base.schedule.__wrapped__(), tmp_path)


def test_valid_bytes_and_private_cli_report(
    prepared: tuple[tuple[dict[str, Any], ...], Path, Path],
    tmp_path: Path,
) -> None:
    bundle, records, blobs = prepared
    report = verifier.verify_preparation_bytes(*bundle, records, blobs)
    assert report["counts"] == {
        "mapped_links": 2,
        "records_verified": 2,
        "blobs_verified": 11,
        "recipes_replayed": 2,
        "short_identifiers_not_scanned": 0,
    }
    assert report["criterion_4"] == {"status": "not_assessed"}
    assert "content-blinding review remain unverified" in " ".join(
        report["limitations"]
    )
    paths = []
    for name, document in zip(
        ("schedule", "receipts", "manifest", "mapping", "ratings"),
        bundle,
        strict=True,
    ):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths.append(str(path))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *paths, str(records), str(blobs)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout)["counts"]["blobs_verified"] == 11
    for link in bundle[3]["links"]:
        assert link["run_id"] not in result.stdout
        assert link["opaque_id"] not in result.stdout
    assert str(records) not in result.stdout
    assert str(blobs) not in result.stdout


def test_short_model_version_does_not_reject_valid_blind_bytes(tmp_path: Path) -> None:
    source = base.schedule.__wrapped__()
    for model in source["models"]:
        model["version"] = "1"
    schedule = base.compile_schedule(
        {
            "schema": 1,
            "seed": source["seed"],
            "protocol_sha256": source["protocol_sha256"],
            "tool_call_cap": source["per_run_limits"]["tool_calls"],
            "models": source["models"],
            "cases": source["cases"],
            "inputs": source["inputs"],
        }
    )
    bundle, records, blobs = _make_prepared(schedule, tmp_path)
    assert (
        b"1"
        in (blobs / f"{bundle[3]['links'][0]['blind_trace_sha256']}.bin").read_bytes()
    )
    report = verifier.verify_preparation_bytes(*bundle, records, blobs)
    assert report["counts"]["short_identifiers_not_scanned"] == 1
    assert report["criterion_4"] == {"status": "not_assessed"}


def test_cli_failure_uses_fixed_code_without_private_values(
    prepared: tuple[tuple[dict[str, Any], ...], Path, Path],
    tmp_path: Path,
) -> None:
    bundle, records, blobs = prepared
    digest = bundle[3]["links"][0]["terminal_artifact_sha256"]
    (blobs / f"{digest}.bin").write_bytes(b"changed")
    paths = []
    for name, document in zip(
        ("schedule", "receipts", "manifest", "mapping", "ratings"),
        bundle,
        strict=True,
    ):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths.append(str(path))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *paths, str(records), str(blobs)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 2
    assert result.stderr == ""
    assert json.loads(result.stdout)["error"] == {"code": "blob_digest_mismatch"}
    assert bundle[3]["links"][0]["run_id"] not in result.stdout
    assert bundle[3]["links"][0]["opaque_id"] not in result.stdout
    assert str(blobs) not in result.stdout


@pytest.mark.parametrize("change", ["changed", "swapped"])
def test_changed_or_swapped_blob_bytes_fail(
    prepared: tuple[tuple[dict[str, Any], ...], Path, Path],
    change: str,
) -> None:
    bundle, records, blobs = prepared
    left, right = bundle[3]["links"]
    left_path = blobs / f"{left['terminal_artifact_sha256']}.bin"
    if change == "changed":
        left_path.write_bytes(left_path.read_bytes() + b"!")
    else:
        right_path = blobs / f"{right['terminal_artifact_sha256']}.bin"
        left_bytes, right_bytes = left_path.read_bytes(), right_path.read_bytes()
        left_path.write_bytes(right_bytes)
        right_path.write_bytes(left_bytes)
    assert _error(bundle, records, blobs) == "blob_digest_mismatch"


@pytest.mark.parametrize("kind", ["sources", "test_outputs"])
def test_missing_source_or_test_blob_fails(
    prepared: tuple[tuple[dict[str, Any], ...], Path, Path],
    kind: str,
) -> None:
    bundle, records, blobs = prepared
    record, _ = _first_record(bundle, records)
    digest = record["source_test_manifest"][kind][0]["sha256"]
    (blobs / f"{digest}.bin").unlink()
    assert _error(bundle, records, blobs) == "missing_blob"


@pytest.mark.parametrize("kind", ["sources", "test_outputs"])
def test_every_source_and_test_must_contribute_included_bytes(
    prepared: tuple[tuple[dict[str, Any], ...], Path, Path],
    kind: str,
) -> None:
    bundle, records, blobs = prepared
    record, path = _first_record(bundle, records)
    ref = record["source_test_manifest"][kind][0]["ref"]
    step = next(
        item
        for item in record["selection_redaction_recipe"]["steps"]
        if item["input_ref"] == ref
    )
    step["action"] = "redact"
    step["redaction"] = "[removed]"
    _rewrite_first(bundle, records, record, path)
    assert _error(bundle, records, blobs) == "source_test_not_included"


@pytest.mark.parametrize(
    "selector",
    [
        "all",
        "bytes[0:999999999]",
        "bytes[2:1]",
        "bytes[00:1]",
        "bytes[1:1]",
    ],
)
def test_only_canonical_bounded_nonempty_selectors_run(
    prepared: tuple[tuple[dict[str, Any], ...], Path, Path],
    selector: str,
) -> None:
    bundle, records, blobs = prepared
    record, path = _first_record(bundle, records)
    record["selection_redaction_recipe"]["steps"][0]["selector"] = selector
    _rewrite_first(bundle, records, record, path)
    assert _error(bundle, records, blobs) == "unsupported_selector"


def test_wrong_transformer_declaration_or_blob_fails(
    prepared: tuple[tuple[dict[str, Any], ...], Path, Path],
) -> None:
    bundle, records, blobs = prepared
    record, path = _first_record(bundle, records)
    record["selection_redaction_recipe"]["transformer_sha256"] = "0" * 64
    _rewrite_first(bundle, records, record, path)
    assert _error(bundle, records, blobs) == "unsupported_transformer"
    record["selection_redaction_recipe"]["transformer_sha256"] = (
        verifier.TRANSFORMER_SHA256
    )
    new_path = records / f"{bundle[3]['links'][0]['preparation_record_sha256']}.json"
    _rewrite_first(bundle, records, record, new_path)
    transformer_path = blobs / f"{verifier.TRANSFORMER_SHA256}.bin"
    transformer_path.write_bytes(b"other transformer\n")
    assert _error(bundle, records, blobs) == "blob_digest_mismatch"


def _replace_first_package(
    bundle: tuple[dict[str, Any], ...],
    records: Path,
    blobs: Path,
    data: bytes,
    record: dict[str, Any],
    path: Path,
) -> None:
    link = bundle[3]["links"][0]
    old_digest = link["blind_package_sha256"]
    old_blob = blobs / f"{old_digest}.bin"
    old_blob.unlink()
    digest = _blob(blobs, data)
    link["blind_package_sha256"] = record["blind_package_sha256"] = digest
    for artifact in bundle[2]["artifacts"]:
        if artifact["opaque_id"] == link["opaque_id"]:
            artifact["artifact_sha256"] = digest
    for rating in bundle[4]["ratings"]:
        if rating["opaque_id"] == link["opaque_id"]:
            rating["artifact_sha256"] = digest
    bundle[3]["manifest_sha256"] = base._digest(bundle[2])
    bundle[4]["manifest_sha256"] = base._digest(bundle[2])
    bundle[3]["ratings_sha256"] = base._digest(bundle[4])
    _rewrite_first(bundle, records, record, path)


def test_replayed_package_must_match_authenticated_blob(
    prepared: tuple[tuple[dict[str, Any], ...], Path, Path],
) -> None:
    bundle, records, blobs = prepared
    record, path = _first_record(bundle, records)
    original = (blobs / f"{record['blind_package_sha256']}.bin").read_bytes()
    _replace_first_package(bundle, records, blobs, original + b"forged", record, path)
    assert _error(bundle, records, blobs) == "blind_output_mismatch"


@pytest.mark.parametrize("identifier", ["run_id", "model_id"])
def test_direct_identifier_leak_fails_even_when_replay_matches(
    prepared: tuple[tuple[dict[str, Any], ...], Path, Path],
    identifier: str,
) -> None:
    bundle, records, blobs = prepared
    record, path = _first_record(bundle, records)
    artifact = (blobs / f"{record['terminal_artifact_sha256']}.bin").read_bytes()
    run_id, model_id = artifact[5:-5].split(b"|", 1)
    if identifier == "run_id":
        start, token = 5, run_id
    else:
        start, token = 6 + len(run_id), model_id
    original = (blobs / f"{record['blind_package_sha256']}.bin").read_bytes()
    steps = record["selection_redaction_recipe"]["steps"]
    steps.append(
        {
            "order": len(steps) + 1,
            "input_ref": "terminal_artifact",
            "selector": f"bytes[{start}:{start + len(token)}]",
            "output_ref": "blind_package",
            "action": "include",
            "redaction": None,
        }
    )
    _replace_first_package(bundle, records, blobs, original + token, record, path)
    assert _error(bundle, records, blobs) == "blind_identifier_leak"


@pytest.mark.parametrize("identifier", ["run_id", "model_version"])
def test_direct_identifier_leak_in_blind_trace_fails(
    prepared: tuple[tuple[dict[str, Any], ...], Path, Path],
    identifier: str,
) -> None:
    bundle, records, blobs = prepared
    record, path = _first_record(bundle, records)
    artifact = (blobs / f"{record['terminal_artifact_sha256']}.bin").read_bytes()
    run_id = artifact[5:-5].split(b"|", 1)[0]
    original_trace = (blobs / f"{record['blind_trace_sha256']}.bin").read_bytes()
    steps = record["selection_redaction_recipe"]["steps"]
    if identifier == "run_id":
        token = run_id
        steps.append(
            {
                "order": len(steps) + 1,
                "input_ref": "terminal_artifact",
                "selector": f"bytes[5:{5 + len(token)}]",
                "output_ref": "blind_trace",
                "action": "include",
                "redaction": None,
            }
        )
    else:
        run = next(
            item for item in bundle[0]["runs"] if item["run_id"] == record["run_id"]
        )
        token = run["model_version"].encode()
        steps.append(
            {
                "order": len(steps) + 1,
                "input_ref": "terminal_trace",
                "selector": "whole input",
                "output_ref": "blind_trace",
                "action": "redact",
                "redaction": run["model_version"],
            }
        )
    digest = _blob(blobs, original_trace + token)
    link = bundle[3]["links"][0]
    link["blind_trace_sha256"] = record["blind_trace_sha256"] = digest
    for artifact_row in bundle[2]["artifacts"]:
        if artifact_row["opaque_id"] == link["opaque_id"]:
            artifact_row["trace_sha256"] = digest
    for rating in bundle[4]["ratings"]:
        if rating["opaque_id"] == link["opaque_id"]:
            rating["trace_sha256"] = digest
    bundle[3]["manifest_sha256"] = base._digest(bundle[2])
    bundle[4]["manifest_sha256"] = base._digest(bundle[2])
    bundle[3]["ratings_sha256"] = base._digest(bundle[4])
    _rewrite_first(bundle, records, record, path)
    assert _error(bundle, records, blobs) == "blind_identifier_leak"


@pytest.mark.parametrize(
    "limit,expected",
    [
        ("MAX_RECORD_COUNT", "too_many_records"),
        ("MAX_RECORD_TOTAL_BYTES", "records_too_large"),
        ("MAX_BLOB_COUNT", "too_many_blobs"),
        ("MAX_BLOB_TOTAL_BYTES", "blobs_too_large"),
        ("MAX_REPLAY_TOTAL_BYTES", "replayed_outputs_too_large"),
    ],
)
def test_resource_caps_return_fixed_errors(
    prepared: tuple[tuple[dict[str, Any], ...], Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    limit: str,
    expected: str,
) -> None:
    bundle, records, blobs = prepared
    monkeypatch.setattr(verifier, limit, 1)
    assert _error(bundle, records, blobs) == expected


@pytest.mark.parametrize("hazard", ["symlink", "fifo", "hardlink", "extra"])
def test_blob_directory_rejects_unsafe_entries(
    prepared: tuple[tuple[dict[str, Any], ...], Path, Path],
    tmp_path: Path,
    hazard: str,
) -> None:
    bundle, records, blobs = prepared
    if hazard == "extra":
        (blobs / "extra.bin").write_bytes(b"unreferenced")
        assert _error(bundle, records, blobs) == "extra_blob"
        return
    record, _ = _first_record(bundle, records)
    digest = record["source_test_manifest"]["sources"][0]["sha256"]
    path = blobs / f"{digest}.bin"
    data = path.read_bytes()
    path.unlink()
    if hazard == "fifo":
        os.mkfifo(path)
    else:
        target = tmp_path / "external.bin"
        target.write_bytes(data)
        if hazard == "symlink":
            path.symlink_to(target)
        else:
            os.link(target, path)
    assert _error(bundle, records, blobs) == "blob_file_invalid"


def test_record_hardlink_and_between_pass_change_fail(
    prepared: tuple[tuple[dict[str, Any], ...], Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, records, blobs = prepared
    _, path = _first_record(bundle, records)
    other = tmp_path / "linked.json"
    os.link(path, other)
    assert _error(bundle, records, blobs) == "record_file_invalid"
    other.unlink()
    original = verifier.verify_preparation_records

    def change_after_structural_pass(*args: Any) -> dict[str, Any]:
        report = original(*args)
        path.write_bytes(path.read_bytes() + b" ")
        return report

    monkeypatch.setattr(
        verifier, "verify_preparation_records", change_after_structural_pass
    )
    assert _error(bundle, records, blobs) == "record_digest_mismatch"


def test_bounded_file_read_accepts_exact_limit_and_detects_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "read-boundary"
    directory.mkdir()
    path = directory / "payload.bin"
    path.write_bytes(b"abcde")
    directory_fd = verifier._directory(directory, "directory_unavailable")
    try:

        def read(maximum: int) -> bytes:
            return verifier._read_file(
                directory_fd,
                path.name,
                maximum,
                "file_invalid",
                "file_too_large",
                "file_changed",
            )

        assert read(5) == b"abcde"
        with pytest.raises(PreparationError, match="file_too_large"):
            read(4)
        actual_stat = os.stat
        changed = False

        def change_on_final_stat(*args: Any, **kwargs: Any) -> os.stat_result:
            nonlocal changed
            if args[0] == path.name and not changed:
                changed = True
                path.write_bytes(b"fghij")
            return actual_stat(*args, **kwargs)

        with monkeypatch.context() as patcher:
            patcher.setattr(verifier.os, "stat", change_on_final_stat)
            with pytest.raises(PreparationError, match="file_changed"):
                read(5)
        assert changed
    finally:
        os.close(directory_fd)
