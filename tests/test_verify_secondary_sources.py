"""Local source bytes and model-invoice arithmetic for secondary evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from test_analyze_secondary_metrics import _bundle, _digest, _hash, _utc  # noqa: E402
import verify_secondary_sources as source_module  # noqa: E402
from verify_secondary_sources import SourceError, verify_secondary_sources  # noqa: E402


def _blob(data: bytes, directory: Path) -> str:
    digest = hashlib.sha256(data).hexdigest()
    (directory / f"{digest}.bin").write_bytes(data)
    return digest


def _json_blob(value: Any, directory: Path) -> str:
    return _blob(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode(),
        directory,
    )


def _fixture(tmp_path: Path) -> tuple[list[dict[str, Any]], Path]:
    schedule, receipts, assembly, secondary = copy.deepcopy(_bundle())
    directory = tmp_path / "sources"
    directory.mkdir()
    solo = next(run for run in schedule["runs"] if run["agents"] == "solo")
    trio = next(run for run in schedule["runs"] if run["agents"] == "trio")
    kept = {solo["run_id"], trio["run_id"]}
    rate = {
        "schema": 1,
        "currency": "USD",
        "models": [
            {
                "model_id": model,
                "model_version": version,
                "input_uncached_usd_per_million": "1",
                "input_cached_usd_per_million": "0.5",
                "output_usd_per_million": "2",
            }
            for model, version in sorted(
                {(run["model_id"], run["model_version"]) for run in (solo, trio)}
            )
        ],
    }
    unused = next(
        run
        for run in schedule["runs"]
        if (run["model_id"], run["model_version"])
        not in {
            (selected["model_id"], selected["model_version"])
            for selected in (solo, trio)
        }
    )
    rate["models"].append(
        {
            "model_id": unused["model_id"],
            "model_version": unused["model_version"],
            "input_uncached_usd_per_million": "1",
            "input_cached_usd_per_million": "0.5",
            "output_usd_per_million": "2",
        }
    )
    secondary["rate_card_sha256"] = _json_blob(rate, directory)
    runs = {run["run_id"]: run for run in schedule["runs"]}
    for row in secondary["runs"]:
        run_id = row["run_id"]
        if run_id not in kept:
            row.clear()
            row.update(
                {"run_id": run_id, "status": "missing", "reason": "development subset"}
            )
            continue
        run = runs[run_id]
        for label, digest in (
            ("reference-" + run["case_id"], row["reference_sha256"]),
            ("audit-" + run_id, row["audit_sha256"]),
            ("injection-" + run_id, row["recovery"]["injection_sha256"]),
            ("human-" + run_id, row["human"]["events_sha256"]),
            ("wall-" + run_id, row["wall"]["event_sha256"]),
        ):
            assert _hash(label) == digest
            assert _blob(label.encode(), directory) == digest
        attempts = [
            attempt for attempt in receipts["attempts"] if attempt["run_id"] == run_id
        ]
        lines = [
            {
                "attempt_number": attempt["attempt_number"],
                "request_id": call["request_id"],
                "model_usd": "0.00019",
            }
            for attempt in attempts
            for agent in attempt["agent_usage"]
            for call in agent["provider_calls"]
        ]
        total = "0.00019" if run["agents"] == "solo" else "0.00057"
        row["cost"].update({"model_usd": total, "total_usd": total})
        row["cost"]["invoice_sha256"] = _json_blob(
            {"schema": 1, "run_id": run_id, "lines": lines}, directory
        )
    return [schedule, receipts, assembly, secondary], directory


def _first_measured(secondary: dict[str, Any]) -> dict[str, Any]:
    return next(row for row in secondary["runs"] if row["status"] == "measured")


def test_local_sources_and_model_invoice_are_recomputed(tmp_path: Path) -> None:
    inputs, directory = _fixture(tmp_path)
    result = verify_secondary_sources(*inputs, directory)
    assert result["classification"] == "development_secondary_source_check_unsealed"
    assert result["counts"]["measured_runs"] == 2
    assert result["counts"]["model_invoice_lines"] == 4
    assert result["counts"]["source_links"] == {
        "reference": 2,
        "audit": 2,
        "injection": 2,
        "human": 2,
        "wall": 2,
        "invoice": 2,
    }
    assert result["criterion_4"]["status"] == "not_assessed"
    assert "model_cost_arithmetic_only" in result["verified_scope"]


def test_rehashed_false_invoice_amount_is_rejected(tmp_path: Path) -> None:
    inputs, directory = _fixture(tmp_path)
    row = _first_measured(inputs[3])
    old = row["cost"]["invoice_sha256"]
    invoice = json.loads((directory / f"{old}.bin").read_bytes())
    invoice["lines"][0]["model_usd"] = "0.00001"
    row["cost"]["invoice_sha256"] = _json_blob(invoice, directory)
    (directory / f"{old}.bin").unlink()
    with pytest.raises(SourceError, match="invoice_line_amount_mismatch"):
        verify_secondary_sources(*inputs, directory)


def test_mutating_caller_receipts_during_blob_read_cannot_rebind_invoice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs, directory = _fixture(tmp_path)
    row = _first_measured(inputs[3])
    run_id = row["run_id"]
    old = row["cost"]["invoice_sha256"]
    invoice = json.loads((directory / f"{old}.bin").read_bytes())
    invoice["lines"][0]["request_id"] = "mutated-request-id"
    row["cost"]["invoice_sha256"] = _json_blob(invoice, directory)
    (directory / f"{old}.bin").unlink()
    original_read = source_module._read_sources

    def mutate_after_read(
        path: Path, expected: set[str], parse: set[str]
    ) -> dict[str, bytes]:
        blobs = original_read(path, expected, parse)
        attempt = next(
            item for item in inputs[1]["attempts"] if item["run_id"] == run_id
        )
        attempt["agent_usage"][0]["provider_calls"][0]["request_id"] = (
            "mutated-request-id"
        )
        return blobs

    monkeypatch.setattr(source_module, "_read_sources", mutate_after_read)
    with pytest.raises(SourceError, match="invoice_request_set_mismatch"):
        verify_secondary_sources(*inputs, directory)


def test_declared_low_cost_cannot_hide_actual_model_charge(tmp_path: Path) -> None:
    inputs, directory = _fixture(tmp_path)
    row = _first_measured(inputs[3])
    row["cost"].update({"model_usd": "0.00001", "total_usd": "0.00001"})
    with pytest.raises(SourceError, match="declared_model_cost_mismatch"):
        verify_secondary_sources(*inputs, directory)


@pytest.mark.parametrize(
    "change,code",
    [
        ("missing", "missing_blob"),
        ("tampered", "blob_digest_mismatch"),
        ("extra", "extra_blob"),
        ("symlink", "blob_file_invalid"),
    ],
)
def test_source_byte_failures_are_not_silent(
    tmp_path: Path, change: str, code: str
) -> None:
    inputs, directory = _fixture(tmp_path)
    digest = _first_measured(inputs[3])["audit_sha256"]
    path = directory / f"{digest}.bin"
    if change == "missing":
        path.unlink()
    elif change == "tampered":
        path.write_bytes(b"changed")
    elif change == "extra":
        (directory / "unexpected.bin").write_bytes(b"extra")
    else:
        path.unlink()
        path.symlink_to(tmp_path / "outside")
    with pytest.raises(SourceError, match=code):
        verify_secondary_sources(*inputs, directory)


def test_nonzero_tool_or_human_cost_is_outside_profile(tmp_path: Path) -> None:
    inputs, directory = _fixture(tmp_path)
    row = _first_measured(inputs[3])
    row["cost"].update({"tools_usd": "0.01", "total_usd": "0.01019"})
    with pytest.raises(SourceError, match="unsupported_nonmodel_cost"):
        verify_secondary_sources(*inputs, directory)


def test_external_failure_retry_requires_its_invoice_line(tmp_path: Path) -> None:
    inputs, directory = _fixture(tmp_path)
    schedule, receipts, assembly, secondary = inputs
    row = _first_measured(secondary)
    run_id = row["run_id"]
    terminal = next(
        attempt for attempt in receipts["attempts"] if attempt["run_id"] == run_id
    )
    first = copy.deepcopy(terminal)
    start = datetime.fromisoformat(terminal["started_at_utc"].replace("Z", "+00:00"))
    first.update(
        {
            "attempt_number": 1,
            "session_id": "secondary-source-retry",
            "status": "external_failure",
            "started_at_utc": _utc(start - timedelta(seconds=30)),
            "ended_at_utc": _utc(start - timedelta(seconds=20)),
            "incident_sha256": _hash("retry-incident"),
        }
    )
    first.pop("artifact_sha256")
    first["agent_usage"][0]["provider_calls"][0]["request_id"] = "retry-request"
    terminal["attempt_number"] = 2
    receipts["attempts"].insert(0, first)
    assembly["receipts_sha256"] = _digest(receipts)
    secondary["receipts_sha256"] = _digest(receipts)
    secondary["assembly_sha256"] = _digest(assembly)
    row["wall"]["released_at_utc"] = first["started_at_utc"]
    row["human"]["wait_seconds"] = 5
    with pytest.raises(SourceError, match="invoice_request_set_mismatch"):
        verify_secondary_sources(schedule, receipts, assembly, secondary, directory)

    old = row["cost"]["invoice_sha256"]
    invoice = json.loads((directory / f"{old}.bin").read_bytes())
    invoice["lines"][0]["attempt_number"] = 2
    invoice["lines"].append(
        {
            "attempt_number": 1,
            "request_id": "retry-request",
            "model_usd": "0.00019",
        }
    )
    row["cost"].update({"model_usd": "0.00038", "total_usd": "0.00038"})
    row["cost"]["invoice_sha256"] = _json_blob(invoice, directory)
    (directory / f"{old}.bin").unlink()
    assert (
        verify_secondary_sources(schedule, receipts, assembly, secondary, directory)[
            "counts"
        ]["model_invoice_lines"]
        == 5
    )


def test_cli_failure_has_fixed_code_and_no_private_run_id(tmp_path: Path) -> None:
    inputs, directory = _fixture(tmp_path)
    paths = []
    for name, value in zip(
        ("schedule", "receipts", "assembly", "secondary"), inputs, strict=True
    ):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths.append(str(path))
    command = [
        sys.executable,
        str(SCRIPTS / "verify_secondary_sources.py"),
        *paths,
        str(directory),
    ]
    positive = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    assert positive.returncode == 0
    assert json.loads(positive.stdout)["counts"]["measured_runs"] == 2
    digest = _first_measured(inputs[3])["audit_sha256"]
    (directory / f"{digest}.bin").unlink()
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["error"] == {"code": "missing_blob"}
    assert _first_measured(inputs[3])["run_id"] not in result.stdout
    assert result.stderr == ""


def test_input_reader_rejects_oversize_and_symlink_before_json_parse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.json"
    source.write_bytes(b" " * 1025)
    monkeypatch.setattr(source_module, "MAX_INPUT_BYTES", 1024)
    with pytest.raises(SourceError, match="input_too_large"):
        source_module._read_json_input(str(source))
    source.write_bytes(b"{}")
    alias = tmp_path / "alias.json"
    alias.symlink_to(source)
    with pytest.raises(SourceError, match="input_unavailable"):
        source_module._read_json_input(str(alias))
