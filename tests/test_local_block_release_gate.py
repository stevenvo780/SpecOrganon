"""The local block registry refuses premature, duplicate, and uncertain releases."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import select
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import local_block_release_gate as gate  # noqa: E402
from plan_confirmatory import compile_schedule  # noqa: E402
from verify_released_run import COORDINATE_FIELDS, RELEASE_NOTICE  # noqa: E402


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ref(value: str) -> dict[str, str]:
    return {"ref": f"synthetic/{value}", "sha256": _sha(value)}


@pytest.fixture(scope="module")
def schedule() -> dict[str, Any]:
    models = []
    for family in ("family-a", "family-b"):
        for tier in ("lower", "higher"):
            controlled = tier == "higher"
            models.append({
                "family": family, "tier": tier, "model_id": f"{family}/{tier}",
                "version": "synthetic-v1", "effort_control": controlled,
                "efforts": ([{"label": "low", "provider_value": "low"},
                             {"label": "high", "provider_value": "high"}]
                            if controlled else [{"label": "default"}]),
            })
    return compile_schedule({
        "schema": 1, "seed": 7, "protocol_sha256": _sha("protocol"),
        "tool_call_cap": 100, "models": models,
        "cases": [{"case_id": case_id, "package_sha256": _sha(case_id),
                   "reference_sha256": _sha("reference-" + case_id)}
                  for case_id in ("R-F", "R-M", "R-S")],
        "inputs": {
            "task_contract": _ref("task"), "common_prompt": _ref("common"),
            "arm_prompts": {arm: _ref("prompt-" + arm) for arm in ("N", "S", "T")},
            "rubric": _ref("rubric"), "tool_policy": _ref("policy"),
            "sdd_guide": _ref("sdd"), "toolkit": _ref("toolkit"),
        },
    })


def _block(schedule: dict[str, Any], order: int) -> dict[int, dict[str, Any]]:
    return {run["order_position"]: run for run in schedule["runs"]
            if run["release_block_order"] == order}


def _claim(schedule: dict[str, Any], run: dict[str, Any], tmp_path: Path,
           *, label: str | None = None,
           attempt_number: int = 1) -> tuple[dict[str, Any], Path]:
    release = tmp_path / (label or (run["run_id"] if attempt_number == 1
                                    else f'{run["run_id"]}-attempt-{attempt_number}'))
    result = gate.claim_release(schedule, run["run_id"], tmp_path / "gate", release,
                                attempt_number=attempt_number)
    return result, release


def _evidence(schedule: dict[str, Any], run: dict[str, Any], release: Path,
              tmp_path: Path, *, status: str = "completed",
              trace_sha256: str | None = None, attempt_number: int = 1) -> Path:
    trace_sha256 = trace_sha256 or _sha("trace-" + run["run_id"])
    evidence = tmp_path / ("evidence-" + run["run_id"] + f"-{attempt_number}.json")
    item = {"schema": 1, "schedule_sha256": schedule["schedule_sha256"],
            "run_id": run["run_id"], "run_sha256": run["run_sha256"],
            "attempt_number": attempt_number, "release_dir": str(release),
            "status": status, "trace_sha256": trace_sha256}
    if status == "completed":
        item["artifact_sha256"] = _sha("artifact-" + run["run_id"])
    elif status == "external_failure":
        item["incident_sha256"] = _sha("incident-" + run["run_id"])
    evidence.write_text(json.dumps(item, sort_keys=True) + "\n", encoding="utf-8")
    evidence.chmod(0o600)
    return evidence


def _populate_release(schedule: dict[str, Any], run: dict[str, Any], release: Path,
                      *, attempt_number: int = 1) -> None:
    contents = {
        "case_package": run["case_id"].encode(),
        "task_contract": b"task",
        "common_prompt": b"common",
        "arm_prompt": ("prompt-" + run["arm"]).encode(),
        "tool_policy": b"policy",
    }
    if run["arm"] == "S":
        contents["sdd_guide"] = b"sdd"
    elif run["arm"] == "T":
        contents["toolkit"] = b"toolkit"
    files = {}
    for role, data in contents.items():
        path = release / role
        path.write_bytes(data)
        path.chmod(0o600)
        files[role] = {"file": role, "sha256": hashlib.sha256(data).hexdigest(),
                       "bytes": len(data)}
    manifest = {
        "schema": 1 if attempt_number == 1 else 2,
        "classification": "development_release_unsealed",
        "notice": RELEASE_NOTICE, "run_id": run["run_id"],
        "run_sha256": run["run_sha256"],
        "schedule_sha256": schedule["schedule_sha256"],
        "coordinates": {key: run[key] for key in COORDINATE_FIELDS},
        "limits": schedule["per_run_limits"], "files": files,
    }
    if attempt_number > 1:
        manifest["attempt_number"] = attempt_number
    output = release / "manifest.json"
    output.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    output.chmod(0o600)


def _publish(schedule: dict[str, Any], run: dict[str, Any], release: Path,
             tmp_path: Path, *, attempt_number: int = 1) -> dict[str, Any]:
    return gate.mark_published(schedule, run["run_id"], tmp_path / "gate", release,
                               hashlib.sha256((release / "manifest.json").read_bytes()).hexdigest(),
                               attempt_number=attempt_number)


def _terminal(schedule: dict[str, Any], run: dict[str, Any], release: Path,
              tmp_path: Path, *, status: str = "completed",
              attempt_number: int = 1) -> tuple[dict[str, Any], Path]:
    release.mkdir(mode=0o700)
    _populate_release(schedule, run, release, attempt_number=attempt_number)
    _publish(schedule, run, release, tmp_path, attempt_number=attempt_number)
    evidence = _evidence(schedule, run, release, tmp_path, status=status,
                         attempt_number=attempt_number)
    result = gate.record_terminal(schedule, run["run_id"], tmp_path / "gate",
                                  status, _sha("trace-" + run["run_id"]), evidence,
                                  attempt_number=attempt_number)
    return result, evidence


def _stop_evidence(schedule: dict[str, Any], run: dict[str, Any], release: Path,
                   terminal: dict[str, Any], tmp_path: Path, *, reason: str,
                   attempt_number: int = 1) -> Path:
    evidence = tmp_path / f'stop-{run["run_id"]}-{attempt_number}.json'
    item = {"schema": 1, "classification": gate.STOPPED_CLASSIFICATION,
            "decision": "nonretryable",
            "schedule_sha256": schedule["schedule_sha256"],
            "run_id": run["run_id"], "run_sha256": run["run_sha256"],
            "block_id": run["block_id"], "attempt_number": attempt_number,
            "release_dir": str(release),
            "terminal_sha256": terminal["terminal_sha256"],
            "incident_sha256": _sha("incident-" + run["run_id"]),
            "reason": reason}
    evidence.write_bytes(gate._canonical(item))
    evidence.chmod(0o600)
    return evidence


def test_global_first_release_and_sequential_arms_with_exact_binding(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    first, second = _block(schedule, 1), _block(schedule, 2)
    root = tmp_path / "gate"
    with pytest.raises(gate.BlockReleaseError, match="earlier block"):
        _claim(schedule, second[1], tmp_path)
    with pytest.raises(gate.BlockReleaseError, match="prior arm"):
        _claim(schedule, first[2], tmp_path)
    claim, release = _claim(schedule, first[1], tmp_path)
    assert claim["schedule_sha256"] == schedule["schedule_sha256"]
    assert claim["run_sha256"] == first[1]["run_sha256"]
    assert claim["attempt_number"] == claim["sequence"] == 1
    assert claim["release_dir"] == str(release)
    assert root.stat().st_mode & 0o777 == 0o700
    assert (root / "state.json").stat().st_mode & 0o777 == 0o600
    with pytest.raises(gate.BlockReleaseError, match="already has"):
        _claim(schedule, first[1], tmp_path, label="another-release")
    with pytest.raises(gate.BlockReleaseError, match="earlier block"):
        _claim(schedule, second[1], tmp_path)
    with pytest.raises(gate.BlockReleaseError, match="prior arm"):
        _claim(schedule, first[2], tmp_path)
    release.mkdir(mode=0o700)
    with pytest.raises(gate.BlockReleaseError, match="pending publication"):
        gate.verify_claim(schedule, first[1]["run_id"], root, release)
    _populate_release(schedule, first[1], release)
    published = _publish(schedule, first[1], release, tmp_path)
    confirmed = gate.verify_claim(schedule, first[1]["run_id"], root, release)
    assert confirmed["claim_sha256"] == claim["claim_sha256"]
    assert confirmed["publication_sha256"] == published["publication_sha256"]
    # The next block may start while the first is active, after publication.
    with pytest.raises(gate.BlockReleaseError, match="already claimed"):
        _claim(schedule, second[1], tmp_path, label=first[1]["run_id"])
    claim_second, _ = _claim(schedule, second[1], tmp_path)
    assert claim_second["sequence"] == 3
    with pytest.raises(gate.BlockReleaseError, match="differs from claim"):
        gate.verify_claim(schedule, first[1]["run_id"], root, tmp_path / "wrong")
    evidence = _evidence(schedule, first[1], release, tmp_path)
    terminal = gate.record_terminal(schedule, first[1]["run_id"], root,
                                    "completed", _sha("trace-" + first[1]["run_id"]),
                                    evidence)
    assert terminal["evidence_sha256"] == hashlib.sha256(evidence.read_bytes()).hexdigest()
    with pytest.raises(gate.BlockReleaseError, match="already has a terminal"):
        gate.verify_claim(schedule, first[1]["run_id"], root, release)
    _claim(schedule, first[2], tmp_path)


def test_terminal_mismatch_tamper_and_external_failure_stop_block(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    block = _block(schedule, 1)
    _, release = _claim(schedule, block[1], tmp_path)
    release.mkdir(mode=0o700)
    evidence = _evidence(schedule, block[1], release, tmp_path)
    with pytest.raises(gate.BlockReleaseError, match="payload cannot be verified"):
        gate.mark_published(schedule, block[1]["run_id"], tmp_path / "gate",
                            release, _sha("missing manifest"))
    with pytest.raises(gate.BlockReleaseError, match="pending publication"):
        gate.record_terminal(schedule, block[1]["run_id"], tmp_path / "gate",
                             "completed", _sha("trace-" + block[1]["run_id"]), evidence)
    _populate_release(schedule, block[1], release)
    _publish(schedule, block[1], release, tmp_path)
    absent_artifact = json.loads(evidence.read_text())
    del absent_artifact["artifact_sha256"]
    evidence.write_text(json.dumps(absent_artifact), encoding="utf-8")
    with pytest.raises(gate.BlockReleaseError, match="artifact digest"):
        gate.record_terminal(schedule, block[1]["run_id"], tmp_path / "gate",
                             "completed", _sha("trace-" + block[1]["run_id"]), evidence)
    evidence = _evidence(schedule, block[1], release, tmp_path)
    wrong = json.loads(evidence.read_text())
    wrong["trace_sha256"] = _sha("different")
    evidence.write_text(json.dumps(wrong), encoding="utf-8")
    with pytest.raises(gate.BlockReleaseError, match="trace_sha256 differs"):
        gate.record_terminal(schedule, block[1]["run_id"], tmp_path / "gate",
                             "completed", _sha("trace-" + block[1]["run_id"]), evidence)
    evidence = _evidence(schedule, block[1], release, tmp_path, status="external_failure")
    absent_incident = json.loads(evidence.read_text())
    del absent_incident["incident_sha256"]
    evidence.write_text(json.dumps(absent_incident), encoding="utf-8")
    with pytest.raises(gate.BlockReleaseError, match="incident digest"):
        gate.record_terminal(schedule, block[1]["run_id"], tmp_path / "gate",
                             "external_failure", _sha("trace-" + block[1]["run_id"]),
                             evidence)
    evidence = _evidence(schedule, block[1], release, tmp_path, status="external_failure")
    gate.record_terminal(schedule, block[1]["run_id"], tmp_path / "gate",
                         "external_failure", _sha("trace-" + block[1]["run_id"]), evidence)
    with pytest.raises(gate.BlockReleaseError, match="prior arm"):
        _claim(schedule, block[2], tmp_path)
    with pytest.raises(gate.BlockReleaseError, match="already has"):
        _claim(schedule, block[1], tmp_path, label="retry-attempt-two")
    evidence.write_bytes(evidence.read_bytes() + b" ")
    with pytest.raises(gate.BlockReleaseError, match="evidence bytes changed"):
        _claim(schedule, _block(schedule, 2)[1], tmp_path)


@pytest.mark.parametrize("terminal_status", ["completed", "truncated"])
def test_external_failure_retry_unblocks_successor_only_after_terminal(
    schedule: dict[str, Any], tmp_path: Path, terminal_status: str,
) -> None:
    block = _block(schedule, 1)
    run = block[1]
    _, first_release = _claim(schedule, run, tmp_path)
    _terminal(schedule, run, first_release, tmp_path, status="external_failure")
    with pytest.raises(gate.BlockReleaseError, match="already claimed"):
        gate.claim_release(schedule, run["run_id"], tmp_path / "gate", first_release,
                           attempt_number=2)
    claim, retry_release = _claim(schedule, run, tmp_path, attempt_number=2)
    assert claim["attempt_number"] == 2
    assert claim["release_dir"] != str(first_release)
    with pytest.raises(gate.BlockReleaseError, match="prior arm"):
        _claim(schedule, block[2], tmp_path)

    retry_release.mkdir(mode=0o700)
    _populate_release(schedule, run, retry_release, attempt_number=2)
    publication = _publish(schedule, run, retry_release, tmp_path, attempt_number=2)
    verified = gate.verify_claim(schedule, run["run_id"], tmp_path / "gate",
                                 retry_release, attempt_number=2)
    assert verified["claim_sha256"] == claim["claim_sha256"]
    assert verified["publication_sha256"] == publication["publication_sha256"]
    with pytest.raises(gate.BlockReleaseError, match="prior arm"):
        _claim(schedule, block[2], tmp_path)
    evidence = _evidence(schedule, run, retry_release, tmp_path, status=terminal_status,
                         attempt_number=2)
    terminal = gate.record_terminal(schedule, run["run_id"], tmp_path / "gate",
                                    terminal_status, _sha("trace-" + run["run_id"]), evidence,
                                    attempt_number=2)
    assert terminal["attempt_number"] == 2
    with pytest.raises(gate.BlockReleaseError, match="previous published external_failure"):
        _claim(schedule, run, tmp_path, attempt_number=3)
    _claim(schedule, block[2], tmp_path)


def test_retry_claim_cannot_publish_schema_one_release(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    run = _block(schedule, 1)[1]
    _, first_release = _claim(schedule, run, tmp_path)
    _terminal(schedule, run, first_release, tmp_path, status="external_failure")
    _, retry_release = _claim(schedule, run, tmp_path, attempt_number=2)
    retry_release.mkdir(mode=0o700)
    _populate_release(schedule, run, retry_release)
    state_file = tmp_path / "gate" / "state.json"
    before = state_file.read_bytes()
    with pytest.raises(gate.BlockReleaseError, match="publication claim or attempt"):
        _publish(schedule, run, retry_release, tmp_path, attempt_number=2)
    assert state_file.read_bytes() == before


def test_replay_rejects_rehashed_schema_one_publication_for_retry(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    run = _block(schedule, 1)[1]
    _, first_release = _claim(schedule, run, tmp_path)
    _terminal(schedule, run, first_release, tmp_path, status="external_failure")
    _, retry_release = _claim(schedule, run, tmp_path, attempt_number=2)
    retry_release.mkdir(mode=0o700)
    _populate_release(schedule, run, retry_release, attempt_number=2)
    _publish(schedule, run, retry_release, tmp_path, attempt_number=2)
    manifest_path = retry_release / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["schema"] = 1
    del manifest["attempt_number"]
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    state_file = tmp_path / "gate" / "state.json"
    state = json.loads(state_file.read_text())
    publication = state["events"][-1]
    publication["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    publication["event_sha256"] = gate._digest({
        key: value for key, value in publication.items() if key != "event_sha256"
    })
    state["head_sha256"] = publication["event_sha256"]
    state["state_sha256"] = gate._digest({
        key: value for key, value in state.items() if key != "state_sha256"
    })
    state_file.write_bytes(gate._canonical(state))
    with pytest.raises(gate.BlockReleaseError, match="publication claim or attempt"):
        gate.verify_claim(schedule, run["run_id"], tmp_path / "gate", retry_release,
                          attempt_number=2)


@pytest.mark.parametrize("status", ["completed", "truncated"])
def test_retry_after_resolved_attempt_is_rejected_without_state_change(
    schedule: dict[str, Any], tmp_path: Path, status: str,
) -> None:
    run = _block(schedule, 1)[1]
    _, release = _claim(schedule, run, tmp_path)
    _terminal(schedule, run, release, tmp_path, status=status)
    state_file = tmp_path / "gate" / "state.json"
    before = state_file.read_bytes()
    with pytest.raises(gate.BlockReleaseError, match="previous published external_failure"):
        _claim(schedule, run, tmp_path, attempt_number=2)
    assert state_file.read_bytes() == before


def test_external_failure_keeps_block_open_without_resolved_retry(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    for order in range(1, 5):
        run = _block(schedule, order)[1]
        _, release = _claim(schedule, run, tmp_path)
        _terminal(schedule, run, release, tmp_path, status="external_failure")
    with pytest.raises(gate.BlockReleaseError, match="four blocks"):
        _claim(schedule, _block(schedule, 5)[1], tmp_path)


def test_explicit_nonretryable_stop_releases_open_block_slot_but_not_successor(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    failed: list[tuple[dict[str, Any], Path, dict[str, Any]]] = []
    for order in range(1, 5):
        run = _block(schedule, order)[1]
        _, release = _claim(schedule, run, tmp_path)
        terminal, _ = _terminal(schedule, run, release, tmp_path,
                                status="external_failure")
        failed.append((run, release, terminal))
    with pytest.raises(gate.BlockReleaseError, match="four blocks"):
        _claim(schedule, _block(schedule, 5)[1], tmp_path)
    run, release, terminal = failed[0]
    reason = "Provider revoked this model permanently"
    evidence = _stop_evidence(schedule, run, release, terminal, tmp_path,
                              reason=reason)
    stopped = gate.stop_block(schedule, run["run_id"], tmp_path / "gate", reason,
                              evidence)
    assert stopped["block_id"] == run["block_id"]
    assert stopped["attempt_number"] == 1
    with pytest.raises(gate.BlockReleaseError, match="block is stopped"):
        _claim(schedule, run, tmp_path, attempt_number=2)
    with pytest.raises(gate.BlockReleaseError, match="block is stopped"):
        _claim(schedule, _block(schedule, 1)[2], tmp_path)
    with pytest.raises(gate.BlockReleaseError, match="already has a nonretryable stop"):
        gate.stop_block(schedule, run["run_id"], tmp_path / "gate", reason, evidence)
    _claim(schedule, _block(schedule, 5)[1], tmp_path)


def test_stop_requires_latest_failure_and_exact_reason_evidence(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    run = _block(schedule, 1)[1]
    _, first_release = _claim(schedule, run, tmp_path)
    first_terminal, _ = _terminal(schedule, run, first_release, tmp_path,
                                  status="external_failure")
    reason = "Provider account cannot be restored"
    evidence = _stop_evidence(schedule, run, first_release, first_terminal,
                              tmp_path, reason=reason)
    state_file = tmp_path / "gate" / "state.json"
    before = state_file.read_bytes()
    with pytest.raises(gate.BlockReleaseError, match="stop evidence reason differs"):
        gate.stop_block(schedule, run["run_id"], tmp_path / "gate",
                        "Different reason", evidence)
    assert state_file.read_bytes() == before
    malformed = json.loads(evidence.read_text())
    malformed["incident_sha256"] = _sha("wrong incident")
    evidence.write_bytes(gate._canonical(malformed))
    with pytest.raises(gate.BlockReleaseError, match="stop evidence incident_sha256 differs"):
        gate.stop_block(schedule, run["run_id"], tmp_path / "gate", reason, evidence)
    assert state_file.read_bytes() == before
    _claim(schedule, run, tmp_path, attempt_number=2)
    with pytest.raises(gate.BlockReleaseError, match="latest published external_failure"):
        gate.stop_block(schedule, run["run_id"], tmp_path / "gate", reason, evidence)


def test_replay_rejects_rehashed_claim_after_stopped_block(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    run = _block(schedule, 1)[1]
    _, release = _claim(schedule, run, tmp_path)
    terminal, _ = _terminal(schedule, run, release, tmp_path,
                            status="external_failure")
    reason = "Nonretryable provider failure"
    evidence = _stop_evidence(schedule, run, release, terminal, tmp_path,
                              reason=reason)
    gate.stop_block(schedule, run["run_id"], tmp_path / "gate", reason, evidence)
    state_file = tmp_path / "gate" / "state.json"
    state = json.loads(state_file.read_text())
    forged = gate._event(gate._event_body(
        run, schedule["schedule_sha256"], str(tmp_path / "forged-retry"),
        state, "claim", 2,
    ))
    state_file.write_bytes(gate._canonical(gate._append(state, forged)))
    before = state_file.read_bytes()
    with pytest.raises(gate.BlockReleaseError, match="block is stopped"):
        _claim(schedule, _block(schedule, 2)[1], tmp_path)
    assert state_file.read_bytes() == before


def test_ten_retry_slots_are_consumed_by_claims_even_when_latest_is_pending(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    run = _block(schedule, 1)[1]
    for attempt in range(1, 11):
        _, release = _claim(schedule, run, tmp_path, attempt_number=attempt)
        _terminal(schedule, run, release, tmp_path, status="external_failure",
                  attempt_number=attempt)
    pending, pending_release = _claim(schedule, run, tmp_path, attempt_number=11)
    assert pending["attempt_number"] == 11
    state_file = tmp_path / "gate" / "state.json"
    claims = [event for event in json.loads(state_file.read_text())["events"]
              if event["kind"] == "claim" and event["attempt_number"] > 1]
    assert len(claims) == 10
    last_terminal, _ = _terminal(schedule, run, pending_release, tmp_path,
                                 status="external_failure", attempt_number=11)
    before = state_file.read_bytes()
    with pytest.raises(gate.BlockReleaseError, match="ten study-wide retry slots"):
        _claim(schedule, run, tmp_path, attempt_number=12)
    assert state_file.read_bytes() == before
    reason = "Retry budget exhausted after provider failures"
    evidence = _stop_evidence(schedule, run, pending_release, last_terminal,
                              tmp_path, reason=reason, attempt_number=11)
    assert gate.stop_block(schedule, run["run_id"], tmp_path / "gate", reason,
                           evidence, attempt_number=11)["attempt_number"] == 11


def test_four_active_releases_and_fifth_denied(schedule: dict[str, Any], tmp_path: Path) -> None:
    for order in range(1, 5):
        run = _block(schedule, order)[1]
        _, release = _claim(schedule, run, tmp_path)
        release.mkdir(mode=0o700)
        _populate_release(schedule, run, release)
        _publish(schedule, run, release, tmp_path)
    with pytest.raises(gate.BlockReleaseError, match="four releases"):
        _claim(schedule, _block(schedule, 5)[1], tmp_path)


def test_four_open_blocks_limit_survives_first_arm_terminals(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    for order in range(1, 5):
        run = _block(schedule, order)[1]
        _, release = _claim(schedule, run, tmp_path)
        _terminal(schedule, run, release, tmp_path)
    with pytest.raises(gate.BlockReleaseError, match="four blocks"):
        _claim(schedule, _block(schedule, 5)[1], tmp_path)
    for position in (2, 3):
        run = _block(schedule, 1)[position]
        _, release = _claim(schedule, run, tmp_path)
        _terminal(schedule, run, release, tmp_path)
    _claim(schedule, _block(schedule, 5)[1], tmp_path)


def test_two_processes_compete_for_one_run(schedule: dict[str, Any], tmp_path: Path) -> None:
    run = _block(schedule, 1)[1]
    schedule_file = tmp_path / "schedule.json"
    schedule_file.write_text(json.dumps(schedule), encoding="utf-8")
    code = """
