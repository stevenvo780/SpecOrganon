"""A local acta check binds fixed private records but cannot certify custody."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "check_preparation_records.py"
sys.path.insert(0, str(SCRIPTS))
import check_preparation_records as checker  # noqa: E402
from check_preparation_records import PreparationError, verify_preparation_records  # noqa: E402
from plan_confirmatory import compile_schedule  # noqa: E402


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _ref(label: str) -> dict[str, str]:
    return {"ref": f"synthetic/{label}", "sha256": _hash(label)}


@pytest.fixture(scope="module")
def schedule() -> dict[str, Any]:
    models = [
        {
            "family": family, "tier": tier, "model_id": f"{family}/{tier}",
            "version": "synthetic-v1", "effort_control": tier == "higher",
            "efforts": ([
                {"label": "low", "provider_value": "low"},
                {"label": "high", "provider_value": "high"},
            ] if tier == "higher" else [{"label": "default"}]),
        }
        for family in ("family-a", "family-b")
        for tier in ("lower", "higher")
    ]
    return compile_schedule({
        "schema": 1, "seed": 31, "protocol_sha256": _hash("protocol"),
        "tool_call_cap": 100, "models": models,
        "cases": [
            {"case_id": case_id, "package_sha256": _hash(case_id),
             "reference_sha256": _hash("reference-" + case_id)}
            for case_id in ("R-F", "R-M", "R-S")
        ],
        "inputs": {
            "task_contract": _ref("task"), "common_prompt": _ref("common"),
            "arm_prompts": {arm: _ref("prompt-" + arm) for arm in ("N", "S", "T")},
            "rubric": _ref("rubric"), "tool_policy": _ref("policy"),
            "sdd_guide": _ref("sdd"), "toolkit": _ref("toolkit"),
        },
    })


def _attempt(run: dict[str, Any]) -> dict[str, Any]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
        seconds=run["release_block_order"] * 100 + run["order_position"] * 10
    )
    end = start + timedelta(seconds=10)
    return {
        "run_id": run["run_id"], "run_sha256": run["run_sha256"],
        "attempt_number": 1, "session_id": f"session-{run['run_id']}",
        "status": "completed", "model_id": run["model_id"],
        "model_version": run["model_version"], "effort": run["effort"],
        "effort_provider_value": run["effort_provider_value"],
        "agents": run["agents"], "case_id": run["case_id"],
        "replica": run["replica"], "arm": run["arm"],
        "started_at_utc": start.isoformat().replace("+00:00", "Z"),
        "ended_at_utc": end.isoformat().replace("+00:00", "Z"),
        "human_wait_seconds": 2, "active_seconds": 8,
        "trace_sha256": _hash("terminal-trace-" + run["run_id"]),
        "artifact_sha256": _hash("terminal-artifact-" + run["run_id"]),
        "agent_usage": [
            {
                "agent_id": f"agent-{index}", "tool_calls": 1,
                "provider_calls": [{
                    "request_id": f"request-{run['run_id']}-{index}",
                    "input_total": 100, "cached_input": 10,
                    "output_total": 20, "reasoning_output": 5,
                }],
            }
            for index in range(1 if run["agents"] == "solo" else 3)
        ],
    }


def _bundle(schedule: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    runs = [
        next(run for run in schedule["runs"] if run["arm"] == arm and run["order_position"] == 1)
        for arm in ("S", "T")
    ]
    attempts = [_attempt(run) for run in runs]
    artifacts = [
        {
            "opaque_id": _hash("opaque-" + run["run_id"])[:32],
            "artifact_sha256": _hash("blind-package-" + run["run_id"]),
            "trace_sha256": _hash("blind-trace-" + run["run_id"]),
            "rubric_sha256": _hash("rubric"),
        }
        for run in runs
    ]
    receipts = {
        "schema": 1, "schedule_sha256": schedule["schedule_sha256"],
        "attempts": attempts,
    }
    manifest = {"schema": 1, "artifacts": artifacts}
    mapping = {
        "schema": 2, "schedule_sha256": schedule["schedule_sha256"],
        "receipts_sha256": _digest(receipts),
        "manifest_sha256": _digest(manifest),
        "ratings_sha256": _hash("locked-ratings-not-supplied-to-this-check"),
        "links": [
            {
                "opaque_id": artifact["opaque_id"],
                "run_id": run["run_id"], "run_sha256": run["run_sha256"],
                "terminal_artifact_sha256": attempt["artifact_sha256"],
                "terminal_trace_sha256": attempt["trace_sha256"],
                "blind_package_sha256": artifact["artifact_sha256"],
                "blind_trace_sha256": artifact["trace_sha256"],
                "preparation_record_sha256": "",
            }
            for run, attempt, artifact in zip(runs, attempts, artifacts, strict=True)
        ],
    }
    return schedule, receipts, manifest, mapping


def _record(link: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": 1,
        "opaque_id": link["opaque_id"],
        "run_id": link["run_id"],
        "run_sha256": link["run_sha256"],
        "prepared_at_utc": "2026-01-03T00:00:00Z",
        "terminal_attempt": {
            field: attempt[field]
            for field in (
                "attempt_number", "session_id", "status",
                "started_at_utc", "ended_at_utc",
            )
        },
        "terminal_artifact_sha256": link["terminal_artifact_sha256"],
        "terminal_trace_sha256": link["terminal_trace_sha256"],
        "blind_package_sha256": link["blind_package_sha256"],
        "blind_trace_sha256": link["blind_trace_sha256"],
        "source_test_manifest": {
            "schema": 1,
            "sources": [{"ref": "source/input", "sha256": _hash("source bytes")}],
            "test_outputs": [{"ref": "test/output", "sha256": _hash("test output bytes")}],
        },
        "selection_redaction_recipe": {
            "schema": 1, "transformer_sha256": _hash("selection tool"),
            "steps": [
                {"order": 1, "input_ref": "terminal_artifact", "selector": "all",
                 "output_ref": "blind_package", "action": "redact",
                 "redaction": "remove run, model, and arm labels"},
                {"order": 2, "input_ref": "source/input", "selector": "all",
                 "output_ref": "blind_package", "action": "include", "redaction": None},
                {"order": 3, "input_ref": "test/output", "selector": "all",
                 "output_ref": "blind_package", "action": "include", "redaction": None},
                {"order": 4, "input_ref": "terminal_trace", "selector": "all",
                 "output_ref": "blind_trace", "action": "redact",
                 "redaction": "remove run, model, and arm labels"},
            ],
        },
    }


def _write_record(directory: Path, link: dict[str, Any], record: dict[str, Any]) -> None:
    data = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(data).hexdigest()
    link["preparation_record_sha256"] = digest
    (directory / f"{digest}.json").write_bytes(data)


def _prepared(schedule: dict[str, Any], tmp_path: Path) -> tuple[tuple[dict[str, Any], ...], Path]:
    bundle = _bundle(schedule)
    receipts, mapping = bundle[1], bundle[3]
    directory = tmp_path / "records"
    directory.mkdir()
    by_run = {attempt["run_id"]: attempt for attempt in receipts["attempts"]}
    for link in mapping["links"]:
        _write_record(directory, link, _record(link, by_run[link["run_id"]]))
    return bundle, directory


def _verify(bundle: tuple[dict[str, Any], ...], directory: Path) -> dict[str, Any]:
    return verify_preparation_records(*bundle, directory)


def _error_code(bundle: tuple[dict[str, Any], ...], directory: Path) -> str:
    with pytest.raises(PreparationError) as caught:
        _verify(bundle, directory)
    return caught.value.code


def test_valid_records_and_private_cli_report(schedule: dict[str, Any], tmp_path: Path) -> None:
    bundle, directory = _prepared(schedule, tmp_path)
    report = _verify(bundle, directory)
    assert report["counts"] == {"mapped_links": 2, "records_verified": 2}
    assert report["criterion_4"]["status"] == "not_assessed"
    assert "Forged records rehashed" in " ".join(report["limitations"])

    paths = []
    for name, document in zip(("schedule", "receipts", "manifest", "mapping"), bundle, strict=True):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths.append(str(path))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *paths, str(directory)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout)["counts"]["records_verified"] == 2
    for link in bundle[3]["links"]:
        assert link["run_id"] not in result.stdout
        assert link["opaque_id"] not in result.stdout


def test_s_t_opaque_swap_with_fixed_actas_fails(schedule: dict[str, Any], tmp_path: Path) -> None:
    bundle, directory = _prepared(schedule, tmp_path)
    left, right = bundle[3]["links"]
    for field in ("opaque_id", "blind_package_sha256", "blind_trace_sha256"):
        left[field], right[field] = right[field], left[field]
    assert _error_code(bundle, directory) == "record_binding_mismatch"
    paths = []
    for name, document in zip(("schedule", "receipts", "manifest", "mapping"), bundle, strict=True):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths.append(str(path))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *paths, str(directory)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert result.stderr == ""
    assert json.loads(result.stdout)["error"] == {"code": "record_binding_mismatch"}
    for link in bundle[3]["links"]:
        assert link["run_id"] not in result.stdout
        assert link["opaque_id"] not in result.stdout


def test_duplicate_record_pointer_fails(schedule: dict[str, Any], tmp_path: Path) -> None:
    bundle, directory = _prepared(schedule, tmp_path)
    left, right = bundle[3]["links"]
    right["preparation_record_sha256"] = left["preparation_record_sha256"]
    assert _error_code(bundle, directory) == "duplicate_record_pointer"


def test_changed_byte_wrong_attempt_missing_and_extra_record(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    bundle, directory = _prepared(schedule, tmp_path)
    first = bundle[3]["links"][0]
    path = directory / (first["preparation_record_sha256"] + ".json")
    original = path.read_bytes()
    path.write_bytes(original + b" ")
    assert _error_code(bundle, directory) == "record_digest_mismatch"
    path.write_bytes(original)

    record = json.loads(original)
    record["terminal_attempt"]["attempt_number"] = 2
    path.unlink()
    _write_record(directory, first, record)
    assert _error_code(bundle, directory) == "record_binding_mismatch"

    path = directory / (first["preparation_record_sha256"] + ".json")
    path.unlink()
    assert _error_code(bundle, directory) == "missing_record"
    _write_record(directory, first, record)
    (directory / (_hash("unreferenced record") + ".json")).write_bytes(b"{}")
    assert _error_code(bundle, directory) == "extra_record"


def test_recipe_must_cover_sources_tests_and_both_outputs(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    bundle, directory = _prepared(schedule, tmp_path)
    first = bundle[3]["links"][0]
    path = directory / (first["preparation_record_sha256"] + ".json")
    record = json.loads(path.read_bytes())
    path.unlink()
    record["selection_redaction_recipe"]["steps"].pop(2)
    for number, step in enumerate(record["selection_redaction_recipe"]["steps"], start=1):
        step["order"] = number
    _write_record(directory, first, record)
    assert _error_code(bundle, directory) == "record_schema_invalid"


def test_explicit_empty_source_and_test_lists_are_valid(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    bundle, directory = _prepared(schedule, tmp_path)
    first = bundle[3]["links"][0]
    path = directory / (first["preparation_record_sha256"] + ".json")
    record = json.loads(path.read_bytes())
    path.unlink()
    record["source_test_manifest"]["sources"] = []
    record["source_test_manifest"]["test_outputs"] = []
    record["selection_redaction_recipe"]["steps"] = [
        step for step in record["selection_redaction_recipe"]["steps"]
        if step["input_ref"] in ("terminal_artifact", "terminal_trace")
    ]
    for number, step in enumerate(record["selection_redaction_recipe"]["steps"], start=1):
        step["order"] = number
    _write_record(directory, first, record)
    assert _verify(bundle, directory)["counts"]["records_verified"] == 2


def test_record_symlink_is_rejected(schedule: dict[str, Any], tmp_path: Path) -> None:
    bundle, directory = _prepared(schedule, tmp_path)
    first = bundle[3]["links"][0]
    path = directory / (first["preparation_record_sha256"] + ".json")
    target = tmp_path / "external.json"
    target.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(target)
    assert _error_code(bundle, directory) == "record_file_invalid"


def test_fifo_record_and_input_fail_without_blocking(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    bundle, directory = _prepared(schedule, tmp_path)
    paths = []
    for name, document in zip(("schedule", "receipts", "manifest", "mapping"), bundle, strict=True):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths.append(str(path))
    first = bundle[3]["links"][0]
    record_path = directory / (first["preparation_record_sha256"] + ".json")
    record_path.unlink()
    os.mkfifo(record_path)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *paths, str(directory)],
        capture_output=True, text=True, check=False, timeout=5,
    )
    assert result.returncode == 2
    assert result.stderr == ""
    assert json.loads(result.stdout)["error"] == {"code": "record_file_invalid"}

    input_fifo = tmp_path / "fifo-mapping.json"
    os.mkfifo(input_fifo)
    paths[-1] = str(input_fifo)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *paths, str(directory)],
        capture_output=True, text=True, check=False, timeout=5,
    )
    assert result.returncode == 2
    assert result.stderr == ""
    assert json.loads(result.stdout)["error"] == {"code": "input_unavailable"}


@pytest.mark.parametrize("input_ref", ["source/input", "test/output", "terminal_artifact"])
def test_recipe_input_only_in_blind_trace_fails(
    schedule: dict[str, Any], tmp_path: Path, input_ref: str,
) -> None:
    bundle, directory = _prepared(schedule, tmp_path)
    first = bundle[3]["links"][0]
    path = directory / (first["preparation_record_sha256"] + ".json")
    record = json.loads(path.read_bytes())
    path.unlink()
    step = next(
        step for step in record["selection_redaction_recipe"]["steps"]
        if step["input_ref"] == input_ref
    )
    step["output_ref"] = "blind_trace"
    _write_record(directory, first, record)
    assert _error_code(bundle, directory) == "record_schema_invalid"


@pytest.mark.parametrize("input_ref", ["source/input", "test/output"])
def test_recipe_source_or_test_may_also_feed_blind_trace(
    schedule: dict[str, Any], tmp_path: Path, input_ref: str,
) -> None:
    bundle, directory = _prepared(schedule, tmp_path)
    first = bundle[3]["links"][0]
    path = directory / (first["preparation_record_sha256"] + ".json")
    record = json.loads(path.read_bytes())
    path.unlink()
    steps = record["selection_redaction_recipe"]["steps"]
    steps.append({
        "order": len(steps) + 1,
        "input_ref": input_ref,
        "selector": "all",
        "output_ref": "blind_trace",
        "action": "include",
        "redaction": None,
    })
    _write_record(directory, first, record)
    assert _verify(bundle, directory)["counts"]["records_verified"] == 2


def test_extra_record_inserted_during_read_is_rejected(
    schedule: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, directory = _prepared(schedule, tmp_path)
    original_read = checker._read_record
    inserted = False

    def inject_extra(directory_fd: int, filename: str) -> bytes:
        nonlocal inserted
        if not inserted:
            inserted = True
            (directory / "late-extra.json").write_bytes(b"{}")
        return original_read(directory_fd, filename)

    monkeypatch.setattr(checker, "_read_record", inject_extra)
    assert _error_code(bundle, directory) == "extra_record"


def test_rehashed_forgery_can_pass_and_limit_is_explicit(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    bundle, directory = _prepared(schedule, tmp_path)
    mapping = bundle[3]
    records = {
        link["run_id"]: json.loads(
            (directory / (link["preparation_record_sha256"] + ".json")).read_bytes()
        )
        for link in mapping["links"]
    }
    for path in directory.iterdir():
        path.unlink()
    left, right = mapping["links"]
    for field in ("opaque_id", "blind_package_sha256", "blind_trace_sha256"):
        left[field], right[field] = right[field], left[field]
    for link in mapping["links"]:
        forged = records[link["run_id"]]
        for field in ("opaque_id", "blind_package_sha256", "blind_trace_sha256"):
            forged[field] = link[field]
        _write_record(directory, link, forged)
    report = _verify(bundle, directory)
    assert report["counts"]["records_verified"] == 2
    assert "Forged records rehashed together with a changed private mapping" in " ".join(
        report["limitations"]
    )
