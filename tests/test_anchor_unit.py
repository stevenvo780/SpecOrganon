"""The external ledger anchor rejects locally coherent history replacement."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from pathlib import Path

import pytest

from specorganon import anchor, approval


@pytest.fixture
def anchored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    case = tmp_path / "case"
    case.mkdir()
    data = {
        "project": {"case_id": str(uuid.uuid4()), "title": "Control", "approval_policy": "signed"},
        "events": [{"hash": "1" * 64}, {"hash": "2" * 64}],
    }
    entry = {
        "path": approval.case_path(case),
        "project_sha256": approval.project_fingerprint(data["project"]),
        "seq": 2,
        "head_hash": "2" * 64,
    }
    payload = {"schema": 1, "cases": {data["project"]["case_id"]: entry}}
    anchor_file = tmp_path / "ledger-anchors.json"
    anchor_file.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("ORGANON_LEDGER_ANCHORS_FILE", str(anchor_file))
    return data, case, anchor_file, payload


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_unconfigured_verifier_is_no_op(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORGANON_LEDGER_ANCHORS_FILE", raising=False)
    assert anchor.verify({}, tmp_path / "missing") is None


def test_valid_external_anchor(anchored) -> None:
    data, case, _, _ = anchored
    assert anchor.verify(data, case) is None


def test_empty_ledger_uses_zero_head(anchored) -> None:
    data, case, anchor_file, payload = anchored
    empty = deepcopy(data)
    empty["events"] = []
    payload["cases"][data["project"]["case_id"]].update(seq=0, head_hash="0" * 64)
    _write(anchor_file, payload)
    assert anchor.verify(empty, case) is None


def test_truncated_ledger_is_rejected(anchored) -> None:
    data, case, _, _ = anchored
    truncated = deepcopy(data)
    truncated["events"].pop()
    with pytest.raises(ValueError, match="sequence"):
        anchor.verify(truncated, case)


@pytest.mark.parametrize("replacement", [
    [{"hash": "1" * 64}, {"hash": "2" * 64}, {"hash": "3" * 64}],
    [{"hash": "1" * 64}, {"hash": "f" * 64}],
])
def test_forged_longer_or_forked_history_is_rejected(anchored, replacement) -> None:
    data, case, _, _ = anchored
    forged = deepcopy(data)
    forged["events"] = replacement
    with pytest.raises(ValueError, match="sequence|head"):
        anchor.verify(forged, case)


def test_registered_path_cannot_downgrade_to_fixture(anchored, monkeypatch: pytest.MonkeyPatch) -> None:
    data, case, _, _ = anchored
    downgraded = deepcopy(data)
    downgraded["project"]["approval_policy"] = "fixture"
    monkeypatch.setenv("ORGANON_ALLOW_FIXTURES", "1")
    with pytest.raises(ValueError, match="metadata"):
        anchor.verify(downgraded, case)


def test_registered_path_requires_case_identity(anchored) -> None:
    data, case, _, _ = anchored
    replaced = deepcopy(data)
    replaced["project"]["case_id"] = str(uuid.uuid4())
    with pytest.raises(ValueError, match="identity"):
        anchor.verify(replaced, case)


def test_missing_anchor_file_fails_closed(anchored) -> None:
    data, case, anchor_file, _ = anchored
    anchor_file.unlink()
    with pytest.raises(ValueError, match="cannot read"):
        anchor.verify(data, case)


def test_anchor_file_inside_case_is_rejected(anchored, monkeypatch: pytest.MonkeyPatch) -> None:
    data, case, anchor_file, _ = anchored
    nested = case / "anchors.json"
    nested.write_bytes(anchor_file.read_bytes())
    monkeypatch.setenv("ORGANON_LEDGER_ANCHORS_FILE", str(nested))
    with pytest.raises(ValueError, match="outside the case directory"):
        anchor.verify(data, case)


def test_stale_anchor_file_fails_closed(anchored) -> None:
    data, case, anchor_file, payload = anchored
    entry = payload["cases"][data["project"]["case_id"]]
    entry.update(seq=1, head_hash="1" * 64)
    _write(anchor_file, payload)
    with pytest.raises(ValueError, match="sequence"):
        anchor.verify(data, case)


def test_rollback_to_previously_valid_anchor_file_fails_closed(anchored) -> None:
    data, case, anchor_file, payload = anchored
    old_payload = deepcopy(payload)
    old_entry = old_payload["cases"][data["project"]["case_id"]]
    old_entry.update(seq=1, head_hash="1" * 64)
    _write(anchor_file, old_payload)
    old_data = deepcopy(data)
    old_data["events"].pop()
    anchor.verify(old_data, case)
    _write(anchor_file, payload)
    anchor.verify(data, case)
    _write(anchor_file, old_payload)
    with pytest.raises(ValueError, match="sequence"):
        anchor.verify(data, case)


def test_unregistered_signed_case_fails_closed(anchored, tmp_path: Path) -> None:
    data, _, _, _ = anchored
    other = tmp_path / "unregistered-signed"
    other.mkdir()
    with pytest.raises(ValueError, match="not registered"):
        anchor.verify(data, other)


def test_unregistered_fixture_requires_explicit_opt_in(anchored, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data, _, _, _ = anchored
    other = tmp_path / "unregistered-fixture"
    other.mkdir()
    fixture = deepcopy(data)
    fixture["project"]["approval_policy"] = "fixture"
    monkeypatch.delenv("ORGANON_ALLOW_FIXTURES", raising=False)
    with pytest.raises(ValueError, match="not registered"):
        anchor.verify(fixture, other)
    monkeypatch.setenv("ORGANON_ALLOW_FIXTURES", "1")
    assert anchor.verify(fixture, other) is None


@pytest.mark.parametrize("invalid", [
    {"schema": 2, "cases": {}},
    {"schema": True, "cases": {}},
    {"schema": 1, "cases": []},
])
def test_malformed_anchor_file_fails_closed(anchored, invalid) -> None:
    data, case, anchor_file, _ = anchored
    _write(anchor_file, invalid)
    with pytest.raises(ValueError, match="malformed"):
        anchor.verify(data, case)


def test_invalid_json_fails_closed(anchored) -> None:
    data, case, anchor_file, _ = anchored
    anchor_file.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot read"):
        anchor.verify(data, case)


def test_duplicate_canonical_paths_fail_closed(anchored) -> None:
    data, case, anchor_file, payload = anchored
    payload["cases"][str(uuid.uuid4())] = deepcopy(next(iter(payload["cases"].values())))
    _write(anchor_file, payload)
    with pytest.raises(ValueError, match="duplicate canonical path"):
        anchor.verify(data, case)


def test_anchor_path_must_be_canonical(anchored) -> None:
    data, case, anchor_file, payload = anchored
    payload["cases"][data["project"]["case_id"]]["path"] = str(case / ".." / case.name)
    _write(anchor_file, payload)
    with pytest.raises(ValueError, match="not canonical"):
        anchor.verify(data, case)


@pytest.mark.parametrize("field,value", [
    ("path", "relative/case"),
    ("project_sha256", "invalid"),
    ("seq", True),
    ("head_hash", "invalid"),
])
def test_malformed_entry_fails_closed(anchored, field, value) -> None:
    data, case, anchor_file, payload = anchored
    payload["cases"][data["project"]["case_id"]][field] = value
    _write(anchor_file, payload)
    with pytest.raises(ValueError, match="malformed"):
        anchor.verify(data, case)


def test_duplicate_json_keys_fail_closed(anchored) -> None:
    data, case, anchor_file, _ = anchored
    anchor_file.write_text('{"schema":1,"schema":1,"cases":{}}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate key"):
        anchor.verify(data, case)


@pytest.mark.parametrize("configured", ["", "relative/anchors.json"])
def test_anchor_configuration_requires_absolute_path(anchored, monkeypatch: pytest.MonkeyPatch, configured) -> None:
    data, case, _, _ = anchored
    monkeypatch.setenv("ORGANON_LEDGER_ANCHORS_FILE", configured)
    with pytest.raises(ValueError, match="absolute path"):
        anchor.verify(data, case)
