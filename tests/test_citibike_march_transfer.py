"""Exercise the March 2024 mobility evidence through the public CLI."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "cases" / "citibike_march2024" / "seed.json"
OUTPUT = ROOT / "experiments" / "development" / "citibike_sample_status_2026-09-27.json"
SCRIPT = ROOT / "cases" / "citibike" / "analyze_sample_status.py"
JUNE_LEDGER = ROOT / "cases" / "citibike" / "organon.json"
MARCH_LEDGER = ROOT / "cases" / "citibike_march2024" / "organon.json"
RECORD = ROOT / "experiments" / "development" / "citibike_march_ledger_2026-09-27.json"
CLI = Path(sys.executable).with_name("organon")


def _cli(env: dict[str, str], *args: str) -> dict:
    result = subprocess.run(
        [str(CLI), *args], cwd=ROOT, env=env,
        text=True, capture_output=True, check=True, timeout=15,
    )
    return json.loads(result.stdout)


def test_march_evidence_is_traced_and_keeps_june_case_intact(tmp_path: Path) -> None:
    june_before = JUNE_LEDGER.read_bytes()
    assert hashlib.sha256(june_before).hexdigest() == (
        "204b8094474113a52f2d271f5ae10e174979c66628e1753dc5df8e2b1e682678"
    )
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    output_hash = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    script_hash = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    assert output_hash == "352ef988b91813912d15c465ba1e597c76eedc1461c33b29afc928c9f88c7ee1"
    assert script_hash == "e384b43d24bf2b928c1772c7781e38c8abbbface8f92bfb98dc5ad804b3bf949"
    published_result = json.loads(OUTPUT.read_text(encoding="utf-8"))
    assert published_result["criterion_5"] == "not_assessed"
    assert published_result["snapshot_row_service"] == {
        "denominator": 1809036,
        "rental_enabled_with_bike": 1725248,
        "return_enabled_with_dock": 1682386,
    }

    env = os.environ.copy()
    for key in ("ORGANON_APPROVERS_FILE", "ORGANON_ALLOW_FIXTURES", "ORGANON_LEDGER_ANCHORS_FILE"):
        env.pop(key, None)
    case = tmp_path / "march2024"
    seeded = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "seed_case.py"), str(SEED), str(case)],
        cwd=ROOT, env=env, text=True, capture_output=True, check=True, timeout=15,
    )
    assert json.loads(seeded.stdout) == {
        "revision": len(seed["items"]), "items": len(seed["items"]),
        "ready_phases": ["frame"],
    }
    state = _cli(env, "status", str(case))
    assert state["project"]["approval_policy"] == "signed"
    assert "marzo de 2024" in state["project"]["title"]
    assert "junio de 2026" in state["items"]["b_sample"]["text"]
    assert not any(item["stale"] or item["issues"] for item in state["items"].values())

    for item_id, locator, count in (
        ("e_eligible", "quality.conservative_dock_rows", 1809036),
        ("e_rental", "snapshot_row_service.rental_enabled_with_bike", 1725248),
        ("e_return", "snapshot_row_service.return_enabled_with_dock", 1682386),
        ("e_excluded", "quality.excluded_rows", 3512),
        ("e_gaps", "gaps_over_30_minutes", 37),
    ):
        item = state["items"][item_id]
        data = item["data"]
        assert data["origin"] == "derived"
        assert data["scope"] == "citibike_sample_march_2024"
        assert data["source"] == str(OUTPUT.relative_to(ROOT))
        assert data["sha256_source"] == output_hash
        assert data["sha256_script"] == script_hash
        assert data["locator"] == locator and data["value"] == count
        trace = _cli(env, "trace", str(case), item_id)
        ancestor_ids = {ancestor["id"] for ancestor in trace["ancestors"]}
        assert {"p_access", "q_rows", "h_distinct", "pr_reanalysis"} <= ancestor_ids

    frame = _cli(env, "gate", str(case), "frame")
    assert frame["ready"] and not frame["accepted"]
    critique = _cli(env, "gate", str(case), "critique")
    assert not critique["ready"] and not critique["accepted"]
    assert any("n_scope requires a verified human approval" in blocker
               for blocker in critique["blockers"])
    observe = _cli(env, "gate", str(case), "observe")
    assert not observe["accepted"]
    assert observe["blockers"] == ["previous phase is not currently accepted"]
    assert JUNE_LEDGER.read_bytes() == june_before


def test_included_march_ledger_keeps_approval_boundary() -> None:
    env = os.environ.copy()
    for key in ("ORGANON_APPROVERS_FILE", "ORGANON_ALLOW_FIXTURES", "ORGANON_LEDGER_ANCHORS_FILE"):
        env.pop(key, None)
    ledger = json.loads(MARCH_LEDGER.read_text(encoding="utf-8"))
    assert len(ledger["events"]) == 24
    review, advance = ledger["events"][-2:]
    assert review["kind"] == "phase_review"
    assert review["actor"] != ledger["project"]["created_by"]
    assert review["payload"]["phase"] == "frame"
    assert review["payload"]["verdict"] == "accept"
    assert advance["kind"] == "phase_advance"
    assert advance["payload"]["review_seq"] == review["seq"]

    state = _cli(env, "status", str(MARCH_LEDGER.parent))
    assert state["revision"] == 24 and len(state["items"]) == 22
    assert not any(item["stale"] or item["issues"] for item in state["items"].values())
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    seed_items = {item["id"]: item for item in seed["items"]}
    archived = json.loads(OUTPUT.read_text(encoding="utf-8"))
    for item_id in ("e_eligible", "e_rental", "e_return", "e_excluded", "e_gaps"):
        item = state["items"][item_id]
        expected = seed_items[item_id]
        assert item["text"] == expected["text"]
        assert item["data"] == expected["data"]
        assert set(item["deps"]) == set(expected["refs"])
        value = archived
        for key in item["data"]["locator"].split("."):
            value = value[key]
        assert item["data"]["value"] == value
    assert state["items"]["e_archive"]["data"]["sha256_source"] == archived["input_sha256"]

    record = json.loads(RECORD.read_text(encoding="utf-8"))
    for key, source in (
        ("goal_sha256", ROOT / "GOAL.md"),
        ("seed_sha256", SEED),
        ("ledger_sha256", MARCH_LEDGER),
        ("june_2026_ledger_sha256_unchanged", JUNE_LEDGER),
        ("derived_result_sha256", OUTPUT),
        ("analysis_script_sha256", SCRIPT),
    ):
        assert record[key] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert record["source_parquet_sha256"] == archived["input_sha256"]
    assert record["criterion_5"] == "not_assessed"
    assert state["phases"]["frame"]["accepted"]
    assert state["phases"]["frame"]["independent_review"]
    assert not state["phases"]["critique"]["accepted"]
    assert state["phases"]["critique"]["blockers"] == [
        "n_scope requires a verified human approval"
    ]
    assert not state["phases"]["observe"]["accepted"]