import json, sys
sys.path.insert(0, sys.argv[1])
from local_block_release_gate import BlockReleaseError, claim_release
schedule = json.loads(open(sys.argv[2], encoding='utf-8').read())
sys.stdin.readline()
try:
    claim_release(schedule, sys.argv[3], sys.argv[4], sys.argv[5])
except BlockReleaseError as exc:
    print('denied:' + str(exc), flush=True)
else:
    print('claimed', flush=True)
"""
    children = [subprocess.Popen(
        [sys.executable, "-c", code, str(SCRIPTS), str(schedule_file),
         run["run_id"], str(tmp_path / "gate"), str(tmp_path / f"release-{index}")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    ) for index in range(2)]
    for child in children:
        assert child.stdin is not None
        child.stdin.write("\n")
        child.stdin.flush()
    results = [child.communicate(timeout=20) for child in children]
    assert [child.returncode for child in children] == [0, 0]
    assert sum(output.strip() == "claimed" for output, _ in results) == 1
    assert sum(output.startswith("denied:") for output, _ in results) == 1
    assert [error for _, error in results] == ["", ""]
    state = json.loads((tmp_path / "gate" / "state.json").read_text())
    assert [event["kind"] for event in state["events"]] == ["claim"]
    assert state["events"][0]["run_id"] == run["run_id"]


def test_two_processes_compete_for_one_retry(schedule: dict[str, Any], tmp_path: Path) -> None:
    run = _block(schedule, 1)[1]
    _, first_release = _claim(schedule, run, tmp_path)
    _terminal(schedule, run, first_release, tmp_path, status="external_failure")
    schedule_file = tmp_path / "schedule.json"
    schedule_file.write_text(json.dumps(schedule), encoding="utf-8")
    code = """
import json, sys
sys.path.insert(0, sys.argv[1])
from local_block_release_gate import BlockReleaseError, claim_release
schedule = json.loads(open(sys.argv[2], encoding='utf-8').read())
sys.stdin.readline()
try:
    claim_release(schedule, sys.argv[3], sys.argv[4], sys.argv[5], attempt_number=2)
except BlockReleaseError as exc:
    print('denied:' + str(exc), flush=True)
else:
    print('claimed', flush=True)
"""
    children = [subprocess.Popen(
        [sys.executable, "-c", code, str(SCRIPTS), str(schedule_file),
         run["run_id"], str(tmp_path / "gate"), str(tmp_path / f"retry-{index}")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    ) for index in range(2)]
    for child in children:
        assert child.stdin is not None
        child.stdin.write("\n")
        child.stdin.flush()
    results = [child.communicate(timeout=20) for child in children]
    assert [child.returncode for child in children] == [0, 0]
    assert sum(output.strip() == "claimed" for output, _ in results) == 1
    assert sum(output.startswith("denied:") for output, _ in results) == 1
    assert [error for _, error in results] == ["", ""]
    state = json.loads((tmp_path / "gate" / "state.json").read_text())
    retry_claims = [event for event in state["events"]
                    if event["kind"] == "claim" and event["attempt_number"] == 2]
    assert len(retry_claims) == 1


def test_hold_claim_prevents_terminal_writer_until_runtime_leaves(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    run = _block(schedule, 1)[1]
    _, release = _claim(schedule, run, tmp_path)
    release.mkdir(mode=0o700)
    _populate_release(schedule, run, release)
    _publish(schedule, run, release, tmp_path)
    evidence = _evidence(schedule, run, release, tmp_path)
    schedule_file = tmp_path / "schedule.json"
    schedule_file.write_text(json.dumps(schedule), encoding="utf-8")
    code = """
import json, sys
sys.path.insert(0, sys.argv[1])
from local_block_release_gate import record_terminal
schedule = json.loads(open(sys.argv[2], encoding='utf-8').read())
print('ready', flush=True)
record_terminal(schedule, sys.argv[3], sys.argv[4], 'completed', sys.argv[5], sys.argv[6])
print('closed', flush=True)
"""
    with gate.hold_claim(schedule, run["run_id"], tmp_path / "gate", release) as held:
        assert held["attempt_number"] == 1
        child = subprocess.Popen(
            [sys.executable, "-c", code, str(SCRIPTS), str(schedule_file),
             run["run_id"], str(tmp_path / "gate"), _sha("trace-" + run["run_id"]),
             str(evidence)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "ready"
        ready, _, _ = select.select([child.stdout], [], [], 0.2)
        assert not ready
        assert child.poll() is None
    stdout, stderr = child.communicate(timeout=20)
    assert child.returncode == 0, stderr
    assert stdout.strip() == "closed"
    with pytest.raises(gate.BlockReleaseError, match="already has a terminal"):
        gate.verify_claim(schedule, run["run_id"], tmp_path / "gate", release)


def test_replay_rejects_rehashed_skipped_retry_attempt(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    run = _block(schedule, 1)[1]
    _, first_release = _claim(schedule, run, tmp_path)
    _terminal(schedule, run, first_release, tmp_path, status="external_failure")
    _claim(schedule, run, tmp_path, attempt_number=2)
    state_file = tmp_path / "gate" / "state.json"
    state = json.loads(state_file.read_text())
    retry_claim = state["events"][-1]
    retry_claim["attempt_number"] = 3
    retry_claim["event_sha256"] = gate._digest({
        key: value for key, value in retry_claim.items() if key != "event_sha256"
    })
    state["head_sha256"] = retry_claim["event_sha256"]
    state["state_sha256"] = gate._digest({
        key: value for key, value in state.items() if key != "state_sha256"
    })
    state_file.write_bytes(gate._canonical(state))
    before = state_file.read_bytes()
    with pytest.raises(gate.BlockReleaseError, match="previous published external_failure"):
        _claim(schedule, _block(schedule, 2)[1], tmp_path)
    assert state_file.read_bytes() == before


@pytest.mark.parametrize("damage", ["truncated", "symlink", "fifo", "rogue", "pending"])
def test_damaged_or_partial_registry_fails_closed(
    schedule: dict[str, Any], tmp_path: Path, damage: str,
) -> None:
    _claim(schedule, _block(schedule, 1)[1], tmp_path)
    state = tmp_path / "gate" / "state.json"
    if damage == "truncated":
        state.write_text('{"schema":', encoding="utf-8")
    elif damage == "symlink":
        state.rename(tmp_path / "saved-state")
        state.symlink_to(tmp_path / "saved-state")
    elif damage == "fifo":
        state.unlink()
        os.mkfifo(state)
    elif damage == "rogue":
        (tmp_path / "gate" / "extra").write_text("unexplained", encoding="utf-8")
    else:
        (tmp_path / "gate" / ".pending.json").write_text("pending", encoding="utf-8")
    with pytest.raises(gate.BlockReleaseError):
        _claim(schedule, _block(schedule, 2)[1], tmp_path)


def test_last_directory_fsync_fault_restores_pending_marker(
    schedule: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = tmp_path / "gate"
    with pytest.raises(gate.BlockReleaseError, match="earlier block"):
        _claim(schedule, _block(schedule, 2)[1], tmp_path)
    actual_fsync = os.fsync
    count = 0

    def fail_last_fsync(fd: int) -> None:
        nonlocal count
        count += 1
        if count == 5:
            raise OSError(errno.EIO, "injected final directory fsync failure")
        actual_fsync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(gate.os, "fsync", fail_last_fsync)
        with pytest.raises(gate.BlockReleaseError, match="durably recorded"):
            _claim(schedule, _block(schedule, 1)[1], tmp_path)
    assert count >= 5
    assert (registry / ".pending.json").exists()
    with pytest.raises(gate.BlockReleaseError, match="pending"):
        _claim(schedule, _block(schedule, 2)[1], tmp_path)


def test_existing_empty_or_deleted_registry_does_not_restart_schedule(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    root = tmp_path / "gate"
    root.mkdir(mode=0o700)
    with pytest.raises(gate.BlockReleaseError, match="missing"):
        _claim(schedule, _block(schedule, 1)[1], tmp_path)
    root.rmdir()
    _claim(schedule, _block(schedule, 1)[1], tmp_path)
    (root / "state.json").unlink()
    with pytest.raises(gate.BlockReleaseError, match="missing"):
        _claim(schedule, _block(schedule, 1)[1], tmp_path, label="second")
    with pytest.raises(gate.BlockReleaseError, match="must be explicit"):
        gate.claim_release(schedule, _block(schedule, 1)[1]["run_id"], None,
                           tmp_path / "third")


def test_malformed_event_identity_is_controlled_failure(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    _claim(schedule, _block(schedule, 1)[1], tmp_path)
    state_file = tmp_path / "gate" / "state.json"
    state = json.loads(state_file.read_text())
    event = state["events"][0]
    event["run_id"] = ["unhashable"]
    event["event_sha256"] = gate._digest({key: value for key, value in event.items()
                                           if key != "event_sha256"})
    state["head_sha256"] = event["event_sha256"]
    state["state_sha256"] = gate._digest({key: value for key, value in state.items()
                                         if key != "state_sha256"})
    state_file.write_bytes(gate._canonical(state))
    with pytest.raises(gate.BlockReleaseError, match="invalid types"):
        _claim(schedule, _block(schedule, 2)[1], tmp_path)


def test_cli_verifies_and_records_declared_terminal(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    run = _block(schedule, 1)[1]
    _, release = _claim(schedule, run, tmp_path)
    release.mkdir(mode=0o700)
    _populate_release(schedule, run, release)
    _publish(schedule, run, release, tmp_path)
    schedule_file = tmp_path / "schedule.json"
    schedule_file.write_text(json.dumps(schedule), encoding="utf-8")
    schedule_file.chmod(0o600)
    verify = subprocess.run(
        [sys.executable, str(SCRIPTS / "local_block_release_gate.py"), "verify",
         str(schedule_file), run["run_id"], str(tmp_path / "gate"), str(release)],
        capture_output=True, text=True, check=False,
    )
    assert verify.returncode == 0, verify.stderr
    assert json.loads(verify.stdout)["claim_sha256"]
    evidence = _evidence(schedule, run, release, tmp_path)
    terminal = subprocess.run(
        [sys.executable, str(SCRIPTS / "local_block_release_gate.py"), "terminal",
         str(schedule_file), run["run_id"], str(tmp_path / "gate"), "completed",
         _sha("trace-" + run["run_id"]), str(evidence)],
        capture_output=True, text=True, check=False,
    )
    assert terminal.returncode == 0, terminal.stderr
    assert json.loads(terminal.stdout)["status"] == "completed"
    again = subprocess.run(
        [sys.executable, str(SCRIPTS / "local_block_release_gate.py"), "verify",
         str(schedule_file), run["run_id"], str(tmp_path / "gate"), str(release)],
        capture_output=True, text=True, check=False,
    )
    assert again.returncode == 2
    assert "already has a terminal" in again.stderr


def test_cli_attempt_flag_verifies_and_records_retry(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    run = _block(schedule, 1)[1]
    _, first_release = _claim(schedule, run, tmp_path)
    _terminal(schedule, run, first_release, tmp_path, status="external_failure")
    _, retry_release = _claim(schedule, run, tmp_path, attempt_number=2)
    retry_release.mkdir(mode=0o700)
    _populate_release(schedule, run, retry_release, attempt_number=2)
    _publish(schedule, run, retry_release, tmp_path, attempt_number=2)
    schedule_file = tmp_path / "schedule.json"
    schedule_file.write_text(json.dumps(schedule), encoding="utf-8")
    schedule_file.chmod(0o600)
    verify = subprocess.run(
        [sys.executable, str(SCRIPTS / "local_block_release_gate.py"), "verify",
         str(schedule_file), run["run_id"], str(tmp_path / "gate"), str(retry_release),
         "--attempt-number", "2"],
        capture_output=True, text=True, check=False,
    )
    assert verify.returncode == 0, verify.stderr
    assert json.loads(verify.stdout)["attempt_number"] == 2
    evidence = _evidence(schedule, run, retry_release, tmp_path, attempt_number=2)
    terminal = subprocess.run(
        [sys.executable, str(SCRIPTS / "local_block_release_gate.py"), "terminal",
         str(schedule_file), run["run_id"], str(tmp_path / "gate"), "completed",
         _sha("trace-" + run["run_id"]), str(evidence), "--attempt", "2"],
        capture_output=True, text=True, check=False,
    )
    assert terminal.returncode == 0, terminal.stderr
    assert json.loads(terminal.stdout)["attempt_number"] == 2


def test_cli_explicit_stop_binds_latest_failed_retry(
    schedule: dict[str, Any], tmp_path: Path,
) -> None:
    run = _block(schedule, 1)[1]
    _, first_release = _claim(schedule, run, tmp_path)
    _terminal(schedule, run, first_release, tmp_path, status="external_failure")
    _, retry_release = _claim(schedule, run, tmp_path, attempt_number=2)
    retry_terminal, _ = _terminal(schedule, run, retry_release, tmp_path,
                                  status="external_failure", attempt_number=2)
    reason = "Provider account permanently disabled"
    evidence = _stop_evidence(schedule, run, retry_release, retry_terminal,
                              tmp_path, reason=reason, attempt_number=2)
    schedule_file = tmp_path / "schedule.json"
    schedule_file.write_text(json.dumps(schedule), encoding="utf-8")
    schedule_file.chmod(0o600)
    stopped = subprocess.run(
        [sys.executable, str(SCRIPTS / "local_block_release_gate.py"), "stop",
         str(schedule_file), run["run_id"], str(tmp_path / "gate"), reason,
         str(evidence), "--attempt-number", "2"],
        capture_output=True, text=True, check=False,
    )
    assert stopped.returncode == 0, stopped.stderr
    assert json.loads(stopped.stdout)["attempt_number"] == 2
    with pytest.raises(gate.BlockReleaseError, match="block is stopped"):
        _claim(schedule, run, tmp_path, attempt_number=3)
